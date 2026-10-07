"""目標不足で停止した比較を、実行していない段階も含め監査する。"""
from collections import Counter
import subprocess
import sys
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, GRES, read, save, digest, check_seal
from objective import tests
from guarded_derivative import tests as guard_tests
from centered_projection import tests as projection_tests
from integration_tests import tests as integration_tests
from inverse import qualify


def main():
    b=LocalBudget()
    with b.job('audit','資料不足停止・採否・上限・旧封印・共有fit拒否の終了監査',2000000):
        p=read(RESULT/'protocol.json');manifest=read(RESULT/'target-manifest.json')
        assert not manifest['fit_supported'] and manifest['qualified_utterances']==10 and len(manifest['rows'])==21
        for contract in ('protocol.json','diagnostic-source-contract.json'):
            for n,sha in read(RESULT/contract)['source_hashes'].items():assert digest(ROOT/n)==sha
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        assert read(RESULT/'entrance-audit.json')['passed'] and read(RESULT/'entrance-audit.json')['old_match_checks']==8
        attempts=[read(path) for path in (RESULT/'inverse-render').rglob('*.json') if path.stem not in ('support-contract','state-inverse')]
        for row in p['training_rows']:
            for name,sha in [('source_training_input','source_sha256'),('teacher_metadata','teacher_metadata_sha256'),('teacher_wav','teacher_wav_sha256')]:assert digest(REPO/row[name])==row[sha]
            search=read(RESULT/'searches'/(row['id']+'.json'));assert search['new_attempts']<=32 and search['extra_shrink_renders']<=3
            n,s,w=[search[v] for v in ('native','statefit','wavefit')]
            assert qualify(n,s,w)==search['qualification']
            assert not qualify(n,s,n)['qualified']
            assert not qualify(n,s,{**w,'support_complete':False})['qualified']
            previous=n
            for iteration in search['iterations']:
                if iteration['accepted']:
                    candidate=read(RESULT/'inverse-render'/row['id']/(iteration['accepted_attempt']+'.json'))
                    assert candidate['objective']<previous['objective'] and candidate['support_complete'] and candidate['E0_pass'] and candidate['internal_unchanged']
                    previous=candidate
            assert previous['wav_sha256']==w['wav_sha256']
            old=GRES/'render'/row['id']/'support-contract.json'
            if old.exists():assert digest(old)==digest(RESULT/'inverse-render'/row['id']/'support-contract.json')
        for r in attempts:
            if 'wav' in r:assert digest(ROOT/r['wav'])==r['wav_sha256']
            if r['status']=='completed':assert r['maximum_abs_half_tone']<=3 and r['support_complete'] and r['E0_pass'] and r['internal_unchanged']
        assert read(RESULT/'negative-tests.json')=={'objective':tests(),'guard':guard_tests(),'integration':integration_tests(),'projection':projection_tests()}
        before=b.events()
        process=subprocess.run([sys.executable,str(ROOT/'train.py')],text=True,capture_output=True,timeout=60)
        assert process.returncode!=0 and '最低12文の目標資格が未達のため共有fitを禁止' in process.stderr
        assert b.events()==before and not any((RESULT/name).exists() for name in ('models','asr','render','bundle'))
        save(RESULT/'training-gate-negative-test.json',{'returncode':process.returncode,'stdout':process.stdout,'stderr':process.stderr,
            'ledger_unchanged':True,'shared_fits':0,'new_diagnostic_render':0,'ai_calls':0,'quality_certified':False})
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'outcome':'目標10文で最低12文を満たさず計画どおり後段を開始せず停止',
            'training_rows':21,'qualified_targets':10,'completed_inverse_final_rows':63,'render_attempt_records':len(attempts),
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'source_and_assets_unchanged':True,'missing_target_not_zero_filled':True,'fit_gate_negative_test_passed':True,
            'pending_processes':[],'all_requirements_met':False,'quality_certified':False,'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish']
    assert len(starts)==len(ends);counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==len(attempts)<=672 and counts['teacher']==counts['train']==counts['ai']==0
    failed=[e for e in ends if e['status']!='completed']
    assert len(failed)==sum(r['status']!='completed' for r in attempts)==20
    assert all(starts[e['id']]['kind']=='render' for e in failed)
    for kind,count in [('render',901),('ai',321),('train',4),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限を拒否しません')
    assert events==b.events();inv=b.inventory();elapsed=time.time()-read(RESULT/'contract.json')['started_epoch']
    assert elapsed<7200 and inv['bytes']+65536<1000000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':failed,'all_jobs_finished':True,
        'seconds_before_report':elapsed,'inventory_before_cost_audit':inv,'source_download_bytes':0,
        'unused_render_calls':900-counts['render'],'unused_ai_calls':320,'unused_shared_fits':3,
        'no_automatic_extension':True,'no_further_generation_evaluation_training':True})
    print({'counts':dict(counts),'failed_jobs':len(failed),'seconds':elapsed,'bytes':inv['bytes']},flush=True)

if __name__=='__main__':main()
