"""One-helper deferred aliases: fixed independent oracle outcomes test authority."""
from dataclasses import asdict
import json
import subprocess
import pytest

from research.continuous_network import ContinuousNetwork
from research.continuous_recurrence import prepare_origin
from research.conditional_recurrence import CONDITIONAL_CHECKS,ACTIVATION_CHECKS,activate_ready
from research.continuous_research import _Research,start_run,resume_run
from research.graph import FactGraph
from research.refutation import Refutation,RefutationStore
from research.run_invocations import RunStopped
from research.run_storage import read_json
from test_continuous_recurrence import Model,Crash,ROOT,CHILD,execute,stop
from test_continuous_network import accept

HELPER="For every finite set X, every bijection b:X->[|X|] preserves cardinalities of subsets and containment."


class Conditional(Model):
    def __init__(self,*,checks=True,bad=None,failure=None):
        super().__init__()
        self.conditional_checks,self.bad,self.failure=checks,bad,failure
    def invoke(self,**kwargs):
        label=kwargs["label"]
        if label in ("conditional_representation_verifier","representation_activation_verifier"):
            self.calls.append(label)
            self.packets[label]=kwargs["prompt"]
            if self.failure==label:raise subprocess.TimeoutExpired("codex",600)
            keys=CONDITIONAL_CHECKS if label=="conditional_representation_verifier" else ACTIVATION_CHECKS
            return {"accepted":True,"external_authority_dependency":False,"violation_type":"NONE",
                "reason":"Frozen independent conditional-interface verdict.",
                **{k:self.conditional_checks for k in keys}}
        result=super().invoke(**kwargs)
        if label=="representation_bridge_worker":
            result={"status":"NEEDS_LEMMA","proof":"","reason":"A local transport identity is missing.",
                    "helper_statement":HELPER,"helper_context":"","mapping":"Map each element by the specified finite bijection; transport its subsets elementwise.",
                    "conditional_transport_proof":"Assume the displayed helper only conditionally. In the forward direction transport the indexed objects by the bijection and use its cardinality identity. In the reverse direction choose X=[N] and the identity map. No claim of a proof of the helper is made."}
            if self.bad=="scope":result["helper_context"]="Assume all sets have the desired property."
            if self.bad=="identity":result["helper_statement"]=ROOT
            if self.bad=="child":result["helper_statement"]=CHILD
            if self.bad=="multiple":result["helpers"]=[HELPER,HELPER]
            if self.bad=="list":result["helper_statement"]=[HELPER,HELPER]
            if self.bad=="empty":result["conditional_transport_proof"]=""
        return result


def deferred(root):
    n=ContinuousNetwork(root)
    return n,next(iter(n.data["deferred_representations"].values()))


def runner(root,model,observer=None):
    state=read_json(root/"continuous_run/state.json")
    state["acknowledged_pauses"]=[p.name for p in (root/"continuous_run/pause_requests").glob("*.json")]
    return _Research(root,state,model,observer)


def prove_helper(root):
    n,row=deferred(root)
    _,fact=accept(n,n.claim(row["helper_claim_id"]).goal,proof="Deterministic independently accepted helper proof.")
    return n,row,fact


def test_conditional_pass_creates_only_helper_and_does_not_activate_or_discharge(tmp_path):
    model=Conditional()
    result=execute(tmp_path,model)
    n,row=deferred(tmp_path)
    assert n.alias_of(row["claim_id"]) is None
    assert n.waiting_on(row["claim_id"])==row["helper_claim_id"]
    assert {s["claim_id"] for s in result["studies"]}=={n.target_id,row["helper_claim_id"]}
    assert n.effective_depth()==1  # parent -> H, never parent -> N -> H
    assert n.truth(n.target_id)==n.truth(row["claim_id"])==n.truth(row["helper_claim_id"])=="OPEN"
    assert n.ready_supports()==()
    assert n.data.get("representations",{})=={}
    assert FactGraph(tmp_path).get_fact(row["conditional_fact_id"]).predecessors==()
    assert model.calls==["continuous_worker","closed_book_verifier","recurrence_probe",
                         "representation_bridge_worker","conditional_representation_verifier"]
    feedback=read_json(tmp_path/"continuous_run/visits/00000000/feedback.json")
    assert feedback["accepted"] is True
    assert feedback["representation_recurrence"]["alias_active"] is False
    assert "Alias inactive" in result["studies"][0]["admission_summary"]


@pytest.mark.parametrize("bad",["scope","identity","child","multiple","list","empty"])
def test_illegal_helper_mechanically_falls_back_without_creating_claim(tmp_path,bad):
    model=Conditional(bad=bad)
    result=execute(tmp_path,model)
    n=ContinuousNetwork(tmp_path)
    assert len(result["studies"])==2
    assert len(n.data["obligations"])==2
    assert not n.data.get("deferred_representations")
    assert "conditional_representation_verifier" not in model.calls
    assert len(list((tmp_path/"facts").glob("*.md")))==1


@pytest.mark.parametrize("check",CONDITIONAL_CHECKS)
def test_conditional_checks_including_semantic_restatement_are_mandatory(tmp_path,check):
    class Rejected(Conditional):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs["label"]=="conditional_representation_verifier":result[check]=False
            return result
    result=execute(tmp_path,Rejected())
    assert len(result["studies"])==2
    n=ContinuousNetwork(tmp_path)
    assert not n.data.get("deferred_representations")
    assert len(n.data["obligations"])==2
    assert len(list((tmp_path/"facts").glob("*.md")))==1


@pytest.mark.parametrize("event",["recurrence_probed","representation_worker_completed","conditional_transport_verified",
    "conditional_fact_admitted","representation_helper_registered","representation_deferred_saved","recurrence_completed"])
def test_conditional_recovery_preserves_one_helper_and_one_call_per_role(tmp_path,event):
    model=Conditional()
    def crash(name,details):
        if name==event:raise Crash()
    with pytest.raises(Crash):execute(tmp_path,model,crash)
    saved={p:p.read_bytes() for folder in ("facts","continuous_run/calls") for p in (tmp_path/folder).rglob('*') if p.is_file()}
    result=resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    assert len(model.calls)==5 and len(set(model.calls))==5
    assert all(p.read_bytes()==v for p,v in saved.items())
    n,row=deferred(tmp_path)
    assert len(n.data['obligations'])==3
    assert {s['claim_id'] for s in result['studies']}=={n.target_id,row['helper_claim_id']}


def test_future_helper_fact_needs_fresh_verified_activation_with_exact_lineage(tmp_path):
    model=Conditional()
    execute(tmp_path,model)
    n,row,helper_fact=prove_helper(tmp_path)
    assert n.alias_of(row['claim_id']) is None
    run=runner(tmp_path,model)
    activate_ready(run,n)
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(row['claim_id'])==n.target_id
    fact=FactGraph(tmp_path).get_fact(n.data['representations'][row['support_id']]['equivalence_fact_id'])
    assert fact.predecessors==tuple(sorted([helper_fact.fact_id,row['conditional_fact_id']]))
    assert {f.fact_id for f in FactGraph(tmp_path).supporting_closure(fact.fact_id)}=={fact.fact_id,helper_fact.fact_id,row['conditional_fact_id']}
    assert n.truth(n.target_id)==n.truth(row['claim_id'])=='OPEN'
    assert model.calls.count('representation_bridge_worker')==1
    assert model.calls.count('representation_activation_verifier')==1
    activate_ready(run,n)
    assert model.calls.count('representation_activation_verifier')==1
    assert n.effective_depth()==0


@pytest.mark.parametrize('event',['representation_activation_verified','representation_activation_fact_admitted',
                                  'representation_activation_saved','representation_activation_completed'])
def test_activation_crash_replays_only_confirmed_verifier_and_mutation(tmp_path,event):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    def crash(name,details):
        if name==event:raise Crash()
    with pytest.raises(Crash):activate_ready(runner(tmp_path,model,crash),n)
    activate_ready(runner(tmp_path,model),ContinuousNetwork(tmp_path))
    assert model.calls.count('representation_activation_verifier')==1
    assert ContinuousNetwork(tmp_path).alias_of(row['claim_id'])==n.target_id
    assert len(list((tmp_path/'facts').glob('*.md')))==4


@pytest.mark.parametrize('revoke',['helper','conditional','activation'])
def test_revocation_after_activation_fails_closed_and_restores_new_claim(tmp_path,revoke):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    run=runner(tmp_path,model)
    activate_ready(run,n)
    fid={'helper':h.fact_id,'conditional':row['conditional_fact_id'],
         'activation':n.data['representations'][row['support_id']]['equivalence_fact_id']}[revoke]
    FactGraph(tmp_path).revoke(fid,'Independent revocation.')
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(row['claim_id']) is None
    assert not n.study_suppressed(row['claim_id'])
    run.restore_revoked_alias_studies(n)
    assert 'study-'+row['claim_id'] in run.state['studies']
    activate_ready(run,n)
    assert model.calls.count('representation_activation_verifier')==1


def test_refuted_helper_releases_new_claim_without_ancestor_refutation(tmp_path):
    execute(tmp_path,Conditional())
    n,row=deferred(tmp_path)
    helper=n.claim(row['helper_claim_id'])
    record=Refutation.create(helper,'Deterministic verified counterexample.',
        {'accepted':True,'assumptions_satisfied':True,'conclusion_falsified':True,'closed_book_clean':True,'reason':'Test oracle.'},
        {'verifier_call':'independent deterministic oracle'})
    RefutationStore(tmp_path).admit(record)
    n.bind_refutation(helper.obligation_id,record.refutation_id)
    n=ContinuousNetwork(tmp_path)
    assert not n.study_suppressed(row['claim_id'])
    run=runner(tmp_path,Conditional())
    run.restore_revoked_alias_studies(n)
    assert 'study-'+row['claim_id'] in run.state['studies']
    assert n.truth(n.target_id)==n.truth(row['claim_id'])=='OPEN'
    assert (tmp_path/'facts'/(row['conditional_fact_id']+'.md')).exists()


@pytest.mark.parametrize('failure',['reject','timeout','interrupted'])
def test_activation_failure_releases_new_claim_no_retry(tmp_path,failure):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    if failure=='reject':model.conditional_checks=False
    if failure=='timeout':model.failure='representation_activation_verifier'
    if failure=='interrupted':
        def crash(name,details):
            if name=='call_started':raise Crash()
        with pytest.raises(Crash):activate_ready(runner(tmp_path,model,crash),n)
    run=runner(tmp_path,model)
    activate_ready(run,ContinuousNetwork(tmp_path))
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(row['claim_id']) is None
    assert not n.study_suppressed(row['claim_id'])
    run.restore_revoked_alias_studies(n)
    assert 'study-'+row['claim_id'] in run.state['studies']
    activate_ready(run,n)
    assert model.calls.count('representation_activation_verifier')==(0 if failure=='interrupted' else 1)


def test_normal_resume_activates_before_new_selection_not_inside_pending_worker(tmp_path):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    def stop_activation(name,details):
        if name=='representation_activation_completed':raise RunStopped('activation boundary')
    result=resume_run(tmp_path,invoker=model,on_event=stop_activation)
    assert result['pause_reason']=='activation boundary'
    assert model.calls[-1]=='representation_activation_verifier'
    assert model.calls.count('continuous_worker')==1
    assert 'continuous_selector' not in model.calls
    assert ContinuousNetwork(tmp_path).alias_of(row['claim_id'])==n.target_id


def test_helper_is_not_recursively_sent_to_recurrence_planning(tmp_path):
    execute(tmp_path,Conditional())
    n,row=deferred(tmp_path)
    helper=n.claim(row['helper_claim_id'])
    candidate={'kind':'SUPPORT','goal':helper.goal,'context':helper.context,'requirements':[{'goal':'Next helper','context':''}]}
    assert prepare_origin(n,{'study':{'claim_id':helper.obligation_id}},candidate) is None


@pytest.mark.parametrize('check',ACTIVATION_CHECKS)
def test_every_activation_check_is_required(tmp_path,check):
    class Rejected(Conditional):
        def invoke(self,**kwargs):
            result=super().invoke(**kwargs)
            if kwargs['label']=='representation_activation_verifier':result[check]=False
            return result
    model=Rejected()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    activate_ready(runner(tmp_path,model),n)
    n=ContinuousNetwork(tmp_path)
    assert n.alias_of(row['claim_id']) is None
    assert not n.study_suppressed(row['claim_id'])


@pytest.mark.parametrize('which',['conditional','activation'])
def test_frozen_packet_corruption_fails_closed_on_reload(tmp_path,which):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    if which=='activation':activate_ready(runner(tmp_path,model),n)
    path=tmp_path/row['evidence_ref']
    if which=='activation':path=path/'activation'
    packet=read_json(path/'packet.json')
    packet['ancestor']['goal']='Changed semantic interface.'
    from research.run_storage import write_json
    write_json(path/'packet.json',packet)
    with pytest.raises(ValueError,match='interface'):
        ContinuousNetwork(tmp_path)


@pytest.mark.parametrize('mode',['timeout','error','interrupted'])
def test_conditional_verifier_failure_never_creates_helper_or_retries(tmp_path,mode):
    class Failure(Conditional):
        def invoke(self,**kwargs):
            if mode=='error' and kwargs['label']=='conditional_representation_verifier':
                self.calls.append(kwargs['label'])
                raise RuntimeError('Deterministic invocation failure.')
            return super().invoke(**kwargs)
    model=Failure(failure='conditional_representation_verifier' if mode=='timeout' else None)
    if mode=='interrupted':
        def crash(name,details):
            if name=='call_started' and details.get('label')=='conditional_representation_verifier':raise Crash()
        with pytest.raises(Crash):execute(tmp_path,model,crash)
        result=resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    else:result=execute(tmp_path,model)
    n=ContinuousNetwork(tmp_path)
    assert not n.data.get('deferred_representations')
    assert len(n.data['obligations'])==2 and len(result['studies'])==2
    assert model.calls.count('conditional_representation_verifier')==(0 if mode=='interrupted' else 1)


def test_frozen_worker_visit_finishes_before_activation(tmp_path):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    state=read_json(tmp_path/'continuous_run/state.json')
    directory=tmp_path/'continuous_run'
    # The existing selected Worker packet is execution state, not a new choice.
    study=read_json(directory/state['studies']['study-'+n.target_id])
    from research.run_storage import write_json
    write_json(directory/f"visits/{state['step']:08d}/packet.json",{
        'study':study,'claim':asdict(n.claim(n.target_id)),'operation':'ADVANCE',
        'accepted_facts':[],'required_fact_ids':[]})
    class PendingWorker(Conditional):
        def invoke(self,**kwargs):
            if kwargs['label']=='continuous_worker':
                self.calls.append(kwargs['label'])
                return {'continuation':'Saved local work.','next_work':'Continue.','candidate':None}
            return super().invoke(**kwargs)
    model=PendingWorker()
    resume_run(tmp_path,invoker=model,on_event=stop(tmp_path))
    assert model.calls==['continuous_worker']
    assert ContinuousNetwork(tmp_path).alias_of(row['claim_id']) is None


@pytest.mark.parametrize('boundary',['call_started','representation_activation_verified'])
@pytest.mark.parametrize('revoke',['helper','conditional'])
def test_revocation_during_interrupted_activation_releases_n_without_reselecting_fact(tmp_path,boundary,revoke):
    model=Conditional()
    execute(tmp_path,model)
    n,row,h=prove_helper(tmp_path)
    def crash(event,details):
        if event==boundary:raise Crash()
    with pytest.raises(Crash):activate_ready(runner(tmp_path,model,crash),n)
    FactGraph(tmp_path).revoke(h.fact_id if revoke=='helper' else row['conditional_fact_id'],'Revoked during interruption.')
    run=runner(tmp_path,model)
    activate_ready(run,ContinuousNetwork(tmp_path))
    n=ContinuousNetwork(tmp_path)
    assert not n.study_suppressed(row['claim_id']) and n.alias_of(row['claim_id']) is None
    run.restore_revoked_alias_studies(n)
    assert 'study-'+row['claim_id'] in run.state['studies']
    assert read_json(tmp_path/row['evidence_ref']/'activation/result.json')['status']=='ERROR'
    assert model.calls.count('representation_activation_verifier')==(0 if boundary=='call_started' else 1)
    if boundary=='call_started':
        assert list((tmp_path/'continuous_run/calls').glob('*/interrupted.json'))
    activate_ready(run,n)
    assert model.calls.count('representation_activation_verifier')==(0 if boundary=='call_started' else 1)
