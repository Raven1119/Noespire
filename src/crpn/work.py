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


def interface_snapshot(network, study):
    """Exact local graph state at a Worker observation; advisory metadata only."""
    cid = study.get('claim_id')
    if not cid:
        return {}, {}
    related = [row for row in network.data['supports'].values()
               if cid == row['conclusion_claim_id'] or cid in row['requirement_claim_ids']]
    versions = _versions(network, cid, related)
    evidence = {}
    for key in versions:
        kind, owner = key.split(':', 1)
        row = (network.data['claims'] if kind == 'claim' else network.data['supports'])[owner]
        slots = ('proofs', 'refutations') if kind == 'claim' else ('certificates',)
        evidence[key] = {fid: ('accepted' if proof['status'] == 'accepted' and network._active(fid)
                               else 'revoked')
                         for slot in slots for fid, proof in row.get(slot, {}).items()}
    return versions, evidence


def reference_snapshot(network, evidence_ids):
    """Exact proof references to inspected evidence, found by a host-side scan."""
    referenced = set(evidence_ids)
    if not referenced:
        return {}
    return {fid: {'status': 'accepted' if row['status'] == 'accepted' and network._active(fid)
                            else 'revoked',
                  'predecessors': sorted(referenced.intersection(row.get('predecessors', [])))}
            for fid, (_table, _owner, _slot, row) in network._records().items()
            if referenced.intersection(row.get('predecessors', []))}


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
    """Rebuild bounded observations, derivations and deltas from original records."""
    state = {'authority': 'UNVERIFIED_RESEARCH_STATE', 'completed_actions': [],
             'unfinished_derivation': None, 'open_questions': [],
             'previous_suggestions': [], 'recent_evidence_changes': [],
             'latest_recheck_reason': None}
    try:
        memory = LocalMemory(lane(network.root, study['study_id']))
        notes, events = memory.read('notes'), memory.read('events')
    except (OSError, ValueError, TypeError, KeyError):
        return state
    returns = {}
    for item in notes:
        row = item.get('record', {}) if isinstance(item, dict) else {}
        if isinstance(row, dict) and str(row.get('source_key', '')).endswith(':worker-return'):
            returns[row['source_key'].removesuffix(':worker-return')] = row
    for item in reversed(events):
        row = item.get('record', {}) if isinstance(item, dict) else {}
        if not isinstance(row, dict) or not isinstance(row.get('task'), str):
            continue
        source = str(row.get('source_key', ''))
        if not source.endswith(':service'):
            continue
        handover = returns.get(source.removesuffix(':service'), {})
        if handover.get('source_status') != 'COMPLETED':
            continue
        report = handover.get('research_state')
        report = report if isinstance(report, dict) else {}
        observation = report.get('completed_observation') or handover.get('continuation', '')
        if not isinstance(observation, str):
            observation = ''
        examined = handover.get('examined_evidence_ids')
        if not isinstance(examined, list):
            examined = []
        initial = handover.get('initially_delivered_evidence_ids')
        if not isinstance(initial, list):
            initial = []
        explicit = report.get('completed_observation')
        if report and not (isinstance(explicit, str) and explicit.strip()):
            continue  # A service can end with only an unfinished derivation.
        action = {'task': row['task'][:1000], 'observation': observation[:3000],
                  'observation_page_required': len(observation) > 3000,
                  'classification': 'EXPLICIT_OBSERVATION' if report.get('completed_observation') else
                                    'HISTORICAL_UNCLASSIFIED',
                  'source_study_id': study['study_id'], 'source_service': source,
                  'source_key': handover.get('source_key', 'UNKNOWN'),
                  'examined_evidence_ids': [v for v in examined if isinstance(v, str)][:8],
                  'initially_delivered_evidence_ids': [v for v in initial if isinstance(v, str)][:8],
                  'evidence_context_ids': list(dict.fromkeys(
                      [v for v in examined + initial if isinstance(v, str)]))[:8],
                  'recheck_reason': (report.get('recheck_reason') or '')[:1000]
                                    if isinstance(report.get('recheck_reason'), str) else '',
                  'observation_graph_version': handover.get('observation_graph_sha256', 'UNKNOWN'),
                  'channel': row.get('channel', 'UNKNOWN')}
        submissions = row.get('tool_submissions', [])
        if isinstance(submissions, list):
            action['verifier_feedback'] = [
                {'verdict': s.get('verdict'), 'fact_id': s.get('fact_id'),
                 'feedback': str(s.get('feedback', ''))[:500]}
                for s in submissions if isinstance(s, dict) and s.get('verdict')][:3]
            action['accepted_fact_ids'] = [s['fact_id'] for s in submissions
                                           if isinstance(s, dict) and s.get('accepted') and s.get('fact_id')][:3]
        state['completed_actions'].append(action)
        if len(state['completed_actions']) >= 3:
            break
    latest_structured = False
    latest_saved = False
    for item in reversed(notes):
        row = item.get('record', {}) if isinstance(item, dict) else {}
        if not isinstance(row, dict):
            continue
        source = row.get('source_key', 'UNKNOWN')
        content = row.get('content')
        if (not latest_structured and not latest_saved and isinstance(content, str)
                and content.startswith('UNFINISHED DERIVATION:\n')):
            work = content.removeprefix('UNFINISHED DERIVATION:\n').strip()
            if work:
                state['unfinished_derivation'] = {'text': work[:4000], 'task': work[:4000],
                    'source_key': source, 'source_study_id': study['study_id'],
                    'source_service': row.get('source_service', 'UNKNOWN'),
                    'page_required': len(work) > 4000,
                    'origin': 'LOCAL_MEMORY_PARTIAL'}
                latest_saved = True
        report = row.get('research_state')
        report = report if isinstance(report, dict) else {}
        if row.get('source_status') == 'COMPLETED':
            first_structured = bool(report) and not latest_structured
            reason = report.get('recheck_reason')
            if first_structured and isinstance(reason, str) and reason.strip():
                state['latest_recheck_reason'] = {'text': reason[:1000],
                    'source_key': source, 'authority': 'UNVERIFIED_RESEARCH_STATE'}
            work = report.get('unfinished_derivation')
            if not latest_structured and not latest_saved and isinstance(work, str) and work.strip():
                state['unfinished_derivation'] = {'text': work[:4000], 'task': work[:4000],
                    'source_key': source, 'source_study_id': study['study_id'],
                    'source_service': str(source).removesuffix(':worker-return'),
                    'page_required': len(work) > 4000}
            question = report.get('open_question')
            if (first_structured and not latest_saved and isinstance(question, str)
                    and question.strip()):
                state['open_questions'].append({'text': question[:1000], 'source_key': source,
                                                'authority': 'UNVERIFIED_RESEARCH_STATE'})
            if report:
                latest_structured = True
        proposal = row.get('next_work') or row.get('strategy_notes')
        if isinstance(proposal, str) and proposal.strip() and len(state['previous_suggestions']) < 3:
            state['previous_suggestions'].append({'text': proposal[:1000], 'source_key': source,
                                                  'authority': 'UNVERIFIED_SUGGESTION'})
        if len(state['previous_suggestions']) >= 3 and len(state['open_questions']) >= 3:
            break
    now_versions, now_evidence = interface_snapshot(network, study)
    for latest in state['completed_actions'][:1]:
        handover = returns.get(latest['source_service'].removesuffix(':service'), {})
        prior = handover.get('observation_graph_versions')
        before = handover.get('observation_graph_evidence')
        keys = ([key for key in sorted(set(prior) | set(now_versions))
                 if prior.get(key) != now_versions.get(key)] if isinstance(prior, dict) else changed)
        for key in keys[:MAX_CHANGES - len(state['recent_evidence_changes'])]:
            delta = {'kind': 'EXACT_GRAPH_INTERFACE_CHANGE', 'key': key,
                     'old_observation': latest['observation'][:700],
                     'source_service': latest['source_service'],
                     'possible_effect': 'May change the earlier observation; inspect exact interfaces.'}
            if isinstance(before, dict):
                old = before.get(key, {})
                current = now_evidence.get(key, {})
                if isinstance(old, dict):
                    delta['evidence'] = [{'fact_id': fid, 'before': old.get(fid, 'ABSENT'),
                                          'now': current.get(fid, 'ABSENT')}
                                         for fid in sorted(set(old) | set(current))
                                         if old.get(fid) != current.get(fid)][:4]
            state['recent_evidence_changes'].append(delta)
        previous_refs = handover.get('observation_referenced_proofs')
        if isinstance(previous_refs, dict) and len(state['recent_evidence_changes']) < MAX_CHANGES:
            observed_ids = handover.get('examined_evidence_ids', [])
            delivered_ids = handover.get('initially_delivered_evidence_ids', [])
            observed_ids = observed_ids if isinstance(observed_ids, list) else []
            delivered_ids = delivered_ids if isinstance(delivered_ids, list) else []
            current_refs = reference_snapshot(network, [v for v in observed_ids + delivered_ids
                                                        if isinstance(v, str)])
            for fid in sorted(set(previous_refs) | set(current_refs)):
                if previous_refs.get(fid) == current_refs.get(fid):
                    continue
                state['recent_evidence_changes'].append({'kind': 'ACTUAL_PREDECESSOR_CHANGE',
                    'fact_id': fid, 'before': previous_refs.get(fid, 'ABSENT'),
                    'now': current_refs.get(fid, 'ABSENT'),
                    'old_observation': latest['observation'][:700],
                    'source_service': latest['source_service'],
                    'possible_effect': 'A proof explicitly refers to examined evidence; inspect its full interface.'})
                if len(state['recent_evidence_changes']) >= MAX_CHANGES:
                    break
        observed_ids = handover.get('examined_evidence_ids', [])
        delivered_ids = handover.get('initially_delivered_evidence_ids', [])
        observed_ids = observed_ids if isinstance(observed_ids, list) else []
        delivered_ids = delivered_ids if isinstance(delivered_ids, list) else []
        for fid in dict.fromkeys(v for v in observed_ids + delivered_ids if isinstance(v, str)):
            if len(state['recent_evidence_changes']) >= MAX_CHANGES:
                break
            records = network._records()
            if fid in records and not network._active(fid):
                state['recent_evidence_changes'].append({'kind': 'EXAMINED_EVIDENCE_INVALIDATED',
                    'fact_id': fid, 'old_observation': latest['observation'][:700],
                    'source_service': latest['source_service'],
                    'possible_effect': 'Recheck use of the revoked evidence.'})
    if state['completed_actions'] and len(state['recent_evidence_changes']) < MAX_CHANGES:
        anchor = state['completed_actions'][0]
        after = False
        for item in notes:
            row = item.get('record', {}) if isinstance(item, dict) else {}
            if not isinstance(row, dict):
                continue
            if row.get('source_key') == anchor['source_key']:
                after = True
                continue
            if not after:
                continue
            if row.get('bridge_status'):
                state['recent_evidence_changes'].append({'kind': 'BRIDGE_RESULT',
                    'source_key': row.get('source_key'), 'status': row['bridge_status'],
                    'fact_id': row.get('fact_id'), 'old_observation': anchor['observation'][:700],
                    'possible_effect': 'Inspect the exact bridge and scope before changing the question.'})
            elif isinstance(row.get('content'), str):
                state['recent_evidence_changes'].append({'kind': 'NEW_LOCAL_RESEARCH',
                    'source_key': row.get('source_key'), 'excerpt': row['content'][:700],
                    'old_observation': anchor['observation'][:700],
                    'authority': 'UNVERIFIED_RESEARCH_STATE'})
            if len(state['recent_evidence_changes']) >= MAX_CHANGES:
                break
        after = False
        for item in events:
            row = item.get('record', {}) if isinstance(item, dict) else {}
            if not isinstance(row, dict):
                continue
            if row.get('source_key') == anchor['source_service']:
                after = True
                continue
            if not after:
                continue
            submissions = row.get('tool_submissions', [])
            for submission in submissions if isinstance(submissions, list) else []:
                if isinstance(submission, dict) and submission.get('verdict'):
                    state['recent_evidence_changes'].append({'kind': 'NEW_VERIFIER_FEEDBACK',
                        'source_service': row.get('source_key'), 'verdict': submission['verdict'],
                        'fact_id': submission.get('fact_id'),
                        'feedback_excerpt': str(submission.get('feedback', ''))[:700],
                        'old_observation': anchor['observation'][:700],
                        'possible_effect': 'Feedback is not proof; update the local research question.'})
                if len(state['recent_evidence_changes']) >= MAX_CHANGES:
                    break
            if len(state['recent_evidence_changes']) >= MAX_CHANGES:
                break
    return state


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
    recent_results = _recent_results(network, study, related)
    local_state = _local_state(network, study, changed)
    unfinished = local_state['unfinished_derivation']
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
    local_state['claim'] = {'claim_id': cid, 'statement': claim['statement'][:3000],
                            'page_required': len(claim['statement']) > 3000}
    local_state['open_requirements'] = open_requirements
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
                          'saved_next_work_role': 'Unverified suggestion, never an unfinished derivation by itself.',
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
        completed = local_state['completed_actions']
        updates = local_state['recent_evidence_changes']
        task = ('Continue the specific unfinished derivation from its saved position; recheck its '
                'unproved steps and pursue its open question without treating drafts as Facts.' if unfinished else
                'Use the new exact evidence to reconsider the earlier observation and seek a '
                'distinguishable result. The old diagnosis is revisable.' if completed and updates else
                'Investigate a concrete open question or requirement left by the completed research; '
                'seek new information rather than repeat the same diagnosis. If no concrete move '
                'is justified, report NO CLEAR LOCAL MOVE.' if completed else
                'Investigate the exact open Claim or requirement through a concrete local question; '
                'NO CLEAR LOCAL MOVE is allowed.' if study.get('claim_id') else
                'Investigate the independent local focus through a concrete question; '
                'NO CLEAR LOCAL MOVE is allowed.')
        options = [{'study_id': study['study_id'], 'operation': 'RESEARCH', 'task': task,
                    'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''}]
        if completed and updates:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Check whether a changed exact interface corrects the earlier observation; '
                                    'establish the connection rather than assuming it.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None,
                            'notes': 'new evidence is a lead, not a proof of the connection'})
        if unfinished and completed:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Reassess the unfinished derivation against the completed observation; '
                                    'change method or question with a concrete reason if needed.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None,
                            'notes': 'unfinished text is unverified research'})
        if completed and exposure.get('channel') == 'REVISIT':
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Recheck the earlier observation only if you identify a specific error, '
                                    'new evidence, or an unresolved step; state the reason and seek new information.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': 'reasoned revisit'})
        if exposure.get('channel') == 'EXPLORE':
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Explore an unknown local direction, construction or representation; '
                                    'its relation to completed research or the Claim may remain unknown.',
                            'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': 'open exploration'})
        if external:
            options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                            'task': 'Check whether the other region offers a precise interface for this local focus; do not assume a connection.',
                            'fact_ids': [], 'research_queries': [study['focus'], external['focus'][:1000]],
                            'bridge': None, 'notes': 'cross-region navigation'})
        # Retrieval suggests inspectable opportunities only; it creates no implication.
        for hit in network.search(study['focus'], 4):
            fid = hit['fact_id']
            if (completed and fid in completed[0]['examined_evidence_ids'] and not updates):
                # The default retrieval window should not hand the same already
                # examined interface back as a fresh action. Explicit, reasoned
                # recheck remains possible through REVISIT and Worker tools.
                continue
            if network.inspect_fact(fid)['scope'] == claim['context']:
                options.append({'study_id': study['study_id'], 'operation': 'RESEARCH',
                                'task': ('Use this accepted interface to obtain new information about the open question; '
                                         'do not repeat a completed check without a reason.' if completed else
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
