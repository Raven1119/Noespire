"""Local evidence changes action inputs without changing proof authority."""
import json
from copy import deepcopy

import pytest

from research.continuous_attention import bounded_packet
from research.continuous_network import ContinuousNetwork
from research.continuous_research import _Research
from research.continuous_selection import fact_page, INSTRUCTIONS
from research.graph import FactGraph
from research.run_storage import read_json, write_json
from test_bridge_discovery import accepted, study, snapshot, Crash


def fixture(root, *, large=False):
    net = ContinuousNetwork.create(root, 'local-action', 'Investigate a bound for a sequence.')
    a = accepted(root, net, 'For every positive x, P(x) <= 20. ' + ('Details. '*110 if large else ''), '')
    b = accepted(root, net, 'For every negative x, P(x) <= 10. ' + ('Conditions. '*100 if large else ''), '')
    foreign = accepted(root, net, 'P(x) = 1.', 'Assume x = 1.')
    target, ref = study(root, 'study-'+net.target_id, claim_id=net.target_id,
                        focus='Investigate a bound for a sequence.', known_fact_ids=[a.fact_id,b.fact_id,foreign.fact_id])
    state = {'run_id':'local-evidence', 'step':1, 'studies':{target['study_id']:ref},
        'schedule':{'channel_cursor':4,'revisit_snapshot':[target['study_id']],'revisit_cursor':0},
        'settings':{'selector_context_tokens':8000,'worker_context_tokens':64000,'verifier_context_tokens':96000},
        'retries':{},'acknowledged_pauses':[]}
    return net, target, state, (a,b,foreign)


def decision(target, refs=(), reason='Study x<0; do not use the positive-domain bound. Derive a recurrence and leave its boundary gap.'):
    return {'study_id':target['study_id'],'operation':'ADVANCE','support_id':'',
            'material_refs':list(refs),'reason':reason,'relation':'UNKNOWN','continuation_window':None}


def test_complete_interfaces_keep_different_conditions_and_do_not_scan_unexposed_graph(tmp_path):
    net, target, state, facts = fixture(tmp_path)
    unrelated = accepted(tmp_path,net,'UNEXPOSED SECRET RESULT.', '')
    before = snapshot(tmp_path)
    exposure = _Research(tmp_path,state,None,None).selector_exposure(net,{target['study_id']:target})['exposure']
    rows = exposure['fact_interfaces']['items']
    assert {r['exact_statement'] for r in rows} == {f.statement for f in facts}
    assert [r['source_scope'] for r in rows] == ['', '', 'Assume x = 1.']
    assert all(r['authority']=='SOURCE_INTERFACE_ONLY' for r in rows)
    assert 'accepted_facts' not in exposure and unrelated.fact_id not in json.dumps(exposure)
    assert 'positive x' in rows[0]['exact_statement'] and 'negative x' in rows[1]['exact_statement']
    assert 'larger' in INSTRUCTIONS and 'conditions' in INSTRUCTIONS
    assert snapshot(tmp_path)==before


@pytest.mark.parametrize('boundary',[None,'call_completed','selection_saved'])
@pytest.mark.parametrize('use',[False,True])
def test_reasonable_nonuse_or_explicit_use_reaches_worker_action_and_recovers_once(tmp_path,boundary,use):
    net,target,state,facts=fixture(tmp_path);schedule=deepcopy(state['schedule']);calls=[]
    reason='Study negative x using its bound; positive x does not apply. New work: derive a recurrence, retain the open boundary step.'
    class Selector:
        def invoke(self,*,prompt,schema,label):
            calls.append(label)
            p=json.loads(prompt.split('\nPACKET:\n')[1])
            assert {r['exact_statement'] for r in p['fact_interfaces']['items']}=={f.statement for f in facts}
            assert 'what is new' in prompt and 'why not' in prompt and 'resumable' in prompt
            return decision(target,['fact:'+facts[1].fact_id] if use else [],reason)
    def crash(event,details):
        if event==boundary:raise Crash()
    if boundary:
        with pytest.raises(Crash):_Research(tmp_path,state,Selector(),crash).select_work(net)
    out=_Research(tmp_path,state,Selector(),None).select_work(net)
    saved=snapshot(tmp_path)
    assert _Research(tmp_path,state,Selector(),None).select_work(net)==out
    assert snapshot(tmp_path)==saved and calls==['continuous_selector']
    assert out['action']==reason and out['relation']=='UNKNOWN'
    assert [f['fact_id'] for f in out['accepted_facts']]==([facts[1].fact_id] if use else [])
    assert state['schedule']==schedule and net.truth(net.target_id)=='OPEN'
    assert len(list((tmp_path/'facts').glob('*.md')))==3


def test_foreign_interface_seen_is_not_permission_to_use(tmp_path):
    net,target,state,facts=fixture(tmp_path)
    class Selector:
        def invoke(self,**kw):return decision(target,['fact:'+facts[2].fact_id])
    with pytest.raises(ValueError,match='exact scope'):
        _Research(tmp_path,state,Selector(),None).select_work(net)
    assert net.truth(net.target_id)=='OPEN'


def test_revoked_fact_and_unbound_candidate_notes_cannot_supply_interfaces(tmp_path):
    net,target,state,facts=fixture(tmp_path)
    FactGraph(tmp_path).revoke(facts[0].fact_id,'fixture')
    target['known_fact_ids'] += ['not-an-accepted-fact']
    target['continuation']='Candidate only: P(x) <= 0 for all x.'
    page=fact_page(net,[target],token_budget=2000)
    assert {r['ref'] for r in page['items']}=={'fact:'+f.fact_id for f in facts[1:]}
    assert 'Candidate only' not in json.dumps(page)


def test_pages_keep_whole_interfaces_and_skip_individually_oversized_statements(tmp_path):
    net,target,state,facts=fixture(tmp_path,large=True)
    huge=accepted(tmp_path,net,'Hypotheses: '+('essential condition; '*800)+' conclusion.', '')
    target['known_fact_ids'].insert(1,huge.fact_id)
    all_rows=[];pages=[];offset=0
    while True:
        page=fact_page(net,[target],offset,token_budget=450);bounded_packet({'fact_interfaces':page},450)
        all_rows+=page['items'];pages.append(page)
        if not page['next_ref']:break
        new_offset=int(page['next_ref'].split(':')[1]);assert new_offset>offset;offset=new_offset
    assert len(pages)>1
    assert {r['exact_statement'] for r in all_rows}=={f.statement for f in facts}
    assert any(n['ref']=='fact:'+huge.fact_id for p in pages for n in p['unexpanded'])


@pytest.mark.parametrize('boundary',[None,'selector_page_saved','call_completed','selection_saved'])
def test_requested_page_is_read_before_action_without_service_or_duplicate_calls(tmp_path,boundary):
    net,target,state,facts=fixture(tmp_path,large=True)
    # Keep normal minimum 2048; large indivisible interfaces fit one page each.
    state['settings']['selector_context_tokens']=4096
    cards=[target]
    first=fact_page(net,cards,token_budget=1024)
    # More interfaces create a real forward page within the unchanged capacity.
    for i in range(4):
        f=accepted(tmp_path,net,f'For integer j={i}, '+('P(j) is defined. '*100)+' P(j)>=0.', '')
        target['known_fact_ids'].append(f.fact_id)
    write_json(tmp_path/'continuous_run'/next(iter(state['studies'].values())),target)
    calls=[]
    class Selector:
        def invoke(self,*,prompt,schema,label):
            calls.append(prompt);p=json.loads(prompt.split('\nPACKET:\n')[1])
            page=p['fact_interfaces']
            if len(calls)==1:
                assert 'INSPECT' in schema['properties']['operation']['enum'] and page['next_ref']
                return {**decision(target,[page['next_ref']]),'operation':'INSPECT'}
            assert page!=first
            assert p['inspection_request_unverified']['reason']==decision(target)['reason']
            assert p['inspection_request_unverified']['material_refs'][0].startswith('fact-interfaces:')
            return decision(target)
    fired=False
    def crash(event,details):
        nonlocal fired
        if event==boundary and not fired:fired=True;raise Crash()
    if boundary:
        with pytest.raises(Crash):_Research(tmp_path,state,Selector(),crash).select_work(net)
    out=_Research(tmp_path,state,Selector(),None).select_work(net)
    assert len(calls)==2 and out['accepted_facts']==[]
    assert state['schedule']['revisit_cursor']==0
    assert len(list((tmp_path/'continuous_run/calls').glob('*/request.json')))==2
    assert not list((tmp_path/'continuous_run/visits').glob('*/worker_result.json'))
    before=snapshot(tmp_path);_Research(tmp_path,state,Selector(),None).select_work(net)
    assert len(calls)==2 and snapshot(tmp_path)==before


def test_arbitrary_or_repeated_page_is_not_an_implicit_resampling_loop(tmp_path):
    net,target,state,_=fixture(tmp_path)
    class Selector:
        def invoke(self,**kw):return {**decision(target,['fact-interfaces:0']),'operation':'INSPECT'}
    with pytest.raises(ValueError,match='advertised forward'):
        _Research(tmp_path,state,Selector(),None).select_work(net)


def test_many_small_results_page_at_sixteen_without_changing_fact_authority(tmp_path):
    net,target,state,_=fixture(tmp_path)
    target['known_fact_ids']=[]
    for i in range(19):
        f=accepted(tmp_path,net,f'{i} + 0 = {i}.','')
        target['known_fact_ids'].append(f.fact_id)
    first=fact_page(net,[target],token_budget=8000)
    assert len(first['items'])==16 and first['next_ref']=='fact-interfaces:16'
    assert len(fact_page(net,[target],16,token_budget=8000)['items'])==3
    for key in target['known_fact_ids'][:16]:FactGraph(tmp_path).revoke(key,'fixture')
    first=fact_page(net,[target],token_budget=8000)
    assert not first['items'] and first['next_ref']=='fact-interfaces:16'


def test_full_existing_foreign_navigation_does_not_advertise_an_empty_fact_page(tmp_path):
    from research.continuous_selection import add_fact_interfaces
    net,target,state,_=fixture(tmp_path)
    target['known_fact_ids']=[]
    exposure={'cards':[target], 'bridge_candidates':[{'existing':'x'*1850}], 'bridge_candidate_pages':[]}
    result=add_fact_interfaces(net,exposure,token_budget=512)
    assert result['fact_interfaces']=={'items':[],'unexpanded':[],'next_ref':None}
    assert result['bridge_candidates']==exposure['bridge_candidates']
