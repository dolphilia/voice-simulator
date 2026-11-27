"""通常の歌唱CLIと固定上流で、予約前からのピッチドリフトだけを比較する。"""

import argparse
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_bilabial_stop import capture_candidate, load_trace
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_glottal_cycle import cycle_factors
from measure_glottal_pitch import independent_pitch
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_upstream_song_schedule_state import DICTIONARY, PROBE, first_difference, relative_segments
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/song-voice-schedule-drift.json'
COLUMNS = {
    'gate': 'gate',
    'lip_opening_cm': 'lip_aperture_cm',
    'lip_area_cm2': 'lip_area_cm2',
    'lung_pressure_dyn_cm2': 'lung_boundary_dyn_cm2',
    'glottal_phase_cycles': 'glottal_phase',
    'glottal_f0_hz': 'glottal_f0_hz',
    'glottal_voicing': 'glottal_voicing',
    'glottal_area_cm2': 'glottal_area_cm2',
    'glottal_flow_cm3_s': 'glottal_flow_cm3_s',
    'subglottal_pressure_dyn_cm2': 'pressure_sub_dyn_cm2',
    'supraglottal_pressure_dyn_cm2': 'pressure_supra_dyn_cm2',
    'lip_radiation_cm3_s': 'lip_flow_cm3_s',
    'nose_radiation_cm3_s': 'nose_flow_cm3_s',
    'radiation_derivative_cm3_s2': 'radiation_derivative_cm3_s2',
}


def read_json(path):
    return json.loads(path.read_text())


def phase_delta(right, left):
    return (right - left + 0.5) % 1.0 - 0.5


def predict_steady_phase(f0, rate, count, jitter, shimmer, cycle_seed):
    """初期F0が一定の区間を、独立に求めた周期倍率で積分する。"""
    wraps = math.ceil(count * f0 / (rate * 0.55))
    period, _ = cycle_factors({'cycle_seed': cycle_seed, 'jitter': jitter, 'shimmer': shimmer}, wraps)
    phase, cycle = 0.0, 0
    result = np.empty(count)
    for i in range(count):
        phase += f0 / (rate * period[cycle])
        if phase >= 1:
            phase -= 1
            cycle += 1
        result[i] = phase
    return result


def compare_pair(zero, five, at, native, voiced_window):
    before, pcm_before = zero
    after, pcm_after = five
    stages = {}
    for key in COLUMNS:
        lhs, rhs = before[key], after[key]
        delta = phase_delta(rhs, lhs) if key == 'glottal_phase_cycles' else rhs - lhs
        first = first_difference(abs(delta), native['thresholds'][key], at)
        i = None if first is None else int(np.searchsorted(at, first))
        stages[key] = {'first_frame': first, 'maximum_absolute_difference': float(abs(delta).max()),
                       'first_values': None if i is None else [float(lhs[i]), float(rhs[i])]}
    lo, hi = voiced_window
    pcm = pcm_after.astype(float) - pcm_before
    first_pcm = first_difference(abs(pcm), native['pcm_difference_floor'])
    return {
        'stages': stages,
        'first_pcm_bit_difference': first_difference(pcm_before.view('<u4') != pcm_after.view('<u4'), 0),
        'first_pcm_over_threshold': first_pcm,
        'pcm_maximum_absolute_difference': float(abs(pcm).max()),
        'pcm_voiced_window_rms_difference': float(np.sqrt(np.mean(pcm[lo:hi] ** 2))),
        'initial_phase_cycles': [float(t['glottal_phase_cycles'][0]) for t in (before, after)],
        'initial_f0_hz': [float(t['glottal_f0_hz'][0]) for t in (before, after)],
    }


def load_upstream(csv, raw, at, start, lead):
    trace = np.genfromtxt(csv, names=True, delimiter=',', dtype=np.float64)
    pcm = np.fromfile(raw, dtype='<f4')
    frames = np.r_[-lead - 1, at]
    if (not np.array_equal(trace['relative_frame'], frames)
            or not np.array_equal(trace['absolute_frame'], frames + start + lead)
            or len(pcm) != len(at) - lead or not np.isfinite(pcm).all()
            or not all(np.isfinite(trace[column]).all() for column in trace.dtype.names)):
        raise ValueError(f'上流のサンプル位置、長さまたは値が不正です ({csv.name})')
    return {key: trace[key][1:] for key in COLUMNS}, pcm


def load_candidate(csv, wave, rate, at, lead, *, columns=COLUMNS):
    trace = load_trace(csv, len(at))
    wav_rate, pcm = wavfile.read(wave)
    if (wav_rate != rate or pcm.dtype != np.float32 or pcm.shape != at.shape
            or not np.isfinite(pcm).all()):
        raise ValueError(f'研究版のPCMの形式またはサンプル範囲が不正です ({wave.name})')
    return {key: trace[column] for key, column in columns.items()}, pcm[lead:]


def measure(study, native, previous_probe, references, phase_case, pitch_case, artifacts, execute):
    rate, fs = native['output_rate_hz'], native['internal_rate_hz']
    lead = round(native['lead_seconds'] * rate)
    at = np.arange(-lead, native['comparison_samples'])
    low, high = study['drift_cents']
    modified = native | {'source': native['source'] | {'drift': low}}
    native_file = artifacts / 'native-input.json'
    native_file.write_text(json.dumps(modified, ensure_ascii=False, indent=2) + '\n')
    dictionary = artifacts / 'cmudict.txt'
    dictionary.write_bytes(gzip.decompress(DICTIONARY.read_bytes()))
    probe = build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    upstream_dir = artifacts / 'upstream'
    upstream_dir.mkdir()
    execute([str(probe), str(native_file), str(dictionary), str(upstream_dir)], cwd=UPSTREAM)
    output_probe = read_json(upstream_dir / 'probe.json')
    expected_plan = relative_segments(previous_probe['segments'], 0, rate)
    probe_arms = {arm['label']: arm for arm in output_probe['arms']}
    checks = {'fixed_upstream_plan': (
        relative_segments(output_probe['segments'], 0, rate) == expected_plan
        and output_probe['end_seconds'] == previous_probe['end_seconds'])}
    start_last = max(native['schedule_engine_frames']) + lead
    factor = fs // rate
    pitch = native['source']['f0']
    model_params = {'f0_hz': pitch, 'drift_cents': high - low,
                    'vibrato_depth_cents': 0.0, 'vibrato_rate_hz': native['source']['vibratoRate']}
    count = start_last * factor
    model_pitch = independent_pitch(pitch_case['measurement'] | {'sample_count': count}, model_params, fs)
    roughness = native['source']['roughness']
    phase_seed = phase_case['glottis']['params']['cycle_seed']
    phases_at_zero = {
        'upstream': predict_steady_phase(pitch, fs, count,
                                         0.0021 + 0.0245 * roughness, 0.02 + 0.22 * roughness, phase_seed),
        'candidate': predict_steady_phase(pitch, fs, count, 0, 0, phase_seed),
    }
    results = {}
    voiced_window = lo, hi = study['voiced_window_frames']
    for label, (start, noise, native_csv, native_pcm, case_file, candidate_csv, candidate_wave) in references.items():
        case = read_json(case_file)
        case['song_voice']['voice']['pitch_drift_cents'] = high
        candidate_dir = artifacts / label
        candidate_dir.mkdir()
        case_file = candidate_dir / 'input.json'
        case_file.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        report, trace_path, pcm_paths = capture_candidate(case_file, study['host_block_frames'], candidate_dir, execute)
        wave, pcm_trace = pcm_paths[0]
        checks[f'{label}/candidate_block_invariance'] = all(
            sha256(p) == sha256(wave) and sha256(c) == sha256(pcm_trace) for p, c in pcm_paths[1:])
        segments = [s for phrase in report['song']['plan']['phrases'] for s in phrase['timing']['segments']]
        checks[f'{label}/candidate_plan'] = (
            [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead, round(s['end_seconds'] * rate) - lead)
             for s in segments] == [(ipa, t0, t1) for _, ipa, _, t0, t1 in expected_plan]
            and report['output_frames'] == len(at) and report['decimation_factor'] == factor)
        arm = probe_arms[label]
        checks[f'{label}/upstream_schedule_and_rate'] = (
            arm['schedule_frame'] == start and arm['noise_scale'] == noise
            and round(arm['clock_at_schedule_seconds'] * rate) == start
            and round(arm['origin_seconds'] * rate) == start + lead
            and arm['internal_sample_rate_hz'] == fs)
        pairs = {
            'upstream': (load_upstream(upstream_dir / f'{label}.csv', upstream_dir / f'{label}.f32le', at, start, lead),
                         load_upstream(native_csv, native_pcm, at, start, lead)),
            'candidate': (load_candidate(candidate_csv, candidate_wave, rate, at, lead),
                          load_candidate(trace_path, wave, rate, at, lead)),
        }
        positions = (start + np.arange(lead) + 1) * factor - 1
        expected_cents = 1200 * np.log2(model_pitch[positions] / pitch)
        result = {}
        for engine, (zero, five) in pairs.items():
            before, _ = zero
            after, _ = five
            f0_before = before['glottal_f0_hz'][:lead]
            cents = 1200 * np.log2(after['glottal_f0_hz'][:lead] / f0_before)
            pitch_error = float(abs(cents - expected_cents).max())
            phase_error = float(abs(phase_delta(before['glottal_phase_cycles'][:lead],
                                                phases_at_zero[engine][positions])).max())
            compare = compare_pair(zero, five, at, native, voiced_window)
            stage = {key: row['first_frame'] for key, row in compare['stages'].items()}
            tag = f'{label}/{engine}'
            checks[f'{tag}/controls_and_voiced_window'] = (
                stage['gate'] is None and stage['lip_opening_cm'] is None
                and all(t['glottal_voicing'][lo + lead:hi + lead].min() >= study['active_voicing_floor']
                        for t in (before, after)))
            checks[f'{tag}/pitch_model'] = (
                pitch_error <= study['pitch_model_tolerance_cents']
                and float(abs(f0_before - pitch).max()) <= native['thresholds']['glottal_f0_hz'])
            checks[f'{tag}/phase_model_without_drift'] = phase_error <= study['phase_tolerance_cycles']
            checks[f'{tag}/drift_propagates_to_pcm'] = (
                stage['glottal_phase_cycles'] == int(at[0])
                and all(stage[key] is not None for key in (
                    'glottal_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2'))
                and compare['first_pcm_over_threshold'] is not None
                and stage['radiation_derivative_cm3_s2'] <= compare['first_pcm_over_threshold'])
            if noise == 0:
                active = first_difference(before['glottal_voicing'], native['thresholds']['glottal_voicing'], at)
                checks[f'{tag}/pcm_difference_follows_voicing'] = (
                    active is not None and compare['first_pcm_over_threshold'] is not None
                    and stage['glottal_area_cm2'] is not None
                    and max(active, stage['glottal_area_cm2']) <= compare['first_pcm_over_threshold'])
            result[engine] = compare | {'max_preface_phase_error_cycles_at_zero_drift': phase_error,
                                        'max_preface_pitch_error_cents': pitch_error,
                                        'predicted_first_pitch_change_cents': float(expected_cents[0])}
        upstream, candidate = pairs['upstream'], pairs['candidate']
        for title, left, right in (('matched_zero', upstream[0], candidate[0]),
                                   ('matched_five', upstream[1], candidate[1]),
                                   ('prior_unmatched', upstream[1], candidate[0])):
            result[title] = compare_pair(left, right, at, native, voiced_window)
        matched = result['matched_zero']
        checks[f'{label}/cross_engine_residual_at_zero'] = (
            matched['stages']['glottal_phase_cycles']['first_frame'] == int(at[0])
            and matched['first_pcm_over_threshold'] is not None)
        results[label] = result
    return {'checks': checks, 'arms': results, 'voiced_window_frames': voiced_window,
            'relative_plan_frames': expected_plan, 'first_observation_frame': int(at[0])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    inputs = [CASE, Path(__file__).resolve(), PROBE, DICTIONARY]
    runs = {}
    for engine in ('upstream', 'candidate'):
        ref = study[f'{engine}_reference']
        case = CASE.parent / ref['case']
        run = run_manifest(ref['run'], read_json(case)['id'], revision)
        if run[1]['status'] != 'pass':
            parser.error(f'基準実行が合格していません ({ref["run"]})')
        inputs.extend([case, run[0] / 'manifest.json', verified_path(run, 'summary.json')])
        runs[engine] = run
    native_file, probe_file = (verified_path(runs['upstream'], f'artifacts/{name}')
                               for name in ('native-input.json', 'probe.json'))
    native, previous_probe = map(read_json, (native_file, probe_file))
    low, high = study['drift_cents']
    if low != 0 or native['source']['drift'] != high:
        parser.error('登録したドリフトと固定上流の基準が一致しません')
    inputs.extend([native_file, probe_file])
    references = {}
    for noise in native['noise_scales']:
        for start in native['schedule_engine_frames']:
            label = f'frame-{start}-noise-{noise}'
            files = [verified_path(runs['upstream'], f'artifacts/{label}.{ext}') for ext in ('csv', 'f32le')]
            files.extend(verified_path(runs['candidate'], f'artifacts/{label}/{name}')
                         for name in ('input.json', 'voicing.csv', 'pcm-128.wav'))
            song = read_json(files[2])['song_voice']
            if (song['voice'].get('pitch_drift_cents', 0) != low or song['warm_up_frames'] != start
                    or song['turbulence']['scale'] != noise or song['voice']['base_pitch_hz'] != native['source']['f0']):
                parser.error(f'研究版の基準が登録条件と一致しません ({label})')
            references[label] = (start, noise, *files)
            inputs.extend(files)
    phase_case, pitch_case = (CASE.parent / f'glottal-{name}.json' for name in ('cycle-jitter', 'pitch-drift'))
    inputs.extend([phase_case, pitch_case, *candidate_sources()])
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_bilabial_stop.py', 'measure_fan_crossing_allocations.py', 'measure_glottal_cycle.py',
        'measure_glottal_pitch.py', 'measure_turbulence.py', 'measure_uniform_tube.py',
        'measure_upstream_song_schedule_state.py'))
    inputs.extend(UPSTREAM / name for name in (
        'Cargo.lock', 'crates/chimera/src/engine.rs', 'crates/chimera/src/math.rs',
        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/sources/glottis.rs',
        'crates/chimera/src/phonetics/sing.rs'))
    details = {'case_id': study['id'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'upstream_reference_run': runs['upstream'][0].name, 'candidate_reference_run': runs['candidate'][0].name}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, native, previous_probe, references, read_json(phase_case),
                                           read_json(pitch_case), artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
