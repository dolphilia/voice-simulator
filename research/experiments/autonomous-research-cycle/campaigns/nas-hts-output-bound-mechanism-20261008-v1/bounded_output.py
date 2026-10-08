"""小振幅を保持する固定・無記憶の出力上限。保存波形から係数を決めない。"""
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
