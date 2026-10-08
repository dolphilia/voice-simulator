"""第26回を互換性不通過として封印する。未観測768件を未知のまま残す。"""
from paths import *
def main():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    assert not (HERE/'diagnostic-manifest.json').exists() and not (HERE/'compatibility-audit.json').exists()
    assert len(read(HERE/'protocol.json')['records'])==768
    with b.job(NAME,'audit','互換3回不通過・未観測分母・費用・封印',reserve_bytes=3000000) as j:
        from analysis_v3 import verify
        verify()
        attempts=[
            dict(attempt=1,build='O2',observed_wave_sha256='1682cabc2eff12b63a1aa9533097ece02d8beb1739a8941a45b3db6c001497f0'),
            dict(attempt=2,build='O2 -ffp-contract=off',observed_wave_sha256='819799d4507812bb7b0c47b5ebe86432e76c69dfbc151482c8be2bd0f5ef8242'),
            dict(attempt=3,build='O3 hook noinline',observed_wave_sha256='1682cabc2eff12b63a1aa9533097ece02d8beb1739a8941a45b3db6c001497f0')]
        old='b879dce299667649c3ee94fe7fc6bb5b5f909b307ee5595be87044d51598073a'
        diagnostic=read(HERE/'compatibility-failure-diagnosis.json')
        assert len(diagnostic['rows'])==4 and all(x['baseline_old_exact'] for x in diagnostic['rows'])
        assert diagnostic['rows'][0]['float32_different_samples']==1
        summary=dict(expected_existing_WORLD=768,full_corpus_observations=0,unknown_actual_excitation_cases=768,
            observer_qualified=False,reason='旧WAV完全一致が最初の固定例で3回不通過。技術再試行2回を消費し停止。',
            attempts=attempts,attempt_first_id='nas-absolute-f0/f0-fresh-00/neutral/native',old_wave_sha256=old,
            first_input_conversion_hashes_exact=True,baseline_existing_PyWORLD_old_exact=4,
            diagnostic_trial_observed_old_exact=3,diagnostic_trial_total=4,
            first_O2_float32_different_samples=1,first_O2_max_abs_difference=2.7755575615628914e-17,
            gate_not_relaxed=True,provisional_traces_not_promoted=True,old_gates_and_decisions_unchanged=True,
            new_synthesis_path=False,new_AI=0,protected_confirmation_opened=False,quality_goal_completed=False,
            next='第27回はWORLD実励振をunknownとして保持。確認済みHTSと固定支持を照合する。')
        b.save(HERE/'aggregate-summary.json',summary,j)
        state=b.snapshot();campaign=state['campaigns'][NAME]
        b.save(HERE/'cost-audit.json',dict(campaign=campaign,conservative_reconstruction_calls=campaign['counts']['render'],
            actual_reconstruct_calls=11,actual_compat_first_example_calls=3,diagnostic_calls=8,technical_retries=2,
            full_corpus_calls=0,new_AI=0,audio_duplicate_saved=0,all_temporary_removed=True,quality_goal_completed=False),j)
        report='''# WORLD励振観測の互換性不通過

既存WORLD768件を登録したが、観測Cと旧WAVの完全一致を最初の固定例で得られず、全件観測へ進まなかった。元PyWORLDで再構成した4例は旧WAVと一致した。F0・power・APの入力hashも一致した。

O2では最初の例のfloat32で1サンプルに2.7756e-17の差があった。O2の演算縮約off、通常O3と観測hook非inline化による技術再試行2回でもhash不一致が残った。差の小ささを理由に事前の完全一致条件を緩和しない。浮動小数点演算段階の差であり、詳細な発生演算の同定は未完了。

全768件の実励振は未確認として残す。試作observerのtraceを旧波形の実励振truthにしない。一次Cが無声にも500Hzの時計パルスを持つこと、APで周期応答をゼロ化すること、最後のnoise_size=0を区別する実装は保存したが、既存波形への資格は得ていない。

実再構成11回、保守的生成計数20回。全件768の生成・新ASRは0。所有一時物は全件削除済み。旧ゲート・旧採否・全体品質未達・P5未開封を維持した。第27回で確認済みHTSと固定支持欠測を照合し、WORLDの未知を推定で埋めない。
'''
        b.write(HERE/'report.md',report.encode(),j)
        files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()}
        b.save(HERE/'artifact-seal.json',dict(files=files,path_base='repository',experiment_completed=True,observer_qualified=False,quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.save(HERE/'completion-audit.json',dict(files_verified=len(files),seal_sha256=digest(HERE/'artifact-seal.json'),all_temporary_removed=True,scientific_nonpass_preserved=True),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s.setdefault('continuation_checkpoint_history',[]).append(s['continuation_checkpoint'])
        s['continuation_checkpoint']=dict(id='world-excitation-nonpass-20261008-0001',active_campaign=None,campaign_closed=True,
            next='commit/push→第27回固定支持欠測診断。WORLD実励振unknownを維持。',git_save_pending=True,
            quality_goal_completed=False,protected_confirmation_opened=False);b._write_state(s)
    b.save(ROOT/'progress-0037.json',dict(latest_completed=NAME,observer_qualified=False,quality_goal_completed=False,
        next='第27回固定支持原因分離。WORLDは未確認。',budget=b.reconcile()))
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
