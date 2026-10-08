"""一次式の句/アクセント応答と、ラベル・状態長からの共有韻律指令を独立検証する。"""
import argparse, ast, hashlib, json, os, subprocess, urllib.request
from pathlib import Path
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-fujisaki-context-mechanism-20261008-v1'
NAME='fujisaki-context-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1/runtime-bundle'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PAPER='https://www.jstage.jst.go.jp/article/ast1980/5/4/5_4_233/_pdf'
BUNDLE=['local_renderer.py','local_hts-v2.dylib','source_renderer.py','counter.dylib','timing_engine.py','timing.dylib','japanese_frontend.py','mei_normal.htsvoice','acoustics.py','LICENSE-HTSVOICE','controls_v2.py','hts_arrays.py','hts_arrays.dylib','HTS-BSD-NOTICE.txt','calibration.py']

MODULE=r'''"""文章指令に対する固定Fujisaki応答。録音・教師・発話lookup・学習を使わない。"""
import math,re,hashlib
import numpy as np
ALPHA=3.;BETA=20.;GAMMA=.9;AP=.15;AA=.25;LEAD=.2;DT=.005
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def gp(t):
 x=np.asarray(t,dtype=float);u=np.maximum(x,0.)
 return np.where(x>=0.,ALPHA**2*u*np.exp(-ALPHA*u),0.)
def ga(t):
 x=np.asarray(t,dtype=float);u=np.maximum(x,0.)
 return np.where(x>=0.,np.minimum(-np.expm1(-BETA*u)-BETA*u*np.exp(-BETA*u),GAMMA),0.)
def contour(times,phrases,accents):
 t=np.asarray(times,dtype=float)
 if t.ndim!=1 or not len(t) or not np.isfinite(t).all():raise ValueError('有限非空の時刻列が必要')
 p=np.zeros_like(t);a=np.zeros_like(t)
 for onset in phrases:
  if not math.isfinite(onset):raise ValueError('句指令時刻が有限でない')
  p+=AP*gp(t-float(onset))
 for onset,offset in accents:
  if not math.isfinite(onset+offset) or onset>=offset:raise ValueError('アクセント指令の開始/終了が不正')
  a+=AA*(ga(t-float(onset))-ga(t-float(offset)))
 if not np.isfinite(p+a).all():raise ValueError('応答が有限でない')
 return p+a,p,a
def commands(labels,duration):
 d=np.asarray(duration)
 if d.ndim!=1 or len(d)!=len(labels)*5 or not np.isfinite(d).all() or np.any(d<1) or np.any(d!=np.floor(d)):
  raise ValueError('各音素5状態の正整数durationが必要')
 bounds=np.r_[0,np.cumsum(d.reshape(-1,5).sum(axis=1))].astype(int);groups=[];current=None
 for i,label in enumerate(labels):
  phone=re.search(r'\-([^+]+)\+',label)
  if phone is None:raise ValueError('音素ラベル構文が不正')
  if phone.group(1) in ('sil','pau'):current=None;continue
  a=re.search(r'/A:(-?\d+)\+(\d+)\+(\d+)',label)
  f=re.search(r'/F:(\d+)_(\d+)#(\d+)_xx@(\d+)_(\d+)\|(\d+)_(\d+)',label)
  breath=re.search(r'/I:(\d+)-(\d+)@(\d+)\+(\d+)&',label)
  if not a or not f or not breath:raise ValueError('A/F/I文脈が不足')
  count,accent,emotion,ap_index,ap_back,mora_start,mora_back=map(int,f.groups());position=int(a.group(2));bg=int(breath.group(3));key=(bg,ap_index)
  if emotion!=0 or not 1<=accent<=count or not 1<=position<=count:raise ValueError('登録外の疑問/アクセント文脈')
  if current is None or current['key']!=key:
   current=dict(key=key,mora_count=count,encoded_accent=accent,terminal_accent_ambiguous=accent==count,moras=[]);groups.append(current)
  if (current['mora_count'],current['encoded_accent'])!=(count,accent):raise ValueError('句内の文脈が不一致')
  if not current['moras'] or current['moras'][-1]['position']!=position:
   current['moras'].append(dict(position=position,start_frame=int(bounds[i]),end_frame=int(bounds[i+1])))
  else:current['moras'][-1]['end_frame']=int(bounds[i+1])
 if not groups:raise ValueError('アクセント句がない')
 phrases=[];accents=[];seen=set()
 for g in groups:
  m=g['moras'];n=g['mora_count'];accent=g['encoded_accent'];bg=g['key'][0]
  if [v['position'] for v in m]!=list(range(1,n+1)):raise ValueError('句の全モーラ順序が不一致')
  if bg not in seen:phrases.append(m[0]['start_frame']*DT-LEAD);seen.add(bg)
  first=0 if accent==1 or n==1 else 1
  accents.append([m[first]['start_frame']*DT,m[accent-1]['end_frame']*DT])
 return dict(phrase_times=phrases,accent_times=accents,groups=groups,frames=int(d.sum()),
             rule='一breath groupの先頭-.2秒に句指令。アクセント1は第1モーラ開始、それ以外は第2開始。終了はencoded accentモーラ末。',
             encoded_final_or_unaccented_not_distinguished=True,phonological_accent_truth_claimed=False)
def transform(native,labels,duration,pitch):
 if len(native)!=3 or not math.isfinite(pitch) or not 70<=pitch<=800:raise ValueError('3streamと登録Hz範囲が必要')
 x=[np.asarray(v) for v in native]
 if any(v.ndim!=2 or not v.size or not np.isfinite(v).all() for v in x) or len({len(v) for v in x})!=1 or x[1].shape[1]!=1:raise ValueError('3streamの形状が不正')
 voiced=x[1][:,0]>0
 if not voiced.any() or np.any(x[1][~voiced]!=-1e10):raise ValueError('有声mask/sentinelが不正')
 c=commands(labels,duration)
 if c['frames']!=len(x[1]):raise ValueError('duration総和と全frameが不一致')
 times=np.arange(len(x[1]),dtype=float)*DT;shape,p,a=contour(times,c['phrase_times'],c['accent_times'])
 center=float(np.median(shape[voiced]));offset=math.log(float(pitch))-center;out=[v.copy() for v in x];out[1][voiced,0]=shape[voiced]+offset
 hz=np.exp(out[1][voiced,0])
 if np.any((hz<70)|(hz>800)):raise ValueError('共有応答LF0が範囲外。clipせず拒否')
 assert out[0].tobytes()==x[0].tobytes() and out[2].tobytes()==x[2].tobytes() and out[1][~voiced].tobytes()==x[1][~voiced].tobytes()
 assert np.array_equal(out[1][:,0]>0,voiced) and abs(np.median(out[1][voiced,0])-math.log(pitch))<=2e-15
 return out,dict(model='fixed-Fujisaki-command-response',commands=c,parameters=dict(alpha=ALPHA,beta=BETA,gamma=GAMMA,Ap_seconds=AP,Aa=AA,phrase_lead_seconds=LEAD),
                 phrase_response_sha256=ah(p),accent_response_sha256=ah(a),uncentered_response_sha256=ah(shape),log_offset=offset,
                 native_LF0_values_used_for_shape=False,generated_voiced_mask_used=True,whole_utterance_voiced_median_calibration=True,
                 causal_response_before_global_calibration=True,whole_utterance_calibration_is_not_streaming_causal=True,
                 MCP_LPF_duration_and_MSD_unchanged=True,original_voiced_contour_preserved=False,AP_noise_power_factor=1.,
                 generated_median_hz=float(np.exp(np.median(out[1][voiced,0]))),waveform_pitch_verified=False,per_waveform_gain_rescue=False)
'''

def runtime():
    s=(PARENT/'runtime.py').read_text()
    s=s.replace('from shape_arrays import synthesize as shape_synthesize','from hts_arrays import synthesize as bare_synthesize\nfrom fujisaki_context import transform as fujisaki_transform')
    s=s.replace("METHODS=['native','lf']","METHODS=['native','fujisaki']")
    old="params,control,relative_error,invariants=transform('calibrated',native,row['full_context_labels'],before['duration'],pitch)"
    new="""params,control,relative_error,invariants=transform('calibrated',native,row['full_context_labels'],before['duration'],pitch)
        if method=='fujisaki':
            params,control=fujisaki_transform(native,row['full_context_labels'],before['duration'],pitch)
            mask=native[1][:,0]>0
            relative_error=float(np.max(np.abs((params[1][mask,0]-np.median(params[1][mask,0]))-(native[1][mask,0]-np.median(native[1][mask,0])))))
            invariants=bool(np.array_equal(params[0],native[0]) and np.array_equal(params[2],native[2]) and np.array_equal(params[1][:,0]>0,mask) and params[1][~mask].tobytes()==native[1][~mask].tobytes())"""
    assert s.count(old)==1;s=s.replace(old,new).replace('raw,conversion=shape_synthesize(params,settings,method)','raw,conversion=bare_synthesize(params,settings)\n        conversion.update(source_method="native-pulse-noise",LF0_factor=method,between_methods_source_clock_identity_claimed=False,render_calls_including_internal_MLSA=1)')
    return s

WORKER=r'''"""二次系の独立応答、人工ラベル、全実frameの因子保持、native配列入口を照合。"""
import sys,json,math,os,tempfile,hashlib
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import signal
from fujisaki_context import gp,ga,contour,commands,transform,ALPHA,BETA,GAMMA,DT,ah
from runtime import generate
from hts_arrays import synthesize
t=np.linspace(0.,3.,3001)
_,impulse=signal.impulse(([ALPHA**2],[1.,2.*ALPHA,ALPHA**2]),T=t)
_,step=signal.step(([BETA**2],[1.,2.*BETA,BETA**2]),T=t)
err_p=float(np.max(np.abs(gp(t)-impulse)));err_a=float(np.max(np.abs(ga(t)-np.minimum(step,GAMMA))))
assert err_p<=1e-11 and err_a<=1e-11
assert gp(-.1)==0 and ga(-.1)==0 and gp(0.)==0 and ga(0.)==0
assert abs(gp(1./ALPHA)-ALPHA/math.e)<=1e-12 and ga(3.)==GAMMA
primitive=[]
for p,a in (([0.],[[.1,.4]]),([-.2,1.],[[0.,.2],[1.1,1.5]]),([],[[-.3,-.1]]),([.4],[])):
 times=np.linspace(-.5,2.,2501);out,phrase,accent=contour(times,p,a)
 def sp(v):return ALPHA**2*v*math.exp(-ALPHA*v) if v>=0 else 0.
 def sa(v):return min(1.-(1.+BETA*v)*math.exp(-BETA*v),GAMMA) if v>=0 else 0.
 reference=np.array([sum(.15*sp(float(v)-u) for u in p)+sum(.25*(sa(float(v)-u)-sa(float(v)-w)) for u,w in a) for v in times])
 error=float(np.max(np.abs(out-reference)));assert error<=1e-12
 future=contour(times,p+[1.],a+[[1.2,1.6]])[0];assert np.array_equal(out[times<1.],future[times<1.])
 primitive.append(dict(phrase_commands=p,accent_commands=a,scalar_max_abs_error=error,causal_response_prefix_exact=True))
invalid=0
for args in (([np.nan],[],[]),([0.],[float('inf')],[]),([0.],[],[[.1,.1]]),([0.],[],[[.2,.1]])):
 try:contour(*args)
 except ValueError:invalid+=1
 else:raise AssertionError('不正な指令を拒否しない')
def label(phone,bg,ap,mora,count,accent):
 return f'xx^xx-{phone}+xx=xx/A:{mora-accent}+{mora}+{count-mora+1}/F:{count}_{accent}#0_xx@{ap}_1|1_1/I:1-1@{bg}+1&1-1|1+1'
labels=['xx^xx-sil+xx=xx/A:xx+xx+xx',label('k',1,1,1,3,2),label('a',1,1,1,3,2),label('i',1,1,2,3,2),label('o',1,1,3,3,2),
        'xx^xx-pau+xx=xx/A:xx+xx+xx',label('u',2,1,1,1,1),'xx^xx-sil+xx=xx/A:xx+xx+xx']
d=np.full(len(labels)*5,2);c=commands(labels,d)
assert c['frames']==80 and np.allclose(c['phrase_times'],[-.15,.1],rtol=0,atol=1e-14) and np.allclose(c['accent_times'],[[.15,.2],[.3,.35]],rtol=0,atol=1e-14)
bad_d=d.copy();bad_d[0]=0
try:commands(labels,bad_d)
except ValueError:invalid+=1
else:raise AssertionError('不正durationを拒否しない')
x=[np.zeros((80,35)),np.full((80,1),math.log(220.)),np.ones((80,1))];x[1][:10]=-1e10
y,detail=transform(x,labels,d,220.);changed=[v.copy() for v in x];changed[1][changed[1][:,0]>0,0]+=np.linspace(-.1,.1,int(np.sum(changed[1][:,0]>0)))
z,_=transform(changed,labels,d,220.);assert np.array_equal(y[1],z[1])
rows=[]
specs=['桜の種を畑にまいた。','荷物を棚に置いた。','川沿いを歩き、橋の下で休んだ。','港の灯りが消える前に、船の鍵を箱へ戻した。']
for text in specs:
 for speed,pitch in ((1.,220.),(1.15,280.)):
  native,mn,pn,rn=generate(text,'native',speed,pitch,True);candidate,mc,pc,rc=generate(text,'fujisaki',speed,pitch,True)
  assert rn==rc
  for key in ('duration','msd','settings','state_sha256','variance_sha256','native_parameter_hashes'):assert mn[key]==mc[key],key
  assert np.array_equal(pn[0],pc[0]) and np.array_equal(pn[2],pc[2]);mask=pn[1][:,0]>0
  assert np.array_equal(mask,pc[1][:,0]>0) and pn[1][~mask].tobytes()==pc[1][~mask].tobytes()
  independent,ind=synthesize(pn,mn['settings']);expected=(independent*.25).astype(np.float32)
  import io
  from scipy.io import wavfile
  fs,native_samples=wavfile.read(io.BytesIO(native));assert fs==24000 and np.array_equal(native_samples,expected)
  _,candidate_samples=wavfile.read(io.BytesIO(candidate));assert np.isfinite(candidate_samples).all() and len(native_samples)==len(candidate_samples)
  assert mc['invariants_pass'] and abs(mc['generated_lf0_median_hz']/pitch-1.)<=1e-14
  assert not np.array_equal(pn[1][mask],pc[1][mask]) and mc['control']['native_LF0_values_used_for_shape'] is False
  rows.append(dict(text=text,speed=speed,pitch=pitch,frames=len(pn[0]),native_wave_sha256=mn['sha256'],candidate_wave_sha256=mc['sha256'],
                   all_frames_MCP_LPF_exact=True,MSD_mask_and_duration_exact=True,shared_model_and_variance_exact=True,native_bare_renderer_exact=True,
                   LF0_intentionally_changed=True,median_error_hz=abs(mc['generated_lf0_median_hz']-pitch),relative_contour_error=mc['relative_LF0_max_abs_error'],
                   E0_native=mn['E0_pass'],E0_candidate=mc['E0_pass'],control=mc['control'],all_input_hashes_native=mn['output_parameter_hashes'],all_input_hashes_candidate=mc['output_parameter_hashes']))
print(json.dumps(dict(passed=True,phrase_LTI_max_error=err_p,accent_LTI_max_error=err_a,primitive_conditions=primitive,synthetic_commands=c,invalid_inputs_rejected=invalid,
                     native_LF0_shape_influence_rejected=True,rows=rows,actual_HTS_render_calls=24,charged_render=80,charged_DSP=256,conservative_counts_not_returned=True,
                     response_causal=True,global_median_centering_not_streaming_causal=True,real_Japanese_quality_qualified=False,perceptual_qualification=False),ensure_ascii=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    previous=ROOT/'campaigns/nas-hts-lf-comparison-20261008-v1'
    assert not read(previous/'aggregate-summary.json')['research_protection_gates']['lf']
    rt=runtime();ast.parse(MODULE);ast.parse(rt);ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=16,audit=16,render=240,dsp=768,download=2000000,ai=0,teacher=0,train=0,inverse=0)
    reg=dict(campaign=NAME,question='句/アクセント指令の二次応答と文章文脈からの時刻規則を、原HTSのMCP/LPF/状態長/MSDを保持する共有韻律因子として実装できるか。',
             factor='原有声LF0の輪郭を、log Fb + Ap Gp(t-T0) + Aa[Ga(t-T1)-Ga(t-T2)]へ置換。元LF0値は輪郭計算に使わず、生成有声maskだけ保持。',
             formula=dict(Gp='alpha^2*t*exp(-alpha*t) for t>=0 else 0',Ga='min(1-(1+beta*t)*exp(-beta*t),gamma) for t>=0 else 0'),
             parameters=dict(alpha=3.,beta=20.,gamma=.9,Ap_seconds=.15,Aa=.25,phrase_lead_seconds=.2,frame_seconds=.005),
             provenance='alpha/beta/gammaは原論文Fig2の典型値。Ap/Aa/leadとラベル時刻規則は出力前固定の設計値で、Meiや人声のfit/最適化ではない。',
             commands_rule='一breath group先頭-.2秒の句指令。AP accent1は第1、それ以外は第2モーラ開始。encoded accentモーラ末でアクセント指令を終了。',
             label_limitation='Open JTalk F2は無アクセント0を末尾モーラ数へ写す。原ラベルだけでは末尾核と無アクセントを区別できず、両者を同じ終了時刻として扱う。疑問emotionは拒否。音韻正解を主張しない。',
             control='有声frame全体のlog中央値を指定220/280Hzへ同じ意味で合わせる。句/アクセント応答は因果的だが、全発話のmedian校正はstreaming因果ではない。F0は70..800、範囲外はclipしない。gain=.25、原pulse/noise/MLSA。',
             fixtures=dict(texts=['桜の種を畑にまいた。','荷物を棚に置いた。','川沿いを歩き、橋の下で休んだ。','港の灯りが消える前に、船の鍵を箱へ戻した。'],conditions=[[1.,220.],[1.15,280.]],LTI_grid=[0.,3.,3001],primitive_conditions=4),
             thresholds=dict(independent_LTI_error=1e-11,scalar_superposition_error=1e-12,causal_prefix_exact=True,all_frame_MCP_LPF_mask_duration_state_variance_exact=True,native_bare_wave_exact=True,generated_log_median_error=2e-15),
             costs=dict(actual_HTS_render_calls=24,render_conservatively_charged=80,DSP_conservatively_charged=256,download_conservatively=2000000,maximum_seconds=6000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),limits=limits,
             sources=dict(paper=PAPER,overview='https://www.isca-archive.org/speechprosody_2004/fujisaki04_speechprosody.pdf',label_definition='https://raw.githubusercontent.com/r9y9/open_jtalk/master/src/jpcommon/jpcommon_label.c',prior_LF_seal_sha256=digest(previous/'artifact-seal.json')),
             frozen_routes='LFの同係数/phase/LPF/gain救済、旧17→96の同8残差/同learner、LF0縮小/平坦化は引き続き凍結。この方式はラベルから指令を作る固定二次応答で、教師/残差学習を使わない。',
             bundle_dependencies={n:digest(PARENT/n) for n in BUNDLE},module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),runtime_sha256=hashlib.sha256(rt.encode()).hexdigest(),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
             perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,
             next='全機構通過時のみ新16文のnative/Fujisakiを別登録し、固定支持・二ASR・通常/隔離CLIを同じ全分母で比較。不改善時は同応答係数/指令時刻/gainを同コホートで救済しない。')
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','固定句/アクセント応答と文章指令の全機構費を出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'fujisaki_context.py',MODULE.encode(),j);b.write(HERE/'runtime.py',rt.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0111.json',dict(active_campaign=NAME,next='登録push→一次式保存→共有bundle→独立応答と全8実条件',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'download','Fujisaki1984一次論文を固定保存',2000000,4000000) as j:
        with urllib.request.urlopen(urllib.request.Request(PAPER,headers={'User-Agent':'VoiceSimulatorResearch/1.0'}),timeout=45) as response:data=response.read(2000001);url=str(response.url)
        assert len(data)<=2000000 and data.startswith(b'%PDF')
        b.write_data(HERE/'upstream/fujisaki-1984.pdf',data,j)
        b.save(HERE/'primary-source-audit.json',dict(url=PAPER,resolved_url=url,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),conservative_charge=2000000,unused_reservations_not_returned=True,implementation_independently_authored=True),j)
    with b.job(NAME,'setup','原共有HMMと声道/源を保持する韻律bundleを固定',reserve_bytes=20000000) as j:
        reg=read(HERE/'registration.json');bundle=HERE/'runtime-bundle'
        for n in BUNDLE:
            assert digest(PARENT/n)==reg['bundle_dependencies'][n];b.write(bundle/n,(PARENT/n).read_bytes(),j)
        for n in ('fujisaki_context.py','runtime.py'):b.write(bundle/n,(HERE/n).read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},neural_inference=False,saved_audio_lookup=False),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('一次式・固定文脈指令・共有bundleを科学出力前に固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','固定二次応答と原native/文脈韻律の全8実条件',80,20000000,expected_seconds=900)
    try:
        d=b.reserve(NAME,'dsp','独立LTI・scalar・因果性・全frame保持・限定校正の監査',256,2000000,expected_seconds=900)
        try:
            with b.workspace(r,'共有韻律fixtureの科学ライブラリと辞書初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=840)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','固定文脈韻律の限定範囲・全条件・費用・一時回収を封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['rows'])==8
        result=dict(mechanical_fixture_passed=True,shared_context_command_response=True,all_frames_MCP_LPF_duration_mask_preserved=True,native_bare_renderer_exact=True,
                    original_LF0_shape_intentionally_replaced=True,native_LF0_values_not_used_for_response=True,between_method_source_clock_identity_claimed=False,
                    independent_LTI_and_scalar_verified=True,response_causal_before_calibration=True,whole_utterance_median_not_streaming_causal=True,
                    encoded_terminal_accent_ambiguity_retained=True,real_Japanese_quality_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False,next=read(HERE/'registration.json')['next'])
        b.save(HERE/'aggregate-summary.json',result,j)
        b.write(HERE/'report.md',('# 句/アクセント指令の共有文脈韻律機構\n\n原論文Fig2のalpha=3/beta=20/gamma=.9を参照し、Ap=.15秒/Aa=.25/句先行.2秒と時刻規則を出力前に固定した。原有声LF0値の輪郭を使わず、生成maskとHMM状態長・A/F/I文脈から指令を作る。教師/録音/残差学習/発話lookupなし。原pulse/noise/MLSAとgain=.25を保持する。\n\n独立LTIのimpulse/step、独立scalar重畳、将来指令の前半不変、不正入力拒否、人工ラベル時刻、全8実条件のMCP/LPF/duration/MSD/state/variance不変、native配列入口の完全一致を確認した。原native8・候補8・独立native8の24HTS生成。応答/輪郭分を含め80render/256DSPを保守的に課し返金しない。\n\n句/アクセント応答は因果的だが、全発話有声中央値の校正はstreaming因果ではない。F2の末尾核/無アクセント同値化を保持し音韻正解を仮定しない。モデルの典型値をMeiの測定値/最適値と主張せず、機構通過を自然さ・内容・知覚pitchの資格へ拡張しない。方式間のLF0/源時計は意図して異なる。\n\n一次資料: [Fujisaki and Hirose (1984)]('+PAPER+')、[Open JTalkラベル定義](https://raw.githubusercontent.com/r9y9/open_jtalk/master/src/jpcommon/jpcommon_label.c)。式と文脈定義を参照した独自実装。\n\n'+result['next']+'\n\nP5未開封・日本語知覚資格なし・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];tmp=[x for x in s['temporary_work'].values() if x['campaign']==NAME];assert all(x['status']=='removed' and not os.path.lexists(x['path']) for x in tmp)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(tmp),all_owned_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='fujisaki-context-mechanism-completed',active_campaign=None,next=result['next'],git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0112.json',dict(latest_completed=NAME,next=result['next'],quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(mechanical_fixture_passed=True,real_Japanese_quality_qualified=False,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
