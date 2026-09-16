"""CRPN mathematical/search relations. DANUS alone stores verified truth.

No process, invocation, memory or permission journal lives here. Claims and
Supports are immutable interfaces; accepted Fact bindings are checked against
DANUS on every use. Alias certificates transport representations, never truth.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from danus.core.durable_io import atomic_json, read_json
from danus.core.factgraph import FactGraph, parse_fact


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


class Network:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'crpn.json'
        self.data = read_json(self.path)
        self.problem_id = self.data['problem_id']
        self.target_id = self.data['target_claim_id']
        self.graph = FactGraph(self.root)
        self.validate()

    @classmethod
    def create(cls, root, problem_id, goal, context=''):
        path = Path(root) / 'crpn.json'
        if path.exists():
            raise ValueError('CRPN state exists')
        claim = make_claim(problem_id, context, goal)
        atomic_json(path, {'schema_version': 'crpn-danus-1', 'problem_id': claim['problem_id'],
            'target_claim_id': claim['claim_id'], 'claims': {claim['claim_id']: claim},
            'fact_bindings': {}, 'supports': {}, 'studies': {}, 'refutations': {},
            'representations': {}, 'deferred_representations': {}, 'pending_recurrence': []})
        result = cls(root)
        result.ensure_studies()
        return result

    def claim(self, claim_id):
        try:
            return deepcopy(self.data['claims'][claim_id])
        except KeyError as error:
            raise ValueError('unknown Claim') from error

    def register_claim(self, goal, context=''):
        claim = make_claim(self.problem_id, context, goal)
        if claim['claim_id'] not in self.data['claims']:
            self.data['claims'][claim['claim_id']] = claim
            self.save()
        return deepcopy(claim)

    def save(self):
        self.validate()
        atomic_json(self.path, self.data)

    def _stored(self, fact_id):
        # Revoked certificates are retained as history, never returned by _accepted.
        self.graph._path(fact_id)
        if fact_id in self.graph.revoked_ids():
            path = self.graph.revoked_dir / (fact_id + '.md')
            active_path = self.graph._path(fact_id)
            if path.exists() and active_path.exists() and path.read_bytes() != active_path.read_bytes():
                raise ValueError('conflicting revoked Fact evidence')
            # A durable DANUS revocation batch already invalidates the Fact,
            # even if a crash precedes its move to the archive. Read its old
            # bytes only for historical interface validation, never acceptance.
            if not path.exists():
                path = active_path
            if not path.exists():
                raise ValueError('missing revoked Fact evidence')
            fact = parse_fact(path.read_text(encoding='utf-8'), fact_id)
        else:
            fact = self.graph.get(fact_id)
        if fact.problem_id != self.problem_id:
            raise ValueError('cross-problem Fact')
        return fact

    def _accepted(self, fact_id):
        fact = self.graph.get(fact_id)
        closure = self.graph.supporting_closure(fact_id)
        if any(item.problem_id != self.problem_id for item in closure):
            raise ValueError('cross-problem Fact closure')
        return fact

    def _active(self, fact_id):
        # Revocation is a lawful transition; missing/corrupt files remain errors.
        if fact_id in self.graph.revoked_ids():
            return False
        self._accepted(fact_id)
        return True

    def facts_for(self, claim_id):
        claim = self.claim(claim_id)
        return tuple(self._accepted(fid) for fid in self.data['fact_bindings'].get(claim_id, [])
                     if self._active(fid) and normalize(self._stored(fid).statement) == claim['statement'])

    def truth(self, claim_id):
        self.claim(claim_id)
        if self.facts_for(claim_id):
            return 'DISCHARGED'
        fid = self.data['refutations'].get(claim_id)
        return 'REFUTED' if fid and self._active(fid) else 'OPEN'

    def bind_fact(self, claim_id, fact_id):
        fact, claim = self._accepted(fact_id), self.claim(claim_id)
        if normalize(fact.statement) != claim['statement'] or self.truth(claim_id) == 'REFUTED':
            raise ValueError('Fact does not establish this exact scoped Claim')
        bindings = self.data['fact_bindings'].setdefault(claim_id, [])
        if fact_id not in bindings:
            bindings.append(fact_id)
            self.save()

    def refutation_statement(self, claim_id):
        claim = self.claim(claim_id)
        return 'The following proposition is false: ' + json.dumps(claim['statement'], ensure_ascii=False) + '.'

    def bind_refutation(self, claim_id, fact_id):
        fact = self._accepted(fact_id)
        if normalize(fact.statement) != self.refutation_statement(claim_id) or self.facts_for(claim_id):
            raise ValueError('Refutation must contradict exactly this unresolved Claim')
        old = self.data['refutations'].get(claim_id)
        if old and old != fact_id:
            raise ValueError('cannot replace Refutation evidence')
        self.data['refutations'][claim_id] = fact_id
        self.save()

    def _contexts(self, fact_id):
        contexts = {self.claim(cid)['context'] for cid, ids in self.data['fact_bindings'].items() if fact_id in ids}
        contexts.update(self.claim(row['conclusion_claim_id'])['context'] for row in self.data['supports'].values()
                        if row['bridge_fact_id'] == fact_id)
        for table, key in (('representations', 'equivalence_fact_id'),
                           ('deferred_representations', 'conditional_fact_id')):
            contexts.update(self.claim(row['ancestor_claim_id'])['context'] for row in self.data[table].values()
                            if row[key] == fact_id)
        contexts.update(self.claim(cid)['context'] for cid, fid in self.data['refutations'].items() if fid == fact_id)
        return contexts

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

    def accept_verified(self, descriptor, fact_id):
        prepared, checked = self.prepare_candidate(descriptor, descriptor['visible_fact_ids'])
        fact = self._accepted(fact_id)
        if (normalize(fact.statement) != prepared['statement'] or normalize(fact.proof) != normalize(prepared['proof'])
                or fact.predecessors != prepared['predecessors']):
            raise ValueError('accepted Fact does not match candidate')
        claim = make_claim(self.problem_id, checked['context'], checked['goal'])
        self.data['claims'].setdefault(claim['claim_id'], claim)
        if checked['kind'] == 'FACT':
            bindings = self.data['fact_bindings'].setdefault(claim['claim_id'], [])
            if fact_id not in bindings:
                bindings.append(fact_id)
            self.save()  # Claim registration and its binding publish together.
            return {'kind': 'FACT', 'claim_id': claim['claim_id'], 'fact_id': fact_id}
        if checked['kind'] == 'REFUTATION':
            self.bind_refutation(claim['claim_id'], fact_id)
            return {'kind': 'REFUTATION', 'claim_id': claim['claim_id'], 'fact_id': fact_id}
        old_claims = set(self.data['claims'])
        requirements = [make_claim(self.problem_id, r['context'], r['goal']) for r in checked['requirements']]
        path = self.ancestor_path(claim['claim_id'])
        values = {'conclusion_claim_id': claim['claim_id'], 'requirement_claim_ids': [r['claim_id'] for r in requirements],
                  'scope_ref': identity('scope-', {'problem_id': self.problem_id, 'context': claim['context']}),
                  'bridge_fact_id': fact_id}
        support = {'support_id': identity('support-', values), **values}
        sid = support['support_id']
        if sid not in self.data['supports']:
            self.data['claims'].update((r['claim_id'], r) for r in requirements)
            self.data['supports'][sid] = support
            child = requirements[0]['claim_id']
            if len(requirements) == 1 and (child not in old_claims or child in path):
                self.data['pending_recurrence'].append(sid)
            self.ensure_studies(save=False)
            self.save()
        return {'kind': 'SUPPORT', **deepcopy(support), 'fact_id': fact_id}

    def ready_supports(self):
        return tuple(deepcopy(row) for _, row in sorted(self.data['supports'].items())
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
                'facts': [vars(f) for f in self.graph.supporting_closure(facts[0].fact_id)]}

    def validate(self):
        if self.data.get('schema_version') != 'crpn-danus-1' or self.target_id not in self.data['claims']:
            raise ValueError('invalid CRPN state')
        for cid, claim in self.data['claims'].items():
            if claim != make_claim(self.problem_id, claim['context'], claim['goal']) or cid != claim['claim_id']:
                raise ValueError('Claim identity changed')
        for cid, ids in self.data['fact_bindings'].items():
            if len(ids) != len(set(ids)):
                raise ValueError('duplicate Fact binding')
            for fid in ids:
                if normalize(self._stored(fid).statement) != self.claim(cid)['statement']:
                    raise ValueError('Fact binding mismatch')
                if self._active(fid):
                    self._accepted(fid)
        for cid, fid in self.data['refutations'].items():
            if normalize(self._stored(fid).statement) != self.refutation_statement(cid):
                raise ValueError('Refutation binding mismatch')
            if self._active(fid) and self.facts_for(cid):
                raise ValueError('contradictory truth bindings')
        for sid, row in self.data['supports'].items():
            values = {k: v for k, v in row.items() if k != 'support_id'}
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
                        helpers = self.data['fact_bindings'].get(deferred['helper_claim_id'], [])
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
