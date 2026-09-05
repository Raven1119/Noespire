"""Execute one existing proof obligation through the verified Fact gate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .agents import ResearchWorker
from .fact import CandidateFact, Fact
from .graph import FactGraph
from .obligation import ObligationRegistry, ObligationStatus, ProofObligation
from .pipeline import RepairContext, VerificationResult, Verifier, submit_candidate


@dataclass(frozen=True)
class ObligationExecutionResult:
    obligation: ProofObligation
    candidate: Optional[CandidateFact]
    verification: Optional[VerificationResult]
    fact: Optional[Fact]
    executed: bool


def execute_obligation(
    *,
    registry: ObligationRegistry,
    obligation_id: str,
    graph: FactGraph,
    problem_id: str,
    problem: str,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
    repair_context: Optional[RepairContext] = None,
) -> ObligationExecutionResult:
    obligation = registry.get(obligation_id)
    if obligation.status is ObligationStatus.DISCHARGED:
        fact = graph.get_fact(obligation.resolved_by_fact_id or "")
        return ObligationExecutionResult(obligation, None, None, fact, False)

    premises = [graph.get_fact(fact_id) for fact_id in obligation.premises]
    if any(fact.problem_id != problem_id for fact in premises):
        raise ValueError("all obligation premises must belong to problem_id")

    registry.transition(obligation_id, ObligationStatus.RUNNING)
    subgoal = (
        "Use every provided accepted Fact jointly as a premise. "
        "Return the goal text verbatim as the candidate statement and return exactly "
        "the provided fact IDs as predecessors.\n\n"
        f"Goal:\n{obligation.goal}"
    )
    if repair_context is None:
        # Legacy call shape: first rounds and one-shot callers never see the keyword.
        candidate = worker.propose(problem=problem, existing_facts=premises, subgoal=subgoal)
    else:
        candidate = worker.propose(
            problem=problem,
            existing_facts=premises,
            subgoal=subgoal,
            repair_context=repair_context,
        )
    candidate_predecessors = tuple(sorted(set(candidate.predecessors)))
    if " ".join(candidate.statement.split()) != obligation.goal:
        return _open_without_submission(
            registry, obligation_id, candidate, "candidate statement does not match obligation goal"
        )
    if candidate_predecessors != obligation.premises:
        return _open_without_submission(
            registry, obligation_id, candidate, "candidate predecessors do not match obligation premises"
        )

    submission = submit_candidate(
        graph=graph,
        problem_id=problem_id,
        problem=problem,
        author=author,
        candidate=candidate,
        verifier=verifier,
    )
    if submission.fact is None:
        opened = registry.transition(obligation_id, ObligationStatus.OPEN)
        return ObligationExecutionResult(
            opened,
            candidate,
            submission.verification,
            None,
            True,
        )

    discharged = registry.resolve(obligation_id, submission.fact.fact_id, graph)
    return ObligationExecutionResult(
        discharged,
        candidate,
        submission.verification,
        submission.fact,
        True,
    )


def _open_without_submission(
    registry: ObligationRegistry,
    obligation_id: str,
    candidate: CandidateFact,
    reason: str,
) -> ObligationExecutionResult:
    opened = registry.transition(obligation_id, ObligationStatus.OPEN)
    return ObligationExecutionResult(
        opened,
        candidate,
        VerificationResult(False, reason),
        None,
        True,
    )
