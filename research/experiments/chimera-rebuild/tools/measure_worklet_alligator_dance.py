"""アリゲーターの dance を実時間ブラウザで照合し、放射経路と低域を調べる。"""

from pathlib import Path

import numpy as np

import measure_alligator_bellow as call
import measure_alligator_dance as dance
import measure_wasm_fixed as wasm
import measure_worklet_alligator_call as common
from measure_seal_sustain_pcm import columns, independent_output
from measure_worklet_seal_sustain import compare_at, run
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-alligator-dance.json'
OFFICIAL = 'official-full-48000'
FIXED_CHAOS = 'artifacts/standalone-96000/fixed-chaos'
PATHS = ('wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s')


def browser_spectrum(case, variant, spec, samples, state, audio):
    rate = case['sample_rate_hz']
    factor = 2 if rate <= 60000 else 1
    internal_rate = rate * factor
    limits = spec['spectral_window']
    first = variant['first_control']
    inside = dance.spectral_window(internal_rate, first * factor, limits['seconds'])
    output = dance.spectral_window(rate, first, limits['seconds'])
    lo, hi = np.searchsorted(samples, [inside.start, inside.stop])
    if not np.array_equal(samples[lo:hi], np.arange(inside.start, inside.stop)):
        raise ValueError('スペクトルの計測窓内の内部サンプルがそろっていません')
    spectra = {key: dance.summarize_spectrum(state[key][lo:hi], internal_rate, limits)
               for key in dance.SPECTRAL_FIELDS}
    spectra['pcm_f32'] = dance.summarize_spectrum(audio[output], rate, limits)
    return spectra


def browser_handoff(case, variant, points, observed):
    request, = [event['frame'] for event in case['events'] if event.get('play_call', {}).get('id') == 'dance']
    first = variant['first_control']
    before, control = np.searchsorted(points, [request - 1, first])
    if not np.array_equal(points[before:control + 1], np.arange(request - 1, first + 1)):
        raise ValueError('切り替えの待ち時間は連続した出力フレームから求めます')
    saved, = [event['params']['hiss'] for event in case['events'] if event['frame'] == variant['before_switch_edit']]
    launch, = [event['play_call'] for event in case['events'] if event['frame'] == request]
    span = slice(before + 1, control)
    checks = {
        'browser_hiss_handoff': bool(np.all(observed['target_hiss'][span] == saved)
                                     and observed['target_hiss'][before] != saved),
        'browser_hiss_smoothing_waits': bool(np.all(observed['hiss'][span] == observed['hiss'][before])
                                            and observed['hiss'][control] < observed['hiss'][before]),
        'browser_dance_first_target': bool(observed['target_pitch_hz'][control] == launch['pitch_hz']
                                           and observed['target_mouth'][control] == 0),
    }
    return checks, {'request_frame': request, 'first_control_frame': first, 'control_wait_frames': first - request,
                    'target_hiss': float(observed['target_hiss'][before + 1]),
                    'target_pitch_hz': float(observed['target_pitch_hz'][control])}


def reconstruct_radiation(trace, observed, audio, rate, level, variant, spec, config):
    limits, output, tolerance = (spec[key] for key in ('spectral_window', 'output', 'tolerances'))
    window = dance.spectral_window(rate, variant['first_control'], limits['seconds'])
    prefix = config['continuous_prefix_output_frames']
    points = np.arange(prefix)
    total = sum(trace[key] for key in PATHS)
    derivative = np.diff(total, prepend=0.0) * rate
    _, dc, pcm = independent_output(derivative, rate, 1, level, output)
    filtered_paths = {key: independent_output(np.diff(trace[key], prepend=0.0) * rate, rate, 1, level, output)[1]
                      for key in PATHS}
    signals = {'total_flow': total, 'differentiated_flow': derivative, 'dc_removed': dc, 'pcm_f32': audio}
    spectra = {key: dance.summarize_spectrum(values[window], rate, limits) for key, values in signals.items()}
    ratios = {key: item['bands'][1]['rms'] / item['bands'][0]['rms'] for key, item in spectra.items()}
    without_path = {key: dance.summarize_spectrum((dc - values)[window], rate, limits)
                    for key, values in filtered_paths.items()}
    differences = {
        'derivative': compare_at(trace[call.fixed.RADIATION], derivative, tolerance['radiation_cm3_s2'], points,
                                 coordinate='internal_sample'),
        'dc_removed': compare_at(observed['dc_removed'][:prefix], dc, tolerance['dc_removed'], points),
        'pcm_f32': compare_at(audio[:prefix], pcm, tolerance['pcm_f32'], points),
        'separate_paths': compare_at(dc, sum(filtered_paths.values()), config['linear_output_absolute_tolerance'], points),
    }
    checks = {
        'browser_radiation_reconstruction': all(item['passed'] for item in differences.values()),
        'browser_upper_band_gains_after_derivative_and_dc': (
            ratios['total_flow'] < ratios['differentiated_flow'] < ratios['dc_removed']),
    }
    limited = int(np.count_nonzero(np.abs(observed['dc_removed'][window]) > output['limiter_threshold']))
    return checks, {'spectra': spectra, 'upper_band_to_low_band_rms': ratios, 'without_path': without_path,
                    'differences': differences, 'limited_frames_in_window': limited}


def measure_roughness(trace, observed, case, variant, spec, baseline):
    control = spec['fixed_chaos_control']
    frames, rate = control['frames'], case['sample_rate_hz']
    first = variant['first_control']
    start, = [event['frame'] for event in case['events'] if event.get('play_call', {}).get('id') == 'dance']
    expected = case | {'frames': frames, 'shape': case['shape'] | {'chaos': control['chaos']},
                       'events': [{'frame': start, 'gate': 1.0}]}
    folder = baseline / FIXED_CHAOS
    if wasm.read_json(folder / 'case.json')['alligator_voice'] != expected:
        raise ValueError('粗さ0の対照の入力が登録条件と一致しません')
    fixed = columns(folder / 'pcm-128.csv', frames, call.CANDIDATE)
    actual = trace | {key: observed[key][:frames] for key in ('chaos', 'pitch_hz', 'gate')}
    same = ('gate', 'lung_pressure_dyn_cm2', 'oral_tip_area_cm2', 'velum_area_cm2', 'pitch_hz', 'glottis_f0_hz')
    window = dance.spectral_window(rate, first, spec['spectral_window']['seconds'])
    period = spec['cycle_model']
    cycles = call.cycle_comparison(actual, rate, period, spec['seeds']['cycles'], first,
                                   [spec['spectral_window']['seconds']])
    intervals = {}
    for label, values in (('constant', fixed), ('ramp', actual)):
        indices, scales = call.cycle_period_scales(values, rate, period['phase_wrap_threshold'])
        inside = scales[(indices >= window.start) & (indices < window.stop)]
        intervals[label] = {'cycles': len(inside), 'mean_scale': float(np.mean(inside)) if inside.size else None,
                            'standard_deviation': float(np.std(inside)) if inside.size else None}
    enough = all(item['cycles'] >= control['minimum_cycles_in_window'] for item in intervals.values())
    checks = {
        'browser_cycle_scale_independent': cycles['period_scale']['passed'],
        'browser_roughness_control_shared_input': all(np.array_equal(actual[key], fixed[key]) for key in same),
        'browser_roughness_control_zero': bool(np.all(fixed['chaos'] == control['chaos'])),
        'browser_roughness_ramp_lengthens_period': (
            enough and intervals['ramp']['mean_scale'] > intervals['constant']['mean_scale']),
    }
    return checks, {'cycles': intervals, 'independent': cycles}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    decomposition = config['measurement']['decomposition']

    def observe(case, variant, spec, points, observed, samples, state, audio):
        spectra = browser_spectrum(case, variant, spec, samples, state, audio)
        area_peak = spectra['glottis_area_cm2']['peak_hz']
        low, high = variant['peak_area_hz']
        checks = {'browser_glottal_area_peak': low <= area_peak <= high,
                  'browser_pcm_peak_above_area': spectra['pcm_f32']['peak_hz'] > area_peak}
        details = {'browser_spectrum': spectra}
        if label == OFFICIAL:
            checks['official_full_length'] = len(audio) == spec['official_demo_frames']
        if 'before_switch_edit' in variant:
            handoff, details['browser_handoff'] = browser_handoff(case, variant, points, observed)
            checks.update(handoff)
        if label == decomposition['variant']:
            prefix = decomposition['continuous_prefix_output_frames']
            if not np.array_equal(samples[:prefix], np.arange(prefix)):
                raise ValueError('放射の再構成には初期状態からの連続した内部サンプルが必要です')
            trace = {key: values[:prefix] for key, values in state.items()}
            radiation, details['browser_radiation'] = reconstruct_radiation(
                trace, observed, audio, case['sample_rate_hz'], case['level'], variant, spec, decomposition)
            roughness, details['browser_roughness'] = measure_roughness(trace, observed, case, variant, spec, baseline)
            checks.update(radiation | roughness)
        return checks, details

    result = common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                    call_name='dance', boundary_checks=dance.boundary_checks, observe=observe,
                                    extra_measurement=('spectrum', dance.measure_spectra), official_variant=OFFICIAL)
    result['checks']['browser_spectrum_peak_bins_match_upstream'] = all(
        item['peak_hz'] == result['spectrum']['upstream'][key]['peak_hz']
        for key, item in result['browser_spectrum'].items())
    return result


if __name__ == '__main__':
    sources = (Path(common.__file__), *(WORKSPACE / 'tools' / name for name in (
        'measure_alligator_dance.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
        'measure_worklet_alligator_fixed_voice.py', 'measure_seal_airway.py', 'measure_turbulence.py')))
    raise SystemExit(run(CASE, dance.CASE, compare_variant, 'alligator_dance_render_does_not_allocate',
                         (96000,), __doc__, extra_sources=sources, creature='alligator', official_variant=OFFICIAL,
                         reference_files=(f'{FIXED_CHAOS}/case.json', f'{FIXED_CHAOS}/pcm-128.csv'),
                         upstream_files=('crates/chimera/src/airway/network.rs',
                                         'crates/chimera/src/sources/glottis.rs',
                                         'crates/chimera-cli/src/render.rs')))
