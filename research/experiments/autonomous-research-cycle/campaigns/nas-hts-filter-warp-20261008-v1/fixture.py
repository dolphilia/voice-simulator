"""原波形/励振一致と独立したMLSA係数・周波数軸恒等式の検証。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original
from shape_arrays import raw,synthesize,mc2b,ALPHA
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
  for rich in (False,True):
    mcp=np.zeros((100,35));mcp[:,0]=7.
    if rich:mcp[:,1]=.35;mcp[:,2]=.15;mcp[:,6]=.12
    lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz);params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);native,_=synthesize(params,settings,'native');assert np.array_equal(baseline,native)
    a,ta=raw(params,settings,'native')
    for method in ('alpha_low','alpha_high'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        assert np.isfinite(z).all()
        if rich:assert not np.array_equal(a,z)
        else:assert np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,nonflat=rich,legacy_audio_exact=True,excitation_and_clock_exact=True,flat_filter_alpha_invariant=not rich))
mechanical=[];w=np.linspace(0,np.pi,1025);z=np.exp(-1j*w)
vectors=[np.r_[7.,np.zeros(34)],np.r_[7.,.35,np.zeros(33)],np.r_[7.,0.,0.,0.,.2,np.zeros(30)],np.r_[7.,.08*np.cos(np.arange(1,35))/np.arange(1,35)]]
for alpha in (.50,.55,.60):
 q=(z-alpha)/(1-alpha*z);phi1=(1-alpha*alpha)*z/(1-alpha*z)
 for idx,c in enumerate(vectors):
    b=mc2b(c,alpha);expected=np.empty(35);expected[-1]=c[-1]
    for j in range(33,-1,-1):expected[j]=c[j]-alpha*expected[j+1]
    assert np.array_equal(b,expected)
    a=sum(c[m]*q**m for m in range(35));v=b[0]+sum(b[m]*phi1*q**(m-1) for m in range(1,35))
    err=float(np.max(np.abs(a-v)));assert err<1e-12
    mechanical.append(dict(alpha=alpha,vector=idx,mc2b_exact=True,allpass_log_transfer_maxerr=err))
print(json.dumps(dict(passed=True,checks=checks,filter_identity_checks=mechanical,render=40,dsp=600,fixture_only=True,
    effective_alpha_only_factor=True,original_excitation_exact=True,frequency_warp_is_not_uniform_tract_scale=True,quality_certified=False)))
