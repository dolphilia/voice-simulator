"""原HTSと固定長FFT FIRの表現を比較し、新入力・固定二ASR・隔離生成で比較する。"""
from contextlib import contextmanager
import ast
import re
import hashlib
import json
from pathlib import Path
import subprocess
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2]
HERE=ROOT/'campaigns/nas-hts-fir-gain-comparison-20261008-v1'
NAME='hts-fir-gain-comparison-v1'
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

FIXTURE='# 同一機構fixtureをhash照合で引継ぐ。新波形生成なし。\n'

PATHS='''"""新共有フィルタ因子実験。旧資料は読み取り、長期承認台帳を継承する。"""
from pathlib import Path
from contextlib import contextmanager
import sys,time
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT))
from budget import read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
NAME='hts-fir-gain-comparison-v1'
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

POOL={'candidate_pool_short': ['青磁の皿を洗う。', '銀杏の殻を割る。', '絹糸の端を結ぶ。', '暖炉の薪を足す。', '葡萄の房を持つ。', '書棚の埃を払う。', '木靴の底を直す。', '麦茶の瓶を冷やす。'], 'candidate_pool_long': ['木の橋を渡った先で、叔父は荷物を下ろして川の流れを眺めた。', '夕方の台所から香りが漂い、妹は窓を閉めて食卓の椅子を並べた。', '海辺の道を進んでいると、友人が白い貝殻を拾って私に見せた。', '畑の隅で作業を終えた祖父は、手袋を外して井戸の水で手を洗った。', '曇り空の下を歩きながら、姉は明日の予定を一つずつ話してくれた。', '倉庫の奥から道具を運び出し、父は壊れた扉の蝶番を取り替えた。', '坂道を登った少年は、花の咲く庭を見つけて足を止めた。', '夕食の片付けが済むと、母は机に向かって短い手紙を書き始めた。']}

MECHANISM=ROOT/'campaigns/nas-hts-fir-gain-mechanism-20261008-v1'
MINPHASE='"""MCP→有限gridの最小位相IR。現入力から計算し、保存軌跡は読まない。"""\nimport hashlib\nimport numpy as np\nfrom scipy import signal\nfrom hts_arrays import ah\nfrom shape_arrays import raw\nIR_LENGTH=2048\nFFT_LENGTH=16384\n_q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)\ndef kernel(mc,alpha=.55):\n    x=np.asarray(mc,dtype=np.float64);assert x.shape==(35,) and np.isfinite(x).all() and abs(alpha)<1.\n    a=(_q-alpha)/(1.-alpha*_q)\n    target=np.exp(np.polynomial.polynomial.polyval(a,x))\n    h=np.fft.irfft(target,n=FFT_LENGTH)[:IR_LENGTH].copy()\n    assert np.isfinite(h).all()\n    return h\ndef log_gain(mc,alpha=.55):\n    # mc2bのb0 = sum((-alpha)**m * mc[m])。波形から利得を推定しない。\n    x=np.asarray(mc,dtype=np.float64);assert x.shape==(35,) and np.isfinite(x).all()\n    return float(np.polynomial.polynomial.polyval(-alpha,x))\ndef filter_source(mc,source,interpolation=\'linear\'):\n    if interpolation not in (\'linear\',\'loggain\'):raise ValueError(\'未登録の利得補間\')\n    m=np.asarray(mc,dtype=np.float64);x=np.asarray(source,dtype=np.float64)\n    assert m.ndim==2 and m.shape[1]==35 and x.shape==(len(m)*240,) and np.isfinite(x).all()\n    before=(ah(m),ah(x));y=np.empty(len(x));previous=kernel(m[0]);previous_log=log_gain(m[0]);u=np.arange(240)/240.\n    for frame,c in enumerate(m):\n        current=kernel(c);current_log=log_gain(c);start=frame*240;stop=start+240\n        left=max(0,start-IR_LENGTH+1);past=x[left:stop]\n        if start<IR_LENGTH-1:past=np.pad(past,(IR_LENGTH-1-start,0))\n        assert len(past)==IR_LENGTH-1+240\n        windows=np.lib.stride_tricks.sliding_window_view(past,IR_LENGTH)[:,::-1]\n        if interpolation==\'linear\':\n            a=windows@previous;b=windows@current;y[start:stop]=a+u*(b-a)\n        else:\n            a=windows@(previous/np.exp(previous_log));b=windows@(current/np.exp(current_log))\n            y[start:stop]=(a+u*(b-a))*np.exp(previous_log+u*(current_log-previous_log))\n        previous=current;previous_log=current_log\n    assert before==(ah(m),ah(x)) and np.isfinite(y).all()\n    return y\ndef synthesize(params,settings,method):\n    if method not in (\'native\',\'fft_fir\',\'fft_loggain\'):raise ValueError(\'未登録のFFT FIR方式\')\n    native,tr=raw(params,settings,\'native\')\n    out=native if method==\'native\' else filter_source(params[0],tr[\'excitation\'],\'loggain\' if method==\'fft_loggain\' else \'linear\')\n    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)\n    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]\n    return audio,dict(renderer=\'HTS-MLSA\' if method==\'native\' else \'MCP-FFT-causal-FIR\',filter_method=method,\n        effective_filter_alpha=.55,model_original_alpha=settings[\'alpha\'],input_streams_unchanged=True,\n        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},cycle_events=int(tr[\'event\'].sum()),\n        cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,periodic_source_delay_samples=0,\n        render_calls_including_internal_MLSA=1 if method==\'native\' else 2,FIR_length=IR_LENGTH if method!=\'native\' else None,\n        FFT_length=FFT_LENGTH if method!=\'native\' else None,IR_interpolation=\'対数利得を分離し形状crossfade j/240\' if method==\'fft_loggain\' else \'前frame/current IRの出力crossfade j/240\',\n        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)\n'
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
    reg=dict(campaign=NAME,status='registered_before_output',question='全体IRの算術補間と対数利得分離補間を新日本語で切り分け、原nativeの内容/固定支持/工学制御を守れるか。',
        variants=['native','fft_fir','fft_loggain'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='原HTS Pade-MLSA alpha=.55完全一致対照',fft_fir='解析IR2048の全利得込み算術出力crossfade j/240',fft_loggain='IR/exp(b0)形状の算術補間×exp(線形補間b0)。b0=polyval(-.55,MCP)。'),
        effective_alpha=dict(native=.55,fft_fir=.55,fft_loggain=.55),IR_length=2048,FFT_length=16384,
        fixed_control='校正LF0・全MCP/LPF/duration/state/MSD/variance・源period/counter/event/実励振をbyte固定。sqrt(period)、gain.25、resample24k、12ms fade、volume1、因果参照・ゼロ追加遅延を保持。MLSA状態/全b補間との同一性は主張しない。',
        normalization='入力MCPと励振を保持。解析式b0のみを使い、波形別gain救済なし。',
        input='未使用16文×2条件×3方式=96。全履歴文章/ラベル非衝突を出力前確認。P5本文は読まない。',
        source=dict(url='https://sp-nitech.github.io/sptk/latest/main/mc2b.html',related_url='https://sp-nitech.github.io/sptk/latest/main/mglsadf.html',mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),previous_speech_seal_sha256=digest(ROOT/'campaigns/nas-hts-fir-gain-comparison-20261008-v1/artifact-seal.json')),
        support='原nativeから一度固定し、欠測を除外せず二候補全件へ保持。旧249欠測/旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上を全件。短窓/動的/知覚資格へ一般化しない。',content='二固定ASR各33群で原native以下。群間/方式間の悪化相殺なし。',independence='全96通常/隔離・CLI4と実読取/通信拒否。',FIR_mechanism='全32nativeの全MCP frameで16384gridの複素応答相対誤差≤1e-3、参考IR2048以降tail energy割合≤1e-6。保存三方式列の全64対を物理照合。'),
        CPU_limits='生成/測定/隔離子のBLAS/VECLIB/OMP=1。二ASRの明示threads4/2と環境は既存契約を引継ぐ。',
        estimates=dict(comparison_render=160,comparison_output_waves=96,internal_MLSA_helpers=64,comparison_dsp=288,isolation_render=320,isolation_dsp=192,CLI_render=6,CLI_dsp=4,fixture_render=0,inherited_fixture=True,all_frame_FIR_dsp=96,two_ASR_ai=192,total_without_retry=dict(render=486,dsp=580,ai=192),maximum_seconds=11000,external_peak=800000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,controller_sha256=digest(Path(__file__)),closeout_source_sha256=digest(ROOT/'hts_fir_gain_closeout_20261008.py'),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        stop_rule='FIR経路は1024/2048の既不通過を引継ぐ。この三回目でも全件保護不通過なら同補間・係数救済は封印し、別測定資格へ進む。',
        old_FIR_failures_kept=True,new_route_does_not_qualify_perception=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with job(b,'setup','原励振固定・最小位相FIR・全比較費を生成前登録',size=2000000) as j:
        b.save(HERE/'registration.json',reg,j);b.save(HERE/'candidate-pool.json',POOL,j)
        b.write(HERE/'paths.py',PATHS.encode(),j);b.write(HERE/'shape.c',C_SOURCE.encode(),j)
        b.write(HERE/'shape_arrays.py',WRAPPER.encode(),j);b.write(HERE/'fft_fir.py',MINPHASE.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('HTS_hidden.h','HTS_engine.h'):b.write(HERE/'vendor'/n,(PERIOD/'vendor'/n).read_bytes(),j)
        src=(PERIOD/'vendor/HTS_vocoder.c').read_text()
        shaped=replace_once(src,'x = HTS_Vocoder_get_excitation(v, lpf);','x = shape_excitation(v, lpf);')
        b.write(HERE/'vendor/HTS_vocoder_shaped.c',shaped.encode(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(BASE/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        # 既存controllerの比較と隔離を別版へコピー。元の契約/ソースを変更しない。
        controller='"""予約・pipe・外部一時領域を統一し、凍結比較を段階実行する。"""\nfrom paths import *\nimport argparse\nimport base64\nimport hashlib\nimport io\nimport json\nimport os\nimport subprocess\nimport sys\nimport time\nimport zipfile\n\n\ndef verify():\n    contract=read(HERE/\'execution-contract.json\')\n    assert digest(HERE/\'protocol.json\')==contract[\'protocol_sha256\']\n    assert digest(HERE/\'registration.json\')==contract[\'registration_sha256\']\n    assert digest(HERE/\'runtime-bundle/manifest.json\')==contract[\'runtime_manifest_sha256\']\n    for name,expected in contract[\'source_hashes\'].items(): assert digest(HERE/name)==expected,name\n    return contract\n\n\ndef requests():\n    p = read(HERE / \'protocol.json\')\n    return [dict(id=row[\'id\'] + \'/\' + c + \'/\' + method, text=row[\'text\'],\n                 method=method, speed=q[\'speed\'], pitch=q[\'requested_f0\'])\n            for row in p[\'rows\'] for c, q in p[\'conditions\'].items() for method in p[\'variants\']]\n\n\ndef profile(b, work, isolated):\n    text = \'(version 1)\\n(allow default)\\n(deny network*)\\n(deny file-write*)\\n\'\n    text += \'(allow file-write* (subpath \' + json.dumps(str(work)) + \'))\\n\'\n    if isolated:\n        text += \'(deny file-read* (subpath \' + json.dumps(str(REPO / \'research\')) + \'))\\n\'\n        text += \'(deny file-read-data (subpath \' + json.dumps(str(b.guard.root)) + \'))\\n\'\n        site = OLD / \'.venv-eval/lib/python3.11/site-packages\'\n        allowed = [OLD / \'.venv-eval\', HERE / \'runtime-bundle\', work]\n        text += \'(allow file-read* \' + \'\'.join(\'(subpath \' + json.dumps(str(p)) + \') \' for p in allowed) + \')\\n\'\n        text += \'(allow file-read-data (literal \' + json.dumps(str(b.guard.root / \'identity.json\')) + \'))\\n\'\n        text += \'(deny file-read* \' + \'\'.join(\'(subpath \' + json.dumps(str(site / n)) + \') \'\n            for n in (\'torch\', \'tensorflow\', \'transformers\', \'faster_whisper\', \'ctranslate2\',\n                      \'onnxruntime\', \'sherpa_onnx\')) + \')\\n\'\n    if isolated:\n        ancestors=set()\n        for path in [OLD / \'.venv-eval\', HERE / \'runtime-bundle\', work]: ancestors.update(path.parents)\n        text += \'(allow file-read-metadata \' + \'\'.join(\'(literal \' + json.dumps(str(p)) + \') \' for p in sorted(ancestors)) + \')\\n\'\n    return text\n\n\ndef execute(command, env, profile_text=None, input_text=None, timeout=1800):\n    env=dict(env)\n    if \'--engine\' not in command:env.update(OPENBLAS_NUM_THREADS=\'1\',OMP_NUM_THREADS=\'1\',MKL_NUM_THREADS=\'1\',VECLIB_MAXIMUM_THREADS=\'1\')\n    state=Budget().snapshot();c=state[\'campaigns\'][NAME]\n    remaining=c[\'limits\'][\'seconds\']-(state[\'seconds\']-c[\'start_seconds\'])-60\n    jobs=[v for v in state[\'jobs\'].values() if v[\'campaign\']==NAME]\n    expected=min((v[\'expected_seconds\']-(time.time()-v[\'started_epoch\']) for v in jobs),default=timeout)\n    timeout=min(timeout,remaining,expected)\n    assert timeout>0\n    if profile_text:\n        command = [\'/usr/bin/sandbox-exec\', \'-p\', profile_text, *command]\n    # runはtimeout/失敗時も子を終了・waitし、pipeを閉じてから戻る。\n    return subprocess.run(command, env=env, input=input_text, text=True,\n                          stdout=subprocess.PIPE, check=True, timeout=timeout).stdout\n\n\ndef comparison_worker(render_job, dsp_job):\n    import tempfile\n    assert Path(tempfile.gettempdir()).resolve() == Path(os.environ[\'TMPDIR\']).resolve()\n    sys.path.insert(0, str(HERE / \'runtime-bundle\'))\n    import numpy as np\n    import re\n    from scipy.io import wavfile\n    from runtime import generate, verify as verify_bundle\n    from measurement import measure, pitch_pass, ELIGIBLE\n    verify_bundle()\n    b = Budget()\n    p = read(HERE / \'protocol.json\')\n    records = []\n    for row in p[\'rows\']:\n        for condition, q in p[\'conditions\'].items():\n            support = None\n            native_meta = None\n            by_method = {}\n            for method in p[\'variants\']:\n                base = HERE / \'render\' / row[\'id\'] / condition / method\n                assert not base.with_suffix(\'.json\').exists(), \'保存済みの比較は再生成しない\'\n                data, meta, params, analyzed = generate(row[\'text\'], method, q[\'speed\'], q[\'requested_f0\'], full=True)\n                assert analyzed[\'full_context_labels\'] == row[\'full_context_labels\']\n                if native_meta:\n                    for key in [\'duration\', \'msd\', \'settings\', \'state_sha256\', \'variance_sha256\', \'native_parameter_hashes\']:\n                        assert meta[key] == native_meta[key], key\n                    assert meta[\'output_parameter_hashes\'][0] == native_meta[\'output_parameter_hashes\'][0]\n                    assert meta[\'output_parameter_hashes\'] == native_meta[\'output_parameter_hashes\']\n                    assert meta[\'conversion\'][\'source_clock_hashes\'] == native_meta[\'conversion\'][\'source_clock_hashes\']\n                else:\n                    native_meta = meta\n                if method.startswith(\'hts_\'):\n                    reference=by_method[method[4:]]\n                    assert meta[\'output_parameter_hashes\']==reference[\'output_parameter_hashes\']\n                    assert meta[\'generated_lf0_median_hz\']==reference[\'generated_lf0_median_hz\']\n                    assert meta[\'conversion\'][\'input_streams_unchanged\']\n                by_method[method]=meta\n                b.write(base.with_suffix(\'.wav\'), data, render_job)\n                arrays = io.BytesIO()\n                np.savez_compressed(arrays, mcp=params[0], lf0=params[1], lpf=params[2], duration=meta[\'duration\'])\n                b.write(base.with_suffix(\'.npz\'), arrays.getvalue(), render_job)\n                _, audio = wavfile.read(io.BytesIO(data))\n                eligible = [i for i, label in enumerate(row[\'full_context_labels\'])\n                            if re.search(r\'\\-([^+]+)\\+\', label).group(1) in ELIGIBLE\n                            and any(meta[\'msd\'][i * 5:(i + 1) * 5][k] > .5 for k in range(5))]\n                measured, f0, times = measure(audio, meta[\'duration\'], eligible, support)\n                if support is None:\n                    support = measured[\'support\']\n                    b.save(HERE / \'support\' / row[\'id\'] / (condition + \'.json\'),\n                        dict(indices=support, excluded=[r[\'index\'] for r in measured[\'eligible_native_intervals\']\n                        if not r[\'support_complete\']], native_wave_sha256=meta[\'sha256\'],\n                        fixed_from_native=True, not_candidate_selected=True), dsp_job)\n                arrays = io.BytesIO()\n                np.savez_compressed(arrays, f0=f0, times=times)\n                b.write(base.with_suffix(\'.dio.npz\'), arrays.getvalue(), dsp_job)\n                record = {k: row[k] for k in [\'text\', \'length\', \'challenge_group\', \'cohort\']}\n                record.update(id=row[\'id\'] + \'/\' + condition + \'/\' + method, condition=condition,\n                    variant=method, wav=str(base.with_suffix(\'.wav\').relative_to(REPO)),\n                    wav_sha256=meta[\'sha256\'], status=\'completed\', meta=meta,\n                    measurement=measured, pitch_gate=pitch_pass(measured, q[\'requested_f0\']),\n                    E0_pass=meta[\'E0_pass\'], invariants_pass=meta[\'invariants_pass\'],\n                    protocol_sha256=digest(HERE / \'protocol.json\'), quality_certified=False)\n                b.write_data(base.with_suffix(\'.json\'), encode(record), dsp_job)\n                records.append(dict(id=record[\'id\'], record=str(base.with_suffix(\'.json\').relative_to(REPO)),\n                                    sha256=digest(base.with_suffix(\'.json\'))))\n            print(\'比較\', len(records), \'/96\', flush=True)\n    assert len(records) == 96\n    b.save(HERE / \'render-manifest.json\', dict(rows=records, new_render_calls=160, internal_MLSA_helpers=64, output_waves=96,\n        new_DSP_calls=288, no_optimization_after_output=True, quality_certified=False), dsp_job)\n\n\ndef computation(stage):\n    b = Budget()\n    count=160\n    dsp=288\n    with managed_job(b,NAME, \'render\', stage, count=count, reserve_bytes=200_000_000) as render_job:\n        with managed_job(b,NAME, \'dsp\', stage + \' 固定測定\', count=dsp, reserve_bytes=16_000_000) as dsp_job:\n            with b.workspace(render_job, stage + \' ライブラリ初期化・必要時一時処理\') as (_, env):\n                execute([str(PYTHON), \'-B\', str(HERE / \'controller.py\'),\n                         stage + \'-worker\', \'--render-job\', render_job, \'--dsp-job\', dsp_job], env)\n    print(stage, \'保存完了\', flush=True)\n\n\ndef isolate():\n    b = Budget()\n    reqs = requests()\n    expected = {r[\'id\']: read(REPO / r[\'record\'])[\'wav_sha256\']\n                for r in read(HERE / \'render-manifest.json\')[\'rows\']}\n    outputs, profiles = {}, {}\n    for mode in [\'normal\', \'isolated\']:\n        with managed_job(b,NAME, \'render\', \'通常/隔離batch96 \' + mode, count=160, reserve_bytes=200_000_000) as job:\n            with managed_job(b,NAME, \'dsp\', \'通常/隔離batch96 E0 \' + mode, count=96, reserve_bytes=100_000):\n                with b.workspace(job, mode + \' ランタイム初期化\') as (work, env):\n                    sb = profile(b, work, mode == \'isolated\')\n                    output = execute([str(PYTHON), \'-I\', \'-B\', str(HERE / \'runtime-bundle/runtime_batch.py\')],\n                                     env, sb, json.dumps(reqs, ensure_ascii=False))\n                    archive_data = base64.b64decode(output, validate=False)\n                    profiles[mode] = dict(source=sb, sha256=hashlib.sha256(sb.encode()).hexdigest())\n                b.write(HERE / \'runtime-archives\' / (mode + \'.zip\'), archive_data, job)\n                with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:\n                    manifest = json.loads(archive.read(\'manifest.json\'))\n                    assert len(manifest[\'records\']) == 96\n                    assert manifest[\'synthesis_calls\'] == manifest[\'E0_calls\'] == 96\n                    assert len(archive.namelist()) == 193\n                    assert sum(r[\'conversion\'][\'render_calls_including_internal_MLSA\'] for r in manifest[\'records\']) == 160\n                    records = {}\n                    for r in manifest[\'records\']:\n                        data = archive.read(r[\'id\'] + \'.wav\')\n                        assert hashlib.sha256(data).hexdigest() == r[\'sha256\'] == expected[r[\'id\']]\n                        assert r[\'synthesis_calls\'] == r[\'E0_calls\'] == 1 and not r[\'forbidden_imports\']\n                        records[r[\'id\']] = r\n                b.write_data(HERE / (\'runtime-batch-\' + mode + \'.json\'), encode(dict(records=records,\n                    all_hash_match=True, profile=profiles[mode])), job)\n                outputs[mode] = records\n        print(mode, \'96件のhash一致\', flush=True)\n    cli = []\n    for request in [reqs[0], reqs[-1]]:\n        for mode in [\'normal\', \'isolated\']:\n            with managed_job(b,NAME, \'render\', \'CLI \' + mode + \'/\' + request[\'id\'], count=1 if request[\'method\']==\'native\' else 2, reserve_bytes=10_000_000) as job:\n                with managed_job(b,NAME, \'dsp\', \'CLI E0 \' + mode + \'/\' + request[\'id\'], reserve_bytes=100_000):\n                    with b.workspace(job, \'単独CLI ライブラリ初期化\') as (work, env):\n                        output = json.loads(execute([str(PYTHON), \'-I\', \'-B\',\n                            str(HERE / \'runtime-bundle/runtime.py\'), \'--text\', request[\'text\'],\n                            \'--method\', request[\'method\'], \'--speed\', str(request[\'speed\']),\n                            \'--pitch\', str(request[\'pitch\'])], env, profile(b, work, mode == \'isolated\')))\n                    data = base64.b64decode(output[\'wav_base64\'])\n                    assert hashlib.sha256(data).hexdigest() == output[\'meta\'][\'sha256\'] == expected[request[\'id\']]\n                    b.write(HERE / \'runtime-cli\' / mode / (request[\'id\'] + \'.wav\'), data, job)\n                    cli.append(dict(id=request[\'id\'], mode=mode, sha256=output[\'meta\'][\'sha256\'], bit_match=True))\n    # 禁止資料は、論理参照と外部の実体、現在の入力と出力の全てを実際に拒否する。\n    logical = HERE / \'render/fir-gain-fresh-00/neutral/native.wav\'\n    blocked = [logical, logical.resolve(), HERE / \'protocol.json\', HERE / \'registration.json\',\n               PREVIOUS / \'protocol.json\', HERE / \'runtime-archives/normal.zip\',\n               (HERE / \'runtime-archives/normal.zip\').resolve()]\n    code = \'import json,socket; paths=\' + repr([str(p) for p in blocked]) + \'; a=[]\\n\'\n    code += "for p in paths:\\n try:\\n  open(p,\'rb\').close();a.append(False)\\n except PermissionError:a.append(True)\\n"\n    code += "s=socket.socket()\\ntry:s.bind((\'127.0.0.1\',0));net=False\\nexcept PermissionError:net=True\\nprint(json.dumps(dict(read_denied=a,network_denied=net)))"\n    with managed_job(b,NAME, \'audit\', \'論理/物理資料と通信の実拒否\', reserve_bytes=10_000_000) as job:\n        with b.workspace(job, \'拒否probe\') as (work, env):\n            proof = json.loads(execute([str(PYTHON), \'-I\', \'-B\', \'-c\', code], env, profile(b, work, True)))\n        assert all(proof[\'read_denied\']) and proof[\'network_denied\']\n        b.save(HERE / \'denial-probe.json\', dict(proof, paths=[str(p) for p in blocked]), job)\n        pairs = [dict(id=r[\'id\'], bit_match=outputs[\'normal\'][r[\'id\']][\'sha256\'] ==\n            outputs[\'isolated\'][r[\'id\']][\'sha256\']) for r in reqs]\n        assert len(pairs) == 96 and all(r[\'bit_match\'] for r in pairs)\n        b.save(HERE / \'runtime-audit.json\', dict(passed=True, pairs=pairs, CLI=cli,\n            new_render_calls=326, new_DSP_calls=196, internal_MLSA_helpers=130, denial_probe=proof,\n            final_non_neural=True, quality_certified=False), job)\n    print(\'通常/隔離96組・CLI4件・読取/通信拒否を確認\', flush=True)\n\n\ndef asr(name):\n    b = Budget()\n    assert read(HERE / \'runtime-audit.json\')[\'passed\']\n    engine = read(HERE / \'engine-contract.json\')\n    with managed_job(b,NAME, \'audit\', \'ASRモデル・辞書・正規化hash照合 \' + name, reserve_bytes=100_000):\n        for n, h in engine[\'asr_model_hashes\'].items():\n            assert digest(REPO / n) == h, n\n        assert digest(OLD / \'diagnostics.py\') == engine[\'normalizer_source_sha256\']\n        cfg = engine[\'reading_diagnostic\'][\'contract\']\n        for n, h in cfg[\'dictionary_files\'].items():\n            assert digest(Path(cfg[\'dictionary_path\']) / n) == h\n        assert digest(cfg[\'library\']) == cfg[\'library_sha256\']\n    with managed_job(b,NAME, \'ai\', \'固定ASR96 \' + name, count=96, reserve_bytes=12_000_000) as job:\n        with b.workspace(job, name + \' 認識器初期化・評価\') as (work, env):\n            result = json.loads(execute([str(PYTHON), \'-B\', str(HERE / \'asr_worker.py\'),\n                \'--engine\', name], env, profile(b, work, False)))\n        assert len(result[\'rows\']) == result[\'ai_calls\'] == 96\n        rows = []\n        for value in result[\'rows\']:\n            target = HERE / \'asr\' / name / (value[\'id\'] + \'.json\')\n            b.write_data(target, encode(value), job)\n            rows.append(dict(path=str(target.relative_to(REPO)), sha256=digest(target)))\n        b.save(HERE / (\'asr-manifest-\' + name + \'.json\'), dict(rows=rows, new_ai=96,\n            reused=0, optimization_after_asr=False), job)\n    print(name, \'96件保存完了\', flush=True)\n\n\ndef main():\n    parser = argparse.ArgumentParser()\n    parser.add_argument(\'stage\', choices=[\'comparison\', \'isolate\', \'asr\', \'comparison-worker\'])\n    parser.add_argument(\'--engine\', choices=[\'whisper\', \'reazon\'])\n    parser.add_argument(\'--render-job\')\n    parser.add_argument(\'--dsp-job\')\n    args = parser.parse_args()\n    verify()\n    if args.stage.endswith(\'-worker\'):\n        globals()[args.stage.replace(\'-\', \'_\')](args.render_job, args.dsp_job)\n        return\n    b = Budget()\n    b.recover()\n    if args.stage == \'comparison\':\n        computation(args.stage)\n    elif args.stage == \'isolate\':\n        isolate()\n    elif args.stage == \'asr\':\n        assert args.engine\n        asr(args.engine)\n    print(b.reconcile(), flush=True)\n\n\nif __name__ == \'__main__\':\n    main()\n'
        b.write(HERE/'controller.py',controller.encode(),j)
        for name in ('asr_worker.py','runtime_batch.py','measurement.py'):
            text=(ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1'/name).read_text()
            if name in ('asr_worker.py','runtime_batch.py'):text=re.sub(r'(?<![A-Za-z0-9_])64(?![A-Za-z0-9_])','96',text)
            b.write(HERE/name,text.encode(),j)
        runtime=(BASE/'runtime-bundle/runtime.py').read_text()
        runtime=runtime.replace('from world_renderer2 import synthesize as world_synthesize\n','')
        runtime=runtime.replace('from hts_arrays import synthesize as hts_synthesize','from fft_fir import synthesize as shape_synthesize')
        runtime=runtime.replace("METHODS=['native','calibrated','voicing','hts_native','hts_calibrated','hts_voicing']","METHODS=['native','fft_fir','fft_loggain']")
        runtime=runtime.replace("transform(method[4:] if method.startswith('hts_') else method,", "transform('calibrated',")
        start=runtime.index("        if method.startswith('hts_'):");end=runtime.index('        assert engine.snapshot()',start)
        runtime=runtime[:start]+"        raw,conversion=shape_synthesize(params,settings,method)\n"+runtime[end:]
        b.write(HERE/'runtime.py',runtime.encode(),j)
        old=(BASE/'prepare.py').read_text();node=next(n for n in ast.parse(old).body if isinstance(n,ast.FunctionDef) and n.name=='inputs')
        inp=ast.get_source_segment(old,node).replace("ROOT / 'vocoder-f0-candidate-pool-0001.json'", "HERE / 'candidate-pool.json'").replace('voc-fresh-','fir-gain-fresh-')
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
        b.write(HERE/'shape.dylib',(MECHANISM/'runtime-bundle/shape.dylib').read_bytes(),j)
        assert digest(HERE/'shape.c')==digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')
        b.save(HERE/'build-audit.json',dict(binary_sha256=digest(HERE/'shape.dylib'),source_sha256=digest(HERE/'shape.c'),inherited_binary_exact=True,mechanism_seal_sha256=digest(MECHANISM/'artifact-seal.json'),new_compilation=False),j)
        bundle=HERE/'runtime-bundle';mapping={}
        for n in read(BASE/'runtime-bundle/manifest.json')['files']:
            if n.startswith('packages-v2/') or n in ('world_renderer2.py','LICENSE-WORLD.txt','runtime.py','runtime_batch.py'):continue
            mapping[n]=BASE/'runtime-bundle'/n
        mapping.update({n:HERE/n for n in ('runtime.py','runtime_batch.py','shape_arrays.py','shape.dylib','fft_fir.py')})
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
    b.save(ROOT/'progress-0076.json',dict(active_campaign=NAME,next='登録commit/push→機構hash照合→96波形三方式比較（内部helper別計数）→通常/隔離/CLI→二ASR→全MCP応答監査/封印',new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(b.reconcile(),flush=True)

def run(stage,engine=None):
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    if stage=='fixture':
        with job(b,'audit','同一C機構資格のhash照合と追補',size=1000000) as j:
            assert digest(HERE/'shape.dylib')==digest(MECHANISM/'runtime-bundle/shape.dylib')
            assert digest(HERE/'shape.c')==digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/shape.c')
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
