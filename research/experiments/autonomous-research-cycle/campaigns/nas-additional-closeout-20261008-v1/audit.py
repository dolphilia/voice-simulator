"""第28回：全サイクルの契約・封印・会計・外部保存を実読取で照合する。"""
from paths import *
from collections import Counter
import os,sqlite3,subprocess,shutil,time
def verify():
    contract=read(HERE/'execution-contract.json')
    assert digest(HERE/'registration.json')==contract['registration_sha256']
    for n,h in contract['source_hashes'].items():assert digest(HERE/n)==h,n
    for n,h in contract['input_hashes'].items():assert digest(REPO/n)==h,n
    return contract
def main():
    contract=verify();b=Budget();b.recover();v=b.snapshot()
    assert len(v['campaigns'])==28 and not v['jobs']
    assert all(c['closed'] for n,c in v['campaigns'].items() if n!=NAME)
    cache={};hash_bytes=0
    def hashed(path):
        nonlocal hash_bytes
        physical=str(Path(path).resolve(strict=True))
        if physical not in cache:
            size=Path(physical).stat().st_size
            cache[physical]=dict(bytes=size,sha256=digest(physical))
            hash_bytes+=size
        return cache[physical]['sha256']
    with b.job(NAME,'audit','全27終了封印・52390移動・全外部・予算と一時を統合照合',reserve_bytes=80_000_000) as job:
        seals={};references=0
        for name,c in v['campaigns'].items():
            if name==NAME:continue
            p=ROOT/c['prefix']/'artifact-seal.json';seal=read(p)
            assert seal['path_base'] in ('repository',str(REPO))
            assert not seal.get('quality_goal_completed',False)
            for n,h in seal['files'].items():
                path=REPO/n
                assert not Path(n).is_absolute() and '..' not in Path(n).parts and path.is_file(),n
                assert hashed(path)==h,n
                references+=1
            seals[name]=dict(seal_sha256=digest(p),sealed_references_verified=len(seal['files']),
                experiment_completed=seal.get('experiment_completed',False),
                preparation_only=seal.get('preparation_only',False),quality_goal_completed=False,
                lifecycle=c,scientific_gate_unchanged=True)
            print('seal',name,len(seal['files']),flush=True)
        migration=REPO/'research/storage-migrations/2026-10-08-v1'
        plan=read(migration/'plan.json')
        for n,h in plan['sealed_documents'].items():assert hashed(REPO/n)==h,n
        db=migration/'manifest.sqlite'
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as con:
            rows=con.execute('SELECT name,physical,size,managed,status,sha256 FROM files ORDER BY name').fetchall()
        assert len(rows)==52390
        migrated_bytes=0;managed_count=0
        for i,(n,physical,size,managed,status,h) in enumerate(rows,1):
            logical=REPO/n;target=b.guard.root/physical
            assert status=='linked' and logical.is_symlink() and os.readlink(logical)==str(target),n
            assert target.is_file() and target.stat().st_size==size and hashed(target)==h,n
            migrated_bytes+=size;managed_count+=managed
            if i%5000==0:print('migration',i,len(rows),flush=True)
        assert migrated_bytes==21427485651
        locations=b.locations()
        for n,row in locations.items():
            target=b.guard.root/row['physical'];logical=ROOT/n
            assert logical.is_symlink() and os.readlink(logical)==str(target)
            assert target.stat().st_size==row['size'] and hashed(target)==row['sha256'],n
        frozen_inventory=b.reconcile();current=b.snapshot()
        running=current['jobs'];assert set(running)=={job}
        replay={};counts=Counter();failed=[];started=0;finished=0
        for line in (ROOT/'control/jobs.jsonl').read_text().splitlines():
            e=read_line(line)
            if e.get('event')=='start':
                assert e['id'] not in replay;replay[e['id']]=e
                counts[e['kind']]+=e['count'];started+=1
            elif e.get('event')=='finish':
                first=replay.pop(e['id']);assert first['campaign']==e['campaign'] and first['kind']==e['kind'] and first['count']==e['count']
                finished+=1
                if e['status']=='failed':failed.append(dict(id=e['id'],campaign=e['campaign'],kind=e['kind'],label=e['label'],error=e['error']))
        assert set(replay)==set(running) and dict(counts)==current['counts']
        total=Counter()
        for n,c in current['campaigns'].items():
            total.update(c['counts'])
            assert c['payload_bytes']<c['limits']['bytes']
            for k,used in c['counts'].items():assert used<=c['limits'][k],(n,k)
            duration=(current['seconds'] if not c['closed'] else c['end_seconds'])-c['start_seconds']
            assert duration<c['limits']['seconds'],(n,duration)
        assert dict(total)==current['counts']
        for k,used in current['counts'].items():
            if k in current['limits']:assert used<=current['limits'][k],k
        assert current['seconds']<current['limits']['seconds']-14400
        assert current['write_bytes']<current['limits']['write_bytes']
        works=current.get('temporary_work',{})
        assert all(w['status']=='removed' and w['absence_verified'] and not os.path.lexists(w['path']) for w in works.values())
        workbase=b.guard.root/'work'/b.storage['cycle_directory']
        assert not workbase.exists() or not list(workbase.iterdir())
        assert not (ROOT/'control/state.tmp').exists()
        config=read(ROOT/'control/storage-config.json');b.guard.check()
        free_internal=shutil.disk_usage(ROOT).free;free_external=shutil.disk_usage(b.guard.mount).free
        assert free_internal>=20_000_000_000 and free_external>=config['external_closing_bytes']+80_000_000
        ext_bytes=sum(row['size'] for row in locations.values())
        aliases=sum(row['alias_size'] for row in locations.values())
        overhead=sum(p.stat().st_size for p in (ROOT/'control').iterdir() if p.is_file())
        internal=current['payload_bytes']-ext_bytes+aliases+overhead
        assert internal<config['internal_experiment_bytes'] and ext_bytes<config['external_experiment_bytes']
        cross=read(PREVIOUS/'aggregate-summary.json');period=read(PERIOD/'aggregate-summary.json');scope=read(PERIOD/'scope-denominator-audit.json')
        assert cross['old_group_counts_exact_match'] and cross['total_wave_records']==992 and cross['total_existing_ASR_records']==1984
        assert all(not m['old_qualification'] for c in cross['cohorts'].values() for m in c['methods'].values())
        assert not current['continuation_checkpoint'].get('protected_confirmation_opened',False)
        b.write_data(HERE/'integrity-manifest.json',encode(dict(physical_file_hashes=cache,
            bytes_read_once=hash_bytes,hash_only_no_signal_decoding=True,
            protected_evaluation_text_not_used=True)),job)
        result=dict(prior_campaigns=seals,prior_sealed_references=references,
            distinct_physical_files_hashed=len(cache),distinct_bytes_hashed=hash_bytes,
            current_external_files_verified=len(locations),current_external_bytes=ext_bytes,
            moved_files_verified=len(rows),moved_bytes=migrated_bytes,moved_managed_files=managed_count,
            preexisting_seal_documents_verified=len(plan['sealed_documents']),
            hash_cache_avoided_duplicate_read=True,old_scientific_contracts_and_gates_unchanged=True,
            all_jobs_replay_exact=True,job_starts=started,job_finishes=finished,current_audit_job_only=True,
            global_and_campaign_counts_exact=True,failed_jobs_preserved=failed,
            temporary_owned_workspaces=len(works),all_temporary_removed=True,
            temporary_paths_physically_absent=True,no_unregistered_work_children=True,new_temporary_files=0,
            volume_UUID=config['volume_uuid'],marker_sha256=config['marker_sha256'],volume_guard_passed=True,
            real_free_internal=free_internal,real_free_external=free_external,
            internal_arc_bytes_including_aliases_control=internal,
            whole_external_usage_not_inferred_from_arc_only=True,
            heldout_evaluation_not_opened=True,protected_confirmation_opened=False,
            cross_factor_summary_sha256=digest(PREVIOUS/'aggregate-summary.json'),
            source_period_summary_sha256=digest(PERIOD/'aggregate-summary.json'),
            source_period_scope=scope,new_scientific_outputs=0,
            final_runtime_independence_not_retested=True,previous_runtime_evidence_preserved=True,
            quality_goal_completed=False,perceptual_qualification=False,
            stop_reason='campaigns_limit_reached',campaigns_used=28,campaigns_limit=28,
            remaining_other_limits_not_reusable_as_campaigns=True,
            budget_at_audit=current,integrity_manifest_sha256=digest(HERE/'integrity-manifest.json'))
        # 大きな稼働台帳は集計に埋め込まず、明示した観測断面の容量・回数だけを残す。
        result['budget_at_audit']=dict(seconds=current['seconds'],counts=current['counts'],
            payload_bytes=current['payload_bytes'],write_bytes=current['write_bytes'],limits=current['limits'])
        b.save(HERE/'aggregate-summary.json',result,job)
        b.save(HERE/'file-integrity-audit.json',dict(unique_files=len(cache),unique_bytes=hash_bytes,
            seal_references=references,current_external_files=len(locations),migrated_files=len(rows),
            all_expected_hashes_matched=True,read_only_no_copy_or_regeneration=True,
            protected_text_semantically_unopened=True),job)
    print('audit complete',b.reconcile(),flush=True)
def read_line(line):
    import json
    return json.loads(line)
if __name__=='__main__':main()
