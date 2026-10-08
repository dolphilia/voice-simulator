"""MCPの全極射影と反射係数補間を、FIRとは異なる因果機構として検証する。"""
import ast,hashlib,json,os,subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-lattice-mechanism-20261008-v1'
NAME='hts-lattice-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-allpass-mechanism-20261008-v1'
PREVIOUS=ROOT/'campaigns/nas-hts-output-bound-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

C_SOURCE=r'''/* 独自の全極合成lattice。前frameからの反射係数/対数gainを標本ごとに補間する。 */
#include <math.h>
#include <stddef.h>
int lattice_filter(const double *k,const double *logg,const double *x,double *y,
                   size_t frames,size_t order,size_t samples) {
    if(!k||!logg||!x||!y||frames<1||frames>6000||order<1||order>34||samples!=frames*240)return 0;
    for(size_t f=0;f<frames;f++){
        if(!isfinite(logg[f])||fabs(logg[f])>100.)return 0;
        for(size_t m=0;m<order;m++)if(!isfinite(k[f*order+m])||fabs(k[f*order+m])>=.99999999)return 0;
    }
    for(size_t i=0;i<samples;i++)if(!isfinite(x[i]))return 0;
    double state[34]={0};
    for(size_t f=0;f<frames;f++){
        size_t p=f?f-1:0;
        for(size_t j=0;j<240;j++){
            double u=(double)j/240.;
            double v=x[f*240+j]*exp(logg[p]+u*(logg[f]-logg[p]));
            for(size_t m=order;m>0;m--){
                double r=k[p*order+m-1]+u*(k[f*order+m-1]-k[p*order+m-1]);
                v-=r*state[m-1];
                if(m<order)state[m]=r*v+state[m-1];
            }
            state[0]=v;y[f*240+j]=v;
            if(!isfinite(v))return 0;
        }
    }
    return 1;
}
'''

MODULE=r'''"""現MCPから自己相関/Yule-Walker係数を計算する。保存波形の推定は使わない。"""
import ctypes as C
import numpy as np
from pathlib import Path
from scipy import signal
from hts_arrays import ah
from shape_arrays import raw
ORDER=34
FFT_LENGTH=16384
_q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
_lib=C.CDLL(str(Path(__file__).resolve().parent/'lattice.dylib'))
P=C.POINTER(C.c_double);S=C.c_size_t
_fn=_lib.lattice_filter;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,P,S,S,S]
def response(mc,alpha=.55):
    x=np.asarray(mc,dtype=np.float64)
    if x.shape!=(35,) or not np.isfinite(x).all() or abs(alpha)>=1.:raise ValueError('有限MCPと安定warpが必要')
    w=(_q-alpha)/(1.-alpha*_q);h=np.exp(np.polynomial.polynomial.polyval(w,x))
    if not np.isfinite(h).all():raise ValueError('MCP応答が非有限')
    return h
def levinson(r):
    x=np.asarray(r,dtype=np.float64)
    if x.ndim!=1 or len(x)<2 or len(x)>35 or not np.isfinite(x).all() or x[0]<=0:raise ValueError('正の有限自己相関が必要')
    rr=x/x[0];a=np.zeros(len(x));a[0]=1.;e=1.;k=np.empty(len(x)-1)
    for m in range(1,len(x)):
        v=-(rr[m]+np.dot(a[1:m],rr[m-1:0:-1]))/e
        if not np.isfinite(v) or abs(v)>=.99999999:raise ValueError('射影反射係数が登録安定域外')
        old=a[1:m].copy();a[1:m]=old+v*old[::-1];a[m]=v;k[m-1]=v;e*=1.-v*v
        if not np.isfinite(e) or e<=0:raise ValueError('予測誤差が非正')
    return a,k,float(np.sqrt(e*x[0]))
def project(mc,alpha=.55):
    h=response(mc,alpha);r=np.fft.irfft(np.abs(h)**2,n=FFT_LENGTH)[:ORDER+1].copy()
    a,k,g=levinson(r)
    return a,k,g,r
def polynomial(k):
    a=np.array([1.])
    for v in np.asarray(k,dtype=np.float64):a=np.r_[a,0.]+v*np.r_[0.,a[::-1]]
    return a
def filter_coefficients(k,logg,source):
    p=np.ascontiguousarray(k,dtype=np.float64);g=np.ascontiguousarray(logg,dtype=np.float64);x=np.ascontiguousarray(source,dtype=np.float64)
    if p.ndim!=2 or not 1<=p.shape[1]<=34 or g.shape!=(len(p),) or x.shape!=(len(p)*240,):raise ValueError('lattice列と駆動列の形が不正')
    before=(ah(p),ah(g),ah(x));y=np.empty_like(x)
    if not _fn(p.ctypes.data_as(P),g.ctypes.data_as(P),x.ctypes.data_as(P),y.ctypes.data_as(P),len(p),p.shape[1],len(x)):raise ValueError('lattice生成が登録安定域外または非有限')
    assert before==(ah(p),ah(g),ah(x));return y
def filter_source(mc,source):
    m=np.asarray(mc,dtype=np.float64);before=ah(m)
    projected=[project(c) for c in m];k=np.array([v[1] for v in projected]);g=np.log([v[2] for v in projected])
    y=filter_coefficients(k,g,source);assert ah(m)==before
    return y
def synthesize(params,settings,method):
    if method not in ('native','lattice'):raise ValueError('未登録の全極方式')
    native,tr=raw(params,settings,'native');out=native if method=='native' else filter_source(params[0],tr['original_excitation'])
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='原HTS-MLSA' if method=='native' else 'MCP自己相関→全極lattice',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},original_excitation_sha256=ah(tr['original_excitation']),
        processed_excitation_sha256=ah(tr['processed_excitation']),original_excitation_and_processed_excitation_equal=True,
        cycle_events=int(tr['event'].sum()),lattice_order=ORDER if method!='native' else None,
        FFT_length=FFT_LENGTH if method!='native' else None,loading_or_coefficient_clipping=False,
        interpolation='反射係数の算術補間、対数gainの算術補間。前frameからj/240。発話頭state0。',
        extra_delay_samples=0,projection_is_not_exact_MLSA_or_acoustic_truth=True,
        render_calls_including_internal_MLSA=1 if method=='native' else 2,
        neural_model=False,utterance_lookup=False,saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
'''

FIXTURE=r'''"""既知全極系、独立Toeplitz解、標準直接形、動的解析の逆写像を確認する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal,linalg
from hts_arrays import synthesize as original,ah
from lattice import response,project,polynomial,filter_coefficients,synthesize,ORDER,FFT_LENGTH
rng=np.random.default_rng(1055055);q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
cases=[[],[.2],[.5],[-.3,.3],[.45+.2j,.45-.2j],[.5*np.exp(.7j),.5*np.exp(-.7j)],
 [.45*np.exp(.3j),.45*np.exp(-.3j),.35*np.exp(1.4j),.35*np.exp(-1.4j)],[-.25,.35,.2+.2j,.2-.2j]]
spectral=[]
for index,poles in enumerate(cases):
 for alpha in (0.,.55):
    poles=np.array(poles,dtype=np.complex128);gain=1.3
    mc=np.zeros(35);mc[0]=np.real(np.log(gain)-np.log(1.-alpha*poles).sum())
    w=(poles-alpha)/(1.-alpha*poles)
    for m in range(1,35):mc[m]=np.real((np.sum(w**m)+len(poles)*(-1)**(m+1)*alpha**m)/m)
    known_polynomial=np.atleast_1d(np.poly(poles).real)
    h=response(mc,alpha);exact=gain/np.polynomial.polynomial.polyval(q,known_polynomial)
    herr=float(np.max(np.abs(h-exact))/max(np.max(np.abs(exact)),1e-12));assert herr<=1e-8
    a,k,g,r=project(mc,alpha);dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[:-1]/r[0]),-r[1:]/r[0])]
    independent=float(np.max(np.abs(a-dense)));known=np.pad(known_polynomial,(0,35-len(poles)-1));knownerr=float(np.max(np.abs(a-known)))
    gainerr=abs(g-gain);assert independent<=1e-10 and knownerr<=1e-7 and gainerr<=1e-7
    assert np.max(np.abs(np.roots(polynomial(k))))<1. and np.max(np.abs(a-polynomial(k)))<=1e-10
    spectral.append(dict(case=index,alpha=alpha,known_response_relative_error=herr,dense_coefficient_max_abs_error=independent,known_coefficient_max_abs_error=knownerr,known_gain_error=gainerr,passed=True))
static=[]
ks=[np.array([.3]),np.array([-.4,.25]),np.array([-.35,.2,-.1,.05])]
drivers={};n=4800
for mode in ('impulse','noise','step','sine'):
    if mode=='impulse':x=np.zeros(n);x[0]=1.;x[1000]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,n)
    elif mode=='step':x=np.r_[np.zeros(600),np.full(n-600,.1)]
    else:x=.2*np.sin(2*np.pi*220*np.arange(n)/48000.)
    drivers[mode]=x
    for k in ks:
        coeff=np.tile(k,(20,1));logg=np.full(20,np.log(1.3));y=filter_coefficients(coeff,logg,x);z=signal.lfilter([1.3],polynomial(k),x)
        err=float(np.max(np.abs(y-z)));assert err<=1e-10
        future=x.copy();future[2400:]+=1.;yp=filter_coefficients(coeff,logg,future);assert np.array_equal(y[:2400],yp[:2400])
        static.append(dict(mode=mode,order=len(k),direct_form_max_abs_error=err,causal_prefix_exact=True,passed=True))
frames=20;k=rng.normal(0.,.025,(frames,34));k[:,0]=np.linspace(-.4,.4,frames);logg=np.linspace(np.log(.5),np.log(1.5),frames)
roots=[]
for row in k:
    radius=float(np.max(np.abs(np.roots(polynomial(row)))));assert radius<1.;roots.append(radius)
dynamic=[]
for mode in ('noise','sine'):
    x=rng.normal(0.,.1,n) if mode=='noise' else .2*np.sin(2*np.pi*280*np.arange(n)/48000.)
    y=filter_coefficients(k,logg,x);states=np.zeros(34);reconstructed=np.empty(n)
    # 合成の降順再帰と異なる昇順解析latticeで源を復元する。
    for t,value in enumerate(y):
        f=t//240;j=t%240;p=max(0,f-1);u=j/240.;r=k[p]+u*(k[f]-k[p]);old=states.copy();states[0]=value;forward=value
        for m in range(34):
            prior=forward;forward=prior+r[m]*old[m]
            if m<33:states[m+1]=r[m]*prior+old[m]
        reconstructed[t]=forward/np.exp(logg[p]+u*(logg[f]-logg[p]))
    err=float(np.max(np.abs(reconstructed-x)));assert err<=1e-10
    future=x.copy();future[2400:]+=1.;yp=filter_coefficients(k,logg,future);assert np.array_equal(y[:2400],yp[:2400])
    dynamic.append(dict(mode=mode,analysis_inverse_max_abs_error=err,causal_prefix_exact=True,finite_registered_trajectory=True,passed=True))
artificial=[]
for i in range(8):
    mc=np.zeros(35);mc[0]=.2*i;mc[1:]=rng.normal(0.,.03,34)*np.exp(-np.arange(1,35)/12.)
    a,k,g,r=project(mc);dense=np.r_[1.,np.linalg.solve(linalg.toeplitz(r[:-1]/r[0]),-r[1:]/r[0])]
    err=float(np.max(np.abs(a-dense)));radius=float(np.max(np.abs(np.roots(a))));assert err<=1e-10 and radius<1.
    h=response(mc);approx=g/np.polynomial.polynomial.polyval(q,a);rms=float(np.sqrt(np.mean((20*np.log10(np.abs(approx)/np.abs(h)))**2)))
    artificial.append(dict(case=i,dense_coefficient_error=err,root_radius=radius,finite_grid_log_magnitude_RMSE_dB=rms,approximation_error_is_not_exact_reproduction=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
sources=[]
for hz in (110.,280.):
 for lpf in (0.,1.):
    mc=np.zeros((20,35));mc[:,0]=5.;mc[:,1]=np.linspace(.1,.2,20);mc[:,2]=.05
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mc,lf0,np.full((20,1),lpf)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,nm=synthesize(params,settings,'native');candidate,cm=synthesize(params,settings,'lattice')
    assert np.array_equal(expected,native) and [ah(v) for v in params]==before
    assert nm['source_clock_hashes']==cm['source_clock_hashes'] and nm['original_excitation_sha256']==cm['original_excitation_sha256'] and nm['processed_excitation_sha256']==cm['processed_excitation_sha256']
    assert np.isfinite(candidate).all()
    sources.append(dict(hz=hz,lpf=lpf,native_exact=True,all_input_streams_and_original_source_clock_exact=True,candidate_finite=True,frames_projected=20,passed=True))
print(json.dumps(dict(passed=True,known_AR_checks=spectral,static_driving_checks=static,dynamic_checks=dynamic,instantaneous_registered_root_radii=roots,artificial_MCP_checks=artificial,HTS_checks=sources,
    order=34,FFT_length=16384,render=62,dsp=232,
    render_breakdown=dict(driving_signals=4,static_C=12,static_direct_form=12,static_causal=12,dynamic_drivers=2,dynamic_C=2,dynamic_causal=2,original_HTS=4,native_HTS=4,candidate_HTS_helper=4,candidate_lattice=4),
    dsp_breakdown=dict(known_AR_projection=16,known_AR_independent=16,known_AR_response_and_gain=16,known_AR_stability=16,static_direct_form=12,static_causality=12,dynamic_inverse=2,dynamic_causality=2,dynamic_instantaneous_roots=20,artificial_MCP_projection=8,artificial_MCP_independent=8,artificial_MCP_grid=8,artificial_MCP_stability=8,HTS_frame_projection=80,HTS_native_exact=4,HTS_source_clock=4),
    scope='登録人工全極系/MCPの射影と有限動的latticeのみ。実HTS全frameの射影損失、未知日本語/短窓pitch/知覚は別。',
    time_varying_global_stability_proven=False,exact_MCP_or_MLSA_reproduction_claimed=False,quality_certified=False)))
'''

def verify(contract):
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due'];assert read(PREVIOUS/'aggregate-summary.json')['total']==64
    ast.parse(MODULE);ast.parse(FIXTURE)
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=10,audit=10,render=186,dsp=696,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='MCPの有限power gridから全極/Yule-Walkerへ射影し、反射係数と対数gainを因果latticeで時間補間する別の声道表現を独立検証できるか。',
        factor='alpha.55の解析MCP応答→16384点power逆FFTの自己相関r0..r34→正規化Levinson-Durbin→order34反射係数とsqrt予測誤差gain。前/currentをj/240補間。',
        controls='原MCP/LF0/LPF/励振と時計不変、candidateは原HTS helperの源を別filterへ渡す。state0、追加delay0、係数clip/diagonal loading/波形gain救済なし。最終非ニューラル。',
        thresholds=dict(known_AR_response_relative=1e-8,known_AR_coefficients_and_gain=1e-7,dense_coefficient_absolute=1e-10,static_direct_form_absolute=1e-10,dynamic_analysis_inverse_absolute=1e-10,
            causal_prefix_exact=True,native_exact=True,source_clock_and_all_parameters_exact=True,reflection_abs_below=.99999999,registered_instantaneous_roots_below=1.),
        interpretation='全極射影は一般MCP/MLSAの厳密再現ではない。瞬時係数の安定や有限人工動的trajectoryを任意時間変動の一様安定/自然さへ拡張しない。FIR係数救済でもない。',
        costs=dict(render=62,dsp=232,maximum_seconds=3000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8),limits=limits,
        sources=dict(urls=['https://sp-nitech.github.io/sptk/latest/main/levdur.html','https://sp-nitech.github.io/sptk/latest/main/par2lpc.html','https://sp-nitech.github.io/sptk/latest/main/poledf.html'],
            implementation='一次式を読んだ独自C/Python実装。SPTKソースやlibraryは取得/コピーしていない。',native_parent_seal_sha256=digest(PARENT/'artifact-seal.json'),previous_seal_sha256=digest(PREVIOUS/'artifact-seal.json')),
        c_sha256=hashlib.sha256(C_SOURCE.encode()).hexdigest(),module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='科学24件の定期レビュー後、保存済み新native全MCP frameで射影損失/安定性を別登録して確認。許容域を守る場合だけ新日本語の比較一式を登録。',
        old_allpass_output_bound_FIR_and_all_frozen_routes_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','全極射影とlatticeの独立機構・全費用を生成前登録',reserve_bytes=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'lattice.c',C_SOURCE.encode(),j);b.write(HERE/'lattice.py',MODULE.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        b.save(HERE/'source-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0089.json',dict(active_campaign=NAME,new_scientific_outputs=0,next=reg['next'],quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)
def prepare():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];verify(read(HERE/'source-contract.json'))
    with b.job(NAME,'setup','独自lattice Cのbuildと原HTS共有bundle固定',reserve_bytes=30000000) as j:
        with b.workspace(j,'lattice buildの専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules');tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang';sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-isysroot',sdk,str(HERE/'lattice.c'),'-o',str(HERE/'lattice.dylib')]
            with b.external_output(HERE/'lattice.dylib',100000,j):out=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=out.stderr,source_sha256=digest(HERE/'lattice.c'),binary_sha256=digest(HERE/'lattice.dylib'),temporary_removed=True),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib','shape_arrays.py','shape.dylib'):b.write(HERE/'runtime-bundle'/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        for n in ('lattice.py','lattice.dylib'):b.write(HERE/'runtime-bundle'/n,(HERE/n).read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={str(p.relative_to(HERE/'runtime-bundle')):digest(p) for p in (HERE/'runtime-bundle').rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    print('全極latticeをbuildし、人工出力前の共有bundleを固定',flush=True)
def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','全極latticeの人工駆動源・独立直接形・原HTS全生成',62,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','独立Toeplitz・既知AR・動的逆写像・安定域・原源照合',232,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'lattice fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','全極射影の範囲・全費用・hash・一時回収の終了照合',reserve_bytes=2000000) as j:
        assert fixture['passed'] and sum(fixture['render_breakdown'].values())==62 and sum(fixture['dsp_breakdown'].values())==232;verify(contract)
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,lattice_order=34,FFT_length=16384,original_native_wave_exact=True,source_clock_and_all_input_parameters_exact=True,causal_prefix_exact=True,known_AR_and_independent_Toeplitz_verified=True,finite_dynamic_analysis_inverse_verified=True,
            global_time_varying_stability_proven=False,real_HTS_MCP_projection_qualified=False,real_Japanese_speech_qualified=False,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# MCPの全極射影と因果lattice\n\n解析MCP powerの16384点逆FFTから自己相関r0..r34を計算し、Levinson-Durbinでorder34の反射係数/予測誤差gainへ射影する。原励振を因果latticeへ渡し、前frame/currentの反射係数と対数gainをj/240で補間する。係数clipやloading、波形からのgain推定はしない。\n\n既知8全極系×alpha0/.55の応答・独立密Toeplitz・既知係数/gain・根、4駆動源×3次数の独立標準形/因果性、有限動的34次の昇順解析逆写像、8人工MCPの射影、4HTS原native/パラメータ/源時計を確認した。\n\n一般MCPやMLSAの厳密再現、任意の時間変動の一様安定、自然声の資格ではない。FIRの有限IR/補間を救済する処理とも区別する。次は科学24件のレビュー後、保存済み新native全MCP frameの射影損失/安定性を別契約で確認する。日本語知覚資格なし・P5未開封・品質未達。\n\n一次資料: [SPTK levdur](https://sp-nitech.github.io/sptk/latest/main/levdur.html)、[par2lpc](https://sp-nitech.github.io/sptk/latest/main/par2lpc.html)、[poledf](https://sp-nitech.github.io/sptk/latest/main/poledf.html)。ソース/libraryの取得・コピーは行っていない。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME];assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True,internal_HTS_helpers_counted=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='lattice-mechanism-completed',active_campaign=None,next='科学24件レビュー後に全実MCP射影の独立資格',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0090.json',dict(latest_completed=NAME,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,quality_goal_completed=False),flush=True)
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture']);a=p.parse_args();{'register':register,'prepare':prepare,'fixture':run}[a.stage]()
