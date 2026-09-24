"""Rebuildable work and temporary attention cuts from the CRPN graph.

This is a projection, not a queue of mathematical facts. Graph evidence and
the Study's own unfinished LocalMemory remain the sources of every item.
"""
from hashlib import sha256
import json
import re

from danus.core import LocalMemory
from substrate.store import lane
from .materials import checked_size
from .model import make_claim


MAX_ROUTES = 4
MAX_CHANGES = 4


def awakened(network, studies):
    """Rebuild affected Study IDs from exact graph neighbors, not search hints."""
    by_claim = {}
    for row in network.data['supports'].values():
        for cid in {row['conclusion_claim_id'], *row['requirement_claim_ids']}:
            by_claim.setdefault(cid, []).append(row)
    result = set()
    for study in studies:
        cid = study.get('claim_id')
        if not cid:
            continue
        related = by_claim.get(cid, [])
        prior = study.get('observed_versions')
        if prior is not None:
            if prior != _versions(network, cid, related):
                result.add(study['study_id'])
        elif any(row['conclusion_claim_id'] == cid and
                 row.get('certificates', {}).get(row['bridge_fact_id'], {}).get('status') == 'accepted' and
                 all(any(p['status'] == 'accepted' for p in network.data['claims'][need].get('proofs', {}).values())
                     for need in row['requirement_claim_ids']) and
                 network.support_ready(row['support_id']) for row in related):
            result.add(study['study_id'])
    return result


def _study_claim(network, study):
    return (network.claim(study['claim_id']) if study.get('claim_id') else
            make_claim(network.problem_id, study['scope'], study['focus']))


def _versions(network, claim_id, related):
    """Version only the directly connected graph interfaces and proof records."""
    versions = {}
    for cid in {claim_id, *(r['conclusion_claim_id'] for r in related),
                  *(cid for r in related for cid in r['requirement_claim_ids'])}:
        if cid not in network.data['claims']:
            continue  # Independent Study focus is not an invented proposition.
        row = network.data['claims'][cid]
        versions['claim:' + cid] = sha256(json.dumps(
            [(slot, fid, proof['status'], len(proof['history']))
             for slot in ('proofs', 'refutations')
             for fid, proof in sorted(row.get(slot, {}).items())],
            separators=(',', ':')).encode()).hexdigest()[:16]
    for row in related:
        sid = row['support_id']
        versions['support:' + sid] = sha256(json.dumps(
            [(fid, proof['status'], len(proof['history']))
             for fid, proof in sorted(row.get('certificates', {}).items())] +
            [row['conclusion_claim_id'], *row['requirement_claim_ids']],
            separators=(',', ':')).encode()).hexdigest()[:16]
    return versions


def _unfinished(network, study):
    try:
        notes = LocalMemory(lane(network.root, study['study_id'])).read('notes')
    except (OSError, ValueError, TypeError, KeyError):
        return None
    for item in reversed(notes):
        row = item.get('record', {})
        if isinstance(row, dict):
            work = row.get('next_work')
            if isinstance(work, str) and work.strip():
                source = row.get('source_key') or sha256(json.dumps(item, ensure_ascii=False,
                    sort_keys=True).encode()).hexdigest()
                continuation = row.get('continuation', '')
                if not isinstance(continuation, str):
                    continuation = ''
                if len(work) <= 8000:
                    return {'task': work, 'source_key': source,
                            'continuation_excerpt': continuation[:4000],
                            'continuation_page_required': len(continuation) > 4000}
                return {'task': 'Continue the saved unfinished derivation; read its exact local record first.',
                        'source_key': source, 'page_required': True,
                        'continuation_excerpt': continuation[:4000],
                        'continuation_page_required': len(continuation) > 4000}
    return None


def _recent_results(network, study, related):
    """Small receipt view; neither notes nor receipts discharge a Claim."""
    try:
        events = LocalMemory(lane(network.root, study['study_id'])).read('events')
    except (OSError, ValueError, TypeError, KeyError):
        return []
    relevant = {study.get('claim_id')}
    relevant_supports = {row['support_id'] for row in related}
    for row in related:
        relevant.update((row['conclusion_claim_id'], *row['requirement_claim_ids']))
    records = network._records()
    results = []
    for item in reversed(events):
        record = item.get('record', {})
        if not isinstance(record, dict):
            continue
        for submission in reversed(record.get('tool_submissions', [])):
            fid = submission.get('fact_id')
            if not submission.get('accepted') or not fid:
                continue
            if fid not in records:
                continue
            table, owner, _slot, fact = records[fid]
            active = fact['status'] == 'accepted' and network._active(fid)
            results.append({'fact_id': fid, 'status': 'accepted' if active else 'revoked',
                            'statement_excerpt': fact['statement'][:500],
                            'statement_page_required': len(fact['statement']) > 500,
                            'graph_interface': (owner in relevant if table == 'claims' else
                                                owner in relevant_supports),
                            'source_task': record.get('task', '')[:500]})
            if len(results) == 3:
                return results
    return results


def _local_state(network, study, changed):
    """Bounded, rebuildable research handover; never an input to graph truth."""
    try:
        memory = LocalMemory(lane(network.root, study['study_id']))
        notes, events = memory.read('notes'), memory.read('events')
    except (OSError, ValueError, TypeError, KeyError):
        return {'authority': 'UNVERIFIED_RESEARCH_STATE', 'current_obstacle': None,
                'completed_local_actions': [], 'mentioned_evidence_ids': [],
                'new_evidence_since_obstacle': []}
    actions = []
    for item in reversed(events):
        if not isinstance(item, dict):
            continue
        row = item.get('record', {})
        if (not isinstance(row, dict) or row.get('status') != 'COMPLETED'
                or not isinstance(row.get('task'), str)):
            continue
        submissions = row.get('tool_submissions', [])
        if not isinstance(submissions, list):
            submissions = []
        actions.append({'task': row['task'][:1000], 'status': row.get('status'),
                        'channel': row.get('channel'), 'source_key': row.get('source_key'),
                        'accepted_fact_ids': [s['fact_id'] for s in submissions
                                              if isinstance(s, dict) and s.get('accepted') and s.get('fact_id')][:3]})
        if len(actions) == 3:
            break
    obstacle = None
    obstacle_at = -1
    mentioned_ids = []
    for i in range(len(notes) - 1, -1, -1):
        if not isinstance(notes[i], dict):
            continue
        row = notes[i].get('record', {})
        if not isinstance(row, dict) or not str(row.get('source_key', '')).endswith(':worker-return'):
            continue
        report = row.get('continuation')
        if row.get('source_status') == 'COMPLETED' and isinstance(report, str) and report.strip():
            obstacle_at = i
            obstacle = {'authority': 'UNVERIFIED_RESEARCH_STATE',
                        'worker_report': report[:4000], 'source_key': row['source_key'],
                        'page_required': len(report) > 4000,
                        'interpretation': 'Worker-reported completed work and remaining gap; verify before use.'}
            # Exact evidence IDs in the handover are navigation history only.
            # They are never authorized as premises by this view.
            mentioned_ids = list(dict.fromkeys(re.findall(r'\b[0-9a-f]{16}\b', report)))[:8]
        break
    updates = [{'kind': 'EXACT_GRAPH_INTERFACE_CHANGE', 'key': key,
                'possible_effect': 'Recheck the reported gap; no implication is inferred.'}
               for key in changed[:MAX_CHANGES]]
    if obstacle and len(updates) < MAX_CHANGES:
        records = network._records()
        for fid in mentioned_ids:
            if fid in records and not network._active(fid):
                updates.append({'kind': 'MENTIONED_EVIDENCE_INVALIDATED', 'fact_id': fid,
                                'possible_effect': 'Earlier research cited this evidence; recheck its use.'})
            if len(updates) >= MAX_CHANGES:
                break
    if obstacle_at >= 0:
        for item in notes[obstacle_at + 1:]:
            if not isinstance(item, dict):
                continue
            row = item.get('record', {})
            if not isinstance(row, dict):
                continue
            if isinstance(row.get('content'), str):
                updates.append({'kind': 'NEW_LOCAL_RESEARCH', 'source_key': row.get('source_key'),
                                'excerpt': row['content'][:700], 'authority': 'UNVERIFIED_RESEARCH'})
            elif row.get('bridge_status'):
                updates.append({'kind': 'BRIDGE_RESULT', 'source_key': row.get('source_key'),
                                'status': row['bridge_status'], 'fact_id': row.get('fact_id'),
                                'authority': 'RECHECK_GRAPH_BEFORE_USE'})
            if len(updates) >= MAX_CHANGES:
                break
        source_prefix = obstacle['source_key'].removesuffix(':worker-return')
        obstacle_time = notes[obstacle_at].get('timestamp_utc', '')
        for item in events:
            if not isinstance(item, dict) or item.get('timestamp_utc', '') <= obstacle_time:
                continue
            row = item.get('record', {})
            if not isinstance(row, dict) or str(row.get('source_key', '')).startswith(source_prefix):
                continue
            submissions = row.get('tool_submissions', [])
            for submission in submissions if isinstance(submissions, list) else []:
                if isinstance(submission, dict) and submission.get('verdict'):
                    updates.append({'kind': 'NEW_VERIFIER_FEEDBACK',
                                    'verdict': submission['verdict'], 'fact_id': submission.get('fact_id'),
                                    'feedback_excerpt': str(submission.get('feedback', ''))[:700]})
                if len(updates) >= MAX_CHANGES:
                    break
            if len(updates) >= MAX_CHANGES:
                break
    return {'authority': 'UNVERIFIED_RESEARCH_STATE', 'current_obstacle': obstacle,
            'completed_local_actions': actions, 'mentioned_evidence_ids': mentioned_ids,
            'new_evidence_since_obstacle': updates[:MAX_CHANGES]}


def _route(network, row):
    sid = row['support_id']
    if sum(len(network.claim(cid)['statement']) for cid in row['requirement_claim_ids']) > 12000:
        return {'support_id': sid, 'requirements_count': len(row['requirement_claim_ids']),
                'interface_page_required': True, 'compose_ready': False,
                'notice': 'This route is too wide for one attention window. No condition is omitted or assumed.'}
    route = {'support_id': sid, 'conclusion': network.claim(row['conclusion_claim_id']),
             'requirements': [{**network.claim(cid), 'truth': network.truth(cid)}
                              for cid in row['requirement_claim_ids']],
             'certificate_fact_id': row['bridge_fact_id'] if network._active(row['bridge_fact_id']) else None,
             'compose_ready': network.support_ready(sid)}
    try:
        checked_size(route, 16000)
    except ValueError:
        return {'support_id': sid, 'requirements_count': len(row['requirement_claim_ids']),
                'interface_page_required': True, 'compose_ready': False,
                'notice': 'This route is too wide for one attention window. No condition is omitted or assumed.'}
    return route


def derive(network, exposure):
    """Return one bounded cut, local actions and the observed version snapshot."""
    study = network.data['studies'][exposure['focus_study_id']]
    claim = _study_claim(network, study)
    cid = claim['claim_id']
    related = [row for _, row in sorted(network.data['supports'].items())
               if cid == row['conclusion_claim_id'] or cid in row['requirement_claim_ids']]
    versions = _versions(network, cid, related)
    prior = study.get('observed_versions')
    changed = [] if prior is None else [key for key in sorted(set(prior) | set(versions))
                                      if prior.get(key) != versions.get(key)]
    cursor = study.get('work_cursor', 0)
    window = related[cursor % len(related):] + related[:cursor % len(related)] if related else []
    # Cheap graph-owned existence check first; the actual readiness decision
    # still comes from Network and its full valid-closure rules.
    possible = [r for r in window if r['conclusion_claim_id'] == cid
                and r.get('certificates', {}).get(r['bridge_fact_id'], {}).get('status') == 'accepted'
                and all(any(p['status'] == 'accepted' for p in
                            network.data['claims'][need].get('proofs', {}).values())
                        for need in r['requirement_claim_ids'])]
    ready_row = next((r for r in possible if network.support_ready(r['support_id'])), None)
    if ready_row is not None:
        window = [ready_row] + [r for r in window if r['support_id'] != ready_row['support_id']]
    selected = [_route(network, row) for row in window[:MAX_ROUTES]]
    unfinished = _unfinished(network, study)
    recent_results = _recent_results(network, study, related)
    local_state = _local_state(network, study, changed)
    open_requirements = []
    for route in selected:
        if route.get('conclusion', {}).get('claim_id') != cid:
            continue  # A route consuming this Claim is output use, not its missing input.
        for requirement in route.get('requirements', []):
            if requirement['truth'] == 'OPEN' and len(open_requirements) < MAX_ROUTES:
                open_requirements.append({'support_id': route['support_id'],
                                          'claim_id': requirement['claim_id'],
                                          'statement': requirement['statement'][:2000],
                                          'page_required': len(requirement['statement']) > 2000})
    consumers = [r['support_id'] for r in related if cid in r['requirement_claim_ids']]
    external = network.data['studies'].get(exposure.get('external_study_id'))
    cut = {'focus': {'study_id': study['study_id'], 'claim': claim, 'revision': study.get('revision', 0)},
           'input_interface': {'scope': claim['context'], 'accepted_premises': 'Only delivered CRPN evidence IDs are usable.'},
           'unfinished': unfinished,
           'local_state': local_state,
           'task_frame': {'unresolved_focus_claim_id': cid,
                          'unresolved_focus_source': 'cut.focus.claim',
                          'focus_truth': network.truth(cid) if study.get('claim_id') else 'NO_CLAIM',
                          'open_requirements': open_requirements,
                          'recent_accepted': recent_results,
                          'saved_next_work_role': 'Unverified route proposal, not the task definition or proof.',
                          'remaining_gap': 'Unknown unless the exact Claim or Support requirements are discharged.'},
           'routes': selected, 'related_route_count': len(related),
           'changes': changed[:MAX_CHANGES], 'other_change_count': max(0, len(changed) - MAX_CHANGES),
           'output_use': {'known_support_ids': consumers[:MAX_ROUTES],
                          'other_known_count': max(0, len(consumers) - MAX_ROUTES),
                          'unknown': not bool(consumers)},
           'external': ({'study_id': external['study_id'], 'scope': external['scope'],
                         'focus': external['focus'][:4000], 'navigation_only': True,
                         'focus_page_required': len(external['focus']) > 4000} if external else None),
           'explore_mode': exposure.get('explore_mode')}
    checked_size(cut, 96000)
    ready = [r for r in selected if r['compose_ready']]
    if ready:
        options = [{'study_id': study['study_id'], 'operation': 'COMPOSE',
                    'support_id': r['support_id'], 'task': 'Combine this exact ready Support with every required accepted condition.',
                    'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''}
                   for r in ready[:1]]
    else:
        obstacle = local_state['current_obstacle']
        task = ('Investigate a concrete unresolved part of the reported obstacle and obtain new '
                'mathematical information about it. Keep the exact Claim as the long-term target; '
                'do not merely repeat a completed diagnosis without new evidence or a specific reason to doubt it.'
                if obstacle else
                'Address the exact unresolved local Claim or one of its open Support requirements; '
                'use the saved derivation only where it serves this focus.' if study.get('claim_id') else
                'Investigate the current independent research focus and its specific remaining question.')
        options = [{'study_id': study['study_id'], 'operation': 'RESEARCH', 'task': task,
                    'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''}]
        if obstacle and local_state['new_evidence_since_obstacle']:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Check whether the newly changed exact interface or research feedback changes '
                                    'the reported obstacle; establish any connection rather than assuming it.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None,
                            'notes': 'new evidence is a lead, not a proof of the connection'})
        if unfinished:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': ('Continue the saved derivation only if it yields new information about '
                                     'the reported obstacle; otherwise change the local question with a reason.'
                                     if obstacle else 'Test whether the saved next step serves the exact local focus; '
                                     'change route if new evidence leaves a different gap.'),
                            'fact_ids': [], 'research_queries': [], 'bridge': None,
                            'notes': 'saved next_work is unverified research, not a renewed task'})
            if not obstacle:
                options.append({'study_id': study['study_id'], 'operation': 'CLOSE',
                                'task': 'Check whether the saved derivation now yields a complete local proof; otherwise preserve its exact gap.',
                                'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''})
        if obstacle and exposure.get('channel') == 'REVISIT':
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Recheck the earlier diagnosis only if you identify a specific error, '
                                    'new evidence, or an unresolved step; state the reason and seek new information.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': 'reasoned revisit'})
        if exposure.get('channel') == 'EXPLORE':
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Explore an unknown local direction, construction or representation; '
                                    'its relation to the current obstacle or Claim may remain unknown.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': 'open exploration'})
        if external:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Check whether the other region offers a precise interface for this local focus; do not assume a connection.',
                            'fact_ids': [], 'research_queries': [study['focus'], external['focus'][:1000]],
                            'bridge': None, 'notes': 'cross-region navigation'})
        # Retrieval suggests inspectable opportunities only; it creates no implication.
        for hit in network.search(study['focus'], 4):
            fid = hit['fact_id']
            if (obstacle and fid in local_state['mentioned_evidence_ids']
                    and not local_state['new_evidence_since_obstacle']):
                # The default retrieval window should not hand the same already
                # examined interface back as a fresh action. Explicit, reasoned
                # recheck remains possible through REVISIT and Worker tools.
                continue
            if network.inspect_fact(fid)['scope'] == claim['context']:
                options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                                'task': ('Use this accepted interface to obtain new information about the reported '
                                         'obstacle; do not simply repeat a completed directional check.' if obstacle else
                                         'Examine whether this accepted interface addresses the exact local focus or an open requirement.'),
                                'fact_ids': [fid], 'research_queries': [], 'bridge': None,
                                'notes': 'retrieval is a lead, not a mathematical connection'})
            else:
                options.append({'study_id': study['study_id'], 'operation': 'INSPECT',
                                'task': 'Inspect a foreign-scope interface before considering an explicit bridge.',
                                'fact_ids': [fid], 'research_queries': [], 'bridge': None, 'notes': ''})
        if exposure.get('explore_mode') and not any(row['operation'] == 'INSPECT' for row in options):
            # Finite meeting opportunity even when lexical search finds no link.
            foreign = [fid for fid in network.proof_ids()
                       if network.inspect_fact(fid)['scope'] != claim['context']]
            if foreign:
                fid = foreign[cursor % len(foreign)]
                options.append({'study_id': study['study_id'], 'operation': 'INSPECT',
                                'task': 'Check one foreign-scope interface as a possible bridge lead; no relation is assumed.',
                                'fact_ids': [fid], 'research_queries': [], 'bridge': None, 'notes': ''})
    cut['candidate_count'] = len(options)
    if len(options) > MAX_ROUTES:
        # Keep the exact obligation visible while rotating optional leads.
        remaining = options[1:]
        start = cursor % len(remaining)
        options = options[:1] + (remaining[start:] + remaining[:start])[:MAX_ROUTES - 1]
    return cut, options, versions


def after_inspection(options, inspections, study_id):
    """Offer only inspected foreign sources for an explicit local bridge choice."""
    base = [row for row in options if row['operation'] != 'INSPECT'][:MAX_ROUTES - 1]
    if inspections:
        base.append({'study_id': study_id, 'operation': 'REQUEST_BRIDGE',
                     'task': 'If the inspected source is applicable, propose an exact auxiliary interface and correspondence.',
                     'fact_ids': [], 'research_queries': [], 'bridge': None,
                     'notes': 'An inspection is not an accepted premise.'})
    return base
