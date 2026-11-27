"""停止中のWorklet作成時刻と再開後のフレーム番号をSafariで比較する。"""

import argparse
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

from measure_worklet_fixed import ROOT, WEB, UPSTREAM, WORKSPACE
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement


CASE = WORKSPACE / 'cases/worklet-safari-clock-at-creation.json'
TOOLS = WEB / 'tools'
CAPTURE = TOOLS / 'capture-safari-worklet-creation-clock.mjs'


def read_json(path):
    return json.loads(path.read_text())


def compare(trial, mode, spec):
    driver = trial['capabilities']
    quantum, count = spec['quantum_frames'], spec['captured_blocks']
    rate = spec['sample_rate_hz']
    rows = trial['blocks']
    marks = {mark['phase']: mark for mark in trial['events']}
    stopped = ['suspended', 'registration_requested', 'registered', 'constructor_received',
               'index_signal_scheduled', 'resume_requested']
    position = marks['suspended']['frame']
    ordered = list(marks)
    index = [ordered.index(phase) for phase in (*stopped, 'resumed', 'blocks_received', 'closed')]
    evaluation, constructor = (trial['creation'][phase] for phase in ('evaluation', 'constructor'))
    clock_frames = [row['frame'] for row in rows]
    clocks = [evaluation, constructor, *rows]
    samples = [value for row in rows for value in row['samples']]
    expected = range(1, quantum * count + 1)
    measured = struct.pack(f'<{len(samples)}f', *samples)
    ramp = struct.pack(f'<{len(expected)}f', *(i / spec['ramp_denominator'] for i in expected))
    checks = {
        'safari_on_macos': driver['browserName'] == 'Safari' and driver['platformName'] == 'macOS',
        'one_click_per_stage': trial['prepareTrusted'] is True and trial['resumeTrusted'] is True,
        'planned_starting_position': position % quantum == 0 and (
            position == 0 if mode == 'fresh' else position >= spec['advanced_minimum_frames']),
        'stopped_through_creation': all(marks[phase]['state'] == 'suspended' and marks[phase]['frame'] == position
                                        for phase in stopped),
        'resumed_after_creation_then_closed': (index == sorted(index) and marks['resumed']['state'] == 'running'
                                               and marks['closed']['state'] == 'closed'),
        'recorded_all_callbacks': len(rows) == count and all(row['quantum'] == quantum
            and ((row['channels'] == 0 and not row['samples'])
                 or (row['channels'] == 1 and len(row['samples']) == quantum)) for row in rows),
        'clock_time_and_rate': (evaluation['rate'] == constructor['rate'] == rate and all(
            clock['frame'] >= 0 and clock['frame'] % quantum == 0
            and math.isclose(clock['time'], clock['frame'] / rate, rel_tol=0, abs_tol=1e-9) for clock in clocks)),
        'finite_pcm': all(math.isfinite(value) for value in samples),
    }
    expected_frames = [position + i * quantum for i in range(count)]
    predicted_frames = [0, *expected_frames[1:]]
    result = {'stopped_frame': position, 'evaluation_frame': evaluation['frame'],
              'constructor_frame': constructor['frame'], 'processing_frames': clock_frames,
              'expected_contiguous_frames': expected_frames, 'predicted_safari_frames': predicted_frames,
              'input_block_lengths': [len(row['samples']) for row in rows], 'input_samples': len(samples),
              'pcm_matches_ramp': measured == ramp, 'processing_matches_prediction': clock_frames == predicted_frames,
              'constructor_matches_context': constructor['frame'] == position,
              'evaluation_matches_context': evaluation['frame'] == position}
    return checks, result


def measure(case_path, study, artifacts, execute):
    execute(['node', str(CAPTURE), str(case_path), str(artifacts)], stdout=artifacts / 'safari.log')
    checks, trials = {}, []
    for index, pair in enumerate(study['condition_order'], 1):
        for mode in pair:
            label = f'{index}-{mode}'
            row = {'trial': label, 'mode': mode, 'pair': index}
            try:
                observation = read_json(artifacts / f'{label}.json')
                if observation.get('error') or observation.get('stage') != 'complete':
                    raise ValueError(observation.get('error', 'Safariで4量子の取得まで完了しませんでした'))
                local, result = compare(observation, mode, study['measurement'])
                row.update(result)
            except (OSError, ValueError, KeyError, TypeError, struct.error) as error:
                local = {'capture_completed': False}
                row['error'] = str(error)
            checks.update({f'{label}/{key}': passed for key, passed in local.items()})
            trials.append(row)
    predictions = {}
    for mode in ('fresh', 'advanced'):
        rows = [row for row in trials if row['mode'] == mode and 'error' not in row]
        complete = len(rows) == len(study['condition_order'])
        predictions[f'{mode}/evaluation_and_constructor_read_zero'] = complete and all(
            row['evaluation_frame'] == row['constructor_frame'] == 0 for row in rows)
        for key in ('constructor_matches_context', 'processing_matches_prediction', 'pcm_matches_ramp'):
            predictions[f'{mode}/{key}'] = complete and all(row[key] for row in rows)
    return {'checks': checks, 'predictions': predictions, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = read_json(case_path)
    spec = study['measurement']
    revision = study['upstream_revision']
    if (not study['condition_order'] or any(sorted(pair) != ['advanced', 'fresh'] for pair in study['condition_order'])
            or spec['advanced_minimum_frames'] <= 0 or spec['advanced_minimum_frames'] % spec['quantum_frames']
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流またはSafariの比較条件が一致しません')
    previous = study['song_reference']
    previous_case_path = CASE.parent / previous['case']
    previous_case = read_json(previous_case_path)
    run = run_manifest(previous['run'], previous_case['id'], revision)
    summary = verified_path(run, 'summary.json')
    if (run[1]['status'] != 'pass' or not any(row['mode'] == 'immediate' and row['node_after_registration']['first_frame_step']
                                           > spec['quantum_frames'] for row in read_json(summary)['trials'])):
        parser.error('Workletの番号が飛んだ保存済み歌唱を確認できません')
    details = {'case_id': study['id'], 'upstream_revision': revision, 'webkit_reference': study['webkit_reference'],
               'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    inputs = [case_path, previous_case_path, run[0] / 'manifest.json', summary, Path(__file__).resolve(), CAPTURE,
              TOOLS / 'safari-webdriver.mjs', TOOLS / 'worklet-creation-clock-processor.js']
    return record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case_path, study, artifacts, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
