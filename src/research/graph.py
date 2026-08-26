"""A small, inspectable, file-backed Research Fact Graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set

from .fact import Fact


_STATEMENT = "\n---\n# Statement\n\n"
_PROOF = "\n\n# Proof\n\n"


class FactGraph:
    def __init__(self, root: Path) -> None:
        self.facts_dir = root / "facts"
        self.facts_dir.mkdir(parents=True, exist_ok=True)

    def add_fact(self, fact: Fact) -> Fact:
        for predecessor_id in fact.predecessors:
            predecessor = self.get_fact(predecessor_id)
            if predecessor.problem_id != fact.problem_id:
                raise ValueError("predecessors must belong to the same problem")

        path = self._path(fact.fact_id)
        if path.exists():
            stored = self.get_fact(fact.fact_id)
            stored_content = (stored.problem_id, stored.statement, stored.proof, stored.predecessors)
            submitted_content = (fact.problem_id, fact.statement, fact.proof, fact.predecessors)
            if stored_content != submitted_content:
                raise ValueError(f"fact ID collision or corrupt file: {fact.fact_id}")
            return stored

        metadata = json.dumps(
            {
                "fact_id": fact.fact_id,
                "problem_id": fact.problem_id,
                "author": fact.author,
                "predecessors": list(fact.predecessors),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        path.write_text(
            f"---\n{metadata}{_STATEMENT}{fact.statement}{_PROOF}{fact.proof}\n",
            encoding="utf-8",
        )
        return fact

    def get_fact(self, fact_id: str) -> Fact:
        path = self._path(fact_id)
        if not path.is_file():
            raise KeyError(f"unknown fact: {fact_id}")
        raw = path.read_text(encoding="utf-8")
        metadata_text, body = raw.removeprefix("---\n").split(_STATEMENT, 1)
        statement, proof = body.split(_PROOF, 1)
        metadata = json.loads(metadata_text)
        fact = Fact.create(
            problem_id=metadata["problem_id"],
            author=metadata["author"],
            statement=statement,
            proof=proof,
            predecessors=metadata["predecessors"],
        )
        if fact.fact_id != metadata["fact_id"] or fact.fact_id != fact_id:
            raise ValueError(f"fact content hash mismatch: {fact_id}")
        return fact

    def list_facts(self) -> List[Fact]:
        return [self.get_fact(path.stem) for path in sorted(self.facts_dir.glob("*.md"))]

    def predecessors(self, fact_id: str) -> List[Fact]:
        return [self.get_fact(item) for item in self.get_fact(fact_id).predecessors]

    def supporting_closure(self, target_fact_id: str) -> List[Fact]:
        facts: Dict[str, Fact] = {}
        frontier = [target_fact_id]
        while frontier:
            fact_id = frontier.pop()
            if fact_id in facts:
                continue
            fact = self.get_fact(fact_id)
            facts[fact_id] = fact
            frontier.extend(fact.predecessors)

        remaining: Set[str] = set(facts)
        ordered: List[Fact] = []
        while remaining:
            ready = sorted(
                fact_id
                for fact_id in remaining
                if not remaining.intersection(facts[fact_id].predecessors)
            )
            if not ready:
                raise ValueError("research fact graph contains a cycle")
            ordered.extend(facts[fact_id] for fact_id in ready)
            remaining.difference_update(ready)
        return ordered

    def _path(self, fact_id: str) -> Path:
        return self.facts_dir / f"{fact_id}.md"
