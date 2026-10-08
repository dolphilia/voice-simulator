"""SI体積速度源・共有声道・バッフル放射・軸上観測を一つの状態列へ結合する。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from radiation_passive_state_20261008 import C_SOURCE as PORT_C
from volume_velocity_observer_20261009 import C_SOURCE as UNITS_C
from waveguide_sequence_runtime_20261008 import MODULE as SEQUENCE
from radiated_waveguide_mechanism_20261009 import INDEPENDENT,requests
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-volume-waveguide-coupling-20261009-v1';NAME='volume-waveguide-coupling-v1'
PREV=ROOT/'campaigns/nas-volume-velocity-observer-20261009-v1'
PORT=ROOT/'campaigns/nas-radiation-passive-state-20261008-v1'
TUBE=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
FLOW=ROOT/'campaigns/nas-radiated-waveguide-mechanism-20261009-v1/runtime-bundle/flow-normalization.json'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

C_SOURCE=PORT_C+UNITS_C+r'''
/* 左端は理想体積速度源。口元flowと源の仕事はSI、lossは収支専用。 */
int tube_volume(const double*u,const double*area,size_t n,const double*initial,double*last,double*mouth,double*source_pressure,double*loss,double*energy){
 if(!u||!area||!initial||!last||!mouth||!source_pressure||!loss||!energy||n<1||n>96000)return 0;
 for(size_t j=0;j<34;j++)if(!isfinite(initial[j])||fabs(initial[j])>100.)return 0;
 for(size_t i=0;i<n;i++){
  if(!isfinite(u[i])||fabs(u[i])>.001)return 0;
  for(size_t j=0;j<16;j++)if(!area_ok(area[16*i+j]))return 0;
  double radius=.01*sqrt(area[16*i+15]/3.14159265358979323846);if(radius<.003||radius>.03)return 0;
 }
 double r[16],l[16],nr[16],nl[16],z0=initial[32],z1=initial[33],K[12];
 for(int j=0;j<16;j++){r[j]=initial[j];l[j]=initial[16+j];}
 for(size_t i=0;i<n;i++){
  const double*a=area+16*i;double radius=.01*sqrt(a[15]/3.14159265358979323846);
  if(!port_matrix(34300.,radius,1,K))return 0;
  double incident=r[15],v0=K[0]*z0+K[1]*z1+K[2]*incident,v1=K[3]*z0+K[4]*z1+K[5]*incident;
  nl[15]=K[6]*z0+K[7]*z1+K[8]*incident;loss[i]=K[9]*z0+K[10]*z1+K[11]*incident;
  double root=sqrt(a[0]*1e-4);nr[0]=1.2*343.*u[i]/root+l[0];source_pressure[i]=(nr[0]+l[0])/root;
  mouth[i]=sqrt(a[15]*1e-4)*(incident-nl[15])/(1.2*343.);
  for(int j=0;j<15;j++){double k=(a[j]-a[j+1])/(a[j]+a[j+1]),t=sqrt(1.-k*k);nr[j+1]=t*r[j]-k*l[j+1];nl[j]=k*r[j]+t*l[j+1];}
  z0=v0;z1=v1;double E=z0*z0+z1*z1;
  for(int j=0;j<16;j++){r[j]=nr[j];l[j]=nl[j];E+=r[j]*r[j]+l[j]*l[j];}
  energy[i]=E/(1.2*343.*34300.);
 }
 for(int j=0;j<16;j++){last[j]=r[j];last[16+j]=l[j];}last[32]=z0;last[33]=z1;return 1;
}
'''

PREFIX=SEQUENCE[:SEQUENCE.index('P=C.POINTER')]
PREFIX=PREFIX.replace("HERE/'coefficients.json'","HERE/'lf-coefficients.json'").replace('CUTOFF=8000.;GAIN=.10','CUTOFF=6000.;GAIN=1.')
# 源は元の解析積分AC形。新規のSI振幅と帯域を出力前に固定する。
PREFIX=PREFIX.replace('coefficient(m)*np.exp','(coefficient(m)/(2j*math.pi*m*FLOW_STD)*FLOW_RMS)*np.exp')
PREFIX=PREFIX.replace('def driver(f0,samples):',"FLOW_STD=json.loads((HERE/'flow-normalization.json').read_text())['standard_deviation'];FLOW_RMS=3e-5\ndef driver(f0,samples):")
CONTROL=SEQUENCE[SEQUENCE.index('def controls(request):'):SEQUENCE.index('def generate(request,')]
CONTROL=CONTROL.replace('coefficient(m)*np.exp','(coefficient(m)/(2j*math.pi*m*FLOW_STD)*FLOW_RMS)*np.exp')
MODULE=PREFIX+r'''
P=C.POINTER(C.c_double);_lib=C.CDLL(str(HERE/'volume_tube.dylib'));_fn=_lib.tube_volume;_obs=_lib.axial_observer
_fn.restype=C.c_int;_fn.argtypes=[P,P,C.c_size_t,P,P,P,P,P,P]
_obs.restype=C.c_int;_obs.argtypes=[P,C.c_size_t,C.c_double,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def block(u,a,state):
 u,a,state=[np.ascontiguousarray(v,dtype=float) for v in (u,a,state)]
 if u.ndim!=1 or a.shape!=(len(u),16) or state.shape!=(34,):raise ValueError('SI源/断面/状態寸法が不整合')
 before=(ah(u),ah(a),ah(state));m=np.empty_like(u);p=np.empty_like(u);loss=np.empty_like(u);energy=np.empty_like(u);last=np.empty(34)
 if not _fn(u.ctypes.data_as(P),a.ctypes.data_as(P),len(u),state.ctypes.data_as(P),last.ctypes.data_as(P),m.ctypes.data_as(P),p.ctypes.data_as(P),loss.ctypes.data_as(P),energy.ctypes.data_as(P)):raise ValueError('有限SI源/状態/面積範囲を拒否')
 assert before==(ah(u),ah(a),ah(state));return m,p,loss,energy,last
def observe(u,state):
 u=np.ascontiguousarray(u,dtype=float);state=np.ascontiguousarray(state,dtype=float)
 if u.ndim!=1 or state.shape!=(108,):raise ValueError('口元flow/観測履歴寸法が不整合')
 before=(ah(u),ah(state));out=np.empty_like(u);last=np.empty(108)
 if not _obs(u.ctypes.data_as(P),len(u),1.,state.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P)):raise ValueError('登録済み観測flow/履歴範囲を拒否')
 assert before==(ah(u),ah(state));return out,last
''' + CONTROL + r'''
def generate(request,partition=(4096,)):
 if not isinstance(partition,tuple) or not partition or any(type(v) is not int or not 1<=v<=96000 for v in partition):raise ValueError('内部block寸法が登録範囲外')
 u,a,meta=controls(request);state=np.zeros(34);observer_state=np.zeros(108);raw=np.empty(len(u));mouth=np.empty(len(u));pressure=np.empty(len(u));loss=np.empty(len(u));energy=np.empty(len(u));start=0;calls=0
 while start<len(u):
  stop=min(len(u),start+partition[calls%len(partition)]);m,p,l,e,state=block(u[start:stop],a[start:stop],state);y,observer_state=observe(m,observer_state);raw[start:stop]=y;mouth[start:stop]=m;pressure[start:stop]=p;loss[start:stop]=l;energy[start:stop]=e;start=stop;calls+=1
 audio=output(raw);meta.update(source_kind='prescribed_AC_volume_velocity',source_global_continuous_RMS_m3_s=FLOW_RMS,source_truncation_RMS_renormalized=False,source_mean=0.,source_is_acoustic_perturbation_not_total_nonnegative_flow=True,glottal_reflection=1.,termination='flanged',microphone_distance_m=1.,propagation_samples=100,numerical_observer_delay_samples=4,Pa_to_PCM=GAIN,block_calls=calls,source_and_block_render_calls=1+2*calls,final_tube_state_sha256=ah(state),final_observer_state_sha256=ah(observer_state),raw_Pa_sha256=ah(raw),mouth_m3_s_sha256=ah(mouth),output_sha256=ah(audio),stored_energy_max_J=float(energy.max()),state_reset_only_at_utterance_start=True,source_phase_reset_at_block_boundaries=False,causal_raw_but_offline_output_resampling=True)
 return audio,meta,raw,u,a,mouth,pressure,loss,energy
'''

WORKER=r'''"""SI収支と声道/反射/口元/観測を独立に計算し、新波形の全分母を保持。"""
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
''' + INDEPENDENT + r'''
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
'''

@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield j
    except BaseException as e:b.finish(j,repr(e));raise
    else:b.finish(j)
def execute(cmd,env,timeout=600):
    env=dict(env);env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1');return subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=timeout)
def verify(name):
    c=read(HERE/name);assert digest(Path(__file__))==c['controller_sha256']
    for p,h in c['files'].items():assert digest(HERE/p)==h,p
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'] and read(PREV/'aggregate-summary.json')['passed']
    for src in (MODULE,WORKER):ast.parse(src)
    limits=dict(seconds=14400,bytes=600000000,write_bytes=1200000000,setup=20,audit=20,render=3000,dsp=6000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='理想的SI体積速度源・共有声道・flanged放射と口元flow・軸上観測を結合し、源の仕事と放射損失の収支/因果/状態/新波形工学の全分母を保持できるか。',
      inherited=dict(units_observer_seal=digest(PREV/'artifact-seal.json'),port_seal=digest(PORT/'artifact-seal.json'),tube_seal=digest(TUBE/'artifact-seal.json'),diameters=digest(TUBE/'runtime-bundle/diameters.json'),LF_coefficients=digest(TUBE/'runtime-bundle/coefficients.json'),flow_global_normalization=digest(FLOW)),
      source=dict(type='prescribed acoustic AC volume perturbation',global_continuous_RMS_m3_s=3e-5,mean=0.,maximum_harmonic_hz=6000,phase_start=.125,no_per_wave_or_truncated_RMS_fit=True,not_total_nonnegative_glottal_flow_or_lung_vortex_model=True),
      boundary=dict(ideal_volume_source_reflection=1.,rho_kg_m3=1.2,c_m_s=343.,source_pressure='(rho*c*Us/sqrt(Ag)+2*Lold)/sqrt(Ag)',mouth_flow='sqrt(Al)*(Rincident-Rreflected)/(rho*c)',radiation_termination='flanged',radiation_loss_for_energy_only_not_audio=True,microphone='qualified ideal infinite-baffle uniform-disk axis at 1m, 9tap derivative, 100+4 samples delay'),
      output=dict(fs=34300,output_fs=24000,Pa_to_PCM=1.,full_scale_peak_pressure_Pa=1.,fade_ms=12.,conversion_is_predeclared_engineering_not_fitted_recording=True,offline_resample_240_343_Kaiser5=True),
      derivation='E=(sum(R^2+L^2)+radstate^2)/(rho*c*Fs), units J. Enew-Eold=(Us*source_pressure-loss^2/(rho*c))/Fs. Zero input glottal source is perfectly reflecting, radiation drains energy. Uniform Uout/Us=(1-R(z))*z^-16/(1-R(z)*z^-32), microphone G(z) times this. Canonical variable-area energy is a mathematical model, not actual moving-wall work.',
      fixtures=dict(requests=requests(),uniform_radii_m=[.007,.008,.012,.016],uniform_samples=262144,uniform_blocks=65536,uniform_impulse_m3_s=1e-6,energy_geometries=['fixed a','i→a ramp','7Hz sine i/a','half-step i/a'],energy_samples=4096,forced_SD_m3_s=1e-6,initial_state_SD_Pa_m=.001,forced_and_unforced=True,seed=770910,sequence_partitions=[4096,[2048,4096,8192]]),
      gates=dict(uniform_volume_transfer_absolute_error=2e-8,uniform_microphone_complex_error_relative_to_peak=1e-8,mouth_flow_reference_m3_s=5e-13,source_pressure_reference_Pa=5e-8,microphone_reference_Pa=1e-8,energy_reference_J=1e-14,per_sample_energy_balance_error_J=1e-16,unforced_energy_increase_J_at_most=1e-16,partition_raw_audio_flow_tube_and_observer_states_bytes_exact=True,future_input_area_request_raw_prefix_bytes_exact=True,invalid_cases=17,E0='旧evaluate全条件、振幅/測定ゲート変更なし',pitch='旧DIO/ACF±1半音、confidence≥.6。3固定支持/列は各[+.105,終了-.01]。3frame以上/半数以上。欠測全分母。'),
      scope='SI源/口元/理想軸上の結合。源RMSやPa→PCMを出力後fit/正規化しない。構成の数値一致と6kHz固定観測誤差の限定域を、実人声/頭部/移動壁/総気流/知覚/子音の資格へ移さない。動的形状による帯域外成分を含む可能性があり、全過渡の物理誤差2%とは主張しない。旧語句や8kHz候補は再判定せず、旧全不採択/全凍結を保持。',
      estimates=dict(render=2000,dsp=3000,internal_calls_references_and_source_included=True,temporary_peak=64000000,temporary_write=128000000,RAM_gb=8,closeout_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      next='全結果を保持して共有SI生成器の通常/隔離/CLIを別登録する。全43工学が不通過なら、その事実/原因を保持し、source/gain/径/時刻/基準で救済しない。独立のdistributed wall loss/鼻/閉鎖/子音などを選ぶ。内容・知覚・独立P5の未達を保持する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','SI結合の源振幅/物理単位/バッフル/観測/全43波形と費用を事前固定',size=4000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'requests.json',requests(),j)
        for n,s in [('volume_tube.c',C_SOURCE),('volume_sequence.py',MODULE),('worker.py',WORKER)]:b.write(HERE/n,s.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    b.save(ROOT/'progress-0138.json',dict(active_campaign=NAME,next='登録push→共有SI結合C/固定源/build→独立全収支/伝達と43波形工学を封印',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()));print('SI声道結合と全波形を事前登録',flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('source-contract.json')
    with job(b,'setup','SI結合Cと元LF/共有径/固定全球正規化のbundle',size=55000000) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'volume_sequence.py',MODULE.encode(),j)
        for dest,origin in [('diameters.json',TUBE/'runtime-bundle/diameters.json'),('lf-coefficients.json',TUBE/'runtime-bundle/coefficients.json'),('flow-normalization.json',FLOW),('radiation-coefficients.json',PORT/'coefficients.json'),('acoustics.py',TUBE/'runtime-bundle/acoustics.py')]:b.write(bundle/dest,origin.read_bytes(),j)
        b.save(HERE/'measurement-package-contract.json',read(TUBE/'measurement-package-contract.json'),j)
        with b.workspace(j,'SI結合C build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'volume_tube.c'),'-o',str(bundle/'volume_tube.dylib')]
            with b.external_output(bundle/'volume_tube.dylib',100000,j):out=execute(cmd,env,120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'volume_tube.c'),binary_sha256=digest(bundle/'volume_tube.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recording=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_waveforms=True),j)
    print('共有SI生成bundleを初波形前に固定',flush=True)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract.json')
    with job(b,'render','SI結合全源/参照/内部block/観測/未来/区切りの実呼出し',2000,160000000,2200) as r:
        with job(b,'dsp','SI伝達/仕事とlossの収支/動的受動/43全工学支持',3000,12000000,2200) as d:
            with b.workspace(r,'SI結合の全43WAVと科学依存初期化',64000000,128000000) as (work,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE),str(work)],env,2200)
                except subprocess.CalledProcessError as e:b.save(HERE/'child-failure.json',dict(returncode=e.returncode,stdout=e.stdout,stderr=e.stderr),d);raise
                v=json.loads(out.stdout);assert v['mechanism_passed']
                for row in v['rows']:b.write_data(HERE/'audio'/(row['id']+'.wav'),(work/(row['id']+'.wav')).read_bytes(),d)
                b.save(HERE/'fixture-audit.json',v,d)
    with job(b,'audit','SI声道/理想観測の限定資格と全波形/欠測/費用/回収を封印',size=3000000) as j:
        verify('execution-contract.json')
        for prev in (PREV,PORT,TUBE):
            for n,h in read(prev/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        result=dict(v,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        s=v['summary'];lines=['# SI体積速度源・声道・理想バッフル放射の結合','','[SI境界/軸上観測の資格](../nas-volume-velocity-observer-20261009-v1/report.md)を使い、理想体積速度源と16区間声道、flanged受動放射、口元の流れ、1m軸上観測を結合した。元LF積分AC形を全球RMS 3e-5 m³/s・6000Hz帯域・phase .125で固定し、音源/波形ごとの正規化なし。1PaをPCM1とする固定換算。これは総非負気流や肺/渦/非線形声門モデルではない。','',
          '左端の反射+1は体積速度境界から導く。源の仕事Us*psrcと数学的放射loss²/(rho*c)によって、全正規化状態のJ単位収支を検証した。動的形状の共通状態を実移動壁の仕事へ読み替えない。lossは収支専用で音声出力ではない。音声は口元flowから独立資格化した理想軸上音圧を計算する。','',
          f'一様管4半径の解析SI複素伝達、8強制/無強制列、全43波形の独立正規化計算/静的圧力計算/観測と収支を通過。E0 {s["E0_pass"]}/{s["total"]}、pitch {s["pitch_pass"]}/{s["total"]}、欠測{s["missing_support"]}/{s["fixed_support_intervals"]}。全43工学通過={v["engineering_all_required_pass"]}。8連続列の区切り/両stateと未来語句前半のbyte一致、不正17件拒否を保持。','',
          '有限バッフル/頭部/移動口/非一様流/総声門気流/鼻/子音/知覚は未資格。6kHzの固定観測誤差の資格は、全過渡の物理誤差2%を意味しない。旧73/74の不通過や旧係数/gain/径/時刻/ゲートの凍結を保持し、旧候補を再採択しない。','',
          '2000render/3000DSPは内部source/blocks/独立参照/再partitionを含む保守的費用。全自分一時領域を指定外部から回収し、波形は指定外部へ保持。P5未開封・知覚資格なし・品質未達。','',result['next'],''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        snap=b.snapshot();c=snap['campaigns'][NAME];tmp=[x for x in snap['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=snap['seconds']-c['start_seconds'],write_bytes=snap['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        snap=b._load();snap['continuation_checkpoint'].update(id='volume-waveguide-coupling-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(snap)
    b.save(ROOT/'progress-0139.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(summary=s,all_engineering_pass=v['engineering_all_required_pass'],quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();globals()[a.stage]()
