"""登録人工MCP、独立C prefix、直接畳み込み、有声/無声を照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from minphase import kernel as old_C_kernel
from fft_fir import kernel,filter_source,IR_LENGTH,FFT_LENGTH
rng=np.random.default_rng(1045045);mc=np.zeros((8,35));mc[:,0]=np.linspace(0.,1.,8)
mc[1,1]=.3;mc[2,2]=-.25;mc[3,1:4]=[.35,.15,.12];mc[4:,1:]=rng.normal(0.,.04,(4,34))*np.exp(-np.arange(1,35)/12.)
spectral=[]
for i,c in enumerate(mc):
 for alpha in (0.,.55):
    h=kernel(c,alpha);ref=old_C_kernel(c,alpha)
    error=float(np.max(np.abs(h[:1024]-ref))/max(float(np.max(np.abs(ref))),1e-12))
    assert error<=1e-10 and np.isfinite(h).all()
    spectral.append(dict(case=i,alpha=alpha,C_prefix_relative_error=error,passed=True))
def independent(mc,x):
    h=[kernel(c) for c in mc];out=np.empty(len(x));u=np.arange(240)/240.
    for frame,current in enumerate(h):
        previous=h[max(0,frame-1)];start=frame*240;stop=start+240
        a=signal.convolve(x,previous,method='direct')[start:stop]
        b=signal.convolve(x,current,method='direct')[start:stop]
        out[start:stop]=a+u*(b-a)
    return out
convolution=[]
for mode in ('impulse','noise','step','zeros'):
    frames=8;p=np.zeros((frames,35));p[:,0]=np.linspace(.1,.4,frames);p[:,1]=np.linspace(.1,.35,frames)
    if mode=='impulse':x=np.zeros(frames*240);x[0]=1.;x[720]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,frames*240)
    elif mode=='step':x=np.r_[np.zeros(600),np.ones(frames*240-600)*.1]
    else:x=np.zeros(frames*240)
    y=filter_source(p,x);z=independent(p,x);error=float(np.max(np.abs(y-z)));assert error<=1e-10
    xp=x.copy();xp[960:]+=1.;yp=filter_source(p,xp);assert np.array_equal(y[:960],yp[:960])
    convolution.append(dict(source=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((20,35));mcp[:,0]=5.;mcp[:,1]=np.linspace(.1,.35,20);mcp[:,2]=.15
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mcp,lf0,np.full((20,1),coefficient)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,tr=raw(params,settings,'native');out=filter_source(mcp,tr['excitation'])
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before and np.isfinite(out).all()
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_wave_exact=True,input_streams_exact=True,source_sha256=ah(tr['excitation']),passed=True))
print(json.dumps(dict(passed=True,spectral_checks=spectral,convolution_checks=convolution,source_checks=source_checks,
    IR_length=IR_LENGTH,FFT_length=FFT_LENGTH,render=60,dsp=64,render_breakdown=dict(FFT_kernel=16,C_reference_kernel=16,driving_signal=4,FFT_FIR=12,independent_convolution=4,original_HTS=4,observed_HTS=4),
    direct_past_only=True,extra_alignment_latency_samples=0,scope='登録人工MCPの機構のみ。未知日本語MCPと波形の工学/内容/知覚は別契約。',quality_certified=False)))
