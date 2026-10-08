"""独立再帰・解析応答・tail込みエネルギー・原HTS/源時計を照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'));sys.path.insert(0,sys.argv[1])
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw,phase_filter
from yin_style import estimate
rng=np.random.default_rng(1051051);n=8192;x=np.zeros(n);x[0]=1.;h=phase_filter(x);q=np.exp(-2j*np.pi*np.arange(n//2+1)/n);expected=(q-.95)/(1.-.95*q)
response=np.fft.rfft(h);response_error=float(np.max(np.abs(response-expected)));magnitude_error=float(np.max(np.abs(np.abs(response)-1.)))
assert response_error<=1e-10 and magnitude_error<=1e-10
driving=[]
for mode in ('impulse','noise','step','sine'):
    n=4000
    if mode=='impulse':x=np.zeros(n);x[0]=1.;x[1000]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,n)
    elif mode=='step':x=np.r_[np.zeros(500),np.full(n-500,.1)]
    else:x=.2*np.sin(2*np.pi*220*np.arange(n)/48000.)
    y=phase_filter(x);z=signal.lfilter([-.95,1.],[1.,-.95],x);error=float(np.max(np.abs(y-z)));assert error<=1e-10
    changed=x.copy();changed[2000:]+=1.;future=phase_filter(changed);assert np.array_equal(y[:2000],future[:2000])
    driving.append(dict(mode=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
x=np.r_[rng.normal(0.,.1,2000),np.zeros(8192)];y=phase_filter(x);energy_error=float(abs(np.sum(y*y)-np.sum(x*x))/np.sum(x*x));assert energy_error<=1e-10
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.2;lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)];before=[ah(v) for v in params];expected,_=original(params,settings)
    native,tn=raw(params,settings,'native');changed,tc=raw(params,settings,'allpass')
    assert all(np.array_equal(tn[k],tc[k]) for k in ('period','counter','event','original_excitation'))
    assert np.array_equal(tn['original_excitation'],tn['processed_excitation'])
    independent=signal.lfilter([-.95,1.],[1.,-.95],tc['original_excitation']);error=float(np.max(np.abs(tc['processed_excitation']-independent)));assert error<=1e-10
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before and np.isfinite(changed).all()
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_exact=True,all_input_streams_exact=True,original_excitation_and_clock_exact=True,processed_source_max_abs_error=error,passed=True))
pitch=[]
for hz in (80.,110.,160.,220.,280.,350.,400.):
    t=np.arange(19200)/48000.;x=.2*np.sin(2*np.pi*hz*t);y=phase_filter(x)
    for mode,wave in (('original',x),('allpass',y)):
        audio=signal.resample_poly(wave,1,2);out=estimate(audio[-960:]);error=None if out['hz'] is None else float(12*np.log2(out['hz']/hz))
        assert out['hz'] is not None and abs(error)<=.5
        pitch.append(dict(hz=hz,mode=mode,window_ms=40,steady_last_window=True,error_semitones=error,passed=True))
print(json.dumps(dict(passed=True,response_absolute_error=response_error,magnitude_absolute_error=magnitude_error,tail_included_energy_relative_error=energy_error,
    driving_checks=driving,source_checks=source_checks,pitch_checks=pitch,render=60,dsp=33,
    render_breakdown=dict(response_driver=1,response_filter=1,driving_signals=4,C_driving_filter=4,independent_driving_filter=4,causal_driving_filter=4,energy_driver=1,energy_filter=1,original_HTS=4,native_HTS=4,allpass_HTS=4,sine_driver=7,sine_phase_filter=7,sine_resample=14),
    dsp_breakdown=dict(response=2,driving=8,energy=1,HTS_clock_and_processed_source=8,sine_pitch=14),
    scope='固定LTI機構と登録人工HTS/定常正弦。実日本語/全音素/境界/知覚品質の資格ではない。',quality_certified=False)))
