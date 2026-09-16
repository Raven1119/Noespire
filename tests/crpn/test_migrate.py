"""Migration imports mathematics, never an old runtime authority or old permissions."""
from hashlib import sha256
import json
from pathlib import Path
import pytest
from danus.core.local_memory import LocalMemory
from danus.core.global_memory import GlobalMemory
from crpn.model import Network, identity, make_claim, normalize
from crpn.migrate import migrate, source_hashes


def write(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def legacy_fact(root,statement,proof,predecessors=(),revoked=False):
    values=dict(problem_id='p',statement=normalize(statement),proof=normalize(proof),predecessors=sorted(set(predecessors)))
    fid=sha256(json.dumps(values,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:16]
    metadata=dict(fact_id=fid,problem_id='p',author='original-worker',predecessors=values['predecessors'])
    path=root/('_revoked' if revoked else 'facts')/(fid+'.md')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text('---\n'+json.dumps(metadata)+'\n---\n# Statement\n\n'+values['statement']+'\n\n# Proof\n\n'+values['proof']+'\n',encoding='utf-8')
    return fid


def legacy(tmp_path,*,revoked=False):
    root=tmp_path/'source'
    t=make_claim('p','','T');a=make_claim('p','','A');b=make_claim('p','','B')
    fa=legacy_fact(root,'A','Original proof A',revoked=revoked)
    fb=legacy_fact(root,'B','Apply source Fact '+fa,[fa])
    cs='The conjunction of these statements ["B"] implies the statement "T".'
    certificate=legacy_fact(root,cs,'Conditional certificate')
    values=dict(conclusion_claim_id=t['claim_id'],requirement_claim_ids=[b['claim_id']],scope_ref=identity('scope-',{'problem_id':'p','context':''}),bridge_fact_id=certificate)
    sid=identity('support-',values)
    obligations={r['claim_id']:{'obligation_id':r['claim_id'],'problem_id':'p','context':r['context'],'goal':r['goal'],'truth_state':'OPEN','resolved_fact_id':None,'resolved_route_id':None,'refutation_id':None} for r in [t,a,b]}
    g=dict(schema_version='crpn-1',problem_id='p',target_obligation_id=t['claim_id'],obligations=obligations,
           fact_bindings={a['claim_id']:[fa],b['claim_id']:[fb]},supports={sid:{'support_id':sid,**values}},refutations={})
    studies={}
    for claim in [t,a,b]:
        study='study-'+claim['claim_id'];ref=f'studies/{study}/000002.json'
        row=dict(study_id=study,claim_id=claim['claim_id'],scope='',focus=claim['goal'],revision=2,
                 continuation='Exact original unverified derivation '+claim['goal'],next_work='Continue the remaining gap.',known_fact_ids=[fa],
                 material_refs=['arbitrary-old-file'],evidence_refs=['old-call'],verified=False,visit=4)
        write(root/'continuous_run'/ref,row);studies[study]=ref
    study='study-explore';ref=f'studies/{study}/000000.json'
    write(root/'continuous_run'/ref,dict(study_id=study,claim_id=None,scope='',focus='Independent exploration',revision=0,continuation='Unverified hypothesis',next_work='Test it'))
    studies[study]=ref
    run=dict(run_id='old-run',code_digest='frozen-code',status='PAUSED',step=8,studies=studies,
             schedule=dict(channel_cycle=['ADVANCE','ADVANCE','ADVANCE','EXPLORE','REVISIT'],channel_cursor=7,revisit_cursor=1,revisit_snapshot=list(studies)),runtime={'model':'gpt-5.6-sol','timeout_seconds':600})
    write(root/'proof_graph.json',g);write(root/'continuous_run/state.json',run)
    artifact=dict(kind='UNVERIFIED_RESEARCH_ARTIFACT',study_id='study-'+t['claim_id'],verified=False,source_visit=6,
                  invocation_id='timeout-call',message_id='item_3',text='An exact partial result, not a Fact.')
    write(root/'continuous_run/research_artifacts'/artifact['study_id']/'artifact.json',artifact)
    write(root/'continuous_run/calls/timeout-call/result.json',{'status':'TIMEOUT'})
    if revoked:
        (root/'revocation_log.jsonl').write_text(json.dumps({'fact_id':fa,'reason':'invalidated'})+'\n')
    return root,g,run,(fa,fb,certificate)


def test_full_import_lineage_scope_memories_and_schedule(tmp_path):
    root,g,run,ids=legacy(tmp_path);before=source_hashes(root)
    dest=tmp_path/'new'
    report=migrate(root,dest)
    net=Network(dest);mapped=report['fact_id_map']
    assert mapped[ids[0]]!=ids[0]
    assert net.graph.get(mapped[ids[1]]).predecessors==[mapped[ids[0]]]
    assert ids[0] in net.graph.get(mapped[ids[1]]).proof  # original text, explicit provenance map
    assert net.data['schedule']==run['schedule']
    assert net.data['control']['run_id']!='old-run'
    assert not (dest/'continuous_run').exists()
    assert not (dest/'facts').exists()
    assert net.truth(net.target_id)=='OPEN'
    assert len(net.ready_supports())==1
    assert 'study-explore' in net.data['studies']
    assert not set(net.data['studies']['study-'+net.target_id]) & {'known_fact_ids','material_refs','evidence_refs','continuation'}
    notes=LocalMemory(dest/'workers'/('study-'+net.target_id)).read('notes')
    assert any(r['record'].get('source_status')=='TIMEOUT' for r in notes)
    assert all(r['record']['authority']=='UNVERIFIED_RESEARCH' for r in notes)
    assert GlobalMemory(dest).read('direction')
    assert source_hashes(root)==before
    after=source_hashes(dest)
    assert migrate(root,dest)==report
    assert source_hashes(dest)==after


def test_revoked_source_and_active_descendant_import_fail_closed(tmp_path):
    root,g,run,ids=legacy(tmp_path,revoked=True)
    report=migrate(root,tmp_path/'new')
    net=Network(tmp_path/'new')
    assert report['dependency_invalidated']==[ids[1]]
    for fid in ids[:2]:
        assert report['fact_id_map'][fid] in net.graph.revoked_ids()
        with pytest.raises((ValueError,KeyError)):
            net.graph.get(report['fact_id_map'][fid])
    assert net.truth(g['supports'][next(iter(g['supports']))]['requirement_claim_ids'][0])=='OPEN'
    assert not net.ready_supports()
    assert (tmp_path/'new/migration/legacy_revocation_log.jsonl').read_bytes()==(root/'revocation_log.jsonl').read_bytes()


@pytest.mark.parametrize('boundary',['fact_imported','before_state_commit','migration_completed'])
def test_interrupted_import_is_reentrant_without_duplicates(tmp_path,boundary):
    root,g,run,ids=legacy(tmp_path)
    fired=[]
    def interrupt(name,**kwargs):
        if name==boundary and not fired:
            fired.append(True)
            raise KeyboardInterrupt('simulated process interruption')
    with pytest.raises(KeyboardInterrupt):
        migrate(root,tmp_path/'new',on_event=interrupt)
    result=migrate(root,tmp_path/'new')
    assert result['active_facts']==3
    assert len(Network(tmp_path/'new').data['studies'])==4
    memory=LocalMemory(tmp_path/'new/workers'/('study-'+g['target_obligation_id'])).read('notes')
    keys=[r['record']['source_key'] for r in memory]
    assert len(keys)==len(set(keys))
    assert len(GlobalMemory(tmp_path/'new').read('direction'))==4


def test_source_mutation_and_nonempty_destination_rejected(tmp_path):
    root,*_=legacy(tmp_path)
    occupied=tmp_path/'occupied';occupied.mkdir();(occupied/'untouched').write_text('keep')
    with pytest.raises(ValueError,match='empty'):
        migrate(root,occupied)
    migrate(root,tmp_path/'new')
    (root/'extra.json').write_text('{}')
    with pytest.raises(ValueError,match='source changed'):
        migrate(root,tmp_path/'new')
    with pytest.raises(ValueError,match='separate destination'):
        migrate(root,root/'child')


def test_path_escape_in_study_pointer_rejected(tmp_path):
    root,g,run,ids=legacy(tmp_path)
    run['studies']['study-evil']='../../outside.json'
    write(root/'continuous_run/state.json',run)
    with pytest.raises(ValueError,match='escapes'):
        migrate(root,tmp_path/'new')


def test_legacy_fact_corruption_never_imported(tmp_path):
    root,g,run,ids=legacy(tmp_path)
    path=root/'facts'/(ids[0]+'.md')
    path.write_text(path.read_text().replace('Original proof A','Different proof'))
    with pytest.raises(ValueError,match='content hash'):
        migrate(root,tmp_path/'new')
    assert not (tmp_path/'new/fact_graph').exists()
