from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
NOESPIRE = ROOT.parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(
            (ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8")
        )

    def test_six_fresh_problem_and_private_reference_hashes_are_frozen(self) -> None:
        self.assertEqual(len(self.manifest["problems"]), 6)
        historical = {
            digest(path)
            for experiment in (
                "danus_baseline_a",
                "danus_n15_diagnostic",
                "danus_n16_blind",
                "danus_n18_matched_scheduling",
            )
            for path in (NOESPIRE / "experiments" / experiment / "problems").glob("*.md")
        }
        for problem in self.manifest["problems"]:
            observed = digest(ROOT / "problems" / problem["problem_file"])
            self.assertEqual(observed, problem["problem_sha256"])
            self.assertNotIn(observed, historical)
            self.assertEqual(
                Path(problem["private_source"]),
                Path(self.manifest["private_reference_store"]) / problem["reference_file"],
            )
            reference = ROOT / "reference" / problem["reference_file"]
            if reference.exists():
                self.assertEqual(digest(reference), problem["reference_sha256"])

    def test_worker_contract_is_strictly_matched(self) -> None:
        contract = self.manifest["worker_contract"]
        self.assertEqual(digest(ROOT / "protocol/worker_assignment.txt"), contract["assignment_sha256"])
        self.assertEqual(
            (contract["model"], contract["role"], contract["reasoning_effort"]),
            ("gpt-5.6-sol", "high", "high"),
        )
        self.assertEqual({arm["configured_roles"] for arm in self.manifest["arms"].values()}, {"high:7"})

    def test_frozen_n19a_boundary_is_reused(self) -> None:
        policy = self.manifest["blind_policy"]
        self.assertEqual(digest(NOESPIRE / policy["wrapper_path"]), policy["wrapper_sha256"])
        self.assertEqual(
            digest(NOESPIRE / policy["capability_evidence"]),
            policy["capability_evidence_sha256"],
        )
        self.assertEqual(policy["allowed_loopback_host"], "127.19.0.1")

    def test_counterbalanced_order_contains_every_pair_once(self) -> None:
        expected = [list(order) for order in ("ABC", "BCA", "CAB", "ACB", "BAC", "CBA")]
        by_problem: dict[str, list[str]] = {}
        for item in self.manifest["run_order"]:
            by_problem.setdefault(item["problem_id"], []).append(item["arm"])
        self.assertEqual(
            [by_problem[item["problem_id"]] for item in self.manifest["problems"]],
            expected,
        )
        self.assertEqual(len({(item["problem_id"], item["arm"]) for item in self.manifest["run_order"]}), 18)


if __name__ == "__main__":
    unittest.main()
