import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
EXPERIMENT = REPOSITORY / "experiments" / "n114_obligation_local_verifier"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class N114ExperimentArtifactTests(unittest.TestCase):
    def test_frozen_packet_ablation_matches_every_expected_verdict(self) -> None:
        aggregate = read_json(EXPERIMENT / "aggregate.json")
        outcomes = {
            item["packet_id"]: (item["new_verdict"], item["expected_verdict"])
            for item in aggregate["packet_results"]
        }

        self.assertEqual(
            outcomes,
            {
                "P1": ("ACCEPT", "ACCEPT"),
                "P2": ("ACCEPT", "ACCEPT"),
                "N1": ("REJECT", "REJECT"),
                "N2": ("REJECT", "REJECT"),
            },
        )
        self.assertEqual(aggregate["false_positive_count"], 0)
        self.assertEqual(aggregate["false_negative_count"], 0)

    def test_real_verifier_threads_are_fresh_and_blind(self) -> None:
        aggregate = read_json(EXPERIMENT / "aggregate.json")
        invocations = aggregate["packet_results"] + aggregate["e2e_result"]["invocations"]
        thread_ids = [item["thread_id"] for item in invocations]

        self.assertTrue(all(thread_ids))
        self.assertEqual(len(thread_ids), len(set(thread_ids)))
        self.assertTrue(all(item.get("blind_boundary_pass", item.get("boundary_pass")) for item in invocations))

    def test_frozen_scaffold_regression_crosses_the_existing_truth_gate(self) -> None:
        aggregate = read_json(EXPERIMENT / "aggregate.json")
        e2e = aggregate["e2e_result"]

        self.assertEqual(e2e["status"], "SOLVED")
        self.assertEqual(e2e["advance_node_ids"], ["divisible_by_2", "divisible_by_3", "target"])
        self.assertEqual(e2e["attempt_verdicts"], ["PASS", "PASS", "PASS"])
        self.assertEqual(e2e["facts_admitted"], 3)
        self.assertEqual(e2e["supporting_closure_size"], 3)
        self.assertEqual(e2e["worker_calls"], 3)
        self.assertEqual(e2e["verifier_calls"], 3)
        self.assertEqual(e2e["architect_calls"], 0)
        self.assertFalse(e2e["automatic_retry"])
        self.assertEqual(aggregate["verdict"], "OBLIGATION_LOCAL_VERIFIER_VALIDATED")

    def test_pre_review_harness_failure_is_preserved_not_counted_as_retry(self) -> None:
        results = read_json(EXPERIMENT / "results.json")
        pre_review_results = read_json(EXPERIMENT / "pre_review_results.json")
        preflight = read_json(EXPERIMENT / "pre_review_e2e_run" / "result.json")

        self.assertFalse(results["resumed_after_pre_verifier_harness_error"])
        self.assertTrue(pre_review_results["resumed_after_pre_verifier_harness_error"])
        self.assertEqual(preflight["status"], "ERROR")
        self.assertEqual(preflight["verifier_calls"], 0)
        self.assertEqual(preflight["facts_admitted"], 0)


if __name__ == "__main__":
    unittest.main()
