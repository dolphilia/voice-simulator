"""科学24件で測定・位相・振幅・全極表現の範囲を点検し、次の配分を限定する。"""
import hashlib,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v4'
NAME='long-horizon-review-v4'
SCIENCE=['nas-yin-scope-qualification-20261008-v1','nas-hts-allpass-mechanism-20261008-v1','nas-hts-allpass-comparison-20261008-v1','nas-hts-output-bound-mechanism-20261008-v1','nas-hts-output-bound-comparison-20261008-v1','nas-hts-lattice-mechanism-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==24
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==18 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=4,trigger='前回レビュー後に科学6件終了',scientific_completed=24,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','新六封印・有限資格・失敗・旧保護・次の配分を照合',reserve_bytes=10000000) as j:
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
        results={name:read(ROOT/'campaigns'/name/'aggregate-summary.json') for name in SCIENCE}
        yin=results[SCIENCE[0]];lattice=results[SCIENCE[-1]]
        assert not yin['all_declared_domains_passed'] and not lattice['mechanical_fixture_passed'] and lattice['implementation_mechanical_fixture_passed']
        compact={}
        for name in (SCIENCE[2],SCIENCE[4]):
            r=results[name];assert r['total']==64
            compact[name]=dict(total=r['total'],parameter_pairs=r['physical_parameter_audit']['pairs_checked'],parameters_frames=r['physical_parameter_audit']['all_frames_checked'],research_gates=r['research_protection_gates'],
                methods={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in r['content'][m].items()}) for m,e in r['engineering'].items()})
        bound=results[SCIENCE[4]]['physical_parameter_audit'];changed_samples=sum(v['large_region_samples'] for v in bound['rows']);assert changed_samples==2
        decision=dict(review_number=4,scientific_completed=24,previous_review=previous,comparisons=compact,
            measurement=dict(YIN_domains=yin['domains'],all_domains_qualified=False,scope='登録人工静的40/80ms、動的40msと無周期条件のみ。20ms/境界/動的80msは不通過。旧249欠測や未知HTSのtruthを救済しない。'),
            output_bound=dict(unchanged_low_region_and_bound_verified=True,large_region_samples_changed=changed_samples,independent_float32_mapping_max_error=max(v['independent_float32_mapping_max_abs_error'] for v in bound['rows']),
                content_non_worsening_on_this_cohort=True,native_and_candidate_E0=32,pitch=30,large_change_content_protection_qualified=False,actual_E0_improvement_on_this_cohort=False),
            lattice=dict(original_mechanical_qualification=False,original_known_AR_pass=14,original_known_AR_denominator=16,limited_implementation_qualification=True,known_AR_failed_cases=lattice['known_AR_failed_cases'],
                analytic_finite_MCP_tail_bound_verified=True,arbitrary_time_varying_stability_proven=False,real_HTS_projection_qualified=False),
            causes=['YINの人工40ms通過は未知HTS・境界・自然さの資格へ移せない。',
                '振幅1の固定LTI位相は非定常MLSA/有限波形の振幅保存を保証せず、オールパスは二ASR各7群を悪化させた。',
                '固定無記憶出力上限は数学的に保持でき、二ASR非悪化だったが、未知コホートでは変更2標本で元もE0全件通過。大変更の内容保護や品質改善を示していない。',
                '有限35 MCPは無限ARを厳密には表せず、負poleを含むalpha.55の2条件を元閾値で不通過として保持。独立Toeplitz/静的直接形/有限動的逆写像は限定資格として通過した。'],
            actual_generated_speech_quality_improvement_verified=False,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            frozen_routes=['前レビューまでの全凍結を維持','YINの同855条件を閾値/phase選択で救済しない','オールパスの同コホートpole調整をしない','出力boundの同コホートknee/ceiling救済をしない','既知AR2不通過を閾値緩和/条件除外で通過にしない'],
            old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
            two_review_rule='第3回・第4回も最終品質/全件生成保護の改善資格なし。有限機構だけの検証を繰り返さず、全極表現の一回の実MCP監査と、通過時だけ一回の新日本語比較に限定する。不通過なら共有音響モデル/文脈表現または調音制御へ変更し、同HTSフィルタ係数探索へ戻らない。',
            next_question='新native全20,276 MCP frameのorder34/FFT16384全極射影は、独立密Toeplitz・反射係数安定域・有限grid log振幅誤差・32768点による観測refinementを全件保持できるか。',
            next_estimate=dict(seconds=7200,bytes=300000000,write_bytes=800000000,render=0,dsp=160,ai=0,teacher=0,train=0,inverse=0,download=0,
                comparison='保存済み32nativeの全frameを対象にする近似/安定域監査。wave/source再生成なし、candidate gainや係数をこのコホートで調整しない。'),
            next_fixed_gates_proposal=dict(log_magnitude_RMSE_dB_at_most=2.,independent_dense_normalized_coefficient_error_at_most=1e-10,reflection_abs_below=.99999999,
                finite_grid_refinement_relative_coefficient_and_gain_error_at_most=1e-8,all_frames_required=True,no_coefficient_clip_or_loading=True),
            next_allocation_after_failure='同フィルタ表現をIDだけ変えて反復せず、共有文脈/状態から全音響を計算する別の非ニューラルモデル、または独立な調音制御の新契約へ進む。旧17→96の同8残差/同learner救済は凍結を維持。',
            perceptual_status='現HTS域の日本語刺激/個別評点/独立確認/利用条件の資格は得ていない。SingMOS-Proは新公開カードでも歌唱域で、発話の資格へ移さない。新公開対応がない同じ8資料は繰り返さない。',
            perceptual_new_metadata_sources=['https://huggingface.co/datasets/TangRain/SingMOS-Pro','https://arxiv.org/abs/2510.01812'],
            resource_status=b.review_due(),review_does_not_require_user_approval=True,all_caps_and_closing_reserve_kept=True)
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第4回定期レビュー','','科学6件、累計24件。最終品質未達・日本語知覚資格なし・P5未開封。旧消費、旧契約・封印・31方式・支持31,601/欠測249・各ASR33群は保持する。','',
            '|比較|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---|---:|---:|---:|---:|---:|']
        for name,r in compact.items():
            for m,e in r['methods'].items():lines.append(f'|{name}|{m}|{e["E0"]}/32|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
        lines+=['', 'YINは人工静的40/80ms、動的40msの限定範囲。境界の周期truthを与えず、旧欠測を通過へ変えない。オールパスの振幅1も非定常出力の保護ではなかった。','',
            '固定出力制御は内容非悪化だったが、変更はわずか2標本、元もE0全件通過。大振幅変換への一般化や改善を主張しない。全極射影は既知AR14/16、元全件資格不通過。有限35 MCPの尾で誤差を説明でき、別版の限定実装機構は通過した。','',
            decision['two_review_rule'],'',decision['next_question'],'',
            '新六封印の全参照をhash照合した。旧28契約と管理ガード、指定媒体/位置索引、全所有一時領域の不存在も確認した。旧102,794実体の全再hashは今回行っていない。192時間と最後12時間終了専用、0円、資源上限を保持して次の有効処理へ継続する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=24,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0004-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0091.json',dict(latest_completed=NAME,scientific_completed=24,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(dict(review_completed=True,scientific_completed=24,large_bound_change_samples=changed_samples,original_lattice_qualification=False,quality_goal_completed=False),flush=True)
if __name__=='__main__':main()
