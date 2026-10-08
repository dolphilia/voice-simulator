"""原nativeを保護し、共通遅延と周期内位置補間を分離した別版を生成する。"""
import ast
from pathlib import Path
from budget import ROOT,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
import hts_glottal_shape_20261008 as old

KERNEL=r'''/* 有声開始はphase原点0。それ以外は元clockの端数を同じcell内で補間する。 */
static double previous_period=0.;
static double *phase_out=NULL;
int shape_kernel(double p,int selected,double remainder,double *out,size_t n) {
    if(!isfinite(p)||p<60.||p>48000./70.||n!=9||selected<1||selected>3||!isfinite(remainder)||remainder<0.||remainder>1.)return 0;
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
    double scale=sqrt(p/energy);for(size_t i=0;i<n;i++)out[i]*=scale;
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
MODES={'native':0,'latency':1,'linear':2,'sinc':3}
def kernel(period,remainder,method):
    a=np.empty(9);assert method in ('latency','linear','sinc')
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
        energy_per_cycle='period:LPF前kernelの二乗和。出力/雑音/LPFは固定。',
        waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

FIXTURE=r'''"""元波形一致・位相cell・エネルギー・直接周波数応答の工程検証。"""
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
    for method in ('latency','linear','sinc'):
        z,tz=raw(params,settings,method);assert all(np.array_equal(ta[k],tz[k]) for k in ta)
        if coefficient==0.:assert np.array_equal(a,z)
        else:assert not np.array_equal(a,z)
    checks.append(dict(hz=hz,lpf=coefficient,legacy_audio_exact=True,all_clock_and_phase_exact=True,zero_LPF_exact=coefficient==0.))
phase_checks=[]
for hz in (80.,110.,220.,280.,400.,800.):
 for remainder in np.linspace(0,1,11):
    response={};target=4-remainder;p=48000/hz;w=2*np.pi*hz/48000
    for method in ('latency','linear','sinc'):
        k=kernel(p,float(remainder),method);assert np.isfinite(k).all() and abs(float(np.sum(k*k))-p)<1e-10
        H=np.dot(k,np.exp(-1j*w*np.arange(9)));error=float(abs(np.angle(H*np.exp(1j*w*target))/w));response[method]=error
        if method=='linear':assert abs(float(np.dot(np.arange(9),k)/k.sum())-target)<1e-12
    assert abs(response['latency']-remainder)<1e-12
    assert response['linear']<=max(.05,remainder+1e-9) and response['sinc']<=max(.05,remainder+1e-9)
    phase_checks.append(dict(hz=hz,remainder=float(remainder),phase_error_samples=response))
print(json.dumps(dict(passed=True,checks=checks,phase_checks=phase_checks,render=24,dsp=900,fixture_only=True,mechanical_phase_is_not_audible_pitch_truth=True,quality_certified=False)))
'''

REGISTRATION='''reg=dict(campaign=NAME,status='registered_before_output',question='元pulseを対照に、周期内位置の整数丸めと共通遅延/線形/窓付きsincを分離して、位置誤差・固定支持・内容保護への因果効果を検証する',
        variants=['native','latency','linear','sinc'],conditions=dict(neutral=dict(speed=1.,requested_f0=220.),higher=dict(speed=1.15,requested_f0=280.)),
        factor_rules=dict(native='元HTS励振、完全一致対照',latency='周期pulseだけ4sample遅延、noiseと全時計不変',linear='同遅延下でcell端数を2tap線形補間',sinc='同遅延下で9tap raised-cosine窓sinc補間'),
        phase_definition='有声開始の原点0。それ以外はclip(counter+1-period,0,1)。native丸めと各補間の共通機械clock。瞬時F0/知覚truthと呼ばない。',
        energy='各周期kernel二乗和period。出力gain.25、noise、MCP、LPF、全clock不変。出力後の音量調整なし。',
        fixed_control='全方式calibrated LF0、原有声相対輪郭・未補完MSD・duration・全3stream byte不変。',
        input='新16文×2条件×4方式=128。全履歴の文章/ラベル非衝突を波形前確認。P5未開封。',
        source=dict(url=PAPER,title='Julius O. Smith, Physical Audio Signal Processing: Windowed Sinc Interpolation',retrieved='2026-10-08',scope='補間原理の一次解説。9tapの独自実装、最適設計や聴取品質の再現は主張しない。'),
        support='nativeから一度固定し全候補へ引継ぎ。欠測を除外しない。eligible/除外理由も保存。旧支持/249欠測と旧判定不変。',
        gates=dict(engineering='E0、DIO/全体ACF両中央値±1半音、ACF confidence≥.6、固定支持3以上で全件確認。短窓/動的/知覚へ資格を拡張しない。',content='二固定ASR各33群が原native以下。別コホートの悪化を相殺しない。',independence='全128通常/隔離、CLI4、禁止資料/通信の実拒否。'),
        estimates=dict(comparison_render=128,comparison_dsp=384,isolation_render=256,isolation_dsp=256,CLI_render=4,CLI_dsp=4,fixture_render=24,fixture_dsp=900,two_ASR_ai=256,total_without_retry=dict(render=412,dsp=1544,ai=256),maximum_seconds=11000,external_peak=500000000,temporary_peak=16000000,temporary_write=32000000,RAM_gb=8,closeout_Git_included=True),
        limits=limits,technical_retry_per_job=2,technical_retry_campaign=10,failed_consumption_retained=True,
        controller_sha256=digest(Path(__file__)),base_seal_sha256=digest(BASE/'artifact-seal.json'),
        perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)'''

POOL=dict(candidate_pool_short=['岩の上に苔が育つ。','夜空に星が滲む。','赤い紐をほどく。','小瓶に塩を入れる。','波間に鳥が浮く。','細い枝が折れる。','砂浜に跡が残る。','道の端で鈴を拾う。'],
    candidate_pool_long=['春の夕暮れに、川岸の細い道をゆっくり歩いて家へ帰った。','花屋の前を通ると、淡い色の花束がいくつも並んでいた。','棚の隅にあった小さな瓶を、弟が大事そうに手で包んだ。','遠くの森から鳥の声が届くので、窓を開けて耳を澄ました。','昨日見つけた青い石を、机の上の丸い皿にそっと置いた。','薄暗い廊下の奥で、古い戸棚の扉が静かに閉じられた。','日曜日の朝に、祖母と庭の鉢を一つずつ日向へ運んだ。','海の方から風が吹いてきたので、帽子を片手で押さえた。'])

def constant(text,name,value):
    node=next(n for n in ast.parse(text).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in n.targets))
    segment=ast.get_source_segment(text,node);assert text.count(segment)==1
    return text.replace(segment,name+'='+value)

def main():
    b=Budget();assert not b.snapshot()['jobs']
    parent=ROOT/'hts_glottal_difference_20261008.py';text=parent.read_text()
    c=old.C_SOURCE[:old.C_SOURCE.index('/* 流量の上昇')]+KERNEL+old.C_SOURCE[old.C_SOURCE.index('int shape_render('):]
    c=c.replace('double *counter,uint8_t *event,size_t samples)','double *counter,double *phase,uint8_t *event,size_t samples)')
    c=c.replace('!counter||!event','!counter||!phase||!event').replace('(selected!=0&&selected!=1)','(selected<0||selected>3)')
    c=c.replace('cursor=observed=0;capacity=samples;', 'cursor=observed=0;previous_period=0.;phase_out=phase;capacity=samples;')
    c=c.replace('period_out=counter_out=NULL;event_out=NULL;', 'period_out=counter_out=phase_out=NULL;event_out=NULL;')
    text=constant(text,'C_SOURCE',"r'''"+c+"'''")
    text=constant(text,'WRAPPER',"r'''"+WRAPPER+"'''");text=constant(text,'FIXTURE',"r'''"+FIXTURE+"'''");text=constant(text,'POOL',repr(POOL))
    node=next(n for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='reg' for t in n.targets) and isinstance(n.value,ast.Call))
    segment=ast.get_source_segment(text,node);assert text.count(segment)==1;text=text.replace(segment,REGISTRATION)
    text=text.replace('hts-glottal-difference','hts-fractional-pulse').replace('difference-fresh','fractional-fresh')
    text=text.replace('render=1000,dsp=2200,ai=576','render=1400,dsp=6000,ai=768')
    text=text.replace(".replace('192','96').replace('576','288').replace('385','193').replace('388','196')", ".replace('192','128').replace('576','384').replace('385','257').replace('388','260')")
    text=text.replace("text=(BASE/name).read_text().replace('192','96')", "text=(BASE/name).read_text().replace('192','128')")
    text=text.replace("METHODS=['native','rosenberg','difference2']", "METHODS=['native','latency','linear','sinc']")
    text=text.replace('expected_records=96','expected_records=128').replace('progress-0051.json','progress-0054.json')
    text=text.replace("job(b,'render','源形状の数値対照fixture',20", "job(b,'render','pulse補間の数値対照fixture',24")
    text=text.replace("job(b,'dsp','kernelエネルギー・時計・旧波形一致fixture',60", "job(b,'dsp','kernelエネルギー・位相・直接応答・旧波形fixture',900")
    text=text.replace("PAPER='https://www.fon.hum.uva.nl/david/ma_ssp/2007/rosenberg_JASA_1971.pdf'", "PAPER='https://ccrma.stanford.edu/~jos/pasp/Windowed_Sinc_Interpolation.html'")
    path=ROOT/'hts_fractional_pulse_20261008.py';ast.parse(text);b.write(path,text.encode())
    b.save(ROOT/'fractional-pulse-source-derivation.json',dict(parent_sha256=digest(parent),generator_sha256=digest(Path(__file__)),controller_sha256=digest(path),
        original_native_is_primary_content_control=True,latency_factor_separate=True,all_four_variants_frozen_before_output=True,phase_not_audible_truth=True,quality_goal_completed=False))
    print('元nativeを保護した四方式128件の生成前ソースを保存',flush=True)

if __name__=='__main__':main()
