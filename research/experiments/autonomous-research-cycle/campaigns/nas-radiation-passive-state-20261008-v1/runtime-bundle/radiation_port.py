"""二状態/二出力の等長行列。lossは正規化損失portで、遠方micではない。"""
import ctypes as C,math,json,hashlib
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent;COEF=json.loads((HERE/'coefficients.json').read_text());P=C.POINTER(C.c_double)
_lib=C.CDLL(str(HERE/'radiation_port.dylib'));_matrix=_lib.port_matrix;_matrix.restype=C.c_int;_matrix.argtypes=[C.c_double,C.c_double,C.c_int,P]
_fn=_lib.radiation_port;_fn.restype=C.c_int;_fn.argtypes=[P,P,C.c_size_t,C.c_double,C.c_int,P,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def matrix(fs,radius,flanged):
 if type(flanged) is not bool:raise ValueError('終端はboolのみ')
 out=np.empty((4,3))
 if not _matrix(fs,radius,int(flanged),out.ctypes.data_as(P)):raise ValueError('有限Fs/半径が登録範囲外')
 return out
def block(x,radius,fs,flanged,state=None):
 if type(flanged) is not bool:raise ValueError('終端はboolのみ')
 x=np.ascontiguousarray(x,dtype=float);radius=np.ascontiguousarray(radius,dtype=float);state=np.zeros(2) if state is None else np.ascontiguousarray(state,dtype=float)
 if x.ndim!=1 or radius.shape!=x.shape or state.shape!=(2,) or not 1<=len(x)<=96000:raise ValueError('列/状態寸法が不整合')
 before=(ah(x),ah(radius),ah(state));r=np.empty_like(x);l=np.empty_like(x);energy=np.empty_like(x);last=np.empty_like(state)
 if not _fn(x.ctypes.data_as(P),radius.ctypes.data_as(P),len(x),fs,int(flanged),state.ctypes.data_as(P),last.ctypes.data_as(P),r.ctypes.data_as(P),l.ctypes.data_as(P),energy.ctypes.data_as(P)):raise ValueError('有限入力/状態/半径を拒否')
 assert before==(ah(x),ah(radius),ah(state));return r,l,energy,last
