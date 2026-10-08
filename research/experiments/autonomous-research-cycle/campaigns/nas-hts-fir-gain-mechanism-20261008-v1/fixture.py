"""固定人工条件で利得式・独立畳み込み・過去参照・原HTSを照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from minphase import kernel as old_C_kernel
from fft_fir import kernel,filter_source,log_gain,IR_LENGTH,FFT_LENGTH
rng=np.random.default_rng(1047047);mc=np.zeros((8,35));mc[:,0]=np.linspace(0.,1.,8)
mc[1,1]=.3;mc[2,2]=-.25;mc[3,1:4]=[.35,.15,.12];mc[4:,1:]=rng.normal(0.,.04,(4,34))*np.exp(-np.arange(1,35)/12.)
spectral=[]
for i,c in enumerate(mc):
 for alpha in (0.,.55):
    h=kernel(c,alpha);ref=old_C_kernel(c,alpha);b0=sum(float(v)*(-alpha)**j for j,v in enumerate(c))
    error=float(np.max(np.abs(h[:1024]-ref))/max(float(np.max(np.abs(ref))),1e-12))
    gain_error=abs(log_gain(c,alpha)-b0);assert error<=1e-10 and gain_error<=1e-12
    spectral.append(dict(case=i,alpha=alpha,C_prefix_relative_error=error,independent_b0_error=gain_error,passed=True))
def independent(mc,x,mode):
    h=[kernel(c) for c in mc];g=[sum(float(v)*(-.55)**j for j,v in enumerate(c)) for c in mc];out=np.empty(len(x));u=np.arange(240)/240.
    for frame,current in enumerate(h):
        previous=h[max(0,frame-1)];gp=g[max(0,frame-1)];gc=g[frame];start=frame*240;stop=start+240
        if mode=='linear':
            a=signal.convolve(x,previous,method='direct')[start:stop];b=signal.convolve(x,current,method='direct')[start:stop];out[start:stop]=a+u*(b-a)
        else:
            a=signal.convolve(x,previous/np.exp(gp),method='direct')[start:stop];b=signal.convolve(x,current/np.exp(gc),method='direct')[start:stop]
            out[start:stop]=((1.-u)*a+u*b)*np.exp((1.-u)*gp+u*gc)
    return out
convolution=[]
for source in ('impulse','noise','step','zeros'):
    frames=8;p=np.zeros((frames,35));p[:,0]=np.linspace(.1,.8,frames);p[:,1]=np.linspace(.1,.35,frames)
    if source=='impulse':x=np.zeros(frames*240);x[0]=1.;x[720]=-.5
    elif source=='noise':x=rng.normal(0.,.1,frames*240)
    elif source=='step':x=np.r_[np.zeros(600),np.ones(frames*240-600)*.1]
    else:x=np.zeros(frames*240)
    for mode in ('linear','loggain'):
        y=filter_source(p,x,mode);z=independent(p,x,mode);error=float(np.max(np.abs(y-z)));assert error<=1e-10
        xp=x.copy();xp[960:]+=1.;yp=filter_source(p,xp,mode);assert np.array_equal(y[:960],yp[:960])
        convolution.append(dict(source=source,mode=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
pure_gain=[]
for direction in ('up','down'):
    p=np.zeros((8,35));p[:,0]=np.linspace(.1,1.8,8) if direction=='up' else np.linspace(1.8,.1,8)
    params=[p,np.full((8,1),np.log(220.)),np.ones((8,1))];native,tr=raw(params,settings,'native');x=tr['excitation'];u=np.arange(240)/240.
    expected_log=np.concatenate([np.exp(p[max(0,i-1),0]+u*(p[i,0]-p[max(0,i-1),0])) for i in range(8)])*x
    # HTSは係数を反復加算するので、ここは数学的一致の許容誤差。byte一致とは呼ばない。
    native_error=float(np.max(np.abs(native-expected_log)));assert native_error<=1e-10
    for mode in ('linear','loggain'):
        y=filter_source(p,x,mode)
        expected=expected_log if mode=='loggain' else np.concatenate([np.exp(p[max(0,i-1),0])+u*(np.exp(p[i,0])-np.exp(p[max(0,i-1),0])) for i in range(8)])*x
        error=float(np.max(np.abs(y-expected)));assert error<=1e-10
        pure_gain.append(dict(direction=direction,mode=mode,max_abs_error=error,native_log_gain_error=native_error,passed=True))
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((20,35));mcp[:,0]=5.;mcp[:,1]=np.linspace(.1,.35,20);mcp[:,2]=.15
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mcp,lf0,np.full((20,1),coefficient)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,tr=raw(params,settings,'native')
    for mode in ('linear','loggain'):assert np.isfinite(filter_source(mcp,tr['excitation'],mode)).all()
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_wave_exact=True,input_streams_exact=True,source_sha256=ah(tr['excitation']),passed=True))
print(json.dumps(dict(passed=True,spectral_checks=spectral,convolution_checks=convolution,pure_gain_checks=pure_gain,source_checks=source_checks,
    IR_length=IR_LENGTH,FFT_length=FFT_LENGTH,render=86,dsp=46,
    render_breakdown=dict(FFT_kernel=16,C_reference_kernel=16,driving_signal=4,convolution_filter=16,independent_convolution=8,pure_gain_native=2,pure_gain_filter=4,pure_gain_expected=4,original_HTS=4,observed_HTS=4,source_filter=8),
    dsp_breakdown=dict(spectral=16,convolution=8,causal=8,pure_gain=4,native_gain=2,source_check=8),
    direct_past_only=True,extra_alignment_latency_samples=0,scope='登録人工MCPの利得・形状補間機構のみ。新日本語の工学/二ASR/知覚は別契約。',quality_certified=False)))
