"""Discovery is navigation; inspection never grants foreign-scope truth."""
from selector_fixtures import object_choice
from dataclasses import asdict
import json

import pytest

from research.continuous_attention import bounded_packet
from research.continuous_materials import (
    bridge_candidate_page, expose_bridge_candidates, load_materials, load_selector_materials,
)
from research.continuous_network import ContinuousNetwork
from research.continuous_research import _Research
from research.fact import Fact
from research.graph import FactGraph
from research.run_storage import read_json, write_json


def accepted(root, network, goal, scope):
    candidate, descriptor = network.prepare_candidate({'kind': 'FACT', 'context': scope,
        'goal': goal, 'proof': 'Deterministic oracle proof.', 'predecessors': []}, [])
    fact = Fact.create(problem_id=network.problem_id, author='fixture', **asdict(candidate))
    FactGraph(root).add_fact(fact)
    network.accept_verified(descriptor, fact.fact_id)
    return fact


def study(root, key, scope='', focus='Bound rho_k(n) for each integer n.', **extra):
    value = {'study_id': key, 'scope': scope, 'focus': focus, 'revision': 0,
             'continuation': '', 'next_work': 'Continue the estimate.', **extra}
    ref = f'studies/{key}/000000.json'
    write_json(root / 'continuous_run' / ref, value)
    return value, ref


def snapshot(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.fixture
def case(tmp_path):
    network = ContinuousNetwork.create(tmp_path, 'discovery', 'Bound rho_k(n) for each integer n.')
    target, ref = study(tmp_path, 'study-' + network.target_id, claim_id=network.target_id)
    foreign = accepted(tmp_path, network, 'rho_k(n) >= 0.', 'Define rho_k(n) = n*n + k*k.')
    return network, target, {target['study_id']: ref}, foreign


def test_same_scope_material_behavior_is_unchanged(tmp_path, case):
    network, target, refs, _ = case
    local = accepted(tmp_path, network, 'rho_k(n) = rho_k(n).', '')
    args = (tmp_path, target, ['fact:' + local.fact_id], refs, network)
    assert load_selector_materials(*args) == load_materials(*args)
    assert local.fact_id not in json.dumps(bridge_candidate_page(tmp_path, target, refs, network))


def test_exact_notation_discovers_unindexed_foreign_fact_and_retains_conditions(tmp_path, case):
    network, target, refs, foreign = case
    unrelated = accepted(tmp_path, network, 'tau(m) is positive.', 'Define tau(m) = m*m + 1.')
    before = snapshot(tmp_path)
    page = bridge_candidate_page(tmp_path, target, refs, network)
    assert len(page['candidates']) == 1
    card = page['candidates'][0]
    assert card['kind'] == 'BRIDGE_CANDIDATE'
    assert card['source_fact_id'] == foreign.fact_id
    assert card['source_scope'] == 'Define rho_k(n) = n*n + k*k.'
    assert card['exact_statement'] == foreign.statement
    assert card['requires_bridge'] is card['navigation_only'] is True
    assert card['discovery_reason'] == {'shared_object_refs': [], 'exact_notation': ['rho_k']}
    assert unrelated.fact_id not in json.dumps(page)
    assert snapshot(tmp_path) == before


def test_shared_object_reference_discovers_without_notation_match(tmp_path, case):
    network, target, refs, foreign = case
    target = {**target, 'focus': 'Estimate the size.', 'object_refs': ['object:obj-shared']}
    peer, ref = study(tmp_path, 'study-peer', scope='Another context.', focus='A different expression.',
                      object_refs=['object:obj-shared'], known_fact_ids=[foreign.fact_id])
    refs[peer['study_id']] = ref
    page = bridge_candidate_page(tmp_path, target, refs, network)
    card = page['candidates'][0]
    assert card['source_fact_id'] == foreign.fact_id
    assert card['discovery_reason'] == {'shared_object_refs': ['object:obj-shared'], 'exact_notation': []}


def test_inspection_is_read_only_and_does_not_bypass_ordinary_scope_gate(tmp_path, case):
    network, target, refs, foreign = case
    before = snapshot(tmp_path)
    candidates = bridge_candidate_page(tmp_path, target, refs, network)['candidates']
    facts, notes, notices = load_selector_materials(tmp_path, target, ['fact:' + foreign.fact_id], refs, network,
                                                   candidates=candidates)
    assert facts == {} and notes == [] and len(notices) == 1
    inspected = notices[0]
    assert inspected['kind'] == 'BRIDGE_CANDIDATE_INSPECTION'
    assert inspected['source_fact_id'] == foreign.fact_id
    assert inspected['exact_statement'] == foreign.statement
    assert inspected['accepted_in_target_scope'] is False
    assert inspected['provenance']['predecessors'] == []
    assert inspected['source_scope'] == network.inspect_fact(foreign.fact_id)['scope']
    assert 'proof' not in inspected
    assert network.truth(network.target_id) == 'OPEN'
    assert snapshot(tmp_path) == before
    with pytest.raises(ValueError, match='exact scope'):
        load_selector_materials(tmp_path, target, ['fact:' + foreign.fact_id], refs, network)
    with pytest.raises(ValueError, match='exact scope'):
        load_materials(tmp_path, target, ['fact:' + foreign.fact_id], refs, network)
    with pytest.raises(ValueError, match='exact scope'):
        network.visible_fact(foreign.fact_id, target['scope'])
    with pytest.raises(ValueError, match='scope'):
        network.prepare_candidate({'kind':'FACT', 'context':'', 'goal':'rho_k(n) >= 0.',
            'proof':'Use the navigation card.', 'predecessors':[foreign.fact_id]}, [foreign.fact_id])


@pytest.mark.parametrize('invalid', ['revoked', 'cross_problem', 'unbound'])
def test_invalid_facts_are_not_candidates_or_inspectable(tmp_path, case, invalid):
    network, target, refs, foreign = case
    if invalid == 'revoked':
        FactGraph(tmp_path).revoke(foreign.fact_id, 'Fixture revocation.')
    else:
        foreign = Fact.create(problem_id='other' if invalid == 'cross_problem' else network.problem_id,
            author='fixture', statement='rho_k(n) > 0.', proof='Unbound.', predecessors=[])
        FactGraph(tmp_path).add_fact(foreign)
    peer, ref = study(tmp_path, 'study-peer', object_refs=['object:obj-shared'], known_fact_ids=[foreign.fact_id])
    refs[peer['study_id']] = ref
    target = {**target, 'object_refs':['object:obj-shared']}
    assert foreign.fact_id not in json.dumps(bridge_candidate_page(tmp_path, target, refs, network))
    with pytest.raises(ValueError):
        load_selector_materials(tmp_path, target, ['fact:' + foreign.fact_id], refs, network)


def test_page_is_bounded_and_exposure_does_not_truncate_mathematical_interfaces(tmp_path, case):
    network, target, refs, _ = case
    for i in range(18):
        accepted(tmp_path, network, f'rho_k(n) + {i} >= {i}.', 'Define rho_k(n) = n*n + k*k.')
    first = bridge_candidate_page(tmp_path, target, refs, network, token_budget=6000)
    assert len(first['candidates']) == 16 and first['next_ref']
    facts, notes, notices = load_selector_materials(tmp_path, target, [first['next_ref']], refs, network, token_budget=6000)
    second = notices[0]
    assert not facts and not notes and len(second['candidates']) == 3 and second['next_ref'] is None
    assert {c['source_fact_id'] for c in first['candidates']}.isdisjoint(c['source_fact_id'] for c in second['candidates'])
    exposure = {'cards':[{'study_id':target['study_id']}], 'channel':'REVISIT'}
    output = expose_bridge_candidates(tmp_path, exposure, {target['study_id']:target}, refs, network, token_budget=650)
    bounded_packet({k:output[k] for k in ('bridge_candidates','bridge_candidate_pages')}, 650)
    assert output['bridge_candidate_pages']
    assert len(output['bridge_candidates']) < 16
    for card in output['bridge_candidates']:
        assert card['exact_statement'] == FactGraph(tmp_path).get_fact(card['source_fact_id']).statement
    assert exposure == {'cards':[{'study_id':target['study_id']}], 'channel':'REVISIT'}


def test_common_single_letter_parameters_do_not_create_lexical_candidates(tmp_path, case):
    network, target, refs, _ = case
    other = accepted(tmp_path, network, 'f(n) >= n.', 'Let f(n) = n + 1.')
    target = {**target, 'focus':'Prove f(n) <= max(n, 3).'}
    assert other.fact_id not in json.dumps(bridge_candidate_page(tmp_path, target, refs, network))


def test_notation_is_case_and_subscript_sensitive_not_semantic_equivalence(tmp_path, case):
    network, target, refs, foreign = case
    for focus in ('Bound Rho_k(n).', 'Bound rho_j(n).', 'Bound rho(n).'):
        assert foreign.fact_id not in json.dumps(bridge_candidate_page(tmp_path, {**target,'focus':focus}, refs, network))


def test_oversized_conditional_interface_has_reference_but_no_truncated_candidate(tmp_path, case):
    network, target, refs, _ = case
    long_fact = accepted(tmp_path, network, 'rho_k(n) >= 0.', 'Definitions: ' + ('rho_k(n) is defined locally. ' * 2000))
    exposure = {'cards':[{'study_id':target['study_id']}], 'channel':'REVISIT'}
    output = expose_bridge_candidates(tmp_path, exposure, {target['study_id']:target}, refs, network, token_budget=700)
    assert long_fact.fact_id not in [c['source_fact_id'] for c in output['bridge_candidates']]
    assert output['bridge_candidate_pages']
    ref = output['bridge_candidate_pages'][0]['ref']
    _, _, pages = load_selector_materials(tmp_path, target, [ref], refs, network)
    notice = next(c for c in pages[0]['unexpanded'] if c['source_fact_id'] == long_fact.fact_id)
    assert notice['reason'] == 'complete_interface_exceeds_navigation_budget'
    assert 'exact_statement' not in notice
    assert pages[0]['candidates']  # the small interface is still reachable
    bounded_packet(pages, 2000)


def test_stale_or_other_study_candidate_cannot_be_inspected(tmp_path, case):
    network, target, refs, foreign = case
    card = bridge_candidate_page(tmp_path, target, refs, network)['candidates'][0]
    for altered in ({**card,'exact_statement':'Changed conditions.'}, {**card,'source_scope':''},
                    {**card,'study_id':'study-someone-else'}):
        with pytest.raises(ValueError):
            load_selector_materials(tmp_path, target, [card['ref']], refs, network, candidates=[altered])


def test_exposure_leaves_scheduler_and_base_cards_identical(tmp_path, case):
    from research.continuous_attention import expose
    network, target, refs, _ = case
    state = {'run_id':'discovery', 'step':1, 'studies':refs, 'schedule':{'channel_cursor':4}, 'settings':{'selector_context_tokens':8000}}
    run = _Research(tmp_path, state, None, None)
    expected, schedule = expose([{**target,'ref':refs[target['study_id']], 'last_served_visit':-1,
                                  'completed':False}], state['schedule'], card_budget=4000)
    actual = run.selector_exposure(network, {target['study_id']:target})
    assert actual['next_schedule'] == schedule
    assert {k:actual['exposure'][k] for k in expected} == expected


class Crash(BaseException):
    pass


@pytest.mark.parametrize('boundary', [None, 'call_completed', 'selection_saved'])
def test_normal_selector_opportunity_and_recovery_preserve_navigation_only_state(tmp_path, case, boundary):
    network, target, refs, foreign = case
    state = {'run_id':'deterministic-discovery', 'step':1, 'studies':refs,
        'schedule':{'channel_cursor':4, 'revisit_snapshot':[target['study_id']], 'revisit_cursor':0},
        'settings':{'selector_context_tokens':8000,'worker_context_tokens':64000,'verifier_context_tokens':96000},
        'retries':{}, 'acknowledged_pauses':[]}
    calls = []

    class Selector:
        def invoke(self, *, prompt, schema, label):
            assert label == 'continuous_selector'
            calls.append(label)
            packet = json.loads(prompt.split('\nPACKET:\n')[1])
            assert packet['forced_study_id'] == target['study_id']
            assert packet['bridge_candidates'][0]['source_fact_id'] == foreign.fact_id
            assert 'accepted_facts' not in packet
            return {**object_choice(), 'study_id':target['study_id'], 'operation':'ADVANCE', 'support_id':'',
                'material_refs':['fact:' + foreign.fact_id], 'reason':'Inspect whether a bridge is justified.',
                'relation':'RELEVANT', 'continuation_window':None}

    def crash(event, details):
        if event == boundary:
            raise Crash()

    before_graph = (tmp_path / 'proof_graph.json').read_bytes()
    if boundary:
        with pytest.raises(Crash):
            _Research(tmp_path, state, Selector(), crash).select_work(network)
    packet = _Research(tmp_path, state, Selector(), None).select_work(network)
    confirmed = snapshot(tmp_path)
    again = _Research(tmp_path, state, Selector(), None).select_work(network)
    assert packet == again and snapshot(tmp_path) == confirmed
    assert calls == ['continuous_selector']
    assert packet['accepted_facts'] == []
    assert packet['material_notices'][0]['kind'] == 'BRIDGE_CANDIDATE_INSPECTION'
    assert (tmp_path / 'proof_graph.json').read_bytes() == before_graph
    assert state['schedule']['channel_cursor'] == 4
    assert state['schedule']['revisit_cursor'] == 0
    assert not (tmp_path / 'fact_bridges').exists()
    assert not list((tmp_path / 'continuous_run').glob('visits/*/worker_result.json'))


@pytest.mark.parametrize('change', ['new_fact', 'revoke'])
def test_confirmed_selector_input_is_frozen_even_if_sources_change_during_pause(tmp_path, case, change):
    network, target, refs, foreign = case
    state = {'run_id':'frozen-input', 'step':1, 'studies':refs, 'schedule':{'channel_cursor':4},
        'settings':{'selector_context_tokens':8000}, 'retries':{}, 'acknowledged_pauses':[]}
    calls = []

    class Selector:
        def invoke(self, *, prompt, schema, label):
            calls.append(prompt)
            return {**object_choice(), 'study_id':target['study_id'], 'operation':'ADVANCE', 'support_id':'',
                'material_refs':['fact:' + foreign.fact_id], 'reason':'Inspect.',
                'relation':'UNKNOWN', 'continuation_window':None}

    def crash(event, details):
        if event == 'call_completed':
            raise Crash()

    with pytest.raises(Crash):
        _Research(tmp_path, state, Selector(), crash).select_work(network)
    saved = {p:p.read_bytes() for p in (tmp_path/'continuous_run').rglob('*.json')}
    if change == 'new_fact':
        accepted(tmp_path, network, 'rho_k(n) >= -1.', 'Define rho_k(n) = n*n + k*k.')
        _Research(tmp_path, state, Selector(), None).select_work(ContinuousNetwork(tmp_path))
    else:
        FactGraph(tmp_path).revoke(foreign.fact_id, 'Fixture revocation while paused.')
        with pytest.raises(ValueError, match='revoked'):
            _Research(tmp_path, state, Selector(), None).select_work(ContinuousNetwork(tmp_path))
    assert len(calls) == 1
    assert all(p.read_bytes() == data for p,data in saved.items())


@pytest.mark.parametrize('crash_after_reselection', [False, True])
def test_large_inspection_window_uses_existing_reselection_without_consuming_service(tmp_path, case, crash_after_reselection):
    from research.continuous_research import resume_run, pause_run
    from research.dynamic_run import _code_digest
    network, target, refs, _ = case
    long_fact = accepted(tmp_path, network, 'rho_k(n) >= 0.',
                         'Define rho_k(n) = n*n + k*k. ' + 'All parameters are integers. ' * 85)
    state = {'run_id':'inspection-window', 'code_digest':_code_digest(), 'runtime':{'backend':'injected'},
        'status':'PAUSED', 'step':1, 'studies':refs, 'schedule':{'channel_cursor':4},
        'settings':{'selector_context_tokens':8000,'worker_context_tokens':64000,'verifier_context_tokens':96000},
        'retries':{}, 'retry_role':None, 'acknowledged_pauses':[]}
    write_json(tmp_path/'continuous_run/state.json', state)
    selectors, workers = [], []

    class Actors:
        def invoke(self, *, prompt, schema, label):
            packet = json.loads(prompt.split('\nPACKET:\n')[1])
            if label == 'continuous_selector':
                selectors.append(packet)
                if len(selectors) == 1:
                    assert long_fact.fact_id in [c['source_fact_id'] for c in packet['bridge_candidates']]
                    materials = ['bridge-candidates:0:' + target['study_id'], 'fact:' + long_fact.fact_id]
                else:
                    assert 'fewer material_refs' in packet['cards'][0]['attention_notice']
                    materials = ['fact:' + long_fact.fact_id]
                return {**object_choice(), 'study_id':target['study_id'], 'operation':'ADVANCE', 'support_id':'',
                    'material_refs':materials, 'reason':'Inspect this bounded interface.',
                    'relation':'UNKNOWN', 'continuation_window':None}
            if label == 'continuous_selector_bridge':
                return {'action':'IGNORE','bridge_request':None,'reason':'Inspect applicability later.'}
            assert label == 'continuous_worker'
            workers.append(packet)
            return {'continuation':'The foreign interface still requires a verified bridge.',
                    'next_work':'Inspect applicability.', 'candidate':None}

    def observe(event, details):
        if event == 'window_reselection_required':
            assert read_json(tmp_path/'continuous_run/state.json')['schedule'] == state['schedule']
            if crash_after_reselection:
                raise Crash()
        if event == 'visit_completed':
            pause_run(tmp_path, 'deterministic proof-slice boundary')

    if crash_after_reselection:
        with pytest.raises(Crash):
            resume_run(tmp_path, invoker=Actors(), on_event=observe)
        old = {p:p.read_bytes() for p in (tmp_path/'continuous_run/calls').rglob('*.json')}
    result = resume_run(tmp_path, invoker=Actors(), on_event=observe)
    if crash_after_reselection:
        assert all(p.read_bytes() == value for p,value in old.items())
    assert len(selectors) == 2 and len(workers) == 1
    assert result['model_calls'] == 4 and result['status'] == 'PAUSED'  # includes post-inspection Selector
    assert result['schedule']['channel_cursor'] == 5
    assert workers[0]['accepted_facts'] == []
    assert not (tmp_path/'continuous_run/visits/00000001/packet.json').exists()
