"""Deterministic control evidence; fixtures do not establish mathematics."""
import json

from crpn.engine import Research
from crpn.materials import selector_packet, worker_packet
from crpn.model import Network, make_claim
from crpn.scheduler import focus
from crpn.work import awakened, derive
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
