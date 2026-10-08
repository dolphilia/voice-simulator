"""固定Tp=.4/Te=.6/Ta=.05/Ee=1のLF。連続時間の二乗積分で源の尺度を固定する。"""
import math,ctypes as C
from pathlib import Path
import numpy as np
TP=.4;TE=.6;TA=.05;EE=1.
def bisect(fn,lo,hi):
 f=fn(lo);h=fn(hi)
 if not math.isfinite(f+h) or f*h>=0:raise ValueError('正根の事前区間が成立しない')
 for _ in range(160):
  mid=(lo+hi)/2.;v=fn(mid)
  if v==0:return mid
  if f*v>0:lo=mid;f=v
  else:hi=mid
 return (lo+hi)/2.
def coefficients():
 length=1.-TE;w=math.pi/TP
 ep=bisect(lambda e:-math.expm1(-e*length)-e*TA,1e-8,1./TA)
 end=math.exp(-ep*length)
 returning=-((-math.expm1(-ep*length))/ep-length*end)/(ep*TA)
 def opened(a):
  e0=-EE/(math.exp(a*TE)*math.sin(w*TE))
  return e0*(math.exp(a*TE)*(a*math.sin(w*TE)-w*math.cos(w*TE))+w)/(a*a+w*w)
 alpha=bisect(lambda a:opened(a)+returning,0.,10.)
 e0=-EE/(math.exp(alpha*TE)*math.sin(w*TE))
 z=complex(2.*alpha,2.*w)
 first=(math.expm1(2.*alpha*TE)/(2.*alpha)-((__import__('cmath').exp(z*TE)-1.)/z).real)*e0*e0/2.
 second=((-math.expm1(-2.*ep*length))/(2.*ep)-2.*end*(-math.expm1(-ep*length))/ep+end*end*length)/(ep*TA)**2
 power=first+second
 if not power>0 or not math.isfinite(power):raise ValueError('LF周期powerが正の有限値でない')
 return np.array([TP,TE,TA,ep,alpha,e0,1./math.sqrt(power)]),dict(return_equation_residual=-math.expm1(-ep*length)-ep*TA,
  open_integral=opened(alpha),return_integral=returning,net_integral=opened(alpha)+returning,continuous_power=power,source_RMS_normalization='連続周期の解析二乗積分、全入力で固定。波形別gainではない。')
def scalar(t,c):
 tp,te,ta,ep,a,e0,scale=map(float,c)
 if not math.isfinite(t) or not 0.<=t<=1.:raise ValueError('phaseが有限0..1でない')
 return scale*(e0*math.exp(a*t)*math.sin(math.pi*t/tp) if t<=te else -(math.exp(-ep*(t-te))-math.exp(-ep*(1.-te)))/(ep*ta))
_lib=C.CDLL(str(Path(__file__).resolve().parent/'lf_source.dylib'));_fn=_lib.lf_evaluate
P=C.POINTER(C.c_double);_fn.restype=C.c_int;_fn.argtypes=[P,P,C.c_size_t,P,C.c_size_t]
def evaluate(phase,c):
 p=np.ascontiguousarray(phase,dtype=np.float64);v=np.ascontiguousarray(c,dtype=np.float64)
 if p.ndim!=1 or not len(p) or v.shape!=(7,):raise ValueError('phase列と7係数が必要')
 before=(p.tobytes(),v.tobytes());out=np.empty_like(p)
 if not _fn(p.ctypes.data_as(P),out.ctypes.data_as(P),len(p),v.ctypes.data_as(P),len(v)):raise ValueError('LF入力または有限出力を内部検査が拒否')
 assert before==(p.tobytes(),v.tobytes());return out
def tests(c):
 assert not _fn(None,None,0,None,0)
 for p in (np.array([np.nan]),np.array([np.inf]),np.array([-.01]),np.array([1.01])):
  try:evaluate(p,c)
  except ValueError:pass
  else:raise AssertionError('不正phaseを拒否しない')
 return dict(null_and_four_invalid_phases_rejected=True)
