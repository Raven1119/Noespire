"""One-attempt natural-language proof flow for a complete problem statement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from .agents import ResearchWorker
from .attempt import execute_obligation_with_evidence
from .graph import FactGraph
from .obligation import ObligationRegistry, ProofObligation
from .pipeline import Verifier


@dataclass(frozen=True)
class ProblemSpec:
    problem_id: str
    statement: str
    premise_fact_ids: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        problem_id = " ".join(self.problem_id.split())
        statement = " ".join(self.statement.split())
        premises = tuple(sorted(set(item.strip() for item in self.premise_fact_ids)))
        if not problem_id or not statement or any(not item for item in premises):
            raise ValueError("problem_id, statement, and premise Fact IDs must be non-empty")
        object.__setattr__(self, "problem_id", problem_id)
        object.__setattr__(self, "statement", statement)
        object.__setattr__(self, "premise_fact_ids", premises)


@dataclass(frozen=True)
class ProblemResult:
    problem_id: str
    status: str
    obligation_id: str
    target_fact_id: Optional[str]
    supporting_closure_fact_ids: Tuple[str, ...]
    attempt_id: Optional[str]


def solve_problem_once(
    *,
    problem: ProblemSpec,
    registry: ObligationRegistry,
    graph: FactGraph,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
) -> ProblemResult:
    """Create or resume the root and execute at most one worker attempt."""
    obligation = _get_or_create_root(problem, registry, graph)
    attempt = execute_obligation_with_evidence(
        registry=registry,
        obligation_id=obligation.obligation_id,
        graph=graph,
        problem_id=problem.problem_id,
        problem=problem.statement,
        author=author,
        worker=worker,
        verifier=verifier,
    )
    execution = attempt.execution
    attempt_id = attempt.attempt_id
    if execution.fact is None:
        return ProblemResult(
            problem.problem_id,
            "OPEN",
            obligation.obligation_id,
            None,
            (),
            attempt_id,
        )

    closure = graph.supporting_closure(execution.fact.fact_id)
    return ProblemResult(
        problem.problem_id,
        "SOLVED",
        obligation.obligation_id,
        execution.fact.fact_id,
        tuple(fact.fact_id for fact in closure),
        attempt_id,
    )


def _get_or_create_root(
    problem: ProblemSpec,
    registry: ObligationRegistry,
    graph: FactGraph,
) -> ProofObligation:
    for fact_id in problem.premise_fact_ids:
        if graph.get_fact(fact_id).problem_id != problem.problem_id:
            raise ValueError("all problem premises must belong to problem_id")

    expected = ProofObligation(
        obligation_id=f"root:{problem.problem_id}",
        premises=problem.premise_fact_ids,
        goal=problem.statement,
        route_id="root",
    )
    try:
        existing = registry.get(expected.obligation_id)
    except KeyError:
        return registry.add(expected)
    if (existing.premises, existing.goal, existing.route_id) != (
        expected.premises,
        expected.goal,
        expected.route_id,
    ):
        raise ValueError(f"problem ID collision: {problem.problem_id}")
    return existing
