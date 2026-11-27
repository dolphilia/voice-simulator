"""歌唱中の面積パルスの振幅揺らぎを固定上流と独立計算に照合する。"""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_bilabial_stop import capture_candidate
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_glottal_cycle import cycle_factors
from measure_song_schedule_drift import COLUMNS, compare_pair, load_candidate, load_upstream, read_json
from measure_song_schedule_jitter import calculate_phase
from measure_uniform_tube import candidate_sources, record_measurement
from measure_upstream_song_schedule_state import first_difference, relative_segments
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/song-voice-schedule-shimmer.json'
CANDIDATE_COLUMNS = COLUMNS | {'lip_area_cm2': 'lip_minimum_cm2'}


def expected_amplitudes(study, native, trace, start, factor):
    phase, cycles = calculate_phase(trace, start, native['source']['f0'], native['internal_rate_hz'], factor,
                                    study['period_jitter'], study['cycle_seed'])
    return cycle_amplitudes(study, phase, cycles)


def cycle_amplitudes(study, phase, cycles):
    wraps = np.r_[False, np.diff(phase) < 0]
    index = cycles - np.count_nonzero(wraps) + np.cumsum(wraps)
    _, amplitude = cycle_factors({'cycle_seed': study['cycle_seed'], 'jitter': study['period_jitter'],
                                  'shimmer': study['amplitude_shimmer']}, cycles)
    return amplitude[index], index


def measure(study, native, probe, references, artifacts, execute):
    rate, fs = native['output_rate_hz'], native['internal_rate_hz']
    factor = fs // rate
    lead = round(native['lead_seconds'] * rate)
    at = np.arange(-lead, native['comparison_samples'])
    window = lo, hi = study['voiced_window_frames']
    voiced = slice(lo + lead, hi + lead)
    expected_plan = [(ipa, t0, t1) for _, ipa, _, t0, t1 in relative_segments(probe['segments'], 0, rate)]
    checks, predictions, results, pcm = {}, {}, {}, {}
    transfer = ('glottal_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')

    for label, (start, noise, up_csv, up_pcm, source, base_csv, base_wav) in references.items():
        folder = artifacts / label
        folder.mkdir()
        case = read_json(source)
        case['song_voice']['voice']['amplitude_shimmer'] = study['amplitude_shimmer']
        candidate_file = folder / 'input.json'
        candidate_file.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        info, csv, paths = capture_candidate(candidate_file, study['host_block_frames'], folder, execute)
        wave, stage = paths[0]
        checks[f'{label}/block_invariance'] = all(
            sha256(w) == sha256(wave) and sha256(s) == sha256(stage) for w, s in paths[1:])
        segments = [s for phrase in info['song']['plan']['phrases'] for s in phrase['timing']['segments']]
        checks[f'{label}/score_and_rates'] = (
            [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead, round(s['end_seconds'] * rate) - lead)
             for s in segments] == expected_plan
            and info['output_frames'] == len(at) and info['decimation_factor'] == factor
            and info['control_block_internal_samples'] == 64 * factor)
        upstream = load_upstream(up_csv, up_pcm, at, start, lead)
        baseline = load_candidate(base_csv, base_wav, rate, at, lead, columns=CANDIDATE_COLUMNS)
        shimmer = load_candidate(csv, wave, rate, at, lead,
                                 columns=CANDIDATE_COLUMNS | {'cycle_amplitude': 'glottal_cycle_amplitude_scale'})
        observed_amplitude = shimmer[0]['cycle_amplitude']
        amplitude, cycle = expected_amplitudes(study, native, shimmer[0], start, factor)
        amplitude_error = float(abs(observed_amplitude - amplitude).max())
        checks[f'{label}/independent_cycle_amplitude'] = amplitude_error <= study['cycle_amplitude_tolerance']
        checks[f'{label}/active_voicing_window'] = all(
            float(trace['glottal_voicing'][voiced].min()) >= study['active_voicing_floor']
            for trace, _ in (upstream, baseline, shimmer))
        predictions[f'{label}/unchanged_phase_and_f0'] = all(
            np.array_equal(trace[key].view(np.uint64), shimmer[0][key].view(np.uint64))
            for trace, _ in (upstream, baseline) for key in ('glottal_phase_cycles', 'glottal_f0_hz'))
        pairs = {
            'upstream_to_zero_shimmer': (upstream, baseline),
            'upstream_to_matched_shimmer': (upstream, shimmer),
            'candidate_shimmer_only': (baseline, shimmer),
        }
        comparisons = {}
        for name, pair in pairs.items():
            row = compare_pair(*pair, at, native, window)
            row['stages']['lip_minimum_cm2'] = row['stages'].pop('lip_area_cm2')
            comparisons[name] = row
        old, new, direct = comparisons.values()
        checks[f'{label}/articulators_and_gate'] = (
            all(direct['stages'][key]['first_frame'] is None for key in ('gate', 'lip_minimum_cm2'))
            and new['stages']['lip_minimum_cm2']['first_frame'] is None)
        predictions[f'{label}/cross_engine_voiced_error_falls'] = (
            new['pcm_voiced_window_rms_difference'] < old['pcm_voiced_window_rms_difference'])
        predictions[f'{label}/cross_engine_area_flow_radiation_error_falls'] = all(
            new['stages'][key]['maximum_absolute_difference'] < old['stages'][key]['maximum_absolute_difference']
            for key in transfer)
        if noise == 0:
            arrivals = [direct['stages'][key]['first_frame'] for key in transfer]
            active = first_difference(shimmer[0]['glottal_voicing'], native['thresholds']['glottal_voicing'], at)
            first_pcm = direct['first_pcm_over_threshold']
            predictions[f'{label}/shimmer_propagates_without_turbulence'] = (
                active is not None and first_pcm is not None and all(f is not None for f in arrivals)
                and active <= min(arrivals) and max(arrivals) <= first_pcm)
        results[label] = comparisons | {
            'cycle_amplitude_error': amplitude_error,
            'cycle_index_first_and_last': [int(cycle[0]), int(cycle[-1])],
            'cycle_amplitude_range': [float(observed_amplitude.min()), float(observed_amplitude.max())],
            'voiced_window_cycle_amplitude_range': [float(observed_amplitude[voiced].min()),
                                                    float(observed_amplitude[voiced].max())],
        }
        pcm[noise, start] = [pair[1] for pair in (upstream, baseline, shimmer)]

    first, second = native['schedule_engine_frames']
    reservation = {
        str(noise): dict(zip(
            ('upstream', 'candidate_zero_shimmer', 'candidate_matched_shimmer'),
            (first_difference(abs(b.astype(float) - a), native['pcm_difference_floor'])
             for a, b in zip(pcm[noise, first], pcm[noise, second], strict=True)), strict=True))
        for noise in native['noise_scales']
    }
    return {'checks': checks | predictions, 'hypothesis_checks': predictions, 'arms': results,
            'between_schedule_first_pcm_over_threshold': reservation, 'relative_plan_frames': expected_plan,
            'voiced_window_frames': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    runs, inputs = {}, [CASE, Path(__file__).resolve()]
    for name in ('upstream', 'candidate'):
        ref = study[f'{name}_reference']
        path = CASE.parent / ref['case']
        run = run_manifest(ref['run'], read_json(path)['id'], revision)
        if run[1]['status'] != 'pass':
            parser.error(f'基準実行が合格していません ({ref["run"]})')
        runs[name] = run
        inputs.extend([path, run[0] / 'manifest.json', verified_path(run, 'summary.json')])
    native_file = verified_path(runs['upstream'], 'artifacts/native-input.json')
    probe_file = verified_path(runs['upstream'], 'artifacts/upstream/probe.json')
    native, probe = map(read_json, (native_file, probe_file))
    reference = native['source']
    cycle_case = CASE.parent / 'glottal-cycle-shimmer.json'
    if (reference['drift'] != study['pitch_drift_cents'] or reference['fry'] != 0
            or reference['vibratoDepth'] != 0 or reference['roughness'] != 0.1
            or not math.isclose(0.02 + 0.22 * reference['roughness'], study['amplitude_shimmer'], abs_tol=1e-15)
            or not math.isclose(0.0021 + 0.0245 * reference['roughness'], study['period_jitter'], abs_tol=1e-15)
            or read_json(cycle_case)['glottis']['params']['cycle_seed'] != study['cycle_seed']):
        parser.error('固定上流の音源が登録条件と一致しません')
    inputs.extend([native_file, probe_file, cycle_case])
    references = {}
    for noise in native['noise_scales']:
        for start in native['schedule_engine_frames']:
            label = f'frame-{start}-noise-{noise}'
            files = [verified_path(runs['upstream'], f'artifacts/upstream/{label}.{ext}') for ext in ('csv', 'f32le')]
            files.extend(verified_path(runs['candidate'], f'artifacts/{label}/{name}')
                         for name in ('input.json', 'voicing.csv', 'pcm-128.wav'))
            song = read_json(files[2])['song_voice']
            voice = song['voice']
            if (song['warm_up_frames'] != start or song['turbulence']['scale'] != noise
                    or voice.get('amplitude_shimmer', 0) != 0 or voice['period_jitter'] != study['period_jitter']
                    or voice.get('pitch_drift_cents', 0) != study['pitch_drift_cents']
                    or voice['base_pitch_hz'] != reference['f0']):
                parser.error(f'研究版の基準が登録条件と一致しません ({label})')
            references[label] = (start, noise, *files)
            inputs.extend(files)
    inputs.extend(candidate_sources())
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_bilabial_stop.py', 'measure_fan_crossing_allocations.py', 'measure_glottal_cycle.py',
        'measure_song_schedule_drift.py', 'measure_song_schedule_jitter.py', 'measure_turbulence.py',
        'measure_uniform_tube.py', 'measure_upstream_song_schedule_state.py', 'upstream_song_schedule_state_probe.rs'))
    inputs.extend(UPSTREAM / name for name in (
        'Cargo.lock', 'crates/chimera/src/math.rs', 'crates/chimera/src/sources/glottis.rs',
        'crates/chimera/src/voice/human_voice.rs'))
    details = {'case_id': study['id'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'upstream_reference_run': runs['upstream'][0].name, 'candidate_reference_run': runs['candidate'][0].name}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, native, probe, references, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
