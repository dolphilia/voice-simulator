"""包絡と時間を標準のまま、既存16特徴と新しい韻律4特徴を比較する。"""
import sys,io,math,hashlib,json
from paths import *
sys.path[:0]=[str(HERE),str(SHARED),str(BUNDLE)]
import numpy as np
from scipy.io import wavfile
from local_renderer import StateEngine
from local_control import deltas,describe,ELIGIBLE,linear_predict
from checks import invariant
from objective import extract_local,centered_semitones
from measurement import measure
from research_nn import prediction
from prosody_model import predict

def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def packed(**x):
 out=io.BytesIO();np.savez_compressed(out,**x);return out.getvalue()
def run_one(b,p,row,condition,method,predictors):
 base=HERE/'render'/row['id']/condition/method
 if base.with_suffix('.json').exists():
  r=read(base.with_suffix('.json'));assert digest(REPO/r['wav'])==r['wav_sha256'];return r
 old= CURRENT/'render/baseline'/row['id']/condition/(method+'.json')
 if row['cohort']=='legacy_diagnostic' and method in p['variants'][:4]:
  with b.job(NAME,'audit','旧診断読取再使用 '+row['id']+'/'+condition+'/'+method,reserve_bytes=100000) as j:
   r=read(old);assert digest(REPO/r['wav'])==r['wav_sha256'];r.update(reused_record=str(old.relative_to(REPO)),reused_record_sha256=digest(old),new_render_calls=0,new_dsp_calls=0)
   b.save(base.with_suffix('.json'),r,j)
  return r
 request=row['requests'][condition];settings={'speed':request['speed'],'half_tone':12*math.log2(request['requested_f0']/220)}
 if base.with_suffix('.render.json').exists():
  r=read(base.with_suffix('.render.json'));assert digest(REPO/r['wav'])==r['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256']
  fs,audio=wavfile.read(REPO/r['wav']);assert fs==24000
  lf0=np.load(REPO/r['parameters'])['generated_lf0'];before={'duration':r['duration'],'msd':r['msd']}
  for key in ['state_snapshot_before','state_snapshot_after']:
   if key in r:r[key+'_sha256']=hashlib.sha256(encode(r.pop(key))).hexdigest()
 else:
  with b.job(NAME,'render',row['id']+'/'+condition+'/'+method,reserve_bytes=3_000_000) as j:
   with StateEngine(row,BUNDLE/'mei_normal.htsvoice',**settings) as e:
    before=e.snapshot()
    if method=='native':delta,phones=np.zeros(e.count),[]
    elif method=='neural':
     with b.job(NAME,'ai','研究NN制御 '+row['id']+'/'+condition,reserve_bytes=1000):delta,phones=deltas(row,before,predictors[method])
    else:delta,phones=deltas(row,before,predictors[method])
    e.modify(delta);after=e.snapshot();invariant(before,after,delta);raw,lf0=e.generate();assert after==e.snapshot()
   peak=float(np.max(abs(raw)));gain=min(1.,.95/peak) if peak else 1.;audio=(raw*gain).astype(np.float32)
   assert np.isfinite(audio).all() and np.max(abs(audio))<1
   wav=io.BytesIO();wavfile.write(wav,24000,audio);b.write(base.with_suffix('.wav'),wav.getvalue(),j)
   b.write(base.with_suffix('.npz'),packed(generated_lf0=lf0,state_deltas=delta),j)
   r={k:row[k] for k in ['text','length','challenge_group','cohort']}
   r.update(id=row['id']+'/'+condition+'/'+method,condition=condition,variant=method,mode='prosody-comparison',status='rendered',factor=1.,wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(base.with_suffix('.wav')),parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),duration=before['duration'],msd=before['msd'],state_snapshot_before=before,state_snapshot_after=after,state_deltas_sha256=ah(delta),internal_unchanged=True,local_residuals=phones,output_gain=gain,raw_peak=peak,output_peak=float(np.max(abs(audio))),rms=float(np.sqrt(np.mean(audio.astype(float)**2))),runtime_neural=method=='neural',new_render_calls=1,quality_certified=False)
   r['state_snapshot_before_sha256']=hashlib.sha256(encode(r.pop('state_snapshot_before'))).hexdigest();r['state_snapshot_after_sha256']=hashlib.sha256(encode(r.pop('state_snapshot_after'))).hexdigest()
   b.save(base.with_suffix('.render.json'),r,j)
 with b.job(NAME,'dsp','同じ固定DIO/ACF/E0 '+r['id'],count=3,reserve_bytes=300000) as j:
  supportpath=HERE/'support'/row['id']/(condition+'.json')
  if row['cohort']=='legacy_diagnostic':support=read(CURRENT/'support'/row['id']/(condition+'.json'))['indices']
  elif supportpath.exists():support=read(supportpath)['indices']
  else:assert method=='native';support=[]
  eligible=[q['label_index'] for q in describe(row) if q['phone'] in ELIGIBLE and any(before['msd'][k]>.5 for k in range(q['label_index']*5,(q['label_index']+1)*5))]
  measurement=measure(audio,lf0,before['duration'],support,eligible);f0,times=measurement.pop('f0'),measurement.pop('times')
  if not supportpath.exists():
   if row['cohort']=='legacy_diagnostic':excluded=[]
   else:
    found,excluded=extract_local(f0,times,before,eligible);support=[v['label_index'] for v in found]
   b.save(supportpath,{'indices':support,'excluded_native_intervals':excluded,'frozen_from_native':True,'source_wave_sha256':r['wav_sha256'],'teacher_available':False},j)
  found,missing=extract_local(f0,times,before,support) if support else ([],[])
  complete=len(support)>=3 and not missing and [v['label_index'] for v in found]==support
  shape=centered_semitones([v['wave_log_f0'] for v in found]).tolist() if complete else None
  if base.with_suffix('.dio.npz').exists():
   saved=np.load(base.with_suffix('.dio.npz'));assert np.array_equal(f0,saved['f0']) and np.array_equal(times,saved['times'])
  else:b.write(base.with_suffix('.dio.npz'),packed(f0=f0,times=times),j)
  r.update(status='completed',measurement=measurement,E0_pass=measurement['E0']['E0_pass'],local_measurements=found,missing_support=missing,support_complete=complete,wave_shape=shape,support_sha256=digest(supportpath),new_dsp_calls=3,primary_dio_calls=1)
  b.save(base.with_suffix('.json'),r,j)
 return r

def main():
 b=Budget();p=read(HERE/'protocol.json')
 for n,h in p['dependencies'].items():assert digest(REPO/n)==h
 for n,h in p['source_hashes'].items():assert digest(HERE/n)==h
 with b.job(NAME,'setup','実行コードと全6制御を生成前凍結',reserve_bytes=100000) as j:
  models=read(HERE/'model-comparison.json')
  for n,h in models['new_model_hashes'].items():assert digest(HERE/'models'/(n+'.json'))==h
  predictors={v:(lambda x,m=read(SRES/'models'/(v+'.json')):linear_predict(m,x)) for v in ['direct_non_neural','distilled_non_neural']}
  predictors.update({v:(lambda x,m=read(HERE/'models'/(v+'.json')):predict(m,x)) for v in ['direct_prosody','distilled_prosody']});predictors['neural']=prediction()
  if not (HERE/'execution-contract.json').exists():
   b.save(HERE/'execution-contract.json',{'protocol_sha256':digest(HERE/'protocol.json'),'source_hashes':{q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb','.dylib']},'model_hashes':models['new_model_hashes'],'no_optimization_after_asr':True,'all_frozen_before_first_wave':True},j)
  for n,h in read(HERE/'execution-contract.json')['source_hashes'].items():assert digest(HERE/n)==h
 records=[]
 for row in p['rows']:
  for condition in row['requests']:
   for method in p['variants']:records.append(run_one(b,p,row,condition,method,predictors))
  print('rendered',row['id'],flush=True);b.reconcile()
 assert len(records)==192
 b.save(HERE/'render-manifest.json',{'rows':[{'id':r['id'],'record':str((HERE/'render'/(r['id']+'.json')).relative_to(REPO)),'wav':r['wav'],'wav_sha256':r['wav_sha256']} for r in records],'search_completed_before_asr':True,'new_diagnostic_renders':128,'reused_saved_renders':64,'new_diagnostic_DSP':384,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
