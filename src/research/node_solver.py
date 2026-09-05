"""Bounded verifier-guided repair over the single-attempt obligation executor.

``execute_obligation`` stays single-attempt; the repair loop lives here only.
Each round is one ``execute_obligation_with_evidence`` call with its own
durable attempt artifact. Round 1 invokes the worker exactly as the legacy
one-shot path; rounds >= 2 carry a ``RepairContext`` built from the previous
round's rejected candidate and the verifier/contract-guard reason.

Truth boundary: only a verifier PASS admits a Fact (inside
``execute_obligation``, unchanged). BLOCKED means "solver exhausted budget",
never "the statement is false". A worker/verifier exception stops the loop
immediately as ERROR — system errors do not consume the remaining budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .agents import ResearchWorker
from .attempt import execute_obligation_with_evidence
from .fact import Fact
from .graph import FactGraph
from .obligation import ObligationRegistry
from .obligation_execution import ObligationExecutionResult
from .pipeline import RepairContext, Verifier
from .problem import ProblemSpec


@dataclass(frozen=True)
class NodeSolverConfig:
    """Per-obligation attempt budget. The research-layer default is 1:
    without an explicit config the solver is exactly the one-shot path."""

    max_attempts_per_obligation: int = 1

    def __post_init__(self) -> None:
        if self.max_attempts_per_obligation < 1:
            raise ValueError("max_attempts_per_obligation must be >= 1")


@dataclass(frozen=True)
class NodeSolveOutcome:
    status: str  # "SOLVED" | "BLOCKED" | "ERROR"
    fact: Optional[Fact]
    attempt_ids: Tuple[str, ...]
    reason: Optional[str]
    execution: Optional[ObligationExecutionResult] = None
    error: Optional[BaseException] = None


class NodeSolver:
    """Runs the bounded repair loop for one existing obligation."""

    def __init__(
        self,
        *,
        worker: ResearchWorker,
        verifier: Verifier,
        config: NodeSolverConfig = NodeSolverConfig(),
    ) -> None:
        self.worker = worker
        self.verifier = verifier
        self.config = config

    def solve_obligation(
        self,
        *,
        problem: ProblemSpec,
        registry: ObligationRegistry,
        graph: FactGraph,
        author: str,
        obligation_id: str,
        goal: str,
        premise_fact_ids: Tuple[str, ...],
    ) -> NodeSolveOutcome:
        obligation = registry.get(obligation_id)
        if obligation.goal != goal or obligation.premises != tuple(
            sorted(set(premise_fact_ids))
        ):
            raise ValueError(f"obligation identity mismatch: {obligation_id}")

        attempt_ids: List[str] = []
        repair_context: Optional[RepairContext] = None
        execution: Optional[ObligationExecutionResult] = None
        for round_number in range(1, self.config.max_attempts_per_obligation + 1):
            try:
                attempt = execute_obligation_with_evidence(
                    registry=registry,
                    obligation_id=obligation_id,
                    graph=graph,
                    problem_id=problem.problem_id,
                    problem=problem.statement,
                    author=author,
                    worker=self.worker,
                    verifier=self.verifier,
                    repair_context=repair_context,
                )
            except Exception as error:
                return NodeSolveOutcome(
                    status="ERROR",
                    fact=None,
                    attempt_ids=tuple(attempt_ids),
                    reason=f"{type(error).__name__}: {error}",
                    execution=execution,
                    error=error,
                )
            execution = attempt.execution
            if attempt.attempt_id:
                attempt_ids.append(attempt.attempt_id)
            if execution.fact is not None:
                # Verifier PASS (or an already-DISCHARGED resume): exactly one
                # verified Fact; a resume short-circuit consumes no budget.
                return NodeSolveOutcome(
                    status="SOLVED",
                    fact=execution.fact,
                    attempt_ids=tuple(attempt_ids),
                    reason=None,
                    execution=execution,
                )
            # Failed round: execute_obligation guarantees a candidate and a
            # (possibly guard-fabricated) verification result here.
            candidate = execution.candidate
            verification = execution.verification
            repair_context = RepairContext(
                previous_statement=candidate.statement,
                previous_proof=candidate.proof,
                verifier_reason=verification.reason,
                attempt_number=round_number + 1,
                max_attempts=self.config.max_attempts_per_obligation,
            )
        return NodeSolveOutcome(
            status="BLOCKED",
            fact=None,
            attempt_ids=tuple(attempt_ids),
            reason=repair_context.verifier_reason if repair_context else None,
            execution=execution,
        )
