"""放射結合の二駆動を選別せず、有限母音語句の内容を原native対照で診断する。"""
import argparse,ast,base64,hashlib,importlib.util,json,os,re,subprocess,sys
from pathlib import Path
from contextlib import contextmanager
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from waveguide_vowel_comparison_20261008 import CANDIDATE as OLD_CANDIDATE,BATCH as OLD_BATCH,CLI as OLD_CLI,WORKER as OLD_WORKER
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-radiated-waveguide-comparison-20261009-v1';NAME='radiated-waveguide-comparison-v1'
PREV=ROOT/'campaigns/nas-radiated-waveguide-mechanism-20261009-v1'
PARENT=ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1'
NATIVE=ROOT/'campaigns/nas-waveguide-vowel-comparison-20261008-v1'
GUARD=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
POOL=dict(candidate_pool_short=['青い家。','多い家。','青い愛。','多い愛。','会う家。','合う家。','会う王。','追う家。','覆う家。','愛を負う。','甥を負う。','会う上。','合う王。','追う王。','覆う王。','王を負う。','多い上。','青い上。','硫黄を。','愛を会う。','家を会う。','上を会う。','甥を会う。','王を会う。'],
          candidate_pool_long=['青い家を覆い合う。','多い家を覆い合う。','青い王を追い合う。','多い王を追い合う。','いい家を覆い合う。','いい王を追い合う。','青い甥を追い合う。','多い甥を追い合う。','青い家を追い合う。','多い家を追い合う。','会う王を追い合う。','覆う家を追い合う。','合う家を覆い合う。','会う家を覆い合う。','覆う王を追い合う。','青い王を覆い合う。'])
CANDIDATE=OLD_CANDIDATE.replace('raw,source,areas','raw,drive,areas').replace('from sequence_tract import generate as tract','from radiated_sequence import generate as tract').replace('def generate(text,speed,pitch,full=False):',"def generate(text,speed,pitch,full=False,source='derivative'):").replace('if not 3<=n<=24:','if not 4<=n<=24:').replace('3..24母音','4..24母音').replace('=tract(request);','=tract(request,source);').replace('output_gain=.10,','output_gain=.10, source_kind=source,').replace('各母音250/215ms・定数F0・100ms面積遷移。源/声道/長さ/gainは原HTSと意図して異なる。','各母音250/215ms・定数F0・100ms面積遷移。現在径の放射loss portと共有34state。両駆動は同時固定。源/声道/長さ/gainは原HTSと意図して異なる。実mic音圧は資格なし。')
CALL="generate(r['text'],r['speed'],r['pitch']) if r['method']=='native' else generate(r['text'],r['speed'],r['pitch'],source=r['method'])"
BATCH=OLD_BATCH.replace("generate(r['text'],r['speed'],r['pitch'])",CALL)
CLI=OLD_CLI.replace("generate(r['text'],r['speed'],r['pitch'])",CALL)
WORKER=OLD_WORKER.replace('全64音声','全96音声').replace("[('native',native),('waveguide',candidate)]","[('native',native),('derivative',candidate),('flow',candidate)]").replace("m.generate(row['text'],q['speed'],q['requested_f0'],full=True)","m.generate(row['text'],q['speed'],q['requested_f0'],full=True) if method=='native' else m.generate(row['text'],q['speed'],q['requested_f0'],full=True,source=method)").replace('/64','/96').replace('==64','==96').replace('output_waves=64','output_waves=96').replace('new_DSP_calls=192','new_DSP_calls=288').replace('records=64','records=96')
PHYSICAL=r'''"""全保存32組の二駆動・源/状態/時計・原native中央値を再生成なしに確認する。"""
import sys,json,re,math
from pathlib import Path
import numpy as np
here=Path(sys.argv[1]);p=json.loads((here/'protocol.json').read_text());rows=[]
for row in p['rows']:
 for c,q in p['conditions'].items():
  base=here/'render'/row['id']/c;n=json.loads((base/'native.json').read_text())
  for source in ('derivative','flow'):
   w=json.loads((base/(source+'.json')).read_text());m=w['meta'];ctl=m['control'];phones=[re.search(r'\-([^+]+)\+',x).group(1) for x in row['full_context_labels']][1:-1];ms=250 if q['speed']==1. else 215
   assert m['request']==dict(segments=[dict(vowel=v,duration_ms=ms) for v in phones],f0=q['requested_f0']) and m['source_kind']==ctl['source_kind']==source
   bounds=np.rint(np.arange(len(phones)+1)*ms*34300/1000.).astype(np.int64).tolist();assert bounds==ctl['bounds_samples'];frames=ms//5;part=[frames//5+(k<frames%5) for k in range(5)];assert m['duration']==[0]*5+part*len(phones)+[0]*5
   assert ctl['source_f0']==q['requested_f0'] and ctl['phase_start']==.125 and ctl['harmonics']==math.floor(8000/q['requested_f0'])
   assert m['output_gain']==ctl['shared_gain']==.10 and not m['HMM_called'] and not m['between_method_clock_identity_claimed']
   assert ctl['state_reset_only_at_utterance_start'] and not ctl['source_phase_reset_at_block_boundaries'];assert n['measurement']['support']==w['measurement']['support']
  assert n['meta']['output_gain']==.25 and n['meta']['conversion']['source_method']=='native-pulse-noise'
  with np.load(base/'native.npz',allow_pickle=False) as z:
   assert z['duration'].tolist()==n['meta']['duration'];mask=z['lf0'][:,0]>0;assert abs(np.median(z['lf0'][mask,0])-math.log(q['requested_f0']))<=3e-15
  rows.append(dict(id=row['id']+'/'+c,passed=True,variants=2,source_state_duration_gain_intentionally_different=True,phone_index_support_exact=True,clock_identity_claimed=False))
assert len(rows)==32
print(json.dumps(dict(passed=True,triplets_checked=32,candidate_pairs_checked=64,rows=rows,no_wave_resynthesis=True,render=0,dsp=192)))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];v=read(PREV/'aggregate-summary.json');assert v['mechanism_passed'] and not v['engineering_all_required_pass']
    assert digest(ROOT/'waveguide_vowel_comparison_20261008.py')==read(NATIVE/'registration.json')['controller_sha256']
    for s in (CANDIDATE,BATCH,CLI,WORKER,PHYSICAL):ast.parse(s)
    limits=dict(seconds=28800,bytes=1800000000,write_bytes=2800000000,setup=40,audit=40,render=6000,dsp=3000,ai=384,teacher=0,train=0,inverse=0,download=0)
    reason='96比較波形・192通常/隔離・CLI6と両駆動の全内部blockを一つの事前比較として扱うため、通常3000を超える生成費を事前見積もる。上限6000render/8hを開始前固定し、旧消費と残額を保持する。'
    reg=dict(campaign=NAME,question='放射loss portを持つ共有声道の両固定駆動は、新しい有限母音語句で原nativeの工学/二ASR内容を保持できるか。第73の全工学不通過を保持した限定診断。',
      factor='現在唇径の共通放射二状態+R16/L16、正規化loss port、LF微分形/積分AC形。同径/遷移/源係数/phase/帯域/gain.10。原nativeは従来Mei/中央値校正/pulse-noise/MLSA/gain.25。両駆動を出力後選別しない。',
      conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),variants=['native','derivative','flow'],
      input='短pool24/長pool16から本文とfull-context非衝突・母音のみの先頭順で8短8長。短4..6母音/長8..24母音。旧第70の最少支持不足を基準緩和で救わず、新入力の最小長を出力前設計。意味の自然さや一般長文の資格なし。内部pau/子音/無声化母音を拒否。',
      duration='候補は各母音250/215ms、100ms smoothstep、5ms clockへ5state均等分割。nativeからphone-index支持を一度固定し、両候補の自身のdurationへ同じindexで測定。方式間clock同一性を主張しない。',
      gates=dict(engineering='全32件E0、DIO/ACF±1半音/confidence.6、固定支持最低3、各区間3frame以上/半数以上・欠測全分母。旧基準不変。',content='二ASR各33群でnative以下、悪化相殺なし。',independence='96通常と96隔離/CLI6のhash一致。候補bundle以外のHMM/neural/参照/教師/過去入力・音声・配列・通信を実拒否。',physical='全32組/64候補対の保存制御・境界・共有state/source・固定gain・支持indexと原native中央値を再合成なしに照合。'),
      source=dict(coupled_seal=digest(PREV/'artifact-seal.json'),coupled_module=digest(PREV/'runtime-bundle/radiated_sequence.py'),coupled_binary=digest(PREV/'runtime-bundle/radiated_tube.dylib'),flow_normalization=digest(PREV/'runtime-bundle/flow-normalization.json'),native_seal=digest(NATIVE/'artifact-seal.json'),template_controller=digest(ROOT/'waveguide_vowel_comparison_20261008.py')),
      prior_coupled_engineering=dict(all_required_pass=False,sources=v['summary'],same_failures_not_rejudged=True),
      estimates=dict(render_before_retries_at_most=5200,DSP=678,AI=192,source_and_internal_blocks_counted=True,temporary_peak=20000000,temporary_write=40000000,RAM_gb=8,closeout_and_Git_included=True),limits=limits,expansion_reason=reason,controller_sha256=digest(Path(__file__)),old_contracts_and_seals_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
      after_failure='同コホートの径/gain/終端/時刻/LF係数/基準で救済しない。実mic/声門volume velocity/肺圧の資格なしを保持。内容不保護なら新一次MRI形状や分布壁/粘熱損失・閉鎖/鼻腔/子音を別機構へ配分する。内容通過でも第73工学不通過・知覚資格不足を消さず最終採択しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest(),expansion_reason=reason)
    with job(b,'setup','新16語句/二駆動/96波形と全費用を初出力前登録',size=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        paths=(NATIVE/'paths.py').read_text().replace('waveguide-vowel-comparison','radiated-waveguide-comparison')
        b.write(HERE/'paths.py',paths.encode(),j)
        for n,s in [('candidate-runtime.py',CANDIDATE),('runtime_batch.py',BATCH),('cli.py',CLI),('worker.py',WORKER),('physical.py',PHYSICAL)]:b.write(HERE/n,s.encode(),j)
        for n in ('asr_worker.py','measurement.py'):b.write(HERE/n,(NATIVE/n).read_bytes(),j)
        src=(NATIVE/'prepare_inputs.py').read_text().replace('waveguide-fresh','radiated-fresh').replace('(3<=count<=6)','(4<=count<=6)').replace('(5<=count<=24)','(8<=count<=24)');ast.parse(src);b.write(HERE/'prepare_inputs.py',src.encode(),j)
        b.save(HERE/'engine-contract.json',read(NATIVE/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_output=True),j)
    b.save(ROOT/'progress-0132.json',dict(active_campaign=NAME,new_waveforms=0,next='登録push→新入力と二駆動bundle/全費用固定→96比較/通常隔離/CLI6/二ASR→全分母終了',quality_goal_completed=False,budget=b.reconcile()));print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];assert digest(Path(__file__))==read(HERE/'registration.json')['controller_sha256']
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','共有放射声道/原nativeを分離し新入力/全費用/実拒否を固定',size=120000000,seconds=900) as j:
        bundle=HERE/'runtime-bundle';native=HERE/'native-bundle'
        for n in ('radiated_sequence.py','radiated_tube.dylib','diameters.json','lf-coefficients.json','radiation-coefficients.json','flow-normalization.json','acoustics.py'):b.write(bundle/n,(PREV/'runtime-bundle'/n).read_bytes(),j)
        b.write(bundle/'japanese_frontend.py',(NATIVE/'runtime-bundle/japanese_frontend.py').read_bytes(),j);b.write(bundle/'runtime.py',CANDIDATE.encode(),j)
        for n in read(NATIVE/'native-bundle/manifest.json')['files']:
            if n in ('runtime_batch.py','cli.py'):continue
            b.write(native/n,(NATIVE/'native-bundle'/n).read_bytes(),j)
        for folder in (bundle,native):
            for n,s in [('runtime_batch.py',BATCH),('cli.py',CLI)]:b.write(folder/n,s.encode(),j)
            assert all(not p.is_symlink() for p in folder.iterdir())
            b.save(folder/'manifest.json',dict(files={str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file()},shared_assets=True,HMM=folder==native,neural=False,utterance_tables=0,quality_certified=False),j)
        b.save(HERE/'measurement-package-contract.json',read(NATIVE/'measurement-package-contract.json'),j)
        with b.workspace(j,'出力前の全文履歴/最小母音長/ラベル照合',20000000,40000000) as (_,env):value=execute([str(PYTHON),'-B',str(HERE/'prepare_inputs.py')],env,timeout=180)
        assert len(value['rows'])==16;b.save(HERE/'novelty-audit.json',value['audit'],j);reg=read(HERE/'registration.json')
        b.save(HERE/'protocol.json',dict(rows=value['rows'],variants=reg['variants'],conditions=reg['conditions'],expected_records=96,protected_confirmation_opened=False,no_optimization_after_first_audio=True,quality_certified=False),j)
        reqs=requests();comp=sum(map(render_cost,reqs));cli=2*sum(render_cost(q) for q in (reqs[0],reqs[-2],reqs[-1]));total=3*comp+cli;assert total<=5200,total
        b.save(HERE/'render-plan.json',dict(comparison=comp,normal=comp,isolated=comp,CLI=cli,total=total,source_and_all_block_calls_counted=True,no_wave_yet=True),j)
        with b.workspace(j,'出力前の共有二駆動bundle実拒否',16000000,32000000) as (work,env):
            blocked=[HERE/'protocol.json',HERE/'registration.json',native/'mei_normal.htsvoice',PREV/'audio/long-forward-flow.wav',(PREV/'audio/long-forward-flow.wav').resolve()];assert all(p.is_file() for p in blocked)
            code=(GUARD/'runtime-bundle/denial_probe.py').read_text();proof=execute([str(PYTHON),'-I','-B','-c',code],env,profile(b,work,True,'flow'),json.dumps([str(p) for p in blocked]),timeout=45);assert proof['all_denied']
        b.save(HERE/'isolation-preflight.json',dict(proof,paths=[str(p) for p in blocked],empty_allow_absent=True,new_waveforms=0),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),fixed_before_first_wave=True),j)
    print(dict(prepared=True,records=96,all_render_including_internal_calls=total,new_waveforms=0),flush=True)


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

def profile(b,work,isolated,variant='derivative'):
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
        if variant!='native':s+='(deny file-read-data (regex #"\\\\.htsvoice$"))\n'
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

def comparison():
    verify();b=Budget();assert not b.snapshot()['jobs'];plan=read(HERE/'render-plan.json')
    with job(b,'render','母音語句96波形と全源/声道block',plan['comparison'],200000000,1800) as r:
        with job(b,'dsp','E0/DIO/ACFと固定支持の全96測定',288,16000000,1800) as d:
            with b.workspace(r,'新語句の通常生成・科学依存初期化',16000000,32000000) as (_,env):out=execute([str(PYTHON),'-B',str(HERE/'worker.py'),r,d],env,timeout=1500)
            assert out['calls']==plan['comparison'];print(out,flush=True)

def isolate():
    verify();b=Budget();assert not b.snapshot()['jobs'];reqs=requests();plan=read(HERE/'render-plan.json');expected={x['id']:read(REPO/x['record'])['wav_sha256'] for x in read(HERE/'render-manifest.json')['rows']};pairs=[];CLI_rows=[]
    for mode in ('normal','isolated'):
        for variant in ('native','derivative','flow'):
            selected=[q for q in reqs if q['method']==variant];cost=sum(map(render_cost,selected));bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
            with job(b,'render',mode+' '+variant+'全32件と内部block',cost,180000000,1800) as r:
                with job(b,'dsp',mode+' '+variant+'全32件E0',32,1000000,1800):
                    with b.workspace(r,'共有生成の'+mode+'/'+variant,16000000,32000000) as (work,env):value=execute([str(PYTHON),'-I','-B',str(bundle/'runtime_batch.py')],env,profile(b,work,mode=='isolated',variant),json.dumps(selected,ensure_ascii=False),timeout=1500)
                    assert len(value['rows'])==32 and value['calls']==cost
                    for x in value['rows']:
                        data=base64.b64decode(x['wav_base64']);assert hashlib.sha256(data).hexdigest()==x['meta']['sha256']==expected[x['id']];pairs.append(dict(id=x['id'],mode=mode,sha256=x['meta']['sha256'],bit_match=True))
                    b.write_data(HERE/('runtime-batch-'+mode+'-'+variant+'.json'),encode(value),r)
            print(mode+' '+variant+'32件一致',flush=True)
    for q in (reqs[0],reqs[-2],reqs[-1]):
        for mode in ('normal','isolated'):
            variant=q['method'];bundle=HERE/('native-bundle' if variant=='native' else 'runtime-bundle')
            with job(b,'render','CLI '+mode+'/'+q['id'],render_cost(q),50000000,600) as r:
                with job(b,'dsp','CLI E0 '+mode+'/'+q['id'],1,1000000,600):
                    with b.workspace(r,'単独CLI '+mode,16000000,32000000) as (work,env):value=execute([str(PYTHON),'-I','-B',str(bundle/'cli.py')],env,profile(b,work,mode=='isolated',variant),json.dumps(q,ensure_ascii=False),timeout=500)
                    data=base64.b64decode(value['wav_base64']);assert hashlib.sha256(data).hexdigest()==value['meta']['sha256']==expected[q['id']];b.write_data(HERE/'runtime-cli'/mode/(q['id']+'.wav'),data,r);CLI_rows.append(dict(id=q['id'],mode=mode,sha256=value['meta']['sha256'],bit_match=True))
    with job(b,'audit','禁止された実ファイル/重み/通信と全入口一致',size=50000000) as j:
        logical=HERE/'render'/read(HERE/'protocol.json')['rows'][0]['id']/'neutral/native.wav';archive=HERE/'runtime-batch-normal-flow.json'
        blocked=[logical,logical.resolve(),logical.with_suffix('.npz'),logical.with_suffix('.npz').resolve(),HERE/'protocol.json',HERE/'registration.json',PARENT/'protocol.json',archive,archive.resolve(),HERE/'native-bundle/mei_normal.htsvoice']
        assert all(p.is_file() for p in blocked)
        with b.workspace(j,'候補の論理/実体/原HMM読取と実接続拒否',16000000,32000000) as (work,env):
            code=(GUARD/'runtime-bundle/denial_probe.py').read_text();proof=execute([str(PYTHON),'-I','-B','-c',code],env,profile(b,work,True),json.dumps([str(p) for p in blocked]),timeout=45);assert proof['all_denied']
        b.save(HERE/'denial-probe.json',dict(proof,paths=[str(p) for p in blocked]),j)
        assert len(pairs)==192 and len(CLI_rows)==6;b.save(HERE/'runtime-audit.json',dict(passed=True,pairs=pairs,CLI=CLI_rows,new_render_calls=2*plan['comparison']+plan['CLI'],new_DSP_calls=198,source_and_block_calls_counted=True,denial_probe=proof,candidate_HMM_denied=True,final_non_neural=True,quality_certified=False),j)

def asr(engine):
    verify();b=Budget();assert not b.snapshot()['jobs'];assert read(HERE/'runtime-audit.json')['passed'];cfg=read(HERE/'engine-contract.json')
    with job(b,'audit','二ASRの固定モデル・辞書・正規化hash '+engine,size=1000000) as j:
        for n,h in cfg['asr_model_hashes'].items():assert digest(REPO/n)==h,n
        assert digest(REPO/'research/experiments/autonomous-speech-synthesis/diagnostics.py')==cfg['normalizer_source_sha256']
        q=cfg['reading_diagnostic']['contract']
        for n,h in q['dictionary_files'].items():assert digest(Path(q['dictionary_path'])/n)==h
        assert digest(q['library'])==q['library_sha256']
    with job(b,'ai','固定'+engine+'全96件',96,60000000,3000) as j:
        with b.workspace(j,'固定'+engine+'の研究評価',16000000,32000000) as (work,env):value=execute([str(PYTHON),'-B',str(HERE/'asr_worker.py'),'--engine',engine],env,profile(b,work,False),timeout=2700)
        assert len(value['rows'])==value['ai_calls']==96;rows=[]
        for v in value['rows']:
            p=HERE/'asr'/engine/(v['id']+'.json');b.write_data(p,encode(v),j);rows.append(dict(path=str(p.relative_to(REPO)),sha256=digest(p)))
        b.save(HERE/('asr-manifest-'+engine+'.json'),dict(rows=rows,new_ai=96,reused=0,optimization_after_asr=False),j)
    print(engine+' 全96件保存',flush=True)

def close():
    verify();b=Budget();assert not b.snapshot()['jobs'];protocol=read(HERE/'protocol.json');manifest=read(HERE/'render-manifest.json');runtime=read(HERE/'runtime-audit.json');assert len(manifest['rows'])==96 and runtime['passed']
    for n,h in read(HERE/'measurement-package-contract.json')['files'].items():assert digest(REPO/n)==h
    for n,h in read(PREV/'artifact-seal.json')['files'].items():assert digest(REPO/n)==h,n
    with job(b,'dsp','保存全32組の二候補の時計/有限源/支持/保持尺度照合',192,50000000,600) as j:
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
                am=read(HERE/('asr-manifest-'+engine+'.json'));assert len(am['rows'])==am['new_ai']==96
                for x in am['rows']:assert digest(REPO/x['path'])==x['sha256']
                comparisons=[]
                for row in protocol['rows']:
                    for c in protocol['conditions']:
                        p=HERE/'asr'/engine/row['id']/c/(method+'.json');x=read(p);n=read(p.with_name('native.json'));assert x['status']==n['status']=='completed' and x['reference_kana']==n['reference_kana'] and x['characters']==n['characters']
                        for v in (x,n):assert v['protocol_sha256']==digest(HERE/'protocol.json') and v['engine_contract_sha256']==digest(HERE/'engine-contract.json') and digest(REPO/v['wav'])==v['wav_sha256']
                        comparisons.append(dict(text_id=row['id'],condition=c,length=row['length'],challenge_group=row['challenge_group'],status='completed',errors=x['errors'],native_errors=n['errors'],characters=x['characters'],candidate_hypothesis=x['hypothesis'],native_hypothesis=n['hypothesis']))
                groups=grouped(comparisons);content[method][engine]=dict(pairs=comparisons,groups=groups,worsening_groups=[k for k,v in groups.items() if not v['non_worsening']],all_groups_non_worsening=all(v['non_worsening'] for v in groups.values()))
        research={m:engineering[m]['all_required_pass'] and all(v['all_groups_non_worsening'] for v in content[m].values()) for m in protocol['variants']}
        summary=dict(total=96,engineering=engineering,content=content,physical_audit=physical,research_protection_gates=research,independent_noncollision=True,final_non_neural_runtime_verified=True,
          methodological_limits='母音のみの有限語句に限定。長群は一般長文ではない。一次径の機構資格/ASRを母音知覚・自然さへ拡張しない。原nativeと源/声道/duration/gainは異なる。固定支持phone-indexは同じでもclockは異なる。',
          inherited_sequence_mechanism=True, prior_coupled_engineering_all_required_pass=False, loss_port_not_far_field=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,adopted=False,old_contracts_and_seals_and_two_ASR33_groups_kept=True,next=read(HERE/'registration.json')['after_failure'])
        b.write_data(HERE/'summary.json',encode(summary),j);compact=dict(summary);compact['content']={m:{n:{k:v for k,v in z.items() if k!='pairs'} for n,z in engines.items()} for m,engines in content.items()};compact['detailed_summary_path']=str((HERE/'summary.json').relative_to(REPO));compact['detailed_summary_sha256']=digest(HERE/'summary.json');b.save(HERE/'aggregate-summary.json',compact,j)
        lines=['# 放射結合の二固定駆動による有限母音語句の原native診断','','新16語句×2条件×3方式。候補は現文章の辞書/規則で得た母音だけを連続生成する。短4..6母音、長8..24母音の有限診断で、一般長文・子音・自然さの資格ではない。','','|方式|E0|pitch|支持欠測|Whisper悪化群|Reazon悪化群|','|---|---:|---:|---:|---:|---:|']
        for m,e in engineering.items():lines.append(f'|{m}|{e["E0_pass_count"]}/32|{e["pitch_pass_count"]}/32|{e["missing_support"]}/{e["fixed_support_intervals"]}|{len(content[m]["whisper"]["worsening_groups"])}/33|{len(content[m]["reazon"]["worsening_groups"])}/33|')
        lines+=['','両候補の径/二固定LF/共通受動放射/100ms遷移/gain.10は機構封印のまま。第73全工学のpitch 37/43という不通過を保持する。各母音250/215ms・定数F0、原nativeは共有Mei/原励振/MLSA/gain.25。方式間clockや音響パラメータ保持を主張しない。nativeで固定したphone-index支持は候補自身の時計で測り、欠測を分母に保持した。','',f'全源/内部blockを含む実生成費 {read(HERE/"render-plan.json")["total"]}render、678DSP、192AI。失敗/再試行があれば費用監査に追加保持。通常/隔離96件・CLI6件byte一致、候補の過去資料/原HMMと通信の実拒否。','',summary['methodological_limits'],'','研究保護: '+str(research),'日本語知覚資格なし・P5未開封・品質未達・最終採択なし。',summary['next'],'']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],all_owned_temporary_absent=True,temporary_owned=len(tmp),internal_source_and_block_calls_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='radiated-waveguide-comparison-completed',active_campaign=None,next=summary['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0133.json',dict(latest_completed=NAME,quality_goal_completed=False,next=summary['next'],review=b.review_due(),budget=b.reconcile()))
    print({m:dict(E0=e['E0_pass_count'],pitch=e['pitch_pass_count'],missing=e['missing_support'],ASR={n:len(v['worsening_groups']) for n,v in content[m].items()}) for m,e in engineering.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','comparison','isolate','asr','close']);p.add_argument('--engine',choices=['whisper','reazon']);a=p.parse_args()
    if a.stage=='asr':asr(a.engine)
    else:globals()[a.stage]()
