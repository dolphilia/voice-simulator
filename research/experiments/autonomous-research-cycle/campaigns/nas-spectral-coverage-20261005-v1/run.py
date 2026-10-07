"""教師を必要としない共有スペクトル制御を実WORLD波形で比較する。"""
from paths import *
import sys,io,math,hashlib
SRC=ROOT/'campaigns/nas-source-identity-20261004-v1'
sys.path[:0]=[str(HERE),str(SRC),str(WORLD),str(SHARED),str(BUNDLE)]
import numpy as np
from source_renderer import Engine
from world_renderer2 import synthesize as world_synthesize
from spectral_model import apply,predict,tests
from local_control import describe,ELIGIBLE
from research_nn import predictor
from teacher_common import wavbytes
from measurement import measure
from objective import extract_local,centered_semitones

def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def packed(**v):
 f=io.BytesIO();np.savez_compressed(f,**v);return f.getvalue()
def run_one(b,row,condition,variant,mode,predictors):
 base=HERE/'render'/mode/row['id']/condition/variant
 if base.with_suffix('.json').exists():return read(base.with_suffix('.json'))
 request=row['requests'][condition];settings=dict(speed=request['speed'],half_tone=12*math.log2(request['requested_f0']/220))
 with b.job(NAME,'render',mode+'/'+row['id']+'/'+condition+'/'+variant,reserve_bytes=6000000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',**settings) as e:
   before=e.snapshot();params=e.parameters();vocoder=e.get_settings()
   if variant=='native':out=[x.copy() for x in params];residual=np.zeros((len(params[0]),8));notes=[]
   elif variant.startswith('neural'):
    with b.job(NAME,'ai','研究NNスペクトル '+mode+'/'+row['id']+'/'+condition,reserve_bytes=1000):out,residual,notes=apply(row,before,params,predictors[variant])
   else:out,residual,notes=apply(row,before,params,predictors[variant])
   assert before==e.snapshot() and np.array_equal(out[0][:,0],params[0][:,0]) and np.array_equal(out[0][:,9:],params[0][:,9:]) and np.array_equal(out[1],params[1]) and np.array_equal(out[2],params[2])
   native_path=HERE/'render'/mode/row['id']/condition/'native.npz'
   if variant!='native':
    native=np.load(native_path);assert np.array_equal(params[0],native['spectrum']) and np.array_equal(params[1],native['lf0']) and np.array_equal(params[2],native['lpf'])
   raw,conversion=world_synthesize(out,vocoder);assert before==e.snapshot()
  audio=(raw*.25).astype(np.float32);assert np.isfinite(audio).all() and np.max(abs(audio))<1,'clip/nonfinite：利得や係数boundを事後救済しない'
  b.write(base.with_suffix('.wav'),wavbytes(audio),j);b.write(base.with_suffix('.npz'),packed(spectrum=out[0],lf0=out[1],lpf=out[2],spectral_residual=residual),j)
  r={k:row[k] for k in ['text','length','challenge_group','cohort']};r.update(id=row['id']+'/'+condition+'/'+variant,condition=condition,variant=variant,mode=mode,factor=0 if variant=='native' else 1,status='rendered',wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(base.with_suffix('.wav')),parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),duration=before['duration'],msd=before['msd'],vocoder_settings=vocoder,base_parameter_hashes=[ah(p) for p in params],modified_parameter_hashes=[ah(p) for p in out],state_snapshot_hash=hashlib.sha256(encode(before)).hexdigest(),spectral_phone_controls=notes,frame_coefficient_L1_max=float(np.max(np.sum(abs(residual),axis=1))),c0_c9plus_LF0_LPF_state_clock_unchanged=True,output_gain=.25,output_peak=float(np.max(abs(audio))),raw_peak=float(np.max(abs(raw))),runtime_neural=variant.startswith('neural'),WORLD_conversion=conversion,teacher_wave_runtime_used=False,quality_certified=False)
  b.save(base.with_suffix('.render.json'),r,j)
 with b.job(NAME,'dsp','固定DIO/ACF/E0 '+mode+'/'+r['id'],count=3,reserve_bytes=300000) as j:
  path=HERE/'support'/mode/row['id']/(condition+'.json');eligible=[q['label_index'] for q in describe(row) if q['phone'] in ELIGIBLE and any(before['msd'][k]>.5 for k in range(q['label_index']*5,(q['label_index']+1)*5))]
  if path.exists():support=read(path)['indices']
  else:assert variant=='native';support=[]
  value=measure(audio,out[1][:,0],before['duration'],support,eligible);f0,t=value.pop('f0'),value.pop('times')
  if not path.exists():
   found,excluded=extract_local(f0,t,before,eligible);support=[q['label_index'] for q in found];b.save(path,dict(indices=support,excluded_native_intervals=excluded,frozen_from_native=True,source_wave_sha256=r['wav_sha256'],teacher_available=False),j)
  found,missing=extract_local(f0,t,before,support) if support else ([],[]);complete=len(support)>=3 and not missing and [q['label_index'] for q in found]==support
  b.write(base.with_suffix('.dio.npz'),packed(f0=f0,times=t),j);r.update(status='completed',measurement=value,E0_pass=value['E0']['E0_pass'],local_measurements=found,missing_support=missing,support_complete=complete,support_sha256=digest(path),wave_shape=centered_semitones([q['wave_log_f0'] for q in found]).tolist() if complete else None,new_dsp_calls=3)
  b.save(base.with_suffix('.json'),r,j)
 return r

def main():
 b=Budget();p=read(HERE/'protocol.json');models=read(HERE/'model-comparison.json')
 for n,h in p['dependencies'].items():assert digest(REPO/n)==h
 for n,h in models['model_hashes'].items():assert digest(HERE/'models'/n)==h
 with b.job(NAME,'setup','固定4モデル・MCP機構・利得・測定を初波形前凍結',reserve_bytes=300000) as j:
  b.save(HERE/'execution-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),model_hashes=models['model_hashes'],gain_contract_sha256=digest(HERE/'gain-contract.json'),source_hashes={q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb']},external_generation_sources={str((directory/n).relative_to(REPO)):digest(directory/n) for directory,names in [(SRC,['source_renderer.py','counter.dylib','local_renderer.py','local_hts-v2.dylib']),(WORLD,['world_renderer2.py','packages-v2/pyworld/__init__.py'])] for n in names},models_and_sources_fixed_before_first_wave=True,no_optimization_after_ASR=True),j)
  b.save(HERE/'model-self-test.json',tests(),j)
  predictors={v:(lambda x,m=read(HERE/'models'/(v+'.json')):predict(m,x)) for v in ['direct17','student17','direct96','student96']};predictors.update({v:predictor(v) for v in ['neural17','neural96']})
 records=[]
 for row in p['training_rows']:
  for v in p['variants']:records.append(run_one(b,row,'neutral',v,'training',predictors))
  print('training wave',row['id'],flush=True)
 for row in p['rows']:
  for c in row['requests']:
   for v in p['variants']:records.append(run_one(b,row,c,v,'diagnostic',predictors))
  print('diagnostic wave',row['id'],flush=True)
 assert len(records)==1008
 b.save(HERE/'render-manifest.json',dict(rows=[dict(id=r['mode']+'/'+r['id'],record=str((HERE/'render'/r['mode']/(r['id']+'.json')).relative_to(REPO)),wav=r['wav'],wav_sha256=r['wav_sha256']) for r in records],search_completed_before_ASR=True,training_renders=672,diagnostic_renders=336,planned_ASR_records=2016,training_ASR_not_independent_quality=True,all_models_fixed_before_audio=True,quality_certified=False));print(b.reconcile(),flush=True)
if __name__=='__main__':main()
