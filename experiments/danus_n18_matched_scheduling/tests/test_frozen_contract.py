from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.danus_n18_matched_scheduling import run_once


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FrozenContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(
            (ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8")
        )

    def test_six_problem_and_reference_hashes_are_frozen(self) -> None:
        self.assertEqual(len(self.manifest["problems"]), 6)
        for problem in self.manifest["problems"]:
            self.assertEqual(
                digest(ROOT / "problems" / problem["problem_file"]),
                problem["problem_sha256"],
            )
            reference = ROOT / "reference" / problem["reference_file"]
            if reference.exists():
                self.assertEqual(digest(reference), problem["reference_sha256"])

    def test_worker_contract_is_identical_for_every_arm(self) -> None:
        contract = self.manifest["worker_contract"]
        self.assertEqual(digest(ROOT / "protocol/worker_assignment.txt"), contract["assignment_sha256"])
        self.assertEqual(contract["model"], run_once.MODEL)
        self.assertEqual(contract["role"], "high")
        self.assertEqual(contract["reasoning_effort"], run_once.EFFORT)
        self.assertEqual(contract["configured_roles"], run_once.ROLES)
        self.assertEqual(contract["maximum_worker_slots"], 7)
        self.assertEqual(
            {arm["configured_roles"] for arm in self.manifest["arms"].values()},
            {"high:7"},
        )

    def test_blind_wrapper_is_the_frozen_n16_wrapper(self) -> None:
        wrapper = run_once.NOESPIRE_ROOT / self.manifest["blind_policy"]["wrapper_path"]
        self.assertEqual(digest(wrapper), self.manifest["blind_policy"]["wrapper_sha256"])

    def test_runner_resolves_blind_controls_from_manifest(self) -> None:
        wrapper, evidence = run_once.control_paths(self.manifest)

        self.assertEqual(
            wrapper,
            run_once.NOESPIRE_ROOT / self.manifest["blind_policy"]["wrapper_path"],
        )
        self.assertEqual(
            evidence,
            run_once.NOESPIRE_ROOT / self.manifest["blind_policy"]["capability_evidence"],
        )

    def test_counterbalanced_order_contains_every_pair_once(self) -> None:
        expected_orders = [
            ["A", "B", "C"],
            ["B", "C", "A"],
            ["C", "A", "B"],
            ["A", "C", "B"],
            ["B", "A", "C"],
            ["C", "B", "A"],
        ]
        by_problem: dict[str, list[str]] = {}
        for item in self.manifest["run_order"]:
            by_problem.setdefault(item["problem_id"], []).append(item["arm"])
        self.assertEqual(
            [by_problem[problem["problem_id"]] for problem in self.manifest["problems"]],
            expected_orders,
        )
        self.assertEqual(len(self.manifest["run_order"]), 18)
        self.assertEqual(
            len({(item["problem_id"], item["arm"]) for item in self.manifest["run_order"]}),
            18,
        )

    def test_completion_collector_uses_the_actual_high_seven_roster(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            workers = tuple("high" if i == 1 else f"high{i}" for i in range(1, 8))
            for worker in workers:
                worker_dir = project / "workers" / worker
                worker_dir.mkdir(parents=True)
                (worker_dir / ".status.json").write_text(
                    json.dumps({"state": "max_rounds", "round": 1, "last_rc": 0}),
                    encoding="utf-8",
                )

            statuses = run_once.read_worker_statuses(project, workers)

            self.assertEqual(set(statuses), set(workers))


if __name__ == "__main__":
    unittest.main()
