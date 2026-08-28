"""Unverified proof-search state, kept separate from the Fact Graph."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .graph import FactGraph


class ObligationStatus(str, Enum):
    OPEN = "OPEN"
    RUNNING = "RUNNING"
    DISCHARGED = "DISCHARGED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ProofObligation:
    obligation_id: str
    premises: Tuple[str, ...]
    goal: str
    route_id: str
    status: ObligationStatus = ObligationStatus.OPEN
    resolved_by_fact_id: Optional[str] = None

    def __post_init__(self) -> None:
        obligation_id = self.obligation_id.strip()
        goal = " ".join(self.goal.split())
        route_id = self.route_id.strip()
        if not obligation_id or not goal or not route_id:
            raise ValueError("obligation_id, goal, and route_id must be non-empty")
        if self.status is ObligationStatus.DISCHARGED and not self.resolved_by_fact_id:
            raise ValueError("a discharged obligation requires resolved_by_fact_id")
        if self.status is not ObligationStatus.DISCHARGED and self.resolved_by_fact_id:
            raise ValueError("only a discharged obligation may have resolved_by_fact_id")
        object.__setattr__(self, "obligation_id", obligation_id)
        object.__setattr__(self, "premises", tuple(sorted(set(self.premises))))
        object.__setattr__(self, "goal", goal)
        object.__setattr__(self, "route_id", route_id)


@dataclass(frozen=True)
class Route:
    route_id: str
    obligation_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        route_id = self.route_id.strip()
        if not route_id:
            raise ValueError("route_id must be non-empty")
        object.__setattr__(self, "route_id", route_id)
        object.__setattr__(self, "obligation_ids", tuple(dict.fromkeys(self.obligation_ids)))


class ObligationRegistry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._obligations: Dict[str, ProofObligation] = {}
        if self.path.is_file():
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            for item in payload["obligations"]:
                obligation = ProofObligation(
                    obligation_id=item["obligation_id"],
                    premises=tuple(item["premises"]),
                    goal=item["goal"],
                    route_id=item["route_id"],
                    status=ObligationStatus(item["status"]),
                    resolved_by_fact_id=item["resolved_by_fact_id"],
                )
                self._obligations[obligation.obligation_id] = obligation

    def add(self, obligation: ProofObligation) -> ProofObligation:
        if obligation.status is not ObligationStatus.OPEN:
            raise ValueError("new obligations must be OPEN")
        existing = self._obligations.get(obligation.obligation_id)
        if existing is not None:
            if existing == obligation:
                return existing
            raise ValueError(f"obligation ID collision: {obligation.obligation_id}")
        identity = (obligation.premises, obligation.goal, obligation.route_id)
        if any((item.premises, item.goal, item.route_id) == identity for item in self._obligations.values()):
            raise ValueError("duplicate obligation")
        self._obligations[obligation.obligation_id] = obligation
        self._save()
        return obligation

    def get(self, obligation_id: str) -> ProofObligation:
        return self._obligations[obligation_id]

    def list(self) -> List[ProofObligation]:
        return [self._obligations[key] for key in sorted(self._obligations)]

    def transition(self, obligation_id: str, status: ObligationStatus) -> ProofObligation:
        obligation = self.get(obligation_id)
        allowed = {
            ObligationStatus.OPEN: {ObligationStatus.RUNNING, ObligationStatus.REJECTED},
            ObligationStatus.RUNNING: {ObligationStatus.OPEN, ObligationStatus.REJECTED},
            ObligationStatus.REJECTED: {ObligationStatus.RUNNING},
            ObligationStatus.DISCHARGED: set(),
        }
        if status not in allowed[obligation.status]:
            raise ValueError(f"invalid obligation transition: {obligation.status.value} -> {status.value}")
        updated = replace(obligation, status=status)
        self._obligations[obligation_id] = updated
        self._save()
        return updated

    def resolve(self, obligation_id: str, fact_id: str, graph: FactGraph) -> ProofObligation:
        obligation = self.get(obligation_id)
        fact = graph.get_fact(fact_id)
        if fact.statement != obligation.goal:
            raise ValueError("resolved Fact statement does not match obligation goal")
        if obligation.status is not ObligationStatus.RUNNING:
            raise ValueError("only a RUNNING obligation may be discharged")
        updated = replace(
            obligation,
            status=ObligationStatus.DISCHARGED,
            resolved_by_fact_id=fact.fact_id,
        )
        self._obligations[obligation_id] = updated
        self._save()
        return updated

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"obligations": []}
        for obligation in self.list():
            item = asdict(obligation)
            item["premises"] = list(obligation.premises)
            item["status"] = obligation.status.value
            payload["obligations"].append(item)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.path)
