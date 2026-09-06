import pytest
from research.proof_graph import ProofGraph, ProofObligation, ProofRoute
from research.proof_patch import GraphPatch


@pytest.mark.parametrize("operator,kind", [("SPLIT", "SPLIT"), ("INSERT_CUT_SET", "CUT"),
                                           ("ADD_ALTERNATIVE_ROUTE", "ALTERNATIVE")])
def test_existing_operators_compile_to_routes_on_the_same_target(tmp_path, operator, kind):
    target = ProofObligation.create("p", "x=2", "x+x=4")
    old = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(old,))
    nodes = [{"node_id": "a", "goal": "x=1+1", "depends_on": [], "premise_fact_ids": []},
             {"node_id": "b", "goal": "2*x=4", "depends_on": ["a"], "premise_fact_ids": []}]
    patch = GraphPatch.compile(graph, target.obligation_id, operator, nodes, boundary_fact_ids=())
    patch.validate(graph, boundary_fact_ids=())
    assert [o.goal for o in patch.obligations] == ["x=1+1", "2*x=4"]
    parent_route = next(r for r in patch.routes if r.target_obligation_id == target.obligation_id)
    assert parent_route.kind == kind
    assert set(parent_route.prerequisite_obligation_ids) == {o.obligation_id for o in patch.obligations}
    assert all(o.context == target.context and o.truth_state == "OPEN" for o in patch.obligations)
    assert len(graph.obligations()) == 1  # Compilation is read-only.
    assert not (tmp_path / "scaffold.json").exists()


def test_approved_patch_is_atomic_idempotent_and_never_admits_truth(tmp_path):
    from research.proof_patch import structural_schema
    from research.run_storage import read_json
    target = ProofObligation.create("p", "", "target")
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target)
    patch = GraphPatch.compile(graph, target.obligation_id, "SPLIT", [
        dict(node_id="a", goal="helper", depends_on=[], premise_fact_ids=[])], boundary_fact_ids=())
    approval = dict(patch_id=patch.patch_id, audit=dict(verdict="PASS", reasons=["coherent"],
        checks={key: True for key in structural_schema("SPLIT")["properties"]["checks"]["required"]}))
    class Crash(BaseException):
        pass
    def interrupt(name, **details):
        if name == "patch_applied":
            raise Crash()
    with pytest.raises(Crash):
        patch.apply(graph, approval, boundary_fact_ids=(), event=interrupt)
    frozen = (tmp_path / "proof_graph.json").read_bytes()
    graph = ProofGraph(tmp_path)
    patch.apply(graph, approval, boundary_fact_ids=())
    assert frozen == (tmp_path / "proof_graph.json").read_bytes()
    assert len(graph.obligations()) == 2
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert not list((tmp_path / "facts").glob("*.md"))
    assert read_json(tmp_path / "graph_patches" / patch.patch_id / "completion.json")["applied"] is True


def test_route_can_reuse_a_shared_obligation_without_resetting_its_route(tmp_path):
    target = ProofObligation.create("p", "", "target")
    helper = ProofObligation.create("p", "", "helper")
    direct = ProofRoute.create(helper.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, obligations=(helper,), routes=(direct,))
    patch = GraphPatch.compile(graph, target.obligation_id, "INSERT_CUT_SET", [
        dict(node_id="shared", goal="helper", depends_on=[], premise_fact_ids=[])], boundary_fact_ids=())
    proposed = patch.validate(graph, boundary_fact_ids=())
    assert len(proposed["obligations"]) == 2
    assert proposed["routes"][direct.route_id]["origin_patch_id"] is None


@pytest.mark.parametrize("audit_verdicts", [("PASS",), ("REVISE", "PASS"), ("REVISE", "REVISE")])
def test_two_stage_roles_compile_a_boundary_supported_route_without_truth_admission(tmp_path, audit_verdicts):
    from research.refinement.route_driver import run_route_refinement
    from research.refinement.sketch import parse_sketch_output
    from research.local_attention import strategist_packet
    from research.proof_patch import structural_schema
    from research.fact import Fact
    from research.graph import FactGraph
    from research.run_storage import write_json
    from test_proof_execution import ScriptedCodex
    import json
    target = ProofObligation.create("p", "", "target")
    fact = FactGraph(tmp_path).add_fact(Fact.create(problem_id="p", statement="support", proof="inline", author="fixture"))
    old = ProofRoute.create(target.obligation_id, support_fact_ids=(fact.fact_id,))
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(old,))
    write_json(tmp_path / "attempts/attempt-000001.json", dict(attempt_id="attempt-000001",
        obligation_id=target.obligation_id, route_id=old.route_id, outcome="NO_RESULT", reason="gap"))
    graph.exhaust_route(old.route_id, ("attempt-000001",), "gap")
    sketch = parse_sketch_output(json.dumps(dict(operator="ADD_ALTERNATIVE_ROUTE", obstruction="gap", evidence=[],
        mathematical_idea="new mechanism", why_this_reduces_difficulty="local helper", why_current_route_is_exhausted="gap",
        decline_reason="", candidate_claims=["helper"])), blocked_node_id=target.obligation_id)
    codex = ScriptedCodex([
        ("n2s_sketch_audit", dict(strategy_class="PLAUSIBLE_STRATEGY", difficulty_reduction="UNCLEAR", strategy_family="test", reasons=[])),
        ("boundary_aware_patch_builder", dict(compilation_decline=False, decline_reason="", support_fact_ids=[fact.fact_id],
            new_nodes=[dict(node_id="a", goal="helper", depends_on=[], premise_fact_ids=[])])),
        ("n2t_fidelity_audit", dict(strategy_fidelity="FAITHFUL", operator_check="OPERATOR_PRESERVED", claim_fidelity=[], reasons=[])),
        ("structural_auditor", dict(verdict=audit_verdicts[0], reasons=["clarify helper"], checks={k: True for k in
            structural_schema(sketch.operator)["properties"]["checks"]["required"]})),
    ])
    if len(audit_verdicts) == 2:
        codex.responses.extend([
            ("mathematical_reviser", dict(repairable=True, compilation_decline=False, decline_reason="", support_fact_ids=[fact.fact_id],
                new_nodes=[dict(node_id="a", goal="precise helper", depends_on=[], premise_fact_ids=[])])),
            ("structural_auditor", dict(verdict=audit_verdicts[1], reasons=["checked"], checks={k: True for k in
                structural_schema(sketch.operator)["properties"]["checks"]["required"]})),
        ])
    packet = strategist_packet(graph, target.obligation_id)
    result = run_route_refinement(graph, packet, sketch,
                                  invoker_for=lambda role: codex, directory=tmp_path / "step/patch")
    accepted = audit_verdicts[-1] == "PASS"
    assert result["outcome"] == ("PATCH_APPLIED" if accepted else "REVISION_FAILED")
    graph = ProofGraph(tmp_path)
    assert len(graph.routes_for(target.obligation_id)) == (2 if accepted else 1)
    if accepted:
        new = next(r for r in graph.routes_for(target.obligation_id) if r.route_id != old.route_id)
        assert new.support_fact_ids == (fact.fact_id,)
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert len(FactGraph(tmp_path).list_facts()) == 1
    assert not codex.responses
    from dataclasses import replace
    with pytest.raises(ValueError, match="inputs"):
        run_route_refinement(graph, packet, replace(sketch, mathematical_idea="a different strategy"),
                             invoker_for=lambda role: codex, directory=tmp_path / "step/patch")


def test_refuting_an_early_cut_invalidates_its_whole_parent_route(tmp_path):
    from research.proof_patch import structural_schema
    from research.refutation import Refutation, RefutationStore
    target = ProofObligation.create("p", "", "inverse target")
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target)
    patch = GraphPatch.compile(graph, target.obligation_id, "INSERT_CUT_SET", [
        dict(node_id="false", goal="false major arc", depends_on=[], premise_fact_ids=[]),
        dict(node_id="later", goal="later mechanism", depends_on=["false"], premise_fact_ids=[])], boundary_fact_ids=())
    patch.apply(graph, dict(patch_id=patch.patch_id, audit=dict(verdict="PASS", reasons=["fixture"], checks={k: True for k in
        structural_schema(patch.operator)["properties"]["checks"]["required"]})), boundary_fact_ids=())
    child = patch.obligations[0]
    refutation = Refutation.create(child, "n=1", dict(accepted=True, assumptions_satisfied=True,
        conclusion_falsified=True, closed_book_clean=True, reason="checked"), {"verifier_call": "fixture"})
    RefutationStore(tmp_path).admit(refutation)
    graph.resolve_refutation(child.obligation_id, refutation.refutation_id)
    assert [(f.kind, f.obligation_id) for f in graph.frontiers()] == [("STRUCTURAL", target.obligation_id)]
    with pytest.raises(ValueError, match="resolved"):
        GraphPatch.compile(graph, target.obligation_id, "ADD_ALTERNATIVE_ROUTE", [
            dict(node_id="same", goal=child.goal, depends_on=[], premise_fact_ids=[])], boundary_fact_ids=())
