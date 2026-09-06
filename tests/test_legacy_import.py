from research.legacy_import import LegacyScaffoldImporter
from research.scaffold import ProofScaffold, ScaffoldNode
from research.problem import ProblemSpec
from research.proof_graph import ProofGraph
import pytest


def test_import_is_one_time_isolated_and_preserves_existing_fact_bytes(tmp_path):
    from research.fact import Fact
    from research.graph import FactGraph
    source, destination = tmp_path / "legacy", tmp_path / "v3"
    source.mkdir()
    fact = FactGraph(source).add_fact(Fact.create(problem_id="p", statement="helper", proof="inline", author="fixture"))
    scaffold = ProofScaffold.create(source / "scaffold.json", problem=ProblemSpec("p", "target"), target_node_id="target",
        nodes=(ScaffoldNode("helper", "helper"),
               ScaffoldNode("target", "target", depends_on=("helper",))))
    scaffold.resolve("helper", fact.fact_id, FactGraph(source))
    original = {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()}
    result = LegacyScaffoldImporter(source).import_to(destination)
    graph = ProofGraph(destination)
    assert len(graph.obligations()) == 2
    assert graph.obligation(result["obligation_ids"]["helper"]).resolved_fact_id == fact.fact_id
    assert [(f.kind, f.obligation_id) for f in graph.frontiers()] == [("PROOF", graph.target_obligation_id)]
    assert {p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()} == original
    assert (destination / "facts" / (fact.fact_id + ".md")).read_bytes() == original[next(p for p in original if p.parts[0] == "facts")]
    assert not (destination / "scaffold.json").exists()
    with pytest.raises(ValueError, match="fresh isolated"):
        LegacyScaffoldImporter(source).import_to(destination)


def test_import_rejects_a_copy_that_does_not_match_frozen_source(tmp_path, monkeypatch):
    import research.legacy_import as importer
    source, destination = tmp_path / "legacy", tmp_path / "v3"
    source.mkdir()
    ProofScaffold.create(source / "scaffold.json", problem=ProblemSpec("p", "target"), target_node_id="target",
                        nodes=(ScaffoldNode("target", "target"),))
    copy = importer.shutil.copytree
    def altered_copy(src, dst, *args, **kwargs):
        result = copy(src, dst, *args, **kwargs)
        (dst / "unexpected.txt").write_text("source changed during copy")
        return result
    monkeypatch.setattr(importer.shutil, "copytree", altered_copy)
    with pytest.raises(ValueError, match="fingerprint"):
        LegacyScaffoldImporter(source).import_to(destination)
    assert not (destination / "proof_graph.json").exists()


@pytest.mark.parametrize("operator,corruption", [("SPLIT", None), ("INSERT_CUT_SET", None),
    ("ADD_ALTERNATIVE_ROUTE", None), ("INSERT_CUT_SET", "missing"), ("INSERT_CUT_SET", "post_image"),
    ("INSERT_CUT_SET", "audit"), ("INSERT_CUT_SET", "wrapper"),
    ("SPLIT", "completed"), ("INSERT_CUT_SET", "completed"), ("ADD_ALTERNATIVE_ROUTE", "completed")])
def test_import_reconstructs_routes_from_actual_legacy_refinement_evidence(tmp_path, operator, corruption):
    import json
    from test_local_refinement import make_workspace, StubBuilder
    from research.agents import StructuralAuditor
    from research.local_refinement import parse_builder_output, parse_cut_set_output, parse_alternative_route_output, run_local_redecomposition
    from research.proof_patch import KINDS
    source = tmp_path / "legacy"
    make_workspace(source)
    raw = json.dumps(dict(outcome=operator, obstruction="gap", expected_effect="local steps",
        why_current_route_is_exhausted="bounded attempts failed", missing_context="", new_nodes=[
            dict(node_id="a", goal="First local claim", depends_on=[], premise_fact_ids=[]),
            dict(node_id="b", goal="Second local claim", depends_on=["a"], premise_fact_ids=[])]))
    parser = {"SPLIT": parse_builder_output, "INSERT_CUT_SET": parse_cut_set_output,
              "ADD_ALTERNATIVE_ROUTE": parse_alternative_route_output}[operator]
    class AuditorCodex:
        def invoke(self, *, prompt, schema, label):
            return dict(verdict="PASS", reasons=["fixture structural check"],
                        checks={k: True for k in schema["properties"]["checks"]["required"]})
    result = run_local_redecomposition(source, problem_id="p", blocked_node_id="mid", operation=operator.lower(),
        builder=StubBuilder(parser(raw, blocked_node_id="mid")), auditor=StructuralAuditor(AuditorCodex(), operation=operator.lower()))
    assert result.outcome == "APPLIED"
    destination = tmp_path / "v3"
    if corruption == "completed":
        from test_local_refinement import GoalEchoWorker, RejectingVerifier
        from research.scaffold import solve_scaffold
        from research.obligation import ObligationRegistry
        from research.graph import FactGraph
        outcome = solve_scaffold(scaffold=ProofScaffold(source / "scaffold.json"),
            problem=ProblemSpec("p", "Target theorem T."), registry=ObligationRegistry(source / "obligations.json"),
            graph=FactGraph(source), author="fixture", worker=GoalEchoWorker(), verifier=RejectingVerifier())
        assert outcome.status == "SOLVED"
        original_facts = {p.name: p.read_bytes() for p in (source / "facts").glob("*.md")}
    elif corruption:
        from research.run_storage import read_json, write_json
        path = next((source / "local_refinements").glob("*.json"))
        if corruption == "missing":
            path.rename(path.with_suffix(".missing"))
        else:
            record = read_json(path)
            if corruption == "post_image":
                record["post_patch_nodes"][0]["goal"] = "unsupported rewrite"
            elif corruption == "wrapper":
                wrapper = next(n for n in record["post_patch_nodes"] if n["node_id"] == "mid__cut")
                wrapper["depends_on"] = ["a"]
                scaffold = read_json(source / "scaffold.json")
                next(n for n in scaffold["nodes"] if n["node_id"] == "mid__cut")["depends_on"] = ["a"]
                write_json(source / "scaffold.json", scaffold)
            else:
                record["auditor_raw"] = json.dumps(dict(verdict="REJECT", reasons=[], checks={}))
            write_json(path, record)
        with pytest.raises(ValueError, match="provenance|post-images"):
            LegacyScaffoldImporter(source).import_to(destination)
        assert not (destination / "proof_graph.json").exists()
        return
    imported = LegacyScaffoldImporter(source).import_to(destination)
    graph = ProofGraph(destination)
    if corruption == "completed":
        assert graph.obligation(graph.target_obligation_id).truth_state == "DISCHARGED"
        assert graph.supporting_closure()
        assert {p.name: p.read_bytes() for p in (destination / "facts").glob("*.md")} == original_facts
        return
    mid = imported["obligation_ids"]["mid"]
    assert len(graph.obligations()) == 5
    routes = graph.routes_for(mid)
    assert len(routes) == 2
    new = next(r for r in routes if r.kind == KINDS[operator])
    assert set(new.prerequisite_obligation_ids) == {imported["obligation_ids"]["a"], imported["obligation_ids"]["b"]}
    assert any(graph.route_state(r.route_id) == "EXHAUSTED" for r in routes)
    assert graph.routes_for(graph.target_obligation_id)[0].prerequisite_obligation_ids == (mid,)
    from research.refutation import Refutation, RefutationStore
    from research.local_attention import strategist_packet
    child = graph.obligation(imported["obligation_ids"]["a"])
    evidence = dict(accepted=True, assumptions_satisfied=True, conclusion_falsified=True,
                    closed_book_clean=True, reason="fixture counterexample")
    refutation = Refutation.create(child, "fixture", evidence, {"verifier_call": "independent fixture"})
    RefutationStore(destination).admit(refutation)
    graph.resolve_refutation(child.obligation_id, refutation.refutation_id)
    packet = strategist_packet(graph, mid)
    assert len(packet["refinement_history"]) == 1
    assert packet["refinement_history"][0]["operator"] == operator
    assert packet["refinement_history"][0]["claims"] == ["First local claim", "Second local claim"]


@pytest.mark.parametrize("remaining", [1, 3])
def test_imported_partial_attempt_history_limits_and_informs_continuation(tmp_path, remaining):
    from test_local_refinement import make_workspace
    from test_proof_execution import ScriptedCodex
    from research.agents import ResearchWorker
    from research.closed_book import ClosedBookVerifier
    from research.node_solver import NodeSolver, NodeSolverConfig
    source, destination = tmp_path / "legacy", tmp_path / "v3"
    make_workspace(source)
    imported = LegacyScaffoldImporter(source).import_to(destination)
    no_result = dict(kind="NO_RESULT", reason="same gap", statement="", proof="", predecessors=[], counterexample="")
    backend = ScriptedCodex([("research_worker", no_result)] * min(remaining, 2))
    solver = NodeSolver(worker=ResearchWorker(backend), verifier=ClosedBookVerifier(backend), config=NodeSolverConfig(remaining))
    result = solver.solve_route(graph=ProofGraph(destination), route_id=imported["route_ids"]["mid"], author="fixture")
    assert result.status == "BLOCKED"
    assert "scripted verdict" in backend.calls[0][1]
    assert len(backend.calls) == min(remaining, 2)
    assert not backend.responses
