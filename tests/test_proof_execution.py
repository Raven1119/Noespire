from research.agents import ResearchWorker
from research.closed_book import ClosedBookVerifier
from research.node_solver import NodeSolver, NodeSolverConfig
from research.proof_graph import ProofGraph, ProofObligation, ProofRoute
from research.refutation import RefutationVerifier
import pytest


class ScriptedCodex:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def invoke(self, *, label, prompt, schema):
        self.calls.append((label, prompt))
        expected, response = self.responses.pop(0)
        assert label == expected
        if isinstance(response, BaseException):
            raise response
        return response


def proof(statement, text):
    return dict(kind="PROOF_CANDIDATE", statement=statement, proof=text,
                predecessors=[], counterexample="", reason="")


def verdict(accepted):
    return dict(accepted=accepted, reason="valid" if accepted else "missing arithmetic",
                external_authority_dependency=False, violation_type="NONE")


def test_route_solver_repairs_proof_and_admits_exact_contextual_fact(tmp_path):
    target = ProofObligation.create("p", "x=2", "x+x=4")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    codex = ScriptedCodex([
        ("research_worker", proof(target.statement, "obvious")),
        ("closed_book_verifier", verdict(False)),
        ("research_worker", proof(target.statement, "Substitute x=2: x+x=2+2=4.")),
        ("closed_book_verifier", verdict(True)),
    ])
    solver = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        config=NodeSolverConfig(3), progress_path=tmp_path / "step/solver.json")
    result = solver.solve_route(graph=graph, route_id=route.route_id, author="test")
    assert result.status == "SOLVED"
    assert ProofGraph(tmp_path).obligation(target.obligation_id).truth_state == "DISCHARGED"
    assert len(ProofGraph(tmp_path).supporting_closure()) == 1
    assert "missing arithmetic" in codex.calls[2][1]
    assert not codex.responses


@pytest.mark.parametrize("corruption", ["identity", "fact", "refutation"])
def test_replayed_attempt_cannot_forge_a_result_for_an_open_obligation(tmp_path, corruption):
    from research.run_storage import write_json
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    progress = tmp_path / "step/solver.json"
    write_json(progress, dict(obligation_id=target.obligation_id, route_id=route.route_id,
        max_attempts=1, attempt_ids=["attempt-000001"], active_attempt_id="attempt-000001"))
    write_json(tmp_path / "attempts/attempt-000001.json", dict(
        attempt_id="attempt-999999" if corruption == "identity" else "attempt-000001",
        obligation_id=target.obligation_id, route_id=route.route_id,
        outcome="REFUTATION_ADMITTED" if corruption == "refutation" else "FACT_ADMITTED",
        fact_id="not-a-fact", refutation_id="not-a-refutation", verification={"reason": "claimed"}))
    solver = NodeSolver(worker=ResearchWorker(ScriptedCodex([])), verifier=ClosedBookVerifier(ScriptedCodex([])),
                        progress_path=progress)
    with pytest.raises(ValueError, match="identity|canonical"):
        solver.solve_route(graph=graph, route_id=route.route_id, author="test")


@pytest.mark.parametrize("failure,expected", [("none", "BLOCKED"), ("timeout", "HORIZON"), ("error", "ERROR")])
def test_no_proof_and_runtime_failures_never_refute(tmp_path, failure, expected):
    import subprocess
    from research.run_storage import read_json
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    response = dict(kind="NO_RESULT", statement="", proof="", predecessors=[], counterexample="", reason="gap")
    if failure == "timeout":
        response = subprocess.TimeoutExpired("codex", 600)
    elif failure == "error":
        response = RuntimeError("transport error")
    codex = ScriptedCodex([("research_worker", response)])
    result = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        refutation_verifier=RefutationVerifier(codex)).solve_route(
        graph=graph, route_id=route.route_id, author="test")
    assert result.status == expected
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    # One failure of any class is below the default route allowance (3):
    # the route stays READY for later visits instead of dying outright.
    assert graph.route_state(route.route_id) == "READY"
    assert read_json(tmp_path / "attempts/attempt-000001.json")["outcome"] == {
        "none": "NO_RESULT", "timeout": "TIMEOUT", "error": "ERROR"}[failure]


def test_timeout_exhausts_route_only_at_allowance_across_visits(tmp_path):
    import subprocess
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    codex = ScriptedCodex([("research_worker", subprocess.TimeoutExpired("codex", 600))] * 3)
    solver = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        config=NodeSolverConfig(3, route_attempt_allowance=3),
                        refutation_verifier=RefutationVerifier(codex))
    for visit in (1, 2):
        result = solver.solve_route(graph=ProofGraph(tmp_path), route_id=route.route_id, author="test")
        assert result.status == "HORIZON"
        assert ProofGraph(tmp_path).route_state(route.route_id) == "READY", f"visit {visit}"
    result = solver.solve_route(graph=ProofGraph(tmp_path), route_id=route.route_id, author="test")
    assert result.status == "HORIZON"
    exhausted = ProofGraph(tmp_path).route(route.route_id)
    assert exhausted.lifecycle == "EXHAUSTED"
    assert exhausted.exhaustion_attempt_ids == ("attempt-000001", "attempt-000002", "attempt-000003")
    assert "timed out" in exhausted.exhaustion_reason
    assert not codex.responses


@pytest.mark.parametrize("count,exhausted", [(2, False), (3, True)])
def test_no_result_tally_exhausts_at_allowance(tmp_path, count, exhausted):
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    decline = dict(kind="NO_RESULT", statement="", proof="", predecessors=[], counterexample="", reason="gap")
    codex = ScriptedCodex([("research_worker", decline)] * count)
    result = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        config=NodeSolverConfig(count, route_attempt_allowance=3)).solve_route(
        graph=graph, route_id=route.route_id, author="test")
    assert result.status == "BLOCKED"
    assert (ProofGraph(tmp_path).route(route.route_id).lifecycle == "EXHAUSTED") == exhausted
    assert not codex.responses


def test_failure_classes_are_tallied_separately_across_visits(tmp_path):
    target = ProofObligation.create("p", "", "target")
    route = ProofRoute.create(target.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target, routes=(route,))
    decline = dict(kind="NO_RESULT", statement="", proof="", predecessors=[], counterexample="", reason="gap")
    codex = ScriptedCodex([
        ("research_worker", proof(target.statement, "missing argument")),
        ("closed_book_verifier", verdict(False)),
        ("research_worker", proof(target.statement, "still missing")),
        ("closed_book_verifier", verdict(False)),
        ("research_worker", decline),
        ("research_worker", decline),
    ])
    solver = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        config=NodeSolverConfig(2, route_attempt_allowance=3),
                        refutation_verifier=RefutationVerifier(codex))
    # Visit 1: two verifier rejections; visit 2: two worker declines.
    # 2 + 2 failures, but no single class reaches the allowance of 3.
    for step in ("step1", "step2"):
        solver = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                            config=NodeSolverConfig(2, route_attempt_allowance=3),
                            progress_path=tmp_path / step / "solver.json",
                            refutation_verifier=RefutationVerifier(codex))
        result = solver.solve_route(graph=ProofGraph(tmp_path), route_id=route.route_id, author="test")
        assert result.status == "BLOCKED"
    assert ProofGraph(tmp_path).route_state(route.route_id) == "READY"
    assert len(list((tmp_path / "attempts").glob("attempt-*.json"))) == 4
    assert not codex.responses


@pytest.mark.parametrize("accepted", [True, False])
def test_counterexample_requires_independent_verification_and_only_refutes_child(tmp_path, accepted):
    from research.refutation import RefutationStore
    target = ProofObligation.create("p", "", "target")
    child = ProofObligation.create("p", "n is an integer", "n is even")
    parent_route = ProofRoute.create(target.obligation_id, (child.obligation_id,))
    direct = ProofRoute.create(child.obligation_id)
    graph = ProofGraph.create(tmp_path, problem_id="p", target=target,
                              obligations=(child,), routes=(parent_route, direct))
    codex = ScriptedCodex([
        ("research_worker", dict(kind="COUNTEREXAMPLE_CANDIDATE", statement="", proof="", predecessors=[],
                                 counterexample="n=1 is an integer and is odd", reason="")),
        ("refutation_verifier", dict(accepted=accepted, assumptions_satisfied=True,
                                    conclusion_falsified=accepted, closed_book_clean=True, reason="1 is odd")),
    ])
    result = NodeSolver(worker=ResearchWorker(codex), verifier=ClosedBookVerifier(codex),
                        refutation_verifier=RefutationVerifier(codex)).solve_route(
        graph=graph, route_id=direct.route_id, author="test")
    assert result.status == ("REFUTED" if accepted else "BLOCKED")
    graph = ProofGraph(tmp_path)
    assert graph.obligation(child.obligation_id).truth_state == ("REFUTED" if accepted else "OPEN")
    assert graph.obligation(target.obligation_id).truth_state == "OPEN"
    assert graph.route_state(parent_route.route_id) == ("IMPOSSIBLE" if accepted else "WAITING")
    assert len(RefutationStore(tmp_path).list()) == int(accepted)
    assert not list((tmp_path / "facts").glob("*.md"))
    assert not codex.responses
