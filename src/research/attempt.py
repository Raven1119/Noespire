"""Durable evidence around one proof-obligation execution attempt."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import List, Optional, Sequence

from .agents import ResearchWorker
from .fact import CandidateFact, Fact
from .graph import FactGraph
from .obligation import ObligationRegistry, ObligationStatus
from .obligation_execution import ObligationExecutionResult, execute_obligation
from .pipeline import VerificationResult, Verifier


@dataclass(frozen=True)
class AttemptExecutionResult:
    execution: ObligationExecutionResult
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


def execute_obligation_with_evidence(
    *,
    registry: ObligationRegistry,
    obligation_id: str,
    graph: FactGraph,
    problem_id: str,
    problem: str,
    author: str,
    worker: ResearchWorker,
    verifier: Verifier,
) -> AttemptExecutionResult:
    """Execute once while preserving candidate, verifier, and error evidence."""
    obligation = registry.get(obligation_id)
    attempt_id = None
    if obligation.status is not ObligationStatus.DISCHARGED:
        attempt_id = _start_attempt(registry, problem_id, obligation_id)
    attempt_worker = _EvidenceWorker(worker, registry, attempt_id) if attempt_id else worker
    attempt_verifier = _EvidenceVerifier(verifier, registry, attempt_id) if attempt_id else verifier
    try:
        execution = execute_obligation(
            registry=registry,
            obligation_id=obligation_id,
            graph=graph,
            problem_id=problem_id,
            problem=problem,
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
        current = registry.get(obligation_id)
        if current.status is ObligationStatus.RUNNING:
            registry.transition(obligation_id, ObligationStatus.OPEN)
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
    return AttemptExecutionResult(execution, attempt_id)


def _start_attempt(
    registry: ObligationRegistry,
    problem_id: str,
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
        "problem_id": problem_id,
        "obligation_id": obligation_id,
        "candidate_artifact": None,
        "verifier_artifact": None,
        "verdict": "RUNNING",
        "error": None,
    }
    _write_json(attempts_dir / f"{attempt_id}.json", payload)
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
