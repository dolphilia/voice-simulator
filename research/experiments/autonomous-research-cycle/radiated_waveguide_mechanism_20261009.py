"""共有声道と受動放射状態を結合し、LF微分形/積分AC形を全条件で検証する。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from radiation_passive_state_20261008 import C_SOURCE as PORT_C,WORKER as PORT_WORKER
from waveguide_sequence_runtime_20261008 import MODULE as SEQUENCE
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-radiated-waveguide-mechanism-20261009-v1';NAME='radiated-waveguide-mechanism-v1'
PREV=ROOT/'campaigns/nas-radiation-passive-state-20261008-v1'
TUBE=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

C_SOURCE=PORT_C+r'''
/* 声道と放射の共通正規化状態。lossは遠方音圧ではない。 */
int tube_radiated(const double*drive,const double*area,size_t samples,size_t sections,double fs,double rg,const double*initial,double*final,double*out,double*energy){
 if(!drive||!area||!initial||!final||!out||!energy||samples<1||samples>96000||sections<2||sections>44||!isfinite(fs)||fs<16000||fs>96000||!isfinite(rg)||fabs(rg)>=1.)return 0;
 for(size_t j=0;j<2*sections+2;j++)if(!isfinite(initial[j]))return 0;
 for(size_t i=0;i<samples;i++){
  if(!isfinite(drive[i]))return 0;
  for(size_t j=0;j<sections;j++)if(!isfinite(area[i*sections+j])||area[i*sections+j]<.05||area[i*sections+j]>12.)return 0;
  double radius=.01*sqrt(area[i*sections+sections-1]/3.14159265358979323846);
  if(radius<.003||radius>.03)return 0;
 }
 double right[44],left[44],nr[44],nl[44],z0=initial[2*sections],z1=initial[2*sections+1],K[12];
 for(size_t j=0;j<sections;j++){right[j]=initial[j];left[j]=initial[sections+j];}
 for(size_t i=0;i<samples;i++){
  const double*a=area+i*sections;double radius=.01*sqrt(a[sections-1]/3.14159265358979323846);
  if(!port_matrix(fs,radius,0,K))return 0;
  double incident=right[sections-1];double v0=K[0]*z0+K[1]*z1+K[2]*incident,v1=K[3]*z0+K[4]*z1+K[5]*incident;
  nl[sections-1]=K[6]*z0+K[7]*z1+K[8]*incident;out[i]=K[9]*z0+K[10]*z1+K[11]*incident;
  nr[0]=drive[i]+rg*left[0];
  for(size_t j=0;j+1<sections;j++){
   double k=(a[j]-a[j+1])/(a[j]+a[j+1]),t=sqrt(1.-k*k);
   nr[j+1]=t*right[j]-k*left[j+1];nl[j]=k*right[j]+t*left[j+1];
  }
  z0=v0;z1=v1;double E=z0*z0+z1*z1;
  for(size_t j=0;j<sections;j++){right[j]=nr[j];left[j]=nl[j];E+=right[j]*right[j]+left[j]*left[j];}
  energy[i]=E;
 }
 for(size_t j=0;j<sections;j++){final[j]=right[j];final[sections+j]=left[j];}
 final[2*sections]=z0;final[2*sections+1]=z1;return 1;
}
'''

MODULE=SEQUENCE.replace("HERE/'coefficients.json'","HERE/'lf-coefficients.json'").replace("HERE/'waveguide_stream.dylib'","HERE/'radiated_tube.dylib'").replace('_lib.tube_stream','_lib.tube_radiated').replace('s.shape!=(32,)','s.shape!=(34,)').replace('16,.75,-.85,','16,FS,.75,').replace('def controls(request):',"def controls(request,source='derivative'):").replace('def generate(request,partition=(4096,)):',"def generate(request,source='derivative',partition=(4096,)):").replace('x,a,meta=controls(request);state=np.zeros(32)','x,a,meta=controls(request,source);state=np.zeros(34)').replace('for m in range(1,harmonics+1):x+=2*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))',"for m in range(1,harmonics+1):x+=2*np.real(source_coefficient(m,source)*np.exp(2j*np.pi*m*phase))").replace('return x,a,dict(source_f0=f0,','return x,a,dict(source_kind=source,source_f0=f0,')
MODULE=MODULE.replace("P=C.POINTER(C.c_double);S=C.c_size_t",r'''
FLOW=json.loads((HERE/'flow-normalization.json').read_text())
def source_coefficient(m,source):
 if source not in ('derivative','flow'):raise ValueError('駆動は事前固定の二種のみ')
 return coefficient(m) if source=='derivative' else coefficient(m)/(2j*math.pi*m*FLOW['standard_deviation'])
P=C.POINTER(C.c_double);S=C.c_size_t''')
MODULE=MODULE.replace("f0=request['f0'];segments=request['segments']","if source not in ('derivative','flow'):raise ValueError('駆動は事前固定の二種のみ')\n f0=request['f0'];segments=request['segments']")
assert 's.shape!=(34,)' in MODULE and 'state=np.zeros(34)' in MODULE and '16,FS,.75,' in MODULE

NORMALIZER=r'''"""元LFの積分形の平均と分散を解析原始関数/独立積分で固定する。"""
import sys,json,math,cmath
from pathlib import Path
from scipy.integrate import quad
here=Path(sys.argv[1]);tp,te,ta,ep,a,e0,scale=map(float,json.loads((here/'lf-coefficients.json').read_text()));w=math.pi/tp
def g(t):
 opened=lambda u:scale*e0/(a*a+w*w)*(math.exp(a*u)*(a*math.sin(w*u)-w*math.cos(w*u))+w)
 if t<=te:return opened(t)
 v=t-te;return opened(te)-scale/(ep*ta)*((1-math.exp(-ep*v))/ep-math.exp(-ep*(1-te))*v)
def integrate(f):return sum(quad(f,lo,hi,epsabs=2e-12,epsrel=2e-12)[0] for lo,hi in [(0.,te),(te,1.)])
mean=integrate(g);variance=integrate(lambda t:(g(t)-mean)**2);std=math.sqrt(variance);assert abs(g(0))<2e-12 and abs(g(1))<2e-12 and std>0
def coefficient(m):
 omega=2*math.pi*m;length=1-te;z1=complex(a,w-omega);z2=complex(a,-w-omega)
 opened=e0*((cmath.exp(z1*te)-1.)/z1-(cmath.exp(z2*te)-1.)/z2)/(2j)
 returning=-(cmath.exp(-1j*omega*te)*(1.-cmath.exp(-complex(ep,omega)*length))/complex(ep,omega)-math.exp(-ep*length)*(cmath.exp(-1j*omega*te)-cmath.exp(-1j*omega))/(1j*omega))/(ep*ta)
 return scale*(opened+returning)
rows=[]
for m in (1,3,7,30,72):
 ref=complex(integrate(lambda t:(g(t)-mean)/std*math.cos(2*math.pi*m*t)),integrate(lambda t:-(g(t)-mean)/std*math.sin(2*math.pi*m*t)))
 error=abs(ref-coefficient(m)/(2j*math.pi*m*std));assert error<5e-11;rows.append(dict(harmonic=m,error=error))
power=2*sum(abs(coefficient(m)/(2j*math.pi*m*std))**2 for m in range(1,4097));assert abs(power-1)<1e-10
print(json.dumps(dict(mean=mean,variance=variance,standard_deviation=std,mean_removed=True,global_continuous_RMS=1.,per_wave_or_F0_or_truncation_normalization=False,quadrature_rows=rows,parseval_4096_power=power,physical_glottal_volume_velocity=False)))
'''

tree=ast.parse(PORT_WORKER);node=next(v for v in tree.body if isinstance(v,ast.FunctionDef) and v.name=='independent_matrix')
INDEPENDENT=ast.get_source_segment(PORT_WORKER,node).replace("COEF['flanged' if flanged else 'unflanged']","RCOEF['flanged' if flanged else 'unflanged']")
WORKER=r'''"""結合の独立反射/伝達/エネルギーと両固定駆動の全分母を評価する。"""
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
''' + INDEPENDENT + r'''
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
'''

def requests():
    def row(id,kind,letters,ms,f0):return dict(id=id,kind=kind,request=dict(segments=[dict(vowel=v,duration_ms=duration) for v,duration in zip(letters,ms)],f0=f0))
    rows=[row('static-'+v+'-'+str(f),'static',v,[600],f) for v in 'aiueo' for f in (110,220,280)]
    rows += [row('transition-'+v+w,'transition',v+w,[200,400],220) for v in 'aiueo' for w in 'aiueo' if v!=w]
    for id,letters,ms,f in [('single-a','a',600,220),('single-i','i',600,110),('single-u','u',600,280),('all-five','aiueo',250,220),('reverse-five','oeuia',250,280),('long-forward','aiueo'*4,250,220),('long-reverse','oeuia'*4,250,110),('long-alternating','ai'*12,250,280)]:rows.append(row(id,'sequence',letters,[ms]*len(letters),f))
    assert len(rows)==43;return rows
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
    for src in (MODULE,NORMALIZER,WORKER):ast.parse(src)
    limits=dict(seconds=14400,bytes=600000000,write_bytes=1200000000,setup=20,audit=20,render=3000,dsp=6000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='共有16区間声道と可変半径の受動放射stateを結合し、固定LF微分形/積分AC形の両方で独立伝達/受動/因果/区切りと工学全分母を保持できるか。',
      inherited=dict(port_seal=digest(PREV/'artifact-seal.json'),tube_effective_seal=digest(TUBE/'artifact-seal.json'),diameters=digest(TUBE/'runtime-bundle/diameters.json'),LF_coefficients=digest(TUBE/'runtime-bundle/coefficients.json'),radiation_coefficients=digest(PREV/'coefficients.json'),source_cutoff_hz=8000,source_fs=34300,output_fs=24000,glottal_reflection=.75,gain=.10,fade_ms=12),
      factors=['唇定数反射を現在唇半径の共通受動stateへ変更。声道R16/L16と放射2の計34stateを継承。','出力を正規化唇圧力から補完放射loss portへ変更。loss portは実micの位相/位置/指向性ではない。','二駆動を同時固定：旧RMS1 LF微分形と、解析LF原始関数から平均を除いた積分形のAC RMS1。分散は連続形の一回の積分で固定し、F0/波形/帯域打切りで再正規化しない。'],
      fixtures=dict(requests=requests(),sources=['derivative','flow'],uniform_radii_m=[.007,.008,.012,.016],uniform_samples=16384,energy_geometries=['fixed a','i→a ramp','7Hz sine i/a','half-step i/a'],energy_samples=4096,forced_and_unforced=True,initial_random_seed=730910,partitions=[4096,[2048,4096,8192]]),
      gates=dict(independent_normalized_rotation_Cholesky=1e-10,independent_static_pressure_SciPy_DF1=1e-10,uniform_complex_transfer=1e-10,unforced_energy_increase_at_most=2e-10,first_port_delay_samples=16,partition_raw_audio_and_final_state_bytes_exact=True,future_input_area_request_prefix_bytes_exact=True,flow_fourier_quadrature=5e-11,flow_parseval_error=1e-10,invalid_cases=15,E0='元の全evaluate条件',pitch='元DIO/ACF±1半音、confidence≥.6。0.6s条件は元3固定区間、sequenceは各区間[開始+.105s,終了-.01s]。3frame以上/半数以上、欠測全分母。'),
      derivation='tube energy plus common radiation state. Zero drive Eold-Enew=(1-rg^2)*Lold[0]^2+loss^2。Uniform H(z)=T(z)z^-16/(1-rg R(z)z^-32)。LF積分形の非零Fourier係数は元c_m/(2j*pi*m*global_STD)。DC0。',
      scope='独自の正規化受動モデル。源はpower-wave注入であり声門volume velocityの単位/肺圧/流れとの相互作用は資格なし。移動壁の仕事/物理圧力連続/鼻腔/壁損失/子音/遠方mic/知覚資格を主張しない。二駆動の出力を見て係数/径/反射/gainをfitしない。',
      estimates=dict(render=2000,dsp=3000,source_and_internal_blocks_and_independent_reference_included=True,temporary_peak=64000000,temporary_write=128000000,RAM_gb=8,closeout_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),all_old_seals_and_failed_routes_kept=True,protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,
      next='科学42件終了の第7回レビューを先に実施。全機構通過なら二駆動を選別せず、新しい母音語句・原nativeとの内容比較を通常/隔離/CLIと二ASRを含めて別登録する。旧第70コホートや基準を救済せず、新入力の最小支持数を事前固定する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','結合状態/二駆動/全86波と全費用を実出力前固定',size=4000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'requests.json',requests(),j)
        for n,s in [('radiated_tube.c',C_SOURCE),('radiated_sequence.py',MODULE),('normalizer.py',NORMALIZER),('worker.py',WORKER)]:b.write(HERE/n,s.encode(),j)
        b.save(HERE/'lf-coefficients.json',read(TUBE/'runtime-bundle/coefficients.json'),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    b.save(ROOT/'progress-0129.json',dict(active_campaign=NAME,next='登録push→原始関数の一回正規化/build→全結合と二駆動の工学封印→包括レビュー',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()));print('結合受動声道と二駆動を事前登録',flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('source-contract.json')
    with job(b,'setup','結合Cと共有径/元LF/放射係数の固定bundle',size=60000000) as j:
        bundle=HERE/'runtime-bundle';b.write(bundle/'radiated_sequence.py',MODULE.encode(),j)
        for dest,origin in [('diameters.json',TUBE/'runtime-bundle/diameters.json'),('lf-coefficients.json',HERE/'lf-coefficients.json'),('radiation-coefficients.json',PREV/'coefficients.json'),('acoustics.py',TUBE/'runtime-bundle/acoustics.py')]:b.write(bundle/dest,origin.read_bytes(),j)
        b.save(HERE/'measurement-package-contract.json',read(TUBE/'measurement-package-contract.json'),j)
        with b.workspace(j,'結合state C build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'radiated_tube.c'),'-o',str(bundle/'radiated_tube.dylib')]
            with b.external_output(bundle/'radiated_tube.dylib',100000,j):out=execute(cmd,env,120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'radiated_tube.c'),binary_sha256=digest(bundle/'radiated_tube.dylib'),temporary_removed=True),j)
    with job(b,'dsp','連続LF原始関数の平均/分散と独立Fourier/Parseval',count=4,size=40000000) as j:
        with b.workspace(j,'LF積分形の科学依存初期化',16000000,32000000) as (_,env):v=json.loads(execute([str(PYTHON),'-B',str(HERE/'normalizer.py'),str(HERE)],env).stdout)
        b.save(bundle/'flow-normalization.json',v,j);b.save(HERE/'flow-normalization-audit.json',v,j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recording=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_waveforms=True),j)
    print('共有結合stateと両LF駆動を波形出力前固定',flush=True)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract.json')
    with job(b,'render','全結合/両駆動/内部block/独立参照/区切り/未来入力',count=2000,size=160000000,seconds=2200) as r:
        with job(b,'dsp','全工学分母/独立伝達/動的受動/源保存/支持測定',count=3000,size=10000000,seconds=2200) as d:
            with b.workspace(r,'全86結合waveと科学一時領域',64000000,128000000) as (work,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE),str(work)],env,2200)
                except subprocess.CalledProcessError as e:b.save(HERE/'child-failure.json',dict(returncode=e.returncode,stdout=e.stdout,stderr=e.stderr),d);raise
                v=json.loads(out.stdout);assert v['mechanism_passed']
                for row in v['rows']:b.write_data(HERE/'audio'/(row['id']+'-'+row['source']+'.wav'),(work/(row['id']+'-'+row['source']+'.wav')).read_bytes(),d)
                b.save(HERE/'fixture-audit.json',v,d)
    with job(b,'audit','結合限定資格/二駆動全分母/累計費用/一時回収を封印',size=3000000) as j:
        verify('execution-contract.json')
        for previous in (PREV,TUBE):
            for n,h in read(previous/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        result=dict(v,engineering_all_required_pass=all(s['E0_pass']==43 and s['pitch_pass']==43 and s['missing_support']==0 for s in v['summary'].values()),perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 受動放射stateを結合した共有声道と二つのLF駆動','','同じ共有径/元LF係数/phase/源帯域/gainを継承。唇定数反射を共通エネルギーの放射二状態へ変更し、出力は補完loss port。元微分形と、連続積分形から平均を除いたAC RMS1形の両方を出力前固定した。','', '|駆動|E0|pitch|固定支持欠測|','|---|---:|---:|---:|']
        for source,s in v['summary'].items():lines.append(f'|{source}|{s["E0_pass"]}/43|{s["pitch_pass"]}/43|{s["missing_support"]}/{s["fixed_support_intervals"]}|')
        lines += ['', '各駆動は静的15・有向遷移20・連続列8。全結合の独立正規化回転/Cholesky、静的圧力波/DF1、一様管の複素伝達、動的無強制の正規化エネルギー、因果前半、連続列の任意区切り/最終state byte一致、不正15件拒否を通過。元E0/DIO/ACF/支持基準は変更しない。工学不通過も全分母に残す。','',
          '正規化loss portは遠方micではない。源のAC積分形は共有の数学的形状であり実声門volume velocityの単位/肺圧/声道相互作用を表さない。変化する人体壁の仕事、圧力連続、壁損失/鼻腔/子音/日本語知覚の資格なし。原一次近似の範囲とbilinear周波数ずれも継承する。','',
          '2000render/3004DSPは原始関数・源・全内部block・独立参照を含む保守的費用。指定外部の自分一時領域を全回収。二駆動の出力後の係数調整や選別なし。全旧封印/不採択を保持、P5未開封・知覚資格なし・品質未達。','',result['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='radiated-waveguide-mechanism-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0130.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(passed=True,conditions=86,summary=v['summary'],quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();globals()[a.stage]()
