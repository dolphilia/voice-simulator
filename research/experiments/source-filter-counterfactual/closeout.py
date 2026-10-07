"""成功・停止のどちらも旧資産と全費用を保存して閉じる。"""
from collections import Counter
from campaign import *

def main():
    b=LocalBudget();stopped=(RESULT/'stop.json').exists()
    with b.job('audit','旧17封印と54生成・54非学習測定の終了監査',2000000):
        p=read(RESULT/'protocol.json')
        for name,sha in p['source_hashes'].items():assert digest(ROOT/name)==sha
        for name,sha in p['dependencies'].items():assert digest(REPO/name)==sha
        for row in p['rows']:
            for name,sha in [('source_record','source_record_sha256'),('wav','wav_sha256'),('parameter_lf0_source_npz','parameter_lf0_source_npz_sha256'),('support_contract','support_contract_sha256')]:assert digest(REPO/row[name])==row[sha]
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        records=[read(path) for path in (RESULT/'render').rglob('*.json')]
        if not stopped:
            assert len(records)==54 and read(RESULT/'baseline-gate.json')['passed'] and (RESULT/'summary.json').is_file()
            assert all(r['status']=='completed' and r['finite'] and not r['forbidden_imports'] for r in records)
            for r in records:assert digest(REPO/r['wav'])==r['wav_sha256']
        else:
            assert not (RESULT/'baseline-gate.json').exists() or read(RESULT/'stop.json')['additional_contrasts_started']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':not stopped,'source_and_old_assets_unchanged':True,
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'records':len(records),'dsp_f0_measurements_completed':sum('measurement' in r for r in records),'pending_processes':[],
            'quality_certified':False,'all_requirements_met':False})
    events=b.events();starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event']=='finish']
    assert {e['id'] for e in starts}=={e['id'] for e in ends};counts=Counter()
    for e in starts:counts[e['kind']]+=e.get('count',1)
    assert counts['render']<=54 and counts['ai']==counts['teacher']==counts['train']==0
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory()
    assert seconds<3600 and inv['bytes']+65536<100000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'dsp_measurements_completed':sum('measurement' in r for r in records),
        'reserved_job_failures':sum(e['status']=='failed' for e in ends),'all_reserved_jobs_finished':True,
        'seconds_before_report':seconds,'inventory_before_report':inv,'source_download_bytes':0,
        'resource_limit_compliance':True,'no_automatic_extension':True})
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'comparison_completed':not stopped,
        'no_new_campaign_started':True,'no_automatic_extension':True,'pending_processes':[],'current_turn_classification':'progress'})
    print({'counts':dict(counts),'seconds':seconds,'bytes':inv['bytes'],'completed':not stopped},flush=True)

if __name__=='__main__':main()
