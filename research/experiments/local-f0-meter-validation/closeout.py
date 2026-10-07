"""新24信号・48測定・93回帰・旧保存・上限を監査する。"""
from collections import Counter
import time
import numpy as np
from campaign import LocalBudget, ROOT, RESULT, REPO, WRES, read, save, digest, check_seal
from fixtures import tests as fixture_tests
from metrics import tests as metric_tests, aggregate, choose


def main():
    b=LocalBudget()
    with b.job('audit','既知正解・測定記録・再利用・上限・旧封印の終了監査',1000000):
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        protocol=read(RESULT/'protocol.json')
        for n,sha in protocol['source_hashes'].items():assert digest(ROOT/n)==sha
        for p,sha in protocol['world_files'].items():assert digest(REPO/p)==sha
        manifest=read(RESULT/'signal-manifest.json');assert manifest['completed']==len(manifest['rows'])==24
        source={r['id']:r for r in manifest['rows']}
        for row in protocol['rows']:
            s=source[row['id']];assert digest(ROOT/s['wav'])==s['wav_sha256'] and digest(ROOT/s['phase_file'])==s['phase_sha256']
            assert digest(ROOT/row['truth_file'])==row['truth_sha256'] and s['peak']<=.8000001 and s['phase_recovery_error_hz']<1e-6
        measurements=read(RESULT/'measurement-manifest.json');assert measurements['completed']==len(measurements['rows'])==48
        for r in measurements['rows']:
            assert r['wav_sha256']==source[r['id']]['wav_sha256'] and r['ai_calls']==0
            assert read(RESULT/'measurements'/r['method']/(r['id']+'.json'))==r
        dev={method:aggregate([r for r in measurements['rows'] if r['split']=='development' and r['method']==method]) for method in protocol['methods']}
        assert choose(dev)==read(RESULT/'development-selection.json')['selected_method']
        assert read(RESULT/'development-selection.json')['selection_frozen_before_confirmation']
        inputs=read(RESULT/'regression-inputs.json');assert digest(REPO/inputs['cached_harvest_file'])==inputs['cached_harvest_sha256']
        for row in inputs['rows']:
            r=read(RESULT/'regression'/(row['id']+'.json'));assert r['status']=='completed' and r['wav_sha256']==row['wav_sha256']
            assert r['harvest_reused']==row['harvest_reused']
        reg=read(RESULT/'regression-summary.json');assert reg['completed']==93 and reg['harvest_reused']==32 and reg['harvest_new_measurements']==61
        assert read(RESULT/'negative-tests.json')=={'fixtures':fixture_tests(),'metrics':metric_tests()}
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'new_signals':24,'completed_dsp_measurements':48,
            'regression_waves':93,'reused_harvest_results':32,'new_harvest_regression_measurements':61,
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'sources_and_truth_hashes_match':True,'negative_missing_octave_false_voice_boundary_tests':True,
            'selection_frozen_before_confirmation':True,'pending_processes':[],'all_requirements_met':False,'quality_certified':False,
            'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish']
    assert len(starts)==len(ends) and all(e['status']=='completed' for e in ends)
    counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==24 and counts['ai']==counts['train']==counts['teacher']==0
    for kind,count in [('render',9),('ai',1),('train',1),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限・禁止処理を拒否しません')
    assert b.events()==events
    contract=read(RESULT/'contract.json');inv=b.inventory();elapsed=time.time()-contract['started_epoch']
    assert elapsed<1800 and inv['bytes']+65536<50000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':[],'all_jobs_finished':True,'limits':contract['limits'],
        'seconds_before_report':elapsed,'inventory_before_cost_audit':inv,'source_download_bytes':0,'unused_render_calls':8,
        'unused_ai_calls':0,'no_further_generation_evaluation_training':True,'no_automatic_extension':True})
    print({'counts':dict(counts),'seconds':elapsed,'bytes':inv['bytes']})

if __name__=='__main__':main()
