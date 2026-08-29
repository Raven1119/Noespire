"""Preserve the sole pre-valid-run collector failure without inspecting proofs."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.danus_n16_blind.run_once import copy_project_artifacts, utc_now  # noqa: E402


RUN_ID = "vieta-jumping-square_20260829T174157Z"
PROJECT = "n18a_vieta_jumping_square_20260829t174157z"
VERIFIER_RUN_IDS = [
    "20260829T174522Z_16fd6a6ce65d",
    "20260829T174532Z_16fd6a6ce65d",
    "20260829T174533Z_16fd6a6ce65d",
    "20260829T174540Z_16fd6a6ce65d",
    "20260829T174556Z_16fd6a6ce65d",
    "20260829T174606Z_16fd6a6ce65d",
    "20260829T174619Z_16fd6a6ce65d",
]


def main() -> None:
    danus = ROOT / "baselines/danus"
    run = ROOT / "experiments/danus_n18_matched_scheduling/arm_a_parallel" / RUN_ID
    project = danus / "runtime/projects" / PROJECT
    project_copy = run / "project_artifacts"
    if not project_copy.exists():
        copy_project_artifacts(project, project_copy)
    verifier_copy = run / "verifier_outputs"
    verifier_copy.mkdir(exist_ok=True)
    for run_id in VERIFIER_RUN_IDS:
        destination = verifier_copy / run_id
        if not destination.exists():
            shutil.copytree(danus / "runtime/verify-runs" / run_id, destination)
    (run / "system_invalid.json").write_text(
        json.dumps(
            {
                "classification": "SYSTEM_INVALID_RUN",
                "arm": "A",
                "problem_id": "vieta-jumping-square",
                "error_type": "CompletionCollectorRosterMismatch",
                "error": (
                    "The experiment imported the N1.6 status enumerator, which knows "
                    "high:3,xhigh:4 and cannot observe N1.8 workers high4 through high7."
                ),
                "recorded_at_utc": utc_now(),
                "interruption": (
                    "Controller was interrupted after all seven actual workers reached "
                    "max_rounds with last_rc=0; the orphan verifier was terminated."
                ),
                "mathematical_metrics_included": False,
                "replacement_allowed": True,
                "verifier_run_ids_preserved": VERIFIER_RUN_IDS,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
