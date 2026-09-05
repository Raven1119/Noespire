"""N2L long-horizon driver — evaluation-only deterministic orchestration.

NOT a product scheduler (task card §14): the fixed escalation
SPLIT -> INSERT_CUT_SET -> ADD_ALTERNATIVE_ROUTE exists only to keep the
existing, frozen mechanisms running under a reproducible policy so
long-horizon behavior can be observed. No operator-selection model, no
memory, no transcript: every episode rebuilds its bounded context from the
workspace (scaffold, FactGraph, local attempts, per-obligation operator
outcomes) via the unchanged ``run_local_redecomposition``.

Escalation state is scanned from the persisted ``local_refinements/*.json``
evidence (filename prefix -> operator, payload -> blocked_node_id), so a
(pnode, operator) pair is tried at most once even across driver invocations.
New node identities created by an applied mutation are new obligations and
restart escalation naturally (§15).
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from research.graph import FactGraph
from research.local_refinement import run_local_redecomposition
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry
from research.scaffold import ProofScaffold, solve_scaffold


ESCALATION_ORDER = ("split", "insert_cut_set", "add_alternative_route")

# Frozen before the real runs (§16).
@dataclass(frozen=True)
class LongHorizonBudget:
    max_mutation_episodes: int = 6
    max_solver_attempts: int = 24
    max_builder_proposals: int = 12
    max_auditor_calls: int = 12


@dataclass(frozen=True)
class LongHorizonResult:
    stop_reason: str
    # TARGET_SOLVED | BUDGET_EXHAUSTED | OPERATORS_EXHAUSTED
    # | FRONTIER_EXHAUSTED | SYSTEM_ERROR
    solve_status: Optional[str]
    error: Optional[str] = None
    mutation_episodes: int = 0
    solver_attempts: int = 0
    builder_proposals: int = 0
    auditor_calls: int = 0
    episodes: Tuple[dict, ...] = ()
    # N2M: solve-path LOCAL_HORIZON_EXHAUSTED handoffs (timeout is execution
    # evidence, not a mathematical verdict). 0 in N2L runs.
    horizon_handoffs: int = 0


_PREFIX_TO_OPERATION = {
    "no-split": "split",
    "split": "split",
    "no-cut": "insert_cut_set",
    "cut": "insert_cut_set",
    "no-route": "add_alternative_route",
    "alt": "add_alternative_route",
}
_PREFIXES = ("no-split", "no-cut", "no-route", "split", "cut", "alt")


def _attempt_count(problem_dir: Path) -> int:
    attempts_dir = problem_dir / "attempts"
    if not attempts_dir.is_dir():
        return 0
    return len(list(attempts_dir.glob("attempt-*.json")))


def _tried_operators(problem_dir: Path) -> Dict[str, Set[str]]:
    """blocked_node_id -> operators already attempted, from evidence files."""
    refinement_dir = problem_dir / "local_refinements"
    tried: Dict[str, Set[str]] = {}
    if not refinement_dir.is_dir():
        return tried
    for path in sorted(refinement_dir.glob("*.json")):
        kind = next(
            (prefix for prefix in _PREFIXES if path.name.startswith(prefix + "-")),
            None,
        )
        if kind is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        node_id = payload.get("blocked_node_id")
        if node_id:
            tried.setdefault(str(node_id), set()).add(_PREFIX_TO_OPERATION[kind])
    return tried


def run_long_horizon(
    problem_dir,
    *,
    problem,
    worker,
    verifier,
    builder_for,
    auditor_for,
    budget: LongHorizonBudget = LongHorizonBudget(),
    solver_config: NodeSolverConfig = NodeSolverConfig(max_attempts_per_obligation=3),
    author: str = "n2l",
    solve_error_handoff: Optional[Callable[[BaseException, Path], Optional[str]]] = None,
) -> LongHorizonResult:
    """Run the frozen machinery under the fixed escalation policy until a
    §17 stop condition fires.

    ``solve_error_handoff`` (N2M): optional seam consulted when the solve
    path raises. It classifies the exception and returns the frontier node
    to hand off to the graph escalation (LOCAL_HORIZON_EXHAUSTED), or None
    to keep the N2L behavior (SYSTEM_ERROR stop).
    """
    root = Path(problem_dir)
    journal_path = root / "long_horizon_journal.jsonl"
    initial_attempts = _attempt_count(root)
    episodes: List[dict] = []
    mutation_episodes = 0
    builder_proposals = 0
    auditor_calls = 0
    horizon_handoffs = 0
    solve_status: Optional[str] = None
    pending_frontier: Optional[str] = None

    def finish(stop_reason: str, error: Optional[str] = None) -> LongHorizonResult:
        return LongHorizonResult(
            stop_reason=stop_reason,
            solve_status=solve_status,
            error=error,
            mutation_episodes=mutation_episodes,
            solver_attempts=_attempt_count(root) - initial_attempts,
            builder_proposals=builder_proposals,
            auditor_calls=auditor_calls,
            episodes=tuple(episodes),
            horizon_handoffs=horizon_handoffs,
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
                # LOCAL_HORIZON_EXHAUSTED (N2M §2/§10): the frozen attempt
                # layer already kept the obligation OPEN and admitted no
                # Fact. The timeout is execution evidence, not a
                # mathematical verdict — hand the frontier to the graph
                # escalation without re-solving the exhausted obligation.
                horizon_handoffs += 1
                pending_frontier = handoff_frontier
                with journal_path.open("a", encoding="utf-8") as handle:
                    handle.write(
                        json.dumps(
                            {
                                "event": "horizon_handoff",
                                "blocked_node_id": handoff_frontier,
                                "error_type": type(error).__name__,
                                # The frozen horizon that was hit (typed;
                                # None for non-timeout handoffs).
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
                # §17: the attempt budget is a hard stop, checked again right
                # after the solve that exhausted it (before any operator call).
                return finish("BUDGET_EXHAUSTED")
            frontier = solved.advances[-1].node_id if solved.advances else None
            if frontier is None:
                # No ready node: every open obligation waits on something that
                # can never resolve under the current routes.
                return finish("FRONTIER_EXHAUSTED")
        else:
            # A decline/rejection advances the escalation directly (§13);
            # re-solving the same budget-exhausted obligation would just burn
            # attempts on an unchanged frontier.
            frontier = pending_frontier
            pending_frontier = None
        tried = _tried_operators(root).get(frontier, set())
        remaining = [op for op in ESCALATION_ORDER if op not in tried]
        if not remaining:
            # The blocked node is still ready; re-solving would just burn
            # attempts on the same exhausted obligation.
            return finish("OPERATORS_EXHAUSTED")
        if (
            mutation_episodes >= budget.max_mutation_episodes
            or builder_proposals >= budget.max_builder_proposals
            or auditor_calls >= budget.max_auditor_calls
        ):
            return finish("BUDGET_EXHAUSTED")
        operation = remaining[0]
        outcome = run_local_redecomposition(
            root,
            problem_id=problem.problem_id,
            blocked_node_id=frontier,
            builder=builder_for(operation),
            auditor=auditor_for(operation),
            operation=operation,
        )
        builder_proposals += 1
        if outcome.auditor is not None:
            auditor_calls += 1
        applied = outcome.outcome == "APPLIED"
        if applied:
            mutation_episodes += 1
        else:
            # Decline / reject / error: continue the escalation on the same
            # frontier without re-solving (nothing about the graph changed).
            pending_frontier = frontier
        episode = {
            "episode": len(episodes) + 1,
            "blocked_node_id": frontier,
            "operation": operation,
            "outcome": outcome.outcome,
            "proposal_id": (
                outcome.proposal.proposal_id if outcome.proposal is not None else None
            ),
            "mechanical_errors": list(outcome.mechanical_errors),
            "auditor_verdict": (
                outcome.auditor.verdict if outcome.auditor is not None else None
            ),
            "child_node_ids": list(outcome.child_node_ids),
            "error": outcome.error,
        }
        episodes.append(episode)
        with journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(episode, ensure_ascii=False, sort_keys=True) + "\n")
