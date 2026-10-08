"""ゼロ/単位LPFと遷移で、source単独の工程と旧対照一致を検証する。"""
import io,json,os,sys,tempfile
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
    mcp=np.zeros((100,35));mcp[:,0]=7.
    lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);pulse,_=synthesize(params,settings,'native')
    a,ta=raw(params,settings,'native');b,tb=raw(params,settings,'rosenberg')
    assert np.array_equal(baseline,pulse)
    assert all(np.array_equal(ta[k],tb[k]) for k in ta)
    if coefficient==0.:assert np.array_equal(a,b)
    else:assert not np.array_equal(a,b)
    k=kernel(48000./hz)
    assert abs(float(np.sum(k*k))-48000./hz)<1e-10 and abs(float(k.sum()))<1e-12
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,cycle_clock_exact=True,kernel_energy_exact=True,zero_lpf_exact=coefficient==0.))
print(json.dumps(dict(passed=True,checks=checks,render=16,dsp=40,fixture_only=True,quality_certified=False)))
