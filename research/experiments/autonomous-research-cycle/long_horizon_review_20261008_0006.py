"""科学36件のレビュー。LFと文脈韻律の不採択から独立した声道制御へ配分する。"""
import hashlib,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v6'
NAME='long-horizon-review-v6'
SCIENCE=['nas-hts-lf-coupling-20261008-v1','nas-hts-lf-comparison-20261008-v1','nas-perceptual-new-four-20261008-v1','nas-fujisaki-context-mechanism-20261008-v1','nas-fujisaki-context-comparison-20261008-v1','nas-waveguide-tract-mechanism-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==36
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==30 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=6,trigger='前回レビュー後の科学6件終了',scientific_completed=36,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','六封印・全数値/内容結果・旧契約・所有一時不存在・次の調音配分',reserve_bytes=10000000) as j:
        b.save(HERE/'registration.json',reg,j);checked={};seals={}
        for name in SCIENCE:
            p=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(p);seals[str(p.relative_to(REPO))]=digest(p)
            assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened']
            for n,h in seal['files'].items():
                f=REPO/n;assert not any(v in f.parts for v in ('protected','holdout','splits'))
                if n in checked:assert checked[n]==h
                else:assert digest(f)==h,n;checked[n]=h
        a=state['long_horizon'];assert digest(ROOT/a['preservation_path'])==a['preservation_sha256'];b._authorization(b.snapshot());b._science_ready(b.snapshot())
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in b.snapshot()['temporary_work'].values())
        b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),old_preservation_audit_sha256=a['preservation_sha256'],old_28_contracts_exact=True,validated_management_sources_exact=True,old_102794_physical_files_full_rehash_this_review=False,all_owned_temporary_absent=True,protected_confirmation_text_read=False),j)
        results={n:read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE};compact={}
        for name in (SCIENCE[1],SCIENCE[4]):
            r=results[name];assert r['total']==64 and not r['adopted'] and r['physical_parameter_audit']['passed']
            compact[name]=dict(total=r['total'],parameter_pairs=r['physical_parameter_audit']['pairs_checked'],parameter_frames=r['physical_parameter_audit']['all_frames_checked'],research_gates=r['research_protection_gates'],
                methods={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in r['content'][m].items()}) for m,e in r['engineering'].items()})
        assert not results[SCIENCE[1]]['research_protection_gates']['lf'] and not results[SCIENCE[4]]['research_protection_gates']['fujisaki']
        resources=results[SCIENCE[2]];assert resources['eligible_for_current_Japanese_non_neural']==0 and resources['calibration_count']==0 and len(resources['candidates'])==4
        tube=results[SCIENCE[-1]];fixture=read(ROOT/'campaigns'/SCIENCE[-1]/'fixture-audit.json');assert tube['mechanical_fixture_passed'] and fixture['passed']
        assert len(fixture['static_rows'])==8 and len(fixture['dynamic_rows'])==6 and len(fixture['frequency_rows'])==4
        decision=dict(review_number=6,scientific_completed=36,previous_review=previous,comparisons=compact,
            LF=dict(coupling_mechanism_passed=results[SCIENCE[0]]['mechanical_fixture_passed'],native_clock_noise_inputs_exact=True,independent_LPF_mixing_verified=True,Japanese_comparison_adopted=False,source_shape_area_zero_not_extended_to_dynamic_cycles=True,antialiasing_qualified=False),
            Fujisaki=dict(independent_response_mechanism_passed=results[SCIENCE[3]]['mechanical_fixture_passed'],fixed_alpha_beta_gamma=[3.,20.,.9],fixed_phrase_accent_amplitudes=[.15,.25],native_LF0_values_used_for_mask_only=True,encoded_terminal_accent_ambiguity_retained=True,whole_utterance_median_not_streaming_causal=True,Japanese_comparison_adopted=False),
            new_perceptual_resources=dict(total=4,eligible=0,calibrations=0,new_audio_or_model_download_bytes=0,new_human_responses=0,all_six_public_metadata_fetches_succeeded=all(x['saved'] for x in resources['public_metadata_sources']),
                public_JNLP_stimulus_page_available=True,public_stimulus_not_individual_rating_mapping_or_audio_permission=True,candidate_ids=[x['id'] for x in resources['candidates']]),
            waveguide=dict(mechanical_fixture_passed=True,static_cases=8,dynamic_cases=6,uniform_section_counts=[8,16,24],frequency_geometries=4,
                maximum_static_output_error=max(x['output_max_error'] for x in fixture['static_rows']),maximum_dynamic_output_error=max(x['output_max_error'] for x in fixture['dynamic_rows']),maximum_frequency_complex_error=max(x['maximum_complex_error'] for x in fixture['frequency_rows']),
                independent_pressure_wave_and_matrix_verified=True,normalized_dynamic_energy_passive=True,future_drive_and_area_prefix_exact=True,moving_wall_mechanical_work_modeled=False,artificial_geometries_not_vowel_truth=True,Japanese_vowels_or_phonemes_qualified=False),
            causes=['LF結合は時計/入力/乱数noise/独立LPFの保持を確認したが、新64波のpitch・E0・固定支持と二ASRを保持せず不採択。',
                '固定句/アクセント応答は独立式と全保存frameに整合したが、新64波でpitchと内容を保持せず不採択。native全件通過を候補へ移さない。',
                '新4知覚資料も日本語・現非ニューラル域・刺激/個別評点対応・条件・未使用確認の全要件を満たさない。JNLP刺激頁は取得成功しており非公開と扱わない。',
                '独立声道伝搬は静的/動的正断面の計算を確認した。人工形状を母音正解にせず、測定由来の共有形状と有限帯域駆動を別登録する。'],
            actual_generated_speech_quality_improvement_verified=False,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            frozen_routes=['前レビューまでの全凍結を維持','同LF失敗コホートの係数/phase/LPF/gainを探索しない','同Fujisaki失敗コホートのalpha/beta/gamma・振幅・指令時刻・中央値/gainを探索しない','新4知覚資料の同条件探索を新しい対応公開なしに繰り返さない','独立声道の数値通過を旧Rosenberg/有限差分/LF0縮小/FIR/全極/モデル交換の救済に転用しない'],
            old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
            two_review_rule='第5回・第6回も生成音声の最終品質改善資格なし。同HMM/フィルタ/励振救済へ戻らず、正断面で制御する独立な声道機構を次の生成器として進める。公開一次測定の形状と明示指令から有限帯域駆動を生成し、測定出典・操作的pitch・安定性・内容を段階ごとに検証する。',
            next_question='Arai 2007の一次表に固定した日本語五母音の16個の径から独立声道を制御し、有限帯域の共有LF駆動と母音遷移を再現できるか。',
            next_estimate=dict(seconds=7200,bytes=300000000,write_bytes=800000000,render=160,dsp=800,ai=0,teacher=0,train=0,inverse=0,download=3000000,scope='一次表の全数値/方向/単位を照合し、静的母音と全20有向遷移の生成を限定検証。自然さや全日本語の資格なし。'),
            next_primary_sources=['https://splab.net/papers/2007/2007_01.pdf','https://splab.net/apd/g210/'],
            next_data_scope='Araiの管模型はChiba/Kajiyama由来の粗い形状。論文Table1と研究室頁の径の一部が異なるため、論文を固定し差異を記録する。録音/第三者codeは最終音源に用いず、論文の全文/図表をGitで再配布しない。数値事実を引用して独自生成制御を実装する。',
            next_allocation_after_failure='出力後に同母音コホートを径/終端反射/gainで救済しない。測定形状の精度・放射/損失・閉鎖/鼻腔・子音/調音指令という異なる機構の不足を明示し、独立登録へ進める。',
            perceptual_status='現HTS域の既存12資料は実校正資格なし。次の声道域へ旧評点の資格を自動移転しない。新しい一次の対応資料がある場合だけ限定監査する。',
            resource_status=b.review_due(),review_does_not_require_user_approval=True,all_caps_and_closing_reserve_kept=True)
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第6回定期レビュー','','科学6件、累計36件。最終品質未達・日本語知覚資格なし・P5未開封。旧消費/契約/封印・31方式・支持31,601/欠測249・各ASR33群を保持する。','',
            '|比較|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---|---:|---:|---:|---:|---:|']
        for name,r in compact.items():
            for m,e in r['methods'].items():lines.append(f'|{name}|{m}|{e["E0"]}/32|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
        lines+=['','LFと固定Fujisakiはともに不採択。同失敗コホートの係数/phase/指令時刻/LPF/中央値/gainの探索を凍結する。原入力と機構の保持を音声品質の資格に広げない。','',
            '新4知覚資料の適格候補0/4。JNLPの刺激頁は実取得できたが、個別評点対応と音声利用条件を確認できない。同資料は新しい公開対応がない限り反復しない。','',
            '独自声道primitiveは4静的形状×2駆動、3動的形状×2駆動、一様管解析、圧力行列の複素応答、無入力正規化エネルギーと因果前半を全通過。移動壁の仕事・閉鎖・鼻腔・放射・子音・日本語自然さの資格はない。','',decision['two_review_rule'],'',decision['next_question'],'',decision['next_data_scope'],'',
            '[Arai 2007一次論文](https://splab.net/papers/2007/2007_01.pdf)と[著者研究室頁](https://splab.net/apd/g210/)を出典とする。測定形状/共有指令は録音の再生や発話lookupではない。','',
            '新六封印の全参照、旧28契約と管理ガード、指定媒体/索引、全所有一時領域の不存在を照合した。旧102,794実体の全再hashは行っていない。192時間・終了専用12時間・0円・全資源上限を引き継ぎ、承認枠内で次の有効処理へ継続する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=36,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0006-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0117.json',dict(latest_completed=NAME,scientific_completed=36,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(dict(review_completed=True,scientific_completed=36,quality_goal_completed=False),flush=True)
if __name__=='__main__':main()
