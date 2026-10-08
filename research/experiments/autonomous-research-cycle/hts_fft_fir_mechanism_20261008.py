"""全MCP検査で固定した長さのFFT IRと直接因果畳み込みを、別fixtureで検証する。"""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-hts-fft-fir-mechanism-20261008-v1';NAME='hts-fft-fir-mechanism-v1'
CUTOFF=ROOT/'campaigns/nas-hts-fir-cutoff-qualification-20261008-v1'
PARENT=ROOT/'campaigns/nas-hts-minphase-comparison-20261008-v1'
PYTHON=REPO/'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

MODULE=r'''"""MCP→有限gridの最小位相IR。現入力から計算し、保存軌跡は読まない。"""
import hashlib
import numpy as np
from scipy import signal
from hts_arrays import ah
from shape_arrays import raw
IR_LENGTH=__L__
FFT_LENGTH=16384
_q=np.exp(-2j*np.pi*np.arange(FFT_LENGTH//2+1)/FFT_LENGTH)
def kernel(mc,alpha=.55):
    x=np.asarray(mc,dtype=np.float64);assert x.shape==(35,) and np.isfinite(x).all() and abs(alpha)<1.
    a=(_q-alpha)/(1.-alpha*_q)
    target=np.exp(np.polynomial.polynomial.polyval(a,x))
    h=np.fft.irfft(target,n=FFT_LENGTH)[:IR_LENGTH].copy()
    assert np.isfinite(h).all()
    return h
def filter_source(mc,source):
    m=np.asarray(mc,dtype=np.float64);x=np.asarray(source,dtype=np.float64)
    assert m.ndim==2 and m.shape[1]==35 and x.shape==(len(m)*240,) and np.isfinite(x).all()
    before=(ah(m),ah(x));y=np.empty(len(x));previous=kernel(m[0]);u=np.arange(240)/240.
    for frame,c in enumerate(m):
        current=kernel(c);start=frame*240;stop=start+240
        left=max(0,start-IR_LENGTH+1);past=x[left:stop]
        if start<IR_LENGTH-1:past=np.pad(past,(IR_LENGTH-1-start,0))
        assert len(past)==IR_LENGTH-1+240
        windows=np.lib.stride_tricks.sliding_window_view(past,IR_LENGTH)[:,::-1]
        # 各行はその出力時刻以前だけを参照。FFT convolutionのblock漏れを使わない。
        a=windows@previous;b=windows@current;y[start:stop]=a+u*(b-a)
        previous=current
    assert before==(ah(m),ah(x)) and np.isfinite(y).all()
    return y
def synthesize(params,settings,method):
    if method not in ('native','fft_fir'):raise ValueError('未登録のFFT FIR方式')
    native,tr=raw(params,settings,'native')
    out=native if method=='native' else filter_source(params[0],tr['excitation'])
    audio=signal.resample_poly(out/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    return audio,dict(renderer='HTS-MLSA' if method=='native' else 'MCP-FFT-causal-FIR',filter_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:hashlib.sha256(v.tobytes()).hexdigest() for k,v in tr.items()},cycle_events=int(tr['event'].sum()),
        cycle_event_is_not_impulse_truth=True,original_excitation_noise_LPF_unchanged=True,periodic_source_delay_samples=0,
        render_calls_including_internal_MLSA=1 if method=='native' else 2,FIR_length=IR_LENGTH if method=='fft_fir' else None,
        FFT_length=FFT_LENGTH if method=='fft_fir' else None,IR_interpolation='前frame/current IRの出力crossfade j/240',
        per_waveform_gain_rescue=False,waveform_pitch_verified=False,saved_waveform_analysis_used=False,neural_model=False,utterance_lookup=False)
'''

FIXTURE=r'''"""登録人工MCP、独立C prefix、直接畳み込み、有声/無声を照合する。"""
import sys,json,os,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent;assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from minphase import kernel as old_C_kernel
from fft_fir import kernel,filter_source,IR_LENGTH,FFT_LENGTH
rng=np.random.default_rng(1045045);mc=np.zeros((8,35));mc[:,0]=np.linspace(0.,1.,8)
mc[1,1]=.3;mc[2,2]=-.25;mc[3,1:4]=[.35,.15,.12];mc[4:,1:]=rng.normal(0.,.04,(4,34))*np.exp(-np.arange(1,35)/12.)
spectral=[]
for i,c in enumerate(mc):
 for alpha in (0.,.55):
    h=kernel(c,alpha);ref=old_C_kernel(c,alpha)
    error=float(np.max(np.abs(h[:1024]-ref))/max(float(np.max(np.abs(ref))),1e-12))
    assert error<=1e-10 and np.isfinite(h).all()
    spectral.append(dict(case=i,alpha=alpha,C_prefix_relative_error=error,passed=True))
def independent(mc,x):
    h=[kernel(c) for c in mc];out=np.empty(len(x));u=np.arange(240)/240.
    for frame,current in enumerate(h):
        previous=h[max(0,frame-1)];start=frame*240;stop=start+240
        a=signal.convolve(x,previous,method='direct')[start:stop]
        b=signal.convolve(x,current,method='direct')[start:stop]
        out[start:stop]=a+u*(b-a)
    return out
convolution=[]
for mode in ('impulse','noise','step','zeros'):
    frames=8;p=np.zeros((frames,35));p[:,0]=np.linspace(.1,.4,frames);p[:,1]=np.linspace(.1,.35,frames)
    if mode=='impulse':x=np.zeros(frames*240);x[0]=1.;x[720]=-.5
    elif mode=='noise':x=rng.normal(0.,.1,frames*240)
    elif mode=='step':x=np.r_[np.zeros(600),np.ones(frames*240-600)*.1]
    else:x=np.zeros(frames*240)
    y=filter_source(p,x);z=independent(p,x);error=float(np.max(np.abs(y-z)));assert error<=1e-10
    xp=x.copy();xp[960:]+=1.;yp=filter_source(p,xp);assert np.array_equal(y[:960],yp[:960])
    convolution.append(dict(source=mode,max_abs_error=error,causal_prefix_exact=True,passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source_checks=[]
for hz in (110.,280.):
 for coefficient in (0.,1.):
    mcp=np.zeros((20,35));mcp[:,0]=5.;mcp[:,1]=np.linspace(.1,.35,20);mcp[:,2]=.15
    lf0=np.full((20,1),-1e10);lf0[4:16]=np.log(hz);params=[mcp,lf0,np.full((20,1),coefficient)];before=[ah(v) for v in params]
    expected,_=original(params,settings);native,tr=raw(params,settings,'native');out=filter_source(mcp,tr['excitation'])
    audio=signal.resample_poly(native/32768.,1,2);n=min(round(.012*24000),len(audio)//2);env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    assert np.array_equal(expected,audio) and [ah(v) for v in params]==before and np.isfinite(out).all()
    source_checks.append(dict(hz=hz,lpf=coefficient,original_native_wave_exact=True,input_streams_exact=True,source_sha256=ah(tr['excitation']),passed=True))
print(json.dumps(dict(passed=True,spectral_checks=spectral,convolution_checks=convolution,source_checks=source_checks,
    IR_length=IR_LENGTH,FFT_length=FFT_LENGTH,render=60,dsp=64,render_breakdown=dict(FFT_kernel=16,C_reference_kernel=16,driving_signal=4,FFT_FIR=12,independent_convolution=4,original_HTS=4,observed_HTS=4),
    direct_past_only=True,extra_alignment_latency_samples=0,scope='登録人工MCPの機構のみ。未知日本語MCPと波形の工学/内容/知覚は別契約。',quality_certified=False)))
'''

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs']
    cutoff=read(CUTOFF/'aggregate-summary.json');length=cutoff['selected_minimum_length']
    assert length in (2048,4096) and cutoff['length_eligibility'][str(length)]
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=8,audit=10,render=180,dsp=192,ai=0,teacher=0,train=0,inverse=0,download=0)
    module=MODULE.replace('__L__',str(length))
    reg=dict(campaign=NAME,question='全実MCPで選んだ固定IR長のFFT生成と過去だけの直接畳み込みは、独立C prefix・静的畳み込みcrossfade・原HTSを保護できるか。',
        IR_length=length,FFT_length=16384,alpha=.55,frame=240,interpolation='出力時刻のIR crossfade j/240。MLSA b補間と同一とは呼ばない。',
        source=dict(cutoff_seal_sha256=digest(CUTOFF/'artifact-seal.json'),old_C_binary_sha256=digest(PARENT/'runtime-bundle/shape.dylib'),urls=['https://sp-nitech.github.io/sptk/latest/main/freqt.html','https://sp-nitech.github.io/sptk/latest/main/c2mpir.html']),
        thresholds=dict(C_prefix_relative_error=1e-10,convolution_absolute_error=1e-10,causal_prefix_exact=True,native_wave_exact=True),
        costs=dict(render=60,dsp=64,maximum_seconds=3000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),
        module_sha256=hashlib.sha256(module.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),limits=limits,
        next='機構資格を同一共有bundleへ固定し、新16日本語文の原native/FFT FIR比較を生成前登録する。',
        old_selected_MCP_evidence_is_not_independent_quality=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','固定長FFT IRと直接畳み込みの出力前登録',reserve_bytes=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'fft_fir.py',module.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib','shape_arrays.py','shape.dylib','minphase.py'):
            b.write(HERE/'runtime-bundle'/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        b.write(HERE/'runtime-bundle/fft_fir.py',module.encode(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={str(p.relative_to(HERE/'runtime-bundle')):digest(p) for p in (HERE/'runtime-bundle').rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0070.json',dict(active_campaign=NAME,next=reg['next'],new_scientific_outputs=0,quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,IR_length=length,new_scientific_outputs=0),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json')
    assert digest(Path(__file__))==contract['controller_sha256']
    for n,h in contract['files'].items():assert digest(HERE/n)==h,n
    r=b.reserve(NAME,'render','FFT IR・駆動源・HTS・因果FIRの全生成',60,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','独立C prefix・直接畳み込み・原対照の限定資格',64,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'FFT FIR fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','機構範囲・共有依存・費用・一時回収の終了照合',reserve_bytes=2000000) as j:
        assert fixture['passed'] and len(fixture['spectral_checks'])==16 and len(fixture['source_checks'])==len(fixture['convolution_checks'])==4
        for n,h in contract['files'].items():assert digest(HERE/n)==h,n
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,IR_length=fixture['IR_length'],FFT_length=16384,original_native_wave_exact=True,causal_prefix_exact=True,real_unknown_MCP_or_speech_qualified=False,perceptual_qualification=False,quality_goal_completed=False,protected_confirmation_opened=False),j)
        b.write(HERE/'report.md',('# 固定長FFT FIRの機構検証\n\n16人工MCP条件の独立C1024 prefix、4駆動源の独立直接畳み込みと因果prefix、4HTS条件の原native完全一致・入力列不変を通過した。IR長は前の全実MCP検査で固定し、16384gridから計算する。過去の源を行ごとの直接内積で参照し、出力時刻のIRをcrossfadeする。\n\n資格は登録人工条件の機構に限る。未知日本語MCP・工学F0・内容・自然さは別比較とし、旧FIR1024の結果や旧249欠測を変更しない。原HTSの内部補助生成もrenderへ別計上する。知覚資格なし・P5未開封・品質未達。\n\n一次資料: [SPTK freqt](https://sp-nitech.github.io/sptk/latest/main/freqt.html)、[c2mpir](https://sp-nitech.github.io/sptk/latest/main/c2mpir.html)。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='FFT-FIR-mechanism-completed',active_campaign=None,next='新16日本語文の原native/固定長FFT FIR比較を生成前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0071.json',dict(latest_completed=NAME,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,IR_length=fixture['IR_length'],quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args()
    register() if a.stage=='register' else run()
