"""状態継承・任意区切り不変・独立回転・一母音の旧入口一致・全固定支持を検査。"""
import sys,json,math,os,tempfile,importlib.util,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;work=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
import numpy as np
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from sequence_tract import generate,controls,block,ah,AREA,FS,OUTFS
repo=here.parents[4];old=repo/'research/experiments/autonomous-research-cycle/campaigns/nas-waveguide-vowel-mechanism-20261008-v1/runtime-bundle'
sys.path.append(str(old));spec=importlib.util.spec_from_file_location('frozen_vowel_baseline',old/'vowel_tract.py');baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
contract=json.loads((here/'measurement-package-contract.json').read_text())
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import pyworld
def independent(x,a):
 r=[0.]*16;l=[0.]*16;out=[]
 for at,drive in enumerate(x):
  out.append(.15*r[-1]);nr=[0.]*16;nl=[0.]*16;nr[0]=drive+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(15):
   k=(float(a[at,j])-float(a[at,j+1]))/(float(a[at,j])+float(a[at,j+1]));theta=math.asin(k)
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl
 return np.array(out)
invalid=0
bad=[{},dict(segments=[],f0=220),dict(segments=[dict(vowel='k',duration_ms=200)],f0=220),dict(segments=[dict(vowel='a',duration_ms=124)],f0=220),dict(segments=[dict(vowel='a',duration_ms=601)],f0=220),dict(segments=[dict(vowel='a',duration_ms=200)],f0=float('nan')),dict(segments=[dict(vowel='a',duration_ms=200)]*25,f0=220),dict(segments=[dict(vowel='a',duration_ms=600)]*11,f0=220),dict(segments=[dict(vowel='a',duration_ms=200)],f0=220,gain=.25)]
for q in bad:
 try:controls(q)
 except (ValueError,TypeError):invalid+=1
 else:raise AssertionError('登録外のrequestを拒否しない')
try:block(np.zeros(4),np.ones((4,16)),np.full(32,np.nan))
except ValueError:invalid+=1
else:raise AssertionError('非有限状態を拒否しない')
rows=[];calls=0
for row in json.loads((here/'requests.json').read_text()):
 request=row['request'];audio,meta,raw,x,a=generate(request);alternate=generate(request,(2048,4096,8192));calls+=meta['source_and_block_render_calls']+alternate[1]['source_and_block_render_calls']
 assert np.array_equal(raw,alternate[2]) and np.array_equal(audio,alternate[0]) and meta['final_state_sha256']==alternate[1]['final_state_sha256']
 ref=independent(x,a);calls+=1;error=float(np.max(np.abs(raw-ref)));assert error<=1e-10
 original_exact=None
 if len(request['segments'])==1:
  original=baseline.generate(request['segments'][0]['vowel'],request['f0']);calls+=2;assert np.array_equal(raw,original[2]) and np.array_equal(audio,original[0]);original_exact=True
 if row['id']=='all-five':
  future=[dict(s) for s in request['segments']];future[-1]['vowel']='i';q=dict(segments=future,f0=request['f0']);changed=generate(q);calls+=changed[1]['source_and_block_render_calls'];cut=int(meta['bounds_samples'][-2]);assert np.array_equal(raw[:cut],changed[2][:cut])
 path=work/(row['id']+'.wav');wavfile.write(path,OUTFS,audio.astype(np.float32));fs,saved=wavfile.read(path)
 e0=evaluate(saved,dict(expected_duration_seconds=meta['duration_ms']/1000.),fs);f,t=pyworld.dio(saved.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(saved.astype(float),f,t,fs)
 hz,confidence=estimate_f0(saved[round(.06*fs):-round(.06*fs)],fs,minimum=70,maximum=800);v=f[f>0];median=float(np.median(v)) if len(v) else None;target=request['f0'];de=abs(12*math.log2(median/target)) if median else None;ae=abs(12*math.log2(hz/target)) if hz else None
 support=[]
 for index,segment in enumerate(request['segments']):
  lo=meta['bounds_samples'][index]/FS+.105;hi=meta['bounds_samples'][index+1]/FS-.01;sel=(t>=lo)&(t<hi);valid=f[sel & (f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5
  support.append(dict(index=index,bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),complete=bool(complete)))
 missing=sum(not s['complete'] for s in support);passed=bool(de is not None and ae is not None and de<=1. and ae<=1. and confidence>=.6 and not missing)
 rows.append(dict(id=row['id'],request=request,metadata=meta,independent_rotation_error=error,partition_wave_and_final_state_exact=True,old_single_vowel_raw_and_audio_exact=original_exact,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=dict(passed=passed,dio_hz=median,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,support=support,missing=missing)))
print(json.dumps(dict(mechanism_passed=True,rows=rows,actual_render_calls=calls,invalid_requests_and_state_rejected=invalid,longest_ms=max(r['metadata']['duration_ms'] for r in rows),fixed_support_intervals=sum(len(r['pitch']['support']) for r in rows),missing_support=sum(r['pitch']['missing'] for r in rows),E0_pass=sum(r['E0']['E0_pass'] for r in rows),pitch_pass=sum(r['pitch']['passed'] for r in rows),future_request_raw_prefix_exact=True,all_partitions_exact=True,content_or_perceptual_qualification=False)))
