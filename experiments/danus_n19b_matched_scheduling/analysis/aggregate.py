"""Re-derive N1.9b metrics with the frozen N1.8 evidence collector."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from experiments.danus_n18_matched_scheduling.analysis import aggregate as base
from experiments.danus_n19b_matched_scheduling import run_once as runtime


ROOT = Path(__file__).resolve().parents[1]
MATERIAL_REDUCTION = 0.5
_BASE_VALIDATE_RESULT = base.validate_result_against_raw


def _reduction(baseline: int, candidate: int) -> float:
    return (baseline - candidate) / baseline if baseline else 0.0


def verdict(evidence: dict[str, Any]) -> str:
    if not evidence["integrity_pass"]:
        return "INCONCLUSIVE"
    arm_a, arm_b, arm_c = evidence["A"], evidence["B"], evidence["C"]
    by_a = {run["problem_id"]: run for run in arm_a["runs"]}
    by_b = {run["problem_id"]: run for run in arm_b["runs"]}
    by_c = {run["problem_id"]: run for run in arm_c["runs"]}

    parallel_only_wins = any(
        run["solved"]
        and not by_b[problem]["solved"]
        and not by_c[problem]["solved"]
        for problem, run in by_a.items()
    )
    if parallel_only_wins:
        return "PARALLEL_REDUNDANCY_SUPPORTED"

    recoveries = base.sequential_recoveries(evidence)
    if recoveries:
        return "SEQUENTIAL_RECOVERY_SUPPORTED"

    c_first_passes = sum(
        run.get("first_worker_result") == "PASS" and run.get("first_success_index") == 1
        for run in arm_c["runs"]
    )
    b_worker_reduction = _reduction(arm_a["workers_launched"], arm_b["workers_launched"])
    c_worker_reduction = _reduction(arm_a["workers_launched"], arm_c["workers_launched"])
    b_token_reduction = _reduction(arm_a["total_tokens"], arm_b["total_tokens"])
    c_token_reduction = _reduction(arm_a["total_tokens"], arm_c["total_tokens"])
    both_materially_lower = (
        (b_worker_reduction >= MATERIAL_REDUCTION or b_token_reduction >= MATERIAL_REDUCTION)
        and (c_worker_reduction >= MATERIAL_REDUCTION or c_token_reduction >= MATERIAL_REDUCTION)
    )
    c_approximately_a = arm_c["solved"] >= arm_a["solved"] - 1
    c_needed_more_than_one = any(run["workers_launched"] > 1 for run in arm_c["runs"])
    if (
        arm_c["solved"] >= arm_b["solved"]
        and c_approximately_a
        and c_needed_more_than_one
        and (c_worker_reduction >= MATERIAL_REDUCTION or c_token_reduction >= MATERIAL_REDUCTION)
    ):
        return "DEMAND_DRIVEN_EXECUTION_SUPPORTED"

    if arm_b["solved"] >= arm_a["solved"] and c_first_passes >= 5 and both_materially_lower:
        return "SINGLE_WORKER_FIRST_SUPPORTED"

    a_latency = arm_a["mean_time_to_first_verified_target_seconds"]
    comparison_latencies = [
        value
        for value in (
            arm_b["mean_time_to_first_verified_target_seconds"],
            arm_c["mean_time_to_first_verified_target_seconds"],
        )
        if value is not None
    ]
    if (
        a_latency is not None
        and comparison_latencies
        and a_latency <= 0.5 * min(comparison_latencies)
        and arm_a["total_tokens"] <= 2 * min(arm_b["total_tokens"], arm_c["total_tokens"])
    ):
        return "PARALLEL_REDUNDANCY_SUPPORTED"
    arms = {"A": arm_a, "B": arm_b, "C": arm_c}
    tie_priority = {"B": 0, "C": 1, "A": 2}
    dominant = min(
        arms,
        key=lambda arm: (
            -arms[arm]["solved"],
            arms[arm]["workers_launched"],
            arms[arm]["total_tokens"],
            tie_priority[arm],
        ),
    )
    if dominant == "A":
        return "PARALLEL_REDUNDANCY_SUPPORTED"
    if dominant == "C" and c_needed_more_than_one:
        return "DEMAND_DRIVEN_EXECUTION_SUPPORTED"
    return "SINGLE_WORKER_FIRST_SUPPORTED"


def validate_scheduling_metrics(run: Path, result: dict[str, Any]) -> None:
    project = run / "project_artifacts"
    workers = json.loads((project / "project.json").read_text(encoding="utf-8"))["workers"]
    events = runtime.base.load_jsonl(project / "global_memory/verification.jsonl")
    expected = runtime.scheduling_metrics(
        events,
        (run / "input.md").read_text(encoding="utf-8"),
        workers,
    )
    for field, value in expected.items():
        if result.get(field) != value:
            raise ValueError(
                f"raw scheduling metric mismatch in {result['run_id']}: {field}: "
                f"recorded={result.get(field)!r}, observed={value!r}"
            )


def validate_result_against_raw(run: Path, result: dict[str, Any]) -> None:
    _BASE_VALIDATE_RESULT(run, result)
    validate_scheduling_metrics(run, result)


def configure_base() -> None:
    base.EXPERIMENT_ROOT = ROOT
    base.MANIFEST_PATH = ROOT / "protocol/runtime_manifest.json"
    base.MATERIAL_REDUCTION = MATERIAL_REDUCTION
    base.validate_result_against_raw = validate_result_against_raw
    base.verdict = verdict


def main() -> None:
    configure_base()
    base.main()


if __name__ == "__main__":
    main()
