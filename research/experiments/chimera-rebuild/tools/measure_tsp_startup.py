"""TSPの発話前に出た放射を、舌先の初期座標だけを変えて照合する。"""

import argparse
import csv
import math
import os
from pathlib import Path

import numpy as np

from measure_tsp_active_duration import active_interval, compare_pcm, load, read_generated, save, windows
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-startup-resting-tip.json'


def resting_tip(pose):
    angle = -pose['jaw_cm'] / 9.84
    cx, cy = -2.5, 10.5
    dx, dy = 6.45 - cx, 7.35 - cy
    x, y = pose['tongue_body_cm']
    return [cx + dx * math.cos(angle) - dy * math.sin(angle) + 0.30 * (x - 2.9),
            cy + dx * math.sin(angle) + dy * math.cos(angle) + 0.35 * (y - 6.85)]


def measure(case, baseline, base, artifacts, execute):
    cutoff = case['pre_roll_frames']
    rate = base['sample_rate_hz']
    size, hop = base['window_frames'], base['hop_frames']
    old_run = load(baseline / 'manifest.json')
    cli = WORKSPACE / 'target/release/vocal-cli'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    if sha256(cli) != base['binaries']['candidate_sha256']:
        raise ValueError('候補のバイナリが保存済み実行と一致しません')
    old_hashes = {entry['path']: entry['sha256'] for entry in old_run['outputs']}
    rows = {}
    for record_id in case['recording_ids']:
        original = baseline / 'artifacts' / record_id
        folder = artifacts / record_id
        folder.mkdir()
        for name in ('candidate.json', 'candidate.wav', 'upstream.wav', 'candidate.retained.csv'):
            path = original / name
            if sha256(path) != old_hashes[path.relative_to(baseline).as_posix()]:
                raise ValueError(f'保存済みの成果が記録と異なります ({record_id}/{name})')
        input_case = load(original / 'candidate.json')
        pose = input_case['speech_voice']['posture']
        before = pose['tongue_tip_cm']
        pose['tongue_tip_cm'] = resting_tip(pose)
        settings = folder / 'candidate.json'
        save(settings, input_case)
        trace = folder / 'candidate.csv'
        wave = folder / 'candidate.wav'
        execute([str(cli), 'render-pcm', str(settings), str(wave), str(trace), '128'])
        upper, old = (read_generated(original / f'{name}.wav', rate) for name in ('upstream', 'candidate'))
        new = read_generated(wave, rate)
        prefix = np.loadtxt(trace, delimiter=',', skiprows=1, max_rows=cutoff, ndmin=2)
        with (original / 'candidate.retained.csv').open(newline='') as stream:
            first = next(csv.DictReader(stream))
        pre_pcm = {name: float(np.max(np.abs(samples[:cutoff])))
                   for name, samples in (('upstream', upper), ('old_candidate', old), ('new_candidate', new))}
        pre_decimated = float(np.max(np.abs(prefix[:, 2])))
        rms = {name: windows(samples, size, hop)
               for name, samples in (('upstream', upper), ('old_candidate', old), ('new_candidate', new))}
        intervals = {name: active_interval(levels, size, hop, -35) for name, levels in rms.items()}
        rows[record_id] = {'old_tip_cm': before, 'rest_tip_cm': pose['tongue_tip_cm'],
                           'pre_roll_peak_pcm': pre_pcm, 'new_pre_roll_peak_decimated': pre_decimated,
                           'old_frame_zero_decimated': float(first['decimated']),
                           'new_frame_zero_decimated': float(prefix[0, 2]),
                           'primary_intervals': intervals,
                           'pcm_old_to_upstream': compare_pcm(upper, old),
                           'pcm_new_to_upstream': compare_pcm(upper, new),
                           'checks': {'complete_prefix_and_render': prefix.shape[0] == cutoff and new.size == old.size,
                                      'baseline_pre_roll': pre_pcm['upstream'] == 0 and float(first['decimated']) != 0,
                                      'new_pre_roll_pcm': pre_pcm['new_candidate'] <= case['maximum_pre_roll_pcm_peak'],
                                      'new_pre_roll_decimated': pre_decimated <= case['maximum_pre_roll_decimated_peak']}}
        if 'sensitivity_threshold_db' in case:
            threshold = case['sensitivity_threshold_db']
            secondary = {name: active_interval(levels, size, hop, threshold) for name, levels in rms.items()}
            rows[record_id]['sensitivity_intervals'] = secondary
            if record_id in case.get('match_sensitivity_intervals', []):
                rows[record_id]['checks']['matched_sensitivity_interval'] = secondary['new_candidate'] == secondary['upstream']
            if record_id in case.get('match_sensitivity_starts', []):
                rows[record_id]['checks']['matched_sensitivity_start'] = secondary['new_candidate'][0] == secondary['upstream'][0]
        if case.get('keep_primary_intervals'):
            rows[record_id]['checks']['primary_interval_preserved'] = intervals['new_candidate'] == intervals['old_candidate']
        expected = case.get('expected_first_nonzero_frames', {}).get(record_id)
        if expected is not None:
            first_frames = {}
            for name, samples in (('upstream', upper), ('old_candidate', old), ('new_candidate', new)):
                nonzero = np.flatnonzero(samples)
                first_frames[name] = int(nonzero[0]) if nonzero.size else None
            rows[record_id]['first_nonzero_frames'] = first_frames
            rows[record_id]['checks']['first_output_at_planned_motion'] = (
                first_frames['upstream'] == first_frames['new_candidate'] == expected)
    checks = {name: all(item['checks'][name] for item in rows.values() if name in item['checks'])
              for name in dict.fromkeys(check for row in rows.values() for check in row['checks'])}
    return {'checks': checks, 'pre_roll_frames': cutoff, 'recordings': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='舌先対照のケースJSON')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('時系列は CHIMERA_RUN_STORAGE=rtl9210b で作業用ディスクに出力してください')
    case_path = args.case.resolve()
    case = load(case_path)
    baseline = WORKSPACE / 'runs' / case['baseline_run']
    base = load(baseline / 'summary.json')
    inputs = [case_path, Path(__file__).resolve(), WORKSPACE / 'tools/measure_tsp_active_duration.py',
              baseline / 'manifest.json', baseline / 'summary.json', *candidate_sources()]
    for record_id in case['recording_ids']:
        inputs.extend(baseline / 'artifacts' / record_id / name for name in
                      ('candidate.json', 'candidate.wav', 'upstream.wav', 'candidate.retained.csv'))
    return record_measurement(args.run_id, case_path, inputs,
                              {'case_id': case['id'], 'revision': case['revision'],
                               'upstream_revision': case['upstream_revision'], 'invoked_from': str(Path.cwd())},
                              lambda out, execute: measure(case, baseline, base, out, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
