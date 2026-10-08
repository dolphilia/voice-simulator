"""低F0短母音の参照欠測を保持し、別条件でnative参照の測定成立域を調べる。"""
import argparse,ast,hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
from vtl_native_reference_screen_20261009 import PREFIX,SOURCE,PYTHON
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1';NAME='vtl-native-reference-conditions-v1'
CONDITIONS=[dict(id='higher-normal',speed=1.,F0_Hz=[220,280]),dict(id='lower-longer',speed=.5,F0_Hz=[120,160]),dict(id='higher-longer',speed=.5,F0_Hz=[220,280])]
WORKER=PREFIX.replace("verify();spec=json.loads((here/'registration.json').read_text());centers","verify();centers")+r'''
study=Path(sys.argv[3]);reg=json.loads((study/'registration.json').read_text());refs=[];render_calls=0
for cond in reg['conditions']:
 for vowel,text in zip('aiueo',['ア','イ','ウ','エ','オ']):
  for target in cond['F0_Hz']:
   data,meta,params,row=native(text,cond['speed'],target,full=True);render_calls+=meta['conversion']['render_calls_including_internal_MLSA'];measure_calls+=3
   assert meta['settings']['sampling_frequency']==48000 and meta['settings']['fperiod']==240
   indices=[i for i,label in enumerate(row['full_context_labels']) if re.search(r'\-([^+]+)\+',label).group(1).lower()==vowel];assert len(indices)==1
   i=indices[0];bounds=np.r_[0,np.cumsum(meta['duration'])]*.005;start,end=float(bounds[i*5]),float(bounds[(i+1)*5]);width=end-start
   measurement=measure(data,[start+.2*width,end-.2*width],target);ident=cond['id']+'-'+vowel+'-'+str(int(target));(work/(ident+'.wav')).write_bytes(data)
   refs.append(dict(id=ident,condition=cond['id'],speed=cond['speed'],vowel=vowel,text=text,target_F0_Hz=target,wav_sha256=hashlib.sha256(data).hexdigest(),source_state_interval_seconds=[start,end],label_boundary_not_observed_truth=True,measurement=measurement,native_gain=.25,settings=meta['settings']))
assert render_calls==30 and measure_calls==300
(work/'references.json').write_text(json.dumps(dict(references=refs,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,protected_confirmation_opened=False),ensure_ascii=False,allow_nan=False))
print(json.dumps(dict(actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,output_files=[x['id']+'.wav' for x in refs])))
'''
def verify():
 c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(REPO/n)==h,n
def register():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due'];check_plan(s,3600);ast.parse(WORKER)
 limits=dict(seconds=3600,bytes=256000000,write_bytes=800000000,setup=6,audit=6,render=64,dsp=640,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(question='native参照のF0と母音の生成長を変えた新訓練条件で、五母音の固定波形診断を満たす共通条件があるか。旧120/160Hz・speed1.0の学習コホートを救済しない。',controller_sha256=digest(Path(__file__)),native_source_manifest_sha256=digest(SOURCE/'native-bundle/manifest.json'),conditions=CONDITIONS,condition_selection_priority=[x['id'] for x in CONDITIONS],selection='一条件で五母音二F0の全10参照が同じE0/F0支持を通過したものだけを候補とし、事前優先順で最初の一条件を次契約の訓練候補にする。次契約では実VTL適格性も新条件で検証する。全不通過なら新条件も採択せず別経路。',roles=dict(train_qualification='再使用nativeモデル/母音入力による新条件の診断。教師内部時計は真の音素境界ではない。',old_lower_short='i/uの固定120/160・speed1を保持し再生成/再判定しない。e/o同条件は予約不足で未実施、未知のまま。a旧grid未生成。',development_and_unused_selection='未使用。旧結果と異なるコホートの率はpoolしない。',P5_opened=False),gates='中央生成state60%・旧測定器のE0、DIO/stonemaskとACF±1半音/confidence.6、DIO3frame以上/有声半数以上。一母音診断のみ。',gain=.25,estimates=dict(native_render=30,DSP_macro=300,fit=0,inverse=0,retained_WAV_bytes_at_most=6000000,JSON_bytes_at_most=1000000,work_peak_bytes=64000000,work_write_bytes=128000000,render_job_reservation_bytes=96000000,DSP_job_reservation_bytes=2000000,logs_at_most=2000000,RAM_at_most=1000000000,control_index_failed_job_Git_included=True),technical_stopping='同じ失敗ラベルで追加一回を上限64render/640DSPの開始前枠内に確保。成功ラベル再使用/科学不通過の技術再試行はしない。',limits=limits,quality_goal_completed=False,original_condition_failure_not_rescued=True)
 assert reg['estimates']['work_peak_bytes']<=reg['estimates']['render_job_reservation_bytes']
 assert reg['estimates']['render_job_reservation_bytes']+reg['estimates']['DSP_job_reservation_bytes']+reg['estimates']['work_peak_bytes']+4000000<limits['bytes']
 assert reg['estimates']['work_write_bytes']*2+100000000<limits['write_bytes']
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
 with b.job(NAME,'setup','新F0/生成長/参照役割/優先順/全費用の初出力前固定',reserve_bytes=6000000) as j:
  b.save(HERE/'registration.json',reg,j);b.write(HERE/'worker.py',WORKER.encode(),j)
  paths=[Path(__file__),ROOT/'vtl_native_reference_screen_20261009.py',ROOT/'vtl_shared_vowel_fit_20261009_v2.py',HERE/'worker.py',HERE/'registration.json',SOURCE/'native-bundle/manifest.json']+[SOURCE/'native-bundle'/n for n in read(SOURCE/'native-bundle/manifest.json')['files']]
  b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(REPO)):digest(p) for p in paths}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=NAME,next='保存後に新三条件30native参照だけを診断。科学54終了時の定期レビューを先に行う。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-native-reference-conditions-register-20261009.json',dict(active_campaign=NAME,registered_before_outputs=True,old_unmeasured_and_failures_retained=True,budget=b.reconcile()));print('新三条件30参照の成立域を初出力前登録')
def run():
 b=Budget();b.recover();verify()
 r=b.reserve(NAME,'render','新三条件五母音二F0のnative参照',30,96000000,expected_seconds=600)
 try:
  d=b.reserve(NAME,'dsp','新条件30参照の固定E0/F0/包絡',300,2000000,expected_seconds=600)
  try:
   with b.workspace(r,'新三条件の参照資格だけを測定する所有領域',64000000,128000000) as (work,env):
    env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    attempt=read(b.state_path)['campaigns'][NAME]['attempts']['render:新三条件五母音二F0のnative参照'][-1]['id']
    stdout,stderr,observed=run_observed([str(PYTHON),'-B',str(HERE/'worker.py'),str(SOURCE),str(work),str(HERE)],env,work,label='reference-conditions',timeout=540)
    b.save(HERE/('process-observation-'+attempt+'.json'),observed,r)
    if observed['returncode']!=0:
     b.save(HERE/('failure-'+attempt+'.json'),dict(stdout=stdout,stderr=stderr),r);raise RuntimeError('新条件参照診断の技術起動不成立')
    counts=json.loads(stdout);b.save(HERE/'generation-counts.json',counts,r);b.save(HERE/'successful-process.json',dict(path='process-observation-'+attempt+'.json'),r)
    b.write_data(HERE/'data/references.json',(work/'references.json').read_bytes(),r)
    for n in counts['output_files']:b.write_data(HERE/'audio'/n,(work/n).read_bytes(),r)
  except BaseException as e:b.finish(d,repr(e));raise
  else:b.finish(d)
 except BaseException as e:b.finish(r,repr(e));raise
 else:b.finish(r)
 with b.job(NAME,'audit','新条件全参照/不通過/成立域/費用/回収の封印',reserve_bytes=5000000) as j:
  value=read(HERE/'data/references.json');results=[]
  for cond in CONDITIONS:
   rows=[x for x in value['references'] if x['condition']==cond['id']];assert len(rows)==10
   results.append(dict(**cond,reference_total=10,passed=sum(x['measurement']['engineering_diagnostic_pass'] for x in rows),eligible=all(x['measurement']['engineering_diagnostic_pass'] for x in rows),rows=[dict(id=x['id'],vowel=x['vowel'],F0=x['target_F0_Hz'],interval=x['source_state_interval_seconds'],E0=x['measurement']['E0']['E0_pass'],pitch=x['measurement']['pitch']) for x in rows]))
  selected=next((x['id'] for x in results if x['eligible']),None)
  summary=dict(conditions=results,selected_condition=selected,condition_selection_preregistered=True,reference_total=30,candidate_generation_or_fit_performed=False,prior_conditions_and_failures_frozen=True,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False)
  b.save(HERE/'aggregate-summary.json',summary,j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(HERE/'cost-audit.json',dict(counts=c['counts'],actual=read(HERE/'generation-counts.json'),seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,process=read(HERE/read(HERE/'successful-process.json')['path'])),j)
  lines=['# 別訓練条件におけるnative参照の成立域','','旧短母音120/160Hzコホートの窓・利得・ゲートを変えず、別に登録した三条件を測定した。全30参照を保持する。','', '|条件|参照通過|共通訓練候補|','|---|---:|---|']
  for x in results:lines.append('|'+x['id']+'|'+str(x['passed'])+'/10|'+str(x['eligible'])+'|')
  lines+=['','事前優先順による新条件候補: '+str(selected),'','これはnative参照の診断のみ。実VTL学習、内容、自然さ、一般化の成果ではない。品質未達、P5未開封。']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=None,next='科学54件後のレビュー9を先に行い、旧不通過/未実施を保持して新条件の採否と次の直接学習を登録する。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-native-reference-conditions-completed-20261009.json',dict(selected_condition=selected,conditions=[dict(id=x['id'],passed=x['passed'],eligible=x['eligible']) for x in results],review=b.review_due(),budget=b.reconcile()));print(json.dumps(dict(selected_condition=selected,conditions=[dict(id=x['id'],passed=x['passed']) for x in results]),ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);a=p.parse_args();globals()[a.stage]()
