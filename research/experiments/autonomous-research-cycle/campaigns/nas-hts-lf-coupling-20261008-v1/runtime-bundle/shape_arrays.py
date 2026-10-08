"""原時計でLFをLPF前有声成分へ入れる。自然さ/aliasingの資格は別に扱う。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
import lf_source
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,P,P,P,P,U,S]
MODES={'native':0,'lf':1}
COEFF=np.array([0.4, 0.6, 0.05, 19.99327266898377, 1.0502723051897425, 0.5325047916081669, 2.2310779262248825],dtype=np.float64)
def raw(params,settings,method):
 if method not in MODES:raise ValueError('未登録のLF源方式')
 x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
 arrays=[np.empty(n) for _ in range(7)];event=np.empty(n,dtype=np.uint8)
 assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],COEFF.ctypes.data_as(P),*(v.ctypes.data_as(P) for v in arrays),event.ctypes.data_as(U),n)
 out,period,counter,source,noise,periodic,phase=arrays
 assert [ah(v) for v in x]==before and np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
 assert all(np.isfinite(v).all() for v in arrays)
 return out,dict(period=period,counter=counter,excitation=source,noise=noise,periodic=periodic,phase=phase,event=event)
def synthesize(params,settings,method):
 x,tr=raw(params,settings,method);original=tr
 if method!='native':
  _,original=raw(params,settings,'native')
  assert all(np.array_equal(tr[k],original[k]) for k in ('period','counter','event','noise','phase'))
 audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
 env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
 return audio,dict(renderer='原HTS-MLSA/LPF前有声LF',source_method=method,effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
  source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(original['excitation']),processed_excitation_sha256=ah(tr['excitation']),
  noise_sha256=ah(tr['noise']),periodic_sha256=ah(tr['periodic']),LF_phase_sha256=ah(tr['phase']),cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
  original_noise_RNG_LPF_and_source_clock_unchanged=True,sqrt_period_replaced_only_for_LF_voiced_component=method=='lf',
  processed_excitation_intentionally_changed=method!='native',LF_fixed_time_ratios=[.4,.6,.05],LF_continuous_RMS_normalization=True,
  source_phase_rule='元counterに1を足しeventなら元periodを一度引く。その後counter/periodをfmod(.,1)し、period補間更新前にLFを評価。',
  phase_is_frequency_dependent=False,constant_delay_samples_not_defined=True,render_calls_including_internal_MLSA=1 if method=='native' else 2,
  finite_dynamic_zero_area_or_antialiasing_claimed=False,neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
