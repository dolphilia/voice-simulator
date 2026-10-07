"""旧64再現を必須にし、全256波形を固定包絡条件で生成する。"""
import io,json,math,sys,time,hashlib
from paths import *
sys.path[:0]=[str(HERE),str(SHARED),str(COUNTER),str(BUNDLE)]
import numpy as np
from scipy.io import wavfile
from spectrum_renderer import Engine
from local_renderer import StateEngine,frames,parameter
from local_control import deltas,linear_predict,describe,ELIGIBLE
from checks import invariant
from objective import extract_local,centered_semitones
from measurement import measure

def packed(**values):
 out=io.BytesIO();np.savez_compressed(out,**values);return out.getvalue()
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def jsonvalue(x):return json.loads(json.dumps(x))
def prediction():
 import torch
 from torch import nn
 model=read(SRES/'models/neural.json');assert digest(SRES/'models/neural.pt')==model['weights_sha256']
 net=nn.Sequential(nn.Linear(16,16),nn.Tanh(),nn.Linear(16,16),nn.Tanh(),nn.Linear(16,1))
 net.load_state_dict(torch.load(SRES/'models/neural.pt',map_location='cpu',weights_only=True));net.eval();torch.set_num_threads(2)
 def predict(x):
  z=(np.asarray(x)-np.asarray(model['x_mean']))/np.asarray(model['x_scale'])
  with torch.no_grad():return net(torch.tensor(z,dtype=torch.float32)).flatten().numpy()
 return predict

def verify(p):
 for n,h in p['dependencies'].items():assert digest(REPO/n)==h,n
 for n,h in p['source_hashes'].items():assert digest(HERE/n)==h,n
 audit=read(PREP/'history-completion-audit.json')
 assert audit['all_nonprotected_history_present'] and not any(r['exact_normalized_collision'] or r['full_context_label_collision'] for r in audit['rows'])

def run_one(b,p,row,condition,variant,factor,predictors):
 mode='baseline' if factor==1. else 'partial'
 base=HERE/'render'/mode/row['id']/condition/variant
 if base.with_suffix('.json').exists():
  r=read(base.with_suffix('.json'));assert r['status']=='completed' and digest(REPO/r['wav'])==r['wav_sha256'];return r
 requested=row['requests'][condition];settings={'speed':requested['speed'],'half_tone':12*math.log2(requested['requested_f0']/220)}
 before=None
 with b.job(NAME,'render',mode+'/'+row['id']+'/'+condition+'/'+variant,count=2 if factor==1. and row['cohort']=='legacy_diagnostic' else 1,reserve_bytes=3_000_000) as job:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',**settings) as e:
   before=e.snapshot();correction,phones=(np.zeros(e.count),[]) if variant=='native' else deltas(row,before,predictors[variant])
   e.modify(correction);after=e.snapshot();invariant(before,after,correction)
   params=e.parameters();vocoder=e.get_settings()
   if factor==1 and row['cohort']=='legacy_diagnostic':
    old=read(SRES/'render'/row['id']/condition/(variant+'.json'))
    saved=np.load(SRES/'render'/row['id']/condition/(variant+'.npz'))
    assert jsonvalue(before)==old['state_snapshot_before'] and jsonvalue(after)==old['state_snapshot_after']
    assert np.array_equal(correction,saved['state_deltas']) and np.array_equal(params[1][:,0],saved['generated_lf0'])
   if factor==.75:
    reference=HERE/'render/baseline'/row['id']/condition/(variant+'.npz');a=np.load(reference)
    assert all(np.array_equal(params[i],a[n]) for i,n in enumerate(('spectrum','lf0','lpf')))
    oldbase=read(reference.with_suffix('.json'));assert vocoder==oldbase['vocoder_settings']
    assert ah(correction)==oldbase['state_deltas_sha256']
   audio,out_hashes=e.synthesize(params,factor)
   assert jsonvalue(after)==jsonvalue(e.snapshot())
  if factor==1. and row['cohort']=='legacy_diagnostic':
   # 旧の全生成経路を一回追加し、波形と全MLPG列を直接比較する。
   with StateEngine(row,BUNDLE/'mei_normal.htsvoice',**settings) as ref:
    assert jsonvalue(ref.snapshot())==jsonvalue(before)
    ref.modify(correction);reference_audio,reference_lf0=ref.generate()
    reference_params=[np.array([[parameter(ref.pointer,s,f,k) for k in range(x.shape[1])] for f in range(frames(ref.pointer))]) for s,x in enumerate(params)]
   assert np.array_equal(audio,reference_audio) and np.array_equal(params[1][:,0],reference_lf0)
   assert all(np.array_equal(x,z) for x,z in zip(params,reference_params))
  peak=float(np.max(abs(audio)));gain=(min(1.,.95/peak) if peak else 1.) if factor==1 else oldbase['output_gain']
  audio=(audio*gain).astype(np.float32)
  assert np.isfinite(audio).all() and np.max(abs(audio))<1.,'非有限/clipを保存し採択しません'
  buf=io.BytesIO();wavfile.write(buf,24000,audio);b.write(base.with_suffix('.wav'),buf.getvalue(),job)
  b.write(base.with_suffix('.npz'),packed(spectrum=params[0],lf0=params[1],lpf=params[2],state_deltas=correction),job)
  wavehash=digest(base.with_suffix('.wav'))
  legacy_matches=None
  if factor==1 and row['cohort']=='legacy_diagnostic':
   assert wavehash==old['wav_sha256'],'旧64の波形bit不一致'
   legacy_matches=True
  record={k:row[k] for k in ('id','text','length','challenge_group','cohort')}
  record.update(id=row['id']+'/'+condition+'/'+variant,condition=condition,variant=variant,factor=factor,mode=mode,status='rendered',
   wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=wavehash,
   parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),
   settings=settings,vocoder_settings=vocoder,source_parameter_hashes=[ah(x) for x in params],vocoder_input_hashes=out_hashes,
   state_deltas_sha256=ah(correction),duration=before['duration'],msd=before['msd'],
   all_state_streams_unchanged_except_registered_lf0=True,legacy_wav_state_lf0_bit_match=legacy_matches,
   raw_peak=peak,output_gain=gain,output_peak=float(np.max(abs(audio))),rms=float(np.sqrt(np.mean(audio.astype(float)**2))),
   runtime_neural=variant=='neural',quality_certified=False)
  b.save(base.with_suffix('.render.json'),record,job)
 with b.job(NAME,'dsp',mode+'/'+record['id'],count=3,reserve_bytes=300000) as job:
  support_path=HERE/'support'/row['id']/(condition+'.json')
  if row['cohort']=='legacy_diagnostic':support=read(SRES/'render'/row['id']/condition/'support-contract.json')['indices']
  elif support_path.exists():support=read(support_path)['indices']
  else:
   assert variant=='native' and factor==1
   support=[]
  eligible=[r['label_index'] for r in describe(row) if r['phone'] in ELIGIBLE and any(before['msd'][i]>.5 for i in range(r['label_index']*5,(r['label_index']+1)*5))]
  measured=measure(audio,params[1][:,0],before['duration'],support,eligible)
  f0,times=measured.pop('f0'),measured.pop('times')
  if not support_path.exists():
   if row['cohort']!='legacy_diagnostic':
    native,excluded=extract_local(f0,times,before,eligible);support=[r['label_index'] for r in native]
   else:excluded=[]
   b.save(support_path,{'indices':support,'excluded_native_intervals':excluded,'frozen_from_baseline_native':True,
    'source_native_wave_sha256':wavehash,'minimum_three_intervals':len(support)>=3,'teacher_available':False},job)
  found,missing=extract_local(f0,times,before,support) if support else ([],[])
  complete=len(support)>=3 and not missing and [r['label_index'] for r in found]==support
  shape=centered_semitones([r['wave_log_f0'] for r in found]).tolist() if complete else None
  if factor==1 and row['cohort']=='legacy_diagnostic':
   saved=np.load(SRES/'render'/row['id']/condition/(variant+'.npz'))
   assert np.array_equal(f0,saved['dio_f0']) and np.array_equal(times,saved['dio_times'])
  b.write(base.with_suffix('.dio.npz'),packed(f0=f0,times=times),job)
  record.update(status='completed',measurement=measured,E0_pass=measured['E0']['E0_pass'],
   local_measurements=found,missing_support=missing,support_complete=complete,wave_shape=shape,
   support_sha256=digest(support_path),new_dsp_calls=3,primary_dio_calls=1)
  b.save(base.with_suffix('.json'),record,job)
 return record

def main():
 b=Budget();p=read(HERE/'protocol.json');verify(p);assert read(PREP/'entry-audit.json')['passed']
 with b.job(NAME,'setup','固定制御器の読込と実行コード凍結',reserve_bytes=200000) as job:
  predictors={v:(lambda x,m=read(SRES/'models'/(v+'.json')):linear_predict(m,x)) for v in p['variants'][1:] if v!='neural'}
  predictors['neural']=prediction()
  if not (HERE/'execution-contract.json').exists():
   b.save(HERE/'execution-contract.json',{'protocol_sha256':digest(HERE/'protocol.json'),
    'history_audit_sha256':digest(PREP/'history-completion-audit.json'),
    'source_hashes':{str(q.relative_to(HERE)):digest(q) for q in HERE.rglob('*') if q.is_file() and q.suffix in ('.py','.c','.h','.dylib','.sb')},
    'planned_diagnostic_render':256,'planned_old_reference_render':64,'planned_isolation_render':48,'planned_dsp':792,'planned_asr_maximum':512,
    'all_controls_frozen_before_first_wave':True,'no_new_teacher_fit_inverse':True},job)
  ec=read(HERE/'execution-contract.json')
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h
 records=[]
 for cohort in ('legacy_diagnostic','prospective_once'):
  if cohort=='prospective_once':assert read(HERE/'baseline-gate.json')['passed']
  for row in [r for r in p['rows'] if r['cohort']==cohort]:
   for condition in row['requests']:
    for variant in p['variants']:records.append(run_one(b,p,row,condition,variant,1.,predictors))
   print('baseline',row['id'],flush=True)
  if cohort=='legacy_diagnostic' and not (HERE/'baseline-gate.json').exists():
   assert len(records)==64 and all(r['legacy_wav_state_lf0_bit_match'] for r in records)
   b.save(HERE/'baseline-gate.json',{'passed':True,'wav_state_all_streams_lf0_dio_time_bit_matches':64,
    'old_path_all_mlpg_streams_directly_reconstructed_and_bit_matched':64,'comparison_scope':p['old_saved_stream_scope']})
  b.reconcile()
 for row in p['rows']:
  for condition in row['requests']:
   for variant in p['variants']:records.append(run_one(b,p,row,condition,variant,.75,predictors))
  print('partial',row['id'],flush=True)
  if len(records)%32==0:b.reconcile()
 assert len(records)==256
 b.save(HERE/'render-manifest.json',{'rows':[{'id':r['mode']+'/'+r['id'],'record':str((HERE/'render'/r['mode']/r['id']).with_suffix('.json').relative_to(REPO)),'wav':r['wav'],'wav_sha256':r['wav_sha256']} for r in records],
  'all_controls_frozen':True,'search_completed_before_asr':True,'new_render':320,'new_dsp':768,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
