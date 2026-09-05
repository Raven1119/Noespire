"""N2S runner — strategy/patch separation probe, treatment arm (task card §9).

One case: `treatment` — K=4 fresh independent strategy-only samples over the
N2R frozen `finite_discrepancy` snapshot, using the treatment prompt (no
GraphPatch generation). Control is NOT re-run (§9): the N2R historical
record (2/8 completed, 6/8 timeout at the same 600s bound on the same
frozen input) is the baseline.

No patch builder (§16), no Structural Auditor (§17), no N2Q revision (§18),
no NodeSolver (§4). Post-hoc SketchAuditor quality audits only.

    .venv/Scripts/python.exe experiments/n2s_strategy_patch_separation/run_n2s.py \
        --case treatment [--force]
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2m_horizon_handoff",
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist",
    REPO_ROOT / "experiments" / "n2q_auditor_guided_revision",
    REPO_ROOT / "experiments" / "n2r_strategist_stability",
    HERE,
):
    sys.path.insert(0, str(path))

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from closed_book import ClosedBookCodexInvoker  # noqa: E402
from sampler import prepare_snapshot  # noqa: E402  (N2R, read-only)
from sketch import (  # noqa: E402
    SketchAuditor,
    StrategySketcher,
    run_sketch_samples,
)

PID = n2l.ERDOS67_PROBLEM_ID
FRONTIER = "finite_discrepancy"
K = 4  # §9: fixed before the run, never adjusted

# The already-stripped, hash-verified N2R primary frozen input (source audit
# §1). Read-only here; prepare_snapshot re-applies the strip defensively.
N2R_SNAPSHOT = (
    REPO_ROOT / "experiments" / "n2r_strategist_stability"
    / "runs" / "primary" / "snapshot"
)

# §9/§11: historical control from N2R — not re-run.
CONTROL = {"completed": 2, "timeout": 6, "k": 8}


def run_treatment(case_root: Path) -> dict:
    snapshot = prepare_snapshot(N2R_SNAPSHOT, case_root / "frozen_input")
    invoker = ClosedBookCodexInvoker(audit_dir=case_root / "evidence" / "invocations")
    sketcher = StrategySketcher(invoker)

    t0 = time.time()
    result = run_sketch_samples(
        snapshot,
        runs_dir=case_root,
        k=K,
        problem_id=PID,
        frontier=FRONTIER,
        sketcher=sketcher,
    )
    wall = round(time.time() - t0, 1)

    # Post-hoc independent quality audits (§12-§14) — never fed back.
    auditor = SketchAuditor(invoker)
    audits = []
    for record in result.records:
        entry = {"sample": record.sample, "outcome": record.outcome}
        if record.audit_packet is not None:
            try:
                entry["quality_audit"] = auditor.audit(record.audit_packet)
            except Exception as error:
                entry["quality_audit"] = {"error": f"{type(error).__name__}: {error}"}
            n2l._write_json(
                case_root / f"sample_{record.sample:02d}" / "quality_audit.json",
                entry["quality_audit"],
            )
        audits.append(entry)

    outcome_counts = {}
    for record in result.records:
        outcome_counts[record.outcome] = outcome_counts.get(record.outcome, 0) + 1
    useful = {"USEFUL_STRATEGY", "PLAUSIBLE_STRATEGY"}
    metrics = {
        "control": CONTROL,
        "treatment": {
            "k": result.k,
            "outcome_counts": outcome_counts,
            "completion": f"{outcome_counts.get('COMPLETED', 0) + outcome_counts.get('DECLINE', 0)}/{result.k}",
            "elapsed_seconds": {str(r.sample): r.elapsed_seconds for r in result.records},
            "useful_or_plausible_strategy_count": sum(
                1
                for a in audits
                if (a.get("quality_audit") or {}).get("strategy_class") in useful
            ),
            "real_reduction_count": sum(
                1
                for a in audits
                if (a.get("quality_audit") or {}).get("difficulty_reduction")
                == "REAL_REDUCTION"
            ),
            "strategy_families": {
                str(a["sample"]): (a.get("quality_audit") or {}).get("strategy_family")
                for a in audits
                if a.get("quality_audit")
            },
        },
        "snapshot_unchanged": result.snapshot_unchanged,
    }
    summary = {
        "case": "treatment",
        "frozen_input": str(N2R_SNAPSHOT.relative_to(REPO_ROOT)),
        "frontier": FRONTIER,
        "k": result.k,
        "snapshot_sha256": result.snapshot_hash,
        "snapshot_unchanged": result.snapshot_unchanged,
        "records": [asdict(record) for record in result.records],
        "quality_audits": audits,
        "metrics": metrics,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "wall_seconds": wall,
    }
    n2l._write_json(case_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, choices=("treatment",))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    case_root = HERE / "runs" / args.case
    if case_root.exists():
        if not args.force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    summary = run_treatment(case_root)
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
