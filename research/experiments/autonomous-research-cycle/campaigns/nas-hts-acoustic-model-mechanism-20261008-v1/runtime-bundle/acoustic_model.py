"""共有文脈HMMのMCP分布だけを交換する。波形や教師から係数を推定しない。"""
import ctypes as C
from pathlib import Path
import numpy as np
from timing_engine import Engine as NativeEngine
from hts_arrays import ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'mcp_model.dylib'))
_transfer=_lib.mcp_transfer;_transfer.restype=C.c_int;_transfer.argtypes=[C.c_void_p,C.c_void_p]
_count=_lib.mcp_gv_count;_count.restype=C.c_size_t;_count.argtypes=[C.c_void_p]
_copy=_lib.mcp_gv_copy;_copy.restype=C.c_int;_copy.argtypes=[C.c_void_p,C.POINTER(C.c_double),C.c_size_t]
def gv(engine):
 n=_count(engine.pointer);assert n>0;x=np.empty(n);assert _copy(engine.pointer,x.ctypes.data_as(C.POINTER(C.c_double)),n);assert np.isfinite(x).all();return x
class Engine(NativeEngine):
 def transfer_mcp(self,donor):
  before=self.snapshot();variance=self.variance();protected_gv=gv(self);settings=self.get_settings()
  source=donor.snapshot();source_variance=donor.variance();source_gv=gv(donor);source_settings=donor.get_settings()
  if self.layout[0]!=(35,3) or self.layout!=donor.layout or self.count!=donor.count:raise ValueError('MCP状態・window互換性が不足')
  n=self.count*105
  if not _transfer(self.pointer,donor.pointer):raise ValueError('MLPG前のMCP分布交換を内部検査が拒否')
  after=self.snapshot();new_variance=self.variance()
  for key in ('duration','msd','layout'):assert before[key]==after[key]
  assert before['means'][1:]==after['means'][1:] and after['means'][0]==source['means'][0]
  assert np.array_equal(new_variance[:n],source_variance[:n]) and np.array_equal(new_variance[n:],variance[n:])
  assert np.array_equal(protected_gv,gv(self)) and self.get_settings()==settings
  assert donor.snapshot()==source and np.array_equal(donor.variance(),source_variance) and np.array_equal(gv(donor),source_gv) and donor.get_settings()==source_settings
  return dict(state_MCP_donor_exact=True,other_state_distributions_exact=True,duration_MSD_windows_exact=True,GV_and_settings_exact=True,donor_unmodified=True,
   before_MCP_mean_sha256=ah(before['means'][0]),after_MCP_mean_sha256=ah(after['means'][0]),before_MCP_variance_sha256=ah(variance[:n]),after_MCP_variance_sha256=ah(new_variance[:n]),
   donor_MCP_mean_sha256=ah(source['means'][0]),donor_MCP_variance_sha256=ah(source_variance[:n]),fixed_shared_HMM=True,neural_model=False,utterance_lookup=False)
def tests():
 assert not _transfer(None,None) and not _count(None) and not _copy(None,None,0)
 return dict(null_rejected=True,actual_render=0)
