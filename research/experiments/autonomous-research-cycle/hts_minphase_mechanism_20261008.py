"""原HTS励振からの最小位相FIR経路を、解析式と独立畳み込みで資格限定する。"""
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1'
NAME='hts-minphase-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-lf0-contour-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
KERNEL=1024

APPEND_C=r'''
/* MCPの周波数変換と最小位相IR。alphaは通常.55、fixtureで0も照合。 */
int shape_kernel(const double *mc,double alpha,double *h,size_t length) {
    if(!mc||!h||length!=1024||!isfinite(alpha)||fabs(alpha)>=1.)return 0;
    for(size_t k=0;k<35;k++)if(!isfinite(mc[k]))return 0;
    HTS_Vocoder v;double cep[1024];
    SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    HTS_freqt(&v,mc,34,cep,1023,-alpha);
    HTS_c2ir(cep,1024,h,1024);
    SHAPE_Vocoder_clear(&v);
    for(size_t k=0;k<1024;k++)if(!isfinite(h[k]))return 0;
    return 1;
}
/* 出力時刻のIRを前frameから線形補間し、過去の励振だけを参照する。 */
int shape_fir(const double *mc,const double *source,size_t frames,double *out) {
    if(!mc||!source||!out||frames<1||frames>6000)return 0;
    double previous[1024],current[1024];
    if(!shape_kernel(mc,.55,previous,1024))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!shape_kernel(mc+35*f,.55,current,1024))return 0;
        for(size_t j=0;j<240;j++) {
            size_t n=f*240+j,maximum=n<1023?n:1023;
            double u=(double)j/240.,y=0.;
            for(size_t k=0;k<=maximum;k++) {
                double h=previous[k]+u*(current[k]-previous[k]);
                y+=h*source[n-k];
            }
            if(!isfinite(y))return 0;
            out[n]=y;
        }
        memcpy(previous,current,sizeof(previous));
    }
    return 1;
}
'''

WRAPPER=r'''"""保存列を使わず、その入力のMCPとHTS励振から因果FIRを計算する。"""
import ctypes as C
from pathlib import Path
import numpy as np
from hts_arrays import ah
from shape_arrays import raw
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);S=C.c_size_t
_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[P,C.c_double,P,S]
_fir=_lib.shape_fir;_fir.restype=C.c_int;_fir.argtypes=[P,P,S,P]
def kernel(mc,alpha=.55):
    a=np.ascontiguousarray(mc,dtype=np.float64);assert a.shape==(35,)
    h=np.empty(1024);assert _kernel(a.ctypes.data_as(P),alpha,h.ctypes.data_as(P),1024)
    return h
def filter_source(mc,source):
    a=np.ascontiguousarray(mc,dtype=np.float64);x=np.ascontiguousarray(source,dtype=np.float64)
    assert a.ndim==2 and a.shape[1]==35 and x.shape==(len(a)*240,) and np.isfinite(x).all()
    before=(ah(a),ah(x));out=np.empty(len(x))
    assert _fir(a.ctypes.data_as(P),x.ctypes.data_as(P),len(a),out.ctypes.data_as(P))
    assert (ah(a),ah(x))==before
    return out
def fir_raw(params,settings):
    # 原MLSA出力も内部で一回生成される。この費用をrenderへ別計上する。
    native,tr=raw(params,settings,'native')
    out=filter_source(params[0],tr['excitation'])
    return out,tr,native
'''

FIXTURE=r'''"""人工条件の有限IR・因果性・時間補間だけを検証し、知覚資格と区別する。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from minphase import kernel,filter_source,fir_raw
rng=np.random.default_rng(1042042)
mc=np.zeros((8,35));mc[:,0]=np.linspace(0.,1.,8)
mc[1,1]=.3;mc[2,2]=-.25;mc[3,1:4]=[.35,.15,.12]
mc[4:,1:]=rng.normal(0.,.04,(4,34))*np.exp(-np.arange(1,35)/12.)
spectral=[];N=8192;q=np.exp(-2j*np.pi*np.arange(N//2+1)/N)
for index,c in enumerate(mc):
 for alpha in (0.,.55):
    a=(q-alpha)/(1.-alpha*q)
    target=np.exp(np.polynomial.polynomial.polyval(a,c))
    h=kernel(c,alpha);reference=np.fft.irfft(target,n=N)
    # 全複素応答と因果prefixを別検査。声の自然さや実MCPの資格にはしない。
    absolute=float(np.max(np.abs(h-reference[:1024])))
    relative=float(np.max(np.abs(np.fft.rfft(h,n=N)-target)/np.maximum(np.abs(target),1e-12)))
    tail=float(np.sum(reference[1024:]**2)/np.sum(reference**2))
    assert absolute<=1e-10 and relative<=1e-8 and tail<=1e-14
    spectral.append(dict(case=index,alpha=alpha,kernel_prefix_max_abs_error=absolute,complex_response_max_relative_error=relative,tail_energy_fraction=tail,passed=True))

def independent(mc,source):
    # Cのsampleループを写さず、静的畳み込み二本の出力をcrossfadeする。
    h=[kernel(c) for c in mc];out=np.empty(len(source));u=np.arange(240)/240.
    for frame,current in enumerate(h):
        previous=h[max(0,frame-1)];start=frame*240;stop=start+240
        p=signal.convolve(source,previous,method='direct')[start:stop]
        z=signal.convolve(source,current,method='direct')[start:stop]
        out[start:stop]=p+u*(z-p)
    return out

convolution=[]
for mode in ('impulse','noise','step','zeros'):
    frames=8;p=np.zeros((frames,35));p[:,0]=np.linspace(.1,.4,frames);p[:,1]=np.linspace(.1,.35,frames)
    if mode=='impulse':x=np.zeros(frames*240);x[0]=1.;x[720]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,frames*240)
    elif mode=='step':x=np.r_[np.zeros(600),np.ones(frames*240-600)*.1]
    else:x=np.zeros(frames*240)
    y=filter_source(p,x);z=independent(p,x);error=float(np.max(np.abs(y-z)))
    assert error<=1e-11 and (mode!='zeros' or np.array_equal(y,x))
    prefix=x.copy();prefix[960:]+=1.;yp=filter_source(p,prefix)
    assert np.array_equal(y[:960],yp[:960])
    convolution.append(dict(source=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))

settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((20,35));mcp[:,0]=5.;mcp[:,1]=np.linspace(.1,.35,20);mcp[:,2]=.15
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz)
    params=[mcp,lf0,np.full((20,1),coefficient)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,tr=raw(params,settings,'native')
    # fir_raw内部の余分なMLSAを避け、既存の励振をそのままFIRへ渡す。
    out=filter_source(mcp,tr['excitation'])
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before and np.isfinite(out).all()
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_wave_exact=True,input_streams_exact=True,
        source_sha256=ah(tr['excitation']),clock_hashes={k:ah(v) for k,v in tr.items()},FIR_wave_changed=not np.array_equal(out,native),passed=True))
assert len(spectral)==16 and len(convolution)==4 and len(source_checks)==4
print(json.dumps(dict(passed=True,spectral_checks=spectral,convolution_checks=convolution,source_checks=source_checks,
    render=60,dsp=64,render_breakdown=dict(C_kernel=16,independent_FFT_kernel=16,driving_signal=4,C_FIR=12,independent_convolution=4,original_HTS=4,observed_HTS=4),
    scope='登録した人工MCPのみ。実日本語MCPのtail・指定F0・内容・知覚は未検証。',
    finite_IR_length=1024,IR_interpolation='出力時刻の前frame/current IRをj/240で補間。MLSAのb係数補間と同一とは呼ばない。',
    extra_latency_samples=0,causal_past_only=True,quality_certified=False,perceptual_qualification=False)))
'''

def values():
    tree=ast.parse((ROOT/'hts_lf0_contour_20261008.py').read_text())
    def value(name):return ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets)))
    c=value('C_SOURCE').replace('原励振を一度だけ呼び、フィルタのalphaだけを変更する別版。','原HTSを純観測し、その励振に独立の最小位相FIRを適用する別版。')
    return c+APPEND_C,value('WRAPPER')

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=12,audit=12,render=180,dsp=192,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='Pade-MLSAとは別のMCP→最小位相因果FIR経路を、解析複素応答・独立畳み込み・原HTS励振で検証できるか。',
        finite_IR=1024,alpha=.55,cepstral_order=1023,MCP=35,frame=240,sample_rate=48000,
        interpolation='出力時刻のIRを前frame→currentでj/240補間。過去の励振だけを参照。MLSAのb補間との差も新経路の仕様。',
        source='原HTS pulse/noise/LPFを一回ずつ観測。原MLSAの内部生成もrenderへ別計上。',
        citations=['https://sp-nitech.github.io/sptk/latest/main/freqt.html','https://sp-nitech.github.io/sptk/latest/main/c2mpir.html'],
        fixture=dict(MCP_cases=8,alphas=[0.,.55],FFT=8192,complex_relative_error=1e-8,prefix_absolute_error=1e-10,tail_energy=1e-14,convolution_absolute_error=1e-11,original_wave_exact=True,render=60,dsp=64),
        limits=limits,max_expected_seconds=3000,external_temporary_peak=16000000,external_temporary_write=32000000,
        controller_sha256=digest(Path(__file__)),parent_source_sha256=digest(ROOT/'hts_lf0_contour_20261008.py'),
        next_if_pass='別契約の新日本語入力で原nativeとの全件生成/隔離/CLI/二ASRを比較。実MCPごとのtail/応答誤差を欠測を除外せず記録。',
        fixture_is_not_general_pitch_or_perception_truth=True,old_results_unchanged=True,quality_goal_completed=False,protected_confirmation_opened=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','最小位相FIRの機構契約とソースの生成前固定',reserve_bytes=16000000) as j:
        c,wrapper=values();b.save(HERE/'registration.json',reg,j)
        for name,data in [('shape.c',c),('shape_arrays.py',wrapper),('minphase.py',WRAPPER),('fixture.py',FIXTURE)]:b.write(HERE/name,data.encode(),j)
        for name in ('HTS_hidden.h','HTS_engine.h','HTS_vocoder_shaped.c'):b.write(HERE/'vendor'/name,(PARENT/'vendor'/name).read_bytes(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_output=True),j)
    with b.job(NAME,'setup','最小位相C実装のbuildと閉じた機構bundle',reserve_bytes=30000000) as j:
        with b.workspace(j,'最小位相build専用cache',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang'
            sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',sdk,'-I'+str(HERE/'vendor'),str(HERE/'shape.c'),'-o',str(HERE/'shape.dylib')]
            with b.external_output(HERE/'shape.dylib',200000,j):r=subprocess.run(cmd,env=env,check=True,capture_output=True,text=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,stderr=r.stderr,source_sha256=digest(HERE/'shape.c'),binary_sha256=digest(HERE/'shape.dylib'),temporary_removed=True),j)
        mapping={n:HERE/n for n in ('shape_arrays.py','shape.dylib','minphase.py')}
        for n in ('hts_arrays.py','hts_arrays.dylib'):mapping[n]=PARENT/'runtime-bundle'/n
        for n,p in mapping.items():b.write(HERE/'runtime-bundle'/n,p.read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={n:digest(HERE/'runtime-bundle'/n) for n in mapping},final_neural_inference=False,utterance_tables=0),j)
        b.save(HERE/'execution-contract.json',dict(source_files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},registration_sha256=digest(HERE/'registration.json'),controller_sha256=digest(Path(__file__)),no_scientific_outputs_yet=True),j)
    b.save(ROOT/'progress-0063.json',dict(active_campaign=NAME,quality_goal_completed=False,new_scientific_outputs=0,next='登録commit/push→機構fixture→全照合/封印→科学12件の定期レビュー→日本語生成比較',budget=b.reconcile()))
    print('最小位相FIRの初回機構出力前登録を完了',flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    contract=read(HERE/'execution-contract.json');assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['source_files'].items():assert digest(HERE/n)==h,n
    with b.job(NAME,'render','人工最小位相IR・駆動源・原HTS・FIRの全生成',count=60,reserve_bytes=20000000,expected_seconds=300) as r:
        with b.job(NAME,'dsp','解析応答・独立畳み込み・源時計の限定資格',count=64,reserve_bytes=1000000,expected_seconds=300) as d:
            with b.workspace(r,'最小位相fixtureの科学ライブラリ初期化') as (_,env):
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            b.save(HERE/'fixture-audit.json',json.loads(out.stdout),d)
    with b.job(NAME,'audit','限定資格・全ソースhash・一時回収・費用の終了照合',reserve_bytes=2000000) as j:
        fixture=read(HERE/'fixture-audit.json');assert fixture['passed'] and fixture['render']==60 and fixture['dsp']==64
        assert len(fixture['spectral_checks'])==16 and len(fixture['source_checks'])==len(fixture['convolution_checks'])==4
        for n,h in contract['source_files'].items():assert digest(HERE/n)==h,n
        temporary=[v for v in b.snapshot()['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,source_checks=4,spectral_checks=16,convolution_checks=4,
            real_Japanese_MCP_qualified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False,
            next='原HTS励振と全MCP/LPF/LF0を守る最小位相FIRの日本語比較を別契約で生成前登録する。'),j)
        b.write(HERE/'report.md',('# 最小位相FIRの機構検証\n\n登録した人工MCPの16条件で、1024点IRは解析式の複素応答・因果prefixと所定誤差内で一致した。4駆動源のC畳み込みは独立した静的畳み込み二本のcrossfadeと一致し、未来の励振変更による過去の出力変化はない。4HTS条件は原対照の波形完全一致・入力列不変を確認した。\n\nこの資格は人工MCPの機構に限る。FIRの有限長とIR補間はPade-MLSAのb補間と異なる。実日本語MCPのtail、工学F0・内容・知覚は未検証で、旧欠測・旧判定を変更しない。\n\n一次資料は[SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)と[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。自然さ改善をこの資料から推論しない。P5未開封・品質未達。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='minphase-mechanism-completed',active_campaign=None,next='科学12件の定期レビュー後、最小位相FIRの日本語生成比較',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0064.json',dict(latest_completed=NAME,review=b.review_due(),quality_goal_completed=False,budget=b.reconcile()))
    print(fixture,flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args()
    register() if a.stage=='register' else run()
