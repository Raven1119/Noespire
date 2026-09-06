from research.proof_graph import ProofGraph, ProofObligation, ProofRoute
from dataclasses import replace
import pytest


def test_routes_share_one_mathematical_obligation_and_derive_readiness(tmp_path):
    target = ProofObligation.create("p", "x is real", "x squared is nonnegative")
    same = ProofObligation.create("p", "x  is real", "x squared is nonnegative")
    child = ProofObligation.create("p", "x is real", "x is zero or nonzero")
    direct = ProofRoute.create(target.obligation_id)
    split = ProofRoute.create(target.obligation_id, (child.obligation_id,), kind="SPLIT")
    ProofGraph.create(tmp_path, problem_id="p", target=target,
                      obligations=(same, child), routes=(direct, split))

    graph = ProofGraph(tmp_path)
    assert len(graph.obligations()) == 2
    assert len(graph.routes_for(target.obligation_id)) == 2
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert graph.route_state(direct.route_id) == "READY"
    assert graph.route_state(split.route_id) == "WAITING"
    assert not (tmp_path / "scaffold.json").exists()


@pytest.mark.parametrize("invalid", ["cycle", "missing", "foreign", "forged_truth", "identity"])
def test_invalid_structure_never_creates_a_canonical_graph(tmp_path, invalid):
    target = ProofObligation.create("p", "", "target")
    child = ProofObligation.create("p", "", "child")
    routes = [ProofRoute.create(target.obligation_id, (child.obligation_id,))]
    if invalid == "cycle":
        routes.append(ProofRoute.create(child.obligation_id, (target.obligation_id,)))
    elif invalid == "missing":
        routes.append(ProofRoute.create(child.obligation_id, ("missing",)))
    elif invalid == "foreign":
        child = ProofObligation.create("other", "", "child")
    elif invalid == "forged_truth":
        target = replace(target, truth_state="DISCHARGED", resolved_fact_id="invented")
    else:
        target = replace(target, goal="a different theorem")
    with pytest.raises(ValueError):
        ProofGraph.create(tmp_path, problem_id="p", target=target,
                          obligations=(child,), routes=routes)
    assert not (tmp_path / "proof_graph.json").exists()


def test_verified_refutation_invalidates_only_consuming_route(tmp_path):
    from research.refutation import Refutation, RefutationStore

    target = ProofObligation.create("p", "", "a target")
    false = ProofObligation.create("p", "", "Every integer is even")
    other = ProofObligation.create("p", "", "a different helper")
    failed = ProofRoute.create(target.obligation_id, (false.obligation_id,))
    alternative = ProofRoute.create(target.obligation_id, (other.obligation_id,), kind="ALTERNATIVE")
    direct = ProofRoute.create(other.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target,
        obligations=(false, other), routes=(failed, alternative, direct))
    verification = {"accepted": True, "assumptions_satisfied": True,
                    "conclusion_falsified": True, "closed_book_clean": True, "reason": "1 is odd."}
    refutation = Refutation.create(false, "n=1", verification, {"verifier_call": "independent-test-verifier"})
    RefutationStore(tmp_path).admit(refutation)
    graph.resolve_refutation(false.obligation_id, refutation.refutation_id)

    graph = ProofGraph(tmp_path)
    assert graph.obligation(false.obligation_id).truth_state == "REFUTED"
    assert graph.route_state(failed.route_id) == "IMPOSSIBLE"
    assert graph.route_state(alternative.route_id) == "WAITING"
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert [(f.kind, f.obligation_id) for f in graph.frontiers()] == [("PROOF", other.obligation_id)]
    assert not list((tmp_path / "facts").glob("*"))


def test_all_prerequisites_only_make_route_ready_and_target_needs_its_own_fact(tmp_path):
    from research.fact import Fact
    from research.graph import FactGraph

    target, a, b = [ProofObligation.create("p", "", goal) for goal in ("target", "a", "b")]
    facts = FactGraph(tmp_path)
    support = facts.add_fact(Fact.create(problem_id="p", author="verified-fixture", statement="support", proof="established"))
    route = ProofRoute.create(target.obligation_id, (a.obligation_id, b.obligation_id), (support.fact_id,), kind="CUT")
    ra, rb = ProofRoute.create(a.obligation_id), ProofRoute.create(b.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, obligations=(a, b), routes=(route, ra, rb))
    fa = facts.add_fact(Fact.create(problem_id="p", author="verified-fixture", statement="a", proof="established"))
    fb = facts.add_fact(Fact.create(problem_id="p", author="verified-fixture", statement="b", proof="established"))
    graph.resolve_fact(ra.route_id, fa.fact_id)
    assert graph.route_state(route.route_id) == "WAITING"
    graph.resolve_fact(rb.route_id, fb.fact_id)
    assert graph.route_state(route.route_id) == "READY"
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    ft = facts.add_fact(Fact.create(problem_id="p", author="verified-fixture", statement="target", proof="uses a, b, support",
                                   predecessors=(fa.fact_id, fb.fact_id, support.fact_id)))
    graph.resolve_fact(route.route_id, ft.fact_id)
    assert ProofGraph(tmp_path).obligation(target.obligation_id).resolved_fact_id == ft.fact_id
    assert {f.fact_id for f in graph.supporting_closure()} == {fa.fact_id, fb.fact_id, support.fact_id, ft.fact_id}


def test_exhausted_route_becomes_structural_frontier_without_refuting_goal(tmp_path):
    from research.run_storage import write_json
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    write_json(tmp_path / "attempts/attempt-000001.json", {
        "attempt_id": "attempt-000001", "obligation_id": target.obligation_id,
        "route_id": route.route_id, "outcome": "PROOF_REJECTED"})
    graph.exhaust_route(route.route_id, ("attempt-000001",), "local attempt budget exhausted")
    graph = ProofGraph(tmp_path)
    assert graph.route_state(route.route_id) == "EXHAUSTED"
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert [(f.kind, f.obligation_id) for f in graph.frontiers()] == [("STRUCTURAL", target.obligation_id)]


@pytest.mark.parametrize("check", ["accepted", "assumptions_satisfied", "conclusion_falsified", "closed_book_clean"])
def test_counterexample_without_every_verifier_check_cannot_enter_truth_store(tmp_path, check):
    from research.refutation import Refutation, RefutationStore
    obligation = ProofObligation.create("p", "", "all integers are even")
    evidence = dict(accepted=True, assumptions_satisfied=True, conclusion_falsified=True,
                    closed_book_clean=True, reason="1 is odd")
    evidence[check] = False
    with pytest.raises(ValueError, match="verifier checks"):
        RefutationStore(tmp_path).admit(Refutation.create(obligation, "1", evidence, {"verifier_call": "v"}))
    assert RefutationStore(tmp_path).list() == ()


def test_forged_persisted_resolution_is_not_loaded_as_truth(tmp_path):
    from research.run_storage import read_json, write_json
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    data = read_json(graph.path)
    data["obligations"][target.obligation_id].update(
        truth_state="DISCHARGED", resolved_fact_id="invented", resolved_route_id=route.route_id)
    write_json(graph.path, data)
    with pytest.raises((KeyError, ValueError)):
        ProofGraph(tmp_path)


@pytest.mark.parametrize("corruption", ["missing_attempt", "mismatched_id", "duplicate_ids", "open_with_evidence"])
def test_exhaustion_is_revalidated_when_loading_persisted_graph(tmp_path, corruption):
    from research.run_storage import read_json, write_json
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    write_json(tmp_path / "attempts/attempt-000001.json", {
        "attempt_id": "wrong" if corruption == "mismatched_id" else "attempt-000001",
        "obligation_id": target.obligation_id, "route_id": route.route_id, "outcome": "PROOF_REJECTED"})
    data = read_json(graph.path)
    ids = ["attempt-999999"] if corruption == "missing_attempt" else ["attempt-000001"]
    if corruption == "duplicate_ids":
        ids *= 2
    data["routes"][route.route_id].update(lifecycle="OPEN" if corruption == "open_with_evidence" else "EXHAUSTED",
                                         exhaustion_attempt_ids=ids, exhaustion_reason="spent")
    write_json(graph.path, data)
    with pytest.raises(ValueError):
        ProofGraph(tmp_path)


def test_unknown_support_fact_is_rejected_before_graph_creation(tmp_path):
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id, support_fact_ids=("1234567890abcdef",))
    with pytest.raises((KeyError, ValueError)):
        ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    assert not (tmp_path / "proof_graph.json").exists()
