"""Two-stage compilation and independent gates for the first-class route graph."""
from dataclasses import asdict
import json
import subprocess

from ..agents import StructuralAuditor
from ..proof_patch import GraphPatch, graph_digest
from ..local_attention import strategist_packet
from ..run_storage import read_json, write_json
from .boundary_builder import BoundaryAwarePatchBuilder
from .patch_builder import PATCH_SCHEMA, FidelityAuditor, parse_patch_build_output
from .sketch import SketchAuditor
from .reviser import MathematicalReviser


ROUTE_BUILD_SCHEMA = {**PATCH_SCHEMA,
    "properties": {**PATCH_SCHEMA["properties"], "support_fact_ids": {"type": "array", "items": {"type": "string"}}},
    "required": [*PATCH_SCHEMA["required"], "support_fact_ids"]}


def route_build_prompt(packet, sketch):
    return """You are the BoundaryAware Patch Builder. Compile this frozen mathematical
Strategy Sketch and its selected operator; do not re-diagnose or change strategy.
Refine its 1-4 candidate claims into self-contained propositions with explicit
domains, quantifiers and definitions. All inherit exactly the parent's context.
Return new_nodes with local aliases, goals, sibling depends_on, and premise_fact_ids.
The compiler makes each child one obligation plus a route requiring its siblings;
ALL new claims jointly become prerequisites of a new route to the SAME target.
Use top-level support_fact_ids for accepted boundary Facts needed directly by
that target route; child premise_fact_ids are support of that child's route.
Only boundary_facts IDs may be cited, only where mathematically needed. Do not
inline an accepted Fact as a replacement for its lineage. No truth fields or
operator field: the operator is locked externally. Decline if faithful local
compilation is impossible. CLOSED BOOK; no external authority or retrieval.
""" + json.dumps(dict(local=packet, strategy=asdict(sketch)), ensure_ascii=False, indent=2)


def parse_route_build(response):
    if set(response) != set(ROUTE_BUILD_SCHEMA["properties"]):
        raise ValueError("unexpected route compilation fields")
    parse_patch_build_output(json.dumps(response, ensure_ascii=False))
    if not isinstance(response["support_fact_ids"], list) or any(not isinstance(k, str) for k in response["support_fact_ids"]):
        raise ValueError("route support must be Fact IDs")
    return response


def run_route_refinement(graph, packet, sketch, *, invoker_for, directory, event=None):
    """Durable stage artifacts retain a frozen packet and one compilation decision."""
    inputs = json.loads(json.dumps(dict(packet=packet, sketch=asdict(sketch)), ensure_ascii=False))
    manifest_path = directory / "inputs.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        if inputs != manifest["inputs"]:
            raise ValueError("refinement inputs changed across replay")
        if graph_digest(graph) != manifest["base_digest"]:
            applied = read_json(graph.path)["applied_patches"]
            completed_patch = False
            for path in (directory / "v1.json", directory / "v2.json"):
                if path.exists():
                    previous = GraphPatch.from_dict(read_json(path))
                    completed_patch |= (previous.patch_id == previous.identity() and previous.patch_id in applied
                                        and previous.base_digest == manifest["base_digest"])
            if not completed_patch:
                raise ValueError("refinement graph inputs changed before apply")
    else:
        if list(directory.glob("*.json")):
            raise ValueError("refinement outputs lack frozen inputs")
        canonical = strategist_packet(graph, packet["obligation"]["obligation_id"])
        if inputs["packet"] != json.loads(json.dumps(canonical)):
            raise ValueError("refinement inputs are not the canonical local packet")
        write_json(manifest_path, dict(inputs=inputs, base_digest=graph_digest(graph)))

    def saved(name, call):
        path = directory / (name + ".json")
        if not path.exists():
            write_json(path, call())
        return read_json(path)

    gate = saved("gate", lambda: SketchAuditor(invoker_for("gate")).audit(
        dict(local=packet, strategy=asdict(sketch))))
    if gate.get("strategy_class") not in ("USEFUL_STRATEGY", "PLAUSIBLE_STRATEGY"):
        return dict(outcome="STRATEGY_GATE_REJECT")
    try:
        build = saved("build", lambda: BoundaryAwarePatchBuilder(invoker_for("builder")).compile_local(packet, sketch))
    except subprocess.TimeoutExpired:
        return dict(outcome="PATCH_BUILDER_TIMEOUT")
    if build["compilation_decline"]:
        return dict(outcome="PATCH_COMPILATION_INVALID", reason=build["decline_reason"])
    fidelity = saved("fidelity", lambda: FidelityAuditor(invoker_for("fidelity")).audit(
        sketch, tuple(build["new_nodes"]), sketch.operator))
    if (fidelity.get("strategy_fidelity") not in ("FAITHFUL", "PARTIALLY_FAITHFUL")
            or fidelity.get("operator_check") != "OPERATOR_PRESERVED"):
        return dict(outcome="PATCH_COMPILATION_INVALID")
    boundary = [f["fact_id"] for f in packet["boundary_facts"]]
    try:
        patch = GraphPatch.from_dict(saved("v1", lambda: asdict(GraphPatch.compile(graph,
            packet["obligation"]["obligation_id"], sketch.operator, build["new_nodes"],
            boundary_fact_ids=boundary, support_fact_ids=build["support_fact_ids"]))))
    except ValueError as error:
        return dict(outcome="MECHANICAL_FAIL", reason=str(error))
    audit = saved("audit_v1", lambda: StructuralAuditor(invoker_for("structural-1")).audit_local(packet, patch, sketch))
    if audit.get("verdict") == "REVISE":
        revision = saved("revision", lambda: MathematicalReviser(invoker_for("reviser")).revise_local(
            packet, sketch, build, audit["reasons"]))
        if not revision["repairable"] or revision["compilation_decline"]:
            return dict(outcome="REVISION_FAILED")
        try:
            patch = GraphPatch.from_dict(saved("v2", lambda: asdict(GraphPatch.compile(graph,
                packet["obligation"]["obligation_id"], sketch.operator, revision["new_nodes"],
                boundary_fact_ids=boundary, support_fact_ids=revision["support_fact_ids"]))))
        except ValueError as error:
            return dict(outcome="REVISION_FAILED", reason=str(error))
        audit = saved("audit_v2", lambda: StructuralAuditor(invoker_for("structural-2")).audit_local(packet, patch, sketch))
        if audit.get("verdict") != "PASS":
            return dict(outcome="REVISION_FAILED")
    if audit.get("verdict") != "PASS":
        return dict(outcome="STRUCTURAL_AUDITOR_" + audit.get("verdict", "INVALID"))
    patch.apply(graph, dict(patch_id=patch.patch_id, audit=audit), boundary_fact_ids=boundary, event=event)
    return dict(outcome="PATCH_APPLIED", patch_id=patch.patch_id)
