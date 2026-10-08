"""所有一時領域の読取許可だけを直す技術アダプタ。旧上限・費用・科学条件を保持。"""
import argparse,importlib.util,json,hashlib,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
spec=importlib.util.spec_from_file_location('frozen_phrase_original',ROOT/'vtl_frozen_phrase_suite_20261009_v2.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
HERE,NAME=m.campaign_location('fixture')
base_profile=m.profile;base_observe=m.observe
def profile(b,work,method,isolated):
 p=base_profile(b,work,method,isolated)
 if isolated:p+='(allow file-read-data (subpath '+json.dumps(str(work))+'))\n'
 return p
m.profile=profile
def verify():
 m.verify();c=read(HERE/'technical-adapter-contract.json');assert digest(Path(__file__))==c['adapter_sha256']
 assert digest(ROOT/'vtl_frozen_phrase_suite_20261009_v2.py')==c['original_controller_sha256']
def register():
 b=Budget();b.recover();m.verify();s=b.snapshot();c=s['campaigns'][NAME]
 assert c['counts']['render']==1714 and c['limits']['render']==2571 and not s['jobs']
 reg=dict(adapter_sha256=digest(Path(__file__)),original_controller_sha256=digest(ROOT/'vtl_frozen_phrase_suite_20261009_v2.py'),failure_sha256=digest(HERE/'isolated-native-failure.json'),reason='所有workをallow file-read*していたが、外部rootのより具体的file-read-data拒否が勝った。所有workへのfile-read-dataだけ追加。科学条件/共有資産/その他拒否/旧ゲートは変更なし。',same_failed_label_retry_count=857,remaining_original_render_cap=857,old_failed_reservation_kept=857,normal_success_not_repeated=True,unstarted_CLI_moved_to_new_finite_piece=True,stage_D_original_allocation=36000,original_suite_forecast=30537,forecast_including_failed_job=31394,no_cap_increase_or_refund_or_cycle_reset=True)
 with m.job(b,NAME,'setup','所有領域読取だけの技術修正と未実施CLIの配分追記',size=4000000) as j:b.save(HERE/'technical-adapter-contract.json',reg,j)
 m.checkpoint(b,NAME,'技術修正登録push→旧失敗isolatedラベルを旧残857以内で一回のみ再試行→未実施CLIを新有限部分へ。')
 print('所有領域読取の技術修正だけを登録')
def retry():
 b=Budget();b.recover();verify();first=read(m.HERE/'protocol.json')['rows'][0]['id'];requests=[q for q in m.requests() if q['id'].startswith(first+'/neutral/')]
 def observe(*args,**kwargs):
  args=list(args);args[4]=args[4]+'-retry1';return base_observe(*args,**kwargs)
 m.observe=observe
 with m.job(b,NAME,'render','D小入口 isolated 全内部生成',857,100000000,900) as j:
  with m.job(b,NAME,'dsp','D小入口 isolated 自己WAV全E0',24,2000000,900) as d:rows=m.runtime(b,NAME,HERE,requests,'isolated',j,d)
 normal=[x for method in m.METHODS for x in read(HERE/('normal-'+method+'-manifest.json'))['rows']]
 exact={x['request']['id']:x['wav_sha256'] for x in rows}=={x['request']['id']:x['wav_sha256'] for x in normal}
 e0=all(x['E0'] and x['E0']['E0_pass'] for x in rows+normal)
 assert exact and e0
 summary=dict(expected_original_fixture_waveforms=9,completed_original_fixture_waveforms=6,normal_and_isolated_exact=exact,normal_and_isolated_E0=bool(e0),CLI_unperformed=3,preflight_passed=False,partial_technical_recovery=True,old_failed_render_reservation_kept=857,new_render_original_campaign_cap=2571,quality_goal_completed=False,old_gate_not_lowered=True)
 m.seal_close(b,HERE,NAME,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
def cli_register():
 verify();m.register_piece('cli-continuation',857,48)
def denial(b,name,here):
 with m.job(b,name,'audit','旧計画の候補の依存拒否を実検査',size=100000000) as j:
  past=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1/audio/higher-longer-a-220.wav';data=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1/data/references.json'
  blocked=[past,past.resolve(),data,data.resolve(),m.NATIVE/'mei_normal.htsvoice',m.HERE/'protocol.json'];assert all(p.is_file() for p in blocked)
  with b.workspace(j,'D候補の論理/外部実体/原HMM/通信拒否',32000000,64000000) as (work,env):
   m.env_settings(env)
   code="import json,socket,errno;paths="+repr([str(p) for p in blocked])+";rows=[]\nfor p in paths:\n try:\n  open(p,'rb').read(1);rows.append(dict(path=p,denied=False))\n except OSError as e:rows.append(dict(path=p,denied=e.errno in [1,13]))\ns=socket.socket();network=False\ntry:s.connect(('1.1.1.1',443))\nexcept OSError as e:network=e.errno in [1,13]\nfinally:s.close()\nprint(json.dumps(dict(rows=rows,network_denied=network,all_denied=all(x['denied'] for x in rows))))"
   value=m.observe(b,work,env,[str(m.PYTHON),'-I','-B','-c',code],'denial-probe',j,here,isolated=True,method='learned',timeout=30)
  assert value['all_denied'] and value['network_denied'];b.save(here/'denial-audit.json',value,j)
def cli():
 b=Budget();b.recover();verify();here,name=m.campaign_location('cli-continuation');first=read(m.HERE/'protocol.json')['rows'][0]['id'];requests=[q for q in m.requests() if q['id'].startswith(first+'/neutral/')]
 m.check_D(b,857)
 with m.job(b,name,'render','未実施D単独CLI三方式の全内部費',857,100000000,900) as j:
  with m.job(b,name,'dsp','未実施D単独CLI自己WAV全E0',24,2000000,900) as d:rows=m.runtime(b,name,here,requests,'cli',j,d)
 expected={x['request']['id']:x for method in m.METHODS for x in read(HERE/('normal-'+method+'-manifest.json'))['rows']}
 exact=all(x['wav_sha256']==expected[x['request']['id']]['wav_sha256'] for x in rows);allE0=all(x['E0'] and x['E0']['E0_pass'] for x in rows)
 assert exact and allE0;denial(b,name,here)
 old=read(HERE/'aggregate-summary.json');assert old['normal_and_isolated_exact'] and old['normal_and_isolated_E0']
 summary=dict(preflight_passed=True,whole_fixture_expected=9,whole_fixture_completed=9,normal_isolated_CLI_exact=True,all_E0=9,total_internal_render_reservations_including_failed=3428,actual_render_success=2571,failed_isolated_reservation_kept=857,original_contract_closed_without_cap_change=True,unstarted_CLI_only_new_piece=True,owned_work_read_permission_only_fix=True,all_denials=True,quality_goal_completed=False)
 m.seal_close(b,here,name,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
def batch_register(mode,length,condition):
 verify();assert read(m.campaign_location('cli-continuation')[0]/'aggregate-summary.json')['preflight_passed']
 plan=m.batch_plan(mode,length,condition);m.register_piece(mode+'-'+length+'-'+condition,plan['render_reservation'],200)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','retry','cli-register','cli','batch-register','batch','asr-register','asr','close']);p.add_argument('--mode',choices=['normal','isolated']);p.add_argument('--length',choices=['short','long']);p.add_argument('--condition',choices=['neutral','higher']);p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args()
 if a.stage=='register':register()
 else:
  verify()
  if a.stage in ['batch-register','batch']:
   (batch_register if a.stage=='batch-register' else m.batch)(a.mode,a.length,a.condition)
  elif a.stage in ['asr-register','asr']:(m.asr_register if a.stage=='asr-register' else m.asr)(a.engine)
  elif a.stage=='close':m.close()
  else:globals()[a.stage.replace('-','_')]()
