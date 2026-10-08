"""元波形一致・位相cell・エネルギー・直接周波数応答の工程検証。"""
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
    for method in ('latency','linear','sinc'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        if coefficient==0.:assert np.array_equal(a,z)
        else:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,all_clock_and_phase_exact=True,zero_LPF_exact=coefficient==0.))
phase_checks=[]
for hz in (80.,110.,220.,280.,400.,800.):
 for remainder in np.linspace(0,1,11):
    response={};target=4-remainder;p=48000/hz;w=2*np.pi*hz/48000
    for method in ('latency','linear','sinc'):
        k=kernel(p,float(remainder),method);assert np.isfinite(k).all() and abs(float(np.sum(k*k))-p)<1e-10
        H=np.dot(k,np.exp(-1j*w*np.arange(9)));error=float(abs(np.angle(H*np.exp(1j*w*target))/w));response[method]=error
        if method=='linear':assert abs(float(np.dot(np.arange(9),k)/k.sum())-target)<1e-12
    assert abs(response['latency']-remainder)<1e-12
    assert response['linear']<=max(.05,remainder+1e-9) and response['sinc']<=max(.05,remainder+1e-9)
    phase_checks.append(dict(hz=hz,remainder=float(remainder),phase_error_samples=response))
print(json.dumps(dict(passed=True,checks=checks,phase_checks=phase_checks,render=24,dsp=900,fixture_only=True,mechanical_phase_is_not_audible_pitch_truth=True,quality_certified=False)))
