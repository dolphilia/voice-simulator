"""Aで登録した15CVを三組に分け、固定共有係数の移転を開発診断する。"""
import argparse,ast,hashlib,json,os
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget,check_plan
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2];PREFLIGHT=ROOT/'campaigns/nas-vtl-shared-cv-preflight-20261009-v1'
NATIVE=ROOT/'campaigns/nas-vtl-shared-vowel-fit-20261009-u-v2/native-bundle'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
def location(group):
 assert group in 'kts';return ROOT/('campaigns/nas-vtl-shared-cv-development-20261009-'+group+'-v1'),'vtl-shared-cv-development-'+group+'-v1'
@contextmanager
def job(b,name,kind,label,count=1,size=0,seconds=600):
 j=b.reserve(name,kind,label,count,size,expected_seconds=seconds)
 try:yield j
 except BaseException as e:b.finish(j,repr(e));raise
 else:b.finish(j)
def verify(here):
 c=read(here/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(REPO/n)==h,n
def register(group):
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due'];assert read(PREFLIGHT/'aggregate-summary.json')['preflight_passed'];check_plan(s,7200);here,name=location(group);worker=(ROOT/'vtl_shared_cv_development_worker_20261009.py').read_text();ast.parse(worker)
 kana={'k':'カキクケコ','t':'タチツテト','s':'サシスセソ'}[group];onsets={'k':['k']*5,'t':['t','ch','ts','t','t'],'s':['s','sh','s','s','s']}[group];cases=[]
 pre={x['id']:x for x in read(PREFLIGHT/'normal-audit.json')['rows']}
 for char,v,onset in zip(kana,'aiueo',onsets):
  token=onset+v;case=dict(id=token,kana=char,vowel=v,onset=onset,pure_k_t_s_CV=onset in 'kts',reuse={})
  for method in ['baseline','learned']:
   key=token+'-'+method
   if key in pre:
    row=pre[key];path=PREFLIGHT/'audio/normal'/(key+'.wav');assert digest(path)==row['meta']['wav_sha256'];case['reuse'][method]=dict(path=str(path),wav_sha256=row['meta']['wav_sha256'],meta=row['meta'],role='既に見た開発資料。新独立品質証拠ではない。')
  cases.append(case)
 assert sum(len(x['reuse']) for x in cases)==2
 limits=dict(seconds=7200,bytes=128000000,write_bytes=800000000,setup=8,audit=8,render=3000,dsp=600,ai=0,teacher=0,train=0,inverse=0,download=0)
 reg=dict(question='共有aiu六係数の訓練包絡改善が、未fitの'+group+'行五CV/F0=140Hzへ移転するか。',controller_sha256=digest(Path(__file__)),worker_sha256=digest(ROOT/'vtl_shared_cv_development_worker_20261009.py'),shared_model_sha256=digest(PREFLIGHT/'runtime-bundle/shared-model.json'),preflight_seal_sha256=digest(PREFLIGHT/'artifact-seal.json'),native_manifest_sha256=digest(NATIVE/'manifest.json'),cases=cases,methods=['native','baseline','learned'],F0_Hz=140,seed=41,speed=1.,gain=dict(native=.25,VTL=.5),roles=dict(development='Aの15CVを三組に分割。五CV×三方式を全分母に保持。未使用品質確認ではない。',reused='小事前検査の三CV六出力を各組二つ再使用。再生成しない。',reference='同コホートnative共有モデルの新生成。教師内部state境界を実境界真値にしない。',P5_opened=False),gates=dict(E0='旧評価器の全E0。',pitch='各生成器の母音区間中央60%。DIO/stonemaskとACF±1半音/confidence.6、有声3frame/半数以上。単CV診断で旧発話3音素支持の資格ではない。',admissibility='同ケースのnative/既定/学習の全工学が通過したときだけ距離改善を適格な開発改善とする。欠測/不通過は全15分母へ保持。',objective='訓練と同一の500..4000Hz/20帯域/Welch1024/512/4096/ln2÷6/平均引きshape MSE。gain/時刻/係数を調整しない。',scientific_generation_failures='既存native LF0値域不通過は失敗行として記録し、その条件を再試行せず次の未実施行へ進む。',content_ASR_or_perceptual_claim=False),parameters_frozen=True,new_fit_or_inverse=0,estimates=dict(new_VTL_waveforms=8,reused_VTL_waveforms=2,new_native_attempts=5,actual_render_at_most=1381,render_reservation=1400,DSP_reservation=300,work_peak_bytes=32000000,work_write_bytes=64000000,render_job_reservation_bytes=80000000,WAV_bytes_at_most=1500000,JSON_bytes_at_most=600000,RAM_bytes_at_most=1500000000,control_index_failure_Git_included=True),limits=limits,quality_goal_completed=False,protected_confirmation_opened=False,next='k→tを診断し科学60終了後にレビュー10を先に実施。その後sへ進み、全15CVの開発結果と不通過を統合して工程Dの未使用入力比較を出力前登録する。')
 assert reg['estimates']['work_peak_bytes']<=reg['estimates']['render_job_reservation_bytes']
 b.start_campaign(name,str(here.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
 with job(b,name,'setup','五CV三方式/再使用/固定中央窓/目的/全費用を初出力前固定',size=6000000) as j:
  b.save(here/'registration.json',reg,j);b.write(here/'worker.py',worker.encode(),j);paths=[Path(__file__),ROOT/'vtl_shared_cv_development_worker_20261009.py',here/'worker.py',here/'registration.json',PREFLIGHT/'runtime-bundle/manifest.json',NATIVE/'manifest.json']
  paths += [PREFLIGHT/'runtime-bundle'/n for n in read(PREFLIGHT/'runtime-bundle/manifest.json')['files']]+[NATIVE/n for n in read(NATIVE/'manifest.json')['files']]
  b.save(here/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(REPO)):digest(p) for p in paths}),j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=name,next='登録push後、五CVの固定開発診断。二既出VTL波形を再生成せず測定資料として再使用。',git_save_pending=True);b._write_state(s)
 b.save(ROOT/('vtl-shared-cv-development-register-'+group+'-20261009.json'),dict(active_campaign=name,registered_before_outputs=True,budget=b.reconcile()));print(group+'行CVの開発診断を初出力前登録')
def run(group):
 b=Budget();b.recover();here,name=location(group);verify(here)
 with job(b,name,'render','五CVの未実施八VTL候補と五native参照の内部生成費',1400,80000000,900) as j:
  with job(b,name,'dsp','再使用二波形を含む全15CVの固定E0/F0/包絡',300,2000000,900) as dj:
   with b.workspace(j,'五CV三方式の固定開発診断と各行中間保存',32000000,64000000) as (work,env):
    env.update(PYTHONPATH=str(ROOT/'campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    stdout,stderr,obs=run_observed([str(PYTHON),'-B',str(here/'worker.py'),str(PREFLIGHT/'runtime-bundle'),str(NATIVE),str(work),str(here)],env,work,label='CV-development',timeout=840);b.save(here/'process-observation.json',obs,j)
    if obs['returncode']!=0:
     if (work/'partial.json').exists():b.write_data(here/'data/partial.json',(work/'partial.json').read_bytes(),j)
     for p in work.glob('*.wav'):b.write_data(here/'partial-audio'/p.name,p.read_bytes(),j)
     b.save(here/'failure.json',dict(stdout=stdout,stderr=stderr),j);raise RuntimeError('CV開発の技術起動不成立')
    counts=json.loads(stdout);assert counts['rows']==15 and counts['cases']==5 and counts['completed_render_calls']<=1400 and counts['reused_waveforms']==2
    b.save(here/'generation-counts.json',counts,j);b.write_data(here/'data/grid.json',(work/'grid.json').read_bytes(),j)
    for n in counts['generated_files']:b.write_data(here/'audio'/n,(work/n).read_bytes(),j)
 with job(b,name,'audit','五CV全方式/不通過/再使用/開発差/全費用/一時回収を封印',size=4000000) as j:
  data=read(here/'data/grid.json');by={}
  for method in ['native','baseline','learned']:
   rows=[x for x in data['rows'] if x['method']==method];assert len(rows)==5
   by[method]=dict(total=5,generated_waveforms=sum(bool(x['wav_sha256']) and not x['render_reused'] for x in rows),reused_waveforms=sum(x['render_reused'] for x in rows),E0_pass=sum(bool(x['measurement'] and x['measurement']['E0']['E0_pass']) for x in rows),pitch_pass=sum(bool(x['measurement'] and x['measurement']['pitch']['passed']) for x in rows),missing_measurements=sum(x['measurement'] is None for x in rows))
  cases=data['cases'];summary=dict(group=group,methods=by,cases=cases,case_total=5,waveform_denominator=15,joint_qualified_cases=sum(x['joint_comparison_valid'] for x in cases),qualified_shape_improvements=sum(x['qualified_shape_improvement'] for x in cases),qualified_shape_worsenings=sum(x['qualified_shape_worsening'] for x in cases),coefficients_not_adjusted=True,development_only=True,content_or_naturalness_or_generalization_verified=False,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False);b.save(here/'aggregate-summary.json',summary,j)
  s=b.snapshot();c=s['campaigns'][name];tmp=[x for x in s['temporary_work'].values() if x['campaign']==name];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(here/'cost-audit.json',dict(counts=c['counts'],actual=read(here/'generation-counts.json'),seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,process=read(here/'process-observation.json')),j)
  lines=['# '+group+'行CVの固定開発診断','','五CV×native/既定/学習の全15分母。既出二波形は再生成せず開発資料として再使用。共有係数・時刻・gain・ゲートを変更しない。','','|CV|共通工学|既定shape MSE|学習shape MSE|適格改善|適格悪化|','|---|---|---:|---:|---|---|']+[f"|{x['kana']}|{x['joint_comparison_valid']}|{x['baseline_shape_MSE']}|{x['learned_shape_MSE']}|{x['qualified_shape_improvement']}|{x['qualified_shape_worsening']}|" for x in cases]+['','単CVの音素診断であり、内容ASR・旧最低三音素支持・自然さ・一般化を認定しない。全失敗/欠測を保持。品質未達、知覚資格なし、P5未開封。']
  b.write(here/'report.md','\n'.join(lines).encode(),j);b.save(here/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in here.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(name)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=None,next=read(here/'registration.json')['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/('vtl-shared-cv-development-completed-'+group+'-20261009.json'),dict(result=summary,review=b.review_due(),budget=b.reconcile()));print(json.dumps(dict(group=group,joint_qualified_cases=summary['joint_qualified_cases'],qualified_improvements=summary['qualified_shape_improvements'],qualified_worsenings=summary['qualified_shape_worsenings']),ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','run']);p.add_argument('group',choices=list('kts'));a=p.parse_args();globals()[a.stage](a.group)
