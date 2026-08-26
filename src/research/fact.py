"""Content-addressed research facts."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Tuple


def _normalize(text: str) -> str:
    return " ".join(text.split())


@dataclass(frozen=True)
class CandidateFact:
    statement: str
    proof: str
    predecessors: Tuple[str, ...]


@dataclass(frozen=True)
class Fact:
    fact_id: str
    problem_id: str
    author: str
    statement: str
    proof: str
    predecessors: Tuple[str, ...]

    @classmethod
    def create(
        cls,
        *,
        problem_id: str,
        author: str,
        statement: str,
        proof: str,
        predecessors: Iterable[str] = (),
    ) -> "Fact":
        normalized = {
            "problem_id": _normalize(problem_id),
            "statement": _normalize(statement),
            "proof": _normalize(proof),
            "predecessors": tuple(sorted(set(predecessors))),
        }
        if not all((normalized["problem_id"], _normalize(author), normalized["statement"], normalized["proof"])):
            raise ValueError("problem_id, author, statement, and proof must be non-empty")
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return cls(
            fact_id=sha256(canonical.encode("utf-8")).hexdigest()[:16],
            author=_normalize(author),
            **normalized,
        )
