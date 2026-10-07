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
  used=read(SRES/'training-contract.json')['used'];old=read(SRES/'protocol.json');old_rows={r['id']:r for r in old['training_rows']};rows=[]
  for length in ['short','long']:
   chosen=sorted([r for r in used if r['length']==length],key=lambda r:r['id'])[:2];assert len(chosen)==2
   for group,r in enumerate(chosen):
    source=old_rows[r['id']];row=analyze(r['text']);assert row['full_context_labels']==source['full_context_labels']
    assert digest(REPO/source['teacher_wav'])==source['teacher_wav_sha256'] and digest(REPO/source['teacher_metadata'])==source['teacher_metadata_sha256']
    row.update(id=r['id'],cohort='legacy_diagnostic',length=length,challenge_group=group,old_teacher_wav=source['teacher_wav'],old_teacher_wav_sha256=source['teacher_wav_sha256'],old_teacher_metadata=source['teacher_metadata'],old_teacher_metadata_sha256=source['teacher_metadata_sha256'],kana=pyopenjtalk.g2p(r['text'],kana=True));rows.append(row)
  pool=[];fresh=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    row=analyze(text);collision=norm(text) in texts or tuple(row['full_context_labels']) in labels;select=not collision and len(chosen)<4;pool.append({'text':text,'length':length,'text_collision':norm(text) in texts,'label_collision':tuple(row['full_context_labels']) in labels,'selected':select})
    if select:chosen.append(row)
   assert len(chosen)==4,'出力前に新4文が不足：生成を始めない'
   for group,row in enumerate(chosen):
    row.update(id='teacher-fresh-'+str(len(fresh)).zfill(2),cohort='prospective_once',length=length,challenge_group=group,kana=pyopenjtalk.g2p(row['text'],kana=True));fresh.append(row)
  rows+=fresh;assert len(rows)==12 and len({norm(r['text']) for r in rows})==12
  deps=dict(read(WORLD/'protocol.json')['dependencies'])
  for row in rows[:4]:
   for key in ['old_teacher_wav','old_teacher_metadata']:deps[row[key]]=digest(REPO/row[key])
  b.save(HERE/'novelty-audit.json',{'history_reference_hashes':history,'historical_texts':len(texts),'historical_labels':len(labels),'pool_checked_before_output':pool,'selected_rows':[{'id':r['id'],'text':r['text'],'kana':r['kana']} for r in fresh],'protected_unused_confirmation_opened':False,'final_quality_independence_claim':False},j)
  b.save(HERE/'protocol.json',{'registration_sha256':digest(HERE/'registration.json'),'rows':rows,'dependencies':deps,'teachers':['kokoro','jvnv'],'conditions':['neutral'],'teacher_generation_new':20,'old_teacher_cache_reuse':4,'WORLD_analysis_resynthesis':24,'ASR_new_planned':96,'new_groups':7,'legacy_groups':'all/short/long/group0/group1の5群。群2/3を作らず旧4文の診断へ限定','source_hashes':{q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.sb']},'no_optimization_after_ASR':True,'legacy_teacher_seed':'旧metadataの20261002を保持。新生成は42、whole教師対照で同seed因果主張なし','quality_certified':False},j)
  b.save(HERE/'engine-contract.json',read(WORLD/'engine-contract.json'),j)
 print({'legacy':[r['text'] for r in rows[:4]],'fresh':[r['text'] for r in fresh],'excluded_pool':[r['text'] for r in pool if r['text_collision'] or r['label_collision']]},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
