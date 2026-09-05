"""Existing long-horizon limits; persisted runs retain consumed amounts."""
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class LongHorizonBudget:
    max_mutation_episodes: int = 6
    max_solver_attempts: int = 24
    max_builder_proposals: int = 12
    max_auditor_calls: int = 12



def _attempt_count(problem_dir: Path) -> int:
    return len(list((problem_dir / "attempts").glob("attempt-*.json")))
