"""共有母音列を状態継承で連続生成し、区切り不変と通常/隔離/CLIを検証する。"""
import argparse,ast,hashlib,json,os,subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from waveguide_tract_mechanism_20261008 import C_SOURCE as BASE_C
from waveguide_vowel_mechanism_20261008 import MODULE as BASE_MODULE
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-waveguide-sequence-runtime-20261008-v1'
NAME='waveguide-sequence-runtime-v1'
PREV=ROOT/'campaigns/nas-waveguide-vowel-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
C_SOURCE=BASE_C.replace('int tube_render(', 'int tube_stream(').replace('double rg,double rl,double *out,double *energy)', 'double rg,double rl,const double *initial,double *final,double *out,double *energy)')
C_SOURCE=C_SOURCE.replace('if(!drive||!area||!out||!energy||', 'if(!drive||!area||!initial||!final||!out||!energy||')
C_SOURCE=C_SOURCE.replace('double right[44]={0},left[44]={0},nr[44],nl[44];',
 'double right[44],left[44],nr[44],nl[44];\n for(size_t j=0;j<sections;j++) {if(!isfinite(initial[j])||!isfinite(initial[sections+j]))return 0;right[j]=initial[j];left[j]=initial[sections+j];}')
C_SOURCE=C_SOURCE.replace('return 1;','for(size_t j=0;j<sections;j++){final[j]=right[j];final[sections+j]=left[j];}\n return 1;')
assert 'int tube_stream(' in C_SOURCE and 'const double *initial' in C_SOURCE and 'double right[44]={0}' not in C_SOURCE

MODULE=BASE_MODULE.split('def generate(first,')[0].replace('from waveguide_tract import render,ah','import ctypes as C,hashlib')+r'''
P=C.POINTER(C.c_double);S=C.c_size_t
_lib=C.CDLL(str(HERE/'waveguide_stream.dylib'));_fn=_lib.tube_stream
_fn.restype=C.c_int;_fn.argtypes=[P,P,S,S,C.c_double,C.c_double,P,P,P,P]
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def block(x,a,state):
 x=np.ascontiguousarray(x,dtype=np.float64);a=np.ascontiguousarray(a,dtype=np.float64);s=np.ascontiguousarray(state,dtype=np.float64)
 if x.ndim!=1 or a.ndim!=2 or len(a)!=len(x) or a.shape[1]!=16 or s.shape!=(32,):raise ValueError('列/断面/状態の次元が不整合')
 before=(ah(x),ah(a),ah(s));out=np.empty_like(x);energy=np.empty_like(x);last=np.empty_like(s)
 if not _fn(x.ctypes.data_as(P),a.ctypes.data_as(P),len(x),16,.75,-.85,s.ctypes.data_as(P),last.ctypes.data_as(P),out.ctypes.data_as(P),energy.ctypes.data_as(P)):raise ValueError('連続声道の有限入力/出力を拒否')
 assert before==(ah(x),ah(a),ah(s));return out,energy,last
def controls(request):
 if not isinstance(request,dict) or set(request)!= {'segments','f0'}:raise ValueError('segments/f0だけを指定する')
 f0=request['f0'];segments=request['segments']
 if type(f0) not in (int,float) or not math.isfinite(f0) or not 70<=f0<=400:raise ValueError('有限F0 70..400Hzが必要')
 if not isinstance(segments,list) or not 1<=len(segments)<=24:raise ValueError('母音列は1..24区間')
 for s in segments:
  if not isinstance(s,dict) or set(s)!= {'vowel','duration_ms'} or s['vowel'] not in AREA or type(s['duration_ms']) is not int or not 125<=s['duration_ms']<=600:raise ValueError('各区間は登録母音と整数125..600ms')
 total=sum(s['duration_ms'] for s in segments)
 if total>6000:raise ValueError('発話は6000ms以内')
 bounds=np.rint(np.r_[0,np.cumsum([s['duration_ms'] for s in segments])]*FS/1000.).astype(np.int64);n=int(bounds[-1]);a=np.empty((n,16));previous=AREA[segments[0]['vowel']]
 for index,s in enumerate(segments):
  start,stop=map(int,bounds[index:index+2]);target=AREA[s['vowel']]
  if index==0:a[start:stop]=target
  else:
   q=np.clip((np.arange(stop-start)/FS)/.10,0.,1.);weight=q*q*(3.-2.*q);a[start:stop]=(1.-weight[:,None])*previous+weight[:,None]*target
  previous=target
 phase=(np.arange(n,dtype=float)*f0/FS+.125)%1.;x=np.zeros(n);harmonics=math.floor(CUTOFF/f0)
 for m in range(1,harmonics+1):x+=2*np.real(coefficient(m)*np.exp(2j*np.pi*m*phase))
 return x,a,dict(source_f0=f0,phase_start=.125,harmonics=harmonics,maximum_source_harmonic_hz=harmonics*f0,source_fs=FS,output_fs=OUTFS,source_sha256=ah(x),area_sha256=ah(a),bounds_samples=bounds.tolist(),duration_ms=total)
def generate(request,partition=(4096,)):
 if not isinstance(partition,tuple) or not partition or any(type(v) is not int or not 1<=v<=96000 for v in partition):raise ValueError('内部block寸法が登録範囲外')
 x,a,meta=controls(request);state=np.zeros(32);raw=np.empty(len(x));energy=np.empty(len(x));start=0;calls=0
 while start<len(x):
  stop=min(len(x),start+partition[calls%len(partition)]);y,e,state=block(x[start:stop],a[start:stop],state);raw[start:stop]=y;energy[start:stop]=e;start=stop;calls+=1
 audio=output(raw);meta.update(block_calls=calls,source_and_block_render_calls=calls+1,final_state_sha256=ah(state),raw_sha256=ah(raw),output_sha256=ah(audio),energy_max=float(energy.max()),shared_gain=GAIN,state_reset_only_at_utterance_start=True,source_phase_reset_at_block_boundaries=False)
 return audio,meta,raw,x,a
'''

CLI=r'''"""JSONの共有母音列だけから生成する独立CLI。過去波形/台帳/教師を参照しない。"""
import argparse,json,sys,hashlib
from pathlib import Path
from scipy.io import wavfile
from sequence_tract import generate,OUTFS
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();request=json.loads(sys.stdin.read());audio,meta,*_=generate(request)
path=Path(a.output);wavfile.write(path,OUTFS,audio.astype('float32'));meta.update(wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),request=request,HMM=False,neural_inference=False,recorded_audio=False,utterance_lookup=False,quality_certified=False)
print(json.dumps(meta,ensure_ascii=False))
'''

BATCH=r'''"""入力JSONからの生成だけ。隔離時も評価器や過去音声を読み込まない。"""
import sys,json,tempfile,os,hashlib
from pathlib import Path
from scipy.io import wavfile
from sequence_tract import generate,OUTFS
work=Path(sys.argv[1]);assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
requests=json.loads(sys.stdin.read());rows=[]
for row in requests:
 audio,meta,*_=generate(row['request']);p=work/(row['id']+'.wav');wavfile.write(p,OUTFS,audio.astype('float32'))
 rows.append(dict(id=row['id'],wav_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),meta=meta))
print(json.dumps(dict(rows=rows,calls=sum(r['meta']['source_and_block_render_calls'] for r in rows),HMM=False,neural_inference=False,recorded_audio=False,utterance_lookup=False)))
'''

WORKER=r'''"""状態継承・任意区切り不変・独立回転・一母音の旧入口一致・全固定支持を検査。"""
import sys,json,math,os,tempfile,importlib.util,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;work=Path(sys.argv[1]);sys.path.insert(0,str(here/'runtime-bundle'))
assert work.resolve()==Path(os.environ['TMPDIR']).resolve()==Path(tempfile.gettempdir()).resolve()
import numpy as np
from scipy.io import wavfile
from acoustics import evaluate,estimate_f0
from sequence_tract import generate,controls,block,ah,AREA,FS,OUTFS
repo=here.parents[4];old=repo/'research/experiments/autonomous-research-cycle/campaigns/nas-waveguide-vowel-mechanism-20261008-v1/runtime-bundle'
sys.path.append(str(old));spec=importlib.util.spec_from_file_location('frozen_vowel_baseline',old/'vowel_tract.py');baseline=importlib.util.module_from_spec(spec);spec.loader.exec_module(baseline)
contract=json.loads((here/'measurement-package-contract.json').read_text())
for n,h in contract['files'].items():assert hashlib.sha256((repo/n).read_bytes()).hexdigest()==h
sys.path.insert(0,str(repo/'research/experiments/autonomous-research-cycle/campaigns/nas-vocoder-f0-20261008-v1/runtime-bundle/packages-v2'))
import pyworld
def independent(x,a):
 r=[0.]*16;l=[0.]*16;out=[]
 for at,drive in enumerate(x):
  out.append(.15*r[-1]);nr=[0.]*16;nl=[0.]*16;nr[0]=drive+.75*l[0];nl[-1]=-.85*r[-1]
  for j in range(15):
   k=(float(a[at,j])-float(a[at,j+1]))/(float(a[at,j])+float(a[at,j+1]));theta=math.asin(k)
   nr[j+1]=math.cos(theta)*r[j]-math.sin(theta)*l[j+1];nl[j]=math.sin(theta)*r[j]+math.cos(theta)*l[j+1]
  r=nr;l=nl
 return np.array(out)
invalid=0
bad=[{},dict(segments=[],f0=220),dict(segments=[dict(vowel='k',duration_ms=200)],f0=220),dict(segments=[dict(vowel='a',duration_ms=124)],f0=220),dict(segments=[dict(vowel='a',duration_ms=601)],f0=220),dict(segments=[dict(vowel='a',duration_ms=200)],f0=float('nan')),dict(segments=[dict(vowel='a',duration_ms=200)]*25,f0=220),dict(segments=[dict(vowel='a',duration_ms=600)]*11,f0=220),dict(segments=[dict(vowel='a',duration_ms=200)],f0=220,gain=.25)]
for q in bad:
 try:controls(q)
 except (ValueError,TypeError):invalid+=1
 else:raise AssertionError('登録外のrequestを拒否しない')
try:block(np.zeros(4),np.ones((4,16)),np.full(32,np.nan))
except ValueError:invalid+=1
else:raise AssertionError('非有限状態を拒否しない')
rows=[];calls=0
for row in json.loads((here/'requests.json').read_text()):
 request=row['request'];audio,meta,raw,x,a=generate(request);alternate=generate(request,(2048,4096,8192));calls+=meta['source_and_block_render_calls']+alternate[1]['source_and_block_render_calls']
 assert np.array_equal(raw,alternate[2]) and np.array_equal(audio,alternate[0]) and meta['final_state_sha256']==alternate[1]['final_state_sha256']
 ref=independent(x,a);calls+=1;error=float(np.max(np.abs(raw-ref)));assert error<=1e-10
 original_exact=None
 if len(request['segments'])==1:
  original=baseline.generate(request['segments'][0]['vowel'],request['f0']);calls+=2;assert np.array_equal(raw,original[2]) and np.array_equal(audio,original[0]);original_exact=True
 if row['id']=='all-five':
  future=[dict(s) for s in request['segments']];future[-1]['vowel']='i';q=dict(segments=future,f0=request['f0']);changed=generate(q);calls+=changed[1]['source_and_block_render_calls'];cut=int(meta['bounds_samples'][-2]);assert np.array_equal(raw[:cut],changed[2][:cut])
 path=work/(row['id']+'.wav');wavfile.write(path,OUTFS,audio.astype(np.float32));fs,saved=wavfile.read(path)
 e0=evaluate(saved,dict(expected_duration_seconds=meta['duration_ms']/1000.),fs);f,t=pyworld.dio(saved.astype(float),fs,f0_floor=70.,f0_ceil=800.,frame_period=5.);f=pyworld.stonemask(saved.astype(float),f,t,fs)
 hz,confidence=estimate_f0(saved[round(.06*fs):-round(.06*fs)],fs,minimum=70,maximum=800);v=f[f>0];median=float(np.median(v)) if len(v) else None;target=request['f0'];de=abs(12*math.log2(median/target)) if median else None;ae=abs(12*math.log2(hz/target)) if hz else None
 support=[]
 for index,segment in enumerate(request['segments']):
  lo=meta['bounds_samples'][index]/FS+.105;hi=meta['bounds_samples'][index+1]/FS-.01;sel=(t>=lo)&(t<hi);valid=f[sel & (f>=70)&(f<=800)];complete=len(valid)>=3 and len(valid)>=sel.sum()*.5
  support.append(dict(index=index,bounds=[lo,hi],frames=int(sel.sum()),voiced_frames=len(valid),complete=bool(complete)))
 missing=sum(not s['complete'] for s in support);passed=bool(de is not None and ae is not None and de<=1. and ae<=1. and confidence>=.6 and not missing)
 rows.append(dict(id=row['id'],request=request,metadata=meta,independent_rotation_error=error,partition_wave_and_final_state_exact=True,old_single_vowel_raw_and_audio_exact=original_exact,wav_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),E0=e0,pitch=dict(passed=passed,dio_hz=median,acf_hz=hz,acf_confidence=confidence,dio_error_semitones=de,acf_error_semitones=ae,support=support,missing=missing)))
print(json.dumps(dict(mechanism_passed=True,rows=rows,actual_render_calls=calls,invalid_requests_and_state_rejected=invalid,longest_ms=max(r['metadata']['duration_ms'] for r in rows),fixed_support_intervals=sum(len(r['pitch']['support']) for r in rows),missing_support=sum(r['pitch']['missing'] for r in rows),E0_pass=sum(r['E0']['E0_pass'] for r in rows),pitch_pass=sum(r['pitch']['passed'] for r in rows),future_request_raw_prefix_exact=True,all_partitions_exact=True,content_or_perceptual_qualification=False)))
'''

PROBE=r'''"""禁止された実データ読取りとネットワーク接続が権限で拒否されるかを確認。"""
import sys,json,socket,errno
rows=[]
for path in json.loads(sys.stdin.read()):
 try:
  with open(path,'rb') as f:f.read(1)
 except PermissionError as e:rows.append(dict(path=path,denied=True,error=type(e).__name__))
 except OSError as e:rows.append(dict(path=path,denied=False,error=type(e).__name__))
 else:rows.append(dict(path=path,denied=False,error=None))
s=socket.socket();s.settimeout(2.)
try:s.connect(('1.1.1.1',80))
except OSError as e:network=e.errno in (errno.EPERM,errno.EACCES)
else:network=False
finally:s.close()
print(json.dumps(dict(files=rows,network_denied=network,all_denied=all(r['denied'] for r in rows) and network)))
'''

def requests():
    def row(id,letters,ms,f0):return dict(id=id,request=dict(segments=[dict(vowel=v,duration_ms=ms) for v in letters],f0=f0))
    return [row('single-a','a',600,220),row('single-i','i',600,110),row('single-u','u',600,280),row('all-five','aiueo',250,220),row('reverse-five','oeuia',250,280),row('long-forward','aiueo'*4,250,220),row('long-reverse','oeuia'*4,250,110),row('long-alternating','ai'*12,250,280)]

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n

def profile(b,work,isolated):
    text='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
    if isolated:
        allowed=[PYTHON.parent.parent,HERE/'runtime-bundle',work]
        text+='(deny file-read* (subpath '+json.dumps(str(REPO/'research'))+'))\n(deny file-read-data (subpath '+json.dumps(str(b.guard.root))+'))\n'
        text+='(allow file-read* '+''.join('(subpath '+json.dumps(str(p))+') ' for p in allowed)+')\n'
        text+='(allow file-read-data (literal '+json.dumps(str(b.guard.root/'identity.json'))+'))\n'
        ancestors=set();[ancestors.update(p.parents) for p in allowed]
        text+='(allow file-read-metadata '+''.join('(literal '+json.dumps(str(p))+') ' for p in sorted(ancestors))+')\n'
        site=PYTHON.parent.parent/'lib/python3.11/site-packages'
        text+='(deny file-read* '+''.join('(subpath '+json.dumps(str(site/n))+') ' for n in ('torch','tensorflow','transformers','faster_whisper','ctranslate2','onnxruntime','sherpa_onnx'))+')\n'
    assert '(allow file-read-data )' not in text and '(allow file-read-metadata )' not in text
    return text

def execute(command,env,text=None,input_text=None,timeout=900):
    if text:command=['/usr/bin/sandbox-exec','-p',text,*command]
    out=subprocess.run(command,env=env,input=input_text,capture_output=True,text=True,check=True,timeout=timeout)
    return json.loads(out.stdout)

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'] and read(PREV/'aggregate-summary.json')['engineering_all_required_pass']
    for source in (MODULE,CLI,BATCH,WORKER,PROBE):ast.parse(source)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=20,audit=20,render=3000,dsp=3000,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='母音の共有面積/有限帯域源を変えず、声道状態と位相を継承して6秒までの列を連続生成し、区切り不変と通常/隔離/CLIを保持できるか。',
        factor='新Cは外から渡す正規化右/左stateを読み最終stateを返す。旧一母音出力と演算順は同じ。母音指令の先頭を初期形状、次母音の開始後100msを面積smoothstepとする。',
        inherited=dict(diameters=digest(PREV/'diameters.json'),LF_coefficients=digest(PREV/'coefficients.json'),source_cutoff_hz=8000,source_fs=34300,output_fs=24000,glottal_reflection=.75,lip_reflection=-.85,gain=.10,fade_ms=12,original_single_vowel_seal=digest(PREV/'artifact-seal.json')),
        inputs=requests(),request_bounds=dict(vowels=['a','i','u','e','o'],segments=[1,24],integer_segment_ms=[125,600],total_ms_at_most=6000,F0_Hz=[70,400],additional_keys_rejected=True),
        fixture=dict(partitions=[4096,[2048,4096,8192]],independent_wave_error=1e-10,partition_raw_audio_and_final_state_bytes_exact=True,old_three_single_vowels_raw_audio_exact=True,future_request_prefix_exact=True,
            E0='原evaluate全条件',pitch='DIO/ACF±1半音、confidence≥.6。各moraの事前[開始+.105s,終了-.01s]で3frame以上/半数以上、欠測全分母。',normal_and_isolated_wave_bytes_exact=True,CLI_conditions=['single-a','long-forward','long-alternating'],actual_prohibited_file_reads_and_network_must_be_Permission_denied=True),
        engineering_is_not_content_or_perception=True,Japanese_consonants_or_full_speech_qualified=False,all_prior_frozen_routes_kept=True,
        c_sha256=hashlib.sha256(C_SOURCE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),limits=limits,
        estimates=dict(render=1000,dsp=1000,internal_block_and_source_calls_included=True,maximum_seconds=6000,temporary_peak=32000000,temporary_write=64000000,RAM_gb=8),
        protected_confirmation_opened=False,perceptual_qualification=False,quality_goal_completed=False,
        next='全機構/隔離通過時だけ新しい有限母音語列で原nativeと二ASR内容比較を出力前登録。工学不通過を同列のgain/径/反射/指令時刻で救済しない。子音/鼻腔/閉鎖/損失/放射は別機構。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','状態継承と6秒母音列・全工程/隔離費を出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'requests.json',requests(),j)
        for n,src in [('waveguide_stream.c',C_SOURCE),('sequence_tract.py',MODULE),('cli.py',CLI),('batch.py',BATCH),('worker.py',WORKER),('denial_probe.py',PROBE)]:b.write(HERE/n,src.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0120.json',dict(active_campaign=NAME,next='登録push→state継承C buildと共有入口固定→独立/区切り/通常隔離CLI→全分母封印',new_waveforms=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'setup','状態継承Cを外部cacheでbuildし共有生成bundleを固定',reserve_bytes=30000000) as j:
        bundle=HERE/'runtime-bundle'
        for name in ('sequence_tract.py','cli.py','batch.py','denial_probe.py'):b.write(bundle/name,(HERE/name).read_bytes(),j)
        for name in ('diameters.json','coefficients.json','acoustics.py'):b.write(bundle/name,(PREV/'runtime-bundle'/name).read_bytes(),j)
        b.save(HERE/'measurement-package-contract.json',read(PREV/'measurement-package-contract.json'),j)
        with b.workspace(j,'state継承C build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'waveguide_stream.c'),'-o',str(bundle/'waveguide_stream.dylib')]
            with b.external_output(bundle/'waveguide_stream.dylib',100000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        assert all(not p.is_symlink() for p in bundle.iterdir())
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'waveguide_stream.c'),binary_sha256=digest(bundle/'waveguide_stream.dylib'),temporary_removed=True),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},HMM=False,neural=False,recorded_audio=False,utterance_lookup=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('state継承Cと共有母音列入口を出力前固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','母音列の連続/区切り/独立参照/通常隔離CLIの全block源',1000,120000000,expected_seconds=2400)
    try:
        d=b.reserve(NAME,'dsp','状態/位相/全分母と実読取り接続拒否・入口byte一致',1000,3000000,expected_seconds=2400)
        try:
            with b.workspace(r,'連続生成の数値と通常実行の専用領域',32000000,64000000) as (work,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                fixture=execute([str(PYTHON),'-B',str(HERE/'worker.py'),str(work)],env,timeout=1800)
                b.save(HERE/'fixture-audit.json',fixture,d);manifest=[]
                for p in sorted(work.glob('*.wav')):
                    target=HERE/'render'/p.name;b.write_data(target,p.read_bytes(),r);manifest.append(dict(path=str(target.relative_to(REPO)),sha256=digest(target)))
                assert len(manifest)==8;b.save(HERE/'render-manifest.json',dict(rows=manifest,output_waves=8),d)
            with b.workspace(r,'隔離生成と実読取り接続拒否専用領域',16000000,32000000) as (work,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1');strict=profile(b,work,True)
                isolated=execute([str(PYTHON),'-B',str(HERE/'runtime-bundle/batch.py'),str(work)],env,strict,json.dumps(requests()),timeout=600)
                assert [x['wav_sha256'] for x in isolated['rows']]==[x['wav_sha256'] for x in fixture['rows']]
                forbidden=[PREV/'render/a-220.wav',(PREV/'render/a-220.wav').resolve(),PREV/'upstream/arai-2007.pdf',(PREV/'upstream/arai-2007.pdf').resolve(),HERE/'registration.json',ROOT/'control/state.json',ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/protocol.json',ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/runtime-batch-normal.json', (ROOT/'campaigns/nas-fujisaki-context-comparison-20261008-v1/runtime-batch-normal.json').resolve()]
                assert all(p.is_file() for p in forbidden)
                probe=execute([str(PYTHON),'-B',str(HERE/'runtime-bundle/denial_probe.py')],env,strict,json.dumps([str(p) for p in forbidden]),timeout=45);assert probe['all_denied']
                cli=[]
                for id in read(HERE/'registration.json')['fixture']['CLI_conditions']:
                    row=next(x for x in fixture['rows'] if x['id']==id);out=execute([str(PYTHON),'-B',str(HERE/'runtime-bundle/cli.py'),'--output',str(work/(id+'-cli.wav'))],env,strict,json.dumps(row['request']),timeout=300)
                    assert out['wav_sha256']==row['wav_sha256'];cli.append(dict(id=id,wav_sha256=out['wav_sha256'],calls=out['source_and_block_render_calls']))
                b.save(HERE/'denial-probe.json',probe,d);b.save(HERE/'runtime-audit.json',dict(normal_isolated_all8_exact=True,CLI_all3_exact=True,CLI_rows=cli,normal_calls=fixture['actual_render_calls'],isolated_calls=isolated['calls'],CLI_calls=sum(x['calls'] for x in cli),actual_calls=fixture['actual_render_calls']+isolated['calls']+sum(x['calls'] for x in cli),charged_render=1000,charged_DSP=1000,forbidden_files_and_network_denied=True,all_generation_bundle_files_internal=True,no_unconditional_empty_read_allow=True,HMM=False,neural=False,recorded_audio=False,utterance_lookup=False),d)
                assert fixture['actual_render_calls']+isolated['calls']+sum(x['calls'] for x in cli)<=1000
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','母音列の連続/入口限定資格・全工学分母・費用・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['mechanism_passed'];engineering=fixture['E0_pass']==8 and fixture['pitch_pass']==8 and fixture['missing_support']==0
        result=dict(mechanism_passed=True,engineering_all_required_pass=engineering,E0_pass=fixture['E0_pass'],pitch_pass=fixture['pitch_pass'],total=8,missing_support=fixture['missing_support'],fixed_support_intervals=fixture['fixed_support_intervals'],longest_ms=fixture['longest_ms'],partition_raw_audio_state_exact=True,old_three_single_vowels_exact=True,future_request_raw_prefix_exact=True,normal_isolated_all8_exact=True,CLI_all3_exact=True,actual_reads_and_network_denied=True,consonants_or_full_Japanese_content_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next'])
        b.save(HERE/'aggregate-summary.json',result,j)
        lines=['# 状態を継承する連続母音列の生成入口','','原五母音の径・終端・LF尺度・帯域・gainを変えず、独自Cが正規化右/左stateを引き継ぐ。発話先頭だけstate0/phase.125。4096単位と2048/4096/8192の混合区切りでraw/audio/final stateがbyte一致。原3単母音は旧入口とbyte一致し、8列を独立回転計算と照合した。','',
            '次母音の開始後100msに面積をsmoothstepで変え、源位相は途切れない。1..24母音・125..600ms/区間・総6000ms・F0 70..400Hzのみを受け付け、未知母音/追加キー/不正状態を拒否する。子音・声門閉鎖・鼻腔・放射/損失・移動壁の仕事は未実装。','',
            f'全8列のE0 {fixture["E0_pass"]}/8、pitch {fixture["pitch_pass"]}/8、事前支持欠測 {fixture["missing_support"]}/{fixture["fixed_support_intervals"]}。最長{fixture["longest_ms"]}ms。全工学通過 {engineering}。閾値を変えず不通過も全分母へ残す。','',
            '通常/隔離8波と隔離CLI3条件が全byte一致。過去波形/一次PDFの論理・実体パス、登録、台帳、旧protocol、通常実行archiveの実読取り9件と実接続が権限で拒否された。最終生成bundleの実体だけを許可し、HMM/神経推論/録音/発話lookupを用いない。','',
            '1000render/1000DSPは源と内部block呼出し、独立参照、通常隔離CLIを含む保守的費用で返金しない。全自分一時領域を指定外部媒体から回収し、残存なしを照合した。連続母音の計算資格を内容/母音知覚/全日本語自然さへ拡張しない。','',result['next'],'','旧契約/封印/凍結・日本語知覚資格なし・P5未開封・品質未達を保持。','']
        b.write(HERE/'report.md','\n'.join(lines).encode(),j);s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='waveguide-sequence-runtime-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0121.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,budget=b.reconcile()))
    print(dict(mechanism_passed=True,engineering_all_required_pass=engineering,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
