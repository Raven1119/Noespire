"""Authority convergence, OR/AND integrity and admission interruption boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from crpn.model import Network
from crpn.admission import Admission
from crpn.materials import worker_packet, selector_packet
from crpn.scheduler import expose
from test_model import fact, support, submit, Correct


def test_revoking_one_or_route_preserves_the_other(tmp_path):
    n = Network.create(tmp_path, 'p', 'T')
    left = support(n, 'T', ['A', 'B'])
    right = support(n, 'T', ['C', 'D'])
    proofs = {cid: fact(n, cid) for row in (left, right) for cid in row['requirement_claim_ids']}
    target_proofs = []
    for row in (left, right):
        # Exact composition readiness belongs to the AND prerequisites, not an alias.
        packet = n.support_materials(row['support_id']) if not target_proofs else None
        ids = [row['bridge_fact_id']] + [proofs[cid] for cid in row['requirement_claim_ids']]
        candidate = dict(kind='FACT', goal='T', context='', requirements=[], predecessors=ids,
                         proof='Apply precisely this certificate and its two proved conditions: ' + row['support_id'])
        prepared, descriptor = n.prepare_candidate(candidate, ids)
        target_proofs.append(submit(n, prepared, descriptor)['fact_id'])
    n.revoke(proofs[left['requirement_claim_ids'][0]], 'left condition invalid')
    n = Network(tmp_path)
    assert n.truth(n.target_id) == 'DISCHARGED'
    assert [f.fact_id for f in n.facts_for(n.target_id)] == [target_proofs[1]]
    assert target_proofs[0] in n.revoked_ids()
    assert n.export()['target_fact_id'] == target_proofs[1]
    assert all(f['status'] == 'accepted' for f in n.export()['facts'])
    n.revoke(target_proofs[1], 'right proof invalid')
    assert n.truth(n.target_id) == 'OPEN'


def test_incomplete_and_and_cycles_do_not_complete(tmp_path):
    n = Network.create(tmp_path, 'p', 'T')
    route = support(n, 'T', ['A', 'B'])
    a, b = route['requirement_claim_ids']
    fact(n, a)
    assert not n.ready_supports()
    with pytest.raises(ValueError, match='not ready'):
        n.support_materials(route['support_id'])
    support(n, 'B', ['T'])
    assert n.truth(n.target_id) == n.truth(b) == 'OPEN'
    assert not n.ready_supports()


@pytest.mark.parametrize('boundary', ['verification.json', 'graph_commit', 'result.json'])
def test_admission_crash_uses_one_verification_one_graph_write(tmp_path, monkeypatch, boundary):
    import crpn.admission as module
    import crpn.model as model
    n = Network.create(tmp_path, 'p', 'T')
    candidate = dict(kind='FACT', goal='New lemma', context='', proof='Complete proof', predecessors=[], requirements=[])
    prepared, descriptor = n.prepare_candidate(candidate, [])
    calls, writes, fired = [], [], []
    class Backend:
        def verify(self, *args):
            calls.append(args)
            return {'verdict':'correct', 'reason':'fixture'}
    original_immutable, original_atomic = module.immutable_json, model.atomic_json
    def immutable(path, value):
        original_immutable(path, value)
        if Path(path).name == boundary and not fired:
            fired.append(1)
            raise KeyboardInterrupt()
    def atomic(path, value):
        original_atomic(path, value)
        writes.append(deepcopy(value))
        if boundary == 'graph_commit' and not fired:
            fired.append(1)
            raise KeyboardInterrupt()
    monkeypatch.setattr(module, 'immutable_json', immutable)
    monkeypatch.setattr(model, 'atomic_json', atomic)
    gate = Admission(Backend())
    kwargs = dict(prepared=prepared, descriptor=descriptor, author='fixture', purpose='test')
    with pytest.raises(KeyboardInterrupt):
        gate.submit(n, 'same-call', **kwargs)
    n = Network(tmp_path)
    result = gate.submit(n, 'same-call', **kwargs)
    assert result['accepted'] and len(calls) == len(writes) == 1
    assert len(n.proof_ids()) == 1
    assert gate.submit(Network(tmp_path), 'same-call', **kwargs) == result
    assert len(calls) == len(writes) == 1
    n.revoke(result['fact_id'], 'invalidate after receipt')
    with pytest.raises(ValueError, match='revoked'):
        gate.submit(Network(tmp_path), 'same-call', **kwargs)
    assert len(calls) == 1


def test_admission_rechecks_predecessor_after_verifier(tmp_path):
    n = Network.create(tmp_path, 'p', 'T')
    prior = fact(n, n.register_claim('A')['claim_id'])
    candidate = dict(kind='FACT', goal='T', context='', proof='Use A', predecessors=[prior], requirements=[])
    prepared, desc = n.prepare_candidate(candidate, [prior])
    class Backend:
        def verify(self, *args):
            Network(tmp_path).revoke(prior, 'revoked concurrently')
            return {'verdict':'correct'}
    with pytest.raises(ValueError, match='concurrent|changed|revoked'):
        Admission(Backend()).submit(n, 'concurrent', prepared=prepared, descriptor=desc, author='f', purpose='f')
    assert Network(tmp_path).truth(n.target_id) == 'OPEN'


def test_views_do_not_expose_embedded_proof_storage(tmp_path):
    n = Network.create(tmp_path, 'p', 'T')
    route = support(n, 'T', ['A', 'B'])
    for cid in route['requirement_claim_ids']:
        fact(n, cid, proof='SECRET_PROOF_BODY_' + cid)
    exposure, _ = expose(n.active_studies(), {})
    selection = selector_packet(n, exposure)
    worker = worker_packet(n, dict(study_id='study-' + n.target_id, operation='RESEARCH', task='Continue', fact_ids=[], research_queries=[]))
    for packet in (selection, worker):
        text = json.dumps(packet)
        assert 'SECRET_PROOF_BODY' not in text
        assert 'certificates' not in text and 'history' not in text and 'proofs' not in text
    assert selection['studies'][0]['ready_supports']


def test_old_imports_are_absent_from_active_entry():
    code = '''import sys
from crpn.engine import Research
from crpn.cli import status
from crpn.materials import capability_tools
assert 'danus.core.factgraph' not in sys.modules
assert 'danus.gateway.submission' not in sys.modules
assert 'danus.gateway.server' not in sys.modules
assert 'danus.execution.scaffold' not in sys.modules
assert not any(x.startswith('danus.orchestration') for x in sys.modules)
'''
    result = subprocess.run([sys.executable, '-B', '-c', 'import sys; sys.path[:0] = ' + repr(sys.path) + '\n' + code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_saving_a_forged_acceptance_is_not_a_second_admission(tmp_path):
    from crpn.model import proof_identity
    n = Network.create(tmp_path, 'p', 'T')
    record = dict(problem_id='p', statement='T', proof='Unverified', predecessors=[], author='intruder',
                  status='accepted', id_scheme='content-v1', history=[{'event':'accepted'}])
    record['fact_id'] = proof_identity(record)
    n.data['claims'][n.target_id]['proofs'] = {record['fact_id']: record}
    with pytest.raises(ValueError, match='verified submission'):
        n.save()
    assert Network(tmp_path).truth(n.target_id) == 'OPEN'


def test_stale_closure_and_history_rewrite_fail_closed(tmp_path):
    n = Network.create(tmp_path, 'p', 'T')
    fid = fact(n, n.target_id)
    stale = Network(tmp_path)
    n.revoke(fid, 'invalid')
    with pytest.raises(ValueError, match='changed'):
        stale.supporting_closure(fid)
    n.data['claims'][n.target_id]['proofs'][fid]['status'] = 'accepted'
    n.data['claims'][n.target_id]['proofs'][fid]['history'].pop()
    with pytest.raises(ValueError, match='immutable'):
        n.save()
    assert Network(tmp_path).truth(n.target_id) == 'OPEN'
