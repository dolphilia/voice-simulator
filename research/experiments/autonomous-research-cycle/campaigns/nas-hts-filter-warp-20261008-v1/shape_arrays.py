"""共有MCPと原励振を保ち、実フィルタalphaだけを変更する入口。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,U,S]
_mc2b=_lib.shape_mc2b;_mc2b.restype=C.c_int;_mc2b.argtypes=[P,C.c_double,P,S]
MODES={'native':0,'alpha_low':1,'alpha_high':2}
ALPHA={'native':.55,'alpha_low':.50,'alpha_high':.60}
def mc2b(mc,alpha):
    x=np.ascontiguousarray(mc,dtype=np.float64);assert x.shape==(35,)
    b=np.empty(35);assert _mc2b(x.ctypes.data_as(P),alpha,b.ctypes.data_as(P),35)
    return b
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録の周波数軸設定')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);source=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),source.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before
    assert np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    return out,dict(period=period,counter=counter,excitation=source,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method)
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA/周波数軸の独立因子',filter_method=method,effective_filter_alpha=ALPHA[method],model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        original_excitation_noise_LPF_and_gain_unchanged=True,periodic_source_delay_samples=0,
        frequency_axis_rule='MCP35を変換せず、同じalphaをmc2bとMLSAへ渡す。周波数一様倍率/物理声道長ではない。',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
