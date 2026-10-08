"""既知全極系、独立Toeplitz解、標準直接形、動的解析の逆写像を確認する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal,linalg
from hts_arrays import synthesize as original,ah
from lattice import response,project,polynomial,filter_coefficients,synthesize,ORDER,FFT_LENGTH
rng=np.random.default_rng(1055055);q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
cases=[[],[.2],[.5],[-.3,.3],[.45+.2j,.45-.2j],[.5*np.exp(.7j),.5*np.exp(-.7j)],
 [.45*np.exp(.3j),.45*np.exp(-.3j),.35*np.exp(1.4j),.35*np.exp(-1.4j)],[-.25,.35,.2+.2j,.2-.2j]]
spectral=[]
for index,poles in enumerate(cases):
 for alpha in (0.,.55):
    poles=np.array(poles,dtype=np.complex128);gain=1.3
    mc=np.zeros(35);mc[0]=np.real(np.log(gain)-np.log(1.-alpha*poles).sum())
    w=(poles-alpha)/(1.-alpha*poles)
    for m in range(1,35):mc[m]=np.real((np.sum(w**m)+len(poles)*(-1)**(m+1)*alpha**m)/m)
    known_polynomial=np.atleast_1d(np.poly(poles).real)
    h=response(mc,alpha);exact=gain/np.polynomial.polynomial.polyval(q,known_polynomial)
    herr=float(np.max(np.abs(h-exact))/max(np.max(np.abs(exact)),1e-12));assert herr<=1e-8
    a,k,g,r=project(mc,alpha);dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[:-1]/r[0]),-r[1:]/r[0])]
    independent=float(np.max(np.abs(a-dense)));known=np.pad(known_polynomial,(0,35-len(poles)-1));knownerr=float(np.max(np.abs(a-known)))
    gainerr=abs(g-gain);assert independent<=1e-10 and knownerr<=1e-7 and gainerr<=1e-7
    assert np.max(np.abs(np.roots(polynomial(k))))<1. and np.max(np.abs(a-polynomial(k)))<=1e-10
    spectral.append(dict(case=index,alpha=alpha,known_response_relative_error=herr,dense_coefficient_max_abs_error=independent,known_coefficient_max_abs_error=knownerr,known_gain_error=gainerr,passed=True))
static=[]
ks=[np.array([.3]),np.array([-.4,.25]),np.array([-.35,.2,-.1,.05])]
drivers={};n=4800
for mode in ('impulse','noise','step','sine'):
    if mode=='impulse':x=np.zeros(n);x[0]=1.;x[1000]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,n)
    elif mode=='step':x=np.r_[np.zeros(600),np.full(n-600,.1)]
    else:x=.2*np.sin(2*np.pi*220*np.arange(n)/48000.)
    drivers[mode]=x
    for k in ks:
        coeff=np.tile(k,(20,1));logg=np.full(20,np.log(1.3));y=filter_coefficients(coeff,logg,x);z=signal.lfilter([1.3],polynomial(k),x)
        err=float(np.max(np.abs(y-z)));assert err<=1e-10
        future=x.copy();future[2400:]+=1.;yp=filter_coefficients(coeff,logg,future);assert np.array_equal(y[:2400],yp[:2400])
        static.append(dict(mode=mode,order=len(k),direct_form_max_abs_error=err,causal_prefix_exact=True,passed=True))
frames=20;k=rng.normal(0.,.025,(frames,34));k[:,0]=np.linspace(-.4,.4,frames);logg=np.linspace(np.log(.5),np.log(1.5),frames)
roots=[]
for row in k:
    radius=float(np.max(np.abs(np.roots(polynomial(row)))));assert radius<1.;roots.append(radius)
dynamic=[]
for mode in ('noise','sine'):
    x=rng.normal(0.,.1,n) if mode=='noise' else .2*np.sin(2*np.pi*280*np.arange(n)/48000.)
    y=filter_coefficients(k,logg,x);states=np.zeros(34);reconstructed=np.empty(n)
    # 合成の降順再帰と異なる昇順解析latticeで源を復元する。
    for t,value in enumerate(y):
        f=t//240;j=t%240;p=max(0,f-1);u=j/240.;r=k[p]+u*(k[f]-k[p]);old=states.copy();states[0]=value;forward=value
        for m in range(34):
            prior=forward;forward=prior+r[m]*old[m]
            if m<33:states[m+1]=r[m]*prior+old[m]
        reconstructed[t]=forward/np.exp(logg[p]+u*(logg[f]-logg[p]))
    err=float(np.max(np.abs(reconstructed-x)));assert err<=1e-10
    future=x.copy();future[2400:]+=1.;yp=filter_coefficients(k,logg,future);assert np.array_equal(y[:2400],yp[:2400])
    dynamic.append(dict(mode=mode,analysis_inverse_max_abs_error=err,causal_prefix_exact=True,finite_registered_trajectory=True,passed=True))
artificial=[]
for i in range(8):
    mc=np.zeros(35);mc[0]=.2*i;mc[1:]=rng.normal(0.,.03,34)*np.exp(-np.arange(1,35)/12.)
    a,k,g,r=project(mc);dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[:-1]/r[0]),-r[1:]/r[0])]
    err=float(np.max(np.abs(a-dense)));radius=float(np.max(np.abs(np.roots(a))));assert err<=1e-10 and radius<1.
    h=response(mc);approx=g/np.polynomial.polynomial.polyval(q,a);rms=float(np.sqrt(np.mean((20*np.log10(np.abs(approx)/np.abs(h)))**2)))
    artificial.append(dict(case=i,dense_coefficient_error=err,root_radius=radius,finite_grid_log_magnitude_RMSE_dB=rms,approximation_error_is_not_exact_reproduction=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
sources=[]
for hz in (110.,280.):
 for lpf in (0.,1.):
    mc=np.zeros((20,35));mc[:,0]=5.;mc[:,1]=np.linspace(.1,.2,20);mc[:,2]=.05
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mc,lf0,np.full((20,1),lpf)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,nm=synthesize(params,settings,'native');candidate,cm=synthesize(params,settings,'lattice')
    assert np.array_equal(expected,native) and [ah(v) for v in params]==before
    assert nm['source_clock_hashes']==cm['source_clock_hashes'] and nm['original_excitation_sha256']==cm['original_excitation_sha256'] and nm['processed_excitation_sha256']==cm['processed_excitation_sha256']
    assert np.isfinite(candidate).all()
    sources.append(dict(hz=hz,lpf=lpf,native_exact=True,all_input_streams_and_original_source_clock_exact=True,candidate_finite=True,frames_projected=20,passed=True))
print(json.dumps(dict(passed=True,known_AR_checks=spectral,static_driving_checks=static,dynamic_checks=dynamic,instantaneous_registered_root_radii=roots,artificial_MCP_checks=artificial,HTS_checks=sources,
    order=34,FFT_length=16384,render=62,dsp=232,
    render_breakdown=dict(driving_signals=4,static_C=12,static_direct_form=12,static_causal=12,dynamic_drivers=2,dynamic_C=2,dynamic_causal=2,original_HTS=4,native_HTS=4,candidate_HTS_helper=4,candidate_lattice=4),
    dsp_breakdown=dict(known_AR_projection=16,known_AR_independent=16,known_AR_response_and_gain=16,known_AR_stability=16,static_direct_form=12,static_causality=12,dynamic_inverse=2,dynamic_causality=2,dynamic_instantaneous_roots=20,artificial_MCP_projection=8,artificial_MCP_independent=8,artificial_MCP_grid=8,artificial_MCP_stability=8,HTS_frame_projection=80,HTS_native_exact=4,HTS_source_clock=4),
    scope='登録人工全極系/MCPの射影と有限動的latticeのみ。実HTS全frameの射影損失、未知日本語/短窓pitch/知覚は別。',
    time_varying_global_stability_proven=False,exact_MCP_or_MLSA_reproduction_claimed=False,quality_certified=False)))
