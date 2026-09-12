"""Shared conditional proof interfaces over the existing Fact admission seam."""
from dataclasses import asdict
import json
import pytest

from research.continuous_network import ContinuousNetwork
from research.fact import Fact
from research.graph import FactGraph
from research.refutation import Refutation, RefutationStore


def accept(network, goal, *, context="", requirements=None, predecessors=(), visible=(), proof=None):
    candidate = {"kind": "FACT" if requirements is None else "SUPPORT", "goal": goal,
                 "context": context, "proof": proof or "A complete deterministic test proof.",
                 "predecessors": list(predecessors)}
    if requirements is not None:
        candidate["requirements"] = [{"goal": item, "context": context} for item in requirements]
    prepared, descriptor = network.prepare_candidate(candidate, visible)
    fact = Fact.create(problem_id=network.problem_id, author="deterministic-verifier",
                       **asdict(prepared))
    FactGraph(network.root).add_fact(fact)  # deterministic accepted oracle, never a real model
    return network.accept_verified(descriptor, fact.fact_id), fact


def test_and_certificate_waits_for_every_condition_then_only_schedules_composition(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "arithmetic", "x = 3")
    support, bridge = accept(network, "x = 3", requirements=["x = y + 1", "y = 2"])
    assert bridge.statement == ('The conjunction of these statements ["x = y + 1", "y = 2"] '
                                'implies the statement "x = 3".')
    assert network.truth(network.target_id) == "OPEN"
    assert network.ready_supports() == ()
    _, first = accept(network, "x = y + 1")
    assert network.ready_supports() == ()
    _, second = accept(network, "y = 2")
    reopened = ContinuousNetwork(tmp_path)
    assert [s["support_id"] for s in reopened.ready_supports()] == [support["support_id"]]
    materials = reopened.support_materials(support["support_id"])
    assert {f.fact_id for f in materials["facts"]} == {bridge.fact_id, first.fact_id, second.fact_id}
    assert reopened.truth(network.target_id) == "OPEN"


@pytest.mark.parametrize("bad_material", ["unbound", "other_scope", "revoked"])
def test_visible_predecessors_are_accepted_network_facts_in_the_exact_scope(tmp_path, bad_material):
    network = ContinuousNetwork.create(tmp_path, "scopes", "x > 0", "x is real")
    if bad_material == "unbound":
        fact = Fact.create(problem_id="scopes", author="oracle", statement="Unregistered material", proof="Proof.")
        FactGraph(tmp_path).add_fact(fact)
    else:
        context = "x is complex" if bad_material == "other_scope" else "x is real"
        _, fact = accept(network, "x = 1", context=context)
        if bad_material == "revoked":
            FactGraph(tmp_path).revoke(fact.fact_id, "independent invalidation")
    candidate = {"kind": "FACT", "goal": "x > 0", "context": "x is real",
                 "proof": "Use the supplied identity.", "predecessors": [fact.fact_id]}
    with pytest.raises(ValueError, match="scope|accepted|revoked"):
        network.prepare_candidate(candidate, [fact.fact_id])


@pytest.mark.parametrize("corruption", ["binding", "support_edge", "missing_bridge", "refutation"])
def test_reopen_rejects_corrupt_truth_or_conditional_interfaces(tmp_path, corruption):
    network = ContinuousNetwork.create(tmp_path, "bindings", "x = 2")
    support, _ = accept(network, "x = 2", requirements=["x = y", "y = 2"])
    first, fact = accept(network, "x = y")
    path = tmp_path / "proof_graph.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if corruption == "binding":
        data["fact_bindings"][network.target_id] = [fact.fact_id]
    elif corruption == "support_edge":
        data["supports"][support["support_id"]]["requirement_claim_ids"] = [first["claim_id"]]
    elif corruption == "missing_bridge":
        data["supports"][support["support_id"]]["bridge_fact_id"] = "0123456789abcdef"
    else:
        data["refutations"][network.target_id] = "ref-doesnotexist"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises((ValueError, FileNotFoundError)):
        ContinuousNetwork(tmp_path)


def test_verified_refutation_invalidates_only_its_support_and_cannot_coexist_with_fact(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "refutation", "T")
    bad, _ = accept(network, "T", requirements=["F"])
    good, _ = accept(network, "T", requirements=["H"])
    false_claim = network.claim(bad["requirement_claim_ids"][0])
    record = Refutation.create(false_claim, "An explicit counterexample.",
        {"accepted": True, "assumptions_satisfied": True, "conclusion_falsified": True,
         "closed_book_clean": True, "reason": "The counterexample establishes falsity."},
        {"verifier_call": "deterministic-independent-call"})
    RefutationStore(tmp_path).admit(record)
    network.bind_refutation(false_claim.obligation_id, record.refutation_id)
    assert network.truth(false_claim.obligation_id) == "REFUTED"
    assert network.truth(network.target_id) == "OPEN"
    accept(network, "H")
    assert [s["support_id"] for s in network.ready_supports()] == [good["support_id"]]
    with pytest.raises(ValueError, match="refuted|conflict"):
        accept(network, "F")
    assert ContinuousNetwork(tmp_path).truth(false_claim.obligation_id) == "REFUTED"


def test_or_alternatives_never_merge_requirements_and_share_one_accepted_claim(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "alternatives", "T")
    left, _ = accept(network, "T", requirements=["A", "B"])
    right, _ = accept(network, "T", requirements=["A"])
    another, _ = accept(network, "U", requirements=["A"])
    _, shared = accept(network, "A")
    ready = {s["support_id"] for s in network.ready_supports()}
    assert ready == {right["support_id"], another["support_id"]}
    assert left["support_id"] not in ready
    assert network.truth(network.target_id) == "OPEN"
    for support_id in ready:
        materials = network.support_materials(support_id)
        assert shared.fact_id in {f.fact_id for f in materials["facts"]}


def test_waiting_search_cycle_cannot_bootstrap_verified_truth(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "cycle", "A")
    first, _ = accept(network, "A", requirements=["B"])
    second, _ = accept(network, "B", requirements=["A"])
    network = ContinuousNetwork(tmp_path)
    assert network.ready_supports() == ()
    assert network.truth(first["conclusion_claim_id"]) == "OPEN"
    assert network.truth(second["conclusion_claim_id"]) == "OPEN"
    with pytest.raises(ValueError, match="no accepted"):
        network.export()


def test_homonymous_claim_in_other_scope_does_not_discharge_requirement(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "scopes", "T", "x is real")
    support, _ = accept(network, "T", context="x is real", requirements=["H"])
    accept(network, "H", context="x is complex")
    assert network.ready_supports() == ()
    assert network.truth(support["requirement_claim_ids"][0]) == "OPEN"


def test_composition_closure_contains_bridge_and_used_facts_but_not_visible_unused_material(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "lineage", "T")
    support, bridge = accept(network, "T", requirements=["H"])
    _, child = accept(network, "H")
    _, unused = accept(network, "Unrelated but visible fact")
    materials = network.support_materials(support["support_id"])
    used = [f.fact_id for f in materials["facts"]]
    _, conclusion = accept(network, "T", predecessors=used, visible=[*used, unused.fact_id],
                           proof="Apply the conditional certificate to H.")
    assert set(conclusion.predecessors) == {bridge.fact_id, child.fact_id}
    assert {f["fact_id"] for f in network.export()["facts"]} == {
        bridge.fact_id, child.fact_id, conclusion.fact_id}
    assert network.truth(network.target_id) == "DISCHARGED"
    assert network.ready_supports() == ()


def test_nonvisible_predecessor_is_rejected_even_if_accepted_elsewhere(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "visibility", "T")
    _, hidden = accept(network, "H")
    with pytest.raises(ValueError, match="visible"):
        accept(network, "T", predecessors=[hidden.fact_id], visible=[])


def test_changed_conditional_edges_cannot_bind_an_accepted_certificate(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "certificate", "T")
    candidate, descriptor = network.prepare_candidate({"kind": "SUPPORT", "goal": "T", "context": "",
        "proof": "H suffices for T.", "predecessors": [], "requirements": [{"goal": "H", "context": ""}]}, [])
    fact = Fact.create(problem_id=network.problem_id, author="oracle", **asdict(candidate))
    FactGraph(tmp_path).add_fact(fact)
    descriptor["requirements"] = [{"goal": "Different H", "context": ""}]
    with pytest.raises(ValueError, match="interface"):
        network.accept_verified(descriptor, fact.fact_id)
    assert network.data["supports"] == {}
    assert network.truth(network.target_id) == "OPEN"


def test_multiple_proofs_survive_partial_revocation_and_bridge_revocation_removes_readiness(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "revocation", "T")
    support, bridge = accept(network, "T", requirements=["H"])
    first, proof1 = accept(network, "H", proof="First independent proof.")
    _, proof2 = accept(network, "H", proof="Second independent proof.")
    assert len(network.facts_for(first["claim_id"])) == 2
    FactGraph(tmp_path).revoke(proof1.fact_id, "First proof invalidated")
    network = ContinuousNetwork(tmp_path)
    assert [f.fact_id for f in network.facts_for(first["claim_id"])] == [proof2.fact_id]
    assert len(network.ready_supports()) == 1
    FactGraph(tmp_path).revoke(bridge.fact_id, "Conditional proof invalidated")
    network = ContinuousNetwork(tmp_path)
    assert network.ready_supports() == ()
    assert network.truth(network.target_id) == "OPEN"
    assert network.truth(first["claim_id"]) == "DISCHARGED"
