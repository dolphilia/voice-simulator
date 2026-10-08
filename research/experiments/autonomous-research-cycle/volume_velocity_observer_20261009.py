"""体積速度源/口元音圧と流れ/理想バッフルの軸上観測を独立資格化する。"""
import argparse,ast,hashlib,json,os,subprocess,urllib.request
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-volume-velocity-observer-20261009-v1';NAME='volume-velocity-observer-v1'
PREV=ROOT/'campaigns/nas-mri-primary-source-access-20261009-v1'
FAILED=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PDFPY='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3'
POPPLER='/Users/dolphilia/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm'
URLS={'mit-plane.pdf':'https://ocw.mit.edu/courses/6-551j-acoustics-of-speech-and-hearing-fall-2004/7056ab51d5cb75810bf976ee38ac8f30_lec_3_2004.pdf','illinois-piston.pdf':'https://jontalle.web.engr.illinois.edu/uploads/473.F18/Lectures/Chapter_7b.pdf'}

C_SOURCE='''/* 一次の平面波とRayleigh式から独自実装。正規化振幅の単位を明示する。 */
#include <math.h>
#include <stddef.h>
#include <string.h>
static int area_ok(double a){return isfinite(a)&&a>=.05&&a<=12.;}
int volume_boundary(const double*u,const double*left,const double*area,size_t n,double*right,double*pressure){
 if(!u||!left||!area||!right||!pressure||n<1||n>96000)return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(u[i])||fabs(u[i])>.001||!isfinite(left[i])||fabs(left[i])>100.||!area_ok(area[i]))return 0;
 for(size_t i=0;i<n;i++){double root=sqrt(area[i]*1e-4);right[i]=1.2*343.*u[i]/root+left[i];pressure[i]=(right[i]+left[i])/root;}
 return 1;
}
int mouth_units(const double*right,const double*left,const double*area,size_t n,double*pressure,double*volume){
 if(!right||!left||!area||!pressure||!volume||n<1||n>96000)return 0;
 for(size_t i=0;i<n;i++)if(!isfinite(right[i])||fabs(right[i])>100.||!isfinite(left[i])||fabs(left[i])>100.||!area_ok(area[i]))return 0;
 for(size_t i=0;i<n;i++){double root=sqrt(area[i]*1e-4);pressure[i]=(right[i]+left[i])/root;volume[i]=root*(right[i]-left[i])/(1.2*343.);}
 return 1;
}
int axial_observer(const double*u,size_t n,double distance,const double*initial,double*last,double*out){
 if(!u||!initial||!last||!out||n<1||n>96000||!(distance==.5||distance==1.||distance==2.))return 0;
 int delay=(int)(distance*100.),length=delay+8;
 for(size_t i=0;i<n;i++)if(!isfinite(u[i])||fabs(u[i])>.001)return 0;
 for(int i=0;i<length;i++)if(!isfinite(initial[i])||fabs(initial[i])>.001)return 0;
 double history[209],h[9]={0.},coef[4]={4./5.,-1./5.,4./105.,-1./280.};
 for(int j=1;j<=4;j++){h[4-j]=34300.*coef[j-1];h[4+j]=-34300.*coef[j-1];}
 memcpy(history,initial,(size_t)length*sizeof(double));double factor=1.2/(2.*acos(-1.)*distance);
 for(size_t i=0;i<n;i++){
  memmove(history+1,history,(size_t)length*sizeof(double));history[0]=u[i];double sum=0.;
  for(int k=0;k<9;k++)sum+=h[k]*history[delay+k];out[i]=factor*sum;
 }
 memcpy(last,history,(size_t)length*sizeof(double));return 1;
}
'''

MODULE='''"""面積cm²、正規化波Pa*m、体積速度m³/s、音圧Pa。理想的線形境界。"""
import ctypes as C,hashlib,math
from pathlib import Path
import numpy as np
FS=34300.;RHO=1.2;SPEED=343.;P=C.POINTER(C.c_double)
_lib=C.CDLL(str(Path(__file__).with_name('volume_observer.dylib')))
_source=_lib.volume_boundary;_mouth=_lib.mouth_units;_observer=_lib.axial_observer
for f in (_source,_mouth):f.restype=C.c_int;f.argtypes=[P,P,P,C.c_size_t,P,P]
_observer.restype=C.c_int;_observer.argtypes=[P,C.c_size_t,C.c_double,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def arrays(x,y,a):
 x,y,a=[np.ascontiguousarray(v,dtype=float) for v in (x,y,a)]
 if x.ndim!=1 or y.shape!=x.shape or a.shape!=x.shape or not 1<=len(x)<=96000:raise ValueError('列寸法が登録範囲外')
 return x,y,a
def pair(fn,x,y,a):
 x,y,a=arrays(x,y,a);before=(ah(x),ah(y),ah(a));v=np.empty_like(x);w=np.empty_like(x)
 if not fn(x.ctypes.data_as(P),y.ctypes.data_as(P),a.ctypes.data_as(P),len(x),v.ctypes.data_as(P),w.ctypes.data_as(P)):raise ValueError('有限入力/面積を拒否')
 assert before==(ah(x),ah(y),ah(a));return v,w
def source(u,left,area):return pair(_source,u,left,area)
def mouth(right,left,area):return pair(_mouth,right,left,area)
def taps(distance):
 if type(distance) not in (int,float) or distance not in (.5,1.,2.):raise ValueError('観測距離は0.5/1/2m')
 h=np.zeros(9)
 for j,c in enumerate((4/5,-1/5,4/105,-1/280),1):h[4-j]=FS*c;h[4+j]=-FS*c
 return np.r_[np.zeros(int(distance*100)),h]*RHO/(2*np.pi*distance)
def observe(u,distance,state=None):
 taps(distance);u=np.ascontiguousarray(u,dtype=float);length=int(distance*100)+8;state=np.zeros(length) if state is None else np.ascontiguousarray(state,dtype=float)
 if u.ndim!=1 or not 1<=len(u)<=96000 or state.shape!=(length,):raise ValueError('観測入力/履歴寸法が登録範囲外')
 before=(ah(u),ah(state));out=np.empty_like(u);last=np.empty_like(state)
 if not _observer(u.ctypes.data_as(P),len(u),distance,state.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P)):raise ValueError('観測の非有限入力/履歴を拒否')
 assert before==(ah(u),ah(state));return out,last
'''

WORKER='''"""独立圧力波単位式、Rayleigh面積積分、遅延FIRを全固定条件で照合。"""
import sys,json,math,ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal,integrate
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
from volume_observer import source,mouth,observe,taps,FS,RHO,SPEED,P,_source,_mouth,_observer
T=8192;rng=np.random.default_rng(760910);calls=0;unitrows=[];max_u=0.;max_power=0.;max_mouth=0.
curves=[('fixed-'+str(a),np.full(T,a)) for a in (.05,.2,1.,5.,12.)]
curves += [('ramp',np.linspace(.05,12.,T)),('sine',6.025+5.975*np.sin(2*np.pi*7*np.arange(T)/FS)),('step',np.where(np.arange(T)<T//2,.05,12.))]
for name,area in curves:
 prescribed=rng.normal(0,1e-6,T);left=rng.normal(0,.03,T);right,p=source(prescribed,left,area);calls+=1
 A=area*1e-4;Z=RHO*SPEED/A;pp=right/np.sqrt(A);pm=left/np.sqrt(A)
 uref=(pp-pm)/Z;pref=pp+pm;calls+=1
 ue=float(np.max(abs(uref-prescribed)));pe=float(np.max(abs((right*right-left*left)/(RHO*SPEED)-prescribed*p)));assert ue<=5e-19 and pe<=3e-17 and np.max(abs(pref-p))<=3e-13
 max_u=max(max_u,ue);max_power=max(max_power,pe)
 rr=rng.normal(0,.03,T);ll=rng.normal(0,.03,T);mp,mu=mouth(rr,ll,area);calls+=1
 mpr=(rr/np.sqrt(A)+ll/np.sqrt(A));mur=(rr/np.sqrt(A)-ll/np.sqrt(A))/Z;calls+=1
 me=float(np.max(abs(mp-mpr)));assert me<=3e-13 and np.max(abs(mu-mur))<=5e-19
 power=float(np.max(abs(mp*mu-(rr*rr-ll*ll)/(RHO*SPEED))));assert power<=3e-17;max_mouth=max(max_mouth,me)
 unitrows.append(dict(area=name,samples=T,source_flow_error=ue,source_power_error=pe,mouth_pressure_error=me,mouth_power_error=power,passed=True))
# 係数を別の多項式連立方程式から求める。結果へのfitではない。
positions=np.arange(4,-5,-1,dtype=float);V=np.array([positions**m for m in range(9)]);target=np.zeros(9);target[1]=1.;weights=np.linalg.solve(V,target)
registered=taps(1.)[100:]*2*np.pi/RHO/FS;weight_error=float(np.max(abs(weights-registered)));moment_error=float(np.max(abs(V@registered-target)));assert weight_error<=3e-14 and moment_error<=3e-12
freq=np.arange(1,6001,dtype=float);omega=2*np.pi*freq/FS;derivative=2j*FS*sum(c*np.sin(j*omega) for j,c in enumerate((4/5,-1/5,4/105,-1/280),1))
fderivative=1j*2*np.pi*freq;derivative_error=float(np.max(abs(derivative/fderivative-1)));assert derivative_error<=.01
frequencyrows=[];quad_max=0.;relative_max=0.
for distance in (.5,1.,2.):
 H=RHO/(2*np.pi*distance)*derivative*np.exp(-1j*omega*(distance*100+4))
 for radius in (.007,.008,.012,.016):
  delta=radius*radius/(np.sqrt(distance*distance+radius*radius)+distance)
  exact=RHO*SPEED/(np.pi*radius*radius)*np.exp(-1j*2*np.pi*freq*distance/SPEED)*(-np.expm1(-1j*2*np.pi*freq*delta/SPEED))*np.exp(-4j*omega)
  relative=float(np.max(abs(H/exact-1)));assert relative<=.02;relative_max=max(relative_max,relative)
  for f in (1.,110.,220.,1000.,6000.):
   k=2*np.pi*f/SPEED
   def integrand(s):return np.exp(-1j*k*np.sqrt(distance*distance+s*s))*s/np.sqrt(distance*distance+s*s)
   value=integrate.quad(lambda s:float(integrand(s).real),0,radius,epsabs=1e-14)[0]+1j*integrate.quad(lambda s:float(integrand(s).imag),0,radius,epsabs=1e-14)[0]
   independent=1j*2*np.pi*f*RHO/(np.pi*radius*radius)*value
   analytic=RHO*SPEED/(np.pi*radius*radius)*np.exp(-1j*k*distance)*(-np.expm1(-1j*k*delta))
   error=float(abs(independent/analytic-1));assert error<=2e-12;quad_max=max(quad_max,error)
  frequencyrows.append(dict(distance_m=distance,radius_m=radius,frequency_points=6000,max_relative_complex_error=relative,passed=True))
rows=[];max_wave=0.;max_fft=0.
for distance in (.5,1.,2.):
 for name in ('impulse','noise'):
  u=np.zeros(T) if name=='impulse' else rng.normal(0,1e-6,T)
  if name=='impulse':u[0]=1e-6
  p,last=observe(u,distance);calls+=1;ref=signal.lfilter(taps(distance),[1.],u);calls+=1
  direct=np.convolve(u,taps(distance))[:T];calls+=1
  error=max(float(np.max(abs(p-ref))),float(np.max(abs(p-direct))));assert error<=3e-14;max_wave=max(max_wave,error)
  assert np.all(p[:int(distance*100)]==0.)
  if name=='impulse':
   f=np.fft.rfftfreq(T,1/FS);keep=(f>0)&(f<=6000);w=2*np.pi*f[keep]/FS;H=RHO/(2*np.pi*distance)*2j*FS*sum(c*np.sin(j*w) for j,c in enumerate((4/5,-1/5,4/105,-1/280),1))*np.exp(-1j*w*(distance*100+4))
   fe=float(np.max(abs(np.fft.rfft(p)[keep]/1e-6-H)));assert fe<=2e-9;max_fft=max(max_fft,fe)
  future=u.copy();future[T//2:]=1e-5;other=observe(future,distance)[0];calls+=1;assert other[:T//2].tobytes()==p[:T//2].tobytes()
  state=np.zeros(int(distance*100)+8);pieces=[];start=0;j=0
  while start<T:
   stop=min(T,start+(2048,4096,8192)[j%3]);out,state=observe(u[start:stop],distance,state);pieces.append(out);calls+=1;start=stop;j+=1
  assert np.concatenate(pieces).tobytes()==p.tobytes() and state.tobytes()==last.tobytes()
  rows.append(dict(distance_m=distance,signal=name,samples=T,independent_wave_error=error,propagation_samples=int(distance*100),numerical_group_delay_samples=4,partition_and_prefix_exact=True,passed=True))
invalid=0
unitcases=[(np.zeros(0),np.zeros(0),np.zeros(0)),(np.zeros(2),np.zeros(1),np.ones(2)),(np.array([np.nan]),np.zeros(1),np.ones(1)),(np.zeros(1),np.array([np.inf]),np.ones(1)),(np.zeros(1),np.zeros(1),np.array([.049])),(np.zeros(1),np.zeros(1),np.array([12.01])),(np.zeros(1),np.zeros(1),np.array([np.nan])),(np.zeros((2,2)),np.zeros((2,2)),np.ones((2,2))),(np.array([1e308]),np.zeros(1),np.ones(1))]
for fn in (source,mouth):
 for args in unitcases:
  try:fn(*args)
  except ValueError:invalid+=1
  else:raise AssertionError('不正単位境界を受理')
observercases=[(np.zeros(0),1.,None),(np.zeros((2,2)),1.,None),(np.array([np.nan]),1.,None),(np.array([np.inf]),1.,None),(np.zeros(2),.6,None),(np.zeros(2),np.nan,None),(np.zeros(2),1.,np.zeros(5)),(np.zeros(2),1.,np.full(108,np.inf)),(np.array([.002]),1.,None),(np.zeros(2),1.,np.full(108,.002))]
for args in observercases:
 try:observe(*args)
 except ValueError:invalid+=1
 else:raise AssertionError('不正観測入力を受理')
assert invalid==28
z=np.zeros(4);a=np.ones(4);out=np.full(4,123.);v=np.full(4,321.)
for fn in (_source,_mouth):assert not fn(None,z.ctypes.data_as(P),a.ctypes.data_as(P),4,out.ctypes.data_as(P),v.ctypes.data_as(P)) and np.all(out==123.) and np.all(v==321.)
state=np.zeros(108);last=np.full(108,321.)
assert not _observer(None,4,1.,state.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(last==321.) and np.all(out==123.)
assert len(unitrows)==8 and len(frequencyrows)==12 and len(rows)==6 and calls<=192
print(json.dumps(dict(passed=True,unit_rows=unitrows,frequency_rows=frequencyrows,observer_rows=rows,max_source_flow_error=max_u,max_source_power_error=max_power,max_mouth_pressure_error=max_mouth,independent_weights_error=weight_error,polynomial_moments_error=moment_error,max_derivative_relative_error=derivative_error,max_exact_disk_relative_complex_error=relative_max,max_Rayleigh_quadrature_relative_error=quad_max,max_observer_independent_wave_error=max_wave,max_FFT_complex_error=max_fft,actual_render_calls=calls,invalid_cases=invalid+3,pressure_Pa_volume_m3_s_and_power_W_consistent=True,ideal_prescribed_glottal_flow_only=True,infinite_baffle_uniform_disk_axis_only=True,full_human_glottis_or_head_microphone_or_speech_qualified=False)))
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
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];assert not read(PREV/'aggregate-summary.json')['source_available'] and not read(FAILED/'aggregate-summary.json')['adopted']
    for src in (MODULE,WORKER):ast.parse(src)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=20,audit=20,render=600,dsp=4000,ai=0,teacher=0,train=0,inverse=0,download=4000000)
    reg=dict(campaign=NAME,question='正規化波から体積速度源/口元の圧力と流れをSI単位で構成し、理想バッフル円形開口の因果的軸上音圧を独立資格化できるか。数学的lossをmicへ読み替えない。',
      previous_seals=[digest(PREV/'artifact-seal.json'),digest(FAILED/'artifact-seal.json')],MRI_PDF_unavailable_HTML_readable_kept=True,previous_two_sources_not_adopted=True,old_gain_geometry_source_timing_or_gates_rescue_frozen=True,
      primary=dict(URLs=URLS,MIT='Lecture 3, 16-September-2004, page 1 equations 3.2–3.4: plane waves, pressure/particle velocity/intensity',Illinois='Oelze ECE/TAM373 Chapter7, printed pages 14–16 (PDF 1–3): uniform circular piston in infinite rigid baffle, Rayleigh integral and exact axis solution',private_research_source_and_images_external_no_Git_redistribution=True,no_copied_code=True),
      units=dict(area_input='cm^2 -> m^2 *1e-4',normalized_wave='pressure wave *sqrt(area_m^2), Pa*m',density_kg_m3=1.2,speed_m_s=343.,physical_constants_are_predeclared_engineering_not_measured_human=True),
      boundary='Rnew=rho*c*Us/sqrt(Ag)+Lold. Source pressure=(Rnew+Lold)/sqrt(Ag), imposed Us=sqrt(Ag)*(Rnew-Lold)/(rho*c), net W=(Rnew^2-Lold^2)/(rho*c)=Us*pressure. Mouth p=(R+L)/sqrt(Al), U=sqrt(Al)*(R-L)/(rho*c). Ideal volume source has reflection +1, not old .75 source power injection, no lung/Bernoulli/vortex qualification.',
      observer='Uniform infinitely baffled piston, axis distance r. Exact P/U=rho*c/(pi*a^2)*(exp(-j*k*r)-exp(-j*k*sqrt(r^2+a^2))). Far-axis P/U=j*omega*rho/(2*pi*r)*exp(-j*k*r). Independently integrate Rayleigh disk. Do not substitute the unbaffled monopole rho/(4*pi*r) beyond its low-ka scope.',
      discrete=dict(fs=34300,distances_m=[.5,1.,2.],propagation_samples=[50,100,200],derivative='eighth-order centered 9tap, c1=4/5,c2=-1/5,c3=4/105,c4=-1/280; causal extra group delay4, h[4-j]=Fs*cj,h[4+j]=-Fs*cj',state='D+8 most-recent flow history samples',reset_at_each_block=False,no_fractional_delay_fit_or_output_normalization=True),
      fixtures=dict(samples=8192,seed=760910,area_cm2=[.05,.2,1.,5.,12.],dynamic_area=['ramp .05→12','7Hz sine 6.025±5.975','half .05→12'],flow_noise_SD_m3_s=1e-6,left_wave_noise_SD_Pa_m=.03,observer_signals=['impulse 1e-6','noise SD1e-6'],radii_m=[.007,.008,.012,.016],frequency_Hz=dict(first=1,last=6000,step=1),Rayleigh_quadrature_Hz=[1,110,220,1000,6000]),
      gates=dict(source_volume_absolute_error_m3_s=5e-19,power_absolute_error_W=3e-17,pressure_vs_independent_Pa=3e-13,derivative_weights_vs_polynomial_system=3e-14,polynomial_moment_residual=3e-12,discrete_derivative_relative_error=.01,observer_vs_exact_disk_relative_complex_error=.02,Rayleigh_quadrature_relative_error=2e-12,observer_vs_SciPy_lfilter_and_convolution_Pa=3e-14,FFT_vs_analytic_complex=2e-9,partition_and_future_prefix_bytes_exact=True,invalid_rejected=31),
      input_domain=dict(area_cm2=[.05,12.],absolute_volume_m3_s_at_most=.001,absolute_normalized_wave_Pa_m_at_most=100.,observer_history_volume_limit=.001),
      scope='独立した線形SI境界と理想的軸上観測のみ。実人体の頭/移動する開口/非一様流/鼻/閉鎖/声門気流物理/日本語音声や知覚は未資格。6kHzは数値近似範囲の事前選択で旧8kHz波形/ゲートを再判定しない。',
      estimates=dict(render=192,dsp=1400,download=4000000,temporary_peak=24000000,temporary_write=48000000,internal_blocks_and_references_and_closeout_Git_included=True),limits=limits,controller_sha256=digest(Path(__file__)),perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      next='通過時だけ、別契約でSI体積速度LF源と声道を結合し、flanged近似境界/口元flow/この理想観測の整合と非強制エネルギーを検証する。物理SIと数学的正規化lossを混同せず、新しい波形前に源振幅/帯域/バッフル/観測距離/因果を固定する。通過だけで日本語を採択しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','体積速度/音圧の境界と理想軸上観測の全式/単位/条件を出力前固定',size=3000000) as j:
        b.save(HERE/'registration.json',reg,j)
        for n,s in [('volume_observer.c',C_SOURCE),('volume_observer.py',MODULE),('worker.py',WORKER)]:b.write(HERE/n,s.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0136.json',dict(active_campaign=NAME,next='登録push→一次PDFの式を目視・独自C build→SI境界/独立Rayleigh/因果観測の全分母を検証',quality_goal_completed=False,budget=b.reconcile()));print('SI境界と軸上観測を事前登録',flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('source-contract.json')
    with job(b,'download','MIT/Illinois一次講義PDFだけの有限公開取得',4000000,6000000,120) as j:
        for name,url in URLS.items():
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as f:data=f.read(2000001)
            assert len(data)<=2000000 and data.startswith(b'%PDF-');b.write_data(HERE/'upstream'/name,data,j)
        b.save(HERE/'upstream-receipt.json',dict(rows=[dict(name=n,URL=u,sha256=digest(HERE/'upstream'/n),bytes=(HERE/'upstream'/n).stat().st_size) for n,u in URLS.items()],charged_download=4000000,no_audio_or_models=True),j)
    with job(b,'setup','一次平面波/円形開口式の頁確認と独自SI観測C build',size=150000000) as j:
        with b.workspace(j,'一次講義PDF読取と式の目視頁生成',24000000,48000000) as (work,env):
            code="from pypdf import PdfReader;import sys,json; m=PdfReader(sys.argv[1]);i=PdfReader(sys.argv[2]);assert len(m.pages)==12 and 'Lecture 3' in m.pages[0].extract_text() and len(i.pages)==13 and 'Oelze' in i.pages[0].extract_text();print(json.dumps(dict(MIT_pages=12,Illinois_pages=13,identities_passed=True,full_equations_visual_pending=True)))"
            value=json.loads(execute([PDFPY,'-B','-c',code,*[str(HERE/'upstream'/n) for n in URLS]],env,120).stdout)
            for name,page,target in [('mit-plane.pdf',1,'plane-wave'),('illinois-piston.pdf',2,'rayleigh-integral'),('illinois-piston.pdf',3,'exact-axis')]:
                execute([POPPLER,'-f',str(page),'-singlefile','-r','120','-png',str(HERE/'upstream'/name),str(work/target)],env,120);b.write_data(HERE/(target+'.png'),(work/(target+'.png')).read_bytes(),j)
            b.save(HERE/'source-identity-audit.json',value,j)
        bundle=HERE/'runtime-bundle';b.write(bundle/'volume_observer.py',MODULE.encode(),j)
        with b.workspace(j,'独自SI観測C build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk';cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'volume_observer.c'),'-o',str(bundle/'volume_observer.dylib')]
            with b.external_output(bundle/'volume_observer.dylib',100000,j):out=execute(cmd,env,120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'volume_observer.c'),binary_sha256=digest(bundle/'volume_observer.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recording=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract-before-visual.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
    print('平面波1頁/Rayleigh2頁/軸上3頁の3画像を確認後visualを実行',flush=True)
def visual():
    b=Budget();assert not b.snapshot()['jobs'];verify('execution-contract-before-visual.json')
    with job(b,'audit','一次平面波/バッフルRayleigh/軸上解の3頁を目視照合',size=1000000) as j:
        b.save(HERE/'source-visual-audit.json',dict(images={n:digest(HERE/(n+'.png')) for n in ['plane-wave','rayleigh-integral','exact-axis']},plane_p_equals_forward_plus_backward=True,plane_v_equals_difference_over_rho_c=True,uniform_infinite_rigid_baffle_checked=True,Rayleigh_prefactor_j_omega_rho_over_2pi_checked=True,exact_axis_two_retarded_exponentials_checked=True,volume_velocity_is_area_times_uniform_particle_velocity=True,engineering_density_and_sound_speed_not_primary_measurements=True,no_choice_after_output=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_science=True),j)
def fixture():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify('execution-contract.json')
    with job(b,'render','SI源/口元と遅延観測の全入力/参照/前半/区切り',192,90000000,1200) as r:
        with job(b,'dsp','SI境界/9tap/全72000複素点/Rayleigh積分/因果の独立監査',1400,3000000,1200) as d:
            with b.workspace(r,'体積速度と理想観測の科学依存初期化',16000000,32000000) as (_,env):
                try:out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(HERE)],env,1000)
                except subprocess.CalledProcessError as e:b.save(HERE/'child-failure.json',dict(returncode=e.returncode,stdout=e.stdout,stderr=e.stderr),d);raise
            value=json.loads(out.stdout);assert value['passed'];b.save(HERE/'fixture-audit.json',value,d)
    with job(b,'audit','SI境界と理想軸上観測の限定資格/全分母/費用/回収を封印',size=2000000) as j:
        verify('execution-contract.json')
        for prev in (PREV,FAILED):
            for n,h in read(prev/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
        result=dict(value,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 体積速度境界と理想バッフルの軸上音圧','','[MIT平面波講義](https://ocw.mit.edu/courses/6-551j-acoustics-of-speech-and-hearing-fall-2004/7056ab51d5cb75810bf976ee38ac8f30_lec_3_2004.pdf)のp/v関係から、面積cm²→m²と正規化波Pa*mを明示して、体積速度m³/s/音圧Pa/境界仕事Wを独自に導いた。理想的な体積速度源の反射は+1。肺圧や声門のBernoulli/渦/非線形気流を計算した資格ではない。','',
          '[Illinois円形ピストン講義](https://jontalle.web.engr.illinois.edu/uploads/473.F18/Lectures/Chapter_7b.pdf)の一様速度/無限剛体バッフル/Rayleigh面積積分/軸上厳密解を目視確認した。軸上遠方近似のrho/(2pi*r)微分と伝搬を、Fs34300・距離0.5/1/2m・遅延50/100/200標本、8次精度9tap微分の追加4標本で因果実装した。自由空間の小ka単極子や数学的loss portと混同しない。','',
          f'面積8列、観測6信号、12半径/距離×各6000固定複素点、60の独立Rayleigh積分を通過。体積速度誤差 {value["max_source_flow_error"]:.3g} m³/s、源の仕事誤差 {value["max_source_power_error"]:.3g} W、9tap微分相対誤差 {value["max_derivative_relative_error"]:.3g}、厳密円形開口に対する相対複素誤差最大 {value["max_exact_disk_relative_complex_error"]:.3g}。独立lfilter/畳み込み、区切りと因果前半byte一致、不正31件拒否が通過。','',
          '6kHz/半径7〜16mm/軸上0.5〜2mの限定観測。有限の人間の頭、動く開口、非一様流、鼻、閉鎖、日本語音声や知覚は未資格。rho=1.2/c=343は出力前の工学定数で人間の計測真値ではない。旧8kHz・語句コホート・係数/gain・ゲートを救済しない。','',
          '192render/1400DSP/4M取得を返金せず、原PDF/頁画像は指定外部へ私的参照として保存してGit再配布しない。全自分一時領域を回収。旧MRIのHTTP403/公開HTML、二駆動不採択、全旧封印を保持。P5未開封・品質未達。','',result['next'],''];b.write(HERE/'report.md','\n'.join(lines).encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='volume-velocity-observer-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0137.json',dict(latest_completed=NAME,next=result['next'],review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()));print(dict(passed=True,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','visual','fixture']);a=p.parse_args();globals()[a.stage]()
