"""アザラシの zap とコール切り替えを実時間ブラウザで照合する。"""

import json
from pathlib import Path

import numpy as np

import measure_wasm_fixed as wasm
from measure_seal_sustain_pcm import CANDIDATE, columns, internal
from measure_seal_trill import CASE as TRILL, CALL_IDS, OUTPUT_CASE
from measure_seal_zap import CASE as SOURCE, boundary_checks
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import compare_at, run
from measure_worklet_seal_trill import EXTRA_FIELDS, compare_variant
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-seal-zap.json'


def compare_without_switch(points, observed, native_trace, source, audio, factor, config, artifacts, execute):
    request, control, end = (config[key] for key in (
        'request_output_frame', 'first_control_output_frame', 'search_end_output_frame_exclusive'))
    keep = [item for item in source['events'] if not (
        item['frame'] == request and item.get('play_call', {}).get('id') == config['omit_call'])]
    if len(keep) != len(source['events']) - 1:
        raise ValueError('切り替えを省く対照はコールの開始指示を一つだけ除く必要があります')
    case_path, wave_path, trace_path = (artifacts / f'zap-omitted.{ext}' for ext in ('json', 'wav', 'csv'))
    case_path.write_text(json.dumps({'seal_voice': source | {'events': keep}}, indent=2) + '\n')
    execute([*CLI, 'render-pcm', str(case_path), str(wave_path), str(trace_path)])
    rate, frames = (source['breath'][key] for key in ('sample_rate_hz', 'frames'))
    reference = read_wave(wave_path, rate, frames)
    trace = columns(trace_path, frames, (*CANDIDATE, *EXTRA_FIELDS))

    fields = ('call_id', 'target_pitch_hz', 'target_pulse_depth', 'pitch_hz', 'pulse_depth',
              'gate_target', 'gate', 'lung_pressure_dyn_cm2', 'decimated', 'dc_removed')
    first = {key: wasm.first_index(native_trace[key] != trace[key]) for key in fields}
    raw, reference_raw = (internal(values, factor)['radiation'] for values in (native_trace, trace))
    first_radiation = wasm.first_index(raw != reference_raw)
    pcm_tolerance = config['pcm_significance_absolute']
    pcm = wasm.compare_pcm(audio, reference, pcm_tolerance)
    first_pcm = pcm['first_bit_difference_frame']

    # 切り替え後の制御区間はブラウザから全フレームを保存する。
    in_window = (points >= control) & (points < end)
    dense_points = points[in_window]
    indices = (dense_points[:, None] * factor + np.arange(factor)).ravel()
    saved_radiation = internal({name: values[in_window] for name, values in observed.items()}, factor)['radiation']
    radiation_index = wasm.first_index(saved_radiation != reference_raw[indices])
    browser_radiation = None if radiation_index is None else int(indices[radiation_index])
    checks = {
        'switch_counterfactual_id_and_targets': all(first[key] == request for key in
                                                    ('call_id', 'target_pitch_hz', 'target_pulse_depth')),
        'switch_counterfactual_smoothed_values_and_pressure': all(first[key] == control for key in
            ('pitch_hz', 'pulse_depth', 'gate_target', 'gate', 'lung_pressure_dyn_cm2')),
        'switch_counterfactual_first_radiation': (first_radiation is not None
                                                and control * factor <= first_radiation < end * factor
                                                and first_radiation == browser_radiation
                                                and np.array_equal(dense_points, np.arange(control, end))),
        'switch_counterfactual_first_pcm': first_pcm is not None and control <= first_pcm < end,
    }
    precursor_frames = {key: compare_at(observed[key], trace[key][points], 0, points) for key in fields}
    return checks, {'first_difference_output_frames': first,
                    'first_radiation_internal_sample': first_radiation,
                    'first_radiation_output_frame': None if first_radiation is None else first_radiation // factor,
                    'first_browser_radiation_internal_sample': browser_radiation, 'pcm': pcm,
                    'pcm_significance_absolute': pcm_tolerance, 'browser_stages': precursor_frames}


def evaluate_zap(points, observed, native_trace, source, variant, spec, *, artifacts, execute, measurement, audio,
                 upper_pcm, factor):
    checks, metrics = boundary_checks(native_trace, source, variant, spec)
    request = metrics['zap_request_frame']
    control, end = (variant[key] for key in ('expected_zap_control', 'expected_zap_end'))
    zap = observed['call_id'] == CALL_IDS['zap']
    transitions = np.diff(zap.astype(int), prepend=0)
    launch = next(item['play_call'] for item in source['events'] if item['frame'] == request)
    pitch = np.clip(launch.get('pitch_hz') or spec['zap_keys']['initial_pitch_hz'], *spec['pitch_limits_hz'])
    active_pitch = (np.abs(observed['target_pitch_hz'] - pitch) <= spec['independent_control_absolute_tolerance'])
    matches = points[zap & active_pitch]
    checks.update({
        'browser_zap_start_and_end': points[transitions == 1].tolist() == [request]
                                    and points[transitions == -1].tolist() == [end],
        'browser_zap_first_control': bool(matches.size and matches[0] == control),
    })
    marks = {request - 1, request, control - 1, control, end - 1, end}
    label = variant['id']
    if label == 'official-prefix-48000':
        marks.add(variant['curves_sample'])
        pcm = wasm.compare_pcm(audio[request:], upper_pcm[request:], spec['pcm_absolute_tolerance'])
        checks['official_zap_interval_bits'] = pcm['first_bit_difference_frame'] is None
        metrics['official_zap_interval_pcm'] = {'start_frame': request, 'frames': len(audio) - request, **pcm}
    elif label == measurement['counterfactual']['variant']:
        marks.update((variant['edit_during_zap'], variant['edit_control']))
        counter_checks, counter = compare_without_switch(points, observed, native_trace, source, audio, factor,
                                                         measurement['counterfactual'], artifacts, execute)
        checks.update(counter_checks)
        metrics['without_switch'] = counter
    else:
        expected_pressure = observed['gate'] * (
            spec['cm_h2o_to_dyn_cm2'] * source['breath']['controls']['pressure_cm_h2o'])
        pressure = compare_at(observed['lung_pressure_dyn_cm2'], expected_pressure,
                              spec['zero_depth_pressure_absolute_tolerance_dyn_cm2'], points)
        phase = observed['pulse_phase'][(points >= control) & (points < end)]
        wraps = int(np.count_nonzero(np.diff(phase) < 0))
        checks['browser_no_pulse_modulation_with_phase_progress'] = (
            pressure['passed'] and bool(np.all(observed['pulse_depth'] == 0))
            and wraps == metrics['phase_wraps_during_zap'] and wraps > 0)
        metrics['browser_zero_depth'] = {'phase_wraps_during_zap': wraps, 'pressure': pressure}
    checks['browser_boundary_points_present'] = marks.issubset(set(points))
    metrics['snapshots'] = {
        str(frame): {key: float(observed[key][i]) for key in
                     ('call_id', 'target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz', 'pulse_rate_hz',
                      'target_duty', 'target_pressure_cm_h2o', 'target_pulse_depth', 'pulse_depth', 'pulse_phase',
                      'gate_target', 'gate', 'lung_pressure_dyn_cm2')}
        for i, frame in enumerate(points) if frame in marks
    }
    return checks, metrics


def compare_zap(label, baseline, config, source, artifacts, execute, browser, module):
    source = source | {'measurement': wasm.read_json(TRILL)['measurement'] | source['measurement']}
    return compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                           evaluate=evaluate_zap)


if __name__ == '__main__':
    extra_sources = (Path(__file__).resolve(), TRILL, OUTPUT_CASE, *(WORKSPACE / 'tools' / name for name in
                     ('measure_seal_trill.py', 'measure_seal_zap.py', 'measure_worklet_seal_trill.py')))
    raise SystemExit(run(CASE, SOURCE, compare_zap, 'seal_zap_switch_does_not_allocate', (44100,), __doc__,
                         extra_sources=extra_sources))
