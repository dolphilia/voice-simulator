"""元pulseと共通4sample遅延下の整数/線形/9tap sinc pulse。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,U,S]
_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[C.c_double,C.c_int,C.c_double,P,S]
MODES={'native':0,'latency':1,'linear':2,'sinc':3}
def kernel(period,remainder,method):
    a=np.empty(9);assert method in ('latency','linear','sinc')
    assert _kernel(period,MODES[method],remainder,a.ctypes.data_as(P),len(a))
    return a
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録のpulse補間')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);phase=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),phase.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before
    assert np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    expected=np.where(event,np.clip(counter+1-period,0,1),0.);expected[np.r_[True,period[:-1]==0]]=0.
    assert np.array_equal(phase,expected)
    return out,dict(period=period,counter=counter,phase=phase,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method)
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA/pulse位置補間',source_method=method,input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        periodic_source_delay_samples=0 if method=='native' else 4,
        phase_definition='有声開始0。他はclip(counter+1-period,0,1)。同4sample遅延でcell内端数を補間。',
        energy_per_cycle='period:LPF前kernelの二乗和。出力/雑音/LPFは固定。',
        waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
