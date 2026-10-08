"""位相と形状の一致、DC/二乗和の別条件、元波形/clockの工程検証。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original
from shape_arrays import raw,synthesize,kernel
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((100,35));mcp[:,0]=7.;lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);native,_=synthesize(params,settings,'native')
    assert np.array_equal(baseline,native)
    a,ta=raw(params,settings,'native')
    for method in ('sinc','sinc_dc'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        if coefficient==0.:assert np.array_equal(a,z)
        else:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,all_clock_and_phase_exact=True,zero_LPF_exact=coefficient==0.))
normalization_checks=[]
for hz in (80.,110.,220.,280.,400.,800.):
 for remainder in np.linspace(0,1,11):
    p=48000/hz;w=2*np.pi*hz/48000;target=4-remainder
    a=kernel(p,float(remainder),'sinc');z=kernel(p,float(remainder),'sinc_dc')
    assert np.isfinite(a).all() and np.isfinite(z).all()
    assert abs(float(np.sum(a*a))-p)<1e-10 and abs(float(z.sum())-np.sqrt(p))<1e-10
    assert np.allclose(z,a*(np.sqrt(p)/a.sum()),rtol=0,atol=1e-12)
    Ha=np.dot(a,np.exp(-1j*w*np.arange(9)));Hz=np.dot(z,np.exp(-1j*w*np.arange(9)))
    assert abs(float(np.angle(Hz/Ha)))<1e-12
    normalization_checks.append(dict(hz=hz,remainder=float(remainder),phase_error_samples=float(abs(np.angle(Ha*np.exp(1j*w*target))/w)),
        L2_DC_gain=float(a.sum()/np.sqrt(p)),DC_DC_gain=float(z.sum()/np.sqrt(p)),DC_energy_ratio=float(np.sum(z*z)/p),shape_and_phase_equal=True))
print(json.dumps(dict(passed=True,checks=checks,normalization_checks=normalization_checks,render=20,dsp=800,fixture_only=True,
    L2_energy_and_DC_gain_are_different_constraints=True,mechanical_truth_not_perceptual_truth=True,quality_certified=False)))
