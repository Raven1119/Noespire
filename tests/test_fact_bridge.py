"""Explicit scope transport uses real admission/storage and deterministic actors."""
from truth_gate_fixtures import no_counterexample
from dataclasses import asdict
import json
import subprocess

import pytest

from research import fact_bridge as bridge
from research.continuous_materials import load_materials
from research.continuous_network import ContinuousNetwork
from research.fact import Fact
from research.graph import FactGraph
from research.refutation import Refutation, RefutationStore
from research.run_storage import read_json, run_lock, write_json


SOURCE_SCOPE = "Define f(n) = n + 1 for every integer n."
TARGET_GOAL = "Define g(k) = k + 1 for integers k. Then g(k) > k for every integer k."
CORRESPONDENCE = "Use the identity on integers and identify f(n) with g(k) after n := k."


class Crash(BaseException):
    pass


class Actors:
    def __init__(self, *, accepted=True, failure=None):
        self.calls = []
        self.accepted, self.failure = accepted, failure

    def invoke(self, *, prompt, schema, label):
        self.calls.append((label, prompt))
        if self.failure:
            raise self.failure
        if label == "statement_sanity":
            return no_counterexample()
        if label == "fact_bridge_worker":
            packet = json.loads(prompt.split("\nPACKET:\n")[1])
            assert packet["accepted_facts"] == []
            assert packet["source_fact"]["scope"] == SOURCE_SCOPE
            assert SOURCE_SCOPE in packet["source_fact"]["statement"]
            assert "proof" not in packet["source_fact"]
            assert packet["correspondence"] == CORRESPONDENCE
            assert "UNRELATED_GLOBAL_SENTINEL" not in prompt
            return {"status": "PROOF", "proof": "The definitions identify g(k) with f(k). "
                    "The supplied conditional theorem applies under exactly this definition, "
                    "and gives g(k) > k for all integers k.", "reason": "Explicit definition transport."}
        assert label == "closed_book_verifier"
        assert "BRIDGE_INTERFACE:" in prompt
        assert SOURCE_SCOPE in prompt and TARGET_GOAL in prompt
        assert CORRESPONDENCE in prompt
        assert "UNRELATED_GLOBAL_SENTINEL" not in prompt
        return {"accepted": self.accepted, "external_authority_dependency": False,
                "violation_type": "NONE", "reason": "Source conditions were checked."}


@pytest.fixture
def source(tmp_path):
    network = ContinuousNetwork.create(tmp_path, "bridge-test", "The original requirement remains open.")
    candidate, desc = network.prepare_candidate({"kind": "FACT", "goal": "f(n) > n for all integers n.",
        "context": SOURCE_SCOPE, "proof": "For every integer n, n + 1 > n.", "predecessors": []}, [])
    fact = Fact.create(problem_id=network.problem_id, author="oracle", **asdict(candidate))
    FactGraph(tmp_path).add_fact(fact)
    network.accept_verified(desc, fact.fact_id)
    network.register_claim("UNRELATED_GLOBAL_SENTINEL", "Unrelated assumptions.")
    return fact


def start(root, source, actors, **kwargs):
    return bridge.bridge_fact(root, source_fact_id=source.fact_id, target_context="",
        target_goal=TARGET_GOAL, correspondence=CORRESPONDENCE, invoker=actors, **kwargs)


def assert_materialized(root, original, status):
    network = ContinuousNetwork(root)
    assert status["status"] == "COMPLETED" and status["usable"]
    fact = network.visible_fact(status["fact_id"], "")
    assert fact.predecessors == (original.fact_id,)
    assert [f.fact_id for f in FactGraph(root).supporting_closure(fact.fact_id)] == [original.fact_id, fact.fact_id]
    assert network.truth(network.target_id) == "OPEN"
    loaded, notes, notices = load_materials(root, {"scope": ""}, ["fact:" + fact.fact_id], {}, network)
    assert loaded == {fact.fact_id: {"fact_id": fact.fact_id, "statement": TARGET_GOAL}}
    assert notes == notices == []
    with pytest.raises(ValueError, match="exact scope"):
        load_materials(root, {"scope": ""}, ["fact:" + original.fact_id], {}, network)
    with pytest.raises(ValueError, match="exact scope"):
        network.prepare_candidate({"kind": "FACT", "context": "", "goal": TARGET_GOAL,
            "proof": "An unbridged assertion.", "predecessors": [original.fact_id]}, [original.fact_id])


def test_bridge_preserves_source_conditions_lineage_and_ordinary_scope_guard(tmp_path, source):
    actors = Actors()
    original = (tmp_path / "facts" / (source.fact_id + ".md")).read_bytes()
    status = start(tmp_path, source, actors)
    assert_materialized(tmp_path, source, status)
    assert status["model_calls"] == 3
    assert (tmp_path / "facts" / (source.fact_id + ".md")).read_bytes() == original
    assert [label for label, _ in actors.calls] == ["fact_bridge_worker", "statement_sanity", "closed_book_verifier"]
    assert start(tmp_path, source, Actors()) == status
    assert bridge.resume_bridge(tmp_path, status["bridge_id"]) == status


@pytest.mark.parametrize("boundary", ["worker_call", "sanity_call", "verifier_call", "worker_completed",
    "verification_completed", "fact_admitted", "claim_registered", "fact_bound"])
def test_resume_never_repeats_confirmed_calls_or_admission(tmp_path, source, boundary):
    actors = Actors()

    def interrupt(event, details):
        point = {"fact_bridge_worker": "worker_call", "statement_sanity": "sanity_call", "closed_book_verifier": "verifier_call"}.get(details.get("label")) if event == "call_completed" else event
        if point == boundary:
            raise Crash()

    with pytest.raises(Crash):
        start(tmp_path, source, actors, on_event=interrupt)
    directory = next((tmp_path / "fact_bridges").iterdir())
    confirmed = {p: p.read_bytes() for p in directory.glob("calls/*/*.json")}
    status = bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    assert_materialized(tmp_path, source, status)
    assert len(actors.calls) == status["model_calls"] == 3
    assert all(p.read_bytes() == data for p, data in confirmed.items())
    assert len(list((tmp_path / "facts").glob("*.md"))) == 2
    receipt = (directory / "admission.json").read_bytes()
    assert bridge.resume_bridge(tmp_path, directory.name, invoker=actors) == status
    assert (directory / "admission.json").read_bytes() == receipt


@pytest.mark.parametrize("failure,status", [(RuntimeError("transport failed"), "ERROR"),
    (subprocess.TimeoutExpired("codex", 600), "TIMEOUT"), (Crash(), "INTERRUPTED")])
def test_failed_or_unconfirmed_call_is_never_retried_or_admitted(tmp_path, source, failure, status):
    actors = Actors(failure=failure)
    if isinstance(failure, Crash):
        with pytest.raises(Crash):
            start(tmp_path, source, actors)
        directory = next((tmp_path / "fact_bridges").iterdir())
        result = bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    else:
        result = start(tmp_path, source, actors)
    assert result["status"] == status
    assert result["model_calls"] == len(actors.calls) == 1
    assert start(tmp_path, source, actors) == result
    assert len(list((tmp_path / "facts").glob("*.md"))) == 1
    assert ContinuousNetwork(tmp_path).truth(ContinuousNetwork(tmp_path).target_id) == "OPEN"


def test_verifier_rejection_retains_evidence_without_fact_or_retry(tmp_path, source):
    actors = Actors(accepted=False)
    before = (tmp_path / "proof_graph.json").read_bytes()
    status = start(tmp_path, source, actors)
    assert status["status"] == "REJECTED"
    assert status["model_calls"] == 3
    assert (tmp_path / "proof_graph.json").read_bytes() == before
    assert start(tmp_path, source, actors) == status
    assert len(actors.calls) == 3


@pytest.mark.parametrize("role", ["fact_bridge_worker", "closed_book_verifier"])
def test_malformed_response_fails_closed(tmp_path, source, role):
    actors = Actors()
    invoke = actors.invoke

    def malformed(**kwargs):
        if kwargs["label"] != role:
            return invoke(**kwargs)
        actors.calls.append((role, kwargs["prompt"]))
        return {"status": "PROOF", "proof": 7, "reason": "Bad type"} if role == "fact_bridge_worker" else {
            "accepted": "false", "external_authority_dependency": False, "violation_type": "NONE", "reason": "Bad type"}

    actors.invoke = malformed
    status = start(tmp_path, source, actors)
    assert status["status"] == "ERROR"
    assert len(list((tmp_path / "facts").glob("*.md"))) == 1


def test_bridge_decline_does_not_call_verifier(tmp_path, source):
    class Decline:
        def invoke(self, **kwargs):
            return {"status": "DECLINE", "proof": "", "reason": "Cannot justify source conditions."}
    result = start(tmp_path, source, Decline())
    assert result["status"] == "DECLINED" and result["model_calls"] == 1


@pytest.mark.parametrize("invalid", ["unbound", "revoked", "other_problem"])
def test_invalid_sources_stop_before_model_invocation(tmp_path, source, invalid):
    if invalid == "revoked":
        FactGraph(tmp_path).revoke(source.fact_id, "Test revocation")
    else:
        source = Fact.create(problem_id="other" if invalid == "other_problem" else "bridge-test",
            author="oracle", statement="Another fact.", proof="Proof.")
        FactGraph(tmp_path).add_fact(source)
    actors = Actors()
    with pytest.raises(ValueError):
        start(tmp_path, source, actors)
    assert actors.calls == []


def test_source_revoked_after_verification_cannot_be_admitted(tmp_path, source):
    def revoke(event, details):
        if event == "verification_completed":
            FactGraph(tmp_path).revoke(source.fact_id, "No longer accepted")
    result = start(tmp_path, source, Actors(), on_event=revoke)
    assert result["status"] == "ERROR"
    assert not list((tmp_path / "facts").glob("*.md"))


def test_completed_bridge_is_not_usable_after_cascade_revocation(tmp_path, source):
    status = start(tmp_path, source, Actors())
    FactGraph(tmp_path).revoke(source.fact_id, "Independent invalidation")
    read = bridge.read_bridge(tmp_path, status["bridge_id"])
    assert read["status"] == "COMPLETED" and not read["usable"]
    assert bridge.resume_bridge(tmp_path, status["bridge_id"]) == read


def test_partially_admitted_bridge_cannot_resurrect_its_revoked_fact(tmp_path, source):
    def interrupt(event, details):
        if event == "fact_admitted":
            raise Crash()
    actors = Actors()
    with pytest.raises(Crash):
        start(tmp_path, source, actors, on_event=interrupt)
    graph = FactGraph(tmp_path)
    derived = next(f for f in graph.list_facts() if f.fact_id != source.fact_id)
    graph.revoke(derived.fact_id, "Rejected independently before binding")
    directory = next((tmp_path / "fact_bridges").iterdir())
    result = bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    assert result["status"] == "ERROR" and "revoked" in result["reason"]
    assert len(actors.calls) == 3
    assert [f.fact_id for f in graph.list_facts()] == [source.fact_id]


def test_resume_rejects_code_change_and_preserves_old_run_metadata(tmp_path, source, monkeypatch):
    old_run = {"run_id": "frozen-run", "code_digest": "old-fingerprint", "status": "PAUSED"}
    write_json(tmp_path / "continuous_run/state.json", old_run)
    old_bytes = (tmp_path / "continuous_run/state.json").read_bytes()

    def interrupt(event, details):
        if event == "worker_completed":
            raise Crash()
    actors = Actors()
    with pytest.raises(Crash):
        start(tmp_path, source, actors, on_event=interrupt)
    directory = next((tmp_path / "fact_bridges").iterdir())
    monkeypatch.setattr(bridge, "_code_digest", lambda: "changed")
    with pytest.raises(ValueError, match="fingerprint"):
        bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    assert len(actors.calls) == 1
    assert (tmp_path / "continuous_run/state.json").read_bytes() == old_bytes


def test_same_workspace_writer_lock_blocks_bridge(tmp_path, source):
    actors = Actors()
    with run_lock(tmp_path / "continuous_run"):
        with pytest.raises(RuntimeError, match="active writer"):
            start(tmp_path, source, actors)
    assert actors.calls == []


def test_request_tampering_does_not_create_a_new_call(tmp_path, source):
    def interrupt(event, details):
        if event == "worker_completed":
            raise Crash()
    actors = Actors()
    with pytest.raises(Crash):
        start(tmp_path, source, actors, on_event=interrupt)
    directory = next((tmp_path / "fact_bridges").iterdir())
    request = read_json(directory / "request.json")
    request["packet"]["correspondence"] = "Different objects with similar names."
    write_json(directory / "request.json", request)
    with pytest.raises(ValueError, match="identity"):
        bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    assert len(actors.calls) == 1


@pytest.mark.parametrize("torn", [False, True])
def test_missing_or_torn_native_usage_does_not_block_interruption_recovery(tmp_path, source, torn):
    actors = Actors(failure=Crash())
    with pytest.raises(Crash):
        start(tmp_path, source, actors)
    directory = next((tmp_path / "fact_bridges").iterdir())
    path = directory / "invocations/001_fact_bridge_worker.json"
    if torn:
        path.parent.mkdir()
        path.write_bytes(b'{"events": [')
    result = bridge.resume_bridge(tmp_path, directory.name, invoker=actors)
    assert result["status"] == "INTERRUPTED"
    assert result["model_calls"] == result["unknown_usage_calls"] == 1
    assert result["reported_tokens"] == 0  # no reported usage, not known-zero cost
    assert len(actors.calls) == 1
    if torn:
        assert path.read_bytes() == b'{"events": ['
        assert len(result["usage_evidence_errors"]) == 1


def test_refuted_auxiliary_target_stops_before_worker(tmp_path, source):
    network = ContinuousNetwork(tmp_path)
    claim = network.register_claim("0 = 1", "")
    refutation = Refutation.create(claim, "The distinct integers 0 and 1.",
        {"accepted": True, "assumptions_satisfied": True, "conclusion_falsified": True,
         "closed_book_clean": True, "reason": "Different integers."}, {"verifier_call": "deterministic-oracle"})
    RefutationStore(tmp_path).admit(refutation)
    network.bind_refutation(claim.obligation_id, refutation.refutation_id)
    actors = Actors()
    result = bridge.bridge_fact(tmp_path, source_fact_id=source.fact_id, target_context="",
        target_goal=claim.goal, correspondence=CORRESPONDENCE, invoker=actors)
    assert result["status"] == "ERROR" and "refuted" in result["reason"]
    assert result["model_calls"] == 0 and actors.calls == []
    assert len(FactGraph(tmp_path).list_facts()) == 1


def test_unproved_condition_survives_worker_verifier_and_materialization(tmp_path, source):
    network = ContinuousNetwork(tmp_path)
    candidate, desc = network.prepare_candidate({"kind": "FACT", "goal": "If H(n) holds, f(n) > n.",
        "context": SOURCE_SCOPE, "proof": "n+1 > n independently of H.", "predecessors": []}, [])
    conditional = Fact.create(problem_id=network.problem_id, author="oracle", **asdict(candidate))
    FactGraph(tmp_path).add_fact(conditional)
    network.accept_verified(desc, conditional.fact_id)
    goal = "Define g(n)=n+1. If H(n) holds, g(n)>n."
    seen = []

    class ConditionalActors:
        def invoke(self, *, prompt, schema, label):
            seen.append(prompt)
            assert "If H(n) holds" in prompt
            if label == "statement_sanity":
                return no_counterexample()
            if label == "fact_bridge_worker":
                return {"status": "PROOF", "proof": "Under H(n), apply the source with f=g as defined.", "reason": "H stays conditional."}
            return {"accepted": True, "external_authority_dependency": False, "violation_type": "NONE", "reason": "Condition retained."}

    result = bridge.bridge_fact(tmp_path, source_fact_id=conditional.fact_id, target_context="",
        target_goal=goal, correspondence="Identify f with g under the identical definitions; retain H(n).", invoker=ConditionalActors())
    fact = ContinuousNetwork(tmp_path).visible_fact(result["fact_id"], "")
    assert "If H(n) holds" in fact.statement and fact.predecessors == (conditional.fact_id,)
    assert len(seen) == 3


def test_real_runtime_fingerprint_failure_can_resume_without_repeating_worker(tmp_path, source, monkeypatch):
    runtime = {"backend": "codex", "model": "gpt-5.6-sol", "effort": "xhigh", "timeout_seconds": 600,
               "image": "sha256:test", "cli": "fixed-cli", "config_digest": "fixed-config"}
    actors = Actors()
    monkeypatch.setattr(bridge, "real_runtime", lambda image: dict(runtime))
    monkeypatch.setattr(bridge, "SolInvoker", lambda **kwargs: actors)

    def interrupt(event, details):
        if event == "worker_completed":
            raise Crash()
    with pytest.raises(Crash):
        bridge.bridge_fact(tmp_path, source_fact_id=source.fact_id, target_context="", target_goal=TARGET_GOAL,
            correspondence=CORRESPONDENCE, on_event=interrupt)
    directory = next((tmp_path / "fact_bridges").iterdir())
    monkeypatch.setattr(bridge, "real_runtime", lambda image: {**runtime, "cli": "changed-cli"})
    paused = bridge.resume_bridge(tmp_path, directory.name)
    assert paused["status"] == "PAUSED" and "fingerprint" in paused["reason"]
    assert paused["model_calls"] == len(actors.calls) == 1
    monkeypatch.setattr(bridge, "real_runtime", lambda image: dict(runtime))
    result = bridge.resume_bridge(tmp_path, directory.name)
    assert_materialized(tmp_path, source, result)
    assert result["model_calls"] == len(actors.calls) == 3
