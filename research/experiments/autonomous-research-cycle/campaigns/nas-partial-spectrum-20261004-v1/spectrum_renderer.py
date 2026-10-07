"""固定0.75倍のMCPだけを変更し、駆動列は復元する。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
from local_renderer import StateEngine,copy_audio,nsamples
lib=C.CDLL(str(Path(__file__).resolve().parent/'counter.dylib'))
P,S,D=C.c_void_p,C.c_size_t,C.c_double
def bind(name,result,args):
 f=getattr(lib,name);f.restype=result;f.argtypes=args;return f
prepare=bind('counter_prepare',C.c_int,[P])
frames=bind('counter_frames',S,[P]);length=bind('counter_length',S,[P,S])
copy=bind('counter_copy',C.c_int,[P,S,C.POINTER(D),S])
wave=bind('counter_wave',C.c_int,[P,D])
output_streams=bind('counter_output_streams',S,[P])
output=bind('counter_output',D,[P,S,S,S])
settings=bind('counter_settings',C.c_int,[P,C.POINTER(D),S])
def inputs(parameters,factor):
 if factor not in (1.,.75):raise ValueError('事前固定された倍率だけを要求します')
 if len(parameters)!=3:raise ValueError('3streamを要求します')
 p=[np.asarray(x,dtype=float) for x in parameters]
 if any(x.ndim!=2 or not x.size or not np.isfinite(x).all() for x in p):raise ValueError('非空・有限・二次元列')
 if len({len(x) for x in p})!=1 or p[0].shape[1]<=1 or p[1].shape[1]!=1 or p[2].shape[1]%2!=1:raise ValueError('stream形状不正')
 out=[x.copy() for x in p];out[0][:,1:]*=factor;return out
def tests():
 p=[np.arange(12.).reshape(4,3),np.full((4,1),np.log(220)),np.ones((4,3))]
 q=inputs(p,.75)
 assert np.array_equal(q[0][:,0],p[0][:,0]) and np.array_equal(q[0][:,1:],p[0][:,1:]*.75)
 assert all(np.array_equal(q[i],p[i]) for i in (1,2))
 assert all(np.array_equal(a,z) for a,z in zip(inputs(p,1.),p))
 for factor in (0.,.5,float('nan'),float('inf')):
  try:inputs(p,factor)
  except ValueError:pass
  else:raise AssertionError('未登録倍率')
 assert not prepare(None) and not wave(None,.75)
 return {'factor_only':True,'c0_lf0_lpf_preserved':True,'unregistered_factor_rejected':True,'actual_render_calls':0}
class Engine(StateEngine):
 def parameters(self):
  if not prepare(self.pointer):raise RuntimeError('MLPG不通過')
  rows=[]
  for s in range(3):
   x=np.empty((frames(self.pointer),length(self.pointer,s)),dtype=float)
   if not copy(self.pointer,s,x.ctypes.data_as(C.POINTER(D)),x.size):raise RuntimeError('stream読出し失敗')
   rows.append(x)
  return rows
 def get_settings(self):
  x=np.empty(9,dtype=float);assert settings(self.pointer,x.ctypes.data_as(C.POINTER(D)),9)
  return dict(zip(('stage','use_log_gain','sampling_frequency','fperiod','alpha','beta','volume','audio_buff_size','stop'),x.tolist()))
 def synthesize(self,parameters,factor):
  expected=inputs(parameters,factor)
  if not wave(self.pointer,factor):raise RuntimeError('波形生成失敗')
  assert output_streams(self.pointer)==3
  hashes=[]
  import hashlib
  for s,x in enumerate(expected):
   actual=np.array([[output(self.pointer,s,f,j) for j in range(x.shape[1])] for f in range(len(x))])
   assert np.array_equal(actual,x),'vocoder入力が倍率式と異なります'
   hashes.append(hashlib.sha256(actual.astype('<f8').tobytes()).hexdigest())
  for s,x in enumerate(parameters):
   restored=np.empty_like(x);assert copy(self.pointer,s,restored.ctypes.data_as(C.POINTER(D)),x.size)
   assert np.array_equal(restored,x),'駆動列が復元されません'
  audio=np.empty(nsamples(self.pointer),dtype=float)
  copy_audio(self.pointer,audio.ctypes.data_as(C.POINTER(D)),len(audio))
  audio=signal.resample_poly(audio/32768,1,2)
  n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2
  audio[:n]*=env;audio[-n:]*=env[::-1]
  return audio,hashes
