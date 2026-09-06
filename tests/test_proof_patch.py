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
    assert parent_route.prerequisite_obligation_ids == (patch.obligations[1].obligation_id,)
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
