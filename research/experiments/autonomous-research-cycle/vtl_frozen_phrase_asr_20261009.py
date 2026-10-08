"""未開始ASRの保存先だけを現campaignへ移す。凍結済みモデル/正規化/評価条件を保持。"""
import argparse,ast,hashlib,importlib.util,json
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
spec=importlib.util.spec_from_file_location('phrase_resource',ROOT/'vtl_frozen_phrase_resource_continuation_20261009.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a);m=a.m
def verify(engine):
 a.verify();here,name=m.campaign_location('asr-'+engine);c=read(here/'execution-contract.json')
 assert digest(Path(__file__))==c['controller_sha256'] and digest(here/'asr_worker.py')==c['worker_sha256']
 assert digest(m.HERE/'asr_worker.py')==c['original_worker_sha256']
def register(engine):
 a.verify();m.asr_register(engine);b=Budget();here,name=m.campaign_location('asr-'+engine)
 src=(m.HERE/'asr_worker.py').read_text();assert 'from paths import *' in src
 replacement="""HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
SUITE=ROOT/'campaigns/nas-vtl-frozen-phrase-suite-20261009-v1'
OLD=REPO/'research/experiments/autonomous-speech-synthesis'
PILOT=REPO/'research/experiments/neural-control-distillation'
sys.path.insert(0,str(ROOT))
from budget import read,digest
"""
 src=src.replace('from paths import *',replacement)
 for text in ["HERE / 'engine-contract.json'","HERE / 'protocol.json'","HERE/'engine-contract.json'","HERE/'protocol.json'"]:src=src.replace(text,text.replace('HERE','SUITE'))
 ast.parse(src)
 with m.job(b,name,'setup','未開始ASRの保存先を所有campaignへ限定',size=6000000) as j:
  b.write(here/'asr_worker.py',src.encode(),j)
  b.save(here/'execution-contract.json',dict(controller_sha256=digest(Path(__file__)),worker_sha256=digest(here/'asr_worker.py'),original_worker_sha256=digest(m.HERE/'asr_worker.py'),suite_source_contract_sha256=digest(m.HERE/'source-contract.json'),engine_contract_sha256=digest(m.HERE/'engine-contract.json'),protocol_sha256=digest(m.HERE/'protocol.json'),reason='登録管理campaignは既に終了しているため、個票/入力manifestを現ASR campaignへ保存し、凍結protocol/engineは旧suiteから読取る。評価器/モデル/正規化/波形/48全分母/33群は変更しない。ASR初出力前の実行配線修正。',new_render=0,new_DSP=0,AI_reserved=48,quality_goal_completed=False),j)
 print(engine+'の未開始評価保存先を現campaignへ登録')
def run(engine):
 b=Budget();b.recover();verify(engine);here,name=m.campaign_location('asr-'+engine);cfg=read(m.HERE/'engine-contract.json')
 with m.job(b,name,'audit','固定ASR/辞書/正規化hashと全48保存波形 '+engine,size=8000000) as j:
  for n,h in cfg['asr_model_hashes'].items():assert digest(m.REPO/n)==h,n
  assert digest(m.REPO/'research/experiments/autonomous-speech-synthesis/diagnostics.py')==cfg['normalizer_source_sha256']
  c=cfg['reading_diagnostic']['contract']
  for n,h in c['dictionary_files'].items():assert digest(Path(c['dictionary_path'])/n)==h,n
  assert digest(c['library'])==c['library_sha256']
  manifest=[]
  for p in read(m.HERE/'render-plan.json')['batches']:
   if p['mode']!='normal':continue
   group,_=m.campaign_location('normal-'+p['length']+'-'+p['condition'])
   for row in read(group/'render-manifest.json')['rows']:
    q=row['request']
    if row['wav']:assert digest(m.REPO/row['wav'])==row['wav_sha256']
    record=dict(id=q['id'],text=q['text'],length=q['length'],challenge_group=q['challenge_group'],condition=q['condition'],variant=q['method'],wav=row['wav'],wav_sha256=row['wav_sha256'])
    path=here/'data'/('record-'+str(len(manifest)).zfill(2)+'.json');b.write_data(path,encode(record),j);manifest.append(dict(record=str(path.relative_to(m.REPO)),sha256=digest(path)))
  assert len(manifest)==48;b.save(here/'render-manifest.json',dict(rows=manifest),j)
 with m.job(b,name,'ai','固定'+engine+'全48波形',48,100000000,3000) as j:
  with b.workspace(j,'同コホート48波形の固定'+engine+'評価',32000000,64000000) as (work,env):
   m.env_settings(env);value=m.observe(b,work,env,[str(m.PYTHON),'-B',str(here/'asr_worker.py'),'--engine',engine],'asr-'+engine,j,here,method='evaluation',timeout=2700)
  assert len(value['rows'])==48 and value['ai_calls']<=48
  for row in value['rows']:
   assert row['protocol_sha256']==digest(m.HERE/'protocol.json') and row['engine_contract_sha256']==digest(m.HERE/'engine-contract.json')
  b.write_data(here/'data/results.json',encode(value),j);b.save(here/'asr-manifest.json',dict(path=str((here/'data/results.json').relative_to(m.REPO)),sha256=digest(here/'data/results.json'),new_AI_reserved=48,new_AI_actual=value['ai_calls']),j)
 summary=dict(engine=engine,expected=48,completed=sum(x['status']=='completed' for x in value['rows']),missing=sum(x['status']!='completed' for x in value['rows']),optimization_after_ASR=False,old_engine_and_normalizer_unchanged=True,quality_goal_completed=False)
 m.seal_close(b,here,name,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);p.add_argument('engine',choices=['whisper','reazon']);q=p.parse_args();globals()[q.stage](q.engine)
