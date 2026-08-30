from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from experiments.danus_n19b_matched_scheduling.analysis.aggregate import (
    validate_scheduling_metrics,
    verdict,
)


def arm(solved: int, workers: int, tokens: int, first_indices=None) -> dict:
    runs = []
    for index in range(6):
        success = index < solved
        item = {"problem_id": f"p{index}", "solved": success, "workers_launched": workers // 6}
        if first_indices is not None:
            item["first_worker_result"] = "PASS" if first_indices[index] == 1 else "FAIL"
            item["first_success_index"] = first_indices[index]
        runs.append(item)
    return {
        "solved": solved,
        "workers_launched": workers,
        "total_tokens": tokens,
        "mean_time_to_first_verified_target_seconds": 100.0,
        "runs": runs,
    }


class VerdictTests(unittest.TestCase):
    def test_scheduling_metrics_are_revalidated_from_raw_events(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            project = run / "project_artifacts"
            (project / "global_memory").mkdir(parents=True)
            (project / "project.json").write_text(
                json.dumps({"workers": ["high", "high2"]}), encoding="utf-8"
            )
            (project / "global_memory/verification.jsonl").write_text(
                json.dumps(
                    {
                        "verdict": "correct",
                        "fact_id": "f1",
                        "claim": "Target.",
                        "author": "high2",
                        "timestamp_utc": "2026-01-01T00:00:01Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run / "input.md").write_text("Target.", encoding="utf-8")
            result = {
                "run_id": "p1_stamp",
                "first_success_index": 2,
                "successful_worker_count": 1,
                "redundant_verified_targets": 99,
            }
            with self.assertRaisesRegex(ValueError, "redundant_verified_targets"):
                validate_scheduling_metrics(run, result)

    def test_all_first_workers_support_single_worker_first(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm(6, 6, 600),
            "C": arm(6, 6, 600, [1] * 6),
        }
        self.assertEqual(verdict(evidence), "SINGLE_WORKER_FIRST_SUPPORTED")

    def test_genuine_c_recovery_supports_sequential_recovery(self) -> None:
        indices = [1, 1, 1, 1, 1, 2]
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm(6, 6, 600),
            "C": arm(6, 7, 700, indices),
        }
        self.assertEqual(verdict(evidence), "SEQUENTIAL_RECOVERY_SUPPORTED")

    def test_parallel_only_win_supports_parallel_redundancy(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm(5, 6, 600),
            "C": arm(5, 11, 1100, [1, 1, 1, 1, 1, None]),
        }
        self.assertEqual(verdict(evidence), "PARALLEL_REDUNDANCY_SUPPORTED")

    def test_matched_conditional_escalation_supports_demand_driven_execution(self) -> None:
        arm_c = arm(5, 12, 1200, [1, 1, 1, 1, 1, None])
        evidence = {
            "integrity_pass": True,
            "A": arm(5, 42, 4200),
            "B": arm(4, 6, 600),
            "C": arm_c,
        }
        self.assertEqual(verdict(evidence), "DEMAND_DRIVEN_EXECUTION_SUPPORTED")

    def test_integrity_failure_is_inconclusive(self) -> None:
        evidence = {
            "integrity_pass": False,
            "A": arm(6, 42, 4200),
            "B": arm(6, 6, 600),
            "C": arm(6, 6, 600, [1] * 6),
        }
        self.assertEqual(verdict(evidence), "INCONCLUSIVE")

    def test_zero_solve_tie_uses_lower_compute_dominance(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(0, 42, 4200),
            "B": arm(0, 6, 600),
            "C": arm(0, 42, 4200, [None] * 6),
        }
        self.assertEqual(verdict(evidence), "SINGLE_WORKER_FIRST_SUPPORTED")

    def test_b_retention_beats_partial_a_advantage_over_c(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(4, 42, 4200),
            "B": arm(5, 6, 600),
            "C": arm(3, 42, 4200, [None] * 6),
        }
        self.assertEqual(verdict(evidence), "SINGLE_WORKER_FIRST_SUPPORTED")

    def test_unmatched_valid_outcome_uses_dominant_sequential_arm(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(3, 42, 4200),
            "B": arm(2, 6, 600),
            "C": arm(4, 18, 1800, [1, 1, 1, 1, None, None]),
        }
        self.assertEqual(verdict(evidence), "DEMAND_DRIVEN_EXECUTION_SUPPORTED")


if __name__ == "__main__":
    unittest.main()
