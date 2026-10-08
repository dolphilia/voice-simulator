"""科学48件後の第8回レビュー。基盤の限定資格を保持して直接学習へ移す。"""
import hashlib,os,json
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v8';NAME='long-horizon-review-v8'
SCIENCE=['nas-radiated-waveguide-comparison-20261009-v1','nas-mri-primary-source-access-20261009-v1','nas-volume-velocity-observer-20261009-v1','nas-volume-waveguide-coupling-20261009-v1','nas-viscothermal-primary-source-20261009-v1','nas-viscothermal-reference-20261009-v2']
def main():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and s['long_horizon']['scientific_completed']==48 and b.review_due(s)['due'];previous=s['long_horizon']['last_review'];assert previous['scientific_completed']==42 and digest(ROOT/previous['path'])==previous['sha256']
 limits=dict(seconds=3600,bytes=64000000,write_bytes=300000000,setup=6,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(review_number=8,trigger='科学6件・累計48件終了',scientific_completed=48,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'audit','新六封印/旧消費/全分母/基盤資格/工程切替を確認',reserve_bytes=12000000) as j:
  b.save(HERE/'registration.json',reg,j);checked={};seals={}
  for name in SCIENCE:
   path=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(path);assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened'];seals[str(path.relative_to(REPO))]=digest(path)
   for n,h in seal['files'].items():
    f=REPO/n;assert not any(p in f.parts for p in ('protected','holdout','splits'))
    if n in checked:assert checked[n]==h
    else:assert digest(f)==h,n;checked[n]=h
  b._science_ready(b.snapshot());assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in b.snapshot()['temporary_work'].values())
  comp,mri,observer,coupling,primary,ref=[read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE]
  assert not comp['adopted'] and not mri['source_available'] and observer['passed'] and not coupling['adopted'] and coupling['within_original_observer_domain']==38 and primary['source_available'] and ref['frequency_reference_passed'] and ref['causal_wall_only']['passed'] and not ref['causal_time_realization_qualified']
  comparison={m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],support=e['fixed_support_intervals'],ASR={n:len(v['worsening_groups']) for n,v in comp['content'][m].items()}) for m,e in comp['engineering'].items()}
  obs=read(ROOT/'campaigns'/SCIENCE[-1]/'child-process-observation.json')
  decision=dict(review_number=8,scientific_completed=48,previous_review=previous,comparison=comparison,SI_domain=dict(within=38,total=43,source_or_domain_gain_gates_not_rescued=True,full_waveform_engineering_unverified=True),frequency_reference=dict(points=ref['all_grid_points'],CGS_SI_gamma_error=ref['max_gamma_CGS_SI_relative_error'],CGS_SI_impedance_error=ref['max_impedance_CGS_SI_relative_error'],max_two_port_power_excess=ref['max_two_port_power_excess'],shared_vowel_profiles=15),wall_only=dict(conditions=65,fs_Hz=48000,maximum_analog_relative_complex_error=ref['causal_wall_only']['maximum_original_analog_relative_error'],state_causality_passed=True,energy_passed=True,full_viscothermal_tract_connected=False),observed_process=obs,
   actual_speech_quality_improvement_verified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
   preserved=['全旧不採択・源振幅/径/観測範囲/利得/時計/ゲート・旧31方式支持31601欠測249を保持','第74両駆動の全pitch通過をASRや自然さ認定へ移さない','二ASR33群と個別コホートをpoolしない','PDFアクセス403を迂回せず、新対応資料なしの12知覚資料探索を反復しない','共有壁一portを全粘熱損失・人の壁物性・因果声道音声へ昇格しない'],
   causes=['両固定駆動は新32組の工学を通過しても二ASR各33群の内容を保護しなかった。','SI源/観測は38/43の適用範囲。源振幅/観測域を出力後に救済していない。','一次式の単位と周波数散逸、壁一portの因果受動性は確認できたが、空気R/Gと複素接合を持つ動的全声道は未実装。'],
   stage_B_exit='partial_switched',stage_B_exit_reason='最小壁一portは完了したが、全周波数依存接合の因果近似/動的状態/波形工学/新比較をこの基盤経路へ追加する必要がある。第7/8レビューで音声改善資格が得られていないため、6時間の上限を使い切らず副線へ移し、採用済みA設計の成立VTLで直接学習へ配分する。',
   foundation_clock=b.snapshot()['research_execution_plan']['foundation_only'],next='工程C: 五母音の共有TCX/TCY標的を直接有限学習する前に、JD3/API/形状と通常/隔離/CLI・自分のWAV再読取/回収・内部更新費を小fixtureで確認し、各母音のfit契約を登録する。',
   next_estimate=dict(seconds=7200,bytes=200000000,write_bytes=400000000,render=3000,dsp=200,ai=0,teacher=0,train=0,inverse=0,download=0),review_does_not_require_user_approval=True,resource_status=b.review_due())
  b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,new_references_hashed=len(checked),new_references_sha256=hashlib.sha256(encode(checked)).hexdigest(),old_28_contracts_exact=True,old_management_sources_exact=True,all_owned_temporary_absent=True,protected_text_read=False),j);b.save(HERE/'decision.json',decision,j)
  lines=['# 第8回定期レビューと工程Cへの切替','','科学48件。品質未達・知覚資格なし・P5未開封。旧結果と全費用/凍結を維持する。','','|同コホート方式|E0|pitch|欠測/支持|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
  for m,e in comparison.items():lines.append(f'|{m}|{e["E0"]}/32|{e["pitch"]}/32|{e["missing"]}/{e["support"]}|{e["ASR"]["whisper"]}/33|{e["ASR"]["reazon"]}/33|')
  lines+=['',f'分布損失は766545周波数点とCGS/SI単位を通過し、Suzuki壁65条件の因果/受動/状態継承を確認。元連続壁への48kHz離散化ずれは最大{decision["wall_only"]["maximum_analog_relative_complex_error"]:.3%}。子群RSSは50msサンプル最大{obs["sampled_process_group_peak_RSS_bytes"]/1e6:.1f}MB、controllerを加えた観測値は{obs["combined_observed_RSS_upper_bytes"]/1e6:.1f}MB。連続的な真のピークではなく共有ページの重複と未追跡分離groupの限界を明記。全声道/音声品質は未資格。','',decision['stage_B_exit_reason'],'',decision['next'],'','各母音の九候補×二F0を有限fitし共有十係数へ統合する。通常/隔離の自分の出力読取りと全内部API費を先に検査し、教師的参照適合を日本語自然さへ昇格しない。工程A/B時間・基盤12時間時計・総192時間/終了12時間・旧契約をリセットしない。','']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=48,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='review8-completed-stageC-ready',active_campaign=None,next=decision['next'],git_save_pending=True);b._write_state(s)
 b.transition_stage('C',decision['stage_B_exit_reason'],previous_status='partial_switched',foundation_only=False)
 b.save(ROOT/'progress-0144.json',dict(latest_completed=NAME,scientific_completed=48,review_completed=True,current_stage='C',quality_goal_completed=False,next=decision['next'],budget=b.reconcile()));print(json.dumps(dict(review_completed=True,scientific_completed=48,current_stage='C',foundation_moved_to_secondary=True),ensure_ascii=False))
if __name__=='__main__':main()
