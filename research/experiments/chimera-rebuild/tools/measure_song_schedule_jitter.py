"""歌唱CLIの周期ジッターを独立した位相積分と固定上流に照合する。"""

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
from measure_song_schedule_drift import compare_pair, load_candidate, load_upstream, phase_delta, read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_upstream_song_schedule_state import first_difference, relative_segments
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/song-voice-schedule-jitter.json'


def calculate_phase(trace, start, preface_f0, fs, factor, jitter, seed):
    """予備描画のF0（定数または出力レートの系列）と予約後の観測F0から位相を復元する。"""
    f0 = np.r_[np.broadcast_to(preface_f0, (start,)), trace['glottal_f0_hz']]
    increments = np.repeat(f0 / fs, factor)
    max_cycles = math.ceil(increments.sum() / 0.55)
    period, _ = cycle_factors({'jitter': jitter, 'shimmer': 0, 'cycle_seed': seed}, max_cycles)
    phase = 0.0
    cycle = 0
    result = np.empty(len(increments))
    for i, increment in enumerate(increments):
        phase += increment / period[cycle]
        if phase >= 1.0:
            phase -= 1.0
            cycle += 1
        result[i] = phase
    output = result[(start + 1) * factor - 1::factor]
    return output, cycle


def measure(study, native, probe, references, artifacts, execute):
    rate, fs = native['output_rate_hz'], native['internal_rate_hz']
    factor = fs // rate
    lead = round(native['lead_seconds'] * rate)
    at = np.arange(-lead, native['comparison_samples'])
    window = lo, hi = study['voiced_window_frames']
    tolerance = study['phase_tolerance_cycles']
    expected_plan = [(ipa, t0, t1) for _, ipa, _, t0, t1 in relative_segments(probe['segments'], 0, rate)]
    checks, predictions, rows, signals = {}, {}, {}, {}

    for label, (start, noise, up_csv, up_pcm, input_file, base_csv, base_wav) in references.items():
        candidate_dir = artifacts / label
        candidate_dir.mkdir()
        case = read_json(input_file)
        case['song_voice']['voice']['period_jitter'] = study['jitter']
        source = candidate_dir / 'input.json'
        source.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        report, csv, paths = capture_candidate(source, study['host_block_frames'], candidate_dir, execute)
        wave, stage = paths[0]
        checks[f'{label}/block_invariance'] = all(
            sha256(w) == sha256(wave) and sha256(s) == sha256(stage) for w, s in paths[1:])
        segments = [s for phrase in report['song']['plan']['phrases'] for s in phrase['timing']['segments']]
        checks[f'{label}/plan_and_rates'] = (
            [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead, round(s['end_seconds'] * rate) - lead)
             for s in segments] == expected_plan
            and report['output_frames'] == len(at) and report['decimation_factor'] == factor
            and report['control_block_internal_samples'] == 64 * factor)
        upstream = load_upstream(up_csv, up_pcm, at, start, lead)
        baseline = load_candidate(base_csv, base_wav, rate, at, lead)
        jitter = load_candidate(csv, wave, rate, at, lead)
        comparisons = {
            'upstream_to_zero_candidate': compare_pair(upstream, baseline, at, native, window),
            'upstream_to_matched_candidate': compare_pair(upstream, jitter, at, native, window),
            'candidate_jitter_only': compare_pair(baseline, jitter, at, native, window),
        }
        delta = comparisons['candidate_jitter_only']
        checks[f'{label}/candidate_source_settings_isolated'] = all(
            delta['stages'][key]['first_frame'] is None for key in ('gate', 'lip_opening_cm', 'glottal_f0_hz'))
        checks[f'{label}/active_voicing_window'] = all(
            float(trace['glottal_voicing'][lo + lead:hi + lead].min()) >= study['active_voicing_floor']
            for trace, _ in (upstream, baseline, jitter))
        phase_errors, cycles = {}, {}
        for name, (trace, _), coefficient in (('upstream', upstream, study['jitter']),
                                             ('candidate_zero', baseline, 0),
                                             ('candidate_jitter', jitter, study['jitter'])):
            model, cycles[name] = calculate_phase(trace, start, native['source']['f0'], fs, factor,
                                                  coefficient, study['cycle_seed'])
            phase_errors[name] = float(abs(phase_delta(trace['glottal_phase_cycles'], model)).max())
            checks[f'{label}/{name}_phase_integral'] = phase_errors[name] <= tolerance

        phases = [t['glottal_phase_cycles'] for t, _ in (upstream, baseline, jitter)]
        preface = [float(abs(phase_delta(t[:lead], phases[0][:lead])).max()) for t in phases[1:]]
        corrected = comparisons['upstream_to_matched_candidate']
        predictions[f'{label}/phase_matches_at_schedule'] = preface[0] > tolerance and preface[1] <= tolerance
        predictions[f'{label}/voiced_rms_error_falls'] = corrected['pcm_voiced_window_rms_difference'] < (
            comparisons['upstream_to_zero_candidate']['pcm_voiced_window_rms_difference'])
        predictions[f'{label}/pcm_difference_remains'] = corrected['first_pcm_over_threshold'] is not None
        if noise == 0:
            f = delta['first_pcm_over_threshold']
            arrivals = [delta['stages'][key]['first_frame'] for key in (
                'glottal_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')]
            voiced = first_difference(jitter[0]['glottal_voicing'], native['thresholds']['glottal_voicing'], at)
            predictions[f'{label}/jitter_propagates_without_turbulence'] = (
                delta['stages']['glottal_phase_cycles']['first_frame'] == int(at[0])
                and f is not None and voiced is not None and all(p is not None for p in arrivals)
                and max(voiced, *arrivals) <= f)
        rows[label] = comparisons | {'phase_error_from_independent_integral_cycles': phase_errors,
                                     'cycle_wraps_from_initialization': cycles,
                                     'maximum_preface_phase_errors_to_upstream_cycles': dict(
                                         zip(('candidate_zero', 'candidate_jitter'), preface, strict=True))}
        signals[noise, start] = [pair[1] for pair in (upstream, baseline, jitter)]

    first_start, second_start = native['schedule_engine_frames']
    reservation_effect = {}
    for noise in native['noise_scales']:
        pair = zip(signals[noise, first_start], signals[noise, second_start], strict=True)
        differences = [first_difference(abs(b.astype(float) - a), native['pcm_difference_floor']) for a, b in pair]
        reservation_effect[str(noise)] = dict(
            zip(('upstream', 'candidate_zero', 'candidate_jitter'), differences, strict=True))
    return {'checks': checks | predictions, 'hypothesis_checks': predictions, 'arms': rows,
            'between_schedule_first_pcm_over_threshold': reservation_effect,
            'relative_plan_frames': expected_plan, 'voiced_window_frames': window}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    inputs = [CASE, Path(__file__).resolve()]
    runs = {}
    for name in ('upstream', 'candidate'):
        ref = study[f'{name}_reference']
        path = CASE.parent / ref['case']
        run = run_manifest(ref['run'], read_json(path)['id'], revision)
        if run[1]['status'] != 'pass':
            parser.error(f'基準実行が合格していません ({ref["run"]})')
        inputs.extend([path, run[0] / 'manifest.json', verified_path(run, 'summary.json')])
        runs[name] = run
    native_file = verified_path(runs['upstream'], 'artifacts/native-input.json')
    probe_file = verified_path(runs['upstream'], 'artifacts/upstream/probe.json')
    native, probe = map(read_json, (native_file, probe_file))
    phase_case = CASE.parent / 'glottal-cycle-jitter.json'
    original_seed = read_json(phase_case)['glottis']['params']['cycle_seed']
    upstream_source = native['source']
    if (upstream_source['drift'] != study['pitch_drift_cents'] or upstream_source['fry'] != 0
            or upstream_source['vibratoDepth'] != 0 or upstream_source['roughness'] != 0.1
            or not math.isclose(study['jitter'], 0.0021 + 0.0245 * upstream_source['roughness'], abs_tol=1e-15)
            or study['cycle_seed'] != original_seed):
        parser.error('登録したジッターまたは基準音源の条件が一致しません')
    inputs.extend([native_file, probe_file, phase_case])
    references = {}
    for noise in native['noise_scales']:
        for start in native['schedule_engine_frames']:
            label = f'frame-{start}-noise-{noise}'
            files = [verified_path(runs['upstream'], f'artifacts/upstream/{label}.{ext}') for ext in ('csv', 'f32le')]
            files.extend(verified_path(runs['candidate'], f'artifacts/{label}/{name}')
                         for name in ('input.json', 'voicing.csv', 'pcm-128.wav'))
            song = read_json(files[2])['song_voice']
            voice = song['voice']
            if (voice.get('period_jitter', 0) != 0 or voice.get('pitch_drift_cents', 0) != study['pitch_drift_cents']
                    or voice['base_pitch_hz'] != upstream_source['f0'] or song['warm_up_frames'] != start
                    or song['turbulence']['scale'] != noise):
                parser.error(f'研究版の基準が登録条件と一致しません ({label})')
            references[label] = (start, noise, *files)
            inputs.extend(files)
    inputs.extend(candidate_sources())
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_bilabial_stop.py', 'measure_fan_crossing_allocations.py', 'measure_glottal_cycle.py',
        'measure_song_schedule_drift.py', 'measure_turbulence.py', 'measure_uniform_tube.py',
        'measure_upstream_song_schedule_state.py'))
    inputs.extend(UPSTREAM / path for path in (
        'Cargo.lock', 'crates/chimera/src/engine.rs', 'crates/chimera/src/math.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/voice/human_voice.rs'))
    details = {'case_id': study['id'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'upstream_reference_run': runs['upstream'][0].name, 'candidate_reference_run': runs['candidate'][0].name}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, native, probe, references, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
