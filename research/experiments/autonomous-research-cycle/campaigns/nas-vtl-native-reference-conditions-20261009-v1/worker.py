"""実VTL候補の全包絡/工学とnative参照を固定方法で測定する。"""
import sys,json,io,re,hashlib,os,tempfile
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import pyworld
here=Path(sys.argv[1]);work=Path(sys.argv[2]);vowel=sys.argv[3];assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()

sys.path.insert(0,str(here/'native-bundle'));from runtime import generate as native,verify
from acoustics import evaluate,estimate_f0
verify();centers=np.geomspace(500.,4000.,20);sigma=np.log(2)/6
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
