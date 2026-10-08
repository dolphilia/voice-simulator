"""保存列を使わず、その入力のMCPとHTS励振から因果FIRを計算する。"""
import ctypes as C
from pathlib import Path
import numpy as np
from hts_arrays import ah
from shape_arrays import raw
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);S=C.c_size_t
_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[P,C.c_double,P,S]
_fir=_lib.shape_fir;_fir.restype=C.c_int;_fir.argtypes=[P,P,S,P]
def kernel(mc,alpha=.55):
    a=np.ascontiguousarray(mc,dtype=np.float64);assert a.shape==(35,)
    h=np.empty(1024);assert _kernel(a.ctypes.data_as(P),alpha,h.ctypes.data_as(P),1024)
    return h
def filter_source(mc,source):
    a=np.ascontiguousarray(mc,dtype=np.float64);x=np.ascontiguousarray(source,dtype=np.float64)
    assert a.ndim==2 and a.shape[1]==35 and x.shape==(len(a)*240,) and np.isfinite(x).all()
    before=(ah(a),ah(x));out=np.empty(len(x))
    assert _fir(a.ctypes.data_as(P),x.ctypes.data_as(P),len(a),out.ctypes.data_as(P))
    assert (ah(a),ah(x))==before
    return out
def fir_raw(params,settings):
    # 原MLSA出力も内部で一回生成される。この費用をrenderへ別計上する。
    native,tr=raw(params,settings,'native')
    out=filter_source(params[0],tr['excitation'])
    return out,tr,native
