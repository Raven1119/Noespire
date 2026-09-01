"""Slice 3 — Execution: POST …/attempts, claim discipline, execution log,
outcome classification (spec §6/§7.2/§8.2). All execution is real
``solve_problem_once`` over scripted worker/verifier doubles; the doubles are
injected through ExecutionService factories, never by patching the core.

Since N1.14P a FRESH problem (no root obligation, no scaffold.json) is
scaffold-mode and goes through the Architect; these Slice-3 tests pin the
LEGACY_DIRECT path, so each one pre-creates the root obligation (the legacy
workspace shape) with ``add_open_obligation``.
"""

import json
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from application.execution import ExecutionService
from application.http import create_app

from research.fact import CandidateFact
from research.pipeline import VerificationResult

from application_fixtures import (
    BlockingWorker,
    ExplodingVerifier,
    ExplodingWorker,
    ScriptedVerifier,
    WorkspaceBuilder,
    add_open_obligation,
    run_attempt,
    wait_for,
)


def read_log(problem_dir: Path) -> list:
    log = problem_dir / "_execution_log.jsonl"
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def finished_events(problem_dir: Path) -> list:
    return [event for event in read_log(problem_dir) if event["kind"] == "ATTEMPT_FINISHED"]


class EchoWorker:
    """Candidate statement = the problem statement verbatim (contract-passing)."""

    def propose(self, *, problem, existing_facts, subgoal):
        return CandidateFact(problem, "A candidate proof.", ())


class ExecutionHttpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _client(self, service: ExecutionService) -> TestClient:
        return TestClient(create_app(self.builder.root, execution_service=service))

    def test_post_attempts_on_open_problem_returns_202_without_attempt_id(self) -> None:
        problem_dir = self.builder.add_problem("p-open", "Open theorem.")
        add_open_obligation(problem_dir, "p-open", "Open theorem.")
        service = ExecutionService(
            self.builder.root,
            worker_factory=EchoWorker,
            verifier_factory=lambda: ScriptedVerifier(True),
        )

        response = self._client(service).post("/api/problems/p-open/attempts")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"status": "accepted"})
        self.assertTrue(wait_for(lambda: not service.is_running("p-open")))

    def test_post_attempts_unknown_problem_returns_404(self) -> None:
        service = ExecutionService(
            self.builder.root,
            worker_factory=EchoWorker,
            verifier_factory=lambda: ScriptedVerifier(True),
        )

        response = self._client(service).post("/api/problems/p-missing/attempts")

        self.assertEqual(response.status_code, 404)

    def test_post_attempts_on_solved_problem_returns_409_already_solved(self) -> None:
        solved_dir = self.builder.add_problem("p-solved", "Solved theorem.")
        run_attempt(solved_dir, "p-solved", "Solved theorem.", accepted=True)
        calls = []

        def counting_worker():
            calls.append(1)
            return EchoWorker()

        service = ExecutionService(
            self.builder.root,
            worker_factory=counting_worker,
            verifier_factory=lambda: ScriptedVerifier(True),
        )

        response = self._client(service).post("/api/problems/p-solved/attempts")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "already_solved"})
        self.assertEqual(calls, [])

    def test_second_post_during_live_run_returns_409_already_running(self) -> None:
        problem_dir = self.builder.add_problem("p-live", "Live theorem.")
        add_open_obligation(problem_dir, "p-live", "Live theorem.")
        started, release = threading.Event(), threading.Event()
        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: BlockingWorker(
                CandidateFact("Live theorem.", "A candidate proof.", ()), started, release
            ),
            verifier_factory=lambda: ScriptedVerifier(True),
        )
        client = self._client(service)

        first = client.post("/api/problems/p-live/attempts")
        self.assertEqual(first.status_code, 202)
        self.assertTrue(started.wait(timeout=5))

        second = client.post("/api/problems/p-live/attempts")

        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json(), {"error": "already_running"})
        release.set()
        self.assertTrue(wait_for(lambda: not service.is_running("p-live")))

    def test_concurrent_double_start_exactly_one_accepted(self) -> None:
        for iteration in range(5):
            with self.subTest(iteration=iteration):
                self.builder.add_problem(f"p-conc-{iteration}", f"Concurrent theorem {iteration}.")
                add_open_obligation(
                    self.builder.root / f"p-conc-{iteration}",
                    f"p-conc-{iteration}",
                    f"Concurrent theorem {iteration}.",
                )
                started, release = threading.Event(), threading.Event()
                service = ExecutionService(
                    self.builder.root,
                    worker_factory=lambda: BlockingWorker(
                        CandidateFact(
                            f"Concurrent theorem {iteration}.", "A candidate proof.", ()
                        ),
                        started,
                        release,
                    ),
                    verifier_factory=lambda: ScriptedVerifier(True),
                )
                client = self._client(service)
                barrier = threading.Barrier(2)
                responses = []

                def do_post() -> None:
                    barrier.wait()
                    responses.append(client.post(f"/api/problems/p-conc-{iteration}/attempts"))

                threads = [threading.Thread(target=do_post) for _ in range(2)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

                self.assertEqual(sorted(r.status_code for r in responses), [202, 409])
                conflict = next(r for r in responses if r.status_code == 409)
                self.assertEqual(conflict.json(), {"error": "already_running"})
                self.assertTrue(started.wait(timeout=5))
                release.set()
                self.assertTrue(
                    wait_for(lambda: not service.is_running(f"p-conc-{iteration}"))
                )

    def test_concurrent_starts_on_different_problems_both_run(self) -> None:
        dir_a = self.builder.add_problem("p-a", "Shared statement theorem.")
        dir_b = self.builder.add_problem("p-b", "Shared statement theorem.")
        add_open_obligation(dir_a, "p-a", "Shared statement theorem.")
        add_open_obligation(dir_b, "p-b", "Shared statement theorem.")
        started, release = threading.Event(), threading.Event()
        worker_calls = []

        class CountingWorker(BlockingWorker):
            def propose(self, **kwargs):
                worker_calls.append(1)
                return super().propose(**kwargs)

        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: CountingWorker(
                CandidateFact("Shared statement theorem.", "A candidate proof.", ()),
                started,
                release,
            ),
            verifier_factory=lambda: ScriptedVerifier(True),
        )
        client = self._client(service)

        responses = [
            client.post("/api/problems/p-a/attempts"),
            client.post("/api/problems/p-b/attempts"),
        ]

        self.assertEqual([r.status_code for r in responses], [202, 202])
        self.assertTrue(wait_for(lambda: len(worker_calls) == 2))
        # Both are genuinely live at the same time.
        self.assertTrue(service.is_running("p-a"))
        self.assertTrue(service.is_running("p-b"))
        release.set()
        self.assertTrue(wait_for(lambda: len(worker_calls) == 2 and not service.is_running("p-a") and not service.is_running("p-b")))
        for problem_id in ("p-a", "p-b"):
            model = client.get(f"/api/problems/{problem_id}").json()
            self.assertEqual(model["status"], "SOLVED")


class FactoryFailureTests(unittest.TestCase):
    """Regression: a raising factory must not leak the active claim — the
    claim release is unconditional, and the failure is logged honestly."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_raising_verifier_factory_releases_claim_and_logs_runtime_error(self) -> None:
        problem_dir = self.builder.add_problem("p-fac", "Factory theorem.")
        add_open_obligation(problem_dir, "p-fac", "Factory theorem.")
        calls = []

        def flaky_verifier_factory():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Codex CLI is not installed or not on PATH")
            return ScriptedVerifier(True)

        service = ExecutionService(
            self.builder.root,
            worker_factory=EchoWorker,
            verifier_factory=flaky_verifier_factory,
        )

        service.start_attempt("p-fac")
        self.assertTrue(wait_for(lambda: not service.is_running("p-fac")))

        (event,) = finished_events(problem_dir)
        self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
        self.assertIsNone(event["attempt_id"])  # no attempt was ever allocated
        self.assertFalse(event["verifier_called"])

        # Claim released: the retry is accepted and succeeds.
        service.start_attempt("p-fac")
        self.assertTrue(wait_for(lambda: not service.is_running("p-fac")))
        outcomes = [e["outcome_stage"] for e in finished_events(problem_dir)]
        self.assertEqual(outcomes, ["RUNTIME_ERROR", "PASS"])

    def test_raising_worker_factory_releases_claim_and_logs_runtime_error(self) -> None:
        problem_dir = self.builder.add_problem("p-fac2", "Factory theorem two.")
        add_open_obligation(problem_dir, "p-fac2", "Factory theorem two.")
        calls = []

        def flaky_worker_factory():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("Codex CLI is not installed or not on PATH")
            return EchoWorker()

        service = ExecutionService(
            self.builder.root,
            worker_factory=flaky_worker_factory,
            verifier_factory=lambda: ScriptedVerifier(True),
        )

        service.start_attempt("p-fac2")
        self.assertTrue(wait_for(lambda: not service.is_running("p-fac2")))

        (event,) = finished_events(problem_dir)
        self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
        self.assertIsNone(event["attempt_id"])

        service.start_attempt("p-fac2")
        self.assertTrue(wait_for(lambda: not service.is_running("p-fac2")))
        outcomes = [e["outcome_stage"] for e in finished_events(problem_dir)]
        self.assertEqual(outcomes, ["RUNTIME_ERROR", "PASS"])


class ExecutionOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _run_once(self, problem_id, worker_factory, verifier_factory):
        # Legacy-mode shape: pre-create the root obligation so the execution
        # takes the LEGACY_DIRECT path these tests pin (fresh problems are
        # scaffold-mode since N1.14P).
        from application.problem_index import ProblemIndex

        statement = ProblemIndex(self.builder.root).get(problem_id).statement
        add_open_obligation(self.builder.root / problem_id, problem_id, statement)
        service = ExecutionService(
            self.builder.root,
            worker_factory=worker_factory,
            verifier_factory=verifier_factory,
        )
        service.start_attempt(problem_id)
        self.assertTrue(wait_for(lambda: not service.is_running(problem_id)))
        return service

    def test_verifier_rejection_classifies_fresh_verifier_reject(self) -> None:
        problem_dir = self.builder.add_problem("p-rej", "Rejected theorem.")

        self._run_once("p-rej", EchoWorker, lambda: ScriptedVerifier(False))

        events = finished_events(problem_dir)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["problem_id"], "p-rej")
        self.assertEqual(event["attempt_id"], "attempt-000001")
        self.assertEqual(event["outcome_stage"], "FRESH_VERIFIER_REJECT")
        self.assertTrue(event["verifier_called"])
        self.assertIsNotNone(event["started_at"])
        self.assertIsNotNone(event["finished_at"])
        self.assertIsNotNone(event["execution_id"])

    def test_contract_guard_classifies_without_verifier_call(self) -> None:
        problem_dir = self.builder.add_problem("p-guard", "Guarded theorem.")
        verifier_calls = []

        class GuardVerifier:
            def verify(self, problem, candidate, predecessors):
                verifier_calls.append(1)
                return VerificationResult(True, "should never be called")

        self._run_once(
            "p-guard",
            lambda: type(
                "MismatchedWorker",
                (),
                {"propose": lambda self, **kw: CandidateFact("A different statement.", "P.", ())},
            )(),
            GuardVerifier,
        )

        self.assertEqual(verifier_calls, [])
        event = finished_events(problem_dir)[0]
        self.assertEqual(event["outcome_stage"], "CONTRACT_GUARD")
        self.assertFalse(event["verifier_called"])
        self.assertEqual(event["attempt_id"], "attempt-000001")

    def test_pass_classifies_and_solves(self) -> None:
        problem_dir = self.builder.add_problem("p-pass", "Passing theorem.")

        self._run_once("p-pass", EchoWorker, lambda: ScriptedVerifier(True))

        event = finished_events(problem_dir)[0]
        self.assertEqual(event["outcome_stage"], "PASS")
        self.assertTrue(event["verifier_called"])

    def test_worker_exception_is_runtime_error_and_releases_claim(self) -> None:
        problem_dir = self.builder.add_problem("p-boom", "Fragile theorem.")
        add_open_obligation(problem_dir, "p-boom", "Fragile theorem.")
        workers = iter(
            [ExplodingWorker(), EchoWorker()]
        )
        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: next(workers),
            verifier_factory=lambda: ScriptedVerifier(True),
        )

        service.start_attempt("p-boom")
        self.assertTrue(wait_for(lambda: not service.is_running("p-boom")))

        event = finished_events(problem_dir)[0]
        self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
        self.assertFalse(event["verifier_called"])
        self.assertEqual(event["attempt_id"], "attempt-000001")

        # The claim was released: a retry is accepted and can succeed.
        service.start_attempt("p-boom")
        self.assertTrue(wait_for(lambda: not service.is_running("p-boom")))
        outcomes = [e["outcome_stage"] for e in finished_events(problem_dir)]
        self.assertEqual(outcomes, ["RUNTIME_ERROR", "PASS"])

    def test_verifier_exception_is_runtime_error_with_verifier_called(self) -> None:
        problem_dir = self.builder.add_problem("p-verr", "Verifier-fragile theorem.")

        self._run_once("p-verr", EchoWorker, ExplodingVerifier)

        event = finished_events(problem_dir)[0]
        self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
        self.assertTrue(event["verifier_called"])
        self.assertEqual(event["attempt_id"], "attempt-000001")

    def test_verifier_invoked_is_appended_before_the_real_call(self) -> None:
        problem_dir = self.builder.add_problem("p-order", "Ordering theorem.")
        observed = {}

        class OrderingVerifier:
            def verify(self, problem, candidate, predecessors):
                invoked = [
                    event
                    for event in read_log(problem_dir)
                    if event["kind"] == "VERIFIER_INVOKED"
                ]
                observed["event"] = invoked[-1] if invoked else None
                return VerificationResult(True, "ok")

        self._run_once("p-order", EchoWorker, OrderingVerifier)

        # The inner verifier itself observed the VERIFIER_INVOKED line already
        # on disk when it ran (frozen ordering contract, spec §7.2).
        event = observed["event"]
        self.assertIsNotNone(event)
        self.assertEqual(event["problem_id"], "p-order")
        self.assertEqual(event["attempt_id"], "attempt-000001")
        self.assertIn("execution_id", event)
        self.assertIn("ts", event)


    def test_worker_invoked_is_appended_before_the_real_call(self) -> None:
        problem_dir = self.builder.add_problem("p-worder", "Worker ordering theorem.")
        observed = {}

        class OrderingWorker:
            def propose(self, *, problem, existing_facts, subgoal):
                invoked = [
                    event
                    for event in read_log(problem_dir)
                    if event["kind"] == "WORKER_INVOKED"
                ]
                observed["event"] = invoked[-1] if invoked else None
                return CandidateFact(problem, "A candidate proof.", ())

        self._run_once("p-worder", OrderingWorker, lambda: ScriptedVerifier(True))

        # The inner worker itself observed the WORKER_INVOKED line already on
        # disk when it ran (same before-call ordering contract as the verifier).
        event = observed["event"]
        self.assertIsNotNone(event)
        self.assertEqual(event["problem_id"], "p-worder")
        self.assertEqual(event["attempt_id"], "attempt-000001")
        self.assertIn("execution_id", event)
        self.assertIn("ts", event)


class DefaultFactoryIsolationTests(unittest.TestCase):
    """Production wiring: the default factories build worker/verifier over
    fresh IsolatedCodexInvoker instances (Docker is the boundary), and an
    isolation failure fails closed — RUNTIME_ERROR + claim released."""

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_default_factories_build_separate_isolated_invokers(self) -> None:
        import application.execution as execution_module

        created = []

        class RecordingInvoker:
            def __init__(self, **kwargs):
                created.append(kwargs)

        service = ExecutionService(self.builder.root)
        with mock.patch.object(execution_module, "IsolatedCodexInvoker", RecordingInvoker):
            worker = service.worker_factory()
            verifier = service.verifier_factory()

        self.assertIsInstance(worker.codex, RecordingInvoker)
        self.assertIsInstance(verifier.codex, RecordingInvoker)
        # Separate fresh invoker instances, constructed with production
        # defaults (the service passes no overrides).
        self.assertIsNot(worker.codex, verifier.codex)
        self.assertEqual(created, [{}, {}])

    def test_invoker_constructor_defaults_are_the_settled_production_values(self) -> None:
        import inspect

        from application.codex_isolation import IsolatedCodexInvoker

        parameters = inspect.signature(IsolatedCodexInvoker.__init__).parameters
        self.assertEqual(parameters["image"].default, "noespire-codex-isolated:local")
        self.assertEqual(parameters["auth_dir"].default, Path.home() / ".codex")
        self.assertEqual(parameters["timeout_seconds"].default, 600)

    def test_isolation_unavailable_fails_closed_and_releases_claim(self) -> None:
        import application.execution as execution_module

        from application.codex_isolation import IsolationUnavailableError

        problem_dir = self.builder.add_problem("p-iso", "Isolated theorem.")
        service = ExecutionService(self.builder.root)

        def raising_invoker(**kwargs):
            raise IsolationUnavailableError("docker daemon unavailable")

        with mock.patch.object(execution_module, "IsolatedCodexInvoker", raising_invoker):
            service.start_attempt("p-iso")
            self.assertTrue(wait_for(lambda: not service.is_running("p-iso")))

            (event,) = finished_events(problem_dir)
            self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
            self.assertIsNone(event["attempt_id"])  # no attempt was ever allocated

            # The claim was released: a retry is accepted (not 409), and also
            # fails closed while isolation stays unavailable.
            service.start_attempt("p-iso")
            self.assertTrue(wait_for(lambda: not service.is_running("p-iso")))

        outcomes = [e["outcome_stage"] for e in finished_events(problem_dir)]
        self.assertEqual(outcomes, ["RUNTIME_ERROR", "RUNTIME_ERROR"])


if __name__ == "__main__":
    unittest.main()
