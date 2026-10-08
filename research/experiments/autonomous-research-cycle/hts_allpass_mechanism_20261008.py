"""LPF後の原励振へ固定オールパスを入れ、振幅と位相を別機構として検証する。"""
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-hts-allpass-mechanism-20261008-v1';NAME='hts-allpass-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1';YIN=ROOT/'campaigns/nas-yin-scope-qualification-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

def make_c():
    text=(PARENT/'shape.c').read_text()
    text=text.replace('static double *period_out,*counter_out,*source_out;', '''static double *period_out,*counter_out,*source_out,*processed_out;
static int phase_mode=0;
static double phase_x=0.,phase_y=0.;
/* 一次オールパス。係数は登録時に固定し、MCPや波形から適応させない。 */
static double phase_step(double x,double *xp,double *yp) {
    double y=.95*(*yp)+(*xp)-.95*x;*xp=x;*yp=y;return y;
}
int phase_filter(const double *x,double *out,size_t n) {
    if(!x||!out||n<1||n>2880000)return 0;
    double xp=0.,yp=0.;
    for(size_t i=0;i<n;i++){if(!isfinite(x[i]))return 0;out[i]=phase_step(x[i],&xp,&yp);if(!isfinite(out[i]))return 0;}
    return 1;
}''')
    text=text.replace('    observed++;return x;', '    double y=phase_mode?phase_step(x,&phase_x,&phase_y):x;\n    if(observed<capacity)processed_out[observed]=y;\n    observed++;return y;')
    text=text.replace('double *counter,double *source,uint8_t *event,size_t samples)', 'double *counter,double *source,double *processed,uint8_t *event,size_t samples)')
    text=text.replace('!counter||!source||!event','!counter||!source||!processed||!event').replace('selected!=0','(selected<0||selected>1)')
    text=text.replace('    observed=0;capacity=samples;', '    phase_mode=selected;phase_x=phase_y=0.;processed_out=processed;\n    observed=0;capacity=samples;')
    text=text.replace('    SHAPE_Vocoder_clear(&v);','    phase_mode=0;phase_x=phase_y=0.;processed_out=NULL;\n    SHAPE_Vocoder_clear(&v);',1)
    text=text.replace('!isfinite(source[i]))','!isfinite(source[i])||!isfinite(processed[i]))')
    return text

WRAPPER=r'''"""原励振の振幅応答を保つ固定位相処理。自然発声のモデルとは呼ばない。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,P,U,S]
_phase=_lib.phase_filter;_phase.restype=C.c_int;_phase.argtypes=[P,P,S]
MODES={'native':0,'allpass':1}
def phase_filter(x):
    a=np.ascontiguousarray(x,dtype=np.float64);out=np.empty_like(a);before=ah(a);assert a.ndim==1
    assert _phase(a.ctypes.data_as(P),out.ctypes.data_as(P),len(a));assert ah(a)==before;return out
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録のオールパス源方式')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);source=np.empty(n);processed=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),source.ctypes.data_as(P),processed.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before and np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    if method=='native':assert np.array_equal(source,processed)
    return out,dict(period=period,counter=counter,original_excitation=source,processed_excitation=processed,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method);audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='原HTS-MLSA/LPF後オールパス',source_method=method,effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(tr['original_excitation']),processed_excitation_sha256=ah(tr['processed_excitation']),
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,original_noise_RNG_LPF_and_sqrt_period_unchanged=True,
        processed_excitation_intentionally_changed=method!='native',source_allpass_pole=.95 if method=='allpass' else None,
        source_phase_rule='y[n]=.95*y[n-1]+x[n-1]-.95*x[n]。発話頭で状態0、全LPF後励振を一度だけ処理。',
        phase_is_frequency_dependent=True,constant_delay_samples_not_defined=True,render_calls_including_internal_MLSA=1,
        infinite_LTI_magnitude_unity_is_not_finite_wave_energy_truth=True,neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
'''

FIXTURE=r'''"""独立再帰・解析応答・tail込みエネルギー・原HTS/源時計を照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'));sys.path.insert(0,sys.argv[1])
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw,phase_filter
from yin_style import estimate
rng=np.random.default_rng(1051051);n=8192;x=np.zeros(n);x[0]=1.;h=phase_filter(x);q=np.exp(-2j*np.pi*np.arange(n//2+1)/n);expected=(q-.95)/(1.-.95*q)
response=np.fft.rfft(h);response_error=float(np.max(np.abs(response-expected)));magnitude_error=float(np.max(np.abs(np.abs(response)-1.)))
assert response_error<=1e-10 and magnitude_error<=1e-10
driving=[]
for mode in ('impulse','noise','step','sine'):
    n=4000
    if mode=='impulse':x=np.zeros(n);x[0]=1.;x[1000]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,n)
    elif mode=='step':x=np.r_[np.zeros(500),np.full(n-500,.1)]
    else:x=.2*np.sin(2*np.pi*220*np.arange(n)/48000.)
    y=phase_filter(x);z=signal.lfilter([-.95,1.],[1.,-.95],x);error=float(np.max(np.abs(y-z)));assert error<=1e-10
    changed=x.copy();changed[2000:]+=1.;future=phase_filter(changed);assert np.array_equal(y[:2000],future[:2000])
    driving.append(dict(mode=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
x=np.r_[rng.normal(0.,.1,2000),np.zeros(8192)];y=phase_filter(x);energy_error=float(abs(np.sum(y*y)-np.sum(x*x))/np.sum(x*x));assert energy_error<=1e-10
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((100,35));mcp[:,0]=7.;mcp[:,1]=.2;lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)];before=[ah(v) for v in params];expected,_=original(params,settings)
    native,tn=raw(params,settings,'native');changed,tc=raw(params,settings,'allpass')
    assert all(np.array_equal(tn[k],tc[k]) for k in ('period','counter','event','original_excitation'))
    assert np.array_equal(tn['original_excitation'],tn['processed_excitation'])
    independent=signal.lfilter([-.95,1.],[1.,-.95],tc['original_excitation']);error=float(np.max(np.abs(tc['processed_excitation']-independent)));assert error<=1e-10
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before and np.isfinite(changed).all()
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_exact=True,all_input_streams_exact=True,original_excitation_and_clock_exact=True,processed_source_max_abs_error=error,passed=True))
pitch=[]
for hz in (80.,110.,160.,220.,280.,350.,400.):
    t=np.arange(19200)/48000.;x=.2*np.sin(2*np.pi*hz*t);y=phase_filter(x)
    for mode,wave in (('original',x),('allpass',y)):
        audio=signal.resample_poly(wave,1,2);out=estimate(audio[-960:]);error=None if out['hz'] is None else float(12*np.log2(out['hz']/hz))
        assert out['hz'] is not None and abs(error)<=.5
        pitch.append(dict(hz=hz,mode=mode,window_ms=40,steady_last_window=True,error_semitones=error,passed=True))
print(json.dumps(dict(passed=True,response_absolute_error=response_error,magnitude_absolute_error=magnitude_error,tail_included_energy_relative_error=energy_error,
    driving_checks=driving,source_checks=source_checks,pitch_checks=pitch,render=60,dsp=33,
    render_breakdown=dict(response_driver=1,response_filter=1,driving_signals=4,C_driving_filter=4,independent_driving_filter=4,causal_driving_filter=4,energy_driver=1,energy_filter=1,original_HTS=4,native_HTS=4,allpass_HTS=4,sine_driver=7,sine_phase_filter=7,sine_resample=14),
    dsp_breakdown=dict(response=2,driving=8,energy=1,HTS_clock_and_processed_source=8,sine_pitch=14),
    scope='固定LTI機構と登録人工HTS/定常正弦。実日本語/全音素/境界/知覚品質の資格ではない。',quality_certified=False)))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];assert read(YIN/'aggregate-summary.json')['domains']['static']['40']['all_required_pass']
    c=make_c();ast.parse(WRAPPER);ast.parse(FIXTURE)
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=10,audit=10,render=180,dsp=99,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='振幅整形と分離した固定LTIオールパス位相因子を、原HTSの源時計/原励振/全MCPを保持して独立検証できるか。',
        factor='LPF後の全励振xにpole=.95の一次オールパス y=.95*y_prev+x_prev-.95*x。noiseとperiodicの両成分を処理。元源を一回だけ呼ぶ。',
        controls='alpha.55/beta0/volume1/sqrt(period)/LF0/LPF/MCPと時計・乱数算法は原HTS。候補の実処理励振は意図した差分。発話頭で状態0。係数探索なし。',
        thresholds=dict(response_absolute=1e-10,magnitude_absolute=1e-10,independent_recurrence_absolute=1e-10,tail_included_energy_relative=1e-10,native_wave_exact=True,source_clock_and_original_source_exact=True,causal_prefix_exact=True,sine_pitch_error_semitones=.5),
        interpretation='振幅1/エネルギー保存は無限LTIの性質。有限音声端/tail truncation、原MLSA非定常出力、自然声やLF glottalの再現とは呼ばない。一定遅延ではない。',
        costs=dict(render=60,dsp=33,maximum_seconds=3000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
        source=dict(url='https://ccrma.stanford.edu/~jos/filters/Allpass_Filters.html',title='Julius O. Smith, Introduction to Digital Filters with Audio Applications, Allpass Filters',scope='安定因果LTIの振幅/エネルギー性質の一次解説。音声自然さは推論しない。',original_HTS_parent_seal_sha256=digest(PARENT/'artifact-seal.json'),YIN_seal_sha256=digest(YIN/'artifact-seal.json')),
        c_sha256=hashlib.sha256(c.encode()).hexdigest(),wrapper_sha256=hashlib.sha256(WRAPPER.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='機構通過時に未使用16文のnative/allpassを出力前登録し二ASR/固定支持/通常隔離で実比較。FIR救済へ戻らない。',
        old_FIR_and_glottal_shape_and_fractional_failed_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','励振の固定オールパス因子と全機構費を出力前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'shape.c',c.encode(),j);b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):b.write(HERE/'vendor'/n,(PARENT/'vendor'/n).read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0081.json',dict(active_campaign=NAME,next=reg['next'],new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)

def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'source-contract.json');assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    with b.job(NAME,'setup','位相因子Cのbuildと閉じた共有機構bundle',reserve_bytes=30000000) as j:
        with b.workspace(j,'オールパスbuild専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',sdk,'-I'+str(HERE/'vendor'),str(HERE/'shape.c'),'-o',str(HERE/'shape.dylib')]
            with b.external_output(HERE/'shape.dylib',200000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'shape.c'),binary_sha256=digest(HERE/'shape.dylib'),temporary_removed=True),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib'):b.write(HERE/'runtime-bundle'/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        for n in ('shape_arrays.py','shape.dylib'):b.write(HERE/'runtime-bundle'/n,(HERE/n).read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={str(p.relative_to(HERE/'runtime-bundle')):digest(p) for p in (HERE/'runtime-bundle').rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('固定オールパスをbuildし閉じたbundleを登録',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    r=b.reserve(NAME,'render','オールパスの全駆動源・原HTS・定常正弦生成',60,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','解析応答・独立再帰・原源時計・限定正弦pitch検証',33,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'位相因子fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py'),str(YIN)],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','機構範囲・原HTS対照・費用・一時回収の終了照合',reserve_bytes=2000000) as j:
        assert fixture['passed'] and sum(fixture['render_breakdown'].values())==60 and sum(fixture['dsp_breakdown'].values())==33
        for n,h in contract['files'].items():assert digest(HERE/n)==h,n
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,source_pole=.95,source_clock_and_original_excitation_exact=True,processed_excitation_intentionally_changed=True,original_native_wave_exact=True,causal_prefix_exact=True,real_Japanese_speech_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# LPF後励振の固定オールパス位相因子\n\n解析応答、4駆動源の独立再帰/因果性、tail込みエネルギー、4HTS条件の原native完全一致・原励振/時計/入力列不変、7周波数の定常正弦×2条件40ms測定を照合した。候補の実処理励振は意図して変わり、noiseもperiodicもLPF後に一回だけ処理する。\n\npole=.95は固定設計値。安定LTIの振幅1を非定常MLSA出力や有限音声のエネルギー保存へ広げず、一定遅延や自然glottalモデルとも呼ばない。前のFIR/shape/fractional不通過経路と旧判定は保持する。\n\n未知日本語・音素支持・二ASR・知覚は次の別契約。P5未開封・品質未達。\n\n一次資料: [Julius O. Smith, Allpass Filters](https://ccrma.stanford.edu/~jos/filters/Allpass_Filters.html)。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='allpass-mechanism-completed',active_campaign=None,next='未使用16文のnative/allpass源位相比較を生成前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0082.json',dict(latest_completed=NAME,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
