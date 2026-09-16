"""Automatic bridging in ordinary run/resume, without counting Study service."""
import json
import subprocess
import pytest

from test_continuous_fact_bridge import case, Actors, Crash
from research.continuous_research import resume_run, pause_run, read_status, _Research
from research.continuous_network import ContinuousNetwork
from research.continuous_materials import load_materials
from research.continuous_fact_bridge import read_materialization
from research.graph import FactGraph
from research.run_storage import read_json, write_json


class LoopActors(Actors):
    def invoke(self, **kw):
        if kw['label'] == 'continuous_worker':
            self.calls.append(kw['label'])
            assert self.calls.count('continuous_worker') <= 1, 'Unexpected extra Study service'
            self.worker_packet = json.loads(kw['prompt'].split('\nPACKET:\n')[1])
            return dict(continuation='Local research continues.', next_work='Check the remaining bound.',
                        context_requests=[], new_study=None, definitions=[], candidate=None)
        return super().invoke(**kw)


def stop_materials(root):
    def observe(event, details):
        if event == 'material_surface_ready':
            pause_run(root, 'stop before ordinary proof Worker')
    return observe


def test_loop_bridge_materials_and_fairness(tmp_path, case):
    network, source = case
    before = read_json(tmp_path/'continuous_run/state.json')
    actors = LoopActors()
    result = resume_run(tmp_path, invoker=actors, on_event=stop_materials(tmp_path))
    receipt = read_materialization(tmp_path)
    packet = read_json(tmp_path/'continuous_run/visits/00000001/packet.json')
    assert receipt['usable']
    assert actors.calls == ['continuous_selector', 'continuous_selector_bridge', 'fact_bridge_worker', 'statement_sanity', 'closed_book_verifier']
    assert [f['fact_id'] for f in packet['accepted_facts']] == [receipt['fact_id']]
    assert result['schedule'] == before['schedule'] and result['step'] == before['step']
    assert result['studies'][0]['revision'] == 0
    assert result['studies'][0]['known_fact_ids'] == [receipt['fact_id']]
    assert result['model_calls'] == 5 and result['bridge_model_calls'] == 3
    assert result['reported_tokens'] is None and result['unknown_usage_calls']==5
    assert receipt['closure'] == [source.fact_id, receipt['fact_id']]
    with pytest.raises(ValueError, match='exact scope'):
        load_materials(tmp_path, packet['study'], ['fact:'+source.fact_id], {}, ContinuousNetwork(tmp_path))
    def stop_visit(event, details):
        if event == 'visit_completed': pause_run(tmp_path, 'one real Study service')
    resumed = resume_run(tmp_path, invoker=actors, on_event=stop_visit)
    assert actors.calls[-1] == 'continuous_worker' and len(actors.calls) == 6
    assert resumed['step'] == 2 and resumed['schedule']['revisit_cursor'] == 1
    state = read_json(tmp_path/'continuous_run/state.json')
    exposure = _Research(tmp_path,state,actors,None).selector_exposure(ContinuousNetwork(tmp_path),
        {s['study_id']:s for s in resumed['studies']})
    assert receipt['fact_id'] in json.dumps(exposure['exposure']['cards'])


@pytest.mark.parametrize('boundary', ['selection_saved','inspection_saved','selector_call','bridge_request_saved',
    'worker_call','sanity_call','verifier_call','verification_completed','fact_admitted','claim_registered','fact_bound',
    'materialized','bridge_materials_bound','material_surface_ready'])
def test_loop_crash_exact_recovery(tmp_path, case, boundary):
    actors = LoopActors()
    def crash(event, details):
        point = {'continuous_selector_bridge':'selector_call','fact_bridge_worker':'worker_call',
            'statement_sanity':'sanity_call','closed_book_verifier':'verifier_call'}.get(details.get('label')) if event=='call_completed' else event
        if point == boundary: raise Crash()
    with pytest.raises(Crash): resume_run(tmp_path,invoker=actors,on_event=crash)
    confirmed = {p:p.read_bytes() for p in tmp_path.rglob('calls/*/result.json')}
    result = resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    assert result['step']==1 and result['studies'][0]['revision']==0
    assert len(actors.calls)==5 and read_materialization(tmp_path)['usable']
    assert all(p.read_bytes()==value for p,value in confirmed.items())
    assert len(list((tmp_path/'facts').glob('*.md')))==2


@pytest.mark.parametrize('failure', ['decline','reject','timeout','error','unconfirmed'])
def test_bridge_failure_continues_normal_service_without_retry(tmp_path,case,failure):
    actors=LoopActors(accepted=failure!='reject')
    if failure in ('timeout','error','unconfirmed'):
        actors.failure=('fact_bridge_worker', {'timeout':subprocess.TimeoutExpired('codex',600),
            'error':RuntimeError('runtime call failed'), 'unconfirmed':Crash()}[failure])
    original=actors.invoke
    def invoke(**kw):
        if failure=='decline' and kw['label']=='fact_bridge_worker':
            actors.calls.append(kw['label'])
            return dict(status='DECLINE',proof='',reason='No reliable transport.')
        return original(**kw)
    actors.invoke=invoke
    if failure=='unconfirmed':
        with pytest.raises(Crash): resume_run(tmp_path,invoker=actors)
    def stop(event,details):
        if event=='visit_completed': pause_run(tmp_path,'one Study service')
    result=resume_run(tmp_path,invoker=actors,on_event=stop)
    assert result['step']==2 and result['studies'][0]['revision']==1
    assert actors.calls.count('fact_bridge_worker')==1
    assert actors.calls.count('continuous_worker')==1
    assert actors.worker_packet['accepted_facts']==[]
    assert len(list((tmp_path/'facts').glob('*.md')))==1


@pytest.mark.parametrize('which',['source','output'])
def test_revoke_after_packet_freeze_fails_closed(tmp_path,case,which):
    _,source=case
    actors=LoopActors()
    resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    receipt=read_materialization(tmp_path)
    FactGraph(tmp_path).revoke(source.fact_id if which=='source' else receipt['fact_id'],'withdraw')
    result=resume_run(tmp_path,invoker=actors)
    assert result['status']=='PAUSED' and len(actors.calls)==5
    assert not read_materialization(tmp_path)['usable']


def test_same_request_across_visits_reuses_bridge_ledger(tmp_path,case):
    actors=LoopActors()
    def stop(event,details):
        if event=='visit_completed': pause_run(tmp_path,'one service')
    resume_run(tmp_path,invoker=actors,on_event=stop)
    result=resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    assert result['step']==2
    assert actors.calls.count('fact_bridge_worker')==1
    assert actors.calls.count('closed_book_verifier')==1
    assert result['bridge_model_calls']==3
    assert len(list((tmp_path/'facts').glob('*.md')))==2


@pytest.mark.parametrize('boundary',['continuous_selector_bridge','fact_bridge_worker','statement_sanity','closed_book_verifier','fact_bound'])
def test_cooperative_pause_keeps_same_bridge_identity(tmp_path,case,boundary):
    actors=LoopActors()
    def stop(event,details):
        if (event=='call_completed' and details.get('label')==boundary) or event==boundary:
            pause_run(tmp_path,'pause inside bridge')
    first=resume_run(tmp_path,invoker=actors,on_event=stop)
    assert first['pause_reason']=='pause inside bridge' and first['retry_role'] is None
    result=resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    assert read_materialization(tmp_path)['usable']
    assert len(actors.calls)==5 and result['step']==1


@pytest.mark.parametrize('failure',['os_error','process_error','timeout','fingerprint'])
def test_runtime_preflight_inside_loop_fails_closed(tmp_path,case,monkeypatch,failure):
    from research import continuous_research as core, continuous_fact_bridge as auto, fact_bridge as bridge
    from test_continuous_runtime_recovery import LocalRuntime
    stable=LocalRuntime()
    transient=LocalRuntime()
    transient.failure=failure
    actors=LoopActors()
    path=tmp_path/'continuous_run/state.json'
    state=read_json(path)
    state['runtime']=stable.manifest
    write_json(path,state)
    monkeypatch.setattr(core,'real_runtime',stable)
    monkeypatch.setattr(core,'SolInvoker',lambda **kw:actors)
    monkeypatch.setattr(auto,'real_runtime',transient)
    monkeypatch.setattr(bridge,'real_runtime',stable)
    monkeypatch.setattr(bridge,'SolInvoker',lambda **kw:actors)
    first=resume_run(tmp_path)
    assert first['pause_reason']=='RUNTIME_UNAVAILABLE' and first['retry_role'] is None
    assert actors.calls==['continuous_selector','continuous_selector_bridge']
    assert not (tmp_path/'continuous_run/visits/00000001/packet.json').exists()
    transient.failure=None
    result=resume_run(tmp_path,on_event=stop_materials(tmp_path))
    assert read_materialization(tmp_path)['usable'] and len(actors.calls)==5
    receipt=read_materialization(tmp_path)
    assert receipt['bridge']['runtime']==stable.manifest


def test_normal_packet_retains_existing_scope_whitespace_normalization(tmp_path,case):
    from dataclasses import asdict
    from research.fact import Fact
    network,_=case
    claim=network.register_claim('Prove m=m.', 'Let  m  be an integer.')
    candidate,desc=network.prepare_candidate(dict(kind='FACT',context=claim.context,
        goal='m+0=m.',proof='Addition.',predecessors=[]),[])
    fact=Fact.create(problem_id=network.problem_id,author='fixture',**asdict(candidate))
    FactGraph(tmp_path).add_fact(fact)
    network.accept_verified(desc,fact.fact_id)
    path=tmp_path/'continuous_run/state.json';state=read_json(path)
    key='study-'+claim.obligation_id
    ref=f'studies/{key}/000000.json'
    study=dict(study_id=key,claim_id=claim.obligation_id,scope='Let  m  be an integer.',
        focus=claim.goal,revision=0,continuation='',next_work='Continue.')
    write_json(tmp_path/'continuous_run'/ref,study)
    state['studies']={key:ref};write_json(path,state)
    write_json(tmp_path/'continuous_run/visits/00000001/packet.json',dict(study=study,claim=asdict(claim),
        accepted_facts=[dict(fact_id=fact.fact_id,statement=fact.statement)]))
    actors=LoopActors()
    result=resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    assert result['pause_reason']=='stop before ordinary proof Worker'
    assert actors.calls==[]


@pytest.mark.parametrize('active',[False,True])
def test_bridge_coexists_with_deferred_helper_and_active_alias(tmp_path,active):
    from dataclasses import asdict
    from research.fact import Fact
    from test_conditional_recurrence import Conditional, execute, prove_helper, deferred
    from test_continuous_network import accept
    model=Conditional()
    model.root='For integers k,n define rho_k(n)=n*n+k*k. Prove rho_k(n)>=1.'
    execute(tmp_path,model)
    network,row=deferred(tmp_path)
    if active:
        network,row,_=prove_helper(tmp_path)
    _,source=accept(network,'For integers k,n, rho_k(n)>=0.',context='Define rho_k(n)=n*n+k*k.')
    before=network.data['deferred_representations']
    actors=LoopActors()
    original=actors.invoke
    def invoke(**kw):
        if kw['label']=='representation_activation_verifier': return model.invoke(**kw)
        return original(**kw)
    actors.invoke=invoke
    result=resume_run(tmp_path,invoker=actors,on_event=stop_materials(tmp_path))
    assert read_materialization(tmp_path)['usable']
    now=ContinuousNetwork(tmp_path)
    assert now.data['deferred_representations']==before
    assert (now.alias_of(row['claim_id']) is not None)==active
    assert now.truth(now.target_id)=='OPEN'
    assert not any(s['claim_id']==row['claim_id'] for s in result['studies'])
    assert FactGraph(tmp_path).get_fact(row['conditional_fact_id'])


@pytest.mark.parametrize('failure',['os_error','process_error','timeout','fingerprint'])
def test_bridge_own_preflight_cannot_change_enclosing_runtime(tmp_path,case,monkeypatch,failure):
    from research import continuous_research as core, continuous_fact_bridge as auto, fact_bridge as bridge
    from test_continuous_runtime_recovery import LocalRuntime
    stable=LocalRuntime(); transient=LocalRuntime(); transient.failure=failure
    actors=LoopActors()
    path=tmp_path/'continuous_run/state.json'; state=read_json(path)
    state['runtime']=stable.manifest; write_json(path,state)
    monkeypatch.setattr(core,'real_runtime',stable)
    monkeypatch.setattr(auto,'real_runtime',stable)
    monkeypatch.setattr(bridge,'real_runtime',transient)
    monkeypatch.setattr(core,'SolInvoker',lambda **kw:actors)
    monkeypatch.setattr(bridge,'SolInvoker',lambda **kw:actors)
    first=resume_run(tmp_path)
    assert first['pause_reason']=='RUNTIME_UNAVAILABLE' and len(actors.calls)==2
    request=read_json(next((tmp_path/'fact_bridges').glob('*/request.json')))
    assert request['runtime']==stable.manifest
    transient.failure=None
    resume_run(tmp_path,on_event=stop_materials(tmp_path))
    assert len(actors.calls)==5 and read_materialization(tmp_path)['usable']


def test_worker_timeout_after_bridge_preserves_known_material_without_false_service(tmp_path,case):
    actors=LoopActors()
    original=actors.invoke
    def invoke(**kw):
        if kw['label']=='continuous_worker':
            actors.calls.append(kw['label'])
            raise subprocess.TimeoutExpired('codex',600)
        return original(**kw)
    actors.invoke=invoke
    def stop(event,details):
        if event=='visit_completed': pause_run(tmp_path,'one timed out Study slice')
    result=resume_run(tmp_path,invoker=actors,on_event=stop)
    receipt=read_materialization(tmp_path,step=1)
    assert result['step']==2 and result['schedule']['revisit_cursor']==1
    assert result['studies'][0]['known_fact_ids']==[receipt['fact_id']]
    assert result['studies'][0]['revision']==0
    assert ContinuousNetwork(tmp_path).truth(case[0].target_id)=='OPEN'


@pytest.mark.parametrize('crash_worker',[False,True])
def test_normal_worker_can_admit_using_bridge_binding_without_stale_graph(tmp_path,case,crash_worker):
    actors=LoopActors()
    original=actors.invoke
    def invoke(**kw):
        if kw['label']=='closed_book_verifier' and 'BRIDGE_INTERFACE:' not in kw['prompt']:
            actors.calls.append(kw['label'])
            return dict(accepted=True,external_authority_dependency=False,violation_type='NONE',reason='Add one to both sides.')
        response=original(**kw)
        if kw['label']=='continuous_worker':
            fact=actors.worker_packet['accepted_facts'][0]
            response['candidate']=dict(kind='FACT',context='',goal='For integers j,m define sigma_j(m)=m*m+j*j. Then sigma_j(m)+1>=1.',
                proof='The accepted nonnegative bound plus one gives the claim.',predecessors=[fact['fact_id']],requirements=[])
        return response
    actors.invoke=invoke
    if crash_worker:
        def crash(event,details):
            if event=='call_completed' and details.get('label')=='continuous_worker': raise Crash()
        with pytest.raises(Crash): resume_run(tmp_path,invoker=actors,on_event=crash)
    def stop(event,details):
        if event=='visit_completed': pause_run(tmp_path,'one service')
    result=resume_run(tmp_path,invoker=actors,on_event=stop)
    admission=read_json(tmp_path/'continuous_run/visits/00000001/admission.json')
    bridge=read_materialization(tmp_path,step=1)
    fact=FactGraph(tmp_path).get_fact(admission['fact_id'])
    assert fact.predecessors==(bridge['fact_id'],)
    assert [f.fact_id for f in FactGraph(tmp_path).supporting_closure(fact.fact_id)]==[
        case[1].fact_id,bridge['fact_id'],fact.fact_id]
    assert actors.calls.count('continuous_worker')==1 and len(actors.calls)==8
    assert result['target_state']=='OPEN'


def test_capacity_reselection_retains_material_and_fairness(tmp_path,case,monkeypatch):
    from research import continuous_research as core
    original=core.bounded_packet
    def overflow(packet,limit):
        return original(packet, 1 if packet.get('prompt','').startswith('Continue this local mathematical study.') else limit)
    monkeypatch.setattr(core,'bounded_packet',overflow)
    state=read_json(tmp_path/'continuous_run/state.json')
    actors=LoopActors()
    def stop(event,details):
        if event=='window_reselection_required': pause_run(tmp_path,'capacity boundary')
    result=resume_run(tmp_path,invoker=actors,on_event=stop)
    bridge=read_materialization(tmp_path,step=1)
    assert result['schedule']==state['schedule'] and result['step']==2
    assert result['studies'][0]['known_fact_ids']==[bridge['fact_id']]
    assert result['studies'][0]['revision']==0 and len(actors.calls)==5
    updated=read_json(tmp_path/'continuous_run/state.json')
    exposure=_Research(tmp_path,updated,actors,None).selector_exposure(ContinuousNetwork(tmp_path),
        {s['study_id']:s for s in result['studies']})
    assert bridge['fact_id'] in json.dumps(exposure['exposure']['cards'])
