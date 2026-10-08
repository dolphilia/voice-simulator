"""独立圧力波単位式、Rayleigh面積積分、遅延FIRを全固定条件で照合。"""
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
