"""Slice 3 — startup crash-consistency recovery (spec §7.3).

Crashes are simulated by hand-crafting on-disk state with the real core
constructors (application_fixtures patterns), never by killing threads.
Each recovery run is a fresh ``ExecutionService.recover_stale_running()`` —
the same code path the FastAPI lifespan invokes.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from application.execution import ExecutionService
from application.http import create_app
from application.workspace_read_model import build_read_model

from research.obligation import ObligationStatus

from application_fixtures import (
    WorkspaceBuilder,
    add_fact,
    add_open_obligation,
    append_log,
    candidate_artifact,
    registry_for,
    write_pass_attempt,
    write_residual_running_attempt,
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


class RecoveryTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _service(self) -> ExecutionService:
        # Recovery never invokes worker/verifier factories; no doubles needed.
        return ExecutionService(self.builder.root)

    def _running_obligation(self, problem_dir: Path, problem_id: str, statement: str) -> None:
        add_open_obligation(problem_dir, problem_id, statement)
        registry_for(problem_dir).transition(f"root:{problem_id}", ObligationStatus.RUNNING)


class CrashWindowTests(RecoveryTestBase):
    def test_window_a_running_no_candidate_recovers_interrupted(self) -> None:
        problem_dir = self.builder.add_problem("p-a", "Crash theorem A.")
        self._running_obligation(problem_dir, "p-a", "Crash theorem A.")
        attempt_id = write_residual_running_attempt(problem_dir, "p-a")

        self._service().recover_stale_running()

        obligation = registry_for(problem_dir).get("root:p-a")
        self.assertEqual(obligation.status, ObligationStatus.OPEN)
        events = read_log(problem_dir)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["kind"], "RECOVERED_INTERRUPTED")
        self.assertEqual(event["problem_id"], "p-a")
        self.assertEqual(event["attempt_id"], attempt_id)
        self.assertTrue(event["execution_id"].startswith("recovery-"))
        self.assertFalse(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-a")
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"][0]["failure_class"], "interrupted")
        self.assertFalse(model["attempts"][0]["verifier_called"])

    def test_window_b_candidate_persisted_verifier_never_called(self) -> None:
        problem_dir = self.builder.add_problem("p-b", "Crash theorem B.")
        self._running_obligation(problem_dir, "p-b", "Crash theorem B.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-b", candidate=candidate_artifact("Crash theorem B.")
        )

        self._service().recover_stale_running()

        self.assertEqual(
            registry_for(problem_dir).get("root:p-b").status, ObligationStatus.OPEN
        )
        (event,) = read_log(problem_dir)
        self.assertEqual(event["kind"], "RECOVERED_INTERRUPTED")
        self.assertEqual(event["attempt_id"], attempt_id)
        self.assertTrue(event["execution_id"].startswith("recovery-"))
        self.assertFalse(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-b")
        self.assertEqual(model["status"], "OPEN")
        self.assertFalse(model["attempts"][0]["verifier_called"])

    def test_window_c_orphan_verifier_invoked_binds_execution_id(self) -> None:
        problem_dir = self.builder.add_problem("p-c", "Crash theorem C.")
        self._running_obligation(problem_dir, "p-c", "Crash theorem C.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-c", candidate=candidate_artifact("Crash theorem C.")
        )
        append_log(
            problem_dir,
            {
                "kind": "VERIFIER_INVOKED",
                "execution_id": "exec-orphan",
                "problem_id": "p-c",
                "attempt_id": attempt_id,
                "ts": "t1",
            },
        )

        self._service().recover_stale_running()

        events = read_log(problem_dir)
        (event,) = [e for e in events if e["kind"] == "RECOVERED_INTERRUPTED"]
        # Exactly one orphan VERIFIER_INVOKED -> its execution_id is reused,
        # which is what makes the read model's verifier_called honest.
        self.assertEqual(event["execution_id"], "exec-orphan")
        self.assertTrue(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-c")
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"][0]["failure_class"], "interrupted")
        self.assertTrue(model["attempts"][0]["verifier_called"])

    def test_window_c2_finished_invocation_is_not_an_orphan(self) -> None:
        problem_dir = self.builder.add_problem("p-c2", "Crash theorem C2.")
        self._running_obligation(problem_dir, "p-c2", "Crash theorem C2.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-c2", candidate=candidate_artifact("Crash theorem C2.")
        )
        # A VERIFIER_INVOKED whose execution DID finish is not orphan evidence.
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-done", "problem_id": "p-c2", "ts": "t0"},
            {
                "kind": "ATTEMPT_FINISHED",
                "execution_id": "exec-done",
                "problem_id": "p-c2",
                "attempt_id": "attempt-000000",
                "started_at": "t0",
                "finished_at": "t1",
                "outcome_stage": "RUNTIME_ERROR",
                "verifier_called": True,
            },
        )

        self._service().recover_stale_running()

        (event,) = [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_INTERRUPTED"]
        self.assertTrue(event["execution_id"].startswith("recovery-"))
        self.assertFalse(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-c2")
        self.assertFalse(model["attempts"][0]["verifier_called"])

    def test_window_d_pass_evidence_without_fact_recovers_interrupted(self) -> None:
        """Crash between verifier PASS and add_fact: NEVER materialize a Fact
        from PASS evidence (§7.3)."""
        problem_dir = self.builder.add_problem("p-d", "Crash theorem D.")
        self._running_obligation(problem_dir, "p-d", "Crash theorem D.")
        attempt_id = write_pass_attempt(problem_dir, "p-d", "Crash theorem D.")
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-d", "problem_id": "p-d",
             "attempt_id": attempt_id, "ts": "t1"},
        )

        self._service().recover_stale_running()

        self.assertEqual(
            registry_for(problem_dir).get("root:p-d").status, ObligationStatus.OPEN
        )
        (event,) = [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_INTERRUPTED"]
        self.assertEqual(event["attempt_id"], attempt_id)
        self.assertEqual(event["execution_id"], "exec-d")
        self.assertTrue(event["verifier_called"])
        # No Fact was materialized from the PASS evidence.
        self.assertEqual(list((problem_dir / "facts").glob("*.md")), [])
        model = build_read_model(self.builder.root, "p-d")
        self.assertEqual(model["status"], "OPEN")
        # The attempt file (verdict PASS) is not reinterpreted as interrupted:
        # only verdict-RUNNING attempts map to interrupted.
        self.assertEqual(model["attempts"][0]["verdict"], "PASS")

    def test_window_e_pass_evidence_with_fact_recovers_discharged(self) -> None:
        """Crash between add_fact and resolve: discharge via the public
        registry.resolve (§7.3 case 1)."""
        problem_dir = self.builder.add_problem("p-e", "Crash theorem E.")
        self._running_obligation(problem_dir, "p-e", "Crash theorem E.")
        attempt_id = write_pass_attempt(problem_dir, "p-e", "Crash theorem E.")
        fact = add_fact(problem_dir, "p-e", "Crash theorem E.", "A candidate proof.")
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-e", "problem_id": "p-e",
             "attempt_id": attempt_id, "ts": "t1"},
        )

        self._service().recover_stale_running()

        obligation = registry_for(problem_dir).get("root:p-e")
        self.assertEqual(obligation.status, ObligationStatus.DISCHARGED)
        self.assertEqual(obligation.resolved_by_fact_id, fact.fact_id)
        (event,) = [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_DISCHARGED"]
        self.assertEqual(event["problem_id"], "p-e")
        self.assertEqual(event["attempt_id"], attempt_id)
        model = build_read_model(self.builder.root, "p-e")
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["target_fact"]["fact_id"], fact.fact_id)
        self.assertIsNone(model["attempts"][0]["failure_class"])
        self.assertNotIn("live", model)


class RecoveryIdempotenceTests(RecoveryTestBase):
    def test_second_startup_after_interrupted_recovery_is_a_noop(self) -> None:
        problem_dir = self.builder.add_problem("p-i", "Crash theorem I.")
        self._running_obligation(problem_dir, "p-i", "Crash theorem I.")
        write_residual_running_attempt(problem_dir, "p-i")

        self._service().recover_stale_running()
        first_log = read_log(problem_dir)
        first_obligation = registry_for(problem_dir).get("root:p-i")

        self._service().recover_stale_running()

        self.assertEqual(read_log(problem_dir), first_log)
        self.assertEqual(registry_for(problem_dir).get("root:p-i"), first_obligation)

    def test_second_startup_after_discharged_recovery_is_a_noop(self) -> None:
        problem_dir = self.builder.add_problem("p-i2", "Crash theorem I2.")
        self._running_obligation(problem_dir, "p-i2", "Crash theorem I2.")
        write_pass_attempt(problem_dir, "p-i2", "Crash theorem I2.")
        add_fact(problem_dir, "p-i2", "Crash theorem I2.", "A candidate proof.")

        self._service().recover_stale_running()
        first_log = read_log(problem_dir)

        self._service().recover_stale_running()

        self.assertEqual(read_log(problem_dir), first_log)
        self.assertEqual(
            registry_for(problem_dir).get("root:p-i2").status, ObligationStatus.DISCHARGED
        )

    def test_non_indexed_directories_are_never_scanned(self) -> None:
        problem_dir = self.builder.root / "p-stray"
        problem_dir.mkdir(parents=True)
        self._running_obligation(problem_dir, "p-stray", "Stray theorem.")
        write_residual_running_attempt(problem_dir, "p-stray")

        self._service().recover_stale_running()

        self.assertEqual(
            registry_for(problem_dir).get("root:p-stray").status, ObligationStatus.RUNNING
        )
        self.assertEqual(read_log(problem_dir), [])


class StartupLifespanTests(RecoveryTestBase):
    def test_startup_recovery_runs_via_testclient_lifespan(self) -> None:
        problem_dir = self.builder.add_problem("p-life", "Crash theorem L.")
        self._running_obligation(problem_dir, "p-life", "Crash theorem L.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-life", candidate=candidate_artifact("Crash theorem L.")
        )

        with TestClient(create_app(self.builder.root)) as client:
            model = client.get("/api/problems/p-life").json()

        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"][0]["attempt_id"], attempt_id)
        self.assertEqual(model["attempts"][0]["failure_class"], "interrupted")

        # A second server start does not duplicate recovery events.
        with TestClient(create_app(self.builder.root)):
            pass
        events = [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_INTERRUPTED"]
        self.assertEqual(len(events), 1)

    def test_startup_does_not_touch_healthy_problems(self) -> None:
        from application_fixtures import run_attempt

        solved_dir = self.builder.add_problem("p-ok", "Healthy theorem.")
        run_attempt(solved_dir, "p-ok", "Healthy theorem.", accepted=True)
        open_dir = self.builder.add_problem("p-open", "Fresh theorem.")

        with TestClient(create_app(self.builder.root)) as client:
            solved = client.get("/api/problems/p-ok").json()
            fresh = client.get("/api/problems/p-open").json()

        self.assertEqual(solved["status"], "SOLVED")
        self.assertEqual(fresh["status"], "OPEN")
        self.assertEqual(read_log(solved_dir), [])
        self.assertEqual(read_log(open_dir), [])


if __name__ == "__main__":
    unittest.main()
