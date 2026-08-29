from __future__ import annotations

import json
from pathlib import Path
import unittest

from experiments.danus_n17_worker_scheduling.scheduler import run_schedule
from experiments.danus_n17_worker_scheduling import run_once
from experiments.danus_n16_blind import run_once as n16_run_once


class SchedulingPolicyTests(unittest.TestCase):
    def test_frozen_runtime_uses_the_n16_direct_worker_contract(self) -> None:
        self.assertEqual(
            run_once.DIRECT_TASK,
            n16_run_once.WORKER_TASKS["high"] + n16_run_once.TASK_SUFFIX,
        )
        self.assertEqual(run_once.ARM_CONFIG["B"]["roles"], "high:1")
        self.assertEqual(run_once.ARM_CONFIG["C"]["roles"], "high:7")

    def test_problem_bytes_match_the_frozen_manifest(self) -> None:
        manifest = json.loads(
            (run_once.EXPERIMENT_ROOT / "protocol/runtime_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        for problem in manifest["problems"]:
            path = run_once.NOESPIRE_ROOT / Path(problem["path"])
            self.assertEqual(run_once.sha256(path), problem["sha256"])

    def test_verifier_results_are_pinned_to_the_wrapper_write_scope(self) -> None:
        overrides = run_once.runtime_overrides(
            Path("/wrapper"), Path("/wrapper.log"), 4321, Path("/runtime/verify-runs")
        )

        self.assertEqual(overrides["VERIFIER_RESULTS_DIR"], "/runtime/verify-runs")

    def test_single_worker_never_escalates_after_failure(self) -> None:
        launched: list[int] = []

        outcome = run_schedule("B", lambda index: launched.append(index) or False)

        self.assertEqual(launched, [1])
        self.assertFalse(outcome.solved)
        self.assertEqual(outcome.unused_worker_budget, 0)

    def test_sequential_stops_at_first_success(self) -> None:
        launched: list[int] = []

        outcome = run_schedule(
            "C", lambda index: launched.append(index) or index == 3
        )

        self.assertEqual(launched, [1, 2, 3])
        self.assertTrue(outcome.solved)
        self.assertEqual(outcome.worker_index_of_first_success, 3)
        self.assertTrue(outcome.stopped_after_success)
        self.assertEqual(outcome.unused_worker_budget, 4)

    def test_sequential_uses_full_budget_only_when_every_attempt_fails(self) -> None:
        launched: list[int] = []

        outcome = run_schedule("C", lambda index: launched.append(index) or False)

        self.assertEqual(launched, list(range(1, 8)))
        self.assertFalse(outcome.solved)
        self.assertIsNone(outcome.worker_index_of_first_success)
        self.assertFalse(outcome.stopped_after_success)
        self.assertEqual(outcome.unused_worker_budget, 0)


if __name__ == "__main__":
    unittest.main()
