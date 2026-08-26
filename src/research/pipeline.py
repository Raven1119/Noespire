"""Verification-gated fact submission."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from .fact import CandidateFact, Fact
from .graph import FactGraph


@dataclass(frozen=True)
class VerificationResult:
    accepted: bool
    reason: str


@dataclass(frozen=True)
class SubmissionResult:
    verification: VerificationResult
    fact: Optional[Fact]


class Verifier(Protocol):
    def verify(
        self,
        problem: str,
        candidate: CandidateFact,
        predecessors: List[Fact],
    ) -> VerificationResult:
        ...


def submit_candidate(
    *,
    graph: FactGraph,
    problem_id: str,
    problem: str,
    author: str,
    candidate: CandidateFact,
    verifier: Verifier,
) -> SubmissionResult:
    predecessors = [graph.get_fact(fact_id) for fact_id in candidate.predecessors]
    verification = verifier.verify(problem, candidate, predecessors)
    if not verification.accepted:
        return SubmissionResult(verification=verification, fact=None)
    fact = Fact.create(
        problem_id=problem_id,
        author=author,
        statement=candidate.statement,
        proof=candidate.proof,
        predecessors=candidate.predecessors,
    )
    return SubmissionResult(verification=verification, fact=graph.add_fact(fact))
