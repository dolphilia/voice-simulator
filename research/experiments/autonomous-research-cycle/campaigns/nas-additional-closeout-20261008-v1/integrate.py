"""全結果と二ASR悪化群から次の制御比較の有効性を判断する。"""
from paths import *
from collections import Counter
def main():
    from audit import verify
    verify();b=Budget();b.recover()
    with b.job(NAME,'audit','既存992/1984ASR・追加測定/源区分・次の比較条件を統合',reserve_bytes=3000000) as j:
        cross=read(PREVIOUS/'aggregate-summary.json');window=read(WINDOW/'aggregate-summary.json');world=read(WORLD/'aggregate-summary.json');support=read(SUPPORT/'aggregate-summary.json')
        assert cross['total_wave_records']==support['total']==992 and cross['total_existing_ASR_records']==1984
        assert support['actual_HTS_source_known']==224 and support['WORLD_actual_source_unknown']==768
        assert world['full_corpus_observations']==0 and not world['observer_qualified']
        methods={};all_source=Counter();missing_source=Counter()
        for cohort,c in cross['cohorts'].items():
            for method,m in c['methods'].items():
                key=cohort.removesuffix('-20261008-v1')+'/'+method;s=support['groups'][key]
                assert s['files']==m['expected']==32 and not m['old_qualification']
                all_source.update(s['all_source_states']);missing_source.update(s['missing_source_states'])
                methods[key]=dict(files=32,pitch_pass=m['pitch_pass_count'],support_pass=m['support_pass_count'],
                    fixed_support_intervals=s['fixed_support_intervals'],missing_support_intervals=s['missing_intervals'],
                    source_known_files=s['known_source_files'],missing_source_states=s['missing_source_states'],
                    missing_drive_states=s['missing_drive_states'],old_qualification=m['old_qualification'],
                    content={engine:dict(groups=v['groups'],worsening_groups=v['worsening_groups'],
                        edit_operations=v['edit_operations'],old_groups_exact_match=v['old_groups_exact_match'])
                        for engine,v in m['content'].items()},
                    within_cohort_pairs_only=True,ASR_edits_not_aligned_to_source_intervals=True,diagnostic_not_causal=True)
        assert len(methods)==31
        summary=dict(methods=methods,known_HTS_wave_cases=224,unknown_WORLD_wave_cases=768,all_fixed_support_source_states=dict(all_source),
            missing_fixed_support_source_states=dict(missing_source),total_fixed_support_intervals=sum(x['fixed_support_intervals'] for x in methods.values()),
            missing_fixed_support_intervals=sum(x['missing_support_intervals'] for x in methods.values()),
            HTS_window_results=window['results'],WORLD_compatibility=world,
            source_pulse_presence_does_not_qualify_acoustic_or_perceived_pitch=True,
            next_new_control_comparison_valid_now=False,
            decision='未確認WORLDと短窓/動的測定の不足が残り、源不足と音響測定の失敗を十分に分離できない。次の係数比較を旧DIO/ACFだけで採否決定する根拠は不足。測定・源成分検証を先に進める。',
            required_before_control_comparison=['HTSでLPF後の周期寄与と音響測定の関係を旧波形不変で確認','WORLDで未観測原実装の再現差を演算段階へ分離し、純観測の全旧波形一致を得る','短区間・動的区間の測定可能な範囲と欠測を事前固定','新入力・同コホート対照・二ASR33群・旧内容保護・通常隔離/CLI証拠を新比較前に登録'],
            human_response_not_required_for_measurement_or_control_research=True,
            previous_content_protection_and_qualification_unchanged=True,new_ASR_or_waveform=0,
            quality_goal_completed=False,protected_confirmation_opened=False,perceptual_qualification=False)
        b.save(HERE/'integration-summary.json',summary,j)
        lines=['# 追加4枠の測定・励振・内容保護の統合','',
            '第25〜27回の結果と、6コホート31方式・992既存波形・1,984既存ASR記録の二認識器33群を統合した。全方式の旧資格は不通過のまま。コホート内のnative対照を保持し、コホート間の総率で順位を作らない。','',
            '現時点で、新たな係数比較の採否を旧DIO/ACFだけで判断する根拠は不足している。HTSの源時計は224件確認できたが、LPF後の周期寄与・知覚pitchは未確認。WORLD768件の実励振は互換不通過のためunknown。短窓・動的区間へ安定60ms資格を流用できない。','',
            '|コホート/方式|ピッチ通過/32|支持欠測区間|悪化群W/R|','|---|---:|---:|---|']
        for k,m in methods.items():lines.append(f"|{k}|{m['pitch_pass']}|{m['missing_support_intervals']}|{len(m['content']['whisper']['worsening_groups'])}/{len(m['content']['reazon']['worsening_groups'])}|")
        lines+=['',f"固定支持は計{summary['total_fixed_support_intervals']}区間、欠測は{summary['missing_fixed_support_intervals']}区間。欠測の源区分: {dict(missing_source)}。",
            '源の無声/短いパルス列と、パルス存在下の音響的な曖昧さを分けた。後者には周期成分の弱さ、SNR、残響、非定常、測定器の限界が混在し、測定器の失敗と断定しない。WORLDは未確認を保持した。kana編集は音素時刻と対応付けない。',
            '次は既存HTSのLPF後周期成分、WORLDの未観測原実装の演算再現、短窓/動的測定の対象範囲を検証する。新しい人の回答をこれらの研究の必須条件にしない。知覚資格・独立P5は未充足で、全体品質は未達。','']
        b.write(HERE/'integration-report.md','\n'.join(lines).encode(),j)
    print(b.reconcile(),flush=True)
if __name__=='__main__':main()
