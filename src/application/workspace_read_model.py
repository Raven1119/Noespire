"""The single deep read module behind the workspace REST contract (spec §5).

Combines the application-owned index entry with research-core state
(``ObligationRegistry``, ``FactGraph``, ``attempts/*.json``, and — in
scaffold mode — ``scaffold.json``; in v3 mode — ``proof_graph.json``,
``dynamic_run/``, ``refutations/``, ``graph_patches/``) and the
application-owned execution log (``_execution_log.jsonl``) into the one
aggregate the workspace UI needs. Read-only: this module never writes core
files or the execution log.

Execution modes (proof_execution.py) are projected additively: legacy
workspaces keep every previously existing key and semantic; scaffold-mode
workspaces gain ``execution_mode``, ``proof_structure``, per-attempt
``obligation_id`` / ``scaffold_node_id``, and ``last_execution_failure``.
v3 (``DYNAMIC_PROOF_V3``) workspaces gain ``dynamic`` (run phase /
stop_reason / frontier), ``proof_graph`` (obligations, AND/OR routes with
backend-derived states, frontiers), ``refutations``, and ``patches``
(applied GraphPatch history) — all PROJECTIONS of search state and verified
truth computed here; the frontend never infers AND/OR, route viability, or
frontiers, and never parses ids. ``obligation`` / ``proof_structure`` are
null in v3 mode; ``dynamic`` / ``proof_graph`` are null in the older modes.

``running_phase_hint`` is a UI heuristic inferred from attempt-artifact field
presence; it is NOT a backend execution phase and must never be presented as
one (spec §2, ADR-0003). v3 mode instead exposes the authoritative persisted
run phase under ``dynamic.phase``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation
from research.proof_graph import ProofGraph
from research.refutation import RefutationStore
from research.scaffold import ProofScaffold

from .problem_index import (
    ProblemEntry,
    ProblemIndex,
    read_execution_events,
    workspace_last_activity,
)
from .proof_execution import (
    DYNAMIC_PROOF_V3,
    LEGACY_DIRECT,
    STATIC_SCAFFOLD,
    detect_execution_mode,
    is_problem_solved,
    read_run_state,
)

_EXECUTION_FAILURE_STAGES = {
    "ARCHITECT_ERROR",
    "ARCHITECT_INVALID",
    "SYSTEM_ERROR",
    "RUNTIME_ERROR",
    "INTERRUPTED",
}


def build_read_model(
    workspaces_root: Path,
    problem_id: str,
    execution_service=None,
) -> dict:
    """The spec §5 aggregate for one problem. Raises KeyError if unknown.

    ``execution_service`` (optional) is the live-execution table: status is
    RUNNING iff a live execution exists for the problem (authoritative,
    spec §5) or an obligation is RUNNING in the pre-recovery window.
    """
    index = ProblemIndex(workspaces_root)
    entry = index.get(problem_id)
    problem_dir = index.root / problem_id
    mode = detect_execution_mode(problem_dir, problem_id)
    if mode == DYNAMIC_PROOF_V3:
        return _v3_read_model(entry, problem_dir, execution_service)
    obligation = _root_obligation(problem_dir, problem_id)
    events = _read_events(problem_dir)
    attempts = [
        _project_attempt(raw, events, problem_id)
        for raw in _read_attempts(problem_dir)
    ]

    # Recovery binds per attempt (spec §7.2): only a RECOVERED_INTERRUPTED
    # naming the LATEST attempt suppresses live-RUNNING; earlier recovery
    # history must not affect a new attempt of the same problem.
    latest_recovered = bool(attempts) and attempts[-1]["failure_class"] == "interrupted"
    live_execution = execution_service is not None and execution_service.is_running(problem_id)
    if mode == LEGACY_DIRECT:
        status = _status(obligation, latest_recovered, live_execution)
    else:
        status = _scaffold_status(problem_dir, problem_id, attempts, live_execution)
    target_fact = None
    supporting_closure: List[dict] = []
    if status == "SOLVED":
        graph = FactGraph(problem_dir)
        if mode == LEGACY_DIRECT:
            fact = graph.get_fact(obligation.resolved_by_fact_id or "")
        else:
            scaffold = ProofScaffold(problem_dir / "scaffold.json")
            fact = graph.get_fact(
                scaffold.get(scaffold.target_node_id).resolved_by_fact_id or ""
            )
        target_fact = _fact_payload(fact)
        supporting_closure = [
            _fact_payload(item) for item in graph.supporting_closure(fact.fact_id)
        ]
    model = {
        "problem_id": entry.problem_id,
        "statement": entry.statement,
        "status": status,
        "display_status": _display_status(status, attempts),
        "derived_from": entry.derived_from,
        "archived": entry.archived,
        "execution_mode": mode,
        "obligation": (
            _obligation_payload(obligation) if mode == LEGACY_DIRECT else None
        ),
        "proof_structure": (
            _proof_structure(problem_dir, problem_id, attempts, live_execution)
            if mode == STATIC_SCAFFOLD
            else None
        ),
        # v3-only keys: null/empty in the older modes (stable REST shape).
        "dynamic": None,
        "proof_graph": None,
        "refutations": [],
        "patches": [],
        "attempts": attempts,
        "target_fact": target_fact,
        "supporting_closure": supporting_closure,
        "running_phase_hint": _running_phase_hint(status, attempts),
        "last_execution_failure": _last_execution_failure(events),
    }
    if status == "RUNNING":
        model["live"] = {
            "running": True,
            "current_attempt_id": _current_attempt_id(
                execution_service, live_execution, problem_id, attempts
            ),
        }
    return model


def _current_attempt_id(
    execution_service,
    live_execution: bool,
    problem_id: str,
    attempts: List[dict],
) -> Optional[str]:
    """The live execution's attempt (None until _start_attempt writes it);
    in the pre-recovery window, the residual RUNNING attempt."""
    if live_execution:
        current = execution_service.current_attempt_id(problem_id)
        if current is not None:
            return current
    if attempts and attempts[-1]["verdict"] == "RUNNING":
        return attempts[-1]["attempt_id"]
    return None


def build_problem_list(workspaces_root: Path, execution_service=None) -> List[dict]:
    """The spec §6 list payload, in ProblemIndex (last-activity) order."""
    index = ProblemIndex(workspaces_root)
    return [
        _summarize(index.root / entry.problem_id, entry, execution_service)
        for entry in index.list()
    ]


def _summarize(problem_dir: Path, entry: ProblemEntry, execution_service=None) -> dict:
    mode = detect_execution_mode(problem_dir, entry.problem_id)
    live_execution = (
        execution_service is not None and execution_service.is_running(entry.problem_id)
    )
    if mode == DYNAMIC_PROOF_V3:
        v3_attempts = _v3_attempts(problem_dir, None)
        status = _v3_status(problem_dir, entry.problem_id, live_execution)
        activity = workspace_last_activity(problem_dir)
        return {
            "problem_id": entry.problem_id,
            "statement": entry.statement,
            "status": status,
            "display_status": _display_status(status, v3_attempts),
            "derived_from": entry.derived_from,
            "archived": entry.archived,
            "attempt_count": len(v3_attempts),
            "last_activity": (
                datetime.fromtimestamp(activity, timezone.utc).isoformat()
                if activity is not None
                else None
            ),
        }
    obligation = _root_obligation(problem_dir, entry.problem_id)
    events = _read_events(problem_dir)
    attempts = [_project_attempt(raw, events, entry.problem_id) for raw in _read_attempts(problem_dir)]
    latest_recovered = bool(attempts) and attempts[-1]["failure_class"] == "interrupted"
    if mode == LEGACY_DIRECT:
        status = _status(obligation, latest_recovered, live_execution)
    else:
        status = _scaffold_status(problem_dir, entry.problem_id, attempts, live_execution)
    activity = workspace_last_activity(problem_dir)
    return {
        "problem_id": entry.problem_id,
        "statement": entry.statement,
        "status": status,
        "display_status": _display_status(status, attempts),
        "derived_from": entry.derived_from,
        "archived": entry.archived,
        "attempt_count": len(attempts),
        "last_activity": (
            datetime.fromtimestamp(activity, timezone.utc).isoformat()
            if activity is not None
            else None
        ),
    }


def _display_status(status: str, attempts: List[dict]) -> str:
    """Obligation truth stays OPEN; a latest ERROR attempt only changes display."""
    if status == "OPEN" and attempts and attempts[-1]["verdict"] == "ERROR":
        return "ERROR"
    return status


def _running_phase_hint(status: str, attempts: List[dict]) -> Optional[str]:
    """UI heuristic only (see module docstring); None when not RUNNING."""
    if status != "RUNNING" or not attempts:
        return None
    latest = attempts[-1]
    if latest["candidate"] is None:
        return "generating"
    if latest["verifier"] is None:
        return "checking"
    return None


def _fact_payload(fact) -> dict:
    return {
        "fact_id": fact.fact_id,
        "statement": fact.statement,
        "proof": fact.proof,
        "predecessors": list(fact.predecessors),
    }


def _root_obligation(problem_dir: Path, problem_id: str) -> Optional[ProofObligation]:
    path = problem_dir / "obligations.json"
    if not path.is_file():
        return None
    try:
        return ObligationRegistry(path).get(f"root:{problem_id}")
    except KeyError:
        return None


def _obligation_payload(obligation: Optional[ProofObligation]) -> Optional[dict]:
    if obligation is None:
        return None
    return {
        "obligation_id": obligation.obligation_id,
        "goal": obligation.goal,
        "premises": list(obligation.premises),
        "route_id": obligation.route_id,
        "status": obligation.status.value,
        "resolved_by_fact_id": obligation.resolved_by_fact_id,
    }


def _read_attempts(problem_dir: Path) -> List[dict]:
    attempts_dir = problem_dir / "attempts"
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(attempts_dir.glob("attempt-*.json"))
    ]


def _read_events(problem_dir: Path) -> List[dict]:
    """Execution-log events via the single shared tolerant reader (only an
    unparseable FINAL line is skipped; corrupt non-final lines raise)."""
    return read_execution_events(problem_dir)


def _project_attempt(raw: dict, events: List[dict], problem_id: str) -> dict:
    finished = next(
        (
            event
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
            and event.get("attempt_id") == raw["attempt_id"]
        ),
        None,
    )
    obligation_id = raw.get("obligation_id")
    payload = {
        "attempt_id": raw["attempt_id"],
        "verdict": raw["verdict"],
        "failure_class": _failure_class(raw, finished, events),
        "candidate": raw["candidate_artifact"],
        "verifier": raw["verifier_artifact"],
        "error": raw["error"],
        "obligation_id": obligation_id,
        "scaffold_node_id": _scaffold_node_id(obligation_id, problem_id),
        # v3-only keys: null in the older modes (stable REST shape).
        "outcome": None,
        "route_id": None,
        "obligation_goal": None,
        "fact_id": None,
        "refutation_id": None,
        "started_at": finished.get("started_at") if finished else None,
        "finished_at": finished.get("finished_at") if finished else None,
    }
    if payload["failure_class"] == "interrupted":
        payload["verifier_called"] = _interrupted_verifier_called(raw["attempt_id"], events)
    return payload


def _scaffold_node_id(obligation_id: Optional[str], problem_id: str) -> Optional[str]:
    """``scaffold:<problem_id>:<node>`` → ``<node>``; anything else → None.
    Server-side parsing only — the frontend never parses obligation ids."""
    prefix = f"scaffold:{problem_id}:"
    if obligation_id and obligation_id.startswith(prefix):
        return obligation_id[len(prefix):]
    return None


def _all_obligations(problem_dir: Path) -> List[ProofObligation]:
    path = problem_dir / "obligations.json"
    if not path.is_file():
        return []
    return ObligationRegistry(path).list()


def _latest_attempt_for(obligation_id: str, attempts: List[dict]) -> Optional[dict]:
    """Attempts are filename-ordered, so the last match is the latest."""
    matching = [a for a in attempts if a["obligation_id"] == obligation_id]
    return matching[-1] if matching else None


def _scaffold_status(
    problem_dir: Path,
    problem_id: str,
    attempts: List[dict],
    live_execution: bool,
) -> str:
    """Scaffold-mode status: SOLVED iff the target node's resolved Fact
    exists (fail closed on corruption); RUNNING iff a live execution exists
    or a RUNNING obligation's latest attempt is not covered by a
    RECOVERED_INTERRUPTED naming it (same pre-recovery rule as legacy);
    else OPEN."""
    if is_problem_solved(problem_dir, problem_id, STATIC_SCAFFOLD):
        return "SOLVED"
    if live_execution:
        return "RUNNING"
    for obligation in _all_obligations(problem_dir):
        if obligation.status is not ObligationStatus.RUNNING:
            continue
        latest = _latest_attempt_for(obligation.obligation_id, attempts)
        if latest is None or latest["failure_class"] != "interrupted":
            return "RUNNING"
    return "OPEN"


def _proof_structure(
    problem_dir: Path,
    problem_id: str,
    attempts: List[dict],
    live_execution: bool,
) -> Optional[dict]:
    """Search-state projection over scaffold.json (never an authority):
    per-node state VERIFIED (resolved Fact) > RUNNING (its obligation's
    latest attempt is RUNNING and live-or-unrecovered, same rule as status)
    > BLOCKED (latest attempt FAIL/ERROR) > READY (dependencies resolved)
    > PLANNED. None when no scaffold has been materialized yet."""
    scaffold_path = problem_dir / "scaffold.json"
    if not scaffold_path.is_file():
        return None
    scaffold = ProofScaffold(scaffold_path)
    obligations = {
        obligation.obligation_id: obligation
        for obligation in _all_obligations(problem_dir)
    }
    nodes = []
    for node in scaffold.list_nodes():
        obligation_id = f"scaffold:{problem_id}:{node.node_id}"
        obligation = obligations.get(obligation_id)
        latest = _latest_attempt_for(obligation_id, attempts)
        nodes.append(
            {
                "node_id": node.node_id,
                "statement": node.goal,
                "dependency_node_ids": sorted(node.depends_on),
                "resolved_fact_id": node.resolved_by_fact_id,
                "latest_attempt_id": latest["attempt_id"] if latest else None,
                "state": _node_state(scaffold, node, obligation, latest, live_execution),
            }
        )
    return {"target_node_id": scaffold.target_node_id, "nodes": nodes}


def _node_state(scaffold, node, obligation, latest_attempt, live_execution: bool) -> str:
    if node.resolved_by_fact_id:
        return "VERIFIED"
    if (
        obligation is not None
        and obligation.status is ObligationStatus.RUNNING
        and latest_attempt is not None
        and latest_attempt["verdict"] == "RUNNING"
        and (live_execution or latest_attempt["failure_class"] != "interrupted")
    ):
        return "RUNNING"
    if latest_attempt is not None and latest_attempt["verdict"] in ("FAIL", "ERROR"):
        return "BLOCKED"
    if all(scaffold.get(dependency).resolved_by_fact_id for dependency in node.depends_on):
        return "READY"
    return "PLANNED"


def _last_execution_failure(events: List[dict]) -> Optional[dict]:
    """The last ATTEMPT_FINISHED, if it is an execution-level failure
    (attempt_id null): architect-stage failures and pre-attempt
    runtime/interrupted failures — the latter were previously invisible in
    legacy mode. A later per-attempt finish supersedes it (→ None)."""
    finishes = [event for event in events if event.get("kind") == "ATTEMPT_FINISHED"]
    if not finishes:
        return None
    last = finishes[-1]
    if last.get("attempt_id") is not None:
        return None
    if last.get("outcome_stage") not in _EXECUTION_FAILURE_STAGES:
        return None
    return {
        "outcome_stage": last["outcome_stage"],
        "error": last.get("error"),
        "finished_at": last.get("finished_at"),
    }


def _failure_class(raw: dict, finished: Optional[dict], events: List[dict]) -> Optional[str]:
    """Failure classification (spec §8.2). No log event means honest unknown."""
    if raw["verdict"] == "ERROR":
        return "runtime"
    if raw["verdict"] == "FAIL" and finished is not None:
        return {
            "CONTRACT_GUARD": "contract",
            "FRESH_VERIFIER_REJECT": "rejection",
        }.get(finished.get("outcome_stage"))
    if raw["verdict"] == "RUNNING" and _recovery_for(raw["attempt_id"], events) is not None:
        return "interrupted"
    return None


def _recovery_for(attempt_id: str, events: List[dict]) -> Optional[dict]:
    """The RECOVERED_INTERRUPTED naming this attempt (per-attempt binding, §7.2)."""
    return next(
        (
            event
            for event in events
            if event.get("kind") == "RECOVERED_INTERRUPTED"
            and event.get("attempt_id") == attempt_id
        ),
        None,
    )


def _interrupted_verifier_called(attempt_id: str, events: List[dict]) -> bool:
    """Whether the crashed execution behind an interrupted attempt ran the verifier.

    Correlation rule: the RECOVERED_INTERRUPTED naming the attempt carries the
    crashed execution's ``execution_id``; ``verifier_called`` is True iff an
    orphan VERIFIER_INVOKED — one whose execution has no ATTEMPT_FINISHED —
    shares that execution_id. (VERIFIER_INVOKED is appended before the real
    verifier call, spec §7.2, so the orphan proves the fresh verifier ran and
    its verdict was lost to the crash.) A recovery event without an
    ``execution_id``, or one whose orphan invocation cannot be attributed to
    the same execution, yields False — never a guess. Only called for attempts
    already classified ``interrupted``.
    """
    recovery = _recovery_for(attempt_id, events) or {}
    execution_id = recovery.get("execution_id")
    if execution_id is None:
        return False
    finished_ids = {
        event.get("execution_id")
        for event in events
        if event.get("kind") == "ATTEMPT_FINISHED"
    }
    return any(
        event.get("kind") == "VERIFIER_INVOKED"
        and event.get("execution_id") == execution_id
        and execution_id not in finished_ids
        for event in events
    )


def _status(
    obligation: Optional[ProofObligation],
    latest_recovered: bool,
    live_execution: bool = False,
) -> str:
    """RUNNING iff a live execution exists (in-memory table is authoritative,
    spec §5) or the obligation is RUNNING and the latest attempt is not
    covered by a RECOVERED_INTERRUPTED naming it (§7.2 per-attempt binding;
    the pre-recovery window)."""
    if obligation is None:
        return "RUNNING" if live_execution else "OPEN"
    if obligation.status is ObligationStatus.DISCHARGED:
        return "SOLVED"
    if live_execution:
        return "RUNNING"
    if obligation.status is ObligationStatus.RUNNING and not latest_recovered:
        return "RUNNING"
    return "OPEN"


# -- DYNAMIC_PROOF_V3 projection ---------------------------------------------
#
# All v3 graph semantics are computed here from the canonical core stores
# (ProofGraph / run state / attempt files / RefutationStore). The frontend
# receives derived states verbatim and never infers AND/OR, route
# viability, or frontiers itself. Core attempt files use the v3 ``outcome``
# schema; the projection maps them into the shared Attempt envelope
# (``verdict`` / ``failure_class``) so existing display plumbing keeps
# working, while preserving the raw ``outcome`` for precise v3 labels.

#: v3 attempt outcome → shared display verdict (read-model mapping only).
_V3_VERDICT = {
    "FACT_ADMITTED": "PASS",
    "REFUTATION_ADMITTED": "PASS",
    "PROOF_REJECTED": "FAIL",
    "COUNTEREXAMPLE_REJECTED": "FAIL",
    "NO_RESULT": "FAIL",
    "TIMEOUT": "ERROR",
    "ERROR": "ERROR",
    "INTERRUPTED": "RUNNING",
    "RUNNING": "RUNNING",
}

#: v3 attempt outcome → shared failure classification. NO_RESULT is
#: neither a verifier rejection nor a runtime error: the raw ``outcome``
#: carries it. FACT_ADMITTED / RUNNING have no failure class.
_V3_FAILURE_CLASS = {
    "PROOF_REJECTED": "rejection",
    "COUNTEREXAMPLE_REJECTED": "rejection",
    "TIMEOUT": "runtime",
    "ERROR": "runtime",
    "INTERRUPTED": "interrupted",
}


def _v3_read_model(
    entry: ProblemEntry, problem_dir: Path, execution_service=None
) -> dict:
    """The workspace aggregate for a DYNAMIC_PROOF_V3 workspace.

    Status: SOLVED iff the target obligation is DISCHARGED and its resolved
    Fact exists (fail closed on corruption); RUNNING iff a live execution
    holds the claim; otherwise OPEN — a crashed run (phase != STOPPED, no
    live execution) shows OPEN, with ``dynamic.phase`` telling the UI the
    run was interrupted and is resumable via Retry.
    """
    live_execution = execution_service is not None and execution_service.is_running(
        entry.problem_id
    )
    status = _v3_status(problem_dir, entry.problem_id, live_execution)
    graph = (
        ProofGraph(problem_dir)
        if (problem_dir / "proof_graph.json").is_file()
        else None
    )
    attempts = _v3_attempts(problem_dir, graph)
    state = read_run_state(problem_dir)
    model = {
        "problem_id": entry.problem_id,
        "statement": entry.statement,
        "status": status,
        "display_status": _display_status(status, attempts),
        "derived_from": entry.derived_from,
        "archived": entry.archived,
        "execution_mode": DYNAMIC_PROOF_V3,
        "obligation": None,
        "proof_structure": None,
        "dynamic": _dynamic_section(state),
        "proof_graph": _proof_graph_projection(graph, attempts) if graph else None,
        "refutations": _refutation_payloads(problem_dir),
        "patches": _patch_history(problem_dir),
        "attempts": attempts,
        "target_fact": None,
        "supporting_closure": [],
        # v3 exposes the authoritative persisted run phase instead.
        "running_phase_hint": None,
        "last_execution_failure": _last_execution_failure(_read_events(problem_dir)),
    }
    if status == "SOLVED":
        fact = FactGraph(problem_dir).get_fact(
            graph.obligation(graph.target_obligation_id).resolved_fact_id or ""
        )
        model["target_fact"] = _fact_payload(fact)
        model["supporting_closure"] = [
            _fact_payload(item) for item in graph.supporting_closure()
        ]
    if status == "RUNNING":
        model["live"] = {
            "running": True,
            "current_attempt_id": (
                execution_service.current_attempt_id(entry.problem_id)
                if live_execution
                else None
            ),
        }
    return model


def _v3_status(problem_dir: Path, problem_id: str, live_execution: bool) -> str:
    if is_problem_solved(problem_dir, problem_id, DYNAMIC_PROOF_V3):
        return "SOLVED"
    if live_execution:
        return "RUNNING"
    return "OPEN"


def _dynamic_section(state: Optional[dict]) -> Optional[dict]:
    """Persisted run state; None before the first execution."""
    if state is None:
        return None
    return {
        "run_id": state["run_id"],
        "phase": state["phase"],
        "stop_reason": state.get("stop_reason"),
        "error": state.get("error"),
        "frontier_obligation_id": state.get("frontier"),
    }


def _v3_attempts(problem_dir: Path, graph: Optional[ProofGraph]) -> List[dict]:
    """All v3 attempt records, filename-ordered (creation order).

    ``graph`` may be None (list summaries, corrupt-state tolerance is NOT
    intended — a present graph is always valid by ProofGraph load); goals
    then fall back to None rather than guessing."""
    goals = (
        {o.obligation_id: o.goal for o in graph.obligations()}
        if graph is not None
        else {}
    )
    attempts_dir = problem_dir / "attempts"
    return [
        _project_v3_attempt(
            json.loads(path.read_text(encoding="utf-8")), goals
        )
        for path in sorted(attempts_dir.glob("attempt-*.json"))
    ]


def _project_v3_attempt(raw: dict, goals: dict) -> dict:
    outcome = raw["outcome"]
    if outcome not in _V3_VERDICT:
        raise ValueError(f"unknown v3 attempt outcome: {outcome}")
    return {
        "attempt_id": raw["attempt_id"],
        "verdict": _V3_VERDICT[outcome],
        "outcome": outcome,
        "failure_class": _V3_FAILURE_CLASS.get(outcome),
        "candidate": raw.get("candidate"),
        "verifier": raw.get("verification"),
        "error": raw.get("reason") if outcome in ("TIMEOUT", "ERROR") else None,
        "obligation_id": raw.get("obligation_id"),
        "obligation_goal": goals.get(raw.get("obligation_id")),
        "route_id": raw.get("route_id"),
        "scaffold_node_id": None,
        "fact_id": raw.get("fact_id"),
        "refutation_id": raw.get("refutation_id"),
        "started_at": None,
        "finished_at": None,
    }


def _proof_graph_projection(graph: ProofGraph, attempts: List[dict]) -> dict:
    """Obligations, AND/OR routes with derived states, and live frontiers.

    Route ``derived_state`` (READY / WAITING / IMPOSSIBLE / EXHAUSTED) comes
    from ``ProofGraph.route_state``; ``frontiers`` from
    ``ProofGraph.frontiers``. Both are backend-computed authorities for
    display; neither admits mathematical truth.
    """
    latest: dict = {}
    for attempt in attempts:  # filename-ordered: last match is latest
        if attempt["obligation_id"]:
            latest[attempt["obligation_id"]] = attempt["attempt_id"]
    obligations = [
        {
            "obligation_id": obligation.obligation_id,
            "goal": obligation.goal,
            "context": obligation.context,
            "statement": obligation.statement,
            "truth_state": obligation.truth_state,
            "resolved_fact_id": obligation.resolved_fact_id,
            "resolved_route_id": obligation.resolved_route_id,
            "refutation_id": obligation.refutation_id,
            "latest_attempt_id": latest.get(obligation.obligation_id),
        }
        for obligation in graph.obligations()
    ]
    routes = []
    for obligation in graph.obligations():
        for route in graph.routes_for(obligation.obligation_id):
            routes.append(
                {
                    "route_id": route.route_id,
                    "target_obligation_id": route.target_obligation_id,
                    "prerequisite_obligation_ids": list(
                        route.prerequisite_obligation_ids
                    ),
                    "support_fact_ids": list(route.support_fact_ids),
                    "kind": route.kind,
                    "lifecycle": route.lifecycle,
                    "derived_state": graph.route_state(route.route_id),
                    "exhaustion_reason": route.exhaustion_reason,
                    "origin_patch_id": route.origin_patch_id,
                }
            )
    # Direct attempt routes first, then stable ids; never an inferred order.
    routes.sort(key=lambda r: (r["kind"] != "DIRECT", r["route_id"]))
    return {
        "target_obligation_id": graph.target_obligation_id,
        "obligations": obligations,
        "routes": routes,
        "frontiers": [asdict(f) for f in graph.frontiers()],
    }


def _refutation_payloads(problem_dir: Path) -> List[dict]:
    if not (problem_dir / "refutations").is_dir():
        return []
    return [
        {
            "refutation_id": refutation.refutation_id,
            "obligation_id": refutation.obligation_id,
            "goal": refutation.goal,
            "context": refutation.context,
            "counterexample": refutation.counterexample,
            "reason": refutation.verification_evidence.get("reason"),
        }
        for refutation in RefutationStore(problem_dir).list()
    ]


def _patch_history(problem_dir: Path) -> List[dict]:
    """Applied GraphPatches in step order (the durable application record).

    Sources: ``dynamic_run/steps/NNNNNN/patch.json`` for order and identity;
    ``graph_patches/<id>/approved.json`` for operator, target, and the child
    obligation goals. A PATCH_APPLIED result without its approved evidence
    violates the core contract and raises — never silently skipped.
    """
    steps = problem_dir / "dynamic_run" / "steps"
    if not steps.is_dir():
        return []
    patches = []
    for step_dir in sorted(p for p in steps.iterdir() if p.name.isdigit()):
        result_path = step_dir / "patch.json"
        if not result_path.is_file():
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("outcome") != "PATCH_APPLIED":
            continue
        approved = json.loads(
            (
                problem_dir
                / "graph_patches"
                / result["patch_id"]
                / "approved.json"
            ).read_text(encoding="utf-8")
        )
        patch = approved["patch"]
        patches.append(
            {
                "step": int(step_dir.name),
                "patch_id": result["patch_id"],
                "operator": patch["operator"],
                "target_obligation_id": patch["target_obligation_id"],
                "obligation_goals": [o["goal"] for o in patch["obligations"]],
            }
        )
    return patches
