"""旧22封印・観測済み履歴・読み・入力を生成前に固定する。"""
import sys,re,unicodedata,json,socket
from paths import *
sys.path.insert(0,str(BUNDLE))
from japanese_frontend import analyze
from spectrum_renderer import tests
import pyopenjtalk

def norm(text):return re.sub(r'[\W_]','',unicodedata.normalize('NFKC',text))
def collect(value,texts,labels):
 if isinstance(value,dict):
  if isinstance(value.get('text'),str):
   texts.add(norm(value['text']))
   if value.get('full_context_labels'):labels.add(tuple(value['full_context_labels']))
  for x in value.values():collect(x,texts,labels)
 elif isinstance(value,list):
  for x in value:collect(x,texts,labels)
def main():
 b=Budget()
 with b.job(NAME,'setup','旧封印・履歴・前段・固定依存を検証',reserve_bytes=3_000_000) as j:
  try:
   sock=socket.socket();sock.bind(('127.0.0.1',0));sock.close()
  except PermissionError:network_denied=True
  else:network_denied=False
  assert network_denied,'OSでnetworkを拒否した実行を要求します'
  previous=read(REVIEW/'input-preservation.json')['seals']+[{'seal':str((REVIEW/'artifact-seal.json').relative_to(REPO))}]
  hashes={};verified=[]
  for item in previous:
   seal_path=REPO/item['seal'];seal=read(seal_path);base=Path(seal['path_base'])
   for n,h in seal['files'].items():
    path=base/n;assert digest(path)==h,n
    hashes[str(path.relative_to(REPO))]=h
   verified.append({'seal':item['seal'],'sha256':digest(seal_path),'files':len(seal['files'])})
  b.save(HERE/'input-preservation.json',{'seals':verified,'verified_unique_files':len(hashes),'all_verified':True},j)
  old=read(ERES/'protocol.json');history=set();label_history=set();checked={};skipped=[]
  # 旧の観測済み履歴だけ参照し、保護確認のsplits.jsonは読まない。
  names=set(old['history'])
  rp=read(REVIEW/'protocol.json');names.update(n for n in rp['input_hashes'] if n.endswith('.json') and 'next-trial' not in n)
  for name in sorted(names):
   if re.search('splits|protected|holdout|final-confirm',name,re.I):skipped.append({'path':name,'reason':'未使用確認に接続し得る参照'});continue
   if name not in hashes:skipped.append({'path':name,'reason':'今回の旧封印集合に含まれない'});continue
   value=read(REPO/name);collect(value,history,label_history);checked[name]=hashes[name]
  registration=read(REVIEW/'next-trial-registration.json');rows=[];novel=[]
  for spec in registration['inputs']:
   row=analyze(spec['text']);row.update(spec,split=spec['cohort'])
   kana=pyopenjtalk.g2p(spec['text'],kana=True)
   if spec['cohort']=='legacy_diagnostic':
    saved=next(r for r in old['rows'] if r['id']==spec['id'])
    assert row['full_context_labels']==saved['full_context_labels']
   else:
    novel.append({'id':spec['id'],'text_collision':norm(spec['text']) in history,
                  'label_collision':tuple(row['full_context_labels']) in label_history,'kana':kana,
                  'resolved_frontend':True,'scope':'辞書と規則。人手の知覚/アクセント真値ではない'})
   rows.append(row)
  b.save(HERE/'novelty-audit.json',{'history':checked,'history_texts':len(history),'history_labels':len(label_history),
   'skipped_protected_or_unsealed':skipped,'rows':novel,'protected_unused_confirmation_opened':False,
   'fresh_prospective_only':True,'final_independent_quality_claim':False},j)
  assert not any(r['text_collision'] or r['label_collision'] for r in novel),'新規入力が既出です。生成前の登録見直しが必要'
  engine=read(ERES/'engine-contract.json')
  dependencies={}
  for name,h in engine['asr_model_hashes'].items():assert digest(REPO/name)==h;dependencies[name]=h
  cfg=engine['reading_diagnostic']['contract']
  for name,h in cfg['dictionary_files'].items():assert digest(Path(cfg['dictionary_path'])/name)==h
  assert digest(cfg['library'])==cfg['library_sha256']
  dependencies[str(Path(cfg['library']).relative_to(REPO))]=cfg['library_sha256']
  assert digest(OLD/'diagnostics.py')==engine['normalizer_source_sha256']
  deps=[BUNDLE/'mei_normal.htsvoice',BUNDLE/'japanese_frontend.py',BUNDLE/'acoustics.py',BUNDLE/'acoustic_control.py',
   SHARED/'local_control.py',SHARED/'centered_projection.py',SHARED/'checks.py',SHARED/'objective.py',SHARED/'render.py',
   COUNTER/'counter_diagnostics.py',COUNTER/'counter.c',EVAL/'evaluate.py',EVAL/'summarize.py',OLD/'diagnostics.py']
  for name,h in read(SRES/'model-comparison.json')['model_hashes'].items():
   path=SRES/'models'/name;assert digest(path)==h;deps.append(path)
  for path in deps:dependencies[str(path.relative_to(REPO))]=digest(path)
  legacy=[]
  for row in rows[:8]:
   for condition in row['requests']:
    for variant in old['variants']:
     record=SRES/'render'/row['id']/condition/(variant+'.json');wav=record.with_suffix('.wav');npz=record.with_suffix('.npz')
     for path in (record,wav,npz,record.parent/'support-contract.json'):
      dependencies[str(path.relative_to(REPO))]=digest(path)
     r=read(record);assert r['status']=='completed'
     legacy.append({'id':r['id'],'record':str(record.relative_to(REPO)),'sha256':digest(record)})
  assert len(legacy)==64
  b.save(HERE/'engine-contract.json',engine,j)
  b.save(HERE/'negative-tests.json',tests(),j)
  b.save(HERE/'protocol.json',{'registration_sha256':digest(REVIEW/'next-trial-registration.json'),
   'rows':rows,'variants':old['variants'],'factors':[1.,.75],'baseline64_first':True,
   'legacy_reference':legacy,'dependencies':dependencies,
   'source_hashes':{str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file() and p.suffix in ('.py','.c','.h','.dylib','.sb')},
   'gain_policy':'candidateは同じrow/method alpha1のoutput_gainを固定使用。candidate peakによる再正規化はしない',
   'support_policy':'legacyは保存native支持域、新規はalpha1/nativeだけで固定。candidateで再選択しない',
   'measurement_counts':{'dio_primary':256,'wide_acf':256,'engineering_E0':256,'global_dsp_limit':768},
   'content_policy':'既存21群・二ASR別判定・cohort別・missing reject。自然さ資格ではない',
   'no_new_teacher_fit_inverse':True,'final_quality_certified':False,'no_optimization_after_asr':True,
   'old_saved_stream_scope':'旧64はWAV/LF0/全状態streamと時間を照合。旧NPZにMCP/LPFのMLPG列は保存されていないため、candidateと再現baselineで全MLPG列を直接比較する。旧18行は保存MCP/LPFも直接照合できる。'},j)
  b.save(HERE/'entry-audit.json',{'passed':True,'old_seals':22,'legacy_rows':64,'fresh_rows':8,
   'new_render_calls':0,'source_frozen':True,'network_denied':True,'quality_certified':False},j)
 print({'entry_passed':True,'history_texts':len(history),'fresh_exact_collisions':0,'protected_paths_skipped':len(skipped)},flush=True)
if __name__=='__main__':main()
