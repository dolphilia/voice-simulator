"""科学30件で全極・共有HMM・LF周期関数の資格を点検し、次の生成へ配分する。"""
import hashlib,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-long-horizon-review-20261008-v5'
NAME='long-horizon-review-v5'
SCIENCE=['nas-hts-lattice-projection-20261008-v1','nas-hts-acoustic-model-mechanism-20261008-v1','nas-hts-acoustic-model-comparison-20261008-v1','nas-hts-tohoku-mechanism-20261008-v1','nas-hts-tohoku-comparison-20261008-v1','nas-lf-source-mechanism-20261008-v1']

def main():
    b=Budget();b.recover();state=b.snapshot();assert not state['jobs'] and b.review_due(state)['due'] and state['long_horizon']['scientific_completed']==30
    previous=state['long_horizon']['last_review'];assert previous['scientific_completed']==24 and digest(ROOT/previous['path'])==previous['sha256']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=300000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(review_number=5,trigger='前回レビュー後に科学6件終了',scientific_completed=30,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
    with b.job(NAME,'audit','新六封印・共有モデル比較・LF限定資格・旧保護・次の配分を照合',reserve_bytes=10000000) as j:
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
        results={n:read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE};projection=results[SCIENCE[0]];lf=results[SCIENCE[-1]]
        assert not projection['all_required_pass'] and projection['total_frames']==20276 and projection['excluded_frames']==0
        assert lf['mechanical_fixture_passed'] and not lf['HTS_coupling_qualified']
        compact={}
        for name in (SCIENCE[2],SCIENCE[4]):
            r=results[name];assert r['total']==64
            compact[name]=dict(total=r['total'],parameter_pairs=r['physical_parameter_audit']['pairs_checked'],parameters_frames=r['physical_parameter_audit']['all_frames_checked'],research_gates=r['research_protection_gates'],
                methods={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in r['content'][m].items()}) for m,e in r['engineering'].items()})
        failed=sum(v['failed_frames'] for v in projection['rows']);assert failed==8289
        fixture=read(ROOT/'campaigns'/SCIENCE[-1]/'fixture-audit.json');assert fixture['passed'] and len(fixture['rows'])==20
        decision=dict(review_number=5,scientific_completed=30,previous_review=previous,comparisons=compact,
            projection=dict(total_frames=20276,failed_frames=failed,fully_passed_wave_conditions=sum(v['all_required_pass'] for v in projection['rows']),order=34,alpha=.55,FFT=16384,all_required_pass=False,
                maximum_log_magnitude_RMSE_dB=max(v['maximum_log_magnitude_RMSE_dB'] for v in projection['rows']),threshold_relaxation_or_coefficient_rescue=False,dependent_lattice_Japanese_comparison_run=False),
            shared_acoustic_models=dict(happy_MCP_factor_only=True,Tohoku_full_model_factor_including_GV=True,between_models_clock_identity_claimed=False,licenses_and_attribution_kept=True,
                happy_MCP_adopted=False,Tohoku_adopted=False,same_cohort_model_style_or_gain_search=False),
            LF=dict(fixed_T0_Tp_Te_Ta_Ee=[1.,.4,.6,.05,1.],coefficients=fixture['coefficients'],quad_mean=fixture['independent_quad_mean'],quad_power=fixture['independent_quad_power'],C_Python_dense_grid_error=fixture['dense_grid_error'],
                qualified='固定形状・固定phase入力の周期関数だけ。人工20条件の数値と面積/連続性/二乗積分の限定資格。',HTS_coupling_qualified=False,antialiasing_qualified=False,real_Japanese_speech_qualified=False),
            causes=['全極射影は全20,276 frame中8,289不通過、全件通過の発話条件0/32。第4回の失敗時分岐に従い係数救済/日本語lattice比較を実施しなかった。',
                'happyモデルのMCP状態分布だけの交換は機構を保持したが、固定支持と二ASRを悪化させた。原LF0等を同じにしても音響観測のpitchを保持しない。',
                'Tohokuの全共有HMMは実装互換でも、固有duration/全音響列/GVの差を含む。E0全件だけでは内容/固定支持を保持せず、新日本語比較で不採択。',
                'LF固定周期関数は一次式の実装範囲を確認した。原HTS/LPFへの結合、時間変動、aliasing、知覚pitch、日本語の自然さへ資格を移さない。'],
            actual_generated_speech_quality_improvement_verified=False,generalization_quality_certified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            frozen_routes=['前レビューまでの全凍結を維持','order34/alpha.55全極射影の同MCPコホートを次数/warp/loading/閾値で救済しない','happy MCPの同コホートを感情style/補間/係数/gainで救済しない','Tohoku全モデルの同コホートを感情style/係数/gainで救済しない','LF固定primitiveの通過を既存Rosenberg/有限差分/LF0列縮小の救済と扱わない'],
            old_support_intervals=31601,old_missing=dict(total=249,HTS=94,WORLD=155),old_31_methods_and_each_ASR33_groups_kept=True,
            two_review_rule='第4回・第5回も最終品質/全件生成保護の改善資格なし。共有HMM選別・同フィルタ救済を止め、一次式に基づくLF sourceを原HTSへ結合する一機構と、通過時の一新日本語比較に限定する。その比較でも不改善なら同LF係数探索へ戻らず、独立な調音source-tract制御または共有文脈/韻律表現の異なる方式へ変更する。',
            next_question='固定LF声門流微分を原HTSの混合励振の有声成分へ結合し、元native、時計、乱数noise、MCP/LF0/LPF、独立LPF混合、入力保持、因果前半を保持できるか。',
            next_estimate=dict(seconds=7200,bytes=300000000,write_bytes=800000000,render=120,dsp=180,ai=0,teacher=0,train=0,inverse=0,download=0,scope='結合機構と人工条件だけ。実日本語は別の出力前登録。波形別係数/gainなし。'),
            next_allocation_after_failure='同LF固定形状の係数/phase/LPFをこの失敗コホートで救済しない。独立な調音機構/文脈韻律表現へ進む。旧17→96の同8残差/同learner救済は凍結を維持。',
            perceptual_status='現HTS域の日本語刺激/個別評点/独立確認/利用条件の資格なし。既存の同資料は新しい対応公開がない限り繰り返さない。LF原論文は数式の一次資料で知覚資格ではない。',
            resource_status=b.review_due(),review_does_not_require_user_approval=True,all_caps_and_closing_reserve_kept=True)
        b.save(HERE/'decision.json',decision,j)
        lines=['# 長期包括承認後の第5回定期レビュー','','科学6件、累計30件。最終品質未達・日本語知覚資格なし・P5未開封。旧消費/契約/封印・31方式・支持31,601/欠測249・各ASR33群を保持する。','',
            '|比較|方式|E0|pitch|固定支持欠測|Whisper悪化群|Reazon悪化群|','|---|---|---:|---:|---:|---:|---:|']
        for name,r in compact.items():
            for m,e in r['methods'].items():lines.append(f'|{name}|{m}|{e["E0"]}/32|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
        lines+=['','全極射影8,289/20,276 frameが不通過、全件通過0/32条件。登録分岐に従い日本語lattice比較を行わず、係数/閾値を救済しない。共有MCP分布交換と全HMM交換の両候補も不採択。モデル間のclock/音響列の同一性を主張しない。','',
            'LFは固定Tp/Te/Ta/Eeからepsilon/alphaを数式で求め、面積0・二乗積分1・連続性・20人工条件のC/Python一致を確認した。HTS結合/aliasing/日本語自然さの資格はない。LF0列変更とは別の機構。','',decision['two_review_rule'],'',decision['next_question'],'',
            '新六封印の全参照、旧28契約と管理ガード、指定媒体/索引、全所有一時領域の不存在を照合した。旧102,794実体の全再hashは行っていない。192時間と最後12時間終了専用、0円、全資源上限を保持して次の有効処理へ継続する。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=30,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='long-horizon-review-0005-completed',active_campaign=None,next=decision['next_question'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0104.json',dict(latest_completed=NAME,scientific_completed=30,review_completed=True,quality_goal_completed=False,next=decision['next_question'],budget=b.reconcile()))
    print(dict(review_completed=True,scientific_completed=30,projection_failed_frames=failed,quality_goal_completed=False),flush=True)
if __name__=='__main__':main()
