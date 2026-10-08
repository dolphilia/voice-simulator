"""等長行列と固定伝達を別計算し、時間変化下の正規化エネルギーを検証する。"""
import sys,json,math
from pathlib import Path
import numpy as np
from scipy import signal
here=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
from radiation_port import matrix,block,COEF,_fn,P
def independent_matrix(fs,radius,flanged):
 n,d,e=COEF['flanged' if flanged else 'unflanged'];delta=d*d-2*e-n*n;root=np.sqrt(delta)
 metric=np.array([[d-n,e],[e,e*(d-root)]]);U=np.linalg.cholesky(metric).T;V=np.linalg.inv(U)
 A=U@np.array([[0.,1.],[-1/e,-d/e]])@V;B=U@np.array([0.,1/e]);C=np.array([[-1.,-n],[-1.,root-d]])@V
 h=343/(2*fs*radius);inv=np.linalg.inv(np.eye(2)-h*A)
 return np.vstack([np.column_stack([inv@(np.eye(2)+h*A),np.sqrt(2*h)*inv@B]),np.column_stack([np.sqrt(2*h)*C@inv,np.array([0.,1.])+h*C@inv@B])])
grid=[];max_matrix=0.;max_isometry=0.
for fs in (34300.,48000.):
 for flanged in (False,True):
  for radius in np.linspace(.003,.03,129):
   K=matrix(fs,float(radius),flanged);ref=independent_matrix(fs,float(radius),flanged);err=float(np.max(abs(K-ref)));iso=float(np.max(abs(K.T@K-np.eye(3))));assert err<=3e-12 and iso<=3e-12
   max_matrix=max(max_matrix,err);max_isometry=max(max_isometry,iso)
  grid.append(dict(fs=fs,flanged=flanged,points=129))
T=8192;rng=np.random.default_rng(720810);rows=[];calls=0
for fs in (34300.,48000.):
 for flanged in (False,True):
  n,d,e=COEF['flanged' if flanged else 'unflanged'];tau=None;delta=d*d-2*e-n*n
  for radius in (.007,.008,.012,.016):
   tau=radius/343.;den=[e*tau*tau,d*tau,1.];br,ar=signal.bilinear([-n*tau,-1.],den,fs);bl,al=signal.bilinear([e*tau*tau,np.sqrt(delta)*tau,0.],den,fs)
   for name in ('impulse','noise'):
    x=np.zeros(T) if name=='impulse' else rng.normal(0,.1,T)
    if name=='impulse':x[0]=1.
    radius_values=np.full(T,radius);r,l,E,last=block(x,radius_values,fs,flanged);calls+=1
    rr=signal.lfilter(br,ar,x);ll=signal.lfilter(bl,al,x);calls+=2
    error=max(float(np.max(abs(r-rr))),float(np.max(abs(l-ll))));assert error<=3e-13
    balance=float(np.max(abs(E+np.cumsum(r*r+l*l)-np.cumsum(x*x))));assert balance<=2e-11
    state=np.zeros(2);pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,w,_,state=block(x[start:stop],radius_values[start:stop],fs,flanged,state);pieces.append(np.column_stack([z,w]));calls+=1;start=stop;k+=1
    assert np.concatenate(pieces).tobytes()==np.column_stack([r,l]).tobytes() and state.tobytes()==last.tobytes()
    rows.append(dict(kind='fixed',fs=fs,radius_m=radius,flanged=flanged,signal=name,independent_transfer_error=error,cumulative_energy_error=balance,passed=True))
  t=np.arange(T)/fs
  curves=[('ramp',np.linspace(.007,.016,T)),('sine',.0115+.0045*np.sin(2*np.pi*7*t)),('step',np.where(np.arange(T)<T//2,.016,.007))]
  for name,radius_values in curves:
   matrices=np.stack([independent_matrix(fs,float(v),flanged) for v in radius_values])
   for forced in (False,True):
    x=rng.normal(0,.1,T) if forced else np.zeros(T);initial=np.array([.7,-.4]);r,l,E,last=block(x,radius_values,fs,flanged,initial);calls+=1
    refstate=initial.copy();ref=np.empty((T,2))
    for i,K in enumerate(matrices):
     out=K@np.r_[refstate,x[i]];refstate=out[:2];ref[i]=out[2:]
    calls+=1;error=float(np.max(abs(np.column_stack([r,l])-ref)));assert error<=3e-13 and float(np.max(abs(refstate-last)))<=3e-13
    balance=float(np.max(abs(E+np.cumsum(r*r+l*l)-np.cumsum(x*x)-initial@initial)));assert balance<=2e-11
    if not forced:assert np.max(np.diff(np.r_[initial@initial,E]))<=3e-12
    future_r=radius_values.copy();future_r[T//2:]=.003;future_x=x.copy();future_x[T//2:]=.3;future=block(future_x,future_r,fs,flanged,initial);calls+=1
    assert future[0][:T//2].tobytes()==r[:T//2].tobytes() and future[1][:T//2].tobytes()==l[:T//2].tobytes()
    state=initial.copy();pieces=[];start=0;k=0
    while start<T:
     stop=min(T,start+(2048,4096,8192)[k%3]);z,w,_,state=block(x[start:stop],radius_values[start:stop],fs,flanged,state);pieces.append(np.column_stack([z,w]));calls+=1;start=stop;k+=1
    assert np.concatenate(pieces).tobytes()==np.column_stack([r,l]).tobytes() and state.tobytes()==last.tobytes()
    rows.append(dict(kind='dynamic',fs=fs,flanged=flanged,radius_curve=name,forced=forced,independent_state_error=error,cumulative_energy_error=balance,unforced_monotone=not forced,passed=True))
invalid=0
cases=[(np.zeros(0),np.zeros(0),34300.,False,None),(np.zeros(3),np.zeros(2),34300.,False,None),(np.array([np.nan]),np.array([.007]),34300.,False,None),(np.zeros(1),np.array([np.inf]),34300.,False,None),(np.zeros(1),np.array([.002]),34300.,False,None),(np.zeros(1),np.array([.031]),34300.,False,None),(np.zeros(1),np.array([.007]),np.nan,False,None),(np.zeros(1),np.array([.007]),1000.,False,None),(np.zeros(1),np.array([.007]),34300.,2,None),(np.zeros(1),np.array([.007]),34300.,False,np.zeros(3)),(np.zeros(1),np.array([.007]),34300.,False,np.array([np.nan,0.]))]
for args in cases:
 try:block(*args)
 except ValueError:invalid+=1
 else:raise AssertionError('不正入力を受理')
assert invalid==11
initial=np.zeros(2);last=np.full(2,321.);out=np.full(4,123.);radii=np.full(4,.007)
assert not _fn(None,radii.ctypes.data_as(P),4,34300.,0,initial.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P),out.ctypes.data_as(P)) and np.all(out==123.) and np.all(last==321.)
assert len(rows)==56 and calls<=450
print(json.dumps(dict(passed=True,rows=rows,matrix_grid=grid,grid_points=516,max_independent_matrix_error=max_matrix,max_isometry_error=max_isometry,actual_render_calls=calls,invalid_cases=invalid+1,fixed_transfer_matches_previous_Pade=True,dynamic_normalized_energy_passive=True,partition_and_future_prefix_exact=True,loss_port_is_not_far_field_microphone=True,moving_wall_physical_work_qualified=False)))
