"""固定出典、再利用証跡、全試行と上限を終了監査する。"""
from collections import Counter
from pathlib import Path
import time
from campaign import LocalBudget, ROOT, RESULT, REPO, WRES, read, save, digest, check_seal
from objective import tests
from guarded_derivative import tests as guard_tests
from integration_tests import tests as integration_tests
from summarize import paired


def main():
    b=LocalBudget()
    with b.job('audit','出典・差分・受理・再利用・旧封印・費用の終了監査',1000000):
        p=read(RESULT/'protocol.json')
        for n,sha in p['source_hashes'].items():assert digest(ROOT/n)==sha
        seals=read(RESULT/'input-preservation.json')['seals'];assert [check_seal(REPO/s['seal']) for s in seals]==seals
        for row in p['rows']:
            for name,sha in [('source_training_input','source_sha256'),('teacher_metadata','teacher_metadata_sha256'),('teacher_wav','teacher_wav_sha256')]:assert digest(REPO/row[name])==row[sha]
            support=RESULT/'render'/row['id']/'support-contract.json';assert digest(support)==digest(WRES/'render'/row['id']/'support-contract.json')
            search=read(RESULT/'searches'/(row['id']+'.json'));assert search['new_attempts']<=32 and search['extra_shrink_renders']<=3
            previous=search['native']
            for iteration in search['iterations']:
                assert 'unavailable' not in iteration['derivative_methods'] or not iteration['accepted']
                if iteration['accepted']:
                    accepted=read(RESULT/'render'/row['id']/(iteration['accepted_attempt']+'.json'))
                    assert accepted['status']=='completed' and accepted['support_complete'] and accepted['E0_pass'] and accepted['internal_unchanged']
                    assert accepted['objective']<previous['objective'];previous=accepted
            assert search['wavefit']['wav_sha256']==previous['wav_sha256']
        assert read(RESULT/'entrance-audit.json')['all_eight_matched']
        manifest=read(RESULT/'render-manifest.json');assert len(manifest['rows'])==12 and manifest['search_completed_before_asr']
        ai_results=[]
        for row in manifest['rows']:
            assert digest(ROOT/row['wav'])==row['wav_sha256'] and row['E0_pass'] and row['internal_unchanged'] and row['support_complete']
            for engine in ('whisper','reazon'):
                r=read(RESULT/'asr'/engine/(row['id']+'.json'));ai_results.append(r)
                if r['status']=='completed':
                    assert r['wav_sha256']==row['wav_sha256'] and r['protocol_sha256']==digest(RESULT/'protocol.json')
                    if r['ai_calls']==0:
                        source=REPO/r['reused_from'];assert digest(source)==r['reused_result_sha256']
                        other=read(source);assert other['wav_sha256']==r['wav_sha256'] and other['text']==r['text'] and other['engine']==r['engine']
                        assert r['original_protocol_sha256']==other['protocol_sha256']
                        assert r['original_evaluation_contract_sha256']==digest(WRES/'engine-contract.json')
                        for k in ('hypothesis','reference_kana','predicted_kana','errors','characters'):assert other[k]==r[k]
                if row['variant']!='wavefit':assert r['status']=='completed' and r['ai_calls']==0
        attempts=[read(path) for path in (RESULT/'render').rglob('*.json') if path.stem not in ('support-contract','state-inverse')]
        assert all(r['maximum_abs_half_tone']<=3 for r in attempts if r['status']=='completed')
        assert read(RESULT/'negative-tests.json')==tests() and read(RESULT/'guard-tests.json')==guard_tests()
        assert read(RESULT/'integration-tests.json')==integration_tests()
        fixture={'text_id':'f','status':'completed','errors':1,'native_errors':1,'characters':8}
        assert paired([fixture])['non_worsening'] and not paired([])['non_worsening']
        assert not paired([fixture,{'text_id':'f','status':'missing'}])['non_worsening'] and not paired([{**fixture,'errors':2}])['non_worsening']
        save(RESULT/'completion-audit.json',{'authorized_comparison_completed':True,'render_attempt_records':len(attempts),
            'final_rows':12,'completed_final_rows':manifest['completed'],'completed_asr_rows':sum(r['status']=='completed' for r in ai_results),
            'asr_reuse_rows':sum(r.get('ai_calls')==0 and r['status']=='completed' for r in ai_results),
            'previous_seals_verified':len(seals),'previous_sealed_files_verified':sum(s['verified_files'] for s in seals),
            'source_and_assets_unchanged':True,'negative_support_acceptance_missing_tests':True,'pending_processes':[],
            'all_requirements_met':False,'quality_certified':False,'current_turn_classification':'progress','fresh_resumed_turn':1})
    events=b.events();starts={e['id']:e for e in events if e['event']=='start'};ends=[e for e in events if e['event']=='finish']
    assert len(starts)==len(ends);counts=Counter()
    for e in starts.values():counts[e['kind']]+=e['count']
    assert counts['render']==len(attempts)<=128 and counts['ai']==sum(r.get('ai_calls',0) for r in ai_results)<=8
    assert counts['teacher']==counts['train']==0
    for kind,count in [('ai',9),('render',129),('train',1),('teacher',1)]:
        try:b.reserve(kind,'上限・禁止処理の拒否検査',count=count)
        except RuntimeError:pass
        else:raise AssertionError('上限を拒否しません')
    assert b.events()==events
    failed=[e for e in ends if e['status']!='completed']
    assert sum(starts[e['id']]['kind']=='render' for e in failed)==sum(r['status']!='completed' for r in attempts)
    contract=read(RESULT/'contract.json');inv=b.inventory();elapsed=time.time()-contract['started_epoch']
    assert elapsed<3600 and inv['bytes']+65536<150000000
    save(RESULT/'cost-audit.json',{'counts':dict(counts),'failed_jobs':failed,'all_jobs_finished':True,'limits':contract['limits'],
        'seconds_before_report':elapsed,'inventory_before_cost_audit':inv,'source_download_bytes':0,
        'unused_render_calls':128-counts['render'],'unused_ai_calls':8-counts['ai'],'no_automatic_extension':True,
        'no_further_generation_evaluation_training':True})
    print({'counts':dict(counts),'failed_jobs':len(failed),'seconds':elapsed,'bytes':inv['bytes']},flush=True)

if __name__=='__main__':main()
