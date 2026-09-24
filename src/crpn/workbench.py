"""Local research access over existing stores and durable invocation evidence.

No permission database: premises are reconstructed from the frozen Worker packet
and completed capability responses, then checked against the live CRPN graph.
"""
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from danus.core import LocalMemory, GlobalMemory
from danus.core._util import read_jsonl
from danus.core.durable_io import read_json
from .model import Network, normalize
from .materials import checked_size


def packet_for(request_path):
    request = read_json(request_path)
    return request, json.loads(request['prompt'].split('\nLOCAL INPUT:\n', 1)[1])


def memory_id(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def page_text(text, start=0, length=8000):
    if type(start) is not int or start < 0 or type(length) is not int or not 1 <= length <= 8000:
        raise ValueError('invalid text range')
    if start > len(text):
        raise ValueError('range starts beyond text')
    end = min(len(text), start + length)
    return {'text': text[start:end], 'start': start, 'end': end, 'total_chars': len(text),
            'next_start': end if end < len(text) else None,
            'first_line': text[:start].count('\n') + 1,
            'last_line': text[:end].count('\n') + 1,
            'sha256': sha256(text.encode()).hexdigest()}


def authorized_predecessors(network, request_path, requested):
    request, packet = packet_for(request_path)
    if request['role'] != 'worker' or 'study' not in packet or 'claim' not in packet:
        raise ValueError('ordinary Worker authority required')
    delivered = {f['fact_id'] for f in packet['accepted_facts']}
    for event in read_jsonl(Path(request_path).with_name('capabilities.jsonl')):
        if event.get('phase') != 'response' or event.get('name') not in ('premise_request', 'candidate_submit'):
            continue
        response = event.get('result', {})
        premise = response.get('premise')
        if response.get('accepted') is True and isinstance(premise, dict):
            delivered.add(premise['fact_id'])
    requested = sorted(set(requested))
    if not set(requested) <= delivered:
        raise ValueError('predecessor was not delivered as a CRPN-authorized premise in this call')
    for fid in requested:
        network.visible_fact(fid, packet['claim']['context'])
    return requested


def submit_candidate(network, runtime, request_path, candidate, *, gate=None):
    from .admission import Admission
    from .verification import VerifierBackend
    request, packet = packet_for(request_path)
    if request['role'] != 'worker' or 'study' not in packet:
        raise ValueError('candidate submission requires an ordinary Study service')
    if normalize(candidate['context']) != packet['claim']['context']:
        raise ValueError('Worker candidate must retain current ambient scope')
    allowed = authorized_predecessors(network, request_path, candidate['predecessors'])
    # Content identity coalesces repeated tool requests within a service.
    # A revised or genuinely alternative proof is a different candidate.
    key = request['key'] + ':candidate:' + memory_id(candidate)
    directory = network.root / 'submissions' / sha256(key.encode()).hexdigest()
    frozen = directory / 'request.json'
    if frozen.exists():
        old = read_json(frozen)
        prepared = {k: old[k] for k in ('statement', 'proof', 'predecessors')}
        descriptor = old['binding']
    elif packet.get('compose'):
        prepared, descriptor = network.prepare_compose(packet['compose']['support']['support_id'], candidate)
    else:
        prepared, descriptor = network.prepare_candidate(candidate, allowed)
    return (gate or Admission(VerifierBackend(runtime))).submit(network, key,
        prepared=prepared, descriptor=descriptor, author=packet['study']['study_id'],
        purpose='local ' + descriptor['kind'])


def recover_submissions(network, runtime, request_path):
    """Settle only already reserved tool admissions from this call's evidence.

    DurableRounds decides whether the verifier was confirmed or interrupted. No
    unrecorded request is invented and no unconfirmed model call is retried.
    """
    request, _ = packet_for(request_path)
    recovered = []
    seen = set()
    for event in read_jsonl(Path(request_path).with_name('capabilities.jsonl')):
        if event.get('phase') != 'request' or event.get('name') != 'candidate_submit':
            continue
        candidate = event['arguments']['candidate']
        key = request['key'] + ':candidate:' + memory_id(candidate)
        if key in seen:
            continue
        seen.add(key)
        directory = network.root / 'submissions' / sha256(key.encode()).hexdigest()
        if not (directory / 'request.json').exists():
            continue
        if (directory / 'result.json').exists():
            result = read_json(directory / 'result.json')
        else:
            result = submit_candidate(network, runtime, request_path, candidate)
        fid = result.get('fact_id')
        current = Network(network.root)
        valid = bool(fid and fid in current.proof_ids())
        recovered.append({'submission': directory.name, 'verdict': result['verdict'],
                          'accepted': valid, 'fact_id': fid if valid else None,
                          'admission': result.get('admission') if valid else None,
                          'feedback': {k: v for k, v in result.get('verification', {}).items()
                                       if k in ('verdict', 'reason')}})
    network.refresh()
    return recovered


def examined_evidence_ids(request_path):
    """IDs actually delivered for inspection in this Worker call, not permissions."""
    ids = set()
    for event in read_jsonl(Path(request_path).with_name('capabilities.jsonl')):
        if event.get('phase') != 'response' or event.get('name') not in (
                'fact_inspect', 'proof_read', 'premise_request', 'support_read'):
            continue
        result = event.get('result', {})
        if not isinstance(result, dict) or result.get('accepted') is False:
            continue
        premise = result.get('premise')
        fid = result.get('fact_id') or (premise.get('fact_id') if isinstance(premise, dict) else None)
        if isinstance(fid, str):
            ids.add(fid)
        if event.get('name') == 'support_read':
            certificate = result.get('certificate_fact_id')
            if isinstance(certificate, str):
                ids.add(certificate)
    return sorted(ids)


def tools(network, wl, role, *, runtime=None, request_path=None):
    from danus.execution.isolation import CapabilityTool
    from .contracts import obj, STR, CANDIDATE
    root = network.root
    request, packet = packet_for(request_path) if request_path else ({}, {})
    if request and (request['role'] != role or not Path(request_path).resolve().is_relative_to(wl.dir.resolve() / 'rounds')):
        raise ValueError('capability binding differs from durable invocation')
    if role == 'worker' and 'study' in packet and packet['study']['study_id'] != wl.name:
        raise ValueError('Worker capability bound to a different Study')
    read_names = {'proof_read', 'support_read', 'fact_search', 'fact_inspect', 'gm_search', 'gm_read',
                  'study_research', 'local_search', 'local_record', 'local_read', 'premise_request'}
    journal = Path(request_path).with_name('capabilities.jsonl') if request_path else None
    delivered_bytes = sum(len(json.dumps(event.get('result'), ensure_ascii=False).encode())
                          for event in read_jsonl(journal) if event.get('phase') == 'response'
                          and event.get('name') in read_names) if journal else 0
    read_lock = Lock()
    def current():
        return Network(root)
    def tool(name, description, schema, callback, waits=False):
        def call(arguments):
            # Only mathematical validation messages are returned. Unhandled IO or
            # runtime faults stay exceptions and are redacted by the broker.
            try:
                if name in read_names:
                    with read_lock:
                        nonlocal delivered_bytes
                        if delivered_bytes >= 256000:
                            return {'accepted': False, 'error': 'ATTENTION_BUDGET_EXHAUSTED',
                                    'reason': 'Continue this bounded local read in a later Study service.'}
                        response = checked_size(callback(**arguments), 64000)
                        size = len(json.dumps(response, ensure_ascii=False).encode())
                        if delivered_bytes + size > 256000:
                            return {'accepted': False, 'error': 'ATTENTION_BUDGET_EXHAUSTED',
                                    'reason': 'This read would exceed the current session material budget.'}
                        delivered_bytes += size
                        return response
                return checked_size(callback(**arguments), 64000)
            except (ValueError, KeyError) as error:
                return {'accepted': False, 'error': 'INVALID_REQUEST', 'reason': str(error)}
        return CapabilityTool(name, description, schema, call, waits_for_model=waits)
    offset = {'type': 'integer', 'minimum': 0}
    length = {'type': 'integer', 'minimum': 1, 'maximum': 8000}
    page = {'type': 'integer', 'minimum': 0, 'maximum': 10000}
    proof_schema = obj({'fact_id': STR, 'start': offset, 'length': length})
    def proof_read(fact_id, start=0, length=8000):
        n = current()
        if role == 'verifier' and fact_id not in {f['fact_id'] for f in packet.get('accepted_predecessors', [])}:
            raise ValueError('Verifier may read only its explicitly declared predecessors')
        interface = n.inspect_fact(fact_id)
        fact = n._accepted(fact_id)
        return {'authority': 'AUTHORIZED_PREDECESSOR_TEXT' if role == 'verifier' else 'INSPECTION_ONLY',
                **interface, 'predecessors': fact.predecessors,
                'definitions': getattr(fact, 'glossary_introduces', {}),
                'source': {'problem_id': fact.problem_id, 'author': fact.author,
                           'provenance': getattr(fact, 'provenance', {})},
                'proof': page_text(fact.proof, start, length),
                'notice': 'Internal assertions are not separate accepted Facts. All source conditions remain in force.'}
    proof_tool = tool('proof_read', 'Read a precise character range of an accepted proof, with complete source interface and conditions. Start at 0; follow next_start. Reading grants no new premises.', proof_schema, proof_read)
    if role == 'verifier':
        return [proof_tool] if request_path else []
    if role not in ('worker', 'selector'):
        return []
    def support_read(support_id, page=0):
        cut = packet.get('local_cut') or packet.get('cut') or {}
        if support_id not in {r['support_id'] for r in cut.get('routes', [])}:
            raise ValueError('Support is outside the current local cut')
        n = current()
        row = n.data['supports'][support_id]
        requirements = row['requirement_claim_ids']
        if page * 8 > len(requirements):
            raise ValueError('Support requirement page is out of range')
        return {'authority': 'INSPECTION_ONLY', 'support_id': support_id,
                'conclusion': n.claim(row['conclusion_claim_id']),
                'certificate_fact_id': row['bridge_fact_id'] if n._active(row['bridge_fact_id']) else None,
                'requirements': [{**n.claim(cid), 'truth': n.truth(cid)}
                                 for cid in requirements[page * 8:(page + 1) * 8]],
                'page': page, 'total_requirements': len(requirements),
                'next_page': page + 1 if (page + 1) * 8 < len(requirements) else None,
                'notice': 'All conditions remain required; this page grants no premise.'}
    def fact_search(query, page=0):
        hits = current().search(query, 8 * (page + 1))[8 * page:8 * (page + 1)]
        return [{'fact_id': h['fact_id'], 'score': h['score'], 'statement_excerpt': h['statement'][:1200],
                 'interface_complete': len(h['statement']) <= 1200} for h in hits]
    def fact_inspect(fact_id):
        return {'authority': 'INSPECTION_ONLY', **current().inspect_fact(fact_id)}
    def memory_search(query, page=0):
        result = GlobalMemory(root).search(query, limit_per_kind=4 * (page + 1))
        return {'authority': 'UNVERIFIED_RESEARCH', 'query': query, 'results': [
            {'kind': kind, 'id': h['entry']['id'], 'score': h['score'],
             'excerpt': json.dumps(h['entry'], ensure_ascii=False)[:800]}
            for kind, row in result['results_by_kind'].items()
            for h in row['results'][4 * page:4 * (page + 1)]]}
    def gm_read(kind, record_id, start=0, length=8000):
        from danus.core.schema import GLOBAL_KINDS
        if kind not in GLOBAL_KINDS:
            raise ValueError('unknown research channel')
        entry = next((r for r in GlobalMemory(root).read(kind) if r.get('id') == record_id), None)
        if entry is None:
            raise ValueError('unknown research record')
        return {'authority': 'UNVERIFIED_RESEARCH', 'kind': kind, 'record_id': record_id,
                'record': page_text(json.dumps(entry, ensure_ascii=False, sort_keys=True), start, length)}
    result = [tool('fact_search', 'Search existing accepted results; discover IDs without premise authority.', obj({'query': STR, 'page': page}), fact_search),
              tool('fact_inspect', 'Read the complete accepted statement and scope, without authorizing its use.', obj({'fact_id': STR}), fact_inspect), proof_tool,
              tool('gm_search', 'Search bounded shared research; awareness is unverified.', obj({'query': STR, 'page': page}), memory_search),
              tool('gm_read', 'Read an exact shared research record by returned kind and ID, in character ranges.', obj({'kind': STR, 'record_id': STR, 'start': offset, 'length': length}), gm_read)]
    cut = packet.get('local_cut') or packet.get('cut') or {}
    if any(row.get('interface_page_required') for row in cut.get('routes', [])):
        result.append(tool('support_read', 'Read exact requirements of a broad Support in this cut, eight per page. Inspection only; every condition remains required.', obj({'support_id': STR, 'page': page}), support_read))
    if role == 'selector':
        from substrate.store import lane
        def study_research(study_id, page=0):
            if study_id not in current().data['studies']:
                raise ValueError('unknown Study')
            records = LocalMemory(lane(root, study_id)).read('notes')
            return {'authority': 'UNVERIFIED_RESEARCH', 'records': records[page * 2:(page + 1) * 2]}
        return result + [tool('study_research', 'Page complete Study research; no truth authority.', obj({'study_id': STR, 'page': page}), study_research)]
    local = LocalMemory(wl.dir)
    def local_search(query, page=0):
        found = local.search(query, limit_per_channel=4 * (page + 1))
        return {'authority': 'UNVERIFIED_RESEARCH', 'results': [
            {'channel': channel, 'record_id': memory_id(h['item']), 'score': h['score'],
             'excerpt': json.dumps(h['item'], ensure_ascii=False)[:800]}
            for channel, row in found['results_by_channel'].items()
            for h in row['results'][page * 4:(page + 1) * 4]]}
    def local_record(channel, record_id, start=0, length=8000):
        if channel not in ('notes', 'events'):
            raise ValueError('unknown local channel')
        entry = next((r for r in local.read(channel) if memory_id(r) == record_id), None)
        if entry is None:
            raise ValueError('unknown local record in this Study')
        return {'authority': 'UNVERIFIED_RESEARCH', 'channel': channel, 'record_id': record_id,
                'record': page_text(json.dumps(entry, ensure_ascii=False, sort_keys=True), start, length)}
    def local_read(page=0):
        return {'authority': 'UNVERIFIED_RESEARCH', 'records': local.read('notes')[page * 4:(page + 1) * 4]}
    def local_append(note):
        row = local.append('notes', {'content': note, 'authority': 'UNVERIFIED_RESEARCH',
                                     'source_service': request.get('key', 'UNKNOWN')})
        return {'status': 'ok', 'record_id': memory_id(row['entry']), 'channel': 'notes'}
    def gm_add(kind, claim, evidence):
        if kind not in ('conclusion', 'example', 'counterexample', 'proof_attempt', 'plan', 'dead_end', 'direction', 'obstacle'):
            raise ValueError('worker research channel not allowed')
        return {'id': GlobalMemory(root).append(kind, claim, evidence, wl.name)}
    result += [tool('local_search', 'Search your own Study history using existing LocalMemory BM25. Returns exact record IDs.', obj({'query': STR, 'page': page}), local_search),
               tool('local_record', 'Read an exact record from your own Study history, in character ranges.', obj({'channel': STR, 'record_id': STR, 'start': offset, 'length': length}), local_record),
               tool('local_read', 'Page your lane research in chronological order.', obj({'page': page}), local_read),
               tool('local_append', 'Persist unfinished research immediately; never a Fact.', obj({'note': STR}), local_append),
               tool('gm_add', 'Share unverified findings or obstacles.', obj({'kind': STR, 'claim': STR, 'evidence': STR}), gm_add)]
    if runtime is not None and request_path and 'study' in packet:
        def premise_request(fact_id):
            n = current()
            fact = n.visible_fact(fact_id, packet['claim']['context'])
            return {'accepted': True, 'premise': {**n.inspect_fact(fact_id), 'statement': fact.statement},
                    'authority': 'CRPN_ACCEPTED_PREMISE'}
        def candidate_submit(candidate):
            n = current()
            response = submit_candidate(n, runtime, request_path, candidate)
            return {'accepted': response['accepted'], 'verdict': response['verdict'],
                    'feedback': {k: v for k, v in response['verification'].items() if k != 'evidence'},
                    'admission': response['admission'],
                    'premise': n.inspect_fact(response['fact_id']) if response['accepted'] else None}
        result += [tool('premise_request', 'Request an existing result as an actual premise for this session. Checks current scope and valid closure. Foreign scope requires the existing Selector bridge; inspection alone is not authorization.', obj({'fact_id': STR}), premise_request),
                   tool('candidate_submit', 'Submit a complete local Fact, conditional Support or refutation through CRPN and a fresh independent Verifier. Returns feedback or an accepted evidence ID; you may continue within the same task. Identical requests reuse the verdict.', obj({'candidate': CANDIDATE}), candidate_submit, waits=True)]
    return result
