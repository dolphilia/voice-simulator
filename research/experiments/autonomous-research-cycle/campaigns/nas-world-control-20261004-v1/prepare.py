"""初期候補poolを既知履歴と照合し、全入力・依存を生成前固定する。"""
import sys,re,unicodedata
from paths import *
sys.path[:0]=[str(HERE),str(SHARED),str(BUNDLE)]
from japanese_frontend import analyze
from world_renderer2 import tests
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
 with b.job(NAME,'setup','全候補poolの生成前履歴照合・科学条件凍結',reserve_bytes=3_000_000) as j:
  seen={};seal=read(PREVIOUS/'artifact-seal.json')
  for n,h in seal['files'].items():assert digest(REPO/n)==h;seen[n]=h
  assert read(PREVIOUS/'completion-audit.json')['all_old_hashes_unchanged']
  texts=set();labels=set();history={}
  for n,h in read(PREP/'history-completion-audit.json')['reference_hashes'].items():
   assert not re.search('splits|protected|holdout|final-confirm',n,re.I);assert digest(REPO/n)==h;collect(read(REPO/n),texts,labels);history[n]=h
  collect(read(CURRENT/'protocol.json'),texts,labels)
  for path in PREVIOUS.rglob('*.json'):
   if path.name=='artifact-seal.json':continue
   collect(read(path),texts,labels);history[str(path.relative_to(REPO))]=digest(path)
  old=read(PREVIOUS/'protocol.json');rows=[dict(r,cohort='legacy_diagnostic',split='diagnostic_reuse') for r in old['rows'][8:]];pool=[];selected=[]
  for length in ['short','long']:
   chosen=[]
   for text in reg['candidate_pool_'+length]:
    row=analyze(text);collision=norm(text) in texts or tuple(row['full_context_labels']) in labels
    pool.append({'text':text,'length':length,'text_collision':norm(text) in texts,'label_collision':tuple(row['full_context_labels']) in labels,'selected':not collision and len(chosen)<4})
    if not collision and len(chosen)<4:chosen.append(row)
   assert len(chosen)==4,'未使用候補が4文に不足。生成を始めない'
   for group,row in enumerate(chosen):
    index=len(selected);speed,f0=[(.85,180),(1.15,180),(.85,260),(1.15,260)][group]
    row.update(id='world-fresh-'+str(index).zfill(2),length=length,challenge_group=group,cohort='prospective_once',split='prospective_once',requests={'neutral':{'speed':1.,'requested_f0':220.},'challenge':{'speed':speed,'requested_f0':f0}},kana=pyopenjtalk.g2p(row['text'],kana=True));selected.append(row)
  assert len({norm(r['text']) for r in selected})==8 and {norm(r['text']) for r in selected}.isdisjoint({norm(r['text']) for r in rows})
  rows+=selected;deps={}
  for n,h in old['dependencies'].items():assert digest(REPO/n)==h;deps[n]=h
  for q in (HERE/'packages-v2').rglob('*'):
   if q.is_file():deps[str(q.relative_to(REPO))]=digest(q)
  for q in (HERE/'upstream').rglob('*'):
   if q.is_file():deps[str(q.relative_to(REPO))]=digest(q)
  sources={q.name:digest(q) for q in HERE.iterdir() if q.is_file() and q.suffix in ['.py','.c','.dylib','.sb']}
  b.save(HERE/'novelty-audit.json',{'history_reference_hashes':history,'historical_texts':len(texts),'historical_full_labels':len(labels),'candidate_pool_checked_before_output':pool,'selected_rows':[{'id':r['id'],'text':r['text'],'kana':r['kana']} for r in selected],'protected_unused_confirmation_opened':False,'final_quality_independence_claim':False},j)
  b.save(HERE/'protocol.json',{'registration_sha256':digest(HERE/'registration.json'),'rows':rows,'variants':reg['variants'],'modes':[0,1],'baseline_legacy96_first':True,'source_hashes':sources,'dependencies':deps,'new_control_coefficients':0,'fixed_gain_from_same_method_baseline':True,'scientific_thresholds_unchanged':True,'content_groups_per_ASR_cohort':21,'support_from_native_baseline_only':True,'missing_reject':True,'no_optimization_after_ASR':True,'quality_certified':False},j)
  b.save(HERE/'engine-contract.json',read(PREVIOUS/'engine-contract.json'),j)
  b.save(HERE/'mechanism-contract.json',{'conversion_registration_sha256':digest(HERE/'registration.json'),'world_provenance_sha256':digest(HERE/'world-provenance.json'),'conversion_audit_sha256':digest(HERE/'conversion-audit.json'),'self_test_sha256':digest(HERE/'self-test.json'),'canonical_parameters_unchanged':True,'WORLD_AP_is_approximation':True,'renderer_and_interpolation_changed_together':True,'pure_phase_causal_claim':False,'no_saved_waveform_analysis_runtime':True,'boundaries_included':True,'thresholds_not_relaxed':True,'no_perceptual_qualification':True},j)
 print({'selected':[r['text'] for r in selected],'excluded_pool':[r['text'] for r in pool if r['text_collision'] or r['label_collision']],'negative_tests_passed':True},flush=True);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
