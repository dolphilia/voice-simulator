"""未完評価の内容・費用・固定資産を監査して終了する。"""
from collections import Counter
import time
from campaign import *

def main():
    b=LocalBudget()
    with b.job('audit','内容320記録・隔離32生成・固定資産・容量を終了監査',2_000_000):
        source=read(RESULT/'source-contract.json')
        for name,sha in source['source_hashes'].items():assert digest(ROOT/name)==sha
        for name,sha in {**source['source_models'],**source['source_support_contracts']}.items():assert digest(REPO/name)==sha
        assert source['source_protocol_sha256']==digest(SRES/'protocol.json')==digest(RESULT/'protocol.json')
        for r in read(RESULT/'render-manifest.json')['rows']:
            assert digest(REPO/r['source_record'])==r['source_record_sha256'] and digest(REPO/r['wav'])==r['wav_sha256']
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        records=[read(p) for p in (RESULT/'asr').rglob('*.json')];assert len(records)==320
        runtime=read(RESULT/'runtime-audit.json');assert runtime['passed'] and len(runtime['rows'])==32
        for i,r in enumerate(runtime['rows']):assert digest(RESULT/'runtime-audit'/f'isolated-{i:02d}.wav')==r['wav_sha256']==r['normal_wav_sha256']
        summary=read(RESULT/'summary.json');assert not summary['quality_certified'] and not summary['all_requirements_met']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'old_diagnostic_waves':160,
            'isolated_waves':32,'asr_records':320,'asr_completed':sum(r['status']=='completed' for r in records),
            'source_and_old_assets_unchanged':True,'previous_seals_verified':len(seals),
            'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),'pending_processes':[],
            'no_new_fit_inverse_teacher_download':True,'quality_certified':False,'all_requirements_met':False})
    events=b.events();starts=[e for e in events if e['event']=='start'];ends=[e for e in events if e['event']=='finish']
    assert {e['id'] for e in starts}=={e['id'] for e in ends}
    counts=Counter()
    for e in starts:counts[e['kind']]+=e.get('count',1)
    assert counts['render']==32 and counts['ai']==sum(r.get('ai_calls',0) for r in records)<=320
    assert counts['train']==counts['teacher']==0
    inv=b.inventory();seconds=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert inv['bytes']+65536<100_000_000 and seconds<3600
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'asr_reused':sum(r.get('ai_calls')==0 for r in records),
        'all_reserved_jobs_finished':True,'reserved_job_failures':sum(e['status']!='completed' for e in ends),
        'source_download_bytes':0,'resource_limit_compliance':True,'inventory_before_report':inv,
        'seconds_before_report':seconds,'no_automatic_extension':True})
    save(RESULT/'closeout.json',{'campaign_closed':True,'quality_goal_completed':False,'pending_processes':[],
        'qualifications':summary['qualifications'],'runtime_independence_passed':True,'no_automatic_extension':True,
        'next_campaign_started':False,'current_turn_classification':'progress'})
    print({'counts':dict(counts),'seconds':seconds,'bytes':inv['bytes'],'qualifications':summary['qualifications']},flush=True)

if __name__=='__main__':main()
