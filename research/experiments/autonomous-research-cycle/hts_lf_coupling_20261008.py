"""LF固定周期関数を原HTSの有声LPF入力へ結合し、時計/noise/独立混合を検証する。"""
import ast,hashlib,json,os,subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-lf-coupling-20261008-v1'
NAME='hts-lf-coupling-v1'
PARENT=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1'
LF=ROOT/'campaigns/nas-lf-source-mechanism-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

def make_sources():
    c=(PARENT/'shape.c').read_text().split('/* MCPの周波数変換')[0]
    c=c.replace('/* 原HTSを純観測し、その励振に独立の最小位相FIRを適用する別版。 */','/* 原HTSの有声LPF入力を固定LF周期関数へ置換する。 */')
    c=c.replace('static double *period_out,*counter_out,*source_out;', '''static double *period_out,*counter_out,*source_out,*noise_out,*periodic_out,*phase_out;
static int lf_mode=0;
static double lf_coeff[7],sample_noise,sample_periodic,sample_phase;
int lf_evaluate(const double *,double *,size_t,const double *,size_t);''')
    c=c.replace('    observed++;return x;', '    if(observed<capacity){noise_out[observed]=sample_noise;periodic_out[observed]=sample_periodic;phase_out[observed]=sample_phase;}\n    observed++;return x;')
    c=c.replace('size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,', 'size_t frames,size_t cols,size_t nlpf,int selected,const double *coeff,double *out,double *period,')
    c=c.replace('double *counter,double *source,uint8_t *event,size_t samples)', 'double *counter,double *source,double *noise,double *periodic,double *phase,uint8_t *event,size_t samples)')
    c=c.replace('!counter||!source||!event', '!counter||!source||!noise||!periodic||!phase||!coeff||!event').replace('selected!=0','(selected<0||selected>1)')
    c=c.replace('    double alpha=.55;', '    double probe=0.,zero=0.;if(!lf_evaluate(&zero,&probe,1,coeff,7))return 0;\n    double alpha=.55;')
    c=c.replace('    observed=0;capacity=samples;', '    lf_mode=selected;memcpy(lf_coeff,coeff,7*sizeof(double));noise_out=noise;periodic_out=periodic;phase_out=phase;\n    observed=0;capacity=samples;')
    c=c.replace('    SHAPE_Vocoder_clear(&v);', '    lf_mode=0;noise_out=periodic_out=phase_out=NULL;\n    SHAPE_Vocoder_clear(&v);')
    c=c.replace('!isfinite(source[i]))', '!isfinite(source[i])||!isfinite(noise[i])||!isfinite(periodic[i])||!isfinite(phase[i]))')
    vendor=(PARENT/'vendor/HTS_vocoder_shaped.c').read_text()
    start=vendor.index('static double HTS_Vocoder_get_excitation(');end=vendor.index('/* HTS_Vocoder_end_excitation:',start)
    original=vendor[start:end]
    assert original.count('pulse = sqrt(v->pitch_of_curr_point);')==1 and original.count('x = sqrt(v->pitch_of_curr_point);')==1
    # 元のnoise/RNG・counter・ring演算順を維持する。phaseはcounter更新後、period更新前。
    modified=original.replace('   double noise, pulse = 0.0;', '   double noise=0.0, pulse = 0.0;\n   sample_noise=sample_periodic=0.0;sample_phase=-1.0;')
    needle='         HTS_Vocoder_excite_voiced_frame(v, noise, pulse, lpf);'
    modified=modified.replace(needle, '''         sample_phase=fmod(v->pitch_counter/v->pitch_of_curr_point,1.0);
         if(lf_mode && !lf_evaluate(&sample_phase,&pulse,1,lf_coeff,7))pulse=NAN;
         sample_periodic=pulse;
'''+needle)
    needle='         v->pitch_of_curr_point += v->pitch_inc_per_point;'
    assert modified.count(needle)==2
    # excite_buff_size==0の枝も同じLF置換。noiseの呼出条件は元のまま。
    pos=modified.index('   } else {\n      if (v->pitch_of_curr_point == 0.0)')
    first,second=modified[:pos],modified[pos:]
    second=second.replace('         x = HTS_white_noise(v);', '         x = noise = HTS_white_noise(v);')
    second=second.replace(needle, '''         sample_phase=fmod(v->pitch_counter/v->pitch_of_curr_point,1.0);
         if(lf_mode && !lf_evaluate(&sample_phase,&x,1,lf_coeff,7))x=NAN;
         sample_periodic=x;
'''+needle)
    modified=(first+second).replace('   return x;', '   sample_noise=noise;\n   return x;')
    vendor=vendor[:start]+modified+vendor[end:]
    return c,vendor

WRAPPER=r'''"""原時計でLFをLPF前有声成分へ入れる。自然さ/aliasingの資格は別に扱う。"""
import ctypes as C
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
import lf_source
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,P,P,P,P,U,S]
MODES={'native':0,'lf':1}
COEFF=np.array(__COEFFICIENTS__,dtype=np.float64)
def raw(params,settings,method):
 if method not in MODES:raise ValueError('未登録のLF源方式')
 x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
 arrays=[np.empty(n) for _ in range(7)];event=np.empty(n,dtype=np.uint8)
 assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],COEFF.ctypes.data_as(P),*(v.ctypes.data_as(P) for v in arrays),event.ctypes.data_as(U),n)
 out,period,counter,source,noise,periodic,phase=arrays
 assert [ah(v) for v in x]==before and np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
 assert all(np.isfinite(v).all() for v in arrays)
 return out,dict(period=period,counter=counter,excitation=source,noise=noise,periodic=periodic,phase=phase,event=event)
def synthesize(params,settings,method):
 x,tr=raw(params,settings,method);original=tr
 if method!='native':
  _,original=raw(params,settings,'native')
  assert all(np.array_equal(tr[k],original[k]) for k in ('period','counter','event','noise','phase'))
 audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
 env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
 return audio,dict(renderer='原HTS-MLSA/LPF前有声LF',source_method=method,effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
  source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(original['excitation']),processed_excitation_sha256=ah(tr['excitation']),
  noise_sha256=ah(tr['noise']),periodic_sha256=ah(tr['periodic']),LF_phase_sha256=ah(tr['phase']),cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
  original_noise_RNG_LPF_and_source_clock_unchanged=True,sqrt_period_replaced_only_for_LF_voiced_component=method=='lf',
  processed_excitation_intentionally_changed=method!='native',LF_fixed_time_ratios=[.4,.6,.05],LF_continuous_RMS_normalization=True,
  source_phase_rule='元counterに1を足しeventなら元periodを一度引く。その後counter/periodをfmod(.,1)し、period補間更新前にLFを評価。',
  phase_is_frequency_dependent=False,constant_delay_samples_not_defined=True,render_calls_including_internal_MLSA=1 if method=='native' else 2,
  finite_dynamic_zero_area_or_antialiasing_claimed=False,neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
'''

WORKER=r'''"""原配列vocoder対照と独立PythonのLF/LPF混合、元時計/noise、未来差分を照合する。"""
import sys,json,os,tempfile,math
from pathlib import Path
here=Path(__file__).resolve().parent;sys.path.insert(0,str(here/'runtime-bundle'))
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
import numpy as np
from scipy import signal
from hts_arrays import synthesize as bare,ah
from shape_arrays import raw,COEFF
from lf_source import scalar
def reference(tr,lpf,method):
 p=tr['period'];counter=tr['counter'];phase=np.full(len(p),-1.);pulse=np.zeros(len(p));source=np.empty(len(p));size=lpf.shape[1];ring=np.zeros(size);index=0
 for n in range(len(p)):
  if p[n]>0:
   c=counter[n]+1.;event=c>=p[n]
   if event:c-=p[n]
   phase[n]=math.fmod(c/p[n],1.)
   pulse[n]=scalar(float(phase[n]),COEFF) if method=='lf' else (math.sqrt(p[n]) if event else 0.)
  noise=tr['noise'][n];lp=lpf[n//240];center=(size-1)//2
  if p[n]==0:ring[(index+center)%size]+=noise
  else:
   if noise!=0.:
    for i in range(size):ring[(index+i)%size]+=noise*((1. if i==center else 0.)-lp[i])
   if pulse[n]!=0.:
    for i in range(size):ring[(index+i)%size]+=pulse[n]*lp[i]
  source[n]=ring[index];ring[index]=0.;index=(index+1)%size
 return source,pulse,phase
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
cases=[]
for hz in (110.,280.):
 for LPF in ('zero','one','31tap'):
  cases.append((str(hz)+'/'+LPF,np.full(60,hz),LPF))
cases.extend([('rising/31tap',np.linspace(110.,280.,60),'31tap'),('falling/31tap',np.linspace(280.,110.,60),'31tap')])
rows=[]
for name,hz,mode in cases:
 mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.2;lf0=np.full((100,1),-1e10);lf0[20:80,0]=np.log(hz)
 if mode=='31tap':
  q=np.arange(-15,16);kernel=np.sinc(.12*q)*np.hanning(31);kernel/=kernel.sum();lpf=np.tile(kernel,(100,1))
 else:lpf=np.full((100,1),0. if mode=='zero' else 1.)
 params=[mcp,lf0,lpf];before=[ah(v) for v in params];expected,_=bare(params,settings)
 native,tn=raw(params,settings,'native');changed,tc=raw(params,settings,'lf')
 a=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(a)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;a[:n]*=env;a[-n:]*=env[::-1]
 assert np.array_equal(a,expected) and [ah(v) for v in params]==before
 assert all(np.array_equal(tn[k],tc[k]) for k in ('period','counter','event','noise','phase'))
 errors={}
 for method,tr in (('native',tn),('lf',tc)):
  ref,pulse,phase=reference(tr,lpf,method)
  errors[method]=dict(source=float(np.max(np.abs(ref-tr['excitation']))),periodic=float(np.max(np.abs(pulse-tr['periodic']))),phase=float(np.max(np.abs(phase-tr['phase']))))
  assert errors[method]['source']<=1e-10 and errors[method]['periodic']<=1e-12 and errors[method]['phase']<=1e-12
 future=[v.copy() for v in params];future[0][50:,1]+=.1;future[1][50:80,0]=np.log(220.);future[2][50:]*=.9
 for method,old,tr in (('native',native,tn),('lf',changed,tc)):
  y,t=raw(future,settings,method);assert np.array_equal(old[:12000],y[:12000]) and all(np.array_equal(tr[k][:12000],t[k][:12000]) for k in tr)
 assert np.isfinite(changed).all()
 if mode=='zero':assert np.array_equal(native,changed)
 # unvoicedへの切替後、LPF ringのtailが尽きた領域だけ原励振と完全一致を要求する。
 assert np.array_equal(tn['excitation'][80*240+31:],tc['excitation'][80*240+31:])
 rows.append(dict(case=name,frames=100,LPF_columns=lpf.shape[1],native_wave_exact=True,input_streams_exact=True,source_clock_and_noise_exact=True,independent_errors=errors,
  causal_raw_prefix_exact=True,unvoiced_after_LPF_tail_exact=True,zero_LPF_wave_exact=mode=='zero',LF_source_changed=not np.array_equal(tn['excitation'],tc['excitation']),
  source_clock_hashes={k:ah(tn[k]) for k in ('period','counter','event')},native_excitation_sha256=ah(tn['excitation']),LF_excitation_sha256=ah(tc['excitation']),passed=True))
assert len(rows)==8 and sum(v['LF_source_changed'] for v in rows)==6
print(json.dumps(dict(passed=True,rows=rows,render=56,dsp=96,scope='登録人工8条件の原native対照、LF周期関数と独立LPF混合、元時計/noise/入力、raw未来差分だけ。',
 real_Japanese_speech_qualified=False,antialiasing_qualified=False,perceived_pitch_or_quality_truth=False,quality_certified=False),allow_nan=False))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    for n,h in contract.get('inherited_files',{}).items():assert digest(REPO/n)==h,n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert b.snapshot()['long_horizon']['last_review']['scientific_completed']==30 and read(LF/'aggregate-summary.json')['mechanical_fixture_passed']
    coefficients=read(LF/'fixture-audit.json')['coefficients'];wrapper=WRAPPER.replace('__COEFFICIENTS__',repr(coefficients));c,vendor=make_sources();ast.parse(wrapper);ast.parse(WORKER)
    limits=dict(seconds=7200,bytes=300000000,write_bytes=800000000,setup=16,audit=16,render=168,dsp=288,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='固定LF周期関数を原HTSのLPF前有声入力へ結合し、元native/時計/noise/独立混合/因果性を保持できるか。',
        factor='元sqrt(period) impulseを、有声時だけ連続周期RMS=1の固定LF derivativeへ置換。noiseの算法/seed/呼出条件と元counter/period/LPF/MLSA/全入力を維持。',
        phase='counter+=1、eventなら元periodを一度引く。period補間更新前にphase=fmod(counter/period,1)を評価。無声phase=-1。源の時間変動や有限区間面積0を保証しない。',
        coefficients=coefficients,controls='C独自LF式・元HTS-BSDの混合ring手順、alpha.55/stage0/48k/fperiod240/24k resample/12msfade。波形別gain/係数/phase探索なし。LF0列縮小とは別。',
        fixture=dict(F0=[110.,280.,'rising110to280','falling280to110'],LPF=['0','1','31tap fixed sinc(.12*n)*hann normalized'],frames=100,voiced_frames=[20,80],all_eight_required=True,
            future_changes_at_frame=50,native_wave_byte_exact=True,clock_noise_and_inputs_byte_exact=True,independent_phase_and_periodic_error_at_most=1e-12,independent_mixed_excitation_error_at_most=1e-10,causal_raw_prefix_exact=True),
        estimates=dict(render=56,render_breakdown='8条件×(bare/native/LF/独立native源/独立LF源/未来native/未来LF)=56',dsp=96,dsp_breakdown='8条件×12のnative/clock/noise/phase/二周期成分/二混合励振/入力/有限/二因果監査',maximum_seconds=6000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
        scope='人工結合機構だけ。未知日本語/短文・長文/固定音素支持/二ASR/通常隔離/CLI/aliasing/知覚品質は未資格。元native観測にも新Cを用いるためbare byte一致を全条件必須にする。',
        sources=dict(LF_seal_sha256=digest(LF/'artifact-seal.json'),HTS_parent_seal_sha256=digest(PARENT/'artifact-seal.json'),review5_sha256=b.snapshot()['long_horizon']['last_review']['sha256']),
        c_sha256=hashlib.sha256(c.encode()).hexdigest(),vendor_sha256=hashlib.sha256(vendor.encode()).hexdigest(),wrapper_sha256=hashlib.sha256(wrapper.encode()).hexdigest(),worker_sha256=hashlib.sha256(WORKER.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='結合通過時だけ未使用16日本語文のnative/LF比較を出力前登録。失敗したコホートのLF係数/phase/LPF救済をしない。',
        old_consumption_and_all_frozen_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','LF/原HTS混合励振の独立結合と人工全条件費用を出力前登録',reserve_bytes=4000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'shape.c',c.encode(),j);b.write(HERE/'shape_arrays.py',wrapper.encode(),j);b.write(HERE/'worker.py',WORKER.encode(),j)
        b.write(HERE/'vendor/HTS_vocoder_shaped.c',vendor.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h'):b.write(HERE/'vendor'/n,(PARENT/'vendor'/n).read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.write(HERE/'lf_source.c',(LF/'lf_source.c').read_bytes(),j)
        inherited={str(p.relative_to(REPO)):digest(p) for p in [LF/'runtime-bundle/lf_source.py',LF/'runtime-bundle/lf_source.dylib',*[PARENT/'runtime-bundle'/n for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib')]]}
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},inherited_files=inherited,controller_sha256=digest(Path(__file__)),no_waveform_yet=True),j)
    b.save(ROOT/'progress-0105.json',dict(active_campaign=NAME,new_waveforms=0,next='登録push→結合C build→人工8条件の独立LPF混合/原native/因果性',quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_waveforms=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'setup','LF結合Cと原HTS依存を閉じた共有bundleに固定',reserve_bytes=30000000) as j:
        bundle=HERE/'runtime-bundle'
        with b.workspace(j,'LF結合build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',sdk,'-I'+str(HERE/'vendor'),str(HERE/'shape.c'),str(HERE/'lf_source.c'),'-o',str(bundle/'shape.dylib')]
            with b.external_output(bundle/'shape.dylib',200000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,binary_sha256=digest(bundle/'shape.dylib'),temporary_removed=True),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib'):b.write(bundle/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        for n in ('lf_source.py','lf_source.dylib'):b.write(bundle/n,(LF/'runtime-bundle'/n).read_bytes(),j)
        b.write(bundle/'shape_arrays.py',(HERE/'shape_arrays.py').read_bytes(),j);b.write(bundle/'HTS-BSD-NOTICE.txt',(HERE/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={str(p.relative_to(bundle)):digest(p) for p in bundle.rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_waveform_yet=True),j)
    print('LF結合と原依存を科学出力前に固定',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','原native/LF/独立混合/未来差分の人工8条件',56,20000000,expected_seconds=600)
    try:
        d=b.reserve(NAME,'dsp','原clock/noise/入力と独立LPF混合/因果性',96,2000000,expected_seconds=600)
        try:
            with b.workspace(r,'LF結合と独立混合の科学ライブラリ初期化',8000000,16000000) as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'worker.py')],env=env,check=True,capture_output=True,text=True,timeout=540)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','結合機構の限定資格・費用・一時回収を終了封印',reserve_bytes=2000000) as j:
        verify(contract);assert fixture['passed'] and len(fixture['rows'])==8
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,LF_voiced_before_LPF=True,original_native_wave_exact=True,source_clock_and_noise_exact=True,input_streams_exact=True,
            independent_Python_mixed_excitation_verified=True,causal_raw_prefix_exact=True,real_Japanese_speech_qualified=False,antialiasing_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# 固定LFと原HTS混合励振の結合\n\n有声のsqrt(period) impulseだけを連続周期RMS=1の固定LF derivativeへ置換した。元counter/period・noise算法/呼出条件・LPF ring演算・MCP/LF0/LPF/MLSAを保持する。phaseは元counter更新後、period補間前のfmod(counter/period,1)。新しい位相積分器ではなく、時間変動の周期面積0やaliasingを保証しない。\n\n人工8条件(110/280Hz×LPF0/1/31tap、上昇/下降F0×31tap)でbare/native完全一致・源時計/noise/入力完全一致、独立Pythonの周期関数/LPF混合、rawの因果前半、LPF tail終了後の無声励振一致を確認した。56生成/96DSP。未知日本語の内容・固定音素支持・通常隔離/CLI・知覚品質は別契約。\n\nHTS-BSDを保持し、変更した励振を明示する。LFは一次式に基づく独自実装。波形別gain/係数/phaseの選別なし。旧封印/欠測と全凍結保持。P5未開封・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='hts-lf-coupling-completed',active_campaign=None,next='未使用16日本語文のnative/LF比較を出力前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0106.json',dict(latest_completed=NAME,quality_goal_completed=False,next='未使用16日本語文のnative/LF比較を出力前登録',review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,artificial_coupling_only=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
