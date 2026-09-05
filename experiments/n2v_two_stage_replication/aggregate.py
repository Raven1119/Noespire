"""N2V aggregate analysis (task card §9/§10/§12/§13/§19/§21/§22).

Mechanical aggregation over the three run summaries (N2U run 1 by
reference; N2V runs 2/3). All classifications that require judgment
(frontier audit §14, strategy families §15, partial-fidelity review §18)
are done on the persisted evidence at report time — this module only
computes what can be computed honestly from the summaries.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

RUNS = {
    "run_01_n2u": (
        REPO_ROOT
        / "experiments" / "n2u_live_two_stage" / "runs" / "erdos67"
        / "evidence" / "summary.json"
    ),
    "run_02": HERE / "runs" / "run_02" / "evidence" / "summary.json",
    "run_03": HERE / "runs" / "run_03" / "evidence" / "summary.json",
}


def load_summaries(paths: Optional[dict] = None) -> dict:
    summaries = {}
    for name, path in (paths or RUNS).items():
        summaries[name] = json.loads(Path(path).read_text(encoding="utf-8"))
    return summaries


def fact_classes(summary: dict) -> Tuple[list, list, list]:
    """(substantive, trivial, invalid) fact ids from the CASCADED audit —
    INVALID entries and their downstream dependents are never counted as
    progress (§21)."""
    substantive, trivial, invalid = [], [], []
    for entry in summary.get("fact_audit", []):
        cls = entry.get("classification")
        if cls == "SUBSTANTIVE":
            substantive.append(entry.get("fact_id"))
        elif cls == "TRIVIAL":
            trivial.append(entry.get("fact_id"))
        elif cls == "INVALID":
            invalid.append(entry.get("fact_id"))
    return substantive, trivial, invalid


def applied_episodes(summary: dict) -> list:
    return [e for e in summary.get("episodes", []) if e.get("outcome") == "PATCH_APPLIED"]


def distinct_applied_frontiers(summary: dict) -> int:
    return len({e["blocked_node_id"] for e in applied_episodes(summary)})


def supporting_closure_size(summary: dict) -> int:
    """Transitive predecessor-closure size of the deepest admitted Fact
    (§13), computed over the cascaded-valid facts only."""
    invalid = set(fact_classes(summary)[2])
    facts = {
        f["fact_id"]: tuple(f.get("predecessors", ()))
        for f in summary.get("metrics", {}).get("facts", [])
        if f["fact_id"] not in invalid
    }
    if not facts:
        return 0
    best = 0
    for start in facts:
        seen, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node in seen or node not in facts:
                continue
            seen.add(node)
            stack.extend(facts[node])
        best = max(best, len(seen))
    return best


def replicated_long_horizon_progress(summary: dict) -> Tuple[bool, dict]:
    """§9 primary replication criterion, mechanically checkable parts."""
    substantive, _, invalid = fact_classes(summary)
    checks = {
        "horizon_handoff>=1": summary.get("horizon_handoffs", 0) >= 1,
        "complete_two_stage_episode>=1": len(summary.get("episodes", ())) >= 1,
        "patch_applied>=1": summary.get("mutation_episodes", 0) >= 1,
        "substantive_valid_fact>=1": len(substantive) >= 1,
        "frontier_movement": distinct_applied_frontiers(summary) >= 1
        and len(substantive) >= 1,
        "zero_invalid_supporting_facts": len(invalid) == 0,
    }
    return all(checks.values()), checks


def multi_stage_replication(summary: dict) -> bool:
    """§10 strong criterion."""
    substantive, _, invalid = fact_classes(summary)
    return (
        summary.get("mutation_episodes", 0) >= 2
        and distinct_applied_frontiers(summary) >= 2
        and len(substantive) >= 2
        and len(invalid) == 0
    )


def precise_stop_reason(summary: dict) -> str:
    """§19 stop-reason vocabulary; splits BUDGET_EXHAUSTED by which frozen
    budget actually bound the run."""
    stop = summary.get("stop_reason")
    if stop != "BUDGET_EXHAUSTED":
        return {
            "TARGET_SOLVED": "TARGET_SOLVED",
            "STRATEGIST_TIMEOUT": "STRATEGIST_TIMEOUT",
            "STRATEGIST_DECLINE": "STRATEGIST_DECLINE",
            "STRATEGY_GATE_REJECT": "STRATEGY_GATE_REJECT",
            "PATCH_BUILDER_TIMEOUT": "PATCH_STAGE_FAILURE",
            "PATCH_COMPILATION_INVALID": "PATCH_STAGE_FAILURE",
            "MECHANICAL_FAIL": "PATCH_STAGE_FAILURE",
            "STRUCTURAL_AUDITOR_REJECT": "STRUCTURAL_AUDIT_STOP",
            "REVISION_FAILED": "STRUCTURAL_AUDIT_STOP",
            "FRONTIER_EXHAUSTED": "OPERATORS/STRATEGY_EXHAUSTED",
            "SYSTEM_ERROR": "SYSTEM_ERROR",
        }.get(stop, f"SYSTEM_ERROR({stop})")
    budget = summary.get("budget", {})
    audit_side = (
        summary.get("gate_calls", 0)
        + summary.get("fidelity_calls", 0)
        + summary.get("auditor_calls", 0)
    )
    proposal_side = (
        summary.get("strategist_calls", 0)
        + summary.get("patch_builder_calls", 0)
        + summary.get("revision_calls", 0)
    )
    if audit_side >= budget.get("max_auditor_calls", 0):
        return "AUDIT_BUDGET_EXHAUSTED"
    if summary.get("mutation_episodes", 0) >= budget.get("max_mutation_episodes", 0):
        return "MUTATION_BUDGET_EXHAUSTED"
    if summary.get("metrics", {}).get("solver_attempts_during_run", 0) >= budget.get(
        "max_solver_attempts", 0
    ):
        return "NODE_ATTEMPT_BUDGET_EXHAUSTED"
    if proposal_side >= budget.get("max_builder_proposals", 0):
        return "PROPOSAL_BUDGET_EXHAUSTED"
    return "BUDGET_EXHAUSTED(unattributed)"


def per_run_metrics(summary: dict) -> dict:
    """§12/§13 per-run metrics extraction."""
    substantive, trivial, invalid = fact_classes(summary)
    episodes = summary.get("episodes", [])
    revisions = [e.get("revision") or {} for e in episodes]
    return {
        "stop_reason": precise_stop_reason(summary),
        "raw_stop_reason": summary.get("stop_reason"),
        "horizon_handoffs": summary.get("horizon_handoffs", 0),
        "strategy_calls": summary.get("strategist_calls", 0),
        "strategy_timeout": summary.get("strategist_timeouts", 0),
        "strategy_completed": summary.get("strategist_calls", 0)
        - summary.get("strategist_timeouts", 0),
        "strategy_gate_pass": summary.get("gate_calls", 0)
        - summary.get("gate_rejects", 0),
        "strategy_gate_reject": summary.get("gate_rejects", 0),
        "patch_builder_calls": summary.get("patch_builder_calls", 0),
        "patch_builder_timeout": summary.get("patch_builder_timeouts", 0),
        "structural_auditor_pass": sum(
            1 for e in episodes if e.get("auditor_verdict") == "PASS"
        ) + sum(1 for r in revisions if r.get("auditor_v2_verdict") == "PASS"),
        "structural_auditor_revise": sum(
            1 for e in episodes if e.get("auditor_verdict") == "REVISE"
        ),
        "structural_auditor_reject": sum(
            1 for e in episodes if e.get("auditor_verdict") == "REJECT"
        ) + sum(1 for r in revisions if r.get("auditor_v2_verdict") == "REJECT"),
        "revision_calls": summary.get("revision_calls", 0),
        "revision_pass": sum(
            1 for r in revisions if r.get("outcome") == "REVISION_PASS"
        ),
        "patches_applied": summary.get("mutation_episodes", 0),
        "node_solver_attempts": summary.get("metrics", {}).get(
            "solver_attempts_during_run", 0
        ),
        "node_solver_timeouts": summary.get("metrics", {}).get("system_errors", 0),
        "verifier_rejections": summary.get("metrics", {}).get(
            "verifier_rejections", 0
        ),
        "external_authority_rejects": summary.get("metrics", {}).get(
            "external_authority_rejections", 0
        ),
        "facts_total": summary.get("metrics", {}).get("fact_count", 0),
        "facts_substantive": len(substantive),
        "facts_trivial": len(trivial),
        "facts_invalid": len(invalid),
        "verified_reasoning_depth": summary.get("metrics", {}).get(
            "verified_reasoning_depth", 0
        ),
        "frontier_advances": distinct_applied_frontiers(summary),
        "supporting_closure_size": supporting_closure_size(summary),
        "operators": {
            op: sum(1 for e in episodes if e.get("operator") == op)
            for op in ("SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE")
        },
        "fidelity": {
            cls: sum(1 for e in episodes if e.get("strategy_fidelity") == cls)
            for cls in ("FAITHFUL", "PARTIALLY_FAITHFUL", "STRATEGY_DRIFT")
        },
        "operator_drift": sum(
            1 for e in episodes if e.get("operator_check") == "OPERATOR_DRIFT"
        ),
        "network_retrieval_attempts": summary.get("network_retrieval_attempts", 0),
        "wall_seconds": summary.get("wall_seconds"),
    }


def aggregate(summaries: dict) -> dict:
    """The §22/§23 verdict inputs, computed mechanically."""
    per_run = {}
    for name, summary in summaries.items():
        replicated, checks = replicated_long_horizon_progress(summary)
        per_run[name] = {
            "metrics": per_run_metrics(summary),
            "replicated_long_horizon_progress": replicated,
            "replication_checks": checks,
            "multi_stage_replication": multi_stage_replication(summary),
        }
    replicated_count = sum(
        1 for r in per_run.values() if r["replicated_long_horizon_progress"]
    )
    clean_progress_count = sum(
        1
        for r in per_run.values()
        if r["replication_checks"]["zero_invalid_supporting_facts"]
        and r["metrics"]["facts_substantive"] >= 1
        and r["metrics"]["frontier_advances"] >= 1
    )
    multi_stage_count = sum(
        1 for r in per_run.values() if r["multi_stage_replication"]
    )
    return {
        "per_run": per_run,
        "replicated_count": replicated_count,
        "clean_substantive_progress_count": clean_progress_count,
        "multi_stage_count": multi_stage_count,
        # §22: run 1 (N2U) progress AND >=1 of run 2/3 replicated AND
        # >=2 of 3 runs clean with substantive frontier movement.
        "replication_supported": (
            per_run.get("run_01_n2u", {}).get("replicated_long_horizon_progress", False)
            and any(
                per_run.get(name, {}).get("replicated_long_horizon_progress", False)
                for name in ("run_02", "run_03")
            )
            and clean_progress_count >= 2
        ),
        # §23: STRONG = 3/3 replicated AND >=2/3 multi-stage;
        # MODERATE = 2/3 substantive progress; LOW = only run 1.
        "stability": (
            "STRONG"
            if replicated_count == 3 and multi_stage_count >= 2
            else "MODERATE"
            if clean_progress_count >= 2
            else "LOW"
        ),
    }


def write_aggregate(out_path: Path, summaries: Optional[dict] = None) -> dict:
    result = aggregate(summaries or load_summaries())
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
