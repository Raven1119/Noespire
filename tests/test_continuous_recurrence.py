"""Truth and recovery tests use fixed model judgements, never similarity heuristics."""
from truth_gate_fixtures import no_counterexample
import json
import subprocess
from dataclasses import asdict

import pytest

from research.continuous_research import start_run, resume_run, pause_run, _Research
from research.continuous_network import ContinuousNetwork
from research.continuous_materials import load_materials
from research.continuous_recurrence import ancestor_path, prepare_origin, _CHECKS
from research.graph import FactGraph
from research.run_storage import read_json

ROOT = "For all natural n, n + 0 = n."
CHILD = "For every natural k, k + 0 = k."


class Crash(BaseException):
    pass


class Model:
    def __init__(self, child=CHILD, match=True, checks=True, multi=False, decline=False, failure=None):
        self.child,self.match,self.checks,self.multi = child,match,checks,multi
        self.decline,self.failure = decline,failure
        self.root = ROOT
        self.transport_proof = "Assume the first universal statement. Instantiate n=k to prove the second. Conversely instantiate k=n. Domains are identical."
        self.calls,self.packets = [],{}

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        self.packets[label] = prompt
        if label == self.failure:
            raise subprocess.TimeoutExpired("codex",600)
        if label == "statement_sanity":
            return no_counterexample(prompt)
        if label == "continuous_worker":
            p = json.loads(prompt.split("PACKET:\n")[1])
            return {"continuation":"A representation may permit the same research.","next_work":"Inspect the reduction.",
                "candidate":{"kind":"SUPPORT","context":p["claim"]["context"],"goal":p["claim"]["goal"],
                    "proof":"The quantified renamed statement implies this statement by substitution.","predecessors":[],
                    "requirements":[{"goal":self.child,"context":""}]+([{"goal":"0 = 0","context":""}] if self.multi else [])}}
        if label == "recurrence_probe":
            p = json.loads(prompt.split("PACKET:\n")[1])
            return {"status":"POSSIBLE_REPRESENTATION_EQUIVALENCE" if self.match else "NO_MATCH",
                    "ancestor_claim_id":p["ancestors"][0]["obligation_id"] if self.match else "",
                    "explicit_mapping":"Replace the bound natural n by k in both quantified directions." if self.match else "",
                    "reason":"Fixed independent test judgement."}
        if label == "representation_bridge_worker":
            return {"status":"DECLINE" if self.decline else "PROOF", "reason":"Frozen transport judgement.",
                    "proof":self.transport_proof}
        if label in ("closed_book_verifier","representation_verifier"):
            return {"accepted":True,"external_authority_dependency":False,"violation_type":"NONE",
                    "reason":"Verified both renaming directions." if self.checks else "Reverse needs a substantive independent theorem.",
                    **({k:self.checks for k in _CHECKS} if label=="representation_verifier" else {})}
        raise AssertionError(label)


def stop(root):
    def observe(event,details):
        if event == "visit_completed":
            pause_run(root,"one deterministic visit")
    return observe


def execute(root,model,observe=None):
    return start_run(root,problem_id="representation",statement=model.root,invoker=model,on_event=observe or stop(root))


@pytest.mark.parametrize("root,child,proof", [
    (ROOT,ROOT,"Each implication is the identity: assume exactly the proposition and return it."),
    (ROOT,CHILD,"Instantiate n=k in the forward implication, and k=n in the reverse; the natural domains agree."),
    ("For N>=1 and A a subset of [N]={1,...,N}, |A|<=N.",
     "For any finite X and Y a subset of X, |Y|<=|X|.",
     "If X is nonempty choose a bijection b:X->[N], N=|X|. Its restriction bijects Y with b(Y), so apply the first statement. If X is empty Y is empty and 0<=0. Conversely take X=[N],Y=A; |[N]|=N by enumeration."),
    (ROOT,"For every natural k define z(k)=k+0. Then z(k)=k.",
     "Forward: substitute n=k and the defining expression for z. Reverse: instantiate k=n and unfold z(n)=n+0. No existence property is assumed beyond the explicit definition.")])
def test_verified_representation_has_no_independent_study_or_depth_or_truth(tmp_path,root,child,proof):
    model=Model(child=child)
    model.root,model.transport_proof=root,proof
    result=execute(tmp_path,model)
    n=ContinuousNetwork(tmp_path)
    row=next(iter(n.data["representations"].values()))
    assert row["ancestor_claim_id"] == n.target_id
    assert n.truth(n.target_id)==n.truth(row["claim_id"])=="OPEN"
    assert len(result["studies"])==1
    assert n.effective_depth()==0
    assert len(n.data["supports"])==1
    assert len(list((tmp_path/"facts").glob("*.md")))==2  # implication + equivalence only
    assert len(FactGraph(tmp_path).supporting_closure(row["equivalence_fact_id"]))==1
    assert n.ready_supports()==()
    assert model.calls==["continuous_worker","statement_sanity", "closed_book_verifier","recurrence_probe",
                         "representation_bridge_worker","statement_sanity", "representation_verifier"]
    feedback=read_json(tmp_path/"continuous_run/visits/00000000/feedback.json")
    assert feedback["accepted"] is True and feedback["representation_recurrence"]["status"]=="ALIAS"
    assert "ancestor-equivalent" in result["studies"][0]["admission_summary"]


@pytest.mark.parametrize("match,checks,decline",[(False,True,False),(True,False,False),(True,True,True)])
def test_no_match_stronger_theorem_and_nontrivial_reverse_keep_study(tmp_path,match,checks,decline):
    model=Model(child="A genuinely stronger theorem requiring an independent estimate.",match=match,checks=checks,decline=decline)
    result=execute(tmp_path,model)
    n=ContinuousNetwork(tmp_path)
    assert not n.data.get("representations")
    assert len(result["studies"])==2 and n.effective_depth()==1
    assert n.truth(n.target_id)=="OPEN"
    assert len(list((tmp_path/"facts").glob("*.md")))==1
    assert read_json(tmp_path/"continuous_run/visits/00000000/verification.json")["accepted"] is True


def test_multi_requirement_has_no_probe_or_collapse(tmp_path):
    model=Model(multi=True)
    result=execute(tmp_path,model)
    assert model.calls==["continuous_worker","statement_sanity", "closed_book_verifier"]
    assert len(result["studies"])==3
    assert ContinuousNetwork(tmp_path).effective_depth()==1


@pytest.mark.parametrize("boundary",["fact_admitted","fact_bound","recurrence_probed",
    "representation_worker_completed","representation_verified","representation_fact_admitted",
    "representation_alias_saved","recurrence_completed"])
def test_resume_never_repeats_calls_or_alias_admission(tmp_path,boundary):
    model=Model()
    def crash(event,details):
        if event==boundary:
            raise Crash()
    with pytest.raises(Crash):
        execute(tmp_path,model,crash)
    immutable={p:p.read_bytes() for folder in ("facts","continuous_run/calls")
               for p in (tmp_path/folder).rglob("*") if p.is_file()}
    result=resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    assert result["status"]=="PAUSED"
    assert len(model.calls)==7 and len(set(model.calls))==6 and model.calls.count("statement_sanity")==2
    assert all(p.read_bytes()==v for p,v in immutable.items())
    assert len(ContinuousNetwork(tmp_path).data["representations"])==1
    assert len(result["studies"])==1


@pytest.mark.parametrize("role",["recurrence_probe","representation_bridge_worker","representation_verifier"])
def test_timeout_falls_back_without_retry_or_changing_support_acceptance(tmp_path,role):
    model=Model(failure=role)
    result=execute(tmp_path,model)
    assert len(result["studies"])==2
    assert model.calls.count(role)==1
    feedback=read_json(tmp_path/"continuous_run/visits/00000000/feedback.json")
    assert feedback["accepted"] is True
    assert feedback["representation_recurrence"]["status"]=="TIMEOUT"
    assert result.get("retry_role") is None


def test_unconfirmed_probe_is_interrupted_no_resampling(tmp_path):
    model=Model()
    def crash(event,details):
        if event=="call_started" and details.get("label")=="recurrence_probe":
            raise Crash()
    with pytest.raises(Crash):
        execute(tmp_path,model,crash)
    result=resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    assert model.calls==["continuous_worker","statement_sanity", "closed_book_verifier"]
    assert len(result["studies"])==2
    feedback=read_json(tmp_path/"continuous_run/visits/00000000/feedback.json")
    assert feedback["representation_recurrence"]["status"]=="INTERRUPTED"
    assert list((tmp_path/"continuous_run/calls").glob("*/interrupted.json"))


def test_representation_navigation_is_on_demand_not_accepted_material(tmp_path):
    execute(tmp_path,Model())
    n=ContinuousNetwork(tmp_path)
    state=read_json(tmp_path/"continuous_run/state.json")
    run=_Research(tmp_path,state,None,None)
    studies={k:read_json(tmp_path/"continuous_run"/ref) for k,ref in state["studies"].items()}
    exposure=run.selector_exposure(n,studies)["exposure"]
    ref=exposure["cards"][0]["representation_ref"]
    assert ref=="representations:"+n.target_id
    assert CHILD not in json.dumps(exposure)
    facts,unverified,notices=load_materials(tmp_path,next(iter(studies.values())),[ref],state["studies"],n)
    assert facts=={} and not notices
    assert unverified[0]["verified"] is False
    assert unverified[0]["representation_views"][0]["statement"]==CHILD
    eq=next(iter(n.data["representations"].values()))["equivalence_fact_id"]
    with pytest.raises(ValueError):
        n.visible_fact(eq,"")  # no automatic premise binding of transport certificate


@pytest.mark.parametrize("revoke",["equivalence_fact_id","bridge_fact_id"])
def test_revocation_restores_open_child_before_selection_preserving_evidence(tmp_path,revoke):
    execute(tmp_path,Model())
    n=ContinuousNetwork(tmp_path)
    row=next(iter(n.data["representations"].values()))
    fid=row[revoke] if revoke in row else n.data["supports"][row["support_id"]][revoke]
    FactGraph(tmp_path).revoke(fid,"Independent invalidation.")
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(row["claim_id"]) is None
    assert n.representation_views(n.target_id)==()
    state=read_json(tmp_path/"continuous_run/state.json")
    run=_Research(tmp_path,state,None,None)
    run.restore_revoked_alias_studies(n)
    assert "study-"+row["claim_id"] in run.state["studies"]
    assert n.truth(row["claim_id"])=="OPEN"
    assert (tmp_path/row["evidence_ref"]/"verification.json").exists()


def test_path_packet_excludes_unrelated_graph_and_multi_support_ancestors(tmp_path):
    from test_continuous_network import accept
    n=ContinuousNetwork.create(tmp_path,"path","Root")
    s,_=accept(n,"Root",requirements=["Middle","Unrelated private branch"])
    middle=s["requirement_claim_ids"][0]
    n.register_claim("GLOBAL SENTINEL SECRET MATHEMATICS","")
    candidate={"kind":"SUPPORT","context":"","goal":"Middle","requirements":[{"context":"","goal":"Renamed root"}]}
    origin=prepare_origin(n,{"study":{"claim_id":middle}},candidate)
    assert [c["goal"] for c in origin["ancestors"]]==["Root","Middle"]
    assert "Unrelated" not in json.dumps(origin) and "SENTINEL" not in json.dumps(origin)
    assert set(origin)=={"new_claim","ancestors"}


@pytest.mark.parametrize("check",_CHECKS)
def test_each_independent_representation_check_is_mandatory(tmp_path,check):
    class MissingCheck(Model):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs["label"]=="representation_verifier":
                result[check]=False
            return result
    result=execute(tmp_path,MissingCheck())
    assert len(result["studies"])==2
    assert not ContinuousNetwork(tmp_path).data.get("representations")
    assert len(list((tmp_path/"facts").glob("*.md")))==1


def test_probe_cannot_match_nonancestor_or_modify_scope(tmp_path):
    class BadID(Model):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs["label"]=="recurrence_probe":
                result["ancestor_claim_id"]="ob-"+"a"*24
            return result
    model=BadID()
    result=execute(tmp_path,model)
    assert len(result["studies"])==2
    assert "representation_bridge_worker" not in model.calls


@pytest.mark.parametrize("kind",["scope","mapping","uncertain"])
def test_illegal_or_uncertain_probe_has_no_authority(tmp_path,kind):
    class BadProbe(Model):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs["label"]=="recurrence_probe":
                if kind=="mapping": result["explicit_mapping"]=""
                if kind=="uncertain": result["status"]="UNCERTAIN"
            return result
    model=BadProbe()
    if kind=="scope":
        # The guard is exercised directly: different assumptions are never
        # transported by this representation-only entry.
        from research.continuous_recurrence import equivalence_statement
        n=ContinuousNetwork.create(tmp_path,"scope","x>0","x is real")
        other=n.register_claim("x>0","x is positive real")
        with pytest.raises(ValueError,match="exact ambient scope"):
            equivalence_statement(n,n.target_id,other.obligation_id)
        return
    result=execute(tmp_path,model)
    assert len(result["studies"])==2
    assert "representation_bridge_worker" not in model.calls


def test_return_to_existing_ancestor_never_suppresses_original_study(tmp_path):
    execute(tmp_path,Model(match=False))  # A -> B, two existing Studies
    n=ContinuousNetwork(tmp_path)
    existing=set(n.data["obligations"])
    b=next(k for k in existing if k!=n.target_id)
    state=read_json(tmp_path/"continuous_run/state.json")
    run=_Research(tmp_path,state,None,None)
    study=read_json(run.directory/state["studies"]["study-"+b])
    from research.run_storage import write_json
    write_json(run.step_dir/"packet.json",{"study":study,"claim":asdict(n.claim(b)),
        "operation":"ADVANCE","accepted_facts":[],"required_fact_ids":[]})
    class ReturnToRoot(Model):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs["label"]=="recurrence_probe":
                packet=json.loads(kwargs["prompt"].split("PACKET:\n")[1])
                result["ancestor_claim_id"]=packet["ancestors"][-1]["obligation_id"]
            return result
    model=ReturnToRoot(child=ROOT)
    run.backend=model
    run.state["acknowledged_pauses"]=[p.name for p in (run.directory/"pause_requests").glob("*.json")]
    run.visit(n)
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(n.target_id) is None
    assert set(n.data["obligations"])==existing
    studies={k:read_json(run.directory/ref) for k,ref in run.state["studies"].items()}
    assert len(run.selector_exposure(n,studies)["exposure"]["cards"])==2
    assert n.effective_depth()==1


def test_revoked_equivalence_after_certificate_admission_not_resurrected(tmp_path):
    model=Model()
    def crash(event,details):
        if event=="representation_fact_admitted":
            FactGraph(tmp_path).revoke(details["fact_id"],"Rejected by a later independent audit.")
            raise Crash()
    with pytest.raises(Crash):
        execute(tmp_path,model,crash)
    result=resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    assert len(model.calls)==7
    assert len(result["studies"])==2
    assert not ContinuousNetwork(tmp_path).data.get("representations")
    assert len(list((tmp_path/"facts").glob("*.md")))==1
    assert len(list((tmp_path/"_revoked").glob("*.md")))==1
