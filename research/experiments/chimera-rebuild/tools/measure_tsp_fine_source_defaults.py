"""確認用07で固定上流の既定の揺らぎを指定し、声門からPCMまで照合する。"""

import argparse
from copy import deepcopy
import gzip
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import independent_stages, trace_input
from measure_glottal_cycle import cycle_factors
from measure_glottal_pitch import independent_pitch
from measure_speech_timing import read, write
from measure_tsp_coat_to import DICT
from measure_tsp_fine_gain import render_cli
from measure_tsp_fine_tip import peak, radiated, read_series
from measure_tsp_fine_variation import FIELDS, LOCAL, signal_difference, wave_difference
from measure_tsp_listening import ROOT, hydrate_run, snapshot_case
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fine-source-defaults.json'


def capture(study, source, out, execute):
    probe = build_upstream_probe(LOCAL, out, execute, upstream=WORKSPACE, lto='off',
                                 package='vocal-core', extra_libraries=('serde_json',),
                                 cargo_args=('--offline',))
    pcm_path = out / 'probe.f32le'
    state_path = out / 'source.f64le'
    output_path = out / 'output.f64le'
    amplitude_path = out / 'cycle-amplitude.f64le'
    with TemporaryDirectory(prefix='tsp-source-defaults-', dir=out.parent / 'tmp') as directory:
        dictionary = Path(directory) / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        execute([str(probe), str(source), str(dictionary), str(study['trace_frames']),
                 str(study['initial_f0_hz']), str(study['speaking_f0_hz']),
                 *map(str, (state_path, pcm_path, output_path, amplitude_path))])
    return pcm_path, state_path, output_path, amplitude_path


def phase_checks(study, f0_unmodulated, states, amplitude, out):
    variation = study['source_variation']
    fs = study['internal_sample_rate_hz']
    pitch_cfg = {'sample_count': len(f0_unmodulated), 'update_interval_samples': study['update_interval_samples'],
                 'drift_seed': study['drift_seed']}
    pitch_params = {'f0_hz': 1.0, 'vibrato_depth_cents': 0.0, 'vibrato_rate_hz': 6.0,
                    'drift_cents': variation['pitch_drift_cents']}
    expected_f0 = f0_unmodulated * independent_pitch(pitch_cfg, pitch_params, fs)
    parameters = {'cycle_seed': study['cycle_seed'], 'jitter': variation['period_jitter'],
                  'shimmer': variation['amplitude_shimmer']}
    results = {}
    for name, source in states.items():
        advance = np.diff(source['phase'], prepend=0.0)
        wraps = advance < 0.0
        indices = np.flatnonzero(wraps)
        cycle = np.cumsum(wraps)
        periods, amplitudes = cycle_factors(parameters, len(indices))
        advance_error = advance + wraps - (expected_f0 / fs) / periods[np.r_[0, cycle[:-1]]]
        results[name] = {'f0_peak_error_hz': peak(expected_f0 - source['f0_hz']),
                         'phase_increment_peak_error_cycles': peak(advance_error),
                         'cycle_count': len(indices), 'first_wrap_sample': int(indices[0]) if len(indices) else None}
        if name == 'candidate':
            results[name]['cycle_amplitude_peak_error'] = peak(amplitude - amplitudes[cycle])
            table = np.column_stack((indices, periods[1:], amplitudes[1:], amplitude[indices]))
            np.savetxt(out / 'cycle-boundaries.csv', table, delimiter=',', fmt=('%d', '%.17g', '%.17g', '%.17g'),
                       header='internal_sample,expected_period_scale,expected_amplitude_scale,observed_amplitude_scale',
                       comments='')
    return results


def measure(study, paths, out, execute):
    base_case = read(paths['resting-tip-case.json'])
    case = deepcopy(base_case)
    case['speech_voice']['source_variation'] = study['source_variation']
    source = out / 'source-defaults-case.json'
    write(source, case)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'body_mix', '--test',
             'engine', '--test', 'lung_port'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'],
            stdout=out / 'candidate-tests.log')
    (rate, ordinary), plan = render_cli('source-defaults', source, out, execute)
    pcm_path, state_path, output_path, amplitude_path = capture(study, source, out, execute)
    old_rate, baseline = wavfile.read(paths['resting-tip.wav'])
    waveform = {'candidate': ordinary, 'candidate_zero': baseline, 'probe': np.fromfile(pcm_path, dtype='<f4'),
                'upstream': np.fromfile(paths['upstream.f32le'], dtype='<f4')}
    if any(wave.dtype != np.float32 or wave.shape != (study['frames'],) or not np.isfinite(wave).all()
           for wave in waveform.values()):
        raise ValueError('PCMの形式・長さ・有限性が登録条件と一致しません')
    count = study['trace_frames']
    factor = study['internal_sample_rate_hz'] // study['sample_rate_hz']
    internal_count = count * factor
    traces = {'candidate': read_series(state_path, internal_count),
              'candidate_zero': {key: value[:internal_count] for key, value in
                                  read_series(paths['resting-tip-source.f64le'], study['frames'] * factor).items()},
              'upstream': read_series(paths['upstream-source.f64le'], internal_count),
              'upstream_zero': read_series(paths['upstream_zero-source.f64le'], internal_count)}
    amplitude = np.fromfile(amplitude_path, dtype='<f8')
    if amplitude.shape != (internal_count,) or not np.isfinite(amplitude).all():
        raise ValueError('声門振幅の観測系列が登録した長さまたは有限性を満たしません')
    states = {name: traces[name] for name in ('upstream', 'candidate')}
    independent_source = phase_checks(study, traces['upstream_zero']['f0_hz'], states, amplitude, out)
    output_data = {'candidate': trace_input(output_path, count),
                   'upstream': trace_input(paths['upstream-output.f64le'], count)}
    radiation = {name: radiated(study, values, output_data[name]) for name, values in states.items()}
    replay = {name: independent_stages(output_data[name], waveform[name][:count], study['base_gain'], study)
              for name in states}
    upstream, candidate = states['upstream'], states['candidate']
    pcm = {name: wave_difference(study, waveform['upstream'], waveform[name])
           for name in ('candidate_zero', 'candidate')}
    separate = {name: signal_difference(upstream[name], candidate[name]) for name in FIELDS}
    within = {name: signal_difference(traces['candidate_zero'][name], candidate[name]) for name in FIELDS}
    phase_error = np.abs(upstream['phase'] - candidate['phase'])
    circular_error = peak(np.minimum(phase_error, 1.0 - phase_error))
    tol = study['tolerance']
    baseline_plan = read(paths['resting-tip-plan.json'])
    phase_pass = circular_error <= tol['phase_cycles']
    pcm_pass = pcm['candidate']['peak_error'] <= tol['significant_pcm']
    predictions = {'pcm_matches_upstream': pcm_pass, 'phase_matches_upstream': phase_pass,
                   'variation_begins_before_gate': all(within[key]['first_unequal_sample'] == 0
                                                      for key in ('f0_hz', 'phase'))
                   and candidate['gate'][0] == 0.0 and within['gate']['first_unequal_sample'] is None}
    return {
        'checks': {
            'ordinary_pcm_matches_probe': rate == old_rate == study['sample_rate_hz']
            and bit_equal(ordinary, waveform['probe']),
            'same_plan_and_only_source_variation_changed': all(plan[key] == baseline_plan[key] for key in
                ('speech', 'gestures', 'output_frames', 'control_block_internal_samples', 'decimation_factor'))
            and case == {'speech_voice': base_case['speech_voice'] | {'source_variation': study['source_variation']}},
            'independent_source': all(row['f0_peak_error_hz'] <= tol['f0_hz']
                                      and row['phase_increment_peak_error_cycles'] <= tol['phase_cycles']
                                      and row['cycle_count'] > 0 for row in independent_source.values())
            and independent_source['candidate']['cycle_amplitude_peak_error'] <= tol['cycle_amplitude_scale'],
            'radiation_identity': all(row['timeline_matches']
                                      and row['sum_peak_error_cm3_s'] <= tol['radiation_derivative_cm3_s2']
                                      / study['internal_sample_rate_hz']
                                      and row['difference_peak_error_cm3_s2'] <= tol['radiation_derivative_cm3_s2']
                                      for row in radiation.values()),
            'independent_output': all(all(row[key] <= tol['independent_normalized'] for key in
                                          ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
                                      and row['hold_error_frames'] == 0 and row['pcm_matches_independent_limiter']
                                      for row in replay.values()),
            **predictions,
        },
        'hypotheses': predictions, 'frames': study['frames'], 'observed_internal_samples': internal_count,
        'internal_columns': FIELDS, 'source_variation': study['source_variation'],
        'pcm_comparisons': pcm, 'upstream_to_candidate': separate, 'candidate_zero_to_default': within,
        'phase_circular_peak_error_cycles': circular_error, 'independent_source': independent_source,
        'radiation_identity': radiation, 'independent_output': replay,
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
    resting = hydrate_run(study['resting_run'], study['resting_case'], rev)
    reference = hydrate_run(study['reference_run'], study['reference_case'], rev)
    base_case = snapshot_case(resting, study['resting_case'])
    upper_case = snapshot_case(reference, study['reference_case'])
    base, upper = read(base_case), read(upper_case)
    keys = ('recording_id', 'frames', 'sample_rate_hz', 'internal_sample_rate_hz', 'stage',
            'initial_f0_hz', 'speaking_f0_hz', 'attention_frames')
    if (any(base[key] != study[key] or upper[key] != study[key] for key in keys)
            or base['reference_run'] != study['reference_run'] or base['base_gain'] != study['base_gain']
            or upper['trace_frames'] != study['trace_frames']):
        parser.error('初期舌先をそろえたケースと固定上流の保存条件が登録と一致しません')
    paths = {name: verified_file(*resting, f'artifacts/{name}') for name in
             ('resting-tip-case.json', 'resting-tip-plan.json', 'resting-tip.wav', 'resting-tip-source.f64le')}
    paths.update({name: verified_file(*reference, f'artifacts/{name}') for name in
                  ('upstream.f32le', 'upstream-source.f64le', 'upstream_zero-source.f64le', 'upstream-output.f64le')})
    inputs = [CASE, Path(__file__).resolve(), LOCAL, DICT, base_case, upper_case, *paths.values(),
              resting[0] / 'manifest.json', reference[0] / 'manifest.json',
              *(WORKSPACE / 'tools' / name for name in ('tsp_fine_trace.rs', 'measure_tsp_fine_tip.py',
                'measure_tsp_fine_gain.py', 'measure_tsp_fine_variation.py', 'measure_glottal_pitch.py',
                'measure_glottal_cycle.py', 'measure_turbulence.py', 'measure_duet_child_output_gain.py',
                'measure_duet_child_glottal_noise_origin.py', 'measure_tsp_coat_to.py',
                'measure_csd_envelope_timing.py', 'measure_tsp_listening.py', 'measure_speech_timing.py',
                'measure_uniform_tube.py', 'upstream_baseline.py')), *candidate_sources()]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
                'invoked_from': str(Path.cwd()), 'arguments': sys.argv[1:]}
    return record_measurement(args.run_id, CASE, inputs, metadata, lambda out, run: measure(study, paths, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
