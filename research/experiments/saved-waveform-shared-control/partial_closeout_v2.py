"""容量上限超過で止めた部分比較を、証拠・未実施・修復を含め終了監査する。"""
from collections import Counter
import gzip
import hashlib
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, read, save, digest, check_seal
from checks import invariant
from summarize import mse_groups
from storage_preflight import tests as storage_tests
import numpy as np


def main():
    b=LocalBudget()
    with b.job('audit','上限超過・可逆圧縮・160波形・未実施比較の終了監査',2000000):
        p=read(RESULT/'protocol.json');archive=read(RESULT/'lossless-archive.json')
        assert archive['resource_limit_violation'] and digest(RESULT/archive['compressed_path'])==archive['compressed_sha256']
        with gzip.open(RESULT/archive['compressed_path'],'rb') as f:
            decoded=f.read();assert hashlib.sha256(decoded).hexdigest()==archive['original_sha256']
        import json
        manifest=json.loads(decoded);records={r['id']:r for r in manifest['rows']};assert len(records)==160
        for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
        for n,sha in read(RESULT/'recovery-source-contract.json')['source_hashes'].items():assert digest(ROOT/n)==sha
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        for row in manifest['rows']:
            assert row['status']=='completed' and row['E0_pass'] and row['internal_unchanged']
            assert digest(ROOT/row['wav'])==row['wav_sha256']
            invariant(row['state_snapshot_before'],row['state_snapshot_after'],np.load((ROOT/row['wav']).with_suffix('.npz'))['state_deltas'])
            original=RESULT/'render'/PathParts(row['id'])
            assert read(original)==row
        models=read(RESULT/'model-comparison.json')
        for n,sha in models['model_hashes'].items():assert digest(RESULT/'models'/n)==sha
        assert read(RESULT/'training-contract.json')['training_utterances']==17
        assert not any((RESULT/n).exists() for n in ('asr','runtime-audit','bundle','runtime-audit.json'))
        engineering={}
        for v in p['variants'][1:]:
            control=[];mse=[]
            for row in manifest['rows']:
                if row['variant']!=v:continue
                native=records[row['id'].rsplit('/',1)[0]+'/native']
                diff={f:row['measurement'][f]/native['measurement'][f]-1 for f in ('f0_hz','dio_f0_hz','active_seconds')}
                control.append({'id':row['id'],'split':row['split'],'relative':diff,'support_complete':row['support_complete'],
                    'missing_support':row['missing_support'],'control_protected':all(abs(diff[f])<=limit for f,limit in [('f0_hz',.05),('dio_f0_hz',.05),('active_seconds',.03)])})
                if row['split']=='selection':mse.append({'text_id':row['id'].split('/')[0],'length':row['length'],'condition':row['condition'],'wave_mse':row['wave_mse'],'native_mse':native['wave_mse']})
            engineering[v]={'rows':control,'selection_mse_groups':mse_groups(mse),'support_missing_conditions':sum(not r['support_complete'] for r in control),
                'global_control_failed_conditions':sum(not r['control_protected'] for r in control),'content_evaluated':False,'research_qualified':False}
        save(RESULT/'partial-summary.json',{'engineering':engineering,'training_mse':models['training_mse'],'shared_models_fitted':3,'generated_diagnostic_waves':160,
            'planned_isolated_waves':32,'actual_isolated_waves':0,'planned_asr_records':320,'actual_asr_records':0,
            'stop_reason':'保存実装の不備による容量上限超過','resource_limit_violation':True,'content_evaluated':False,'runtime_independence_evaluated':False,
            'qualifications_complete':False,'quality_certified':False,'all_requirements_met':False,'no_optimization_after_asr':True})
        save(RESULT/'storage-preflight-tests.json',storage_tests())
        save(RESULT/'completion-audit-v2.json',{'authorized_comparison_completed':False,'authorized_campaign_closed_at_limit':True,
            'shared_models_fitted':3,'training_utterances':17,'diagnostic_waves':160,'isolated_waves':0,'asr_records':0,
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'saved_manifest_lossless_verified':True,'original_per_wave_records_unchanged':True,'source_and_old_assets_unchanged':True,
            'resource_limit_violation':True,'pending_processes':[],'quality_certified':False,'all_requirements_met':False,
            'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish'];assert len(starts)==len(ends)
    counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==160 and counts['train']==3 and counts['ai']==counts['teacher']==0
    assert all(e['status']=='completed' for e in ends)
    for kind,count in [('render',193),('ai',321),('train',4),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限を拒否しません')
    assert b.events()==events;inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<350000000
    save(RESULT/'cost-audit-v2.json',{'counts':dict(counts),'all_reserved_jobs_finished':True,'reserved_job_failures':0,
        'unreserved_action_rejections':[{'action':'非ニューラルbundle setup','reason':'容量の上限です','calls_started':0}],
        'resource_limit_compliance':False,'resource_limit_violation':True,'peak_observed_bytes':archive['inventory_peak_during_lossless_recovery_bytes'],
        'before_recovery_bytes':archive['inventory_before_recovery_bytes'],'final_inventory_before_report':inv,'seconds_before_report':elapsed,
        'source_download_bytes':0,'new_inverse_calls':0,'remaining_isolated_renders':32,'remaining_ai_calls':320,
        'no_automatic_extension':True,'no_further_generation_evaluation_training':True})
    print({'counts':dict(counts),'seconds':elapsed,'bytes_after_lossless_recovery':inv['bytes'],'resource_limit_compliance':False},flush=True)


def PathParts(identity):
    from pathlib import Path
    parts=identity.split('/');return Path(*parts[:-1])/(parts[-1]+'.json')

if __name__=='__main__':main()
