"""解析積分を独立quadで確認し、固定phaseのC/Python二波形を全件照合する。"""
import sys,json,os,tempfile,hashlib,math
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import integrate
from lf_source import coefficients,scalar,evaluate,tests,TP,TE,TA,EE
c,proof=coefficients();tests(c);tp,te,ta,ep,alpha,e0,scale=c
assert max(abs(proof['return_equation_residual']),abs(proof['net_integral']))<=1e-12
mean=sum(integrate.quad(lambda t:scalar(t,c),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.)))
power=sum(integrate.quad(lambda t:scalar(t,c)**2,a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.)))
assert abs(mean)<=1e-12 and abs(power-1.)<=1e-12
left=scale*e0*math.exp(alpha*te)*math.sin(math.pi*te/tp)
right=-scale*(1.-math.exp(-ep*(1.-te)))/(ep*ta)
assert abs(left-right)<=1e-12 and abs(left+scale*EE)<=1e-12
assert abs(scalar(0.,c))<=1e-12 and abs(scalar(1.,c))<=1e-12
grid=np.unique(np.r_[np.linspace(0.,1.,4097),tp,te]);x=evaluate(grid,c);ref=np.array([scalar(float(t),c) for t in grid])
grid_error=float(np.max(np.abs(x-ref)));assert grid_error<=1e-12
flow=[]
for t in np.linspace(0.,1.,17):
 v=sum(integrate.quad(lambda q:scalar(q,c),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,min(t,te)),(te,max(te,t))))
 flow.append(dict(phase=float(t),normalized_flow=v));assert v>=-1e-12
rows=[]
for fs in (24000,48000):
 for frequency in (80.,110.,220.,280.,400.):
  for initial in (.125,.731):
   phase=np.mod(initial+np.arange(fs//2)*frequency/fs,1.);a=evaluate(phase,c);b=np.array([scalar(float(t),c) for t in phase])
   error=float(np.max(np.abs(a-b)));assert error<=1e-12
   # 同じ入力phaseの前半を別評価して完全一致を確認する。時間変動の声道安定ではない。
   prefix=evaluate(phase[:len(phase)//2],c);assert np.array_equal(a[:len(prefix)],prefix)
   rows.append(dict(fs=fs,frequency=frequency,initial_phase=initial,samples=len(a),C_Python_max_abs_error=error,C_prefix_exact=True,finite_wave=bool(np.isfinite(a).all()),
    wave_sha256=hashlib.sha256(a.astype('<f8').tobytes()).hexdigest(),passed=True))
fundamental=complex(*[sum(integrate.quad(lambda t:scalar(t,c)*fn(2*math.pi*t),a,b,epsabs=1e-13,epsrel=1e-13)[0] for a,b in ((0.,te),(te,1.))) for fn in (math.cos,lambda x:-math.sin(x))])
assert abs(fundamental)>1e-6
assert len(rows)==20
print(json.dumps(dict(passed=True,coefficients=c.tolist(),proof=proof,independent_quad_mean=mean,independent_quad_power=power,closing_continuity_error=abs(left-right),dense_grid_error=grid_error,
 flow_grid=flow,fundamental_coefficient=[fundamental.real,fundamental.imag],rows=rows,render=42,dsp=128,
 spectrum_and_root_definition_only=True,antialiasing_claimed=False,biological_voice_or_perceived_pitch_truth=False,HTS_coupling_qualified=False,quality_certified=False),allow_nan=False))
