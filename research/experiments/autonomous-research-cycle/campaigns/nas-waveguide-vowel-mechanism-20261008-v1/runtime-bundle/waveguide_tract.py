"""断面積を直接入力する正規化波の共有声道primitive。保存音声・HMM・学習なし。"""
import ctypes as C,hashlib
from pathlib import Path
import numpy as np
P=C.POINTER(C.c_double);S=C.c_size_t
_lib=C.CDLL(str(Path(__file__).resolve().parent/'waveguide_tract.dylib'))
_fn=_lib.tube_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,S,S,C.c_double,C.c_double,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def render(drive,area,rg=.75,rl=-.85):
 x=np.ascontiguousarray(drive,dtype=np.float64);a=np.ascontiguousarray(area,dtype=np.float64)
 if x.ndim!=1 or not len(x) or a.ndim!=2 or len(x)!=len(a):raise ValueError('駆動列と同標本数の2D断面積が必要')
 before=(ah(x),ah(a));out=np.empty_like(x);energy=np.empty_like(x)
 if not _fn(x.ctypes.data_as(P),a.ctypes.data_as(P),len(x),a.shape[1],rg,rl,out.ctypes.data_as(P),energy.ctypes.data_as(P)):
  raise ValueError('断面積/終端反射/駆動/有限出力の内部検査に不通過')
 assert before==(ah(x),ah(a));return out,energy
def tests():
 assert not _fn(None,None,0,0,0.,0.,None,None)
 invalid=0
 for value in (np.nan,np.inf,0.,.049,12.001):
  a=np.ones((8,24));a[3,4]=value
  try:render(np.zeros(8),a)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の断面積を拒否しない')
 for value in (np.nan,np.inf,1.,-1.):
  try:render(np.zeros(8),np.ones((8,24)),rg=value)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の終端反射を拒否しない')
 for x,a in ((np.zeros(8),np.ones((8,1))),(np.zeros(8),np.ones((8,45))),(np.full(8,np.nan),np.ones((8,24)))):
  try:render(x,a)
  except ValueError:invalid+=1
  else:raise AssertionError('登録外の駆動/sectionを拒否しない')
 return dict(null_rejected=True,invalid_arrays_or_reflections_rejected=invalid)
