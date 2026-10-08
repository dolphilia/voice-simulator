"""原励振の振幅応答を保つ固定位相処理。自然発声のモデルとは呼ばない。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,P,U,S]
_phase=_lib.phase_filter;_phase.restype=C.c_int;_phase.argtypes=[P,P,S]
MODES={'native':0,'allpass':1}
def phase_filter(x):
    a=np.ascontiguousarray(x,dtype=np.float64);out=np.empty_like(a);before=ah(a);assert a.ndim==1
    assert _phase(a.ctypes.data_as(P),out.ctypes.data_as(P),len(a));assert ah(a)==before;return out
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録のオールパス源方式')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);source=np.empty(n);processed=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),source.ctypes.data_as(P),processed.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before and np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    if method=='native':assert np.array_equal(source,processed)
    return out,dict(period=period,counter=counter,original_excitation=source,processed_excitation=processed,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method);audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='原HTS-MLSA/LPF後オールパス',source_method=method,effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(tr['original_excitation']),processed_excitation_sha256=ah(tr['processed_excitation']),
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,original_noise_RNG_LPF_and_sqrt_period_unchanged=True,
        processed_excitation_intentionally_changed=method!='native',source_allpass_pole=.95 if method=='allpass' else None,
        source_phase_rule='y[n]=.95*y[n-1]+x[n-1]-.95*x[n]。発話頭で状態0、全LPF後励振を一度だけ処理。',
        phase_is_frequency_dependent=True,constant_delay_samples_not_defined=True,render_calls_including_internal_MLSA=1,
        infinite_LTI_magnitude_unity_is_not_finite_wave_energy_truth=True,neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
