"""Resume the pre-registered N1.9b matrix in counterbalanced order."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent
ARM_DIRECTORIES = {
    "A": "arm_a_parallel",
    "B": "arm_b_single",
    "C": "arm_c_sequential",
}


def assert_completed_prefix(root: Path, manifest: dict[str, Any]) -> None:
    results = []
    for directory in ARM_DIRECTORIES.values():
        for path in (root / directory).glob("*/result.json"):
            result = json.loads(path.read_text(encoding="utf-8"))
            results.append((result["started_at_utc"], result["problem_id"], result["arm"]))
    observed = [(problem, arm) for _, problem, arm in sorted(results)]
    expected = [
        (item["problem_id"], item["arm"])
        for item in manifest["run_order"]
    ]
    if observed != expected[: len(observed)]:
        raise RuntimeError("existing valid runs are not a prefix of the frozen order")


def cell_complete(
    arm_root: Path, problem_id: str, finish_pending: Callable[[], object]
) -> bool:
    results = sorted(arm_root.glob(f"{problem_id}_*/result.json"))
    if not results:
        return False
    if len(results) != 1:
        raise RuntimeError(f"multiple valid results for {problem_id}: {results}")
    result = json.loads(results[0].read_text(encoding="utf-8"))
    if result["blind_integrity"] == "PENDING_POST_RUN_AUDIT":
        finish_pending()
        result = json.loads(results[0].read_text(encoding="utf-8"))
    if result["blind_integrity"] != "BLIND_INTEGRITY_PASS":
        raise RuntimeError(f"non-passing blind integrity for {results[0].parent.name}")
    return True


def main() -> None:
    if str(ROOT.parents[1]) not in sys.path:
        sys.path.insert(0, str(ROOT.parents[1]))
    from experiments.danus_n19b_matched_scheduling.run_once import finish_pending_run

    manifest = json.loads(
        (ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8")
    )
    for item in manifest["run_order"]:
        assert_completed_prefix(ROOT, manifest)
        problem_id, arm = item["problem_id"], item["arm"]
        arm_root = ROOT / ARM_DIRECTORIES[arm]
        if cell_complete(arm_root, problem_id, finish_pending_run):
            continue
        subprocess.run(
            [
                sys.executable,
                "-m",
                "experiments.danus_n19b_matched_scheduling.run_once",
                arm,
                problem_id,
            ],
            cwd=ROOT.parents[1],
            check=True,
        )


if __name__ == "__main__":
    main()
