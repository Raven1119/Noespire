from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest

from experiments.danus_n18_matched_scheduling import run_once as base
from experiments.danus_n19b_matched_scheduling import run_once
from experiments.danus_n19b_matched_scheduling.run_matrix import (
    assert_completed_prefix,
    cell_complete,
)


class RuntimeAdapterTests(unittest.TestCase):
    def test_adapter_selects_n19b_root_and_n19a_loopback(self) -> None:
        previous = (
            base.EXPERIMENT_ROOT,
            base.runtime_overrides,
            base.allocate_loopback_port,
            base.wait_for_verifier,
        )
        try:
            run_once.configure_base_runner()
            self.assertEqual(base.EXPERIMENT_ROOT, run_once.EXPERIMENT_ROOT)
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                values = run_once.runtime_overrides(root / "wrapper", root / "log", 12345, root / "verify")
            self.assertEqual(values["VERIFY_HOST"], "127.19.0.1")
            self.assertEqual(values["DANUS_VERIFY_URL"], "http://127.19.0.1:12345/verify")
            self.assertEqual(values["N19A_ALLOWED_LOOPBACK_PORT"], "12345")
            self.assertIn("N19A_BLIND_WRAPPER_LOG", values)
        finally:
            (
                base.EXPERIMENT_ROOT,
                base.runtime_overrides,
                base.allocate_loopback_port,
                base.wait_for_verifier,
            ) = previous

    def test_parallel_first_success_and_redundancy_are_derived_from_events(self) -> None:
        events = [
            {"verdict": "correct", "fact_id": "f3", "claim": "Target theorem.", "author": "high3", "timestamp_utc": "2026-01-01T00:00:03Z"},
            {"verdict": "incorrect", "claim": "Target theorem.", "author": "high", "timestamp_utc": "2026-01-01T00:00:01Z"},
            {"verdict": "correct", "claim": "Target theorem.", "author": "high", "timestamp_utc": "2026-01-01T00:00:01Z"},
            {"verdict": "correct", "fact_id": "f2", "claim": "Target theorem.", "author": "high2", "timestamp_utc": "2026-01-01T00:00:02Z"},
        ]
        observed = run_once.scheduling_metrics(
            events,
            "Target theorem.",
            ["high", "high2", "high3"],
        )
        self.assertEqual(observed["first_success_index"], 2)
        self.assertEqual(observed["successful_worker_count"], 2)
        self.assertEqual(observed["redundant_verified_targets"], 1)

    def test_resume_audits_pending_result_before_skipping_cell(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arm_root = Path(directory)
            result = arm_root / "p1_stamp/result.json"
            result.parent.mkdir()
            result.write_text(json.dumps({"blind_integrity": "PENDING_POST_RUN_AUDIT"}), encoding="utf-8")

            def finish() -> None:
                pending = json.loads(result.read_text(encoding="utf-8"))
                self.assertNotIn("redundant_verified_targets", pending)
                result.write_text(
                    json.dumps(
                        {
                            "blind_integrity": "BLIND_INTEGRITY_PASS",
                            "first_success_index": 1,
                            "successful_worker_count": 1,
                            "redundant_verified_targets": 0,
                        }
                    ),
                    encoding="utf-8",
                )

            self.assertTrue(cell_complete(arm_root, "p1", finish))
            completed = json.loads(result.read_text(encoding="utf-8"))
            self.assertEqual(completed["redundant_verified_targets"], 0)

    def test_resume_rejects_failed_blind_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            arm_root = Path(directory)
            result = arm_root / "p1_stamp/result.json"
            result.parent.mkdir()
            result.write_text(json.dumps({"blind_integrity": "BLIND_INTEGRITY_FAIL"}), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                cell_complete(arm_root, "p1", lambda: None)

    def test_existing_results_must_be_frozen_order_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = root / "arm_b_single/p2_stamp/result.json"
            result.parent.mkdir(parents=True)
            result.write_text(
                json.dumps(
                    {
                        "started_at_utc": "2026-01-01T00:00:00Z",
                        "problem_id": "p2",
                        "arm": "B",
                    }
                ),
                encoding="utf-8",
            )
            manifest = {
                "run_order": [
                    {"problem_id": "p1", "arm": "A"},
                    {"problem_id": "p2", "arm": "B"},
                ]
            }
            with self.assertRaisesRegex(RuntimeError, "prefix"):
                assert_completed_prefix(root, manifest)


if __name__ == "__main__":
    unittest.main()
