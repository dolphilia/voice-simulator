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

def synthesize(params,settings,method):
    import hashlib
    from scipy import signal
    if method=='native':out,tr=raw(params,settings,'native');calls=1
    elif method=='fir1024':out,tr,unused_native=fir_raw(params,settings);calls=2
    else:raise ValueError('未登録の最小位相比較方式')
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA' if method=='native' else 'MCP-minimum-phase-causal-FIR1024',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,
        periodic_source_delay_samples=0,render_calls_including_internal_MLSA=calls,
        FIR_length=1024 if method=='fir1024' else None,
        interpolation='前frame/current IRの出力時刻crossfade j/240。MLSA b補間とは別表現。' if method=='fir1024' else 'HTS原b係数補間',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
