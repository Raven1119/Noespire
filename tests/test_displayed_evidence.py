"""Displayed navigation references remain unverified, recovery-safe materials."""
from copy import deepcopy
import json
import pytest

from research import continuous_selection as selection
from research.continuous_research import _Research
from research.continuous_materials import load_materials
from research.run_storage import write_json
from test_continuous_selection import fixture, decision
from test_bridge_discovery import snapshot, Crash


REF = 'visits/00000000/feedback.json'


def navigation_case(root):
    net, target, state, facts = fixture(root)
    target['evidence_refs'] = [REF]
    write_json(root/'continuous_run'/state['studies'][target['study_id']], target)
    write_json(root/'continuous_run/visits/00000000/packet.json', {'study': target})
    # Even a stored acceptance report or a mentioned Fact is not a premise read.
    write_json(root/'continuous_run'/REF, {'accepted': True, 'fact_id': facts[0].fact_id,
                                        'note': 'Historical verifier feedback.'})
    return net, target, state, facts


def action(target, refs=(REF,)):
    return {**decision(target, refs), 'action_mode': 'RESEARCH',
            'local_object': 'Inspect the local feedback and work on the remaining boundary.',
            'proposed_boundary': 'Retain the exact assumptions.', 'remaining_gap': 'Open local step.',
            'expected_deliverable': 'A corrected derivation or precise unresolved step.',
            'evidence_refs': list(refs)}


@pytest.mark.parametrize('boundary', [None, 'call_completed', 'selection_saved'])
def test_displayed_navigation_read_is_unverified_and_recovery_does_not_recall(tmp_path, boundary):
    net, target, state, facts = navigation_case(tmp_path)
    schedule = deepcopy(state['schedule']); calls = []
    class Selector:
        def invoke(self, *, prompt, schema, label):
            calls.append(label)
            packet = json.loads(prompt.split('\nPACKET:\n')[1])
            assert REF in packet['cards'][0]['evidence_refs']
            return action(target)
    def crash(event, details):
        if event == boundary: raise Crash()
    if boundary:
        with pytest.raises(Crash):
            _Research(tmp_path, state, Selector(), crash).select_work(net)
    packet = _Research(tmp_path, state, Selector(), None).select_work(net)
    assert calls == ['continuous_selector']
    assert packet['accepted_facts'] == []
    assert packet['unverified_materials'][0]['ref'] == REF
    assert packet['unverified_materials'][0]['verified'] is False
    assert packet['unverified_materials'][0]['evidence']['fact_id'] == facts[0].fact_id
    assert state['schedule'] == schedule
    before = snapshot(tmp_path)
    for predecessor in (REF, facts[0].fact_id):
        with pytest.raises(ValueError, match='accepted visible Facts'):
            net.prepare_candidate({'kind':'FACT', 'goal':'A local result.', 'context':'',
                                   'proof':'Use the feedback.', 'predecessors':[predecessor]}, [])
    assert snapshot(tmp_path) == before
    assert _Research(tmp_path, state, Selector(), None).select_work(net) == packet
    assert calls == ['continuous_selector'] and snapshot(tmp_path) == before


def test_confirmed_response_rejected_by_old_contract_is_reused(monkeypatch, tmp_path):
    net, target, state, _ = navigation_case(tmp_path); calls = []
    class Selector:
        def invoke(self, **kwargs): calls.append(kwargs['label']); return action(target)
    schedule = deepcopy(state['schedule']); fixed = selection._displayed_refs
    # Reproduce the historical durable boundary, without replacing its response.
    with monkeypatch.context() as patch:
        patch.setattr(selection, '_displayed_refs', lambda exposure: fixed(exposure) - {REF})
        with pytest.raises(ValueError, match='unexposed evidence'):
            _Research(tmp_path, state, Selector(), None).select_work(net)
    assert not (tmp_path/'continuous_run/visits/00000001/selection.json').exists()
    results = list((tmp_path/'continuous_run/calls').glob('*/result.json'))
    assert len(results) == 1
    confirmed = results[0].read_bytes()
    packet = _Research(tmp_path, state, Selector(), None).select_work(net)
    assert results[0].read_bytes() == confirmed
    assert calls == ['continuous_selector']
    assert packet['unverified_materials'][0]['ref'] == REF
    assert state['schedule'] == schedule
    assert not list((tmp_path/'continuous_run/visits').glob('*/worker_result.json'))


def test_existing_but_undisplayed_reference_remains_rejected(tmp_path):
    net, target, state, _ = navigation_case(tmp_path)
    hidden = 'visits/00000000/verification.json'
    write_json(tmp_path/'continuous_run'/hidden, {'accepted': True})
    class Selector:
        def invoke(self, **kwargs): return action(target, [hidden])
    with pytest.raises(ValueError, match='unexposed evidence'):
        _Research(tmp_path, state, Selector(), None).select_work(net)


def test_compacted_or_unexposed_card_does_not_contribute_refs():
    card = {'study_id':'shown', 'ref':'study-ref'}
    assert REF not in selection._displayed_refs({'cards':[card]})
    assert REF in selection._displayed_refs({'cards':[{**card, 'evidence_refs':[REF]}]})


def test_displayed_path_does_not_expand_resolver_allowlist(tmp_path):
    net, target, state, _ = navigation_case(tmp_path)
    for ref in ('state.json', '../proof_graph.json', 'private.json'):
        write_json(tmp_path/'continuous_run/private.json', {'not':'local evidence'})
        fs, ms, notices = load_materials(tmp_path, target, [ref], state['studies'], net)
        assert not fs and not ms and notices


def test_foreign_fact_reference_still_requires_exact_scope(tmp_path):
    net, target, state, facts = navigation_case(tmp_path)
    ref = 'fact:' + facts[2].fact_id
    target['evidence_refs'].append(ref)
    write_json(tmp_path/'continuous_run'/state['studies'][target['study_id']], target)
    class Selector:
        def invoke(self, **kwargs): return action(target, [ref])
    with pytest.raises(ValueError, match='exact scope'):
        _Research(tmp_path, state, Selector(), None).select_work(net)


def test_historical_owner_scope_mismatch_is_not_rebound(tmp_path):
    net, target, state, _ = navigation_case(tmp_path)
    write_json(tmp_path/'continuous_run/visits/00000000/packet.json',
               {'study': {**target, 'scope':'An additional assumption.'}})
    with pytest.raises(ValueError, match='scope changed'):
        load_materials(tmp_path, target, [REF], state['studies'], net)
