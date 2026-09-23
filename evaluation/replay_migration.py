"""Zero-model historical migration/semantic replay. Sources are always read-only.

Usage: python evaluation/replay_migration.py --sources frozen_sources.json --output workspaces/replay
The JSON source file is a list of {name, workspace}; freeze it before execution.
"""
import argparse
import json
from pathlib import Path

from danus.core.durable_io import atomic_json, immutable_json, read_json
from danus.core.local_memory import LocalMemory
from crpn.migrate import migrate, source_hashes, _legacy_data
from crpn.model import Network
from crpn.scheduler import focus
from substrate.store import lane


def replay_case(source,destination):
    source=Path(source)
    before=source_hashes(source)
    old,run,claims,facts,order,revoked,invalidated=_legacy_data(source)
    report=migrate(source,destination)
    net=Network(destination)
    id_map=report['fact_id_map']
    expected_truth={cid:('DISCHARGED' if any(f not in invalidated for f in old['fact_bindings'].get(cid,[]))
                        else 'REFUTED' if cid in old.get('refutations',{}) else 'OPEN') for cid in claims}
    assert report['truth']==expected_truth
    for old_id in order:
        new_id=id_map[old_id]
        if old_id in invalidated:
            assert new_id in net.revoked_ids()
            assert new_id not in net.proof_ids()
            continue
        fact=net._accepted(new_id)
        assert fact.statement==facts[old_id]['statement']
        assert fact.proof==facts[old_id]['proof']
        assert set(fact.predecessors)=={id_map[f] for f in facts[old_id]['predecessors']}
        assert all(f.fact_id not in net.revoked_ids() for f in net.supporting_closure(new_id))
    ready_before={sid for sid,row in old['supports'].items() if row['bridge_fact_id'] not in invalidated
                  and expected_truth[row['conclusion_claim_id']]=='OPEN'
                  and all(expected_truth[c]=='DISCHARGED' for c in row['requirement_claim_ids'])}
    assert {r['support_id'] for r in net.ready_supports()}=={report['support_id_map'][sid] for sid in ready_before}
    for sid in run['studies']:
        old_study=read_json(source/'continuous_run'/run['studies'][sid])
        study=net.data['studies'][sid]
        for key in ('claim_id','scope','focus','revision'):
            assert study.get(key)==old_study.get(key)
        assert study['last_served_visit']==run['schedule'].get('last_served',{}).get(sid,-1)
        notes=LocalMemory(lane(destination,sid)).read('notes')
        assert any(row['record'].get('source_record',{}).get('continuation')==old_study.get('continuation') for row in notes)
        assert all(row['record'].get('authority')=='UNVERIFIED_RESEARCH' for row in notes)
        assert not {'known_fact_ids','evidence_refs','material_refs','displayed_refs'} & study.keys()
    active=net.active_studies()
    if active:
        exposure,next_schedule=focus(active,net.data['schedule'])
        assert net.data['schedule']==run['schedule']  # exposure is not service
        assert next_schedule['channel_cursor']==run['schedule'].get('channel_cursor',0)+1
    else:
        exposure,next_schedule=None,None
    # Every ready composition has its actual certificate and condition Facts.
    for row in net.ready_supports():
        material=net.support_materials(row['support_id'])
        assert row['bridge_fact_id'] in {f.fact_id for f in material['facts']}
        assert all(net.truth(cid)=='DISCHARGED' for cid in row['requirement_claim_ids'])
    # Historical active representation views suppress scheduling, never root truth.
    aliases={}
    for sid,row in net.data['representations'].items():
        aliases[row['claim_id']]=net.alias_of(row['claim_id'])
        assert net.truth(row['claim_id'])==expected_truth[row['claim_id']]
        if aliases[row['claim_id']]:
            assert all(s.get('claim_id')!=row['claim_id'] for s in active)
    post=source_hashes(destination)
    assert migrate(source,destination)==report
    assert source_hashes(destination)==post
    assert source_hashes(source)==before
    result={**report,'checks':{'exact_statement_and_proof_preserved':True,'predecessor_mapping_complete':True,
        'truth_matches_frozen_state':True,'ready_supports_match':True,'research_notes_preserved':True,
        'old_material_permissions_not_imported':True,'exposure_did_not_service_study':True, 'last_service_order_preserved':True,
        'idempotent_import_bytes_unchanged':True,'source_bytes_unchanged':True},
        'next_exposure':exposure,'alias_views':aliases,'new_mathematics':False}
    atomic_json(Path(destination)/'migration/historical_replay.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    sources=read_json(args.sources)
    args.output.mkdir(parents=True,exist_ok=True)
    immutable_json(args.output/'preregistration.json',{'sources':sources,'model_calls':0,
        'purpose':'Migration and deterministic strategy semantics, not mathematical capability evaluation.'})
    results=[]
    for entry in sources:
        name=entry['name']
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in name):
            raise ValueError('invalid case name')
        result=replay_case(entry['workspace'],args.output/name)
        results.append(result)
        print(json.dumps({k:result[k] for k in ('source','active_facts','revoked_facts','claims','supports','studies','effective_depth','target_truth','model_calls')},ensure_ascii=False),flush=True)
    atomic_json(args.output/'aggregate.json',{'cases':results,'model_calls':0,'all_checks_passed':True})
    return 0


if __name__=='__main__':
    raise SystemExit(main())
