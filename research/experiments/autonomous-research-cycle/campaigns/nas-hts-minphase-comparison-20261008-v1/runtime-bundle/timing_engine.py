"""対応版HTSエンジンの状態長のみを、MLPG前に変更する。"""
from source_renderer import Engine as NativeEngine
import ctypes as C,numpy as np
from pathlib import Path
_lib=C.CDLL(str(Path(__file__).resolve().parent/'timing.dylib'))
set_duration=_lib.timing_apply;set_duration.restype=C.c_int;set_duration.argtypes=[C.c_void_p,C.POINTER(C.c_size_t),C.c_size_t]
vari_count=_lib.timing_vari_count;vari_count.restype=C.c_size_t;vari_count.argtypes=[C.c_void_p]
vari_copy=_lib.timing_vari_copy;vari_copy.restype=C.c_int;vari_copy.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_size_t]
class Engine(NativeEngine):
 def variance(self):
  n=vari_count(self.pointer);assert n>0;x=np.empty(n,float);assert vari_copy(self.pointer,x.ctypes.data_as(C.POINTER(C.c_double)),n);assert np.isfinite(x).all();return x

 def modify_duration(self,values):
  before=self.snapshot();variance=self.variance();v=np.asarray(values)
  if v.ndim!=1 or len(v)!=self.count or not np.isfinite(v).all() or np.any(v<1) or np.any(v!=np.floor(v)) or v.sum()!=sum(before['duration']):raise ValueError('状態長の形状/整数/総時間が不正')
  x=v.astype(np.uintp);assert x.dtype.itemsize==C.sizeof(C.c_size_t)
  if not set_duration(self.pointer,x.ctypes.data_as(C.POINTER(C.c_size_t)),len(x)):raise ValueError('MLPG前の状態長更新を内部検査が拒否')
  after=self.snapshot();assert np.array_equal(variance,self.variance());assert after['duration']==v.tolist()
  for k in ['msd','means','layout']:assert before[k]==after[k]
  return before,after
def tests():
 assert not set_duration(None,None,0)
 return dict(null_rejected=True,fixture_not_quality_evidence=True)
