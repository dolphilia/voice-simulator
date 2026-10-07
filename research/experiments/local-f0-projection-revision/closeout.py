"""限定比較の上限・固定資産・負例・旧成果を監査する。"""
from collections import Counter
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from summarize import paired

def main():
    b = LocalBudget()
    with b.job('audit','内容・不変性・固定資産・旧封印・欠損負例の終了監査',1000000):
        seals=read(RESULT/'input-preservation.json')['seals']
        assert [check_seal(REPO/p['seal']) for p in seals] == seals
        for name in ('protocol.json','render-contract.json','evaluation-contract.json'):
            for p,sha in read(RESULT/name)['source_hashes'].items(): assert digest(ROOT/p)==sha
        for p,sha in read(RESULT/'model-comparison.json')['model_hashes'].items(): assert digest(RESULT/'models'/p)==sha
        for p,sha in read(RESULT/'engine-contract.json')['asr_model_hashes'].items(): assert digest(REPO/p)==sha
        manifest=read(RESULT/'render-manifest.json')
        assert manifest['completed']==len(manifest['rows'])==64 and not manifest['development_rows']
        for row in manifest['rows']:
            assert row['status']=='completed' and digest(ROOT/row['wav'])==row['wav_sha256']
            assert row['evaluation']['E0_pass'] and row['maximum_abs_half_tone']<=3 and len(row['internal_unchanged'])==5
            for engine in ('whisper','reazon'):
                a=read(RESULT/'asr'/engine/(row['id']+'.json'))
                assert a['status']=='completed' and a['wav_sha256']==row['wav_sha256']
        assert read(RESULT/'entry-audit.json')['passed'] and read(RESULT/'runtime-audit.json')['passed']
        for p,sha in read(RESULT/'bundle/manifest.json')['files'].items(): assert digest(RESULT/'bundle'/p)==sha
        f={'text_id':'fixture','status':'completed','errors':1,'native_errors':1,'characters':8}
        assert paired([f])['observed_non_worsening']
        assert not paired([])['observed_non_worsening']
        assert not paired([f,{'text_id':'fixture','status':'missing'}])['observed_non_worsening']
        assert not paired([{**f,'errors':2}])['observed_non_worsening']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'diagnostic_wavs':64,'completed_ai_results':128,
            'failed_or_missing_asr':0,'runtime_exact_match_pairs':4,'entry_exact_match':True,'previous_seals_verified':len(seals),
            'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),'models_and_frozen_source_hashes_match':True,
            'negative_missing_empty_worsening_tests':True,'pending_processes':[],'all_requirements_met':False,'quality_certified':False,
            'unresolved':read(RESULT/'summary.json')['unresolved'],'fresh_resumed_turn':1,'current_turn_classification':'progress'})
    events=b.events(); starts={e['id']:e for e in events if e['event']=='start'}; finishes=[e for e in events if e['event']=='finish']
    assert len(starts)==len(finishes)
    for kind in ('ai','teacher','train'):
        try: b.reserve(kind,'終了前の上限拒否検査')
        except RuntimeError: pass
        else: raise AssertionError('上限・禁止処理が拒否されません')
    assert b.events()==events
    counts=Counter()
    for e in starts.values(): counts[e['kind']]+=e['count']
    failed=[e for e in finishes if e['status']!='completed']
    assert counts['render']==80 and counts['ai']==128 and counts['train']==counts['teacher']==0 and not failed
    contract=read(RESULT/'contract.json'); inv=b.inventory(); elapsed=time.time()-contract['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<100000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':failed,'all_jobs_finished':True,'limits':contract['limits'],
        'seconds_before_report':elapsed,'inventory_before_cost_audit':inv,'source_download_bytes':0,
        'no_further_generation_evaluation_training':True,'unused_render_calls':16,'unused_ai_calls':0,'no_automatic_extension':True})
    print({'counts':dict(counts),'seconds':elapsed,'bytes':inv['bytes']})

if __name__=='__main__': main()
