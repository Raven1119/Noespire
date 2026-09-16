"""Revocation survives cached acceptance while retaining immutable proof history."""
from dataclasses import asdict
import json

import pytest

from research.continuous_network import ContinuousNetwork
from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.pipeline import VerificationResult, submit_candidate


def make_fact(statement, predecessors=()):
    return Fact.create(problem_id="revocation-test", author="deterministic-oracle",
                       statement=statement, proof="Frozen accepted test proof.",
                       predecessors=predecessors)


def bind(network, statement, predecessors=()):
    prepared, descriptor = network.prepare_candidate({
        "kind": "FACT", "goal": statement, "context": "", "requirements": [],
        "proof": "Frozen accepted test proof.", "predecessors": list(predecessors),
    }, predecessors)
    fact = Fact.create(problem_id=network.problem_id, author="deterministic-oracle",
                       **asdict(prepared))
    FactGraph(network.root).add_fact(fact)
    return network.accept_verified(descriptor, fact.fact_id), fact


def test_revoked_identity_cannot_be_readded(tmp_path):
    graph = FactGraph(tmp_path)
    fact = graph.add_fact(make_fact("A"))
    original = graph._path(fact.fact_id).read_bytes()
    graph.revoke(fact.fact_id, "Independent invalidation.")
    log = graph.revocation_log.read_bytes()

    # A fresh graph instance models recovery rather than relying on process state.
    with pytest.raises(ValueError, match="fact_revoked"):
        FactGraph(tmp_path).add_fact(fact)

    assert not graph._path(fact.fact_id).exists()
    assert (graph.revoked_dir / f"{fact.fact_id}.md").read_bytes() == original
    assert graph.revocation_log.read_bytes() == log


def test_transitive_revocation_preserves_proofs_and_reopens_bound_claims(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "revocation-test", "C")
    first, a = bind(network, "A")
    second, b = bind(network, "B", [a.fact_id])
    third, c = bind(network, "C", [b.fact_id])
    _, independent = bind(network, "Independent")
    graph = FactGraph(tmp_path)
    assert graph.descendants(a.fact_id) == [b.fact_id, c.fact_id]
    assert [f.fact_id for f in graph.supporting_closure(c.fact_id)] == [
        a.fact_id, b.fact_id, c.fact_id]
    original = {f.fact_id: graph._path(f.fact_id).read_bytes() for f in (a, b, c)}
    graph_history = network.path.read_bytes()

    assert graph.revoke(a.fact_id, "Accepted proof later invalidated.") == [
        a.fact_id, b.fact_id, c.fact_id]
    restored = ContinuousNetwork(tmp_path)
    assert network.path.read_bytes() == graph_history  # bindings remain historical evidence
    for admission, fact in ((first, a), (second, b), (third, c)):
        assert restored.truth(admission["claim_id"]) == "OPEN"
        assert restored.facts_for(admission["claim_id"]) == ()
        with pytest.raises(ValueError, match="revoked"):
            restored.visible_fact(fact.fact_id, "")
        with pytest.raises(KeyError):
            graph.supporting_closure(fact.fact_id)
        assert (graph.revoked_dir / f"{fact.fact_id}.md").read_bytes() == original[fact.fact_id]
    assert graph.get_fact(independent.fact_id) == independent
    records = [json.loads(line) for line in graph.revocation_log.read_text().splitlines()]
    assert [r["fact_id"] for r in records] == [a.fact_id, b.fact_id, c.fact_id]
    assert [r["revoked_as_dependent_of"] for r in records] == [None, a.fact_id, a.fact_id]
    replacement = make_fact("A new dependent", [a.fact_id])
    with pytest.raises(ValueError, match="predecessor_revoked"):
        graph.add_fact(replacement)


def test_cached_successful_verification_cannot_resurrect_fact(tmp_path):
    candidate = CandidateFact("A", "Frozen accepted test proof.", ())

    class CachedVerifier:
        def verify(self, problem, candidate, predecessors):
            return VerificationResult(True, "Original persisted verifier PASS.")

    arguments = dict(problem_id="revocation-test", problem="A", author="deterministic-oracle",
                     candidate=candidate, verifier=CachedVerifier())
    result = submit_candidate(graph=FactGraph(tmp_path), **arguments)
    graph = FactGraph(tmp_path)
    graph.revoke(result.fact.fact_id, "A later concrete counterexample.")
    revoked = (graph.revoked_dir / f"{result.fact.fact_id}.md").read_bytes()

    with pytest.raises(ValueError, match="fact_revoked"):
        submit_candidate(graph=FactGraph(tmp_path), **arguments)

    assert graph.list_facts() == []
    assert (graph.revoked_dir / f"{result.fact.fact_id}.md").read_bytes() == revoked


def test_revoked_tombstone_wins_over_a_duplicate_active_copy(tmp_path):
    graph = FactGraph(tmp_path)
    fact = graph.add_fact(make_fact("A"))
    original = graph._path(fact.fact_id).read_bytes()
    graph.revoke(fact.fact_id, "Invalidated before recovery.")
    # Simulate a corrupt/legacy recovery which has copied an active file back.
    graph._path(fact.fact_id).write_bytes(original)
    with pytest.raises(ValueError, match="fact_revoked"):
        graph.add_fact(fact)
    assert (graph.revoked_dir / f"{fact.fact_id}.md").read_bytes() == original


def test_corrupt_active_copy_cannot_override_tombstone_on_read(tmp_path):
    graph=FactGraph(tmp_path)
    fact=graph.add_fact(make_fact("A"))
    data=graph._path(fact.fact_id).read_bytes()
    graph.revoke(fact.fact_id,"Invalidation")
    graph._path(fact.fact_id).write_bytes(data)
    for read in [lambda:graph.get_fact(fact.fact_id), graph.list_facts,
                 lambda:graph.supporting_closure(fact.fact_id)]:
        with pytest.raises(ValueError,match="fact_revoked"): read()
    graph.facts_dir=graph.revoked_dir
    assert graph.get_fact(fact.fact_id)==fact  # Historical evidence remains readable.
