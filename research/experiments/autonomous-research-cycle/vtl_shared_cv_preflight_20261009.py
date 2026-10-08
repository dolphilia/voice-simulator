"""共有aiu係数のCV移転前に入口・隔離・自己出力・内部費を少量検査する。"""
import argparse,ast,hashlib,json,os
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-vtl-shared-cv-preflight-20261009-v1';NAME='vtl-shared-cv-preflight-v1'
SOURCE=ROOT/'campaigns/nas-vtl-shared-target-preflight-20261009-v1/runtime-bundle'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
 token=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
 try:yield token
 except BaseException as e:b.finish(token,repr(e));raise
 else:b.finish(token)
def profile(b,work,isolated):
 s='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
 if isolated:
  s+='(deny file-read* (subpath '+json.dumps(str(REPO/'research'))+'))\n(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n'
  allowed=[PYTHON.parents[1],HERE/'runtime-bundle',work]
  s+='(allow file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in allowed)+')\n(allow file-read-data (subpath '+json.dumps(str(work))+'))\n(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n'
  site=PYTHON.parents[1]/'lib/python3.11/site-packages'
  s+='(deny file-read* '+''.join('(subpath '+json.dumps(str(site/n))+') ' for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'])+')\n(deny file-read-data (regex #"\\\\.htsvoice$"))\n'
  ancestors=set()
  for p in allowed:ancestors.update(p.parents)
  s+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(ancestors))+')\n'
 return s
def register():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due'];assert s['research_execution_plan']['first_stage']['current']=='C';check_plan(s,7200)
 expected={}
 for v in 'aiu':
  here=ROOT/('campaigns/nas-vtl-qualified-vowel-fit-20261009-'+v+'-v1');fit=read(here/'fit-summary.json');grid=read(here/'data/grid.json');assert fit['model']['fit_valid']
  row=next(x for x in grid['rows'] if x['candidate_id']==fit['selected']['id'] and x['target_F0_Hz']==280);expected[v]=row['wav_sha256']
 runtime=ROOT/'vtl_shared_cv_runtime_20261009.py';cli=ROOT/'vtl_shared_cv_cli_20261009.py';probe=ROOT/'vtl_shared_cv_probe_20261009.py'
 for p in [runtime,cli,probe]:ast.parse(p.read_text())
 limits=dict(seconds=7200,bytes=200000000,write_bytes=1000000000,setup=12,audit=12,render=6000,dsp=200,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(question='三母音の六共有係数が静的実VTL出力を再現し、三CVの通常/隔離/CLIと自己WAV再読取で共有非ニューラル生成に載るか。',controller_sha256=digest(Path(__file__)),shared_model_sha256=digest(ROOT/'vtl-shared-aiu-model-20261009.json'),source_manifest_sha256=digest(SOURCE/'manifest.json'),cases=[dict(id='ka',kana='カ',onset='k',vowel='a'),dict(id='chi',kana='チ',onset='ch',vowel='i',not_pure_ti=True),dict(id='su',kana='ス',onset='s',vowel='u')],F0_Hz=140,speed=1.,gain=.5,seed=41,static_training_reproduction=dict(F0_Hz=280,vowels=list('aiu'),expected_WAV_sha256=expected,not_new_quality_evidence=True),model_factor='TCX/TCYだけ。子音形状/声門template/規則/時刻はbaselineとlearnedで同一。e/oは既定・未学習。',timing=dict(leading_seconds=.05,consonant_seconds=.08,vowel_seconds=.24,trailing_seconds=.05,mora_seconds=.32,ramp_consonant=.02,ramp_vowel=.04,ramp_affricate=.025),onset_shapes=dict(k='tb-velar-closure',t='tt-alveolar-closure',s='tt-alveolar-fricative',sh='tt-postalveolar-fricative',ch='tt-postalveolar-closure→fricative',ts='tt-alveolar-closure→fricative',contexts='eはa、oはu、aiuは同名形状の文脈。',glottis='公開Geometric glottisのvoiceless-plosive/fricativeとmodalを同じ規則で補間。F0固定、pressure dPa。'),roles=dict(CV='Aで登録した15CVのうち三つの開発診断。次の15CVでは同条件の本六出力を再使用する。未使用品質証拠ではない。',static='訓練実波形の同一再現だけ。独立品質証拠ではない。',P5_opened=False),gates=dict(normal_isolated_CLI_exact=True,self_WAV_read_after_close=True,static_exact=True,all_E0=True,pitch='本入口ではE0と同一性だけ。DIO/ACFのCV母音診断は15CV別契約で登録。',previous_audio_reference_training_and_HTS_and_network_denied=True),estimates=dict(normal_render=1428,isolated_render=1032,CLI_render=1032,all_internal_render=3492,reservations=[1500,1100,1100],DSP_reservation=200,WAV_bytes_at_most=1200000,result_JSON_bytes_at_most=300000,work_peak_bytes=16000000,work_write_bytes=32000000,per_mode_job_reservation_bytes=60000000,RAM_expected_at_most=1500000000,control_index_failure_Git_included=True),limits=limits,quality_goal_completed=False,protected_confirmation_opened=False,next='同一性/拒否/全E0が成立したら共有CVコードを固定してAの15CVをnative/既定/学習で診断。三CV六出力を再生成せず再使用する。不通過なら本規則を未資格として保持して別の成立生成経路へ。')
 assert reg['estimates']['work_peak_bytes']<=reg['estimates']['per_mode_job_reservation_bytes']
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),expansion_reason='静的3+三CV×二方式×三入口の全内部3492renderを開始前計算。通常3000を超えるため6000を事前登録し、失敗した入口だけの有限技術再試行余裕を含む。')
 with job(b,'setup','共有六係数/CV規則/隔離とCLI/全費用を初出力前固定',size=60000000) as j:
  b.save(HERE/'registration.json',reg,j);bundle=HERE/'runtime-bundle'
  for n in ['JD3.speaker','libVocalTractLabApi.dylib','LICENSE-VTL','SOURCE.json','vtl_runtime.py','acoustics.py']:b.write(bundle/n,(SOURCE/n).read_bytes(),j)
  for p,n in [(runtime,'cv_runtime.py'),(cli,'cv_cli.py'),(probe,'probe.py'),(ROOT/'vtl-shared-aiu-model-20261009.json','shared-model.json')]:b.write(bundle/n,p.read_bytes(),j)
  b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},neural=False,utterance_lookup=False,stored_dense_trajectory=False,final_runtime=['cv_runtime.py','cv_cli.py','vtl_runtime.py','shared-model.json','JD3.speaker','libVocalTractLabApi.dylib'],diagnostics=['probe.py','acoustics.py']),j)
  b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=NAME,next='登録push後、小CVの通常/隔離/CLI・静的係数再現・close後自己読取・拒否・回収を検査。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-shared-cv-preflight-register-20261009.json',dict(active_campaign=NAME,registered_before_outputs=True,quality_goal_completed=False,budget=b.reconcile()));print('共有CV入口の小事前検査を登録')
def fixture():
 b=Budget();b.recover();c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(HERE/n)==h,n
 old=ROOT/'campaigns/nas-vtl-native-reference-conditions-20261009-v1';past=old/'audio/higher-longer-a-220.wav'
 blocked=[HERE/'registration.json',ROOT/'campaigns/nas-vtl-shared-vowel-fit-20261009-u-v2/native-bundle/mei_normal.htsvoice',past,past.resolve(),old/'data/references.json',(old/'data/references.json').resolve()]
 assert all(p.is_file() for p in blocked)
 results={}
 for mode,count in [('normal',1500),('isolated',1100),('cli',1100)]:
  with job(b,'render','CV-'+mode+'の全内部生成費',count,60000000,900) as j:
   with b.workspace(j,'三CVの'+mode+'出力とclose後自己読取',16000000,32000000) as (work,env):
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    cmd=['/usr/bin/sandbox-exec','-p',profile(b,work,mode!='normal'),str(PYTHON),'-B',str(HERE/'runtime-bundle/probe.py'),str(work),'--mode',mode,'--blocked',json.dumps([str(x) for x in blocked]) if mode!='normal' else '[]']
    stdout,stderr,observed=run_observed(cmd,env,work,label=mode,timeout=840);b.save(HERE/(mode+'-process.json'),observed,j)
    if observed['returncode']!=0:
     for p in work.glob('*.wav'):b.write_data(HERE/'partial-audio'/mode/p.name,p.read_bytes(),j)
     b.save(HERE/(mode+'-failure.json'),dict(stdout=stdout,stderr=stderr),j);raise RuntimeError('共有CV '+mode+'起動不成立')
    value=json.loads(stdout);assert value['network_permission_denied'] and not value['forbidden_imports']
    if mode!='normal':assert len(value['denial_probes'])==6 and all(x['denied'] for x in value['denial_probes'])
    assert sum(x['meta']['render_calls'] for x in value['rows'])<=count;results[mode]=value;b.save(HERE/(mode+'-audit.json'),value,j)
    for row in value['rows']:b.write_data(HERE/'audio'/mode/(row['id']+'.wav'),(work/(row['id']+'.wav')).read_bytes(),j)
 with job(b,'dsp','三CV二方式三入口と静的三係数再現の固定比較',200,4000000,300) as j:
  normal={x['id']:x for x in results['normal']['rows']};exact=True
  for mode in ['isolated','cli']:
   for row in results[mode]['rows']:exact &= row['meta']['wav_sha256']==normal[row['id']]['meta']['wav_sha256']
  expected=read(HERE/'registration.json')['static_training_reproduction']['expected_WAV_sha256'];static=all(normal['static-'+v]['meta']['wav_sha256']==h for v,h in expected.items());all_E0=all(x['E0']['E0_pass'] for a in results.values() for x in a['rows'])
  actual=sum(x['meta']['render_calls'] for a in results.values() for x in a['rows']);summary=dict(preflight_passed=bool(exact and static and all_E0),normal_isolated_CLI_exact=bool(exact),static_training_WAV_reproduction_exact=static,all_E0_pass=all_E0,E0_pass_count=sum(x['E0']['E0_pass'] for a in results.values() for x in a['rows']),waveform_total=21,actual_render_calls=actual,render_reservations=3700,isolated_denials_verified=True,close_then_self_read=True,phoneme_pitch_and_content_not_yet_qualified=True,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False,next=read(HERE/'registration.json')['next']);assert actual==3492;b.save(HERE/'aggregate-summary.json',summary,j)
 with job(b,'audit','共有CV入口の全分母/費用/一時不存在を封印',size=3000000) as j:
  s=b.snapshot();cc=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(HERE/'cost-audit.json',dict(counts=cc['counts'],seconds=s['seconds']-cc['start_seconds'],write_bytes=s['write_bytes']-cc['start_write_bytes'],all_owned_temporary_absent=True,observed_process={m:read(HERE/(m+'-process.json')) for m in results}),j)
  b.write(HERE/'report.md',('# 共有六係数のCV入口検査\n\nカ/チ/ス、F0=140Hz、baseline/learned、gain.5/seed41。同じ子音/声門/遷移規則で係数だけ変える。静的aiu三出力は280Hzの訓練波形再現を確認する。\n\n'+json.dumps(summary,ensure_ascii=False)+'\n\n母音F0支持・音素/語句内容・自然さ・一般化は本入口の資格に含めない。e/o未学習、無声化未実装、チはch/つはts/しはsh。全一時物を回収、品質未達、P5未開封。\n').encode(),j)
  b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/'vtl-shared-cv-preflight-completed-20261009.json',dict(result=summary,review=b.review_due(),budget=b.reconcile()));print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args();globals()[a.stage]()
