"""seemsの初期舌先だけをそろえ、発話前の断面・放射・PCMを比較する。"""

import argparse
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_seems_amplitude_shimmer as shimmer
import measure_tsp_seems_drift_only as drift
import measure_tsp_seems_period_jitter as jitter
import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_output_gain import independent_stages
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_tip import component_output, nonzero, peak, radiated
from measure_tsp_fine_variation import FIELDS, first_difference
from measure_tsp_startup import resting_tip
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-seems-initial-tip.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_initial_geometry_probe.rs'
MODES = ('shimmer_zero', 'candidate', 'candidate_rest_tip')


def section_errors(reference, measured):
    a, b = reference['sections'], measured['sections']
    if [row[:2] for row in a] != [row[:2] for row in b]:
        raise ValueError('咽頭と口腔のセル番号が上流と一致しません')
    metrics = {}
    for tube in ('pharynx', 'oral'):
        x, y = (np.array([row[2:] for row in cells if row[0] == tube]) for cells in (a, b))
        measures = abs(x - y)
        metrics[tube] = {
            'count': len(x), 'length_cm': float(measures[:, 0].max()), 'area_cm2': float(measures[:, 1].max()),
            'minimum_cm2': float(measures[:, 2].max()),
            'effective_volume_cm3': float(np.max(abs(x[:, 0] * x[:, 1] - y[:, 0] * y[:, 1]))),
        }
    return metrics


def pcm_error(a, b, pre_roll, tolerance):
    delta = b.astype('f8') - a
    start, stop = pre_roll
    after = np.flatnonzero(abs(delta) > tolerance)
    return {'first_different_frame': first_difference(delta), 'first_over_limit_frame': int(after[0]) if after.size else None,
            'last_over_limit_frame': int(after[-1]) if after.size else None,
            'peak_frame': int(np.argmax(abs(delta))), 'peak_absolute_difference': peak(delta),
            'pre_roll_peak_absolute_difference': peak(delta[start:stop])}


def observe_output(study, signals, cfg, out):
    baseline = signals['shimmer_zero'][2]
    begin, end = study['pre_roll_frames']
    factor = study['internal_sample_rate_hz'] // study['sample_rate_hz']
    previous_peak = begin + int(np.argmax(abs(signals['candidate'][2][begin:end].astype('f8') - baseline[begin:end])))
    analysis = study | {'previous_peak_frame': previous_peak}
    diagnostics, source_changes, pcm, traces, windows = {}, {}, {}, {}, {}
    lpc_start = study['window_start_12khz']
    lpc_stop = lpc_start + study['window_samples_12khz']
    for name, (state, output, wave) in signals.items():
        diagnostics[name] = {
            'radiation': radiated(study, state, output),
            'components': component_output(analysis, state, output),
            'independent': independent_stages(output, wave, study['base_gain'], study),
        }
        pcm[name] = {'first_nonzero_frame': nonzero(wave), 'pre_roll_peak': peak(wave[begin:end]),
                     **pcm_error(baseline, wave, study['pre_roll_frames'], study['limits']['full_pcm'])}
        source_changes[name] = {key: first_difference(state[key] - signals['shimmer_zero'][0][key]) for key in FIELDS}
        traces.update({f'{name}_{key}': values[begin * factor:end * factor] for key, values in state.items()})
        traces[f'{name}_pcm'] = wave[begin:end]
        windows[name] = tsp.analysis_downsample(wave.astype(float), cfg)[lpc_start:lpc_stop]
    np.savez_compressed(out / 'pre-roll.npz', **traces)
    np.savez_compressed(out / 'lpc-windows.npz', **windows)
    limits = study['limits']
    independent_limit = limits['independent_normalized']
    diagnostics_pass = all(
        row['radiation']['timeline_matches'] and row['radiation']['sum_peak_error_cm3_s'] <= limits['radiation_sum_cm3_s']
        and row['radiation']['difference_peak_error_cm3_s2'] <= limits['radiation_identity_cm3_s2']
        and not row['components']['pre_roll_limited'] and row['components']['sum_peak_error_after_dc'] <= independent_limit
        and row['independent']['hold_error_frames'] == 0 and row['independent']['pcm_matches_independent_limiter']
        and all(row['independent'][key] <= independent_limit for key in
                ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
        for row in diagnostics.values())
    same_window = all(np.array_equal(frame, windows['shimmer_zero']) for frame in windows.values())
    return diagnostics_pass, same_window, {
        'pcm': pcm, 'diagnostics': diagnostics, 'first_internal_difference_to_upstream': source_changes,
        'baseline_pre_roll_peak_frame': previous_peak, 'pre_roll_frame_interval': [begin, end],
        'lpc_window_12khz_frame_interval': [lpc_start, lpc_stop],
    }


def measure(case, base, cfg, original, references, archived, out, execute):
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    measured_path = out / 'shimmer_zero-initial-geometry.json'
    execute([str(probe)], cwd=UPSTREAM, stdout=measured_path)
    upstream_geometry = tsp.read(measured_path)
    tip = upstream_geometry['tongue_tip_cm']
    pose = tsp.read(original)['speech_voice']['posture']
    predicted_tip = resting_tip(pose)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'geometry_continuity'],
            cwd=UPSTREAM, stdout=out / 'upstream-geometry-tests.log')
    observation = {**base, 'trace_frames': case['frames']}
    signals, upstream_checks, _, _ = drift.capture(
        observation, original, references['upstream.wav'], out, execute,
        variants={'upstream': 'default', 'shimmer_zero': 'zero'})
    signals.pop('upstream')
    candidate_signals, _, candidate_checks, same_plan = jitter.candidate_capture(
        observation, original, references['candidate.wav'], references['inspect.json'], out, execute,
        adjustment=('candidate_rest_tip', 'tongue_tip_cm', tip), adjustment_section='posture', snapshot_request=CASE)
    signals.update(candidate_signals)
    if any(signal[2].shape != (case['frames'],) for signal in signals.values()):
        raise ValueError('全PCMのフレーム数が登録内容と一致しません')
    study = {**case, **base, 'limits': base['limits'] | case['limits']}
    diagnostics_pass, same_window, result = observe_output(study, signals, cfg, out)
    initial = {name: tsp.read(out / f'{name}-initial-geometry.json') for name in MODES}
    sections = {name: section_errors(upstream_geometry, initial[name]) for name in ('candidate', 'candidate_rest_tip')}
    limits = case['limits']
    peak_sources = result['diagnostics']['candidate']['components']['at_previous_peak_frame']
    simultaneous_rest = all(row['length_cm'] <= limits['geometry_cm']
                            and max(row['area_cm2'], row['minimum_cm2']) <= limits['geometry_cm2']
                            for row in sections['candidate_rest_tip'].values())
    pcm = result['pcm']
    checks = {
        'independent_rest_tip': upstream_geometry['tip_free'] and upstream_geometry['jaw_cm'] == pose['jaw_cm']
            and upstream_geometry['tongue_body_cm'] == pose['tongue_body_cm']
            and peak(np.asarray(tip) - predicted_tip) <= limits['tip_cm'],
        'initial_geometry_before_render': all(state['completed_frames'] == 0 for state in initial.values())
            and all(np.isfinite([value for row in state['sections'] for value in row[2:]]).all() for state in initial.values()),
        'ordinary_cli_and_plans_match': upstream_checks['default_matches_ordinary_pcm']
            and upstream_checks['ordinary_matches_archived_wav'] and upstream_checks['same_plan']
            and candidate_checks['candidate']['default_wav_matches_archive'] and same_plan
            and all(item['pcm_matches_candidate_cli'] for item in candidate_checks.values()),
        'matched_baselines_agree_with_previous_pcm': upstream_checks['shimmer_zero'] == archived['pcm_verification']['shimmer_zero']
            and candidate_checks['candidate'] == archived['pcm_verification']['candidate'],
        'independent_radiation_components_and_pcm': diagnostics_pass,
    }
    predictions = {
        'rest_tip_matches_initial_geometry': simultaneous_rest and sections['candidate']['oral']['area_cm2'] > limits['geometry_cm2'],
        'rest_tip_removes_preroll': pcm['candidate_rest_tip']['pre_roll_peak_absolute_difference'] <= limits['pre_roll_pcm']
            and pcm['candidate_rest_tip']['first_nonzero_frame'] == pcm['shimmer_zero']['first_nonzero_frame']
            and abs(peak_sources['lip_cm3_s']) > max(abs(peak_sources['nose_cm3_s']), abs(peak_sources['wall_cm3_s'])),
        'rest_tip_matches_full_pcm_within_limit': pcm['candidate_rest_tip']['peak_absolute_difference'] <= limits['full_pcm'],
    }
    return {'checks': checks, 'predictions': predictions, **result, 'section_errors': sections, 'lpc_inputs_match': same_window,
            'initial_tip_cm': {'upstream': tip, 'candidate': pose['tongue_tip_cm'], 'independent': predicted_tip},
            'pcm_verification': upstream_checks | candidate_checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference = tsp.open_run(case['reference'], revision)
    shimmer_case, shimmer_path = saved_case(reference, shimmer.CASE)
    jitter_run = tsp.open_run(shimmer_case['reference'], revision)
    jitter_case, jitter_path = saved_case(jitter_run, jitter.CASE)
    base, cfg, original, references, paths = jitter.reference_inputs(jitter_case, revision)
    archived = tsp.verified_path(reference, 'summary.json')
    inputs = [CASE, Path(__file__).resolve(), PROBE, Path(shimmer.__file__), shimmer_path, jitter_path,
              archived, reference[0] / 'manifest.json', jitter_run[0] / 'manifest.json',
              *(WORKSPACE / 'tools' / key for key in ('tsp_transfer_request.rs', 'candidate_tsp_tract_snapshot.rs',
                  'measure_tsp_fine_tip.py', 'measure_tsp_startup.py')),
              *(UPSTREAM / 'crates/chimera' / key for key in ('src/anatomy/human.rs', 'src/control/articulators.rs',
                  'src/voice/human_airway.rs', 'src/airway/network.rs', 'tests/geometry_continuity.rs')),
              *paths]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, base, cfg, original, references, tsp.read(archived), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
