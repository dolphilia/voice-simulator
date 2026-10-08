"""共有母音生成と全方向遷移の独立数値、固定区間DIO/ACF、保存音声E0を検査。"""
import sys,json,math,tempfile,os,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;work=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
contract=json.loads((here/'measurement-package-contract.json').read_text());repo=here.parents[4]
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import numpy as np
import pyworld
from scipy.integrate import quad
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from vowel_tract import generate,coefficient,COEF,AREA,FS,OUTFS,output
from waveguide_tract import render,ah
def scalar(t):
 tp,te,ta,ep,a,e0,scale=map(float,COEF)
 return scale*(e0*math.exp(a*t)*math.sin(math.pi*t/tp) if t<=te else -(math.exp(-ep*(t-te))-math.exp(-ep*(1-te)))/(ep*ta))
fourier=[]
for m in (1,3,7,30,72):
 real=sum(quad(lambda t:scalar(t)*math.cos(2*math.pi*m*t),lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,.6),(.6,1.)])
 imag=sum(quad(lambda t:-scalar(t)*math.sin(2*math.pi*m*t),lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,.6),(.6,1.)])
 error=abs(coefficient(m)-complex(real,imag));assert error<=3e-11
 fourier.append(dict(harmonic=m,independent_complex_error=error))
def pressure_reference(x,A):
 n=len(A);r=np.zeros(n);l=np.zeros(n);out=[]
 for drive in x:
  out.append(.15*r[-1]*math.sqrt(A[-1]));nr=np.empty(n);nl=np.empty(n);nr[0]=drive/math.sqrt(A[0])+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(n-1):
   R1=1./A[j];R2=1./A[j+1];k=(R2-R1)/(R1+R2);nr[j+1]=(1.+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1.-k)*l[j+1]
  r=nr;l=nl
 return np.array(out)
def normalized_reference(x,areas):
 n=areas.shape[1];r=[0.]*n;l=[0.]*n;out=[]
 for at,drive in enumerate(x):
  out.append(.15*r[-1]);nr=[0.]*n;nl=[0.]*n;nr[0]=drive+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(n-1):
   k=(float(areas[at,j])-float(areas[at,j+1]))/(float(areas[at,j])+float(areas[at,j+1]));theta=math.asin(k)
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl
 return np.array(out)
def observe(audio,f0):
 f,t=pyworld.dio(audio.astype(float),OUTFS,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(audio.astype(float),f,t,OUTFS)
 intervals=[]
 for lo,hi in ((.10,.25),(.25,.40),(.40,.55)):
  sel=(t>=lo)&(t<hi);valid=f[sel & (f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5
  median=float(np.median(valid)) if len(valid) else None;distance=abs(12*math.log2(median/f0)) if median else None
  intervals.append(dict(bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),median_hz=median,complete=bool(complete),distance_semitones=distance))
 hz,confidence=estimate_f0(audio[2400:13200],OUTFS,minimum=70,maximum=800);allpositive=f[f>0];dio=float(np.median(allpositive)) if len(allpositive) else None
 de=abs(12*math.log2(dio/f0)) if dio else None;ae=abs(12*math.log2(hz/f0)) if hz else None
 passed=bool(de is not None and ae is not None and de<=1. and ae<=1. and confidence>=.6 and all(r['complete'] for r in intervals))
 return dict(passed=passed,dio_hz=dio,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,predefined_support=intervals,missing=sum(not r['complete'] for r in intervals),waveform_metrics_not_naturalness=True)
def save(id,audio,meta):
 path=work/(id+'.wav');wavfile.write(path,OUTFS,audio.astype(np.float32));fs,saved=wavfile.read(path);assert fs==OUTFS and len(saved)==14400
 e0=evaluate(saved,dict(kind='vowel',f0_hz=meta['source']['f0'],expected_duration_seconds=.6),fs);p=observe(saved,meta['source']['f0'])
 return dict(id=id,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=p,metadata=meta)
static=[];stored={};source_hashes={};calls=0
for v in ('a','i','u','e','o'):
 for f0 in (110,220,280):
  audio,meta,raw,x,area=generate(v,f0);reference=pressure_reference(x,AREA[v]);calls+=2
  error=float(np.max(np.abs(raw-reference)));assert error<=1e-10
  if f0 in source_hashes:assert source_hashes[f0]==meta['driver_sha256']
  else:source_hashes[f0]=meta['driver_sha256']
  row=save(f'{v}-{f0}',audio,meta);row['independent_pressure_error']=error;static.append(row)
  if f0==220:
   repeat=generate(v,f0);calls+=1;assert np.array_equal(audio,repeat[0]) and np.array_equal(raw,repeat[2]);stored[v]=raw
transition=[]
for first in ('a','i','u','e','o'):
 for second in ('a','i','u','e','o'):
  if first==second:continue
  audio,meta,raw,x,area=generate(first,220,second);reference=normalized_reference(x,area);calls+=2
  error=float(np.max(np.abs(raw-reference)));assert error<=1e-10
  assert meta['driver_sha256']==source_hashes[220] and np.array_equal(raw[:6860],stored[first][:6860])
  tail=float(np.max(np.abs(raw[17150:]-stored[second][17150:])));assert tail<=1e-7
  row=save(f'{first}-to-{second}',audio,meta);row.update(independent_normalized_error=error,initial_raw_prefix_exact=True,final_static_tail_max_error=tail);transition.append(row)
assert len(static)==15 and len(transition)==20 and calls==75
print(json.dumps(dict(mechanism_passed=True,rows=static,transitions=transition,independent_Fourier_rows=fourier,actual_valid_generation_or_reference_calls=calls,charged_render=160,charged_DSP=800,
 static_E0_pass=sum(x['E0']['E0_pass'] for x in static),static_pitch_pass=sum(x['pitch']['passed'] for x in static),static_missing=sum(x['pitch']['missing'] for x in static),static_fixed_intervals=45,
 transition_E0_pass=sum(x['E0']['E0_pass'] for x in transition),transition_pitch_pass=sum(x['pitch']['passed'] for x in transition),transition_missing=sum(x['pitch']['missing'] for x in transition),transition_fixed_intervals=60,
 all_static_source_hashes_shared=True,deterministic_repeat_exact=True,coarse_plate_shape_not_modern_MRI_truth=True,normalized_moving_wall_work_not_modeled=True,geometry_labels_not_independent_perceptual_identification=True,
 full_Japanese_content_qualified=False,perceptual_qualification=False,quality_goal_completed=False)))
