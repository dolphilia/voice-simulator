"""科学60後のレビュー10。訓練適合とCV不通過を分け、C残額を保持してDへ。"""
import hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v10';NAME='long-horizon-review-v10'
SCIENCE=['nas-vtl-qualified-vowel-fit-20261009-a-v1','nas-vtl-qualified-vowel-fit-20261009-i-v1','nas-vtl-qualified-vowel-fit-20261009-u-v1','nas-vtl-shared-cv-preflight-20261009-v1','nas-vtl-shared-cv-development-20261009-k-v1','nas-vtl-shared-cv-development-20261009-t-v1']
def main():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values());assert s['long_horizon']['scientific_completed']==60 and b.review_due(s)['due']
 previous=s['long_horizon']['last_review'];assert previous['scientific_completed']==54 and digest(ROOT/previous['path'])==previous['sha256']
 limits=dict(seconds=3600,bytes=64000000,write_bytes=400000000,setup=6,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(review_number=10,trigger='前回54から科学六契約終了',scientific_completed=60,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'audit','新六封印/訓練適合/CV不通過/C配分とD凍結条件を確認',reserve_bytes=12000000) as j:
  b.save(HERE/'registration.json',reg,j);checked={};seals={}
  for name in SCIENCE:
   path=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(path);assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened'];seals[str(path.relative_to(REPO))]=digest(path)
   for n,h in seal['files'].items():
    f=REPO/n;assert not any(x in f.parts for x in ['protected','holdout','splits'])
    if n in checked:assert checked[n]==h
    else:assert digest(f)==h,n;checked[n]=h
  b._science_ready(b.snapshot());assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in b.snapshot()['temporary_work'].values())
  fits=[read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE[:3]];pre=read(ROOT/'campaigns'/SCIENCE[3]/'aggregate-summary.json');cv={}
  for g,n in zip('kt',SCIENCE[4:]):
   data=read(ROOT/'campaigns'/n/'data/grid.json');original=read(ROOT/'campaigns'/n/'aggregate-summary.json');methods={}
   for m in ['native','baseline','learned']:
    rows=[x for x in data['rows'] if x['method']==m];methods[m]=dict(total=5,whole_E0_pass=sum(bool((x['measurement']['E0'] if x['measurement'] else x['meta'].get('E0',{})).get('E0_pass')) for x in rows),pitch_pass=sum(bool(x['measurement'] and x['measurement']['pitch']['passed']) for x in rows),missing_measurements=sum(x['measurement'] is None for x in rows))
   assert original['joint_qualified_cases']==0
   cv[g]=dict(methods=methods,joint_qualified_cases=0,case_total=5,cases=original['cases'],unqualified_numeric_distance_not_adoption=True)
  start=read(ROOT/'progress-0144.json')['budget']['counts']['render'];current=b.snapshot()['counts']['render'];used=current-start;cap=read(ROOT/'campaigns/nas-research-resume-stage-A-20261009-v1/stage-A-design.json')['estimates']['stage_C']['render_at_most'];assert start==28604 and cap==24000 and used==23851 and cap-used==149
  reason='三母音の訓練適合は確認したが、k/tの同コホート参照は各F0 0/5、学習候補は各4/5でuのACF支持欠測。CV移転・内容・自然さは未資格。Cの事前render配分24000に対し23851を全失敗込みで消費し、149ではs組1400予約を開始できない。sを未実施のまま残し、係数を変更せず工程Dの新語句で同コホートの工学・二ASRを診断する。C資源をDへ繰越・再初期化してsを実行しない。'
  decision=dict(review_number=10,scientific_completed=60,previous_review=previous,training_fits=[dict(vowel=x['vowel'],valid_candidates=x['admissible_candidates'],candidate_total=9,baseline_shape_MSE=x['baseline_shape_MSE'],selected_shape_MSE=x['selected_shape_MSE'],training_improved=x['training_objective_improved'],selected_coefficients=[x['shared_model']['TCX_delta_cm'],x['shared_model']['TCY_delta_cm']],reference_reused=True,not_independent_quality_evidence=True) for x in fits],shared_CV_entry=dict(preflight_passed=pre['preflight_passed'],all_E0=pre['E0_pass_count'],total=21,normal_isolated_CLI_exact=pre['normal_isolated_CLI_exact'],static_training_reproduction_exact=pre['static_training_WAV_reproduction_exact'],actual_render_calls=3492),CV_development=cv,C_allocation=dict(original_stage_A_design_sha256=digest(ROOT/'campaigns/nas-research-resume-stage-A-20261009-v1/stage-A-design.json'),stage_C_start_render=start,cumulative_render_now=current,consumed_render=used,original_render_allocation=cap,remaining_render=149,fit_runs_consumed=5,maximum_initial_fit_runs=5,completed_CV_cases=10,initial_CV_cases=15,s_group_not_started=True),stage_C_exit='partial_switched',stage_C_exit_reason=reason,candidate_frozen=dict(model_path='vtl-shared-aiu-model-20261009.json',model_sha256=digest(ROOT/'vtl-shared-aiu-model-20261009.json'),CV_runtime_bundle_manifest_sha256=digest(ROOT/'campaigns/nas-vtl-shared-cv-preflight-20261009-v1/runtime-bundle/manifest.json'),shared_parameters_learned=6,e_o_trained=False,old_lower_short_failures_and_CV_gates_not_rescued=True),
   next_D=dict(maximum_seconds=21600,inputs_short=4,inputs_long=4,conditions=[dict(id='neutral',F0_Hz=140,speed=1.),dict(id='higher',F0_Hz=180,speed=1.15)],methods=['native','VTL-baseline','VTL-learned'],maximum_VTL_duration_seconds=1.6,proposed_render_allocation_at_most=36000,original_D_render_allocation_at_most=54000,register_whole_suite_and_33_group_series_before_output=True,ordinary_isolated_and_CLI_counted=True,comparison_role='新未使用入力の限定選別診断。P5ではない。既にCで見た資料を未使用証拠へ戻さない。',gates='全分母、同コホート対照、固定支持、全E0/指定F0/最低3音素支持、二ASR各33群・非対象/0分母を保持。悪化相殺や係数/gain/時刻/窓/閾値の救済なし。知覚/一般化/旧C不通過が未資格なら最終採択しない。',known_risk='CVのu支持不通過と参照F0欠測は既知。語句比較が通過しても旧CVの不通過を覆さず、全日本語/自然さの認定にはしない。',resource_review='現在render43.7%。Dは元54000案から36000以下へ実量計算し、70%をまたぐ前に配分をレビュー。85%以降の新render経路は避ける。'),
   content_ASR_not_yet_measured=True,actual_generalizable_speech_improvement_verified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,no_group_or_cohort_pool=True,resources=b.review_due(),stage_clock=b.snapshot()['research_execution_plan'],next='工程D：共有係数/コード/対照/測定器/ゲートを凍結し、P5本文を読まず既知の非保護履歴だけで新短4/長4を衝突確認。全33群・同コホート・固定支持・生成量を初出力前登録し、通常/隔離/CLIと二ASRの有限比較を実施。')
  b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,checked_files=len(checked),checked_files_sha256=hashlib.sha256(encode(checked)).hexdigest(),all_owned_temporary_absent=True,old_guard_sources_and_approval_exact=True,P5_text_read=False),j);b.save(HERE/'decision.json',decision,j)
  lines=['# 第10回レビューと工程Dへの切替','','科学60件。品質未達、知覚資格なし、P5未開封。','','|訓練母音|適格候補|既定MSE|学習MSE|','|---|---:|---:|---:|']+[f"|{x['vowel']}|{x['valid_candidates']}/9|{x['baseline_shape_MSE']:.4f}|{x['selected_shape_MSE']:.4f}|" for x in decision['training_fits']]+['','訓練の三母音では共有六係数による包絡適合を確認。実CVのk/tでは全30E0通過、native pitch 0/10、既定10/10、学習8/10。両組の共同適格比較は0/5。ク/ツの学習後ACF支持欠測を保持し、未資格の距離数値を採択へ使わない。共有入口21波形の同一性は品質改善ではない。','',reason,'','Dは元の140/180Hz二条件を保持し、短4/長4、同コホート三方式を初出力前登録する。36000render以下へ実量計算し、原配分・70/85%レビュー・総192時間・終了12時間を維持。P5は開かず、知覚や一般化を認定しない。','',decision['next'],'']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=60,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='review10-completed-C-partial-D-ready',active_campaign=None,next=decision['next'],git_save_pending=True);b._write_state(s)
 b.transition_stage('D',reason,previous_status='partial_switched',foundation_only=False)
 b.save(ROOT/'long-horizon-review10-completed-20261009.json',dict(scientific_completed=60,current_stage='D',quality_goal_completed=False,next=decision['next'],budget=b.reconcile()));print(json.dumps(dict(review_completed=True,current_stage='D',C_consumed_render=used,C_remaining_render=149,quality_goal_completed=False),ensure_ascii=False))
if __name__=='__main__':main()
