"""母音別のTCX/TCY有限直接学習。生成/測定とfitを分け、旧凍結を維持。"""
import argparse,ast,hashlib,json,os,time,resource
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2];PREFLIGHT=ROOT/'campaigns/nas-vtl-shared-target-preflight-20261009-v1';NATIVE=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1/native-bundle';PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
WORKER=r"""\"\"\"実VTL候補の全包絡/工学とnative参照を固定方法で測定する。\"\"\"
import sys,json,io,re,hashlib,os,tempfile
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
import pyworld
here=Path(sys.argv[1]);work=Path(sys.argv[2]);vowel=sys.argv[3];assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
sys.path.insert(0,str(here/'runtime-bundle'));from vtl_runtime import VTL
sys.path.insert(0,str(here/'native-bundle'));from runtime import generate as native,verify
from acoustics import evaluate,estimate_f0
verify();spec=json.loads((here/'registration.json').read_text());centers=np.geomspace(500.,4000.,20);sigma=np.log(2)/6
measure_calls=0
def measure(data,bounds,target):
 global measure_calls
 fs,audio=wavfile.read(io.BytesIO(data));assert fs==24000;audio=audio.astype(float);e0=evaluate(audio,{},fs);measure_calls+=3
 start,end=bounds;core=audio[round(start*fs):round(end*fs)];assert len(core)>=1024
 f0,times=pyworld.dio(audio,fs,f0_floor=70.,f0_ceil=400.,frame_period=5.);f0=pyworld.stonemask(audio,f0,times,fs);measure_calls+=2
 mask=(times>=start)&(times<end);voiced=f0[mask&(f0>=70)&(f0<=400)];dio=float(np.median(voiced)) if len(voiced) else None;acf,conf=estimate_f0(core,fs,minimum=70,maximum=400);measure_calls+=1
 def error(hz):return float(abs(12*np.log2(hz/target))) if hz and hz>0 else None
 de,ae=error(dio),error(acf);support=bool(int(mask.sum())>=3 and len(voiced)>=3 and len(voiced)>=int(mask.sum())*.5);passed=bool(e0['E0_pass'] and support and de is not None and ae is not None and de<=1. and ae<=1. and conf>=.6)
 freq,power=signal.welch(core,fs=fs,window='hann',nperseg=1024,noverlap=512,nfft=4096,detrend='constant',scaling='density',average='mean');measure_calls+=1
 weights=np.exp(-.5*(np.log(np.maximum(freq[:,None],1.)/centers[None,:])/sigma)**2);band=(power[:,None]*weights).sum(axis=0)/weights.sum(axis=0);shape=10*np.log10(np.maximum(band,1e-20));shape-=shape.mean()
 return dict(E0=e0,pitch=dict(dio_Hz=dio,ACF_Hz=acf,ACF_confidence=conf,dio_error_semitones=de,ACF_error_semitones=ae,central_interval_frames=int(mask.sum()),voiced_frames=len(voiced),single_interval_support=support,passed=passed,not_utterance_three_phone_support=True),central_window_seconds=[start,end],engineering_diagnostic_pass=passed,shape_log_power_dB=shape.tolist())
refs={};all_rows=[];render_calls=0;text=dict(zip('aiueo',['ア','イ','ウ','エ','オ']))[vowel]
for target in [120.,160.]:
 data,meta,params,row=native(text,1.,target,full=True);render_calls+=meta['conversion']['render_calls_including_internal_MLSA'];measure_calls+=3;phone_indices=[i for i,label in enumerate(row['full_context_labels']) if re.search(r'\-([^+]+)\+',label).group(1).lower()==vowel];assert len(phone_indices)==1
 i=phone_indices[0];bounds=np.r_[0,np.cumsum(meta['duration'])]*.005;start,end=float(bounds[i*5]),float(bounds[(i+1)*5]);width=end-start;central=[start+.2*width,end-.2*width];measurement=measure(data,central,target);ident='native-'+str(int(target));(work/(ident+'.wav')).write_bytes(data)
 refs[str(int(target))]=dict(id=ident,text=text,target_F0_Hz=target,wav_sha256=hashlib.sha256(data).hexdigest(),source_phone_label_index=i,source_state_interval_seconds=[start,end],label_boundary_not_observed_truth=True,measurement=measurement,native_gain=.25)
vtl=VTL()
try:
 for c in spec['candidates']:
  for target in [120.,160.]:
   ident=c['id']+'-'+str(int(target));data,meta=vtl.render(vowel,target,.32,41,c['dx_cm'],c['dy_cm']);render_calls+=meta['render_calls'];(work/(ident+'.wav')).write_bytes(data);measurement=measure(data,[.064,.256],target);ref=refs[str(int(target))]['measurement'];distance=float(np.mean((np.asarray(measurement['shape_log_power_dB'])-np.asarray(ref['shape_log_power_dB']))**2));valid=bool(measurement['engineering_diagnostic_pass'] and ref['engineering_diagnostic_pass'])
   all_rows.append(dict(id=ident,candidate_id=c['id'],target_F0_Hz=target,dx_cm=c['dx_cm'],dy_cm=c['dy_cm'],wav_sha256=hashlib.sha256(data).hexdigest(),meta=meta,measurement=measurement,reference_engineering_pass=ref['engineering_diagnostic_pass'],admissible=valid,shape_distance=distance,role='training candidate; not unused comparison'))
finally:vtl.close()
assert len(all_rows)==18 and render_calls<=3000 and measure_calls<=300
value=dict(vowel=vowel,references=refs,rows=all_rows,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,fit_performed=False,quality_goal_completed=False,protected_confirmation_opened=False)
(work/'grid.json').write_text(json.dumps(value,ensure_ascii=False,allow_nan=False));print(json.dumps(dict(vowel=vowel,rows=18,references=2,actual_render_calls=render_calls,actual_DSP_macro_calls=measure_calls,output_files=[x['id']+'.wav' for x in all_rows]+[x['id']+'.wav' for x in refs.values()])))
"""
WORKER=WORKER.replace('\\"','"')
def location(vowel):
 assert vowel in 'aiueo';return ROOT/('campaigns/nas-vtl-shared-vowel-fit-20261009-'+vowel+'-v2'),'vtl-shared-vowel-fit-'+vowel+'-v2'
@contextmanager
def job(b,name,kind,label,count=1,size=0,seconds=600):
 token=b.reserve(name,kind,label,count,size,expected_seconds=seconds)
 try:yield token
 except BaseException as e:b.finish(token,repr(e));raise
 else:b.finish(token)
def verify(here):
 c=read(here/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(here/n)==h,n
 return c
def register(vowel):
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due'];assert read(PREFLIGHT/'aggregate-summary.json')['preflight_passed'];assert s['research_execution_plan']['first_stage']['current']=='C';ast.parse(WORKER);here,name=location(vowel)
 limits=dict(seconds=7200,bytes=200000000,write_bytes=1000000000,setup=20,audit=12,render=6000,dsp=600,ai=0,teacher=0,train=1,inverse=1,download=0);check_plan(s,limits['seconds'])
 candidates=[dict(id='grid-'+str(i),dx_cm=dx,dy_cm=dy) for i,(dx,dy) in enumerate(( (x,y) for x in [-.4,0.,.4] for y in [-.4,0.,.4]))]
 reg=dict(question='共有'+vowel+'母音のTCX/TCY二係数を、二F0の日本語native参照と実VTL波形の有限包絡損失から直接推定できるか。',vowel=vowel,controller_sha256=digest(Path(__file__)),preflight_seal_sha256=digest(PREFLIGHT/'artifact-seal.json'),stage_A_design_sha256=digest(ROOT/'campaigns/nas-research-resume-stage-A-20261009-v1/stage-A-design.json'),candidates=candidates,seed=41,F0_conditions=[120,160],VTL_duration_seconds=.32,VTL_gain=.5,native_gain=.25,
 roles=dict(train='再使用のnative共有モデルが生成する当該単独母音。生成内部state中央60%を切出すが実測音素境界とはしない。',development='本契約ではCV生成なし。五母音係数を統合後、A登録の少数CVを別契約で測定。',unused_selection='本文未作成・未評価。訓練/開発出力を選別未使用証拠へ戻さない。',P5_opened=False),
 objective=dict(method='direct non-neural independent 9-grid per vowel',parameters=2,Welch=dict(fs=24000,window='hann',nperseg=1024,noverlap=512,nfft=4096,detrend='constant',scaling='density',average='mean'),centers_Hz=dict(first=500,last=4000,geomspace_points=20),log_frequency_Gaussian_sigma='ln(2)/6',power_floor=1e-20,shape='10log10(帯域平均power)から20帯域平均を引く',loss='二F0のshape MSEを等重み平均 + .01*(dx^2+dy^2)',gain_optimized=False,regularization=.01,tie_break='objective、offset平方和、grid登録順。zeroを候補に保持。'),
 gates=dict(E0='既存acoustics評価の全E0。閾値を変更しない。',pitch='固定中央一母音区間: DIO/stonemask中央値とACF±1半音/confidence.6。DIO3frame以上/区間の半数以上が有声。単独母音の診断だけであり旧発話最低3音素支持を満たしたとは称さない。',joint_F0='両F0の候補とnative参照が全通過した候補だけを選ぶ。欠測/失敗を全18分母に保持。',all_candidates_invalid='baseline二係数0を保存し未資格。ゲート・候補・窓・gainを救済しない。',optimization_improvement='baselineが同じ診断を通過した場合だけobjective/shape MSEを比較。訓練適合を内容/自然さ/一般化へ移さない。'),
 stopping=dict(fit_seconds=1800,max_updates=18,max_parameters=2,fit_runs=1,inverse_runs=1,finite_candidates=9,no_seed_CV_or_condition_hidden_fits=True),
 estimates=dict(render=2380,actual_render_expected=18*132+2,DSP=160,fit=1,inverse=1,shared_runtime_size=sum((p.stat().st_size) for p in (PREFLIGHT/'runtime-bundle').iterdir() if p.is_file())+sum((NATIVE/n).stat().st_size for n in read(NATIVE/'manifest.json')['files']),WAV_encoded_total_at_most=2000000,grid_JSON_at_most=1500000,temporary_peak=32000000,temporary_write=64000000,max_logs=2000000,array_RAM_expected_at_most=1000000000,ledger_index_failed_job_Git_included=True),limits=limits,quality_goal_completed=False,protected_confirmation_opened=False,next='全18実波形/二参照を計測してから一fit/一inverseで共有二係数を選別し凍結。次母音を別契約で登録し、科学54件終了後レビュー9を先に行う。aは未測定、学習した係数数を実数で示す。')
 b.start_campaign(name,str(here.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),expansion_reason='実2378内部renderの単位を事前確認済み。予約2380を使い、技術起動不成立の有限一回再試行まで契約内に確保するため開始前に6000上限を登録。a旧失敗/3000予約は保持し再初期化しない。')
 with job(b,name,'setup','有限九標的/二F0/窓/目的関数/全費用/範囲を初出力前固定',size=80000000) as j:
  b.save(here/'registration.json',reg,j)
  with b.workspace(j,'既存pyworld評価packageのimportだけを出力前に確認',16000000,32000000) as (work,env):
   package=ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2';env.update(PYTHONPATH=str(package),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
   stdout,stderr,observed=run_observed([str(PYTHON),'-B','-c','import json,pyworld;print(json.dumps(dict(version=pyworld.__version__,file=pyworld.__file__)))'],env,work,label='dependency-import',timeout=60)
   b.save(here/'dependency-import-audit.json',dict(observation=observed,stdout=stdout,stderr=stderr,no_waveforms_no_DSP=True),j)
   assert observed['returncode']==0 and str(package) in json.loads(stdout)['file']
  for n,h in read(PREFLIGHT/'runtime-bundle/manifest.json')['files'].items():
   assert digest(PREFLIGHT/'runtime-bundle'/n)==h
   if n not in ['probe.py','acoustics.py']:b.write(here/'runtime-bundle'/n,(PREFLIGHT/'runtime-bundle'/n).read_bytes(),j)
  for n,h in read(NATIVE/'manifest.json')['files'].items():
   assert digest(NATIVE/n)==h;b.write(here/'native-bundle'/n,(NATIVE/n).read_bytes(),j)
  for directory in ['runtime-bundle','native-bundle']:
   folder=here/directory;b.save(folder/'manifest.json',dict(files={str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file()},neural=False,utterance_table=False),j)
  b.write(here/'worker.py',WORKER.encode(),j);b.save(here/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(here)):digest(p) for p in here.rglob('*') if p.is_file()}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=name,next='登録push後に全候補の実VTL生成/測定→直接finite fit→限定訓練適合を封印。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/('vtl-fit-register-'+vowel+'-20261009.json'),dict(active_campaign=name,registered_before_outputs=True,vowel=vowel,quality_goal_completed=False,budget=b.reconcile()));print('共有母音'+vowel+'の有限直接学習を登録')
def generate(vowel):
 b=Budget();b.recover();here,name=location(vowel);verify(here)
 with job(b,name,'render','全18VTL候補と二native参照の内部生成費',2380,100000000,1200) as j:
  with job(b,name,'dsp','全20波形のE0/固定中央F0/包絡の同時事前予約',160,2000000,1200) as dj:
   with b.workspace(j,'当該母音の実候補18/二native参照と包絡距離の学習一時領域',32000000,64000000) as (work,env):
    env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    stdout,stderr,observed=run_observed([str(PYTHON),'-B',str(here/'worker.py'),str(here),str(work),vowel],env,work,label='grid',timeout=1100);b.save(here/'grid-process-observation.json',observed,j)
    if observed['returncode']!=0:
     b.save(here/'grid-child-failure.json',dict(stdout=stdout,stderr=stderr,observation=observed),j);raise RuntimeError('共有母音grid生成/計測不通過')
    value=json.loads(stdout);assert value['rows']==18 and value['references']==2 and value['actual_render_calls']<=3000 and value['actual_DSP_macro_calls']<=300
    b.write_data(here/'data/grid.json',(work/'grid.json').read_bytes(),j)
    for n in value['output_files']:b.write_data(here/'audio'/n,(work/n).read_bytes(),j)
    b.save(here/'generation-counts.json',value,j)
 print('共有母音'+vowel+'の全候補実生成・固定測定を保存')
def fit(vowel):
 b=Budget();b.recover();here,name=location(vowel);verify(here);started=time.monotonic()
 with job(b,name,'train','固定測定から九候補二F0を有限直接fit',1,4000000,60) as tj:
  with job(b,name,'inverse','共有二舌標的の九候補を直接逆推定',1,1000000,60) as ij:
   grid=read(here/'data/grid.json');reg=read(here/'registration.json');scores=[]
   for c in reg['candidates']:
    rows=[x for x in grid['rows'] if x['candidate_id']==c['id']];assert len(rows)==2;valid=all(x['admissible'] for x in rows);mse=sum(x['shape_distance'] for x in rows)/2;penalty=.01*(c['dx_cm']**2+c['dy_cm']**2);scores.append(dict(**c,admissible=valid,mean_shape_MSE=mse,regularization=penalty,objective=mse+penalty,engineering=[x['measurement']['pitch'] for x in rows]))
   feasible=[x for x in scores if x['admissible']];baseline=next(x for x in scores if x['dx_cm']==x['dy_cm']==0.)
   selected=min(feasible,key=lambda x:(x['objective'],x['dx_cm']**2+x['dy_cm']**2,int(x['id'].split('-')[1]))) if feasible else baseline
   trained=bool(feasible);comparison=bool(trained and baseline['admissible']);improved=bool(comparison and selected['objective']<baseline['objective']-1e-8)
   model=dict(vowel=vowel,TCX_delta_cm=selected['dx_cm'] if trained else 0.,TCY_delta_cm=selected['dy_cm'] if trained else 0.,shared_parameters=2,fit_valid=trained,training_improved=improved,seed=41,source_sha256=digest(here/'data/grid.json'),baseline_and_selected_gain_fixed=.5,role='training fit; development and unused comparison pending; a startup failure remains unmeasured',not_natural_speech_quality_certificate=True)
   wall=time.monotonic()-started;assert wall<1800
   result=dict(model=model,scores=scores,all_candidates=9,generated_waveforms=20,candidate_training_waveforms=18,missing_or_failed_candidates=sum(not x['admissible'] for x in scores),reference_engineering=[x['measurement']['engineering_diagnostic_pass'] for x in grid['references'].values()],baseline=baseline,selected=selected,baseline_comparison_valid=comparison,training_objective_improved=improved,fit_runs=1,inverse_runs=1,updates=18,wall_seconds=wall,controller_cumulative_ru_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,process_group_contains_no_child=True,training_actual_waveforms_verified=True,development_or_unused_content_or_perception_improvement_verified=False,quality_goal_completed=False,protected_confirmation_opened=False)
   b.save(here/'shared-vowel-model.json',model,tj);b.save(here/'fit-summary.json',result,tj)
 print(json.dumps(dict(vowel=vowel,fit_valid=trained,training_improved=improved,selected=[model['TCX_delta_cm'],model['TCY_delta_cm']],valid_candidates=len(feasible)),ensure_ascii=False))
def close(vowel):
 b=Budget();b.recover();here,name=location(vowel);verify(here);result=read(here/'fit-summary.json')
 with job(b,name,'audit','全九候補/欠測/訓練適合/全費用/回収を封印',size=3000000) as j:
  s=b.snapshot();c=s['campaigns'][name];tmp=[v for v in s['temporary_work'].values() if v['campaign']==name];assert c['counts']['train']==c['counts']['inverse']==1 and all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  model=result['model'];aggregate=dict(vowel=vowel,shared_model=model,admissible_candidates=9-result['missing_or_failed_candidates'],candidate_total=9,training_waveforms=18,references=2,training_objective_improved=result['training_objective_improved'],baseline_comparison_valid=result['baseline_comparison_valid'],baseline_shape_MSE=result['baseline']['mean_shape_MSE'],selected_shape_MSE=result['selected']['mean_shape_MSE'],baseline_objective=result['baseline']['objective'],selected_objective=result['selected']['objective'],fit_valid=model['fit_valid'],actual_generated_training_speech_only=True,content_or_perception_or_generalization_certified=False,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False,next=read(here/'registration.json')['next']);b.save(here/'aggregate-summary.json',aggregate,j)
  b.save(here/'cost-audit.json',dict(counts=c['counts'],actual_generation=read(here/'generation-counts.json'),seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,fit_30min_20000_updates_1million_params_respected=True),j)
  lines=['# 共有母音'+vowel+'の有限直接学習','','実VTLの九舌標的×二F0を全生成し、固定二native参照に対する包絡shapeを測定した。gainや窓をfitせず、二TCX/TCY係数だけを選んだ。再使用native生成器への訓練適合で、人の自然さ・語句内容・未知入力の改善ではない。','',f'許容候補 {aggregate["admissible_candidates"]}/9。選択 TCX={model["TCX_delta_cm"]:+.1f}cm、TCY={model["TCY_delta_cm"]:+.1f}cm。訓練objective改善: {aggregate["training_objective_improved"]}、baseline比較有効: {aggregate["baseline_comparison_valid"]}。全不通過/欠測を保持し、旧発話最低3音素支持を単独母音の一中央区間で通過したとは称さない。','',f'全18候補/二参照、2380render/160DSP予約、一fit/一inverseを計数。実生成費は{read(here/"generation-counts.json")["actual_render_calls"]}、DSP macroは{read(here/"generation-counts.json")["actual_DSP_macro_calls"]}。予約を返金せず全一時物を回収。','',aggregate['next'],'','品質未達・知覚資格なし・P5未開封。','']
  b.write(here/'report.md','\n'.join(lines).encode(),j);b.save(here/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in here.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(name)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(id='vtl-shared-vowel-'+vowel+'-completed',active_campaign=None,next=aggregate['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/('vtl-fit-completed-'+vowel+'-20261009.json'),dict(latest_completed=name,vowel=vowel,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()));print('共有母音'+vowel+'の訓練適合と全未資格を封印')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','generate','fit','close']);p.add_argument('vowel',choices=list('iueo'));a=p.parse_args();globals()[a.stage](a.vowel)
