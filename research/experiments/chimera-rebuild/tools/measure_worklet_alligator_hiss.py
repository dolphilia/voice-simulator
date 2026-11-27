"""アリゲーターの hiss の乱流と実断面を実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_alligator_bellow as call
import measure_alligator_hiss as hiss
import measure_wasm_fixed as wasm
import measure_worklet_alligator_call as common
from measure_seal_sustain_pcm import columns
from measure_worklet_seal_sustain import compare_at, run
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-alligator-hiss.json'
MUTED = ('artifacts/standalone-96000/mute-case.json', 'artifacts/standalone-96000/upstream-muted.csv')


def measure_registration(observed, points, samples, state, variant, spec, measurement):
    factor = len(samples) // len(points)
    changed = np.flatnonzero(np.diff(observed['oral_noise']) != 0) + 1
    changed = changed[(points[changed] >= variant['first_control']) & (points[changed] < variant['end'])]
    frames_per_block = spec['control_frames']
    threshold = spec['oral_noise_threshold_cm2']
    transitions = []
    for position in changed:
        sample = int(points[position]) * factor
        start = int(np.searchsorted(samples, sample))
        end = start + frames_per_block * factor
        if not np.array_equal(samples[start - 1:end], np.arange(sample - 1, sample + frames_per_block * factor)):
            raise ValueError('口腔乱流の切り替え前後を内部サンプル単位で観測する必要があります')
        block = state['oral_tip_area_cm2'][start:end]
        registered = bool(observed['oral_noise'][position])
        crossed = np.flatnonzero((block < threshold) == registered)
        crossing = int(crossed[0]) if crossed.size else None
        transitions.append({
            'registered': registered, 'switch_internal_sample': sample,
            'crossing_internal_sample': None if crossing is None else sample + crossing,
            'advance_internal_samples': crossing, 'area_at_switch_cm2': float(block[0]),
            'area_at_block_end_cm2': float(block[-1]),
            'commanded_area_cm2': 0.05 + 12 * float(observed['mouth'][position]),
        })
    checks = {
        'browser_noise_registration_samples': [item['switch_internal_sample'] for item in transitions]
        == measurement['oral_noise_switch_internal_samples'][variant['id']],
        'browser_noise_registration_precedes_geometry': (
            [item['registered'] for item in transitions] == [False, True]
            and all((item['advance_internal_samples'] or 0) > 0
                    and (item['commanded_area_cm2'] < threshold) == item['registered'] for item in transitions)),
    }
    return checks, transitions


def measure_browser_noise(case, variant, spec, points, observed, state, audio, measurement, baseline):
    config = measurement['direct_noise']
    prefix = config['continuous_prefix_output_frames']
    if not np.array_equal(points[:prefix], np.arange(prefix)):
        raise ValueError('乱数とフィルタを初期化した時点から連続する観測が必要です')
    rate = case['sample_rate_hz']
    if rate <= 60000:
        raise ValueError('連続する乱流の直接検証は内部と出力のレートが同じ条件で行います')
    trace = {key: values[:prefix] for key, values in state.items()}
    trace['oral_noise'] = observed['oral_noise'][:prefix]
    cfg, aspiration = (spec[key] for key in ('noise_model', 'aspiration_window'))
    window, _ = hiss.aspiration_intervals(variant['first_control'], rate, 1, aspiration)
    tolerance = cfg['absolute_tolerance_dyn_cm2']
    coordinates = points[:prefix]
    level, pressure = hiss.noise_reference(trace, rate, cfg, spec)
    direct = {key: compare_at(trace[key], expected, tolerance, coordinates, coordinate='internal_sample')
              for key, expected in ((hiss.GLOTTAL_LEVEL, level), (hiss.GLOTTAL_PRESSURE, pressure))}
    two_draws = trace | {'oral_noise': np.full(prefix, config['fixed_draw_count'] - 1, dtype=int)}
    fixed_level, fixed_pressure = hiss.noise_reference(two_draws, rate, cfg, spec)
    difference = compare_at(trace[hiss.GLOTTAL_PRESSURE], fixed_pressure, tolerance, coordinates,
                            coordinate='internal_sample')
    first_difference = difference['first_over_tolerance_internal_sample']
    first_switch = measurement['oral_noise_switch_internal_samples'][variant['id']][0]
    pressure_rms = hiss.rms(trace[hiss.GLOTTAL_PRESSURE][window])
    pcm_rms = hiss.rms(audio[window])
    peak_voicing = float(np.max(trace['glottis_voicing'][window]))
    recovery = np.flatnonzero(trace['glottis_voicing'][window.stop:] >= config['recovered_voicing_threshold'])
    recovery_frame = int(recovery[0]) + window.stop if recovery.size else None
    release = variant['first_control'] + round(rate * spec['hiss_keys']['hold_seconds'])

    # 固定上流を乱流倍率0で描画した基準へ、ブラウザの同じ区間を照合する。
    muted_spec = spec['mute_control']
    muted_frames = muted_spec['trace_frames']
    expected_case = case | {'frames': muted_frames, 'events': [event for event in case['events']
                                                               if event['frame'] < muted_frames]}
    if wasm.read_json(baseline / MUTED[0])['alligator_voice'] != expected_case:
        raise ValueError('乱流を消した固定上流の入力が一致しません')
    muted = columns(baseline / MUTED[1], muted_frames, (*call.UPPER, *call.NOISE_FIELDS))
    muted_rms = hiss.rms(muted['pcm_f32'][window])
    ratio = muted_rms / pcm_rms if pcm_rms else None
    checks = {
        'browser_noise_reference': all(item['passed'] for item in direct.values()),
        'browser_aspiration_noise_without_voicing': (
            peak_voicing <= aspiration['max_voicing'] and pressure_rms > 0 and pcm_rms > 0
            and not trace['oral_noise'][window].any() and not trace[hiss.ORAL_LEVEL][window].any()),
        'fixed_rng_stride_changes_pressure_only': (
            np.array_equal(level, fixed_level) and first_difference is not None
            and first_switch < first_difference <= window.start),
        'early_voicing_recovery': recovery_frame is not None and recovery_frame < release,
        'muted_reference_removes_noise': not any(muted[key].any() for key in call.NOISE_FIELDS),
        'muted_reference_pcm_rms_reduction': ratio is not None and ratio <= muted_spec['max_pcm_rms_ratio'],
    }
    return checks, {
        'continuous_prefix_frames': prefix, 'independent': direct, 'fixed_rng_stride': difference,
        'fixed_rng_stride_pressure_error_rms_dyn_cm2': hiss.rms(
            (trace[hiss.GLOTTAL_PRESSURE] - fixed_pressure)[window]),
        'aspiration': {'window_output_frames': [window.start, window.stop], 'peak_voicing': peak_voicing,
                       'pcm_rms': pcm_rms, 'pressure_rms_dyn_cm2': pressure_rms, 'muted_pcm_rms': muted_rms,
                       'muted_to_browser_pcm_rms_ratio': ratio},
        'recovered_voicing_frame': recovery_frame,
        'recovered_voicing_gate_target': None if recovery_frame is None else float(observed['gate_target'][recovery_frame]),
        'gate_release_start_frame': release,
    }


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    measurement = config['measurement']

    def observe(case, variant, spec, points, observed, samples, state, audio):
        checks, transitions = measure_registration(observed, points, samples, state, variant, spec, measurement)
        details = {'browser_noise_transitions': transitions}
        if label == measurement['direct_noise']['variant']:
            direct_checks, details['browser_direct_noise'] = measure_browser_noise(
                case, variant, spec, points, observed, state, audio, measurement, baseline)
            checks.update(direct_checks)
        return checks, details

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  call_name='hiss', boundary_checks=hiss.boundary_checks, observe=observe,
                                  extra_measurement=('noise', hiss.measure_noise))


if __name__ == '__main__':
    sources = (Path(common.__file__), *(WORKSPACE / 'tools' / name for name in (
        'measure_alligator_hiss.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
        'measure_worklet_alligator_fixed_voice.py', 'measure_seal_airway.py', 'measure_turbulence.py')))
    raise SystemExit(run(CASE, hiss.CASE, compare_variant, 'alligator_hiss_noise_switches_do_not_allocate',
                         (96000,), __doc__, extra_sources=sources, creature='alligator', official_variant=common.OFFICIAL,
                         reference_files=MUTED, upstream_files=('crates/chimera/src/airway/network.rs',
                                                               'crates/chimera/src/sources/glottis.rs',
                                                               'crates/chimera/src/physics.rs',
                                                               'crates/chimera-cli/src/render.rs')))
