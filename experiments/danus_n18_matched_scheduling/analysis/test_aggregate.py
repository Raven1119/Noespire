from __future__ import annotations

import sys
from pathlib import Path
import unittest


ANALYSIS_DIR = Path(__file__).parent
sys.path.insert(0, str(ANALYSIS_DIR))

import aggregate  # noqa: E402


def arm(solved: int, workers: int, tokens: int, *, first_indices=None) -> dict:
    runs = []
    for index in range(6):
        run_solved = index < solved
        run = {
            "problem_id": f"p{index + 1}",
            "solved": run_solved,
            "workers_launched": workers // 6,
            "total_tokens": tokens // 6,
        }
        if first_indices is not None:
            run["first_worker_result"] = "PASS" if first_indices[index] == 1 else "FAIL"
            run["first_success_index"] = first_indices[index]
        runs.append(run)
    return {
        "valid_runs": 6,
        "solved": solved,
        "solve_rate": solved / 6,
        "workers_launched": workers,
        "total_tokens": tokens,
        "runs": runs,
    }


class VerdictTests(unittest.TestCase):
    def test_single_worker_sufficient_is_the_strictest_all_pass_gate(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm(6, 6, 600),
            "C": arm(6, 6, 600, first_indices=[1] * 6),
        }

        self.assertEqual(
            aggregate.verdict(evidence), "SINGLE_WORKER_SUFFICIENT_ON_SET"
        )

    def test_sequential_recovery_requires_later_success_after_first_failure(self) -> None:
        arm_b = arm(5, 6, 600)
        arm_c = arm(6, 7, 700, first_indices=[1, 1, 1, 1, 1, 2])
        arm_c["runs"][-1]["solved"] = True
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm_b,
            "C": arm_c,
        }

        self.assertEqual(
            aggregate.verdict(evidence), "SEQUENTIAL_RECOVERY_SUPPORTED"
        )

    def test_parallel_redundancy_wins_when_a_solves_a_problem_c_fails(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm(5, 6, 600),
            "C": arm(5, 11, 1100, first_indices=[1, 1, 1, 1, 1, None]),
        }

        self.assertEqual(
            aggregate.verdict(evidence), "PARALLEL_REDUNDANCY_SUPPORTED"
        )

    def test_matched_demand_gate_uses_frozen_fifty_percent_threshold(self) -> None:
        evidence = {
            "integrity_pass": True,
            "A": arm(5, 42, 4200),
            "B": arm(5, 6, 2100),
            "C": arm(5, 10, 2200, first_indices=[1, 1, 1, 1, 1, None]),
        }

        self.assertEqual(
            aggregate.verdict(evidence), "MATCHED_DEMAND_DRIVEN_SUPPORTED"
        )

    def test_integrity_failure_is_inconclusive(self) -> None:
        evidence = {
            "integrity_pass": False,
            "A": arm(6, 42, 4200),
            "B": arm(6, 6, 600),
            "C": arm(6, 6, 600, first_indices=[1] * 6),
        }

        self.assertEqual(aggregate.verdict(evidence), "INCONCLUSIVE")


if __name__ == "__main__":
    unittest.main()
