"""五母音の共有径/面積、明示遷移、有限Fourier LF駆動。録音/学習/HMM/lookupなし。"""
import json,math,cmath
from pathlib import Path
import numpy as np
from scipy import signal
import ctypes as C,hashlib
HERE=Path(__file__).resolve().parent
DIAM=json.loads((HERE/'diameters.json').read_text());COEF=json.loads((HERE/'coefficients.json').read_text())
FS=34300;OUTFS=24000;CUTOFF=8000.;GAIN=.10
AREA={v:np.pi*(np.array(d[::-1],dtype=float)/20.)**2 for v,d in DIAM.items()}
def coefficient(m):
 tp,te,ta,ep,a,e0,scale=map(float,COEF);w=math.pi/tp;omega=2*math.pi*m;length=1-te
 if m==0:return 0j
 z1=complex(a,w-omega);z2=complex(a,-w-omega)
 opened=e0*((cmath.exp(z1*te)-1.)/z1-(cmath.exp(z2*te)-1.)/z2)/(2j)
 returning=-(cmath.exp(-1j*omega*te)*(1.-cmath.exp(-complex(ep,omega)*length))/complex(ep,omega)
             -math.exp(-ep*length)*(cmath.exp(-1j*omega*te)-cmath.exp(-1j*omega))/(1j*omega))/(ep*ta)
 return scale*(opened+returning)
def driver(f0,samples):
 if not math.isfinite(f0) or not 70<=f0<=400 or not 1<=samples<=96000:raise ValueError('F0/標本数が登録範囲外')
 phase=(np.arange(samples,dtype=float)*f0/FS+.125)%1.;x=np.zeros(samples);harmonics=math.floor(CUTOFF/f0)
 for m in range(1,harmonics+1):x+=2.*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))
 return x,dict(f0=f0,phase_start=.125,harmonics=harmonics,maximum_source_harmonic_hz=harmonics*f0,continuous_LF_scale_fixed=True,truncation_RMS_renormalized=False)
def areas(first,second=None,samples=20580):
 if first not in AREA or second is not None and second not in AREA:raise ValueError('登録外の母音')
 if second is None:return np.tile(AREA[first],(samples,1))
 t=np.arange(samples)/FS;q=np.clip((t-.20)/.10,0.,1.);s=q*q*(3.-2.*q)
 return (1.-s[:,None])*AREA[first]+s[:,None]*AREA[second]
def output(raw):
 y=signal.resample_poly(raw,240,343,window=('kaiser',5.))*GAIN
 n=min(round(.012*OUTFS),len(y)//2);fade=np.sin(np.linspace(0,np.pi/2,n))**2;y[:n]*=fade;y[-n:]*=fade[::-1]
 return y

P=C.POINTER(C.c_double);S=C.c_size_t
_lib=C.CDLL(str(HERE/'waveguide_stream.dylib'));_fn=_lib.tube_stream
_fn.restype=C.c_int;_fn.argtypes=[P,P,S,S,C.c_double,C.c_double,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def block(x,a,state):
 x=np.ascontiguousarray(x,dtype=np.float64);a=np.ascontiguousarray(a,dtype=np.float64);s=np.ascontiguousarray(state,dtype=np.float64)
 if x.ndim!=1 or a.ndim!=2 or len(a)!=len(x) or a.shape[1]!=16 or s.shape!=(32,):raise ValueError('列/断面/状態の次元が不整合')
 before=(ah(x),ah(a),ah(s));out=np.empty_like(x);energy=np.empty_like(x);last=np.empty_like(s)
 if not _fn(x.ctypes.data_as(P),a.ctypes.data_as(P),len(x),16,.75,-.85,s.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),energy.ctypes.data_as(P)):raise ValueError('連続声道の有限入力/出力を拒否')
 assert before==(ah(x),ah(a),ah(s));return out,energy,last
def controls(request):
 if not isinstance(request,dict) or set(request)!= {'segments','f0'}:raise ValueError('segments/f0だけを指定する')
 f0=request['f0'];segments=request['segments']
 if type(f0) not in (int,float) or not math.isfinite(f0) or not 70<=f0<=400:raise ValueError('有限F0 70..400Hzが必要')
 if not isinstance(segments,list) or not 1<=len(segments)<=24:raise ValueError('母音列は1..24区間')
 for s in segments:
  if not isinstance(s,dict) or set(s)!= {'vowel','duration_ms'} or s['vowel'] not in AREA or type(s['duration_ms']) is not int or not 125<=s['duration_ms']<=600:raise ValueError('各区間は登録母音と整数125..600ms')
 total=sum(s['duration_ms'] for s in segments)
 if total>6000:raise ValueError('発話は6000ms以内')
 bounds=np.rint(np.r_[0,np.cumsum([s['duration_ms'] for s in segments])]*FS/1000.).astype(np.int64);n=int(bounds[-1]);a=np.empty((n,16));previous=AREA[segments[0]['vowel']]
 for index,s in enumerate(segments):
  start,stop=map(int,bounds[index:index+2]);target=AREA[s['vowel']]
  if index==0:a[start:stop]=target
  else:
   q=np.clip((np.arange(stop-start)/FS)/.10,0.,1.);weight=q*q*(3.-2.*q);a[start:stop]=(1.-weight[:,None])*previous+weight[:,None]*target
  previous=target
 phase=(np.arange(n,dtype=float)*f0/FS+.125)%1.;x=np.zeros(n);harmonics=math.floor(CUTOFF/f0)
 for m in range(1,harmonics+1):x+=2*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))
 return x,a,dict(source_f0=f0,phase_start=.125,harmonics=harmonics,maximum_source_harmonic_hz=harmonics*f0,source_fs=FS,output_fs=OUTFS,source_sha256=ah(x),area_sha256=ah(a),bounds_samples=bounds.tolist(),duration_ms=total)
def generate(request,partition=(4096,)):
 if not isinstance(partition,tuple) or not partition or any(type(v) is not int or not 1<=v<=96000 for v in partition):raise ValueError('内部block寸法が登録範囲外')
 x,a,meta=controls(request);state=np.zeros(32);raw=np.empty(len(x));energy=np.empty(len(x));start=0;calls=0
 while start<len(x):
  stop=min(len(x),start+partition[calls%len(partition)]);y,e,state=block(x[start:stop],a[start:stop],state);raw[start:stop]=y;energy[start:stop]=e;start=stop;calls+=1
 audio=output(raw);meta.update(block_calls=calls,source_and_block_render_calls=calls+1,final_state_sha256=ah(state),raw_sha256=ah(raw),output_sha256=ah(audio),energy_max=float(energy.max()),shared_gain=GAIN,state_reset_only_at_utterance_start=True,source_phase_reset_at_block_boundaries=False)
 return audio,meta,raw,x,a
