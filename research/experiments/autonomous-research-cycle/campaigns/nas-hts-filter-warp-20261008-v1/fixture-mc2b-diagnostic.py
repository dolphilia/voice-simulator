"""HTS係数再帰の分離演算と独立libm fmaを照合する。"""
import sys,json,ctypes as C
import numpy as np
sys.path.insert(0,sys.argv[1])
from shape_arrays import mc2b
f=C.CDLL('/usr/lib/libSystem.B.dylib').fma;f.restype=C.c_double;f.argtypes=[C.c_double]*3
vectors=[np.r_[7.,np.zeros(34)],np.r_[7.,.35,np.zeros(33)],np.r_[7.,0.,0.,0.,.2,np.zeros(30)],np.r_[7.,.08*np.cos(np.arange(1,35))/np.arange(1,35)]]
rows=[]
for alpha in (.50,.55,.60):
 for idx,c in enumerate(vectors):
  b=mc2b(c,alpha);split=np.empty(35);fused=np.empty(35);split[-1]=fused[-1]=c[-1]
  for j in range(33,-1,-1):
   split[j]=c[j]-alpha*split[j+1];fused[j]=f(-alpha,float(fused[j+1]),float(c[j]))
  rows.append(dict(alpha=alpha,vector=idx,split_exact=bool(np.array_equal(b,split)),fused_exact=bool(np.array_equal(b,fused)),max_split_error=float(np.max(np.abs(b-split))),max_fused_error=float(np.max(np.abs(b-fused))),different_split_indices=np.flatnonzero(b!=split).tolist()))
print(json.dumps(dict(rows=rows,all_fused_exact=all(r['fused_exact'] for r in rows),diagnostic_only=True,quality_certified=False)))
