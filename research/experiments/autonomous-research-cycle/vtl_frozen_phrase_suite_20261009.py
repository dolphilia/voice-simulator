"""工程Dの固定語句比較。全体登録を保持し、個別上限内で生成/隔離/評価を分割する。"""
import argparse,ast,hashlib,json,math,os,re,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-vtl-frozen-phrase-suite-20261009-v1'
NAME='vtl-frozen-phrase-suite-registration-v1'
CV=ROOT/'campaigns/nas-vtl-shared-cv-preflight-20261009-v1/runtime-bundle'
NATIVE=ROOT/'campaigns/nas-vtl-shared-vowel-fit-20261009-u-v2/native-bundle'
OLD=ROOT/'campaigns/nas-waveguide-vowel-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
CONDITIONS={'neutral':dict(F0_Hz=140.,speed=1.),'higher':dict(F0_Hz=180.,speed=1.15)}
METHODS=['native','baseline','learned']
@contextmanager
def job(b,name,kind,label,count=1,size=0,seconds=600):
 token=b.reserve(name,kind,label,count,size,expected_seconds=seconds)
 try:yield token
 except BaseException as e:b.finish(token,repr(e));raise
 else:b.finish(token)
def limits(render=0,dsp=0,ai=0,seconds=7200):
 return dict(seconds=seconds,bytes=200000000,write_bytes=1200000000,setup=20,audit=20,render=render,dsp=dsp,ai=ai,teacher=0,train=0,inverse=0,download=0)
def checkpoint(b,campaign,next):
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=campaign,next=next,git_save_pending=True);b._write_state(s)
def verify():
 for n,h in read(HERE/'source-contract.json')['files'].items():assert digest(REPO/n)==h,n
 assert digest(HERE/'protocol.json')==read(HERE/'source-contract.json')['protocol_sha256']
def profile(b,work,method,isolated):
 s='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
 if isolated:
  s+='(deny file-read* (subpath '+json.dumps(str(REPO/'research'))+'))\n(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n'
  allowed=[PYTHON.parents[1],CV if method!='native' else NATIVE,work]
  s+='(allow file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in allowed)+')\n'
  s+='(allow file-read* (literal '+json.dumps(str(HERE/'runtime_worker.py'))+'))\n'
  s+='(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n'
  site=PYTHON.parents[1]/'lib/python3.11/site-packages'
  s+='(deny file-read* '+''.join('(subpath '+json.dumps(str(site/n))+') ' for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'])+')\n'
  if method!='native':s+='(deny file-read-data (regex #"\\\\.htsvoice$"))\n'
  ancestors=set()
  for p in allowed+[HERE/'runtime_worker.py']:ancestors.update(p.parents)
  s+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(ancestors))+')\n'
 return s
def env_settings(env):
 env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
def requests():
 p=read(HERE/'protocol.json')
 return [dict(id=r['id']+'/'+c+'/'+m,file_id=r['id']+'-'+c+'-'+m,text=r['text'],kana=r['kana'],length=r['length'],challenge_group=r['challenge_group'],method=m,condition=c,**q) for r in p['rows'] for c,q in p['conditions'].items() for m in METHODS]
def cost(q):
 if q['method']=='native':return 1
 row=next(r for r in read(HERE/'protocol.json')['rows'] if r['id']==q['id'].split('/')[0])
 samples=round((.1+len(row['moras'])*.32/q['speed'])*44100)
 return math.ceil(samples/110)+3
def check_D(b,additional=0):
 s=b.snapshot();assert s['research_execution_plan']['first_stage']['current']=='D'
 used=s['counts']['render']-read(HERE/'protocol.json')['stage_D_start_render']
 assert used+additional<=36000,('D事前配分の上限',used,additional)
 return used
def observe(b,work,env,cmd,label,token,study,isolated=False,method='native',timeout=840):
 if method!='evaluation':cmd=['/usr/bin/sandbox-exec','-p',profile(b,work,method,isolated),*cmd]
 else:cmd=['/usr/bin/sandbox-exec','-p',profile(b,work,'native',False),*cmd]
 out,err,obs=run_observed(cmd,env,work,label=label,timeout=timeout)
 b.save(study/(label+'-process.json'),obs,token)
 if obs['returncode']!=0:
  for p in work.glob('*.json'):b.write_data(study/'failure-data'/p.name,p.read_bytes(),token)
  for p in work.glob('*.wav'):b.write_data(study/'partial-audio'/p.name,p.read_bytes(),token)
  b.save(study/(label+'-failure.json'),dict(stdout=out,stderr=err),token)
  raise RuntimeError('所有領域内の子処理不成立: '+label)
 return json.loads(out)
def sources():
 paths=[Path(__file__),HERE/'registration.json',HERE/'input_worker.py',HERE/'runtime_worker.py',HERE/'measurement_worker.py',HERE/'asr_worker.py',HERE/'paths.py',HERE/'engine-contract.json',OLD/'measurement.py',ROOT/'campaigns/nas-vocoder-f0-20261008-v1/summarize.py',ROOT/'observed_process_20261009.py']
 for folder in [CV,NATIVE]:
  paths.append(folder/'manifest.json');paths += [folder/n for n in read(folder/'manifest.json')['files']]
 return paths
def register():
 b=Budget();b.recover();s=b.snapshot()
 assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due']
 assert s['research_execution_plan']['first_stage']['current']=='D';check_plan(s,7200)
 review=read(ROOT/'campaigns/nas-long-horizon-review-20261009-v10/decision.json')
 assert digest(CV/'shared-model.json')==review['candidate_frozen']['model_sha256']
 pool=dict(short=['答え','臭い','奇跡','確か','かかと','高さ','硬さ','逆さ','袈裟','世界'],long=['挨拶','大切','色彩','催促','掛け方','立て方','貸し方','戦い','たくさん','朝方'])
 previous=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1/novelty-audit.json'
 history={n:h for n,h in read(previous)['history_reference_hashes'].items() if n.endswith('protocol.json')}
 path=previous.parent/'protocol.json';history[str(path.relative_to(REPO))]=digest(path)
 # 既知の非保護campaignのprotocolだけを照合。P5/splits本文や全JSONを走査しない。
 for name,c in s['campaigns'].items():
  prefix=c['prefix'];p=ROOT/prefix/'protocol.json'
  if p.is_file():
   assert not re.search('splits|protected|holdout|final.confirm',str(p),re.I)
   history[str(p.relative_to(REPO))]=digest(p)
 reg=dict(question='単独aiuの訓練適合が、新しいk/t/s系の短3/長4モーラ語の内容・工学へ移転するか。既知CV不通過を保持する。',scope=dict(short=4,long=4,conditions=CONDITIONS,methods=METHODS,expected_normal=48,expected_isolated=48,CLI=3,groups_per_ASR=33,challenge_groups=list(range(4)),uncovered_challenge_groups=list(range(4,8)),not_full_Japanese_or_long_sentence=True),candidate_frozen=review['candidate_frozen'],role='出力前一度の未使用選別。参照/開発/P5へ再ラベルしない。',pool_selection='各長さの固定順から、文字正規化/全文ラベル非衝突・対象かな/音素・短3/長4モーラを満たす最初4件。音声結果で選ばずuも除外しない。',gates=dict(E0='旧acoustics全E0',pitch='旧measurement.pyのDIO/stonemask・独立全体ACF±1半音/conf.6。nativeで固定した有声phone-indexを全方式自身の時計へ適用し、最低3音素・各3frame/半数以上、全欠測を保持。',content='旧grouped関数の二ASR各33系列。0分母のgroup4..7は不通過として保持。対象部分の非悪化を全33群通過へ拡張しない。learned対baselineの同コホート差も別表に保持。',invariance='通常/隔離48件同一hash、最初の短neutral一件×三方式の単独CLIを隔離実行、過去論理/外部実体/参照/原HTS/通信の実拒否',no_post_output_adjustment=True),source_gains=dict(native=.25,VTL=.5),timing='VTL前後各50ms、一モーラ320ms/speed、CV子音80ms/speed。native旧HTS自身のstate時計。音源/声道/gain/時計同一を方式間で主張しない。',resources=dict(stage_D_render_allocation=36000,first_sample_fixture_reused=True,retained_waveforms_bytes_at_most=20000000,work_peak_bytes=32000000,work_write_bytes=64000000,job_reserve_bytes=100000000,RAM_observed_limit_bytes=8000000000,process_group_RSS_sampling_seconds=.05,continuous_exact_peak=False,total_reserved_render_computed_before_output=True,AI=96,new_fit=0,new_inverse=0,control_index_Git_failure_included=True),staging='管理登録/前処理は科学回数を増やさない。小入口1campaign、通常4/隔離4のバッチ、二ASR2campaignへ分割。科学6終了レビューを途中で先に実行。全体分母/時計/配分は分割で初期化しない。',P5_opened=False,perceptual_qualification=False,quality_goal_completed=False,controller_sha256=digest(Path(__file__)),history=history,pool=pool,limits=limits())
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),reg['limits'],hashlib.sha256(encode(reg)).hexdigest(),purpose='management')
 with job(b,NAME,'setup','工程D全分母/固定係数/入力選別/費用系列を初出力前登録',size=12000000) as j:
  b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',dict(pool=pool,history=history),j)
  for source,target in [('vtl_frozen_phrase_input_20261009.py','input_worker.py'),('vtl_frozen_phrase_runtime_20261009.py','runtime_worker.py'),('vtl_frozen_phrase_measure_20261009.py','measurement_worker.py')]:
   data=(ROOT/source).read_bytes();ast.parse(data);b.write(HERE/target,data,j)
  src=(OLD/'asr_worker.py').read_text().replace('64','48')
  missing="""        if record['wav'] is None:
            result={k:record[k] for k in ('id','text','length','challenge_group','condition','variant','wav','wav_sha256')}
            result.update(status='missing_generation',engine=name,ai_calls=0,hypothesis=None,reference_kana=normalize_text(pyopenjtalk.g2p(record['text'],kana=True)),predicted_kana=None,errors=None,characters=len(normalize_text(pyopenjtalk.g2p(record['text'],kana=True))),protocol_sha256=digest(HERE/'protocol.json'),engine_contract_sha256=digest(HERE/'engine-contract.json'))
            rows.append(result)
            continue
"""
  src=src.replace("        assert digest(REPO / record['wav']) == record['wav_sha256']",missing+"        assert digest(REPO / record['wav']) == record['wav_sha256']")
  src=src.replace("ai_calls=48, reused=0","ai_calls=sum(x['ai_calls'] for x in rows), reused=0")
  ast.parse(src);b.write(HERE/'asr_worker.py',src.encode(),j)
  paths=(OLD/'paths.py').read_text();b.write(HERE/'paths.py',paths.encode(),j);b.save(HERE/'engine-contract.json',read(OLD/'engine-contract.json'),j)
 checkpoint(b,NAME,'D登録をpush後、音声なしで新入力/全33群/全内部費を固定。')
 print('D全体の初出力前登録完了',flush=True)
def prepare():
 b=Budget();b.recover();assert digest(Path(__file__))==read(HERE/'registration.json')['controller_sha256']
 with job(b,NAME,'setup','音声なしの新入力/全文ラベル衝突/全量計算',size=100000000,seconds=900) as j:
  with b.workspace(j,'非保護履歴の入力前処理のみ',32000000,64000000) as (work,env):
   env_settings(env);cfg=read(HERE/'candidate-pool.json');(work/'inputs.json').write_bytes(encode(cfg))
   value=observe(b,work,env,[str(PYTHON),'-B',str(HERE/'input_worker.py'),str(REPO),str(NATIVE),str(work/'inputs.json')],'input-prepare',j,HERE,method='evaluation',timeout=180)
  assert len(value['rows'])==8
  b.save(HERE/'novelty-audit.json',value,j)
  p=dict(rows=value['rows'],conditions=CONDITIONS,methods=METHODS,expected_normal=48,expected_isolated=48,CLI=3,stage_D_start_render=b.snapshot()['counts']['render'],P5_opened=False,parameters_frozen=True,no_optimization_after_output=True)
  b.save(HERE/'protocol.json',p,j);req=requests();comp=sum(cost(q) for q in req);first=[q for q in req if q['id'].startswith(p['rows'][0]['id']+'/neutral/')];cli=sum(cost(q) for q in first)
  assert comp*2+cli<36000 and len(first)==3
  group_rows=[]
  for condition in ['both','neutral','higher']:
   for group in ['all','short','long']+['group'+str(i) for i in range(8)]:
    chosen=[q for q in req if q['method']=='learned' and (condition=='both' or q['condition']==condition) and (group=='all' or q['length']==group or group=='group'+str(q['challenge_group']))]
    group_rows.append(dict(id=condition+'/'+group,expected=len(chosen),characters_unknown_before_ASR=True,zero_denominator=len(chosen)==0,zero_is_not_passing=len(chosen)==0))
  assert len(group_rows)==33
  batches=[]
  for mode in ['normal','isolated']:
   for length in ['short','long']:
    for condition in CONDITIONS:
     selected=[q for q in req if q['length']==length and q['condition']==condition and q not in first]
     batches.append(dict(mode=mode,length=length,condition=condition,expected_records=12,first_fixture_records_reused=3 if length=='short' and condition=='neutral' else 0,render_reservation=sum(cost(q) for q in selected)))
  fixture=3*cli;total=fixture+sum(x['render_reservation'] for x in batches)
  assert total==comp*2+cli
  b.save(HERE/'render-plan.json',dict(normal_full=comp,isolated_full=comp,CLI=cli,fixture=fixture,batches=batches,total=total,D_allocation=36000,reserved_before_outputs=True,internal_reset_and_zero_AddTract_and_blocks_counted=True,new_audio_yet=0),j)
  b.save(HERE/'33-group-plan.json',dict(groups=group_rows,scope_all_33_passing_impossible_with_zero_groups=True,limited_active_groups_only_diagnostic=True),j)
  b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in sources()+[HERE/'protocol.json',HERE/'render-plan.json',HERE/'33-group-plan.json']},protocol_sha256=digest(HERE/'protocol.json')),j)
  b.save(HERE/'registration-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.iterdir() if p.is_file()},registered_before_first_output=True),j)
 b.close_campaign(NAME);checkpoint(b,None,'Dの有限小入口を登録→push→通常/隔離/CLI。通常/隔離の先行3出力は後続比較で再使用。')
 print(json.dumps(dict(prepared=True,inputs=[r['text'] for r in p['rows']],render=total,no_audio_yet=True),ensure_ascii=False),flush=True)
def campaign_location(label):
 assert re.fullmatch('[a-z0-9-]+',label)
 return ROOT/('campaigns/nas-vtl-frozen-phrase-'+label+'-20261009-v1'),'vtl-frozen-phrase-'+label+'-v1'
def register_piece(label,render,dsp=0,ai=0):
 b=Budget();b.recover();verify();s=b.snapshot()
 assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due']
 check_D(b,render);check_plan(s,7200);here,name=campaign_location(label)
 lim=limits(render,dsp,ai);reason='固定全体比較の同長さ/条件バッチに内部AddTract費を含め、通常3000を超えるため開始前理由付き上限内で予約。全体D36000/各6000/工程時計を保持。' if render>3000 else None
 reg=dict(label=label,whole_suite=str(HERE.relative_to(ROOT)),source_contract_sha256=digest(HERE/'source-contract.json'),protocol_sha256=digest(HERE/'protocol.json'),render_reservation=render,DSP_reservation=dsp,AI_reservation=ai,limits=lim,stage_D_allocation=36000,no_scientific_retry_or_rescue=True,P5_opened=False,quality_goal_completed=False)
 b.start_campaign(name,str(here.relative_to(ROOT)),lim,hashlib.sha256(encode(reg)).hexdigest(),expansion_reason=reason)
 with job(b,name,'setup','固定全体比較の部分実行登録',size=4000000) as j:b.save(here/'registration.json',reg,j)
 checkpoint(b,name,label+'登録push後に未実施部分だけを実行。')
 print(label+' 登録済み',flush=True)
def runtime(b,name,here,selected,mode,token,dsp_token):
 allrows=[]
 for method in METHODS:
  items=[q for q in selected if q['method']==method]
  if not items:continue
  with b.workspace(token,'D共有生成 '+mode+'/'+method,32000000,64000000) as (work,env):
   env_settings(env);(work/'requests.json').write_bytes(encode(items))
   cmd=[str(PYTHON),'-B',str(HERE/'runtime_worker.py'),'--bundle',str(NATIVE if method=='native' else CV),'--input',str(work/'requests.json')]
   if mode=='cli':assert len(items)==1;cmd.append('--single')
   value=observe(b,work,env,cmd,mode+'-'+method,token,here,isolated=mode!='normal',method=method)
   assert len(value['rows'])==len(items) and value['calls']<=sum(cost(q) for q in items)
   for row in value['rows']:
    if row['file']:
     path=here/'audio'/mode/(row['request']['id']+'.wav');b.write_data(path,(work/row['file']).read_bytes(),token);row['wav']=str(path.relative_to(REPO))
    else:row['wav']=None
   b.save(here/(mode+'-'+method+'-manifest.json'),value,token);allrows.extend(value['rows'])
 return allrows
def seal_close(b,here,name,summary):
 with job(b,name,'audit','全分母/失敗/費用/所有一時不存在を封印',size=6000000) as j:
  b.save(here/'aggregate-summary.json',summary,j);s=b.snapshot();c=s['campaigns'][name];tmp=[x for x in s['temporary_work'].values() if x['campaign']==name]
  assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(here/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,temporary_count=len(tmp)),j)
  b.write(here/'report.md',('# 固定語句比較の部分結果\n\n'+json.dumps(summary,ensure_ascii=False,indent=2)+'\n\n全体の未実施/0分母/工学不通過を保持。内容/知覚/一般化/日本語品質の認定は別。P5未開封。\n').encode(),j)
  b.save(here/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in here.rglob('*') if p.is_file()},experiment_completed=True,P5_opened=False,quality_goal_completed=False),j)
 b.close_campaign(name);checkpoint(b,None,'部分結果をpush後、全体計画の次の未実施ラベルへ。レビュー時計は保持。')
def fixture_register():
 p=read(HERE/'render-plan.json');register_piece('fixture',p['fixture'],100)
def fixture():
 b=Budget();b.recover();verify();here,name=campaign_location('fixture');p=read(HERE/'protocol.json');first=[q for q in requests() if q['id'].startswith(p['rows'][0]['id']+'/neutral/')];outputs={}
 for mode in ['normal','isolated','cli']:
  count=sum(cost(q) for q in first);check_D(b,count)
  with job(b,name,'render','D小入口 '+mode+' 全内部生成',count,100000000,900) as j:
   with job(b,name,'dsp','D小入口 '+mode+' 自己WAV全E0',24,2000000,900) as d:
    outputs[mode]=runtime(b,name,here,first,mode,j,d)
 hashes={mode:{x['request']['id']:x['wav_sha256'] for x in rows} for mode,rows in outputs.items()}
 exact=hashes['normal']==hashes['isolated']==hashes['cli'];all_E0=all(x['E0'] and x['E0']['E0_pass'] for rows in outputs.values() for x in rows)
 with job(b,name,'audit','候補の過去論理/外部実体/参照/HMM/通信の実拒否',size=100000000) as j:
  past=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1/audio/higher-longer-a-220.wav'
  data=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1/data/references.json'
  blocked=[past,past.resolve(),data,data.resolve(),NATIVE/'mei_normal.htsvoice',HERE/'protocol.json']
  assert all(p.is_file() for p in blocked)
  with b.workspace(j,'D候補の実依存拒否検査',32000000,64000000) as (work,env):
   env_settings(env)
   code="import json,socket,errno;paths="+repr([str(p) for p in blocked])+";rows=[]\nfor p in paths:\n try:\n  open(p,'rb').read(1);rows.append(dict(path=p,denied=False))\n except OSError as e:rows.append(dict(path=p,denied=e.errno in [1,13]))\ns=socket.socket();network=False\ntry:s.connect(('1.1.1.1',443))\nexcept OSError as e:network=e.errno in [1,13]\nfinally:s.close()\nprint(json.dumps(dict(rows=rows,network_denied=network,all_denied=all(x['denied'] for x in rows))))"
   value=observe(b,work,env,[str(PYTHON),'-I','-B','-c',code],'denial-probe',j,here,isolated=True,method='learned',timeout=30)
  assert value['all_denied'] and value['network_denied'];b.save(here/'denial-audit.json',value,j)
 summary=dict(rows_per_mode=3,total=9,exact=exact,all_E0=bool(all_E0),preflight_passed=bool(exact and all_E0),normal_isolated_CLI_actual=True,close_then_self_read=True,all_denials=True,reuse_first_normal_and_isolated=True,quality_goal_completed=False)
 seal_close(b,here,name,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
def batch_plan(mode,length,condition):
 assert mode in ['normal','isolated'] and length in ['short','long'] and condition in CONDITIONS
 return next(x for x in read(HERE/'render-plan.json')['batches'] if x['mode']==mode and x['length']==length and x['condition']==condition)
def batch_register(mode,length,condition):
 plan=batch_plan(mode,length,condition);assert read(campaign_location('fixture')[0]/'aggregate-summary.json')['preflight_passed']
 register_piece(mode+'-'+length+'-'+condition,plan['render_reservation'],200)
def batch(mode,length,condition):
 b=Budget();b.recover();verify();label=mode+'-'+length+'-'+condition;here,name=campaign_location(label);plan=batch_plan(mode,length,condition)
 selected=[q for q in requests() if q['length']==length and q['condition']==condition];fixture_here=campaign_location('fixture')[0];first=read(HERE/'protocol.json')['rows'][0]['id'];reuse=[]
 if length=='short' and condition=='neutral':
  for method in METHODS:reuse+=read(fixture_here/(mode+'-'+method+'-manifest.json'))['rows']
  selected=[q for q in selected if q['id'].split('/')[0]!=first]
 check_D(b,plan['render_reservation'])
 with job(b,name,'render','D '+label+' 未実施生成/全内部費',plan['render_reservation'],100000000,1200) as j:
  with job(b,name,'dsp','D '+label+' 全E0/固定支持DIO/ACF',200,2000000,1200) as d:
   rows=runtime(b,name,here,selected,mode,j,d)+reuse;assert len(rows)==12
   if mode=='normal':
    by={};phones={}
    for row in rows:
     key=row['request']['id'].rsplit('/',1)[0];by.setdefault(key,{})[row['request']['method']]=row
     spec=next(x for x in read(HERE/'protocol.json')['rows'] if x['id']==key.split('/')[0]);phones[key]=spec['phones']
    with b.workspace(j,'D通常出力の固定時計/全分母測定',32000000,64000000) as (work,env):
     env_settings(env)
     for row in rows:
      if row['wav']:
       assert digest(REPO/row['wav'])==row['wav_sha256'];(work/row['file']).write_bytes((REPO/row['wav']).read_bytes())
     (work/'measurement-input.json').write_bytes(encode(dict(cases=by,phones=phones)))
     measured=observe(b,work,env,[str(PYTHON),'-B',str(HERE/'measurement_worker.py'),str(work),str(OLD),str(CV)],'measurement',d,here,method='evaluation')
    assert len(measured['rows'])==12;b.save(here/'measurement-manifest.json',measured,d)
   else:
    normal_here=campaign_location('normal-'+length+'-'+condition)[0];normal={x['request']['id']:x for x in read(normal_here/'render-manifest.json')['rows']}
    for row in rows:
     assert row['status']==normal[row['request']['id']]['status']
     assert row['wav_sha256']==normal[row['request']['id']]['wav_sha256']
   b.save(here/'render-manifest.json',dict(rows=rows,expected=12,reused=len(reuse),mode=mode),j)
 engineering={}
 if mode=='normal':
  for method in METHODS:
   rr=[x for x in measured['rows'] if x['method']==method]
   engineering[method]=dict(expected=4,E0_pass=sum(x['E0_pass'] for x in rr),pitch_pass=sum(x['pitch_gate']['passed'] for x in rr),missing_records=sum(x['measurement'] is None for x in rr),fixed_support_intervals=sum(len(x['measurement']['support']) for x in rr if x['measurement']),missing_support=sum(len(x['measurement']['missing_support']) for x in rr if x['measurement']))
 summary=dict(label=label,expected_records=12,all_records_retained=True,reused=len(reuse),engineering=engineering,normal_isolated_exact=mode=='isolated',new_fit=0,new_inverse=0,quality_goal_completed=False)
 seal_close(b,here,name,summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
def asr_register(engine):
 assert engine in ['whisper','reazon']
 # 二ASRは全体通常48分母の生成・隔離が閉じた後に一度だけ実施する。
 for p in read(HERE/'render-plan.json')['batches']:
  here,_=campaign_location(p['mode']+'-'+p['length']+'-'+p['condition'])
  assert (here/'artifact-seal.json').is_file()
 register_piece('asr-'+engine,0,0,48)
def asr(engine):
 b=Budget();b.recover();verify();here,name=campaign_location('asr-'+engine);cfg=read(HERE/'engine-contract.json')
 with job(b,name,'audit','固定二ASR/辞書/正規化hash確認 '+engine,size=2000000) as j:
  for n,h in cfg['asr_model_hashes'].items():assert digest(REPO/n)==h,n
  assert digest(REPO/'research/experiments/autonomous-speech-synthesis/diagnostics.py')==cfg['normalizer_source_sha256']
  c=cfg['reading_diagnostic']['contract']
  for n,h in c['dictionary_files'].items():assert digest(Path(c['dictionary_path'])/n)==h,n
  assert digest(c['library'])==c['library_sha256']
  manifest=[]
  for p in read(HERE/'render-plan.json')['batches']:
   if p['mode']!='normal':continue
   group,_=campaign_location('normal-'+p['length']+'-'+p['condition'])
   for row in read(group/'render-manifest.json')['rows']:
    q=row['request'];record=dict(id=q['id'],text=q['text'],length=q['length'],challenge_group=q['challenge_group'],condition=q['condition'],variant=q['method'],wav=row['wav'],wav_sha256=row['wav_sha256'])
    path=HERE/'records'/(q['id']+'.json')
    if path.exists():assert read(path)==record
    else:b.write_data(path,encode(record),j)
    manifest.append(dict(record=str(path.relative_to(REPO)),sha256=digest(path)))
  assert len(manifest)==48
  # このmanifestは共通一度のみ保存。第2評価器は同じhashを確認する。
  if not (HERE/'render-manifest.json').exists():b.save(HERE/'render-manifest.json',dict(rows=manifest),j)
  else:assert read(HERE/'render-manifest.json')['rows']==manifest
 with job(b,name,'ai','固定'+engine+'全48波形',48,100000000,3000) as j:
  with b.workspace(j,'二ASRの同コホート内容評価 '+engine,32000000,64000000) as (work,env):
   env_settings(env);value=observe(b,work,env,[str(PYTHON),'-B',str(HERE/'asr_worker.py'),'--engine',engine],'asr-'+engine,j,here,method='evaluation',timeout=2700)
  assert len(value['rows'])==48 and value['ai_calls']<=48
  b.write_data(here/'data/results.json',encode(value),j);b.save(here/'asr-manifest.json',dict(path=str((here/'data/results.json').relative_to(REPO)),sha256=digest(here/'data/results.json'),new_AI_reserved=48,new_AI_actual=value['ai_calls']),j)
 seal_close(b,here,name,dict(engine=engine,expected=48,completed=sum(x['status']=='completed' for x in value['rows']),missing=sum(x['status']!='completed' for x in value['rows']),optimization_after_ASR=False,quality_goal_completed=False));print(engine+' 48件評価を保存',flush=True)
def close():
 b=Budget();b.recover();verify();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values())
 # 全体集計は管理契約。新render/AI/DSPは発生させない。
 label='whole-summary';here,name=campaign_location(label);lim=limits()
 b.start_campaign(name,str(here.relative_to(ROOT)),lim,digest(HERE/'protocol.json'),purpose='management')
 with job(b,name,'audit','同コホート全48/33系列/対照差/工学/費用の集計',size=12000000) as j:
  reg=dict(protocol_sha256=digest(HERE/'protocol.json'),all_denominators_kept=True,new_scientific_calls=0,quality_goal_completed=False);b.save(here/'registration.json',reg,j)
  module=(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/summarize.py').read_text();node=next(n for n in ast.parse(module).body if isinstance(n,ast.FunctionDef) and n.name=='grouped');scope={};exec(ast.get_source_segment(module,node),scope);grouped=scope['grouped']
  engineering={m:dict(expected=16,E0_pass=0,pitch_pass=0,missing_records=0,fixed_support_intervals=0,missing_support=0) for m in METHODS}
  for plan in read(HERE/'render-plan.json')['batches']:
   source,_=campaign_location(plan['mode']+'-'+plan['length']+'-'+plan['condition'])
   for n,h in read(source/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
   if plan['mode']=='normal':
    for m,z in read(source/'aggregate-summary.json')['engineering'].items():
     for k in engineering[m]:
      if k!='expected':engineering[m][k]+=z[k]
  content={}
  for engine in ['whisper','reazon']:
   source,_=campaign_location('asr-'+engine);manifest=read(source/'asr-manifest.json');assert digest(REPO/manifest['path'])==manifest['sha256'];data=read(REPO/manifest['path']);records={x['id']:x for x in data['rows']};content[engine]={}
   for method,reference in [('baseline','native'),('learned','native'),('learned','baseline')]:
    pairs=[]
    for row in read(HERE/'protocol.json')['rows']:
     for c in CONDITIONS:
      x=records[row['id']+'/'+c+'/'+method];n=records[row['id']+'/'+c+'/'+reference];assert x['reference_kana']==n['reference_kana'] and x['characters']==n['characters']
      pairs.append(dict(text_id=row['id'],condition=c,length=row['length'],challenge_group=row['challenge_group'],status='completed' if x['status']==n['status']=='completed' else 'missing',errors=x['errors'],native_errors=n['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],reference_hypothesis=n['hypothesis']))
    groups=grouped(pairs);content[engine][method+'_vs_'+reference]=dict(groups=groups,active_groups=sum(z['expected']>0 for z in groups.values()),zero_denominator_groups=[k for k,z in groups.items() if z['expected']==0],worsening_active_groups=[k for k,z in groups.items() if z['expected'] and not z['non_worsening']],all_33_non_worsening=all(z['non_worsening'] for z in groups.values()),pairs=pairs)
  summary=dict(inputs=8,conditions=2,methods=METHODS,expected_normal=48,expected_isolated=48,CLI=3,engineering=engineering,content=content,frozen_coefficients=True,actual_generalizable_speech_improvement_verified=False,perceptual_qualification=False,quality_goal_completed=False,P5_opened=False,adopted=False,prior_CV_k_t_joint_qualified=0,prior_CV_s_unperformed=True,D_allocation_consumed_render=check_D(b),D_allocation_maximum=36000,limitations='短3/長4モーラの限定診断、未対応groups4..7は0分母/不通過、e/o未学習、無声化未実装。C不通過・知覚/独立P5不足を本結果で救済しない。',next='全体封印と工程D境界をレビューし、音声改善へ届かなかった原因と残資源を基に、次の新機構/訓練資料/条件を別登録する。旧比較と24時間工程時計を巻戻さない。')
  b.write_data(here/'data/summary.json',encode(summary),j);compact=dict(summary);compact['content']={e:{m:{k:v for k,v in z.items() if k!='pairs'} for m,z in methods.items()} for e,methods in content.items()};b.save(here/'summary-details-manifest.json',dict(path=str((here/'data/summary.json').relative_to(REPO)),sha256=digest(here/'data/summary.json')),j)
 seal_close(b,here,name,compact);print(json.dumps(dict(engineering=engineering,content={e:{m:z['worsening_active_groups'] for m,z in methods.items()} for e,methods in content.items()},quality_goal_completed=False),ensure_ascii=False),flush=True)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture-register','fixture','batch-register','batch','asr-register','asr','close']);p.add_argument('--mode',choices=['normal','isolated']);p.add_argument('--length',choices=['short','long']);p.add_argument('--condition',choices=list(CONDITIONS));p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args()
 if a.stage in ['batch-register','batch']:globals()[a.stage.replace('-','_')](a.mode,a.length,a.condition)
 elif a.stage in ['asr-register','asr']:globals()[a.stage.replace('-','_')](a.engine)
 else:globals()[a.stage.replace('-','_')]()
