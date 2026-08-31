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


class LogCompletionTests(RecoveryTestBase):
    """Late crash window (spec §7.3 amendment): the verifier answered, the
    core persisted the verdict and reset the obligation to OPEN, then the
    process died BEFORE ATTEMPT_FINISHED. Startup log completion appends a
    recovered finish record — timestamps never fabricated."""

    def test_late_window_fail_after_verifier_gets_recovered_finish(self) -> None:
        from application_fixtures import run_attempt

        problem_dir = self.builder.add_problem("p-late", "Late theorem.")
        result = run_attempt(problem_dir, "p-late", "Late theorem.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-late", "problem_id": "p-late",
             "attempt_id": result.attempt_id, "ts": "t1"},
        )

        self._service().recover_stale_running()

        (event,) = [e for e in read_log(problem_dir) if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertEqual(event["attempt_id"], result.attempt_id)
        self.assertEqual(event["execution_id"], "exec-late")
        self.assertEqual(event["outcome_stage"], "FRESH_VERIFIER_REJECT")
        self.assertTrue(event["verifier_called"])
        self.assertTrue(event["recovered"])
        self.assertIsNone(event["started_at"])
        self.assertIsNone(event["finished_at"])
        attempt = build_read_model(self.builder.root, "p-late")["attempts"][0]
        self.assertEqual(attempt["failure_class"], "rejection")
        self.assertIsNone(attempt["started_at"])
        self.assertIsNone(attempt["finished_at"])

    def test_late_window_contract_guard_gets_recovered_finish(self) -> None:
        from application_fixtures import run_attempt

        problem_dir = self.builder.add_problem("p-guard", "Guard theorem.")
        # A prior V1-wrapped execution, fully logged.
        first = run_attempt(problem_dir, "p-guard", "Guard theorem.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-1", "problem_id": "p-guard",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-1", "problem_id": "p-guard",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-1", "problem_id": "p-guard",
             "attempt_id": first.attempt_id, "started_at": "t0", "finished_at": "t1",
             "outcome_stage": "FRESH_VERIFIER_REJECT", "verifier_called": True},
        )
        result = run_attempt(
            problem_dir, "p-guard", "Guard theorem.",
            accepted=True, candidate_statement="A different statement.",
        )
        # Contract-guard late window: the V1 wrapper DID run (WORKER_INVOKED
        # names this attempt) but the fresh verifier was never called (no
        # VERIFIER_INVOKED names it) and the crash took the finish record.
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-2", "problem_id": "p-guard",
             "attempt_id": result.attempt_id, "ts": "t2"},
        )

        self._service().recover_stale_running()

        finishes = [
            e for e in read_log(problem_dir)
            if e["kind"] == "ATTEMPT_FINISHED" and e["attempt_id"] == result.attempt_id
        ]
        self.assertEqual(len(finishes), 1)
        event = finishes[0]
        self.assertEqual(event["outcome_stage"], "CONTRACT_GUARD")
        self.assertFalse(event["verifier_called"])
        self.assertTrue(event["recovered"])
        attempt = build_read_model(self.builder.root, "p-guard")["attempts"][1]
        self.assertEqual(attempt["failure_class"], "contract")

    def test_late_window_error_gets_recovered_finish(self) -> None:
        from application_fixtures import run_attempt, run_error_attempt

        problem_dir = self.builder.add_problem("p-err", "Error theorem.")
        first = run_attempt(problem_dir, "p-err", "Error theorem.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-1", "problem_id": "p-err",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-1", "problem_id": "p-err",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-1", "problem_id": "p-err",
             "attempt_id": first.attempt_id, "started_at": "t0", "finished_at": "t1",
             "outcome_stage": "FRESH_VERIFIER_REJECT", "verifier_called": True},
        )
        run_error_attempt(problem_dir, "p-err", "Error theorem.")
        # The V1 wrapper invoked the worker (which then raised); the crash
        # took the finish record.
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-2", "problem_id": "p-err",
             "attempt_id": "attempt-000002", "ts": "t2"},
        )

        self._service().recover_stale_running()

        finishes = [
            e for e in read_log(problem_dir)
            if e["kind"] == "ATTEMPT_FINISHED" and e["attempt_id"] == "attempt-000002"
        ]
        self.assertEqual(len(finishes), 1)
        event = finishes[0]
        self.assertEqual(event["outcome_stage"], "RUNTIME_ERROR")
        self.assertFalse(event["verifier_called"])
        self.assertTrue(event["recovered"])
        attempt = build_read_model(self.builder.root, "p-err")["attempts"][1]
        self.assertEqual(attempt["failure_class"], "runtime")

    def test_error_attempt_without_wrapper_provenance_stays_unclassified(self) -> None:
        """An ERROR attempt no attempt-named event covers (the core raised
        before the wrapper's worker call, or pre-wrapper evidence) is never
        classified — no evidence, no guess."""
        from application_fixtures import run_attempt, run_error_attempt

        problem_dir = self.builder.add_problem("p-errx", "Error theorem X.")
        first = run_attempt(problem_dir, "p-errx", "Error theorem X.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-1", "problem_id": "p-errx",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-1", "problem_id": "p-errx",
             "attempt_id": first.attempt_id, "ts": "t0"},
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-1", "problem_id": "p-errx",
             "attempt_id": first.attempt_id, "started_at": "t0", "finished_at": "t1",
             "outcome_stage": "FRESH_VERIFIER_REJECT", "verifier_called": True},
        )
        run_error_attempt(problem_dir, "p-errx", "Error theorem X.")
        # attempt-000002 has NO attempt-named event.

        self._service().recover_stale_running()

        finishes = [
            e for e in read_log(problem_dir)
            if e["kind"] == "ATTEMPT_FINISHED" and e["attempt_id"] == "attempt-000002"
        ]
        self.assertEqual(finishes, [])
        attempt = build_read_model(self.builder.root, "p-errx")["attempts"][1]
        self.assertEqual(attempt["verdict"], "ERROR")
        # Verdict ERROR maps to failure_class runtime from the verdict alone;
        # what must not happen is a fabricated finish record.
        self.assertIsNone(attempt["started_at"])
        self.assertIsNone(attempt["finished_at"])

    def test_pre_v1_attempt_survives_later_v1_execution_unclassified(self) -> None:
        """Per-attempt provenance: a pre-V1 FAIL attempt stays unclassified
        even after the problem later had a fully-logged V1 execution."""
        from application_fixtures import run_attempt

        problem_dir = self.builder.add_problem("p-mixed", "Mixed theorem.")
        pre_v1 = run_attempt(problem_dir, "p-mixed", "Mixed theorem.", accepted=False)
        # No events name the pre-V1 attempt. Later: a real V1-wrapped PASS.
        v1 = run_attempt(problem_dir, "p-mixed", "Mixed theorem.", accepted=True)
        append_log(
            problem_dir,
            {"kind": "WORKER_INVOKED", "execution_id": "exec-v1", "problem_id": "p-mixed",
             "attempt_id": v1.attempt_id, "ts": "t0"},
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-v1", "problem_id": "p-mixed",
             "attempt_id": v1.attempt_id, "ts": "t1"},
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-v1", "problem_id": "p-mixed",
             "attempt_id": v1.attempt_id, "started_at": "t0", "finished_at": "t2",
             "outcome_stage": "PASS", "verifier_called": True},
        )

        self._service().recover_stale_running()

        finishes = [
            e for e in read_log(problem_dir)
            if e["kind"] == "ATTEMPT_FINISHED" and e["attempt_id"] == pre_v1.attempt_id
        ]
        self.assertEqual(finishes, [])
        model = build_read_model(self.builder.root, "p-mixed")
        self.assertEqual(model["status"], "SOLVED")
        self.assertIsNone(model["attempts"][0]["failure_class"])
        self.assertIsNone(model["attempts"][1]["failure_class"])

    def test_late_window_pass_after_recovered_resolve(self) -> None:
        """Window E ordering: step one resolves the obligation first, then log
        completion appends the PASS finish record."""
        problem_dir = self.builder.add_problem("p-latep", "Late pass theorem.")
        self._running_obligation(problem_dir, "p-latep", "Late pass theorem.")
        attempt_id = write_pass_attempt(problem_dir, "p-latep", "Late pass theorem.")
        fact = add_fact(problem_dir, "p-latep", "Late pass theorem.", "A candidate proof.")
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-p", "problem_id": "p-latep",
             "attempt_id": attempt_id, "ts": "t1"},
        )

        self._service().recover_stale_running()

        events = read_log(problem_dir)
        kinds = [e["kind"] for e in events]
        self.assertLess(kinds.index("RECOVERED_DISCHARGED"), kinds.index("ATTEMPT_FINISHED"))
        finish = events[kinds.index("ATTEMPT_FINISHED")]
        self.assertEqual(finish["outcome_stage"], "PASS")
        self.assertEqual(finish["attempt_id"], attempt_id)
        self.assertTrue(finish["recovered"])
        self.assertTrue(finish["verifier_called"])
        self.assertIsNone(finish["started_at"])
        model = build_read_model(self.builder.root, "p-latep")
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["target_fact"]["fact_id"], fact.fact_id)
        self.assertIsNone(model["attempts"][0]["failure_class"])

    def test_log_completion_is_idempotent_across_startups(self) -> None:
        from application_fixtures import run_attempt

        problem_dir = self.builder.add_problem("p-idem", "Idempotent theorem.")
        run_attempt(problem_dir, "p-idem", "Idempotent theorem.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-i", "problem_id": "p-idem",
             "attempt_id": "attempt-000001", "ts": "t1"},
        )

        self._service().recover_stale_running()
        first = read_log(problem_dir)
        self._service().recover_stale_running()

        self.assertEqual(read_log(problem_dir), first)

    def test_log_less_workspace_is_never_classified(self) -> None:
        """Pre-V1 / hand-seeded evidence: attempts exist but the execution
        log has no events at all -> the attempt may predate the wrapper, so
        log completion stays out; failure_class remains honestly null."""
        from application_fixtures import run_attempt

        absent_dir = self.builder.add_problem("p-old", "Old theorem.")
        run_attempt(absent_dir, "p-old", "Old theorem.", accepted=False)
        empty_dir = self.builder.add_problem("p-empty", "Empty-log theorem.")
        run_attempt(empty_dir, "p-empty", "Empty-log theorem.", accepted=False)
        (empty_dir / "_execution_log.jsonl").write_text("", encoding="utf-8")

        self._service().recover_stale_running()

        self.assertEqual(read_log(absent_dir), [])
        self.assertEqual(read_log(empty_dir), [])
        for problem_id in ("p-old", "p-empty"):
            attempt = build_read_model(self.builder.root, problem_id)["attempts"][0]
            self.assertEqual(attempt["verdict"], "FAIL")
            self.assertIsNone(attempt["failure_class"])


class OrphanBindingRegressionTests(RecoveryTestBase):
    """Regression (per-attempt binding): a VERIFIER_INVOKED already consumed
    by an old RECOVERED_INTERRUPTED must not pollute a later crash's binding."""

    def _history_with_consumed_invocation(self, problem_dir: Path, problem_id: str) -> str:
        """Attempt-1 crashed and was already recovered; its exec-1 invocation
        is consumed history. Returns attempt-1's id."""
        self._running_obligation(problem_dir, problem_id, f"Theorem {problem_id}.")
        first = write_residual_running_attempt(problem_dir, problem_id, sequence=1)
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-1", "problem_id": problem_id,
             "attempt_id": first, "ts": "t1"},
            {"kind": "RECOVERED_INTERRUPTED", "execution_id": "exec-1", "problem_id": problem_id,
             "attempt_id": first, "verifier_called": True, "ts": "t2"},
        )
        registry_for(problem_dir).transition(f"root:{problem_id}", ObligationStatus.OPEN)
        return first

    def test_later_crash_binds_its_own_invocation(self) -> None:
        problem_dir = self.builder.add_problem("p-2a", "Theorem p-2a.")
        self._history_with_consumed_invocation(problem_dir, "p-2a")
        # Second lifetime: attempt-2 crashes after its own VERIFIER_INVOKED.
        registry_for(problem_dir).transition("root:p-2a", ObligationStatus.RUNNING)
        second = write_residual_running_attempt(
            problem_dir, "p-2a", sequence=2, candidate=candidate_artifact("Theorem p-2a.")
        )
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-2", "problem_id": "p-2a",
             "attempt_id": second, "ts": "t3"},
        )

        self._service().recover_stale_running()

        events = [
            e for e in read_log(problem_dir)
            if e["kind"] == "RECOVERED_INTERRUPTED" and e["attempt_id"] == second
        ]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["execution_id"], "exec-2")
        self.assertTrue(events[0]["verifier_called"])
        model = build_read_model(self.builder.root, "p-2a")
        self.assertEqual(model["attempts"][1]["failure_class"], "interrupted")
        self.assertTrue(model["attempts"][1]["verifier_called"])

    def test_later_crash_without_invocation_binds_fresh_id(self) -> None:
        problem_dir = self.builder.add_problem("p-2b", "Theorem p-2b.")
        self._history_with_consumed_invocation(problem_dir, "p-2b")
        # Second lifetime: attempt-2 crashes BEFORE the verifier ran — no
        # VERIFIER_INVOKED names attempt-2; attempt-1's consumed invocation is
        # irrelevant and must not leak in.
        registry_for(problem_dir).transition("root:p-2b", ObligationStatus.RUNNING)
        second = write_residual_running_attempt(
            problem_dir, "p-2b", sequence=2, candidate=candidate_artifact("Theorem p-2b.")
        )

        self._service().recover_stale_running()

        events = [
            e for e in read_log(problem_dir)
            if e["kind"] == "RECOVERED_INTERRUPTED" and e["attempt_id"] == second
        ]
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["execution_id"].startswith("recovery-"))
        self.assertFalse(events[0]["verifier_called"])
        model = build_read_model(self.builder.root, "p-2b")
        self.assertFalse(model["attempts"][1]["verifier_called"])


class TornLogLineRecoveryTests(RecoveryTestBase):
    """Regression: a crash mid-append leaves a truncated final JSONL line;
    the NEXT startup recovery must survive it (and stay survivable)."""

    def test_recovery_survives_truncated_final_log_line(self) -> None:
        problem_dir = self.builder.add_problem("p-torn", "Torn theorem.")
        self._running_obligation(problem_dir, "p-torn", "Torn theorem.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-torn", candidate=candidate_artifact("Torn theorem.")
        )
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-torn", "problem_id": "p-torn",
             "attempt_id": attempt_id, "ts": "t1"},
        )
        with (problem_dir / "_execution_log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write('{"kind": "ATTEMPT_FINI')  # torn mid-append, no newline

        self._service().recover_stale_running()

        events = read_log(problem_dir)
        recovered = [e for e in events if e["kind"] == "RECOVERED_INTERRUPTED"]
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0]["attempt_id"], attempt_id)
        self.assertEqual(recovered[0]["execution_id"], "exec-torn")
        self.assertTrue(recovered[0]["verifier_called"])
        self.assertEqual(
            registry_for(problem_dir).get("root:p-torn").status, ObligationStatus.OPEN
        )
        # The read model keeps working and the next startup stays clean.
        model = build_read_model(self.builder.root, "p-torn")
        self.assertTrue(model["attempts"][0]["verifier_called"])
        self._service().recover_stale_running()
        self.assertEqual(
            [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_INTERRUPTED"],
            recovered,
        )


class ResidualRunningAttemptTests(RecoveryTestBase):
    """Crash between core _start_attempt (attempt file, verdict RUNNING) and
    execute_obligation's OPEN->RUNNING transition: obligation stays OPEN but
    the residual attempt must still be recovered as interrupted."""

    def test_residual_running_attempt_under_open_obligation_is_recovered(self) -> None:
        problem_dir = self.builder.add_problem("p-res", "Residual theorem.")
        add_open_obligation(problem_dir, "p-res", "Residual theorem.")
        attempt_id = write_residual_running_attempt(problem_dir, "p-res")

        self._service().recover_stale_running()

        # No registry transition was needed or performed.
        self.assertEqual(
            registry_for(problem_dir).get("root:p-res").status, ObligationStatus.OPEN
        )
        (event,) = read_log(problem_dir)
        self.assertEqual(event["kind"], "RECOVERED_INTERRUPTED")
        self.assertEqual(event["attempt_id"], attempt_id)
        self.assertTrue(event["execution_id"].startswith("recovery-"))
        self.assertFalse(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-res")
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"][0]["failure_class"], "interrupted")
        self.assertNotIn("live", model)

    def test_residual_recovery_is_idempotent_across_startups(self) -> None:
        problem_dir = self.builder.add_problem("p-res2", "Residual theorem two.")
        add_open_obligation(problem_dir, "p-res2", "Residual theorem two.")
        write_residual_running_attempt(problem_dir, "p-res2")

        self._service().recover_stale_running()
        first = read_log(problem_dir)
        self._service().recover_stale_running()

        self.assertEqual(read_log(problem_dir), first)

    def test_residual_running_attempt_with_orphan_invocation_binds_it(self) -> None:
        problem_dir = self.builder.add_problem("p-res3", "Residual theorem three.")
        add_open_obligation(problem_dir, "p-res3", "Residual theorem three.")
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-res3", candidate=candidate_artifact("Residual theorem three.")
        )
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-res", "problem_id": "p-res3",
             "attempt_id": attempt_id, "ts": "t1"},
        )

        self._service().recover_stale_running()

        (event,) = [e for e in read_log(problem_dir) if e["kind"] == "RECOVERED_INTERRUPTED"]
        self.assertEqual(event["execution_id"], "exec-res")
        self.assertTrue(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-res3")
        self.assertTrue(model["attempts"][0]["verifier_called"])


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
        result = run_attempt(solved_dir, "p-ok", "Healthy theorem.", accepted=True)
        # A healthy V1 execution: the log already holds the full event pair,
        # so neither recovery step has anything to complete.
        append_log(
            solved_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-ok", "problem_id": "p-ok",
             "attempt_id": result.attempt_id, "ts": "t1"},
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-ok", "problem_id": "p-ok",
             "attempt_id": result.attempt_id, "started_at": "t1", "finished_at": "t2",
             "outcome_stage": "PASS", "verifier_called": True},
        )
        open_dir = self.builder.add_problem("p-open", "Fresh theorem.")
        solved_log_before = read_log(solved_dir)

        with TestClient(create_app(self.builder.root)) as client:
            solved = client.get("/api/problems/p-ok").json()
            fresh = client.get("/api/problems/p-open").json()

        self.assertEqual(solved["status"], "SOLVED")
        self.assertEqual(fresh["status"], "OPEN")
        self.assertEqual(read_log(solved_dir), solved_log_before)
        self.assertEqual(read_log(open_dir), [])


if __name__ == "__main__":
    unittest.main()
