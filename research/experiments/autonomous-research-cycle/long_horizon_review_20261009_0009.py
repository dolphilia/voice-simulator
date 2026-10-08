"""科学54件後のレビュー9。参照不通過と未保存を保持し限定aiuの学習へ配分。"""
import hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v9';NAME='long-horizon-review-v9'
SCIENCE=['nas-vtl-shared-target-preflight-20261009-v1','nas-vtl-shared-vowel-fit-20261009-a-v1','nas-vtl-shared-vowel-fit-20261009-i-v2','nas-vtl-shared-vowel-fit-20261009-u-v2','nas-vtl-native-reference-screen-20261009-v1','nas-vtl-native-reference-conditions-20261009-v1']
def main():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values());assert s['long_horizon']['scientific_completed']==54 and b.review_due(s)['due'];previous=s['long_horizon']['last_review'];assert previous['scientific_completed']==48 and digest(ROOT/previous['path'])==previous['sha256']
 limits=dict(seconds=3600,bytes=64000000,write_bytes=400000000,setup=6,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(review_number=9,trigger='前回48から科学六契約終了。技術停止を品質成果へ変換しない。',scientific_completed=54,previous_review=previous,limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'audit','新六封印/全分母/失敗/未実施/参照適格域/全費用を確認',reserve_bytes=12000000) as j:
  b.save(HERE/'registration.json',reg,j);checked={};seals={}
  for name in SCIENCE:
   path=ROOT/'campaigns'/name/'artifact-seal.json';seal=read(path);assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal['protected_confirmation_opened'];seals[str(path.relative_to(REPO))]=digest(path)
   for n,h in seal['files'].items():
    f=REPO/n;assert not any(p in f.parts for p in ('protected','holdout','splits'))
    if n in checked:assert checked[n]==h
    else:assert digest(f)==h,n;checked[n]=h
  b._science_ready(b.snapshot());assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in b.snapshot()['temporary_work'].values())
  preflight,a,i,u,screen,conditions=[read(ROOT/'campaigns'/n/'aggregate-summary.json') for n in SCIENCE]
  assert preflight['preflight_passed'] and a['all_scientific_waveforms_generated']==0 and not i['fit_valid'] and not u['fit_valid'] and screen['generated_references']==0 and conditions['selected_condition'] is None
  refs=read(ROOT/'campaigns'/SCIENCE[-1]/'data/references.json')['references'];usable=[]
  for v in 'aiueo':
   rows=[x for x in refs if x['condition']=='higher-longer' and x['vowel']==v];assert len(rows)==2
   if all(x['engineering_diagnostic_pass'] for x in rows):usable.append(v)
  assert usable==['a','i','u']
  diagnosis={}
  for v in 'iu':
   grid=read(ROOT/('campaigns/nas-vtl-shared-vowel-fit-20261009-'+v+'-v2/data/grid.json'))
   diagnosis[v]=dict(candidate_pass=sum(x['measurement']['engineering_diagnostic_pass'] for x in grid['rows']),candidate_total=18,reference_total=2,reference_pass=sum(x['measurement']['engineering_diagnostic_pass'] for x in grid['references'].values()),admissible_candidates=0,fit_count=1,inverse_count=1,selected_coefficients=[0.,0.],prior_gates_windows_gain_frozen=True)
  decision=dict(review_number=9,scientific_completed=54,previous_review=previous,shared_VTL_entry=dict(normal_isolated_CLI=True,denials=True,self_output_read=True,actual_render_calls=660,quality_certificate=False),old_lower_short_training=diagnosis,technical_failures=dict(a='依存PYTHONPATH未接続で生成0。3000render/300DSP予約を保持。',e_o_screen='2MBジョブ予約が16MB一時領域を満たさず生成0。4render/40DSPを保持。実OOMではない。'),new_reference_conditions=[dict(id=x['id'],pass_count=x['passed'],total=10,all_five_eligible=x['eligible']) for x in conditions['conditions']],new_reference_partial_scope=dict(condition='higher-longer',speed=.5,F0_Hz=[220,280],qualified_vowels=usable,unqualified_vowels=['e','o'],condition_not_selected_for_all_five=True,first_12_generated_results_unretained_and_unqualified=True,failed_row_not_repeated=True,remaining_17_only_generated=True,roles='全参照は訓練資格の再使用資料。新しい独立品質確認へ戻さない。'),
   allocation=dict(stage='C',abandoned='120/160Hz・speed1で五母音を同時にfitする旧経路と、三条件の五母音一括資格。i/uの不通過やa/e/oの未実施を救済しない。',new_question='既に波形診断を通過した別条件のaiu参照だけを訓練資料として再使用し、六つの共有TCX/TCY係数を事前九候補から直接学習できるか。e/oは既定値・未学習を保持。',target='aiuの固定包絡距離。三つの新有限fitを各別契約で初出力前登録し、実VTL両F0の診断を通過した候補だけ選ぶ。',development='学習した三母音と既定e/oを統合した後、Aで登録したCVの診断へ移る。未学習範囲と実写像を明示。',fit_runs_remaining_in_first_A_design=3,inverse_runs_remaining_in_first_A_design=3,new_parameters_at_most=6,one_factor='共有舌中央TCX/TCYだけ',per_fit_candidates=9,per_fit_render=2380,per_fit_seconds=7200,per_fit_retained_bytes=200000000,per_fit_write_bytes=1000000000,shared_reference_does_not_require_regeneration=True),
   actual_speech_quality_improvement_verified=False,content_ASR_improvement_verified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,no_common_condition_gate_relaxation=True,no_old_cohort_rescue_or_pool=True,no_public_audio_sending_or_contact=True,resource_status=b.review_due(),stage_clock=b.snapshot()['research_execution_plan'],next='工程Cの新限定aiu：通過済み高F0/長母音参照を再使用として固定し、各母音の実VTL九候補×二F0を直接fitする。最初にaを別の科学条件で登録し、旧a依存失敗の上限回避ではないことを明示する。')
  b.save(HERE/'integrity-audit.json',dict(new_six_seals=seals,checked_files=len(checked),checked_files_sha256=hashlib.sha256(encode(checked)).hexdigest(),old_management_sources_and_approval_exact=True,all_owned_temporary_absent=True,protected_text_read=False),j);b.save(HERE/'decision.json',decision,j)
  lines=['# 第9回定期レビューと限定aiu学習への配分','','科学54件終了。品質未達・知覚資格なし・P5未開封。技術停止二件を含む全費用・旧契約・封印を保持する。','','i/uの候補18波形ずつは全診断を通過したが、旧native参照は各0/2でDIO支持が欠測し、fitは各0/9の不採択。係数は0のまま。aは依存起動不成立、e/oの低F0参照は一時予約不足で未実施。','', '|別参照条件|通過/全分母|五母音共通条件|','|---|---:|---|']+[f"|{x['id']}|{x['pass_count']}/10|{x['all_five_eligible']}|" for x in decision['new_reference_conditions']]+['','五母音共通条件は不通過。高F0・長母音のaiu六参照だけが適格であり、これを新しい限定訓練資料として再使用する。e/o不通過を分母から消さず、旧選別や最終品質条件を緩めない。','','三つの新契約でaiuの六共有係数を学習し、実VTL波形を測定する。九候補・二F0・固定gain・同じ工学ゲートと包絡目的関数を初出力前に固定。訓練適合を内容や自然さへ昇格しない。元A設計の五fitのうち旧i/u二fitを消費済みで、残り三fitに収める。','','二ASR・知覚・一般化はこの六契約で未検証。初回十二波形の未保存計測は未資格、科学不通過は再試行せず未実施十七件だけを継続した。全所有一時物は回収済み。','',decision['next'],'']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=54,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(id='review9-completed-aiu-partial-training-ready',active_campaign=None,next=decision['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/'long-horizon-review9-completed-20261009.json',dict(scientific_completed=54,review_completed=True,current_stage='C',next=decision['next'],budget=b.reconcile()));print(json.dumps(dict(review_completed=True,qualified_new_training_vowels=usable,quality_goal_completed=False),ensure_ascii=False))
if __name__=='__main__':main()
