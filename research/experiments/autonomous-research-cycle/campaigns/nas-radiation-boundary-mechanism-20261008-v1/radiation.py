"""固定半径の反射、唇位置pressure/flow。遠方放射音の資格ではない。"""
import ctypes as C,json,hashlib,math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
COEFFICIENTS=json.loads((HERE/'coefficients.json').read_text());P=C.POINTER(C.c_double)
_lib=C.CDLL(str(HERE/'radiation.dylib'));_fn=_lib.radiation
_fn.restype=C.c_int;_fn.argtypes=[P,C.c_size_t,C.c_double,C.c_double,C.c_int,P,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def coefficients(fs,radius,flanged):
 if type(flanged) is not bool or not math.isfinite(fs) or not 16000<=fs<=96000 or not math.isfinite(radius) or not .003<=radius<=.03:raise ValueError('登録した有限Fs/半径/終端が必要')
 n1,d1,d2=COEFFICIENTS['flanged' if flanged else 'unflanged'];q=2.*fs*radius/343.;d=1+d1*q+d2*q*q
 return np.array([-(1+n1*q),-2.,-(1-n1*q)])/d,np.array([1.,(2-2*d2*q*q)/d,(1-d1*q+d2*q*q)/d])
def block(x,fs,radius,flanged,state=None):
 coefficients(fs,radius,flanged);x=np.ascontiguousarray(x,dtype=np.float64);state=np.zeros(4) if state is None else np.ascontiguousarray(state,dtype=np.float64)
 if x.ndim!=1 or not 1<=len(x)<=96000 or state.shape!=(4,):raise ValueError('標本/状態寸法が登録範囲外')
 before=(ah(x),ah(state));y=np.empty_like(x);p=np.empty_like(x);u=np.empty_like(x);last=np.empty_like(state)
 if not _fn(x.ctypes.data_as(P),len(x),fs,radius,int(flanged),state.ctypes.data_as(P),last.ctypes.data_as(P),y.ctypes.data_as(P),p.ctypes.data_as(P),u.ctypes.data_as(P)):raise ValueError('非有限入力を拒否')
 assert before==(ah(x),ah(state));return y,p,u,last
