"""Code-enforced one-relation neighborhoods; no global state is a model packet."""
from dataclasses import asdict
import json

from .graph import FactGraph
from .refutation import RefutationStore
from .run_storage import read_json


class AttentionLimit(ValueError):
    pass


def _bounded(records, maximum, name):
    values = list(records)
    if len(values) > maximum:
        raise AttentionLimit(f"local {name} exceeds {maximum} records")
    return values


def _packet(data):
    # Fail closed rather than silently omit assumptions or a necessary Fact.
    if len(json.dumps(data, ensure_ascii=False).encode()) > 256_000:
        raise AttentionLimit("local packet exceeds 256000 bytes")
    return data


def worker_packet(graph, route_id, attempt_history):
    if not any(f.kind == "PROOF" and f.route_id == route_id for f in graph.frontiers()):
        raise ValueError("Worker route is not a target-reachable proof frontier")
    route = graph.route(route_id)
    obligation = graph.obligation(route.target_obligation_id)
    history = _bounded(attempt_history, 3, "route attempts")
    if any((a["obligation_id"], a["route_id"]) != (obligation.obligation_id, route_id) for a in history):
        raise ValueError("unrelated route history in worker packet")
    facts = _bounded(graph.materialized_predecessors(route_id), 32, "predecessor Facts")
    return _packet(dict(obligation={**asdict(obligation), "statement": obligation.statement},
                        route=asdict(route), predecessor_facts=[asdict(f) for f in facts], attempt_history=history))


def strategist_packet(graph, obligation_id):
    if not any(f.kind == "STRUCTURAL" and f.obligation_id == obligation_id for f in graph.frontiers()):
        raise ValueError("obligation is not a target-reachable structural frontier")
    obligation = graph.obligation(obligation_id)
    if obligation.truth_state != "OPEN":
        raise ValueError("only OPEN obligations can be structural frontiers")
    routes = _bounded(graph.routes_for(obligation_id), 8, "direct routes")
    if any(graph.route_state(r.route_id) in ("READY", "WAITING") for r in routes):
        raise ValueError("obligation still has a viable route")
    prerequisites = _bounded(sorted({k for r in routes for k in r.prerequisite_obligation_ids}), 32, "direct prerequisites")
    children = [graph.obligation(k) for k in prerequisites]
    parent_consumers = []
    for parent in graph.obligations():
        for route in graph.routes_for(parent.obligation_id):
            if obligation_id in route.prerequisite_obligation_ids:
                parent_consumers.append(dict(obligation_id=parent.obligation_id, context=parent.context,
                    goal=parent.goal, route_id=route.route_id, relation="requires_current_obligation"))
    boundary_ids = {f for r in routes for f in r.support_fact_ids}
    boundary_ids.update(c.resolved_fact_id for c in children if c.truth_state == "DISCHARGED")
    facts = FactGraph(graph.root)
    boundary = []
    for key in _bounded(sorted(boundary_ids), 32, "boundary Facts"):
        closure = facts.supporting_closure(key)
        if any(f.problem_id != graph.problem_id for f in closure):
            raise ValueError("foreign local Fact")
        boundary.append(asdict(facts.get_fact(key)))
    failure_ids = _bounded(sorted({key for r in routes for key in r.exhaustion_attempt_ids}), 24, "failure attempts")
    attempts = [read_json(graph.root / "attempts" / (k + ".json")) for k in failure_ids]
    refutations = [asdict(RefutationStore(graph.root).get(c.refutation_id)) for c in children if c.truth_state == "REFUTED"]
    history = []
    for path in sorted((graph.root / "graph_patches").glob("*/approved.json")):
        record = read_json(path)
        patch = record["patch"]
        if patch["target_obligation_id"] == obligation_id:
            history.append(dict(patch_id=patch["patch_id"], operator=patch["operator"],
                                claims=[o["goal"] for o in patch["obligations"]]))
    return _packet(dict(obligation={**asdict(obligation), "statement": obligation.statement},
        routes=[{**asdict(r), "derived_state": graph.route_state(r.route_id)} for r in routes],
        prerequisites=[asdict(c) for c in children], parent_consumers=_bounded(parent_consumers, 16, "parent consumers"),
        failure_attempts=attempts, refutations=refutations, boundary_facts=boundary,
        refinement_history=_bounded(history, 8, "local refinement history")))
