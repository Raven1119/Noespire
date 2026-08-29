"""Mechanically aggregate the frozen N1.7 A/B/C evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = EXPERIMENT_ROOT / "protocol" / "runtime_manifest.json"


def _load_results(directory: str, arm: str) -> list[dict[str, Any]]:
    results = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((EXPERIMENT_ROOT / directory).glob("*/result.json"))
    ]
    if len(results) != 4:
        raise ValueError(f"Arm {arm}: expected four valid results, found {len(results)}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    expected = {item["problem_id"]: item["sha256"] for item in manifest["problems"]}
    observed = {result["problem_id"]: result["problem_sha256"] for result in results}
    if observed != expected:
        raise ValueError(f"Arm {arm}: problem/hash set differs from frozen manifest")
    for result in results:
        if result["arm"] != arm:
            raise ValueError(f"Arm {arm}: mislabeled result {result['run_id']}")
        if result["blind_integrity"] != "BLIND_INTEGRITY_PASS":
            raise ValueError(f"Arm {arm}: non-PASS blind result {result['run_id']}")
        if not isinstance(result["total_tokens"], int):
            raise ValueError(f"Arm {arm}: unavailable token evidence in {result['run_id']}")
    return results


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    valid_runs = len(results)
    verified_facts = sum(result["verified_fact_count"] for result in results)
    outside = sum(result["outside_closure_count"] for result in results)
    tokens = sum(result["total_tokens"] for result in results)
    workers = sum(result["workers_launched"] for result in results)
    aggregate = {
        "valid_runs": valid_runs,
        "solved": sum(bool(result["solved"]) for result in results),
        "solve_rate": sum(bool(result["solved"]) for result in results) / valid_runs,
        "workers_launched": workers,
        "mean_workers_launched": workers / valid_runs,
        "worker_attempts": sum(result["worker_attempts"] for result in results),
        "verifier_accepts": sum(result["verifier_accepts"] for result in results),
        "verifier_rejects": sum(result["verifier_rejects"] for result in results),
        "verified_fact_count": verified_facts,
        "supporting_closure_size": sum(
            result["supporting_closure_size"] for result in results
        ),
        "outside_closure_count": outside,
        "verified_search_waste": outside / verified_facts if verified_facts else None,
        "total_tokens": tokens,
        "mean_tokens_per_problem": tokens / valid_runs,
        "total_wall_clock_seconds": round(
            sum(result["wall_clock_seconds"] for result in results), 6
        ),
        "runs": [
            {
                "problem_id": result["problem_id"],
                "run_id": result["run_id"],
                "solved": result["solved"],
                "workers_launched": result["workers_launched"],
                "worker_attempts": result["worker_attempts"],
                "verifier_accepts": result["verifier_accepts"],
                "verifier_rejects": result["verifier_rejects"],
                "verified_fact_count": result["verified_fact_count"],
                "supporting_closure_size": result["supporting_closure_size"],
                "outside_closure_count": result["outside_closure_count"],
                "total_tokens": result["total_tokens"],
                "wall_clock_seconds": result["wall_clock_seconds"],
                "worker_index_of_first_success": result["worker_index_of_first_success"],
                "stopped_after_success": result["stopped_after_success"],
                "unused_worker_budget": result["unused_worker_budget"],
            }
            for result in sorted(results, key=lambda item: item["problem_id"])
        ],
    }
    return aggregate


def _arm_a(manifest: dict[str, Any]) -> dict[str, Any]:
    source = manifest["arms"]["A"]
    facts = source["verified_fact_count"]
    outside = source["outside_closure_count"]
    return {
        "valid_runs": source["problems"],
        "solved": source["solved"],
        "solve_rate": source["solved"] / source["problems"],
        "workers_launched": source["workers_launched"],
        "mean_workers_launched": source["workers_launched"] / source["problems"],
        "worker_attempts": source["workers_launched"],
        "verifier_accepts": source["verifier_accepts"],
        "verifier_rejects": source["verifier_rejects"],
        "verified_fact_count": facts,
        "supporting_closure_size": source["supporting_closure_size"],
        "outside_closure_count": outside,
        "verified_search_waste": outside / facts,
        "total_tokens": source["total_tokens"],
        "mean_tokens_per_problem": source["total_tokens"] / source["problems"],
        "total_wall_clock_seconds": source["wall_clock_seconds"],
        "source": source["source"],
        "rerun": source["rerun"],
    }


def _relative(arm_a: dict[str, Any], candidate: dict[str, Any]) -> dict[str, float]:
    waste_a = arm_a["verified_search_waste"]
    waste_candidate = candidate["verified_search_waste"]
    return {
        "token_reduction_fraction": (
            arm_a["total_tokens"] - candidate["total_tokens"]
        ) / arm_a["total_tokens"],
        "worker_reduction_fraction": (
            arm_a["workers_launched"] - candidate["workers_launched"]
        ) / arm_a["workers_launched"],
        "waste_reduction_absolute": waste_a - waste_candidate,
        "waste_reduction_fraction": (waste_a - waste_candidate) / waste_a,
        "wall_clock_change_fraction": (
            candidate["total_wall_clock_seconds"] - arm_a["total_wall_clock_seconds"]
        ) / arm_a["total_wall_clock_seconds"],
        "wall_clock_delta_seconds": (
            candidate["total_wall_clock_seconds"] - arm_a["total_wall_clock_seconds"]
        ),
    }


def build_evidence() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    arm_a = _arm_a(manifest)
    arm_b = _aggregate(_load_results("arm_b_single", "B"))
    arm_c = _aggregate(_load_results("arm_c_sequential", "C"))
    arm_c["first_success_indices"] = [
        run["worker_index_of_first_success"] for run in arm_c["runs"]
    ]
    arm_c["unused_worker_budget"] = sum(
        run["unused_worker_budget"] for run in arm_c["runs"]
    )
    evidence = {"A": arm_a, "B": arm_b, "C": arm_c}
    evidence["relative_to_A"] = {
        "B": _relative(arm_a, arm_b),
        "C": _relative(arm_a, arm_c),
    }
    return evidence


def verdict(evidence: dict[str, Any]) -> str:
    arm_a, arm_b, arm_c = evidence["A"], evidence["B"], evidence["C"]
    b_by_problem = {run["problem_id"]: run for run in arm_b["runs"]}
    recoveries = [
        run
        for run in arm_c["runs"]
        if not b_by_problem[run["problem_id"]]["solved"]
        and run["solved"]
        and (run["worker_index_of_first_success"] or 0) > 1
    ]
    if (
        arm_b["solved"] < arm_a["solved"]
        and recoveries
        and arm_c["total_tokens"] < arm_a["total_tokens"]
    ):
        return "SEQUENTIAL_ESCALATION_SUPPORTED"

    materially_lower = any(
        candidate["solved"] == arm_a["solved"]
        and relative["token_reduction_fraction"] >= 0.5
        and relative["worker_reduction_fraction"] >= 0.5
        and relative["waste_reduction_fraction"] >= 0.5
        for candidate, relative in (
            (arm_b, evidence["relative_to_A"]["B"]),
            (arm_c, evidence["relative_to_A"]["C"]),
        )
    )
    if materially_lower:
        return "DEMAND_DRIVEN_EXECUTION_SUPPORTED"
    if arm_a["solve_rate"] - max(arm_b["solve_rate"], arm_c["solve_rate"]) >= 0.25:
        return "REDUNDANCY_ROBUSTNESS_SUPPORTED"
    return "INCONCLUSIVE"


def main() -> None:
    evidence = build_evidence()
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evidence": evidence,
        "verdict": verdict(evidence),
        "material_threshold": (
            "For the DEMAND gate, solve count must equal A and token, worker, and relative "
            "waste reductions must each be at least 50%."
        ),
    }
    output_path = EXPERIMENT_ROOT / "analysis" / "aggregate.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
