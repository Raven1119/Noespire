import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus
from research.pipeline import VerificationResult
from research.problem import ProblemSpec, solve_problem_once


class ScriptedWorker:
    def __init__(self, candidate: CandidateFact) -> None:
        self.candidate = candidate
        self.calls = 0
        self.received_facts = []

    def propose(self, *, problem, existing_facts, subgoal):
        self.calls += 1
        self.received_facts = list(existing_facts)
        return self.candidate


class ScriptedVerifier:
    def __init__(self, accepted: bool) -> None:
        self.accepted = accepted
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(self.accepted, "scripted verdict")


class ExplodingWorker:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal):
        self.calls += 1
        raise RuntimeError("scripted worker error")


class ExplodingVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        raise RuntimeError("scripted verifier error")


class ProblemExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.graph = FactGraph(self.root / "truth")
        self.registry = ObligationRegistry(self.root / "obligations.json")

    def _solve(self, problem: ProblemSpec, *, accepted: bool):
        worker = ScriptedWorker(
            CandidateFact(
                problem.statement,
                "A candidate proof.",
                problem.premise_fact_ids,
            )
        )
        verifier = ScriptedVerifier(accepted)
        result = solve_problem_once(
            problem=problem,
            registry=self.registry,
            graph=self.graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )
        return result, worker, verifier

    def test_problem_creates_single_root_obligation(self) -> None:
        problem = ProblemSpec("p", "Prove target T.")

        self._solve(problem, accepted=False)

        self.assertEqual(len(self.registry.list()), 1)
        self.assertEqual(self.registry.list()[0].obligation_id, "root:p")

    def test_root_goal_equals_exact_problem_statement(self) -> None:
        problem = ProblemSpec("p", "For every positive integer n, prove T(n).")

        self._solve(problem, accepted=False)

        self.assertEqual(self.registry.get("root:p").goal, problem.statement)

    def test_default_root_has_no_premise_facts(self) -> None:
        self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(self.registry.get("root:p").premises, ())

    def test_verified_premises_are_preserved(self) -> None:
        premise = self.graph.add_fact(
            Fact.create(
                problem_id="p",
                author="worker",
                statement="Verified premise P.",
                proof="Proof of P.",
            )
        )
        problem = ProblemSpec("p", "Prove target T.", (premise.fact_id,))

        _, worker, _ = self._solve(problem, accepted=False)

        obligation = self.registry.get("root:p")
        self.assertEqual(obligation.premises, (premise.fact_id,))
        self.assertEqual([fact.fact_id for fact in worker.received_facts], [premise.fact_id])

    def test_invalid_premise_is_rejected_before_worker(self) -> None:
        problem = ProblemSpec("p", "Prove target T.", ("missing-fact",))
        worker = ScriptedWorker(CandidateFact(problem.statement, "Proof.", ("missing-fact",)))
        verifier = ScriptedVerifier(True)

        with self.assertRaises(KeyError):
            solve_problem_once(
                problem=problem,
                registry=self.registry,
                graph=self.graph,
                author="worker",
                worker=worker,
                verifier=verifier,
            )

        self.assertEqual(worker.calls, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(self.registry.list(), [])

    def test_problem_id_cannot_silently_change_statement(self) -> None:
        self._solve(ProblemSpec("p", "First theorem."), accepted=False)
        worker = ScriptedWorker(CandidateFact("Second theorem.", "Proof.", ()))

        with self.assertRaisesRegex(ValueError, "problem ID collision"):
            solve_problem_once(
                problem=ProblemSpec("p", "Second theorem."),
                registry=self.registry,
                graph=self.graph,
                author="worker",
                worker=worker,
                verifier=ScriptedVerifier(True),
            )

        self.assertEqual(worker.calls, 0)

    def test_problem_is_not_fact_before_proof(self) -> None:
        ProblemSpec("p", "Prove target T.")

        self.assertEqual(self.graph.list_facts(), [])

    def test_failed_problem_attempt_does_not_mutate_fact_graph(self) -> None:
        before = self.graph.list_facts()

        self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(self.graph.list_facts(), before)

    def test_solved_problem_requires_accepted_target_fact(self) -> None:
        result, _, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(result.status, "OPEN")
        self.assertIsNone(result.target_fact_id)

    def test_problem_attempt_invokes_worker_once(self) -> None:
        _, worker, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(worker.calls, 1)

    def test_problem_attempt_invokes_verifier_once(self) -> None:
        _, _, verifier = self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(verifier.calls, 1)

    def test_failure_does_not_auto_retry(self) -> None:
        _, worker, verifier = self._solve(
            ProblemSpec("p", "Prove target T."),
            accepted=False,
        )

        self.assertEqual(worker.calls, 1)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(len(list((self.root / "attempts").glob("*.json"))), 1)

    def test_pass_returns_solved_result(self) -> None:
        result, _, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=True)

        self.assertEqual(result.status, "SOLVED")

    def test_pass_discharges_root_obligation(self) -> None:
        self._solve(ProblemSpec("p", "Prove target T."), accepted=True)

        self.assertEqual(self.registry.get("root:p").status, ObligationStatus.DISCHARGED)

    def test_pass_returns_target_fact_id(self) -> None:
        result, _, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=True)

        self.assertIsNotNone(result.target_fact_id)
        self.assertEqual(self.graph.get_fact(result.target_fact_id or "").statement, "Prove target T.")
        self.assertEqual(len(self.graph.list_facts()), 1)

    def test_pass_returns_supporting_closure(self) -> None:
        premise = self.graph.add_fact(
            Fact.create(
                problem_id="p",
                author="worker",
                statement="Verified premise P.",
                proof="Proof of P.",
            )
        )
        problem = ProblemSpec("p", "Prove target T.", (premise.fact_id,))

        result, _, _ = self._solve(problem, accepted=True)

        self.assertEqual(
            result.supporting_closure_fact_ids,
            (premise.fact_id, result.target_fact_id),
        )

    def test_fail_returns_open_result(self) -> None:
        result, _, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(result.status, "OPEN")

    def test_fail_keeps_root_open(self) -> None:
        self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertEqual(self.registry.get("root:p").status, ObligationStatus.OPEN)

    def test_fail_keeps_resolved_fact_id_none(self) -> None:
        self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        self.assertIsNone(self.registry.get("root:p").resolved_by_fact_id)

    def test_failed_attempt_persists_evidence(self) -> None:
        result, _, _ = self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        artifact = json.loads(
            (self.root / "attempts" / f"{result.attempt_id}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(artifact["problem_id"], "p")
        self.assertEqual(artifact["obligation_id"], "root:p")
        self.assertEqual(artifact["candidate_artifact"]["statement"], "Prove target T.")
        self.assertFalse(artifact["verifier_artifact"]["accepted"])
        self.assertEqual(artifact["verdict"], "FAIL")

    def test_solved_reload_does_not_reinvoke_worker(self) -> None:
        problem = ProblemSpec("p", "Prove target T.")
        first, _, _ = self._solve(problem, accepted=True)
        reloaded_graph = FactGraph(self.root / "truth")
        reloaded_registry = ObligationRegistry(self.root / "obligations.json")
        worker = ScriptedWorker(CandidateFact(problem.statement, "Unused proof.", ()))
        verifier = ScriptedVerifier(False)

        second = solve_problem_once(
            problem=problem,
            registry=reloaded_registry,
            graph=reloaded_graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        self.assertEqual(second.status, "SOLVED")
        self.assertEqual(second.target_fact_id, first.target_fact_id)
        self.assertEqual(worker.calls, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(len(list((self.root / "attempts").glob("*.json"))), 1)

    def test_open_reload_preserves_state(self) -> None:
        self._solve(ProblemSpec("p", "Prove target T."), accepted=False)

        reloaded = ObligationRegistry(self.root / "obligations.json").get("root:p")

        self.assertEqual(reloaded.status, ObligationStatus.OPEN)
        self.assertIsNone(reloaded.resolved_by_fact_id)

    def test_worker_exception_reopens_root_and_persists_error_evidence(self) -> None:
        worker = ExplodingWorker()

        with self.assertRaisesRegex(RuntimeError, "scripted worker error"):
            solve_problem_once(
                problem=ProblemSpec("p", "Prove target T."),
                registry=self.registry,
                graph=self.graph,
                author="worker",
                worker=worker,
                verifier=ScriptedVerifier(True),
            )

        obligation = self.registry.get("root:p")
        artifact_path = next((self.root / "attempts").glob("*.json"))
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(worker.calls, 1)
        self.assertEqual(obligation.status, ObligationStatus.OPEN)
        self.assertEqual(artifact["verdict"], "ERROR")
        self.assertEqual(artifact["error"], "scripted worker error")

    def test_attempt_write_failure_does_not_launch_worker(self) -> None:
        (self.root / "attempts").write_text("not a directory", encoding="utf-8")
        worker = ScriptedWorker(CandidateFact("Prove target T.", "Proof.", ()))
        verifier = ScriptedVerifier(True)

        with self.assertRaises(FileExistsError):
            solve_problem_once(
                problem=ProblemSpec("p", "Prove target T."),
                registry=self.registry,
                graph=self.graph,
                author="worker",
                worker=worker,
                verifier=verifier,
            )

        self.assertEqual(worker.calls, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(self.registry.get("root:p").status, ObligationStatus.OPEN)
        self.assertEqual(self.graph.list_facts(), [])

    def test_verifier_exception_preserves_candidate_and_reopens_root(self) -> None:
        problem = ProblemSpec("p", "Prove target T.")
        worker = ScriptedWorker(CandidateFact(problem.statement, "Candidate proof.", ()))
        verifier = ExplodingVerifier()

        with self.assertRaisesRegex(RuntimeError, "scripted verifier error"):
            solve_problem_once(
                problem=problem,
                registry=self.registry,
                graph=self.graph,
                author="worker",
                worker=worker,
                verifier=verifier,
            )

        artifact_path = next((self.root / "attempts").glob("*.json"))
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        self.assertEqual(worker.calls, 1)
        self.assertEqual(verifier.calls, 1)
        self.assertEqual(self.registry.get("root:p").status, ObligationStatus.OPEN)
        self.assertEqual(artifact["candidate_artifact"]["proof"], "Candidate proof.")
        self.assertEqual(artifact["verdict"], "ERROR")


if __name__ == "__main__":
    unittest.main()
