"""Persistent mathematical obligations and AND/OR proof routes.

This is search state. Facts, counterexamples and execution journals have their
own stores; route readiness never admits mathematical truth.
"""
from dataclasses import asdict, dataclass, replace
from copy import deepcopy
from hashlib import sha256
from graphlib import TopologicalSorter
import json
from pathlib import Path
from typing import Optional, Tuple

from .fact import _normalize
from .run_storage import read_json, write_json


def _identity(prefix, payload):
    return prefix + sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24]


@dataclass(frozen=True)
class ProofObligation:
    obligation_id: str
    problem_id: str
    context: str
    goal: str
    truth_state: str = "OPEN"
    resolved_fact_id: Optional[str] = None
    resolved_route_id: Optional[str] = None
    refutation_id: Optional[str] = None

    @classmethod
    def create(cls, problem_id, context, goal):
        values = dict(problem_id=_normalize(problem_id), context=_normalize(context),
                      goal=_normalize(goal))
        if not values["problem_id"] or not values["goal"]:
            raise ValueError("problem and goal must be nonempty")
        return cls(_identity("ob-", values), **values)

    @property
    def statement(self):
        # Context is part of the statement admitted as a Fact, not an implicit
        # assumption that could be lost when the Fact is reused elsewhere.
        return f"Under the assumptions [{self.context}]: {self.goal}" if self.context else self.goal


@dataclass(frozen=True)
class ProofRoute:
    route_id: str
    target_obligation_id: str
    prerequisite_obligation_ids: Tuple[str, ...] = ()
    support_fact_ids: Tuple[str, ...] = ()
    kind: str = "DIRECT"
    origin_patch_id: Optional[str] = None
    lifecycle: str = "OPEN"
    exhaustion_attempt_ids: Tuple[str, ...] = ()
    exhaustion_reason: Optional[str] = None

    @classmethod
    def create(cls, target_obligation_id, prerequisite_obligation_ids=(),
               support_fact_ids=(), *, kind="DIRECT", origin_patch_id=None):
        values = dict(target_obligation_id=target_obligation_id,
                      prerequisite_obligation_ids=tuple(sorted(set(prerequisite_obligation_ids))),
                      support_fact_ids=tuple(sorted(set(support_fact_ids))), kind=kind)
        return cls(_identity("route-", values), **values, origin_patch_id=origin_patch_id)


@dataclass(frozen=True)
class Frontier:
    kind: str
    obligation_id: str
    route_id: Optional[str] = None


class ProofGraph:
    """One canonical, atomically replaced proof_graph.json per problem."""

    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "proof_graph.json"
        self._data = read_json(self.path)
        self._validate(self._data)
        self.problem_id = self._data["problem_id"]
        self.target_obligation_id = self._data["target_obligation_id"]
        self._check_evidence(self.root, self._data)

    @classmethod
    def create(cls, root, *, problem_id, target, obligations=(), routes=()):
        path = Path(root) / "proof_graph.json"
        if path.exists():
            raise ValueError("proof graph already exists")
        items = (*obligations, target)
        if any(o.truth_state != "OPEN" for o in items):
            raise ValueError("new obligations must be OPEN; only verified evidence resolves truth")
        data = {"schema_version": 3, "problem_id": problem_id,
                "target_obligation_id": target.obligation_id,
                "obligations": {o.obligation_id: asdict(o) for o in items},
                "routes": {r.route_id: asdict(r) for r in routes},
                "applied_patches": {}}
        cls._validate(data)
        cls._check_evidence(Path(root), data)
        write_json(path, data)
        return cls(root)

    @staticmethod
    def _validate(data):
        if data["schema_version"] != 3:
            raise ValueError("unsupported proof graph schema")
        obligations, routes = data["obligations"], data["routes"]
        if data["target_obligation_id"] not in obligations:
            raise ValueError("missing target obligation")
        dependencies = {key: set() for key in obligations}
        for key, value in obligations.items():
            item = ProofObligation(**value)
            expected = ProofObligation.create(item.problem_id, item.context, item.goal)
            if (key != item.obligation_id or key != expected.obligation_id
                    or item.problem_id != data["problem_id"]):
                raise ValueError("obligation mathematical identity mismatch")
            links = (item.resolved_fact_id, item.resolved_route_id, item.refutation_id)
            if item.truth_state == "OPEN":
                valid = not any(links)
            elif item.truth_state == "DISCHARGED":
                valid = bool(links[0] and links[1] and not links[2])
            elif item.truth_state == "REFUTED":
                valid = bool(links[2] and not links[0] and not links[1])
            else:
                valid = False
            if not valid:
                raise ValueError("inconsistent mathematical truth state")
        for key, value in routes.items():
            item = ProofRoute(**value)
            expected = ProofRoute.create(item.target_obligation_id,
                item.prerequisite_obligation_ids, item.support_fact_ids, kind=item.kind)
            if key != item.route_id or key != expected.route_id:
                raise ValueError("route identity mismatch")
            if item.kind not in ("DIRECT", "SPLIT", "CUT", "ALTERNATIVE"):
                raise ValueError("unknown route kind")
            if item.lifecycle not in ("OPEN", "EXHAUSTED"):
                raise ValueError("only route lifecycle is persistent")
            if item.lifecycle == "EXHAUSTED" and not (item.exhaustion_attempt_ids and item.exhaustion_reason):
                raise ValueError("route exhaustion requires evidence")
            if item.lifecycle == "OPEN" and (item.exhaustion_attempt_ids or item.exhaustion_reason):
                raise ValueError("OPEN route cannot carry exhaustion evidence")
            if item.target_obligation_id not in obligations or any(
                    p not in obligations for p in item.prerequisite_obligation_ids):
                raise ValueError("unknown route obligation")
            dependencies[item.target_obligation_id].update(item.prerequisite_obligation_ids)
        # Includes historical routes: no hidden cycle can become active later.
        tuple(TopologicalSorter(dependencies).static_order())

    def obligation(self, obligation_id):
        return ProofObligation(**self._data["obligations"][obligation_id])

    @staticmethod
    def _check_evidence(root, data):
        from .graph import FactGraph
        from .refutation import RefutationStore
        facts = FactGraph(root)

        def checked_fact(key):
            if not isinstance(key, str) or len(key) != 16 or any(c not in "0123456789abcdef" for c in key):
                raise ValueError("invalid Fact ID")
            fact = facts.get_fact(key)
            if any(f.problem_id != data["problem_id"] for f in facts.supporting_closure(key)):
                raise ValueError("support Fact belongs to another problem")
            return fact

        for value in data["routes"].values():
            route = ProofRoute(**value)
            for key in route.support_fact_ids:
                checked_fact(key)
            ids = route.exhaustion_attempt_ids
            if len(ids) != len(set(ids)):
                raise ValueError("duplicate exhaustion attempts")
            for key in ids:
                if not key.startswith("attempt-") or not key[8:].isdigit():
                    raise ValueError("invalid attempt ID")
                path = root / "attempts" / (key + ".json")
                if not path.is_file():
                    raise ValueError("missing exhaustion attempt evidence")
                attempt = read_json(path)
                if (attempt.get("attempt_id"), attempt.get("obligation_id"), attempt.get("route_id")) != (
                        key, route.target_obligation_id, route.route_id):
                    raise ValueError("exhaustion evidence identity mismatch")
                if attempt.get("outcome") not in ("PROOF_REJECTED", "COUNTEREXAMPLE_REJECTED", "NO_RESULT", "TIMEOUT"):
                    raise ValueError("system errors and successes do not exhaust a proof route")
        for value in data["obligations"].values():
            item = ProofObligation(**value)
            if item.truth_state == "REFUTED":
                if RefutationStore(root).get(item.refutation_id).obligation_id != item.obligation_id:
                    raise ValueError("persisted refutation does not establish this obligation's falsity")
            elif item.truth_state == "DISCHARGED":
                fact = checked_fact(item.resolved_fact_id)
                route = ProofRoute(**data["routes"][item.resolved_route_id])
                if (fact.problem_id != item.problem_id or fact.statement != item.statement
                        or route.target_obligation_id != item.obligation_id):
                    raise ValueError("persisted Fact does not resolve this obligation")
                prerequisites = [ProofObligation(**data["obligations"][key]) for key in route.prerequisite_obligation_ids]
                if route.lifecycle != "OPEN" or any(o.truth_state != "DISCHARGED" for o in prerequisites):
                    raise ValueError("resolved route lacks discharged prerequisites")
                expected = set(route.support_fact_ids) | {o.resolved_fact_id for o in prerequisites}
                if set(fact.predecessors) != expected:
                    raise ValueError("persisted Fact lost selected-route lineage")

    def obligations(self):
        return tuple(self.obligation(key) for key in sorted(self._data["obligations"]))

    def route(self, route_id):
        value = dict(self._data["routes"][route_id])
        for field in ("prerequisite_obligation_ids", "support_fact_ids", "exhaustion_attempt_ids"):
            value[field] = tuple(value[field])
        return ProofRoute(**value)

    def routes_for(self, obligation_id):
        return tuple(self.route(key) for key in sorted(self._data["routes"])
                     if self._data["routes"][key]["target_obligation_id"] == obligation_id)

    def route_state(self, route_id):
        route = self.route(route_id)
        states = [self.obligation(key).truth_state for key in route.prerequisite_obligation_ids]
        if "REFUTED" in states:
            return "IMPOSSIBLE"
        if route.lifecycle == "EXHAUSTED":
            return "EXHAUSTED"
        return "WAITING" if "OPEN" in states else "READY"

    def frontiers(self):
        """Target-reachable frontiers through viable routes, in stable ID order."""
        seen, found = set(), []
        pending = [self.target_obligation_id]
        while pending:
            key = pending.pop()
            if key in seen:
                continue
            seen.add(key)
            if self.obligation(key).truth_state != "OPEN":
                continue
            viable = [r for r in self.routes_for(key)
                      if self.route_state(r.route_id) in ("READY", "WAITING")]
            if not viable:
                found.append(Frontier("STRUCTURAL", key))
            for route in viable:
                if self.route_state(route.route_id) == "READY":
                    found.append(Frontier("PROOF", key, route.route_id))
                else:
                    pending.extend(route.prerequisite_obligation_ids)
        return tuple(sorted(found, key=lambda f: (f.obligation_id, f.route_id or "")))

    def _save(self, data):
        self._validate(data)
        self._check_evidence(self.root, data)
        write_json(self.path, data)
        self._data = data

    def resolve_refutation(self, obligation_id, refutation_id):
        from .refutation import RefutationStore
        item = self.obligation(obligation_id)
        refutation = RefutationStore(self.root).get(refutation_id)
        if refutation.obligation_id != obligation_id:
            raise ValueError("refutation concerns a different mathematical obligation")
        if item.truth_state != "OPEN":
            if item.refutation_id == refutation_id:
                return
            raise ValueError("cannot overwrite established truth")
        data = deepcopy(self._data)
        data["obligations"][obligation_id] = asdict(replace(item, truth_state="REFUTED", refutation_id=refutation_id))
        self._save(data)

    def materialized_predecessors(self, route_id):
        from .graph import FactGraph
        if self.route_state(route_id) != "READY":
            raise ValueError("route is not ready")
        route = self.route(route_id)
        ids = set(route.support_fact_ids)
        ids.update(self.obligation(key).resolved_fact_id for key in route.prerequisite_obligation_ids)
        graph = FactGraph(self.root)
        facts = tuple(graph.get_fact(key) for key in sorted(ids))
        for fact in facts:
            if fact.problem_id != self.problem_id:
                raise ValueError("support Fact belongs to another problem")
            graph.supporting_closure(fact.fact_id)
        return facts

    def resolve_fact(self, route_id, fact_id):
        """Reconcile a verifier-admitted Fact; never admit a candidate here."""
        from .graph import FactGraph
        route = self.route(route_id)
        item = self.obligation(route.target_obligation_id)
        if item.truth_state != "OPEN":
            if (item.resolved_fact_id, item.resolved_route_id) == (fact_id, route_id):
                return
            raise ValueError("cannot overwrite established truth")
        fact = FactGraph(self.root).get_fact(fact_id)
        if fact.problem_id != self.problem_id or fact.statement != item.statement:
            raise ValueError("Fact does not establish this contextual obligation")
        expected = {f.fact_id for f in self.materialized_predecessors(route_id)}
        if set(fact.predecessors) != expected:
            raise ValueError("Fact lineage does not match selected route")
        data = deepcopy(self._data)
        data["obligations"][item.obligation_id] = asdict(replace(item, truth_state="DISCHARGED",
                                                              resolved_fact_id=fact_id, resolved_route_id=route_id))
        self._save(data)

    def supporting_closure(self):
        from .graph import FactGraph
        target = self.obligation(self.target_obligation_id)
        if target.truth_state != "DISCHARGED":
            raise ValueError("target has no verified solution")
        return tuple(FactGraph(self.root).supporting_closure(target.resolved_fact_id))

    def exhaust_route(self, route_id, attempt_ids, reason):
        route = self.route(route_id)
        if self.obligation(route.target_obligation_id).truth_state != "OPEN":
            raise ValueError("cannot exhaust a resolved obligation's route")
        if not attempt_ids or not reason.strip():
            raise ValueError("exhaustion requires recorded local failure evidence")
        if route.lifecycle == "EXHAUSTED":
            if route.exhaustion_attempt_ids != tuple(attempt_ids) or route.exhaustion_reason != reason:
                raise ValueError("cannot overwrite exhaustion history")
            return
        data = deepcopy(self._data)
        data["routes"][route_id] = asdict(replace(route, lifecycle="EXHAUSTED",
                                                exhaustion_attempt_ids=tuple(attempt_ids), exhaustion_reason=reason))
        self._save(data)
