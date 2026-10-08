"""二次系の独立応答、人工ラベル、全実frameの因子保持、native配列入口を照合。"""
import sys,json,math,os,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import signal
from fujisaki_context import gp,ga,contour,commands,transform,ALPHA,BETA,GAMMA,DT,ah
from runtime import generate
from hts_arrays import synthesize
t=np.linspace(0.,3.,3001)
_,impulse=signal.impulse(([ALPHA**2],[1.,2.*ALPHA,ALPHA**2]),T=t)
_,step=signal.step(([BETA**2],[1.,2.*BETA,BETA**2]),T=t)
err_p=float(np.max(np.abs(gp(t)-impulse)));err_a=float(np.max(np.abs(ga(t)-np.minimum(step,GAMMA))))
assert err_p<=1e-11 and err_a<=1e-11
assert gp(-.1)==0 and ga(-.1)==0 and gp(0.)==0 and ga(0.)==0
assert abs(gp(1./ALPHA)-ALPHA/math.e)<=1e-12 and ga(3.)==GAMMA
primitive=[]
for p,a in (([0.],[[.1,.4]]),([-.2,1.],[[0.,.2],[1.1,1.5]]),([],[[-.3,-.1]]),([.4],[])):
 times=np.linspace(-.5,2.,2501);out,phrase,accent=contour(times,p,a)
 def sp(v):return ALPHA**2*v*math.exp(-ALPHA*v) if v>=0 else 0.
 def sa(v):return min(1.-(1.+BETA*v)*math.exp(-BETA*v),GAMMA) if v>=0 else 0.
 reference=np.array([sum(.15*sp(float(v)-u) for u in p)+sum(.25*(sa(float(v)-u)-sa(float(v)-w)) for u,w in a) for v in times])
 error=float(np.max(np.abs(out-reference)));assert error<=1e-12
 future=contour(times,p+[1.],a+[[1.2,1.6]])[0];assert np.array_equal(out[times<1.],future[times<1.])
 primitive.append(dict(phrase_commands=p,accent_commands=a,scalar_max_abs_error=error,causal_response_prefix_exact=True))
invalid=0
for args in (([np.nan],[],[]),([0.],[float('inf')],[]),([0.],[],[[.1,.1]]),([0.],[],[[.2,.1]])):
 try:contour(*args)
 except ValueError:invalid+=1
 else:raise AssertionError('不正な指令を拒否しない')
def label(phone,bg,ap,mora,count,accent):
 return f'xx^xx-{phone}+xx=xx/A:{mora-accent}+{mora}+{count-mora+1}/F:{count}_{accent}#0_xx@{ap}_1|1_1/I:1-1@{bg}+1&1-1|1+1'
labels=['xx^xx-sil+xx=xx/A:xx+xx+xx',label('k',1,1,1,3,2),label('a',1,1,1,3,2),label('i',1,1,2,3,2),label('o',1,1,3,3,2),
        'xx^xx-pau+xx=xx/A:xx+xx+xx',label('u',2,1,1,1,1),'xx^xx-sil+xx=xx/A:xx+xx+xx']
d=np.full(len(labels)*5,2);c=commands(labels,d)
assert c['frames']==80 and np.allclose(c['phrase_times'],[-.15,.1],rtol=0,atol=1e-14) and np.allclose(c['accent_times'],[[.15,.2],[.3,.35]],rtol=0,atol=1e-14)
bad_d=d.copy();bad_d[0]=0
try:commands(labels,bad_d)
except ValueError:invalid+=1
else:raise AssertionError('不正durationを拒否しない')
x=[np.zeros((80,35)),np.full((80,1),math.log(220.)),np.ones((80,1))];x[1][:10]=-1e10
y,detail=transform(x,labels,d,220.);changed=[v.copy() for v in x];changed[1][changed[1][:,0]>0,0]+=np.linspace(-.1,.1,int(np.sum(changed[1][:,0]>0)))
z,_=transform(changed,labels,d,220.);assert np.array_equal(y[1],z[1])
rows=[]
specs=['桜の種を畑にまいた。','荷物を棚に置いた。','川沿いを歩き、橋の下で休んだ。','港の灯りが消える前に、船の鍵を箱へ戻した。']
for text in specs:
 for speed,pitch in ((1.,220.),(1.15,280.)):
  native,mn,pn,rn=generate(text,'native',speed,pitch,True);candidate,mc,pc,rc=generate(text,'fujisaki',speed,pitch,True)
  assert rn==rc
  for key in ('duration','msd','settings','state_sha256','variance_sha256','native_parameter_hashes'):assert mn[key]==mc[key],key
  assert np.array_equal(pn[0],pc[0]) and np.array_equal(pn[2],pc[2]);mask=pn[1][:,0]>0
  assert np.array_equal(mask,pc[1][:,0]>0) and pn[1][~mask].tobytes()==pc[1][~mask].tobytes()
  independent,ind=synthesize(pn,mn['settings']);expected=(independent*.25).astype(np.float32)
  import io
  from scipy.io import wavfile
  fs,native_samples=wavfile.read(io.BytesIO(native));assert fs==24000 and np.array_equal(native_samples,expected)
  _,candidate_samples=wavfile.read(io.BytesIO(candidate));assert np.isfinite(candidate_samples).all() and len(native_samples)==len(candidate_samples)
  assert mc['invariants_pass'] and abs(mc['generated_lf0_median_hz']/pitch-1.)<=1e-14
  assert not np.array_equal(pn[1][mask],pc[1][mask]) and mc['control']['native_LF0_values_used_for_shape'] is False
  rows.append(dict(text=text,speed=speed,pitch=pitch,frames=len(pn[0]),native_wave_sha256=mn['sha256'],candidate_wave_sha256=mc['sha256'],
                   all_frames_MCP_LPF_exact=True,MSD_mask_and_duration_exact=True,shared_model_and_variance_exact=True,native_bare_renderer_exact=True,
                   LF0_intentionally_changed=True,median_error_hz=abs(mc['generated_lf0_median_hz']-pitch),relative_contour_error=mc['relative_LF0_max_abs_error'],
                   E0_native=mn['E0_pass'],E0_candidate=mc['E0_pass'],control=mc['control'],all_input_hashes_native=mn['output_parameter_hashes'],all_input_hashes_candidate=mc['output_parameter_hashes']))
print(json.dumps(dict(passed=True,phrase_LTI_max_error=err_p,accent_LTI_max_error=err_a,primitive_conditions=primitive,synthetic_commands=c,invalid_inputs_rejected=invalid,
                     native_LF0_shape_influence_rejected=True,rows=rows,actual_HTS_render_calls=24,charged_render=80,charged_DSP=256,conservative_counts_not_returned=True,
                     response_causal=True,global_median_centering_not_streaming_causal=True,real_Japanese_quality_qualified=False,perceptual_qualification=False),ensure_ascii=False))
