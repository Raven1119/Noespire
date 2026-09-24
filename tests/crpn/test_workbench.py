"""Full local research transactions through the actual broker and durable rounds.

Judgments here are fixtures, never evidence of mathematical verifier reliability.
"""
import json
from pathlib import Path
from urllib.request import Request, urlopen
import pytest
from crpn.model import Network
from crpn.engine import Research
from crpn.materials import capability_tools, worker_packet
from crpn.workbench import memory_id, examined_evidence_ids
from substrate.runtime import Runtime
from substrate.store import lane
from danus.core import LocalMemory
from danus.execution.capabilities import CapabilityBroker
from danus.core.durable_io import immutable_json
from test_engine import candidate, output, fixture_fact


def test_examined_evidence_uses_confirmed_inspection_responses_and_support_certificate(tmp_path):
    request = tmp_path / 'request.json'
    journal = tmp_path / 'capabilities.jsonl'
    rows = [
        {'phase': 'request', 'name': 'fact_inspect', 'arguments': {'fact_id': 'unconfirmed'}},
        {'phase': 'response', 'name': 'fact_inspect', 'result': {'fact_id': 'inspected'}},
        {'phase': 'response', 'name': 'support_read', 'result': {'certificate_fact_id': 'certificate',
                                                                'facts': None}},
        {'phase': 'response', 'name': 'premise_request', 'result': {'accepted': True,
                                                                  'premise': {'fact_id': 'authorized'}}},
        {'phase': 'response', 'name': 'proof_read', 'result': {'accepted': False, 'fact_id': 'denied'}}]
    journal.write_text(''.join(json.dumps(row) + '\n' for row in rows))
    assert examined_evidence_ids(request) == ['authorized', 'certificate', 'inspected']


class SessionActors:
    def __init__(self, root, worker):
        self.root, self.worker = root, worker
        self.calls = []
        self.runtime = Runtime(root, runner=self, fingerprint={'test': 'workbench'})
        self.verifier_checks = None

    def __call__(self, wl, role, prompt, log, timeout, **options):
        name = role['ROLE']
        packet = json.loads(prompt.split('\nLOCAL INPUT:\n', 1)[1])
        self.calls.append(name)
        tools = capability_tools(Network(self.root), wl, name, runtime=self.runtime,
                                 request_path=role['REQUEST_PATH'])
        immutable_json(log.parent / 'capabilities.json', {'role': name, 'tools': [t.name for t in tools]})
        with CapabilityBroker(tools, bind='127.0.0.1', evidence_path=log.parent / 'capabilities.jsonl') as broker:
            receipts = []
            def call(tool, **arguments):
                req = Request('http://127.0.0.1:%s/rpc' % broker.port,
                    data=json.dumps({'method': 'call', 'name': tool, 'arguments': arguments}).encode(),
                    headers={'Authorization': 'Bearer ' + broker.token, 'Content-Type': 'application/json'})
                with urlopen(req, timeout=15) as response:
                    body = json.load(response)
                result = body.get('result', body)
                if tool == 'candidate_submit' and result.get('accepted'):
                    receipts.append(result['premise']['fact_id'])
                return result
            if name == 'verifier':
                assert {t.name for t in tools} == {'proof_read'}
                assert 'research_context' not in packet
                if self.verifier_checks:
                    self.verifier_checks(call, packet)
                rejected = packet['candidate']['proof'] == 'Needs correction.'
                result = {'verdict': 'wrong' if rejected else 'correct',
                          'reason': 'Paragraph 2: missing applicability argument; prove its hypothesis.' if rejected else 'Complete fixture.'}
            elif name == 'worker':
                result = self.worker(call, packet, role)
                if isinstance(result, dict):
                    result.pop('candidate', None)
                    result['submission_receipts'] = receipts
            elif name == 'probe':
                result = {'ancestor_claim_id': None, 'mapping': '', 'reason': 'Distinct fixture.'}
            else:
                raise AssertionError(name)
        if result in ('TIMEOUT', 'INTERRUPTED'):
            log.write_text('unconfirmed work\n', encoding='utf8')
            if result == 'INTERRUPTED':
                raise KeyboardInterrupt()
            return 124
        options['output_path'].write_text(json.dumps(result), encoding='utf8')
        log.write_text(json.dumps({'type': 'turn.completed', 'usage': {
            'input_tokens': 20, 'cached_input_tokens': 0, 'output_tokens': 8}}) + '\n', encoding='utf8')
        return 0


@pytest.mark.parametrize('ending', ['COMPLETED', 'TIMEOUT', 'INTERRUPTED'])
def test_full_research_feedback_reuse_and_one_service_even_after_timeout(tmp_path, ending):
    net = Network.create(tmp_path, 'p', 'Target', 'x is real')
    from test_model import fact
    prior = fact(net, net.register_claim('Prior A', 'x is real')['claim_id'],
                 proof='Named proof section\n' + 'Written reasoning. ' * 5000)
    foreign = fixture_fact(net, 'Foreign', 'x is integer')
    study = 'study-' + net.target_id
    local = LocalMemory(lane(tmp_path, study))
    note = local.append('notes', {'content': 'Earlier crucial derivation ' + 'long text ' * 1700})['entry']
    own_id = memory_id(note)
    hidden = LocalMemory(lane(tmp_path, 'unrelated')).append('notes', {'content': 'PRIVATE unrelated record'})['entry']
    admitted = []
    def worker(call, packet, role):
        assert packet['accepted_facts'] == []
        hits = call('local_search', query='crucial derivation', page=0)['results']
        assert any(h['record_id'] == own_id for h in hits)
        first = call('local_record', channel='notes', record_id=own_id, start=0, length=8000)
        second = call('local_record', channel='notes', record_id=own_id, start=first['record']['next_start'], length=8000)
        assert first['record']['sha256'] == second['record']['sha256']
        assert call('local_record', channel='notes', record_id=memory_id(hidden), start=0, length=8000)['accepted'] is False
        hits = call('fact_search', query='Prior A', page=0)
        assert any(h['fact_id'] == prior for h in hits)
        proof = call('proof_read', fact_id=prior, start=0, length=8000)
        assert proof['scope'] == 'x is real' and proof['authority'] == 'INSPECTION_ONLY'
        further = call('proof_read', fact_id=prior, start=proof['proof']['next_start'], length=8000)
        assert further['proof']['start'] == 8000 and further['proof']['sha256'] == proof['proof']['sha256']
        proposed = candidate('New B', context='x is real', predecessors=[prior])
        assert call('candidate_submit', candidate=proposed)['accepted'] is False  # reading is not permission
        assert call('premise_request', fact_id=foreign)['accepted'] is False
        assert call('premise_request', fact_id=prior)['accepted'] is True
        bad = call('candidate_submit', candidate={**proposed, 'proof': 'Needs correction.'})
        assert bad['verdict'] == 'wrong' and 'Paragraph 2' in bad['feedback']['reason']
        good = call('candidate_submit', candidate=proposed)
        assert good['accepted'] is True
        assert good['task_residual']['authority'] == 'UNVERIFIED_RESEARCH_STATE'
        assert good['shared_evidence_core']['results'][0]['fact_id'] == good['premise']['fact_id']
        assert good['shared_evidence_core']['results'][0]['source'][0] == 'SAME_SESSION_ACCEPTED'
        assert good['task_residual']['evidence_core_ids'][0] == good['premise']['fact_id']
        assert good['task_residual']['coverage'] == 'UNDETERMINED'
        assert call('candidate_submit', candidate=proposed) == good
        admitted.append(good['premise']['fact_id'])
        next_candidate = candidate('New C', context='x is real', predecessors=admitted)
        second = call('candidate_submit', candidate=next_candidate)
        assert second['accepted'] is True
        admitted.append(second['premise']['fact_id'])
        call('local_append', note='Continuation after verifier feedback and accepted B then C.')
        return output(next_candidate) if ending == 'COMPLETED' else ending
    actor = SessionActors(tmp_path, worker)
    def verifier_checks(call, packet):
        assert call('proof_read', fact_id=foreign, start=0, length=8000)['accepted'] is False
        for row in packet['accepted_predecessors']:
            assert call('proof_read', fact_id=row['fact_id'], start=0, length=8000)['fact_id'] == row['fact_id']
    actor.verifier_checks = verifier_checks
    research = Research(tmp_path, actor.runtime)
    if ending == 'INTERRUPTED':
        with pytest.raises(KeyboardInterrupt): research.step()
        result = Research(tmp_path, actor.runtime).step()
    else:
        result = research.step()
    current = Network(tmp_path)
    assert actor.calls.count('worker') == 1 and actor.calls.count('verifier') == 3
    assert current.data['control']['visit'] == 1 and current.data['schedule']['channel_cursor'] == 1
    assert current.data['studies'][study]['revision'] == 1
    assert set(admitted) <= set(current.proof_ids())
    assert current._accepted(admitted[1]).predecessors == [admitted[0]]
    assert len(result['tool_submissions']) == 3
    assert len(list((tmp_path / 'submissions').glob('*/verification.json'))) == 5  # two fixtures plus three submissions
    assert 'Continuation after verifier' in json.dumps(local.read('notes'))
    if ending != 'COMPLETED':
        assert result['status'] == ending
        receipts = [json.loads(p.read_text()) for p in tmp_path.glob('workers/*/rounds/*/result.json')]
        assert next(r for r in receipts if r['status'] == ending)['unknown_usage'] is True


@pytest.mark.parametrize('boundary', ['verifier', 'graph', 'response'])
def test_reserved_tool_admission_recovery_without_second_verifier(tmp_path, monkeypatch, boundary):
    net = Network.create(tmp_path, 'p', 'Target')
    proposed = candidate('Recovered local theorem')
    fired = []
    def worker(call, packet, role):
        result = call('candidate_submit', candidate=proposed)
        if boundary == 'response':
            assert result['accepted'] is True  # wire delivered, journal interrupted
        else:
            assert 'error' in result
        return 'TIMEOUT'
    actor = SessionActors(tmp_path, worker)
    if boundary == 'verifier':
        original = actor.runtime.call
        def fail(role, *args, **kwargs):
            result = original(role, *args, **kwargs)
            if role == 'verifier' and not fired:
                fired.append(True); raise OSError('simulated interruption after durable verifier confirmation')
            return result
        monkeypatch.setattr(actor.runtime, 'call', fail)
    elif boundary == 'graph':
        original = Network.save
        def fail(self):
            result = original(self)
            if self.proof_ids() and not fired:
                fired.append(True); raise OSError('simulated interruption after graph publication')
            return result
        monkeypatch.setattr(Network, 'save', fail)
    else:
        from danus.execution import capabilities
        original = capabilities.append_jsonl
        def fail(path, row):
            if row.get('phase') == 'response' and row.get('name') == 'candidate_submit' and not fired:
                fired.append(True); raise OSError('simulated interruption before tool response')
            return original(path, row)
        monkeypatch.setattr(capabilities, 'append_jsonl', fail)
    result = Research(tmp_path, actor.runtime).step()
    assert fired and result['status'] == 'TIMEOUT'
    assert actor.calls.count('verifier') == 1
    assert len(Network(tmp_path).proof_ids()) == 1
    assert result['tool_submissions'][0]['accepted'] is True
    assert Network(tmp_path).data['control']['visit'] == 1


def test_dynamic_premise_revocation_is_rechecked_at_actual_use(tmp_path):
    net = Network.create(tmp_path, 'p', 'Target')
    prior = fixture_fact(net, 'Prior')
    def worker(call, packet, role):
        assert call('premise_request', fact_id=prior)['accepted'] is True
        Network(tmp_path).revoke(prior, 'known wrong proof')
        assert call('proof_read', fact_id=prior, start=0, length=8000)['accepted'] is False
        assert call('candidate_submit', candidate=candidate('B', predecessors=[prior]))['accepted'] is False
        return output()
    actor = SessionActors(tmp_path, worker)
    Research(tmp_path, actor.runtime).step()
    assert actor.calls == ['worker']
    assert Network(tmp_path).revoked_ids() == {prior}


def test_oversized_record_request_returns_repairable_feedback_and_persists_rejection(tmp_path):
    from danus.core import GlobalMemory
    Network.create(tmp_path, 'p', 'Target')
    record_id = GlobalMemory(tmp_path).append('conclusion', 'Old research',
        'Earlier derivation. ' * 1000, 'prior-worker')
    def worker(call, packet, role):
        bad = call('gm_read', kind='conclusion', record_id=record_id, start=0, length=12000)
        assert bad == {'error': {'type': 'INVALID_ARGUMENTS', 'path': ['length'],
                                 'rule': 'maximum', 'expected': 8000}}
        first = call('gm_read', kind='conclusion', record_id=record_id, start=0,
                     length=bad['error']['expected'])
        second = call('gm_read', kind='conclusion', record_id=record_id,
                      start=first['record']['next_start'], length=8000)
        assert first['authority'] == second['authority'] == 'UNVERIFIED_RESEARCH'
        assert first['record']['end'] == second['record']['start'] == 8000
        assert first['record']['sha256'] == second['record']['sha256']
        return output()
    actor = SessionActors(tmp_path, worker)
    Research(tmp_path, actor.runtime).step()
    assert actor.calls == ['worker'] and Network(tmp_path).proof_ids() == []
    events = [json.loads(row) for path in tmp_path.glob('workers/*/rounds/*/capabilities.jsonl')
              for row in path.read_text().splitlines()]
    assert [e['phase'] for e in events] == ['request', 'error', 'request', 'response', 'request', 'response']
    assert events[1]['error']['expected'] == 8000


def test_callback_schema_errors_do_not_expose_private_validation_details(tmp_path):
    from jsonschema import ValidationError
    from danus.execution.capabilities import CapabilityTool
    def private_failure(arguments):
        raise ValidationError('private callback state', validator='const',
                              validator_value='PRIVATE_VALUE')
    tool = CapabilityTool('read', 'fixture', {'type': 'object'}, private_failure)
    with CapabilityBroker([tool], bind='127.0.0.1', evidence_path=tmp_path/'calls.jsonl') as broker:
        req = Request('http://127.0.0.1:%s/rpc' % broker.port,
            data=json.dumps({'method': 'call', 'name': 'read', 'arguments': {}}).encode(),
            headers={'Authorization': 'Bearer ' + broker.token})
        with urlopen(req, timeout=5) as response:
            assert json.load(response) == {'error': 'ValidationError'}
    assert 'PRIVATE_VALUE' not in (tmp_path/'calls.jsonl').read_text()


def test_nested_process_wait_excludes_verification_and_keeps_own_handle(tmp_path):
    import os, sys, threading, time
    from danus.execution import loop
    from danus.execution.layout import WorkerLayout
    from danus.execution.capabilities import CapabilityTool
    w = WorkerLayout(tmp_path / 'project' / 'workers' / 'w')
    v = WorkerLayout(tmp_path / 'project' / 'workers' / 'v')
    w.dir.mkdir(parents=True); v.dir.mkdir(parents=True)
    def process(seconds, extension=None):
        return loop.ProcessCommand([sys.executable, '-c', 'import time; time.sleep(%s)' % seconds],
                                   tmp_path, os.environ.copy(), timeout_extension=extension)
    def verify(arguments):
        code = loop.run_round(v, {}, '', v.dir / 'v.log', 3, safe_read_only=True,
                              command_factory=lambda: process(1.1))
        return {'code': code}
    tool = CapabilityTool('verify', 'test wait', {'type': 'object', 'properties': {}, 'additionalProperties': False},
                          verify, waits_for_model=True)
    with CapabilityBroker([tool], bind='127.0.0.1') as broker:
        outputs = []
        def invoke():
            time.sleep(0.1)
            req = Request('http://127.0.0.1:%s/rpc' % broker.port,
                data=json.dumps({'method': 'call', 'name': 'verify', 'arguments': {}}).encode(),
                headers={'Authorization': 'Bearer ' + broker.token})
            with urlopen(req, timeout=5) as response: outputs.append(json.load(response))
        thread = threading.Thread(target=invoke); thread.start()
        began = time.monotonic()
        result = loop.run_round(w, {}, '', w.dir / 'w.log', 1, safe_read_only=True,
            command_factory=lambda: process(1.6, lambda: broker.wait_seconds))
        thread.join(timeout=5)
        assert result == 0 and outputs == [{'result': {'code': 0}}]
        assert time.monotonic() - began > 1.0 and broker.wait_seconds > 1.0
        assert loop._Child.proc is None


def test_role_deadlines_are_frozen_and_verifier_has_independent_budget(tmp_path):
    calls = []
    def runner(wl, role, prompt, log, timeout, **kwargs):
        calls.append((role['ROLE'], timeout, role['TOOL_TIMEOUT']))
        kwargs['output_path'].write_text('{}', encoding='utf8')
        log.write_text('', encoding='utf8')
        return 0
    rt = Runtime(tmp_path, runner=runner, fingerprint={'test': 'roles'},
                 role_timeouts={'worker': 601, 'verifier': 607})
    rt.call('worker', 'w', 'w', '', {}, {})
    rt.call('verifier', 'v', 'v', '', {}, {})
    assert calls == [('worker', 601, 667), ('verifier', 607, 667)]
    Runtime(tmp_path, runner=runner, fingerprint={'test': 'roles'})  # resume frozen role config
    with pytest.raises(ValueError, match='immutable'):
        Runtime(tmp_path, runner=runner, fingerprint={'test': 'roles'}, role_timeouts={'worker': 602})


def test_fresh_current_authority_workspace_preserves_proofs_revocations_and_memory(tmp_path):
    from crpn.migrate import migrate, source_hashes
    source, destination = tmp_path / 'source', tmp_path / 'fresh'
    net = Network.create(source, 'p', 'Target')
    first = fixture_fact(net, 'A')
    wrong = fixture_fact(net, 'Known wrong')
    net.revoke(wrong, 'historical known error')
    net.data['control'] = {'run_id': 'old-runtime', 'visit': 7, 'pending': None}; net.save()
    study = 'study-' + net.target_id
    LocalMemory(lane(source, study)).append('notes', {'content': 'Existing multistep research.'})
    before = source_hashes(source)
    migrate(source, destination)
    new = Network(destination)
    assert new._records() == net._records()
    assert new.revoked_ids() == {wrong} and new.proof_ids() == [first]
    assert new.data['control']['run_id'] != 'old-runtime' and new.data['control']['visit'] == 7
    assert LocalMemory(lane(destination, study)).read('notes') == LocalMemory(lane(source, study)).read('notes')
    assert source_hashes(source) == before and not (destination / 'runtime.json').exists()
    frozen = source_hashes(destination)
    migrate(source, destination)
    assert source_hashes(destination) == frozen


def test_target_admitted_in_session_then_interrupt_still_commits_service_once(tmp_path):
    Network.create(tmp_path, 'p', 'Target')
    def worker(call, packet, role):
        assert call('candidate_submit', candidate=candidate('Target'))['accepted'] is True
        return 'INTERRUPTED'
    actor = SessionActors(tmp_path, worker)
    with pytest.raises(KeyboardInterrupt): Research(tmp_path, actor.runtime).step()
    result = Research(tmp_path, actor.runtime).step()
    assert result['status'] == 'INTERRUPTED'
    n = Network(tmp_path)
    assert n.data['control']['visit'] == 1 and n.truth(n.target_id) == 'DISCHARGED'
    assert Research(tmp_path, actor.runtime).step()['status'] == 'TARGET_SOLVED'
    assert actor.calls == ['worker', 'verifier']


def test_heartbeat_uses_stable_metadata_and_sharing_conflict_is_nonfatal(tmp_path, monkeypatch):
    from danus.execution.isolation import DockerRoundRunner
    from danus.execution.layout import WorkerLayout
    from danus.execution.capabilities import CapabilityTool
    from danus.execution import isolation
    monkeypatch.setattr(DockerRoundRunner, '_check', lambda self,args: 'sha256:fixture' if args[0]=='image' else 'codex-fixture')
    auth=tmp_path/'auth';auth.mkdir();(auth/'auth.json').write_text('{}')
    tool=CapabilityTool('verify', 'fixture', {'type':'object'}, lambda a: {}, waits_for_model=True)
    runner=DockerRoundRunner(tools=lambda *a:[tool],auth_dir=auth,docker='docker')
    monkeypatch.setattr(runner, '_remove', lambda name:None)
    wl=WorkerLayout(tmp_path/'project'/'workers'/'lane');wl.dir.mkdir(parents=True)
    schema=wl.dir/'schema.json';schema.write_text('{}')
    seen=[]
    def fake_round(wl,role,prompt,log,timeout,**kwargs):
        process=kwargs['command_factory'](); heartbeat=process.cwd/'heartbeat'
        assert heartbeat.exists() and heartbeat.read_bytes()==b''
        inode=heartbeat.stat().st_ino
        real_utime=isolation.os.utime
        def conflict(path,times):
            if not seen:
                seen.append(True);raise PermissionError('simulated Windows sharing conflict')
            return real_utime(path,times)
        with monkeypatch.context() as patch:
            patch.setattr(isolation.os,'utime',conflict)
            process.heartbeat();process.heartbeat()
        assert heartbeat.stat().st_ino==inode and heartbeat.read_bytes()==b''
        (process.cwd/'response.json').write_text('{}')
        log.write_text('')
        return 0
    monkeypatch.setattr(isolation,'run_round',fake_round)
    assert runner(wl,{'ROLE':'worker','MODEL':'gpt-5.6-sol','REASONING_EFFORT':'xhigh'},'',wl.dir/'public.jsonl',600,
                  schema_path=schema,output_path=wl.dir/'response.json')==0
    timing=json.loads((wl.dir/'timing.json').read_text())
    assert timing['heartbeat_refresh_failures']==1


def test_ordinary_worker_handover_cannot_admit_math_and_alternative_tool_proofs_remain_valid(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open target')
    def worker(call, packet, role):
        first = call('candidate_submit', candidate=candidate('Local lemma', proof='First complete proof.'))
        second = call('candidate_submit', candidate=candidate('Local lemma', proof='Independent complete proof.'))
        assert first['accepted'] and second['accepted']
        assert first['premise']['fact_id'] != second['premise']['fact_id']
        return {'submission_receipts': [first['premise']['fact_id'], second['premise']['fact_id']],
                'continuation': 'A further new theorem, with a claimed complete proof in this final prose. The target remains open.', 'next_work': 'Check the target obligation.',
                'new_study': None}
    actor = SessionActors(tmp_path, worker)
    result = Research(tmp_path, actor.runtime).step()
    current = Network(tmp_path)
    assert result['status'] == 'COMPLETED'
    assert actor.calls == ['worker', 'verifier', 'verifier']
    assert len(result['tool_submissions']) == len(current.proof_ids()) == 2
    assert len(current.facts_for(current.register_claim('Local lemma')['claim_id'])) == 2
    assert current.truth(current.target_id) == 'OPEN'
    assert current.data['control']['visit'] == 1


def test_rejection_feedback_reaches_next_local_packet_without_new_authority(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open target')
    def worker(call, packet, role):
        rejected = call('candidate_submit', candidate=candidate('Local lemma', proof='Needs correction.'))
        assert rejected['verdict'] == 'wrong' and 'Paragraph 2' in rejected['feedback']['reason']
        return output(continuation='Repair paragraph 2 before resubmitting.')
    actor = SessionActors(tmp_path, worker)
    result = Research(tmp_path, actor.runtime).step()
    assert result['status'] == 'VERIFIER_REJECTED'
    assert Network(tmp_path).proof_ids() == []
    study = 'study-' + net.target_id
    packet = worker_packet(Network(tmp_path), {'study_id': study, 'task': 'Continue the open claim.',
        'operation': 'RESEARCH', 'fact_ids': [], 'research_queries': []})
    assert 'Paragraph 2' in json.dumps(packet['verification_feedback'])
    assert 'Repair paragraph 2' in json.dumps(packet['research_context'])


def test_local_research_hits_deduplicate_by_original_record_and_keep_queries(tmp_path):
    from danus.core import GlobalMemory
    net = Network.create(tmp_path, 'p', 'Open target')
    study = 'study-' + net.target_id
    LocalMemory(lane(tmp_path, study)).append('notes', {'content': 'alpha beta gamma earlier derivation'})
    gm = GlobalMemory(tmp_path)
    first = gm.append('conclusion', 'alpha beta gamma claim', 'First conditional evidence.', study)
    second = gm.append('conclusion', 'alpha beta gamma claim', 'Different conditional evidence.', study)
    packet = worker_packet(net, {'study_id': study, 'task': 'Continue the open claim.',
        'operation': 'RESEARCH', 'fact_ids': [], 'research_queries': ['alpha', 'beta', 'gamma']})
    local = [item for part in packet['research_context'] for item in part['local']]
    shared = [item for part in packet['research_context'] for item in part['shared']
              if item['kind'] == 'conclusion']
    assert len(local) == 1 and len(shared) == 2
    assert {item['record_id'] for item in shared} == {first, second}
    assert local[0]['matched_queries'] == ['alpha', 'beta', 'gamma']
    assert all(item['matched_queries'] == ['alpha', 'beta', 'gamma'] for item in shared)
    assert packet['accepted_facts'] == [] and packet['local_cut']['shared_evidence_core']['results'] == []


def test_overwide_support_pages_exact_conditions_only_inside_current_cut(tmp_path):
    from test_model import support
    from crpn.scheduler import focus
    from crpn.work import derive
    net = Network.create(tmp_path, 'p', 'Target')
    requirements = [f'Condition {i}: exact domain and boundary assumptions remain in force'
                    for i in range(240)]
    row = support(net, 'Target', requirements)
    for sid, study in net.data['studies'].items():
        if sid != 'study-' + net.target_id:
            study['last_served_visit'] = 0
    exposure, schedule_after = focus(net.active_studies(), {})
    cut, options, observed = derive(net, exposure)
    net.data['control'] = {'run_id': 'wide-interface-test', 'visit': 1, 'pending': {
        'exposure': exposure, 'schedule_after': schedule_after, 'selection_round': 0,
        'inspections': [], 'action': options[0], 'cut': cut, 'options': options,
        'observation': observed, 'work_cursor_after': 1}}
    net.save()
    def worker(call, packet, role):
        assert packet['local_cut']['routes'][0]['interface_page_required']
        page = call('support_read', support_id=row['support_id'], page=0)
        assert page['total_requirements'] == 240 and page['next_page'] == 1
        assert [r['goal'] for r in page['requirements']] == requirements[:8]
        second = call('support_read', support_id=row['support_id'], page=1)
        assert [r['goal'] for r in second['requirements']] == requirements[8:16]
        assert call('support_read', support_id='unexposed-support', page=0)['accepted'] is False
        assert packet['accepted_facts'] == []
        return output()
    actor = SessionActors(tmp_path, worker)
    assert Research(tmp_path, actor.runtime).step()['status'] == 'COMPLETED'
    assert actor.calls == ['worker']


def test_session_material_reads_have_cumulative_bound_without_affecting_submission(tmp_path):
    from test_model import fact
    net = Network.create(tmp_path, 'p', 'Target')
    prior = fact(net, net.register_claim('Auxiliary Target result')['claim_id'],
                 proof='Named proof section\n' + 'Detailed argument. ' * 18000)
    def worker(call, packet, role):
        successes = 0
        for _ in range(40):
            response = call('proof_read', fact_id=prior, start=0, length=8000)
            if response.get('error') == 'ATTENTION_BUDGET_EXHAUSTED':
                break
            assert response['authority'] == 'INSPECTION_ONLY'
            successes += 1
        assert 0 < successes < 40
        assert call('proof_read', fact_id=prior, start=0, length=8000)['error'] == 'ATTENTION_BUDGET_EXHAUSTED'
        return output()
    actor = SessionActors(tmp_path, worker)
    assert Research(tmp_path, actor.runtime).step()['status'] == 'COMPLETED'
    assert actor.calls == ['worker']


def test_existing_task_result_is_exposed_for_inspection_without_premise_authority(tmp_path):
    net = Network.create(tmp_path, 'p', 'Open target')
    prior = fixture_fact(net, 'Exact 836 boundary for a finite witness')
    study = 'study-' + net.target_id
    packet = worker_packet(net, {'study_id': study,
        'task': 'Check the existing exact 836 boundary before trying an extension.',
        'operation': 'RESEARCH', 'fact_ids': [], 'research_queries': []})
    assert any(item['fact_id'] == prior and packet['local_cut']['shared_evidence_core']['authority'] == 'INSPECTION_ONLY'
               for item in packet['local_cut']['shared_evidence_core']['results'])
    assert packet['accepted_facts'] == []
