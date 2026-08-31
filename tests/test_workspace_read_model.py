from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from application.workspace_read_model import build_problem_list, build_read_model

from research.obligation import ObligationStatus

from application_fixtures import (
    WorkspaceBuilder,
    add_fact,
    add_open_obligation,
    append_log,
    candidate_artifact,
    registry_for,
    run_attempt,
    run_error_attempt,
    write_residual_running_attempt,
)


class NeverAttemptedProblemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_never_attempted_problem_reads_as_open_with_no_evidence(self) -> None:
        self.builder.add_problem("p-new", "An unattempted theorem.")

        model = build_read_model(self.builder.root, "p-new")

        self.assertEqual(model["problem_id"], "p-new")
        self.assertEqual(model["statement"], "An unattempted theorem.")
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["display_status"], "OPEN")
        self.assertIsNone(model["derived_from"])
        self.assertFalse(model["archived"])
        self.assertIsNone(model["obligation"])
        self.assertEqual(model["attempts"], [])
        self.assertIsNone(model["target_fact"])
        self.assertEqual(model["supporting_closure"], [])
        self.assertIsNone(model["running_phase_hint"])

    def test_lineage_is_carried_from_the_index(self) -> None:
        self.builder.add_problem("p-parent", "Original theorem.")
        self.builder.add_problem("p-child", "Revised theorem.", derived_from="p-parent")

        model = build_read_model(self.builder.root, "p-child")

        self.assertEqual(model["derived_from"], "p-parent")

    def test_unknown_problem_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            build_read_model(self.builder.root, "p-missing")


class SolvedProblemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_solved_problem_exposes_target_fact_and_closure_in_topo_order(self) -> None:
        problem_dir = self.builder.add_problem("p-solved", "Target theorem T.")
        lemma_one = add_fact(problem_dir, "p-solved", "Lemma one.", "Proof of lemma one.")
        lemma_two = add_fact(
            problem_dir, "p-solved", "Lemma two.", "Proof of lemma two.", (lemma_one.fact_id,)
        )
        result = run_attempt(
            problem_dir, "p-solved", "Target theorem T.", accepted=True,
            premise_fact_ids=(lemma_two.fact_id,),
        )

        model = build_read_model(self.builder.root, "p-solved")

        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["display_status"], "SOLVED")
        self.assertEqual(model["obligation"]["status"], "DISCHARGED")
        self.assertEqual(model["obligation"]["resolved_by_fact_id"], result.target_fact_id)
        self.assertEqual(model["target_fact"]["fact_id"], result.target_fact_id)
        self.assertEqual(model["target_fact"]["statement"], "Target theorem T.")
        self.assertEqual(model["target_fact"]["predecessors"], [lemma_two.fact_id])
        self.assertEqual(
            [fact["fact_id"] for fact in model["supporting_closure"]],
            [lemma_one.fact_id, lemma_two.fact_id, result.target_fact_id],
        )
        self.assertEqual(model["supporting_closure"][0]["statement"], "Lemma one.")
        self.assertEqual(model["attempts"][0]["verdict"], "PASS")


class RunningProblemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _running_problem(self, candidate) -> None:
        problem_dir = self.builder.add_problem("p-live", "Live theorem.")
        add_open_obligation(problem_dir, "p-live", "Live theorem.")
        registry_for(problem_dir).transition("root:p-live", ObligationStatus.RUNNING)
        write_residual_running_attempt(problem_dir, "p-live", candidate=candidate)

    def test_running_before_candidate_hints_generating(self) -> None:
        self._running_problem(candidate=None)

        model = build_read_model(self.builder.root, "p-live")

        self.assertEqual(model["status"], "RUNNING")
        self.assertEqual(model["display_status"], "RUNNING")
        self.assertEqual(model["running_phase_hint"], "generating")
        self.assertEqual(model["attempts"][0]["verdict"], "RUNNING")
        self.assertIsNone(model["attempts"][0]["failure_class"])

    def test_running_with_candidate_hints_checking(self) -> None:
        self._running_problem(candidate=candidate_artifact("Live theorem."))

        model = build_read_model(self.builder.root, "p-live")

        self.assertEqual(model["status"], "RUNNING")
        self.assertEqual(model["running_phase_hint"], "checking")


class ErrorAttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_latest_error_attempt_displays_error_but_obligation_stays_open(self) -> None:
        problem_dir = self.builder.add_problem("p-err", "Fragile theorem.")
        run_error_attempt(problem_dir, "p-err", "Fragile theorem.")

        model = build_read_model(self.builder.root, "p-err")

        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["display_status"], "ERROR")
        self.assertEqual(model["obligation"]["status"], "OPEN")
        attempt = model["attempts"][0]
        self.assertEqual(attempt["verdict"], "ERROR")
        self.assertEqual(attempt["failure_class"], "runtime")
        self.assertEqual(attempt["error"], "scripted worker error")

    def test_earlier_error_attempt_does_not_change_display(self) -> None:
        problem_dir = self.builder.add_problem("p-err", "Fragile theorem.")
        run_error_attempt(problem_dir, "p-err", "Fragile theorem.")
        run_attempt(problem_dir, "p-err", "Fragile theorem.", accepted=False)

        model = build_read_model(self.builder.root, "p-err")

        self.assertEqual(model["display_status"], "OPEN")


class FailureClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_fail_without_log_event_is_honest_unknown(self) -> None:
        problem_dir = self.builder.add_problem("p-fail", "Hard theorem.")
        run_attempt(problem_dir, "p-fail", "Hard theorem.", accepted=False)

        attempt = build_read_model(self.builder.root, "p-fail")["attempts"][0]

        self.assertEqual(attempt["verdict"], "FAIL")
        self.assertIsNone(attempt["failure_class"])
        self.assertIsNone(attempt["started_at"])
        self.assertIsNone(attempt["finished_at"])

    def test_fail_with_verifier_reject_event_is_rejection(self) -> None:
        problem_dir = self.builder.add_problem("p-fail", "Hard theorem.")
        result = run_attempt(problem_dir, "p-fail", "Hard theorem.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-1", "problem_id": "p-fail", "ts": "t1"},
            {
                "kind": "ATTEMPT_FINISHED",
                "execution_id": "exec-1",
                "problem_id": "p-fail",
                "attempt_id": result.attempt_id,
                "started_at": "2026-08-31T10:15:00+08:00",
                "finished_at": "2026-08-31T10:18:00+08:00",
                "outcome_stage": "FRESH_VERIFIER_REJECT",
                "verifier_called": True,
            },
        )

        attempt = build_read_model(self.builder.root, "p-fail")["attempts"][0]

        self.assertEqual(attempt["failure_class"], "rejection")
        self.assertEqual(attempt["started_at"], "2026-08-31T10:15:00+08:00")
        self.assertEqual(attempt["finished_at"], "2026-08-31T10:18:00+08:00")

    def test_fail_with_contract_guard_event_is_contract(self) -> None:
        problem_dir = self.builder.add_problem("p-fail", "Hard theorem.")
        result = run_attempt(
            problem_dir, "p-fail", "Hard theorem.",
            accepted=True, candidate_statement="A different statement.",
        )
        append_log(
            problem_dir,
            {
                "kind": "ATTEMPT_FINISHED",
                "execution_id": "exec-1",
                "problem_id": "p-fail",
                "attempt_id": result.attempt_id,
                "started_at": "2026-08-31T10:15:00+08:00",
                "finished_at": "2026-08-31T10:16:00+08:00",
                "outcome_stage": "CONTRACT_GUARD",
                "verifier_called": False,
            },
        )

        attempt = build_read_model(self.builder.root, "p-fail")["attempts"][0]

        self.assertEqual(attempt["verdict"], "FAIL")
        self.assertEqual(attempt["failure_class"], "contract")

    def test_attempts_are_oldest_to_newest(self) -> None:
        problem_dir = self.builder.add_problem("p-fail", "Hard theorem.")
        first = run_attempt(problem_dir, "p-fail", "Hard theorem.", accepted=False)
        second = run_attempt(problem_dir, "p-fail", "Hard theorem.", accepted=False)

        model = build_read_model(self.builder.root, "p-fail")

        self.assertEqual(
            [attempt["attempt_id"] for attempt in model["attempts"]],
            [first.attempt_id, second.attempt_id],
        )
        self.assertEqual(
            [attempt["candidate"]["proof"] for attempt in model["attempts"]],
            ["A candidate proof.", "A candidate proof."],
        )
        self.assertEqual(model["attempts"][0]["verifier"]["accepted"], False)


class RecoveryProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_recovered_interrupted_residual_attempt_reads_as_interrupted(self) -> None:
        problem_dir = self.builder.add_problem("p-crash", "Crash theorem.")
        add_open_obligation(problem_dir, "p-crash", "Crash theorem.")
        attempt_id = write_residual_running_attempt(problem_dir, "p-crash")
        append_log(
            problem_dir,
            {"kind": "VERIFIER_INVOKED", "execution_id": "exec-9", "problem_id": "p-crash", "ts": "t1"},
            {"kind": "RECOVERED_INTERRUPTED", "execution_id": "exec-9", "problem_id": "p-crash",
             "ts": "t2", "verifier_called": True},
        )

        model = build_read_model(self.builder.root, "p-crash")

        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["display_status"], "OPEN")
        attempt = model["attempts"][0]
        self.assertEqual(attempt["attempt_id"], attempt_id)
        self.assertEqual(attempt["verdict"], "RUNNING")
        self.assertEqual(attempt["failure_class"], "interrupted")
        self.assertTrue(attempt["verifier_called"])

    def test_residual_running_obligation_with_recovery_event_is_not_live(self) -> None:
        problem_dir = self.builder.add_problem("p-crash", "Crash theorem.")
        add_open_obligation(problem_dir, "p-crash", "Crash theorem.")
        registry_for(problem_dir).transition("root:p-crash", ObligationStatus.RUNNING)
        write_residual_running_attempt(problem_dir, "p-crash")
        append_log(
            problem_dir,
            {"kind": "RECOVERED_INTERRUPTED", "execution_id": "exec-9", "problem_id": "p-crash",
             "ts": "t2", "verifier_called": False},
        )

        model = build_read_model(self.builder.root, "p-crash")

        self.assertEqual(model["status"], "OPEN")
        self.assertIsNone(model["running_phase_hint"])
        attempt = model["attempts"][0]
        self.assertEqual(attempt["failure_class"], "interrupted")
        self.assertFalse(attempt["verifier_called"])

    def test_recovered_discharged_reads_as_ordinary_solved(self) -> None:
        problem_dir = self.builder.add_problem("p-crash", "Crash theorem.")
        run_attempt(problem_dir, "p-crash", "Crash theorem.", accepted=True)
        append_log(
            problem_dir,
            {"kind": "RECOVERED_DISCHARGED", "execution_id": "exec-9", "problem_id": "p-crash", "ts": "t2"},
        )

        model = build_read_model(self.builder.root, "p-crash")

        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["attempts"][0]["verdict"], "PASS")
        self.assertIsNone(model["attempts"][0]["failure_class"])
        self.assertIsNotNone(model["target_fact"])


class ProblemListTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def test_list_payload_summarizes_each_problem(self) -> None:
        solved_dir = self.builder.add_problem("p-solved", "Solved theorem.")
        run_attempt(solved_dir, "p-solved", "Solved theorem.", accepted=True)
        open_dir = self.builder.add_problem("p-open", "Open theorem.", derived_from="p-solved")
        run_attempt(open_dir, "p-open", "Open theorem.", accepted=False)
        run_attempt(open_dir, "p-open", "Open theorem.", accepted=False)
        self.builder.add_problem("p-fresh", "Untouched theorem.", archived=True)

        listed = build_problem_list(self.builder.root)

        by_id = {item["problem_id"]: item for item in listed}
        self.assertEqual(set(by_id), {"p-solved", "p-open", "p-fresh"})
        solved = by_id["p-solved"]
        self.assertEqual(solved["statement"], "Solved theorem.")
        self.assertEqual(solved["status"], "SOLVED")
        self.assertEqual(solved["display_status"], "SOLVED")
        self.assertEqual(solved["attempt_count"], 1)
        self.assertIsNone(solved["derived_from"])
        self.assertFalse(solved["archived"])
        datetime.fromisoformat(solved["last_activity"])
        open_item = by_id["p-open"]
        self.assertEqual(open_item["status"], "OPEN")
        self.assertEqual(open_item["attempt_count"], 2)
        self.assertEqual(open_item["derived_from"], "p-solved")
        fresh = by_id["p-fresh"]
        self.assertEqual(fresh["attempt_count"], 0)
        self.assertIsNone(fresh["last_activity"])
        self.assertTrue(fresh["archived"])

    def test_list_is_ordered_by_last_activity_descending(self) -> None:
        first_dir = self.builder.add_problem("p-earlier", "Earlier theorem.")
        run_attempt(first_dir, "p-earlier", "Earlier theorem.", accepted=False)
        second_dir = self.builder.add_problem("p-later", "Later theorem.")
        run_attempt(second_dir, "p-later", "Later theorem.", accepted=False)

        listed = build_problem_list(self.builder.root)

        self.assertEqual([item["problem_id"] for item in listed], ["p-later", "p-earlier"])


if __name__ == "__main__":
    unittest.main()
