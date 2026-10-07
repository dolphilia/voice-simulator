"""3fit・192生成・320評価記録・保存出典・上限を終了監査する。"""
from collections import Counter
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from checks import invariant, tests
from centered_projection import tests as projection_tests


def main():
    b=LocalBudget()
    with b.job('audit','共有fit・全生成・隔離・認識再利用・旧封印・上限の終了監査',2000000):
        p=read(RESULT/'protocol.json')
        for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        targets=read(RESULT/'target-manifest.json');assert targets['qualified_utterances']==17 and targets['fit_supported']
        for row in targets['rows']:assert digest(REPO/row['source_search'])==row['source_sha256']
        for row in p['training_rows']+p['selection_rows']:
            for n,sha in [('source_training_input','source_sha256'),('teacher_metadata','teacher_metadata_sha256'),('teacher_wav','teacher_wav_sha256')]:assert digest(REPO/row[n])==row[sha]
        models=read(RESULT/'model-comparison.json');assert read(RESULT/'training-contract.json')['training_utterances']==17
        for n,sha in models['model_hashes'].items():assert digest(RESULT/'models'/n)==sha
        for n,proof in models['old_state_target_models'].items():assert digest(REPO/proof['path'])==proof['sha256']
        manifest=read(RESULT/'render-manifest.json');assert len(manifest['rows'])==160 and manifest['search_completed_before_asr']
        ai=[]
        for row in manifest['rows']:
            if row['status']=='completed':
                assert digest(ROOT/row['wav'])==row['wav_sha256'] and row['E0_pass'] and row['internal_unchanged'] and row['maximum_abs_half_tone']<=3.
                import numpy as np
                invariant(row['state_snapshot_before'],row['state_snapshot_after'],np.load((ROOT/row['wav']).with_suffix('.npz'))['state_deltas'])
            for engine in ('whisper','reazon'):
                result=read(RESULT/'asr'/engine/(row['id']+'.json'));ai.append(result)
                if result['status']=='completed':
                    assert result['wav_sha256']==row['wav_sha256'] and result['protocol_sha256']==digest(RESULT/'protocol.json')
                    if result['ai_calls']==0:
                        path=REPO/result['reused_from'];previous=read(path)
                        assert digest(path)==result['reused_result_sha256'] and previous['wav_sha256']==result['wav_sha256'] and previous['text']==result['text']
                        assert previous['engine']==result['engine'] and previous['protocol_sha256']==result['original_protocol_sha256']
                        for key in ('hypothesis','reference_kana','predicted_kana','errors','characters'):assert previous[key]==result[key]
                        proof=read(RESULT/'asr-reuse-contract.json')['source_results'].get(str(path.relative_to(REPO)))
                        assert result['original_evaluation_contract_sha256']==(proof['engine_contract_sha256'] if proof else digest(RESULT/'engine-contract.json'))
        runtime=read(RESULT/'runtime-audit.json');assert runtime['passed'] and len(runtime['rows'])==32
        for r in runtime['rows']:assert r['same_wav_sha256'] and r['wav_sha256']==r['normal_wav_sha256']
        assert read(RESULT/'negative-tests.json')['selection']==tests() and read(RESULT/'negative-tests.json')['projection']==projection_tests()
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'training_utterances':17,'shared_models_fitted':3,
            'diagnostic_waves':len(manifest['rows']),'completed_diagnostic_waves':manifest['completed'],'isolated_waves':32,
            'asr_records':len(ai),'completed_asr_records':sum(r['status']=='completed' for r in ai),'asr_reused_records':sum(r.get('ai_calls')==0 and r['status']=='completed' for r in ai),
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),'source_and_assets_unchanged':True,
            'no_optimization_after_asr':True,'pending_processes':[],'all_requirements_met':False,'quality_certified':False,'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish'];assert len(starts)==len(ends)
    counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==192 and counts['train']==3 and counts['ai']==sum(r.get('ai_calls',0) for r in ai)<=320 and counts['teacher']==0
    failed=[e for e in ends if e['status']!='completed']
    assert sum(starts[e['id']]['kind']=='ai' for e in failed)==sum(r['status']=='failed' and r.get('ai_calls')==1 for r in ai)
    for kind,count in [('render',193),('ai',321),('train',4),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限を拒否しません')
    assert b.events()==events;inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<350000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':failed,'all_jobs_finished':True,'seconds_before_report':elapsed,
        'inventory_before_cost_audit':inv,'source_download_bytes':0,'no_new_inverse':True,'unused_render_calls':0,
        'unused_ai_calls':320-counts['ai'],'unused_shared_fits':0,'no_automatic_extension':True,'no_further_generation_evaluation_training':True})
    print({'counts':dict(counts),'failed_jobs':len(failed),'seconds':elapsed,'bytes':inv['bytes']},flush=True)

if __name__=='__main__':main()
