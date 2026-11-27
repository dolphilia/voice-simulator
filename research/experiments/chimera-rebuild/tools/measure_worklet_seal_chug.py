"""アザラシの chug の粗さと呼気・声門の周期を実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_wasm_fixed as wasm
from measure_seal_chug import CASES, boundary_checks, cycle_checks
from measure_seal_trill import CASE as TRILL, CALL_IDS, OUTPUT_CASE, glottis_internal
from measure_seal_whistle import CASE as WHISTLE
from measure_seal_zap import CASE as ZAP
from measure_worklet_seal_sustain import run
from measure_worklet_seal_trill import compare_variant
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-seal-chug.json'
SOURCE = CASES[2]


def browser_cycles(points, observed, start, end, rate, factor, spec, registered):
    if not np.array_equal(points, np.arange(len(points))):
        raise ValueError('周期倍率の復元には全出力フレームの観測が必要です')
    cycle_flags, cycle = cycle_checks(observed, rate, start, spec)
    control_phase = observed['pulse_phase'][start:end]
    breath_wraps = np.flatnonzero(np.diff(control_phase) < 0) + start + 1
    voice_phase = glottis_internal(observed, 'glottis_phase', factor)[start * factor:end * factor]
    voice_wraps = np.flatnonzero(np.diff(voice_phase) < spec['glottal_cycle']['phase_jump_for_wrap'])
    lower, upper = registered['glottis_wraps_during_call_range']
    checks = {f'browser.{key}': value for key, value in cycle_flags.items()}
    checks.update({
        'browser_breath_wraps': len(breath_wraps) == registered['breath_wraps_during_call'],
        'browser_glottis_wraps': lower <= len(voice_wraps) <= upper,
    })
    return checks, {
        'browser_glottal_cycle': cycle,
        'breath_wraps_during_call': len(breath_wraps),
        'breath_wrap_output_frames': breath_wraps.tolist(),
        'glottal_wraps_during_call': len(voice_wraps),
    }


def evaluate_chug(points, observed, native_trace, source, variant, spec, *, measurement, audio, upper_pcm,
                  factor, **_capture):
    checks, native = boundary_checks(native_trace, source, variant, spec)
    request = native['request_frame']
    start, end = (variant[key] for key in ('expected_start_control', 'expected_end'))
    rate = source['breath']['sample_rate_hz']
    active = observed['call_id'] == CALL_IDS['chug']
    transitions = np.diff(active.astype(int), prepend=0)
    keys = spec['chug_keys']
    first = points[active & (np.abs(observed['target_roughness'] - keys['initial_roughness'])
                             <= spec['independent_control_absolute_tolerance'])]
    checks.update({
        'browser_chug_start_and_end': points[transitions == 1].tolist() == [request]
                                     and points[transitions == -1].tolist() == [end],
        'browser_chug_first_control': bool(first.size and first[0] == start),
    })
    marks = {request - 1, request, start - 1, start, end - 1, end,
             variant['roughness_sample'], variant['fade_sample']}
    if 'manual_edit_sample' in variant:
        edit = variant['manual_edit_sample']
        stride = spec['control_frames']
        next_control = ((edit + stride - 1) // stride) * stride
        marks.update((edit - 1, edit, next_control - 1, next_control))
    checks['browser_boundary_points_present'] = marks.issubset(set(points))
    snapshots = {
        str(frame): {key: float(observed[key][i]) for key in
                     ('call_id', 'target_pitch_hz', 'pitch_hz', 'target_pulse_rate_hz', 'pulse_rate_hz',
                      'target_pressure_cm_h2o', 'lung_pressure_dyn_cm2', 'target_roughness', 'roughness',
                      'gate_target', 'pulse_phase', 'glottis_phase_0', 'glottis_f0_hz_0', 'glottis_area_cm2_0')}
        for i, frame in enumerate(points) if frame in marks
    }
    metrics = {'request_frame': request, 'first_control_frame': int(first[0]) if first.size else None,
               'end_frame': end, 'snapshots': snapshots, 'native_glottal_cycle': native['glottal_cycle']}
    cycle = measurement['browser_cycle']
    if variant['id'] == cycle['variant']:
        cycle_checks_, cycles = browser_cycles(points, observed, start, end, rate, factor, spec, cycle)
        checks.update(cycle_checks_)
        metrics.update(cycles)
    if variant['id'] == 'official-prefix-48000':
        actual, upper = audio[request:], upper_pcm[request:]
        pcm = wasm.compare_pcm(actual, upper, spec['pcm_absolute_tolerance'])
        offset = pcm['first_bit_difference_frame']
        checks['official_chug_segment'] = pcm['first_frame_over_tolerance'] is None
        metrics['official_chug_segment_pcm'] = {
            **pcm, 'frames': len(actual), 'start_frame': request,
            'first_bit_difference_output_frame': None if offset is None else request + offset,
            'different_bits': int(np.count_nonzero(actual.view('u4') != upper.view('u4'))),
        }
    return checks, metrics


def compare_chug(label, baseline, config, source, artifacts, execute, browser, module):
    spec = (wasm.read_json(TRILL)['measurement'] | wasm.read_json(ZAP)['measurement']
            | wasm.read_json(WHISTLE)['measurement'] | source['measurement'])
    return compare_variant(label, baseline, config, source | {'measurement': spec}, artifacts, execute,
                           browser, module, evaluate=evaluate_chug)


if __name__ == '__main__':
    extra_sources = (Path(__file__).resolve(), TRILL, ZAP, WHISTLE, OUTPUT_CASE,
                     *(WORKSPACE / 'tools' / name for name in (
                         'measure_worklet_seal_trill.py', 'measure_seal_trill.py', 'measure_seal_zap.py',
                         'measure_seal_whistle.py', 'measure_seal_chug.py', 'measure_glottal_cycle.py',
                         'measure_glottal_coupling.py', 'measure_turbulence.py', 'measure_junction.py',
                         'measure_pcm_output.py')))
    raise SystemExit(run(CASE, SOURCE, compare_chug, 'seal_chug_render_does_not_allocate', (44100,), __doc__,
                         extra_sources=extra_sources))
