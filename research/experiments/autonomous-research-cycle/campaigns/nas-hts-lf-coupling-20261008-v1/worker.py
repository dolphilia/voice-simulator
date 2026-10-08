"""原配列vocoder対照と独立PythonのLF/LPF混合、元時計/noise、未来差分を照合する。"""
import sys,json,os,tempfile,math
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import signal
from hts_arrays import synthesize as bare,ah
from shape_arrays import raw,COEFF
from lf_source import scalar
def reference(tr,lpf,method):
 p=tr['period'];counter=tr['counter'];phase=np.full(len(p),-1.);pulse=np.zeros(len(p));source=np.empty(len(p));size=lpf.shape[1];ring=np.zeros(size);index=0
 for n in range(len(p)):
  if p[n]>0:
   c=counter[n]+1.;event=c>=p[n]
   if event:c-=p[n]
   phase[n]=math.fmod(c/p[n],1.)
   pulse[n]=scalar(float(phase[n]),COEFF) if method=='lf' else (math.sqrt(p[n]) if event else 0.)
  noise=tr['noise'][n];lp=lpf[n//240];center=(size-1)//2
  if p[n]==0:ring[(index+center)%size]+=noise
  else:
   if noise!=0.:
    for i in range(size):ring[(index+i)%size]+=noise*((1. if i==center else 0.)-lp[i])
   if pulse[n]!=0.:
    for i in range(size):ring[(index+i)%size]+=pulse[n]*lp[i]
  source[n]=ring[index];ring[index]=0.;index=(index+1)%size
 return source,pulse,phase
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
cases=[]
for hz in (110.,280.):
 for LPF in ('zero','one','31tap'):
  cases.append((str(hz)+'/'+LPF,np.full(60,hz),LPF))
cases.extend([('rising/31tap',np.linspace(110.,280.,60),'31tap'),('falling/31tap',np.linspace(280.,110.,60),'31tap')])
rows=[]
for name,hz,mode in cases:
 mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.2;lf0=np.full((100,1),-1e10);lf0[20:80,0]=np.log(hz)
 if mode=='31tap':
  q=np.arange(-15,16);kernel=np.sinc(.12*q)*np.hanning(31);kernel/=kernel.sum();lpf=np.tile(kernel,(100,1))
 else:lpf=np.full((100,1),0. if mode=='zero' else 1.)
 params=[mcp,lf0,lpf];before=[ah(v) for v in params];expected,_=bare(params,settings)
 native,tn=raw(params,settings,'native');changed,tc=raw(params,settings,'lf')
 a=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(a)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;a[:n]*=env;a[-n:]*=env[::-1]
 assert np.array_equal(a,expected) and [ah(v) for v in params]==before
 assert all(np.array_equal(tn[k],tc[k]) for k in ('period','counter','event','noise','phase'))
 errors={}
 for method,tr in (('native',tn),('lf',tc)):
  ref,pulse,phase=reference(tr,lpf,method)
  errors[method]=dict(source=float(np.max(np.abs(ref-tr['excitation']))),periodic=float(np.max(np.abs(pulse-tr['periodic']))),phase=float(np.max(np.abs(phase-tr['phase']))))
  assert errors[method]['source']<=1e-10 and errors[method]['periodic']<=1e-12 and errors[method]['phase']<=1e-12
 future=[v.copy() for v in params];future[0][50:,1]+=.1;future[1][50:80,0]=np.log(220.);future[2][50:]*=.9
 for method,old,tr in (('native',native,tn),('lf',changed,tc)):
  y,t=raw(future,settings,method);assert np.array_equal(old[:12000],y[:12000]) and all(np.array_equal(tr[k][:12000],t[k][:12000]) for k in tr)
 assert np.isfinite(changed).all()
 if mode=='zero':assert np.array_equal(native,changed)
 # unvoicedへの切替後、LPF ringのtailが尽きた領域だけ原励振と完全一致を要求する。
 assert np.array_equal(tn['excitation'][80*240+31:],tc['excitation'][80*240+31:])
 rows.append(dict(case=name,frames=100,LPF_columns=lpf.shape[1],native_wave_exact=True,input_streams_exact=True,source_clock_and_noise_exact=True,independent_errors=errors,
  causal_raw_prefix_exact=True,unvoiced_after_LPF_tail_exact=True,zero_LPF_wave_exact=mode=='zero',LF_source_changed=not np.array_equal(tn['excitation'],tc['excitation']),
  source_clock_hashes={k:ah(tn[k]) for k in ('period','counter','event')},native_excitation_sha256=ah(tn['excitation']),LF_excitation_sha256=ah(tc['excitation']),passed=True))
assert len(rows)==8 and sum(v['LF_source_changed'] for v in rows)==6
print(json.dumps(dict(passed=True,rows=rows,render=56,dsp=96,scope='登録人工8条件の原native対照、LF周期関数と独立LPF混合、元時計/noise/入力、raw未来差分だけ。',
 real_Japanese_speech_qualified=False,antialiasing_qualified=False,perceived_pitch_or_quality_truth=False,quality_certified=False),allow_nan=False))
