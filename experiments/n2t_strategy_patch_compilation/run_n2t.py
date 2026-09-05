"""N2T runner — strategy-to-GraphPatch compilation probe (task card §3-§5/§12).

Compiles the four frozen N2S Strategy Sketches (3 PLAUSIBLE + 1 INVALID
control) into typed GraphPatches via a fresh strategy-bound Patch Builder
(K=1 per sketch), then the frozen pipeline: mechanical validation -> fresh
Structural Auditor -> at most one N2Q revision. No NodeSolver (§23), patches
apply only to per-sketch temp workspaces (§24). The builder never sees the
N2S quality-audit verdicts (§3).

    .venv/Scripts/python.exe experiments/n2t_strategy_patch_compilation/run_n2t.py \
        [--force]
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
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation",
    HERE,
):
    sys.path.insert(0, str(path))

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from closed_book import ClosedBookCodexInvoker  # noqa: E402
from sampler import prepare_snapshot  # noqa: E402  (N2R, read-only)
from sketch import parse_sketch_output  # noqa: E402  (N2S, read-only)
from reviser import LocalityAuditor, MathematicalReviser  # noqa: E402  (N2Q)
from patch_builder import (  # noqa: E402
    FidelityAuditor,
    StrategyBoundPatchBuilder,
    run_compilations,
)

PID = n2l.ERDOS67_PROBLEM_ID
FRONTIER = "finite_discrepancy"

N2R_SNAPSHOT = (
    REPO_ROOT / "experiments" / "n2r_strategist_stability"
    / "runs" / "primary" / "snapshot"
)
N2S_RUN = (
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation"
    / "runs" / "treatment"
)

# §3-§5: the four frozen N2S sketches. `role` is bookkeeping for the report
# only — the Patch Builder never sees it (§3: no audit-verdict anchoring).
SKETCHES = (
    ("sample_01", "primary"),   # PLAUSIBLE_STRATEGY (N2S audit)
    ("sample_02", "invalid_control"),  # INVALID (N2S audit)
    ("sample_03", "primary"),   # PLAUSIBLE_STRATEGY
    ("sample_04", "primary"),   # PLAUSIBLE_STRATEGY
)


def _load_sketches() -> tuple:
    sketches = []
    for name, role in SKETCHES:
        packet = json.loads(
            (N2S_RUN / name / "strategist_packet.json").read_text(encoding="utf-8")
        )
        sketch = parse_sketch_output(packet["raw"], blocked_node_id=FRONTIER)
        sketches.append((name, role, sketch, packet))
    return tuple(sketches)


def run_probe(case_root: Path) -> dict:
    snapshot = prepare_snapshot(N2R_SNAPSHOT, case_root / "frozen_input")
    invoker = ClosedBookCodexInvoker(audit_dir=case_root / "evidence" / "invocations")
    builder = StrategyBoundPatchBuilder(invoker)
    reviser = MathematicalReviser(invoker)  # N2Q contract, unchanged

    from research.agents import StructuralAuditor

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)  # fresh session

    loaded = _load_sketches()
    t0 = time.time()
    result = run_compilations(
        snapshot,
        runs_dir=case_root,
        sketches=tuple((name, sketch) for name, role, sketch, _ in loaded),
        problem_id=PID,
        frontier=FRONTIER,
        builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
    )
    wall = round(time.time() - t0, 1)

    # Post-hoc independent audits (§16-§19) — never fed back.
    fidelity_auditor = FidelityAuditor(invoker)
    locality_auditor = LocalityAuditor(invoker)
    audits = []
    for (name, role, sketch, _), record in zip(loaded, result.records):
        entry = {"sketch": name, "role": role, "outcome": record.outcome}
        sample_dir = case_root / f"sketch_{name}"
        packet_path = sample_dir / "patch_builder_packet.json"
        if packet_path.is_file() and record.outcome not in (
            "COMPILATION_DECLINE", "PATCH_TIMEOUT", "SAMPLE_ERROR",
        ):
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            revision = record.revision or {}
            final_nodes = (
                revision.get("v2", {}).get("new_nodes")
                if revision.get("outcome") == "REVISION_PASS"
                else packet["new_nodes"]
            )
            try:
                entry["fidelity_audit"] = fidelity_auditor.audit(
                    sketch, tuple(final_nodes or ()), record.operator
                )
            except Exception as error:
                entry["fidelity_audit"] = {
                    "error": f"{type(error).__name__}: {error}"
                }
            if revision.get("v2"):
                try:
                    from strategist import parse_strategist_output
                    from reviser import parse_revision_output
                    v1 = parse_strategist_output(
                        json.dumps({
                            "obstruction": sketch.obstruction,
                            "evidence": list(sketch.evidence),
                            "mathematical_idea": sketch.mathematical_idea,
                            "why_this_reduces_difficulty": sketch.why_this_reduces_difficulty,
                            "operator": sketch.operator,
                            "why_current_route_is_exhausted": sketch.why_current_route_is_exhausted,
                            "decline_reason": "",
                            "new_nodes": packet["new_nodes"],
                        }),
                        blocked_node_id=FRONTIER,
                    )
                    v2 = parse_revision_output(
                        json.loads(
                            (sample_dir / "revision_packet.json").read_text(
                                encoding="utf-8"
                            )
                        )["raw"],
                        blocked_node_id=FRONTIER,
                        expected_operator=record.operator,
                    ).decision
                    entry["locality_audit"] = locality_auditor.audit(
                        v1, v2, tuple(record.auditor_reasons)
                    )
                except Exception as error:
                    entry["locality_audit"] = {
                        "error": f"{type(error).__name__}: {error}"
                    }
            n2l._write_json(
                sample_dir / "fidelity_audit.json",
                {
                    "fidelity_audit": entry.get("fidelity_audit"),
                    "locality_audit": entry.get("locality_audit"),
                },
            )
        audits.append(entry)

    # §30 metrics.
    primary = [
        (a, r)
        for a, r in zip(audits, result.records)
        if a["role"] == "primary"
    ]

    def faithful(a):
        return (a.get("fidelity_audit") or {}).get("strategy_fidelity") == "FAITHFUL"

    compiled_audited = [
        a["sketch"]
        for a, r in primary
        if r.outcome in ("AUDITOR_PASS", "AUDITOR_REVISE_PASS") and faithful(a)
    ]
    n2s_records = {
        r["sample"]: r
        for r in json.loads(
            (N2S_RUN / "summary.json").read_text(encoding="utf-8")
        )["records"]
    }
    sample_index = {name: int(name.split("_")[1]) for name, *_ in loaded}
    metrics = {
        "plausible_sketches": 3,
        "patch_builder_completion": sum(
            1 for _, r in primary
            if r.outcome not in ("PATCH_TIMEOUT", "SAMPLE_ERROR")
        ),
        "patch_builder_timeouts": sum(
            1 for _, r in primary if r.outcome == "PATCH_TIMEOUT"
        ),
        "mechanically_valid": sum(
            1 for _, r in primary
            if r.outcome in ("AUDITOR_PASS", "AUDITOR_REVISE_PASS",
                             "AUDITOR_REVISE_FAIL", "AUDITOR_REJECT")
        ),
        "auditor_pass": sum(1 for _, r in primary if r.outcome == "AUDITOR_PASS"),
        "auditor_revise_pass": sum(
            1 for _, r in primary if r.outcome == "AUDITOR_REVISE_PASS"
        ),
        "auditor_revise_fail": sum(
            1 for _, r in primary if r.outcome == "AUDITOR_REVISE_FAIL"
        ),
        "auditor_reject": sum(
            1 for _, r in primary if r.outcome == "AUDITOR_REJECT"
        ),
        "compilation_decline": sum(
            1 for _, r in primary if r.outcome == "COMPILATION_DECLINE"
        ),
        "faithful_patch_count": sum(1 for a, _ in primary if faithful(a)),
        "strategy_drift_count": sum(
            1 for a, _ in primary
            if (a.get("fidelity_audit") or {}).get("strategy_fidelity")
            == "STRATEGY_DRIFT"
        ),
        # §18: operator drift is impossible by construction (the builder
        # schema has no operator field); assert it held on every record.
        "operator_drift_count": sum(
            1 for a, r in primary
            if r.operator
            != dict((n, s.operator) for n, _, s, _ in loaded)[a["sketch"]]
        ),
        "COMPILED_AUDITED_PATCH": compiled_audited,
        "timing": {
            # §25: two-stage total = N2S strategy time + N2T patch-stage time.
            a["sketch"]: {
                "strategy_seconds": n2s_records[sample_index[a["sketch"]]]["elapsed_seconds"],
                "patch_compile_seconds": r.elapsed_seconds,
                "revision_seconds": (r.revision or {}).get("revision_seconds"),
            }
            for a, r in zip(audits, result.records)
        },
        "invalid_control_outcome": next(
            a["outcome"] for a in audits if a["role"] == "invalid_control"
        ),
    }
    summary = {
        "case": "compile_probe",
        "frozen_input": str(N2R_SNAPSHOT.relative_to(REPO_ROOT)),
        "sketches_source": str(N2S_RUN.relative_to(REPO_ROOT)),
        "frontier": FRONTIER,
        "snapshot_sha256": result.snapshot_hash,
        "snapshot_unchanged": result.snapshot_unchanged,
        "records": [asdict(record) for record in result.records],
        "audits": audits,
        "metrics": metrics,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "wall_seconds": wall,
    }
    n2l._write_json(case_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    case_root = HERE / "runs" / "compile_probe"
    if case_root.exists():
        if not args.force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    summary = run_probe(case_root)
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
