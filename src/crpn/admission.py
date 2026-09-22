"""CRPN's sole verified submission entry. Receipts are evidence, not truth.

DANUS retains the invocation lifecycle and generic durable IO. Publication of a
proof, its owner, and resulting AND/OR relations is one CRPN graph transaction.
"""
from copy import copy, deepcopy
from hashlib import sha256
import json
from danus.core.durable_io import immutable_json, read_json, locked
from danus.core.global_memory import GlobalMemory
from .model import make_claim, normalize, proof_identity


def _apply(network, descriptor, record):
    kind = descriptor['kind']
    if kind in ('FACT', 'SUPPORT', 'REFUTATION'):
        return network._admit_candidate(descriptor, record)
    if kind == 'BRIDGE':
        claim = make_claim(network.problem_id, descriptor['context'], descriptor['goal'])
        source = network.inspect_fact(descriptor['source_fact_id'])
        if record['statement'] != claim['statement'] or record['predecessors'] != [source['fact_id']]:
            raise ValueError('bridge changed exact interface or lineage')
        network.data['claims'].setdefault(claim['claim_id'], claim)
        network._attach('claims', claim['claim_id'], 'proofs', record)
        return {'kind': 'FACT', 'claim_id': claim['claim_id'], 'fact_id': record['fact_id']}
    sid, ancestor = descriptor['support_id'], descriptor.get('ancestor_claim_id')
    if kind == 'ACTIVATION':
        existing = network.data['representations'].get(sid)
        expected = (vars(network._accepted(existing['equivalence_fact_id'])) if existing
                    else network.activation_candidate(sid))
        if any(record[k] != expected[k] for k in ('statement', 'proof', 'predecessors')):
            raise ValueError('activation changed fixed derivation')
    elif kind == 'REPRESENTATION':
        relation = network._recurrence(sid, ancestor, descriptor['ancestor_path'])
        helper = descriptor.get('helper')
        if helper:
            helper = make_claim(network.problem_id, helper['context'], helper['goal'])
            network.data['claims'].setdefault(helper['claim_id'], helper)
            expected = network.conditional_equivalence_statement(ancestor, relation['claim_id'], helper['claim_id'])
        else:
            expected = network.equivalence_statement(ancestor, relation['claim_id'])
        if record['statement'] != expected or record['predecessors']:
            raise ValueError('representation changed exact interface')
    else:
        raise ValueError('unknown admission binding')
    network._attach('supports', sid, 'certificates', record)
    if kind == 'ACTIVATION':
        network.activate_alias(sid, record['fact_id'])
    elif helper:
        network.defer_alias(sid, ancestor, helper['claim_id'], record['fact_id'], descriptor['ancestor_path'])
    else:
        network.record_alias(sid, ancestor, record['fact_id'], descriptor['ancestor_path'])
    return {'kind': kind, 'support_id': sid, 'fact_id': record['fact_id']}


class Admission:
    def __init__(self, backend):
        self.backend = backend

    def submit(self, network, key, *, prepared, descriptor, author, purpose):
        identity = sha256(key.encode()).hexdigest()
        directory = network.root / 'submissions' / identity
        with locked(directory / '.lock'):
            request = {'problem_id': network.problem_id, 'author': author, **deepcopy(prepared),
                       'predecessors': sorted(set(prepared.get('predecessors', []))),
                       'glossary_introduces': {}, 'provenance': {'purpose': purpose},
                       'binding': deepcopy(descriptor)}
            if not isinstance(request['proof'], str) or not request['proof'].strip():
                raise ValueError('complete proof required')
            immutable_json(directory / 'request.json', request)
            network.refresh()
            prior = [{'fact_id': fid, 'statement': network._accepted(fid).statement}
                     for fid in request['predecessors']]
            record = {k: deepcopy(request[k]) for k in ('problem_id', 'author', 'statement', 'proof',
                                                       'predecessors', 'glossary_introduces')}
            record.update(fact_id=proof_identity(record), status='accepted', id_scheme='content-v1',
                          history=[{'event': 'accepted', 'submission': identity}],
                          provenance={'submission': identity, 'purpose': purpose})
            # Validate the complete mathematical binding before spending a verifier round.
            preview = copy(network)
            preview.data, preview._staging = deepcopy(network.data), True
            admission = _apply(preview, descriptor, record)
            preview.validate()
            verdict_path = directory / 'verification.json'
            if verdict_path.exists():
                verdict = read_json(verdict_path)
            else:
                verdict = self.backend.verify('submission-' + identity, request, prior)
                if not isinstance(verdict, dict) or verdict.get('verdict') not in (
                        'correct', 'wrong', 'inconclusive', 'timeout', 'interrupted', 'error'):
                    verdict = {'verdict': 'inconclusive', 'raw': verdict}
                immutable_json(verdict_path, verdict)
            accepted = verdict['verdict'] == 'correct'
            result = {'accepted': accepted, 'fact_id': record['fact_id'] if accepted else None,
                      'verdict': verdict['verdict'], 'verification': verdict, 'evidence': str(directory),
                      'admission': admission if accepted else None}
            receipt = directory / 'result.json'
            if receipt.exists():
                if read_json(receipt) != result:
                    raise ValueError('submission receipt binding corruption')
                if accepted:
                    network._accepted(record['fact_id'])
                return result
            if accepted:
                record['history'][0]['verification'] = deepcopy(verdict)
                # Never hold the graph/control lock while the independent model runs.
                # Re-read after verification: revocation or another accepted proof
                # may have changed the graph while the caller was waiting.
                with locked(network.root / '.crpn.lock'):
                    network.refresh()
                    with network._transaction():
                        _apply(network, descriptor, record)
            # Crash after graph commit resumes here without a second call or publication.
            immutable_json(receipt, result)
            try:
                GlobalMemory(network.root).append('verification', request['statement'], json.dumps(verdict),
                    author, verifiable=False, fact_id=result['fact_id'], verdict=verdict['verdict'],
                    links={'submission': identity, 'predecessors': request['predecessors']})
            except (ValueError, OSError):
                pass
            return result
