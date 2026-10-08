"""MCP→有限gridの最小位相IR。現入力から計算し、保存軌跡は読まない。"""
import hashlib
import numpy as np
from scipy import signal
from hts_arrays import ah
from shape_arrays import raw
IR_LENGTH=2048
FFT_LENGTH=16384
_q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
def kernel(mc,alpha=.55):
    x=np.asarray(mc,dtype=np.float64);assert x.shape==(35,) and np.isfinite(x).all() and abs(alpha)<1.
    a=(_q-alpha)/(1.-alpha*_q)
    target=np.exp(np.polynomial.polynomial.polyval(a,x))
    h=np.fft.irfft(target,n=FFT_LENGTH)[:IR_LENGTH].copy()
    assert np.isfinite(h).all()
    return h
def filter_source(mc,source):
    m=np.asarray(mc,dtype=np.float64);x=np.asarray(source,dtype=np.float64)
    assert m.ndim==2 and m.shape[1]==35 and x.shape==(len(m)*240,) and np.isfinite(x).all()
    before=(ah(m),ah(x));y=np.empty(len(x));previous=kernel(m[0]);u=np.arange(240)/240.
    for frame,c in enumerate(m):
        current=kernel(c);start=frame*240;stop=start+240
        left=max(0,start-IR_LENGTH+1);past=x[left:stop]
        if start<IR_LENGTH-1:past=np.pad(past,(IR_LENGTH-1-start,0))
        assert len(past)==IR_LENGTH-1+240
        windows=np.lib.stride_tricks.sliding_window_view(past,IR_LENGTH)[:,::-1]
        # 各行はその出力時刻以前だけを参照。FFT convolutionのblock漏れを使わない。
        a=windows@previous;b=windows@current;y[start:stop]=a+u*(b-a)
        previous=current
    assert before==(ah(m),ah(x)) and np.isfinite(y).all()
    return y
def synthesize(params,settings,method):
    if method not in ('native','fft_fir'):raise ValueError('未登録のFFT FIR方式')
    native,tr=raw(params,settings,'native')
    out=native if method=='native' else filter_source(params[0],tr['excitation'])
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA' if method=='native' else 'MCP-FFT-causal-FIR',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},cycle_events=int(tr['event'].sum()),
        cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,periodic_source_delay_samples=0,
        render_calls_including_internal_MLSA=1 if method=='native' else 2,FIR_length=IR_LENGTH if method=='fft_fir' else None,
        FFT_length=FFT_LENGTH if method=='fft_fir' else None,IR_interpolation='前frame/current IRの出力crossfade j/240',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
