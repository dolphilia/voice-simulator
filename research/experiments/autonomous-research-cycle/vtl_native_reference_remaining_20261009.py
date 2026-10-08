"""原契約の未実施17参照だけを継続する。条件・生成器・ゲートを変更しない。"""
import argparse,ast,json,os
from pathlib import Path
from budget import ROOT,read,digest
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
from observed_process_20261009 import run_observed
import vtl_native_reference_conditions_20261009 as old
HERE=old.HERE;NAME=old.NAME;SOURCE=old.SOURCE;PYTHON=old.PYTHON;REPO=ROOT.parents[2]
WORKER=old.PREFIX.replace("verify();spec=json.loads((here/'registration.json').read_text());centers","verify();centers")+r'''
study=Path(sys.argv[3]);reg=json.loads((study/'continuation-registration.json').read_text());refs=[];render_calls=0;attempts=0
for spec in reg['remaining']:
 attempts+=1;vowel=spec['vowel'];target=spec['F0_Hz'];ident=spec['id']
 try:
  data,meta,params,row=native(spec['text'],spec['speed'],target,full=True)
 except ValueError as error:
  if str(error)!='LF0 sentinelまたは有声F0範囲が不正':raise
  refs.append(dict(**spec,status='native_parameter_domain_failed',error=str(error),measurement=None,engineering_diagnostic_pass=False,wav_sha256=None))
 else:
  render_calls+=meta['conversion']['render_calls_including_internal_MLSA'];measure_calls+=3
  indices=[i for i,label in enumerate(row['full_context_labels']) if re.search(r'\-([^+]+)\+',label).group(1).lower()==vowel];assert len(indices)==1
  i=indices[0];bounds=np.r_[0,np.cumsum(meta['duration'])]*.005;start,end=float(bounds[i*5]),float(bounds[(i+1)*5]);width=end-start
  measurement=measure(data,[start+.2*width,end-.2*width],target);(work/(ident+'.wav')).write_bytes(data)
  refs.append(dict(**spec,status='measured',wav_sha256=hashlib.sha256(data).hexdigest(),source_state_interval_seconds=[start,end],label_boundary_not_observed_truth=True,measurement=measurement,engineering_diagnostic_pass=measurement['engineering_diagnostic_pass'],native_gain=.25,settings=meta['settings']))
 (work/'partial.json').write_text(json.dumps(dict(references=refs,completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls),ensure_ascii=False,allow_nan=False))
assert attempts==17 and render_calls<=17 and measure_calls<=170
(work/'references.json').write_text(json.dumps(dict(references=refs,completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls,native_generation_attempts=attempts,partial_DSP_of_parameter_failures_unmeasured=True),ensure_ascii=False,allow_nan=False))
print(json.dumps(dict(completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls,native_generation_attempts=attempts,output_files=[x['id']+'.wav' for x in refs if x['wav_sha256']])))
'''
def register():
 b=Budget();b.recover();old.verify();s=b.snapshot();c=s['campaigns'][NAME];assert not c['closed'] and not s['jobs'];ast.parse(WORKER)
 specs=[dict(id=cond['id']+'-'+v+'-'+str(f),condition=cond['id'],vowel=v,text=t,speed=cond['speed'],F0_Hz=f) for cond in old.CONDITIONS for v,t in zip('aiueo',['ア','イ','ウ','エ','オ']) for f in cond['F0_Hz']]
 work=next(x for x in s['temporary_work'].values() if x['campaign']==NAME);observed={x['relative'][:-4] for x in work['files'] if x['relative'].endswith('.wav')};assert observed=={x['id'] for x in specs[:12]};assert work['status']=='removed' and not os.path.lexists(work['path'])
 failure=next(HERE.glob('failure-*.json'));assert 'LF0 sentinelまたは有声F0範囲が不正' in read(failure)['stderr']
 reg=dict(original_registration_sha256=digest(HERE/'registration.json'),original_worker_sha256=digest(HERE/'worker.py'),controller_sha256=digest(Path(__file__)),no_conditions_gates_gain_generator_or_priority_change=True,completed_12_not_repeated=specs[:12],failed_row_not_repeated=specs[12],remaining=specs[13:],failed_attempt=digest(failure),temporary_manifest_evidence=work,recording_rule='既存LF0値域の科学的不通過を分母へ保持し、未実施行だけを継続する。旧波形12件の計測値は未保存なので未資格。成功済み/不通過行を再生成せず残り17行を一度だけ生成する。',reserved_remaining=dict(render=17,dsp=170,work_peak_bytes=64000000,work_write_bytes=128000000,render_reservation_bytes=96000000),partial_result_checkpoint_each_row=True,not_technical_retry_of_scientific_failed_condition=True,quality_goal_completed=False)
 assert c['counts']['render']+17<=c['limits']['render'] and c['counts']['dsp']+170<=c['limits']['dsp']
 with b.job(NAME,'setup','原契約の未実施行だけを継続する記録方式を出力前固定',reserve_bytes=6000000) as j:
  b.save(HERE/'continuation-registration.json',reg,j);b.write(HERE/'continuation-worker.py',WORKER.encode(),j)
  b.save(HERE/'continuation-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(REPO)):digest(p) for p in [Path(__file__),HERE/'continuation-worker.py',HERE/'continuation-registration.json',HERE/'source-contract.json']}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=NAME,next='保存後、原条件の未実施17行だけを固定診断。失敗1行と未保存12行は未資格のまま残す。',git_save_pending=True);b._write_state(s)
 print('原契約の未実施17参照のみを継続登録')
def run():
 b=Budget();b.recover();old.verify();c=read(HERE/'continuation-contract.json')
 for n,h in c['files'].items():assert digest(REPO/n)==h,n
 r=b.reserve(NAME,'render','原三条件の未実施17参照だけを継続',17,96000000,expected_seconds=600)
 try:
  d=b.reserve(NAME,'dsp','未実施17参照の固定E0/F0/包絡',170,2000000,expected_seconds=600)
  try:
   with b.workspace(r,'再生成せず残り17参照だけを測り個票を随時保存',64000000,128000000) as (work,env):
    env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    stdout,stderr,obs=run_observed([str(PYTHON),'-B',str(HERE/'continuation-worker.py'),str(SOURCE),str(work),str(HERE)],env,work,label='remaining',timeout=540);b.save(HERE/'continuation-process.json',obs,r)
    if (work/'partial.json').exists():b.write_data(HERE/'data/continuation-partial.json',(work/'partial.json').read_bytes(),r)
    if obs['returncode']!=0:
     for p in work.glob('*.wav'):b.write_data(HERE/'audio'/p.name,p.read_bytes(),r)
     b.save(HERE/'continuation-failure.json',dict(stdout=stdout,stderr=stderr),r);raise RuntimeError('未実施参照継続の技術障害')
    counts=json.loads(stdout);b.save(HERE/'generation-counts.json',counts,r);b.write_data(HERE/'data/references.json',(work/'references.json').read_bytes(),r)
    for n in counts['output_files']:b.write_data(HERE/'audio'/n,(work/n).read_bytes(),r)
  except BaseException as e:b.finish(d,repr(e));raise
  else:b.finish(d)
 except BaseException as e:b.finish(r,repr(e));raise
 else:b.finish(r)
 with b.job(NAME,'audit','30分母の生成/不通過/未保存と残り17の診断を封印',reserve_bytes=6000000) as j:
  reg=read(HERE/'continuation-registration.json');rows=[dict(**x,status='generated_measurements_not_retained',measurement=None,engineering_diagnostic_pass=False) for x in reg['completed_12_not_repeated']]+[dict(**reg['failed_row_not_repeated'],status='native_parameter_domain_failed',measurement=None,engineering_diagnostic_pass=False)]+read(HERE/'data/references.json')['references'];assert len(rows)==30 and len({x['id'] for x in rows})==30
  results=[]
  for cond in old.CONDITIONS:
   rr=[x for x in rows if x['condition']==cond['id']];assert len(rr)==10
   results.append(dict(**cond,reference_total=10,passed=sum(x['engineering_diagnostic_pass'] for x in rr),eligible=all(x['engineering_diagnostic_pass'] for x in rr),rows=[dict(id=x['id'],status=x['status'],pitch=x['measurement']['pitch'] if x['measurement'] else None) for x in rr]))
  selected=next((x['id'] for x in results if x['eligible']),None);summary=dict(conditions=results,selected_condition=selected,reference_total=30,first_generated_12_unqualified_due_unretained_measurements=True,failed_conditions_not_retried=True,previous_successful_waveforms_not_regenerated=True,candidate_generation_or_fit_performed=False,prior_conditions_and_failures_frozen=True,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False)
  b.save(HERE/'aggregate-summary.json',summary,j);s=b.snapshot();cc=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(HERE/'cost-audit.json',dict(counts=cc['counts'],initial_completed_native_renders_from_owned_WAV_names=12,initial_completed_DSP_macro_calls_from_original_worker_order=120,initial_partial_DSP_of_parameter_failure_unmeasured=True,continuation=read(HERE/'generation-counts.json'),seconds=s['seconds']-cc['start_seconds'],write_bytes=s['write_bytes']-cc['start_write_bytes'],all_owned_temporary_absent=True,not_OOM_or_capacity_failure_in_this_campaign=True,process=read(HERE/'continuation-process.json')),j)
  lines=['# 新参照条件の全分母と未実施部分の診断','','初回はlower-longer/i/120で既存LF0値域の検査に止まった。生成・計測済み12波形は一時回収時に削除され集計未保存のため、未資格として残した。成功12件と不通過1件を再試行せず、未実施17件だけを同じ条件で継続した。','','|条件|参照通過|全10適格|','|---|---:|---|']+[f"|{x['id']}|{x['passed']}/10|{x['eligible']}|" for x in results]+['','事前優先順による選択: '+str(selected),'','内容・VTL学習・自然さ・一般化は未確認。品質未達、知覚資格なし、P5未開封。']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=None,next='科学54件後の定期レビュー9を先に実施。旧参照不通過/未保存を保持し、適格共通条件がなければnative単母音参照経路を撤退。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-native-reference-conditions-completed-20261009.json',dict(selected_condition=selected,conditions=[dict(id=x['id'],passed=x['passed'],eligible=x['eligible']) for x in results],review=b.review_due(),budget=b.reconcile()));print(json.dumps(dict(selected_condition=selected,conditions=[dict(id=x['id'],passed=x['passed']) for x in results]),ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);a=p.parse_args();globals()[a.stage]()
