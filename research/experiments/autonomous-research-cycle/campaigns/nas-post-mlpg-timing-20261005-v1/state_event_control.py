"""駆動MSDが混在する音素の状態時計を固定し、均質状態だけを再配分する。"""
import numpy as np,re
from timing_control import descriptions,projected,integer_sum,LOWER,UPPER
def durations(row,snapshot,predictor):
 duration=np.array(snapshot['duration'],int).reshape(-1,5)
 prob=np.asarray(snapshot['msd'],float)
 if not np.isfinite(prob).all() or np.any(prob<0) or np.any(prob>1):raise ValueError('MSDの有限確率を要求')
 mask=prob.reshape(-1,5)>.5
 length=duration.sum(1)
 if len(length)!=len(row['full_context_labels']) or mask.shape!=duration.shape or np.any(duration<1):
  raise ValueError('HMM状態時計/有声判定と音素ラベルの不一致')
 r=descriptions(row);indices=[q['label_index'] for q in r]
 if not indices:raise ValueError('発話音素が空')
 value=projected(predictor(np.array([q['x'] for q in r])));assert len(value)==len(indices)
 mixed=np.any(mask,axis=1)&~np.all(mask,axis=1)
 flexible=[i for i in indices if not mixed[i]]
 wanted=length.copy();newduration=duration.copy()
 effective=np.array([y for i,y in zip(indices,value) if not mixed[i]])
 if flexible and np.any(effective):
  l=length[flexible];low=np.maximum(5,np.ceil(LOWER*l).astype(int));high=np.maximum(low,np.floor(UPPER*l).astype(int))
  wanted[flexible]=integer_sum(l*np.exp(effective),int(l.sum()),low,high)
  for i in flexible:
   if wanted[i]!=length[i]:
    newduration[i]=integer_sum(duration[i].astype(float),int(wanted[i]),np.ones(5,int),np.full(5,wanted[i]-4,int))
 notes=[]
 for q,y in zip(r,value):
  i=q['label_index'];notes.append(dict(label_index=i,phone=q['phone'],predicted_log_ratio=float(y),native_frames=int(length[i]),output_frames=int(wanted[i]),mixed_MSD_fixed=bool(mixed[i])))
 assert newduration.sum()==duration.sum() and np.all(newduration>=1)
 for i,q in enumerate(row['full_context_labels']):
  if mixed[i] or re.search(r'\-([^+]+)\+',q)[1] in ['sil','pau']:
   assert np.array_equal(newduration[i],duration[i])
 if not np.any(value):assert np.array_equal(newduration,duration)
 return newduration.ravel().tolist(),notes
