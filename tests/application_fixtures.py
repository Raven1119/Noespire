"""Fixture builders for application-layer tests.

Core research state (facts, obligations, attempt evidence) is produced only
through the real core constructors and ``solve_problem_once`` with scripted
doubles, so fixtures cannot drift from the core persistence format.

Two states cannot be produced through the synchronous public API and are
hand-written with a comment pointing at the core writer they mirror:

- residual RUNNING attempt files (a crash mid-attempt): payload mirrors
  ``src/research/problem.py:_start_attempt`` / ``_update_attempt``;
- ``_execution_log.jsonl`` is application-owned, so tests write it directly.
"""

import json
from pathlib import Path
import time
from typing import Iterable, Optional

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec, solve_problem_once


DEFAULT_CREATED_AT = "2026-08-31T10:15:00+08:00"


class WorkspaceBuilder:
    """Builds one workspaces root: index.json plus per-problem directories."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._entries = []

    def add_problem(
        self,
        problem_id: str,
        statement: str,
        *,
        derived_from: Optional[str] = None,
        archived: bool = False,
        created_at: str = DEFAULT_CREATED_AT,
    ) -> Path:
        self._entries.append(
            {
                "problem_id": problem_id,
                "statement": statement,
                "derived_from": derived_from,
                "archived": archived,
                "created_at": created_at,
            }
        )
        (self.root / "index.json").write_text(
            json.dumps({"problems": self._entries}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        problem_dir = self.root / problem_id
        problem_dir.mkdir(parents=True, exist_ok=True)
        return problem_dir


class ScriptedWorker:
    def __init__(self, candidate: CandidateFact) -> None:
        self.candidate = candidate

    def propose(self, *, problem, existing_facts, subgoal):
        return self.candidate


class ScriptedVerifier:
    def __init__(self, accepted: bool) -> None:
        self.accepted = accepted

    def verify(self, problem, candidate, predecessors):
        return VerificationResult(self.accepted, "scripted verdict")


class ExplodingWorker:
    def propose(self, *, problem, existing_facts, subgoal):
        raise RuntimeError("scripted worker error")


class ExplodingVerifier:
    def verify(self, problem, candidate, predecessors):
        raise RuntimeError("scripted verifier error")


class BlockingWorker:
    """propose() blocks until ``release`` is set; ``started`` signals entry.

    Lets concurrency tests hold an execution in the live window instead of
    racing a scripted worker that returns in microseconds.
    """

    def __init__(self, candidate: CandidateFact, started, release) -> None:
        self.candidate = candidate
        self.started = started
        self.release = release

    def propose(self, *, problem, existing_facts, subgoal):
        self.started.set()
        if not self.release.wait(timeout=10):
            raise RuntimeError("test release timeout")
        return self.candidate


def wait_for(predicate, timeout: float = 10.0, interval: float = 0.01) -> bool:
    """Poll ``predicate`` until it holds; False on timeout (never a hard sleep)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def registry_for(problem_dir: Path) -> ObligationRegistry:
    return ObligationRegistry(problem_dir / "obligations.json")


def add_open_obligation(problem_dir: Path, problem_id: str, goal: str) -> None:
    registry_for(problem_dir).add(
        ProofObligation(f"root:{problem_id}", (), goal, "root")
    )


def run_attempt(
    problem_dir: Path,
    problem_id: str,
    statement: str,
    *,
    accepted: bool,
    premise_fact_ids: Iterable[str] = (),
    candidate_statement: Optional[str] = None,
):
    """One real solve_problem_once call: PASS/FAIL attempt evidence on disk."""
    return solve_problem_once(
        problem=ProblemSpec(problem_id, statement, tuple(premise_fact_ids)),
        registry=registry_for(problem_dir),
        graph=FactGraph(problem_dir),
        author="worker",
        worker=ScriptedWorker(
            CandidateFact(
                candidate_statement or statement,
                "A candidate proof.",
                tuple(premise_fact_ids),
            )
        ),
        verifier=ScriptedVerifier(accepted),
    )


def run_error_attempt(problem_dir: Path, problem_id: str, statement: str) -> None:
    """One real solve_problem_once call whose worker raises (ERROR evidence)."""
    try:
        solve_problem_once(
            problem=ProblemSpec(problem_id, statement),
            registry=registry_for(problem_dir),
            graph=FactGraph(problem_dir),
            author="worker",
            worker=ExplodingWorker(),
            verifier=ScriptedVerifier(True),
        )
    except RuntimeError:
        pass


def write_residual_running_attempt(
    problem_dir: Path,
    problem_id: str,
    sequence: int = 1,
    *,
    candidate: Optional[dict] = None,
) -> str:
    """Attempt file a crash mid-attempt would leave behind.

    Payload shape mirrors src/research/problem.py:_start_attempt/_update_attempt.
    """
    attempts_dir = problem_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt_id = f"attempt-{sequence:06d}"
    payload = {
        "attempt_id": attempt_id,
        "problem_id": problem_id,
        "obligation_id": f"root:{problem_id}",
        "candidate_artifact": candidate,
        "verifier_artifact": None,
        "verdict": "RUNNING",
        "error": None,
    }
    (attempts_dir / f"{attempt_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return attempt_id


def write_pass_attempt(
    problem_dir: Path,
    problem_id: str,
    statement: str,
    *,
    proof: str = "A candidate proof.",
    predecessors: Iterable[str] = (),
    sequence: int = 1,
    reason: str = "scripted verdict",
) -> str:
    """Attempt file a crash AFTER verifier PASS would leave behind.

    Payload mirrors src/research/problem.py:_start_attempt/_update_attempt with
    the verifier verdict persisted (problem.py:85-90) and verdict "PASS".
    """
    attempts_dir = problem_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt_id = f"attempt-{sequence:06d}"
    payload = {
        "attempt_id": attempt_id,
        "problem_id": problem_id,
        "obligation_id": f"root:{problem_id}",
        "candidate_artifact": candidate_artifact(statement, proof, predecessors),
        "verifier_artifact": {"accepted": True, "reason": reason},
        "verdict": "PASS",
        "error": None,
    }
    (attempts_dir / f"{attempt_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return attempt_id


def candidate_artifact(statement: str, proof: str = "A candidate proof.", predecessors=()) -> dict:
    return {"statement": statement, "proof": proof, "predecessors": list(predecessors)}


def append_log(problem_dir: Path, *events: dict) -> None:
    """Append application-owned execution-log events (spec §7.2)."""
    log = problem_dir / "_execution_log.jsonl"
    with log.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def add_fact(
    problem_dir: Path,
    problem_id: str,
    statement: str,
    proof: str,
    predecessors: Iterable[str] = (),
) -> Fact:
    return FactGraph(problem_dir).add_fact(
        Fact.create(
            problem_id=problem_id,
            author="worker",
            statement=statement,
            proof=proof,
            predecessors=predecessors,
        )
    )
