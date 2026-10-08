"""科学66後のレビュー11。D途中の全分母/予約障害/残配分を保持し、未実施比較へ。"""
import hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-long-horizon-review-20261009-v11';NAME='long-horizon-review-v11'
SCIENCE=['fixture','cli-continuation','normal-short-neutral','measure-normal-short-neutral','normal-short-higher','normal-long-neutral']
def location(label):return ROOT/('campaigns/nas-vtl-frozen-phrase-'+label+'-20261009-v1')
def main():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values())
 assert s['long_horizon']['scientific_completed']==66 and b.review_due(s)['due']
 previous=s['long_horizon']['last_review'];assert previous['scientific_completed']==60 and digest(ROOT/previous['path'])==previous['sha256']
 limits=dict(seconds=3600,bytes=64000000,write_bytes=500000000,setup=6,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(review_number=11,scientific_completed=66,previous_review=previous,trigger='科学六終了。分割の科学時計と失敗費用を保持。',limits=limits,controller_sha256=digest(Path(__file__)),scientific_outputs=0,quality_goal_completed=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'audit','新六封印/途中全分母/資源障害/残配分を照合',reserve_bytes=16000000) as j:
  b.save(HERE/'registration.json',reg,j);checked={};seals={}
  for label in SCIENCE:
   path=location(label)/'artifact-seal.json';seal=read(path);assert seal['experiment_completed'] and not seal['quality_goal_completed'] and not seal.get('P5_opened',False);seals[str(path.relative_to(REPO))]=digest(path)
   for n,h in seal['files'].items():
    assert not any(x in Path(n).parts for x in ['protected','holdout','splits'])
    if n in checked:assert checked[n]==h
    else:assert digest(REPO/n)==h,n;checked[n]=h
  b._science_ready(b.snapshot());tmp=b.snapshot()['temporary_work'];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp.values())
  suite=location('suite');p=read(suite/'protocol.json');plan=read(suite/'render-plan.json')
  sections={label:read(location(label)/'aggregate-summary.json')['engineering'] for label in ['measure-normal-short-neutral','normal-short-higher','normal-long-neutral']}
  entry=read(location('cli-continuation')/'aggregate-summary.json');assert entry['preflight_passed']
  current=b.snapshot()['counts']['render'];used=current-p['stage_D_start_render']
  remaining=sum(x['render_reservation'] for x in plan['batches'] if not (location(x['mode']+'-'+x['length']+'-'+x['condition'])/'artifact-seal.json').exists())
  assert used+remaining==31394 and used+remaining<=36000
  decision=dict(review_number=11,scientific_completed=66,previous_review=previous,current_stage='D',candidate_frozen_model_sha256=digest(ROOT/'vtl-shared-aiu-model-20261009.json'),entry=entry,engineering_sections=sections,normal_records_measured=36,normal_expected=48,isolated_full_batch_records_done=0,isolated_entry_reusable_records=3,isolated_expected=48,CLI_done=3,CLI_expected=3,content_ASR_not_started=True,old_C_failures_and_s_unperformed_kept=True,resource_failures=[dict(kind='isolation_owner_read_policy',render_failed_reservation=857,actual_failed_audio=0,observed_memory_termination=False,physical_storage_exhaustion=False,old_cap_not_increased=True),dict(kind='cumulative_workspace_reservation',generated_audio_retained=12,DSP_failed_reservation=200,measurement_started=False,new_render_for_measurement=0,observed_memory_termination=False,physical_storage_exhaustion=False,old_cap_not_increased=True)],D_allocation=dict(start_render=p['stage_D_start_render'],current_render=current,consumed=used,remaining_planned=remaining,original_forecast=30537,forecast_including_all_failed_render=31394,maximum=36000,unallocated=36000-used-remaining,projected_global_render=current+remaining,global_render70_percent_threshold=84000,margin_before70=84000-current-remaining),resources=b.review_due(),stage_clock=b.snapshot()['research_execution_plan'],quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False,actual_generalizable_speech_improvement_verified=False,no_cohort_pool=True,no_post_output_rescue=True,next='工程Dの固定全体を継続。次は未実施normal-long-higher、その後isolated四バッチと二ASR。追加render失敗が151を超えると70%境界へ達するため、境界をまたぐ新予約の前に配分レビューを追記。C/旧比較の係数・窓・gain・支持/ゲートを救済しない。全体終了後、同経路のCV/語句不通過と残資源をレビューして新しい音声改善要因へ切り替える。')
  b.save(HERE/'integrity-audit.json',dict(seals=seals,checked_files=len(checked),checked_files_digest=hashlib.sha256(encode(checked)).hexdigest(),all_owned_temporary_absent=True,old_guards_and_approval_hashes_valid=True,P5_text_read=False),j);b.save(HERE/'decision.json',decision,j)
  lines=['# 第11回レビュー：工程Dの途中結果','','科学66件。研究は継続、品質未達、知覚資格なし、P5未開封。','','|範囲|方式|全E0|固定支持/F0|','|---|---|---:|---:|']
  for label,methods in sections.items():
   for method,x in methods.items():lines.append(f"|{label}|{method}|{x['E0_pass']}/{x['expected']}|{x['pitch_pass']}/{x['expected']}|")
  lines+=['','通常/隔離/実CLIの先行9出力はbyte一致・全E0通過。所有workの読取拒否と、workspace予約の累積消費による測定前停止を技術障害として保持する。どちらもOOM/媒体実空き枯渇ではない。生成成功波形は再生成せず、旧上限を増やさず未実施部分を別の有限契約へ継承した。','',f"全失敗込みのD予定は31,394/36,000 render、全体83,849/120,000。70%境界まで151しかないので、追加失敗予約の前に再レビューする。",'','学習後の工学/内容改善は未確認。最低3音素の固定支持不足やACF不通過を欠測/不通過として保持し、異なる条件/旧コホートをpoolしない。全33系列のgroup4..7は0分母・不通過。二ASR、通常残12/隔離残45を未実施として保持。','',decision['next'],'']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},management_review_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['long_horizon']['last_review']=dict(seconds=s['seconds'],scientific_completed=66,path=str((HERE/'decision.json').relative_to(ROOT)),sha256=digest(HERE/'decision.json'));s['continuation_checkpoint'].update(active_campaign=None,id='review11-D-in-progress',next=decision['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/'long-horizon-review11-completed-20261009.json',dict(scientific_completed=66,current_stage='D',quality_goal_completed=False,next=decision['next'],budget=b.reconcile()));print(json.dumps(dict(review_completed=True,stage='D',D_projected_render=31394,global_render_projected=83849,margin_before70=151,quality_goal_completed=False),ensure_ascii=False))
if __name__=='__main__':main()
