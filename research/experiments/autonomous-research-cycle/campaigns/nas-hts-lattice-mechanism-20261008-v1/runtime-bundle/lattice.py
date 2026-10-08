"""現MCPから自己相関/Yule-Walker係数を計算する。保存波形の推定は使わない。"""
import ctypes as C
import numpy as np
from pathlib import Path
from scipy import signal
from hts_arrays import ah
from shape_arrays import raw
ORDER=34
FFT_LENGTH=16384
_q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
_lib=C.CDLL(str(Path(__file__).resolve().parent/'lattice.dylib'))
P=C.POINTER(C.c_double);S=C.c_size_t
_fn=_lib.lattice_filter;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,P,S,S,S]
def response(mc,alpha=.55):
    x=np.asarray(mc,dtype=np.float64)
    if x.shape!=(35,) or not np.isfinite(x).all() or abs(alpha)>=1.:raise ValueError('有限MCPと安定warpが必要')
    w=(_q-alpha)/(1.-alpha*_q);h=np.exp(np.polynomial.polynomial.polyval(w,x))
    if not np.isfinite(h).all():raise ValueError('MCP応答が非有限')
    return h
def levinson(r):
    x=np.asarray(r,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or len(x)>35 or not np.isfinite(x).all() or x[0]<=0:raise ValueError('正の有限自己相関が必要')
    rr=x/x[0];a=np.zeros(len(x));a[0]=1.;e=1.;k=np.empty(len(x)-1)
    for m in range(1,len(x)):
        v=-(rr[m]+np.dot(a[1:m],rr[m-1:0:-1]))/e
        if not np.isfinite(v) or abs(v)>=.99999999:raise ValueError('射影反射係数が登録安定域外')
        old=a[1:m].copy();a[1:m]=old+v*old[::-1];a[m]=v;k[m-1]=v;e*=1.-v*v
        if not np.isfinite(e) or e<=0:raise ValueError('予測誤差が非正')
    return a,k,float(np.sqrt(e*x[0]))
def project(mc,alpha=.55):
    h=response(mc,alpha);r=np.fft.irfft(np.abs(h)**2,n=FFT_LENGTH)[:ORDER+1].copy()
    a,k,g=levinson(r)
    return a,k,g,r
def polynomial(k):
    a=np.array([1.])
    for v in np.asarray(k,dtype=np.float64):a=np.r_[a,0.]+v*np.r_[0.,a[::-1]]
    return a
def filter_coefficients(k,logg,source):
    p=np.ascontiguousarray(k,dtype=np.float64);g=np.ascontiguousarray(logg,dtype=np.float64);x=np.ascontiguousarray(source,dtype=np.float64)
    if p.ndim!=2 or not 1<=p.shape[1]<=34 or g.shape!=(len(p),) or x.shape!=(len(p)*240,):raise ValueError('lattice列と駆動列の形が不正')
    before=(ah(p),ah(g),ah(x));y=np.empty_like(x)
    if not _fn(p.ctypes.data_as(P),g.ctypes.data_as(P),x.ctypes.data_as(P),y.ctypes.data_as(P),len(p),p.shape[1],len(x)):raise ValueError('lattice生成が登録安定域外または非有限')
    assert before==(ah(p),ah(g),ah(x));return y
def filter_source(mc,source):
    m=np.asarray(mc,dtype=np.float64);before=ah(m)
    projected=[project(c) for c in m];k=np.array([v[1] for v in projected]);g=np.log([v[2] for v in projected])
    y=filter_coefficients(k,g,source);assert ah(m)==before
    return y
def synthesize(params,settings,method):
    if method not in ('native','lattice'):raise ValueError('未登録の全極方式')
    native,tr=raw(params,settings,'native');out=native if method=='native' else filter_source(params[0],tr['original_excitation'])
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='原HTS-MLSA' if method=='native' else 'MCP自己相関→全極lattice',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(tr['original_excitation']),
        processed_excitation_sha256=ah(tr['processed_excitation']),original_excitation_and_processed_excitation_equal=True,
        cycle_events=int(tr['event'].sum()),lattice_order=ORDER if method!='native' else None,
        FFT_length=FFT_LENGTH if method!='native' else None,loading_or_coefficient_clipping=False,
        interpolation='反射係数の算術補間、対数gainの算術補間。前frameからj/240。発話頭state0。',
        extra_delay_samples=0,projection_is_not_exact_MLSA_or_acoustic_truth=True,
        render_calls_including_internal_MLSA=1 if method=='native' else 2,
        neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
