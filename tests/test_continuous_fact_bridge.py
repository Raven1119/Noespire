"""One autonomous materialization opportunity, with no requirement Worker."""
from dataclasses import asdict
import json
import subprocess

import pytest

from research.continuous_network import ContinuousNetwork
from research.continuous_materials import load_materials
from research.dynamic_run import _code_digest
from research.fact import Fact
from research.graph import FactGraph
from research.run_storage import read_json, write_json, run_lock
from research.continuous_fact_bridge import materialize_once, read_materialization


class Crash(BaseException):
    pass


@pytest.fixture
def case(tmp_path):
    network = ContinuousNetwork.create(tmp_path, 'auto-bridge', 'Prove rho_k(n) >= 1 for integers k,n.')
    candidate, desc = network.prepare_candidate({'kind':'FACT', 'context':'Define rho_k(n) = n*n+k*k.',
        'goal':'For all integers k,n, rho_k(n) >= 0.', 'proof':'A sum of squares is nonnegative.',
        'predecessors':[]}, [])
    source = Fact.create(problem_id=network.problem_id, author='fixture', **asdict(candidate))
    FactGraph(tmp_path).add_fact(source)
    network.accept_verified(desc, source.fact_id)
    network.register_claim('UNRELATED_GLOBAL_SENTINEL', 'Hidden assumptions.')
    study_id = 'study-' + network.target_id
    ref = f'studies/{study_id}/000000.json'
    write_json(tmp_path/'continuous_run'/ref, {'study_id':study_id, 'claim_id':network.target_id,
        'scope':'', 'focus':network.claim(network.target_id).goal, 'continuation':'', 'revision':0,
        'next_work':'Investigate the estimate.'})
    write_json(tmp_path/'continuous_run/state.json', {'run_id':'fresh-auto', 'step':1, 'status':'PAUSED',
        'code_digest':_code_digest(), 'runtime':{'backend':'injected'}, 'studies':{study_id:ref},
        'schedule':{'channel_cursor':4, 'revisit_snapshot':[study_id], 'revisit_cursor':0},
        'settings':{'selector_context_tokens':8000,'worker_context_tokens':64000,'verifier_context_tokens':96000},
        'retries':{}, 'retry_role':None, 'acknowledged_pauses':[]})
    return network, source


class Actors:
    def __init__(self, *, inspect=True, request=True, mutate=None, failure=None, accepted=True):
        self.inspect, self.request, self.mutate, self.failure, self.accepted = inspect, request, mutate, failure, accepted
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        assert 'UNRELATED_GLOBAL_SENTINEL' not in prompt
        if self.failure and label == self.failure[0]:
            raise self.failure[1]
        if label == 'closed_book_verifier':
            assert 'BRIDGE_INTERFACE:' in prompt
            return {'accepted':self.accepted, 'external_authority_dependency':False,
                    'violation_type':'NONE', 'reason':'Checked the complete conditional transport.'}
        packet = json.loads(prompt.split('\nPACKET:\n')[1])
        if label == 'continuous_selector':
            card = packet['bridge_candidates'][0]
            return {'study_id':card['study_id'], 'operation':'CONNECT', 'support_id':'',
                'material_refs':[card['ref']] if self.inspect else [], 'reason':'Inspect the conditional estimate.',
                'relation':'UNKNOWN', 'continuation_window':None}
        if label == 'continuous_selector_bridge':
            assert packet['accepted_facts'] == []
            inspection = packet['material_notices'][0]
            assert inspection['kind'] == 'BRIDGE_CANDIDATE_INSPECTION'
            request = {'source_fact_id':inspection['source_fact_id'],
                'target_claim_id':packet['claim']['obligation_id'], 'target_scope':packet['claim']['context'],
                'target_auxiliary_statement':'Define sigma_j(m)=m*m+j*j for integers j,m. Then sigma_j(m)>=0.',
                'correspondence':'For arbitrary integers j,m substitute k=j and n=m. '
                    'The definitions give sigma_j(m)=rho_j(m); the integer domains are identical.'}
            if self.mutate:
                self.mutate(request, packet)
            return {'action':'REQUEST_BRIDGE' if self.request else 'IGNORE', 'reason':'A reusable local estimate.',
                    'bridge_request':request if self.request else None}
        assert label == 'fact_bridge_worker', 'Requirement Worker or unrelated role was called'
        assert packet['accepted_facts'] == []
        assert packet['source_fact']['scope'] in packet['source_fact']['statement']
        return {'status':'PROOF', 'proof':'For integers j,m the stated definitions identify '
            'sigma_j(m) with rho_j(m). The accepted conditional source theorem yields nonnegativity.',
            'reason':'All source conditions retained.'}


def assert_success(root, original, result):
    assert result['status'] == 'MATERIALIZED' and result['usable']
    network = ContinuousNetwork(root)
    fact = network.visible_fact(result['fact_id'], '')
    assert fact.predecessors == (original.fact_id,)
    assert result['closure'] == [original.fact_id, fact.fact_id]
    packet = read_json(root/'continuous_run/visits/00000001/automatic_bridge/material_packet.json')
    assert packet['accepted_facts'] == [{'fact_id':fact.fact_id,'statement':fact.statement}]
    assert original.fact_id not in [f['fact_id'] for f in packet['accepted_facts']]
    assert network.truth(network.target_id) == 'OPEN'
    assert not (root/'continuous_run/visits/00000001/packet.json').exists()
    with pytest.raises(ValueError, match='exact scope'):
        load_materials(root, packet['study'], ['fact:'+original.fact_id], {}, network)


def test_automatic_request_bridge_admission_and_ordinary_materialization(tmp_path, case):
    network, source = case
    state = (tmp_path/'continuous_run/state.json').read_bytes()
    actors = Actors()
    result = materialize_once(tmp_path, invoker=actors)
    assert_success(tmp_path, source, result)
    assert actors.calls == ['continuous_selector','continuous_selector_bridge','fact_bridge_worker','closed_book_verifier']
    assert result['selector_calls'] == 2 and result['bridge']['model_calls'] == 2
    assert (tmp_path/'continuous_run/state.json').read_bytes() == state
    assert materialize_once(tmp_path, invoker=actors) == result
    assert len(actors.calls) == 4


@pytest.mark.parametrize('inspect,wants_bridge', [(False,False), (True,False)])
def test_no_inspection_or_no_request_stops_without_bridge(tmp_path, case, inspect, wants_bridge):
    actors = Actors(inspect=inspect, request=wants_bridge)
    result = materialize_once(tmp_path, invoker=actors)
    assert result['status'] == 'NO_BRIDGE_REQUEST'
    assert len(actors.calls) == (2 if inspect else 1)
    assert not (tmp_path/'fact_bridges').exists()


@pytest.mark.parametrize('mutate', [
    lambda r,p:r.update(source_fact_id='0'*16),
    lambda r,p:r.update(target_claim_id='ob-absent'),
    lambda r,p:r.update(target_scope='Unproved extra assumption.'),
    lambda r,p:r.update(target_auxiliary_statement=p['claim']['goal']),
    lambda r,p:r.update(correspondence='  '),
    lambda r,p:r.update(correspondence={'same':'notation'}),
    lambda r,p:r.update(target_auxiliary_statement=''),
])
def test_invalid_request_never_reaches_bridge(tmp_path, case, mutate):
    actors = Actors(mutate=mutate)
    result = materialize_once(tmp_path, invoker=actors)
    assert result['status'] == 'INVALID_BRIDGE_REQUEST'
    assert actors.calls == ['continuous_selector','continuous_selector_bridge']
    assert not (tmp_path/'fact_bridges').exists()
    assert len(list((tmp_path/'facts').glob('*.md'))) == 1


@pytest.mark.parametrize('boundary', ['discovery_call','inspection_saved','selector_call','bridge_request_saved',
    'worker_call','verifier_call','verification_completed','fact_admitted','claim_registered','fact_bound','materialized'])
def test_recovery_never_repeats_confirmed_calls_or_admission(tmp_path, case, boundary):
    _, source = case
    actors = Actors()
    def observe(event, details):
        point = {'continuous_selector':'discovery_call','continuous_selector_bridge':'selector_call','fact_bridge_worker':'worker_call',
                 'closed_book_verifier':'verifier_call'}.get(details.get('label')) if event == 'call_completed' else event
        if point == boundary:
            raise Crash()
    with pytest.raises(Crash):
        materialize_once(tmp_path, invoker=actors, on_event=observe)
    confirmed = {p:p.read_bytes() for p in tmp_path.rglob('calls/*/*.json')}
    result = materialize_once(tmp_path, invoker=actors)
    assert_success(tmp_path, source, result)
    assert len(actors.calls) == 4
    assert all(p.read_bytes() == data for p,data in confirmed.items())
    assert len(list((tmp_path/'facts').glob('*.md'))) == 2


@pytest.mark.parametrize('role', ['continuous_selector_bridge','fact_bridge_worker','closed_book_verifier'])
@pytest.mark.parametrize('failure', [RuntimeError('system'),subprocess.TimeoutExpired('codex',600),Crash()])
def test_failures_and_unconfirmed_calls_do_not_retry_or_admit(tmp_path, case, role, failure):
    actors = Actors(failure=(role,failure))
    if isinstance(failure, Crash):
        with pytest.raises(Crash):
            materialize_once(tmp_path, invoker=actors)
    result = materialize_once(tmp_path, invoker=actors)
    count = len(actors.calls)
    assert result['status'] in ('ERROR','TIMEOUT','INTERRUPTED','BRIDGE_FAILED')
    assert materialize_once(tmp_path, invoker=actors) == result
    assert len(actors.calls) == count
    assert len(list((tmp_path/'facts').glob('*.md'))) == 1


def test_semantic_request_error_is_not_mechanical_mathematical_authority(tmp_path, case):
    actors = Actors(accepted=False, mutate=lambda r,p:r.update(
        target_auxiliary_statement='Define sigma_j(m)=m*m+j*j. Then sigma_j(m)>0 for all integers j,m.'))
    result = materialize_once(tmp_path, invoker=actors)
    assert result['status'] == 'BRIDGE_FAILED' and result['bridge']['status'] == 'REJECTED'
    assert len(list((tmp_path/'facts').glob('*.md'))) == 1


@pytest.mark.parametrize('which', ['source','output'])
def test_revocation_after_completion_never_rematerializes_cached_fact(tmp_path, case, which):
    _, source = case
    actors = Actors()
    result = materialize_once(tmp_path, invoker=actors)
    FactGraph(tmp_path).revoke(source.fact_id if which=='source' else result['fact_id'], 'Revocation.')
    status = read_materialization(tmp_path)
    assert not status['usable']
    assert not materialize_once(tmp_path, invoker=actors)['usable']
    assert len(actors.calls) == 4


def test_revoked_inspected_source_fails_closed_before_bridge(tmp_path, case):
    _, source = case
    actors = Actors()
    def revoke(event, details):
        if event == 'bridge_request_saved':
            FactGraph(tmp_path).revoke(source.fact_id, 'Source revoked after request.')
    result = materialize_once(tmp_path, invoker=actors, on_event=revoke)
    assert result['status'] == 'INVALID_BRIDGE_REQUEST'
    assert len(actors.calls) == 2 and not (tmp_path/'fact_bridges').exists()


def test_existing_writer_lock_is_authoritative(tmp_path, case):
    with run_lock(tmp_path/'continuous_run'):
        with pytest.raises(RuntimeError, match='writer'):
            materialize_once(tmp_path, invoker=Actors())

@pytest.mark.parametrize('bad_source', ['uninspected','cross_problem'])
def test_existing_but_unauthorized_source_cannot_be_requested(tmp_path, case, bad_source):
    network, _ = case
    if bad_source == 'uninspected':
        candidate, desc = network.prepare_candidate({'kind':'FACT','context':'Define beta(m)=m*m.',
            'goal':'beta(m)>=0 for integers m.','proof':'Square.','predecessors':[]},[])
        foreign = Fact.create(problem_id=network.problem_id,author='fixture',**asdict(candidate))
        FactGraph(tmp_path).add_fact(foreign)
        network.accept_verified(desc,foreign.fact_id)
    else:
        foreign = Fact.create(problem_id='other-problem',author='fixture',statement='Foreign.',
                              proof='Not available here.',predecessors=[])
        FactGraph(tmp_path).add_fact(foreign)
    actors = Actors(mutate=lambda r,p:r.update(source_fact_id=foreign.fact_id))
    result = materialize_once(tmp_path,invoker=actors)
    assert result['status']=='INVALID_BRIDGE_REQUEST' and len(actors.calls)==2
    assert not (tmp_path/'fact_bridges').exists()


def test_existing_unrelated_target_claim_cannot_replace_selected_claim(tmp_path,case):
    network,_ = case
    other = network.register_claim('A different research task.','')
    actors = Actors(mutate=lambda r,p:r.update(target_claim_id=other.obligation_id))
    assert materialize_once(tmp_path,invoker=actors)['status']=='INVALID_BRIDGE_REQUEST'


@pytest.mark.parametrize('change',['packet','worker_reservation','fingerprint','runtime_backend','pending_retry'])
def test_pre_worker_ownership_and_frozen_environment(tmp_path,case,change):
    state_path = tmp_path/'continuous_run/state.json'
    state = read_json(state_path)
    if change=='packet':
        write_json(tmp_path/'continuous_run/visits/00000001/packet.json',{'frozen':'old'})
    elif change=='worker_reservation':
        write_json(tmp_path/'continuous_run/calls/existing/request.json',
                   {'scope':'1:worker:retry-0','label':'continuous_worker'})
    elif change=='fingerprint':
        state['code_digest']='changed'
    elif change=='runtime_backend':
        state['runtime']={'backend':'codex'}
    else:
        state['retry_role']='selector'
    write_json(state_path,state)
    actors = Actors()
    with pytest.raises(ValueError):
        materialize_once(tmp_path,invoker=actors)
    assert actors.calls==[] and not (tmp_path/'fact_bridges').exists()


def test_second_selector_uses_original_selector_attention_ceiling(tmp_path,case,monkeypatch):
    from research import continuous_fact_bridge as module
    monkeypatch.setattr(module,'_PROMPT',module._PROMPT+'x'*32000)
    actors = Actors()
    result = materialize_once(tmp_path,invoker=actors)
    assert result['status']=='ERROR' and result['phase']=='SELECTOR'
    measurement = read_json(tmp_path/'continuous_run/visits/00000001/selector-bridge-attention-overflow.json')
    assert measurement['limit']==8000
    assert actors.calls==['continuous_selector']


def test_materialization_failure_retains_bridge_receipt(tmp_path,case,monkeypatch):
    from research import continuous_fact_bridge as module
    monkeypatch.setattr(module,'load_materials',lambda *a,**k: (_ for _ in ()).throw(ValueError('resolver failure')))
    actors = Actors()
    result = materialize_once(tmp_path,invoker=actors)
    assert result['status']=='MATERIALIZATION_FAILED'
    assert result['bridge']['status']=='COMPLETED' and result['bridge']['usable']
    assert len(actors.calls)==4

def test_materialization_preserves_existing_exact_scope_facts(tmp_path,case):
    network,source = case
    candidate,desc = network.prepare_candidate({'kind':'FACT','context':'',
        'goal':'For integers m, m*m>=0.','proof':'A square is nonnegative.','predecessors':[]},[])
    local = Fact.create(problem_id=network.problem_id,author='fixture',**asdict(candidate))
    FactGraph(tmp_path).add_fact(local)
    network.accept_verified(desc,local.fact_id)
    actors = Actors()
    invoke = actors.invoke
    def select(**kw):
        if kw['label']=='continuous_selector_bridge':
            # Verify the existing local premise was not stripped for inspection.
            packet=json.loads(kw['prompt'].split('\nPACKET:\n')[1])
            assert [f['fact_id'] for f in packet['accepted_facts']]==[local.fact_id]
            # The generic actor's empty-premise assertion applies to other fixtures.
            altered={**packet,'accepted_facts':[]}
            kw={**kw,'prompt':kw['prompt'].split('\nPACKET:\n')[0]+'\nPACKET:\n'+json.dumps(altered)}
        result=invoke(**kw)
        if kw['label']=='continuous_selector':
            result['material_refs'].append('fact:'+local.fact_id)
        return result
    actors.invoke=select
    result=materialize_once(tmp_path,invoker=actors)
    assert result['status']=='MATERIALIZED' and result['usable']
    packet=read_json(tmp_path/'continuous_run/visits/00000001/automatic_bridge/material_packet.json')
    assert [f['fact_id'] for f in packet['accepted_facts']]==[local.fact_id,result['fact_id']]
    assert source.fact_id not in [f['fact_id'] for f in packet['accepted_facts']]

def test_bridge_ledger_remains_linked_when_source_revoked_after_worker_crash(tmp_path,case):
    _,source = case
    actors=Actors()
    def crash(event,details):
        if event=='call_completed' and details.get('label')=='fact_bridge_worker':
            raise Crash()
    with pytest.raises(Crash):
        materialize_once(tmp_path,invoker=actors,on_event=crash)
    before=read_materialization(tmp_path)
    assert before['selector_calls']==2 and before['bridge']['model_calls']==1
    FactGraph(tmp_path).revoke(source.fact_id,'Revoke after confirmed bridge Worker.')
    after=materialize_once(tmp_path,invoker=actors)
    assert after['status']=='INVALID_BRIDGE_REQUEST'
    assert after['bridge']['model_calls']==1 and len(actors.calls)==3
    assert not after['usable']


def test_later_requirement_discharge_does_not_revoke_valid_auxiliary(tmp_path,case):
    network,_=case
    actors=Actors()
    result=materialize_once(tmp_path,invoker=actors)
    network=ContinuousNetwork(tmp_path)
    candidate,desc=network.prepare_candidate({'kind':'FACT','context':'',
        'goal':network.claim(network.target_id).goal,'proof':'Independent fixture proof.',
        'predecessors':[]},[])
    fact=Fact.create(problem_id=network.problem_id,author='oracle',**asdict(candidate))
    FactGraph(tmp_path).add_fact(fact)
    network.accept_verified(desc,fact.fact_id)
    assert network.truth(network.target_id)=='DISCHARGED'
    assert read_materialization(tmp_path)['usable']
    assert materialize_once(tmp_path,invoker=actors)['usable']
    assert len(actors.calls)==4
