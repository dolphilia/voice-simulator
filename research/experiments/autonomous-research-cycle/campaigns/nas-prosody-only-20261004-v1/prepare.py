"""同じ目標と固定4特徴への直接/NN蒸留を、確認生成前に固定する。"""
import sys,re,unicodedata,json
from paths import *
sys.path[:0]=[str(HERE),str(SHARED),str(BUNDLE)]
import numpy as np
from japanese_frontend import analyze
from local_control import describe,ELIGIBLE
from centered_projection import project
from prosody_model import INDEX,FEATURES,tests
from research_nn import prediction
import pyopenjtalk

def norm(s):return re.sub(r'[\W_]','',unicodedata.normalize('NFKC',s))
def collect(value,texts,labels):
 if isinstance(value,dict):
  if isinstance(value.get('text'),str):texts.add(norm(value['text']))
  if value.get('full_context_labels'):labels.add(tuple(value['full_context_labels']))
  for v in value.values():collect(v,texts,labels)
 elif isinstance(value,list):
  for v in value:collect(v,texts,labels)
def centered(x,g):
 out=x.copy()
 for k in sorted(set(g)):out[g==k]-=out[g==k].mean(axis=0)
 return out
def projected(x,g):
 out=x.copy()
 for k in sorted(set(g)):out[g==k]=project(out[g==k])
 return out
def mse(x,y,g):return float(np.mean([np.mean((x[g==k]-y[g==k])**2) for k in sorted(set(g))]))

def main():
 b=Budget();reg=read(HERE/'registration.json');old=read(SRES/'protocol.json');contract=read(SRES/'training-contract.json')
 with b.job(NAME,'setup','既存履歴・学習資料・全科学条件をfit前固定',reserve_bytes=3_000_000) as j:
  current_seal=read(CURRENT/'artifact-seal.json')
  for n,h in current_seal['files'].items():assert digest(REPO/n)==h
  assert read(CURRENT/'completion-audit.json')['all_old_hashes_unchanged']
  textset=set();labelset=set();refs={};hist=read(PREP/'history-completion-audit.json')
  for n,h in hist['reference_hashes'].items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I),n
   assert digest(REPO/n)==h,n;collect(read(REPO/n),textset,labelset);refs[n]=h
  collect(read(CURRENT/'protocol.json'),textset,labelset)
  rows=[dict(r,cohort='legacy_diagnostic') for r in read(CURRENT/'protocol.json')['rows'][:8]];new=[]
  for i,text in enumerate(reg['new_texts']):
   row=analyze(text);assert row['full_context_labels'];group=i%4
   requested=[(.85,180),(1.15,180),(.85,260),(1.15,260)][group]
   info={'id':'prosody-fresh-'+str(i).zfill(2),'text':text,'length':'short' if i<4 else 'long','challenge_group':group,'cohort':'prospective_once','requests':{'neutral':{'speed':1.,'requested_f0':220.},'challenge':{'speed':requested[0],'requested_f0':requested[1]}},'split':'prospective_once'}
   collision=norm(text) in textset or tuple(row['full_context_labels']) in labelset
   new.append({'id':info['id'],'text_collision':norm(text) in textset,'label_collision':tuple(row['full_context_labels']) in labelset,'kana':pyopenjtalk.g2p(text,kana=True)})
   assert not collision,info['id']+' 入力が既出。生成/fitは開始しない'
   rows.append({**row,**info})
  x=[];y=[];g=[];used=[]
  for number,item in enumerate(contract['used']):
   row=next(r for r in old['training_rows'] if r['id']==item['id']);path=REPO/row['source_training_input'];assert digest(path)==row['source_sha256']
   snap=read(path)['snapshot']
   ds=[d for d in describe(row) if d['phone'] in ELIGIBLE and any(snap['msd'][k]>.5 for k in range(d['label_index']*5,(d['label_index']+1)*5))]
   assert [d['label_index'] for d in ds]==item['all_eligible_labels']
   assert abs(sum(item['target_half_tone']))<1e-10
   x.extend(d['x'] for d in ds);y.extend(item['target_half_tone']);g.extend([number]*len(ds));used.append({'id':row['id'],'text':row['text'],'source':row['source_training_input'],'sha256':row['source_sha256'],'label_indices':item['all_eligible_labels']})
  assert len(used)==17 and len(y)==209
  assert not {norm(r['text']) for r in used}&{norm(r['text']) for r in rows}
  deps={str(path.relative_to(REPO)):digest(path) for path in [SRES/'training-contract.json',SRES/'target-manifest.json',SRES/'protocol.json',BUNDLE/'mei_normal.htsvoice',BUNDLE/'japanese_frontend.py',BUNDLE/'acoustics.py',BUNDLE/'acoustic_control.py',SHARED/'local_control.py',SHARED/'centered_projection.py',SHARED/'checks.py',SHARED/'objective.py']}
  for f,h in read(SRES/'model-comparison.json')['model_hashes'].items():
   assert digest(SRES/'models'/f)==h;deps[str((SRES/'models'/f).relative_to(REPO))]=h
  b.save(HERE/'novelty-audit.json',{'reference_hashes':refs,'historical_texts':len(textset),'historical_labels':len(labelset),'fresh_rows':new,'protected_paths_not_opened':hist['protected_paths_not_opened'],'previous_cycle_seal_sha256':digest(CURRENT/'artifact-seal.json'),'independent_final_quality_claim':False},j)
  b.save(HERE/'protocol.json',{'registration_sha256':digest(HERE/'registration.json'),'rows':rows,'variants':reg['variants'],'training_used':used,'training_utterances':17,'training_intervals':209,'feature_indices':INDEX,'ridge_lambda':10.,'dependencies':deps,'source_hashes':{q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb','.dylib']},'model_frozen_before_wave':True,'reuse_legacy64':True,'content_groups':21,'missing_reject':True,'quality_certified':False,'no_tuning_after_asr':True},j)
  b.save(HERE/'negative-tests.json',tests(),j);b.save(HERE/'engine-contract.json',read(CURRENT/'engine-contract.json'),j)
  b.save(HERE/'training-input.json',{'x':x,'y':y,'groups':g,'old_training_contract_sha256':digest(SRES/'training-contract.json')},j)
  neural=prediction()
 data=read(HERE/'training-input.json');x=np.asarray(data['x']);y=np.asarray(data['y']);g=np.asarray(data['groups']);nt=np.empty_like(y)
 for k in sorted(set(g)):
  with b.job(NAME,'ai','保存NN制御の訓練文蒸留出力 '+str(k),reserve_bytes=1000):nt[g==k]=project(neural(x[g==k]))
 mean=x[:,INDEX].mean(0);scale=x[:,INDEX].std(0);scale[scale<1e-6]=1.;z=(x[:,INDEX]-mean)/scale;cz=centered(z,g)
 weight=np.array([1./sum(g==k) for k in g]);metrics={};models={}
 for method,target in [('direct_prosody',y),('distilled_prosody',nt)]:
  with b.job(NAME,'train',method+' 固定4係数ridge λ10',reserve_bytes=100000) as j:
   coef=np.linalg.solve(cz.T@(weight[:,None]*cz)+10.*np.eye(4),cz.T@(weight*target))
   model={'type':'prosody-ridge','features':FEATURES,'x_mean':mean.tolist(),'x_scale':scale.tolist(),'coefficients':coef.tolist(),'lambda':10.,'runtime_neural':False,'utterance_tables':0,'training_input_sha256':digest(HERE/'training-input.json'),'teacher_model_sha256':digest(SRES/'models/neural.pt') if method=='distilled_prosody' else None}
   b.save(HERE/'models'/(method+'.json'),model,j);models[method]=digest(HERE/'models'/(method+'.json'));metrics[method]={'training_control_mse_to_wave_target':mse(projected(z@coef,g),y,g),'training_control_mse_to_NN_target':mse(projected(z@coef,g),nt,g),'coefficients':4}
 with b.job(NAME,'audit','全モデル固定と訓練代理誤差を保存',reserve_bytes=100000) as j:
  b.save(HERE/'model-comparison.json',{'new_model_hashes':models,'training_proxy_metrics':metrics,'saved_16feature_training_metrics':read(SRES/'model-comparison.json')['training_mse'],'not_waveform_quality':True,'no_model_selection':True,'research_nn_fixed':True,'new_fits':2,'NN_inference_batches':17,'quality_certified':False},j)
 print({'fresh_collision':0,'models_frozen':models,'training_proxy_metrics':metrics},flush=True)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
