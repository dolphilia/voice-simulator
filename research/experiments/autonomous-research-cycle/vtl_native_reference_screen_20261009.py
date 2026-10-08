"""未実施e/oのnative参照を先に診断し、適格条件だけに探索費を使う。"""
import argparse,ast,hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
from vtl_shared_vowel_fit_20261009_v2 import WORKER as ORIGINAL
REPO=ROOT.parents[2];SOURCE=ROOT/'campaigns/nas-vtl-shared-vowel-fit-20261009-u-v2'
HERE=ROOT/'campaigns/nas-vtl-native-reference-screen-20261009-v1';NAME='vtl-native-reference-screen-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PREFIX=ORIGINAL.split('refs={};all_rows=[];render_calls=0;text=')[0]
PREFIX=PREFIX.replace("sys.path.insert(0,str(here/'runtime-bundle'));from vtl_runtime import VTL","")
WORKER=PREFIX+r'''
refs=[];render_calls=0
for vowel,text in [('e','エ'),('o','オ')]:
 for target in [120.,160.]:
  data,meta,params,row=native(text,1.,target,full=True);render_calls+=meta['conversion']['render_calls_including_internal_MLSA'];measure_calls+=3
  indices=[i for i,label in enumerate(row['full_context_labels']) if re.search(r'\-([^+]+)\+',label).group(1).lower()==vowel];assert len(indices)==1
  i=indices[0];bounds=np.r_[0,np.cumsum(meta['duration'])]*.005;start,end=float(bounds[i*5]),float(bounds[(i+1)*5]);width=end-start
  central=[start+.2*width,end-.2*width];measurement=measure(data,central,target);ident='native-'+vowel+'-'+str(int(target));(work/(ident+'.wav')).write_bytes(data)
  refs.append(dict(id=ident,vowel=vowel,text=text,target_F0_Hz=target,wav_sha256=hashlib.sha256(data).hexdigest(),source_state_interval_seconds=[start,end],label_boundary_not_observed_truth=True,measurement=measurement,native_gain=.25,settings=meta['settings']))
assert render_calls==4 and measure_calls==40
(work/'references.json').write_text(json.dumps(dict(references=refs,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,protected_confirmation_opened=False),ensure_ascii=False,allow_nan=False))
print(json.dumps(dict(actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,output_files=[x['id']+'.wav' for x in refs])))
'''
def verify():
 c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(REPO/n)==h,n
def register():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due'];check_plan(s,3600);ast.parse(WORKER)
 limits=dict(seconds=3600,bytes=128000000,write_bytes=500000000,setup=6,audit=6,render=4,dsp=48,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(question='i/uの低F0参照でDIO支持が欠測した後、未実施e/oの参照も同じ固定工学を不通過か。候補を作る前に測る。',controller_sha256=digest(Path(__file__)),stage_A_design_sha256=digest(ROOT/'campaigns/nas-research-resume-stage-A-20261009-v1/stage-A-design.json'),native_source_manifest_sha256=digest(SOURCE/'native-bundle/manifest.json'),measure_source_sha256=digest(ROOT/'vtl_shared_vowel_fit_20261009_v2.py'),prior_i_u_results={v:digest(ROOT/('campaigns/nas-vtl-shared-vowel-fit-20261009-'+v+'-v2/artifact-seal.json')) for v in 'iu'},texts=['エ','オ'],F0_Hz=[120,160],speed=1.,gain=.25,roles=dict(reference='既存nativeモデルの再使用。新しい独立品質証拠ではなく、Aで予定した未実施母音の訓練参照資格。',P5_opened=False),gates='旧i/uと同じ中央state60%、E0、DIO/stonemaskとACF±1半音/confidence.6、有声3frame/半数以上。一母音診断で最低3音素支持の発話資格ではない。',selection='e/oそれぞれ両F0参照を通過した場合だけ同じA条件の候補学習を別契約で登録。通過しない母音は既定標的/未資格を保持。参照・窓・閾値は救済しない。',counts=dict(native_render=4,DSP_macro=40,fit=0,inverse=0),estimated=dict(retained_WAV_bytes=400000,JSON_bytes=100000,temporary_peak_bytes=16000000,temporary_write_bytes=32000000,logs_bytes=2000000,RAM_bytes=1000000000,control_index_failure_Git_included=True),limits=limits,quality_goal_completed=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
 with b.job(NAME,'setup','未実施参照の二母音二F0と固定ゲートを初出力前に登録',reserve_bytes=4000000) as j:
  b.save(HERE/'registration.json',reg,j);b.write(HERE/'worker.py',WORKER.encode(),j)
  paths=[Path(__file__),ROOT/'vtl_shared_vowel_fit_20261009_v2.py',HERE/'worker.py',HERE/'registration.json',SOURCE/'native-bundle/manifest.json']
  paths += [SOURCE/'native-bundle'/n for n in read(SOURCE/'native-bundle/manifest.json')['files']]
  b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(REPO)):digest(p) for p in paths}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=NAME,next='登録保存後e/o参照だけを固定診断し、不適格参照の候補探索を省く。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-native-reference-screen-register-20261009.json',dict(active_campaign=NAME,registered_before_outputs=True,budget=b.reconcile()))
 print('e/oの固定参照資格を初出力前登録')
def run():
 b=Budget();b.recover();verify()
 r=b.reserve(NAME,'render','e/oの未実施native訓練参照二F0',4,2000000,expected_seconds=300)
 try:
  d=b.reserve(NAME,'dsp','参照四波形の固定E0/F0/包絡',40,1000000,expected_seconds=300)
  try:
   with b.workspace(r,'e/o参照だけの診断と回収',16000000,32000000) as (work,env):
    env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    stdout,stderr,observed=run_observed([str(PYTHON),'-B',str(HERE/'worker.py'),str(SOURCE),str(work),'e'],env,work,label='references',timeout=240)
    b.save(HERE/'process-observation.json',observed,r)
    if observed['returncode']!=0:
     b.save(HERE/'failure.json',dict(stdout=stdout,stderr=stderr),r);raise RuntimeError('参照診断の技術起動不成立')
    counts=json.loads(stdout);b.save(HERE/'generation-counts.json',counts,r)
    b.write_data(HERE/'data/references.json',(work/'references.json').read_bytes(),r)
    for n in counts['output_files']:b.write_data(HERE/'audio'/n,(work/n).read_bytes(),r)
  except BaseException as e:b.finish(d,repr(e));raise
  else:b.finish(d)
 except BaseException as e:b.finish(r,repr(e));raise
 else:b.finish(r)
 with b.job(NAME,'audit','全参照分母/可否/費用/一時回収を封印',reserve_bytes=3000000) as j:
  value=read(HERE/'data/references.json');results={v:dict(references=[dict(id=x['id'],E0_pass=x['measurement']['E0']['E0_pass'],pitch=x['measurement']['pitch']) for x in value['references'] if x['vowel']==v],eligible_for_candidate_fit=all(x['measurement']['engineering_diagnostic_pass'] for x in value['references'] if x['vowel']==v)) for v in 'eo'}
  summary=dict(vowels=results,reference_total=4,passed=sum(x['measurement']['engineering_diagnostic_pass'] for x in value['references']),candidate_generation_or_fit_performed=False,prior_i_u_frozen=True,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False)
  b.save(HERE/'aggregate-summary.json',summary,j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(HERE/'cost-audit.json',dict(counts=c['counts'],actual=read(HERE/'generation-counts.json'),seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,process=read(HERE/'process-observation.json')),j)
  lines=['# 未実施e/oのnative参照資格','','全四参照を分母へ保持。i/uを救済せず、同じ中央窓・工学診断を適用した。']
  for v,x in results.items():lines+=['',v+'の候補学習に進める参照資格: '+str(x['eligible_for_candidate_fit'])]+[str(y) for y in x['references']]
  lines+=['','候補音声の改善・内容ASR・知覚・一般化は本診断の対象外。品質未達、P5未開封。']
  b.write(HERE/'report.md','\n'.join(lines).encode(),j);b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=None,next='参照資格がある母音だけA条件の候補fit。全不通過なら低F0/native参照経路を撤退し、新しい科学条件を事前登録。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-native-reference-screen-completed-20261009.json',dict(result=summary,review=b.review_due(),budget=b.reconcile()))
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);a=p.parse_args();globals()[a.stage]()
