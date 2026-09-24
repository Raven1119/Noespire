"""Deterministic control evidence; fixtures do not establish mathematics."""
import json

from danus.core import LocalMemory
from crpn.engine import Research
from crpn.materials import selector_packet, worker_packet
from crpn.model import Network, make_claim
from crpn.scheduler import focus
from crpn.work import awakened, derive, interface_snapshot, reference_snapshot
from substrate.store import lane
from test_engine import Actors, action, candidate, output, runtime, start_after_initial_direct
from test_model import fact, support


def cut_for(network, schedule=None):
    exposure, next_schedule = focus(network.active_studies(), schedule or {})
    cut, options, versions = derive(network, exposure)
    return exposure, next_schedule, cut, options, versions


def test_same_cut_is_bounded_with_one_thousand_and_ten_thousand_unrelated_claims(tmp_path):
    net = Network.create(tmp_path, 'scale', 'Exact target')
    packets = []
    for count in (0, 1000, 10000):
        for i in range(len(net.data['claims']) - 1, count):
            unrelated = make_claim(net.problem_id, '', f'Unrelated proposition {i}')
            net.data['claims'][unrelated['claim_id']] = unrelated
        net.ensure_studies(save=False)
        for sid, study in net.data['studies'].items():
            if sid != 'study-' + net.target_id:
                study['last_served_visit'] = 0
        net.save()
        net = Network(tmp_path)
        exposure, _, cut, options, _ = cut_for(net)
        assert len(net.active_studies()) == count + 1
        assert exposure['focus_study_id'] == 'study-' + net.target_id
        assert len(exposure['cards']) == 1 and len(options) <= 4
        selection = selector_packet(net, exposure, cut=cut, options=options)
        worker = worker_packet(net, options[0], cut=cut)
        packets.append((len(json.dumps(selection).encode()), len(json.dumps(worker).encode())))
    assert packets[0] == packets[1] == packets[2]


def test_unrelated_fact_does_not_invalidate_observed_work_but_shared_requirement_does(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    left = support(net, 'Target', ['Shared', 'Left'])
    right = support(net, 'Target', ['Shared', 'Right'])
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    net.save()
    _, _, _, _, observed = cut_for(net)
    net.data['studies'][root]['observed_versions'] = observed
    net.save()
    unrelated = net.register_claim('No shared premise')
    fact(net, unrelated['claim_id'])
    _, _, cut, _, _ = cut_for(net)
    assert cut['changes'] == []
    assert root not in awakened(net, net.active_studies())
    shared = net.register_claim('Shared')
    fact(net, shared['claim_id'])
    _, _, cut, _, _ = cut_for(net)
    assert 'claim:' + shared['claim_id'] in cut['changes']
    assert root in awakened(net, net.active_studies())
    assert {left['support_id'], right['support_id']} <= {r['support_id'] for r in cut['routes']}
    assert all(not r['compose_ready'] for r in cut['routes'])


def test_many_routes_rotate_without_entering_one_selector_packet(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    for i in range(48):
        support(net, 'Target', [f'Requirement {i} A', f'Requirement {i} B'])
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    seen = set()
    for cursor in range(48):
        net.data['studies'][root]['work_cursor'] = cursor
        exposure, _, cut, options, _ = cut_for(net)
        seen.update(route['support_id'] for route in cut['routes'])
        assert len(cut['routes']) <= 4 and len(options) <= 4
        assert len(json.dumps(selector_packet(net, exposure, cut=cut, options=options)).encode()) < 96000
    assert len(seen) == 48


def test_saved_next_work_is_a_lead_while_the_exact_gap_stays_in_every_cut(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    route = support(net, 'Target', ['Actual missing interface'])
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'next_work': 'Extend the endpoint to 1809.',
                            'continuation': 'This endpoint is only a finite check.'})
    intermediate = fact(net, net.register_claim('Finite endpoint 1808')['claim_id'])
    memory.append('events', {'task': 'Explore the finite construction',
                             'tool_submissions': [{'accepted': True, 'fact_id': intermediate}]})
    for cursor in range(8):
        net.data['studies'][root]['work_cursor'] = cursor
        exposure, _, cut, options, _ = cut_for(net)
        assert cut['task_frame']['focus_truth'] == 'OPEN'
        assert cut['task_frame']['open_requirements'][0]['claim_id'] == route['requirement_claim_ids'][0]
        assert cut['task_frame']['recent_receipts'][0]['fact_id'] == intermediate
        assert cut['task_frame']['recent_receipts'][0]['graph_interface'] is False
        assert 'statement_excerpt' not in cut['task_frame']['recent_receipts'][0]
        assert cut['unfinished'] is None
        assert cut['local_state']['previous_suggestions'][0]['text'] == 'Extend the endpoint to 1809.'
        assert options[0]['operation'] == 'RESEARCH' and 'endpoint' not in options[0]['task']
        assert len(options) <= 4
        packet = selector_packet(net, exposure, cut=cut, options=options)
        assert packet['cut']['focus']['claim'] == net.claim(net.target_id)
        assert packet['cut']['task_frame']['unresolved_focus_claim_id'] == net.target_id
    net.revoke(intermediate, 'Fixture revocation')
    _, _, cut, options, _ = cut_for(net)
    assert cut['task_frame']['recent_receipts'][0]['status'] == 'revoked'
    assert all(intermediate not in option['fact_ids'] for option in options)


def test_existing_results_are_bounded_advisory_material_for_the_local_residual(tmp_path):
    net = Network.create(tmp_path, 'p', 'Prove an open theorem')
    root = 'study-' + net.target_id
    stronger = fact(net, net.register_claim('For the same witness, feasibility holds for N <= 1867')['claim_id'])
    fact(net, net.register_claim('Another construction has a distinct failure mechanism')['claim_id'])
    LocalMemory(lane(tmp_path, root)).append('events', {
        'task': 'For the same witness, prove feasibility for N <= 1810',
        'tool_submissions': [{'accepted': True, 'fact_id': stronger}]})
    LocalMemory(lane(tmp_path, root)).append('notes', {
        'next_work': 'For the same witness, prove feasibility for N <= 1810'})
    exposure, _, cut, options, _ = cut_for(net)
    view = cut['task_residual']
    assert view['authority'] == 'UNVERIFIED_RESEARCH_STATE'
    assert view['coverage'] == 'UNDETERMINED'
    assert view['current_task'] == 'For the same witness, prove feasibility for N <= 1810'
    core = cut['shared_evidence_core']['results']
    assert core[0]['fact_id'] == stronger
    assert 'STUDY_ACCEPTED' in core[0]['source']
    assert len(core) <= 4
    assert all(row['relation'] == 'POTENTIALLY_RELEVANT_NOT_PROVEN' for row in core)
    assert '1810' not in options[0]['task']  # Saved next_work is not a repeated primary action.
    assert selector_packet(net, exposure, cut=cut, options=options)['cut']['task_residual'] == view
    worker_cut = worker_packet(net, options[0], cut=cut)['local_cut']
    worker_view = worker_cut['task_residual']
    assert worker_view['current_task'] == options[0]['task']
    assert worker_cut['shared_evidence_core']['results'][0]['fact_id'] == stronger
    assert net.truth(net.target_id) == 'OPEN'


def test_exact_known_task_can_be_saturated_without_removing_or_proofs(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open parent')
    root = 'study-' + net.target_id
    known = net.register_claim('Exact local result')
    first = fact(net, known['claim_id'], proof='First complete fixture proof.')
    LocalMemory(lane(tmp_path, root)).append('notes', {'next_work': 'Exact local result'})
    _, _, cut, options, _ = cut_for(net)
    assert cut['shared_evidence_core']['results'][0]['fact_id'] == first
    assert cut['task_residual']['may_be_saturated'] is True
    assert all(row['task'] != 'Exact local result' for row in options)
    second = fact(net, known['claim_id'], proof='Independent second fixture proof.')
    assert second != first
    assert {first, second} <= set(Network(tmp_path).proof_ids())
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_different_construction_scope_and_consumer_remain_researchable(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open parent')
    root = 'study-' + net.target_id
    stronger = fact(net, net.register_claim('Construction A works through 1867')['claim_id'])
    foreign = fact(net, net.register_claim('Construction A works through 2000', 'foreign scope')['claim_id'])
    support(net, 'Open parent', ['Consumer needs construction B interface'])
    LocalMemory(lane(tmp_path, root)).append('notes', {
        'next_work': 'Study construction B failure mechanism through 1810 for the consumer'})
    _, _, cut, options, _ = cut_for(net)
    rows = cut['shared_evidence_core']['results']
    assert any(row['fact_id'] == stronger and row['same_scope'] for row in rows)
    assert any(row['fact_id'] == foreign and not row['same_scope'] for row in rows)
    assert cut['task_frame']['open_requirements'][0]['statement'].endswith('Consumer needs construction B interface')
    assert any(row['operation'] == 'RESEARCH' for row in options)
    assert net.truth(net.target_id) == 'OPEN'


def test_cross_study_result_is_only_a_lead_in_next_local_cut(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open parent')
    parent = 'study-' + net.target_id
    support(net, 'Open parent', ['Unresolved dependency'])
    LocalMemory(lane(tmp_path, parent)).append('notes', {
        'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'A route needs a modular interface.',
                           'unfinished_derivation': '',
                           'open_question': 'Can the modular interface close the gap?',
                           'recheck_reason': ''}})
    LocalMemory(lane(tmp_path, parent)).append('events', {
        'source_key': 'run:1:service', 'task': 'Inspect modular route.'})
    arrived = fact(net, net.register_claim('Modular interface from another Study')['claim_id'])
    cut, options, _ = derive(Network(tmp_path), {
        'focus_study_id': parent, 'channel': 'ADVANCE',
        'external_study_id': None, 'explore_mode': None})
    assert any(row['fact_id'] == arrived and 'TASK_SEARCH_LEAD' in row['source']
               for row in cut['shared_evidence_core']['results'])
    assert cut['task_residual']['coverage'] == 'UNDETERMINED'
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'
    assert any(row['operation'] == 'RESEARCH' for row in options)


def test_task_search_result_survives_receipt_and_certificate_competition(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open parent')
    study_id = 'study-' + net.target_id
    route = support(net, 'Open parent', ['Unproved interface'])
    older = [fact(net, net.register_claim(f'Old endpoint {i}')['claim_id']) for i in range(3)]
    relevant = fact(net, net.register_claim('Exact construction boundary through 1871')['claim_id'])
    memory = LocalMemory(lane(tmp_path, study_id))
    memory.append('events', {'task': 'Earlier endpoint work', 'tool_submissions': [
        {'accepted': True, 'fact_id': fid} for fid in older]})
    memory.append('notes', {'next_work': 'Check the exact construction boundary through 1871'})
    exposure, _, cut, options, _ = cut_for(net)
    core = cut['shared_evidence_core']['results']
    assert len(core) <= 4
    assert relevant in [row['fact_id'] for row in core]
    assert cut['task_residual']['coverage'] == 'UNDETERMINED'
    assert net.truth(net.target_id) == 'OPEN'
    selector = selector_packet(net, exposure, cut=cut, options=options)
    worker = worker_packet(net, options[0], cut=cut)
    assert [row['fact_id'] for row in selector['cut']['shared_evidence_core']['results']] == [
        row['fact_id'] for row in worker['local_cut']['shared_evidence_core']['results']]
    assert worker['accepted_facts'] == []
    assert 'related_results' not in worker


def test_shared_core_deduplicates_evidence_and_keeps_unselected_searchable(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open theorem')
    study_id = 'study-' + net.target_id
    route = support(net, 'Open theorem', ['Needed local interface'])
    direct = fact(net, route['requirement_claim_ids'][0])
    results = [fact(net, net.register_claim(f'Boundary 1871 method {i}')['claim_id'])
               for i in range(25)]
    memory = LocalMemory(lane(tmp_path, study_id))
    memory.append('events', {'task': 'Boundary 1871 method',
        'tool_submissions': [{'accepted': True, 'fact_id': results[0]}]})
    memory.append('notes', {'next_work': f'Compare {results[0]} with Boundary 1871 method'})
    exposure, _, cut, options, _ = cut_for(net)
    core = cut['shared_evidence_core']['results']
    ids = [row['fact_id'] for row in core]
    assert len(ids) == len(set(ids)) <= 4
    assert results[0] in ids and direct in ids
    assert {'EXPLICIT_TASK_REFERENCE', 'STUDY_ACCEPTED', 'TASK_SEARCH_LEAD'} <= set(
        next(row['source'] for row in core if row['fact_id'] == results[0]))
    assert cut['shared_evidence_core']['_audit']['candidate_count'] > 20
    packet = selector_packet(net, exposure, cut=cut, options=options)
    assert '_audit' not in packet['cut']['shared_evidence_core']
    assert len(packet['cut']['shared_evidence_core']['results']) <= 4
    hidden = next(fid for fid in results if fid not in ids)
    assert any(hit['fact_id'] == hidden for hit in net.search('Boundary 1871 method', 40))
    net.revoke(results[0], 'fixture correction')
    _, _, refreshed, _, _ = cut_for(Network(tmp_path))
    assert results[0] not in [row['fact_id'] for row in refreshed['shared_evidence_core']['results']]
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_stale_boundary_is_visible_without_programmatic_coverage_claim(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open theorem for every construction')
    study_id = 'study-' + net.target_id
    older = [fact(net, net.register_claim(f'Finite endpoint through {n}')['claim_id'])
             for n in (836, 1469, 1810)]
    same = fact(net, net.register_claim('Construction A feasible through N=1871')['claim_id'])
    other = fact(net, net.register_claim('Construction B feasible through N=2000',
                                        'different ambient scope')['claim_id'])
    memory = LocalMemory(lane(tmp_path, study_id))
    memory.append('events', {'task': 'Old finite work', 'tool_submissions': [
        {'accepted': True, 'fact_id': fid} for fid in older]})
    memory.append('notes', {'next_work': 'N=1868 is first uncovered for Construction A'})
    _, _, cut, options, _ = cut_for(net)
    core = cut['shared_evidence_core']['results']
    assert same in [row['fact_id'] for row in core]
    assert cut['task_residual']['coverage'] == 'UNDETERMINED'
    assert cut['task_residual']['remaining_work'] == 'MODEL_MUST_ASSESS'
    assert any(row['operation'] == 'RESEARCH' for row in options)
    assert net.truth(net.target_id) == 'OPEN'
    # The foreign, different-construction result remains a distinct searchable
    # evidence record; neither its larger N nor lexical similarity proves use.
    assert net.inspect_fact(other)['scope'] == 'different ambient scope'
    assert other in [hit['fact_id'] for hit in net.search('Construction B N=2000', 10)]


def test_obstacle_handover_rebuilds_and_does_not_default_to_repeating_diagnosis(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
                            'continuation': 'Checked the accepted P implies Q interface. It cannot prove P; '
                                            'the converse or another route is missing.',
                            'next_work': 'Prove P directly.'})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
                             'channel': 'ADVANCE',
                             'task': 'Examine whether this accepted interface addresses P.'})
    before = (tmp_path / 'crpn.json').read_bytes()
    exposure, _, cut, options, _ = cut_for(net)
    state = cut['local_state']
    assert state['authority'] == 'UNVERIFIED_RESEARCH_STATE'
    assert 'cannot prove P' in state['completed_actions'][0]['observation']
    assert state['completed_actions'][0]['classification'] == 'HISTORICAL_UNCLASSIFIED'
    assert state['completed_actions'][0]['observation_graph_version'] == 'UNKNOWN'
    assert state['completed_actions'][0]['task'].startswith('Examine')
    assert not state['recent_evidence_changes']
    assert 'concrete open question' in options[0]['task']
    assert all('Examine whether this accepted interface' not in option['task'] for option in options)
    assert cut['unfinished'] is None
    assert state['previous_suggestions'][0]['text'] == 'Prove P directly.'
    assert net.truth(net.target_id) == 'OPEN' and not net.proof_ids() and not net.data['supports']
    assert (tmp_path / 'crpn.json').read_bytes() == before
    # A fresh process reconstructs the same advisory state from existing records.
    _, _, rebuilt, _, _ = cut_for(Network(tmp_path))
    assert rebuilt['local_state'] == state


def test_obstacle_reopens_on_exact_graph_change_and_revisit_allows_reasoned_doubt(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    route = support(net, 'P', ['Missing condition', 'Still missing'])
    root = 'study-' + net.target_id
    memory = LocalMemory(lane(tmp_path, root))
    before_versions, before_evidence = interface_snapshot(net, net.data['studies'][root])
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
                            'continuation': 'The old interface has only the wrong implication direction.',
                            'next_work': 'Find a usable interface.',
                            'observation_graph_versions': before_versions,
                            'observation_graph_evidence': before_evidence})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
                             'task': 'Inspect the old interface.'})
    _, _, _, _, versions = cut_for(net)
    net.data['studies'][root]['observed_versions'] = versions
    net.save()
    fact(net, net.register_claim('Missing condition')['claim_id'])
    _, _, cut, options, _ = cut_for(net)
    assert route['requirement_claim_ids'][0] in cut['changes'][0]
    assert cut['local_state']['recent_evidence_changes'][0]['kind'] == 'EXACT_GRAPH_INTERFACE_CHANGE'
    assert cut['local_state']['recent_evidence_changes'][0]['evidence'][0]['now'] == 'accepted'
    assert any('changed exact interface' in row['task'] for row in options)
    memory.append('notes', {'content': 'I suspect my earlier diagnosis missed a condition.'})
    revisit = {'focus_study_id': root, 'external_study_id': None,
               'explore_mode': None, 'channel': 'REVISIT'}
    cut, options, _ = derive(Network(tmp_path), revisit)
    assert any(row['notes'] == 'reasoned revisit' for row in options)
    assert cut['local_state']['recent_evidence_changes']
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'
    corrected_versions, corrected_evidence = interface_snapshot(Network(tmp_path), Network(tmp_path).data['studies'][root])
    memory.append('notes', {'source_key': 'run:2:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'The earlier diagnosis missed a usable condition.',
                           'unfinished_derivation': '', 'open_question': 'Can it discharge P?',
                           'recheck_reason': 'New accepted condition changes the interface.'},
        'observation_graph_versions': corrected_versions,
        'observation_graph_evidence': corrected_evidence})
    memory.append('events', {'source_key': 'run:2:service', 'status': 'COMPLETED',
        'task': 'Recheck with the new condition.'})
    corrected, corrected_options, _ = derive(Network(tmp_path), revisit)
    assert corrected['local_state']['completed_actions'][0]['observation'].startswith('The earlier diagnosis missed')
    assert corrected['local_state']['completed_actions'][1]['observation'].startswith('The old interface')
    assert corrected['local_state']['recent_evidence_changes'] == []
    assert 'Use the new exact evidence' not in corrected_options[0]['task']


def test_obstacle_does_not_suppress_unknown_explore_direction(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    LocalMemory(lane(tmp_path, root)).append('notes', {
        'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'continuation': 'An attempted route is blocked.', 'next_work': 'Investigate a condition.'})
    exposure = {'focus_study_id': root, 'external_study_id': None,
                'explore_mode': 'OPEN', 'channel': 'EXPLORE'}
    cut, options, _ = derive(net, exposure)
    assert cut['local_state']['previous_suggestions']
    assert any(row['notes'] == 'open exploration' for row in options)
    assert len(options) <= 4


def test_completed_observation_and_unfinished_derivation_have_different_actions(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'S proves P implies Q only.',
                           'unfinished_derivation': '', 'open_question': 'Can a different interface prove P?',
                           'recheck_reason': ''},
        'observation_graph_versions': {}, 'examined_evidence_ids': ['0123456789abcdef'],
        'next_work': 'Inspect S again.'})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
        'task': 'Inspect S for the required direction.'})
    _, _, cut, options, _ = cut_for(net)
    assert cut['local_state']['completed_actions'][0]['observation'] == 'S proves P implies Q only.'
    assert cut['local_state']['completed_actions'][0]['examined_evidence_ids'] == ['0123456789abcdef']
    assert cut['local_state']['unfinished_derivation'] is None
    assert cut['unfinished'] is None
    assert cut['local_state']['previous_suggestions'][0]['text'] == 'Inspect S again.'
    assert all('Inspect S again.' not in option['task'] for option in options)
    memory.append('notes', {'source_key': 'run:2:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': '',
                           'unfinished_derivation': 'Steps 1-4 establish a bound; step 5 remains.',
                           'open_question': 'Can step 5 be proved?', 'recheck_reason': ''},
        'observation_graph_versions': {}, 'examined_evidence_ids': []})
    memory.append('events', {'source_key': 'run:2:service', 'status': 'COMPLETED',
                             'task': 'Try the bound.'})
    _, _, cut, options, _ = cut_for(Network(tmp_path))
    assert cut['local_state']['unfinished_derivation']['text'].startswith('Steps 1-4')
    assert len(cut['local_state']['completed_actions']) == 1
    assert [q['text'] for q in cut['local_state']['open_questions']] == ['Can step 5 be proved?']
    assert options[0]['task'].startswith('Continue the specific unfinished derivation')
    assert cut['local_state'] == cut_for(Network(tmp_path))[2]['local_state']
    memory.append('notes', {'source_key': 'run:3:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'The earlier step was completed.',
                           'unfinished_derivation': '', 'open_question': '', 'recheck_reason': ''}})
    memory.append('events', {'source_key': 'run:3:service', 'status': 'COMPLETED',
                             'task': 'Finish step 5.'})
    _, _, resolved, _, _ = cut_for(Network(tmp_path))
    assert resolved['local_state']['unfinished_derivation'] is None
    assert resolved['local_state']['open_questions'] == []


def test_revoked_examined_evidence_reopens_observation_without_granting_truth(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    examined = fact(net, net.register_claim('Auxiliary')['claim_id'])
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'Auxiliary may help the route.',
                           'unfinished_derivation': '', 'open_question': 'Does it connect?',
                           'recheck_reason': ''}, 'examined_evidence_ids': [examined]})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
                             'task': 'Inspect Auxiliary.'})
    net.revoke(examined, 'Fixture error')
    _, _, cut, options, _ = cut_for(Network(tmp_path))
    assert cut['local_state']['recent_evidence_changes'][0]['kind'] == 'EXAMINED_EVIDENCE_INVALIDATED'
    assert all(examined not in option['fact_ids'] for option in options)
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_new_actual_predecessor_reference_reopens_old_observation(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    examined = fact(net, net.register_claim('A')['claim_id'])
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'No known route from A yet.',
                           'unfinished_derivation': '', 'open_question': 'Could A yield a route?',
                           'recheck_reason': ''}, 'examined_evidence_ids': [examined],
        'observation_graph_versions': {},
        'observation_referenced_proofs': reference_snapshot(net, [examined])})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
                             'task': 'Inspect A.'})
    dependent = fact(net, net.register_claim('B')['claim_id'], predecessors=[examined])
    _, _, cut, _, _ = cut_for(Network(tmp_path))
    delta = next(row for row in cut['local_state']['recent_evidence_changes']
                 if row['kind'] == 'ACTUAL_PREDECESSOR_CHANGE')
    assert delta['fact_id'] == dependent and delta['now']['predecessors'] == [examined]
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_full_evidence_context_is_compared_but_packet_remains_bounded(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    exposed = [fact(net, net.register_claim(f'A{i}')['claim_id']) for i in range(9)]
    ninth = sorted(exposed)[8]
    fact(net, net.register_claim('Dependent')['claim_id'], predecessors=[ninth])
    observed_versions, _ = interface_snapshot(net, net.data['studies'][root])
    memory = LocalMemory(lane(tmp_path, root))
    memory.append('notes', {'source_key': 'run:1:worker-return', 'source_status': 'COMPLETED',
        'research_state': {'completed_observation': 'I examined nine interfaces.',
                           'unfinished_derivation': '', 'open_question': 'What follows?',
                           'recheck_reason': ''}, 'examined_evidence_ids': sorted(exposed),
        'observation_graph_versions': observed_versions,
        'observation_referenced_proofs': reference_snapshot(net, exposed)})
    memory.append('events', {'source_key': 'run:1:service', 'status': 'COMPLETED',
                             'task': 'Inspect nine interfaces.'})
    _, _, cut, _, _ = cut_for(Network(tmp_path))
    assert len(cut['local_state']['completed_actions'][0]['examined_evidence_ids']) == 8
    assert cut['local_state']['recent_evidence_changes'] == []


def test_timeout_partial_derivation_recovers_from_local_memory_without_truth(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    LocalMemory(lane(tmp_path, root)).append('notes', {
        'content': 'UNFINISHED DERIVATION:\nEstablished cases 1-4; final bound remains.',
        'source_service': 'run:1:worker'})
    exposure = {'focus_study_id': root, 'external_study_id': None,
                'explore_mode': None, 'channel': 'REVISIT'}
    cut, options, _ = derive(Network(tmp_path), exposure)
    assert cut['local_state']['unfinished_derivation']['origin'] == 'LOCAL_MEMORY_PARTIAL'
    assert cut['local_state']['unfinished_derivation']['source_service'] == 'run:1:worker'
    assert options[0]['task'].startswith('Continue the specific unfinished derivation')
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_confirmed_worker_handover_recovers_with_observation_graph_version(tmp_path):
    net = Network.create(tmp_path, 'p', 'P')
    root = 'study-' + net.target_id
    def handler(role, packet):
        assert role == 'worker'
        result = output(continuation='Worked through four steps, with the fifth unproved.',
                        next_work='Try the final estimate.')
        result['research_state'] = {'completed_observation': 'Steps 1-4 derived a conditional bound.',
            'unfinished_derivation': 'The final estimate in step 5 remains unproved.',
            'open_question': 'Does the conditional bound hold uniformly?', 'recheck_reason': ''}
        return result
    actors = Actors(handler)
    assert Research(tmp_path, runtime(tmp_path, actors)).step()['status'] == 'COMPLETED'
    reloaded = Network(tmp_path)
    exposure = {'focus_study_id': root, 'external_study_id': None,
                'explore_mode': None, 'channel': 'REVISIT'}
    cut, options, _ = derive(reloaded, exposure)
    action = cut['local_state']['completed_actions'][0]
    assert action['observation_graph_version'] != 'UNKNOWN'
    assert action['source_study_id'] == root
    assert action['source_service'].endswith(':service')
    assert cut['local_state']['unfinished_derivation']['text'].startswith('The final estimate')
    assert options[0]['task'].startswith('Continue the specific unfinished derivation')
    assert reloaded.truth(reloaded.target_id) == 'OPEN'


def test_study_task_guidance_does_not_change_proof_authority(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    root = 'study-' + net.target_id
    LocalMemory(lane(tmp_path, root)).append('notes', {'next_work': 'A plausible unproved lemma.'})
    _, _, cut, _, _ = cut_for(net)
    assert cut['task_frame']['focus_truth'] == 'OPEN'
    assert net.proof_ids() == []
    assert net.truth(net.target_id) == 'OPEN'


def test_overwide_support_is_paginated_hint_not_a_partial_compose(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    requirements = [f'Requirement {i}: a long explicit condition on the original domain and variables'
                    for i in range(240)]
    row = support(net, 'Target', requirements)
    for sid, study in net.data['studies'].items():
        if sid != 'study-' + net.target_id:
            study['last_served_visit'] = 0
    _, _, cut, options, _ = cut_for(net)
    route = next(r for r in cut['routes'] if r['support_id'] == row['support_id'])
    assert route['requirements_count'] == 240 and route['interface_page_required']
    assert route['compose_ready'] is False
    assert not any(action['operation'] == 'COMPOSE' for action in options)


def test_ready_or_route_is_dispatched_without_selector_and_other_route_survives_revocation(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    first = support(net, 'Target', ['A', 'Shared'])
    second = support(net, 'Target', ['B', 'Shared'])
    fa = fact(net, net.register_claim('A')['claim_id'])
    fact(net, net.register_claim('B')['claim_id'])
    fact(net, net.register_claim('Shared')['claim_id'])
    net.revoke(fa, 'fixture invalidation')
    start_after_initial_direct(net)
    _, _, cut, options, _ = cut_for(net)
    assert options[0]['operation'] == 'COMPOSE'
    assert options[0]['support_id'] == second['support_id']
    assert first['support_id'] != second['support_id']
    def handler(role, packet):
        assert role != 'selector'
        if role == 'verifier':
            return {'verdict': 'correct', 'reason': 'Deterministic fixture acceptance.'}
        assert packet['operation'] == 'COMPOSE'
        return output(candidate('Target', predecessors=[r['fact_id'] for r in packet['accepted_facts']]))
    actors = Actors(handler)
    outcome = Research(tmp_path, runtime(tmp_path, actors)).step()
    assert outcome['admission']['kind'] == 'FACT'
    assert actors.count('selector') == 0 and actors.count('worker') == 1
    assert Network(tmp_path).truth(net.target_id) == 'DISCHARGED'


def test_fair_focus_visits_every_open_study_without_selector():
    studies = [{'study_id': f'study-{i:02d}', 'focus': f'Focus {i}', 'scope': '',
                'revision': 0} for i in range(23)]
    schedule, visited = {}, set()
    for visit in range(150):
        exposure, schedule = focus(studies, schedule)
        sid = exposure['focus_study_id']
        visited.add(sid)
        next(row for row in studies if row['study_id'] == sid)['last_served_visit'] = visit
        if visit == 20:
            studies.append({'study_id': 'study-new', 'focus': 'New independent region',
                            'scope': '', 'revision': 0})
    assert visited == {row['study_id'] for row in studies}
    assert schedule['channel_cursor'] == 150


def test_dependency_wake_uses_only_one_of_three_advance_slots():
    studies = [{'study_id': 'old', 'focus': 'Old task', 'scope': '', 'last_served_visit': -1},
               {'study_id': 'awakened', 'focus': 'New exact dependency', 'scope': '', 'last_served_visit': 9}]
    first, schedule = focus(studies, {}, priority_ids={'awakened'})
    assert first['focus_study_id'] == 'awakened' and first['focus_reason'] == 'DEPENDENCY_WAKE'
    second, schedule = focus(studies, schedule, priority_ids={'awakened'})
    assert second['focus_study_id'] == 'old' and second['focus_reason'] == 'FAIR_ADVANCE'


def test_region_meeting_delivers_a_navigation_lead_without_proving_a_relation(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    net.register_claim('Independent question')
    net.ensure_studies(save=False)
    net.save()
    before = (tmp_path / 'crpn.json').read_bytes()
    ids = sorted(study['study_id'] for study in net.active_studies())
    exposure, _ = focus(net.active_studies(),
                        {'channel_cursor': 3, 'explore_cursor': 1, 'explore_snapshot': ids})
    cut, options, _ = derive(net, exposure)
    assert exposure['channel'] == 'EXPLORE' and exposure['explore_mode'] == 'REGION_MEET'
    assert exposure['focus_study_id'] != exposure['external_study_id']
    assert cut['external']['study_id'] == exposure['external_study_id']
    assert cut['external']['navigation_only'] is True
    assert any(row['notes'] == 'cross-region navigation' and not row['fact_ids'] for row in options)
    assert not net.data['supports']
    assert all(net.truth(study['claim_id']) == 'OPEN' for study in net.active_studies())
    assert (tmp_path / 'crpn.json').read_bytes() == before


def test_relevant_graph_change_during_local_selector_rebuilds_work_with_new_round_key(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    support(net, 'Target', ['Shared', 'Other'])
    source = net.register_claim('Target related auxiliary')
    fact(net, source['claim_id'])
    root = 'study-' + net.target_id
    for sid, study in net.data['studies'].items():
        if sid != root:
            study['last_served_visit'] = 0
    start_after_initial_direct(net)
    selections = []
    def handler(role, packet):
        if role == 'selector':
            assert len(packet['studies']) == 1 and len(packet['options']) <= 4
            selections.append(packet)
            if len(selections) == 1:
                fresh = Network(tmp_path)
                fact(fresh, fresh.register_claim('Shared')['claim_id'])
            return action(packet['studies'][0])
        assert role == 'worker'
        return output()
    actors = Actors(handler)
    research = Research(tmp_path, runtime(tmp_path, actors))
    assert research.step()['status'] == 'STALE_WORK'
    first = Network(tmp_path)
    assert first.data['control']['visit'] == 1 and first.data['control']['pending'] is None
    assert first.data['control']['generation'] == 1
    assert research.step()['status'] == 'COMPLETED'
    assert actors.count('selector') == 2 and actors.count('worker') == 1
    assert Network(tmp_path).data['control']['visit'] == 2
