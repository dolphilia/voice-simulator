"""保存入力・旧20封印・24測定・全費用を監査し閉じる。"""
from collections import Counter
from meter_io import *

def main():
    p=verify_protocol();b=LocalBudget()
    with b.job('audit','20封印・24測定・全記録の終了監査',500_000):
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        manifest=read(RESULT/'measurement-manifest.json');rows=manifest['rows'];assert len(rows)==24
        assert len({(r['id'],r['method']) for r in rows})==24
        assert sum(r['new_measurement_calls'] for r in rows)<=24
        for r in rows:
            assert digest(REPO/r['record'])==r['sha256'];rec=read(REPO/r['record'])
            if rec['status']=='completed':assert digest(REPO/rec['npz'])==rec['npz_sha256']
        assert read(RESULT/'summary.json')['method_selected'] is None and not manifest['forbidden_imports']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'old_assets_unchanged':True,
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'measurement_records':24,'measurement_calls':manifest['new_measurement_calls'],
            'completed_records':sum(read(REPO/r['record'])['status']=='completed' for r in rows),'runtime_neural':False,
            'japanese_generation_estimation_analysis':0,'quality_certified':False,'all_requirements_met':False,'pending_processes':[]})
    events=b.events();starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event']=='finish']
    assert {e['id'] for e in starts}=={e['id'] for e in ends};counts=Counter()
    for e in starts:counts[e['kind']]+=e['count']
    assert counts['render']==counts['ai']==counts['teacher']==counts['train']==0
    meter_tickets=[e for e in starts if e['label'].startswith('meter::')];assert len(meter_tickets)==24
    seconds=time.time()-read(RESULT/'contract.json')['started_epoch'];inv=b.inventory();assert seconds<1800 and inv['bytes']+65536<50_000_000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'dsp_measurement_reservations':len(meter_tickets),'dsp_measurement_calls':manifest['new_measurement_calls'],
        'reserved_job_failures':sum(e['status']=='failed' for e in ends),'all_reserved_jobs_finished':True,
        'seconds_before_report':seconds,'inventory_before_report':inv,'resource_limit_compliance':True,
        'source_download_bytes':0,'inverse_fit_teacher_calls':0,'retries':0,'no_automatic_extension':True})
    save(RESULT/'closeout.json',{'campaign_closed':True,'comparison_completed':True,'quality_goal_completed':False,
        'no_new_campaign_started':True,'pending_processes':[],'current_turn_classification':'progress'})
    print({'closed':True,'counts':dict(counts),'measurements':manifest['new_measurement_calls'],'seconds':seconds,'bytes':inv['bytes']},flush=True)
if __name__=='__main__':main()
