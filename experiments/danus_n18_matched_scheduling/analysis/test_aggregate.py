from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
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
    def test_raw_metrics_are_rederived_from_preserved_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "input.md").write_text("Target theorem.\n", encoding="utf-8")
            worker = run / "project_artifacts" / "workers" / "high"
            (worker / "logs").mkdir(parents=True)
            (worker / ".status.json").write_text(
                json.dumps({"state": "max_rounds", "round": 1}) + "\n",
                encoding="utf-8",
            )
            (worker / "logs" / "round_1.log").write_text(
                "tokens used\n100\n", encoding="utf-8"
            )
            facts = run / "project_artifacts" / "fact_graph" / "facts"
            facts.mkdir(parents=True)
            (facts / "f1.md").write_text(
                "---\nfact_id: f1\npredecessors: []\n---\n", encoding="utf-8"
            )
            (run / "project_artifacts" / "TARGET.md").write_text(
                "# target\n\nf1\n", encoding="utf-8"
            )
            memory = run / "project_artifacts" / "global_memory"
            memory.mkdir()
            (memory / "verification.jsonl").write_text(
                json.dumps(
                    {
                        "verdict": "correct",
                        "fact_id": "f1",
                        "author": "high",
                        "claim": "Target theorem.",
                        "timestamp_utc": "2026-01-01T00:00:10Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            verifier = run / "verifier_outputs" / "v1"
            verifier.mkdir(parents=True)
            (verifier / "log.md").write_text("tokens used\n50\n", encoding="utf-8")

            metrics = aggregate.raw_metrics(run, "2026-01-01T00:00:00Z")

        self.assertEqual(metrics["workers_launched"], 1)
        self.assertEqual(metrics["worker_attempts"], 1)
        self.assertEqual(metrics["verifier_calls"], 1)
        self.assertEqual(metrics["verifier_accepts"], 1)
        self.assertEqual(metrics["verified_fact_count"], 1)
        self.assertEqual(metrics["supporting_closure"], ["f1"])
        self.assertEqual(metrics["worker_tokens"], 100)
        self.assertEqual(metrics["verifier_tokens"], 50)
        self.assertEqual(metrics["total_tokens"], 150)
        self.assertEqual(metrics["time_to_first_verified_target_seconds"], 10.0)
        self.assertTrue(metrics["solved"])

    def test_raw_metrics_accept_unsolved_run_without_target_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "input.md").write_text("Unsolved theorem.\n", encoding="utf-8")
            worker = run / "project_artifacts" / "workers" / "high"
            worker.mkdir(parents=True)
            (worker / ".status.json").write_text(
                json.dumps({"state": "max_rounds", "round": 1}) + "\n",
                encoding="utf-8",
            )
            logs = worker / "logs"
            logs.mkdir()
            (logs / "round_1.log").write_text("tokens used\n10\n", encoding="utf-8")
            verifier = run / "verifier_outputs" / "v1"
            verifier.mkdir(parents=True)
            (verifier / "log.md").write_text("tokens used\n5\n", encoding="utf-8")

            metrics = aggregate.raw_metrics(run, "2026-01-01T00:00:00Z")

        self.assertFalse(metrics["solved"])
        self.assertEqual(metrics["supporting_closure"], [])
        self.assertEqual(metrics["supporting_closure_size"], 0)
        self.assertIsNone(metrics["selected_target_fact_id"])

    def test_integrity_summary_preserves_failures_for_inconclusive_evidence(self) -> None:
        results = {
            "A": [
                {"run_id": "a1", "blind_integrity": "BLIND_INTEGRITY_PASS"},
                {"run_id": "a2", "blind_integrity": "BLIND_INTEGRITY_FAIL"},
            ],
            "B": [{"run_id": "b1", "blind_integrity": "BLIND_INTEGRITY_PASS"}],
            "C": [{"run_id": "c1", "blind_integrity": "BLIND_INTEGRITY_PASS"}],
        }

        self.assertEqual(
            aggregate.integrity_summary(results),
            {
                "integrity_pass": False,
                "pass_count": 3,
                "fail_count": 1,
                "failed_run_ids": ["a2"],
            },
        )

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

    def test_recovery_event_does_not_depend_on_the_independent_b_result(self) -> None:
        arm_b = arm(6, 6, 600)
        arm_c = arm(6, 7, 700, first_indices=[1, 1, 1, 1, 1, 2])
        evidence = {
            "integrity_pass": True,
            "A": arm(6, 42, 4200),
            "B": arm_b,
            "C": arm_c,
        }

        self.assertEqual(aggregate.sequential_recoveries(evidence), ["p6"])

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
