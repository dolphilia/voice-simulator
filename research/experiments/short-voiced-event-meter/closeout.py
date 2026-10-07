"""旧封印・一回生成・固定測定・全費用を監査して終了する。"""
from collections import Counter
from event_io import *

def main():
    p=verify_protocol();b=LocalBudget()
    with b.job('audit','18封印・24生成・24非学習測定の終了監査',500_000):
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        renders=read(RESULT/'render-manifest.json')['rows'];measures=read(RESULT/'measurement-manifest.json')['rows']
        assert len(renders)==len(measures)==24 and read(RESULT/'regression.json')['saved_waves']==54
        for item in renders:
            assert digest(REPO/item['record'])==item['sha256'];r=read(REPO/item['record'])
            if r['status']=='completed':assert digest(REPO/r['wav'])==r['wav_sha256'] and r['E0_pass']
        for item in measures:
            assert digest(REPO/item['record'])==item['sha256'];r=read(REPO/item['record'])
            if r['status']=='completed':assert digest(REPO/r['npz'])==r['npz_sha256']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'source_and_old_assets_unchanged':True,
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'render_records':len(renders),'dio_records':len(measures),'regression_rows':len(read(RESULT/'regression.json')['rows']),
            'quality_certified':False,'all_requirements_met':False,'pending_processes':[]})
    events=b.events();starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event']=='finish']
    assert {e['id'] for e in starts}=={e['id'] for e in ends};counts=Counter()
    for e in starts:counts[e['kind']]+=e['count']
    assert counts['render']==24 and counts['ai']==counts['teacher']==counts['train']==0
    calls=sum(r['new_dio_calls'] for r in measures);assert calls<=24
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory();assert seconds<1800 and inv['bytes']+65536<50_000_000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'dsp_measurements':calls,'reserved_job_failures':sum(e['status']=='failed' for e in ends),
        'all_reserved_jobs_finished':True,'seconds_before_report':seconds,'inventory_before_report':inv,'resource_limit_compliance':True,
        'source_download_bytes':0,'inverse_fit_teacher_calls':0,'no_automatic_extension':True})
    save(RESULT/'closeout.json',{'campaign_closed':True,'comparison_completed':True,'quality_goal_completed':False,
        'no_new_campaign_started':True,'pending_processes':[],'current_turn_classification':'progress'})
    print({'closed':True,'counts':dict(counts),'dio_calls':calls,'seconds':seconds,'bytes':inv['bytes']},flush=True)
if __name__=='__main__':main()
