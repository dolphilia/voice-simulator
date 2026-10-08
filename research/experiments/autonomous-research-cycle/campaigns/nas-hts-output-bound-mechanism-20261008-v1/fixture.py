"""独立スカラー式、上限・恒等域・因果性と原HTSを検証する。"""
import sys,json,os,tempfile,math
from pathlib import Path
here=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from bounded_output import bound,synthesize,KNEE,CEILING,WIDTH
def scalar(x):
    return x if abs(x)<=.5 else math.copysign(.5+.48*math.tanh((abs(x)-.5)/.48),x)
rng=np.random.default_rng(1053053)
grid=np.unique(np.r_[np.linspace(-4.,4.,16001),[-1e6,-.50000001,-.5,-.49999999,0.,.49999999,.5,.50000001,1e6]])
out=bound(grid);ref=np.array([scalar(float(x)) for x in grid]);error=float(np.max(np.abs(out-ref)))
assert error<=1e-14
assert np.max(np.abs(out))<=.98 and np.max(np.abs(out.astype(np.float32)))<.99
assert np.all(np.diff(out)>=0.) and np.array_equal(bound(-grid),-out)
inside=np.abs(grid)<=.5;assert np.array_equal(out[inside],grid[inside])
grid_checks=dict(scalar_max_abs_error=error,finite_double_and_float32_bounded=True,
    monotone_and_odd=True,identity_region_exact=True,passed=True)
driving=[]
for mode in ('zeros','step','impulse','sine_low','sine_high','noise'):
    n=4800
    if mode=='zeros':x=np.zeros(n)
    elif mode=='step':x=np.r_[np.zeros(600),np.full(n-600,2.)]
    elif mode=='impulse':x=np.zeros(n);x[0]=2.;x[700]=-2.
    elif mode=='sine_low':x=.2*np.sin(2*np.pi*220*np.arange(n)/24000.)
    elif mode=='sine_high':x=1.4*np.sin(2*np.pi*220*np.arange(n)/24000.)
    else:x=rng.normal(0.,.7,n)
    before=ah(x);y=bound(x);z=np.array([scalar(float(v)) for v in x]);err=float(np.max(np.abs(y-z)))
    future=x.copy();future[2400:]+=1.;changed=bound(future)
    assert err<=1e-14 and ah(x)==before and np.array_equal(y[:2400],changed[:2400])
    driving.append(dict(mode=mode,scalar_max_abs_error=err,causal_prefix_exact=True,input_exact=True,
        low_region_samples=int((np.abs(x)<=.5).sum()),changed_samples=int((x!=y).sum()),passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source=[]
for hz in (110.,280.):
 for lpf in (0.,1.):
    mcp=np.zeros((60,35));mcp[:,0]=9.;mcp[:,1]=.2;lf0=np.full((60,1),-1e10);lf0[10:50]=np.log(hz)
    params=[mcp,lf0,np.full((60,1),lpf)];before=[ah(v) for v in params]
    expected,_=original(params,settings)
    native,meta=synthesize(params,settings,'native');candidate,cmeta=synthesize(params,settings,'soft_bound')
    assert np.array_equal(expected,native) and [ah(v) for v in params]==before
    assert meta['source_clock_hashes']==cmeta['source_clock_hashes'] and meta['original_excitation_sha256']==cmeta['original_excitation_sha256']
    assert meta['processed_excitation_sha256']==cmeta['processed_excitation_sha256'] and cmeta['original_excitation_and_processed_excitation_equal']
    expected_final=np.array([scalar(float(v)) for v in native*.25])
    err=float(np.max(np.abs(candidate*.25-expected_final)));assert err<=1e-14
    assert np.max(np.abs((candidate*.25).astype(np.float32)))<.99
    low=np.abs(native*.25)<=.5;assert np.array_equal((candidate*.25)[low],(native*.25)[low])
    source.append(dict(hz=hz,lpf=lpf,native_exact=True,all_parameters_and_source_clock_exact=True,
        expected_final_max_abs_error=err,float32_no_clipping=True,unchanged_low_samples=int(low.sum()),passed=True))
reject=[]
for values in ([float('nan')],[float('inf')],[-float('inf')],[[1.]]):
    try:bound(values)
    except ValueError:reject.append(True)
    else:raise AssertionError('不正振幅列の拒否が必要')
print(json.dumps(dict(passed=True,grid_checks=grid_checks,driving_checks=driving,HTS_checks=source,invalid_inputs_rejected=reject,
    render=39,dsp=28,
    render_breakdown=dict(grid_driver=1,grid_filter=1,grid_independent=1,driving_signals=6,driving_filter=6,driving_independent=6,causal_filter=6,original_HTS=4,native_HTS=4,bounded_HTS=4),
    dsp_breakdown=dict(grid=4,driving_scalar=6,driving_causality=6,HTS_native_and_source=4,HTS_final_mapping=4,invalid_inputs=4),
    scope='登録人工振幅の上限・恒等域・因果性と人工HTSの機構のみ。日本語内容・ピッチ・DC・自然さは別比較。',
    amplitude_bound_is_not_naturalness_truth=True,quality_certified=False)))
