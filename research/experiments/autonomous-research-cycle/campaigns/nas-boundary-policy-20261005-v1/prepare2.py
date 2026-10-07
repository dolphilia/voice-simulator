"""既知4・前向き新8を全観測履歴照合後に出力前固定する。"""
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
 with b.job(NAME,'setup','先生12入力の全履歴照合・出力前固定',reserve_bytes=3_000_000) as j:
  seen=read(WORLD/'novelty-audit.json')['history_reference_hashes'];texts=set();labels=set()
  for n,h in seen.items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I);assert digest(REPO/n)==h;collect(read(REPO/n),texts,labels)
  history=dict(seen)
  for path in WORLD.rglob('*.json'):
   if path.name=='artifact-seal.json':continue
   collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  rows=[dict(row,cohort='legacy_diagnostic') for row in read(JP/'protocol.json')['rows']]
  for path in JP.rglob('*.json'):
   if path.name=='artifact-seal.json':continue
   collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  pool=[];fresh=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    row=analyze(text);collision=norm(text) in texts or tuple(row['full_context_labels']) in labels;select=not collision and len(chosen)<4;pool.append({'text':text,'length':length,'text_collision':norm(text) in texts,'label_collision':tuple(row['full_context_labels']) in labels,'selected':select})
    if select:chosen.append(row)
   assert len(chosen)==4,'出力前に新4文が不足：生成を始めない'
   for group,row in enumerate(chosen):
    row.update(id='boundary-fresh-'+str(len(fresh)).zfill(2),cohort='prospective_once',length=length,challenge_group=group,kana=pyopenjtalk.g2p(row['text'],kana=True));fresh.append(row)
  rows+=fresh;assert len(rows)==20 and len({norm(r['text']) for r in rows})==20
  deps=dict(read(WORLD/'protocol.json')['dependencies'])
  deps[str((JP/'artifact-seal.json').relative_to(REPO))]=digest(JP/'artifact-seal.json')
  b.save(HERE/'novelty-audit.json',{'history_reference_hashes':history,'historical_texts':len(texts),'historical_labels':len(labels),'pool_checked_before_output':pool,'selected_rows':[{'id':r['id'],'text':r['text'],'kana':r['kana']} for r in fresh],'protected_unused_confirmation_opened':False,'final_quality_independence_claim':False},j)
  b.save(HERE/'protocol.json',{'registration_sha256':digest(HERE/'registration.json'),'rows':rows,'fresh_rows':fresh,'dependencies':deps,'teachers':['kokoro','jvnv'],'conditions':['neutral'],'teacher_generation_new':16,'old_teacher_cache_reuse':24,'WORLD_analysis_resynthesis':16,'ASR_new_planned_max':480,'new_groups':7,'legacy_groups':'all/short/long/group0..3の7群。旧12文診断' ,'source_hashes':{q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb']},'no_optimization_after_ASR':True,'legacy_teacher_seed':'旧metadataの20261002を保持。新生成は42、whole教師対照で同seed因果主張なし','quality_certified':False},j)
  b.save(HERE/'engine-contract.json',read(WORLD/'engine-contract.json'),j)
 print({'legacy':[r['text'] for r in rows[:12]],'fresh':[r['text'] for r in fresh],'excluded_pool':[r['text'] for r in pool if r['text_collision'] or r['label_collision']]},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
