"""Mechanically validate and aggregate the frozen N1.8 evidence."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


EXPERIMENT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = EXPERIMENT_ROOT / "protocol" / "runtime_manifest.json"
ARM_DIRECTORIES = {
    "A": "arm_a_parallel",
    "B": "arm_b_single",
    "C": "arm_c_sequential",
}
MATERIAL_REDUCTION = 0.5


def _load_results(arm: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    paths = sorted((EXPERIMENT_ROOT / ARM_DIRECTORIES[arm]).glob("*/result.json"))
    if len(paths) != 6:
        raise ValueError(f"Arm {arm}: expected six valid results, found {len(paths)}")
    expected = {item["problem_id"]: item["problem_sha256"] for item in manifest["problems"]}
    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    observed = {result["problem_id"]: result["problem_sha256"] for result in results}
    if observed != expected:
        raise ValueError(f"Arm {arm}: problem/hash set differs from frozen manifest")
    contract = manifest["worker_contract"]
    for result in results:
        if result["arm"] != arm:
            raise ValueError(f"Arm {arm}: mislabeled result {result['run_id']}")
        if result["blind_integrity"] != "BLIND_INTEGRITY_PASS":
            raise ValueError(f"Arm {arm}: non-PASS blind result {result['run_id']}")
        if result["workers_configured"] != contract["maximum_worker_slots"]:
            raise ValueError(f"Arm {arm}: configured roster mismatch in {result['run_id']}")
        expected_fields = {
            "worker_assignment_sha256": contract["assignment_sha256"],
            "worker_model": contract["model"],
            "worker_role": contract["role"],
            "worker_reasoning_effort": contract["reasoning_effort"],
            "blind_wrapper_sha256": manifest["blind_policy"]["wrapper_sha256"],
            "upstream_commit": manifest["danus"]["commit"],
        }
        for field, expected_value in expected_fields.items():
            if result[field] != expected_value:
                raise ValueError(f"Arm {arm}: {field} mismatch in {result['run_id']}")
        for field in ("worker_tokens", "verifier_tokens", "total_tokens"):
            if not isinstance(result[field], int):
                raise ValueError(f"Arm {arm}: unavailable {field} in {result['run_id']}")
    return results


def _mean(values: list[float | int | None]) -> float | None:
    observed = [float(value) for value in values if value is not None]
    return round(sum(observed) / len(observed), 6) if observed else None


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    facts = sum(result["verified_fact_count"] for result in results)
    outside = sum(result["facts_outside_closure"] for result in results)
    runs = sorted(results, key=lambda item: item["problem_id"])
    solved = sum(bool(result["solved"]) for result in results)
    return {
        "valid_runs": len(results),
        "solved": solved,
        "solve_rate": solved / len(results),
        "workers_launched": sum(result["workers_launched"] for result in results),
        "worker_attempts": sum(result["worker_attempts"] for result in results),
        "verifier_calls": sum(result["verifier_calls"] for result in results),
        "verifier_accepts": sum(result["verifier_accepts"] for result in results),
        "verifier_rejects": sum(result["verifier_rejects"] for result in results),
        "verified_fact_count": facts,
        "supporting_closure_size": sum(result["supporting_closure_size"] for result in results),
        "facts_outside_closure": outside,
        "verified_search_waste": round(outside / facts, 10) if facts else None,
        "worker_tokens": sum(result["worker_tokens"] for result in results),
        "verifier_tokens": sum(result["verifier_tokens"] for result in results),
        "total_tokens": sum(result["total_tokens"] for result in results),
        "mean_time_to_first_verified_target_seconds": _mean(
            [result["time_to_first_verified_target_seconds"] for result in results]
        ),
        "total_terminal_time_seconds": round(
            sum(result["time_to_terminal_run_seconds"] for result in results), 6
        ),
        "mean_terminal_time_seconds": _mean(
            [result["time_to_terminal_run_seconds"] for result in results]
        ),
        "runs": runs,
    }


def _reduction(baseline: int, candidate: int) -> float:
    return (baseline - candidate) / baseline if baseline else 0.0


def _by_problem(arm: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {run["problem_id"]: run for run in arm["runs"]}


def sequential_recoveries(evidence: dict[str, Any]) -> list[str]:
    arm_b = _by_problem(evidence["B"])
    return sorted(
        run["problem_id"]
        for run in evidence["C"]["runs"]
        if run.get("first_worker_result") == "FAIL"
        and run.get("solved")
        and (run.get("first_success_index") or 0) > 1
        and not arm_b[run["problem_id"]]["solved"]
    )


def verdict(evidence: dict[str, Any]) -> str:
    if not evidence["integrity_pass"]:
        return "INCONCLUSIVE"
    arm_a, arm_b, arm_c = evidence["A"], evidence["B"], evidence["C"]
    recoveries = sequential_recoveries(evidence)
    if (
        recoveries
        and arm_c["solved"] >= arm_b["solved"]
        and arm_c["total_tokens"] < arm_a["total_tokens"]
    ):
        return "SEQUENTIAL_RECOVERY_SUPPORTED"
    by_a, by_c = _by_problem(arm_a), _by_problem(arm_c)
    if any(run["solved"] and not by_c[problem]["solved"] for problem, run in by_a.items()):
        return "PARALLEL_REDUNDANCY_SUPPORTED"
    c_first_passes = all(
        run.get("first_worker_result") == "PASS" and run.get("first_success_index") == 1
        for run in arm_c["runs"]
    )
    if arm_b["solved"] == 6 and c_first_passes and arm_a["solved"] <= 6:
        return "SINGLE_WORKER_SUFFICIENT_ON_SET"
    for candidate in (arm_b, arm_c):
        approximately_matches = candidate["solved"] >= arm_a["solved"] - 1
        materially_lower = (
            _reduction(arm_a["workers_launched"], candidate["workers_launched"])
            >= MATERIAL_REDUCTION
            or _reduction(arm_a["total_tokens"], candidate["total_tokens"])
            >= MATERIAL_REDUCTION
        )
        if approximately_matches and materially_lower:
            return "MATCHED_DEMAND_DRIVEN_SUPPORTED"
    raise ValueError("complete integrity-passing evidence did not match a frozen verdict rule")


def build_evidence() -> dict[str, Any]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = {arm: _load_results(arm, manifest) for arm in ARM_DIRECTORIES}
    expected_order = [(item["problem_id"], item["arm"]) for item in manifest["run_order"]]
    observed_order = [
        (result["problem_id"], result["arm"])
        for result in sorted(
            (result for arm_results in results.values() for result in arm_results),
            key=lambda item: item["started_at_utc"],
        )
    ]
    if observed_order != expected_order:
        raise ValueError("valid-run order differs from frozen counterbalance")
    for problem in (item["problem_id"] for item in manifest["problems"]):
        hashes = {
            next(result for result in results[arm] if result["problem_id"] == problem)[
                "initial_state_sha256"
            ]
            for arm in ARM_DIRECTORIES
        }
        if len(hashes) != 1:
            raise ValueError(f"initial state mismatch across arms for {problem}")
    evidence = {
        "integrity_pass": True,
        "frozen_counterbalance_match": True,
        "matched_initial_states": True,
        **{arm: _aggregate(arm_results) for arm, arm_results in results.items()},
    }
    evidence["first_worker_failures"] = sorted(
        run["problem_id"]
        for run in evidence["C"]["runs"]
        if run["first_worker_result"] == "FAIL"
    )
    evidence["sequential_recoveries"] = sequential_recoveries(evidence)
    evidence["relative_to_A"] = {
        arm: {
            "worker_reduction_fraction": _reduction(
                evidence["A"]["workers_launched"], evidence[arm]["workers_launched"]
            ),
            "token_reduction_fraction": _reduction(
                evidence["A"]["total_tokens"], evidence[arm]["total_tokens"]
            ),
        }
        for arm in ("B", "C")
    }
    return evidence


def main() -> None:
    evidence = build_evidence()
    output = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "material_reduction_threshold": MATERIAL_REDUCTION,
        "evidence": evidence,
        "verdict": verdict(evidence),
    }
    output_path = EXPERIMENT_ROOT / "analysis" / "aggregate.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
