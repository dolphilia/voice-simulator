"""新しい共有制御用の既知8/未知8文章をfit前に固定する。"""
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
 with b.job(NAME,'setup','共有fit前に診断16文章/2指定/固定群を凍結',reserve_bytes=6000000) as j:
  seen=read(BOUNDARY/'novelty-audit.json')['history_reference_hashes'];texts=set();labels=set();history=dict(seen)
  for n,h in seen.items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I);assert digest(REPO/n)==h;collect(read(REPO/n),texts,labels)
  for directory in [BOUNDARY,SPECTRAL1]:
   for path in directory.rglob('*.json'):
    if path.name=='artifact-seal.json':continue
    collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  rows=[];old=read(JP/'protocol.json')['rows']
  for length in ['short','long']:
   chosen=sorted([r for r in old if r['length']==length],key=lambda r:r['id'])[:4];assert len(chosen)==4
   for group,source in enumerate(chosen):
    r=analyze(source['text']);assert r['full_context_labels']==source['full_context_labels'];r.update(id=source['id'],cohort='legacy_diagnostic',length=length,challenge_group=group);rows.append(r)
  fresh=[];pool=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    r=analyze(text);collision=norm(text) in texts or tuple(r['full_context_labels']) in labels;select=not collision and len(chosen)<4;pool.append(dict(text=text,length=length,collision=collision,selected=select))
    if select:chosen.append(r)
   assert len(chosen)==4,'新しい4入力が不足：fitを始めない'
   for group,r in enumerate(chosen):r.update(id='spectral-fresh-'+str(len(fresh)).zfill(2),cohort='prospective_once',length=length,challenge_group=group);fresh.append(r)
  rows+=fresh;assert len(rows)==16 and len({norm(r['text']) for r in rows})==16
  for r in rows:r.update(requests={'neutral':{'requested_f0':220.,'speed':1.},'higher':{'requested_f0':280.,'speed':1.15}},kana=pyopenjtalk.g2p(r['text'],kana=True))
  deps=dict(read(WORLD/'protocol.json')['dependencies']);deps.update({str((directory/'artifact-seal.json').relative_to(REPO)):digest(directory/'artifact-seal.json') for directory in [BOUNDARY,SPECTRAL1]})
  b.save(HERE/'novelty-audit.json',dict(history_reference_hashes=history,pool_checked_before_output=pool,selected_rows=[dict(id=r['id'],text=r['text'],kana=r['kana']) for r in fresh],protected_confirmation_opened=False,final_quality_independence_claim=False),j)
  b.save(HERE/'protocol.json',dict(registration_sha256=digest(HERE/'registration.json'),rows=rows,variants=['native','direct_non_neural','neural','distilled_non_neural'],conditions=['neutral','higher'],dependencies=deps,diagnostic_renders=128,new_ASR_diag=256,training_utterances=17,training_renders=68,training_ASR_max=136,no_optimization_after_ASR=True,teacher_available_at_unknown_generation=False,quality_certified=False),j)
  b.save(HERE/'engine-contract.json',read(WORLD/'engine-contract.json'),j)
 print('new inputs',[r['text'] for r in fresh],flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
