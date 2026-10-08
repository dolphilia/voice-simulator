"""SI収支と声道/反射/口元/観測を独立に計算し、新波形の全分母を保持。"""
import sys,json,math,hashlib,os,tempfile
from pathlib import Path
here=Path(sys.argv[1]);work=Path(sys.argv[2]);sys.path.insert(0,str(here/'runtime-bundle'))
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
import numpy as np
from scipy import signal
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from volume_sequence import generate,controls,block,observe,ah,FS,OUTFS,AREA,_fn,P
repo=here.parents[4];contract=json.loads((here/'measurement-package-contract.json').read_text())
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import pyworld
RCOEF=json.loads((here/'runtime-bundle/radiation-coefficients.json').read_text());RHO=1.2;C=343.
def independent_matrix(fs,radius,flanged):
 n,d,e=RCOEF['flanged' if flanged else 'unflanged'];delta=d*d-2*e-n*n;root=np.sqrt(delta)
 metric=np.array([[d-n,e],[e,e*(d-root)]]);U=np.linalg.cholesky(metric).T;V=np.linalg.inv(U)
 A=U@np.array([[0.,1.],[-1/e,-d/e]])@V;B=U@np.array([0.,1/e]);C=np.array([[-1.,-n],[-1.,root-d]])@V
 h=343/(2*fs*radius);inv=np.linalg.inv(np.eye(2)-h*A)
 return np.vstack([np.column_stack([inv@(np.eye(2)+h*A),np.sqrt(2*h)*inv@B]),np.column_stack([np.sqrt(2*h)*C@inv,np.array([0.,1.])+h*C@inv@B])])
def observer_taps():
 positions=np.arange(4,-5,-1,dtype=float);V=np.array([positions**m for m in range(9)]);target=np.zeros(9);target[1]=1.;weights=np.linalg.solve(V,target)
 return np.r_[np.zeros(100),weights*FS*RHO/(2*np.pi)]
matrix_cache={}
def reference(u,areas,initial=None):
 r=np.zeros(16);l=np.zeros(16);z=np.zeros(2)
 if initial is not None:r=initial[:16].copy();l=initial[16:32].copy();z=initial[32:].copy()
 mouth=[];pressure=[];loss=[];energy=[]
 for i,flow in enumerate(u):
  a=areas[i];radius=.01*math.sqrt(float(a[-1])/math.pi)
  if radius not in matrix_cache:matrix_cache[radius]=independent_matrix(FS,radius,True)
  v=matrix_cache[radius]@np.r_[z,r[-1]];z=v[:2];nr=np.empty(16);nl=np.empty(16);nl[-1]=v[2];loss.append(v[3]);root=math.sqrt(float(a[0])*1e-4)
  # 圧力波/特性インピーダンス式から源境界を別に計算する。
  backward=l[0]/root;Z=RHO*C/(float(a[0])*1e-4);forward=flow*Z+backward;nr[0]=forward*root;pressure.append(forward+backward)
  mouth.append((r[-1]/math.sqrt(float(a[-1])*1e-4)-v[2]/math.sqrt(float(a[-1])*1e-4))/(RHO*C/(float(a[-1])*1e-4)))
  for j in range(15):
   theta=math.asin((float(a[j])-float(a[j+1]))/(float(a[j])+float(a[j+1])));nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r,l=nr,nl;energy.append((r@r+l@l+z@z)/(RHO*C*FS))
 return np.array(mouth),np.array(pressure),np.array(loss),np.array(energy),np.r_[r,l,z]
def pressure_reference(u,a):
 radius=.01*math.sqrt(float(a[-1])/math.pi);n,d,e=RCOEF['flanged'];tau=radius/C;br,ar=signal.bilinear([-n*tau,-1.],[e*tau*tau,d*tau,1.],FS)
 r=np.zeros(16);l=np.zeros(16);state=np.zeros(2);mouth=[];pressure=[]
 for flow in u:
  reflected,state=signal.lfilter(br,ar,[r[-1]],zi=state);mouth.append((r[-1]-reflected[0])*a[-1]*1e-4/(RHO*C));nr=np.empty(16);nl=np.empty(16);nr[0]=flow*RHO*C/(a[0]*1e-4)+l[0];pressure.append(nr[0]+l[0]);nl[-1]=reflected[0]
  for j in range(15):
   k=(a[j]-a[j+1])/(a[j]+a[j+1]);nr[j+1]=(1+k)*r[j]-k*l[j+1];nl[j]=k*r[j]+(1-k)*l[j+1]
  r,l=nr,nl
 return np.array(mouth),np.array(pressure)
def balance(u,p,loss,E,initial):return float(np.max(abs(np.diff(np.r_[initial@initial/(RHO*C*FS),E])-(u*p-loss*loss/(RHO*C))/FS)))
rng=np.random.default_rng(770910);calls=0;core=[];h=observer_taps()
for radius in (.007,.008,.012,.016):
 n=262144;a=np.full((n,16),math.pi*(radius*100)**2);u=np.zeros(n);u[0]=1e-6;pieces=[];state=np.zeros(34)
 for start in range(0,n,65536):
  m,p,l,E,state=block(u[start:start+65536],a[start:start+65536],state);pieces.append(m);calls+=1
 mouth=np.concatenate(pieces);raw=signal.lfilter(h,[1.],mouth);calls+=1
 nf,d,e=RCOEF['flanged'];tau=radius/C;br,ar=signal.bilinear([-nf*tau,-1.],[e*tau*tau,d*tau,1.],FS)
 w=2*np.pi*np.arange(1,n//2)/n;_,R=signal.freqz(br,ar,w);q=np.exp(-1j*w);H=(1-R)*q**16/(1-R*q**32);actual=np.fft.rfft(mouth)[1:n//2]/1e-6;error=float(np.max(abs(actual-H)));assert error<=2e-8
 _,G=signal.freqz(h,[1.],w);expected=G*H;mic_error=float(np.max(abs(np.fft.rfft(raw)[1:n//2]/1e-6-expected))/np.max(abs(expected)));assert mic_error<=1e-8
 assert np.all(mouth[:16]==0.);core.append(dict(kind='uniform_SI_transfer',radius_m=radius,samples=n,volume_transfer_absolute_error=error,microphone_complex_error_relative_to_peak=mic_error,passed=True));calls+=1
for kind in ('fixed','ramp','sine','step'):
 n=4096;t=np.arange(n)/FS
 if kind=='fixed':a=np.tile(AREA['a'],(n,1))
 else:
  w=np.linspace(0,1,n) if kind=='ramp' else (.5+.5*np.sin(2*np.pi*7*t) if kind=='sine' else (np.arange(n)>=n//2).astype(float));a=(1-w[:,None])*AREA['i']+w[:,None]*AREA['a']
 for forced in (False,True):
  u=rng.normal(0,1e-6,n) if forced else np.zeros(n);initial=rng.normal(0,.001,34);m,p,l,E,last=block(u,a,initial);calls+=1;rm,rp,rl,rE,rstate=reference(u,a,initial);calls+=1
  ue=float(np.max(abs(m-rm)));pe=float(np.max(abs(p-rp)));be=balance(u,p,l,E,initial);assert ue<=5e-13 and pe<=5e-8 and be<=1e-16 and np.max(abs(E-rE))<=1e-14 and np.max(abs(last-rstate))<=1e-8
  if not forced:assert np.max(np.diff(np.r_[initial@initial/(RHO*C*FS),E]))<=1e-16
  cut=n//2;future_u=u.copy();future_u[cut:]=1e-5;future_a=a.copy();future_a[cut:]=AREA['u'];future=block(future_u,future_a,initial);calls+=1;assert m[:cut].tobytes()==future[0][:cut].tobytes()
  core.append(dict(kind=kind,forced=forced,flow_reference_error_m3_s=ue,source_pressure_reference_error_Pa=pe,per_step_energy_balance_error_J=be,unforced_monotone=not forced,future_input_and_area_prefix_exact=True,passed=True))
rows=[]
for row in json.loads((here/'requests.json').read_text()):
 audio,meta,raw,u,a,m,p,l,E=generate(row['request']);calls+=meta['source_and_block_render_calls'];rm,rp,rl,rE,_=reference(u,a);calls+=1
 ue=float(np.max(abs(m-rm)));pe=float(np.max(abs(p-rp)));micref=signal.lfilter(h,[1.],rm);calls+=1;me=float(np.max(abs(raw-micref)));be=balance(u,p,l,E,np.zeros(34))
 assert ue<=5e-13 and pe<=5e-8 and me<=1e-8 and be<=1e-16 and np.max(abs(E-rE))<=1e-14
 static=None
 if row['kind']=='static':
  pm,pp=pressure_reference(u,a[0]);calls+=1;static=dict(mouth_error_m3_s=float(np.max(abs(m-pm))),source_pressure_error_Pa=float(np.max(abs(p-pp))));assert static['mouth_error_m3_s']<=5e-13 and static['source_pressure_error_Pa']<=5e-8
 partition=None;prefix=None
 if row['kind']=='sequence':
  alternate=generate(row['request'],(2048,4096,8192));calls+=alternate[1]['source_and_block_render_calls'];assert raw.tobytes()==alternate[2].tobytes() and audio.tobytes()==alternate[0].tobytes() and m.tobytes()==alternate[5].tobytes() and meta['final_tube_state_sha256']==alternate[1]['final_tube_state_sha256'] and meta['final_observer_state_sha256']==alternate[1]['final_observer_state_sha256'];partition=True
  if len(row['request']['segments'])>1:
   q=json.loads(json.dumps(row['request']));q['segments'][-1]['vowel']='a' if q['segments'][-1]['vowel']!='a' else 'i';changed=generate(q);calls+=changed[1]['source_and_block_render_calls'];cut=meta['bounds_samples'][-2];assert raw[:cut].tobytes()==changed[2][:cut].tobytes();prefix=True
 path=work/(row['id']+'.wav');wavfile.write(path,OUTFS,audio.astype('float32'));fs,saved=wavfile.read(path);e0=evaluate(saved,dict(expected_duration_seconds=meta['duration_ms']/1000),fs)
 f,t=pyworld.dio(saved.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(saved.astype(float),f,t,fs);target=row['request']['f0'];v=f[f>0];median=float(np.median(v)) if len(v) else None
 lo,hi=(round(.10*fs),round(.55*fs)) if row['kind']!='sequence' else (round(.06*fs),-round(.06*fs));hz,confidence=estimate_f0(saved[lo:hi],fs,minimum=70,maximum=800);de=abs(12*math.log2(median/target)) if median else None;ae=abs(12*math.log2(hz/target)) if hz else None
 intervals=[(.10,.25),(.25,.40),(.40,.55)] if row['kind']!='sequence' else [(meta['bounds_samples'][j]/FS+.105,meta['bounds_samples'][j+1]/FS-.01) for j in range(len(row['request']['segments']))];support=[]
 for lo,hi in intervals:
  sel=(t>=lo)&(t<hi);valid=f[sel&(f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5;support.append(dict(bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),complete=bool(complete)))
 missing=sum(not s['complete'] for s in support);passed=bool(de is not None and ae is not None and de<=1 and ae<=1 and confidence>=.6 and not missing)
 rows.append(dict(id=row['id'],kind=row['kind'],request=row['request'],metadata=meta,mouth_flow_reference_error_m3_s=ue,source_pressure_reference_error_Pa=pe,microphone_reference_error_Pa=me,per_step_energy_balance_error_J=be,static_pressure_reference=static,partition_raw_audio_mouth_and_both_states_exact=partition,future_request_raw_prefix_exact=prefix,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=dict(passed=passed,dio_hz=median,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,support=support,missing=missing)))
invalid=0
for q in [{},dict(segments=[],f0=220),dict(segments=[dict(vowel='k',duration_ms=250)],f0=220),dict(segments=[dict(vowel='a',duration_ms=124)],f0=220),dict(segments=[dict(vowel='a',duration_ms=601)],f0=220),dict(segments=[dict(vowel='a',duration_ms=250)],f0=float('nan')),dict(segments=[dict(vowel='a',duration_ms=250)]*25,f0=220),dict(segments=[dict(vowel='a',duration_ms=600)]*11,f0=220),dict(segments=[dict(vowel='a',duration_ms=250)],f0=220,gain=.2)]:
 try:controls(q)
 except (ValueError,TypeError):invalid+=1
 else:raise AssertionError('不正requestを受理')
for u,a,s in [(np.array([np.nan]),np.ones((1,16)),np.zeros(34)),(np.zeros(1),np.ones((1,16)),np.full(34,np.nan)),(np.zeros(1),np.zeros((1,16)),np.zeros(34)),(np.zeros(1),np.ones((1,16)),np.zeros(32)),(np.array([.002]),np.ones((1,16)),np.zeros(34)),(np.zeros(1),np.ones((1,16)),np.full(34,101.)),(np.zeros(0),np.ones((0,16)),np.zeros(34))]:
 try:block(u,a,s)
 except ValueError:invalid+=1
 else:raise AssertionError('不正SI源/state/areaを受理')
assert invalid==16
last=np.full(34,321.);out=np.full(4,123.);initial=np.zeros(34);area=np.ones((4,16))
assert not _fn(None,area.ctypes.data_as(P),4,initial.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(last==321.) and np.all(out==123.)
assert len(rows)==43 and calls<=2000
summary=dict(total=43,E0_pass=sum(r['E0']['E0_pass'] for r in rows),pitch_pass=sum(r['pitch']['passed'] for r in rows),missing_support=sum(r['pitch']['missing'] for r in rows),fixed_support_intervals=sum(len(r['pitch']['support']) for r in rows))
print(json.dumps(dict(mechanism_passed=True,core_rows=core,rows=rows,summary=summary,invalid_cases=invalid+1,actual_render_calls=calls,engineering_all_required_pass=summary['E0_pass']==43 and summary['pitch_pass']==43,source_flow_is_prescribed_acoustic_perturbation_only=True,moving_wall_physical_work_qualified=False,infinite_baffle_approximation_not_real_head=True,Japanese_content_or_perceptual_qualification=False)))
