"""Support contexts remain ambient; definitions travel in complete child goals."""
from dataclasses import asdict
import json
import pytest

from research.continuous_network import ContinuousNetwork
from research.continuous_research import _Research, _WORKER_SCHEMA
from research.fact import Fact
from research.graph import FactGraph
from research.run_storage import read_json,write_json


CHILD = ("For each integer k>=1 and real t>=0 define U_k(t)=k*t. "
         "If a>=0 is real, prove U_k(t)+a>=0.")


class Crash(BaseException):
    pass


@pytest.fixture
def case(tmp_path):
    network=ContinuousNetwork.create(tmp_path,'support-scope','For all real t>=0, 2*t>=0.','')
    candidate,desc=network.prepare_candidate({'kind':'FACT','goal':'For all real t>=0, t>=0.',
        'context':'','proof':'This is the stated restriction on t.','predecessors':[]},[])
    predecessor=Fact.create(problem_id=network.problem_id,author='fixture',**asdict(candidate))
    FactGraph(tmp_path).add_fact(predecessor)
    network.accept_verified(desc,predecessor.fact_id)
    study={'study_id':'study-'+network.target_id,'claim_id':network.target_id,'scope':'','revision':0,
           'continuation':'','focus':network.claim(network.target_id).goal,'next_work':'Continue.'}
    ref=f"studies/{study['study_id']}/000000.json"
    write_json(tmp_path/'continuous_run'/ref,study)
    state={'run_id':'scope-contract','step':1,'studies':{study['study_id']:ref},'retries':{},
           'schedule':{'channel_cursor':4},'acknowledged_pauses':[],
           'settings':{'worker_context_tokens':64000,'verifier_context_tokens':96000}}
    write_json(tmp_path/'continuous_run/state.json',state)
    packet={'study':study,'claim':asdict(network.claim(network.target_id)),'operation':'ADVANCE',
        'accepted_facts':[{'fact_id':predecessor.fact_id,'statement':predecessor.statement}],
        'required_fact_ids':[],'material_notices':[],'unverified_materials':[],'support':None,
        'feedback':None,'action':'Continue.','relation':'UNKNOWN','channel':'REVISIT'}
    write_json(tmp_path/'continuous_run/visits/00000001/packet.json',packet)
    proposal={'kind':'SUPPORT','context':'','goal':network.claim(network.target_id).goal,
        'proof':'Under the displayed child condition take k=1,a=0 and add its inequality to the accepted nonnegativity.',
        'predecessors':[predecessor.fact_id],'requirements':[{'context':'','goal':CHILD}]}
    return network,state,packet,proposal,predecessor


class Actors:
    def __init__(self,proposal,accepted=True):
        self.proposal,self.accepted=proposal,accepted
        self.calls=[]
        self.worker_prompt=None

    def invoke(self,*,prompt,schema,label):
        self.calls.append(label)
        if label=='continuous_worker':
            self.worker_prompt=prompt
            return {'continuation':'A conditional route using a fully stated auxiliary.',
                    'next_work':'Investigate the child.', 'candidate':self.proposal}
        assert label=='closed_book_verifier'
        assert CHILD in prompt
        return {'accepted':self.accepted,'external_authority_dependency':False,
                'violation_type':'NONE','reason':'Independent deterministic verdict.'}


def test_worker_receives_scope_and_self_containment_contract(tmp_path,case):
    network,state,_,proposal,_=case
    actors=Actors(proposal)
    _Research(tmp_path,state,actors,None).visit(network)
    prompt=actors.worker_prompt
    assert 'copy the conclusion context verbatim' in prompt
    assert 'ambient assumptions only' in prompt
    assert 'self-contained goal' in prompt
    assert 'not an existence proof' in prompt
    fields=_WORKER_SCHEMA['properties']['candidate']['anyOf'][1]['properties']['requirements']['items']['properties']
    assert 'verbatim' in fields['context']['description']
    assert 'definitions' in fields['goal']['description']
    assert 'domains' in fields['goal']['description']


@pytest.mark.parametrize('scope',['','Let t be real.'])
def test_auxiliary_definition_and_conditional_hypothesis_inside_goal_keep_exact_scope(tmp_path,scope):
    network=ContinuousNetwork.create(tmp_path,'local-definitions','A local conclusion.',scope)
    prepared,descriptor=network.prepare_candidate({'kind':'SUPPORT','goal':'A local conclusion.',
        'context':scope,'proof':'Conditional interface.','predecessors':[],
        'requirements':[{'context':scope,'goal':CHILD}]},[])
    assert descriptor['context']==descriptor['requirements'][0]['context']==scope
    assert descriptor['requirements'][0]['goal']==CHILD
    assert CHILD in prepared.statement
    assert 'If a>=0 is real' in prepared.statement
    assert network.data['supports']=={} and len(list((tmp_path/'facts').glob('*.md')))==0


@pytest.mark.parametrize('extra_context',['Assume t>0.','Define U_k(t)=k*t.'])
def test_extra_assumptions_or_definitions_in_child_context_still_rejected(tmp_path,case,extra_context):
    network,state,_,proposal,_=case
    before=(tmp_path/'proof_graph.json').read_bytes()
    proposal['requirements'][0]['context']=extra_context
    actors=Actors(proposal)
    _Research(tmp_path,state,actors,None).visit(network)
    verification=read_json(tmp_path/'continuous_run/visits/00000001/verification.json')
    assert not verification['accepted'] and 'exact conclusion scope' in verification['reason']
    assert actors.calls==['continuous_worker']
    assert (tmp_path/'proof_graph.json').read_bytes()==before
    assert len(list((tmp_path/'facts').glob('*.md')))==1
    assert not (tmp_path/'continuous_run/visits/00000001/admission.json').exists()


@pytest.mark.parametrize('boundary',[None,'worker_completed','verifier_completed','fact_admitted','fact_bound'])
def test_same_scope_support_admission_lineage_and_recovery(tmp_path,case,boundary):
    network,state,_,proposal,predecessor=case
    actors=Actors(proposal)
    fired=False
    def observe(event,details):
        nonlocal fired
        point=({'continuous_worker':'worker_completed','closed_book_verifier':'verifier_completed'}
               .get(details.get('label')) if event=='call_completed' else event)
        if point==boundary and not fired:
            fired=True
            raise Crash()
    if boundary:
        with pytest.raises(Crash):
            _Research(tmp_path,state,actors,observe).visit(network)
        saved={p:p.read_bytes() for p in (tmp_path/'continuous_run/calls').rglob('*.json')}
    _Research(tmp_path,read_json(tmp_path/'continuous_run/state.json'),actors,None).visit(ContinuousNetwork(tmp_path))
    assert actors.calls==['continuous_worker','closed_book_verifier']
    if boundary:
        assert all(p.read_bytes()==v for p,v in saved.items())
    network=ContinuousNetwork(tmp_path)
    assert len(network.data['supports'])==1
    support=next(iter(network.data['supports'].values()))
    child=network.claim(support['requirement_claim_ids'][0])
    assert child.context==network.claim(support['conclusion_claim_id']).context==''
    assert child.goal==CHILD and network.truth(child.obligation_id)=='OPEN'
    fact=FactGraph(tmp_path).get_fact(support['bridge_fact_id'])
    assert fact.predecessors==(predecessor.fact_id,)
    assert [f.fact_id for f in FactGraph(tmp_path).supporting_closure(fact.fact_id)]==[predecessor.fact_id,fact.fact_id]
    assert network.truth(network.target_id)=='OPEN'
    assert not (tmp_path/'continuous_run/visits/00000002').exists()


def test_same_scope_does_not_grant_mathematical_authority(tmp_path,case):
    network,state,_,proposal,_=case
    proposal['requirements'][0]['goal']=CHILD+' There exists a negative real a>=0.'
    actors=Actors(proposal,accepted=False)
    _Research(tmp_path,state,actors,None).visit(network)
    assert actors.calls==['continuous_worker','closed_book_verifier']
    assert not read_json(tmp_path/'continuous_run/visits/00000001/verification.json')['accepted']
    assert ContinuousNetwork(tmp_path).data['supports']=={}
    assert len(list((tmp_path/'facts').glob('*.md')))==1
