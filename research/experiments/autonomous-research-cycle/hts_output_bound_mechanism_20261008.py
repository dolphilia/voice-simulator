"""固定出力振幅制御の数学的範囲と原HTS対照を、音声品質と分けて検証する。"""
import ast
import hashlib
import json
import os
import subprocess
from pathlib import Path
from budget import ROOT, read, digest, encode
from long_horizon_budget import LongHorizonBudget as Budget

REPO = ROOT.parents[2]
HERE = ROOT / 'campaigns/nas-hts-output-bound-mechanism-20261008-v1'
NAME = 'hts-output-bound-mechanism-v1'
PARENT = ROOT / 'campaigns/nas-hts-allpass-mechanism-20261008-v1'
PREVIOUS = ROOT / 'campaigns/nas-hts-allpass-comparison-20261008-v1'
PYTHON = REPO / 'research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python'

MODULE = r'''"""小振幅を保持する固定・無記憶の出力上限。保存波形から係数を決めない。"""
import numpy as np
from scipy import signal
from hts_arrays import ah
from shape_arrays import raw
KNEE=.5
CEILING=.98
WIDTH=CEILING-KNEE
def bound(x):
    a=np.asarray(x,dtype=np.float64)
    if a.ndim!=1 or not np.isfinite(a).all():raise ValueError('有限の一次元振幅列が必要')
    y=a.copy();mask=np.abs(a)>KNEE
    y[mask]=np.sign(a[mask])*(KNEE+WIDTH*np.tanh((np.abs(a[mask])-KNEE)/WIDTH))
    assert np.isfinite(y).all() and np.max(np.abs(y),initial=0.)<=CEILING
    return y
def synthesize(params,settings,method):
    if method not in ('native','soft_bound'):raise ValueError('未登録の固定出力方式')
    x,tr=raw(params,settings,'native')
    audio=signal.resample_poly(x/32768.,1,2);n=min(round(.012*24000),len(audio)//2)
    env=np.sin(np.linspace(0,np.pi/2,n))**2;audio[:n]*=env;audio[-n:]*=env[::-1]
    # 呼出し元の共通gain.25を保つため、2の冪で正確に移す。上限は最終振幅の値。
    if method=='soft_bound':audio=bound(audio*.25)/.25
    return audio,dict(renderer='原HTS-MLSA/固定無記憶出力上限',output_method=method,
        effective_filter_alpha=.55,model_original_alpha=settings['alpha'],input_streams_unchanged=True,
        source_clock_hashes={k:ah(tr[k]) for k in ('period','counter','event')},
        original_excitation_sha256=ah(tr['original_excitation']),processed_excitation_sha256=ah(tr['processed_excitation']),
        original_excitation_and_processed_excitation_equal=True,cycle_events=int(tr['event'].sum()),
        output_knee=KNEE if method!='native' else None,output_ceiling=CEILING if method!='native' else None,
        output_rule='abs(x)<=.5は恒等、それ以外はsign(x)*(.5+.48*tanh((abs(x)-.5)/.48))。xは共通gain.25後。',
        output_bound_intentionally_changes_large_samples=method!='native',memoryless=True,extra_delay_samples=0,
        nonlinear_harmonics_possible=True,finite_wave_energy_not_preserved=True,
        render_calls_including_internal_MLSA=1,neural_model=False,utterance_lookup=False,
        saved_waveform_analysis_used=False,per_waveform_gain_rescue=False)
'''

FIXTURE = r'''"""独立スカラー式、上限・恒等域・因果性と原HTSを検証する。"""
import sys,json,os,tempfile,math
from pathlib import Path
here=Path(__file__).resolve().parent
assert Path(tempfile.gettempdir()).resolve()==Path(os.environ['TMPDIR']).resolve()
sys.path.insert(0,str(here/'runtime-bundle'))
import numpy as np
from scipy import signal
from hts_arrays import synthesize as original,ah
from shape_arrays import raw
from bounded_output import bound,synthesize,KNEE,CEILING,WIDTH
def scalar(x):
    return x if abs(x)<=.5 else math.copysign(.5+.48*math.tanh((abs(x)-.5)/.48),x)
rng=np.random.default_rng(1053053)
grid=np.unique(np.r_[np.linspace(-4.,4.,16001),[-1e6,-.50000001,-.5,-.49999999,0.,.49999999,.5,.50000001,1e6]])
out=bound(grid);ref=np.array([scalar(float(x)) for x in grid]);error=float(np.max(np.abs(out-ref)))
assert error<=1e-14
assert np.max(np.abs(out))<=.98 and np.max(np.abs(out.astype(np.float32)))<.99
assert np.all(np.diff(out)>=0.) and np.array_equal(bound(-grid),-out)
inside=np.abs(grid)<=.5;assert np.array_equal(out[inside],grid[inside])
grid_checks=dict(scalar_max_abs_error=error,finite_double_and_float32_bounded=True,
    monotone_and_odd=True,identity_region_exact=True,passed=True)
driving=[]
for mode in ('zeros','step','impulse','sine_low','sine_high','noise'):
    n=4800
    if mode=='zeros':x=np.zeros(n)
    elif mode=='step':x=np.r_[np.zeros(600),np.full(n-600,2.)]
    elif mode=='impulse':x=np.zeros(n);x[0]=2.;x[700]=-2.
    elif mode=='sine_low':x=.2*np.sin(2*np.pi*220*np.arange(n)/24000.)
    elif mode=='sine_high':x=1.4*np.sin(2*np.pi*220*np.arange(n)/24000.)
    else:x=rng.normal(0.,.7,n)
    before=ah(x);y=bound(x);z=np.array([scalar(float(v)) for v in x]);err=float(np.max(np.abs(y-z)))
    future=x.copy();future[2400:]+=1.;changed=bound(future)
    assert err<=1e-14 and ah(x)==before and np.array_equal(y[:2400],changed[:2400])
    driving.append(dict(mode=mode,scalar_max_abs_error=err,causal_prefix_exact=True,input_exact=True,
        low_region_samples=int((np.abs(x)<=.5).sum()),changed_samples=int((x!=y).sum()),passed=True))
settings=dict(stage=0.,use_log_gain=0.,sampling_frequency=48000.,fperiod=240.,alpha=.55,beta=0.,volume=1.,audio_buff_size=0.,stop=0.)
source=[]
for hz in (110.,280.):
 for lpf in (0.,1.):
    mcp=np.zeros((60,35));mcp[:,0]=9.;mcp[:,1]=.2;lf0=np.full((60,1),-1e10);lf0[10:50]=np.log(hz)
    params=[mcp,lf0,np.full((60,1),lpf)];before=[ah(v) for v in params]
    expected,_=original(params,settings)
    native,meta=synthesize(params,settings,'native');candidate,cmeta=synthesize(params,settings,'soft_bound')
    assert np.array_equal(expected,native) and [ah(v) for v in params]==before
    assert meta['source_clock_hashes']==cmeta['source_clock_hashes'] and meta['original_excitation_sha256']==cmeta['original_excitation_sha256']
    assert meta['processed_excitation_sha256']==cmeta['processed_excitation_sha256'] and cmeta['original_excitation_and_processed_excitation_equal']
    expected_final=np.array([scalar(float(v)) for v in native*.25])
    err=float(np.max(np.abs(candidate*.25-expected_final)));assert err<=1e-14
    assert np.max(np.abs((candidate*.25).astype(np.float32)))<.99
    low=np.abs(native*.25)<=.5;assert np.array_equal((candidate*.25)[low],(native*.25)[low])
    source.append(dict(hz=hz,lpf=lpf,native_exact=True,all_parameters_and_source_clock_exact=True,
        expected_final_max_abs_error=err,float32_no_clipping=True,unchanged_low_samples=int(low.sum()),passed=True))
reject=[]
for values in ([float('nan')],[float('inf')],[-float('inf')],[[1.]]):
    try:bound(values)
    except ValueError:reject.append(True)
    else:raise AssertionError('不正振幅列の拒否が必要')
print(json.dumps(dict(passed=True,grid_checks=grid_checks,driving_checks=driving,HTS_checks=source,invalid_inputs_rejected=reject,
    render=39,dsp=28,
    render_breakdown=dict(grid_driver=1,grid_filter=1,grid_independent=1,driving_signals=6,driving_filter=6,driving_independent=6,causal_filter=6,original_HTS=4,native_HTS=4,bounded_HTS=4),
    dsp_breakdown=dict(grid=4,driving_scalar=6,driving_causality=6,HTS_native_and_source=4,HTS_final_mapping=4,invalid_inputs=4),
    scope='登録人工振幅の上限・恒等域・因果性と人工HTSの機構のみ。日本語内容・ピッチ・DC・自然さは別比較。',
    amplitude_bound_is_not_naturalness_truth=True,quality_certified=False)))
'''

def verify(contract):
    assert digest(Path(__file__)) == contract['controller_sha256']
    for n, h in contract['files'].items():
        assert digest(HERE / n) == h, n

def register():
    b=Budget();b.recover();assert not b.snapshot()['jobs'] and not b.review_due()['due']
    assert read(PREVIOUS/'aggregate-summary.json')['total']==64
    assert not read(PREVIOUS/'aggregate-summary.json')['research_protection_gates']['allpass']
    ast.parse(MODULE);ast.parse(FIXTURE)
    limits=dict(seconds=3600,bytes=200000000,write_bytes=600000000,setup=8,audit=10,
        render=117,dsp=84,ai=0,teacher=0,train=0,inverse=0,download=0)
    reg=dict(campaign=NAME,question='原生成を変えず、固定無記憶の出力制御は恒等域と上限を独立検証できるか。過大ピークの観測を新因子の動機として保持する。',
        factor='最終共通gain.25後のabs(x)<=.5は恒等、外側sign(x)*(.5+.48*tanh((abs(x)-.5)/.48))。ceiling.98/knee.5固定。',
        controls='MCP/LF0/LPF/duration、原励振/時計、alpha.55/beta0/volume1、resample24k/12msfade/gain.25は原HTS。オールパスは使用しない。波形別係数・gain推定なし。',
        thresholds=dict(scalar_absolute_error=1e-14,native_exact=True,input_and_source_clock_exact=True,
            identity_region_exact=True,monotone_and_odd=True,double_peak_at_most=.98,float32_peak_below=.99,causal_prefix_exact=True,invalid_input_reject=True),
        interpretation='上限は任意有限振幅に対する設計性質。非線形で高調波/aliasやDC/内容が変わり得る。知覚品質・pitch・有限エネルギー保存を保証しない。',
        costs=dict(render=39,dsp=28,maximum_seconds=3000,temporary_peak=8000000,temporary_write=16000000,RAM_gb=8),limits=limits,
        sources=dict(previous_comparison_seal_sha256=digest(PREVIOUS/'artifact-seal.json'),native_mechanism_seal_sha256=digest(PARENT/'artifact-seal.json'),
            mathematical_rule='自作の固定解析式。新しい人の評点、教師、保存音声のgain探索は使わない。'),
        module_sha256=hashlib.sha256(MODULE.encode()).hexdigest(),fixture_sha256=hashlib.sha256(FIXTURE.encode()).hexdigest(),controller_sha256=digest(Path(__file__)),
        next='機構通過時に新16文native/soft_boundの64波形を生成前固定し、全件E0/旧pitch/支持/二ASR/通常隔離を比較。knee/ceilingの出力後探索なし。',
        old_allpass_FIR_glottal_fractional_results_kept=True,perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False)
    b.start_campaign(NAME,str(HERE.relative_to(ROOT)),limits,hashlib.sha256(encode(reg)).hexdigest())
    with b.job(NAME,'setup','固定出力上限機構と全費用の生成前登録',reserve_bytes=12000000) as j:
        b.save(HERE/'registration.json',reg,j);b.write(HERE/'bounded_output.py',MODULE.encode(),j);b.write(HERE/'fixture.py',FIXTURE.encode(),j)
        for n in ('hts_arrays.py','hts_arrays.dylib','local_renderer.py','local_hts-v2.dylib','shape_arrays.py','shape.dylib'):
            b.write(HERE/'runtime-bundle'/n,(PARENT/'runtime-bundle'/n).read_bytes(),j)
        b.write(HERE/'runtime-bundle/bounded_output.py',MODULE.encode(),j)
        b.write(HERE/'HTS-BSD-NOTICE.txt',(PARENT/'HTS-BSD-NOTICE.txt').read_bytes(),j)
        b.save(HERE/'runtime-bundle/manifest.json',dict(files={str(p.relative_to(HERE/'runtime-bundle')):digest(p) for p in (HERE/'runtime-bundle').rglob('*') if p.is_file()},no_neural_inference=True),j)
        b.save(HERE/'execution-contract.json',dict(files={str(p.relative_to(HERE)):digest(p) for p in HERE.rglob('*') if p.is_file()},controller_sha256=digest(Path(__file__)),no_scientific_output_yet=True),j)
    b.save(ROOT/'progress-0085.json',dict(active_campaign=NAME,new_scientific_outputs=0,next=reg['next'],quality_goal_completed=False,budget=b.reconcile()))
    print(dict(registered=True,new_scientific_outputs=0),flush=True)

def run():
    b=Budget();b.recover();assert not b.snapshot()['jobs'];contract=read(HERE/'execution-contract.json');verify(contract)
    r=b.reserve(NAME,'render','固定出力上限の人工振幅・駆動源・原HTS全生成',39,20000000,expected_seconds=300)
    try:
        d=b.reserve(NAME,'dsp','独立式・恒等域・上限・原HTS・因果性・拒否の確認',28,1000000,expected_seconds=300)
        try:
            with b.workspace(r,'出力振幅fixtureの科学ライブラリ初期化') as (_,env):
                env.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',VECLIB_MAXIMUM_THREADS='1')
                out=subprocess.run([str(PYTHON),'-B',str(HERE/'fixture.py')],env=env,check=True,capture_output=True,text=True,timeout=240)
            fixture=json.loads(out.stdout);b.save(HERE/'fixture-audit.json',fixture,d)
        except BaseException as exc:
            if isinstance(exc,subprocess.CalledProcessError):b.save(HERE/'child-failure.json',dict(returncode=exc.returncode,stdout=exc.stdout,stderr=exc.stderr),d)
            b.finish(d,repr(exc));raise
        else:b.finish(d)
    except BaseException as exc:b.finish(r,repr(exc));raise
    else:b.finish(r)
    with b.job(NAME,'audit','出力制御の機構範囲・費用・hash・一時回収の終了確認',reserve_bytes=2000000) as j:
        assert fixture['passed'] and sum(fixture['render_breakdown'].values())==39 and sum(fixture['dsp_breakdown'].values())==28
        verify(contract)
        b.save(HERE/'aggregate-summary.json',dict(mechanical_fixture_passed=True,knee=.5,ceiling=.98,
            original_native_wave_exact=True,source_clock_and_original_excitation_exact=True,identity_region_exact=True,
            float32_amplitude_bound_verified=True,causal_prefix_exact=True,real_Japanese_speech_qualified=False,
            perceptual_qualification=False,protected_confirmation_opened=False,quality_goal_completed=False),j)
        b.write(HERE/'report.md',('# 固定出力上限の機構\n\n最終gain.25後のabs(x)<=.5を完全保持し、外側をsign(x)*(.5+.48*tanh((abs(x)-.5)/.48))で固定制御する。上限.98は旧E0のpeak<.99を変更せず満たす設計値。無記憶・単調・奇関数で境界の左右微分は1。係数とgainの発話別推定は使わない。\n\n独立スカラー式、人工振幅gridのdouble/float32上限と恒等域、6駆動源の独立式/因果性、4HTS条件の原native完全一致・入力/源時計・最終振幅式、不正入力拒否を確認した。\n\n非線形処理は高調波/alias、DC、内容、pitchを変え得る。上限や人工機構の通過を自然さに読み替えない。次は未使用日本語16文の比較を別登録する。旧オールパス等の不通過と欠測、知覚資格なし・P5未開封・品質未達を保持する。\n').encode(),j)
        s=b.snapshot();c=s['campaigns'][NAME];temporary=[v for v in s['temporary_work'].values() if v['campaign']==NAME]
        assert all(v['status']=='removed' and not os.path.lexists(v['path']) for v in temporary)
        b.save(HERE/'cost-audit.json',dict(counts=c['counts'],seconds=s['seconds']-c['start_seconds'],write_bytes=s['write_bytes']-c['start_write_bytes'],temporary_owned=len(temporary),all_temporary_absent=True),j)
        b.save(HERE/'artifact-seal.json',dict(files={str(p.relative_to(REPO)):digest(p) for p in HERE.rglob('*') if p.is_file()},path_base='repository',experiment_completed=True,quality_goal_completed=False,protected_confirmation_opened=False),j)
    b.close_campaign(NAME)
    with b.locked():
        s=b._load();s['continuation_checkpoint'].update(id='output-bound-mechanism-completed',active_campaign=None,next='新16文native/soft_bound64波形の比較を生成前登録',git_save_pending=True);b._write_state(s)
    b.save(ROOT/'progress-0086.json',dict(latest_completed=NAME,quality_goal_completed=False,review=b.review_due(),budget=b.reconcile()))
    print(dict(passed=True,quality_goal_completed=False),flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','fixture']);a=p.parse_args()
    register() if a.stage=='register' else run()
