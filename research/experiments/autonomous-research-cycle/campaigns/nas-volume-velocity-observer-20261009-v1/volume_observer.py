"""面積cm²、正規化波Pa*m、体積速度m³/s、音圧Pa。理想的線形境界。"""
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
