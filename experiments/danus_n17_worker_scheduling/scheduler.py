"""Frozen scheduling policies for the N1.7 external experiment harness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScheduleOutcome:
    solved: bool
    workers_launched: int
    worker_index_of_first_success: int | None
    stopped_after_success: bool
    unused_worker_budget: int


def run_schedule(arm: str, launch_and_check: Callable[[int], bool]) -> ScheduleOutcome:
    """Run Arm B once or Arm C serially, stopping C at the first verified target."""
    if arm not in {"B", "C"}:
        raise ValueError(f"unknown arm: {arm}")
    budget = 1 if arm == "B" else 7
    success_index = None
    launched = 0
    for index in range(1, budget + 1):
        launched = index
        if launch_and_check(index):
            success_index = index
            break
    return ScheduleOutcome(
        solved=success_index is not None,
        workers_launched=launched,
        worker_index_of_first_success=success_index,
        stopped_after_success=arm == "C" and success_index is not None,
        unused_worker_budget=budget - launched,
    )
