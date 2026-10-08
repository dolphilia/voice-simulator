"""共有舌標的の学習前にVTL API・独立起動・所有WAV再読取・費用を検査。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from research_plan_budget_20261009 import ResearchPlanBudget as Budget
from observed_process_20261009 import run_observed
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-vtl-shared-target-preflight-20261009-v1';NAME='vtl-shared-target-preflight-v1'
VTL=REPO/'research/experiments/autonomous-speech-synthesis/results/vtl-bundle-v2';NATIVE=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1/native-bundle';PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
RUNTIME=r"""\"\"\"共有VTL物理生成と二つの舌標的だけ。研究参照/学習/評価は読み込まない。\"\"\"
import ctypes as ct,hashlib,io,math
from pathlib import Path
import numpy as np
from scipy import signal
from scipy.io import wavfile
ROOT=Path(__file__).resolve().parent
class VTL:
 def __init__(self):
  self.lib=ct.CDLL(str(ROOT/'libVocalTractLabApi.dylib'));ptr=ct.POINTER(ct.c_double)
  self.lib.vtlInitialize.argtypes=[ct.c_char_p];self.lib.vtlGetTractParams.argtypes=[ct.c_char_p,ptr];self.lib.vtlGetGlottisParams.argtypes=[ct.c_char_p,ptr];self.lib.vtlSynthesisAddTract.argtypes=[ct.c_int,ptr,ptr,ptr]
  self.lib.vtlGetTractParamInfo.argtypes=[ct.c_char_p,ct.c_char_p,ct.c_char_p,ptr,ptr,ptr]
  self.check(self.lib.vtlInitialize(str(ROOT/'JD3.speaker').encode()))
  values=[ct.c_int() for _ in range(5)];rate=ct.c_double();self.check(self.lib.vtlGetConstants(*(ct.byref(v) for v in values),ct.byref(rate)))
  self.fs,self.ntube,self.ntract,self.nglottis,self.step=[v.value for v in values];assert self.fs==44100 and self.ntract==19 and self.step==110
  names=ct.create_string_buffer(1024);desc=ct.create_string_buffer(8192);units=ct.create_string_buffer(1024);lo=(ct.c_double*self.ntract)();hi=(ct.c_double*self.ntract)();standard=(ct.c_double*self.ntract)()
  self.check(self.lib.vtlGetTractParamInfo(names,desc,units,lo,hi,standard));self.names=names.value.decode().split('\t');self.bounds={self.names[i]:[lo[i],hi[i]] for i in range(self.ntract)};assert self.names[8:10]==['TCX','TCY']
  self.constants=dict(fs=self.fs,sections=self.ntube,tract_parameters=self.ntract,glottis_parameters=self.nglottis,step=self.step,internal_rate_Hz=rate.value)
 @staticmethod
 def check(code):
  if code:raise RuntimeError('VTL API失敗: '+str(code))
 def render(self,vowel,f0,duration=.32,seed=41,dx=0.,dy=0.):
  if vowel not in 'aiueo' or duration<=0 or not 70<=f0<=400:raise ValueError('対象母音/条件外')
  tract=(ct.c_double*self.ntract)();glottis=(ct.c_double*self.nglottis)();self.check(self.lib.vtlGetTractParams(vowel.encode(),tract));self.check(self.lib.vtlGetGlottisParams(b'modal',glottis));base=[tract[8],tract[9]]
  for index,delta in [(8,dx),(9,dy)]:
   requested=tract[index]+delta;lo,hi=self.bounds[self.names[index]]
   if not lo<=requested<=hi:raise ValueError('登録舌標的がAPI範囲外')
   tract[index]=requested
  glottis[0]=f0;ct.CDLL(None).srand(ct.c_uint(seed));self.check(self.lib.vtlSynthesisReset());empty=(ct.c_double*1)();self.check(self.lib.vtlSynthesisAddTract(0,empty,tract,glottis))
  samples=round(duration*self.fs);chunks=[];calls=0
  for start in range(0,samples,self.step):
   n=min(self.step,samples-start);buffer=(ct.c_double*n)();self.check(self.lib.vtlSynthesisAddTract(n,buffer,tract,glottis));chunks.append(np.array(buffer));calls+=1
  audio=signal.resample_poly(np.concatenate(chunks)*.5,80,147);fade=min(round(.012*24000),len(audio)//2);envelope=np.sin(np.linspace(0,np.pi/2,fade))**2;audio[:fade]*=envelope;audio[-fade:]*=envelope[::-1];audio[0]=audio[-1]=0.;audio=audio.astype(np.float32)
  buf=io.BytesIO();wavfile.write(buf,24000,audio);data=buf.getvalue();meta=dict(vowel=vowel,requested_f0_Hz=f0,duration_s=duration,seed=seed,TCXY_baseline_cm=base,TCXY_requested_cm=[tract[8],tract[9]],TCXY_delta_cm=[dx,dy],parameter_bounds=self.bounds,constant=self.constants,gain=.5,source_samples=samples,render_calls=calls+3,internal_AddTract_audio_calls=calls,initial_AddTract_zero_calls=1,reset_calls=1,outer_waveform_calls=1,wav_bytes=len(data),wav_sha256=hashlib.sha256(data).hexdigest(),shared_parameters=True,neural=False,teacher_or_saved_audio_read=False,geometry_joint_constraints_not_independently_qualified=True)
  return data,meta
 def close(self):self.check(self.lib.vtlClose())
"""
RUNTIME=RUNTIME.replace('\\"','"')
PROBE=r"""\"\"\"API定数・形状・出力close後の再読取と独立拒否の小検査。\"\"\"
import argparse,hashlib,json,os,socket,sys,tempfile
from pathlib import Path
from scipy.io import wavfile
from vtl_runtime import VTL
from acoustics import evaluate
p=argparse.ArgumentParser();p.add_argument('work');p.add_argument('--vowels',default='ai');p.add_argument('--blocked',default='[]');a=p.parse_args();work=Path(a.work);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
vtl=VTL();rows=[]
try:
 for vowel in a.vowels:
  data,meta=vtl.render(vowel,120.,.32,41);path=work/(vowel+'.wav');path.write_bytes(data);reread=path.read_bytes();assert reread==data and hashlib.sha256(reread).hexdigest()==meta['wav_sha256'];fs,audio=wavfile.read(path);assert fs==24000 and len(audio)==7680
  rows.append(dict(**meta,E0=evaluate(audio,dict(expected_duration_seconds=.32),24000),close_then_read_exact=True))
finally:vtl.close()
probes=[]
for n in json.loads(a.blocked):
 try:
  with Path(n).open('rb') as f:f.read(1)
 except PermissionError:probes.append(dict(path=n,denied=True))
 else:probes.append(dict(path=n,denied=False))
network=socket.socket();rc=network.connect_ex(('127.0.0.1',9));network.close()
print(json.dumps(dict(rows=rows,denial_probes=probes,network_error=rc,network_permission_denied=rc in (1,13),forbidden_imports=[n for n in sys.modules if n.split('.')[0] in ['torch','tensorflow','transformers','onnxruntime','faster_whisper','sherpa_onnx']])))
"""
PROBE=PROBE.replace('\\"','"')
@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
 j=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
 try:yield j
 except BaseException as e:b.finish(j,repr(e));raise
 else:b.finish(j)
def profile(b,work,isolated):
 s='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
 if isolated:
  s+='(deny file-read* (subpath '+json.dumps(str(REPO/'research'))+'))\n(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n'
  allowed=[PYTHON.parents[1],HERE/'runtime-bundle',work];s+='(allow file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in allowed)+')\n(allow file-read-data (subpath '+json.dumps(str(work))+'))\n(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n'
  site=PYTHON.parents[1]/'lib/python3.11/site-packages';s+='(deny file-read* '+''.join('(subpath '+json.dumps(str(site/n))+') ' for n in ['torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'])+')\n(deny file-read-data (regex #"\\\\.htsvoice$"))\n'
  ancestors=set()
  for p in allowed:ancestors.update(p.parents)
  s+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(ancestors))+')\n'
 return s
def register():
 b=Budget();b.recover();s=b.snapshot();assert s['research_execution_plan']['first_stage']['current']=='C' and not s['jobs'] and not b.review_due(s)['due'];ast.parse(RUNTIME);ast.parse(PROBE)
 limits=dict(seconds=7200,bytes=200000000,write_bytes=400000000,setup=12,audit=12,render=3000,dsp=200,ai=0,teacher=0,train=0,inverse=0,download=0)
 size=sum((VTL/n).stat().st_size for n in ['JD3.speaker','libVocalTractLabApi.dylib','LICENSE-VTL','SOURCE.json'])+sum((NATIVE/n).stat().st_size for n in read(NATIVE/'manifest.json')['files'])
 reg=dict(question='共有五母音のTCX/TCY直接学習に先立ち、凍結JD3のAPI/範囲/内部clock/通常・隔離・CLIと自己WAV再読取・回収を成立させられるか。',controller_sha256=digest(Path(__file__)),stage_A_design_sha256=digest(ROOT/'campaigns/nas-research-resume-stage-A-20261009-v1/stage-A-design.json'),VTL_manifest_sha256=digest(VTL/'manifest.json'),native_manifest_sha256=digest(NATIVE/'manifest.json'),scope='a/iの既定標的とF0=120Hz、320ms、seed41、gain.5。通常2/隔離2/CLI1の5波形のみ。内容/自然さ/五母音全工学の資格ではない。',conditions=dict(vowels=['a','i'],F0=120,duration_s=.32,seed=41,gain=.5),gates=dict(normal_isolated_CLI_hash_exact=True,output_reopen_exact=True,API_fs=44100,API_tract_params=19,API_step=110,API_TCXY_indices=[8,9],previous_audio_reference_HTS_and_network_denied=True),estimates=dict(shared_code_models_libraries_bytes=size,WAV_maximum_bytes=200000,raw_and_resample_arrays_peak=1000000,temporary_peak=16000000,temporary_write=32000000,maximum_logs_bytes=2000000,encoded_result_JSON_maximum_bytes=150000,render_reserved=1000,expected_internal_render=5*(129+3),DSP_reserved=10,memory_target=8000000000,all_ledger_index_audit_Git_included=True),limits=limits,quality_goal_completed=False,protected_confirmation_opened=False,next='全独立入口と内部生成費が成立すれば、各母音の九候補×二F0を初出力前固定しnative参照を使って直接有限学習する。初回不成立を保持し技術再試行は最大二回まで。')
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
 with job(b,'setup','VTL共有API/標的範囲/通常隔離CLI/領域計算を事前固定',size=60000000) as j:
  b.save(HERE/'registration.json',reg,j);bundle=HERE/'runtime-bundle'
  for n in ['JD3.speaker','libVocalTractLabApi.dylib','LICENSE-VTL','SOURCE.json']:b.write(bundle/n,(VTL/n).read_bytes(),j)
  b.write(bundle/'vtl_runtime.py',RUNTIME.encode(),j);b.write(bundle/'probe.py',PROBE.encode(),j);b.write(bundle/'acoustics.py',(NATIVE/'acoustics.py').read_bytes(),j)
  b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},final_runtime='vtl_runtime.py',probe_and_acoustics_are_diagnostic_only=True,neural=False,utterance_lookup=False),j)
  b.save(HERE/'source-contract.json',dict(controller_sha256=digest(Path(__file__)),files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()}),j)
 b.save(ROOT/'progress-0145.json',dict(active_campaign=NAME,next='登録push→5小波形の通常/隔離/CLI・再読取・拒否・内部費→学習契約',quality_goal_completed=False,budget=b.reconcile()));print('VTL共有標的の小事前検査を登録')
def fixture():
 b=Budget();b.recover();c=read(HERE/'source-contract.json');assert digest(Path(__file__))==c['controller_sha256']
 for n,h in c['files'].items():assert digest(HERE/n)==h,n
 results={};blocked=[HERE/'registration.json',NATIVE/'mei_normal.htsvoice',ROOT/'campaigns/nas-volume-waveguide-coupling-20261009-v1/audio/long-forward-flow.wav']
 # 拒否probeの存在は別の保存済み音声から固定する。本文や音声内容は読まない。
 existing=list((ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1/render').rglob('*.wav'));assert existing;blocked[-1]=existing[0];blocked.append(existing[0].resolve());assert all(p.is_file() for p in blocked)
 with job(b,'render','通常2/隔離2/CLI1の全内部VTL生成費',1000,60000000,1500) as j:
  for mode in ['normal','isolated','cli']:
   with b.workspace(j,'VTL事前検査の'+mode+'生成とclose後の自己WAV再読取',16000000,32000000) as (work,env):
    env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1');isolated=mode!='normal';cmd=['/usr/bin/sandbox-exec','-p',profile(b,work,isolated),str(PYTHON),'-B',str(HERE/'runtime-bundle/probe.py'),str(work),'--vowels','a' if mode=='cli' else 'ai','--blocked',json.dumps([str(p) for p in blocked]) if isolated else '[]']
    stdout,stderr,observed=run_observed(cmd,env,work,label=mode,timeout=1200);b.save(HERE/(mode+'-process-observation.json'),observed,j)
    if observed['returncode']!=0:
     b.save(HERE/(mode+'-child-failure.json'),dict(stdout=stdout,stderr=stderr,observation=observed),j);raise RuntimeError('VTL '+mode+'起動不通過')
    value=json.loads(stdout);assert value['network_permission_denied'] and not value['forbidden_imports']
    if isolated:assert all(x['denied'] for x in value['denial_probes'])
    results[mode]=value;b.save(HERE/(mode+'-audit.json'),value,j)
    for row in value['rows']:b.write_data(HERE/'audio'/mode/(row['vowel']+'.wav'),(work/(row['vowel']+'.wav')).read_bytes(),j)
 with job(b,'dsp','五波形のhash/全E0/内部clockを独立比較',10,4000000,300) as j:
  for first,second in zip(results['normal']['rows'],results['isolated']['rows']):assert first['wav_sha256']==second['wav_sha256']
  assert results['normal']['rows'][0]['wav_sha256']==results['cli']['rows'][0]['wav_sha256'];actual=sum(x['render_calls'] for a in results.values() for x in a['rows']);assert actual<=1000
  result=dict(preflight_passed=True,normal_isolated_CLI_exact=True,close_then_self_WAV_read=True,isolated_denials_verified=True,actual_render_calls=actual,reserved_render_count=1000,all_E0_observed=[x['E0']['E0_pass'] for a in results.values() for x in a['rows']],parameter_info=results['normal']['rows'][0]['parameter_bounds'],API_constants=results['normal']['rows'][0]['constant'],prior_geometry_joint_constraints_not_independently_qualified=True,quality_goal_completed=False,perceptual_qualification=False,protected_confirmation_opened=False,next=read(HERE/'registration.json')['next']);b.save(HERE/'aggregate-summary.json',result,j)
 with job(b,'audit','共有標的学習入口/全費用/失敗/回収を封印',size=3000000) as j:
  s=b.snapshot();tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
  b.save(HERE/'cost-audit.json',dict(counts=s['campaigns'][NAME]['counts'],seconds=s['seconds']-s['campaigns'][NAME]['start_seconds'],write_bytes=s['write_bytes']-s['campaigns'][NAME]['start_write_bytes'],temporary_owned=len(tmp),all_absent=True),j)
  b.write(HERE/'report.md',('# 共有母音標的の学習前事前検査\n\n既定JD3のa/i、F0=120Hz/320ms/seed41/gain.5。通常2/隔離2/CLI1が同じWAVで、close後に自分のWAVを再読取できた。過去音声/外部実体/HTS/契約と通信の拒否を確認。内部更新も含む実'+str(actual)+'renderに対し1000予約計数を保持。\n\n全E0観測: '+str(result['all_E0_observed'])+'。API範囲と内部clockだけの入口資格で、五母音全工学・内容・自然さ・複合geometry自己回復を認定しない。\n\n'+result['next']+'\n\n指定外部の全自分一時領域を回収し、旧失敗/契約/封印/P5未開封を維持。\n').encode(),j)
  b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
 b.close_campaign(NAME)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(id='vtl-target-preflight-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
 b.save(ROOT/'progress-0146.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,budget=b.reconcile()));print(json.dumps(dict(preflight_passed=True,actual_render_calls=actual,quality_goal_completed=False),ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args();globals()[a.stage]()
