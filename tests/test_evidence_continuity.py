"""Accepted evidence becomes optional local work through the public CRPN loop."""
from truth_gate_fixtures import no_counterexample
import json
import pytest

from selector_fixtures import object_choice
from research.continuous_research import start_run, resume_run, pause_run, export_proof
from research.continuous_network import ContinuousNetwork
from research.graph import FactGraph
from research.run_storage import read_json
from test_continuous_research import Crash


class EvidenceResearch:
    def __init__(self, *, integrate=True):
        self.integrate = integrate
        self.calls = []
        self.packets = []
        self.source_id = None

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "statement_sanity":
            return no_counterexample(prompt)
        if label == 'closed_book_verifier':
            return {'accepted': True, 'external_authority_dependency': False,
                    'violation_type': 'NONE', 'reason': 'The exact elementary conditional interface is valid.'}
        if label == 'recurrence_probe':
            return {'status':'NO_MATCH', 'ancestor_claim_id':'', 'explicit_mapping':'',
                    'reason':'The child equality is distinct from the root computation.'}
        packet = json.loads(prompt.split('\nPACKET:\n')[1])
        if label == 'continuous_selector':
            assert 'conditional reduction' in prompt and 'optional ordinary actions' in prompt
            ready = next(iter(packet.get('ready_supports', [])), None)
            study = min(packet['cards'], key=lambda c:(c['revision'],c['study_id']))
            refs=[]
            for item in packet['fact_interfaces']['items']:
                if item['exact_statement']=='1 + 1 = 2':
                    self.source_id=item['ref'][5:]
                    if self.integrate: refs=[item['ref']]
            return {**object_choice(), 'study_id':ready['study_id'] if ready else study['study_id'],
                    'operation':'COMPOSE' if ready else 'ADVANCE',
                    'support_id':ready['support_id'] if ready else '', 'material_refs':refs,
                    'reason':('Apply the accepted equality to reduce the remaining computation.' if self.integrate
                              else 'Keep the accepted equality for later; investigate another derivation first.'),
                    'relation':'RELEVANT', 'continuation_window':None}
        assert label=='continuous_worker'
        assert 'neither a Support nor a new requirement is mandatory' in prompt
        self.packets.append(packet)
        goal=packet['claim']['goal']
        if len(self.packets)==1:
            candidate={'kind':'FACT','goal':'1 + 1 = 2','context':'',
                       'proof':'This is the defining sum of the first two units.','predecessors':[]}
        elif not self.integrate:
            assert packet['accepted_facts']==[]
            candidate=None
        elif packet['operation']=='COMPOSE':
            candidate={'kind':'FACT','goal':goal,'context':'',
                       'proof':'Apply the supplied conditional certificate to its proved requirement.',
                       'predecessors':[f['fact_id'] for f in packet['accepted_facts']]}
        elif goal=='1 + 1 + 1 = 3':
            assert self.source_id and any(f['fact_id']==self.source_id for f in packet['accepted_facts'])
            candidate={'kind':'SUPPORT','goal':goal,'context':'',
                       'proof':'Use the accepted equality 1+1=2, then apply the requirement 2+1=3.',
                       'predecessors':[self.source_id],
                       'requirements':[{'goal':'2 + 1 = 3','context':''}]}
        else:
            assert goal=='2 + 1 = 3'
            candidate={'kind':'FACT','goal':goal,'context':'',
                       'proof':'Adding one unit to two gives three.','predecessors':[]}
        return {'candidate':candidate,'continuation':'Keep the precise completed computation and remaining interface.',
                'next_work':'Continue from the locally established result.'}


@pytest.mark.parametrize('crash_boundary',[None,'fact_bound','continuation_saved'])
def test_fact_to_support_child_research_and_compose_through_public_entry(tmp_path,crash_boundary):
    model=EvidenceResearch();fired=False
    def observe(event,details):
        nonlocal fired
        if event==crash_boundary and not fired:
            fired=True
            raise Crash()
    if crash_boundary:
        with pytest.raises(Crash):
            start_run(tmp_path,problem_id='evidence',statement='1 + 1 + 1 = 3',invoker=model,on_event=observe)
        result=resume_run(tmp_path,invoker=model)
    else:
        result=start_run(tmp_path,problem_id='evidence',statement='1 + 1 + 1 = 3',invoker=model)
    assert result['status']=='SOLVED'
    assert [p['operation'] for p in model.packets]==['ADVANCE','ADVANCE','ADVANCE','COMPOSE']
    assert model.calls.count('continuous_worker')==4
    assert model.calls.count('closed_book_verifier')==4
    assert model.calls.count('statement_sanity')==4
    assert model.calls.count('recurrence_probe')==1
    net=ContinuousNetwork(tmp_path);support=next(iter(net.data['supports'].values()))
    graph=FactGraph(tmp_path)
    assert list(graph.get_fact(support['bridge_fact_id']).predecessors)==[model.source_id]
    assert net.truth(support['requirement_claim_ids'][0])=='DISCHARGED'
    assert len(export_proof(tmp_path)['facts'])==4
    assert set(f.fact_id for f in graph.supporting_closure(net.facts_for(net.target_id)[0].fact_id)) >= {model.source_id,support['bridge_fact_id']}
    target_study=next(s for s in result['studies'] if s['claim_id']==net.target_id)
    assert model.source_id in target_study['known_fact_ids']
    assert result['schedule']['channel_cycle']==['ADVANCE','ADVANCE','ADVANCE','EXPLORE','REVISIT']


def test_visible_new_fact_does_not_force_use_support_or_extra_model_call(tmp_path):
    model=EvidenceResearch(integrate=False)
    def observe(event,details):
        if event=='visit_completed' and details['visit']==2:
            pause_run(tmp_path,'deterministic observation boundary')
    result=start_run(tmp_path,problem_id='optional',statement='1 + 1 + 1 = 3',invoker=model,on_event=observe)
    assert result['status']=='PAUSED' and result['target_state']=='OPEN'
    assert model.source_id is not None
    assert model.calls==['continuous_worker','statement_sanity','closed_book_verifier','continuous_selector','continuous_worker']
    assert not ContinuousNetwork(tmp_path).data['supports']
    assert len(list((tmp_path/'facts').glob('*.md')))==1
    assert read_json(tmp_path/'continuous_run/visits/00000001/worker_result.json')['candidate'] is None
