"""原励振と共有係数を保ち、MLSAの周波数軸だけを独立因子にする。"""
import ast
from pathlib import Path
from budget import ROOT, digest
from long_horizon_budget import LongHorizonBudget as Budget
from prepare_fractional_pulse_20261008 import constant

PAPER='https://sp-nitech.github.io/sptk/latest/main/mglsadf.html'
C_SOURCE=r'''/* 原励振を一度だけ呼び、フィルタのalphaだけを変更する別版。 */
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
int shape_mc2b(const double *mc,double alpha,double *b,size_t n) {
    if(!mc||!b||n!=35||!isfinite(alpha)||fabs(alpha)>=1.)return 0;
    for(size_t i=0;i<n;i++)if(!isfinite(mc[i]))return 0;
    HTS_mc2b(mc,b,34,alpha);return 1;
}
int shape_render(const double *mcp,const double *lf0,const double *lpf,
    size_t frames,size_t cols,size_t nlpf,int selected,double *out,double *period,
    double *counter,double *source,uint8_t *event,size_t samples) {
    if(capacity || !mcp||!lf0||!lpf||!out||!period||!counter||!source||!event || frames<1 || frames>6000 ||
       cols!=35 || nlpf<1 || nlpf>63 || nlpf%2!=1 || samples!=frames*240 || (selected<0||selected>2))return 0;
    for(size_t f=0;f<frames;f++) {
        if(!isfinite(lf0[f]) || (lf0[f]!=LZERO&&(exp(lf0[f])<70.||exp(lf0[f])>800.)))return 0;
        for(size_t j=0;j<35;j++)if(!isfinite(mcp[f*35+j]))return 0;
        for(size_t j=0;j<nlpf;j++)if(!isfinite(lpf[f*nlpf+j]))return 0;
    }
    double alpha=selected==1?.50:selected==2?.60:.55;
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
'''

WRAPPER=r'''"""共有MCPと原励振を保ち、実フィルタalphaだけを変更する入口。"""
import ctypes as C
import hashlib
from pathlib import Path
import numpy as np
from scipy import signal
from hts_arrays import validated,ah
_lib=C.CDLL(str(Path(__file__).resolve().parent/'shape.dylib'))
P=C.POINTER(C.c_double);U=C.POINTER(C.c_uint8);S=C.c_size_t
_fn=_lib.shape_render;_fn.restype=C.c_int;_fn.argtypes=[P,P,P,S,S,S,C.c_int,P,P,P,P,U,S]
_mc2b=_lib.shape_mc2b;_mc2b.restype=C.c_int;_mc2b.argtypes=[P,C.c_double,P,S]
MODES={'native':0,'alpha_low':1,'alpha_high':2}
ALPHA={'native':.55,'alpha_low':.50,'alpha_high':.60}
def mc2b(mc,alpha):
    x=np.ascontiguousarray(mc,dtype=np.float64);assert x.shape==(35,)
    b=np.empty(35);assert _mc2b(x.ctypes.data_as(P),alpha,b.ctypes.data_as(P),35)
    return b
def raw(params,settings,method):
    if method not in MODES:raise ValueError('未登録の周波数軸設定')
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
    return audio,dict(renderer='HTS-MLSA/周波数軸の独立因子',filter_method=method,effective_filter_alpha=ALPHA[method],model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},
        cycle_events=int(tr['event'].sum()),cycle_event_is_not_impulse_truth=True,
        original_excitation_noise_LPF_and_gain_unchanged=True,periodic_source_delay_samples=0,
        frequency_axis_rule='MCP35を変換せず、同じalphaをmc2bとMLSAへ渡す。周波数一様倍率/物理声道長ではない。',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

FIXTURE=r'''"""原波形/励振一致と独立したMLSA係数・周波数軸恒等式の検証。"""
import json,os,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(HERE/'runtime-bundle'))
import numpy as np
from hts_arrays import synthesize as original
from shape_arrays import raw,synthesize,mc2b,ALPHA
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
  for rich in (False,True):
    mcp=np.zeros((100,35));mcp[:,0]=7.
    if rich:mcp[:,1]=.35;mcp[:,2]=.15;mcp[:,6]=.12
    lf0=np.full((100,1),-1e10);lf0[20:80]=np.log(hz);params=[mcp,lf0,np.full((100,1),coefficient)]
    baseline,_=original(params,settings);native,_=synthesize(params,settings,'native');assert np.array_equal(baseline,native)
    a,ta=raw(params,settings,'native')
    for method in ('alpha_low','alpha_high'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        assert np.isfinite(z).all()
        if rich:assert not np.array_equal(a,z)
        else:assert np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,nonflat=rich,legacy_audio_exact=True,excitation_and_clock_exact=True,flat_filter_alpha_invariant=not rich))
mechanical=[];w=np.linspace(0,np.pi,1025);z=np.exp(-1j*w)
vectors=[np.r_[7.,np.zeros(34)],np.r_[7.,.35,np.zeros(33)],np.r_[7.,0.,0.,0.,.2,np.zeros(30)],np.r_[7.,.08*np.cos(np.arange(1,35))/np.arange(1,35)]]
for alpha in (.50,.55,.60):
 q=(z-alpha)/(1-alpha*z);phi1=(1-alpha*alpha)*z/(1-alpha*z)
 for idx,c in enumerate(vectors):
    b=mc2b(c,alpha);expected=np.empty(35);expected[-1]=c[-1]
    for j in range(33,-1,-1):expected[j]=c[j]-alpha*expected[j+1]
    assert np.array_equal(b,expected)
    a=sum(c[m]*q**m for m in range(35));v=b[0]+sum(b[m]*phi1*q**(m-1) for m in range(1,35))
    err=float(np.max(np.abs(a-v)));assert err<1e-12
    mechanical.append(dict(alpha=alpha,vector=idx,mc2b_exact=True,allpass_log_transfer_maxerr=err))
print(json.dumps(dict(passed=True,checks=checks,filter_identity_checks=mechanical,render=40,dsp=600,fixture_only=True,
    effective_alpha_only_factor=True,original_excitation_exact=True,frequency_warp_is_not_uniform_tract_scale=True,quality_certified=False)))
'''

POOL=dict(candidate_pool_short=['薄い板を持ち上げる。','茶碗に豆を盛る。','坂道で足を止める。','青い箱を畳む。','窓辺に鉢を置く。','木の影が伸びる。','井戸から水を汲む。','小鳥が垣根に止まる。'],
 candidate_pool_long=['夕飯の支度を終えて、父は庭の椅子に腰を下ろした。','小さな駅の待合室で、姉は本の続きを読むことにした。','道を尋ねた旅人に、少年は橋の向こうを指さした。','雨が上がったばかりの畑で、祖母が野菜の葉を確かめた。','浅い川の底に見える石を、弟は岸からじっと眺めていた。','冬の朝に窓を開けると、遠くの山が白く輝いて見えた。','緑の屋根の店で買った菓子を、家に帰って友人と分けた。','古い時計の針を合わせてから、母は壁にそっと掛け直した。'])

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='原励振/雑音/LPFと共有MCP35を固定したとき、MLSA周波数軸のalpha変更が新入力の音響診断・固定支持・二ASR内容保護へ与える因果効果は何か',
        variants=['native','alpha_low','alpha_high'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='元HTS alpha=.55、完全一致対照',alpha_low='実フィルタalpha=.50',alpha_high='実フィルタalpha=.60'),
        effective_alpha=dict(native=.55,alpha_low=.50,alpha_high=.60),
        fixed_control='全方式calibrated LF0、原有声相対輪郭・未補完MSD・duration・全3stream byte不変。周期/雑音/LPF/励振列も完全一致。HMM設定は元alpha=.55を保持し、実フィルタalphaを別記する。',
        normalization='MCP係数c0を含め変更なし。mc2bとMLSAへ同じ実alphaを渡す。volume1、出力gain.25、12ms fade、resample24k固定。全波形/周波数帯ごとの利得救済なし。実alpha変更に伴うフィルタ利得/包絡変化も因果効果に含む。',
        input='新16文×2条件×3方式=96。全履歴の文章/ラベル非衝突を波形前確認。P5未開封。',
        source=dict(url=PAPER,title='SPTK公式: mglsadf、MLSA伝達関数とall-pass constant',retrieved='2026-10-08',related_url='https://sp-nitech.github.io/sptk/latest/main/mc2b.html',scope='alphaとmc2bの意味を確認。既存固定HTS実装を独立版へ使用。周波数一様倍率/物理声道長/知覚改善は仮定しない。'),
        support='nativeから一度固定し全候補へ引継ぎ。欠測を除外しない。eligible/除外理由も保存。旧支持/249欠測と旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上で全件確認。短窓/動的/知覚へ資格を拡張しない。',content='二固定ASR各33群が原native以下。別コホートの悪化を相殺しない。',independence='全96通常/隔離、CLI4、禁止資料/通信の実拒否。'),
        estimates=dict(comparison_render=96,comparison_dsp=288,isolation_render=192,isolation_dsp=192,CLI_render=4,CLI_dsp=4,fixture_render=40,fixture_dsp=600,two_ASR_ai=192,total_without_retry=dict(render=332,dsp=1084,ai=192),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,
        controller_sha256=digest(Path(__file__)),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        frozen_previous_source_route='元nativeを保護するfractional pulse/同形状L2/DC比較は不通過を保存。係数微調整による同経路救済をせず、原励振へ戻して別因子を検証。',
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

def main():
    b=Budget();assert not b.snapshot()['jobs'];parent=ROOT/'hts_sinc_normalization_20261008.py';text=parent.read_text()
    for name,value in [('C_SOURCE',C_SOURCE),('WRAPPER',WRAPPER),('FIXTURE',FIXTURE)]:text=constant(text,name,"r'''"+value+"'''")
    text=constant(text,'POOL',repr(POOL));text=constant(text,'PAPER',repr(PAPER))
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    segment=ast.get_source_segment(text,node);assert text.count(segment)==1;text=text.replace(segment,REGISTRATION)
    text=text.replace('hts-sinc-normalization','hts-filter-warp').replace('normalization-fresh','filter-warp-fresh')
    text=text.replace("METHODS=['native','sinc','sinc_dc']","METHODS=['native','alpha_low','alpha_high']")
    text=text.replace("job(b,'render','sinc正規化の数値対照fixture',20","job(b,'render','フィルタ周波数軸の原波形対照fixture',40")
    text=text.replace("job(b,'dsp','sinc形状/位相・L2/DC条件・旧波形fixture',800","job(b,'dsp','全励振一致・MLSA係数/伝達関数恒等式fixture',600")
    text=text.replace('progress-0056.json','progress-0058.json').replace('fixture→64新入力比較','fixture→96新入力比較')
    text=text.replace('源形状の因子・全比較費とコードを生成前登録','原励振固定・フィルタ周波数軸・全比較費を生成前登録')
    text=text.replace('新共有源実験。','新共有フィルタ因子実験。').replace('共有HTSの周期源形状だけを変更し、','共有HTSのフィルタ周波数軸だけを変更し、')
    path=ROOT/'hts_filter_warp_20261008.py';ast.parse(text);b.write(path,text.encode())
    b.save(ROOT/'filter-warp-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),
        primary_original_native=True,original_excitation_checked_samplewise=True,all_parameters_unchanged=True,effective_alpha_only_factor=True,
        old_results_preserved=True,prior_fractional_normalization_route_closed=True,quality_goal_completed=False))
    print('原励振を保持したフィルタalpha三方式96件を生成前構築',flush=True)

if __name__=='__main__':main()
