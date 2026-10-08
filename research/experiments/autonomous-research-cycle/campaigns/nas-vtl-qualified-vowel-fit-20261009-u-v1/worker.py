"""別条件の固定訓練参照に対し実VTL候補だけを生成する。"""
import sys,json,io,re,hashlib,os,tempfile
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import pyworld
here=Path(sys.argv[1]);work=Path(sys.argv[2]);vowel=sys.argv[3]
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
sys.path.insert(0,str(here/'runtime-bundle'));from vtl_runtime import VTL
sys.path.insert(0,str(here));from acoustics import evaluate,estimate_f0
spec=json.loads((here/'registration.json').read_text());centers=np.geomspace(500.,4000.,20);sigma=np.log(2)/6
measure_calls=0
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
refs=json.loads((here/'training-reference.json').read_text())['references'];all_rows=[];render_calls=0;vtl=VTL()
try:
 for c in spec['candidates']:
  for target in spec['F0_conditions']:
   ident=c['id']+'-'+str(int(target));data,meta=vtl.render(vowel,target,.32,41,c['dx_cm'],c['dy_cm']);render_calls+=meta['render_calls'];(work/(ident+'.wav')).write_bytes(data)
   measurement=measure(data,[.064,.256],target);ref=refs[str(int(target))]['measurement'];distance=float(np.mean((np.asarray(measurement['shape_log_power_dB'])-np.asarray(ref['shape_log_power_dB']))**2));valid=bool(measurement['engineering_diagnostic_pass'] and ref['engineering_diagnostic_pass'])
   all_rows.append(dict(id=ident,candidate_id=c['id'],target_F0_Hz=target,dx_cm=c['dx_cm'],dy_cm=c['dy_cm'],wav_sha256=hashlib.sha256(data).hexdigest(),meta=meta,measurement=measurement,reference_engineering_pass=ref['engineering_diagnostic_pass'],admissible=valid,shape_distance=distance,role='training candidate; reference is reused; not unused comparison'))
   (work/'partial.json').write_text(json.dumps(dict(rows=all_rows,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls),allow_nan=False))
finally:vtl.close()
assert len(all_rows)==18 and render_calls==2376 and measure_calls==126
value=dict(vowel=vowel,references=refs,rows=all_rows,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,fit_performed=False,quality_goal_completed=False,protected_confirmation_opened=False)
(work/'grid.json').write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));print(json.dumps(dict(vowel=vowel,rows=18,references=2,reference_regeneration=0,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,output_files=[x['id']+'.wav' for x in all_rows])))
