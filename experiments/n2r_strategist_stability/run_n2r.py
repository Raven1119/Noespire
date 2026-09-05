"""N2R runner — strategist stability sampling audit (task card §4/§6/§34).

Cases:
- primary: K=8 fresh independent strategist samples over the frozen
  pre-decision `finite_discrepancy` state (snapshot source: the committed N2Q
  live workspace, which ended STRATEGIST_DECLINED with zero mutations — its
  persisted workspace IS the decision-time state; see
  docs/n2r_strategist_stability_source_audit.md §1).
- secondary (optional, §31): K=4 over the advanced frontier
  `uniform_finite_torus_energy_certificate` (N2N committed workspace).

Each sample: strategize -> (DECLINE recorded) or compile -> frozen
mechanical validation -> fresh structural auditor -> on REVISE exactly one
N2Q bounded revision -> fresh auditor. Proposals never apply outside the
sample's own copy (§9). No NodeSolver is run (§10). K is fixed before the
run; there is no best-of-K, no selector, no resampling policy (§2).

    .venv/Scripts/python.exe experiments/n2r_strategist_stability/run_n2r.py \
        --case primary [--force]
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
    HERE,
):
    sys.path.insert(0, str(path))

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from closed_book import ClosedBookCodexInvoker  # noqa: E402
from proposal_audit import ProposalAuditor  # noqa: E402  (N2P)
from strategist import (  # noqa: E402  (N2P, unchanged)
    MathematicalStrategist,
    parse_strategist_output,
)
from reviser import (  # noqa: E402  (N2Q)
    LocalityAuditor,
    MathematicalReviser,
    parse_revision_output,
)
from sampler import prepare_snapshot, run_samples  # noqa: E402

PID = n2l.ERDOS67_PROBLEM_ID

CASES = {
    "primary": {
        "k": 8,
        "frontier": "finite_discrepancy",
        "source": (
            REPO_ROOT / "experiments" / "n2q_auditor_guided_revision"
            / "runs" / "erdos67" / "workspace" / PID
        ),
    },
    "secondary": {
        "k": 4,
        "frontier": "uniform_finite_torus_energy_certificate",
        "source": (
            REPO_ROOT / "experiments" / "n2n_failure_provenance"
            / "runs" / "erdos67" / "workspace" / PID
        ),
    },
}


def _agents(evidence_dir: Path):
    from research.agents import StructuralAuditor

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    strategist = MathematicalStrategist(invoker)  # N2P contract, byte-unchanged
    reviser = MathematicalReviser(invoker)  # N2Q contract, unchanged

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)  # fresh session

    return invoker, strategist, reviser, auditor_for


def _audit_samples(case_root: Path, invoker, result, *, frontier: str) -> list:
    """Post-hoc independent audits (§12-§14) — never fed back into sampling.

    Every sample gets the N2P ProposalAuditor over its decision-time audit
    packet; samples with a repaired v2 additionally get the N2Q
    LocalityAuditor (v1 vs v2, both re-parsed from the persisted packets —
    the same reconstruction run_n2q.py uses) and a proposal audit of v2."""
    proposal_auditor = ProposalAuditor(invoker)
    locality_auditor = LocalityAuditor(invoker)
    audits = []
    for record in result.records:
        entry = {"sample": record.sample, "outcome": record.outcome}
        sample_dir = case_root / f"sample_{record.sample:02d}"
        if record.audit_packet is not None:
            try:
                entry["proposal_audit_v1"] = proposal_auditor.audit(record.audit_packet)
            except Exception as error:
                entry["proposal_audit_v1"] = {
                    "error": f"{type(error).__name__}: {error}"
                }
            n2l._write_json(
                sample_dir / "proposal_audit.json", entry["proposal_audit_v1"]
            )
        revision = record.revision or {}
        v2_packet = revision.get("audit_packet")
        v2 = revision.get("v2")
        if v2_packet is not None and v2 is not None:
            try:
                v1 = parse_strategist_output(
                    json.loads(
                        (sample_dir / "strategist_packet.json").read_text(
                            encoding="utf-8"
                        )
                    )["raw"],
                    blocked_node_id=frontier,
                )
                v2_decision = parse_revision_output(
                    json.loads(
                        (sample_dir / "revision_packet.json").read_text(
                            encoding="utf-8"
                        )
                    )["raw"],
                    blocked_node_id=frontier,
                    expected_operator=record.operator,
                ).decision
                entry["locality_audit"] = locality_auditor.audit(
                    v1, v2_decision, tuple(record.auditor_reasons)
                )
                entry["proposal_audit_v2"] = proposal_auditor.audit(v2_packet)
            except Exception as error:
                entry["locality_audit"] = {"error": f"{type(error).__name__}: {error}"}
            n2l._write_json(
                sample_dir / "locality_audit.json",
                {
                    "locality_audit": entry.get("locality_audit"),
                    "proposal_audit_v2": entry.get("proposal_audit_v2"),
                },
            )
        audits.append(entry)
    return audits


def _aggregate(result, audits) -> dict:
    """Mechanically derivable §22/§23 metrics. Strategy-family clustering,
    duplicate-strategy, decline-cause and operator-demand analysis are
    independent semantic judgments reported separately (§15-§21)."""
    records = result.records
    outcome_counts = {}
    for record in records:
        outcome_counts[record.outcome] = outcome_counts.get(record.outcome, 0) + 1
    audit_by_sample = {a["sample"]: a for a in audits}

    def _v1_field(sample, field):
        audit = audit_by_sample.get(sample, {}).get("proposal_audit_v1") or {}
        return audit.get(field)

    useful = {
        "USEFUL_REDUCTION",
        "PLAUSIBLE_BUT_UNVERIFIED_STRATEGY",
    }
    audited_useful = [
        r.sample
        for r in records
        if r.outcome in ("AUDITOR_PASS", "AUDITOR_REVISE_PASS")
        and _v1_field(r.sample, "proposal_class") in useful
    ]
    decline = [r.sample for r in records if r.outcome == "DECLINE"]
    return {
        "total_samples": result.k,
        "outcome_counts": outcome_counts,
        "decline_count": len(decline),
        "proposal_count": result.k - outcome_counts.get("DECLINE", 0)
        - outcome_counts.get("STRATEGIST_TIMEOUT", 0)
        - outcome_counts.get("SAMPLE_ERROR", 0),
        "mechanically_valid_count": sum(
            outcome_counts.get(o, 0)
            for o in ("AUDITOR_PASS", "AUDITOR_REVISE_PASS",
                      "AUDITOR_REVISE_FAIL", "AUDITOR_REJECT")
        ),
        "auditor_pass_count": outcome_counts.get("AUDITOR_PASS", 0),
        "auditor_revise_count": outcome_counts.get("AUDITOR_REVISE_PASS", 0)
        + outcome_counts.get("AUDITOR_REVISE_FAIL", 0),
        "revision_pass_count": outcome_counts.get("AUDITOR_REVISE_PASS", 0),
        "auditor_reject_count": outcome_counts.get("AUDITOR_REJECT", 0),
        # §23: Audited Useful Strategy Rate = audited-useful / K (x/K, no
        # confidence intervals — §30).
        "audited_useful_strategy_samples": audited_useful,
        "audited_useful_strategy_rate": f"{len(audited_useful)}/{result.k}",
        # §24: False-Negative Decline Evidence — a DECLINE coexists with at
        # least one audited useful strategy on the identical frozen state.
        "false_negative_decline_evidence": bool(decline and audited_useful),
        "proposal_classes": {
            str(r.sample): _v1_field(r.sample, "proposal_class") for r in records
        },
        "difficulty_reduction": {
            str(r.sample): _v1_field(r.sample, "difficulty_reduction")
            for r in records
        },
        "coherence": {
            str(r.sample): _v1_field(r.sample, "coherence") for r in records
        },
        "snapshot_unchanged": result.snapshot_unchanged,
    }


def run_case(case: str, force: bool) -> dict:
    spec = CASES[case]
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)

    snapshot = prepare_snapshot(spec["source"], case_root / "snapshot")
    invoker, strategist, reviser, auditor_for = _agents(case_root / "evidence")

    t0 = time.time()
    result = run_samples(
        snapshot,
        runs_dir=case_root,
        k=spec["k"],
        problem_id=PID,
        frontier=spec["frontier"],
        strategist=strategist,
        reviser=reviser,
        auditor_for=auditor_for,
    )
    wall = round(time.time() - t0, 1)

    audits = _audit_samples(case_root, invoker, result, frontier=spec["frontier"])
    summary = {
        "case": case,
        "source_workspace": str(spec["source"].relative_to(REPO_ROOT)),
        "frontier": spec["frontier"],
        "k": result.k,
        "snapshot_sha256": result.snapshot_hash,
        "snapshot_unchanged": result.snapshot_unchanged,
        "records": [asdict(record) for record in result.records],
        "sample_audits": audits,
        "aggregate_metrics": _aggregate(result, audits),
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "wall_seconds": wall,
    }
    n2l._write_json(case_root / "aggregate_metrics.json", summary["aggregate_metrics"])
    n2l._write_json(case_root / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, choices=tuple(CASES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    print(json.dumps(summary["aggregate_metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
