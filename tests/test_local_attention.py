import json
from research.proof_graph import ProofGraph, ProofObligation, ProofRoute
from research.local_attention import strategist_packet, worker_packet


def test_failed_route_packet_contains_only_direct_relations_and_verified_boundary(tmp_path):
    from research.fact import Fact
    from research.graph import FactGraph
    from research.refutation import Refutation, RefutationStore
    target, local, false, entropy, unrelated = [ProofObligation.create("p", "", g) for g in (
        "target", "local inverse", "false helper", "entropy helper", "UNRELATED_SENTINEL")]
    root_route = ProofRoute.create(target.obligation_id, (local.obligation_id,))
    bad_route = ProofRoute.create(local.obligation_id, (false.obligation_id, entropy.obligation_id))
    entropy_route = ProofRoute.create(entropy.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, obligations=(local, false, entropy, unrelated),
                              routes=(root_route, bad_route, entropy_route))
    fact = FactGraph(tmp_path).add_fact(Fact.create(problem_id="p", statement=entropy.statement, proof="inline", author="fixture"))
    FactGraph(tmp_path).add_fact(Fact.create(problem_id="p", statement="UNRELATED_FACT", proof="SECRET_PROOF", author="fixture"))
    graph.resolve_fact(entropy_route.route_id, fact.fact_id)
    refutation = Refutation.create(false, "counterexample", dict(accepted=True, assumptions_satisfied=True,
        conclusion_falsified=True, closed_book_clean=True, reason="checked"), {"verifier_call": "fixture-verifier"})
    RefutationStore(tmp_path).admit(refutation)
    graph.resolve_refutation(false.obligation_id, refutation.refutation_id)
    assert [(f.kind, f.obligation_id) for f in graph.frontiers()] == [("STRUCTURAL", local.obligation_id)]
    packet = strategist_packet(graph, graph.frontiers()[0].obligation_id)
    assert packet["obligation"]["goal"] == "local inverse"
    assert [f["fact_id"] for f in packet["boundary_facts"]] == [fact.fact_id]
    assert packet["refutations"][0]["counterexample"] == "counterexample"
    assert packet["parent_consumers"][0]["goal"] == "target"
    assert "UNRELATED" not in json.dumps(packet)
    assert "SECRET_PROOF" not in json.dumps(packet)


def test_packet_limit_and_unrelated_worker_history_fail_closed(tmp_path):
    import pytest
    from research.local_attention import AttentionLimit
    target = ProofObligation.create("p", "", "target")
    direct = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(direct,))
    with pytest.raises(ValueError, match="unrelated"):
        worker_packet(graph, direct.route_id, [dict(obligation_id="other", route_id="other")])
    facts = [dict(obligation_id=target.obligation_id, route_id=direct.route_id)] * 4
    with pytest.raises(AttentionLimit):
        worker_packet(graph, direct.route_id, facts)


def test_current_strategist_uses_v3_local_packet_and_existing_operator_schema(tmp_path):
    from research.refinement.sketch import StrategySketcher
    from test_proof_execution import ScriptedCodex
    target = ProofObligation.create("p", "", "target")
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target)
    codex = ScriptedCodex([("strategy_sketcher", dict(operator="DECLINE", obstruction="gap", evidence=[],
        mathematical_idea="", why_this_reduces_difficulty="", why_current_route_is_exhausted="",
        decline_reason="no reliable repair", candidate_claims=[]))])
    sketch = StrategySketcher(codex).strategize_local(strategist_packet(graph, target.obligation_id))
    assert sketch.operator == "DECLINE"
    assert "target" in codex.calls[0][1]
