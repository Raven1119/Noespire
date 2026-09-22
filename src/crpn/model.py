"""The sole CRPN AND/OR authority: Claims own proofs, Supports own certificates.

Runtime receipts and research memory have no mathematical authority.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager

from danus.core.durable_io import atomic_json, read_json, locked
from danus.core import bm25


def normalize(text):
    if not isinstance(text, str):
        raise ValueError("mathematical interfaces must be strings")
    return " ".join(text.split())


def identity(prefix, value):
    return prefix + sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()[:24]


def make_claim(problem_id, context, goal):
    values = dict(problem_id=normalize(problem_id), context=normalize(context), goal=normalize(goal))
    if not values['problem_id'] or not values['goal']:
        raise ValueError('problem and goal must be nonempty')
    statement = (f"Under the assumptions [{values['context']}]: {values['goal']}"
                 if values['context'] else values['goal'])
    return {'claim_id': identity('ob-', values), **values, 'statement': statement}


def proof_identity(record):
    values = {k: record[k] for k in ('problem_id', 'statement', 'proof', 'predecessors')}
    values.update(statement=normalize(values['statement']), proof=normalize(values['proof']),
                  predecessors=sorted(values['predecessors']))
    if record.get('id_scheme') == 'crpn-legacy':
        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    else:
        values['glossary_introduces'] = record.get('glossary_introduces', {})
        canonical = json.dumps(values, ensure_ascii=False, sort_keys=True)
    return sha256(canonical.encode()).hexdigest()[:16]


class Network:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'crpn.json'
        self.data = read_json(self.path)
        self.problem_id = self.data['problem_id']
        self.target_id = self.data['target_claim_id']
        self._snapshot = deepcopy(self.data)
        self._staging = False
        self.validate()

    @classmethod
    def create(cls, root, problem_id, goal, context=''):
        path = Path(root) / 'crpn.json'
        if path.exists():
            raise ValueError('CRPN state exists')
        if (Path(root) / 'fact_graph').exists() or (Path(root) / 'proof_graph.json').exists():
            raise ValueError('legacy truth store exists; migrate into a fresh workspace')
        claim = make_claim(problem_id, context, goal)
        atomic_json(path, {'schema_version': 'crpn-authority-2', 'problem_id': claim['problem_id'],
            'target_claim_id': claim['claim_id'], 'claims': {claim['claim_id']: claim},
            'supports': {}, 'studies': {},
            'representations': {}, 'deferred_representations': {}, 'pending_recurrence': []})
        result = cls(root)
        result.ensure_studies()
        return result

    def claim(self, claim_id):
        try:
            row = self.data['claims'][claim_id]
            return make_claim(self.problem_id, row['context'], row['goal'])
        except KeyError as error:
            raise ValueError('unknown Claim') from error

    def register_claim(self, goal, context=''):
        claim = make_claim(self.problem_id, context, goal)
        if claim['claim_id'] not in self.data['claims']:
            self.data['claims'][claim['claim_id']] = claim
            self.save()
        return deepcopy(claim)

    def save(self):
        if self._staging:
            return
        self.validate()
        self._check_proof_transition()
        with locked(self.root / '.graph.lock'):
            if read_json(self.path) != self._snapshot:
                raise ValueError('concurrent CRPN state change; reload before writing')
            if self.data == self._snapshot:
                return
            atomic_json(self.path, self.data)
            self._snapshot = deepcopy(self.data)

    def _check_proof_transition(self):
        old = Network.__new__(Network)
        old.data = self._snapshot
        before, after = old._records(), self._records()
        for fid, (table, owner, slot, record) in before.items():
            if fid not in after or after[fid][:3] != (table, owner, slot):
                raise ValueError('cannot discard or transfer historical proof ownership')
            current = after[fid][3]
            if ({k:v for k,v in record.items() if k not in ('status', 'history')} !=
                    {k:v for k,v in current.items() if k not in ('status', 'history')}
                    or current['history'][:len(record['history'])] != record['history']
                    or record['status'] == 'revoked' and current['status'] != 'revoked'):
                raise ValueError('historical proof is immutable; revocation cannot be undone')
        for fid in after.keys() - before.keys():
            acceptance = after[fid][3]['history'][0]
            verification = acceptance.get('verification')
            submission = acceptance.get('submission', '')
            if (not isinstance(verification, dict) or verification.get('verdict') != 'correct'
                    or len(submission) != 64 or any(c not in '0123456789abcdef' for c in submission)):
                raise ValueError('new proof requires CRPN verified submission')
            directory = self.root / 'submissions' / submission
            if read_json(directory / 'verification.json') != verification:
                raise ValueError('proof verification receipt mismatch')
            request = read_json(directory / 'request.json')
            if any(after[fid][3][k] != request[k] for k in ('problem_id', 'statement', 'proof', 'predecessors')):
                raise ValueError('proof submission content mismatch')

    def _assert_current(self):
        if (hasattr(self, '_snapshot') and not self._staging
                and read_json(self.path) != self._snapshot):
            raise ValueError('CRPN authority changed; reload before reading premises')

    @contextmanager
    def _transaction(self):
        """One graph publication, including evidence and its mathematical owner."""
        before = deepcopy(self.data)
        if self._staging:
            raise ValueError('nested graph admission')
        self._staging = True
        try:
            yield
            self._staging = False
            self.save()
        except BaseException:
            self.data = before
            raise
        finally:
            self._staging = False

    def _records(self):
        records = {}
        for table, slots in (('claims', ('proofs', 'refutations')), ('supports', ('certificates',))):
            for owner, node in self.data[table].items():
                for slot in slots:
                    for fid, record in node.get(slot, {}).items():
                        if fid in records:
                            raise ValueError('proof has multiple authority owners')
                        records[fid] = (table, owner, slot, record)
        return records

    def _stored(self, fact_id):
        try:
            record = self._records()[fact_id][3]
        except KeyError as error:
            raise ValueError('unknown proof evidence') from error
        return SimpleNamespace(**deepcopy(record))

    def _accepted(self, fact_id):
        self._assert_current()
        self.supporting_closure(fact_id)
        return self._stored(fact_id)

    def _active(self, fact_id):
        if self._stored(fact_id).status == 'revoked':
            return False
        self._accepted(fact_id)
        return True

    def proof_ids(self):
        return sorted(fid for fid in self._records() if self._active(fid))

    def revoked_ids(self):
        self._assert_current()
        return {fid for fid, (_, _, _, r) in self._records().items() if r['status'] == 'revoked'}

    def supporting_closure(self, fact_id):
        self._assert_current()
        records = self._records()
        seen, visiting, ordered = set(), set(), []
        def visit(fid):
            if fid in visiting:
                raise ValueError('proof dependency cycle')
            if fid in seen:
                return
            if fid not in records or records[fid][3]['status'] != 'accepted':
                raise ValueError('missing or revoked proof in closure')
            record = records[fid][3]
            visiting.add(fid)
            for predecessor in record['predecessors']:
                visit(predecessor)
            visiting.remove(fid)
            seen.add(fid)
            ordered.append(SimpleNamespace(**deepcopy(record)))
        visit(fact_id)
        return ordered

    def search(self, query, limit=10):
        ids = self.proof_ids()
        records = [self._stored(fid) for fid in ids]
        documents = [bm25.tokenize(' '.join((r.statement, r.proof, getattr(r, 'intuition', '')))) for r in records]
        scores = bm25.bm25_scores(query, documents)
        return [{'fact_id': r.fact_id, 'score': score, 'statement': normalize(r.statement)}
                for r, score in sorted(zip(records, scores), key=lambda pair: -pair[1]) if score > 0][:limit]

    def revoke(self, fact_id, reason):
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError('revocation requires reason')
        records = self._records()
        if fact_id not in records:
            raise ValueError('unknown proof evidence')
        invalid = {fact_id}
        while True:
            expanded = invalid | {fid for fid, (_, _, _, r) in records.items()
                                  if invalid.intersection(r['predecessors'])}
            if expanded == invalid:
                break
            invalid = expanded
        with self._transaction():
            for fid in sorted(invalid):
                r = records[fid][3]
                if r['status'] != 'revoked':
                    r['status'] = 'revoked'
                    r.setdefault('history', []).append({'event': 'revoked', 'root': fact_id, 'reason': reason})
        return sorted(invalid)

    def facts_for(self, claim_id):
        claim = self.claim(claim_id)
        return tuple(self._accepted(fid) for fid in self.data['claims'][claim_id].get('proofs', {})
                     if self._active(fid) and normalize(self._stored(fid).statement) == claim['statement'])

    def truth(self, claim_id):
        self.claim(claim_id)
        if self.facts_for(claim_id):
            return 'DISCHARGED'
        return ('REFUTED' if any(self._active(fid) for fid in
                self.data['claims'][claim_id].get('refutations', {})) else 'OPEN')

    def refutation_statement(self, claim_id):
        claim = self.claim(claim_id)
        return 'The following proposition is false: ' + json.dumps(claim['statement'], ensure_ascii=False) + '.'

    def _contexts(self, fact_id):
        table, owner, _, _ = self._records()[fact_id]
        cid = owner if table == 'claims' else self.data['supports'][owner]['conclusion_claim_id']
        return {self.claim(cid)['context']}

    def visible_fact(self, fact_id, context):
        if self._contexts(fact_id) != {normalize(context)}:
            raise ValueError('Fact requires exact scope binding; inspect then bridge a foreign interface')
        return self._accepted(fact_id)

    def inspect_fact(self, fact_id):
        contexts = self._contexts(fact_id)
        if len(contexts) != 1:
            raise ValueError('Fact has no unambiguous scope binding')
        fact = self._accepted(fact_id)
        return {'fact_id': fact_id, 'scope': next(iter(contexts)), 'statement': fact.statement}

    def conditional_statement(self, claim, requirements):
        if any(row['context'] != claim['context'] for row in requirements):
            raise ValueError('Support requires exact ambient scope')
        goal = ('The conjunction of these statements ' + json.dumps([r['goal'] for r in requirements], ensure_ascii=False)
                + ' implies the statement ' + json.dumps(claim['goal'], ensure_ascii=False) + '.')
        return make_claim(self.problem_id, claim['context'], goal)['statement']

    def prepare_candidate(self, candidate, visible_fact_ids):
        kind = candidate['kind']
        if kind not in ('FACT', 'SUPPORT', 'REFUTATION'):
            raise ValueError('unknown mathematical candidate')
        claim = make_claim(self.problem_id, candidate['context'], candidate['goal'])
        requirements = [make_claim(self.problem_id, row['context'], row['goal'])
                        for row in candidate.get('requirements', [])]
        if (kind == 'SUPPORT') != bool(requirements):
            raise ValueError('Support requires conditions; other candidates cannot have requirements')
        if any(row['context'] != claim['context'] for row in requirements):
            raise ValueError('Support requires exact ambient scope')
        predecessors = sorted(set(candidate['predecessors']))
        visible = sorted(set(visible_fact_ids))
        if not set(predecessors) <= set(visible):
            raise ValueError('predecessor was not supplied as accepted material')
        for fid in visible:
            self.visible_fact(fid, claim['context'])
        if kind == 'REFUTATION':
            if claim['claim_id'] not in self.data['claims'] or self.facts_for(claim['claim_id']):
                raise ValueError('Refutation must concern an existing unresolved Claim')
            statement = self.refutation_statement(claim['claim_id'])
        elif kind == 'FACT':
            if claim['claim_id'] in self.data['claims'] and self.truth(claim['claim_id']) == 'REFUTED':
                raise ValueError('Claim already refuted')
            statement = claim['statement']
        else:
            statement = self.conditional_statement(claim, requirements)
        proof = candidate['proof']
        if not isinstance(proof, str) or not proof.strip():
            raise ValueError('complete candidate proof required')
        prepared = {'statement': statement, 'proof': proof, 'predecessors': predecessors}
        descriptor = {'kind': kind, 'goal': claim['goal'], 'context': claim['context'], 'proof': proof,
                      'requirements': [{'goal': r['goal'], 'context': r['context']} for r in requirements],
                      'predecessors': predecessors, 'visible_fact_ids': visible}
        return prepared, descriptor

    def _admit_candidate(self, descriptor, record):
        prepared, checked = self.prepare_candidate(descriptor, descriptor['visible_fact_ids'])
        if any(record[k] != prepared[k] for k in ('statement', 'proof', 'predecessors')):
            raise ValueError('verified proof does not match candidate')
        claim = make_claim(self.problem_id, checked['context'], checked['goal'])
        node = self.data['claims'].setdefault(claim['claim_id'], claim)
        fid = record['fact_id']
        if checked['kind'] != 'SUPPORT':
            slot = 'proofs' if checked['kind'] == 'FACT' else 'refutations'
            self._attach('claims', claim['claim_id'], slot, record)
            return {'kind': checked['kind'], 'claim_id': claim['claim_id'], 'fact_id': fid}
        old_claims = set(self.data['claims'])
        requirements = [make_claim(self.problem_id, r['context'], r['goal']) for r in checked['requirements']]
        path = self.ancestor_path(claim['claim_id'])
        values = {'conclusion_claim_id': claim['claim_id'], 'requirement_claim_ids': [r['claim_id'] for r in requirements],
                  'scope_ref': identity('scope-', {'problem_id': self.problem_id, 'context': claim['context']}),
                  'bridge_fact_id': fid}
        support = {'support_id': identity('support-', values), **values}
        sid = support['support_id']
        if sid not in self.data['supports']:
            for r in requirements:
                self.data['claims'].setdefault(r['claim_id'], r)
            self.data['supports'][sid] = support
            child = requirements[0]['claim_id']
            if len(requirements) == 1 and (child not in old_claims or child in path):
                self.data['pending_recurrence'].append(sid)
        self._attach('supports', sid, 'certificates', record)
        self.ensure_studies(save=False)
        return {'kind': 'SUPPORT', **self.support(sid), 'fact_id': fid}

    def _attach(self, table, owner, slot, record):
        """Private to CRPN admission/import; no independent proof-store write."""
        fid = record['fact_id']
        old = self._records().get(fid)
        if old:
            if old[3]['status'] == 'revoked':
                raise ValueError('revoked evidence cannot be readmitted')
            if old[:3] != (table, owner, slot) or any(old[3][k] != record[k] for k in
                    ('problem_id', 'statement', 'proof', 'predecessors')):
                raise ValueError('proof identity/ownership conflict')
            return
        self.data[table][owner].setdefault(slot, {})[fid] = deepcopy(record)

    def support(self, sid):
        return {k: deepcopy(v) for k, v in self.data['supports'][sid].items() if k != 'certificates'}

    def ready_supports(self):
        return tuple(self.support(sid) for sid, row in sorted(self.data['supports'].items())
                     if self.truth(row['conclusion_claim_id']) == 'OPEN' and self._active(row['bridge_fact_id'])
                     and all(self.facts_for(cid) for cid in row['requirement_claim_ids']))

    def support_materials(self, support_id):
        support = next((s for s in self.ready_supports() if s['support_id'] == support_id), None)
        if support is None:
            raise ValueError('Support is not ready to compose')
        ids = [support['bridge_fact_id']] + [self.facts_for(cid)[0].fact_id for cid in support['requirement_claim_ids']]
        return {'support': support, 'conclusion': self.claim(support['conclusion_claim_id']),
                'requirements': [self.claim(cid) for cid in support['requirement_claim_ids']],
                'facts': tuple(self._accepted(fid) for fid in sorted(set(ids)))}

    def prepare_compose(self, support_id, candidate):
        packet = self.support_materials(support_id)
        required = [f.fact_id for f in packet['facts']]
        prepared, descriptor = self.prepare_candidate(candidate, required)
        if (candidate['kind'] != 'FACT' or prepared['statement'] != packet['conclusion']['statement']
                or set(prepared['predecessors']) != set(required)):
            raise ValueError('COMPOSE requires exact conclusion and certificate/condition lineage')
        return prepared, descriptor

    def compose_candidate(self, support_id, proof):
        packet = self.support_materials(support_id)
        claim = packet['conclusion']
        return {'kind': 'FACT', 'context': claim['context'], 'goal': claim['goal'], 'requirements': [],
                'predecessors': [f.fact_id for f in packet['facts']], 'proof': proof}

    def ancestor_path(self, conclusion_id, exclude_support=None):
        self.claim(conclusion_id)
        queue, seen = [(self.target_id, [self.target_id])], set()
        for key, path in queue:
            if key == conclusion_id:
                return path
            if key in seen:
                continue
            seen.add(key)
            for sid, row in sorted(self.data['supports'].items()):
                if sid != exclude_support and row['conclusion_claim_id'] == key and self._active(row['bridge_fact_id']):
                    queue.extend((child, path + [child]) for child in row['requirement_claim_ids'] if child not in path)
        return [conclusion_id]

    def equivalence_statement(self, ancestor_id, claim_id):
        a, b = self.claim(ancestor_id), self.claim(claim_id)
        if a['context'] != b['context']:
            raise ValueError('representation requires exact ambient scope')
        goal = 'The following two propositions are equivalent: ' + json.dumps([a['goal'], b['goal']], ensure_ascii=False) + '.'
        return make_claim(self.problem_id, a['context'], goal)['statement']

    def conditional_equivalence_statement(self, ancestor_id, claim_id, helper_id):
        self.equivalence_statement(ancestor_id, claim_id)
        a, b, h = (self.claim(k) for k in (ancestor_id, claim_id, helper_id))
        if h['context'] != a['context']:
            raise ValueError('helper requires exact ambient scope')
        goal = ('If the proposition ' + json.dumps(h['goal'], ensure_ascii=False)
                + ' holds, then the following two propositions are equivalent: '
                + json.dumps([a['goal'], b['goal']], ensure_ascii=False) + '.')
        return make_claim(self.problem_id, a['context'], goal)['statement']

    def _recurrence(self, support_id, ancestor_id, ancestor_path=None):
        row = self.data['supports'][support_id]
        if len(row['requirement_claim_ids']) != 1:
            raise ValueError('only unary representation recurrence is supported')
        path = ancestor_path or self.ancestor_path(row['conclusion_claim_id'], support_id)
        if not path or path[-1] != row['conclusion_claim_id'] or ancestor_id not in path or len(set(path)) != len(path):
            raise ValueError('invalid ancestor path')
        for parent, child in zip(path, path[1:]):
            if not any(sid != support_id and s['conclusion_claim_id'] == parent and child in s['requirement_claim_ids']
                       and self._active(s['bridge_fact_id']) for sid, s in self.data['supports'].items()):
                raise ValueError('ancestor path has no accepted Support')
        self._accepted(row['bridge_fact_id'])
        cid = row['requirement_claim_ids'][0]
        self.equivalence_statement(ancestor_id, cid)
        return {'support_id': support_id, 'claim_id': cid, 'ancestor_claim_id': ancestor_id, 'ancestor_path': path}

    def finish_recurrence(self, support_id):
        if support_id in self.data['pending_recurrence']:
            self.data['pending_recurrence'].remove(support_id)
        self.ensure_studies(save=False)
        self.save()

    def record_alias(self, support_id, ancestor_id, equivalence_fact_id, ancestor_path=None):
        row = self._recurrence(support_id, ancestor_id, ancestor_path)
        fact = self._accepted(equivalence_fact_id)
        if normalize(fact.statement) != self.equivalence_statement(ancestor_id, row['claim_id']):
            raise ValueError('wrong equivalence certificate')
        row['equivalence_fact_id'] = equivalence_fact_id
        prior = self.data['representations'].get(support_id)
        if prior is not None and prior != row:
            raise ValueError('cannot overwrite representation history')
        self.data['representations'][support_id] = row
        self.finish_recurrence(support_id)

    def defer_alias(self, support_id, ancestor_id, helper_claim_id, conditional_fact_id, ancestor_path=None):
        row = self._recurrence(support_id, ancestor_id, ancestor_path)
        if row['claim_id'] in row['ancestor_path'] or helper_claim_id in row['ancestor_path'] + [row['claim_id']]:
            raise ValueError('helper must be independent of the recurrence path')
        existing = self.data['deferred_representations'].get(support_id)
        if existing:
            if (existing['helper_claim_id'] != helper_claim_id or existing['conditional_fact_id'] != conditional_fact_id
                    or any(existing[k] != row[k] for k in row)):
                raise ValueError('cannot overwrite deferred history')
            self._accepted(conditional_fact_id)
            return
        if self.truth(helper_claim_id) == 'REFUTED' or self.alias_of(helper_claim_id):
            raise ValueError('helper must be an independent, non-refuted Claim')
        fact = self._accepted(conditional_fact_id)
        if normalize(fact.statement) != self.conditional_equivalence_statement(ancestor_id, row['claim_id'], helper_claim_id):
            raise ValueError('wrong conditional equivalence certificate')
        row.update(helper_claim_id=helper_claim_id, conditional_fact_id=conditional_fact_id, released=False)
        prior = self.data['deferred_representations'].get(support_id)
        if prior is not None and prior != row:
            raise ValueError('cannot overwrite deferred history')
        self.data['deferred_representations'][support_id] = row
        self.finish_recurrence(support_id)

    def activation_candidate(self, support_id):
        row = self.data['deferred_representations'][support_id]
        self._accepted(row['conditional_fact_id'])
        self._accepted(self.data['supports'][support_id]['bridge_fact_id'])
        helpers = self.facts_for(row['helper_claim_id'])
        if row.get('released') or not helpers or support_id in self.data['representations']:
            raise ValueError('no pending helper-satisfied activation')
        ids = sorted([row['conditional_fact_id'], helpers[0].fact_id])
        return {'statement': self.equivalence_statement(row['ancestor_claim_id'], row['claim_id']),
                'proof': ('The accepted conditional certificate ' + row['conditional_fact_id']
                          + ' asserts that the helper implies exactly the displayed equivalence. The accepted helper Fact '
                          + helpers[0].fact_id + ' establishes that helper. By modus ponens the equivalence follows. '
                          'Neither proposition is asserted unconditionally.'), 'predecessors': ids}

    def activate_alias(self, support_id, activation_fact_id):
        existing = self.data['representations'].get(support_id)
        if existing:
            if existing['equivalence_fact_id'] != activation_fact_id:
                raise ValueError('activation already completed differently')
            self._accepted(activation_fact_id)
            return
        candidate = self.activation_candidate(support_id)
        fact = self._accepted(activation_fact_id)
        if (normalize(fact.statement) != candidate['statement'] or fact.predecessors != candidate['predecessors']
                or normalize(fact.proof) != normalize(candidate['proof'])):
            raise ValueError('activation must preserve the fixed modus-ponens candidate and lineage')
        row = self.data['deferred_representations'][support_id]
        self.record_alias(support_id, row['ancestor_claim_id'], activation_fact_id, row['ancestor_path'])

    def release_deferred(self, support_id):
        self.data['deferred_representations'][support_id]['released'] = True
        self.ensure_studies(save=False)
        self.save()

    def alias_of(self, claim_id):
        for sid, row in self.data['representations'].items():
            if (row['claim_id'] == claim_id and claim_id != row['ancestor_claim_id']
                    and self._active(row['equivalence_fact_id']) and self._active(self.data['supports'][sid]['bridge_fact_id'])):
                return row['ancestor_claim_id']
        return None

    def waiting_on(self, claim_id):
        for sid, row in self.data['deferred_representations'].items():
            if (row['claim_id'] == claim_id and not row.get('released') and sid not in self.data['representations']
                    and self._active(row['conditional_fact_id']) and self._active(self.data['supports'][sid]['bridge_fact_id'])
                    and self.truth(row['helper_claim_id']) != 'REFUTED'):
                return row['helper_claim_id']
        return None

    def study_suppressed(self, claim_id):
        if self.alias_of(claim_id) or self.waiting_on(claim_id):
            return True
        # Exact ancestor recurrences must never suppress the existing ancestor.
        return any(claim_id in self.data['supports'][sid]['requirement_claim_ids']
                   and 'study-' + claim_id not in self.data['studies']
                   and self._active(self.data['supports'][sid]['bridge_fact_id'])
                   for sid in self.data['pending_recurrence'])

    def ensure_studies(self, *, save=True):
        for cid, claim in self.data['claims'].items():
            key = 'study-' + cid
            if key not in self.data['studies'] and self.truth(cid) == 'OPEN' and not self.study_suppressed(cid):
                self.data['studies'][key] = {'study_id': key, 'claim_id': cid, 'scope': claim['context'],
                    'focus': claim['goal'], 'revision': 0}
        if save:
            self.save()

    def register_study(self, focus, scope='', *, claim_id=None, study_id=None):
        focus, scope = normalize(focus), normalize(scope)
        if not focus:
            raise ValueError('Study requires a research focus')
        if claim_id:
            claim = self.claim(claim_id)
            if scope != claim['context']:
                raise ValueError('Study scope differs from its Claim')
            expected = 'study-' + claim_id
        else:
            expected = identity('study-', {'focus': focus, 'scope': scope})
        key = study_id or expected
        if not key or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key):
            raise ValueError('invalid Study identifier')
        if claim_id and key != expected:
            raise ValueError('Claim Study identity mismatch')
        row = {'study_id': key, 'claim_id': claim_id, 'scope': scope, 'focus': focus, 'revision': 0}
        if key not in self.data['studies']:
            self.data['studies'][key] = row
            self.save()
        elif any(self.data['studies'][key].get(k) != row[k] for k in ('claim_id', 'scope', 'focus')):
            raise ValueError('Study identity changed')
        return deepcopy(self.data['studies'][key])

    def active_studies(self):
        return tuple(deepcopy(s) for s in self.data['studies'].values()
                     if not s.get('claim_id') or (self.truth(s['claim_id']) == 'OPEN'
                                                   and not self.study_suppressed(s['claim_id'])))

    def effective_depth(self):
        def walk(cid, path):
            depths = [0]
            for sid, row in self.data['supports'].items():
                if row['conclusion_claim_id'] != cid or not self._active(row['bridge_fact_id']):
                    continue
                alias = self.data['representations'].get(sid)
                if alias and self._active(alias['equivalence_fact_id']):
                    continue
                children = row['requirement_claim_ids']
                deferred = self.data['deferred_representations'].get(sid)
                if deferred and self.waiting_on(deferred['claim_id']):
                    children = [deferred['helper_claim_id']]
                depths.extend(1 + walk(k, path | {k}) for k in children if k not in path and not self.alias_of(k))
            return max(depths)
        return walk(self.target_id, {self.target_id})

    def export(self):
        facts = self.facts_for(self.target_id)
        if not facts:
            raise ValueError('target remains unresolved')
        return {'target_fact_id': facts[0].fact_id, 'verification': 'LLM-verified',
                'facts': [vars(f) for f in self.supporting_closure(facts[0].fact_id)]}

    def validate(self):
        if self.data.get('schema_version') != 'crpn-authority-2' or self.target_id not in self.data['claims']:
            raise ValueError('invalid CRPN state')
        for cid, claim in self.data['claims'].items():
            if {k:v for k,v in claim.items() if k not in ('proofs', 'refutations')} != make_claim(self.problem_id, claim['context'], claim['goal']) or cid != claim['claim_id']:
                raise ValueError('Claim identity changed')
        if 'fact_bindings' in self.data or 'refutations' in self.data:
            raise ValueError('parallel truth bindings are retired')
        records = self._records()
        for fid, (table, owner, slot, record) in records.items():
            if (fid != record['fact_id'] or record['problem_id'] != self.problem_id
                    or record.get('id_scheme') not in ('content-v1', 'crpn-legacy')
                    or record['status'] not in ('accepted', 'revoked')
                    or proof_identity(record) != fid):
                raise ValueError('proof identity/status corruption')
            if not record.get('history') or record['history'][0].get('event') != 'accepted':
                raise ValueError('missing historical acceptance')
            if any(e.get('event') == 'revoked' for e in record['history']) != (record['status'] == 'revoked'):
                raise ValueError('revoked evidence cannot be resurrected')
            if table == 'claims':
                expected = self.claim(owner)['statement'] if slot == 'proofs' else self.refutation_statement(owner)
                if normalize(record['statement']) != expected:
                    raise ValueError('proof owner interface mismatch')
            else:
                allowed = {self.data['supports'][owner]['bridge_fact_id']}
                for relations, field in (('representations', 'equivalence_fact_id'),
                                         ('deferred_representations', 'conditional_fact_id')):
                    relation = self.data[relations].get(owner)
                    if relation:
                        allowed.add(relation[field])
                if fid not in allowed:
                    raise ValueError('certificate lacks its exact Support relation')
            if self._active(fid):
                self._accepted(fid)
        # Historical revoked closures must still be complete and acyclic.
        seen, visiting = set(), set()
        def history(fid):
            if fid in visiting or fid not in records:
                raise ValueError('missing/cyclic historical proof dependency')
            if fid in seen:
                return
            visiting.add(fid)
            for pred in records[fid][3]['predecessors']:
                history(pred)
            visiting.remove(fid)
            seen.add(fid)
        for fid in records:
            history(fid)
        for cid, claim in self.data['claims'].items():
            if self.facts_for(cid) and any(self._active(fid) for fid in claim.get('refutations', {})):
                raise ValueError('contradictory truth bindings')
        for sid, row in self.data['supports'].items():
            values = {k: v for k, v in row.items() if k not in ('support_id', 'certificates')}
            claim = self.claim(row['conclusion_claim_id'])
            requirements = [self.claim(k) for k in row['requirement_claim_ids']]
            if (not requirements or sid != row['support_id'] or sid != identity('support-', values)
                    or row['scope_ref'] != identity('scope-', {'problem_id': self.problem_id, 'context': claim['context']})
                    or normalize(self._stored(row['bridge_fact_id']).statement) != self.conditional_statement(claim, requirements)):
                raise ValueError('Support interface mismatch')
        for key, study in self.data['studies'].items():
            if (key != study['study_id'] or not key or any(c not in
                    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in key)):
                raise ValueError('Study identity mismatch')
            if study.get('claim_id'):
                claim = self.claim(study['claim_id'])
                if key != 'study-' + claim['claim_id'] or study['scope'] != claim['context']:
                    raise ValueError('Study identity/scope mismatch')
            if not isinstance(study.get('focus'), str) or not isinstance(study.get('scope'), str):
                raise ValueError('Study needs a complete focus and scope')
        if any(sid not in self.data['supports'] or len(self.data['supports'][sid]['requirement_claim_ids']) != 1
               for sid in self.data['pending_recurrence']):
            raise ValueError('invalid pending recurrence')
        for table in ('representations', 'deferred_representations'):
            for sid, row in self.data[table].items():
                support = self.data['supports'][sid]
                if (row['support_id'] != sid or support['requirement_claim_ids'] != [row['claim_id']]
                        or not row['ancestor_path'] or row['ancestor_path'][-1] != support['conclusion_claim_id']
                        or row['ancestor_claim_id'] not in row['ancestor_path']):
                    raise ValueError('invalid representation relation')
                for a, b in zip(row['ancestor_path'], row['ancestor_path'][1:]):
                    if not any(k != sid and s['conclusion_claim_id'] == a and b in s['requirement_claim_ids']
                               for k, s in self.data['supports'].items()):
                        raise ValueError('broken representation ancestor path')
                if table == 'representations':
                    expected = self.equivalence_statement(row['ancestor_claim_id'], row['claim_id'])
                    fid = row['equivalence_fact_id']
                    deferred = self.data['deferred_representations'].get(sid)
                    if deferred:
                        pred = self._stored(fid).predecessors
                        helpers = self.data['claims'][deferred['helper_claim_id']].get('proofs', {})
                        if len(pred) != 2 or deferred['conditional_fact_id'] not in pred or not set(pred).intersection(helpers):
                            raise ValueError('activation lost helper/certificate lineage')
                else:
                    expected = self.conditional_equivalence_statement(row['ancestor_claim_id'], row['claim_id'], row['helper_claim_id'])
                    fid = row['conditional_fact_id']
                    if row['helper_claim_id'] in row['ancestor_path'] + [row['claim_id']] or row['claim_id'] in row['ancestor_path']:
                        raise ValueError('helper is not independent')
                if normalize(self._stored(fid).statement) != expected:
                    raise ValueError('representation certificate mismatch')
        links = {r['claim_id']: r['ancestor_claim_id'] for r in self.data['representations'].values()
                 if r['claim_id'] != r['ancestor_claim_id']}
        for start in links:
            seen = set()
            while start in links:
                if start in seen:
                    raise ValueError('representation alias cycle')
                seen.add(start)
                start = links[start]
