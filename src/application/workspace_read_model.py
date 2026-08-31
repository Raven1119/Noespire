"""The single deep read module behind the workspace REST contract (spec §5).

Combines the application-owned index entry with research-core state
(``ObligationRegistry``, ``FactGraph``, ``attempts/*.json``) and the
application-owned execution log (``_execution_log.jsonl``) into the one
aggregate the workspace UI needs. Read-only: this module never writes core
files or the execution log.

``running_phase_hint`` is a UI heuristic inferred from attempt-artifact field
presence; it is NOT a backend execution phase and must never be presented as
one (spec §2, ADR-0003).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation

from .problem_index import (
    EXECUTION_LOG_NAME,
    ProblemEntry,
    ProblemIndex,
    workspace_last_activity,
)


def build_read_model(
    workspaces_root: Path,
    problem_id: str,
    execution_service=None,
) -> dict:
    """The spec §5 aggregate for one problem. Raises KeyError if unknown.

    ``execution_service`` (optional) is the live-execution table: status is
    RUNNING iff a live execution exists for the problem (authoritative,
    spec §5) or the obligation is RUNNING in the pre-recovery window.
    """
    index = ProblemIndex(workspaces_root)
    entry = index.get(problem_id)
    problem_dir = index.root / problem_id
    obligation = _root_obligation(problem_dir, problem_id)
    events = _read_events(problem_dir)
    attempts = [
        _project_attempt(raw, events)
        for raw in _read_attempts(problem_dir)
    ]

    # Recovery binds per attempt (spec §7.2): only a RECOVERED_INTERRUPTED
    # naming the LATEST attempt suppresses live-RUNNING; earlier recovery
    # history must not affect a new attempt of the same problem.
    latest_recovered = bool(attempts) and attempts[-1]["failure_class"] == "interrupted"
    live_execution = execution_service is not None and execution_service.is_running(problem_id)
    status = _status(obligation, latest_recovered, live_execution)
    target_fact = None
    supporting_closure: List[dict] = []
    if status == "SOLVED":
        graph = FactGraph(problem_dir)
        fact = graph.get_fact(obligation.resolved_by_fact_id or "")
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
        "obligation": _obligation_payload(obligation),
        "attempts": attempts,
        "target_fact": target_fact,
        "supporting_closure": supporting_closure,
        "running_phase_hint": _running_phase_hint(status, attempts),
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
    obligation = _root_obligation(problem_dir, entry.problem_id)
    events = _read_events(problem_dir)
    attempts = [_project_attempt(raw, events) for raw in _read_attempts(problem_dir)]
    latest_recovered = bool(attempts) and attempts[-1]["failure_class"] == "interrupted"
    live_execution = (
        execution_service is not None and execution_service.is_running(entry.problem_id)
    )
    status = _status(obligation, latest_recovered, live_execution)
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
    """Execution-log events. Only an unparseable FINAL line is tolerated
    (crash mid-append artifact — skipped); a corrupt non-final line means
    genuine corruption and raises — the read model never guesses (§5)."""
    log = problem_dir / EXECUTION_LOG_NAME
    if not log.is_file():
        return []
    lines = [
        line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    events = []
    for position, line in enumerate(lines):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            if position == len(lines) - 1:
                continue
            raise
    return events


def _project_attempt(raw: dict, events: List[dict]) -> dict:
    finished = next(
        (
            event
            for event in events
            if event.get("kind") == "ATTEMPT_FINISHED"
            and event.get("attempt_id") == raw["attempt_id"]
        ),
        None,
    )
    payload = {
        "attempt_id": raw["attempt_id"],
        "verdict": raw["verdict"],
        "failure_class": _failure_class(raw, finished, events),
        "candidate": raw["candidate_artifact"],
        "verifier": raw["verifier_artifact"],
        "error": raw["error"],
        "started_at": finished.get("started_at") if finished else None,
        "finished_at": finished.get("finished_at") if finished else None,
    }
    if payload["failure_class"] == "interrupted":
        payload["verifier_called"] = _interrupted_verifier_called(raw["attempt_id"], events)
    return payload


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
