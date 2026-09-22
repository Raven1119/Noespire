"""CRPN policy transitions on DANUS lanes, memory and verified submissions.

crpn.json owns mathematical state and strategy. DANUS owns model reservations,
processes, responses and memory. No reconstructed call journal.
"""
from copy import deepcopy
from uuid import uuid4
import json
from danus.core import LocalMemory, GlobalMemory
from danus.core.durable_io import locked
from .admission import Admission
from .verification import VerifierBackend
from substrate.store import append_once, lane
from . import contracts as C
from .model import Network, make_claim, normalize
from .scheduler import expose
from .materials import selector_packet, worker_packet, inspect


class BlockingError(RuntimeError):
    pass


class Research:
    def __init__(self, root, runtime):
        self.network, self.runtime = Network(root), runtime
        self.gate = Admission(VerifierBackend(runtime))

    def _call(self, role, study, key, instructions, packet, schema):
        result = self.runtime.call(role, study, key, instructions, packet, schema)
        if result['status'] == 'ERROR':
            raise BlockingError(result.get('error') or 'runtime error')
        return result

    def _submit(self, key, prepared, purpose, author, descriptor):
        return self.gate.submit(self.network, key, prepared=prepared, descriptor=descriptor,
                                author=author, purpose=purpose)

    def step(self):
        with locked(self.network.root / '.service.lock'):
            self.network = Network(self.network.root)
            n = self.network
            if 'control' not in n.data:
                n.data['control'] = {'run_id': uuid4().hex, 'visit': 0, 'pending': None}
                n.save()
            control = n.data['control']
            if n.truth(n.target_id) == 'DISCHARGED' and control['pending'] is None:
                return {'status': 'TARGET_SOLVED'}
            self._activations(control)
            self._recurrences(control)
            control = n.data['control']
            n.ensure_studies()
            if control['pending'] is None:
                studies = list(n.active_studies())
                if not studies:
                    return {'status': 'NO_ACTIVE_STUDY'}
                exposure, proposed = expose(studies, n.data.get('schedule', {}))
                control['pending'] = {'exposure': exposure, 'schedule_after': proposed,
                                      'selection_round': 0, 'inspections': [], 'action': None}
                # Direct-first is the existing initialization policy, never imposed later.
                if control['visit'] == 0 and len(studies) == 1 and studies[0].get('revision', 0) == 0:
                    control['pending']['action'] = {'study_id': studies[0]['study_id'],
                        'operation': 'RESEARCH', 'task': 'Try to prove the original Claim directly; preserve unfinished research.',
                        'fact_ids': [], 'research_queries': [], 'bridge': None, 'notes': ''}
                n.save()
            pending = control['pending']
            key = control['run_id'] + ':' + str(control['visit'])
            while pending['action'] is None:
                result = self._call('selector', 'selector', key + ':select:' + str(pending['selection_round']),
                    C.SELECTOR, selector_packet(n, pending['exposure'], pending['inspections']), C.SELECTOR_SCHEMA)
                if result['status'] != 'COMPLETED':
                    # No Worker service, therefore no fairness advancement.
                    pending['selection_round'] += 1; n.save()
                    return {'status': result['status'], 'role': 'selector'}
                action = self._action(result['output'], pending['exposure'])
                if action['operation'] == 'INSPECT':
                    pending['inspections'] = inspect(n, action['fact_ids'])
                    pending['selection_round'] += 1; n.save()
                    continue
                pending['action'] = action
                self._note(action['study_id'], key + ':selection:' + str(pending['selection_round']),
                           {'selected_task': action['task'], 'strategy_notes': action.get('notes', '')})
                n.save()
            action = pending['action']
            if action['operation'] == 'REQUEST_BRIDGE':
                outcome = self._bridge(key + ':bridge:' + str(pending['selection_round']), action, pending)
                control = n.data['control']
                pending = control['pending']
                self._note(action['study_id'], key + ':bridge:' + str(pending['selection_round']), outcome)
                pending['action'] = None
                pending['selection_round'] += 1
                pending['inspections'] = [outcome]
                n.save()
                return {'status': 'BRIDGE', **outcome}
            study = action['study_id']
            # Reconstruct a pending service from its actual frozen delivery. New
            # in-session proofs may already discharge its Claim or its Support.
            request_path = self.runtime.request_path('worker', study, key + ':worker')
            if request_path.exists():
                from .workbench import packet_for
                _, packet = packet_for(request_path)
            else:
                packet = worker_packet(n, action)
                if action['operation'] == 'COMPOSE':
                    ready = [row for row in n.ready_supports() if row['conclusion_claim_id'] == packet['claim']['claim_id']]
                    if not ready:
                        raise BlockingError('COMPOSE action lacks a ready Support')
                    materials = n.support_materials(ready[0]['support_id'])
                    packet['compose'] = {k: v for k, v in materials.items() if k != 'facts'}
                    packet['accepted_facts'] = [{'fact_id': f.fact_id, 'statement': f.statement} for f in materials['facts']]
            result = self._call('worker', study, key + ':worker', C.WORKER, packet, C.WORKER_SCHEMA)
            n.refresh()
            control = n.data['control']
            pending = control['pending']
            outcome = {'status': result['status'], 'study_id': study, 'channel': pending['exposure']['channel']}
            from .workbench import recover_submissions
            tool_submissions = recover_submissions(n, self.runtime, result['evidence']['request'])
            control = n.data['control']
            pending = control['pending']
            if tool_submissions:
                outcome['tool_submissions'] = tool_submissions
            local = LocalMemory(lane(n.root, study))
            if result['status'] == 'COMPLETED':
                output = result['output']
                append_once(local, 'notes', key + ':worker-return', {
                    'authority': 'UNVERIFIED_RESEARCH', 'continuation': output.get('continuation', ''),
                    'next_work': output.get('next_work', ''), 'source_status': result['status']})
                candidate = output.get('candidate')
                if candidate:
                    from .workbench import submit_candidate
                    try:
                        verdict = submit_candidate(n, self.runtime, result['evidence']['request'],
                                                   candidate, gate=self.gate)
                    except (ValueError, KeyError, TypeError) as error:
                        outcome.update(status='CANDIDATE_REJECTED', reason=str(error))
                    else:
                        outcome['verification'] = verdict['verdict']
                        if verdict['accepted']:
                            outcome['admission'] = verdict['admission']
                        else:
                            outcome['status'] = 'VERIFIER_REJECTED'
                self._new_study(study, key, output.get('new_study'))
            self._recurrences(control)
            control = n.data['control']
            pending = control['pending']
            append_once(local, 'events', key + ':service', outcome)
            # The entire policy update is one atomic CRPN transition. Bridge never reaches it.
            current = n.data['studies'][study]
            current['revision'] = current.get('revision', 0) + 1
            current['last_served_visit'] = control['visit']
            n.data['schedule'] = pending['schedule_after']
            control['visit'] += 1
            control['pending'] = None
            n.ensure_studies(save=False)
            n.save()
            return outcome

    def _new_study(self, study, key, proposal):
        if not proposal:
            return
        try:
            if not isinstance(proposal, dict):
                raise ValueError('independent Study proposal must be an object')
            if proposal.get('continues_study_id') == study:
                return  # Same line stays in its persistent lane.
            if proposal.get('continues_study_id'):
                raise ValueError('continuation cannot rebind another Study')
            if any(not isinstance(proposal.get(k), str) for k in ('focus', 'context')):
                raise ValueError('new Study needs a complete focus and explicit scope')
            created = self.network.register_study(proposal['focus'], proposal['context'])
            self._note(created['study_id'], key + ':origin', {'originating_study': study,
                       'research_proposal': proposal})
        except (ValueError, KeyError, TypeError) as error:
            self._note(study, key + ':proposal-rejected', {'diagnostic': str(error)})

    def _note(self, study, key, payload):
        try:
            append_once(LocalMemory(lane(self.network.root, study)), 'notes', key,
                        {'authority': 'UNVERIFIED_RESEARCH', **payload})
        except (ValueError, TypeError, OSError):
            # Confirmed raw actor output remains in DANUS; advisory view may be rebuilt.
            pass

    def _action(self, raw, exposure):
        n = self.network
        if not isinstance(raw, dict):
            raise BlockingError('no executable Selector action')
        study = raw.get('study_id')
        visible = {card['study_id'] for card in exposure['cards']}
        if study not in visible or (exposure['forced_study_id'] and study != exposure['forced_study_id']):
            raise BlockingError('Selector action violates exposed/pinned Study')
        if raw.get('operation') not in ('RESEARCH','CLOSE','COMPOSE','INSPECT','REQUEST_BRIDGE'):
            raise BlockingError('unknown executable operation')
        if not isinstance(raw.get('task'), str) or not raw['task'].strip():
            raise BlockingError('missing executable research task')
        facts = raw.get('fact_ids', [])
        if not isinstance(facts, list) or any(not isinstance(fid, str) for fid in facts):
            raise BlockingError('invalid requested Fact IDs')
        for fid in facts:
            n._accepted(fid)
        # Only execution fields survive. Explanation/old assessments may be any JSON.
        queries = raw.get('research_queries')
        if not isinstance(queries, list) or any(not isinstance(x,str) for x in queries):
            queries = []
        return {k: raw.get(k) for k in ('study_id','operation','task','bridge')} | {
            'fact_ids': facts, 'research_queries': queries,
            'notes': raw.get('notes', '') if isinstance(raw.get('notes'),str) else ''}

    def _bridge(self, key, action, pending):
        n = self.network
        request = action.get('bridge')
        try:
            if not isinstance(request, dict) or not all(isinstance(request.get(k), str) and request[k].strip()
                    for k in ('source_fact_id','target_auxiliary_statement','correspondence')):
                raise ValueError('incomplete bridge request')
            source = n.inspect_fact(request['source_fact_id'])
            if not any(row.get('fact_id') == source['fact_id'] for row in pending['inspections']):
                raise ValueError('bridge requires prior full interface inspection')
            study = n.data['studies'][action['study_id']]
            target = (n.claim(study['claim_id']) if study.get('claim_id') else
                      make_claim(n.problem_id, study['scope'], study['focus']))
            auxiliary = make_claim(n.problem_id, target['context'], request['target_auxiliary_statement'])
            if auxiliary['claim_id'] == target['claim_id']:
                raise ValueError('bridge auxiliary cannot silently discharge the research target')
        except (ValueError, TypeError, KeyError) as error:
            return {'bridge_status': 'REJECTED', 'reason': str(error)}
        # Reuse exactly this admitted auxiliary interface, with genuine source lineage.
        # No semantic matching and no scope rebinding. A revoked closure never qualifies.
        if auxiliary['claim_id'] in n.data['claims']:
            for fact in n.facts_for(auxiliary['claim_id']):
                if source['fact_id'] in {f.fact_id for f in n.supporting_closure(fact.fact_id)}:
                    return {'bridge_status': 'PASS', 'fact_id': fact.fact_id,
                            'scope': auxiliary['context'], 'statement': fact.statement,
                            'accepted_for_scope': True, 'reused': True}
        packet = {'source_interface': source, 'target_auxiliary': auxiliary,
                  'correspondence': request['correspondence'], 'accepted_facts': [],
                  'task': 'Prove the exact auxiliary interface from the source Fact, preserving every source condition. Source is authorized ONLY for this explicit bridge.'}
        result = self._call('worker', action['study_id'], key + ':worker', C.BRIDGE_WORKER, packet, C.WORKER_SCHEMA)
        if result['status'] != 'COMPLETED':
            return {'bridge_status': result['status']}
        self._note(action['study_id'], key + ':returned-research', {
            'continuation': result['output'].get('continuation', ''),
            'next_work': result['output'].get('next_work', '')})
        candidate = result['output'].get('candidate')
        if not candidate:
            return {'bridge_status': 'DECLINE'}
        if (candidate.get('kind') != 'FACT' or candidate.get('requirements') or
                normalize(candidate.get('goal', '')) != auxiliary['goal'] or
                normalize(candidate.get('context', '')) != auxiliary['context'] or
                candidate.get('predecessors') != [source['fact_id']]):
            return {'bridge_status': 'REJECTED', 'reason': 'bridge changed interface or lineage'}
        prepared = {'statement': auxiliary['statement'], 'proof': candidate['proof'], 'predecessors': [source['fact_id']]}
        verdict = self._submit(key + ':candidate', prepared, 'explicit scope bridge', action['study_id'],
            {'kind': 'BRIDGE', 'context': auxiliary['context'], 'goal': auxiliary['goal'],
             'source_fact_id': source['fact_id']})
        if verdict['accepted']:
            return {'bridge_status': 'PASS', 'fact_id': verdict['fact_id'], 'scope': auxiliary['context'],
                    'statement': auxiliary['statement'], 'accepted_for_scope': True}
        return {'bridge_status': verdict['verdict']}

    def _recurrences(self, control):
        n = self.network
        for sid in list(n.data['pending_recurrence']):
            support = n.data['supports'][sid]
            path = n.ancestor_path(support['conclusion_claim_id'], sid)
            child = n.claim(support['requirement_claim_ids'][0])
            key = control['run_id'] + ':recurrence:' + sid
            packet = {'new_claim': child, 'ancestor_path': [n.claim(cid) for cid in path]}
            probe = self._call('probe', 'probe', key + ':probe', C.PROBE, packet, C.PROBE_SCHEMA)
            output = probe.get('output') or {}
            ancestor = output.get('ancestor_claim_id')
            if probe['status'] != 'COMPLETED' or ancestor not in path or n.claim(ancestor)['context'] != child['context']:
                n.finish_recurrence(sid); continue
            result = self._call('representation', 'representation', key + ':bridge', C.REPRESENTATION,
                {**packet, 'proposed_ancestor': ancestor, 'mapping': output.get('mapping', '')}, C.REPRESENTATION_SCHEMA)
            response = result.get('output') or {}
            if result['status'] != 'COMPLETED' or response.get('mode') not in ('DIRECT','CONDITIONAL') or response.get('predecessors'):
                n.finish_recurrence(sid); continue
            helper = None
            if response['mode'] == 'CONDITIONAL':
                item = response.get('helper')
                if (not isinstance(item, dict) or not isinstance(item.get('goal'), str)
                        or not item['goal'].strip() or not isinstance(item.get('context'), str)
                        or normalize(item['context']) != child['context']):
                    n.finish_recurrence(sid); continue
                helper = make_claim(n.problem_id, item['context'], item['goal'])
                if (helper['claim_id'] in path + [child['claim_id']] or
                        (helper['claim_id'] in n.data['claims'] and
                         (n.truth(helper['claim_id']) == 'REFUTED' or n.alias_of(helper['claim_id'])))):
                    n.finish_recurrence(sid); continue
                # Register only after certificate acceptance; derive exact statement without mutation.
                # Match the model's stable conditional interface below using a transient Claim.
                prior_helper = n.data['claims'].get(helper['claim_id'])
                n.data['claims'][helper['claim_id']] = helper
                statement = n.conditional_equivalence_statement(ancestor, child['claim_id'], helper['claim_id'])
                if prior_helper is None:
                    n.data['claims'].pop(helper['claim_id'])
                else:
                    n.data['claims'][helper['claim_id']] = prior_helper
            else:
                statement = n.equivalence_statement(ancestor, child['claim_id'])
            prepared = {'statement': statement, 'proof': response.get('proof',''), 'predecessors': []}
            if not prepared['proof'].strip():
                n.finish_recurrence(sid); continue
            verdict = self._submit(key + ':certificate', prepared, 'representation transport; no new substantive theorem', 'representation',
                {'kind': 'REPRESENTATION', 'support_id': sid, 'ancestor_claim_id': ancestor,
                 'ancestor_path': path, 'helper': helper})
            if verdict['accepted']:
                self._note('study-' + support['conclusion_claim_id'], key + ':recurrence-feedback',
                    {'research_feedback': 'This route returns to an ancestor-equivalent representation. It has not discharged the ancestor.',
                     'ancestor_claim_id': ancestor, 'conditional_helper': helper['claim_id'] if helper else None})
            else:
                n.finish_recurrence(sid)

    def _activations(self, control):
        n = self.network
        for sid, record in list(n.data['deferred_representations'].items()):
            if sid in n.data['representations'] or record.get('released'):
                continue
            try:
                candidate = n.activation_candidate(sid)
            except ValueError:
                continue
            verdict = self._submit(control['run_id'] + ':activation:' + sid, candidate,
                                   'fixed modus ponens; no additional mathematics', 'activation',
                                   {'kind': 'ACTIVATION', 'support_id': sid})
            if not verdict['accepted']:
                n.release_deferred(sid)
