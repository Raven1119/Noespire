"""Deterministic strategy transitions on the actual DANUS truth store."""
import json
import pytest
from danus.core.factgraph import FactGraph
from crpn.model import Network, make_claim


def fact(net, claim_id, *, predecessors=(), proof='A complete deterministic fixture proof.'):
    row = net.claim(claim_id)
    fid = net.graph.add(problem_id=net.problem_id, author='fixture-verifier',
                        statement=row['statement'], proof=proof, predecessors=list(predecessors))
    net.bind_fact(claim_id, fid)
    return fid


def support(net, goal, requirements, *, predecessors=(), context='', visible=None):
    candidate = dict(kind='SUPPORT', goal=goal, context=context, proof='The stated requirements imply the conclusion.',
                     predecessors=list(predecessors), requirements=[dict(goal=g,context=context) for g in requirements])
    prepared, descriptor = net.prepare_candidate(candidate, list(predecessors) if visible is None else visible)
    fid = net.graph.add(problem_id=net.problem_id, author='fixture-verifier', **prepared)
    return net.accept_verified(descriptor, fid)


def certificate(net, statement, *, predecessors=(), proof='Both directions by explicit representation transport.'):
    return net.graph.add(problem_id=net.problem_id, author='fixture-verifier', statement=statement,
                         proof=proof, predecessors=list(predecessors))


def test_claim_identity_scope_and_one_truth_store(tmp_path):
    net = Network.create(tmp_path, 'p', 'T')
    assert net.claim(net.target_id) == make_claim('p', '', 'T')
    assert net.truth(net.target_id) == 'OPEN'
    fid = fact(net, net.target_id)
    assert Network(tmp_path).truth(net.target_id) == 'DISCHARGED'
    assert len(net.export()['facts']) == 1
    assert (tmp_path/'fact_graph'/'facts'/(fid+'.md')).exists()
    assert not (tmp_path/'facts').exists()
    net.graph.revoke(fid,'later invalidated')
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'
    with pytest.raises(ValueError):
        net.export()


def test_support_conditions_wait_compose_and_lineage(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['A','B'])
    a,b = row['requirement_claim_ids']
    assert len(net.data['studies']) == 3
    assert not net.ready_supports()
    fa = fact(net,a)
    fb = fact(net,b)
    assert net.truth(net.target_id) == 'OPEN'
    assert len(net.ready_supports()) == 1
    packet = net.support_materials(row['support_id'])
    ids = [f.fact_id for f in packet['facts']]
    assert set(ids) == {fa,fb,row['bridge_fact_id']}
    candidate = net.compose_candidate(row['support_id'],'Combine the exact certificate and both established conditions.')
    prepared, descriptor = net.prepare_compose(row['support_id'],candidate)
    bad = dict(candidate, predecessors=[fa,fb])
    with pytest.raises(ValueError,match='COMPOSE'):
        net.prepare_compose(row['support_id'],bad)
    fid = net.graph.add(problem_id='p',author='fixture-verifier',**prepared)
    net.accept_verified(descriptor,fid)
    assert net.truth(net.target_id) == 'DISCHARGED'
    assert {f.fact_id for f in net.graph.supporting_closure(fid)} == {*ids,fid}
    net.graph.revoke(fa,'revoke an actual condition')
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'
    assert not net.ready_supports()


def test_scope_definition_in_statement_valid_extra_context_rejected(tmp_path):
    net = Network.create(tmp_path,'p','T','x is real')
    support(net,'T',['For real t define U(t)=t+1; prove U(x)>x.'],context='x is real')
    before = json.loads((tmp_path/'crpn.json').read_text())
    bad=dict(kind='SUPPORT',goal='T',context='x is real',proof='proof',predecessors=[],
             requirements=[dict(goal='U(x)>x',context='x is real; define U(t)=t+1')])
    with pytest.raises(ValueError,match='exact ambient scope'):
        net.prepare_candidate(bad,[])
    assert json.loads((tmp_path/'crpn.json').read_text()) == before


def test_unary_new_study_waits_recurrence_then_releases_idempotently(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['A'])
    child = row['requirement_claim_ids'][0]
    assert 'study-'+child not in net.data['studies']
    assert row['support_id'] in Network(tmp_path).data['pending_recurrence']
    net.finish_recurrence(row['support_id'])
    assert 'study-'+child in net.data['studies']
    before = (tmp_path/'crpn.json').read_bytes()
    net.finish_recurrence(row['support_id'])
    assert (tmp_path/'crpn.json').read_bytes() == before
    assert net.effective_depth() == 1


def test_verified_alias_suppresses_only_new_study_not_truth(tmp_path):
    net = Network.create(tmp_path,'p','Original statement')
    row = support(net,'Original statement',['Relabelled statement'])
    child = row['requirement_claim_ids'][0]
    eq = certificate(net,net.equivalence_statement(net.target_id,child))
    net.record_alias(row['support_id'],net.target_id,eq)
    assert net.alias_of(child) == net.target_id
    assert net.inspect_fact(eq)['scope'] == ''
    assert net.visible_fact(eq,'').fact_id == eq
    with pytest.raises(ValueError,match='exact scope'):
        net.visible_fact(eq,'extra assumption')
    assert 'study-'+child not in net.data['studies']
    assert len(net.active_studies()) == 1
    assert net.effective_depth() == 0
    assert net.truth(net.target_id) == net.truth(child) == 'OPEN'
    assert row['support_id'] in net.data['supports']
    net.graph.revoke(eq,'transport invalidated')
    net = Network(tmp_path)
    assert net.alias_of(child) is None
    net.ensure_studies()
    assert 'study-'+child in net.data['studies']
    assert net.effective_depth() == 1


def test_exact_ancestor_duplicate_does_not_suppress_ancestor(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['T'])
    eq = certificate(net,net.equivalence_statement(net.target_id,net.target_id))
    net.record_alias(row['support_id'],net.target_id,eq)
    assert net.alias_of(net.target_id) is None
    assert len(net.active_studies()) == 1
    assert net.truth(net.target_id) == 'OPEN'
    assert net.effective_depth() == 0


def test_wrong_or_multi_certificate_never_creates_alias(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['A'])
    bad = certificate(net,'A stronger unrelated theorem')
    with pytest.raises(ValueError,match='equivalence certificate'):
        net.record_alias(row['support_id'],net.target_id,bad)
    assert not net.data['representations']
    net.finish_recurrence(row['support_id'])
    assert len(net.active_studies()) == 2
    multi = support(net,'T',['B','C'])
    with pytest.raises(ValueError,match='unary'):
        net.record_alias(multi['support_id'],net.target_id,bad)
    assert len(net.data['studies']) == 4


def test_conditional_helper_activation_and_revoke(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['Representation'])
    child = row['requirement_claim_ids'][0]
    helper = net.register_claim('A genuinely separate helper')['claim_id']
    cond = certificate(net,net.conditional_equivalence_statement(net.target_id,child,helper))
    net.defer_alias(row['support_id'],net.target_id,helper,cond)
    assert net.alias_of(child) is None
    assert net.waiting_on(child) == helper
    assert net.inspect_fact(cond)['scope'] == ''
    assert 'study-'+child not in net.data['studies']
    assert 'study-'+helper in net.data['studies']
    with pytest.raises(ValueError,match='helper-satisfied'):
        net.activation_candidate(row['support_id'])
    hf = fact(net,helper)
    net.defer_alias(row['support_id'],net.target_id,helper,cond)  # replay after helper solved
    candidate = net.activation_candidate(row['support_id'])
    assert candidate['predecessors'] == sorted([cond,hf])
    af = net.graph.add(problem_id='p',author='fixture-verifier',**candidate)
    net.activate_alias(row['support_id'],af)
    net.activate_alias(row['support_id'],af)
    assert net.alias_of(child) == net.target_id
    assert net.truth(net.target_id) == net.truth(child) == 'OPEN'
    assert net.truth(helper) == 'DISCHARGED'
    assert {f.fact_id for f in net.graph.supporting_closure(af)} == {af,cond,hf}
    assert net.effective_depth() == 0
    net.graph.revoke(hf,'helper refuted later')
    net = Network(tmp_path)
    assert net.alias_of(child) is None
    assert net.waiting_on(child) is None
    net.ensure_studies()
    assert 'study-'+child in net.data['studies']


def test_activation_rejects_wrong_lineage_or_added_argument(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = support(net,'T',['R'])
    child = row['requirement_claim_ids'][0]
    h = net.register_claim('H')['claim_id']
    cf = certificate(net,net.conditional_equivalence_statement(net.target_id,child,h))
    net.defer_alias(row['support_id'],net.target_id,h,cf)
    hf = fact(net,h)
    candidate = net.activation_candidate(row['support_id'])
    wrong = certificate(net,candidate['statement'],predecessors=[cf],proof=candidate['proof'])
    with pytest.raises(ValueError,match='lineage'):
        net.activate_alias(row['support_id'],wrong)
    assert net.alias_of(child) is None
    assert net.waiting_on(child) == h


def test_cross_scope_discovery_is_not_authority_bridge_enables_use(tmp_path):
    net = Network.create(tmp_path,'p','T','x>0')
    source = net.register_claim('x*x>=0','x is real')
    sf = fact(net,source['claim_id'])
    assert net.inspect_fact(sf)['scope'] == 'x is real'
    with pytest.raises(ValueError,match='exact scope'):
        net.visible_fact(sf,'x>0')
    target = net.register_claim('x*x>=0','x>0')
    tf = fact(net,target['claim_id'],predecessors=[sf],proof='Positive real x is real; apply the source interface.')
    assert net.visible_fact(tf,'x>0').fact_id == tf
    assert {f.fact_id for f in net.graph.supporting_closure(tf)} == {sf,tf}
    candidate=dict(kind='FACT',goal='T',context='x>0',proof='Use the lawful target interface.',predecessors=[tf],requirements=[])
    net.prepare_candidate(candidate,[tf])
    with pytest.raises(ValueError,match='supplied'):
        net.prepare_candidate(candidate,[])
    net.graph.revoke(sf,'invalid source')
    with pytest.raises((ValueError,KeyError)):
        net.visible_fact(tf,'x>0')


def test_refutation_is_fact_bound_and_revocable(tmp_path):
    net = Network.create(tmp_path,'p','False claim')
    assert net.truth(net.target_id) == 'OPEN'  # notes/failure never resolve it
    rf = certificate(net,net.refutation_statement(net.target_id),proof='A complete counterexample.')
    net.bind_refutation(net.target_id,rf)
    assert Network(tmp_path).truth(net.target_id) == 'REFUTED'
    assert net.inspect_fact(rf)['scope'] == ''
    with pytest.raises(ValueError):
        fact(net,net.target_id)
    net.graph.revoke(rf,'counterexample invalidated')
    assert Network(tmp_path).truth(net.target_id) == 'OPEN'


def test_corrupt_claim_binding_and_cross_problem_fail_closed(tmp_path):
    net = Network.create(tmp_path,'p','T')
    foreign = net.graph.add(problem_id='other',author='fixture',statement='T',proof='proof')
    with pytest.raises(ValueError,match='cross-problem'):
        net.bind_fact(net.target_id,foreign)
    state = json.loads((tmp_path/'crpn.json').read_text())
    state['claims'][net.target_id]['goal'] = 'Changed meaning'
    (tmp_path/'crpn.json').write_text(json.dumps(state))
    with pytest.raises(ValueError,match='identity'):
        Network(tmp_path)


def test_independent_exploratory_study_has_no_truth_authority(tmp_path):
    net = Network.create(tmp_path,'p','T')
    row = net.register_study('Explore a different representation', 'x is real')
    assert row['claim_id'] is None
    assert len(net.active_studies()) == 2
    assert net.truth(net.target_id) == 'OPEN'
    assert Network(tmp_path).data['studies'][row['study_id']] == row


def test_write_ahead_revoke_before_archive_move_is_already_false_closed(tmp_path):
    from danus.core.durable_io import atomic_json
    net = Network.create(tmp_path,'p','T')
    fid = fact(net,net.target_id)
    atomic_json(net.graph.dir/'revocations'/(fid+'.json'),{'fact_ids':[fid],'reason':'revoke','timestamp_utc':'frozen'})
    assert net.graph._path(fid).exists()
    assert not (net.graph.revoked_dir/(fid+'.md')).exists()
    restored = Network(tmp_path)
    assert restored.truth(restored.target_id) == 'OPEN'
    with pytest.raises((ValueError,KeyError)):
        restored.visible_fact(fid,'')
    restored.graph.revoke(fid,'complete recorded revocation')
    assert (restored.graph.revoked_dir/(fid+'.md')).exists()


def test_unbound_accepted_fact_does_not_gain_scope_by_existence(tmp_path):
    net = Network.create(tmp_path,'p','T')
    fid = certificate(net,'Some unrelated valid theorem')
    with pytest.raises(ValueError,match='scope binding'):
        net.inspect_fact(fid)
    with pytest.raises(ValueError,match='exact scope'):
        net.visible_fact(fid,'')


def test_new_local_fact_claim_and_binding_publish_in_one_state_write(tmp_path,monkeypatch):
    import crpn.model as module
    net = Network.create(tmp_path,'p','T')
    candidate = {'kind':'FACT','goal':'A local result','context':'','proof':'A complete proof.',
                 'requirements':[],'predecessors':[]}
    prepared,descriptor = net.prepare_candidate(candidate,[])
    fid = net.graph.add(problem_id='p',author='fixture-verifier',**prepared)
    writes=[]
    original=module.atomic_json
    def record(path,value):
        writes.append(json.loads(json.dumps(value)))
        original(path,value)
    monkeypatch.setattr(module,'atomic_json',record)
    admission = net.accept_verified(descriptor,fid)
    assert len(writes)==1
    assert writes[0]['fact_bindings'][admission['claim_id']]==[fid]
    assert net.truth(net.target_id)=='OPEN'
