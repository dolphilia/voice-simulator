"""輪郭の固定倍率・原波形一致・無周期経路不変を生成前検証する。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original,ah
from shape_arrays import raw,synthesize
from contour import apply_contour
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
  for dynamic in (False,True):
    mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.35;mcp[:,2]=.15;mcp[:,6]=.12
    lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    if dynamic:lf0[20:80,0]+=.2*np.sin(np.linspace(-np.pi,np.pi,60))
    params=[mcp,lf0,np.full((100,1),coefficient)]
    native_params,ct=apply_contour(params,hz,'native');assert all(np.array_equal(a,z) for a,z in zip(params,native_params))
    baseline,_=original(params,settings);native,_=synthesize(native_params,settings,'native');assert np.array_equal(baseline,native)
    a,ta=raw(native_params,settings,'native')
    for method in ('half_contour','flat_contour'):
        changed,meta=apply_contour(params,hz,method);z,tz=raw(changed,settings,method)
        assert meta['passed'] and np.isfinite(z).all()
        assert np.array_equal(ta['period']==0,tz['period']==0)
        if coefficient==0.:assert np.array_equal(a,z)
        if dynamic and coefficient==1.:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,dynamic=dynamic,legacy_audio_exact=True,voicing_mask_exact=True,
        MCP_LPF_sentinel_exact=True,noise_only_wave_exact=coefficient==0.,dynamic_periodic_changed=dynamic and coefficient==1.))
control_checks=[]
for hz in (110.,220.,280.,400.):
 for swing in (0.,.1,.3):
  lf0=np.r_[-1e10,np.log(hz)-swing,np.log(hz),np.log(hz)+swing,-1e10].reshape(-1,1)
  p=[np.zeros((5,35)),lf0,np.ones((5,1))]
  for method,scale in [('native',1.),('half_contour',.5),('flat_contour',0.)]:
    z,m=apply_contour(p,hz,method);assert m['passed'] and np.array_equal(z[1][[0,4]],lf0[[0,4]])
    assert abs(float(np.median(z[1][1:4,0]))-np.log(hz))<1e-14
    assert abs(float(np.ptp(z[1][1:4,0]))-2*swing*scale)<2e-15
    control_checks.append(dict(hz=hz,swing=swing,method=method,scale=scale,passed=True))
print(json.dumps(dict(passed=True,checks=checks,contour_control_checks=control_checks,render=40,dsp=600,fixture_only=True,
    original_native_wave_exact=True,relative_contour_intentionally_changed=True,flat_is_not_naturalness_target=True,quality_certified=False)))
