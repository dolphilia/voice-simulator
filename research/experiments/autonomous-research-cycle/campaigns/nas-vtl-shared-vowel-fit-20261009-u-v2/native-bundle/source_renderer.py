"""固定単位LPFだけを変更し、全GSS入力式と駆動列復元を検証する。"""
import ctypes as C
from pathlib import Path
import hashlib
import numpy as np
from scipy import signal
from local_renderer import StateEngine,copy_audio,nsamples
lib=C.CDLL(str(Path(__file__).resolve().parent/'counter.dylib'))
P,S,D=C.c_void_p,C.c_size_t,C.c_double
def bind(n,r,a):
 f=getattr(lib,n);f.restype=r;f.argtypes=a;return f
prepare=bind('counter_prepare',C.c_int,[P]);frames=bind('counter_frames',S,[P]);length=bind('counter_length',S,[P,S]);copy=bind('counter_copy',C.c_int,[P,S,C.POINTER(D),S]);wave=bind('counter_wave',C.c_int,[P,C.c_int]);unvoiced=bind('counter_unvoiced_test',C.c_int,[P,C.c_int]);output_streams=bind('counter_output_streams',S,[P]);output_copy=bind('counter_output_copy',C.c_int,[P,S,C.POINTER(D),S]);settings=bind('counter_settings',C.c_int,[P,C.POINTER(D),S])
def inputs(params,mode,test=False):
 if mode not in [0,1] or len(params)!=3:raise ValueError('固定0/1mode、3stream')
 p=[np.asarray(x,dtype=float) for x in params]
 if any(x.ndim!=2 or not x.size or not np.isfinite(x).all() for x in p) or len({len(x) for x in p})!=1 or p[0].shape[1]<=1 or p[1].shape[1]!=1 or p[2].shape[1]%2!=1:raise ValueError('有限非空の同フレーム3streamと奇数LPF')
 out=[x.copy() for x in p]
 if mode==1:out[2].fill(0);out[2][:,(out[2].shape[1]-1)//2]=1.
 if test:out[1].fill(-1e10)
 return out
def tests():
 p=[np.arange(12.).reshape(4,3),np.full((4,1),np.log(220)),np.full((4,3),.2)];q=inputs(p,1)
 assert np.array_equal(q[0],p[0]) and np.array_equal(q[1],p[1]) and np.array_equal(q[2],np.tile([0,1,0],(4,1)))
 assert all(np.array_equal(a,z) for a,z in zip(inputs(p,0),p))
 assert not prepare(None) and not wave(None,1) and not unvoiced(None,1)
 for mode in [-1,2,float('nan')]:
  try:inputs(p,mode)
  except ValueError:pass
  else:raise AssertionError('未登録modeを拒否')
 return {'MCP_LF0_unchanged':True,'identity_LPF_formula':True,'three_stream_shapes_preserved':True,'invalid_mode_null_rejected':True,'actual_renders':0}
class Engine(StateEngine):
 def parameters(self):
  if not prepare(self.pointer):raise RuntimeError('MLPG準備失敗')
  out=[]
  for s in range(3):
   x=np.empty((frames(self.pointer),length(self.pointer,s)),dtype=float);assert copy(self.pointer,s,x.ctypes.data_as(C.POINTER(D)),x.size);out.append(x)
  return out
 def get_settings(self):
  x=np.empty(9);assert settings(self.pointer,x.ctypes.data_as(C.POINTER(D)),9)
  return dict(zip(['stage','use_log_gain','sampling_frequency','fperiod','alpha','beta','volume','audio_buff_size','stop'],x.tolist()))
 def synthesize(self,params,mode,test=False):
  expected=inputs(params,mode,test);assert (unvoiced if test else wave)(self.pointer,mode),'C波形生成失敗'
  assert output_streams(self.pointer)==3
  hashes=[]
  for s,x in enumerate(expected):
   actual=np.empty_like(x);assert output_copy(self.pointer,s,actual.ctypes.data_as(C.POINTER(D)),actual.size);assert np.array_equal(actual,x),'GSS列が登録式と不一致';hashes.append(hashlib.sha256(actual.astype('<f8').tobytes()).hexdigest())
  for s,x in enumerate(params):
   restored=np.empty_like(x);assert copy(self.pointer,s,restored.ctypes.data_as(C.POINTER(D)),x.size);assert np.array_equal(restored,x),'駆動列復元失敗'
  audio=np.empty(nsamples(self.pointer));copy_audio(self.pointer,audio.ctypes.data_as(C.POINTER(D)),len(audio));audio=signal.resample_poly(audio/32768,1,2)
  n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
  return audio,hashes
