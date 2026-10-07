"""既存80整列訓練と、新16確認文章を全出力前に固定する。"""
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
 with b.job(NAME,'setup','時間制御の訓練履歴96分母と新確認16を固定',reserve_bytes=18000000) as j:
  previous=read(COVERAGE/'protocol.json');target=read(COVERAGE/'target-manifest.json');used={r['id'] for r in target['rows'] if r['status']=='accepted'};train=[dict(r) for r in previous['training_rows'] if r['id'] in used];assert len(train)==80
  failed=[dict(id=r['id'],text=r['text'],reason=r['reason']) for r in target['rows'] if r['status']!='accepted'];assert len(failed)==16
  seen=read(COVERAGE/'novelty-audit.json')['history_reference_hashes'];texts=set();labels=set();history=dict(seen)
  for n,h in seen.items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I);assert digest(REPO/n)==h;collect(read(REPO/n),texts,labels)
  for filename in ['protocol.json','novelty-audit.json']:
   path=COVERAGE/filename;collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  rows=[]
  for length in ['short','long']:
   for group,source in enumerate(sorted([r for r in read(JP/'protocol.json')['rows'] if r['length']==length],key=lambda r:r['id'])[:4]):
    r=analyze(source['text']);assert r['full_context_labels']==source['full_context_labels'];r.update(id=source['id'],cohort='legacy_diagnostic',length=length,challenge_group=group);rows.append(r)
  fresh=[];pool=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    r=analyze(text);collision=norm(text) in texts or tuple(r['full_context_labels']) in labels;valid=3<=len(r['full_context_labels'])<=122;select=not collision and valid and len(chosen)<8;pool.append(dict(text=text,length=length,collision=collision,label_count=len(r['full_context_labels']),valid_label_count=valid,selected=select))
    if select:chosen.append(r);texts.add(norm(text));labels.add(tuple(r['full_context_labels']))
   assert len(chosen)==8,'時間制御用新入力が不足：fit/生成前停止'
   for group,r in enumerate(chosen):r.update(id='timing-fresh-'+str(len(fresh)).zfill(2),cohort='prospective_once',length=length,challenge_group=group);fresh.append(r)
  rows+=fresh
  for r in train:r.update(cohort='training_diagnostic',requests={'neutral':{'requested_f0':220.,'speed':1.}},kana=pyopenjtalk.g2p(r['text'],kana=True))
  for r in rows:r.update(requests={'neutral':{'requested_f0':220.,'speed':1.},'higher':{'requested_f0':280.,'speed':1.15}},kana=pyopenjtalk.g2p(r['text'],kana=True))
  dependencies=dict(previous['dependencies']);dependencies[str((COVERAGE/'artifact-seal.json').relative_to(REPO))]=digest(COVERAGE/'artifact-seal.json')
  b.save(HERE/'novelty-audit.json',dict(history_reference_hashes=history,pool_checked_before_output=pool,selected_rows=[dict(id=r['id'],text=r['text'],kana=r['kana']) for r in fresh],protected_confirmation_opened=False,final_quality_independence_claim=False),j)
  b.save(HERE/'protocol.json',dict(registration_sha256=digest(HERE/'registration.json'),rows=rows,training_rows=train,excluded_prior_training=failed,original_training_denominator=96,variants=['native','direct','neural','student'],training_variants=['native','direct','neural','student','oracle'],conditions=['neutral','higher'],dependencies=dependencies,diagnostic_renders=192,training_renders=400,training_ASR_not_independent_quality=True,no_optimization_after_ASR=True,teacher_available_at_unknown_generation=False,quality_certified=False),j)
  b.save(HERE/'engine-contract.json',read(COVERAGE/'engine-contract.json'),j)
 print('時間制御入力固定',len(train),len(fresh),flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
