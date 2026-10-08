"""独立声道の有限母音語句を原HTSと比較する。科学依存は管理した子へ限定。"""
import argparse,ast,base64,hashlib,importlib.util,json,os,re,subprocess,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-waveguide-vowel-comparison-20261008-v1'
NAME='waveguide-vowel-comparison-v1'
PREV=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
PARENT=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL=dict(candidate_pool_short=['青い。','多い。','硫黄。','いいえ。','覆う。','いい家。','家を。','上を。','甥を。','王を。','青い王。','多い王。'],
          candidate_pool_long=['青い家を追う。','青い家を覆う。','多い家を追う。','多い家を覆う。','いい家を追う。','いい家を覆う。','硫黄を覆う。','硫黄を追う。','いい王を追う。','青い王を追う。','家を覆う。','上を覆う。'])

CANDIDATE='''"""現入力を辞書で母音へ変換し、共有声道と連続源から生成する。"""
import sys,json,hashlib,io,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
import numpy as np
from scipy.io import wavfile
from japanese_frontend import analyze
from sequence_tract import generate as tract
from acoustics import evaluate
def verify():
 for name,h in json.loads((ROOT/'manifest.json').read_text())['files'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
def generate(text,speed,pitch,full=False):
 if speed not in (1.,1.15):raise ValueError('登録速度のみを受け付ける')
 row=analyze(text);phones=[re.search(r'\\-([^+]+)\\+',x).group(1) for x in row['full_context_labels']]
 if phones[0]!='sil' or phones[-1]!='sil' or any(p not in 'aiueo' or len(p)!=1 for p in phones[1:-1]):raise ValueError('両端silと母音だけの入力が必要')
 n=len(phones)-2
 if not 3<=n<=24:raise ValueError('3..24母音だけを受け付ける')
 ms=250 if speed==1. else 215
 request=dict(segments=[dict(vowel=p,duration_ms=ms) for p in phones[1:-1]],f0=pitch)
 y,control,raw,source,areas=tract(request);audio=y.astype(np.float32)
 frames=ms//5;part=[frames//5+(k<frames%5) for k in range(5)]
 duration=[0]*5+part*n+[0]*5;msd=[0.]*5+[1.]*(5*n)+[0.]*5
 e0=evaluate(audio,{},24000);buf=io.BytesIO();wavfile.write(buf,24000,audio);data=buf.getvalue()
 forbidden=[m for m in sys.modules if m.split('.')[0] in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx')];assert not forbidden
 meta=dict(sha256=hashlib.sha256(data).hexdigest(),E0=e0,E0_pass=e0['E0_pass'],invariants_pass=True,
  duration=duration,msd=msd,control=control,request=request,source_and_block_render_calls=control['source_and_block_render_calls'],
  output_gain=.10,generated_lf0_median_hz=float(pitch),synthesis_calls=control['source_and_block_render_calls'],E0_calls=1,
  runtime_neural=False,HMM_called=False,teacher_audio=0,utterance_tables=0,forbidden_imports=forbidden,
  full_context_labels=row['full_context_labels'],between_method_clock_identity_claimed=False,
  semantics='各母音250/215ms・定数F0・100ms面積遷移。源/声道/長さ/gainは原HTSと意図して異なる。',
  conversion=dict(render_calls_including_internal_MLSA=control['source_and_block_render_calls']))
 return (data,meta,None,row) if full else (data,meta)
'''

BATCH='''"""渡された現入力だけを共有入口で生成し、結果をpipeへ返す。"""
import sys,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
verify();requests=json.loads(sys.stdin.read());rows=[]
for r in requests:
 data,meta=generate(r['text'],r['speed'],r['pitch']);rows.append(dict(id=r['id'],wav_base64=base64.b64encode(data).decode(),meta=meta))
print(json.dumps(dict(rows=rows,calls=sum(r['meta']['synthesis_calls'] for r in rows)),allow_nan=False))
'''
CLI='''"""現文章/速度/F0を標準入力から一件だけ受け付ける。"""
import sys,json,base64
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime import generate,verify
verify();r=json.loads(sys.stdin.read());data,meta=generate(r['text'],r['speed'],r['pitch'])
print(json.dumps(dict(id=r['id'],wav_base64=base64.b64encode(data).decode(),meta=meta),allow_nan=False))
'''

WORKER='''"""全64音声の固定時計支持を測定し、方式間の時間差を保持する。"""
from paths import *
import sys,json,io,re,importlib.util,hashlib
import numpy as np
from scipy.io import wavfile
sys.path.insert(0,str(HERE/'runtime-bundle'))
from measurement import measure,pitch_pass,ELIGIBLE
def module(name,path):
 sys.path.insert(0,str(path));s=importlib.util.spec_from_file_location(name,path/'runtime.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.verify();return m
native=module('_native',HERE/'native-bundle');candidate=module('_candidate',HERE/'runtime-bundle')
b=Budget();rjob,djob=sys.argv[1:3];protocol=read(HERE/'protocol.json');records=[];calls=0
for row in protocol['rows']:
 for condition,q in protocol['conditions'].items():
  support=None
  for method,m in [('native',native),('waveguide',candidate)]:
   path=HERE/'render'/row['id']/condition/method;assert not path.with_suffix('.json').exists()
   data,meta,params,analyzed=m.generate(row['text'],q['speed'],q['requested_f0'],full=True)
   assert analyzed['full_context_labels']==row['full_context_labels'];calls+=meta['synthesis_calls']
   b.write_data(path.with_suffix('.wav'),data,rjob)
   if params is not None:
    buf=io.BytesIO();np.savez_compressed(buf,mcp=params[0],lf0=params[1],lpf=params[2],duration=meta['duration']);b.write_data(path.with_suffix('.npz'),buf.getvalue(),rjob)
   _,audio=wavfile.read(io.BytesIO(data));eligible=[i for i,x in enumerate(row['full_context_labels']) if re.search(r'\\-([^+]+)\\+',x).group(1) in ELIGIBLE and any(v>.5 for v in meta['msd'][i*5:(i+1)*5])]
   measured,f0,times=measure(audio,meta['duration'],eligible,support)
   if support is None:
    support=measured['support'];b.save(HERE/'support'/row['id']/(condition+'.json'),dict(indices=support,excluded=[x['index'] for x in measured['eligible_native_intervals'] if not x['support_complete']],native_wave_sha256=meta['sha256'],fixed_from_native=True,not_candidate_selected=True,phone_index_identity_not_clock_identity=True),djob)
   buf=io.BytesIO();np.savez_compressed(buf,f0=f0,times=times);b.write_data(path.with_suffix('.dio.npz'),buf.getvalue(),djob)
   record={k:row[k] for k in ['text','length','challenge_group','cohort']};record.update(id=row['id']+'/'+condition+'/'+method,condition=condition,variant=method,wav=str(path.with_suffix('.wav').relative_to(REPO)),wav_sha256=meta['sha256'],status='completed',meta=meta,measurement=measured,pitch_gate=pitch_pass(measured,q['requested_f0']),E0_pass=meta['E0_pass'],invariants_pass=meta['invariants_pass'],protocol_sha256=digest(HERE/'protocol.json'),quality_certified=False)
   b.write_data(path.with_suffix('.json'),encode(record),djob);records.append(dict(id=record['id'],record=str(path.with_suffix('.json').relative_to(REPO)),sha256=digest(path.with_suffix('.json'))))
  print('比較 '+str(len(records))+'/64',file=sys.stderr,flush=True)
assert len(records)==64
b.save(HERE/'render-manifest.json',dict(rows=records,new_render_calls=calls,source_and_all_block_calls_counted=True,output_waves=64,new_DSP_calls=192,no_optimization_after_output=True,quality_certified=False),djob)
print(json.dumps(dict(records=64,calls=calls)))
'''

PHYSICAL='''"""保存した制御・時計・源hashを照合する。再生成しない。"""
import sys,json,re,math
from pathlib import Path
import numpy as np
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text());rows=[]
for row in p['rows']:
 for c,q in p['conditions'].items():
  base=here/'render'/row['id']/c
  n=json.loads((base/'native.json').read_text());w=json.loads((base/'waveguide.json').read_text());m=w['meta'];ctl=m['control']
  phones=[re.search(r'\\-([^+]+)\\+',x).group(1) for x in row['full_context_labels']][1:-1];ms=250 if q['speed']==1. else 215
  assert m['request']==dict(segments=[dict(vowel=v,duration_ms=ms) for v in phones],f0=q['requested_f0'])
  bounds=np.rint(np.arange(len(phones)+1)*ms*34300/1000.).astype(np.int64).tolist();assert bounds==ctl['bounds_samples']
  frames=ms//5;part=[frames//5+(k<frames%5) for k in range(5)];assert m['duration']==[0]*5+part*len(phones)+[0]*5
  assert ctl['source_f0']==q['requested_f0'] and ctl['phase_start']==.125 and ctl['harmonics']==math.floor(8000/q['requested_f0'])
  assert m['output_gain']==ctl['shared_gain']==.10 and not m['HMM_called'] and not m['between_method_clock_identity_claimed']
  assert ctl['state_reset_only_at_utterance_start'] and not ctl['source_phase_reset_at_block_boundaries']
  assert n['measurement']['support']==w['measurement']['support']
  assert n['meta']['output_gain']==.25 and n['meta']['conversion']['source_method']=='native-pulse-noise'
  with np.load(base/'native.npz',allow_pickle=False) as z:
   assert z['duration'].tolist()==n['meta']['duration'];mask=z['lf0'][:,0]>0;assert abs(np.median(z['lf0'][mask,0])-math.log(q['requested_f0']))<=3e-15
  rows.append(dict(id=row['id']+'/'+c,passed=True,phone_index_support_exact=True,source_tract_duration_gain_intentionally_different=True,clock_identity_claimed=False))
assert len(rows)==32
print(json.dumps(dict(passed=True,pairs_checked=32,rows=rows,no_wave_resynthesis=True,render=0,dsp=96)))
'''

@contextmanager
def job(b,kind,label,count=1,size=0,seconds=600):
    token=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield token
    except BaseException as exc:b.finish(token,repr(exc));raise
    else:b.finish(token)

def verify():
    c=read(HERE/'execution-contract.json');assert digest(Path(__file__))==c['controller_sha256']
    for n,h in c['files'].items():assert digest(HERE/n)==h,n
    return c

def execute(cmd,env,profile_text=None,input_text=None,timeout=1800):
    env=dict(env);env['PYTHONPATH']=str(BASE/'runtime-bundle/packages-v2');env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
    if profile_text:cmd=['/usr/bin/sandbox-exec','-p',profile_text,*cmd]
    result=subprocess.run(cmd,env=env,input=input_text,check=True,text=True,capture_output=True,timeout=timeout)
    if result.stderr:print(result.stderr[-8000:],flush=True)
    return json.loads(result.stdout)

def profile(b,work,isolated,variant='waveguide'):
    s='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
    if isolated:
        old=REPO/'research/experiments/autonomous-speech-synthesis';bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
        s+='(deny file-read* (subpath '+json.dumps(str(REPO/'research'))+'))\n(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n'
        allowed=[old/'.venv-eval',bundle,work]
        s+='(allow file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in allowed)+')\n'
        s+='(allow file-read-data (subpath '+json.dumps(str(work))+'))\n'
        s+='(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n'
        site=old/'.venv-eval/lib/python3.11/site-packages'
        s+='(deny file-read* '+''.join('(subpath '+json.dumps(str(site/n))+') ' for n in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'))+')\n'
        if variant=='waveguide':s+='(deny file-read-data (regex #"\\\\.htsvoice$"))\n'
        ancestors=set()
        for p in allowed:ancestors.update(p.parents)
        s+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(ancestors))+')\n'
        assert '(allow file-read-data )' not in s
    return s

def requests():
    p=read(HERE/'protocol.json')
    return [dict(id=r['id']+'/'+c+'/'+m,text=r['text'],method=m,speed=q['speed'],pitch=q['requested_f0']) for r in p['rows'] for c,q in p['conditions'].items() for m in p['variants']]

def render_cost(req):
    if req['method']=='native':return 1
    row=next(r for r in read(HERE/'protocol.json')['rows'] if r['text']==req['text']);ms=250 if req['speed']==1. else 215
    samples=round((len(row['full_context_labels'])-2)*ms*34300/1000.)
    return 1+(samples+4095)//4096

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];assert read(PREV/'aggregate-summary.json')['engineering_all_required_pass']
    for s in (CANDIDATE,BATCH,CLI,WORKER,PHYSICAL):ast.parse(s)
    limits=dict(seconds=14400,bytes=1800000000,write_bytes=2800000000,setup=30,audit=40,render=3000,dsp=1800,ai=384,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='一次形状と有限LF源を持つ独立声道は、新しい母音のみの日本語語句で工学と二ASR内容を原native対照に対して保護できるか。',
      factor='源・声道・時間表現を全体として変更。原HTSは共有Mei/中央値校正/pulse-noise/MLSA/gain.25。候補は一次16径/34300Hz/有限LF Fourier8k/定数F0/100ms面積遷移/gain.10。',
      conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),variants=['native','waveguide'],
      input='12短+12長poolから履歴とfull-context非衝突・母音のみを先頭順に8短8長固定。短3..6母音/長5..24母音。両端silは候補0時間、内部pau/子音/無声化母音は拒否。意味の自然さや一般長文を保証しない。',
      duration='候補は各母音250/215ms。5ms計測clockへ整数5stateを均等配分。nativeのphone-index支持を一度固定し、候補の自身のdurationへ同じindexで測る。方式間clock同一性を主張しない。',
      gates=dict(engineering='全32件E0、DIO/ACF±1半音/confidence.6、固定支持3以上・半数以上・欠測全分母。',content='二ASR各33群native以下、悪化相殺なし。',independence='64通常と64隔離/CLI4のhash一致。候補隔離は独立bundleだけ許可しHMM/neural/過去入力/音声/配列/通信を実拒否。',physical='全32対の保存制御/境界/有限源/固定gain/支持indexとnative保存中央値を独立照合。波形再合成なし。'),
      source=dict(sequence_seal=digest(PREV/'artifact-seal.json'),sequence_module=digest(PREV/'runtime-bundle/sequence_tract.py'),sequence_binary=digest(PREV/'runtime-bundle/waveguide_stream.dylib'),native_seal=digest(PARENT/'artifact-seal.json')),
      estimates=dict(render_before_retries_at_most=2600,DSP=420,AI=128,internal_source_and_all_blocks_counted=True,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_and_Git_included=True),
      limits=limits,controller_sha256=digest(Path(__file__)),old_contracts_and_seals_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      after_failure='同コホートの径/gain/終端/時刻/LF係数で救済しない。内容不保護なら放射/損失/閉鎖/鼻腔/別一次形状を別機構として登録する。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','有限母音の新語句・源/声道差・全費用を波形前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        paths=(PARENT/'paths.py').read_text().replace('fujisaki-context-comparison','waveguide-vowel-comparison')
        b.write(HERE/'paths.py',paths.encode(),j)
        for n,s in [('candidate-runtime.py',CANDIDATE),('runtime_batch.py',BATCH),('cli.py',CLI),('worker.py',WORKER),('physical.py',PHYSICAL)]:b.write(HERE/n,s.encode(),j)
        for n in ('asr_worker.py','measurement.py'):b.write(HERE/n,(PARENT/n).read_bytes(),j)
        src=(PARENT/'prepare_inputs.py').read_text().replace('fujisaki-fresh','waveguide-fresh')
        src=src.replace("valid = 3 <= len(row['full_context_labels']) <= 122", "phones=[re.search(r'\\-([^+]+)\\+',x).group(1) for x in row['full_context_labels']]\n            count=len(phones)-2\n            valid=phones[0]==phones[-1]=='sil' and all(v in {'a','i','u','e','o'} for v in phones[1:-1]) and ((3<=count<=6) if length=='short' else (5<=count<=24))")
        ast.parse(src);b.write(HERE/'prepare_inputs.py',src.encode(),j)
        b.save(HERE/'engine-contract.json',read(PARENT/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_output=True),j)
    b.save(ROOT/'progress-0123.json',dict(active_campaign=NAME,new_waveforms=0,next='登録push→母音入力・共有bundle/全費用固定→比較/通常隔離/二ASR/終了',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];assert digest(Path(__file__))==read(HERE/'registration.json')['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','独立声道と原nativeのbundleを分離し入力/隔離/全内部費を固定',size=100000000,seconds=900) as j:
        bundle=HERE/'runtime-bundle';native=HERE/'native-bundle'
        for n in ('sequence_tract.py','waveguide_stream.dylib','diameters.json','coefficients.json','acoustics.py'):b.write(bundle/n,(PREV/'runtime-bundle'/n).read_bytes(),j)
        b.write(bundle/'japanese_frontend.py',(PARENT/'runtime-bundle/japanese_frontend.py').read_bytes(),j)
        b.write(bundle/'runtime.py',CANDIDATE.encode(),j)
        old=(PARENT/'runtime-bundle/runtime.py').read_text();tree=ast.parse(old)
        # 原nativeの演算はそのまま。候補枝とその依存だけを外す。
        lines=old.splitlines(True)
        remove=set()
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module=='fujisaki_context':remove.update(range(node.lineno-1,node.end_lineno))
            if isinstance(node,ast.If) and ast.get_source_segment(old,node.test)=="method=='fujisaki'":remove.update(range(node.lineno-1,node.end_lineno))
        old=''.join(line for i,line in enumerate(lines) if i not in remove).replace("METHODS=['native','fujisaki']","METHODS=['native']")
        old=old.replace('def generate(text, method, speed, pitch, full=False):','def generate(text, speed, pitch, full=False):\n    method="native"')
        old=old.replace('synthesis_calls=1, E0_calls=1,','synthesis_calls=1, E0_calls=1, full_context_labels=row["full_context_labels"],')
        ast.parse(old)
        for n in read(PARENT/'runtime-bundle/manifest.json')['files']:
            if n in ('runtime.py','runtime_batch.py','fujisaki_context.py'):continue
            b.write(native/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        b.write(native/'runtime.py',old.encode(),j)
        for folder in (bundle,native):
            for n,s in [('runtime_batch.py',BATCH),('cli.py',CLI)]:b.write(folder/n,s.encode(),j)
            assert all(not p.is_symlink() for p in folder.iterdir())
            b.save(folder/'manifest.json',dict(files={str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file()},shared_assets=True,HMM=folder==native,neural=False,utterance_tables=0,quality_certified=False),j)
        b.save(HERE/'measurement-package-contract.json',read(PARENT/'measurement-package-contract.json'),j)
        with b.workspace(j,'出力前の全文履歴と母音ラベル照合',16000000,32000000) as (_,env):value=execute([str(PYTHON),'-B',str(HERE/'prepare_inputs.py')],env,timeout=180)
        assert len(value['rows'])==16;b.save(HERE/'novelty-audit.json',value['audit'],j)
        reg=read(HERE/'registration.json');b.save(HERE/'protocol.json',dict(rows=value['rows'],variants=reg['variants'],conditions=reg['conditions'],expected_records=64,protected_confirmation_opened=False,no_optimization_after_first_audio=True,quality_certified=False),j)
        reqs=requests();comp=sum(map(render_cost,reqs));cli=2*(render_cost(reqs[0])+render_cost(reqs[-1]));total=3*comp+cli;assert total<=2600,total
        b.save(HERE/'render-plan.json',dict(comparison=comp,normal=comp,isolated=comp,CLI=cli,total=total,source_and_all_block_calls_counted=True,no_wave_yet=True),j)
        with b.workspace(j,'出力前の独立bundle実拒否',16000000,32000000) as (work,env):
            blocked=[HERE/'protocol.json',HERE/'registration.json',native/'mei_normal.htsvoice',PREV/'render/long-forward.wav',(PREV/'render/long-forward.wav').resolve()]
            # probeコード自身はargv経由。禁止された過去bundleから実行しない。
            code=(PREV/'runtime-bundle/denial_probe.py').read_text();proof=execute([str(PYTHON),'-I','-B','-c',code],env,profile(b,work,True),json.dumps([str(p) for p in blocked]),timeout=45);assert proof['all_denied']
        b.save(HERE/'isolation-preflight.json',dict(proof,paths=[str(p) for p in blocked],empty_allow_absent=True,new_waveforms=0),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_first_wave=True),j)
    print(dict(prepared=True,records=64,all_render_including_internal_calls=total,new_waveforms=0),flush=True)

def comparison():
    verify();b=Budget();assert not b.snapshot()['jobs'];plan=read(HERE/'render-plan.json')
    with job(b,'render','母音語句64波形と全源/声道block',plan['comparison'],200000000,1800) as r:
        with job(b,'dsp','E0/DIO/ACFと固定支持の全64測定',192,16000000,1800) as d:
            with b.workspace(r,'新語句の通常生成・科学依存初期化',16000000,32000000) as (_,env):out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),r,d],env,timeout=1500)
            assert out['calls']==plan['comparison'];print(out,flush=True)

def isolate():
    verify();b=Budget();assert not b.snapshot()['jobs'];reqs=requests();plan=read(HERE/'render-plan.json');expected={x['id']:read(REPO/x['record'])['wav_sha256'] for x in read(HERE/'render-manifest.json')['rows']};pairs=[];CLI_rows=[]
    for mode in ('normal','isolated'):
        for variant in ('native','waveguide'):
            selected=[q for q in reqs if q['method']==variant];cost=sum(map(render_cost,selected));bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
            with job(b,'render',mode+' '+variant+'全32件と内部block',cost,180000000,1800) as r:
                with job(b,'dsp',mode+' '+variant+'全32件E0',32,1000000,1800):
                    with b.workspace(r,'共有生成の'+mode+'/'+variant,16000000,32000000) as (work,env):value=execute([str(PYTHON),'-I','-B',str(bundle/'runtime_batch.py')],env,profile(b,work,mode=='isolated',variant),json.dumps(selected,ensure_ascii=False),timeout=1500)
                    assert len(value['rows'])==32 and value['calls']==cost
                    for x in value['rows']:
                        data=base64.b64decode(x['wav_base64']);assert hashlib.sha256(data).hexdigest()==x['meta']['sha256']==expected[x['id']];pairs.append(dict(id=x['id'],mode=mode,sha256=x['meta']['sha256'],bit_match=True))
                    b.write_data(HERE/('runtime-batch-'+mode+'-'+variant+'.json'),encode(value),r)
            print(mode+' '+variant+'32件一致',flush=True)
    for q in (reqs[0],reqs[-1]):
        for mode in ('normal','isolated'):
            variant=q['method'];bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
            with job(b,'render','CLI '+mode+'/'+q['id'],render_cost(q),50000000,600) as r:
                with job(b,'dsp','CLI E0',1,1000000,600):
                    with b.workspace(r,'単独CLI '+mode,16000000,32000000) as (work,env):value=execute([str(PYTHON),'-I','-B',str(bundle/'cli.py')],env,profile(b,work,mode=='isolated',variant),json.dumps(q,ensure_ascii=False),timeout=500)
                    data=base64.b64decode(value['wav_base64']);assert hashlib.sha256(data).hexdigest()==value['meta']['sha256']==expected[q['id']];b.write_data(HERE/'runtime-cli'/mode/(q['id']+'.wav'),data,r);CLI_rows.append(dict(id=q['id'],mode=mode,sha256=value['meta']['sha256'],bit_match=True))
    with job(b,'audit','禁止された実ファイル/重み/通信と全入口一致',size=50000000) as j:
        logical=HERE/'render'/read(HERE/'protocol.json')['rows'][0]['id']/'neutral/native.wav';archive=HERE/'runtime-batch-normal-waveguide.json'
        blocked=[logical,logical.resolve(),logical.with_suffix('.npz'),logical.with_suffix('.npz').resolve(),HERE/'protocol.json',HERE/'registration.json',PARENT/'protocol.json',archive,archive.resolve(),HERE/'native-bundle/mei_normal.htsvoice']
        assert all(p.is_file() for p in blocked)
        with b.workspace(j,'候補の論理/実体/原HMM読取と実接続拒否',16000000,32000000) as (work,env):
            code=(PREV/'runtime-bundle/denial_probe.py').read_text();proof=execute([str(PYTHON),'-I','-B','-c',code],env,profile(b,work,True),json.dumps([str(p) for p in blocked]),timeout=45);assert proof['all_denied']
        b.save(HERE/'denial-probe.json',dict(proof,paths=[str(p) for p in blocked]),j)
        assert len(pairs)==128 and len(CLI_rows)==4;b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=CLI_rows,new_render_calls=2*plan['comparison']+plan['CLI'],new_DSP_calls=132,source_and_block_calls_counted=True,denial_probe=proof,candidate_HMM_denied=True,final_non_neural=True,quality_certified=False),j)

def asr(engine):
    verify();b=Budget();assert not b.snapshot()['jobs'];assert read(HERE/'runtime-audit.json')['passed'];cfg=read(HERE/'engine-contract.json')
    with job(b,'audit','二ASRの固定モデル・辞書・正規化hash '+engine,size=1000000) as j:
        for n,h in cfg['asr_model_hashes'].items():assert digest(REPO/n)==h,n
        assert digest(REPO/'research/experiments/autonomous-speech-synthesis/diagnostics.py')==cfg['normalizer_source_sha256']
        q=cfg['reading_diagnostic']['contract']
        for n,h in q['dictionary_files'].items():assert digest(Path(q['dictionary_path'])/n)==h
        assert digest(q['library'])==q['library_sha256']
    with job(b,'ai','固定'+engine+'全64件',64,60000000,3000) as j:
        with b.workspace(j,'固定'+engine+'の研究評価',16000000,32000000) as (work,env):value=execute([str(PYTHON),'-B',str(HERE/'asr_worker.py'),'--engine',engine],env,profile(b,work,False),timeout=2700)
        assert len(value['rows'])==value['ai_calls']==64;rows=[]
        for v in value['rows']:
            p=HERE/'asr'/engine/(v['id']+'.json');b.write_data(p,encode(v),j);rows.append(dict(path=str(p.relative_to(REPO)),sha256=digest(p)))
        b.save(HERE/('asr-manifest-'+engine+'.json'),dict(rows=rows,new_ai=64,reused=0,optimization_after_asr=False),j)
    print(engine+' 全64件保存',flush=True)

def close():
    verify();b=Budget();assert not b.snapshot()['jobs'];protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json');assert len(manifest['rows'])==64 and runtime['passed']
    for n,h in read(HERE/'measurement-package-contract.json')['files'].items():assert digest(REPO/n)==h
    for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
    with job(b,'dsp','保存全32対の時計/有限源/支持/保持尺度照合',96,50000000,600) as j:
        with b.workspace(j,'保存制御と原native配列の独立照合',16000000,32000000) as (_,env):physical=execute([str(PYTHON),'-B',str(HERE/'physical.py'),str(HERE)],env,timeout=500)
        assert physical['passed'];b.save(HERE/'physical-audit.json',physical,j)
    old=(BASE/'summarize.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='grouped');scope={};exec(ast.get_source_segment(old,node),scope);grouped=scope['grouped']
    with job(b,'audit','母音語句の全分母/二ASR33群/費用/外部回収を封印',size=16000000) as j:
        records={}
        for x in manifest['rows']:
            assert digest(REPO/x['record'])==x['sha256'];v=read(REPO/x['record']);assert digest(REPO/v['wav'])==v['wav_sha256'];records[v['id']]=v
        engineering={};content={}
        for method in protocol['variants']:
            selected=[r for r in records.values() if r['variant']==method];assert len(selected)==32
            engineering[method]=dict(expected=32,missing_records=0,E0_pass_count=sum(r['E0_pass'] for r in selected),pitch_pass_count=sum(r['pitch_gate']['passed'] for r in selected),fixed_support_intervals=sum(len(r['measurement']['support']) for r in selected),missing_support=sum(len(r['measurement']['missing_support']) for r in selected),all_required_pass=all(r['E0_pass'] and r['pitch_gate']['passed'] and r['invariants_pass'] for r in selected))
            content[method]={}
            for engine in ('whisper','reazon'):
                am=read(HERE/('asr-manifest-'+engine+'.json'));assert len(am['rows'])==am['new_ai']==64
                for x in am['rows']:assert digest(REPO/x['path'])==x['sha256']
                comparisons=[]
                for row in protocol['rows']:
                    for c in protocol['conditions']:
                        p=HERE/'asr'/engine/row['id']/c/(method+'.json');x=read(p);n=read(p.with_name('native.json'));assert x['status']==n['status']=='completed' and x['reference_kana']==n['reference_kana'] and x['characters']==n['characters']
                        for v in (x,n):assert v['protocol_sha256']==digest(HERE/'protocol.json') and v['engine_contract_sha256']==digest(HERE/'engine-contract.json') and digest(REPO/v['wav'])==v['wav_sha256']
                        comparisons.append(dict(text_id=row['id'],condition=c,length=row['length'],challenge_group=row['challenge_group'],status='completed',errors=x['errors'],native_errors=n['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],native_hypothesis=n['hypothesis']))
                groups=grouped(comparisons);content[method][engine]=dict(pairs=comparisons,groups=groups,worsening_groups=[k for k,v in groups.items() if not v['non_worsening']],all_groups_non_worsening=all(v['non_worsening'] for v in groups.values()))
        research={m:engineering[m]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[m].values()) for m in protocol['variants']}
        summary=dict(total=64,engineering=engineering,content=content,physical_audit=physical,research_protection_gates=research,independent_noncollision=True,final_non_neural_runtime_verified=True,
          methodological_limits='母音のみの有限語句に限定。長群は一般長文ではない。一次径の機構資格/ASRを母音知覚・自然さへ拡張しない。原nativeと源/声道/duration/gainは異なる。固定支持phone-indexは同じでもclockは異なる。',
          inherited_sequence_mechanism=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,old_contracts_and_seals_and_two_ASR33_groups_kept=True,next=read(HERE/'registration.json')['after_failure'])
        b.write_data(HERE/'summary.json',encode(summary),j);compact=dict(summary);compact['content']={m:{n:{k:v for k,v in z.items() if k!='pairs'} for n,z in engines.items()} for m,engines in content.items()};compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 共有声道による有限母音語句の原native比較','','新16語句×2条件×2方式。候補は現文章の辞書/規則で得た母音だけを連続生成する。短3..6母音、長5..24母音の有限診断で、一般長文・子音・自然さの資格ではない。','','|方式|E0|pitch|支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['','候補の径/有限LF/終端/100ms遷移/gain.10は機構封印のまま。各母音250/215ms・定数F0、原nativeは共有Mei/原励振/MLSA/gain.25。方式間clockや音響パラメータ保持を主張しない。nativeで固定したphone-index支持は候補自身の時計で測り、欠測を分母に保持した。','',f'全源/内部blockを含む実生成費 {read(HERE/"render-plan.json")["total"]}render、420DSP、128AI。失敗/再試行があれば費用監査に追加保持。通常/隔離64件・CLI4件byte一致、候補の過去資料/原HMMと通信の実拒否。','',summary['methodological_limits'],'','研究保護: '+str(research),'日本語知覚資格なし・P5未開封・品質未達・最終採択なし。',summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,temporary_owned=len(tmp),internal_source_and_block_calls_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='waveguide-vowel-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0124.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','comparison','isolate','asr','close']);p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args()
    if a.stage=='asr':asr(a.engine)
    else:globals()[a.stage]()
