"""N2U live two-stage failure-driven refinement driver (task card §2/§17).

Composition only — every stage is a frozen, already-verified component:

    NodeSolver failure / horizon
    -> N2S Strategy-only Strategist (StrategySketcher, K=1, §5)
    -> N2S SketchAuditor strategy quality gate (§6-§10)
    -> N2T StrategyBoundPatchBuilder (strategy/operator immutable, §11/§12)
    -> N2T FidelityAuditor as a PRE-APPLY live check (§12: drift is
       COMPILATION_INVALID and never reaches the auditor or the graph)
    -> frozen mechanical validator + fresh Structural Auditor
       (research.local_refinement.run_local_redecomposition, §13/§14)
    -> N2Q one-round bounded revision on REVISE (§15; never recurses)
    -> apply -> NodeSolver -> Verifier (truth boundary unchanged, §16)

No resampling (§24), no fixed operator fallback (§18), no new operator
(§25), no memory/checkpoint/context expansion (§3). One decision per
frontier identity, exactly as the frozen N2P/N2Q drivers.

``run_patch_stages`` is the single implementation of stages 2-5 (gate ->
builder -> fidelity -> mechanical/auditor -> one N2Q revision). The live
loop ``run_two_stage`` adds stage 1 (fresh sketcher), budgets, the solve
loop, journaling and evidence persistence; the controls in ``run_n2u.py``
drive the same function directly with frozen sketches, so the wiring under
test is identical in both (§20).

N2W additive seam (task card n2w §2/§25, experiment-local): when the caller
provides ``mechanical_repair`` + ``repair_locality``, a MECHANICAL_REJECT of
a strategy-gated patch triggers exactly ONE fresh diagnostic-guided repair
of the compiler output (v1), gated by a deterministic v1->v2 diff check and
an independent locality audit, then re-validated by the SAME frozen
validator and continued through the frozen auditor / N2Q one-round revision
path. With ``mechanical_repair=None`` (default) every code path is
byte-identical to the frozen N2U/N2V behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

from research.local_refinement import _build_context, run_local_redecomposition
from research.graph import FactGraph
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold, solve_scaffold

from driver import LongHorizonBudget, _attempt_count  # N2L (sys.path)

from strategist import PredecidedBuilder, compile_to_builder_result  # N2P
from treatment_driver import _OPERATION  # N2P

from sketch import build_sketch_audit_packet  # N2S
from patch_builder import _assemble_decision  # N2T

from reviser import OperatorDriftError, decision_view  # N2Q


# §28 stage failure attribution — every two-stage episode lands in exactly
# one of these classes.
EPISODE_OUTCOMES = (
    "STRATEGIST_TIMEOUT",
    "STRATEGIST_DECLINE",
    "STRATEGY_GATE_REJECT",
    "PATCH_BUILDER_TIMEOUT",
    "PATCH_COMPILATION_INVALID",
    "MECHANICAL_FAIL",
    "STRUCTURAL_AUDITOR_REJECT",
    "REVISION_FAILED",
    "PATCH_APPLIED",
    "SYSTEM_ERROR",
    # N2W (additive): one bounded mechanical repair per proposal (§2).
    "MECHANICAL_REPAIR_NOT_LOCAL",
    "MECHANICAL_REPAIR_INVALID",
    "MECHANICAL_REPAIR_TIMEOUT",
    "MECHANICAL_REPAIR_FAILED",
)

# §8: only these N2S strategy classes may enter the Patch Builder. The
# taxonomy itself is reused byte-identical from N2S (no rename, no reshape).
GATE_PASS_CLASSES = ("USEFUL_STRATEGY", "PLAUSIBLE_STRATEGY")


@dataclass(frozen=True)
class TwoStageRunResult:
    stop_reason: str
    # TARGET_SOLVED | STRATEGIST_TIMEOUT | STRATEGIST_DECLINE
    # | STRATEGY_GATE_REJECT | PATCH_BUILDER_TIMEOUT
    # | PATCH_COMPILATION_INVALID | MECHANICAL_FAIL
    # | STRUCTURAL_AUDITOR_REJECT | REVISION_FAILED | BUDGET_EXHAUSTED
    # | FRONTIER_EXHAUSTED | SYSTEM_ERROR
    # | MECHANICAL_REPAIR_NOT_LOCAL | MECHANICAL_REPAIR_INVALID (N2W)
    # | MECHANICAL_REPAIR_TIMEOUT | MECHANICAL_REPAIR_FAILED (N2W)
    solve_status: Optional[str]
    error: Optional[str] = None
    mutation_episodes: int = 0
    solver_attempts: int = 0
    strategist_calls: int = 0
    strategist_timeouts: int = 0
    gate_calls: int = 0
    gate_rejects: int = 0
    patch_builder_calls: int = 0
    patch_builder_timeouts: int = 0
    fidelity_calls: int = 0
    auditor_calls: int = 0
    revision_calls: int = 0
    repair_calls: int = 0  # N2W (counts against max_builder_proposals)
    repair_timeouts: int = 0  # N2W
    repair_locality_calls: int = 0  # N2W (counts against max_auditor_calls)
    horizon_handoffs: int = 0
    episodes: Tuple[dict, ...] = ()


def _sketch_view(sketch) -> dict:
    return {
        "obstruction": sketch.obstruction,
        "evidence": list(sketch.evidence),
        "mathematical_idea": sketch.mathematical_idea,
        "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
        "operator": sketch.operator,
        "why_current_route_is_exhausted": sketch.why_current_route_is_exhausted,
        "decline_reason": sketch.decline_reason,
        "candidate_claims": list(sketch.candidate_claims),
        "raw": sketch.raw,
    }


def run_patch_stages(
    problem_dir,
    *,
    problem_id: str,
    frontier: str,
    context,
    sketch,
    gate,
    fidelity,
    patch_builder,
    reviser,
    auditor_for,
    mechanical_repair=None,
    repair_locality=None,
) -> Tuple[dict, dict, Dict[str, int]]:
    """Stages 2-5 of the two-stage pipeline for one already-decided sketch.

    Returns ``(episode, evidence, counts)``. ``episode["outcome"]`` is one of
    ``EPISODE_OUTCOMES`` minus the strategist-stage classes; ``applied`` is
    true exactly when the (possibly revised) patch was applied to the
    workspace. ``counts`` reports the per-stage agent calls so callers can
    do their own budget accounting. Everything in this function is frozen
    component composition; the only N2U-specific behavior is the §12
    pre-apply fidelity check placement.

    N2W (additive): ``mechanical_repair`` and ``repair_locality`` must be
    provided together or not at all. When provided, a MECHANICAL_REJECT of
    the compiled patch triggers exactly one bounded diagnostic-guided repair
    before the episode goes terminal (n2w §2).
    """
    if (mechanical_repair is None) != (repair_locality is None):
        raise ValueError(
            "mechanical_repair and repair_locality must be provided together"
        )
    root = Path(problem_dir)
    counts = {
        "gate": 0,
        "gate_reject": 0,
        "builder": 0,
        "builder_timeout": 0,
        "fidelity": 0,
        "auditor": 0,
        "revision": 0,
        "repair": 0,
        "repair_timeout": 0,
        "repair_locality": 0,
    }
    episode: dict = {
        "blocked_node_id": frontier,
        "operator": sketch.operator,
        "facts_admitted_by_refinement": 0,
        "applied": False,
    }
    evidence: dict = {
        "sketch": _sketch_view(sketch),
        "gate_packet": build_sketch_audit_packet(context, sketch),
        "gate": None,
        "fidelity": None,
        "patch": None,
        "revision": None,
        "mechanical_repair": None,
    }
    facts_before = len(FactGraph(root).list_facts())

    def close(outcome: str) -> Tuple[dict, dict, Dict[str, int]]:
        episode["outcome"] = outcome
        episode["applied"] = outcome == "PATCH_APPLIED"
        # §16 truth boundary, measured: the refinement stages must admit no
        # Facts — only solve_scaffold's worker->verifier path may.
        episode["facts_admitted_by_refinement"] = (
            len(FactGraph(root).list_facts()) - facts_before
        )
        evidence["facts_admitted_by_refinement"] = episode[
            "facts_admitted_by_refinement"
        ]
        return episode, evidence, counts

    # --- Stage 2: N2S SketchAuditor strategy quality gate (§6-§8) ----------
    counts["gate"] += 1
    try:
        gate_result = dict(gate.audit(evidence["gate_packet"]))
    except Exception as error:
        episode["error"] = f"{type(error).__name__}: {error}"
        return close("SYSTEM_ERROR")
    evidence["gate"] = gate_result
    episode["strategy_class"] = gate_result.get("strategy_class")
    if gate_result.get("strategy_class") not in GATE_PASS_CLASSES:
        # §8/§10: a rejected strategy is terminal — no strategy revision.
        counts["gate_reject"] += 1
        return close("STRATEGY_GATE_REJECT")

    # --- Stage 3: N2T StrategyBoundPatchBuilder (§11) -----------------------
    counts["builder"] += 1
    try:
        patch = patch_builder.compile(context, sketch)
    except subprocess.TimeoutExpired as error:
        counts["builder_timeout"] += 1
        episode["error"] = f"TimeoutExpired: {error}"
        return close("PATCH_BUILDER_TIMEOUT")
    except Exception as error:
        episode["error"] = f"{type(error).__name__}: {error}"
        return close("SYSTEM_ERROR")
    evidence["patch"] = {
        "compilation_decline": patch.compilation_decline,
        "decline_reason": patch.decline_reason,
        "new_nodes": [dict(node) for node in patch.new_nodes],
        "raw": patch.raw,
        "builder_prompt": getattr(patch_builder, "last_prompt", None),
    }
    if patch.compilation_decline:
        # §7: the builder may decline; it may not switch strategy.
        return close("PATCH_COMPILATION_INVALID")
    try:
        decision = _assemble_decision(sketch, patch, blocked_node_id=frontier)
    except ValueError as error:
        episode["error"] = f"{type(error).__name__}: {error}"
        return close("SYSTEM_ERROR")

    # --- §12 pre-apply fidelity check (N2T FidelityAuditor, live) -----------
    counts["fidelity"] += 1
    try:
        fidelity_result = dict(fidelity.audit(sketch, patch.new_nodes, sketch.operator))
    except Exception as error:
        episode["error"] = f"{type(error).__name__}: {error}"
        return close("SYSTEM_ERROR")
    evidence["fidelity"] = fidelity_result
    episode["strategy_fidelity"] = fidelity_result.get("strategy_fidelity")
    episode["operator_check"] = fidelity_result.get("operator_check")
    if (
        fidelity_result.get("strategy_fidelity") == "STRATEGY_DRIFT"
        or fidelity_result.get("operator_check") == "OPERATOR_DRIFT"
    ):
        # §12: drift is COMPILATION_INVALID — never audited, never applied.
        return close("PATCH_COMPILATION_INVALID")

    # --- Stage 4/5: frozen mechanical validation + fresh auditor (§13/§14) --
    operation = _OPERATION[sketch.operator]
    try:
        builder_result = compile_to_builder_result(decision, blocked_node_id=frontier)
    except ValueError as error:
        episode["error"] = str(error)
        return close("MECHANICAL_FAIL")

    repair_record: Optional[dict] = None
    prompt_owner = patch_builder  # evidence: whose last_prompt produced the patch
    while True:
        outcome = run_local_redecomposition(
            root,
            problem_id=problem_id,
            blocked_node_id=frontier,
            builder=PredecidedBuilder(
                builder_result, getattr(prompt_owner, "last_prompt", None)
            ),
            auditor=auditor_for(operation),
            operation=operation,
        )
        if outcome.auditor is not None:
            counts["auditor"] += 1
        if outcome.outcome != "MECHANICAL_REJECT":
            break
        if repair_record is not None:
            # n2w §2: v2 still fails the SAME deterministic validator —
            # terminal, no v3.
            repair_record["mechanical_errors_v2"] = list(outcome.mechanical_errors)
            repair_record["outcome"] = "MECHANICAL_REPAIR_FAILED"
            episode["mechanical_repair"] = repair_record
            evidence["mechanical_repair"] = repair_record
            return close("MECHANICAL_REPAIR_FAILED")
        if mechanical_repair is None:
            break  # frozen N2U/N2V behavior: terminal MECHANICAL_FAIL below

        # --- N2W: one bounded diagnostic-guided repair (§2/§7-§13) ---------
        from repair import (  # N2W (sys.path) — lazy: inert unless wired
            repair_diff_check,
            repair_fields_changed,
        )

        def close_repair(outcome_name: str) -> Tuple[dict, dict, Dict[str, int]]:
            repair_record["outcome"] = outcome_name
            episode["mechanical_repair"] = repair_record
            evidence["mechanical_repair"] = repair_record
            return close(outcome_name)

        counts["repair"] += 1
        repair_record = {
            "mechanical_errors_v1": list(outcome.mechanical_errors),
        }
        try:
            v2_patch = mechanical_repair.repair(
                context, sketch, patch.new_nodes, outcome.mechanical_errors
            )
        except subprocess.TimeoutExpired as error:
            counts["repair_timeout"] += 1
            repair_record["error"] = f"TimeoutExpired: {error}"
            episode["error"] = repair_record["error"]
            return close_repair("MECHANICAL_REPAIR_TIMEOUT")
        except Exception as error:
            repair_record["error"] = f"{type(error).__name__}: {error}"
            episode["error"] = repair_record["error"]
            return close_repair("MECHANICAL_REPAIR_INVALID")
        repair_record["prompt"] = getattr(mechanical_repair, "last_prompt", None)
        repair_record["raw"] = v2_patch.raw
        if v2_patch.compilation_decline:
            # n2w §9: not locally repairable within the frozen strategy and
            # operator — terminal, never a silent re-plan.
            repair_record["not_local_reason"] = v2_patch.decline_reason
            return close_repair("MECHANICAL_REPAIR_NOT_LOCAL")
        repair_record["v2_nodes"] = [dict(node) for node in v2_patch.new_nodes]
        diff_errors = repair_diff_check(patch.new_nodes, v2_patch.new_nodes)
        if diff_errors:
            # n2w §8/§13: a repair edits the compiler output; an added,
            # dropped, or renamed obligation is re-planning. Deterministic
            # gate, before any model judgment.
            repair_record["diff_errors"] = list(diff_errors)
            return close_repair("MECHANICAL_REPAIR_INVALID")
        repair_record["fields_changed"] = repair_fields_changed(
            patch.new_nodes, v2_patch.new_nodes
        )
        counts["repair_locality"] += 1
        try:
            locality = dict(
                repair_locality.audit(
                    sketch, patch.new_nodes, v2_patch.new_nodes,
                    outcome.mechanical_errors,
                )
            )
        except Exception as error:
            repair_record["error"] = f"{type(error).__name__}: {error}"
            episode["error"] = repair_record["error"]
            return close_repair("MECHANICAL_REPAIR_INVALID")
        repair_record["locality"] = locality
        if locality.get("locality") != "LOCAL_MECHANICAL_REPAIR":
            # n2w §13: only a local mechanical repair may enter the second
            # validation; drift is invalid and never applied.
            return close_repair("MECHANICAL_REPAIR_INVALID")
        try:
            decision = _assemble_decision(sketch, v2_patch, blocked_node_id=frontier)
            builder_result = compile_to_builder_result(
                decision, blocked_node_id=frontier
            )
        except ValueError as error:
            repair_record["error"] = str(error)
            episode["error"] = repair_record["error"]
            return close_repair("MECHANICAL_REPAIR_INVALID")
        repair_record["outcome"] = "MECHANICAL_REPAIR_PASS"
        episode["mechanical_repair"] = repair_record
        evidence["mechanical_repair"] = repair_record
        prompt_owner = mechanical_repair
        # Loop: v2 through the SAME deterministic validator (n2w §22), then
        # the frozen auditor / N2Q one-round revision path below (§15).

    if repair_record is not None:
        repair_record.setdefault(
            "mechanical_errors_v2", list(outcome.mechanical_errors)
        )
    episode["mechanical_errors"] = list(outcome.mechanical_errors)
    episode["auditor_verdict"] = (
        outcome.auditor.verdict if outcome.auditor is not None else None
    )
    episode["auditor_reasons"] = (
        list(outcome.auditor.reasons) if outcome.auditor is not None else []
    )
    episode["child_node_ids"] = list(outcome.child_node_ids)

    if outcome.outcome == "APPLIED":
        return close("PATCH_APPLIED")
    if outcome.outcome == "MECHANICAL_REJECT":
        return close("MECHANICAL_FAIL")
    if outcome.outcome == "AUDITOR_REJECT":
        # §14: REJECT stays terminal — zero revision calls.
        return close("STRUCTURAL_AUDITOR_REJECT")
    if outcome.outcome != "AUDITOR_REVISE":
        episode["error"] = f"redecomposition {outcome.outcome}: {outcome.error}"
        return close("SYSTEM_ERROR")

    # --- §15: AUDITOR_REVISE -> exactly one N2Q bounded revision ------------
    counts["revision"] += 1
    revision_record: dict = {}
    try:
        revision = reviser.revise(context, decision, outcome.auditor.reasons)
    except OperatorDriftError as error:
        # §4/§16: a revision may not switch operator — invalid, terminal.
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = str(error)
        episode["revision"] = revision_record
        return close("REVISION_FAILED")
    except Exception as error:
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = f"{type(error).__name__}: {error}"
        episode["revision"] = revision_record
        return close("REVISION_FAILED")
    revision_record["repairable"] = revision.repairable
    revision_record["not_local_reason"] = revision.not_local_reason
    revision_record["raw"] = revision.raw
    revision_record["reviser_prompt"] = getattr(reviser, "last_prompt", None)

    if not revision.repairable:
        # §4: the feedback demands a new strategy — do not re-plan.
        revision_record["outcome"] = "REVISION_NOT_LOCAL"
        episode["revision"] = revision_record
        return close("REVISION_FAILED")

    try:
        v2_builder_result = compile_to_builder_result(
            revision.decision, blocked_node_id=frontier
        )
    except ValueError as error:
        # Includes operator drift (§4).
        revision_record["outcome"] = "REVISION_INVALID"
        revision_record["error"] = str(error)
        episode["revision"] = revision_record
        return close("REVISION_FAILED")

    revision_record["v2"] = decision_view(revision.decision)
    outcome2 = run_local_redecomposition(
        root,
        problem_id=problem_id,
        blocked_node_id=frontier,
        builder=PredecidedBuilder(
            v2_builder_result, getattr(reviser, "last_prompt", None)
        ),
        auditor=auditor_for(operation),  # fresh session (§15)
        operation=operation,
    )
    if outcome2.auditor is not None:
        counts["auditor"] += 1
    revision_record["mechanical_errors"] = list(outcome2.mechanical_errors)
    revision_record["auditor_v2_verdict"] = (
        outcome2.auditor.verdict if outcome2.auditor is not None else None
    )
    revision_record["child_node_ids"] = list(outcome2.child_node_ids)
    episode["revision"] = revision_record
    evidence["revision"] = revision_record

    if outcome2.outcome == "APPLIED":
        revision_record["outcome"] = "REVISION_PASS"
        return close("PATCH_APPLIED")
    if outcome2.outcome == "AUDITOR_REVISE":
        # §20: max_revision_rounds = 1 — a second REVISE is terminal.
        revision_record["outcome"] = "REVISION_STILL_REVISE"
        return close("REVISION_FAILED")
    if outcome2.outcome == "AUDITOR_REJECT":
        revision_record["outcome"] = "REVISION_REJECTED"
        return close("REVISION_FAILED")
    revision_record["outcome"] = "REVISION_INVALID"
    revision_record["error"] = (
        f"redecomposition v2 {outcome2.outcome}: {outcome2.error}"
    )
    return close("REVISION_FAILED")


def run_two_stage(
    problem_dir,
    *,
    problem,
    worker,
    verifier,
    sketcher,
    gate,
    fidelity,
    patch_builder,
    reviser,
    auditor_for,
    budget: LongHorizonBudget = LongHorizonBudget(),
    solver_config: NodeSolverConfig = NodeSolverConfig(max_attempts_per_obligation=3),
    author: str = "n2u",
    solve_error_handoff: Optional[Callable[[BaseException, Path], Optional[str]]] = None,
    mechanical_repair=None,
    repair_locality=None,
) -> TwoStageRunResult:
    root = Path(problem_dir)
    journal_path = root / "two_stage_journal.jsonl"
    evidence_dir = root / "two_stage"
    initial_attempts = _attempt_count(root)
    episodes: List[dict] = []
    mutation_episodes = 0
    strategist_calls = 0
    strategist_timeouts = 0
    gate_calls = 0
    gate_rejects = 0
    patch_builder_calls = 0
    patch_builder_timeouts = 0
    fidelity_calls = 0
    auditor_calls = 0
    revision_calls = 0
    repair_calls = 0
    repair_timeouts = 0
    repair_locality_calls = 0
    horizon_handoffs = 0
    solve_status: Optional[str] = None
    pending_frontier: Optional[str] = None
    decided: set = set()

    def finish(stop_reason: str, error: Optional[str] = None) -> TwoStageRunResult:
        return TwoStageRunResult(
            stop_reason=stop_reason,
            solve_status=solve_status,
            error=error,
            mutation_episodes=mutation_episodes,
            solver_attempts=_attempt_count(root) - initial_attempts,
            strategist_calls=strategist_calls,
            strategist_timeouts=strategist_timeouts,
            gate_calls=gate_calls,
            gate_rejects=gate_rejects,
            patch_builder_calls=patch_builder_calls,
            patch_builder_timeouts=patch_builder_timeouts,
            fidelity_calls=fidelity_calls,
            auditor_calls=auditor_calls,
            revision_calls=revision_calls,
            repair_calls=repair_calls,
            repair_timeouts=repair_timeouts,
            repair_locality_calls=repair_locality_calls,
            horizon_handoffs=horizon_handoffs,
            episodes=tuple(episodes),
        )

    def journal(event: dict) -> None:
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def persist_episode(episode: dict, evidence: dict) -> None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        payload = dict(evidence)
        payload["episode"] = episode["episode"]
        payload["blocked_node_id"] = episode["blocked_node_id"]
        payload["outcome"] = episode["outcome"]
        path = evidence_dir / f"episode-{episode['episode']:03d}-{episode['blocked_node_id']}.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        episode["evidence"] = str(path)

    while True:
        if pending_frontier is None:
            if _attempt_count(root) - initial_attempts >= budget.max_solver_attempts:
                return finish("BUDGET_EXHAUSTED")
            try:
                solved = solve_scaffold(
                    scaffold=ProofScaffold(root / "scaffold.json"),
                    problem=problem,
                    registry=ObligationRegistry(root / "obligations.json"),
                    graph=FactGraph(root),
                    author=author,
                    worker=worker,
                    verifier=verifier,
                    solver_config=solver_config,
                )
            except Exception as error:
                handoff_frontier = (
                    solve_error_handoff(error, root)
                    if solve_error_handoff is not None
                    else None
                )
                if handoff_frontier is None:
                    return finish(
                        "SYSTEM_ERROR", error=f"{type(error).__name__}: {error}"
                    )
                horizon_handoffs += 1
                pending_frontier = handoff_frontier
                journal(
                    {
                        "event": "horizon_handoff",
                        "blocked_node_id": handoff_frontier,
                        "error_type": type(error).__name__,
                        "timeout_seconds": getattr(error, "timeout", None),
                    }
                )
                continue
            solve_status = solved.status
            if solved.status == "SOLVED":
                return finish("TARGET_SOLVED")
            if _attempt_count(root) - initial_attempts >= budget.max_solver_attempts:
                return finish("BUDGET_EXHAUSTED")
            frontier = solved.advances[-1].node_id if solved.advances else None
            if frontier is None:
                return finish("FRONTIER_EXHAUSTED")
        else:
            frontier = pending_frontier
            pending_frontier = None

        if frontier in decided:
            # One decision per frontier identity (K=1, §4/§24).
            return finish("FRONTIER_EXHAUSTED")
        decided.add(frontier)

        proposal_calls = (
            strategist_calls + patch_builder_calls + revision_calls + repair_calls
        )
        audit_side_calls = (
            gate_calls + fidelity_calls + auditor_calls + repair_locality_calls
        )
        if (
            mutation_episodes >= budget.max_mutation_episodes
            or proposal_calls >= budget.max_builder_proposals
            or audit_side_calls >= budget.max_auditor_calls
        ):
            return finish("BUDGET_EXHAUSTED")

        context = _build_context(
            scaffold=ProofScaffold(root / "scaffold.json"),
            graph=FactGraph(root),
            registry=ObligationRegistry(root / "obligations.json"),
            problem_id=problem.problem_id,
            blocked_node_id=frontier,
            allowed_operation="SPLIT",  # label only; no operator preselected
        )

        # --- Stage 1: N2S Strategy-only Strategist (K=1, §5) ----------------
        strategist_calls += 1
        try:
            sketch = sketcher.strategize(context)
        except subprocess.TimeoutExpired as error:
            # §24: a strategist timeout stops this frontier — no resample.
            strategist_timeouts += 1
            episode = {
                "episode": len(episodes) + 1,
                "blocked_node_id": frontier,
                "operator": None,
                "facts_admitted_by_refinement": 0,
                "applied": False,
                "outcome": "STRATEGIST_TIMEOUT",
                "error": f"TimeoutExpired: {error}",
            }
            persist_episode(episode, {"sketch": None, "error": episode["error"]})
            episodes.append(episode)
            journal(episode)
            return finish("STRATEGIST_TIMEOUT")
        except Exception as error:
            episode = {
                "episode": len(episodes) + 1,
                "blocked_node_id": frontier,
                "operator": None,
                "facts_admitted_by_refinement": 0,
                "applied": False,
                "outcome": "SYSTEM_ERROR",
                "error": f"{type(error).__name__}: {error}",
            }
            persist_episode(episode, {"sketch": None, "error": episode["error"]})
            episodes.append(episode)
            journal(episode)
            return finish("SYSTEM_ERROR", error=episode["error"])

        if sketch.operator == "DECLINE":
            # §9/§17: respected decline — no gate, no builder, no revision,
            # no fallback escalation.
            episode = {
                "episode": len(episodes) + 1,
                "blocked_node_id": frontier,
                "operator": "DECLINE",
                "decline_reason": sketch.decline_reason,
                "facts_admitted_by_refinement": 0,
                "applied": False,
                "outcome": "STRATEGIST_DECLINE",
            }
            persist_episode(
                episode,
                {
                    "sketch": _sketch_view(sketch),
                    "sketch_prompt": getattr(sketcher, "last_prompt", None),
                    "gate": None,
                    "fidelity": None,
                    "patch": None,
                    "revision": None,
                },
            )
            episodes.append(episode)
            journal(episode)
            return finish("STRATEGIST_DECLINE")

        # --- Stages 2-5 via the single shared implementation ---------------
        episode, evidence, counts = run_patch_stages(
            root,
            problem_id=problem.problem_id,
            frontier=frontier,
            context=context,
            sketch=sketch,
            gate=gate,
            fidelity=fidelity,
            patch_builder=patch_builder,
            reviser=reviser,
            auditor_for=auditor_for,
            mechanical_repair=mechanical_repair,
            repair_locality=repair_locality,
        )
        gate_calls += counts["gate"]
        gate_rejects += counts["gate_reject"]
        patch_builder_calls += counts["builder"]
        patch_builder_timeouts += counts["builder_timeout"]
        fidelity_calls += counts["fidelity"]
        auditor_calls += counts["auditor"]
        revision_calls += counts["revision"]
        repair_calls += counts["repair"]
        repair_timeouts += counts["repair_timeout"]
        repair_locality_calls += counts["repair_locality"]

        episode["episode"] = len(episodes) + 1
        evidence["sketch_prompt"] = getattr(sketcher, "last_prompt", None)
        persist_episode(episode, evidence)
        episodes.append(episode)
        journal(episode)

        if episode["applied"]:
            mutation_episodes += 1
            continue
        outcome = episode["outcome"]
        if outcome == "SYSTEM_ERROR":
            return finish("SYSTEM_ERROR", error=episode.get("error"))
        # Every other terminal outcome is its own stop reason (§28
        # attribution): the run stops at the first frontier whose episode
        # fails, exactly like the frozen N2P/N2Q drivers.
        return finish(outcome, error=episode.get("error"))
