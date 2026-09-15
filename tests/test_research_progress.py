"""Research judgments survive selection and paging without becoming proof truth."""
from copy import deepcopy
import json
import pytest

from research.continuous_research import _Research
from research.continuous_selection import (fact_page, validate_object_comparison,
    _inspection_base, choose)
from research.research_progress import (validate_assessment, history_rows, progress_page, AUTHORITY)
from research.run_storage import read_json, write_json
from research.graph import FactGraph
from test_continuous_selection import fixture, decision
from test_bridge_discovery import Crash, snapshot


def assessment(facts):
    refs = ['fact:'+f.fact_id for f in facts[:2]]
    return {'series':'Bounds for signed arguments', 'established':'Positive and negative domains differ.',
        'latest_delta':'A negative-domain estimate is available.',
        'judgments':[{'work_refs':[], 'evidence_fact_refs':refs,
            'explanation':'Only positive arguments in the first bound; this negative-domain action is outside its conditions.'}],
        'next_question':'Can the negative-domain recurrence extend the estimate?',
        'why_this_action':'Test the remaining boundary, not the count of accepted results.'}


def test_inspection_has_no_final_object_comparison():
    # Exact envelope shape of ec2 visit27's confirmed response, including its
    # non-null explanation before any research object has been chosen.
    response={'operation':'INSPECT', 'selected_object_id':None, 'considered_objects':[],
        'no_alternative_reason':'The current packet displays no Research Object cards for the selected Study; research-objects:16 must be inspected before identifying genuine object alternatives.'}
    original=deepcopy(response)
    validate_object_comparison(response,{})
    assert response==original
    with pytest.raises(ValueError):
        validate_object_comparison({**response,'operation':'ADVANCE'}, {})


@pytest.mark.parametrize('boundary',[None,'call_completed','selection_saved'])
def test_assessment_survives_confirmation_and_next_local_exposure(tmp_path,boundary):
    net,target,state,facts=fixture(tmp_path);calls=[];schedule=deepcopy(state['schedule'])
    value=assessment(facts)
    class Selector:
        def invoke(self,**kw):
            calls.append(kw['label'])
            return {**decision(target), 'research_assessment':value}
    def crash(event,details):
        if event==boundary:raise Crash()
    if boundary:
        with pytest.raises(Crash):_Research(tmp_path,state,Selector(),crash).select_work(net)
    run=_Research(tmp_path,state,Selector(),None);packet=run.select_work(net)
    assert calls==['continuous_selector'] and state['schedule']==schedule
    assert packet['research_assessment_unverified']=={'authority':AUTHORITY,'content':value}
    assert packet['accepted_facts']==[]
    before=snapshot(tmp_path);assert run.select_work(net)==packet and snapshot(tmp_path)==before
    assert len(calls)==1
    # Existing service journal is sufficient; no new mutation store or call.
    state['schedule']['last_served']={target['study_id']:1}
    rows=history_rows(run.directory,{'cards':[target]},state['schedule'],net)
    assert rows[0]['assessment']==value
    assert rows[0]['source_ref']=='visits/00000001/selection.json'
    exposed=run.selector_exposure(net,{target['study_id']:target})['exposure']
    assert exposed['research_progress']['items']==rows
    with pytest.raises(ValueError,match='accepted visible Facts'):
        net.prepare_candidate({'kind':'FACT','goal':'A conclusion','context':'','proof':'Use the assessment',
            'predecessors':[facts[0].fact_id]}, [])
    assert net.truth(net.target_id)=='OPEN'


def test_coverage_is_an_explicit_revisable_judgment_not_inferred_from_bounds(tmp_path):
    net,target,state,facts=fixture(tmp_path)
    page=fact_page(net,[target],token_budget=4000,recent_first=True)
    assert 'covered_work' not in json.dumps(page)
    value=assessment(facts)
    # Even an erroneous semantic judgment cannot rewrite the graph. The next
    # Worker still needs exact materialization and independent verification.
    value['judgments'][0]['explanation']='Selector alleges coverage; conditions still need review.'
    before=snapshot(tmp_path)
    validate_assessment({'research_assessment':value},set(value['judgments'][0]['evidence_fact_refs']))
    assert snapshot(tmp_path)==before
    assert len(list((tmp_path/'facts').glob('*.md')))==3


@pytest.mark.parametrize('mutation',[
    lambda a:a['judgments'][0]['evidence_fact_refs'].append('fact:unexposed'),
    lambda a:a['judgments'][0]['work_refs'].append('research-object:unseen'),
    lambda a:a['judgments'][0]['evidence_fact_refs'].append('research-artifact:x'),
    lambda a:a.update(next_question=''),
])
def test_uninspected_or_unverified_sources_cannot_author_assessment_relations(tmp_path,mutation):
    _,_,_,facts=fixture(tmp_path);value=assessment(facts)
    seen=set(value['judgments'][0]['evidence_fact_refs']);mutation(value)
    with pytest.raises(ValueError):validate_assessment({'research_assessment':value},seen)


def test_recent_interfaces_round_robin_studies_without_claiming_strength(tmp_path):
    net,target,_,facts=fixture(tmp_path)
    cards=[{**target,'known_fact_ids':[facts[0].fact_id,facts[1].fact_id]},
           {'study_id':'other','known_fact_ids':[facts[2].fact_id]}]
    page=fact_page(net,cards,token_budget=4000,recent_first=True)
    assert [r['ref'] for r in page['items']]==['fact:'+f.fact_id for f in (facts[1],facts[2],facts[0])]
    assert [r['source_scope'] for r in page['items']]==['','Assume x = 1.','']
    assert all('predecessor_refs' in r for r in page['items'])
    assert all(r['authority']=='SOURCE_INTERFACE_ONLY' for r in page['items'])


def test_previous_assessment_revocation_fails_closed_and_unexposed_study_is_absent(tmp_path):
    net,target,state,facts=fixture(tmp_path);run=_Research(tmp_path,state,None,None)
    exposure=run.selector_exposure(net,{target['study_id']:target})['exposure']
    write_json(run.step_dir/'selection.json',{'selected':{**decision(target),'research_assessment':assessment(facts)},'exposure':exposure})
    schedule={'last_served':{target['study_id']:1,'secret-study':99}}
    FactGraph(tmp_path).revoke(facts[0].fact_id,'test')
    rows=history_rows(run.directory,{'cards':[target]},schedule,net)
    assert len(rows)==1 and rows[0]['assessment'] is None
    assert rows[0]['unavailable_sources']==['fact:'+facts[0].fact_id]
    assert 'secret-study' not in json.dumps(rows)


def test_reading_intents_of_different_studies_survive_forward_pages():
    base={'cards':[], 'research_object_cards':{'items':[],'next_ref':'research-objects:16'}}
    first={'study_id':'one','material_refs':['research-objects:16'], 'reason':'A method restriction suggests a changed family.'}
    second={'study_id':'two','material_refs':['research-objects:32'], 'reason':'Inspect a different finite construction.'}
    p1=_inspection_base(base,base,first)
    p2=_inspection_base(base,p1,second)
    assert p2['inspection_intents_unverified']==[first,second]
    assert p1['inspection_intents_unverified']==[first]
    assert 'accepted_facts' not in p2 and 'forced_study_id' not in p2


def test_progress_paging_preserves_complete_judgments_or_explicit_notices():
    rows=[{'study_id':str(i),'source_ref':str(i),'assessment':'ALL CONDITIONS '+('x'*1000)} for i in range(3)]
    page=progress_page(rows,0,lambda p:len(json.dumps(p))<1500)
    assert page['items']==rows[:1] and page['next_ref']=='research-progress:1'
    page2=progress_page(rows,1,lambda p:len(json.dumps(p))<500)
    assert page2['items']==[] and page2['unexpanded']
    assert all(r['reason']=='complete_assessment_exceeds_window' for r in page2['unexpanded'])


@pytest.mark.parametrize('boundary',['call_completed','selector_page_saved'])
def test_inspect_recovers_confirmed_read_without_action_comparison_or_service(tmp_path,boundary):
    from test_bridge_discovery import accepted
    net,target,state,facts=fixture(tmp_path,large=True)
    state['settings']['selector_context_tokens']=5000
    for i in range(8):
        f=accepted(tmp_path,net,f'For integer j={i}, '+('P(j) is defined. '*100)+' P(j)>=0.','')
        target['known_fact_ids'].append(f.fact_id)
    write_json(tmp_path/'continuous_run'/state['studies'][target['study_id']],target)
    calls=[];schedule=deepcopy(state['schedule'])
    class Selector:
        def invoke(self,**kw):
            calls.append(kw['prompt']);p=json.loads(kw['prompt'].split('\nPACKET:\n')[1])
            if len(calls)==1:
                return {**decision(target,[p['fact_interfaces']['next_ref']]),'operation':'INSPECT',
                        'selected_object_id':None,'considered_objects':[],
                        'no_alternative_reason':'Read the requested page before deciding alternatives.'}
            return decision(target)
    fired=False
    def crash(event,details):
        nonlocal fired
        if event==boundary and not fired:fired=True;raise Crash()
    with pytest.raises(Crash):_Research(tmp_path,state,Selector(),crash).select_work(net)
    packet=_Research(tmp_path,state,Selector(),None).select_work(net)
    assert len(calls)==2 and packet['accepted_facts']==[] and state['schedule']==schedule
    assert not list((tmp_path/'continuous_run/visits').glob('*/worker_result.json'))


def test_displayed_assessment_source_uses_ordinary_unverified_material_path(tmp_path):
    from research.continuous_materials import load_materials
    from research.continuous_selection import _displayed_refs
    net,target,state,facts=fixture(tmp_path)
    folder=tmp_path/'continuous_run/visits/00000000'
    write_json(folder/'packet.json',{'study':target})
    write_json(folder/'selection.json',{'selected':{**decision(target),'research_assessment':assessment(facts)}})
    ref='visits/00000000/selection.json'
    exposure={'cards':[{**target,'ref':state['studies'][target['study_id']]}],
              'research_progress':{'items':[{'study_id':target['study_id'],'source_ref':ref}]}}
    assert ref in _displayed_refs(exposure)
    fs,ms,notices=load_materials(tmp_path,target,[ref],state['studies'],net)
    assert fs=={} and ms[0]['verified'] is False and not notices
    write_json(folder/'packet.json',{'study':{**target,'scope':'different assumptions'}})
    with pytest.raises(ValueError,match='scope changed'):
        load_materials(tmp_path,target,[ref],state['studies'],net)


def test_large_prior_judgment_yields_to_requested_intact_fact_page():
    from research.continuous_selection import _reading_budget,_fits,INSTRUCTIONS
    from research.continuous_research import _SELECTOR_SCHEMA
    from research.continuous_attention import bounded_packet
    row={'study_id':'s','source_ref':'visits/00000001/selection.json','assessment':'x'*19000}
    base={'cards':[],'research_progress':{'items':[row],'unexpanded':[],'next_ref':None},
        'inspection_intents_unverified':[{'study_id':'s','reason':'Inspect the next full theorem.'}]}
    original=deepcopy(base);value=_reading_budget(base,_SELECTOR_SCHEMA,8000)
    assert base==original and value['research_progress']['items']==[]
    assert value['research_progress']['unexpanded'][0]['source_ref']==row['source_ref']
    statement='Complete hypotheses and theorem '+('x'*5800)
    value['fact_interfaces']={'items':[{'ref':'fact:x','source_scope':'','exact_statement':statement}],
                              'unexpanded':[],'next_ref':None}
    assert _fits(value,_SELECTOR_SCHEMA,8000)
    assert value['fact_interfaces']['items'][0]['exact_statement']==statement
