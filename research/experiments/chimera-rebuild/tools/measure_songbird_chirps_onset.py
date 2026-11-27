"""鳴禽の押鍵直後に現れる放射を、無励振の気道から再現する。"""

import argparse
import csv
from itertools import islice
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_syrinx import CLI, load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/songbird-chirps-onset-radiation.json'
UPDATED = ('pitch_hz', 'voices', 'drive')
RADIATION = 'radiation_derivative_cm3_s2'
ACOUSTIC = ('sac_pressure_dyn_cm2', 'left_flow_cm3_s', 'right_flow_cm3_s',
            'trachea_pressure_dyn_cm2', 'oec_pressure_dyn_cm2', 'radiation_flow_cm3_s', RADIATION)


def archive_window(path, frame, frames):
    with path.open(newline='') as stream:
        return list(islice(csv.DictReader(stream), frame - 1, frame + frames))


def first_event(values):
    changed = np.flatnonzero(values)
    return int(changed[0]) if changed.size else None


def initial_pressure(initial, updated, rate, block):
    length = math.cbrt(0.4)

    def area(controls):
        low = controls['pitch_hz'] * min(1.0, 2 ** (controls['interval_semitones'] / 12))
        purity = controls['purity']
        tuned = (0.03 / 0.35) * (5570 / low) ** 2
        return max(0.04, min(2.5, purity * tuned + (1 - purity) * controls['oec_cm3'])) / length

    start = area(initial)
    end = area(updated)
    first = start + (end - start) / block
    raw_flow = (start - first) * length * rate
    coefficient = -math.expm1(-math.tau * 60 / rate)
    injection = raw_flow * coefficient ** 2
    compliance = first * length / (1.14e-3 * 35000 ** 2)
    return {'old_area_cm2': start, 'target_area_cm2': end, 'first_area_cm2': first,
            'raw_volume_flow_cm3_s': raw_flow, 'filtered_volume_flow_cm3_s': injection,
            'first_pressure_dyn_cm2': injection / (rate * compliance)}


def measure(case, saved_controls, captures, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'creature_realtime',
             '--test', 'golden_creatures'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    rate = case['internal_sample_rate_hz']
    factor = rate // case['output_sample_rate_hz']
    block = case['control_frames'] * factor
    start = case['presilence_internal_samples']
    count = start + case['observation_internal_samples']
    source = captures['candidate'][1]
    checks = {'archived_onset_is_silent': all(
        int(rows[1]['frame']) == case['onset_frame']
        and int(rows[1]['internal_sample']) == case['onset_frame'] * factor + factor - 1
        and all(float(row['gate']) == 0 and float(row['sac_pressure_dyn_cm2']) == 0 for row in rows)
        for rows in captures.values())}
    excited = saved_controls | {field: float(source[field]) for field in UPDATED}
    pitch_only = saved_controls | {'pitch_hz': excited['pitch_hz']}
    no_tracking = saved_controls | {'purity': case['no_pitch_tracking']}
    variants = {'archived': (saved_controls, excited),
                'pitch-only': (saved_controls, pitch_only),
                'no-tracking': (no_tracking, no_tracking | {'pitch_hz': excited['pitch_hz']})}
    results, output = {}, {}
    for mode, (initial, updated) in variants.items():
        source_case = out / f'{mode}.json'
        write(source_case, {'songbird_airway': {
            'sample_rate_hz': rate, 'sample_count': count, 'control_block_samples': block,
            'controls': initial, 'breath_gate': 0.0,
            'events': [{'sample': start, 'controls': updated, 'breath_gate': 0.0}],
        }})
        paths = {side: out / f'{mode}-{side}.csv' for side in captures}
        execute([*CLI, 'render', str(source_case), str(paths['candidate'])])
        execute([str(probe), str(source_case)], cwd=UPSTREAM, stdout=paths['upstream'])
        traces = {side: load_trace(path, FIELDS, count) for side, path in paths.items()}
        predicted = initial_pressure(initial, updated, rate, block)
        onset = {side: trace[start:] for side, trace in traces.items()}
        report = {}
        for side, trace in traces.items():
            label = f'{mode}/{side}'
            row = trace[start]
            radiation = trace[RADIATION]
            flow = trace['radiation_flow_cm3_s']
            increments = np.diff(flow, prepend=0) * rate
            checks[f'{label}/pressure_and_area_prediction'] = bool(
                abs(row['oec_area_cm2'] - predicted['first_area_cm2']) < case['first_area_absolute_tolerance_cm2']
                and abs(row['oec_pressure_dyn_cm2'] - predicted['first_pressure_dyn_cm2'])
                < case['first_pressure_absolute_tolerance_dyn_cm2'])
            checks[f'{label}/radiation_is_flow_difference'] = bool(np.allclose(
                radiation, increments, rtol=1e-15, atol=1e-15))
            checks[f'{label}/silent_before_event'] = all(not np.any(trace[field][:start]) for field in ACOUSTIC)
            first_radiation = first_event(radiation[start:])
            checks[f'{label}/radiation_onset'] = first_radiation == (
                None if mode == 'no-tracking' else case['expected_first_radiation_offset'])
            if mode == 'archived':
                reference = np.array([float(frame[f'radiation_{slot}'])
                                      for frame in captures[side][1:] for slot in range(factor)])
                checks[f'{label}/matches_original_radiation'] = np.array_equal(radiation[start:], reference)
                report[side] = {'first_difference_from_archive': first_event(radiation[start:] - reference),
                                'max_difference_from_archive': float(np.max(np.abs(radiation[start:] - reference)))}
            if mode == 'no-tracking':
                checks[f'{label}/stationary_geometry_and_zero_flow'] = (
                    all(not np.any(trace[field]) for field in ACOUSTIC)
                    and bool(np.all(trace['oec_area_cm2'] == trace['oec_area_cm2'][0])))
            report.setdefault(side, {}).update(
                first_radiation=first_radiation, first_pressure=float(row['oec_pressure_dyn_cm2']),
                first_oec_area=float(row['oec_area_cm2']), first_radiation_value=(
                    None if first_radiation is None else float(radiation[start + first_radiation])))
        diff = {}
        for field in FIELDS[1:]:
            delta = onset['candidate'][field] - onset['upstream'][field]
            point = first_event(delta)
            if point is not None:
                diff[field] = {'offset': point, **{side: float(trace[field][point]) for side, trace in onset.items()}}
        results[mode] = {'independent': predicted, 'observed': report, 'first_differences': diff}
        output[mode] = onset
    thru = case['expected_first_radiation_offset'] + 1
    for side in captures:
        checks[f'pitch-only/{side}/same_first_radiation_as_archived'] = np.array_equal(
            output['archived'][side][RADIATION][:thru], output['pitch-only'][side][RADIATION][:thru])
    original = output['archived']
    flow = {side: trace['radiation_flow_cm3_s'] for side, trace in original.items()}
    increments = {side: np.diff(value, prepend=0) for side, value in flow.items()}
    candidate = original['candidate'][RADIATION]
    upstream = original['upstream'][RADIATION]
    multiplied = increments['candidate'] * rate
    first_derivative = first_event(candidate - upstream)
    first_flow = first_event(flow['candidate'] - flow['upstream'])
    first_replayed = first_event(multiplied - upstream)
    checks['candidate_derivative_from_division'] = np.array_equal(increments['candidate'] / (1 / rate), candidate)
    checks['upstream_derivative_from_reciprocal'] = np.array_equal(increments['upstream'] * rate, upstream)
    checks['first_rounding_difference_removed_by_replay'] = (
        first_derivative == thru - 1
        and first_replayed == first_flow == case['derivative_replay']['expected_first_flow_delta'])
    rounding = [] if first_derivative is None else [
        {'series': label, 'value': float(values[first_derivative]), 'f64_hex': float(values[first_derivative]).hex()}
        for label, values in (('candidate_derivative', candidate), ('upstream_derivative', upstream),
                              ('reciprocal_replay', multiplied), ('candidate_flow', flow['candidate']),
                              ('upstream_flow', flow['upstream']))]
    return {'checks': checks, 'observation_start': start, 'archived_internal_start': case['onset_frame'] * factor,
            'variants': results, 'derivative_replay': {
                'first_rounding_difference': first_derivative, 'first_flow_difference': first_flow,
                'first_replayed_difference': first_replayed, 'first_original_difference_values': rounding}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs' / case['baseline_run']
    manifest = read(baseline / 'manifest.json')
    if manifest['upstream_revision'] != revision or manifest['status'] != 'pass':
        parser.error('固定上流に照合済みのMIDI実行が必要です')
    source = verified_file(baseline, manifest, 'artifacts/midi-songbird-case.json')
    voice = read(source)['songbird_voice']
    if voice['sample_rate_hz'] != case['output_sample_rate_hz'] or voice['events'][0] != {
        'frame': case['onset_frame'], 'midi_call': {'id': 'chirps', 'note': 60, 'pressed': True},
    }:
        parser.error('保存された最初の押鍵と登録条件が一致しません')
    paths = {side: verified_file(baseline, manifest, f'artifacts/{stem}.retained.csv')
             for side, stem in (('candidate', 'cli'), ('upstream', 'upstream'))}
    archive_frames = case['observation_internal_samples'] // (case['internal_sample_rate_hz']
                                                            // case['output_sample_rate_hz'])
    windows = {side: archive_window(path, case['onset_frame'], archive_frames) for side, path in paths.items()}
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    inputs = [CASE, PROBE, Path(__file__), source, baseline / 'manifest.json', *paths.values(),
              WORKSPACE / 'tools/measure_songbird_airway.py', WORKSPACE / 'tools/measure_songbird_syrinx.py',
              *candidate_sources(), UPSTREAM / 'crates/chimera/src/creatures/songbird.rs',
              UPSTREAM / 'crates/chimera/src/airway/network.rs']
    baseline_replay = WORKSPACE / 'runs' / case['derivative_replay']['baseline_run']
    replay_manifest = read(baseline_replay / 'manifest.json')
    if (replay_manifest['status'], replay_manifest['case_revision'], replay_manifest['upstream_revision']) != (
        'pass', 1, revision
    ):
        parser.error('第1版の放射比較が必要です')
    inputs.extend((baseline_replay / 'manifest.json', verified_file(baseline_replay, replay_manifest, 'summary.json')))
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, voice['controls'], windows, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
