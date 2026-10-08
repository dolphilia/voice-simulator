"""五CVの固定開発診断。旧中央測定器と二方式共有規則を用いる。"""
import sys,json,io,re,hashlib,os,tempfile
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import pyworld
bundle=Path(sys.argv[1]);native_bundle=Path(sys.argv[2]);work=Path(sys.argv[3]);study=Path(sys.argv[4]);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
sys.path.insert(0,str(bundle));from cv_runtime import CV
sys.path.insert(0,str(native_bundle));from runtime import generate as native,verify
from acoustics import evaluate,estimate_f0
verify();centers=np.geomspace(500.,4000.,20);sigma=np.log(2)/6;measure_calls=0
def measure(data,bounds,target):
 global measure_calls
 fs,audio=wavfile.read(io.BytesIO(data));assert fs==24000;audio=audio.astype(float);e0=evaluate(audio,{},fs);measure_calls+=3
 start,end=bounds;core=audio[round(start*fs):round(end*fs)];assert len(core)>=1024
 f0,times=pyworld.dio(audio,fs,f0_floor=70.,f0_ceil=400.,frame_period=5.);f0=pyworld.stonemask(audio,f0,times,fs);measure_calls+=2
 mask=(times>=start)&(times<end);voiced=f0[mask&(f0>=70)&(f0<=400)];dio=float(np.median(voiced)) if len(voiced) else None;acf,conf=estimate_f0(core,fs,minimum=70,maximum=400);measure_calls+=1
 def error(hz):return float(abs(12*np.log2(hz/target))) if hz and hz>0 else None
 de,ae=error(dio),error(acf);support=bool(int(mask.sum())>=3 and len(voiced)>=3 and len(voiced)>=int(mask.sum())*.5);passed=bool(e0['E0_pass'] and support and de is not None and ae is not None and de<=1. and ae<=1. and conf>=.6)
 freq,power=signal.welch(core,fs=fs,window='hann',nperseg=1024,noverlap=512,nfft=4096,detrend='constant',scaling='density',average='mean');measure_calls+=1
 weights=np.exp(-.5*(np.log(np.maximum(freq[:,None],1.)/centers[None,:])/sigma)**2);band=(power[:,None]*weights).sum(axis=0)/weights.sum(axis=0);shape=10*np.log10(np.maximum(band,1e-20));shape-=shape.mean()
 return dict(E0=e0,pitch=dict(dio_Hz=dio,ACF_Hz=acf,ACF_confidence=conf,dio_error_semitones=de,ACF_error_semitones=ae,central_interval_frames=int(mask.sum()),voiced_frames=len(voiced),single_interval_support=support,passed=passed,not_utterance_three_phone_support=True),central_window_seconds=[start,end],engineering_diagnostic_pass=passed,shape_log_power_dB=shape.tolist())
reg=json.loads((study/'registration.json').read_text());refs=[];rows=[];cases=[];render_calls=0;native_attempts=0;vtl=CV()
def checkpoint():
 (work/'partial.json').write_text(json.dumps(dict(rows=rows,cases=cases,completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls),ensure_ascii=False,allow_nan=False))
try:
 for spec in reg['cases']:
  token=spec['id'];vowel=spec['vowel'];native_attempts+=1;reference=None;native_status='measured';data=None
  try:data,meta,params,phone_row=native(spec['kana'],1.,140.,full=True)
  except ValueError as error:
   if str(error)!='LF0 sentinelまたは有声F0範囲が不正':raise
   native_status='native_parameter_domain_failed';meta=dict(error=str(error))
  if data is not None:
   render_calls+=meta['conversion']['render_calls_including_internal_MLSA'];measure_calls+=3;ident=token+'-native';(work/(ident+'.wav')).write_bytes(data)
   indices=[i for i,label in enumerate(phone_row['full_context_labels']) if re.search(r'\-([^+]+)\+',label).group(1).lower()==vowel]
   if len(indices)==1:
    i=indices[0];bounds=np.r_[0,np.cumsum(meta['duration'])]*.005;start,end=float(bounds[i*5]),float(bounds[(i+1)*5]);width=end-start
    if round(.6*width*24000)>=1024:reference=measure(data,[start+.2*width,end-.2*width],140.)
    else:native_status='fixed_vowel_window_too_short'
   else:native_status='fixed_native_vowel_label_not_unique'
   rows.append(dict(id=ident,case=token,method='native',status=native_status,wav_sha256=hashlib.sha256(data).hexdigest(),meta=dict(E0=meta['E0'],full_context_labels=phone_row['full_context_labels'],duration=meta['duration'],source_state_clock_not_observed_boundary=True),measurement=reference,render_reused=False))
  else:rows.append(dict(id=token+'-native',case=token,method='native',status=native_status,wav_sha256=None,meta=meta,measurement=None,render_reused=False))
  checkpoint();pair=[]
  for learned in [False,True]:
   method='learned' if learned else 'baseline';ident=token+'-'+method;old=spec.get('reuse',{}).get(method)
   if old:
    data=Path(old['path']).read_bytes();assert hashlib.sha256(data).hexdigest()==old['wav_sha256'];meta=old['meta'];reused=True
   else:
    data,meta=vtl.render_text(spec['kana'],140.,1.,learned,41);render_calls+=meta['render_calls'];reused=False;(work/(ident+'.wav')).write_bytes(data)
   start,end=meta['phone_intervals'][0]['source_schedule_vowel_interval'];width=end-start;measurement=measure(data,[start+.2*width,end-.2*width],140.);distance=float(np.mean((np.asarray(measurement['shape_log_power_dB'])-np.asarray(reference['shape_log_power_dB']))**2)) if reference else None
   if reference:measure_calls+=1
   row=dict(id=ident,case=token,method=method,status='measured',wav_sha256=hashlib.sha256(data).hexdigest(),meta=meta,measurement=measurement,render_reused=reused,shape_distance=distance,reference_engineering_pass=bool(reference and reference['engineering_diagnostic_pass']));rows.append(row);pair.append(row);checkpoint()
  valid=bool(reference and reference['engineering_diagnostic_pass'] and all(x['measurement']['engineering_diagnostic_pass'] for x in pair))
  cases.append(dict(id=token,kana=spec['kana'],actual_onset=spec['onset'],vowel=vowel,reference_status=native_status,joint_comparison_valid=valid,baseline_shape_MSE=pair[0]['shape_distance'],learned_shape_MSE=pair[1]['shape_distance'],loss_change=pair[1]['shape_distance']-pair[0]['shape_distance'] if reference else None,qualified_shape_improvement=bool(valid and pair[1]['shape_distance']<pair[0]['shape_distance']-1e-8),qualified_shape_worsening=bool(valid and pair[1]['shape_distance']>pair[0]['shape_distance']+1e-8),not_content_or_naturalness_evidence=True));checkpoint()
finally:vtl.close()
assert len(rows)==15 and len(cases)==5 and render_calls<=1400 and measure_calls<=300
(work/'grid.json').write_text(json.dumps(dict(rows=rows,cases=cases,completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls,native_attempts=native_attempts,partial_DSP_of_native_domain_failures_unmeasured=True,quality_goal_completed=False),ensure_ascii=False,allow_nan=False))
print(json.dumps(dict(rows=15,cases=5,completed_render_calls=render_calls,completed_DSP_macro_calls=measure_calls,generated_files=[p.name for p in work.glob('*.wav')],reused_waveforms=sum(x['render_reused'] for x in rows))))
