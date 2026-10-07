"""同一文章から生成したnative MLPG列を、状態内だけで指定整数長へ補間する。"""
import numpy as np
def warp(parameters,native_duration,output_duration,msd):
 def clock(v):
  a=np.asarray(v)
  if a.ndim!=1 or not np.isfinite(a).all() or np.any(a<1) or np.any(a!=np.floor(a)):
   raise ValueError('状態長は有限の正整数列を要求')
  return a.astype(np.int64)
 old=clock(native_duration);new=clock(output_duration)
 prob=np.asarray(msd,float)
 if old.shape!=new.shape or len(old)%5 or prob.shape!=old.shape or old.sum()!=new.sum():
  raise ValueError('状態数・MSD・総フレーム数の不一致')
 if not np.isfinite(prob).all() or np.any(prob<0) or np.any(prob>1):
  raise ValueError('有限MSD確率を要求')
 params=[np.asarray(p) for p in parameters]
 if len(params)!=3 or any(p.shape!=(int(old.sum()),d) for p,d in zip(params,[35,1,31])):
  raise ValueError('MCP35/LF01/LPF31とnative時計の不一致')
 if any(not np.isfinite(p).all() for p in params):raise ValueError('非有限パラメータを拒否')
 voiced=prob>.5
 if not np.array_equal(params[1][:,0]>0,np.repeat(voiced,old)):
  raise ValueError('native LF0の有声配置とMSDの不一致')
 mix=voiced.reshape(-1,5).any(1)&~voiced.reshape(-1,5).all(1)
 if not np.array_equal(old.reshape(-1,5)[mix],new.reshape(-1,5)[mix]):
  raise ValueError('混在MSDの状態長変更を拒否')
 result=[np.empty((int(new.sum()),p.shape[1]),dtype=p.dtype) for p in params]
 a=c=0;copied=changed=0
 for n,m,v in zip(old,new,voiced):
  n=int(n);m=int(m)
  for k,p in enumerate(params):
   block=p[a:a+n]
   if n==m:result[k][c:c+m]=block
   elif k==1 and not v:
    if not np.all(block==block[0]):raise ValueError('無声LF0のsentinelが一定でない')
    result[k][c:c+m]=block[0]
   else:
    x=(np.arange(n)+.5)/n;y=(np.arange(m)+.5)/m
    for column in range(p.shape[1]):result[k][c:c+m,column]=np.interp(y,x,block[:,column])
  copied+=int(n==m);changed+=int(n!=m);a+=n;c+=m
 old_edge=np.r_[0,np.cumsum(old.reshape(-1,5).sum(1))]
 new_edge=np.r_[0,np.cumsum(new.reshape(-1,5).sum(1))]
 for i in np.flatnonzero(mix):
  for p,q in zip(params,result):
   if p[old_edge[i]:old_edge[i+1]].tobytes()!=q[new_edge[i]:new_edge[i+1]].tobytes():
    raise AssertionError('混在音素のnative数値列を保持できなかった')
 assert all(np.isfinite(q).all() for q in result)
 assert np.array_equal(result[1][:,0]>0,np.repeat(voiced,new))
 return result,dict(changed_states=changed,copied_states=copied,mixed_phone_count=int(mix.sum()),mixed_parameter_blocks_exact=True,interpolation='state中心格子・列ごとの線形補間・端値保持',LF0_unvoiced_sentinel_preserved=True,dynamic_MLPG_constraints_claimed=False)
