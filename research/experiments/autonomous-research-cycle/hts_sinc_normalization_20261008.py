"""共有HTSの周期源形状だけを変更し、新入力・固定二ASR・隔離生成で比較する。"""
from contextlib import contextmanager
import ast
import hashlib
import json
from pathlib import Path
import subprocess
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-sinc-normalization-20261008-v1'
NAME='hts-sinc-normalization-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PAPER='https://ccrma.stanford.edu/~jos/pasp/Windowed_Sinc_Interpolation.html'

C_SOURCE=r'''/* 開閉比を固定した声門流の離散微分。元の乱数と周期時計は一度だけ進める。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define RING 2048
static double old_ring[RING],new_ring[RING];
static size_t cursor,observed,capacity;
static int mode;
static double *period_out,*counter_out;
static uint8_t *event_out;
static double shape_excitation(HTS_Vocoder *,const double *);
#define HTS_Vocoder_initialize SHAPE_Vocoder_initialize
#define HTS_Vocoder_synthesize SHAPE_Vocoder_synthesize
#define HTS_Vocoder_clear SHAPE_Vocoder_clear
#include "HTS_vocoder_shaped.c"
#undef HTS_Vocoder_initialize
#undef HTS_Vocoder_synthesize
#undef HTS_Vocoder_clear
/* 有声開始はphase原点0。それ以外は元clockの端数を同じcell内で補間する。 */
static double previous_period=0.;
static double *phase_out=NULL;
int shape_kernel(double p,int selected,double remainder,double *out,size_t n) {
    if(!isfinite(p)||p<60.||p>48000./70.||n!=9||selected<1||selected>4||!isfinite(remainder)||remainder<0.||remainder>1.)return 0;
    double position=4.-remainder,energy=0.;
    for(size_t i=0;i<n;i++)out[i]=0.;
    if(selected==1)out[4]=1.;
    else if(selected==2){out[3]=remainder;out[4]=1.-remainder;}
    else {
        for(size_t i=0;i<n;i++) {
            double d=(double)i-position;
            if(fabs(d)<=4.)out[i]=(fabs(d)<1e-12?1.:sin(M_PI*d)/(M_PI*d))*(.5+.5*cos(M_PI*d/4.));
        }
    }
    for(size_t i=0;i<n;i++)energy+=out[i]*out[i];
    if(energy<=0.)return 0;
    double sum=0.;for(size_t i=0;i<n;i++)sum+=out[i];
    if(selected==4 && sum<=1e-12)return 0;
    double scale=selected==4?sqrt(p)/sum:sqrt(p/energy);for(size_t i=0;i<n;i++)out[i]*=scale;
    return 1;
}
static double shape_excitation(HTS_Vocoder *v,const double *lpf) {
    double p=v->pitch_of_curr_point,c=v->pitch_counter;
    uint8_t event=p>0. && c+1.>=p;
    double remainder=event?fmax(0.,fmin(1.,c+1.-p)):0.;
    if(observed==0 || previous_period==0.)remainder=0.;
    if(event) {
        double kernel[9];
        if(!shape_kernel(p,mode?mode:1,remainder,kernel,9))return NAN;
        for(size_t j=0;j<v->excite_buff_size;j++) {
            old_ring[(cursor+j)%RING]+=sqrt(p)*lpf[j];
            for(size_t k=0;k<9;k++)new_ring[(cursor+j+k)%RING]+=kernel[k]*lpf[j];
        }
    }
    /* 元のget_excitationを一度だけ呼び、noise/RNG/period/counterを保存する。 */
    double x=HTS_Vocoder_get_excitation(v,lpf);
    if(observed<capacity){period_out[observed]=p;counter_out[observed]=c;phase_out[observed]=remainder;event_out[observed]=event;}
    if(mode)x+=new_ring[cursor]-old_ring[cursor];
    old_ring[cursor]=new_ring[cursor]=0.;cursor=(cursor+1)%RING;previous_period=p;observed++;
    return x;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,
    double *counter,double *phase,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!phase||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (selected<0||selected>4))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    memset(old_ring,0,sizeof(old_ring));memset(new_ring,0,sizeof(new_ring));
    cursor=observed=0;previous_period=0.;phase_out=phase;capacity=samples;mode=selected;period_out=period;counter_out=counter;event_out=event;
    HTS_Vocoder v;SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+35*f,35*sizeof(double));memcpy(lp,lpf+nlpf*f,nlpf*sizeof(double));
        SHAPE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,.55,0.,1.,out+240*f,NULL);
    }
    size_t actual=observed;capacity=observed=0;period_out=counter_out=phase_out=NULL;event_out=NULL;
    SHAPE_Vocoder_clear(&v);
    if(actual!=samples)return 0;
    for(size_t i=0;i<samples;i++)if(!isfinite(out[i])||!isfinite(period[i])||!isfinite(counter[i]))return 0;
    return 1;
}
'''

WRAPPER=r'''"""元pulseと共通4sample遅延下の整数/線形/9tap sinc pulse。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,U,S]
_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[C.c_double,C.c_int,C.c_double,P,S]
MODES={'native':0,'latency':1,'linear':2,'sinc':3,'sinc_dc':4}
def kernel(period,remainder,method):
    a=np.empty(9);assert method in ('latency','linear','sinc','sinc_dc')
    assert _kernel(period,MODES[method],remainder,a.ctypes.data_as(P),len(a))
    return a
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録のpulse補間')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);phase=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),phase.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before
    assert np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    expected=np.where(event,np.clip(counter+1-period,0,1),0.);expected[np.r_[True,period[:-1]==0]]=0.
    assert np.array_equal(phase,expected)
    return out,dict(period=period,counter=counter,phase=phase,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method)
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA/pulse位置補間',source_method=method,input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        periodic_source_delay_samples=0 if method=='native' else 4,
        phase_definition='有声開始0。他はclip(counter+1-period,0,1)。同4sample遅延でcell内端数を補間。',
        source_normalization='DC sum=sqrt(period)' if method=='sinc_dc' else 'L2 sumsq=period',output_noise_LPF_gain_fixed=True,
        waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

FIXTURE=r'''"""位相と形状の一致、DC/二乗和の別条件、元波形/clockの工程検証。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original
from shape_arrays import raw,synthesize,kernel
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((100,35));mcp[:,0]=7.;lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz)
    params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);native,_=synthesize(params,settings,'native')
    assert np.array_equal(baseline,native)
    a,ta=raw(params,settings,'native')
    for method in ('sinc','sinc_dc'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        if coefficient==0.:assert np.array_equal(a,z)
        else:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,all_clock_and_phase_exact=True,zero_LPF_exact=coefficient==0.))
normalization_checks=[]
for hz in (80.,110.,220.,280.,400.,800.):
 for remainder in np.linspace(0,1,11):
    p=48000/hz;w=2*np.pi*hz/48000;target=4-remainder
    a=kernel(p,float(remainder),'sinc');z=kernel(p,float(remainder),'sinc_dc')
    assert np.isfinite(a).all() and np.isfinite(z).all()
    assert abs(float(np.sum(a*a))-p)<1e-10 and abs(float(z.sum())-np.sqrt(p))<1e-10
    assert np.allclose(z,a*(np.sqrt(p)/a.sum()),rtol=0,atol=1e-12)
    Ha=np.dot(a,np.exp(-1j*w*np.arange(9)));Hz=np.dot(z,np.exp(-1j*w*np.arange(9)))
    assert abs(float(np.angle(Hz/Ha)))<1e-12
    normalization_checks.append(dict(hz=hz,remainder=float(remainder),phase_error_samples=float(abs(np.angle(Ha*np.exp(1j*w*target))/w)),
        L2_DC_gain=float(a.sum()/np.sqrt(p)),DC_DC_gain=float(z.sum()/np.sqrt(p)),DC_energy_ratio=float(np.sum(z*z)/p),shape_and_phase_equal=True))
print(json.dumps(dict(passed=True,checks=checks,normalization_checks=normalization_checks,render=20,dsp=800,fixture_only=True,
    L2_energy_and_DC_gain_are_different_constraints=True,mechanical_truth_not_perceptual_truth=True,quality_certified=False)))
'''

PATHS='''"""新共有源実験。旧資料は読み取り、長期承認台帳を継承する。"""
from pathlib import Path
from contextlib import contextmanager
import sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
NAME='hts-sinc-normalization-v1'
PREVIOUS=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
OLD=REPO/'research/experiments/autonomous-speech-synthesis'
PILOT=REPO/'research/experiments/neural-control-distillation'
PYTHON=OLD/'.venv-eval/bin/python'
@contextmanager
def managed_job(b,campaign,kind,label,count=1,reserve_bytes=0):
    expected=1800 if kind=='ai' else 600 if kind in ('render','dsp') else 180
    token=b.reserve(campaign,kind,label,count,reserve_bytes,expected_seconds=expected)
    try:yield token
    except BaseException as exc:b.finish(token,repr(exc));raise
    else:b.finish(token)
'''

POOL={'candidate_pool_short': ['胡麻を軽く煎る。', '布団を棚にしまう。', '穏やかな波が寄せる。', '庭石に露が光る。', '柿の皮を剥く。', '小さな笛を吹く。', '白い糸を通す。', '南の窓を閉める。'], 'candidate_pool_long': ['静かな夕方に、猫が廊下の端で丸くなって眠っていた。', '祖父の話を聞きながら、机に広げた地図を指でなぞった。', '青い空の下で、妹は花壇の周りに小さな石を並べた。', '温かい汁を器によそってから、家族を呼ぶために戸を開けた。', '長い旅から戻った友人が、港で見た景色を楽しそうに話した。', '柔らかな日差しが差す部屋で、母は古い写真を一枚ずつ眺めた。', '道端に落ちていた小さな葉を拾い、手帳の間に挟んでおいた。', '遠くの町へ向かう列車を見送り、二人はゆっくり歩き始めた。']}

@contextmanager
def job(b,kind,label,count=1,size=1000000,seconds=180):
    token=b.reserve(NAME,kind,label,count,size,expected_seconds=seconds)
    try:yield token
    except BaseException as exc:b.finish(token,repr(exc));raise
    else:b.finish(token)

def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new)

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    limits=dict(seconds=14400,bytes=1800000000,write_bytes=2800000000,setup=30,audit=40,
        render=1000,dsp=4000,ai=576,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,status='registered_before_output',question='原nativeを対照に、同じ9tap sinc形状・fractional phase・4sample遅延下のL2正規化とDC利得保存を比較し、源の周期ごとの振幅変動が固定支持/内容保護に与える因果効果を検証する',
        variants=['native','sinc','sinc_dc'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='元HTS励振、完全一致対照',sinc='9tap raised-cosine窓sinc、二乗和period',sinc_dc='同形状/位相/遅延、和sqrt(period)。周期二乗和は保存しない。'),
        phase_definition='有声開始の原点0。それ以外はclip(counter+1-period,0,1)。native丸めと各補間の共通機械clock。瞬時F0/知覚truthと呼ばない。',
        energy='native/sincは周期kernel二乗和period。sinc_dcは和sqrt(period)。出力gain.25、noise、MCP、LPF、全clock不変。波形ごとの正規化/出力後調整なし。',
        fixed_control='全方式calibrated LF0、原有声相対輪郭・未補完MSD・duration・全3stream byte不変。',
        input='新16文×2条件×3方式=96。全履歴の文章/ラベル非衝突を波形前確認。P5未開封。',
        source=dict(url=PAPER,title='Julius O. Smith, Physical Audio Signal Processing: Windowed Sinc Interpolation',retrieved='2026-10-08',scope='補間原理の一次解説。9tapの独自実装、最適設計や聴取品質の再現は主張しない。'),
        support='nativeから一度固定し全候補へ引継ぎ。欠測を除外しない。eligible/除外理由も保存。旧支持/249欠測と旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上で全件確認。短窓/動的/知覚へ資格を拡張しない。',content='二固定ASR各33群が原native以下。別コホートの悪化を相殺しない。',independence='全96通常/隔離、CLI4、禁止資料/通信の実拒否。'),
        estimates=dict(comparison_render=96,comparison_dsp=288,isolation_render=192,isolation_dsp=192,CLI_render=4,CLI_dsp=4,fixture_render=20,fixture_dsp=800,two_ASR_ai=192,total_without_retry=dict(render=312,dsp=1284,ai=192),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,
        controller_sha256=digest(Path(__file__)),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','源形状の因子・全比較費とコードを生成前登録',size=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        b.write(HERE/'paths.py',PATHS.encode(),j);b.write(HERE/'shape.c',C_SOURCE.encode(),j)
        b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h'):b.write(HERE/'vendor'/n,(PERIOD/'vendor'/n).read_bytes(),j)
        src=(PERIOD/'vendor/HTS_vocoder.c').read_text()
        shaped=replace_once(src,'x = HTS_Vocoder_get_excitation(v, lpf);','x = shape_excitation(v, lpf);')
        b.write(HERE/'vendor/HTS_vocoder_shaped.c',shaped.encode(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(BASE/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        # 既存controllerの比較と隔離を別版へコピー。元の契約/ソースを変更しない。
        controller=(BASE/'controller.py').read_text().replace('192','96').replace('576','288').replace('385','193').replace('388','196').replace('b.job(', 'managed_job(b,')
        controller=controller.replace("'CLI E0 ' + mode,", "'CLI E0 ' + mode + '/' + request['id'],")
        controller=controller.replace('voc-fresh-00','normalization-fresh-00')
        controller=replace_once(controller,"assert meta['output_parameter_hashes'][2] == native_meta['output_parameter_hashes'][2]", "assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']\n                    assert meta['conversion']['source_clock_hashes'] == native_meta['conversion']['source_clock_hashes']")
        # source凍結を検査し、子処理にcampaign/個別秒の上限を渡す。
        controller=replace_once(controller,'    if profile_text:\n', "    state=Budget().snapshot();c=state['campaigns'][NAME]\n    remaining=c['limits']['seconds']-(state['seconds']-c['start_seconds'])-60\n    jobs=[v for v in state['jobs'].values() if v['campaign']==NAME]\n    expected=min((v['expected_seconds']-(time.time()-v['started_epoch']) for v in jobs),default=timeout)\n    timeout=min(timeout,remaining,expected)\n    assert timeout>0\n    if profile_text:\n")
        b.write(HERE/'controller.py',controller.encode(),j)
        for name in ('asr_worker.py','runtime_batch.py','measurement.py'):
            text=(BASE/name).read_text().replace('192','96')
            b.write(HERE/name,text.encode(),j)
        runtime=(BASE/'runtime-bundle/runtime.py').read_text()
        runtime=runtime.replace('from world_renderer2 import synthesize as world_synthesize\n','')
        runtime=runtime.replace('from hts_arrays import synthesize as hts_synthesize','from shape_arrays import synthesize as shape_synthesize')
        runtime=runtime.replace("METHODS=['native','calibrated','voicing','hts_native','hts_calibrated','hts_voicing']","METHODS=['native','sinc','sinc_dc']")
        runtime=runtime.replace("transform(method[4:] if method.startswith('hts_') else method,", "transform('calibrated',")
        start=runtime.index("        if method.startswith('hts_'):");end=runtime.index('        assert engine.snapshot()',start)
        runtime=runtime[:start]+"        raw,conversion=shape_synthesize(params,settings,method)\n"+runtime[end:]
        b.write(HERE/'runtime.py',runtime.encode(),j)
        old=(BASE/'prepare.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='inputs')
        inp=ast.get_source_segment(old,node).replace("ROOT / 'vocoder-f0-candidate-pool-0001.json'", "HERE / 'candidate-pool.json'").replace('voc-fresh-','normalization-fresh-')
        helper=old[old.index('def norm('):old.index('def prepare(')]
        b.write(HERE/'prepare_inputs.py',('from paths import *\nimport re,json,unicodedata\n'+helper+inp+"\nif __name__=='__main__':inputs()\n").encode(),j)
        b.save(HERE/'engine-contract.json',read(BASE/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(b.reconcile(),flush=True)

def prepare():
    b=Budget();b.recover();reg=read(HERE/'registration.json')
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','新source build・共有bundle固定',size=30000000,seconds=180) as j:
        with b.workspace(j,'clang専用cacheと中間物',16000000,32000000) as (work,env):
            env['CLANG_MODULE_CACHE_PATH']=str(work/'clang-modules')
            tool='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang'
            sdk='/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk'
            cmd=[tool,'-dynamiclib','-O2','-fno-modules','-undefined','dynamic_lookup','-isysroot',sdk,'-I'+str(HERE/'vendor'),str(HERE/'shape.c'),'-o',str(HERE/'shape.dylib')]
            with b.external_output(HERE/'shape.dylib',150000,j):
                out=subprocess.run(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,check=True,timeout=120)
        b.save(HERE/'build-audit.json',dict(command=cmd,binary_sha256=digest(HERE/'shape.dylib'),source_sha256=digest(HERE/'shape.c'),stderr=out.stderr,temporary_removed=True),j)
        bundle=HERE/'runtime-bundle';mapping={}
        for n in read(BASE/'runtime-bundle/manifest.json')['files']:
            if n.startswith('packages-v2/') or n in ('world_renderer2.py','LICENSE-WORLD.txt','runtime.py','runtime_batch.py'):continue
            mapping[n]=BASE/'runtime-bundle'/n
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib')})
        # 測定用PyWORLDは旧source固定packageを使う。最終生成bundleへ含めない。
        for n,source in mapping.items():b.write(bundle/n,source.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
    with job(b,'setup','全履歴非衝突と入力条件の波形前固定',size=16000000) as j:
        with b.workspace(j,'辞書と入力照合') as (_,env):
            result=subprocess.run([str(PYTHON),'-B',str(HERE/'prepare_inputs.py')],env=env,check=True,timeout=120,stdout=subprocess.PIPE,text=True)
        value=json.loads(result.stdout);assert len(value['rows'])==16
        b.save(HERE/'novelty-audit.json',value['audit'],j)
        b.save(HERE/'protocol.json',dict(rows=value['rows'],variants=reg['variants'],conditions=reg['conditions'],expected_records=96,protected_confirmation_opened=False,no_optimization_after_first_audio=True,quality_certified=False),j)
        # 測定側はPyWORLDの元package位置を明示する。隔離生成はこのcontrollerを読まない。
        manifest=read(BASE/'runtime-bundle/manifest.json')
        b.save(HERE/'measurement-package-contract.json',dict(files={str((BASE/'runtime-bundle'/n).relative_to(REPO)):h for n,h in manifest['files'].items() if n.startswith('packages-v2/')}),j)
        b.save(HERE/'execution-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),registration_sha256=digest(HERE/'registration.json'),runtime_manifest_sha256=digest(bundle/'manifest.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},engine_contract_sha256=digest(HERE/'engine-contract.json'),controller_sha256=digest(Path(__file__)),fixed_before_first_wave=True,quality_certified=False),j)
    b.save(ROOT/'progress-0056.json',dict(active_campaign=NAME,next='登録commit/push→fixture→64新入力比較→通常/隔離/CLI→二ASR→全件集計/封印',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(b.reconcile(),flush=True)

def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='fixture':
        with job(b,'render','sinc正規化の数値対照fixture',20,20000000,180) as r:
            with job(b,'dsp','sinc形状/位相・L2/DC条件・旧波形fixture',800,1000000,180) as d:
                with b.workspace(r,'fixtureの科学ライブラリ初期化') as (_,env):
                    result=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,timeout=120,stdout=subprocess.PIPE,text=True)
                b.save(HERE/'fixture-audit.json',json.loads(result.stdout),d)
    else:
        assert read(HERE/'fixture-audit.json')['passed']
        # pyworld固定版を測定だけに追加。生成の隔離子は環境PYTHONPATHを使わない。
        import os
        env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(BASE/'runtime-bundle/packages-v2')
        args=[str(PYTHON),'-B',str(HERE/'controller.py'),stage]
        if engine:args+=['--engine',engine]
        subprocess.run(args,env=env,check=True,timeout=4000)
    print(b.reconcile(),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','prepare','fixture','comparison','isolate','asr']);p.add_argument('--engine')
    args=p.parse_args()
    if args.stage=='register':register()
    elif args.stage=='prepare':prepare()
    else:run(args.stage,args.engine)
