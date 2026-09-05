"""Bounded verifier-guided repair loop over the single-attempt executor.

Each solver round is exactly one ``execute_obligation_with_evidence`` call:
one durable attempt artifact, one worker invocation, at most one verifier
invocation. Only a verifier PASS admits a Fact; an exhausted budget leaves
the obligation OPEN (BLOCKED means "budget exhausted", never "false").
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.node_solver import NodeSolver, NodeSolverConfig
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation
from research.pipeline import RepairContext, VerificationResult
from research.problem import ProblemSpec


GOAL = "Target T."
OBLIGATION_ID = "scaffold:p:target"


class RepairScriptWorker:
    """Plays scripted candidates (or raises scripted errors) in call order.

    Records the ``repair_context`` keyword of every call: round 1 must be
    invoked exactly as the legacy one-shot path (``None``), rounds >= 2 must
    carry the previous candidate and the rejection reason.
    """

    def __init__(self, outcomes: tuple) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0
        self.repair_contexts = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.repair_contexts.append(repair_context)
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedVerifier:
    def __init__(self, verdicts: tuple) -> None:
        self.verdicts = list(verdicts)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        accepted, reason = self.verdicts[self.calls]
        self.calls += 1
        return VerificationResult(accepted, reason)


def _candidate(goal: str = GOAL, proof: str = "A candidate proof.") -> CandidateFact:
    return CandidateFact(statement=goal, proof=proof, predecessors=())


def _workspace(root: Path):
    graph = FactGraph(root)
    registry = ObligationRegistry(root / "obligations.json")
    registry.add(ProofObligation(OBLIGATION_ID, (), GOAL, "scaffold:target"))
    return graph, registry


def _solve(root: Path, worker, verifier, max_attempts: int = 3):
    graph, registry = _workspace(root)
    solver = NodeSolver(
        worker=worker,
        verifier=verifier,
        config=NodeSolverConfig(max_attempts_per_obligation=max_attempts),
    )
    outcome = solver.solve_obligation(
        problem=ProblemSpec("p", GOAL),
        registry=registry,
        graph=graph,
        author="worker",
        obligation_id=OBLIGATION_ID,
        goal=GOAL,
        premise_fact_ids=(),
    )
    return outcome, graph, registry


def _attempt_payloads(root: Path):
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((root / "attempts").glob("attempt-*.json"))
    ]


def test_config_requires_at_least_one_attempt() -> None:
    with pytest.raises(ValueError):
        NodeSolverConfig(max_attempts_per_obligation=0)


def test_first_attempt_pass_solves_with_exactly_one_round() -> None:
    with TemporaryDirectory() as directory:
        worker = RepairScriptWorker((_candidate(),))
        verifier = ScriptedVerifier(((True, "accepted"),))

        outcome, graph, registry = _solve(Path(directory), worker, verifier)

        assert outcome.status == "SOLVED"
        assert outcome.fact is not None
        assert outcome.fact.statement == GOAL
        assert outcome.reason is None
        assert outcome.attempt_ids == ("attempt-000001",)
        assert worker.calls == 1
        assert verifier.calls == 1
        assert worker.repair_contexts == [None]
        assert [fact.statement for fact in graph.list_facts()] == [GOAL]
        assert registry.get(OBLIGATION_ID).status is ObligationStatus.DISCHARGED


def test_fail_then_pass_feeds_verdict_and_previous_candidate_into_round_two() -> None:
    with TemporaryDirectory() as directory:
        flawed = _candidate(proof="Flawed first proof.")
        repaired = _candidate(proof="Repaired second proof.")
        worker = RepairScriptWorker((flawed, repaired))
        verifier = ScriptedVerifier(((False, "gap in step 2"), (True, "accepted")))

        outcome, graph, _ = _solve(Path(directory), worker, verifier)

        assert outcome.status == "SOLVED"
        assert worker.calls == 2
        assert verifier.calls == 2
        assert outcome.attempt_ids == ("attempt-000001", "attempt-000002")
        assert graph.get_fact(outcome.fact.fact_id).proof == "Repaired second proof."
        repair = worker.repair_contexts[1]
        assert isinstance(repair, RepairContext)
        assert repair.previous_statement == flawed.statement
        assert repair.previous_proof == flawed.proof
        assert repair.verifier_reason == "gap in step 2"
        assert repair.attempt_number == 2
        assert repair.max_attempts == 3


def test_verifier_reason_enters_the_next_worker_context_verbatim() -> None:
    with TemporaryDirectory() as directory:
        worker = RepairScriptWorker((_candidate(), _candidate(), _candidate()))
        verifier = ScriptedVerifier(
            ((False, "first reason"), (False, "second reason"), (True, "accepted"))
        )

        outcome, _, _ = _solve(Path(directory), worker, verifier)

        assert outcome.status == "SOLVED"
        assert worker.repair_contexts[0] is None
        assert worker.repair_contexts[1].verifier_reason == "first reason"
        assert worker.repair_contexts[1].attempt_number == 2
        assert worker.repair_contexts[2].verifier_reason == "second reason"
        assert worker.repair_contexts[2].attempt_number == 3


def test_budget_exhaustion_blocks_without_admitting_a_fact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((_candidate(), _candidate(), _candidate()))
        verifier = ScriptedVerifier(
            ((False, "reason one"), (False, "reason two"), (False, "final reason"))
        )

        outcome, graph, registry = _solve(root, worker, verifier)

        assert outcome.status == "BLOCKED"
        assert outcome.fact is None
        assert outcome.reason == "final reason"
        assert outcome.attempt_ids == (
            "attempt-000001",
            "attempt-000002",
            "attempt-000003",
        )
        assert worker.calls == 3
        assert verifier.calls == 3
        assert graph.list_facts() == []
        assert registry.get(OBLIGATION_ID).status is ObligationStatus.OPEN
        assert registry.get(OBLIGATION_ID).resolved_by_fact_id is None


def test_each_round_writes_a_distinct_durable_attempt_artifact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((_candidate(), _candidate(), _candidate()))
        verifier = ScriptedVerifier(
            ((False, "reason one"), (False, "reason two"), (True, "accepted"))
        )

        outcome, _, _ = _solve(root, worker, verifier)

        assert outcome.status == "SOLVED"
        payloads = _attempt_payloads(root)
        assert [payload["attempt_id"] for payload in payloads] == [
            "attempt-000001",
            "attempt-000002",
            "attempt-000003",
        ]
        assert [payload["verdict"] for payload in payloads] == ["FAIL", "FAIL", "PASS"]
        assert [payload["verifier_artifact"]["reason"] for payload in payloads] == [
            "reason one",
            "reason two",
            "accepted",
        ]
        for payload in payloads:
            assert payload["obligation_id"] == OBLIGATION_ID
            assert payload["candidate_artifact"]["statement"] == GOAL


def test_all_fail_budget_never_admits_a_fact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((_candidate(), _candidate()))
        verifier = ScriptedVerifier(((False, "no"), (False, "still no")))

        outcome, graph, _ = _solve(root, worker, verifier, max_attempts=2)

        assert outcome.status == "BLOCKED"
        assert graph.list_facts() == []
        assert [payload["verdict"] for payload in _attempt_payloads(root)] == [
            "FAIL",
            "FAIL",
        ]


def test_worker_error_stops_without_consuming_remaining_budget() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((RuntimeError("worker crashed"), _candidate()))
        verifier = ScriptedVerifier(((True, "accepted"),))

        outcome, graph, registry = _solve(root, worker, verifier)

        assert outcome.status == "ERROR"
        assert outcome.fact is None
        assert outcome.reason == "RuntimeError: worker crashed"
        assert worker.calls == 1
        assert verifier.calls == 0
        assert graph.list_facts() == []
        assert registry.get(OBLIGATION_ID).status is ObligationStatus.OPEN
        (payload,) = _attempt_payloads(root)
        assert payload["verdict"] == "ERROR"
        assert payload["error"] == "worker crashed"


def test_error_mid_loop_stops_immediately_after_a_failed_round() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((_candidate(), RuntimeError("second round crashed")))
        verifier = ScriptedVerifier(((False, "first round rejected"),))

        outcome, _, _ = _solve(root, worker, verifier)

        assert outcome.status == "ERROR"
        assert outcome.reason == "RuntimeError: second round crashed"
        assert outcome.attempt_ids == ("attempt-000001",)
        assert worker.calls == 2
        assert verifier.calls == 1
        assert [payload["verdict"] for payload in _attempt_payloads(root)] == [
            "FAIL",
            "ERROR",
        ]


def test_contract_guard_mismatch_is_a_failed_round_without_verifier_call() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker((_candidate(goal="Wrong statement."), _candidate()))
        verifier = ScriptedVerifier(((True, "accepted"),))

        outcome, _, registry = _solve(root, worker, verifier)

        assert outcome.status == "SOLVED"
        assert worker.calls == 2
        assert verifier.calls == 1  # the guard short-circuited round 1
        repair = worker.repair_contexts[1]
        assert repair.verifier_reason == "candidate statement does not match obligation goal"
        assert repair.previous_statement == "Wrong statement."
        assert registry.get(OBLIGATION_ID).status is ObligationStatus.DISCHARGED
        payloads = _attempt_payloads(root)
        assert [payload["verdict"] for payload in payloads] == ["FAIL", "PASS"]
        assert payloads[0]["verifier_artifact"] == {
            "accepted": False,
            "reason": "candidate statement does not match obligation goal",
        }


def test_guard_exhaustion_blocks_without_admitting_a_fact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RepairScriptWorker(
            (_candidate(goal="Wrong one."), _candidate(goal="Wrong two."))
        )
        verifier = ScriptedVerifier(())

        outcome, graph, _ = _solve(root, worker, verifier, max_attempts=2)

        assert outcome.status == "BLOCKED"
        assert outcome.reason == "candidate statement does not match obligation goal"
        assert verifier.calls == 0
        assert graph.list_facts() == []


def test_discharged_obligation_solves_immediately_without_worker_call() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, registry = _workspace(root)
        registry.transition(OBLIGATION_ID, ObligationStatus.RUNNING)
        fact = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="prior worker",
                statement=GOAL,
                proof="Previously accepted proof.",
            )
        )
        registry.resolve(OBLIGATION_ID, fact.fact_id, graph)
        worker = RepairScriptWorker(())
        verifier = ScriptedVerifier(())
        solver = NodeSolver(
            worker=worker,
            verifier=verifier,
            config=NodeSolverConfig(max_attempts_per_obligation=3),
        )

        outcome = solver.solve_obligation(
            problem=ProblemSpec("p", GOAL),
            registry=registry,
            graph=graph,
            author="worker",
            obligation_id=OBLIGATION_ID,
            goal=GOAL,
            premise_fact_ids=(),
        )

        assert outcome.status == "SOLVED"
        assert outcome.fact is not None and outcome.fact.fact_id == fact.fact_id
        assert outcome.attempt_ids == ()
        assert worker.calls == verifier.calls == 0
        assert not (root / "attempts").exists()
