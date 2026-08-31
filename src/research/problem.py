"""One-attempt natural-language proof flow for a complete problem statement."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from .agents import ResearchWorker
from .fact import CandidateFact, Fact
from .graph import FactGraph
from .obligation import ObligationRegistry, ObligationStatus, ProofObligation
from .obligation_execution import execute_obligation
from .pipeline import VerificationResult, Verifier


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


class _EvidenceWorker:
    def __init__(
        self,
        worker: ResearchWorker,
        registry: ObligationRegistry,
        attempt_id: str,
    ) -> None:
        self.worker = worker
        self.registry = registry
        self.attempt_id = attempt_id

    def propose(
        self,
        *,
        problem: str,
        existing_facts: Sequence[Fact],
        subgoal: str,
    ) -> CandidateFact:
        candidate = self.worker.propose(
            problem=problem,
            existing_facts=existing_facts,
            subgoal=subgoal,
        )
        _update_attempt(self.registry, self.attempt_id, candidate=candidate)
        return candidate


class _EvidenceVerifier:
    def __init__(self, verifier: Verifier, registry: ObligationRegistry, attempt_id: str) -> None:
        self.verifier = verifier
        self.registry = registry
        self.attempt_id = attempt_id

    def verify(
        self,
        problem: str,
        candidate: CandidateFact,
        predecessors: List[Fact],
    ) -> VerificationResult:
        verification = self.verifier.verify(problem, candidate, predecessors)
        _update_attempt(
            self.registry,
            self.attempt_id,
            verification=verification,
            verdict="PASS" if verification.accepted else "FAIL",
        )
        return verification


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
    attempt_id = None
    if obligation.status is not ObligationStatus.DISCHARGED:
        attempt_id = _start_attempt(registry, problem, obligation.obligation_id)
    attempt_worker = _EvidenceWorker(worker, registry, attempt_id) if attempt_id else worker
    attempt_verifier = _EvidenceVerifier(verifier, registry, attempt_id) if attempt_id else verifier
    try:
        execution = execute_obligation(
            registry=registry,
            obligation_id=obligation.obligation_id,
            graph=graph,
            problem_id=problem.problem_id,
            problem=problem.statement,
            author=author,
            worker=attempt_worker,
            verifier=attempt_verifier,
        )
    except Exception as error:
        evidence_error = None
        if attempt_id:
            try:
                _update_attempt(registry, attempt_id, verdict="ERROR", error=error)
            except Exception as update_error:
                evidence_error = update_error
        current = registry.get(obligation.obligation_id)
        if current.status is ObligationStatus.RUNNING:
            registry.transition(obligation.obligation_id, ObligationStatus.OPEN)
        if evidence_error is not None:
            raise evidence_error from error
        raise
    if attempt_id:
        _update_attempt(
            registry,
            attempt_id,
            candidate=execution.candidate,
            verification=execution.verification,
            verdict="PASS" if execution.fact else "FAIL",
        )
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


def _start_attempt(
    registry: ObligationRegistry,
    problem: ProblemSpec,
    obligation_id: str,
) -> str:
    attempts_dir = registry.path.parent / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    sequence = 1
    while (attempts_dir / f"attempt-{sequence:06d}.json").exists():
        sequence += 1
    attempt_id = f"attempt-{sequence:06d}"
    payload = {
        "attempt_id": attempt_id,
        "problem_id": problem.problem_id,
        "obligation_id": obligation_id,
        "candidate_artifact": None,
        "verifier_artifact": None,
        "verdict": "RUNNING",
        "error": None,
    }
    path = attempts_dir / f"{attempt_id}.json"
    _write_json(path, payload)
    return attempt_id


def _update_attempt(
    registry: ObligationRegistry,
    attempt_id: str,
    *,
    candidate: Optional[CandidateFact] = None,
    verification: Optional[VerificationResult] = None,
    verdict: Optional[str] = None,
    error: Optional[Exception] = None,
) -> None:
    path = registry.path.parent / "attempts" / f"{attempt_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if candidate is not None:
        payload["candidate_artifact"] = asdict(candidate)
    if verification is not None:
        payload["verifier_artifact"] = asdict(verification)
    if verdict is not None:
        payload["verdict"] = verdict
    if error is not None:
        payload["error"] = str(error)
    _write_json(path, payload)


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
