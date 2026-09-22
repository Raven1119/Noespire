"""Lossless explicit import into the CRPN authority; old stores are read-only evidence."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from danus.core.durable_io import atomic_json, atomic_text, immutable_json, read_json, locked
from danus.core.local_memory import LocalMemory
from danus.core.global_memory import GlobalMemory
from substrate.store import lane, append_once
from .model import Network, make_claim, normalize, identity, proof_identity


def source_hashes(root):
    root = Path(root).resolve()
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError('migration source may not redirect through symlinks')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha256(path.read_bytes()).hexdigest()
    return result


def _source(root, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError('invalid source reference')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or path == root:
        raise ValueError('source reference escapes frozen workspace')
    return path


def _legacy_fact(path):
    raw = path.read_text(encoding='utf-8')
    metadata, body = raw.removeprefix('---\n').split('\n---\n# Statement\n\n', 1)
    statement, proof = body.split('\n\n# Proof\n\n', 1)
    row = json.loads(metadata)
    values = {'problem_id': normalize(row['problem_id']), 'statement': normalize(statement),
              'proof': normalize(proof), 'predecessors': sorted(set(row['predecessors']))}
    old_id = sha256(json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
    if old_id != row['fact_id'] or old_id != path.stem:
        raise ValueError('legacy Fact content hash mismatch')
    return {**row, **values, 'statement': statement, 'proof': proof.rstrip('\n'), 'id_scheme': 'crpn-legacy'}


def _topological(facts):
    ordered, visiting, seen = [], set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError('legacy Fact dependency cycle')
        if key in seen:
            return
        if key not in facts:
            raise ValueError('legacy Fact closure is incomplete')
        visiting.add(key)
        for pred in facts[key]['predecessors']:
            visit(pred)
        visiting.remove(key)
        seen.add(key)
        ordered.append(key)
    for key in sorted(facts):
        visit(key)
    return ordered


def _legacy_data(root):
    graph = read_json(root/'proof_graph.json')
    run = read_json(root/'continuous_run/state.json')
    if graph.get('schema_version') != 'crpn-1':
        raise ValueError('only explicit legacy CRPN states can migrate')
    claims = {}
    for key, row in graph['obligations'].items():
        claim = make_claim(graph['problem_id'],row['context'],row['goal'])
        if key != claim['claim_id'] or row['obligation_id'] != key or row['problem_id'] != claim['problem_id']:
            raise ValueError('legacy Claim identity mismatch')
        claims[key] = claim
    facts, revoked = {}, set()
    for folder in ('facts', '_revoked'):
        for path in sorted((root/folder).glob('*.md')):
            row = _legacy_fact(path)
            if row['problem_id'] != graph['problem_id']:
                raise ValueError('cross-problem legacy Fact')
            if row['fact_id'] in facts and facts[row['fact_id']] != row:
                raise ValueError('conflicting legacy Fact copies')
            facts[row['fact_id']] = row
            if folder == '_revoked':
                revoked.add(row['fact_id'])
    ordered = _topological(facts)
    invalidated = set(revoked)
    for key in ordered:
        if invalidated.intersection(facts[key]['predecessors']):
            invalidated.add(key)
    return graph, run, claims, facts, ordered, revoked, invalidated


def _copy_evidence(source, dest, relative):
    path = _source(source,relative)
    content = path.read_bytes()
    digest = sha256(content).hexdigest()
    target = dest/'migration'/'source_blobs'/(digest+'.bin')
    if target.exists():
        if target.read_bytes() != content:
            raise ValueError('migration source blob changed')
    else:
        target.parent.mkdir(parents=True,exist_ok=True)
        # Complete local bytes, written before the immutable archive index.
        temporary = target.with_suffix('.tmp')
        temporary.write_bytes(content)
        temporary.replace(target)
    return {'source_ref':relative,'sha256':digest,'archive':target.relative_to(dest).as_posix()}


def _import_notes(source, dest, run, studies, hashes):
    """Notes are DANUS memory, not replayable legacy permissions or truth."""
    archive, counts = [], {'local_records':0,'shared_records':0}
    global_memory = GlobalMemory(dest)
    existing_shared = {r.get('migration_source_key') for r in global_memory.read('direction')}
    definitions = []
    for path in sorted((source/'continuous_run/objects').glob('*.json')):
        ref = path.relative_to(source).as_posix()
        definitions.append({'source_ref':ref,'source_sha256':hashes[ref],'content':read_json(path)})
        archive.append(_copy_evidence(source,dest,ref))
    for sid, study in studies.items():
        memory = LocalMemory(lane(dest,sid))
        entries = []
        for path in sorted((source/'continuous_run/studies'/sid).glob('*.json')):
            row = read_json(path)
            if row.get('study_id') != sid:
                raise ValueError('legacy Study record ownership mismatch')
            entries.append((int(row.get('visit',-1)),0,path,{'kind':'LEGACY_STUDY_RESEARCH',
                'continuation':row.get('continuation',''),'next_work':row.get('next_work',''),
                'focus':row.get('focus',''),'scope':row.get('scope',''),
                'revision':row.get('revision'),'source_record':row}))
        for kind in ('research_artifacts','research_deliveries'):
            for path in sorted((source/'continuous_run'/kind/sid).glob('*.json')):
                row = read_json(path)
                if row.get('study_id') != sid or row.get('verified') is not False:
                    raise ValueError('legacy public artifact ownership/authority mismatch')
                call_id = row.get('invocation_id',row.get('call_id'))
                result = source/'continuous_run/calls'/str(call_id)/'result.json'
                status = read_json(result).get('status') if result.exists() else 'UNCONFIRMED'
                entries.append((int(row.get('source_visit',-1)),2 if kind=='research_deliveries' else 1,path,
                    {'kind':row.get('kind','UNVERIFIED_RESEARCH_DELIVERY'),'source_status':status,
                     'source_invocation':call_id,'source_message_id':row.get('message_id'),'source_record':row,
                     'content':row.get('content',row.get('text',''))}))
        for _,_,path,record in sorted(entries,key=lambda e:(e[0],e[1],str(e[2]))):
            ref = path.relative_to(source).as_posix()
            source_key = 'migration:'+hashes[ref]+':'+ref
            append_once(memory,'notes',source_key,{'authority':'UNVERIFIED_RESEARCH','source_run':run['run_id'],
                'source_ref':ref,'source_sha256':hashes[ref],**record})
            archive.append(_copy_evidence(source,dest,ref))
            counts['local_records'] += 1
        # Definitions are research material. References in them grant no access.
        refs = set(study.get('object_refs',[]))
        for record in definitions:
            if 'object:'+Path(record['source_ref']).stem in refs:
                append_once(memory,'notes','migration-definition:'+record['source_sha256'],
                            {'authority':'UNVERIFIED_RESEARCH','kind':'LEGACY_OBJECT_DEFINITION',**record})
                counts['local_records'] += 1
        current = read_json(_source(source,'continuous_run/'+run['studies'][sid]))
        key = 'migration-current:'+sid+':'+hashes['continuous_run/'+run['studies'][sid]]
        if key not in existing_shared:
            global_memory.append('direction', current.get('focus','Research focus'),
                json.dumps({'continuation':current.get('continuation',''),'next_work':current.get('next_work',''),
                            'scope':current.get('scope','')},ensure_ascii=False), 'legacy-import',verifiable=False,
                links={'study_id':sid,'source_run':run['run_id']},migration_source_key=key,
                authority='UNVERIFIED_RESEARCH')
        counts['shared_records'] += 1
    return archive, counts


def _current_data(source):
    # Historical decoder only: never construct a DANUS FactGraph or write its files.
    from danus.core.factgraph import parse_fact
    data = read_json(source / 'crpn.json')
    if data['schema_version'] != 'crpn-danus-1':
        raise ValueError('unsupported source schema')
    if data.get('control', {}).get('pending'):
        raise ValueError('pause and settle the source admission before migration')
    records, revoked = {}, set()
    for folder in ('facts', '_revoked'):
        for path in sorted((source / 'fact_graph' / folder).glob('*.md')):
            record = vars(parse_fact(path.read_text(encoding='utf-8'), path.stem))
            if path.stem in records and records[path.stem] != record:
                raise ValueError('conflicting source evidence')
            records[path.stem] = record
            if folder == '_revoked':
                revoked.add(path.stem)
    for path in (source / 'fact_graph/revocations').glob('*.json'):
        revoked.update(read_json(path)['fact_ids'])
    if not revoked <= records.keys():
        raise ValueError('missing historical revocation evidence')
    return data, records, revoked


def _legacy_state(source, new_run):
    graph, run, claims, facts, ordered, revoked, invalidated = _legacy_data(source)
    data = {'schema_version': 'crpn-danus-1', 'problem_id': graph['problem_id'],
            'target_claim_id': graph['target_obligation_id'], 'claims': claims,
            'fact_bindings': deepcopy(graph['fact_bindings']), 'supports': deepcopy(graph['supports']),
            'studies': {}, 'refutations': {}, 'representations': {}, 'deferred_representations': {},
            'pending_recurrence': [], 'schedule': deepcopy(run['schedule']),
            'control': {'run_id': new_run, 'visit': run['step'], 'pending': None}}
    for sid, row in data['supports'].items():
        if identity('support-', {k:v for k,v in row.items() if k != 'support_id'}) != sid:
            raise ValueError('legacy Support identity mismatch')
    for table in ('representations', 'deferred_representations'):
        for sid, row in graph.get(table, {}).items():
            evidence = _source(source, row['evidence_ref'])
            if not evidence.is_dir():
                raise ValueError('legacy representation evidence missing')
            converted = {k:deepcopy(v) for k,v in row.items() if k != 'evidence_ref'}
            if table == 'deferred_representations':
                converted['released'] = (evidence / 'activation/result.json').exists() and sid not in graph.get('representations', {})
            data[table][sid] = converted
    for sid, ref in run['studies'].items():
        row = read_json(_source(source, 'continuous_run/' + ref))
        if row['study_id'] != sid:
            raise ValueError('legacy current Study binding mismatch')
        keep = ('study_id', 'claim_id', 'scope', 'focus', 'revision', 'region_ref', 'object_refs')
        study = {key:deepcopy(row[key]) for key in keep if key in row}
        study.setdefault('claim_id', None)
        study['last_served_visit'] = run['schedule'].get('last_served', {}).get(sid, -1)
        data['studies'][sid] = study
    refutation_map = {}
    for cid, rid in graph.get('refutations', {}).items():
        row = read_json(_source(source, 'refutations/' + rid + '.json'))
        values = {k:v for k,v in row.items() if k != 'refutation_id'}
        checks = ('accepted', 'assumptions_satisfied', 'conclusion_falsified', 'closed_book_clean')
        if (identity('ref-', values) != rid or row['obligation_id'] != cid
                or row['context'] != claims[cid]['context'] or row['goal'] != claims[cid]['goal']
                or not all(row['verification_evidence'].get(k) is True for k in checks)
                or not row['provenance'].get('verifier_call')):
            raise ValueError('legacy Refutation evidence mismatch')
        record = {'problem_id': graph['problem_id'], 'author': 'legacy-refutation',
                  'statement': 'The following proposition is false: ' + json.dumps(claims[cid]['statement'], ensure_ascii=False) + '.',
                  'proof': row['counterexample'], 'predecessors': [], 'provenance': row}
        fid = proof_identity(record)
        record['fact_id'] = fid
        facts[fid] = record
        data['refutations'][cid] = fid
        refutation_map[rid] = fid
    return data, facts, revoked, run, refutation_map


def _own_evidence(data, records):
    """Move each proof into its proposition or conditional Support, not a parallel DAG."""
    def attach(table, owner, slot, fid):
        if fid not in records:
            raise ValueError('missing owned evidence')
        target = data[table][owner].setdefault(slot, {})
        if fid in owned and fid not in target:
            # A shared representation certificate is stored once; relations may cite it.
            if table == 'supports' and owned[fid][0] == 'supports':
                return
            raise ValueError('ambiguous historical proof owner')
        target[fid] = records[fid]
        owned[fid] = (table, owner, slot)
    owned = {}
    for cid, ids in data.pop('fact_bindings').items():
        for fid in ids:
            attach('claims', cid, 'proofs', fid)
    for cid, fid in data.pop('refutations').items():
        attach('claims', cid, 'refutations', fid)
    for sid, row in data['supports'].items():
        attach('supports', sid, 'certificates', row['bridge_fact_id'])
    for table, field in (('representations', 'equivalence_fact_id'), ('deferred_representations', 'conditional_fact_id')):
        for sid, row in data[table].items():
            attach('supports', sid, 'certificates', row[field])
    if owned.keys() != records.keys():
        raise ValueError('historical evidence lacks an explicit mathematical owner')


def migrate(source, destination, *, on_event=None):
    source, dest = Path(source).resolve(), Path(destination).resolve()
    if source == dest or dest.is_relative_to(source) or source.is_relative_to(dest):
        raise ValueError('migration requires a separate destination, never the frozen source')
    plan_path = dest / 'migration/plan.json'
    if dest.exists() and any(dest.iterdir()) and not plan_path.exists():
        raise ValueError('destination must be empty or this same incomplete import')
    hashes = source_hashes(source)
    origin = {'source': str(source), 'source_hashes': hashes,
              'policy': 'Read-only historical evidence; one CRPN authority; fresh runtime.'}
    if plan_path.exists():
        plan = read_json(plan_path)
        if plan['origin'] != origin:
            raise ValueError('frozen import source changed')
    else:
        plan = {'origin': origin, 'new_run_id': uuid4().hex}
        immutable_json(plan_path, plan)
    with locked(dest / 'migration/import.lock'):
        if (dest / 'migration/result.json').exists():
            Network(dest)
            return read_json(dest / 'migration/result.json')
        emit = on_event or (lambda *_args, **_kwargs: None)
        legacy = not (source / 'crpn.json').exists()
        if legacy:
            data, records, revoked, run, refutation_map = _legacy_state(source, plan['new_run_id'])
            source_run = run['run_id']
        else:
            data, records, revoked = _current_data(source)
            source_run, refutation_map = data.get('control', {}).get('run_id'), {}
        ordered = _topological(records)
        invalid = set(revoked)
        for fid in ordered:
            if invalid.intersection(records[fid]['predecessors']):
                invalid.add(fid)
        # Archive ALL source bytes, including acceptance/revocation receipts and raw rounds.
        archive = [_copy_evidence(source, dest, ref) for ref in hashes]
        immutable_json(dest / 'migration/source_archive.json', archive)
        for fid in ordered:
            record = records[fid]
            record.setdefault('id_scheme', 'content-v1')
            record['status'] = 'revoked' if fid in invalid else 'accepted'
            record['history'] = [{'event': 'accepted', 'source_run': source_run,
                                  'evidence_archive': 'migration/source_archive.json'}]
            if fid in invalid:
                record['history'].append({'event': 'revoked', 'source_run': source_run,
                    'reason': 'historical revocation' if fid in revoked else 'revoked predecessor',
                    'evidence_archive': 'migration/source_archive.json'})
            record.setdefault('provenance', {})['migration'] = 'migration/plan.json'
            emit('fact_imported', old_id=fid, new_id=fid, revoked=fid in invalid)
        _own_evidence(data, records)
        data['schema_version'] = 'crpn-authority-2'
        data['control'] = {'run_id': plan['new_run_id'], 'visit': data.get('control', {}).get('visit', 0), 'pending': None}
        data['origin'] = {'source_run': source_run, 'source_workspace': str(source), 'migration': 'migration/plan.json'}
        if legacy:
            _, memory_counts = _import_notes(source, dest, run, data['studies'], hashes)
        else:
            memory_counts = {'local_records': 0, 'shared_records': 0}
            for relative in hashes:
                path = Path(relative)
                if path.parts[0] == 'global_memory' or (path.parts[0] == 'workers' and 'local_memory' in path.parts):
                    target = dest / path
                    content = (source / path).read_bytes()
                    if target.exists() and target.read_bytes() != content:
                        raise ValueError('partial memory import changed')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    if path.suffix == '.jsonl':
                        memory_counts['shared_records' if path.parts[0] == 'global_memory' else 'local_records'] += len(content.splitlines())
        if (source / 'revocation_log.jsonl').exists():
            (dest / 'migration/legacy_revocation_log.jsonl').write_bytes((source / 'revocation_log.jsonl').read_bytes())
        fact_map = {fid: fid for fid in records}
        support_map = {sid: sid for sid in data['supports']}
        for name, mapping in (('fact', fact_map), ('support', support_map), ('refutation', refutation_map)):
            immutable_json(dest / ('migration/' + name + '_id_map.json'), mapping)
        network = Network.__new__(Network)
        network.root, network.path, network.data = dest, dest / 'crpn.json', data
        network.problem_id, network.target_id = data['problem_id'], data['target_claim_id']
        network.validate()
        emit('before_state_commit')
        if network.path.exists() and read_json(network.path) != data:
            raise ValueError('partial import state changed')
        if source_hashes(source) != hashes:
            raise ValueError('source changed during migration')
        atomic_json(network.path, data)
        report = {'source': str(source), 'destination': str(dest), 'source_run': source_run,
                  'run_id': plan['new_run_id'], 'old_runtime_resumed': False, 'model_calls': 0,
                  'fact_id_map': fact_map, 'support_id_map': support_map, 'refutation_id_map': refutation_map,
                  'active_facts': len(network.proof_ids()), 'revoked_facts': len(network.revoked_ids()),
                  'source_revoked': sorted(revoked), 'dependency_invalidated': sorted(invalid - revoked),
                  'claims': len(data['claims']), 'supports': len(data['supports']), 'studies': len(data['studies']),
                  'active_representations': sum(bool(network.alias_of(r['claim_id'])) for r in data['representations'].values()),
                  'deferred_records': len(data['deferred_representations']), 'effective_depth': network.effective_depth(),
                  'target_truth': network.truth(network.target_id), 'schedule_preserved': True,
                  'source_hashes_unchanged': True, 'source_file_count': len(hashes), **memory_counts,
                  'truth': {cid:network.truth(cid) for cid in data['claims']},
                  'limitations': ['Historical LLM acceptance retained; migration is not new verification.']}
        immutable_json(dest / 'migration/result.json', report)
        emit('migration_completed')
        return report
