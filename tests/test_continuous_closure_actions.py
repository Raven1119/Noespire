"""CLOSE frames local work; it never schedules it or certifies its notes."""
from copy import deepcopy
import json

import pytest

from research import continuous_research as research
from research.continuous_network import ContinuousNetwork
from research.continuous_attention import bounded_packet
from research.continuous_selection import action_metadata, CLOSE_INSTRUCTIONS
from research.research_delivery import DeliveryStore, MARKER, study_view
from research.run_storage import read_json, write_json
from test_continuous_selection import fixture, decision
from test_bridge_discovery import snapshot, Crash


def action(study, mode="CLOSE", refs=()):
    return {**decision(study), "action_mode": mode,
        "local_object": "The fixed rational sequence in the recorded calculation.",
        "proposed_boundary": "A finite prefix identity, without the infinite target claim.",
        "remaining_gap": "Justify its endpoint and state the finite quantifiers.",
        "expected_deliverable": "A self-contained local Fact, or the exact remaining closing gap.",
        "evidence_refs": list(refs), "reason": "The explicit object is fixed and only the stated endpoint remains."}


def notes(root, state, study, content=None):
    packet={"study":study,"accepted_facts":[]}
    call=root/'continuous_run/calls'/('f'*64)
    write_json(call/'request.json',{"label":"continuous_worker","scope":"0:worker:retry-0",
        "prompt":research.worker_prompt(packet),"schema":research._WORKER_SCHEMA})
    write_json(call/'result.json',{"status":"TIMEOUT","timeout":600})
    store=DeliveryStore(root/'continuous_run',state['run_id'])
    c=content or {"goal":study['focus'],"context":study['scope'],
        "derivation":"Fix the sequence b_j=1/(j+1), j=0,1,2. Its first difference telescopes.",
        "obstruction":"The last endpoint equality still needs to be justified.",
        "next_work":"State the finite quantifiers and check the endpoint.","materials_used":[]}
    assert store.capture(call,packet,MARKER+json.dumps(c))
    return store,study_view(store,study)


@pytest.mark.parametrize('boundary',[None,'call_completed','selection_saved'])
def test_explicit_object_can_close_with_confirmed_action_recovery(tmp_path,boundary):
    net,target,state,facts=fixture(tmp_path);store,view=notes(tmp_path,state,target)
    before=deepcopy(state['schedule']);calls=[];selected=[]
    class Selector:
        def invoke(self,*,prompt,schema,label):
            calls.append(label);p=json.loads(prompt.split('\nPACKET:\n')[1])
            assert schema['properties']['action_mode']['enum']==['RESEARCH','CLOSE']
            rows=p['local_action_evidence']['items']
            item=next(r for r in rows if r['study_id']==target['study_id'])
            assert 'b_j=1/(j+1)' in item['continuation'] and item['verified'] is False
            result=action(target,refs=[item['ref']]);selected.append(result);return result
    fired=False
    def crash(event,details):
        nonlocal fired
        if event==boundary and not fired:fired=True;raise Crash()
    if boundary:
        with pytest.raises(Crash):research._Research(tmp_path,state,Selector(),crash).select_work(net)
    packet=research._Research(tmp_path,state,Selector(),None).select_work(net)
    assert calls==['continuous_selector'] and packet['action_mode']=='CLOSE'
    assert packet['proposed_boundary']==selected[0]['proposed_boundary']
    assert packet['accepted_facts']==[] and state['schedule']==before
    assert net.truth(net.target_id)=='OPEN'
    frozen=snapshot(tmp_path)
    assert research._Research(tmp_path,state,Selector(),None).select_work(net)==packet
    assert snapshot(tmp_path)==frozen
    prompt=research.worker_prompt(packet)
    assert CLOSE_INSTRUCTIONS in prompt and 'smaller complete Fact' in prompt
    assert not list((tmp_path/'continuous_run/visits').glob('*/worker_result.json'))


@pytest.mark.parametrize('checkpoint',[False,True])
def test_vague_work_and_checkpoint_may_stay_research(tmp_path,checkpoint):
    net,target,state,_=fixture(tmp_path)
    target['continuation']='Explore some sequence transformations; no fixed object or proposition yet.'
    write_json(tmp_path/'continuous_run'/state['studies'][target['study_id']],target)
    if checkpoint:
        notes(tmp_path,state,target,{"goal":target['focus'],"context":target['scope'],
            "derivation":target['continuation'],"obstruction":"Neither representation nor scope is stable.",
            "next_work":"Compare two possible representations.","materials_used":[]})
    class Selector:
        def invoke(self,*,prompt,**kw):
            assert 'not a timeout count' in prompt
            s=action(target,'RESEARCH');s['reason']='Current materials do not yet define a stable proposition.'
            return s
    p=research._Research(tmp_path,state,Selector(),None).select_work(net)
    assert p['action_mode']=='RESEARCH' and CLOSE_INSTRUCTIONS not in research.worker_prompt(p)
    assert 'stable proposition' in p['action']


def test_timeout_counter_cannot_change_closure_exposure(tmp_path):
    net,target,state,_=fixture(tmp_path);store,view=notes(tmp_path,state,target)
    run=research._Research(tmp_path,state,None,None)
    a=run.selector_exposure(net,{target['study_id']:view})
    for n in range(6):write_json(run.directory/'calls'/str(n)/'result.json',{'status':'TIMEOUT','timeout':600})
    state['timeout_count']=1000;view['timeout_count']=1000
    b=run.selector_exposure(net,{target['study_id']:view})
    assert a==b and 'timeout_count' not in json.dumps(a)


def test_full_research_evidence_is_bounded_and_never_scans_unexposed_studies(tmp_path):
    net,target,state,_=fixture(tmp_path)
    target['continuation']='indivisible essential condition '*5000
    hidden={**target,'study_id':'unexposed','continuation':'UNEXPOSED SECRET'}
    write_json(tmp_path/'continuous_run/studies/unexposed/000000.json',hidden)
    run=research._Research(tmp_path,state,None,None)
    p=run.selector_exposure(net,{target['study_id']:target})['exposure']
    assert 'UNEXPOSED SECRET' not in json.dumps(p)
    assert not p['local_action_evidence']['items'] and p['local_action_evidence']['unexpanded']
    bounded_packet({'prompt':__import__('research.continuous_selection',fromlist=['INSTRUCTIONS']).INSTRUCTIONS+json.dumps(p,ensure_ascii=False),
                    'schema':research._SELECTOR_SCHEMA},state['settings']['selector_context_tokens'])
    assert target['continuation'] not in json.dumps(p)


def test_close_needs_a_complete_non_authoritative_action_interface():
    s=action({'study_id':'study-x'},refs=['study:study-x'])
    assert action_metadata(s)['action_mode']=='CLOSE'
    for key in ['local_object','proposed_boundary','remaining_gap','expected_deliverable']:
        with pytest.raises(ValueError,match='CLOSE'):action_metadata({**s,key:''})
    with pytest.raises(ValueError,match='evidence'):action_metadata({**s,'evidence_refs':[]})
    with pytest.raises(ValueError):action_metadata({**s,'action_mode':'FORCE_FACT'})
    assert action_metadata(decision({'study_id':'study-x'}))=={} # old frozen decisions remain implicit RESEARCH


@pytest.mark.parametrize('candidate',[False,True])
def test_close_can_shrink_or_leave_gap_without_extra_service(tmp_path,candidate):
    calls=[];packets=[]
    class Backend:
        def invoke(self,*,prompt,schema,label):
            calls.append(label)
            if label=='closed_book_verifier':
                assert '1 + 1 = 2' in prompt
                return {'accepted':True,'external_authority_dependency':False,'violation_type':'NONE','reason':'Elementary arithmetic.'}
            p=json.loads(prompt.split('\nPACKET:\n')[1])
            if label=='continuous_selector':
                return action(p['cards'][0],refs=[p['local_action_evidence']['items'][0]['ref']])
            packets.append(p)
            result=None
            if len(packets)>1:
                assert p['action_mode']=='CLOSE' and 'shrink' in prompt
                if candidate:result={'kind':'FACT','context':'','goal':'1 + 1 = 2','proof':'By addition, 1 + 1 = 2.', 'predecessors':[], 'requirements':[]}
            return {'continuation':'Fixed endpoint identity: 1+1=2. The infinite estimate remains unproved.',
                'next_work':'Determine the exact infinite estimate gap.','context_requests':[], 'definitions':[], 'new_study':None,'candidate':result}
    backend=Backend()
    def pause(event,details):
        if event=='visit_completed':research.pause_run(tmp_path,'one slice')
    first=research.start_run(tmp_path,problem_id='closing',statement='An infinite estimate for all indices.',invoker=backend,on_event=pause)
    before=deepcopy(first['schedule'])
    second=research.resume_run(tmp_path,invoker=backend,on_event=pause)
    assert second['step']==2 and second['target_state']=='OPEN' and len(packets)==2
    assert second['schedule']['channel_cycle']==before.get('channel_cycle',['ADVANCE']*3+['EXPLORE','REVISIT'])
    assert calls.count('continuous_selector')==1
    assert len(list((tmp_path/'facts').glob('*.md')))==int(candidate)
    assert packets[1]['accepted_facts']==[]
    assert not ContinuousNetwork(tmp_path).data['supports']


@pytest.mark.parametrize('channel', ['ADVANCE', 'EXPLORE', 'REVISIT'])
def test_close_is_possible_within_each_existing_channel(tmp_path, channel):
    net,target,state,_=fixture(tmp_path);notes(tmp_path,state,target)
    state['schedule']['channel_cursor']={'ADVANCE':0,'EXPLORE':3,'REVISIT':4}[channel]
    before=deepcopy(state['schedule'])
    class Selector:
        def invoke(self, *, prompt, **kw):
            p=json.loads(prompt.split('\nPACKET:\n')[1])
            assert p['channel']==channel
            return action(target,refs=[p['local_action_evidence']['items'][0]['ref']])
    packet=research._Research(tmp_path,state,Selector(),None).select_work(net)
    assert packet['action_mode']=='CLOSE' and packet['channel']==channel
    assert state['schedule']==before


def test_public_artifact_without_checkpoint_is_visible_but_cannot_be_predecessor(tmp_path):
    from test_research_artifacts import Backend, start, pause
    class Closing(Backend):
        def invoke(self, *, prompt, schema, label):
            assert label=='continuous_selector'  # no Verifier for illegal predecessor
            self.calls.append(label)
            p=json.loads(prompt.split('\nPACKET:\n')[1])
            rows=p['local_action_evidence']['items']
            self.ref=next(r['ref'] for r in rows if 'first endpoint is 1' in r.get('text',''))
            assert all(r['verified'] is False for r in rows)
            assert not any('private note' in str(r) for r in rows)
            return action(p['cards'][0],refs=[self.ref])
        def invoke_with_messages(self, *, prompt, schema, label, on_message):
            response=super().invoke_with_messages(prompt=prompt,schema=schema,label=label,on_message=on_message)
            response['candidate']['predecessors']=[self.ref]
            return response
    backend=Closing(tmp_path,candidate=True)
    start(tmp_path,backend)
    result=research.resume_run(tmp_path,invoker=backend,on_event=pause(tmp_path))
    verification=read_json(tmp_path/'continuous_run/visits/00000001/verification.json')
    assert not verification['accepted'] and 'MECHANICAL_REJECTION' in verification['reason']
    assert not list((tmp_path/'facts').glob('*.md')) and result['target_state']=='OPEN'
    assert backend.packets[1]['accepted_facts']==[] and result['step']==2


def test_action_cannot_cite_unexposed_global_evidence(tmp_path):
    net,target,state,_=fixture(tmp_path)
    class Selector:
        def invoke(self, **kw):return action(target,refs=['research-artifact:'+'0'*32])
    with pytest.raises(ValueError,match='unexposed evidence'):
        research._Research(tmp_path,state,Selector(),None).select_work(net)
    assert not (tmp_path/'continuous_run/visits/00000001/selection.json').exists()
