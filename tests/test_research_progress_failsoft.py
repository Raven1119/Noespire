"""Advisory errors must not veto an otherwise authorized mathematical action."""
from copy import deepcopy
import pytest
from research.continuous_research import _Research
from research.research_progress import project_assessment, record_assessment, fit_worker_advisory, AUTHORITY
from research.run_storage import read_json, write_json
from research.graph import FactGraph
from test_continuous_selection import fixture, decision
from test_research_progress import assessment
from test_bridge_discovery import snapshot, Crash


@pytest.mark.parametrize("invalid", ["notes", [], 4, {"covered_by":"a theorem"},
    {"judgments": None}, {"judgments":[False]}])
@pytest.mark.parametrize("boundary", [None,"call_completed","selection_saved"])
def test_bad_advisory_keeps_raw_and_services_legal_action_without_recall(tmp_path,invalid,boundary):
    net,target,state,facts=fixture(tmp_path); calls=[]; schedule=deepcopy(state['schedule'])
    original={**decision(target,['fact:'+facts[0].fact_id]),'research_assessment':invalid}
    class Selector:
        def invoke(self,**kw):calls.append(kw['label']);return deepcopy(original)
    def crash(event,details):
        if event==boundary:raise Crash()
    if boundary:
        with pytest.raises(Crash):_Research(tmp_path,state,Selector(),crash).select_work(net)
    run=_Research(tmp_path,state,Selector(),None);packet=run.select_work(net)
    assert calls==['continuous_selector'] and state['schedule']==schedule
    assert [f['fact_id'] for f in packet['accepted_facts']]==[facts[0].fact_id]
    assert 'research_assessment_unverified' not in packet
    assert read_json(run.step_dir/'selection.json')['selected']==original
    receipt=read_json(run.step_dir/'research_assessment.json')
    assert receipt['status']=='DROPPED' and receipt['diagnostics'] and receipt['content'] is None
    before=snapshot(tmp_path);assert run.select_work(net)==packet and snapshot(tmp_path)==before
    assert len(calls)==1 and net.truth(net.target_id)=='OPEN' and not net.data['supports']


def test_subject_evidence_and_explanation_are_independent(tmp_path):
    net,target,state,facts=fixture(tmp_path);value=assessment(facts)
    work='research-object:local'
    value['judgments'][0]['work_refs']=[work]
    # Prose is never parsed as a Fact ID, nor is a semantic assertion endorsed.
    value['judgments'][0]['explanation']='The verified positive-domain theorem covers this work; UNKNOWN if this assertion is mathematically right.'
    run=_Research(tmp_path,state,None,None)
    shown=run.selector_exposure(net,{target['study_id']:target})['exposure']['fact_interfaces']['items']
    before=snapshot(tmp_path)
    result=project_assessment({'research_assessment':value},{r['ref']:r for r in shown},[work],net)
    assert result['status']=='USABLE' and result['authority']==AUTHORITY and result['content']==value
    assert snapshot(tmp_path)==before
    value['judgments'][0]['evidence_fact_refs']=[]
    assert project_assessment({'research_assessment':value},{},[work],net)['status']=='USABLE'


@pytest.mark.parametrize('mutation',[
    lambda a:a['judgments'][0]['evidence_fact_refs'].append('fact:not-exposed'),
    lambda a:a['judgments'][0].update(evidence_fact_refs='explanation'),
    lambda a:a['judgments'][0].update(work_refs=['fact:unknown']),
    lambda a:a['judgments'][0].update(explanation={'not':'text'}),
    lambda a:a.update(established='x'*9000),
])
def test_invalid_relations_and_oversized_text_drop_only_advisory(tmp_path,mutation):
    net,target,state,facts=fixture(tmp_path);value=assessment(facts);mutation(value)
    class Selector:
        def invoke(self,**kw):return {**decision(target),'research_assessment':value}
    run=_Research(tmp_path,state,Selector(),None);packet=run.select_work(net)
    assert 'research_assessment_unverified' not in packet and packet['accepted_facts']==[]
    assert read_json(run.step_dir/'research_assessment.json')['status']=='DROPPED'


@pytest.mark.parametrize('problem',['unexposed_evidence','scope','operation','object'])
def test_bad_advisory_does_not_soften_actual_authority_error(tmp_path,problem):
    net,target,state,facts=fixture(tmp_path)
    selected={**decision(target),'research_assessment':{'bad':'advisory'}}
    if problem=='unexposed_evidence':selected['evidence_refs']=['some/private/path.json']
    if problem=='scope':selected['material_refs']=['fact:'+facts[2].fact_id]
    if problem=='operation':selected['operation']='SOLVE_WITHOUT_VERIFIER'
    if problem=='object':selected['selected_object_id']='research-object:not-shown'
    class Selector:
        def invoke(self,**kw):return selected
    before=deepcopy(state['schedule'])
    with pytest.raises(ValueError):_Research(tmp_path,state,Selector(),None).select_work(net)
    assert state['schedule']==before and net.truth(net.target_id)=='OPEN'


def test_recovery_rechecks_advisory_sources_but_keeps_original_receipt(tmp_path):
    net,target,state,facts=fixture(tmp_path);run=_Research(tmp_path,state,None,None)
    exposure=run.selector_exposure(net,{target['study_id']:target})['exposure']
    selected={**decision(target),'research_assessment':assessment(facts)}
    assert record_assessment(run.step_dir,selected,exposure,net)['status']=='USABLE'
    receipt=(run.step_dir/'research_assessment.json').read_bytes()
    FactGraph(tmp_path).revoke(facts[0].fact_id,'test')
    assert record_assessment(run.step_dir,selected,exposure,net)['status']=='DROPPED'
    assert (run.step_dir/'research_assessment.json').read_bytes()==receipt
    selected['reason']='changed confirmed action'
    with pytest.raises(ValueError,match='confirmed selection changed'):
        record_assessment(run.step_dir,selected,exposure,net)


def test_optional_advisory_cannot_block_full_worker_packet_or_change_recovery(tmp_path):
    from research.research_delivery import worker_packet
    from research.continuous_attention import bounded_packet
    from research.continuous_research import worker_prompt,_WORKER_SCHEMA
    net,target,state,facts=fixture(tmp_path)
    class Selector:
        def invoke(self,**kw):return decision(target)
    run=_Research(tmp_path,state,Selector(),None);packet=run.select_work(net)
    _,measurement=bounded_packet({'prompt':worker_prompt(packet),'schema':_WORKER_SCHEMA},64000)
    state['settings']['worker_context_tokens']=measurement['estimated_tokens']+20
    packet['research_assessment_unverified']={'authority':AUTHORITY,'content':'x'*1000}
    before=deepcopy(state['schedule']);out=worker_packet(run,packet)
    assert 'research_assessment_unverified' not in out
    assert out['accepted_facts']==packet['accepted_facts'] and state['schedule']==before
    bounded_packet({'prompt':worker_prompt(out),'schema':_WORKER_SCHEMA},state['settings']['worker_context_tokens'])
    assert read_json(run.step_dir/'research_assessment_capacity.json')['status']=='DROPPED'
    saved=snapshot(tmp_path);assert worker_packet(run,packet)==out and snapshot(tmp_path)==saved


def test_public_artifacts_have_priority_over_optional_judgment(tmp_path):
    from test_research_artifacts import Backend,start
    from research.research_delivery import worker_packet
    from research.continuous_attention import bounded_packet
    from research.continuous_research import worker_prompt,_WORKER_SCHEMA
    actor=Backend(tmp_path,checkpoint=True);start(tmp_path,actor)
    state=read_json(tmp_path/'continuous_run/state.json')
    state['acknowledged_pauses']=[p.name for p in (tmp_path/'continuous_run/pause_requests').glob('*.json')]
    net=__import__('research.continuous_network',fromlist=['ContinuousNetwork']).ContinuousNetwork(tmp_path)
    run=_Research(tmp_path,state,actor,None);packet=run.select_work(net)
    # Freeze the ordinary input first, retaining its checkpoint and public work.
    full=worker_packet(run,packet)
    expected=deepcopy(full['research_handover']['public_messages']);assert len(expected)>=2
    (run.step_dir/'worker-input-retry-0.json').unlink()
    _,size=bounded_packet({'prompt':worker_prompt(full),'schema':_WORKER_SCHEMA},64000)
    state['settings']['worker_context_tokens']=size['estimated_tokens']+20
    packet['research_assessment_unverified']={'authority':AUTHORITY,'content':'x'*8000}
    out=worker_packet(run,packet)
    assert 'research_assessment_unverified' not in out
    assert out['research_handover']['public_messages']==expected
    assert out['research_checkpoint']==full['research_checkpoint']
    assert out['study']==full['study']
