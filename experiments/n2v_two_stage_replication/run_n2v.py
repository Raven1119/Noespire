"""N2V runner — two fresh replications of the N2U live #67 run (§5/§6).

Run 2 / Run 3 call the SAME `run_n2u.run_live(case_root)` — the frozen N2U
system byte-identical, no copied driver (§29). Each run starts from a fresh
`prepare_erdos67` workspace seeded by the frozen baseline; nothing is
inherited from N2U (§6). A drift-control manifest (§7) is persisted before
the run starts.

    .venv/Scripts/python.exe experiments/n2v_two_stage_replication/run_n2v.py \
        --case run_02 [--force]
    .venv/Scripts/python.exe experiments/n2v_two_stage_replication/run_n2v.py \
        --case aggregate
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2m_horizon_handoff",
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist",
    REPO_ROOT / "experiments" / "n2q_auditor_guided_revision",
    REPO_ROOT / "experiments" / "n2r_strategist_stability",
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation",
    REPO_ROOT / "experiments" / "n2t_strategy_patch_compilation",
    REPO_ROOT / "experiments" / "n2u_live_two_stage",
    HERE,
):
    sys.path.insert(0, str(path))

import run_n2u as n2u  # noqa: E402  (the frozen N2U runner, reused as-is)
from aggregate import write_aggregate  # noqa: E402
from manifest import build_manifest, manifest_digest  # noqa: E402


def run_replication(case_root: Path) -> dict:
    manifest = build_manifest()
    manifest["manifest_sha256"] = manifest_digest(manifest)
    manifest_path = case_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    # The frozen N2U live system, unchanged: same budgets, same solver
    # config, same components, same handoff (§2/§4/§7).
    summary = n2u.run_live(case_root)
    shutil.copy2(manifest_path, case_root / "evidence" / "manifest.json")
    summary["manifest_sha256"] = manifest["manifest_sha256"]
    (case_root / "evidence" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, choices=("run_02", "run_03", "aggregate"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.case == "aggregate":
        result = write_aggregate(HERE / "aggregate_summary.json")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    case_root = HERE / "runs" / args.case
    if case_root.exists():
        if not args.force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    summary = run_replication(case_root)
    printable = {k: v for k, v in summary.items() if k not in ("episodes", "fact_audit")}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
