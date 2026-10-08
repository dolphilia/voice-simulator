"""同一HTSパラメータを固定pulse源または開閉流量微分源で生成する。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,U,S]
_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[C.c_double,P,S]
def kernel(period):
    a=np.empty(int(np.ceil(.56*period))+1)
    assert _kernel(period,a.ctypes.data_as(P),len(a))
    return a
def raw(params,settings,method):
    if method not in ('native','rosenberg'):raise ValueError('未登録の周期源')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],int(method=='rosenberg'),out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before
    assert np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    return out,dict(period=period,counter=counter,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method)
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA/周期源形状',source_method=method,input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        opening_fraction=.40,closing_fraction=.16,energy_per_cycle='period:フィルタ前の離散kernel二乗和',
        output_gain_or_LPF_not_adjusted=True,saved_waveform_analysis_used=False,
        neural_model=False,utterance_lookup=False)
