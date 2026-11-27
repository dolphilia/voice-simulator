"""TSP確認用07で、初期舌先による放射とPCMの過渡を比較する。"""

import argparse
from copy import deepcopy
import gzip
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

from measure_csd_envelope_timing import verified_file
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import COLUMNS, decimate_radiation, independent_stages, trace_input
from measure_speech_timing import read, write
from measure_tsp_coat_to import DICT
from measure_tsp_fine_gain import render_cli
from measure_tsp_fine_variation import FIELDS, signal_difference, wave_difference
from measure_tsp_listening import ROOT, hydrate_run, snapshot_case
from measure_tsp_startup import resting_tip
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fine-initial-tip.json'
UPPER_PROBE = WORKSPACE / 'tools/upstream_tsp_rest_tip_probe.rs'
COMPONENTS = ('lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s')


def capture(study, source, observer, out, execute):
    with TemporaryDirectory(prefix='tsp-initial-tip-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        raw = scratch / 'resting-tip.f32le'
        internal = out / 'resting-tip-source.f64le'
        output = out / 'resting-tip-output.f64le'
        execute([str(observer), str(source), str(dictionary), str(study['frames']),
                 str(study['initial_f0_hz']), str(study['speaking_f0_hz']),
                 str(internal), str(raw), str(output)])
        return np.fromfile(raw, dtype='<f4'), internal, output


def read_series(path, count=None):
    series = np.fromfile(path, dtype='<f8').reshape(-1, len(FIELDS))
    if (count is not None and len(series) != count) or not np.isfinite(series).all():
        raise ValueError(f'内部系列が登録した長さまたは有限性の条件を満たしません ({path.name})')
    return dict(zip(FIELDS, series.T, strict=True))


def peak(values):
    return float(np.max(np.abs(values)))


def nonzero(values):
    hits = np.flatnonzero(values)
    return int(hits[0]) if hits.size else None


def radiated(study, source, output):
    rate = study['internal_sample_rate_hz']
    total = source['total_cm3_s']
    derivative = source['radiation_derivative_cm3_s2']
    return {
        'sum_peak_error_cm3_s': peak(total - sum(source[key] for key in COMPONENTS)),
        'difference_peak_error_cm3_s2': peak(derivative - np.diff(total, prepend=0.0) * rate),
        'timeline_matches': bool(np.array_equal(derivative, output[:, :2].ravel())),
    }


def component_output(study, source, output):
    start, stop = study['pre_roll_frames']
    sample_rate = study['sample_rate_hz']
    internal_rate = study['internal_sample_rate_hz']
    factor = internal_rate // sample_rate
    pre = slice(start, stop)
    stage = study['stage']
    pole = math.exp(-math.tau * stage['dc_hz'] / sample_rate)
    values = {}
    for name in COMPONENTS:
        flow = source[name][:stop * factor]
        derivative = np.diff(flow, prepend=0.0) * internal_rate
        fir = decimate_radiation(derivative, factor, stage)
        values[name] = lfilter([1, -1], [1, -pole], fir * study['base_gain'])
    return {
        'peak_by_component': {name: peak(value[pre]) for name, value in values.items()},
        'at_previous_peak_frame': {name: float(value[study['previous_peak_frame']]) for name, value in values.items()},
        'sum_peak_error_after_dc': peak(sum(values.values())[pre] - output[pre, COLUMNS.index('dc_removed')]),
        'pre_roll_limited': bool(np.any(output[pre, COLUMNS.index('envelope')] > stage['peak_threshold'])),
    }


def measure(study, paths, out, execute):
    source = read(paths['matched-case.json'])
    posture = source['speech_voice']['posture']
    probe = build_upstream_probe(UPPER_PROBE, out, execute, cargo_args=('--offline',))
    measured_tip = out / 'upstream-initial-tip.json'
    execute([str(probe)], cwd=UPSTREAM, stdout=measured_tip)
    jaw, body_x, body_y, *tip = read(measured_tip)
    predicted_tip = resting_tip(posture)
    predicted_error = peak(np.asarray(predicted_tip) - tip)
    substitute = deepcopy(source)
    substitute['speech_voice']['posture']['tongue_tip_cm'] = tip
    variant = out / 'resting-tip-case.json'
    write(variant, substitute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'body_mix', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'],
            stdout=out / 'candidate-tests.log')
    (rate, ordinary), plan = render_cli('resting-tip', variant, out, execute)
    native, state_path, output_path = capture(study, variant, paths['observer'], out, execute)
    stored_rate, baseline = wavfile.read(paths['matched.wav'])
    upstream = np.fromfile(paths['upstream_zero.f32le'], dtype='<f4')
    expected_frames = (study['frames'],)
    if any(value.shape != expected_frames or not np.isfinite(value).all() for value in (upstream, baseline, ordinary, native)):
        raise ValueError('PCMの長さか有限性が登録条件と一致しません')
    reference_count = study['reference_trace_frames']
    internal_count = study['frames'] * study['internal_sample_rate_hz'] // study['sample_rate_hz']
    output = {'upstream': trace_input(paths['upstream_zero-output.f64le'], reference_count),
              'base': trace_input(paths['matched-output.f64le'], study['frames']),
              'resting_tip': trace_input(output_path, study['frames'])}
    traces = {'upstream': read_series(paths['upstream_zero-source.f64le'], reference_count * 2),
              'base': read_series(paths['base-source.f64le'], internal_count),
              'resting_tip': read_series(state_path, internal_count)}
    acoustic = {name: radiated(study, values, output[name]) for name, values in traces.items()}
    components = {name: component_output(study, values, output[name]) for name, values in traces.items()}
    replay = independent_stages(output['resting_tip'], native, study['base_gain'], study)
    tol = study['tolerance']
    plan_fields = ('speech', 'gestures', 'output_frames', 'control_block_internal_samples', 'decimation_factor')
    base_plan = read(paths['matched-plan.json'])
    exact = {
        'only_initial_tip_changed': substitute == source | {'speech_voice': source['speech_voice']
                                                             | {'posture': posture | {'tongue_tip_cm': tip}}}
        and source['speech_voice']['voice']['output_gain'] == study['base_gain']
        and posture['tongue_tip_cm'] != tip,
        'independent_tip_position': [jaw, body_x, body_y] == [posture['jaw_cm'], *posture['tongue_body_cm']]
        and predicted_error <= tol['tip_cm'],
        'identical_plan_and_ordinary_pcm': all(plan[key] == base_plan[key] for key in plan_fields)
        and rate == stored_rate == study['sample_rate_hz'] and bit_equal(ordinary, native),
        'radiation_identity': all(result['timeline_matches']
                                  and result['sum_peak_error_cm3_s'] <= tol['radiation_derivative_cm3_s2']
                                  / study['internal_sample_rate_hz']
                                  and result['difference_peak_error_cm3_s2'] <= tol['radiation_derivative_cm3_s2']
                                  for result in acoustic.values()),
        'linear_component_sum_in_pre_roll': all(not row['pre_roll_limited']
                                                and row['sum_peak_error_after_dc'] <= tol['independent_normalized']
                                                for row in components.values()),
        'independent_output_stages': all(replay[key] <= tol['independent_normalized'] for key in
                                         ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
        and replay['hold_error_frames'] == 0 and replay['pcm_matches_independent_limiter'],
    }
    start, stop = study['pre_roll_frames']
    pcm = {'upstream': upstream, 'base': baseline, 'resting_tip': ordinary}
    peaks = {name: peak(wave[start:stop]) for name, wave in pcm.items()}
    first = {name: nonzero(wave) for name, wave in pcm.items()}
    left, right = traces['base'], traces['resting_tip']
    per_state = {key: signal_difference(left[key], right[key]) for key in FIELDS}
    delta = {name: wave_difference(study, upstream, pcm[name]) for name in ('base', 'resting_tip')}
    known_peak = components['base']['at_previous_peak_frame']
    return {
        'checks': exact, 'hypotheses': {
            'pre_roll_pcm_within_tolerance': peaks['resting_tip'] <= tol['pre_roll_pcm'],
            'first_nonzero_agrees': first['upstream'] == first['resting_tip'] == study['expected_reference_first_nonzero_frame'],
            'lip_dominates_previous_peak': abs(known_peak['lip_cm3_s']) > abs(known_peak['wall_cm3_s']),
        }, 'initial_tip_cm': {'base': posture['tongue_tip_cm'], 'resting_tip': tip, 'independent': predicted_tip,
                              'max_error_cm': predicted_error}, 'frames': study['frames'], 'observed_internal_samples': internal_count,
        'internal_columns': FIELDS, 'output_columns': COLUMNS, 'pre_roll_peak_pcm': peaks, 'first_nonzero_pcm_frame': first,
        'first_state_differences_base_to_resting_tip': per_state, 'pcm_comparisons': delta,
        'radiation_identity': acoustic, 'pre_roll_component_dc': components, 'independent_output': replay,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != rev or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版が必要です')
    baseline = hydrate_run(study['base_run'], study['base_case'], rev)
    upstream = hydrate_run(study['reference_run'], study['reference_case'], rev)
    base_case = snapshot_case(baseline, study['base_case'])
    reference_case = snapshot_case(upstream, study['reference_case'])
    base, reference = read(base_case), read(reference_case)
    keys = ('recording_id', 'frames', 'sample_rate_hz', 'internal_sample_rate_hz', 'stage')
    if (any(base[k] != study[k] or reference[k] != study[k] for k in keys)
            or base['reference_run'] != study['reference_run'] or base['matched_gain'] != study['base_gain']):
        parser.error('元のゲイン照合と上流の対照が登録と一致しません')
    registered = study | {'reference_trace_frames': reference['trace_frames']}
    paths = {name: verified_file(*baseline, f'artifacts/{name}')
             for name in ('matched-case.json', 'matched.wav', 'base-source.f64le',
                          'matched-output.f64le', 'matched-plan.json')}
    paths.update({name: verified_file(*upstream, f'artifacts/{name}')
                  for name in ('upstream_zero.f32le', 'upstream_zero-source.f64le', 'upstream_zero-output.f64le')})
    paths['observer'] = verified_file(*baseline, 'artifacts/candidate_tsp_fine_probe-vocal-core.exe')
    inputs = [CASE, Path(__file__).resolve(), UPPER_PROBE, DICT, base_case, reference_case,
              *(WORKSPACE / 'tools' / name for name in ('measure_tsp_fine_gain.py', 'measure_tsp_fine_variation.py',
                'measure_duet_child_output_gain.py', 'measure_duet_child_glottal_noise_origin.py', 'measure_tsp_startup.py',
                'measure_tsp_coat_to.py', 'measure_csd_envelope_timing.py', 'measure_tsp_listening.py',
                'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py')),
              baseline[0] / 'manifest.json', upstream[0] / 'manifest.json', *paths.values(), *candidate_sources()]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
                'invoked_from': str(Path.cwd()), 'arguments': sys.argv[1:]}
    return record_measurement(args.run_id, CASE, inputs, metadata, lambda out, execute: measure(registered, paths, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
