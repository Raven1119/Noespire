"""Rebuildable work and temporary attention cuts from the CRPN graph.

This is a projection, not a queue of mathematical facts. Graph evidence and
the Study's own unfinished LocalMemory remain the sources of every item.
"""
from hashlib import sha256
import json

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
        task = ('Address the exact unresolved local Claim or one of its open Support requirements; '
                'use the saved derivation only where it serves this focus.' if study.get('claim_id') else
                'Investigate the current independent research focus and its specific remaining question.')
        options = [{'study_id': study['study_id'], 'operation': 'RESEARCH', 'task': task,
                    'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''}]
        if unfinished:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Test whether the saved next step serves the exact local focus; '
                                    'change route if new evidence leaves a different gap.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None,
                            'notes': 'saved next_work is unverified research, not a renewed task'})
            options.append({'study_id': study['study_id'], 'operation': 'CLOSE',
                            'task': 'Check whether the saved derivation now yields a complete local proof; otherwise preserve its exact gap.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''})
        if external:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Check whether the other region offers a precise interface for this local focus; do not assume a connection.',
                            'fact_ids': [], 'research_queries': [study['focus'], external['focus'][:1000]],
                            'bridge': None, 'notes': 'cross-region navigation'})
        # Retrieval suggests inspectable opportunities only; it creates no implication.
        for hit in network.search(study['focus'], 4):
            fid = hit['fact_id']
            if network.inspect_fact(fid)['scope'] == claim['context']:
                options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                                'task': 'Examine whether this accepted interface addresses the exact local focus or an open requirement.',
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
