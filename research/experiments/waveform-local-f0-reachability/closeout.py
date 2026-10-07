"""終了した比較の上限、出典、失敗、欠損判定、旧成果を監査する。"""
from collections import Counter
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from objective import tests
from summarize import paired


def main():
    b=LocalBudget()
    with b.job('audit','固定出典・試行・ASR再利用・旧封印・上限の終了監査',1000000):
        seals=read(RESULT/'input-preservation.json')['seals']
        assert [check_seal(REPO/s['seal']) for s in seals]==seals
        for n,sha in read(RESULT/'protocol.json')['source_hashes'].items():assert digest(ROOT/n)==sha
        for row in read(RESULT/'protocol.json')['rows']:
            for p,sha in [(row['source_training_input'],row['source_sha256']),
                          (row['teacher_metadata'],row['teacher_metadata_sha256']),(row['teacher_wav'],row['teacher_wav_sha256'])]:
                assert digest(REPO/p)==sha
        for n,sha in read(RESULT/'engine-contract.json')['asr_model_hashes'].items():assert digest(REPO/n)==sha
        manifest=read(RESULT/'render-manifest.json');assert len(manifest['rows'])==12
        ai_results=[]
        for row in manifest['rows']:
            if row['status']=='completed':
                assert digest(ROOT/row['wav'])==row['wav_sha256'] and row['E0_pass'] and row['internal_unchanged']
            for engine in ('whisper','reazon'):
                r=read(RESULT/'asr'/engine/(row['id']+'.json'));ai_results.append(r)
                if r['status']=='completed':
                    assert r['wav_sha256']==row['wav_sha256']
                    if r['ai_calls']==0:
                        source=RESULT/r['reused_from'];assert digest(source)==r['reused_result_sha256']
                        other=read(source);assert other['wav_sha256']==r['wav_sha256'] and other['text']==r['text'] and other['engine']==r['engine']
                        for k in ('hypothesis','reference_kana','predicted_kana','errors','characters'):assert other[k]==r[k]
        attempts=[read(p) for p in (RESULT/'render').rglob('*.json') if p.stem not in ('support-contract','state-inverse')]
        assert all(r['maximum_abs_half_tone']<=3 for r in attempts if r['status']=='completed')
        negative=tests();assert read(RESULT/'negative-tests.json')==negative
        fixture={'text_id':'f','status':'completed','errors':1,'native_errors':1,'characters':8}
        assert paired([fixture])['non_worsening'] and not paired([])['non_worsening']
        assert not paired([fixture,{'text_id':'f','status':'missing'}])['non_worsening']
        assert not paired([{**fixture,'errors':2}])['non_worsening']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'render_attempt_records':len(attempts),
            'final_rows':12,'completed_final_rows':manifest['completed'],'completed_asr_rows':sum(r['status']=='completed' for r in ai_results),
            'asr_reuse_rows':sum(r.get('ai_calls')==0 and r['status']=='completed' for r in ai_results),
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'source_and_assets_unchanged':True,'negative_support_acceptance_missing_tests':True,'pending_processes':[],
            'all_requirements_met':False,'quality_certified':False,'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish']
    assert len(starts)==len(ends)
    counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==len(attempts)<=116 and counts['ai']==sum(r.get('ai_calls',0) for r in ai_results)<=24
    assert counts['teacher']==counts['train']==0
    for kind,count in [('ai',33),('render',129),('train',1),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限を拒否しません')
    assert b.events()==events
    failed=[e for e in ends if e['status']!='completed']
    assert len(failed)==sum(r['status']!='completed' for r in attempts)
    contract=read(RESULT/'contract.json');inv=b.inventory();elapsed=time.time()-contract['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<100000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':failed,'all_jobs_finished':True,'limits':contract['limits'],
        'seconds_before_report':elapsed,'inventory_before_cost_audit':inv,'source_download_bytes':0,
        'unused_render_calls':128-counts['render'],'unused_ai_calls':32-counts['ai'],'no_automatic_extension':True,
        'no_further_generation_evaluation_training':True})
    print({'counts':dict(counts),'failed_jobs':len(failed),'seconds':elapsed,'bytes':inv['bytes']})

if __name__=='__main__':main()
