"""Application-owned problem discovery over ``<workspaces_root>/index.json``.

Slice 1 added listing and lookup; Slice 2 adds ``add`` — the minimal create
capability behind ``POST /api/problems`` (spec §4/§6). Fork and archive
arrive with later slices. The index is the only listing source (spec §4);
workspace directories without an index entry do not exist as far as the
application layer is concerned.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import Lock
from typing import Dict, List, Optional


EXECUTION_LOG_NAME = "_execution_log.jsonl"

_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")

# FastAPI sync handlers run in a threadpool, and http.py constructs a fresh
# ProblemIndex per request — a per-instance lock would not serialize anything.
# The add() read-modify-write cycle is therefore guarded by module-level locks
# keyed by resolved data root. V1 is a single-process loopback server, so an
# in-process mutex per root is the honest minimal mechanism (no file locks, no
# database); distinct roots never block each other.
_ROOT_LOCKS: Dict[Path, Lock] = {}
_ROOT_LOCKS_GUARD = Lock()


def _lock_for(root: Path) -> Lock:
    with _ROOT_LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(root.resolve(), Lock())


def _normalize(statement: str) -> str:
    """Whitespace-collapse, same style as ``research.fact._normalize``."""
    return " ".join(statement.split())


def _slug(statement: str) -> str:
    """Filesystem-safe slug of the statement prefix (spec §4)."""
    slug = _SLUG_PATTERN.sub("-", statement.lower()).strip("-")
    return slug[:40].strip("-") or "problem"


def _write_json(path: Path, payload: dict) -> None:
    """Atomic tmp-file + replace, matching research-core practice (spec §4)."""
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


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

    def add(self, statement: str) -> ProblemEntry:
        """Create a problem: index entry plus an empty workspace directory.

        No core files are created — the research core writes
        ``obligations.json``/``facts/``/``attempts/`` at first solve (spec §6).
        Raises ``ValueError`` on a blank statement; only ``ValueError`` may be
        mapped to HTTP 400.
        """
        normalized = _normalize(statement)
        if not normalized:
            raise ValueError("statement must be non-empty")
        slug = _slug(normalized)
        # The whole read-modify-write cycle is the critical section: reading
        # outside the lock would reintroduce the stale-index clobber.
        with _lock_for(self.root):
            taken = {entry.problem_id for entry in self._entries()}
            while True:
                created_at = datetime.now().astimezone().isoformat()
                suffix = sha256(f"{normalized}\n{created_at}".encode("utf-8")).hexdigest()[:6]
                problem_id = f"{slug}-{suffix}"
                if problem_id not in taken and not (self.root / problem_id).exists():
                    break  # re-roll with a fresh timestamp; never overwrite
            entry = ProblemEntry(
                problem_id=problem_id,
                statement=normalized,
                derived_from=None,
                archived=False,
                created_at=created_at,
            )
            problem_dir = self.root / problem_id
            problem_dir.mkdir(parents=True)
            payload = {"problems": [vars(item) for item in self._entries()]}
            payload["problems"].append(vars(entry))
            try:
                _write_json(self.root / "index.json", payload)
            except Exception:
                # Roll back only the directory THIS call just created, and only
                # if still empty — rmdir refuses non-empty dirs. Pre-existing
                # dirs and entries are never touched.
                try:
                    problem_dir.rmdir()
                except OSError:
                    pass
                raise
            return entry

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
