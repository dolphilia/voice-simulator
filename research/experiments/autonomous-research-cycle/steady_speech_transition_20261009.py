"""初回A〜Dの全体終了を保存し、既消費・凍結時計を保持して後続入口へ移る。"""
import argparse,ast,copy,hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode,MARGIN
from research_plan_budget_20261009 import ResearchPlanBudget,check_plan
from steady_speech_budget_20261009 import SteadySpeechBudget,prepare_transition
from observed_process_20261009 import run_observed
from long_horizon_budget import TOTALS,CLOSING_SECONDS
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-steady-speech-transition-20261009-v1';NAME='steady-speech-transition-v1';PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
def register():
 b=ResearchPlanBudget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values())
 assert s['long_horizon']['scientific_completed']==73 and not b.review_due(s)['due'];assert read(ROOT/'campaigns/nas-vtl-frozen-phrase-whole-summary-20261009-v1/aggregate-summary.json')['adopted'] is False
 lim=dict(seconds=3600,bytes=128000000,write_bytes=600000000,setup=8,audit=8,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(controller_sha256=digest(Path(__file__)),limits=lim,cycle=s['cycle'],scientific_completed=73,first_stage_current='D',goal_achieved=False,whole_D_seal_sha256=digest(ROOT/'campaigns/nas-vtl-frozen-phrase-whole-summary-20261009-v1/artifact-seal.json'),plan_sha256=s['research_execution_plan']['plan_sha256'],prompt_sha256=s['research_execution_plan']['prompt_sha256'],reason='初回A〜Dの比較手順が終了し、六TCX/TCY係数はCV二組とD語句で不通過。不採択と旧未実施sを保持。再開後の工程上限を巻戻さず、同じ長期総枠の残資源で異なる音声改善要因へ自律継続するため、後続時計を追加する。',new_scientific_calls=0,no_reset_or_increase=True,kept_long_horizon_last_review=s['long_horizon']['last_review'],sources={str((ROOT/n).relative_to(REPO)):digest(ROOT/n) for n in ['steady_speech_budget_20261009.py','test_steady_speech_budget_20261009.py','steady_speech_transition_20261009.py','research_plan_budget_20261009.py','long_horizon_budget.py','observed_process_20261009.py']})
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),lim,hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with b.job(NAME,'setup','初回工程終了後の最小管理境界を登録',reserve_bytes=4000000) as j:b.save(HERE/'registration.json',reg,j)
 print('後続時計の管理検証を登録',flush=True)
def validate():
 b=ResearchPlanBudget();b.recover();reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256']
 for n,h in reg['sources'].items():assert digest(REPO/n)==h,n
 with b.job(NAME,'setup','初回凍結/既消費/停止/同時予約/終了12h/基盤継承の否定検査',reserve_bytes=100000000) as j:
  with b.workspace(j,'後続管理ガードの純状態検査',16000000,32000000) as (work,env):
   out,err,obs=run_observed([str(PYTHON),'-B',str(ROOT/'test_steady_speech_budget_20261009.py')],env,work,label='guard-tests',timeout=60)
   b.save(HERE/'process-observation.json',obs,j);b.save(HERE/'test-output.json',dict(stdout=out,stderr=err),j)
  count=sum(isinstance(n,ast.FunctionDef) and n.name.startswith('test_') for n in ast.walk(ast.parse((ROOT/'test_steady_speech_budget_20261009.py').read_text())))
  assert obs['returncode']==0 and ('Ran '+str(count)+' tests') in err and 'OK' in err
  b.save(HERE/'guard-validation.json',dict(passed=True,test_count=count,validated_sources=reg['sources'],pure_management_fixtures=True,not_quality_evidence=True,new_scientific_calls=0,old_clock_and_resource_caps_and_stop_and_closing_preserved=True),j)
 with b.job(NAME,'audit','管理検証/旧源/一時不存在を封印',reserve_bytes=5000000) as j:
  s=b.snapshot();assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in s['temporary_work'].values())
  b._science_ready(s);b.save(HERE/'integrity-audit.json',dict(old_guards_and_approval_valid=True,all_owned_temporary_absent=True,sources=reg['sources'],new_scientific_calls=0),j)
  b.write(HERE/'report.md',('# 初回工程終了後の後続時計検証\n\n'+str(count)+'否定検査通過。初回A/B/C/Dの上限/消費/部分終了を凍結し、同じcycle・長期総枠・基盤12時間・科学6件/24時間レビューを継承する。既消費や失敗の返金、旧s組の移し替え、旧不通過の救済はしない。\n\n実台帳の遷移と新入口の統合確認は、次の原子的境界保存で実施する。品質未達、知覚資格なし、P5未開封。\n').encode(),j)
  b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},management_completed=True,scientific_outputs=0,quality_goal_completed=False),j)
 b.close_campaign(NAME);print(str(count)+'管理否定検査を通過',flush=True)
def transition():
 old=ResearchPlanBudget();old.recover();validation=HERE/'guard-validation.json';reg=read(HERE/'registration.json');assert read(validation)['passed']
 for n,h in reg['sources'].items():assert digest(REPO/n)==h,n
 path=ROOT/'steady-speech-boundary-20261009-v1.json';assert not path.exists()
 with old.locked():
  s=old._load();old._science_ready(s);assert s['long_horizon']['scientific_completed']==73
  changed=prepare_transition(s,reg['reason'],str(validation.relative_to(ROOT)),digest(validation));p=changed['research_execution_plan'];v=p['steady_phase']
  boundary=dict(cycle=changed['cycle'],first_stage=copy.deepcopy(p['first_stage']),first_stage_sha256=v['first_stage_sha256'],started_cumulative_seconds=v['started_cumulative_seconds'],started_counts=v['started_counts'],started_write_bytes=v['started_write_bytes'],started_scientific_completed=v['started_scientific_completed'],last_review_unchanged=changed['long_horizon']['last_review'],foundation_used_seconds=p['foundation_only']['used_seconds'],long_horizon_limits=changed['limits'],guard_validation=v['guard_validation'],whole_D_seal_sha256=reg['whole_D_seal_sha256'],quality_goal_completed=False,P5_opened=False,clock_reset=False,budget_increase=False)
  data=encode(boundary);v['boundary_sha256']=hashlib.sha256(data).hexdigest();name=str(path.relative_to(ROOT))
  # Budget.writeと同じ保存前予約/index/排他xb/fsync/実mtime確定を使用する。
  # 工程切替中に旧_loadを再入しないため、同じ排他lock内でこの小JSONだけを保存する。
  old._check(s,len(data));old.set_file(changed,name,[len(data),None]);changed['payload_bytes']+=len(data);changed['write_bytes']+=len(data)
  old.event(changed,dict(event='first_stage_frozen_steady_started',first_stage_sha256=v['first_stage_sha256'],scientific_completed=73,counts_kept=True,cycle_unchanged=True,quality_goal_completed=False));changed['continuation_checkpoint'].update(active_campaign=None,id='first-stage-frozen-steady-active',next='後続入口SteadySpeechBudgetを使用。六係数法は撤退し、権利/由来を確認できる参照と低費用の直接非ニューラル方式を新要因として事前登録する。新render70%越えの前に配分レビュー。',git_save_pending=True)
  old._write_state(changed)
  with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
  old.set_file(changed,name,[path.stat().st_size,path.stat().st_mtime_ns]);new=SteadySpeechBudget();new._check(changed);old._write_state(changed)
 new=SteadySpeechBudget();s=new.snapshot();new._science_ready(s)
 denied=False
 try:check_plan(copy.deepcopy(s))
 except (RuntimeError,StopIteration):denied=True
 assert denied
 new.save(ROOT/'steady-speech-transition-completed-20261009.json',dict(current_phase='steady',old_first_stage_entry_denied=True,new_entry_full_old_and_new_guards_passed=True,first_stage_sha256=s['research_execution_plan']['steady_phase']['first_stage_sha256'],all_jobs_closed=True,all_owned_temporary_absent=True,cycle=s['cycle'],scientific_completed=73,last_review_unchanged=s['long_horizon']['last_review'],quality_goal_completed=False,P5_opened=False,budget=new.reconcile()))
 print(json.dumps(dict(phase='steady',scientific_completed=73,old_first_stage_entry_denied=True,cycle_unchanged=True,quality_goal_completed=False),ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','validate','transition']);q=p.parse_args();globals()[q.stage]()
