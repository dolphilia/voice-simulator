"""共有模型のGV有効性を実状態・MLPG内部で照合する。"""
import ctypes as C
from pathlib import Path
import numpy as np
from timing_engine import Engine
_lib=C.CDLL(str(Path(__file__).resolve().parent/'gv.dylib'))
_fn=_lib.gv_status;_fn.restype=C.c_int;_fn.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_size_t]
def status(engine,disabled,parameter_generated=False):
    x=np.empty(12);assert _fn(engine.pointer,x.ctypes.data_as(C.POINTER(C.c_double)),12)
    rows=[]
    for s,name in enumerate(['MCP','LF0','LPF']):
        mean,var,length,weight=x[s*4:s*4+4]
        enabled=name in ['MCP','LF0'] and name not in disabled
        assert bool(mean)==bool(var)==enabled and weight==1.
        assert (length>=0 if parameter_generated else length==-1)
        if parameter_generated:assert (length>0)==enabled
        rows.append(dict(stream=name,GV_mean_present=bool(mean),GV_variance_present=bool(var),
                         GV_length=int(length),GV_weight=float(weight),expected_enabled=enabled))
    return rows
