"""Object comparison is observable decision evidence, never proof or policy."""
from copy import deepcopy
import pytest
from research.continuous_selection import validate_object_comparison

VISIBLE = {'object-a':'study-x', 'object-b':'study-x', 'object-c':'study-y'}

def choice(selected='object-a', disposition='DEFER'):
    return {'study_id':'study-x','selected_object_id':selected,'action_mode':'RESEARCH',
        'considered_objects': ([{'object_id':'object-a','disposition':'SELECT','reason':'Investigate the missing endpoint identity.'},
            {'object_id':'object-b','disposition':disposition,'reason':'Leave the independent finite construction for a later service.'}] if selected else []),
        'no_alternative_reason':None}

@pytest.mark.parametrize('disposition',['DEFER','REJECT'])
def test_same_study_comparison_is_preserved_without_ranking(disposition):
    selected=choice(disposition=disposition);before=deepcopy(selected)
    validate_object_comparison(selected,VISIBLE)
    assert selected==before

@pytest.mark.parametrize('mutation',[
    lambda s: s['considered_objects'].append(deepcopy(s['considered_objects'][0])),
    lambda s: s['considered_objects'][1].update(disposition='SELECT'),
    lambda s: s.update(selected_object_id='object-b'),
    lambda s: s['considered_objects'][1].update(object_id='object-c'),
    lambda s: s['considered_objects'][1].update(object_id='object-unseen'),
    lambda s: s['considered_objects'][1].update(reason='  '),
    lambda s: s['considered_objects'][1].update(reason=None),
    lambda s: s['considered_objects'][1].update(disposition='PARK'),
    lambda s: s['considered_objects'][1].update(score=.9),
    lambda s: s.update(no_alternative_reason='There is no alternative.'),
    lambda s: s.update(considered_objects=None),
    lambda s: s.pop('considered_objects'),
    lambda s: s.pop('no_alternative_reason'),
    lambda s: s.pop('selected_object_id'),
    lambda s: s.update(considered_objects=[]),
])
def test_invalid_interfaces_fail_closed(mutation):
    selected=choice();mutation(selected)
    with pytest.raises(ValueError):validate_object_comparison(selected,VISIBLE)

@pytest.mark.parametrize('reason',[None,'','  ',False])
def test_single_selection_requires_a_specific_nonempty_account(reason):
    selected=choice();selected['considered_objects']=selected['considered_objects'][:1]
    selected['no_alternative_reason']=reason
    with pytest.raises(ValueError):validate_object_comparison(selected,VISIBLE)

def test_single_selection_with_account_is_legal_and_no_mathematics_is_scored():
    selected=choice();selected['considered_objects']=selected['considered_objects'][:1]
    selected['no_alternative_reason']='The other card records a method used in this action, not a separate work item this visit.'
    validate_object_comparison(selected,VISIBLE)

@pytest.mark.parametrize('disposition',[None,'DEFER','REJECT'])
def test_general_research_without_object_can_record_unselected_alternatives(disposition):
    selected=choice(None)
    if disposition:selected['considered_objects']=[{'object_id':'object-b','disposition':disposition,'reason':'First clarify the common definitions before working on this finite construction.'}]
    validate_object_comparison(selected,VISIBLE)

def test_null_object_cannot_select_an_entry():
    selected=choice();selected['selected_object_id']=None
    with pytest.raises(ValueError):validate_object_comparison(selected,VISIBLE)

def test_nonempty_no_alternative_reason_is_only_for_a_single_selected_object():
    selected=choice(None);selected['no_alternative_reason']='None.'
    with pytest.raises(ValueError):validate_object_comparison(selected,VISIBLE)

@pytest.mark.parametrize('mode',['RESEARCH','CLOSE'])
def test_unknown_gaps_do_not_affect_selection_or_deferral(mode):
    selected=choice();selected.update(action_mode=mode,remaining_gap='UNKNOWN')
    validate_object_comparison(selected,VISIBLE)


@pytest.mark.parametrize('boundary',[None,'call_completed','selection_saved'])
def test_confirmed_comparison_recovers_exact_order_once_and_never_becomes_material(tmp_path,boundary):
    from research import continuous_research as research
    from research.run_storage import read_json
    from test_research_object_selection import case,packet
    from test_continuous_closure_actions import action
    from test_bridge_discovery import snapshot,Crash
    network,target,state,studies=case(tmp_path)
    calls=[];returned=[];before_graph=(tmp_path/'proof_graph.json').read_bytes();before_schedule=deepcopy(state['schedule'])
    class Selector:
        def invoke(self,*,prompt,schema,label):
            assert label=='continuous_selector'
            assert {'considered_objects','no_alternative_reason'}<=set(schema['required'])
            rows=packet(prompt)['research_object_cards']['items'];calls.append(label)
            assert rows[0]['remaining_gap']==rows[1]['remaining_gap']=='UNKNOWN'
            result={**action(target,'RESEARCH'),
                'selected_object_id':rows[0]['object_id'],
                'considered_objects':[
                    {'object_id':rows[1]['object_id'],'disposition':'DEFER','reason':'The other finite construction remains a separate available task; this visit examines the endpoint identity.'},
                    {'object_id':rows[0]['object_id'],'disposition':'SELECT','reason':'Work on the endpoint identity for this construction.'}],
                'no_alternative_reason':None}
            returned.append(deepcopy(result));return result
    fired=False
    def crash(event,details):
        nonlocal fired
        if event==boundary and not fired:fired=True;raise Crash()
    if boundary:
        with pytest.raises(Crash):research._Research(tmp_path,state,Selector(),crash).select_work(network)
    run=research._Research(tmp_path,state,Selector(),None);out=run.select_work(network)
    plan=read_json(run.step_dir/'selection.json')
    assert plan['selected']==returned[0]
    assert plan['selected']['considered_objects'][0]['disposition']=='DEFER'
    assert read_json(run.step_dir/'selector_input.json')['object_comparison_contract']==1
    assert 'considered_objects' not in out and 'no_alternative_reason' not in out
    assert out['accepted_facts']==out['unverified_materials']==[]
    assert not (run.directory/'research_artifacts').exists()
    assert not (run.directory/'research_deliveries').exists()
    assert (tmp_path/'proof_graph.json').read_bytes()==before_graph and state['schedule']==before_schedule
    saved=snapshot(tmp_path);assert run.select_work(network)==out and snapshot(tmp_path)==saved
    assert calls==['continuous_selector']


def test_removing_new_comparison_fields_cannot_downgrade_confirmed_input_to_legacy(tmp_path):
    from research import continuous_research as research
    from research.run_storage import read_json,write_json
    from test_research_object_selection import case
    from test_continuous_selection import decision
    network,target,state,_=case(tmp_path)
    class Selector:
        def invoke(self,**kw):return decision(target)
    run=research._Research(tmp_path,state,Selector(),None);run.select_work(network)
    saved=read_json(run.step_dir/'selection.json')
    for key in ('considered_objects','no_alternative_reason'):saved['selected'].pop(key)
    write_json(run.step_dir/'selection.json',saved)
    with pytest.raises(ValueError,match='incomplete object comparison'):run.select_work(network)


def test_new_call_cannot_omit_comparison_to_use_the_legacy_reader(tmp_path):
    from research import continuous_research as research
    from test_research_object_selection import case
    from test_continuous_selection import decision
    network,target,state,_=case(tmp_path)
    class Selector:
        def invoke(self,**kw):
            result=decision(target)
            for key in ('selected_object_id','considered_objects','no_alternative_reason'):result.pop(key)
            return result
    run=research._Research(tmp_path,state,Selector(),None)
    with pytest.raises(ValueError,match='incomplete object comparison'):run.select_work(network)
    assert not (run.step_dir/'selection.json').exists()


def test_general_null_selection_still_rejects_foreign_considered_entry():
    selected=choice(None);selected['considered_objects']=[{'object_id':'object-c','disposition':'DEFER','reason':'Different task.'}]
    with pytest.raises(ValueError,match='another Study'):validate_object_comparison(selected,VISIBLE)
