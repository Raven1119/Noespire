"""Truth-critical boundaries, independent of mathematical model performance."""
from dataclasses import asdict
import json
import subprocess
from types import SimpleNamespace

import pytest

from research.closed_book import ClosedBookVerifier
from research.continuous_research import start_run, resume_run, pause_run
from research.continuous_network import ContinuousNetwork
from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.pipeline import submit_candidate
from research.run_invocations import RecordedInvoker, RunStopped
from research.run_storage import read_json
from research.truth_gate import StatementSanityGate


def sanity(status="NO_CONCRETE_CONTRADICTION"):
    return {"status": status, "checks": [{"case": "n=0", "reason": "Check the stated nonnegative domain."}],
            "counterexample": {"instance": "n=0", "assumptions_satisfied": "0 is nonnegative.",
                 "violated_clause": "n>0", "contradiction": "0>0 is false."}
                if status == "CONCRETE_COUNTEREXAMPLE" else None,
            "reason": "A concrete boundary instance." if status == "CONCRETE_COUNTEREXAMPLE" else "No concrete contradiction established."}


class Backend:
    def __init__(self, response=None, error=None, proof_accept=True):
        self.response = sanity() if response is None else response
        self.error, self.proof_accept, self.calls = error, proof_accept, []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((label, prompt))
        if label == "statement_sanity":
            if self.error:
                raise self.error
            return self.response
        assert label == "closed_book_verifier"
        return {"accepted": self.proof_accept, "external_authority_dependency": False,
                "violation_type": "NONE", "reason": "Independent proof examination."}


def verifier(root, backend, scope=""):
    return ClosedBookVerifier(backend, statement_gate=StatementSanityGate(backend, root, scope))


def test_concrete_counterexample_vetoes_even_a_proof_that_would_pass(tmp_path):
    backend = Backend(sanity("CONCRETE_COUNTEREXAMPLE"))
    candidate = CandidateFact("For every nonnegative integer n, n>0.", "An impressive but false proof.", ())
    result = submit_candidate(graph=FactGraph(tmp_path), problem_id="p", problem="irrelevant",
        author="test", candidate=candidate, verifier=verifier(tmp_path, backend))
    assert result.fact is None and not result.verification.accepted
    assert [c[0] for c in backend.calls] == ["statement_sanity"]
    assert not FactGraph(tmp_path).list_facts()
    assert not (tmp_path/"refutations").exists()
    assert read_json(tmp_path/"statement_sanity.json")["status"] == "CONCRETE_COUNTEREXAMPLE"


@pytest.mark.parametrize("status", ["NO_CONCRETE_CONTRADICTION", "UNCERTAIN"])
@pytest.mark.parametrize("proof_accept", [True, False])
def test_sanity_never_substitutes_for_independent_proof_verification(tmp_path, status, proof_accept):
    backend = Backend(sanity(status), proof_accept=proof_accept)
    candidate = CandidateFact("1+1=2", "Addition.", ())
    result = verifier(tmp_path, backend).verify("background", candidate, [])
    assert result.accepted is proof_accept
    assert [c[0] for c in backend.calls] == ["statement_sanity", "closed_book_verifier"]


def test_only_exact_statement_scope_and_actual_predecessor_interfaces_are_exposed(tmp_path):
    pred = Fact.create(problem_id="p", author="test", statement="Under X: P implies Q.",
                       proof="SECRET_PREDECESSOR_PROOF", predecessors=[])
    c = CandidateFact("Under Y: P implies Q.", "SECRET_CANDIDATE_PROOF", (pred.fact_id,))
    b = Backend()
    verifier(tmp_path, b, "Y").verify("SECRET_GLOBAL_PROBLEM", c, [pred])
    text = b.calls[0][1]
    assert all(x not in text for x in ["SECRET_PREDECESSOR_PROOF", "SECRET_CANDIDATE_PROOF", "SECRET_GLOBAL_PROBLEM"])
    packet = json.loads(text.split("STATEMENT_INTERFACE:\n")[1])
    assert packet == {"statement": c.statement, "ambient_scope": "Y",
                      "accepted_predecessors": [{"fact_id": pred.fact_id, "statement": pred.statement}]}
    assert read_json(tmp_path/"statement_sanity_input.json")["packet"] == packet


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(status="PASS"), lambda r: r.update(checks=[]),
    lambda r: r.update(counterexample={"instance": "n=0"}),
    lambda r: r.update(reason=""), lambda r: r.update(accepted=True),
    lambda r: r.update(status="CONCRETE_COUNTEREXAMPLE"),
    lambda r: r.update(checks=[{"case": "", "reason": ""}]),
])
def test_malformed_truth_evidence_fails_closed(tmp_path, mutation):
    response = sanity(); mutation(response)
    backend = Backend(response)
    result = verifier(tmp_path, backend).verify("", CandidateFact("P", "proof", ()), [])
    assert not result.accepted and "INVALID" in result.reason
    assert len(backend.calls) == 1


def test_sanity_timeout_is_not_falsity_or_admission(tmp_path):
    b = Backend(error=subprocess.TimeoutExpired("codex", 600))
    result = verifier(tmp_path, b).verify("", CandidateFact("P", "proof", ()), [])
    assert not result.accepted and "TIMEOUT" in result.reason
    assert read_json(tmp_path/"statement_sanity.json")["status"] == "TIMEOUT"


def test_changed_candidate_cannot_reuse_a_sanity_receipt(tmp_path):
    b=Backend(); v=verifier(tmp_path,b)
    v.verify("", CandidateFact("P", "proof", ()), [])
    with pytest.raises(RunStopped) as stopped:
        v.verify("", CandidateFact("Q", "proof", ()), [])
    assert stopped.value.reason.startswith("TRUTH_EVIDENCE_CORRUPTION")
    assert len(b.calls)==2


class Crash(BaseException):
    pass


@pytest.mark.parametrize("boundary", ["statement_sanity", "closed_book_verifier", "fact_admitted", "fact_bound"])
def test_full_loop_recovery_does_not_duplicate_any_truth_stage(tmp_path, boundary):
    class Model(Backend):
        def invoke(self, *, prompt, schema, label):
            if label == "continuous_worker":
                self.calls.append((label,prompt))
                return {"continuation":"Addition complete.", "next_work":"", "candidate":{
                    "kind":"FACT", "goal":"1+1=2", "context":"", "proof":"Definition of addition.", "predecessors":[]}}
            return super().invoke(prompt=prompt,schema=schema,label=label)
    model=Model(); fired=False
    def interrupt(event, details):
        nonlocal fired
        if not fired and (event==boundary or event=="call_completed" and details["label"]==boundary):
            fired=True; raise Crash()
    with pytest.raises(Crash):
        start_run(tmp_path,problem_id="p",statement="1+1=2",invoker=model,on_event=interrupt)
    final=resume_run(tmp_path,invoker=model)
    assert final["status"]=="SOLVED"
    assert [c[0] for c in model.calls]==["continuous_worker","statement_sanity","closed_book_verifier"]
    assert final["model_calls"]==3
    assert len(FactGraph(tmp_path).list_facts())==1
    assert final["studies"][0]["revision"]==1


@pytest.mark.parametrize("response,error", [(sanity("CONCRETE_COUNTEREXAMPLE"),None),
                                               (None,subprocess.TimeoutExpired("codex",600))])
def test_gate_rejection_is_local_feedback_not_truth_or_global_pause(tmp_path,response,error):
    class Model(Backend):
        def invoke(self, *, prompt, schema, label):
            if label=="continuous_worker":
                self.calls.append((label,prompt))
                return {"continuation":"Proposed a boundary-sensitive lemma.","next_work":"Recheck boundary.",
                    "candidate":{"kind":"FACT","goal":"For all n>=0, n>0.","context":"",
                                 "proof":"A false proof.","predecessors":[]}}
            return super().invoke(prompt=prompt,schema=schema,label=label)
    b=Model(response,error)
    def observe(event,details):
        if event=="visit_completed": pause_run(tmp_path,"test stop after completed local rejection")
    result=start_run(tmp_path,problem_id="p",statement="For all n>=0, n>=0.",invoker=b,on_event=observe)
    assert result["pause_reason"]=="test stop after completed local rejection"
    assert result["step"]==1 and result["target_state"]=="OPEN"
    assert [c[0] for c in b.calls]==["continuous_worker","statement_sanity"]
    assert not FactGraph(tmp_path).list_facts()
    assert not ContinuousNetwork(tmp_path).data["refutations"]


def test_confirmed_sanity_reused_if_process_dies_before_receipt(tmp_path):
    b=Backend(); events=[]
    def event(name,**kw):
        events.append(name)
        if name=="call_completed" and len(events)==2: raise Crash()
    run=SimpleNamespace(state={"step":0}, directory=tmp_path, step_dir=tmp_path,
                        backend=b,usage=lambda:{},event=event)
    c=CandidateFact("1+1=2","Addition",())
    gate=StatementSanityGate(RecordedInvoker(run,"sanity"),tmp_path,"")
    with pytest.raises(Crash): gate.check(c,[])
    assert not (tmp_path/"statement_sanity.json").exists()
    run.event=lambda *a,**k: None
    assert gate.check(c,[]) is None
    assert len(b.calls)==1


def test_proof_interruption_keeps_confirmed_sanity_identity(tmp_path):
    class Model(Backend):
        def invoke(self, *, prompt, schema, label):
            if label=="continuous_worker":
                self.calls.append((label,prompt))
                return {"continuation":"Done", "next_work":"", "candidate":{
                    "kind":"FACT", "goal":"1+1=2", "context":"", "proof":"Addition.", "predecessors":[]}}
            return super().invoke(prompt=prompt,schema=schema,label=label)
    b=Model()
    def crash(event,details):
        if event=="call_started" and details["label"]=="closed_book_verifier": raise Crash()
    with pytest.raises(Crash):
        start_run(tmp_path,problem_id="p",statement="1+1=2",invoker=b,on_event=crash)
    interrupted=resume_run(tmp_path,invoker=b)
    assert interrupted["pause_reason"]=="INTERRUPTED"
    assert interrupted["retry_role"]=="verifier"
    final=resume_run(tmp_path,invoker=b)
    assert final["status"]=="SOLVED"
    assert [c[0] for c in b.calls]==["continuous_worker","statement_sanity","closed_book_verifier"]
    assert final["model_calls"]==4  # Interrupted reservation remains charged/unknown.


def test_proof_timeout_after_sanity_is_unverified_local_failure(tmp_path):
    class Model(Backend):
        def invoke(self, *, prompt, schema, label):
            if label=="continuous_worker":
                self.calls.append((label,prompt))
                return {"continuation":"Done", "next_work":"", "candidate":{
                    "kind":"FACT", "goal":"1+1=2", "context":"", "proof":"Addition.", "predecessors":[]}}
            if label=="closed_book_verifier":
                self.calls.append((label,prompt)); raise subprocess.TimeoutExpired("codex",600)
            return super().invoke(prompt=prompt,schema=schema,label=label)
    b=Model()
    def observe(event,details):
        if event=="visit_completed": pause_run(tmp_path,"test observation")
    final=start_run(tmp_path,problem_id="p",statement="1+1=2",invoker=b,on_event=observe)
    assert final["step"]==1 and final["pause_reason"]=="test observation"
    assert final["target_state"]=="OPEN" and not FactGraph(tmp_path).list_facts()
    v=read_json(tmp_path/"continuous_run/visits/00000000/verification.json")
    assert not v["accepted"] and "PROOF_VERIFICATION:TIMEOUT" in v["reason"]


def test_frozen_mathematical_panel_uses_only_statement_interfaces(tmp_path):
    from pathlib import Path
    panel=read_json(Path(__file__).parent/"fixtures/truth_gate_regression.json")
    assert len(panel["cases"])==7
    for case in panel["cases"]:
        c=CandidateFact(**{**case["candidate"],"predecessors":tuple(case["candidate"]["predecessors"])})
        preds=[Fact(**{**f,"predecessors":tuple(f["predecessors"])}) for f in case["predecessors"]]
        b=Backend()
        gate=StatementSanityGate(b,tmp_path/case["case_id"],case["ambient_scope"])
        assert gate.check(c,preds) is None
        packet=json.loads(b.calls[0][1].split("STATEMENT_INTERFACE:\n")[1])
        assert packet["statement"]==c.statement
        assert c.proof not in b.calls[0][1]
        assert "expected" not in packet and "variant_description" not in packet
        assert {f["fact_id"] for f in packet["accepted_predecessors"]}==set(c.predecessors)


@pytest.mark.parametrize("name", ["statement_sanity_input.json", "statement_sanity.json"])
def test_torn_sanity_evidence_is_recovery_corruption(tmp_path,name):
    b=Backend(); gate=StatementSanityGate(b,tmp_path,"")
    c=CandidateFact("1+1=2","Addition",())
    assert gate.check(c,[]) is None
    (tmp_path/name).write_text('{"truncated":',encoding="utf8")
    with pytest.raises(RunStopped) as stopped: gate.check(c,[])
    assert stopped.value.reason.startswith("TRUTH_EVIDENCE_CORRUPTION")
