"""結合の独立反射/伝達/エネルギーと両固定駆動の全分母を評価する。"""
import sys,json,math,os,tempfile,hashlib
from pathlib import Path
here=Path(sys.argv[1]);work=Path(sys.argv[2]);sys.path.insert(0,str(here/'runtime-bundle'))
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
import numpy as np
from scipy import signal
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from radiated_sequence import generate,controls,block,ah,FS,OUTFS,_fn,P,AREA
repo=here.parents[4];contract=json.loads((here/'measurement-package-contract.json').read_text())
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import pyworld
RCOEF=json.loads((here/'runtime-bundle/radiation-coefficients.json').read_text())
def independent_matrix(fs,radius,flanged):
 n,d,e=RCOEF['flanged' if flanged else 'unflanged'];delta=d*d-2*e-n*n;root=np.sqrt(delta)
 metric=np.array([[d-n,e],[e,e*(d-root)]]);U=np.linalg.cholesky(metric).T;V=np.linalg.inv(U)
 A=U@np.array([[0.,1.],[-1/e,-d/e]])@V;B=U@np.array([0.,1/e]);C=np.array([[-1.,-n],[-1.,root-d]])@V
 h=343/(2*fs*radius);inv=np.linalg.inv(np.eye(2)-h*A)
 return np.vstack([np.column_stack([inv@(np.eye(2)+h*A),np.sqrt(2*h)*inv@B]),np.column_stack([np.sqrt(2*h)*C@inv,np.array([0.,1.])+h*C@inv@B])])
matrix_cache={}
def reference(x,areas,initial=None):
 r=[0.]*16;l=[0.]*16;z=np.zeros(2)
 if initial is not None:r=list(initial[:16]);l=list(initial[16:32]);z=np.array(initial[32:])
 out=[];energy=[]
 for at,drive in enumerate(x):
  a=areas[at];radius=.01*math.sqrt(float(a[-1])/math.pi)
  if radius not in matrix_cache:matrix_cache[radius]=independent_matrix(FS,radius,False)
  v=matrix_cache[radius]@np.array([z[0],z[1],r[-1]]);z=v[:2];out.append(v[3]);nr=[0.]*16;nl=[0.]*16;nr[0]=drive+.75*l[0];nl[-1]=v[2]
  for j in range(15):
   k=(float(a[j])-float(a[j+1]))/(float(a[j])+float(a[j+1]));theta=math.asin(k);nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl;energy.append(sum(y*y for y in r)+sum(y*y for y in l)+z@z)
 return np.array(out),np.array(energy),np.r_[r,l,z]
def pressure_reference(x,a):
 radius=.01*math.sqrt(float(a[-1])/math.pi);n,d,e=RCOEF['unflanged'];tau=radius/343.;delta=d*d-2*e-n*n
 br,ar=signal.bilinear([-n*tau,-1.],[e*tau*tau,d*tau,1.],FS);bt,at=signal.bilinear([e*tau*tau,math.sqrt(delta)*tau,0.],[e*tau*tau,d*tau,1.],FS)
 r=np.zeros(16);l=np.zeros(16);zr=np.zeros(2);zt=np.zeros(2);out=[]
 for drive in x:
  reflected,zr=signal.lfilter(br,ar,[r[-1]],zi=zr);loss,zt=signal.lfilter(bt,at,[r[-1]],zi=zt);out.append(loss[0]*math.sqrt(a[-1]));nr=np.empty(16);nl=np.empty(16);nr[0]=drive/math.sqrt(a[0])+.75*l[0];nl[-1]=reflected[0]
  for j in range(15):
   k=(a[j]-a[j+1])/(a[j]+a[j+1]);nr[j+1]=(1+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1-k)*l[j+1]
  r=nr;l=nl
 return np.array(out)
rng=np.random.default_rng(730910);core=[];calls=0
for radius in (.007,.008,.012,.016):
 n=16384;a=np.full((n,16),math.pi*(radius*100)**2);x=np.zeros(n);x[0]=1.;y,E,last=block(x,a,np.zeros(34));calls+=1
 nf,d,e=RCOEF['unflanged'];tau=radius/343.;delta=d*d-2*e-nf*nf;br,ar=signal.bilinear([-nf*tau,-1.],[e*tau*tau,d*tau,1.],FS);bt,at=signal.bilinear([e*tau*tau,math.sqrt(delta)*tau,0.],[e*tau*tau,d*tau,1.],FS)
 omega=2*np.pi*np.arange(1,n//2)/n;_,R=signal.freqz(br,ar,omega);_,T=signal.freqz(bt,at,omega);q=np.exp(-1j*omega);H=T*q**16/(1-.75*R*q**32);error=float(np.max(abs(np.fft.rfft(y)[1:n//2]-H)));assert error<=1e-10
 assert np.all(y[:16]==0);core.append(dict(kind='uniform',radius_m=radius,frequency_error=error,passed=True));calls+=1
for kind in ('fixed','ramp','sine','step'):
 n=4096;t=np.arange(n)/FS
 if kind=='fixed':a=np.tile(AREA['a'],(n,1))
 else:
  w=np.linspace(0,1,n) if kind=='ramp' else (.5+.5*np.sin(2*np.pi*7*t) if kind=='sine' else (np.arange(n)>=n//2).astype(float));a=(1-w[:,None])*AREA['i']+w[:,None]*AREA['a']
 for forced in (False,True):
  x=rng.normal(0,.1,n) if forced else np.zeros(n);initial=rng.normal(0,.1,34);y,E,last=block(x,a,initial);calls+=1;ref,re,rstate=reference(x,a,initial);calls+=1;error=float(np.max(abs(y-ref)));assert error<=1e-10 and np.max(abs(last-rstate))<=1e-10
  if not forced:assert np.max(np.diff(np.r_[initial@initial,E]))<=2e-10
  cut=n//2;future_x=x.copy();future_x[cut:]=.3;future_a=a.copy();future_a[cut:]=AREA['u'];future=block(future_x,future_a,initial);calls+=1;assert y[:cut].tobytes()==future[0][:cut].tobytes()
  core.append(dict(kind=kind,forced=forced,independent_error=error,unforced_monotone=not forced,future_input_and_area_prefix_exact=True,passed=True))
invalid=0
for q in [{},dict(segments=[],f0=220),dict(segments=[dict(vowel='k',duration_ms=250)],f0=220),dict(segments=[dict(vowel='a',duration_ms=124)],f0=220),dict(segments=[dict(vowel='a',duration_ms=601)],f0=220),dict(segments=[dict(vowel='a',duration_ms=250)],f0=float('nan')),dict(segments=[dict(vowel='a',duration_ms=250)]*25,f0=220),dict(segments=[dict(vowel='a',duration_ms=600)]*11,f0=220),dict(segments=[dict(vowel='a',duration_ms=250)],f0=220,gain=.2)]:
 try:controls(q)
 except (ValueError,TypeError):invalid+=1
 else:raise AssertionError('不正requestを受理')
try:controls(dict(segments=[dict(vowel='a',duration_ms=250)],f0=220),'other')
except ValueError:invalid+=1
else:raise AssertionError('未登録sourceを受理')
for x,a,s in [(np.array([np.nan]),np.ones((1,16)),np.zeros(34)),(np.zeros(1),np.ones((1,16)),np.full(34,np.nan)),(np.zeros(1),np.zeros((1,16)),np.zeros(34)),(np.zeros(1),np.ones((1,16)),np.zeros(32))]:
 try:block(x,a,s)
 except ValueError:invalid+=1
 else:raise AssertionError('不正state/area/sourceを受理')
assert invalid==14
last=np.full(34,321.);out=np.full(4,123.);initial=np.zeros(34);area=np.ones((4,16))
assert not _fn(None,area.ctypes.data_as(P),4,16,FS,.75,initial.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(last==321.) and np.all(out==123.)
rows=[]
for row in json.loads((here/'requests.json').read_text()):
 for source in ('derivative','flow'):
  audio,meta,raw,x,a=generate(row['request'],source);calls+=meta['source_and_block_render_calls'];ref,_,_=reference(x,a);calls+=1;error=float(np.max(abs(raw-ref)));assert error<=1e-10
  static_pressure_error=None
  if row['kind']=='static':
   pp=pressure_reference(x,a[0]);calls+=1;static_pressure_error=float(np.max(abs(raw-pp)));assert static_pressure_error<=1e-10
  partition=None;future_prefix=None
  if row['kind']=='sequence':
   alternate=generate(row['request'],source,(2048,4096,8192));calls+=alternate[1]['source_and_block_render_calls'];assert raw.tobytes()==alternate[2].tobytes() and audio.tobytes()==alternate[0].tobytes() and meta['final_state_sha256']==alternate[1]['final_state_sha256'];partition=True
   if len(row['request']['segments'])>1:
    q=json.loads(json.dumps(row['request']));q['segments'][-1]['vowel']='a' if q['segments'][-1]['vowel']!='a' else 'i';changed=generate(q,source);calls+=changed[1]['source_and_block_render_calls'];cut=meta['bounds_samples'][-2];assert raw[:cut].tobytes()==changed[2][:cut].tobytes();future_prefix=True
  path=work/(row['id']+'-'+source+'.wav');wavfile.write(path,OUTFS,audio.astype('float32'));fs,saved=wavfile.read(path);e0=evaluate(saved,dict(expected_duration_seconds=meta['duration_ms']/1000),fs)
  f,t=pyworld.dio(saved.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(saved.astype(float),f,t,fs);target=row['request']['f0'];v=f[f>0];median=float(np.median(v)) if len(v) else None
  lo,hi=(round(.10*fs),round(.55*fs)) if row['kind']!='sequence' else (round(.06*fs),-round(.06*fs));hz,confidence=estimate_f0(saved[lo:hi],fs,minimum=70,maximum=800);de=abs(12*math.log2(median/target)) if median else None;ae=abs(12*math.log2(hz/target)) if hz else None
  intervals=[(.10,.25),(.25,.40),(.40,.55)] if row['kind']!='sequence' else [(meta['bounds_samples'][j]/FS+.105,meta['bounds_samples'][j+1]/FS-.01) for j in range(len(row['request']['segments']))];support=[]
  for lo,hi in intervals:
   sel=(t>=lo)&(t<hi);valid=f[sel&(f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5;support.append(dict(bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),complete=bool(complete)))
  missing=sum(not s['complete'] for s in support);passed=bool(de is not None and ae is not None and de<=1 and ae<=1 and confidence>=.6 and not missing)
  rows.append(dict(id=row['id'],kind=row['kind'],source=source,request=row['request'],metadata=meta,independent_error=error,static_pressure_error=static_pressure_error,partition_raw_audio_state_exact=partition,future_request_prefix_exact=future_prefix,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=dict(passed=passed,dio_hz=median,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,support=support,missing=missing)))
assert len(rows)==86 and calls<=2000
summary={s:dict(total=43,E0_pass=sum(r['E0']['E0_pass'] for r in rows if r['source']==s),pitch_pass=sum(r['pitch']['passed'] for r in rows if r['source']==s),missing_support=sum(r['pitch']['missing'] for r in rows if r['source']==s),fixed_support_intervals=sum(len(r['pitch']['support']) for r in rows if r['source']==s)) for s in ('derivative','flow')}
print(json.dumps(dict(mechanism_passed=True,core_rows=core,rows=rows,summary=summary,invalid_cases=invalid+1,actual_render_calls=calls,all_partitions_exact=True,moving_wall_work_qualified=False,far_field_microphone_qualified=False,Japanese_content_or_perceptual_qualification=False)))
