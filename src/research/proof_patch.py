"""Existing mathematical operators compiled into the canonical route graph."""
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
import json

from .proof_graph import ProofGraph, ProofObligation, ProofRoute, _identity
from .run_storage import read_json, write_json


KINDS = {"SPLIT": "SPLIT", "INSERT_CUT_SET": "CUT", "ADD_ALTERNATIVE_ROUTE": "ALTERNATIVE"}


def structural_schema(operator):
    from .agents import _AUDIT_SCHEMA, _CUT_AUDIT_SCHEMA, _ALT_AUDIT_SCHEMA
    return {"SPLIT": _AUDIT_SCHEMA, "INSERT_CUT_SET": _CUT_AUDIT_SCHEMA,
            "ADD_ALTERNATIVE_ROUTE": _ALT_AUDIT_SCHEMA}[operator]


def graph_digest(graph):
    return sha256(json.dumps(read_json(graph.path), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class GraphPatch:
    patch_id: str
    base_digest: str
    target_obligation_id: str
    operator: str
    obligations: tuple
    routes: tuple

    @classmethod
    def compile(cls, graph, target_id, operator, new_nodes, *, boundary_fact_ids, support_fact_ids=()):
        target = graph.obligation(target_id)
        if operator not in KINDS or target.truth_state != "OPEN":
            raise ValueError("operator needs an OPEN mathematical target")
        if not 1 <= len(new_nodes) <= 4:
            raise ValueError("compile one to four local claim sketches")
        aliases = [n["node_id"] for n in new_nodes]
        if len(set(aliases)) != len(aliases) or any(not isinstance(k, str) or not k for k in aliases):
            raise ValueError("patch aliases must be unique and nonempty")
        obligations = tuple(ProofObligation.create(graph.problem_id, target.context, n["goal"]) for n in new_nodes)
        mapping = dict(zip(aliases, (o.obligation_id for o in obligations)))
        routes = []
        consumed, support = set(), set(support_fact_ids)
        for node, obligation in zip(new_nodes, obligations):
            if set(node) != {"node_id", "goal", "depends_on", "premise_fact_ids"}:
                raise ValueError("patch cannot carry truth or runtime fields")
            if any(key not in mapping for key in node["depends_on"]):
                raise ValueError("dependencies must be patch sibling aliases")
            consumed.update(node["depends_on"])
            routes.append(ProofRoute.create(obligation.obligation_id,
                [mapping[key] for key in node["depends_on"]], node["premise_fact_ids"]))
        routes.append(ProofRoute.create(target_id, [mapping[key] for key in aliases if key not in consumed],
                                         support, kind=KINDS[operator]))
        patch = cls("", graph_digest(graph), target_id, operator, obligations, tuple(routes))
        patch_id = patch.identity()
        patch = replace(patch, patch_id=patch_id, routes=tuple(replace(r, origin_patch_id=patch_id) for r in routes))
        patch.validate(graph, boundary_fact_ids=boundary_fact_ids)
        return patch

    def identity(self):
        data = asdict(self)
        data.pop("patch_id")
        for route in data["routes"]:
            route["origin_patch_id"] = None
        return _identity("patch-", data)

    @classmethod
    def from_dict(cls, data):
        return cls(data["patch_id"], data["base_digest"], data["target_obligation_id"], data["operator"],
                   tuple(ProofObligation(**o) for o in data["obligations"]),
                   tuple(ProofRoute(**{**r, **{k: tuple(r[k]) for k in (
                       "prerequisite_obligation_ids", "support_fact_ids", "exhaustion_attempt_ids")}}) for r in data["routes"]))

    def validate(self, graph, *, boundary_fact_ids):
        if self.patch_id != self.identity() or self.base_digest != graph_digest(graph):
            raise ValueError("patch identity or base state mismatch")
        target = graph.obligation(self.target_obligation_id)
        if target.truth_state != "OPEN" or self.operator not in KINDS:
            raise ValueError("invalid patch target/operator")
        keys = {o.obligation_id for o in self.obligations}
        if len(keys) != len(self.obligations) or target.obligation_id in keys:
            raise ValueError("patch duplicates a goal or restates its own target")
        if any(o.truth_state != "OPEN" or o.context != target.context for o in self.obligations):
            raise ValueError("patch cannot change truth or assumptions")
        parents = [r for r in self.routes if r.target_obligation_id == target.obligation_id]
        if len(parents) != 1 or parents[0].kind != KINDS[self.operator]:
            raise ValueError("patch needs one route for its selected operator")
        for route in self.routes:
            if (route.target_obligation_id not in keys | {target.obligation_id}
                    or not set(route.prerequisite_obligation_ids) <= keys
                    or not set(route.support_fact_ids) <= set(boundary_fact_ids)
                    or route.lifecycle != "OPEN" or route.origin_patch_id != self.patch_id):
                raise ValueError("patch leaves its local region or changes route lifecycle")
        data = deepcopy(read_json(graph.path))
        for item in self.obligations:
            data["obligations"].setdefault(item.obligation_id, asdict(item))
        for item in self.routes:
            if item.route_id in data["routes"]:
                if item.target_obligation_id == target.obligation_id:
                    raise ValueError("patch repeats an existing target route")
                continue  # A shared helper keeps its prior route and lifecycle.
            data["routes"][item.route_id] = asdict(item)
        ProofGraph._validate(data)
        ProofGraph._check_evidence(graph.root, data)
        return data

    def apply(self, graph, approval, *, boundary_fact_ids, event=None):
        """Approved evidence -> atomic graph -> completion journal, under the run lock."""
        event = event or (lambda *args, **kwargs: None)
        audit = approval.get("audit", {})
        checks = structural_schema(self.operator)["properties"]["checks"]["required"]
        if (approval.get("patch_id") != self.patch_id or self.identity() != self.patch_id
                or audit.get("verdict") != "PASS"
                or any(audit.get("checks", {}).get(k) is not True for k in checks)):
            raise ValueError("patch needs a bound independent Structural PASS with every check")
        directory = graph.root / "graph_patches" / self.patch_id
        record = json.loads(json.dumps(dict(patch=asdict(self), approval=approval,
                                           boundary_fact_ids=sorted(set(boundary_fact_ids)))))
        approved = directory / "approved.json"
        if approved.exists() and read_json(approved) != record:
            raise ValueError("cannot overwrite approved patch evidence")
        data = read_json(graph.path)
        if self.patch_id not in data["applied_patches"]:
            data = self.validate(graph, boundary_fact_ids=boundary_fact_ids)
            if not approved.exists():
                write_json(approved, record)
            event("patch_approved", patch_id=self.patch_id)
            data["applied_patches"][self.patch_id] = {"target_obligation_id": self.target_obligation_id,
                                                      "operator": self.operator}
            graph._save(data)
            event("patch_applied", patch_id=self.patch_id)
        elif not approved.exists():
            raise ValueError("applied patch is missing its prior approval evidence")
        completion = directory / "completion.json"
        if not completion.exists():
            write_json(completion, dict(patch_id=self.patch_id, applied=True))
        event("patch_completed", patch_id=self.patch_id)
