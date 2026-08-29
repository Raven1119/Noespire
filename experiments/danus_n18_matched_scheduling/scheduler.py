"""Strictly matched launch policies for the N1.8 experiment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ScheduleOutcome:
    solved: bool
    workers_launched: int
    first_success_index: int | None
    workers_saved: int
    stopped_after_success: bool


def run_schedule(
    arm: str, launch_batch: Callable[[tuple[int, ...]], bool]
) -> ScheduleOutcome:
    """Launch the frozen worker slots in the batch pattern defined by one arm."""
    if arm not in {"A", "B", "C"}:
        raise ValueError(f"unknown arm: {arm}")

    if arm == "A":
        solved = launch_batch(tuple(range(1, 8)))
        return ScheduleOutcome(solved, 7, None, 0, False)

    budget = 1 if arm == "B" else 7
    first_success = None
    launched = 0
    for index in range(1, budget + 1):
        launched = index
        if launch_batch((index,)):
            first_success = index
            break
    return ScheduleOutcome(
        solved=first_success is not None,
        workers_launched=launched,
        first_success_index=first_success,
        workers_saved=budget - launched,
        stopped_after_success=arm == "C" and first_success is not None,
    )
