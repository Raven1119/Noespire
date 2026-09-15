"""Object selection is bounded research navigation, never scheduling or truth."""
from copy import deepcopy
import json

import pytest

from research import continuous_research as research
from research.continuous_attention import bounded_packet
from research.continuous_selection import INSTRUCTIONS
from research.run_storage import read_json, write_json
from test_bridge_discovery import Crash, snapshot, study as create_study
from test_continuous_closure_actions import action, notes
from test_continuous_selection import fixture, decision


def case(root, count=2, peer=False):
    network, target, state, facts = fixture(root)
    target['continuation'] = '\n\n'.join(
        f'{i+1}. Object: Construction number {i}.\nBoundary: N = {247+i}.'
        for i in range(count))
    target['next_work'] = ''
    write_json(root/'continuous_run'/state['studies'][target['study_id']], target)
    studies = {target['study_id']: target}
    if peer:
        other, ref = create_study(root, 'study-peer', focus='A different finite construction.',
            continuation='Object: The independent peer construction.\nBoundary: M = 253.', next_work='')
        state['studies'][other['study_id']] = ref
        state['schedule']['channel_cursor'] = 0
        studies[other['study_id']] = other
    write_json(root/'continuous_run/state.json', state)
    return network, target, state, studies


def packet(prompt):
    return json.loads(prompt.split('\nPACKET:\n')[1])


@pytest.mark.parametrize('mode', ['RESEARCH', 'CLOSE'])
def test_object_interface_is_host_indexed_and_does_not_decide_action_maturity(tmp_path, mode):
    network, target, state, studies = case(tmp_path)
    before = deepcopy(state['schedule'])
    class Selector:
        def invoke(self, *, prompt, schema, label):
            assert label == 'continuous_selector'
            p = packet(prompt)
            assert schema['properties']['selected_object_id'] == {
                'anyOf': [{'type': 'null'}, {'type': 'string'}]}
            assert 'research_object_index' not in p
            page = p['research_object_cards']
            assert page['authority'] == 'UNVERIFIED_RESEARCH' and len(page['items']) == 2
            row = page['items'][0]
            assert row['remaining_gap'] == 'UNKNOWN'
            assert set(row) == {'object_id', 'study_id', 'object', 'boundary',
                'established_components', 'remaining_gap', 'possible_deliverable', 'evidence_refs'}
            return {**action(target, mode, row['evidence_refs']), 'selected_object_id': row['object_id']}
    run = research._Research(tmp_path, state, Selector(), None)
    out = run.select_work(network)
    frozen = read_json(run.step_dir/'selector_input.json')
    assert len(frozen['research_object_index']['cards']) == 2
    assert frozen['research_object_index']['sources']
    assert out['action_mode'] == mode and out['selected_object_id']
    assert out['accepted_facts'] == [] and out['unverified_materials'] == []
    assert 'research_object_cards' not in out and 'research_object_index' not in out
    assert state['schedule'] == before and network.truth(network.target_id) == 'OPEN'


@pytest.mark.parametrize('explicit_null', [False, True])
def test_research_can_select_no_object_and_legacy_decisions_keep_their_packet(tmp_path, explicit_null):
    network, target, state, _ = case(tmp_path)
    class Selector:
        def invoke(self, **kw):
            return {**decision(target), **({'selected_object_id': None} if explicit_null else {})}
    run = research._Research(tmp_path, state, Selector(), None)
    out = run.select_work(network)
    assert ('selected_object_id' in out) == explicit_null
    assert out.get('selected_object_id') is None
    saved = snapshot(tmp_path)
    assert run.select_work(network) == out and snapshot(tmp_path) == saved


@pytest.mark.parametrize('boundary', [None, 'call_completed', 'selector_page_saved', 'selection_saved'])
def test_object_pages_are_read_before_selection_and_recover_without_new_calls(tmp_path, boundary):
    network, target, state, _ = case(tmp_path, count=27)
    before = deepcopy(state['schedule'])
    seen, calls = set(), []
    class Selector:
        def invoke(self, *, prompt, schema, label):
            p = packet(prompt)
            calls.append(prompt)
            assert label == 'continuous_selector'
            bounded_packet({'prompt': prompt, 'schema': schema}, 8000)
            rows = p['research_object_cards']
            seen.update(r['object_id'] for r in rows['items'])
            assert not rows['unexpanded']
            if len(calls) > 1:
                assert p['local_action_evidence'] == {'items': [], 'unexpanded': []}
            if rows['next_ref']:
                return {**decision(target, [rows['next_ref']]), 'operation': 'INSPECT',
                        'selected_object_id': None}
            return {**decision(target), 'selected_object_id': rows['items'][-1]['object_id']}
    fired = False
    def crash(event, details):
        nonlocal fired
        if event == boundary and not fired:
            fired = True
            raise Crash()
    if boundary:
        with pytest.raises(Crash):
            research._Research(tmp_path, state, Selector(), crash).select_work(network)
    run = research._Research(tmp_path, state, Selector(), None)
    out = run.select_work(network)
    index = read_json(run.step_dir/'selector_input.json')['research_object_index']
    assert seen == {r['object_id'] for r in index['cards']} and len(seen) == 27
    assert len(calls) > 1 and out['selected_object_id'] in seen
    assert len(list((run.directory/'calls').glob('*/request.json'))) == len(calls)
    assert not list(run.step_dir.glob('*worker*')) and state['schedule'] == before
    assert out['accepted_facts'] == [] and out['unverified_materials'] == []
    frozen = snapshot(tmp_path)
    assert run.select_work(network) == out and snapshot(tmp_path) == frozen


@pytest.mark.parametrize('kind', ['fabricated', 'later-page', 'wrong-study'])
def test_only_an_actually_displayed_same_study_object_can_be_selected(tmp_path, kind):
    network, target, state, _ = case(tmp_path, count=27 if kind == 'later-page' else 2,
                                    peer=kind == 'wrong-study')
    run = research._Research(tmp_path, state, None, None)
    class Selector:
        def invoke(self, *, prompt, **kw):
            p = packet(prompt)
            key = 'research-object:fabricated'
            if kind == 'later-page':
                index = read_json(run.step_dir/'selector_input.json')['research_object_index']
                key = index['cards'][-1]['object_id']
                assert key not in {r['object_id'] for r in p['research_object_cards']['items']}
            elif kind == 'wrong-study':
                key = next(r['object_id'] for r in p['research_object_cards']['items']
                           if r['study_id'] == 'study-peer')
            return {**decision(target), 'selected_object_id': key}
    run.backend = Selector()
    with pytest.raises(ValueError, match='unexposed research object|another Study'):
        run.select_work(network)
    assert not (run.step_dir/'selection.json').exists()


def test_forced_study_override_rechecks_object_before_saving_selection(tmp_path):
    network, target, state, studies = case(tmp_path, peer=True)
    run = research._Research(tmp_path, state, None, None)
    frozen = run.selector_exposure(network, studies)
    frozen['exposure']['forced_study_id'] = target['study_id']
    write_json(run.step_dir/'selector_input.json', frozen)
    class Selector:
        def invoke(self, *, prompt, **kw):
            row = next(r for r in packet(prompt)['research_object_cards']['items']
                       if r['study_id'] == 'study-peer')
            return {**decision(studies['study-peer']), 'selected_object_id': row['object_id']}
    run.backend = Selector()
    with pytest.raises(ValueError, match='another Study'):
        run.select_work(network)
    assert not (run.step_dir/'selection.json').exists()


@pytest.mark.parametrize('change', ['study', 'object'])
def test_recovery_revalidates_saved_object_identity(tmp_path, change):
    network, target, state, _ = case(tmp_path, peer=True)
    class Selector:
        def invoke(self, *, prompt, **kw):
            row = next(r for r in packet(prompt)['research_object_cards']['items']
                       if r['study_id'] == target['study_id'])
            return {**decision(target), 'selected_object_id': row['object_id']}
    run = research._Research(tmp_path, state, Selector(), None)
    run.select_work(network)
    selection = read_json(run.step_dir/'selection.json')
    if change == 'study':
        selection['selected']['study_id'] = 'study-peer'
    else:
        selection['selected']['selected_object_id'] = 'research-object:unseen'
    write_json(run.step_dir/'selection.json', selection)
    with pytest.raises(ValueError, match='another Study|unexposed research object'):
        run.select_work(network)


@pytest.mark.parametrize('boundary', [None, 'selector_page_saved', 'call_completed'])
@pytest.mark.parametrize('source', ['study', 'checkpoint'])
def test_source_inspection_is_complete_same_study_and_not_automatically_forwarded(tmp_path, boundary, source):
    network, target, state, _ = case(tmp_path)
    if source == 'checkpoint':
        notes(tmp_path, state, target)
    calls = []
    chosen = {}
    class Selector:
        def invoke(self, *, prompt, schema, label):
            p = packet(prompt)
            calls.append(prompt)
            if len(calls) == 1:
                row = next(r for r in p['research_object_cards']['items']
                           if any(ref.startswith('research_deliveries/') == (source == 'checkpoint')
                                  for ref in r['evidence_refs']))
                chosen.update(row)
                return {**decision(target, [row['evidence_refs'][0]]), 'operation': 'INSPECT',
                        'selected_object_id': row['object_id']}
            materials = p['local_action_evidence']['items']
            assert len(materials) == 1 and materials[0]['verified'] is False
            assert materials[0]['ref'] == chosen['evidence_refs'][0]
            if source == 'study':
                assert materials[0]['study']['continuation'] == target['continuation']
            else:
                assert 'b_j=1/(j+1)' in materials[0]['content']['derivation']
                assert materials[0]['raw_message'] and materials[0]['authority'] == 'UNVERIFIED_RESEARCH'
            assert p['fact_interfaces']['items'] == []
            bounded_packet({'prompt': prompt, 'schema': schema}, 8000)
            return {**decision(target), 'selected_object_id': chosen['object_id']}
    fired = False
    def crash(event, details):
        nonlocal fired
        if event == boundary and not fired:
            fired = True
            raise Crash()
    if boundary:
        with pytest.raises(Crash):
            research._Research(tmp_path, state, Selector(), crash).select_work(network)
    run = research._Research(tmp_path, state, Selector(), None)
    out = run.select_work(network)
    assert len(calls) == 2 and out['selected_object_id'] == chosen['object_id']
    assert out['accepted_facts'] == [] and out['unverified_materials'] == []
    assert not list(run.step_dir.glob('*worker*'))


@pytest.mark.parametrize('kind', ['repeated', 'other-study', 'fact'])
def test_source_inspection_never_repeats_or_expands_to_unadvertised_material(tmp_path, kind):
    network, target, state, _ = case(tmp_path, peer=kind == 'other-study')
    calls, requested = [], []
    class Selector:
        def invoke(self, *, prompt, **kw):
            p = packet(prompt)
            calls.append(prompt)
            if requested:
                ref = requested[0]
            elif kind == 'fact':
                ref = p['fact_interfaces']['items'][0]['ref']
            else:
                owner = 'study-peer' if kind == 'other-study' else target['study_id']
                row = next(r for r in p['research_object_cards']['items'] if r['study_id'] == owner)
                ref = row['evidence_refs'][0]
                requested.append(ref)
            return {**decision(target, [ref]), 'operation': 'INSPECT', 'selected_object_id': None}
    run = research._Research(tmp_path, state, Selector(), None)
    with pytest.raises(ValueError, match='INSPECT'):
        run.select_work(network)
    assert len(calls) == (2 if kind == 'repeated' else 1)
    assert not (run.step_dir/'selection.json').exists()


def test_oversized_original_source_is_explicitly_unexpanded(tmp_path):
    network, target, state, _ = case(tmp_path)
    target['continuation'] += '\n\nOriginal source details: ' + 'essential condition; ' * 3000
    write_json(tmp_path/'continuous_run'/state['studies'][target['study_id']], target)
    calls = []
    class Selector:
        def invoke(self, *, prompt, **kw):
            p = packet(prompt)
            calls.append(prompt)
            if len(calls) == 1:
                ref = p['research_object_cards']['items'][0]['evidence_refs'][0]
                return {**decision(target, [ref]), 'operation': 'INSPECT', 'selected_object_id': None}
            assert not p['local_action_evidence']['items']
            assert p['local_action_evidence']['unexpanded'][0]['reason'] == 'complete_source_exceeds_selector_context'
            assert target['continuation'] not in prompt
            return {**decision(target), 'selected_object_id': None}
    out = research._Research(tmp_path, state, Selector(), None).select_work(network)
    assert len(calls) == 2 and out['accepted_facts'] == []


def test_selected_object_id_never_enters_accepted_facts_or_predecessors(tmp_path):
    network, target, state, _ = case(tmp_path)
    class Selector:
        def invoke(self, *, prompt, **kw):
            row = packet(prompt)['research_object_cards']['items'][0]
            return {**decision(target, [row['object_id']]), 'selected_object_id': row['object_id']}
    out = research._Research(tmp_path, state, Selector(), None).select_work(network)
    assert out['accepted_facts'] == [] and out['unverified_materials'] == []
    assert out['material_notices'] == [{'ref': out['selected_object_id'], 'error': 'unknown local reference'}]
    with pytest.raises(ValueError, match='accepted visible Facts'):
        network.prepare_candidate({'kind': 'FACT', 'goal': target['focus'], 'context': target['scope'],
            'proof': 'Cite the card.', 'predecessors': [out['selected_object_id']], 'requirements': []}, [])
    assert network.truth(network.target_id) == 'OPEN'
