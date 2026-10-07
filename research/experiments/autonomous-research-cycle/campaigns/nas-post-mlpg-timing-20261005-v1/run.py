"""同じ整数時計をMLPG前後で適用し、固定HMM/WORLDの実波形で比較する。"""
from paths import *
import sys,io,math,hashlib
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD),str(SHARED),str(BUNDLE)]
import numpy as np
from timing_engine import Engine
from world_renderer2 import synthesize
from timing_control import durations,predict,descriptions,LOWER,UPPER,FEATURES
from state_event_control import durations as mixed_durations
from post_mlpg_warp import warp
from local_control import describe,ELIGIBLE
from research_nn import predictor
from teacher_common import wavbytes
from measurement import measure
from objective import extract_local,centered_semitones
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def packed(**v):
 f=io.BytesIO();np.savez_compressed(f,**v);return f.getvalue()
def static(snapshot):return {k:v for k,v in snapshot.items() if k!='duration'}
def run_one(b,row,condition,variant,mode,predictors):
 base=HERE/'render'/mode/row['id']/condition/variant
 if base.with_suffix('.json').exists():return read(base.with_suffix('.json'))
 request=row['requests'][condition];settings=dict(speed=request['speed'],half_tone=12*math.log2(request['requested_f0']/220))
 with b.job(NAME,'render',mode+'/'+row['id']+'/'+condition+'/'+variant,reserve_bytes=7000000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',**settings) as e:
   before=e.snapshot();variance=e.variance();vocoder=e.get_settings();notes=[];clock=mixed_durations;engine_after=before;warp_info=None
   if variant=='native':after=before
   else:
    if variant=='oracle':
     assert mode=='training';t=read(HERE/'targets'/(row['id']+'.json'));desc=descriptions(row);assert [q['label_index'] for q in t['targets']]==[q['label_index'] for q in desc];fun=lambda x:np.array([q['target_log_ratio'] for q in t['targets']])
    else:fun=predictors[variant]
    if variant.startswith('neural_'):
     with b.job(NAME,'ai','研究NN時計 '+mode+'/'+row['id']+'/'+condition,reserve_bytes=1000):d,notes=clock(row,before,fun)
    else:d,notes=clock(row,before,fun)
    if variant.endswith('_post'):after=dict(before,duration=d)
    else:prior,after=e.modify_duration(d);assert prior==before;engine_after=after
   assert static(before)==static(after) and sum(before['duration'])==sum(after['duration']) and np.array_equal(variance,e.variance()) and e.get_settings()==vocoder
   params=e.parameters();assert e.snapshot()==engine_after and np.array_equal(variance,e.variance())
   native_parameter_hashes=[ah(q) for q in params] if variant.endswith('_post') else None
   if variant.endswith('_post'):params,warp_info=warp(params,before['duration'],after['duration'],before['msd'])
   assert len({len(q) for q in params})==1 and len(params[0])==sum(after['duration'])
   raw,conversion=synthesize(params,vocoder);assert e.snapshot()==engine_after
  audio=(raw*.25).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1,'clip/nonfinite：出力後救済なし'
  b.write(base.with_suffix('.wav'),wavbytes(audio),j);b.write(base.with_suffix('.npz'),packed(spectrum=params[0],lf0=params[1],lpf=params[2],duration=after['duration'],native_duration=before['duration']),j)
  r={k:row[k] for k in ['text','length','challenge_group','cohort']};r.update(id=row['id']+'/'+condition+'/'+variant,condition=condition,variant=variant,mode=mode,factor=0 if variant=='native' else 1,status='rendered',wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(base.with_suffix('.wav')),parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),duration=after['duration'],native_duration=before['duration'],msd=after['msd'],vocoder_settings=vocoder,parameter_hashes=[ah(q) for q in params],static_state_hash=hashlib.sha256(encode(static(before))).hexdigest(),variance_sha256=ah(variance),means_variance_MSD_layout_voice_settings_unchanged=True,duration_only_state_change=not variant.endswith('_post'),engine_duration=engine_after['duration'],engine_state_clock_changed=before['duration']!=engine_after['duration'],clock_application='post_MLPG' if variant.endswith('_post') else 'pre_MLPG',native_parameter_hashes=native_parameter_hashes,post_warp=warp_info,total_frame_count_fixed=True,sil_pau_unchanged=True,time_phone_controls=notes,state_clock_changed=before['duration']!=after['duration'],output_gain=.25,output_peak=float(np.max(abs(audio))),runtime_neural=variant.startswith('neural_'),teacher_time_control_used=variant=='oracle',teacher_wave_runtime_used=False,WORLD_conversion=conversion,quality_certified=False)
  state_mask=np.asarray(before['msd']).reshape(-1,5)>.5;mixed=np.any(state_mask,axis=1)&~np.all(state_mask,axis=1);original_states=np.asarray(before['duration']).reshape(-1,5);current_states=np.asarray(after['duration']).reshape(-1,5)
  r.update(state_event_policy='mixed_fixed',mixed_state_duration_fixed=bool(np.array_equal(original_states[mixed],current_states[mixed])),mixed_phone_count=int(mixed.sum()),new_render_calls=1)
  assert r['mixed_state_duration_fixed']
  native=HERE/'render'/mode/row['id']/condition/'native.render.json'
  if variant!='native':
   nr=read(native);assert r['static_state_hash']==nr['static_state_hash'] and r['variance_sha256']==nr['variance_sha256'] and r['native_duration']==nr['duration'] and r['msd']==nr['msd'] and r['vocoder_settings']==nr['vocoder_settings']
  b.save(base.with_suffix('.render.json'),r,j)
 with b.job(NAME,'dsp','固定DIO/ACF/E0 '+mode+'/'+r['id'],count=3,reserve_bytes=300000) as j:
  path=HERE/'support'/mode/row['id']/(condition+'.json');eligible=[q['label_index'] for q in describe(row) if q['phone'] in ELIGIBLE and any(after['msd'][k]>.5 for k in range(q['label_index']*5,(q['label_index']+1)*5))]
  if path.exists():support=read(path)['indices']
  else:assert variant=='native';support=[]
  value=measure(audio,params[1][:,0],after['duration'],support,eligible);f0,t=value.pop('f0'),value.pop('times')
  if not path.exists():
   found,excluded=extract_local(f0,t,after,eligible);support=[q['label_index'] for q in found];b.save(path,dict(indices=support,excluded_native_intervals=excluded,frozen_from_native=True,source_wave_sha256=r['wav_sha256'],native_duration=before['duration'],candidate_measurement_uses_candidate_state_clock=True,teacher_available=False),j)
  found,missing=extract_local(f0,t,after,support) if support else ([],[]);complete=len(support)>=3 and not missing and [q['label_index'] for q in found]==support
  b.write(base.with_suffix('.dio.npz'),packed(f0=f0,times=t),j);r.update(status='completed',measurement=value,E0_pass=value['E0']['E0_pass'],local_measurements=found,missing_support=missing,support_complete=complete,support_sha256=digest(path),wave_shape=centered_semitones([q['wave_log_f0'] for q in found]).tolist() if complete else None,new_dsp_calls=3)
  b.save(base.with_suffix('.json'),r,j)
 return r
def reuse_training(b,p):
 oldseal=read(EVENT/'artifact-seal.json');previous=read(EVENT/'protocol.json');oldrows={r['id']:r for r in previous['training_rows']};copied=[]
 with b.job(NAME,'setup','旧320訓練wave/parameter/支持の完全一致再利用',reserve_bytes=50000000) as j:
  for row in p['training_rows']:
   assert row['full_context_labels']==oldrows[row['id']]['full_context_labels'] and row['requests']==oldrows[row['id']]['requests']
   support=EVENT/'support/training'/row['id']/'neutral.json';target=HERE/'support/training'/row['id']/'neutral.json'
   assert digest(support)==oldseal['files'][str(support.relative_to(REPO))];b.write(target,support.read_bytes(),j)
   for method,source in [('native','native'),('direct_pre','direct_mixed_fixed'),('neural_pre','neural_mixed_fixed'),('student_pre','student_mixed_fixed')]:
    path=EVENT/'render/training'/row['id']/'neutral'/(source+'.json');assert digest(path)==oldseal['files'][str(path.relative_to(REPO))];r=read(path)
    assert digest(REPO/r['wav'])==r['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'] and r['support_sha256']==digest(target)
    r.update(id=row['id']+'/neutral/'+method,variant=method,state_event_policy='mixed_fixed',clock_application='pre_MLPG',engine_duration=r['duration'],engine_state_clock_changed=r['state_clock_changed'],native_parameter_hashes=None,post_warp=None,mixed_state_duration_fixed=bool(np.array_equal(np.array(r['duration']).reshape(-1,5)[(np.array(r['msd']).reshape(-1,5)>.5).any(1)&~(np.array(r['msd']).reshape(-1,5)>.5).all(1)],np.array(r['native_duration']).reshape(-1,5)[(np.array(r['msd']).reshape(-1,5)>.5).any(1)&~(np.array(r['msd']).reshape(-1,5)>.5).all(1)])),new_render_calls=0,new_dsp_calls=0,reused_dsp_calls=3,reused_render_from=str(path.relative_to(REPO)),reused_record_sha256=digest(path))
    base=HERE/'render/training'/row['id']/'neutral'/method;b.save(base.with_suffix('.render.json'),r,j);b.save(base.with_suffix('.json'),r,j);copied.append(dict(path=str(path.relative_to(REPO)),sha256=digest(path),new_variant=method))
  assert len(copied)==320;b.save(HERE/'training-render-reuse-audit.json',dict(records=copied,new_renders=0,reused_renders=320,new_DSP=0,models_and_requests_hash_identical=True),j)
def main():
 b=Budget();p=read(HERE/'protocol.json');models=read(HERE/'model-comparison.json');assert read(HERE/'self-test.json')['passed']
 for n,h in p['dependencies'].items():assert digest(REPO/n)==h
 for n,h in models['model_hashes'].items():assert digest(HERE/'models'/n)==h
 reuse_training(b,p)
 with b.job(NAME,'setup','同voice/状態平均/分散と固定利得・時計制約を初比較波形前固定',reserve_bytes=300000) as j:
  b.save(HERE/'execution-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),model_hashes=models['model_hashes'],gain_contract_sha256=digest(HERE/'gain-contract.json'),source_hashes={q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb','.c','.dylib']},external_generation_sources={str((directory/n).relative_to(REPO)):digest(directory/n) for directory,names in [(SRC,['source_renderer.py','counter.dylib','local_renderer.py','local_hts-v2.dylib']),(WORLD,['world_renderer2.py','packages-v2/pyworld/__init__.py'])] for n in names},models_and_sources_fixed_before_first_comparison_wave=True,no_optimization_after_ASR=True,same_integer_output_clock_pre_post=True,post_parameters_computed_from_current_text_native_MLPG=True,no_dynamic_MLPG_constraint_preservation_claim_post=True),j)
 predictors={v:(lambda x,m=read(HERE/'models'/(v.split('_')[0]+'.json')):predict(m,x)) for v in p['variants'] if v.startswith(('direct_','student_'))};nn=predictor();predictors.update({v:nn for v in p['variants'] if v.startswith('neural_')});records=[]
 for row in p['training_rows']:
  for v in p['training_variants']:records.append(run_one(b,row,'neutral',v,'training',predictors))
  print('state投影訓練wave',row['id'],flush=True)
 for row in p['rows']:
  for c in row['requests']:
   for v in p['variants']:records.append(run_one(b,row,c,v,'diagnostic',predictors))
  print('state投影診断wave',row['id'],flush=True)
 assert len(records)==896
 b.save(HERE/'render-manifest.json',dict(rows=[dict(id=r['mode']+'/'+r['id'],record=str((HERE/'render'/r['mode']/(r['id']+'.json')).relative_to(REPO)),wav=r['wav'],wav_sha256=r['wav_sha256']) for r in records],search_completed_before_ASR=True,training_records=560,diagnostic_records=336,reused_training_renders=320,new_training_renders=240,new_diagnostic_renders=336,planned_ASR_records=1792,training_ASR_not_independent_quality=True,all_models_fixed_before_audio=True,quality_certified=False));print(b.reconcile(),flush=True)
if __name__=='__main__':main()
