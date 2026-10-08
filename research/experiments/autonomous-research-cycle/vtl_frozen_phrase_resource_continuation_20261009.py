"""生成済み波形を保持して未実施測定だけを継続。後続の所有一時予約を実測内で縮小。"""
import argparse,ast,importlib.util,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
spec=importlib.util.spec_from_file_location('recovery_original',ROOT/'vtl_frozen_phrase_fixture_recovery_20261009.py');r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r);m=r.m
HERE,NAME=m.campaign_location('normal-short-neutral')
MEASURE,MNAME=m.campaign_location('measure-normal-short-neutral')
# 旧科学生成のソースと規則は同一。新しい未実施バッチでは作業上限だけ32→16MBに縮小する。
source=(ROOT/'vtl_frozen_phrase_suite_20261009_v2.py').read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='runtime')
runtime_source=ast.get_source_segment(source,node);assert runtime_source.count('32000000,64000000')==1
exec(runtime_source.replace('32000000,64000000','16000000,32000000'),m.__dict__)
def verify():
 r.verify()
 if (MEASURE/'continuation-contract.json').exists():
  c=read(MEASURE/'continuation-contract.json');assert digest(Path(__file__))==c['controller_sha256']
def partial_close():
 b=Budget();b.recover();verify();s=b.snapshot();assert not s['jobs'] and s['campaigns'][NAME]['counts']['render']==2571
 rows=[x for method in m.METHODS for x in read(HERE/('normal-'+method+'-manifest.json'))['rows']]
 fixture=m.campaign_location('fixture')[0]
 rows += [x for method in m.METHODS for x in read(fixture/('normal-'+method+'-manifest.json'))['rows']]
 assert len(rows)==12
 for row in rows:
  if row['wav']:assert digest(m.REPO/row['wav'])==row['wav_sha256']
 with m.job(b,NAME,'audit','保存済み全12生成を保持し未実施測定を明示',size=6000000) as j:b.save(HERE/'render-manifest.json',dict(rows=rows,expected=12,reused=3,mode='normal'),j)
 engineering={method:dict(expected=4,E0_pass=sum(bool(x['E0'] and x['E0']['E0_pass']) for x in rows if x['request']['method']==method),pitch_pass=0,missing_records=4,fixed_support_intervals=0,missing_support=0) for method in m.METHODS}
 summary=dict(label='normal-short-neutral',expected_records=12,all_generated_records_retained=True,reused=3,engineering=engineering,fixed_support_measurement_unperformed=True,technical_reason='render job予約はworkspace毎に減るため、三生成workspace後の第4測定workspaceの32MBを満たせなかった。実ディスク/RAM枯渇ではない。',old_render2571_and_failed_DSP200_kept=True,no_regeneration=True,no_original_cap_change=True,quality_goal_completed=False)
 m.seal_close(b,HERE,NAME,summary);print('全12保存波形を保持し、測定未実施の部分結果として旧契約を終了')
def measurement_register():
 verify();m.register_piece('measure-normal-short-neutral',0,50);b=Budget()
 with m.job(b,MNAME,'setup','未実施測定のみと後続一時予約縮小を登録',size=4000000) as j:
  measured_sizes={p.name:p.stat().st_size for p in HERE.iterdir() if p.is_file()}
  b.save(MEASURE/'continuation-contract.json',dict(controller_sha256=digest(Path(__file__)),original_suite_controller_sha256=digest(ROOT/'vtl_frozen_phrase_suite_20261009_v2.py'),isolation_adapter_sha256=digest(ROOT/'vtl_frozen_phrase_fixture_recovery_20261009.py'),render_manifest_sha256=digest(HERE/'render-manifest.json'),old_seal_sha256=digest(HERE/'artifact-seal.json'),new_render=0,new_fit=0,new_inverse=0,fixed_measurement_source_sha256=digest(m.HERE/'measurement_worker.py'),same_gates_and_audio_and_clock=True,old_failed_costs_kept=True,measurement_workspace_maximum_bytes=32000000,measurement_job_reserve_bytes=100000000,future_generation_workspace_maximum_bytes=16000000,prior_generation_workspace_upper=32000000,measured_manifest_sizes=measured_sizes,reason='通常生成三workは最大量内で完了。後続で生成の各上限を16MB/書込32MBへ縮小し、予約100MBから三work48MB・音声/記録約数MB・測定32MBを累積確保。科学コード/係数/ゲートは変えない。',P5_opened=False,quality_goal_completed=False),j)
 print('未実施の固定支持測定だけを登録')
def measurement():
 b=Budget();b.recover();verify();rows=read(HERE/'render-manifest.json')['rows'];by={};phones={}
 for row in rows:
  key=row['request']['id'].rsplit('/',1)[0];by.setdefault(key,{})[row['request']['method']]=row
  spec=next(x for x in read(m.HERE/'protocol.json')['rows'] if x['id']==key.split('/')[0]);phones[key]=spec['phones']
 with m.job(b,MNAME,'dsp','保存済み短neutral全12の未実施固定支持測定',50,100000000,900) as j:
  with b.workspace(j,'保存済みWAVだけの固定支持/全体ACF測定',32000000,64000000) as (work,env):
   m.env_settings(env)
   for row in rows:
    if row['wav']:
     assert digest(m.REPO/row['wav'])==row['wav_sha256'];(work/row['file']).write_bytes((m.REPO/row['wav']).read_bytes())
   (work/'measurement-input.json').write_bytes(encode(dict(cases=by,phones=phones)))
   value=m.observe(b,work,env,[str(m.PYTHON),'-B',str(m.HERE/'measurement_worker.py'),str(work),str(m.OLD),str(m.CV)],'measurement',j,MEASURE,method='evaluation')
  assert len(value['rows'])==12 and value['DSP']<=50;b.save(MEASURE/'measurement-manifest.json',value,j)
 engineering={}
 for method in m.METHODS:
  rr=[x for x in value['rows'] if x['method']==method]
  engineering[method]=dict(expected=4,E0_pass=sum(x['E0_pass'] for x in rr),pitch_pass=sum(x['pitch_gate']['passed'] for x in rr),missing_records=sum(x['measurement'] is None for x in rr),fixed_support_intervals=sum(len(x['measurement']['support']) for x in rr if x['measurement']),missing_support=sum(len(x['measurement']['missing_support']) for x in rr if x['measurement']))
 m.seal_close(b,MEASURE,MNAME,dict(expected=12,engineering=engineering,old_source_waveforms_unchanged=True,new_render=0,old_failed_DSP200_kept=True,quality_goal_completed=False));print(json.dumps(engineering,ensure_ascii=False),flush=True)
def close():
 verify()
 node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='close')
 text=ast.get_source_segment(source,node)
 old="    for m,z in read(source/'aggregate-summary.json')['engineering'].items():"
 assert old in text
 new="""    summary_path=source/'aggregate-summary.json'
    extra,_=campaign_location('measure-'+plan['mode']+'-'+plan['length']+'-'+plan['condition'])
    if (extra/'artifact-seal.json').exists():
     for n,h in read(extra/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
     summary_path=extra/'aggregate-summary.json'
    for m,z in read(summary_path)['engineering'].items():"""
 scope=dict(m.__dict__);exec(text.replace(old,new),scope);scope['close']()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['partial-close','measurement-register','measurement','batch-register','batch','asr-register','asr','close']);p.add_argument('--mode',choices=['normal','isolated']);p.add_argument('--length',choices=['short','long']);p.add_argument('--condition',choices=['neutral','higher']);p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args();verify()
 if a.stage in ['batch-register','batch']:(r.batch_register if a.stage=='batch-register' else m.batch)(a.mode,a.length,a.condition)
 elif a.stage in ['asr-register','asr']:(m.asr_register if a.stage=='asr-register' else m.asr)(a.engine)
 else:globals()[a.stage.replace('-','_')]()
