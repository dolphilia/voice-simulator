"""SciPyの別式/状態空間と反射の独自Cを全条件で照合する。"""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy import signal
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
from radiation import block,coefficients,COEFFICIENTS,ah,_fn,P
import ctypes as C
rows=[];calls=0;T=8192;rng=np.random.default_rng(710810)
for fs in (34300.,48000.):
 for radius in (.007,.008,.012,.016):
  for flanged in (False,True):
   n1,d1,d2=COEFFICIENTS['flanged' if flanged else 'unflanged'];tau=radius/343.
   b,a=coefficients(fs,radius,flanged);sb,sa=signal.bilinear([-n1*tau,-1.],[d2*tau*tau,d1*tau,1.],fs)
   coefficient_error=max(float(np.max(abs(sb-b))),float(np.max(abs(sa-a))));assert coefficient_error<=1e-14
   poles=np.roots(a);assert max(abs(poles))<1.
   delta=d1*d1-2*d2-n1*n1;assert delta>0 and d1>0 and d2>0
   impulse=np.zeros(T);impulse[0]=1.;noise=rng.normal(0,.1,T)
   for name,x in [('impulse',impulse),('noise',noise)]:
    y,p,u,last=block(x,fs,radius,flanged);calls+=1
    ref=signal.lfilter(sb,sa,x);calls+=1;error=float(np.max(abs(y-ref)));assert error<=3e-14
    assert np.array_equal(p,x+y) and np.array_equal(u,x-y)
    passive=float(np.max(np.cumsum(y*y)-np.cumsum(x*x)));assert passive<=1e-10
    prefix=x.copy();prefix[T//2:]=rng.normal(0,.1,T//2);future=block(prefix,fs,radius,flanged)[0];calls+=1;assert future[:T//2].tobytes()==y[:T//2].tobytes()
    state=np.zeros(4);pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,_,_,state=block(x[start:stop],fs,radius,flanged,state);pieces.append(z);start=stop;k+=1;calls+=1
    assert np.concatenate(pieces).tobytes()==y.tobytes() and state.tobytes()==last.tobytes()
    if name=='impulse':
     spectrum=np.fft.rfft(y);omega=2*np.pi*np.arange(1,T//2)/T;s=2j*fs*tau*np.tan(omega/2)
     expected=-(1+n1*s)/(1+d1*s+d2*s*s);frequency_error=float(np.max(abs(spectrum[1:-1]-expected)));assert frequency_error<=3e-12
     assert abs(spectrum[0]+1.)<=1e-12 and abs(spectrum[-1])<=1e-12 and max(abs(expected))<=1+1e-12
     low=1e-4;R=-(1+n1*1j*low)/(1+d1*1j*low+d2*(1j*low)**2)
     eta=(d1-n1)/2.;beta=delta/2.;assert abs(-np.angle(-R)/(2*low)-eta)<=1e-7
     rows.append(dict(fs=fs,radius_m=radius,flanged=flanged,coefficient_error=coefficient_error,max_pole_radius=float(max(abs(poles))),independent_wave_error=error,frequency_error=frequency_error,passivity_margin=passive,eta_from_rounded_table=eta,beta_from_rounded_table=beta,
         ka_paper_8percent_claim_at_most=2.,maximum_warped_ka_8khz=float(2*fs*tau*np.tan(np.pi*8000/fs)),physical_frequency_warp_qualified_as_exact=False,passed=True))
invalid=0
for x,fs,radius,flanged,state in [(np.zeros(0),34300.,.007,False,None),(np.zeros((2,2)),34300.,.007,False,None),(np.array([np.nan]),34300.,.007,False,None),(np.array([np.inf]),34300.,.007,False,None),(np.zeros(4),np.nan,.007,False,None),(np.zeros(4),1000.,.007,False,None),(np.zeros(4),34300.,0.,False,None),(np.zeros(4),34300.,.1,False,None),(np.zeros(4),34300.,.007,2,None),(np.zeros(4),34300.,.007,False,np.zeros(3)),(np.zeros(4),34300.,.007,False,np.array([0.,0.,np.nan,0.]))]:
 try:block(x,fs,radius,flanged,state)
 except ValueError:invalid+=1
 else:raise AssertionError('不正入力を受理')
assert invalid==11
zero=np.zeros(4);out=np.full(4,123.);state=np.zeros(4);last=np.full(4,321.)
assert not _fn(None,4,34300.,.007,0,state.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(out==123.) and np.all(last==321.)
assert len(rows)==16 and calls<=224
print(json.dumps(dict(rows=rows,passed=True,actual_render_calls=calls,invalid_cases=invalid+1,reflection_state_partition_and_future_prefix_exact=True,pressure_and_normalized_flow_identity_exact=True,fixed_radius_only=True,far_field_or_dynamic_lip_or_speech_qualified=False)))
