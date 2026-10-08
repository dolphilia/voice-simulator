"""IR形状と対数利得の補間を分け、登録人工条件で時間表現を検証する。"""
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget
from hts_fft_fir_mechanism_20261008 import MODULE as ORIGINAL_MODULE

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-hts-fir-gain-mechanism-20261008-v1';NAME='hts-fir-gain-mechanism-v1'
PARENT=ROOT/'campaigns/nas-hts-fft-fir-mechanism-20261008-v1'
COMPARISON=ROOT/'campaigns/nas-hts-fft-fir-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

FILTER=r'''def log_gain(mc,alpha=.55):
    # mc2bのb0 = sum((-alpha)**m * mc[m])。波形から利得を推定しない。
    x=np.asarray(mc,dtype=np.float64);assert x.shape==(35,) and np.isfinite(x).all()
    return float(np.polynomial.polynomial.polyval(-alpha,x))
def filter_source(mc,source,interpolation='linear'):
    if interpolation not in ('linear','loggain'):raise ValueError('未登録の利得補間')
    m=np.asarray(mc,dtype=np.float64);x=np.asarray(source,dtype=np.float64)
    assert m.ndim==2 and m.shape[1]==35 and x.shape==(len(m)*240,) and np.isfinite(x).all()
    before=(ah(m),ah(x));y=np.empty(len(x));previous=kernel(m[0]);previous_log=log_gain(m[0]);u=np.arange(240)/240.
    for frame,c in enumerate(m):
        current=kernel(c);current_log=log_gain(c);start=frame*240;stop=start+240
        left=max(0,start-IR_LENGTH+1);past=x[left:stop]
        if start<IR_LENGTH-1:past=np.pad(past,(IR_LENGTH-1-start,0))
        assert len(past)==IR_LENGTH-1+240
        windows=np.lib.stride_tricks.sliding_window_view(past,IR_LENGTH)[:,::-1]
        if interpolation=='linear':
            a=windows@previous;b=windows@current;y[start:stop]=a+u*(b-a)
        else:
            a=windows@(previous/np.exp(previous_log));b=windows@(current/np.exp(current_log))
            y[start:stop]=(a+u*(b-a))*np.exp(previous_log+u*(current_log-previous_log))
        previous=current;previous_log=current_log
    assert before==(ah(m),ah(x)) and np.isfinite(y).all()
    return y
'''

def make_module():
    text=ORIGINAL_MODULE.replace('__L__','2048');node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='filter_source')
    text=text.replace(ast.get_source_segment(text,node),FILTER.rstrip())
    text=text.replace("('native','fft_fir')","('native','fft_fir','fft_loggain')")
    text=text.replace("filter_source(params[0],tr['excitation'])","filter_source(params[0],tr['excitation'],'loggain' if method=='fft_loggain' else 'linear')")
    text=text.replace("IR_LENGTH if method=='fft_fir' else None","IR_LENGTH if method!='native' else None").replace("FFT_LENGTH if method=='fft_fir' else None","FFT_LENGTH if method!='native' else None")
    text=text.replace("IR_interpolation='前frame/current IRの出力crossfade j/240'","IR_interpolation='対数利得を分離し形状crossfade j/240' if method=='fft_loggain' else '前frame/current IRの出力crossfade j/240'")
    ast.parse(text);return text

FIXTURE=r'''"""固定人工条件で利得式・独立畳み込み・過去参照・原HTSを照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from minphase import kernel as old_C_kernel
from fft_fir import kernel,filter_source,log_gain,IR_LENGTH,FFT_LENGTH
rng=np.random.default_rng(1047047);mc=np.zeros((8,35));mc[:,0]=np.linspace(0.,1.,8)
mc[1,1]=.3;mc[2,2]=-.25;mc[3,1:4]=[.35,.15,.12];mc[4:,1:]=rng.normal(0.,.04,(4,34))*np.exp(-np.arange(1,35)/12.)
spectral=[]
for i,c in enumerate(mc):
 for alpha in (0.,.55):
    h=kernel(c,alpha);ref=old_C_kernel(c,alpha);b0=sum(float(v)*(-alpha)**j for j,v in enumerate(c))
    error=float(np.max(np.abs(h[:1024]-ref))/max(float(np.max(np.abs(ref))),1e-12))
    gain_error=abs(log_gain(c,alpha)-b0);assert error<=1e-10 and gain_error<=1e-12
    spectral.append(dict(case=i,alpha=alpha,C_prefix_relative_error=error,independent_b0_error=gain_error,passed=True))
def independent(mc,x,mode):
    h=[kernel(c) for c in mc];g=[sum(float(v)*(-.55)**j for j,v in enumerate(c)) for c in mc];out=np.empty(len(x));u=np.arange(240)/240.
    for frame,current in enumerate(h):
        previous=h[max(0,frame-1)];gp=g[max(0,frame-1)];gc=g[frame];start=frame*240;stop=start+240
        if mode=='linear':
            a=signal.convolve(x,previous,method='direct')[start:stop];b=signal.convolve(x,current,method='direct')[start:stop];out[start:stop]=a+u*(b-a)
        else:
            a=signal.convolve(x,previous/np.exp(gp),method='direct')[start:stop];b=signal.convolve(x,current/np.exp(gc),method='direct')[start:stop]
            out[start:stop]=((1.-u)*a+u*b)*np.exp((1.-u)*gp+u*gc)
    return out
convolution=[]
for source in ('impulse','noise','step','zeros'):
    frames=8;p=np.zeros((frames,35));p[:,0]=np.linspace(.1,.8,frames);p[:,1]=np.linspace(.1,.35,frames)
    if source=='impulse':x=np.zeros(frames*240);x[0]=1.;x[720]=-.5
    elif source=='noise':x=rng.normal(0.,.1,frames*240)
    elif source=='step':x=np.r_[np.zeros(600),np.ones(frames*240-600)*.1]
    else:x=np.zeros(frames*240)
    for mode in ('linear','loggain'):
        y=filter_source(p,x,mode);z=independent(p,x,mode);error=float(np.max(np.abs(y-z)));assert error<=1e-10
        xp=x.copy();xp[960:]+=1.;yp=filter_source(p,xp,mode);assert np.array_equal(y[:960],yp[:960])
        convolution.append(dict(source=source,mode=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
pure_gain=[]
for direction in ('up','down'):
    p=np.zeros((8,35));p[:,0]=np.linspace(.1,1.8,8) if direction=='up' else np.linspace(1.8,.1,8)
    params=[p,np.full((8,1),np.log(220.)),np.ones((8,1))];native,tr=raw(params,settings,'native');x=tr['excitation'];u=np.arange(240)/240.
    expected_log=np.concatenate([np.exp(p[max(0,i-1),0]+u*(p[i,0]-p[max(0,i-1),0])) for i in range(8)])*x
    # HTSは係数を反復加算するので、ここは数学的一致の許容誤差。byte一致とは呼ばない。
    native_error=float(np.max(np.abs(native-expected_log)));assert native_error<=1e-10
    for mode in ('linear','loggain'):
        y=filter_source(p,x,mode)
        expected=expected_log if mode=='loggain' else np.concatenate([np.exp(p[max(0,i-1),0])+u*(np.exp(p[i,0])-np.exp(p[max(0,i-1),0])) for i in range(8)])*x
        error=float(np.max(np.abs(y-expected)));assert error<=1e-10
        pure_gain.append(dict(direction=direction,mode=mode,max_abs_error=error,native_log_gain_error=native_error,passed=True))
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((20,35));mcp[:,0]=5.;mcp[:,1]=np.linspace(.1,.35,20);mcp[:,2]=.15
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mcp,lf0,np.full((20,1),coefficient)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,tr=raw(params,settings,'native')
    for mode in ('linear','loggain'):assert np.isfinite(filter_source(mcp,tr['excitation'],mode)).all()
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_wave_exact=True,input_streams_exact=True,source_sha256=ah(tr['excitation']),passed=True))
print(json.dumps(dict(passed=True,spectral_checks=spectral,convolution_checks=convolution,pure_gain_checks=pure_gain,source_checks=source_checks,
    IR_length=IR_LENGTH,FFT_length=FFT_LENGTH,render=86,dsp=46,
    render_breakdown=dict(FFT_kernel=16,C_reference_kernel=16,driving_signal=4,convolution_filter=16,independent_convolution=8,pure_gain_native=2,pure_gain_filter=4,pure_gain_expected=4,original_HTS=4,observed_HTS=4,source_filter=8),
    dsp_breakdown=dict(spectral=16,convolution=8,causal=8,pure_gain=4,native_gain=2,source_check=8),
    direct_past_only=True,extra_alignment_latency_samples=0,scope='登録人工MCPの利得・形状補間機構のみ。新日本語の工学/二ASR/知覚は別契約。',quality_certified=False)))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(PARENT/'aggregate-summary.json')['mechanical_fixture_passed']
    assert read(COMPARISON/'aggregate-summary.json')['real_MCP_grid_audit']['passed']
    module=make_module();ast.parse(FIXTURE)
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=8,audit=10,render=258,dsp=138,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='IR全体の算術補間と、形状/対数利得分離補間を独立式で区別できるか。静的応答を変えず時間表現だけを検証する。',
        factor='b0=sum((-alpha)**m * MCP[m]);IR/exp(b0)の形状を算術補間し、exp(b0_prev+u*(b0_current-b0_prev))を出力に適用。u=j/240。',
        controls='alpha=.55/IR2048/FFT16384/因果参照/源時計/LPF/波形後処理を保持。MLSA全係数時間補間との同一性は主張しない。波形別gain推定なし。',
        thresholds=dict(C_prefix_relative_error=1e-10,b0_absolute_error=1e-12,convolution_absolute_error=1e-10,pure_gain_absolute_error=1e-10,native_gain_absolute_error=1e-10,causal_prefix_exact=True,original_native_exact=True),
        costs=dict(render=86,dsp=46,maximum_seconds=3000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),limits=limits,
        source=dict(urls=['https://sp-nitech.github.io/sptk/latest/main/mc2b.html','https://sp-nitech.github.io/sptk/latest/main/mglsadf.html'],
            original_gain_source='campaigns/nas-hts-minphase-mechanism-20261008-v1/vendor/HTS_vocoder_shaped.c:903-945',original_gain_source_sha256=digest(ROOT/'campaigns/nas-hts-minphase-mechanism-20261008-v1/vendor/HTS_vocoder_shaped.c'),
            parent_seal_sha256=digest(PARENT/'artifact-seal.json'),previous_failed_speech_seal_sha256=digest(COMPARISON/'artifact-seal.json')),
        module_sha256=hashlib.sha256(module.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='機構通過時だけ新16文のnative/線形IR/対数利得分離IR三方式96波形を登録。FIR経路三回目の全件不通過なら同補間/係数救済を封印し、別測定資格へ進む。',
        old_FIR1024_and_2048_results_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','利得と形状を分離する時間表現の出力前登録',reserve_bytes=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'fft_fir.py',module.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib','shape_arrays.py','shape.dylib','minphase.py'):
            b.write(HERE/'runtime-bundle'/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        b.write(HERE/'runtime-bundle/fft_fir.py',module.encode(),j);b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={str(p.relative_to(HERE/'runtime-bundle')):digest(p) for p in (HERE/'runtime-bundle').rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0074.json',dict(active_campaign=NAME,next=reg['next'],new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json')
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    r=b.reserve(NAME,'render','二利得補間の源・畳み込み・人工HTS全生成',86,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','利得式・静的prefix・畳み込み・因果性・原HTS照合',46,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'利得補間fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','人工機構の範囲・二時間表現・hash・費用・一時回収の終了照合',reserve_bytes=2000000) as j:
        assert fixture['passed'] and sum(fixture['render_breakdown'].values())==86 and sum(fixture['dsp_breakdown'].values())==46
        for n,h in contract['files'].items():assert digest(HERE/n)==h,n
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,IR_length=2048,FFT_length=16384,log_gain_formula_verified=True,pure_gain_HTS_tolerance_verified=True,original_native_wave_exact=True,causal_prefix_exact=True,real_unknown_MCP_or_speech_qualified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.write(HERE/'report.md',('# FIR形状と対数利得の補間機構\n\n16人工MCPの独立C prefix/係数変換式、4駆動源×2時間表現の独立直接畳み込みと因果prefix、上昇/下降の純利得×2方式、4HTS条件の原native完全一致・入力列不変を検査した。IR2048/FFT16384を保持し、波形からgainを推定しない。\n\n原HTSのb0は線形に時間補間され、源にexp(b0)を掛ける。対数利得分離はこの因子のみを式で保護し、形状の補間やMLSA状態まで同一とは呼ばない。人工純利得の反復浮動小数点加算は許容誤差で照合した。\n\n資格は人工機構に限る。前の日本語FIR1024/2048不通過・旧欠測を保持する。次は未使用16文の三方式比較。三回目も保護不通過ならFIRの同補間/係数救済は封印する。知覚資格なし・P5未開封・品質未達。\n\n一次資料: [SPTK mc2b](https://sp-nitech.github.io/sptk/latest/main/mc2b.html)、[mglsadf](https://sp-nitech.github.io/sptk/latest/main/mglsadf.html)。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='FIR-gain-mechanism-completed',active_campaign=None,next='未使用16文の三方式96波形を生成前登録し、三回目の不通過でFIR同補間/係数救済を封印',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0075.json',dict(latest_completed=NAME,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args()
    register() if a.stage=='register' else run()
