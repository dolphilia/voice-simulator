"""原HTSと最小位相FIRの表現を比較し、新入力・固定二ASR・隔離生成で比較する。"""
from contextlib import contextmanager
import ast
import hashlib
import json
from pathlib import Path
import subprocess
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-minphase-comparison-20261008-v1'
NAME='hts-minphase-comparison-v1'
BASE=ROOT/'campaigns/nas-vocoder-f0-20261008-v1'
PERIOD=ROOT/'campaigns/nas-source-period-audit-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'
PAPER='https://sp-nitech.github.io/sptk/latest/main/freqt.html'

C_SOURCE=r'''/* 原HTSを純観測し、その励振に独立の最小位相FIRを適用する別版。 */
#include "HTS_hidden.h"
#include <math.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
static size_t observed,capacity;
static double *period_out,*counter_out,*source_out;
static uint8_t *event_out;
static double shape_excitation(HTS_Vocoder *,const double *);
#define HTS_Vocoder_initialize SHAPE_Vocoder_initialize
#define HTS_Vocoder_synthesize SHAPE_Vocoder_synthesize
#define HTS_Vocoder_clear SHAPE_Vocoder_clear
#include "HTS_vocoder_shaped.c"
#undef HTS_Vocoder_initialize
#undef HTS_Vocoder_synthesize
#undef HTS_Vocoder_clear
static double shape_excitation(HTS_Vocoder *v,const double *lpf) {
    double p=v->pitch_of_curr_point,c=v->pitch_counter;
    double x=HTS_Vocoder_get_excitation(v,lpf);
    if(observed<capacity){period_out[observed]=p;counter_out[observed]=c;source_out[observed]=x;event_out[observed]=p>0. && c+1.>=p;}
    observed++;return x;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,
    double *counter,double *source,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!source||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || selected!=0)return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    double alpha=.55;
    observed=0;capacity=samples;period_out=period;counter_out=counter;source_out=source;event_out=event;
    HTS_Vocoder v;SHAPE_Vocoder_initialize(&v,34,0,FALSE,48000,240);
    for(size_t f=0;f<frames;f++) {
        double mc[35],lp[63];memcpy(mc,mcp+35*f,35*sizeof(double));memcpy(lp,lpf+nlpf*f,nlpf*sizeof(double));
        SHAPE_Vocoder_synthesize(&v,34,lf0[f],mc,nlpf,lp,alpha,0.,1.,out+240*f,NULL);
    }
    size_t actual=observed;capacity=observed=0;period_out=counter_out=source_out=NULL;event_out=NULL;
    SHAPE_Vocoder_clear(&v);
    if(actual!=samples)return 0;
    for(size_t i=0;i<samples;i++)if(!isfinite(out[i])||!isfinite(period[i])||!isfinite(counter[i])||!isfinite(source[i]))return 0;
    return 1;
}

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

WRAPPER=r'''"""与えたLF0を原HTSのalpha=.55フィルタへ渡す入口。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,U,S]
MODES={'native':0,'half_contour':0,'flat_contour':0}
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録のLF0輪郭設定')
    x=validated(params,settings);before=[ah(v) for v in x];n=len(x[0])*240
    out=np.empty(n);period=np.empty(n);counter=np.empty(n);source=np.empty(n);event=np.empty(n,dtype=np.uint8)
    assert _fn(*(v.ctypes.data_as(P) for v in x),len(x[0]),35,x[2].shape[1],MODES[method],out.ctypes.data_as(P),period.ctypes.data_as(P),counter.ctypes.data_as(P),source.ctypes.data_as(P),event.ctypes.data_as(U),n)
    assert [ah(v) for v in x]==before
    assert np.array_equal(event.astype(bool),(period>0)&(counter+1>=period))
    return out,dict(period=period,counter=counter,excitation=source,event=event)
def synthesize(params,settings,method):
    x,tr=raw(params,settings,method)
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA/LF0輪郭の独立因子',filter_method=method,effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        original_HTS_excitation_algorithm_LPF_filter_gain_unchanged=True,periodic_source_delay_samples=0,
        frequency_axis_rule='全方式alpha=.55固定。LF0輪郭だけが別因子。',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

FIXTURE=r'''機構fixtureは同一C binaryで終了済み。別音声生成を再試行せずhashで引き継ぐ。'''

PATHS='''"""新共有フィルタ因子実験。旧資料は読み取り、長期承認台帳を継承する。"""
from pathlib import Path
from contextlib import contextmanager
import sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
NAME='hts-minphase-comparison-v1'
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

POOL={'candidate_pool_short': ['小箱に石を並べる。', '階段の端に座る。', '布を机に広げる。', '椅子の脚を拭く。', '畑で豆を摘む。', '鍵を紐に通す。', '池に雲が映る。', '窓の外で鈴が鳴る。'], 'candidate_pool_long': ['午後の授業が終わると、少年は鞄を持って図書室へ向かった。', '風が止んだ頃、祖母は庭に干していた布を丁寧に畳んだ。', '坂の途中にある店で、兄は夕食に使う野菜を選んでいた。', '雨の降る朝、母は玄関に置いた長靴の泥を洗い落とした。', '森の入口で道を確かめてから、父は山頂を目指して歩き出した。', '川沿いの道を走っていた弟が、橋の手前で友人を見つけた。', '夕日が海に沈むまで、姉は砂浜に残った貝殻を集めていた。', '駅に着いた旅人は、壁に掛かった時計を見てほっと息をついた。']}

MECHANISM=ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1'
MINPHASE='"""保存列を使わず、その入力のMCPとHTS励振から因果FIRを計算する。"""\nimport ctypes as C\nfrom pathlib import Path\nimport numpy as np\nfrom hts_arrays import ah\nfrom shape_arrays import raw\n_lib=C.CDLL(str(Path(__file__).resolve().parent/\'shape.dylib\'))\nP=C.POINTER(C.c_double);S=C.c_size_t\n_kernel=_lib.shape_kernel;_kernel.restype=C.c_int;_kernel.argtypes=[P,C.c_double,P,S]\n_fir=_lib.shape_fir;_fir.restype=C.c_int;_fir.argtypes=[P,P,S,P]\ndef kernel(mc,alpha=.55):\n    a=np.ascontiguousarray(mc,dtype=np.float64);assert a.shape==(35,)\n    h=np.empty(1024);assert _kernel(a.ctypes.data_as(P),alpha,h.ctypes.data_as(P),1024)\n    return h\ndef filter_source(mc,source):\n    a=np.ascontiguousarray(mc,dtype=np.float64);x=np.ascontiguousarray(source,dtype=np.float64)\n    assert a.ndim==2 and a.shape[1]==35 and x.shape==(len(a)*240,) and np.isfinite(x).all()\n    before=(ah(a),ah(x));out=np.empty(len(x))\n    assert _fir(a.ctypes.data_as(P),x.ctypes.data_as(P),len(a),out.ctypes.data_as(P))\n    assert (ah(a),ah(x))==before\n    return out\ndef fir_raw(params,settings):\n    # 原MLSA出力も内部で一回生成される。この費用をrenderへ別計上する。\n    native,tr=raw(params,settings,\'native\')\n    out=filter_source(params[0],tr[\'excitation\'])\n    return out,tr,native\n\ndef synthesize(params,settings,method):\n    import hashlib\n    from scipy import signal\n    if method==\'native\':out,tr=raw(params,settings,\'native\');calls=1\n    elif method==\'fir1024\':out,tr,unused_native=fir_raw(params,settings);calls=2\n    else:raise ValueError(\'未登録の最小位相比較方式\')\n    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)\n    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]\n    return audio,dict(renderer=\'HTS-MLSA\' if method==\'native\' else \'MCP-minimum-phase-causal-FIR1024\',filter_method=method,\n        effective_filter_alpha=.55,model_original_alpha=settings[\'alpha\'],input_streams_unchanged=True,\n        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},\n        cycle_events=int(tr[\'event\'].sum()),cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,\n        periodic_source_delay_samples=0,render_calls_including_internal_MLSA=calls,\n        FIR_length=1024 if method==\'fir1024\' else None,\n        interpolation=\'前frame/current IRの出力時刻crossfade j/240。MLSA b補間とは別表現。\' if method==\'fir1024\' else \'HTS原b係数補間\',\n        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)\n'
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
        render=1000,dsp=4000,ai=384,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,status='registered_before_output',question='同じMCP/LF0/LPFと原HTS実励振を使う1024点最小位相FIRは、Pade-MLSA原nativeの内容/固定支持/工学制御を新日本語入力で保てるか。有限IRとIR補間を含む経路変更を比較する。',
        variants=['native','fir1024'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTS Pade-MLSA alpha=.55の完全一致対照',fir1024='MCP35→freqt(-.55)の通常cepstrum1024→c2ir1024。前frame/current IRをj/240補間し、過去の原HTS励振へ因果畳み込み。'),
        effective_alpha=dict(native=.55,fir1024=.55),
        fixed_control='全方式の校正LF0・MCP/LPF/duration/state/MSD/variance・源period/counter/event/全sample励振をbyte固定。波形gain.25・24k resample・12ms fade・alpha.55・volume1も固定。FIRはb補間と同一とは呼ばない。',
        normalization='c0を含むMCPと原sqrt(period)源を保護。周波数帯/波形別の利得救済なし。',
        input='新16文×2条件×2方式=64。全履歴文章/ラベル非衝突を出力前確認。P5本文を読まない。',
        source=dict(url=PAPER,related_url='https://sp-nitech.github.io/sptk/latest/main/c2mpir.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),scope='人工MCPの機構資格を同じC binary/kernel/filterで引き継ぐ。実MCP/音声/知覚の資格は別に調べる。'),
        support='原nativeから一度固定。欠測を除外せず全候補で保持。旧支持/欠測249/旧判定は不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。短窓/動的/知覚の資格にはしない。',content='固定二ASR各33群で原native以下。群ごとの悪化を相殺しない。',independence='全64通常/隔離・CLI4と実読取/通信拒否。',FIR_mechanism='全32nativeの全保存MCP frameで8192FFTの解析複素応答に対する1024IRの最大相対誤差≤1e-3、8192点参考IRの1024以降tailエネルギー割合≤1e-6。全frame検査。有限grid/tailであり連続全域や知覚truthではない。'),
        estimates=dict(comparison_render=96,comparison_output_waves=64,internal_MLSA_helpers=32,comparison_dsp=192,isolation_render=192,isolation_dsp=128,CLI_render=6,CLI_dsp=4,fixture_render=0,inherited_fixture=True,all_frame_FIR_dsp=64,two_ASR_ai=128,total_without_retry=dict(render=294,dsp=388,ai=128),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_minphase_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        new_route_not_alpha_or_pulse_coefficient_rescue=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','原励振固定・最小位相FIR・全比較費を生成前登録',size=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        b.write(HERE/'paths.py',PATHS.encode(),j);b.write(HERE/'shape.c',C_SOURCE.encode(),j)
        b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j);b.write(HERE/'minphase.py',MINPHASE.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h'):b.write(HERE/'vendor'/n,(PERIOD/'vendor'/n).read_bytes(),j)
        src=(PERIOD/'vendor/HTS_vocoder.c').read_text()
        shaped=replace_once(src,'x = HTS_Vocoder_get_excitation(v, lpf);','x = shape_excitation(v, lpf);')
        b.write(HERE/'vendor/HTS_vocoder_shaped.c',shaped.encode(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(BASE/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        # 既存controllerの比較と隔離を別版へコピー。元の契約/ソースを変更しない。
        controller=(BASE/'controller.py').read_text().replace('192','64').replace('576','192').replace('385','129').replace('388','132').replace('b.job(', 'managed_job(b,')
        controller=controller.replace("'CLI E0 ' + mode,", "'CLI E0 ' + mode + '/' + request['id'],")
        controller=controller.replace('voc-fresh-00','minphase-fresh-00')
        controller=replace_once(controller,"assert meta['output_parameter_hashes'][2] == native_meta['output_parameter_hashes'][2]", "assert meta['output_parameter_hashes'] == native_meta['output_parameter_hashes']\n                    assert meta['conversion']['source_clock_hashes'] == native_meta['conversion']['source_clock_hashes']")
        # source凍結を検査し、子処理にcampaign/個別秒の上限を渡す。
        controller=replace_once(controller,'    if profile_text:\n', "    state=Budget().snapshot();c=state['campaigns'][NAME]\n    remaining=c['limits']['seconds']-(state['seconds']-c['start_seconds'])-60\n    jobs=[v for v in state['jobs'].values() if v['campaign']==NAME]\n    expected=min((v['expected_seconds']-(time.time()-v['started_epoch']) for v in jobs),default=timeout)\n    timeout=min(timeout,remaining,expected)\n    assert timeout>0\n    if profile_text:\n")
        controller=controller.replace('    count=64\n    dsp=192','    count=96\n    dsp=192')
        controller=controller.replace("'通常/隔離batch64 ' + mode, count=64", "'通常/隔離batch64 ' + mode, count=96")
        controller=controller.replace("'CLI ' + mode + '/' + request['id'], reserve_bytes=", "'CLI ' + mode + '/' + request['id'], count=1 if request['method']=='native' else 2, reserve_bytes=")
        controller=controller.replace('new_render_calls=64,\n        new_DSP_calls=192', 'new_render_calls=96, internal_MLSA_helpers=32, output_waves=64,\n        new_DSP_calls=192')
        controller=controller.replace('new_render_calls=132, new_DSP_calls=132','new_render_calls=198, new_DSP_calls=132, internal_MLSA_helpers=66')
        controller=controller.replace("                    records = {}", "                    assert sum(r['conversion']['render_calls_including_internal_MLSA'] for r in manifest['records']) == 96\n                    records = {}")
        b.write(HERE/'controller.py',controller.encode(),j)
        for name in ('asr_worker.py','runtime_batch.py','measurement.py'):
            text=(BASE/name).read_text().replace('192','64')
            b.write(HERE/name,text.encode(),j)
        runtime=(BASE/'runtime-bundle/runtime.py').read_text()
        runtime=runtime.replace('from world_renderer2 import synthesize as world_synthesize\n','')
        runtime=runtime.replace('from hts_arrays import synthesize as hts_synthesize','from minphase import synthesize as shape_synthesize')
        runtime=runtime.replace("METHODS=['native','calibrated','voicing','hts_native','hts_calibrated','hts_voicing']","METHODS=['native','fir1024']")
        runtime=runtime.replace("transform(method[4:] if method.startswith('hts_') else method,", "transform('calibrated',")
        start=runtime.index("        if method.startswith('hts_'):");end=runtime.index('        assert engine.snapshot()',start)
        runtime=runtime[:start]+"        raw,conversion=shape_synthesize(params,settings,method)\n"+runtime[end:]
        b.write(HERE/'runtime.py',runtime.encode(),j)
        old=(BASE/'prepare.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='inputs')
        inp=ast.get_source_segment(old,node).replace("ROOT / 'vocoder-f0-candidate-pool-0001.json'", "HERE / 'candidate-pool.json'").replace('voc-fresh-','minphase-fresh-')
        helper=old[old.index('def norm('):old.index('def prepare(')]
        b.write(HERE/'prepare_inputs.py',('from paths import *\nimport re,json,unicodedata\n'+helper+inp+"\nif __name__=='__main__':inputs()\n").encode(),j)
        b.save(HERE/'engine-contract.json',read(BASE/'engine-contract.json'),j)
        b.save(HERE/'source-registration.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},fixed_before_wave=True),j)
    print(b.reconcile(),flush=True)

def prepare():
    b=Budget();b.recover();reg=read(HERE/'registration.json')
    for n,h in read(HERE/'source-registration.json')['files'].items():assert digest(HERE/n)==h,n
    with job(b,'setup','新source build・共有bundle固定',size=30000000,seconds=180) as j:
        assert read(MECHANISM/'fixture-audit.json')['passed']
        b.write(HERE/'shape.dylib',(MECHANISM/'shape.dylib').read_bytes(),j)
        assert digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),source_sha256=digest(HERE/'shape.c'),inherited_binary_exact=True,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),new_compilation=False),j)
        bundle=HERE/'runtime-bundle';mapping={}
        for n in read(BASE/'runtime-bundle/manifest.json')['files']:
            if n.startswith('packages-v2/') or n in ('world_renderer2.py','LICENSE-WORLD.txt','runtime.py','runtime_batch.py'):continue
            mapping[n]=BASE/'runtime-bundle'/n
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib','minphase.py')})
        # 測定用PyWORLDは旧source固定packageを使う。最終生成bundleへ含めない。
        for n,source in mapping.items():b.write(bundle/n,source.read_bytes(),j)
        b.save(bundle/'manifest.json',dict(files={n:digest(bundle/n) for n in mapping},shared_assets=True,final_non_neural=True,utterance_tables=0,neural_model=0,quality_certified=False),j)
    with job(b,'setup','全履歴非衝突と入力条件の波形前固定',size=16000000) as j:
        with b.workspace(j,'辞書と入力照合') as (_,env):
            result=subprocess.run([str(PYTHON),'-B',str(HERE/'prepare_inputs.py')],env=env,check=True,timeout=120,stdout=subprocess.PIPE,text=True)
        value=json.loads(result.stdout);assert len(value['rows'])==16
        b.save(HERE/'novelty-audit.json',value['audit'],j)
        b.save(HERE/'protocol.json',dict(rows=value['rows'],variants=reg['variants'],conditions=reg['conditions'],expected_records=64,protected_confirmation_opened=False,no_optimization_after_first_audio=True,quality_certified=False),j)
        # 測定側はPyWORLDの元package位置を明示する。隔離生成はこのcontrollerを読まない。
        manifest=read(BASE/'runtime-bundle/manifest.json')
        b.save(HERE/'measurement-package-contract.json',dict(files={str((BASE/'runtime-bundle'/n).relative_to(REPO)):h for n,h in manifest['files'].items() if n.startswith('packages-v2/')}),j)
        b.save(HERE/'execution-contract.json',dict(protocol_sha256=digest(HERE/'protocol.json'),registration_sha256=digest(HERE/'registration.json'),runtime_manifest_sha256=digest(bundle/'manifest.json'),source_hashes={p.name:digest(p) for p in HERE.glob('*.py')},engine_contract_sha256=digest(HERE/'engine-contract.json'),controller_sha256=digest(Path(__file__)),fixed_before_first_wave=True,quality_certified=False),j)
    b.save(ROOT/'progress-0066.json',dict(active_campaign=NAME,next='登録commit/push→機構hash照合→64波形比較（内部helper別計数）→通常/隔離/CLI→二ASR→全MCP応答監査/封印',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(b.reconcile(),flush=True)

def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='fixture':
        with job(b,'audit','同一C機構資格のhash照合と追補',size=1000000) as j:
            assert digest(HERE/'shape.dylib')==digest(MECHANISM/'shape.dylib')
            assert digest(HERE/'shape.c')==digest(MECHANISM/'shape.c')
            b.save(HERE/'fixture-audit.json',dict(read(MECHANISM/'fixture-audit.json'),inherited=True,original_sha256=digest(MECHANISM/'fixture-audit.json'),new_render=0,new_dsp=0),j)
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
