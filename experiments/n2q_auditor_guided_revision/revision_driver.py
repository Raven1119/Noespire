"""N2Q treatment driver — N2P unified-strategist loop + ONE bounded
auditor-guided revision (task card §2/§19/§20).

Identical to the N2P treatment loop except at exactly one branch: when the
frozen Structural Auditor returns REVISE on proposal v1, the driver runs
exactly one fresh bounded revision and re-enters the frozen pipeline with
proposal v2 (mechanical validation -> new fresh auditor). The revision
branch never recurses: v2's verdict maps to REVISION_PASS (apply +
continue), REVISION_STILL_REVISE, REVISION_REJECTED, or REVISION_INVALID —
all terminal. max_revision_rounds = 1 is structural (§20).

REJECT and DECLINE remain terminal with zero revision calls (§15/§17).
N2P's own driver file is untouched (committed evidence); shared helpers are
imported from it.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from research.local_refinement import _build_context, run_local_redecomposition
from research.graph import FactGraph
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold, solve_scaffold

from driver import LongHorizonBudget, _attempt_count  # N2L (sys.path)

from proposal_audit import build_audit_packet  # N2P (sys.path)
from strategist import PredecidedBuilder, compile_to_builder_result  # N2P
from treatment_driver import _OPERATION, _persist_strategist_packet  # N2P

from reviser import OperatorDriftError, RevisionResult, decision_view


@dataclass(frozen=True)
class RevisionRunResult:
    stop_reason: str
    # TARGET_SOLVED | STRATEGIST_DECLINED | STRATEGY_AUDIT_REJECTED
    # | MECHANICAL_REJECT | REVISION_STILL_REVISE | REVISION_REJECTED
    # | REVISION_INVALID | REVISION_NOT_LOCAL | BUDGET_EXHAUSTED
    # | FRONTIER_EXHAUSTED | SYSTEM_ERROR
    solve_status: Optional[str]
    error: Optional[str] = None
    mutation_episodes: int = 0
    solver_attempts: int = 0
    strategist_calls: int = 0
    revision_calls: int = 0
    auditor_calls: int = 0
    horizon_handoffs: int = 0
    episodes: Tuple[dict, ...] = ()


def _persist_revision_packet(
    root: Path, frontier: str, sequence: int, prompt: Optional[str], revision: RevisionResult
) -> Path:
    directory = Path(root) / "revisions"
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "blocked_node_id": frontier,
        "prompt": prompt,
        "raw": revision.raw,
        "repairable": revision.repairable,
        "not_local_reason": revision.not_local_reason,
        "v2": decision_view(revision.decision) if revision.decision else None,
    }
    path = directory / f"revision-{sequence:03d}-{frontier}.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def run_treatment_with_revision(
    problem_dir,
    *,
    problem,
    worker,
    verifier,
    strategist,
    reviser,
    auditor_for,
    budget: LongHorizonBudget = LongHorizonBudget(),
    solver_config: NodeSolverConfig = NodeSolverConfig(max_attempts_per_obligation=3),
    author: str = "n2q",
    solve_error_handoff: Optional[Callable[[BaseException, Path], Optional[str]]] = None,
) -> RevisionRunResult:
    root = Path(problem_dir)
    journal_path = root / "treatment_journal.jsonl"
    initial_attempts = _attempt_count(root)
    episodes: List[dict] = []
    mutation_episodes = 0
    strategist_calls = 0
    revision_calls = 0
    auditor_calls = 0
    horizon_handoffs = 0
    solve_status: Optional[str] = None
    pending_frontier: Optional[str] = None
    decided: set = set()

    def finish(stop_reason: str, error: Optional[str] = None) -> RevisionRunResult:
        return RevisionRunResult(
            stop_reason=stop_reason,
            solve_status=solve_status,
            error=error,
            mutation_episodes=mutation_episodes,
            solver_attempts=_attempt_count(root) - initial_attempts,
            strategist_calls=strategist_calls,
            revision_calls=revision_calls,
            auditor_calls=auditor_calls,
            horizon_handoffs=horizon_handoffs,
            episodes=tuple(episodes),
        )

    def journal(event: dict) -> None:
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

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
            # One decision per frontier identity (K=1); a re-blocked,
            # already-decided frontier has no further move.
            return finish("FRONTIER_EXHAUSTED")
        decided.add(frontier)
        if (
            mutation_episodes >= budget.max_mutation_episodes
            or strategist_calls + revision_calls >= budget.max_builder_proposals
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
            # N2P §23 / N2Q §17: respected decline — no mutation, no
            # revision, no fallback escalation.
            episode["outcome"] = "DECLINE"
            episode["decline_reason"] = decision.decline_reason
            episodes.append(episode)
            journal(episode)
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
        episode["auditor_reasons"] = (
            list(outcome.auditor.reasons) if outcome.auditor is not None else []
        )
        episode["child_node_ids"] = list(outcome.child_node_ids)

        if outcome.outcome == "APPLIED":
            episodes.append(episode)
            journal(episode)
            mutation_episodes += 1
            continue
        if outcome.outcome == "AUDITOR_REJECT":
            # §15: REJECT stays terminal — zero revision calls.
            episodes.append(episode)
            journal(episode)
            return finish("STRATEGY_AUDIT_REJECTED")
        if outcome.outcome == "MECHANICAL_REJECT":
            episodes.append(episode)
            journal(episode)
            return finish("MECHANICAL_REJECT")
        if outcome.outcome != "AUDITOR_REVISE":
            episodes.append(episode)
            journal(episode)
            return finish("SYSTEM_ERROR", error=f"redecomposition {outcome.outcome}: {outcome.error}")

        # §2/§19: AUDITOR_REVISE -> exactly one bounded revision (§20).
        if (
            strategist_calls + revision_calls >= budget.max_builder_proposals
            or auditor_calls >= budget.max_auditor_calls
        ):
            episodes.append(episode)
            journal(episode)
            return finish("BUDGET_EXHAUSTED")
        revision_calls += 1
        try:
            revision = reviser.revise(context, decision, outcome.auditor.reasons)
        except OperatorDriftError as error:
            # §4: a revision may not switch operator — invalid, terminal.
            episode["revision"] = {
                "outcome": "REVISION_INVALID",
                "error": str(error),
            }
            episodes.append(episode)
            journal(episode)
            return finish("REVISION_INVALID", error=str(error))
        except Exception as error:
            episodes.append(episode)
            journal(episode)
            return finish("SYSTEM_ERROR", error=f"{type(error).__name__}: {error}")
        revision_packet = _persist_revision_packet(
            root, frontier, revision_calls, getattr(reviser, "last_prompt", None), revision
        )
        revision_record = {
            "revision_packet": str(revision_packet),
            "repairable": revision.repairable,
            "not_local_reason": revision.not_local_reason,
        }

        if not revision.repairable:
            # §4/§16: the feedback demands a new strategy — do not re-plan.
            revision_record["outcome"] = "REVISION_NOT_LOCAL"
            episode["revision"] = revision_record
            episodes.append(episode)
            journal(episode)
            return finish("REVISION_NOT_LOCAL")

        try:
            v2_builder_result = compile_to_builder_result(
                revision.decision, blocked_node_id=frontier
            )
        except ValueError as error:
            # Includes operator drift (§4): revision may not switch operator.
            revision_record["outcome"] = "REVISION_INVALID"
            revision_record["error"] = str(error)
            episode["revision"] = revision_record
            episodes.append(episode)
            journal(episode)
            return finish("REVISION_INVALID", error=str(error))

        outcome2 = run_local_redecomposition(
            root,
            problem_id=problem.problem_id,
            blocked_node_id=frontier,
            builder=PredecidedBuilder(v2_builder_result, getattr(reviser, "last_prompt", None)),
            auditor=auditor_for(operation),  # fresh session (§19)
            operation=operation,
        )
        if outcome2.auditor is not None:
            auditor_calls += 1
        revision_record["mechanical_errors"] = list(outcome2.mechanical_errors)
        revision_record["auditor_verdict"] = (
            outcome2.auditor.verdict if outcome2.auditor is not None else None
        )
        revision_record["child_node_ids"] = list(outcome2.child_node_ids)
        revision_record["v2"] = decision_view(revision.decision)
        # Decision-time audit snapshot for v2 (same context — unchanged by
        # the v1 REVISE round, which applies nothing).
        revision_record["audit_packet"] = build_audit_packet(context, revision.decision)
        episode["revision"] = revision_record

        if outcome2.outcome == "APPLIED":
            revision_record["outcome"] = "REVISION_PASS"
            episodes.append(episode)
            journal(episode)
            mutation_episodes += 1
            continue
        if outcome2.outcome == "AUDITOR_REVISE":
            revision_record["outcome"] = "REVISION_STILL_REVISE"
            episodes.append(episode)
            journal(episode)
            return finish("REVISION_STILL_REVISE")
        if outcome2.outcome == "AUDITOR_REJECT":
            revision_record["outcome"] = "REVISION_REJECTED"
            episodes.append(episode)
            journal(episode)
            return finish("REVISION_REJECTED")
        revision_record["outcome"] = "REVISION_INVALID"
        episodes.append(episode)
        journal(episode)
        return finish(
            "REVISION_INVALID",
            error=f"redecomposition v2 {outcome2.outcome}: {outcome2.error}",
        )
