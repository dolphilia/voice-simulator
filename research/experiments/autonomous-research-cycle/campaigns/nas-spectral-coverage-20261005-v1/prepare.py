"""全入力を教師生成/fit前に固定する。"""
from paths import *
import sys,re,unicodedata
sys.path[:0]=[str(BUNDLE),str(SHARED)]
from japanese_frontend import analyze
import pyopenjtalk
def norm(s):return re.sub(r'[\W_]','',unicodedata.normalize('NFKC',s))
def collect(v,texts,labels):
 if isinstance(v,dict):
  if isinstance(v.get('text'),str):texts.add(norm(v['text']))
  if v.get('full_context_labels'):labels.add(tuple(v['full_context_labels']))
  for x in v.values():collect(x,texts,labels)
 elif isinstance(v,list):
  for x in v:collect(x,texts,labels)
def main():
 b=Budget();reg=read(HERE/'registration.json')
 with b.job(NAME,'setup','訓練96/新確認16の全文と固定指定を凍結',reserve_bytes=18000000) as j:
  seen=read(SPECTRAL2/'novelty-audit.json')['history_reference_hashes'];texts=set();labels=set();history=dict(seen)
  for n,h in seen.items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I);assert digest(REPO/n)==h;collect(read(REPO/n),texts,labels)
  for filename in ['protocol.json','novelty-audit.json']:
   path=SPECTRAL2/filename;collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  original=[dict(q['row']) for q in read(SPECTRAL1/'alignment-manifest.json')['rows']];assert len(original)==17
  pool=[];new=[]
  for length,count in [('short',38),('long',41)]:
   chosen=[]
   for text in reg['training_pool_'+length]:
    r=analyze(text);collision=norm(text) in texts or tuple(r['full_context_labels']) in labels;valid=3<=len(r['full_context_labels'])<=122;select=not collision and valid and len(chosen)<count
    pool.append(dict(text=text,length=length,collision=collision,label_count=len(r['full_context_labels']),valid_label_count=valid,selected=select))
    if select:chosen.append(r);texts.add(norm(text));labels.add(tuple(r['full_context_labels']))
   assert len(chosen)==count,'新訓練入力不足'
   for r in chosen:
    r.update(id='coverage-train-'+str(len(new)).zfill(2),length=length,cohort='training_diagnostic',challenge_group=len(new)%8);new.append(r)
  train=original+new
  assert len(train)==96 and sum(r['length']=='short' for r in train)==48 and len({norm(r['text']) for r in train})==96
  rows=[];old=read(JP/'protocol.json')['rows']
  for length in ['short','long']:
   for g,r in enumerate(sorted([r for r in old if r['length']==length],key=lambda r:r['id'])[:4]):
    row=analyze(r['text']);assert row['full_context_labels']==r['full_context_labels'];row.update(id=r['id'],cohort='legacy_diagnostic',length=length,challenge_group=g);rows.append(row)
  fresh=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    r=analyze(text);collision=norm(text) in texts or tuple(r['full_context_labels']) in labels;valid=3<=len(r['full_context_labels'])<=122;select=not collision and valid and len(chosen)<8
    pool.append(dict(text=text,length=length,cohort='prospective_once',collision=collision,valid_label_count=valid,selected=select))
    if select:chosen.append(r);texts.add(norm(text));labels.add(tuple(r['full_context_labels']))
   assert len(chosen)==8,'新確認入力不足'
   for g,r in enumerate(chosen):r.update(id='coverage-fresh-'+str(len(fresh)).zfill(2),cohort='prospective_once',length=length,challenge_group=g);fresh.append(r)
  rows+=fresh
  for r in train:r.update(cohort='training_diagnostic',requests={'neutral':{'requested_f0':220.,'speed':1.}},kana=pyopenjtalk.g2p(r['text'],kana=True))
  for r in rows:r.update(requests={'neutral':{'requested_f0':220.,'speed':1.},'higher':{'requested_f0':280.,'speed':1.15}},kana=pyopenjtalk.g2p(r['text'],kana=True))
  oldmodel={p.name:digest(p) for p in (SPECTRAL2/'models').iterdir()}
  dependencies=dict(read(SPECTRAL2/'protocol.json')['dependencies']);dependencies[str((SPECTRAL2/'artifact-seal.json').relative_to(REPO))]=digest(SPECTRAL2/'artifact-seal.json')
  b.save(HERE/'novelty-audit.json',dict(history_reference_hashes=history,pool_checked_before_output=pool,new_training_rows=[dict(id=r['id'],text=r['text']) for r in new],selected_rows=[dict(id=r['id'],text=r['text'],kana=r['kana']) for r in fresh],protected_confirmation_opened=False,final_quality_independence_claim=False),j)
  b.save(HERE/'protocol.json',dict(registration_sha256=digest(HERE/'registration.json'),rows=rows,training_rows=train,original_training_ids=[r['id'] for r in original],variants=reg['variants'],conditions=['neutral','higher'],dependencies=dependencies,frozen17_model_hashes=oldmodel,diagnostic_renders=336,training_renders=672,training_ASR_not_independent_quality=True,no_optimization_after_ASR=True,teacher_available_at_unknown_generation=False,quality_certified=False),j)
  b.save(HERE/'engine-contract.json',read(SPECTRAL2/'engine-contract.json'),j)
 print('入力固定',len(train),len(fresh),flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
