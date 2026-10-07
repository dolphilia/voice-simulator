"""教師音声なしに、共有文脈関数から音素内の時計を生成する。"""
import numpy as np,re
from local_control import describe,FEATURES as CONTEXT
PHONES=['a','i','u','e','o','A','I','U','E','O','N','cl','b','d','g','p','t','k','m','n','r','s','z','f','h','w','y','sh','ch','ts','j','by','dy','gy','py','ty','ky','my','ny','ry','hy','v']
FEATURES=CONTEXT+['phone_'+p for p in PHONES]
LOWER=.8;UPPER=1.25;LOGBOUND=np.log(UPPER)
def descriptions(row):
 out=[]
 for r in describe(row):
  if r['phone'] in ['sil','pau']:continue
  if r['phone'] not in PHONES:raise ValueError('時間制御の未登録音素 '+r['phone'])
  out.append(dict(r,x=r['x']+[float(r['phone']==p) for p in PHONES]))
 return out
def projected(v):
 x=np.asarray(v,float)
 if x.ndim!=1 or not np.isfinite(x).all():raise ValueError('有限1次元の時間残差を要求')
 return np.clip(x,-LOGBOUND,LOGBOUND)
def predict(model,x):
 if model['type']!='timing-ridge' or model['features']!=FEATURES or model['duration_ratio_bounds']!=[LOWER,UPPER]:raise ValueError('固定共有時間回帰の仕様不一致')
 x=np.asarray(x,float);c=np.array(model['coefficients']);m=np.array(model['x_mean']);s=np.array(model['x_scale']);d=len(FEATURES)
 if x.ndim!=2 or x.shape[1]!=d or c.shape!=(d,) or m.shape!=(d,) or s.shape!=(d,) or not all(np.isfinite(q).all() for q in [x,c,m,s]) or np.min(s)<=0:raise ValueError('時間回帰の形状/有限性/標準化が不正')
 return projected(((x-m)/s)@c)
def integer_sum(w,total,lower,upper):
 w=np.asarray(w,float);lo=np.asarray(lower,int);hi=np.asarray(upper,int)
 if w.shape!=lo.shape or lo.shape!=hi.shape or np.any(lo>hi) or not np.isfinite(w).all() or np.any(w<=0) or not sum(lo)<=total<=sum(hi):raise ValueError('整数時間配分が不正')
 if not len(w):raise ValueError('空の配分')
 a,b=-40.,40.
 for _ in range(100):
  mid=(a+b)/2;desired=np.clip(w*np.exp(mid),lo,hi)
  if desired.sum()<total:a=mid
  else:b=mid
 desired=np.clip(w*np.exp((a+b)/2),lo,hi);n=np.floor(desired+1e-10).astype(int);n=np.minimum(hi,np.maximum(lo,n));remain=int(total-n.sum())
 if remain>0:
  order=np.argsort(-(desired-n),kind='stable')
  for i in order:
   if remain and n[i]<hi[i]:n[i]+=1;remain-=1
 elif remain<0:
  order=np.argsort(desired-n,kind='stable')
  for i in order:
   if remain and n[i]>lo[i]:n[i]-=1;remain+=1
 if remain or n.sum()!=total or np.any(n<lo) or np.any(n>hi):raise ValueError('整数配分の合計/範囲不成立')
 return n
def durations(row,snapshot,predictor):
 duration=np.array(snapshot['duration'],int).reshape(-1,5);length=duration.sum(1)
 if len(length)!=len(row['full_context_labels']) or np.any(duration<1):raise ValueError('HMM状態時間と音素ラベルの不一致')
 r=descriptions(row);indices=[q['label_index'] for q in r]
 if not indices:raise ValueError('発話音素が空')
 value=projected(predictor(np.array([q['x'] for q in r])));assert len(value)==len(indices)
 wanted=length.copy();newduration=duration.copy();notes=[]
 if np.any(value):
  l=length[indices];low=np.maximum(5,np.ceil(LOWER*l).astype(int));high=np.maximum(low,np.floor(UPPER*l).astype(int));wanted[indices]=integer_sum(l*np.exp(value),int(l.sum()),low,high)
  for i in indices:
   if wanted[i]!=length[i]:newduration[i]=integer_sum(duration[i].astype(float),int(wanted[i]),np.ones(5,int),np.full(5,wanted[i]-4,int))
 for q,y in zip(r,value):
  i=q['label_index'];notes.append(dict(label_index=i,phone=q['phone'],predicted_log_ratio=float(y),native_frames=int(length[i]),output_frames=int(wanted[i])))
 assert newduration.sum()==duration.sum() and np.all(newduration>=1)
 for i,q in enumerate(row['full_context_labels']):
  if re.search(r'\-([^+]+)\+',q)[1] in ['sil','pau']:assert np.array_equal(newduration[i],duration[i])
 if not np.any(value):assert np.array_equal(newduration,duration)
 return newduration.ravel().tolist(),notes
def tests():
 for x in [np.array([np.nan]),np.ones((2,1))]:
  try:projected(x)
  except ValueError:pass
  else:raise AssertionError('時間残差の負例を拒否')
 assert np.array_equal(integer_sum([10,20,30],60,[8,16,24],[12,25,37]),[10,20,30])
 for values in [[100,1,1],[1,100,1],[1,1,100]]:
  n=integer_sum(values,60,[8,16,24],[12,25,37]);assert sum(n)==60 and np.all(n>=np.array([8,16,24])) and np.all(n<=np.array([12,25,37]))
 try:integer_sum([1,2],4,[3,3],[5,5])
 except ValueError:pass
 else:raise AssertionError('不可能な時間合計を拒否')
 return dict(nonfinite_shape_infeasible_sum_rejected=True,integer_total_and_bounds_preserved=True,fixture_not_quality_evidence=True)
