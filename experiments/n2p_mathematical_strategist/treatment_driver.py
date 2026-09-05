"""N2P treatment driver — unified-strategist long-horizon loop (§21-§24).

Same solve loop, budgets, and N2M horizon handoff as the N2L/N2M drivers,
but the fixed SPLIT→CUT→ALT escalation is replaced by exactly one
Mathematical Local Strategist decision per frontier (K=1, §5):

    failure (BLOCKED | LOCAL_HORIZON_EXHAUSTED)
        -> strategist diagnoses and chooses ONE operator (or DECLINE)
        -> frozen run_local_redecomposition executes that operator
           (mechanical validation -> fresh structural auditor -> apply)

§23: DECLINE stops the frontier — no fallback escalation (that would
degrade the treatment back into the control). §24: auditor REJECT/REVISE
stops without a second sample. Evaluation-only; not a product scheduler.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from research.graph import FactGraph
from research.local_refinement import _build_context, run_local_redecomposition
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold, solve_scaffold

from driver import LongHorizonBudget, _attempt_count  # N2L (sys.path)

from proposal_audit import build_audit_packet
from strategist import PredecidedBuilder, StrategistResult, compile_to_builder_result

_OPERATION = {
    "SPLIT": "split",
    "INSERT_CUT_SET": "insert_cut_set",
    "ADD_ALTERNATIVE_ROUTE": "add_alternative_route",
}


@dataclass(frozen=True)
class TreatmentResult:
    stop_reason: str
    # TARGET_SOLVED | STRATEGIST_DECLINED | STRATEGY_AUDIT_REJECTED
    # | MECHANICAL_REJECT | BUDGET_EXHAUSTED | FRONTIER_EXHAUSTED
    # | SYSTEM_ERROR
    solve_status: Optional[str]
    error: Optional[str] = None
    mutation_episodes: int = 0
    solver_attempts: int = 0
    strategist_calls: int = 0
    auditor_calls: int = 0
    horizon_handoffs: int = 0
    episodes: Tuple[dict, ...] = ()


def _persist_strategist_packet(
    root: Path, frontier: str, sequence: int, prompt: Optional[str], result: StrategistResult
) -> Path:
    directory = Path(root) / "strategist"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "blocked_node_id": frontier,
        "prompt": prompt,
        "raw": result.raw,
        "obstruction": result.obstruction,
        "evidence": list(result.evidence),
        "mathematical_idea": result.mathematical_idea,
        "why_this_reduces_difficulty": result.why_this_reduces_difficulty,
        "operator": result.operator,
        "why_current_route_is_exhausted": result.why_current_route_is_exhausted,
        "decline_reason": result.decline_reason,
    }
    path = directory / f"strategist-{sequence:03d}-{frontier}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def run_treatment(
    problem_dir,
    *,
    problem,
    worker,
    verifier,
    strategist,
    auditor_for,
    budget: LongHorizonBudget = LongHorizonBudget(),
    solver_config: NodeSolverConfig = NodeSolverConfig(max_attempts_per_obligation=3),
    author: str = "n2p",
    solve_error_handoff: Optional[Callable[[BaseException, Path], Optional[str]]] = None,
) -> TreatmentResult:
    root = Path(problem_dir)
    journal_path = root / "treatment_journal.jsonl"
    initial_attempts = _attempt_count(root)
    episodes: List[dict] = []
    mutation_episodes = 0
    strategist_calls = 0
    auditor_calls = 0
    horizon_handoffs = 0
    solve_status: Optional[str] = None
    pending_frontier: Optional[str] = None
    decided: set = set()

    def finish(stop_reason: str, error: Optional[str] = None) -> TreatmentResult:
        return TreatmentResult(
            stop_reason=stop_reason,
            solve_status=solve_status,
            error=error,
            mutation_episodes=mutation_episodes,
            solver_attempts=_attempt_count(root) - initial_attempts,
            strategist_calls=strategist_calls,
            auditor_calls=auditor_calls,
            horizon_handoffs=horizon_handoffs,
            episodes=tuple(episodes),
        )

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
                with journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "event": "horizon_handoff",
                                "blocked_node_id": handoff_frontier,
                                "error_type": type(error).__name__,
                                "timeout_seconds": getattr(error, "timeout", None),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                        )
                        + "\n"
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
            # One decision per frontier identity (K=1); a re-blocked,
            # already-decided frontier has no further move.
            return finish("FRONTIER_EXHAUSTED")
        decided.add(frontier)
        if (
            mutation_episodes >= budget.max_mutation_episodes
            or strategist_calls >= budget.max_builder_proposals
            or auditor_calls >= budget.max_auditor_calls
        ):
            return finish("BUDGET_EXHAUSTED")

        strategist_calls += 1
        try:
            context = _build_context(
                scaffold=ProofScaffold(root / "scaffold.json"),
                graph=FactGraph(root),
                registry=ObligationRegistry(root / "obligations.json"),
                problem_id=problem.problem_id,
                blocked_node_id=frontier,
                allowed_operation="SPLIT",  # label only; no operator preselected
            )
            decision = strategist.strategize(context)
        except Exception as error:
            # Schema/integration failure is a system error (N2M §9), never a
            # decline.
            return finish("SYSTEM_ERROR", error=f"{type(error).__name__}: {error}")
        packet = _persist_strategist_packet(
            root, frontier, strategist_calls, getattr(strategist, "last_prompt", None), decision
        )
        episode = {
            "episode": len(episodes) + 1,
            "blocked_node_id": frontier,
            "operator": decision.operator,
            "obstruction": decision.obstruction,
            "mathematical_idea": decision.mathematical_idea,
            "why_this_reduces_difficulty": decision.why_this_reduces_difficulty,
            "strategist_packet": str(packet),
            # Decision-time snapshot for the post-hoc independent audit —
            # never rebuilt from post-run workspace state.
            "audit_packet": build_audit_packet(context, decision),
        }

        if decision.operator == "DECLINE":
            # §23: respected decline — no mutation, no fallback escalation.
            episode["outcome"] = "DECLINE"
            episode["decline_reason"] = decision.decline_reason
            episodes.append(episode)
            with journal_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(episode, ensure_ascii=False, sort_keys=True) + "\n")
            return finish("STRATEGIST_DECLINED")

        operation = _OPERATION[decision.operator]
        try:
            builder_result = compile_to_builder_result(decision, blocked_node_id=frontier)
        except ValueError as error:
            return finish("SYSTEM_ERROR", error=f"{type(error).__name__}: {error}")
        outcome = run_local_redecomposition(
            root,
            problem_id=problem.problem_id,
            blocked_node_id=frontier,
            builder=PredecidedBuilder(builder_result, getattr(strategist, "last_prompt", None)),
            auditor=auditor_for(operation),
            operation=operation,
        )
        if outcome.auditor is not None:
            auditor_calls += 1
        episode["outcome"] = outcome.outcome
        episode["mechanical_errors"] = list(outcome.mechanical_errors)
        episode["auditor_verdict"] = (
            outcome.auditor.verdict if outcome.auditor is not None else None
        )
        episode["child_node_ids"] = list(outcome.child_node_ids)
        episodes.append(episode)
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(episode, ensure_ascii=False, sort_keys=True) + "\n")

        if outcome.outcome == "APPLIED":
            mutation_episodes += 1
            continue
        if outcome.outcome in ("AUDITOR_REJECT", "AUDITOR_REVISE"):
            # §24: no second sample (K=1).
            return finish("STRATEGY_AUDIT_REJECTED")
        if outcome.outcome == "MECHANICAL_REJECT":
            return finish("MECHANICAL_REJECT")
        return finish("SYSTEM_ERROR", error=f"redecomposition {outcome.outcome}: {outcome.error}")
