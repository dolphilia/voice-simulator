"""音素文脈から固定8残差を作る非ニューラル共有関数。"""
import numpy as np
from local_control import describe,ELIGIBLE,FEATURES
OUTPUT=list(range(1,9));BOUND=.5

def project(v):
 v=np.asarray(v,float)
 if v.ndim!=2 or v.shape[1]!=8 or not np.isfinite(v).all():raise ValueError('有限N×8残差を要求')
 return v*np.minimum(1.,BOUND/np.maximum(np.sum(abs(v),axis=1,keepdims=True),1e-12))
def predict(model,x):
 if model['type']!='spectral-ridge' or model['features']!=FEATURES or model['output_coefficients']!=OUTPUT or model['L1_bound']!=BOUND:raise ValueError('共有16×8回帰仕様が不一致')
 x=np.asarray(x,float);coef=np.array(model['coefficients']);mean=np.array(model['x_mean']);scale=np.array(model['x_scale'])
 if x.ndim!=2 or x.shape[1]!=16 or coef.shape!=(16,8) or mean.shape!=(16,) or scale.shape!=(16,) or not np.isfinite(x).all() or not np.isfinite(coef).all() or not np.isfinite(mean).all() or not np.isfinite(scale).all() or np.min(scale)<=0:raise ValueError('回帰入力/係数/標準化が不正')
 return project(((x-mean)/scale)@coef)
def apply(row,snapshot,parameters,predictor):
 before=[np.asarray(p,float) for p in parameters];out=[p.copy() for p in before];length=np.array(snapshot['duration'],int).reshape(-1,5).sum(1);edges=np.r_[0,np.cumsum(length)]
 if len(before)!=3 or any(p.ndim!=2 or not p.size or not np.isfinite(p).all() for p in before) or before[0].shape[1]!=35 or before[1].shape[1]!=1 or len({len(p) for p in before})!=1 or edges[-1]!=len(before[0]) or len(length)!=len(row['full_context_labels']):raise ValueError('HMM時計/有限3stream形状不一致')
 eligible=[r for r in describe(row) if r['phone'] in ELIGIBLE and any(snapshot['msd'][k]>.5 for k in range(r['label_index']*5,(r['label_index']+1)*5))];values=project(predictor(np.array([r['x'] for r in eligible]))) if eligible else np.empty((0,8));assert values.shape==(len(eligible),8);residual=np.zeros((len(before[0]),8));notes=[]
 for r,y in zip(eligible,values):
  i=r['label_index'];n=length[i];u=(np.arange(n)+.5)/n;env=np.ones(n);lo=u<.1;hi=u>.9;env[lo]=np.sin(u[lo]/.1*np.pi/2)**2;env[hi]=np.sin((1-u[hi])/.1*np.pi/2)**2;residual[edges[i]:edges[i+1]]=env[:,None]*y;notes.append(dict(label_index=i,phone=r['phone'],coefficients=y.tolist(),frame_bounds=[int(edges[i]),int(edges[i+1])]))
 out[0][:,1:9]+=residual
 assert np.max(np.sum(abs(residual),axis=1))<=.5+1e-12 and np.array_equal(out[0][:,0],before[0][:,0]) and np.array_equal(out[0][:,9:],before[0][:,9:]) and np.array_equal(out[1],before[1]) and np.array_equal(out[2],before[2])
 return out,residual,notes

def tests():
 for bad in [np.ones((2,7)),np.full((2,8),np.nan)]:
  try:project(bad)
  except ValueError:pass
  else:raise AssertionError('不正残差を拒否')
 assert np.allclose(np.sum(abs(project(np.ones((2,8)))),axis=1),.5)
 return dict(invalid_dimension_nonfinite_rejected=True,L1_bound_projected=True,fixture_not_quality_evidence=True)
