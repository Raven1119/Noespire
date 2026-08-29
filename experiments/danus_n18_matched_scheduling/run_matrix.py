"""Resume the frozen 18-run counterbalanced schedule in manifest order."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
ARM_DIRECTORIES = {
    "A": "arm_a_parallel",
    "B": "arm_b_single",
    "C": "arm_c_sequential",
}


def main() -> None:
    manifest = json.loads(
        (ROOT / "protocol/runtime_manifest.json").read_text(encoding="utf-8")
    )
    for item in manifest["run_order"]:
        problem_id, arm = item["problem_id"], item["arm"]
        arm_root = ROOT / ARM_DIRECTORIES[arm]
        if any((path / "result.json").is_file() for path in arm_root.glob(f"{problem_id}_*")):
            continue
        subprocess.run(
            [sys.executable, str(ROOT / "run_once.py"), arm, problem_id],
            check=True,
        )


if __name__ == "__main__":
    main()
