"""Application-owned problem discovery over ``<workspaces_root>/index.json``.

Read-only in Slice 1: listing and lookup only. Creation, fork, and archive
mutations arrive with later slices. The index is the only listing source
(spec §4); workspace directories without an index entry do not exist as far
as the application layer is concerned.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import List, Optional


EXECUTION_LOG_NAME = "_execution_log.jsonl"


def workspace_last_activity(problem_dir: Path) -> Optional[float]:
    """Latest mtime among the problem's attempt files and execution log.

    ``None`` when the problem was never attempted (spec §6: ``last_activity``
    is ``null`` if none).
    """
    mtimes = [
        path.stat().st_mtime
        for path in (problem_dir / "attempts").glob("attempt-*.json")
    ]
    log = problem_dir / EXECUTION_LOG_NAME
    if log.is_file():
        mtimes.append(log.stat().st_mtime)
    return max(mtimes) if mtimes else None


@dataclass(frozen=True)
class ProblemEntry:
    problem_id: str
    statement: str
    derived_from: Optional[str]
    archived: bool
    created_at: str


class ProblemIndex:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list(self) -> List[ProblemEntry]:
        def sort_key(entry: ProblemEntry) -> tuple:
            activity = workspace_last_activity(self.root / entry.problem_id)
            return (activity is None, -(activity or 0.0), entry.problem_id)

        return sorted(self._entries(), key=sort_key)

    def get(self, problem_id: str) -> ProblemEntry:
        for entry in self._entries():
            if entry.problem_id == problem_id:
                return entry
        raise KeyError(f"unknown problem: {problem_id}")

    def _entries(self) -> List[ProblemEntry]:
        path = self.root / "index.json"
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [
            ProblemEntry(
                problem_id=item["problem_id"],
                statement=item["statement"],
                derived_from=item["derived_from"],
                archived=bool(item["archived"]),
                created_at=item["created_at"],
            )
            for item in payload["problems"]
        ]
