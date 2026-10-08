"""旧128音声の分母・除外・欠測・限定測定資格を保持する。"""
from paths import *
from controller_v2 import verify
def main():
    verify();b=Budget();b.recover();p=read(HERE/'protocol.json');manifest=read(HERE/'diagnostic-manifest.json')
    assert len(manifest['rows'])==128 and manifest['all_byte_exact']
    with b.job(NAME,'audit','全観測hash・適用分母・測定不通過を集計',reserve_bytes=2_000_000) as j:
        records=[]
        for x in manifest['rows']:
            assert digest(REPO/x['path'])==x['sha256']
            v=read(REPO/x['path']);assert digest(REPO/v['old_wav'])==v['old_wav_sha256']==v['observed_wav_sha256']
            assert digest(REPO/v['trace_path'])==v['trace_sha256'];records.append(v)
        results={}
        for tracker in ['dio','harvest','centered_acf']:
            groups={}
            for condition in ['both','neutral','higher']:
                for method in ['all','hts_native','hts_postfilter','hts_voicing','hts_voicing_postfilter']:
                    chosen=[r for r in records if (condition=='both' or r['condition']==condition) and (method=='all' or r['method']==method)]
                    s=[r['trackers'][tracker] for r in chosen];assert chosen
                    groups[condition+'/'+method]=dict(expected=len(chosen),passed=sum(x['passed'] for x in s),
                        positive_frames=sum(x['positive_frames'] for x in s),negative_frames=sum(x['negative_frames'] for x in s),
                        correct_positive=sum(x['correct_positive'] for x in s),positive_missing=sum(x['positive_missing'] for x in s),
                        negative_false_accept=sum(x['negative_false_accept'] for x in s),
                        exclusions={k:sum(x['exclusions'][k] for x in s) for k in ['edge','dynamic','boundary']},
                        inadequate_positive=sum(x['positive_frames']<3 for x in s),inadequate_negative=sum(x['negative_frames']<3 for x in s),
                        all_pass=all(x['passed'] for x in s))
            results[tracker]=dict(groups=groups,all_128_pass=groups['both/all']['all_pass'],
                failed_ids=[r['id'] for r in records if not r['trackers'][tracker]['passed']],
                scope='第19回HTS128音声の60ms安定全有声窓/20ms全無声窓と実励振周期だけ。知覚ピッチ・WORLD・日本語一般・旧ゲートには拡張しない。',
                independent_vote=False)
        b.save(HERE/'aggregate-summary.json',dict(total=128,all_byte_exact=True,results=results,
            old_gates_and_decisions_unchanged=True,legacy_ACF_is_diagnostic_only=True,
            trace_is_source_excitation_not_perceived_pitch=True,new_content_evaluation=0,
            final_generator_independence_not_retested=True,perceptual_qualification=False,
            protected_confirmation_opened=False,quality_goal_completed=False),j)
    print({n:x['all_128_pass'] for n,x in results.items()},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
