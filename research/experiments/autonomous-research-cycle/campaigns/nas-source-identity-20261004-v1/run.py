"""旧96波形一致と全無声一致を通過してから固定励起384条件を生成する。"""
import io,sys,math,hashlib,json
from paths import *
sys.path[:0]=[str(HERE),str(SHARED),str(BUNDLE)]
import numpy as np
from scipy.io import wavfile
from source_renderer import Engine
from local_control import deltas,describe,ELIGIBLE,linear_predict
from prosody_model import predict as prosody_predict
from research_nn import prediction
from checks import invariant
from objective import extract_local,centered_semitones
from measurement import measure

def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def packed(**x):
 out=io.BytesIO();np.savez_compressed(out,**x);return out.getvalue()
def wavbytes(x):
 out=io.BytesIO();wavfile.write(out,24000,x.astype(np.float32));return out.getvalue()
def self_test(b,row):
 out=[]
 for mode in [0,1]:
  with b.job(NAME,'render','全無声LF0の同源自己検査 '+str(mode),reserve_bytes=3_000_000) as j:
   with Engine(row,BUNDLE/'mei_normal.htsvoice',speed=1.,half_tone=0.) as e:
    before=e.snapshot();params=e.parameters();raw,hashes=e.synthesize(params,mode,test=True);assert before==e.snapshot();assert np.isfinite(raw).all()
   b.write(HERE/'self-test'/('unvoiced-'+str(mode)+'.wav'),wavbytes(raw),j);out.append(raw)
 assert np.array_equal(out[0],out[1]),'全無声なのにLPF以外の違いが生じた'
 b.save(HERE/'self-test.json',{'passed':True,'two_renders':2,'all_unvoiced_wave_bit_match':True,'same_three_stream_same_ring':True,'quality_certified':False})

def run_one(b,p,row,condition,variant,mode,predictors):
 label='baseline' if mode==0 else 'identity';base=HERE/'render'/label/row['id']/condition/variant
 if base.with_suffix('.json').exists():
  r=read(base.with_suffix('.json'));assert digest(REPO/r['wav'])==r['wav_sha256'];return r
 request=row['requests'][condition];settings={'speed':request['speed'],'half_tone':12*math.log2(request['requested_f0']/220)}
 with b.job(NAME,'render',label+'/'+row['id']+'/'+condition+'/'+variant,reserve_bytes=3_000_000) as j:
  with Engine(row,BUNDLE/'mei_normal.htsvoice',**settings) as e:
   before=e.snapshot()
   if variant=='native':delta=np.zeros(e.count)
   elif variant=='neural':
    with b.job(NAME,'ai','研究NN制御 '+label+'/'+row['id']+'/'+condition,reserve_bytes=1000):delta=deltas(row,before,predictors[variant])[0]
   else:delta=deltas(row,before,predictors[variant])[0]
   e.modify(delta);after=e.snapshot();invariant(before,after,delta);params=e.parameters();vocoder=e.get_settings()
   if mode==1:
    reference=HERE/'render/baseline'/row['id']/condition/(variant+'.npz');saved=np.load(reference);n=read(reference.with_suffix('.json'))
    assert all(np.array_equal(params[k],saved[f]) for k,f in enumerate(['spectrum','lf0','lpf'])) and np.array_equal(delta,saved['state_deltas'])
    assert vocoder==n['vocoder_settings'] and ah(delta)==n['state_deltas_sha256']
   raw,output_hashes=e.synthesize(params,mode);assert after==e.snapshot()
  peak=float(np.max(abs(raw)));old_gain=min(1.,.95/peak) if peak else 1.;legacy=False
  if mode==0 and row['cohort']=='legacy_diagnostic':
   oldpath=PREVIOUS/'render'/row['id']/condition/(variant+'.json');old=read(oldpath)
   assert digest(REPO/old['wav'])==old['wav_sha256'];assert hashlib.sha256(wavbytes(raw*old_gain)).hexdigest()==old['wav_sha256']
   arrays=np.load(REPO/old['parameters']);assert np.array_equal(params[1][:,0],arrays['generated_lf0']) and np.array_equal(delta,arrays['state_deltas'])
   for key,x in [('state_snapshot_before_sha256',before),('state_snapshot_after_sha256',after)]:assert hashlib.sha256(encode(x)).hexdigest()==old[key]
   legacy=True
  gain=old_gain*read(HERE/'gain-amendment-before-wave.json')['factor'] if mode==0 else n['output_gain'];audio=(raw*gain).astype(np.float32)
  assert np.isfinite(audio).all() and np.max(abs(audio))<1,'clip/nonfinite: gainや条件を事後変更しない'
  b.write(base.with_suffix('.wav'),wavbytes(audio),j);b.write(base.with_suffix('.npz'),packed(spectrum=params[0],lf0=params[1],lpf=params[2],state_deltas=delta),j)
  r={k:row[k] for k in ['text','length','challenge_group','cohort']}
  r.update(id=row['id']+'/'+condition+'/'+variant,condition=condition,variant=variant,mode=label,factor=mode,status='rendered',wav=str(base.with_suffix('.wav').relative_to(REPO)),wav_sha256=digest(base.with_suffix('.wav')),parameters=str(base.with_suffix('.npz').relative_to(REPO)),parameters_sha256=digest(base.with_suffix('.npz')),duration=before['duration'],msd=before['msd'],vocoder_settings=vocoder,source_parameter_hashes=[ah(x) for x in params],vocoder_input_hashes=output_hashes,state_deltas_sha256=ah(delta),state_before_sha256=hashlib.sha256(encode(before)).hexdigest(),state_after_sha256=hashlib.sha256(encode(after)).hexdigest(),internal_unchanged=True,baseline_pre_headroom_bit_match=legacy,output_gain=gain,baseline_gain_before_common_factor=old_gain if mode==0 else n['baseline_gain_before_common_factor'],raw_peak=peak,output_peak=float(np.max(abs(audio))),rms=float(np.sqrt(np.mean(audio.astype(float)**2))),runtime_neural=variant=='neural',quality_certified=False)
  b.save(base.with_suffix('.render.json'),r,j)
 with b.job(NAME,'dsp',label+'/'+r['id'],count=3,reserve_bytes=300000) as j:
  supportpath=HERE/'support'/row['id']/(condition+'.json')
  if row['cohort']=='legacy_diagnostic':support=read(PREVIOUS/'support'/row['id']/(condition+'.json'))['indices']
  elif supportpath.exists():support=read(supportpath)['indices']
  else:assert variant=='native' and mode==0;support=[]
  eligible=[q['label_index'] for q in describe(row) if q['phone'] in ELIGIBLE and any(before['msd'][k]>.5 for k in range(q['label_index']*5,(q['label_index']+1)*5))]
  value=measure(audio,params[1][:,0],before['duration'],support,eligible);f0,t=value.pop('f0'),value.pop('times')
  if not supportpath.exists():
   if row['cohort']=='legacy_diagnostic':excluded=[]
   else:
    found,excluded=extract_local(f0,t,before,eligible);support=[x['label_index'] for x in found]
   b.save(supportpath,{'indices':support,'excluded_native_intervals':excluded,'frozen_from_native_baseline':True,'wave_sha256':r['wav_sha256'],'teacher_available':False},j)
  found,missing=extract_local(f0,t,before,support) if support else ([],[]);complete=len(support)>=3 and not missing and [q['label_index'] for q in found]==support
  b.write(base.with_suffix('.dio.npz'),packed(f0=f0,times=t),j)
  r.update(status='completed',measurement=value,E0_pass=value['E0']['E0_pass'],local_measurements=found,missing_support=missing,support_complete=complete,wave_shape=centered_semitones([q['wave_log_f0'] for q in found]).tolist() if complete else None,support_sha256=digest(supportpath),new_dsp_calls=3)
  b.save(base.with_suffix('.json'),r,j)
 return r

def main():
 b=Budget();p=read(HERE/'protocol.json')
 for n,h in p['dependencies'].items():assert digest(REPO/n)==h
 for n,h in p['source_hashes'].items():assert digest(HERE/n)==h
 with b.job(NAME,'setup','全共有制御・利得・励起・測定コードを初波形前に凍結',reserve_bytes=100000) as j:
  predictors={v:(lambda x,m=read(SRES/'models'/(v+'.json')):linear_predict(m,x)) for v in ['direct_non_neural','distilled_non_neural']}
  predictors.update({v:(lambda x,m=read(PREVIOUS/'models'/(v+'.json')):prosody_predict(m,x)) for v in ['direct_prosody','distilled_prosody']});predictors['neural']=prediction()
  if not (HERE/'execution-contract.json').exists():b.save(HERE/'execution-contract.json',{'protocol_sha256':digest(HERE/'protocol.json'),'gain_contract_sha256':digest(HERE/'gain-amendment-before-wave.json'),'source_hashes':{q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.c','.sb','.dylib']},'source_modes_fixed':True,'all_frozen_before_wave':True,'no_optimization_after_ASR':True},j)
  for n,h in read(HERE/'execution-contract.json')['source_hashes'].items():assert digest(HERE/n)==h
 if not (HERE/'self-test.json').exists():self_test(b,p['rows'][0])
 assert read(HERE/'self-test.json')['passed'];records=[]
 for cohort in ['legacy_diagnostic','prospective_once']:
  if cohort=='prospective_once':assert read(HERE/'baseline-gate.json')['passed']
  for row in [r for r in p['rows'] if r['cohort']==cohort]:
   for c in row['requests']:
    for v in p['variants']:records.append(run_one(b,p,row,c,v,0,predictors))
   print('baseline',row['id'],flush=True);b.reconcile()
  if cohort=='legacy_diagnostic' and not (HERE/'baseline-gate.json').exists():
   assert len(records)==96 and all(r['baseline_pre_headroom_bit_match'] for r in records);b.save(HERE/'baseline-gate.json',{'passed':True,'old_pre_headroom_wave_state_lf0_matches':96,'new_baseline_gain_common_factor':.25,'ASR_of_new_gain_wave_reused':False})
 for row in p['rows']:
  for c in row['requests']:
   for v in p['variants']:records.append(run_one(b,p,row,c,v,1,predictors))
  print('identity',row['id'],flush=True);b.reconcile()
 assert len(records)==384
 b.save(HERE/'render-manifest.json',{'rows':[{'id':r['mode']+'/'+r['id'],'record':str((HERE/'render'/r['mode']/(r['id']+'.json')).relative_to(REPO)),'wav':r['wav'],'wav_sha256':r['wav_sha256']} for r in records],'search_completed_before_ASR':True,'new_diagnostic_render':384,'new_diagnostic_DSP':1152,'gain_same_within_source_pairs':True,'quality_certified':False})
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
