"""保存した出力要求で返却時刻から予定ホスト時刻までの残り時間を照合する。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import inspect_firefox_cubeb_output as firefox


song = firefox.tap.song
probe = firefox.cubeb
CASE = song.WORKSPACE / 'cases/worklet-live-song-cubeb-return-time.json'
STREAM_FILES = ('blocks.csv', 'pcm.f32le', 'state.txt')


def saved_run(run_id, case_id, revision):
    run = song.run_manifest(run_id, case_id, revision)
    if run[1]['status'] != 'pass':
        raise ValueError(f'{run_id} は保存済みの実行判定が不合格です')
    summary = song.verified_path(run, 'summary.json')
    return run, json.loads(summary.read_text()), [run[0] / 'manifest.json', summary]


def saved_files(run, folder, names):
    return [song.verified_path(run, (folder / name).relative_to(run[0]).as_posix()) for name in names]


def reference_trials(study, reference_case, base, inputs):
    cases_per_run = len(reference_case['delay_us']) * len(reference_case['round_order'])
    expected_binary = None
    for name in study['reference_runs']:
        run, evidence, files = saved_run(name, reference_case['id'], study['upstream_revision'])
        inputs.extend(files)
        binary = run[1]['probe_binary_sha256']
        expected_binary = expected_binary or binary
        if (len(evidence['conditions']) != cases_per_run or binary != expected_binary or
                run[1]['cubeb_coreaudio_revision'] != base['cubeb_coreaudio_revision'] or
                run[1]['firefox_revision'] != base['firefox_revision']):
            raise ValueError(f'{name} の既知PCM対照の入力が一致しません')
        for label, saved in evidence['conditions'].items():
            folder = run[0] / 'artifacts' / label
            stream, = folder.glob('cubeb-output-*')
            metadata, = saved_files(run, folder, ('probe.json',))
            inputs.extend([metadata, *saved_files(run, stream, STREAM_FILES)])
            yield name, label, stream, json.loads(metadata.read_text()), saved['target']


def firefox_trials(study, inputs):
    for case_id, runs in study['firefox_runs'].items():
        for name in runs:
            run, evidence, files = saved_run(name, case_id, study['upstream_revision'])
            inputs.extend(files)
            if run[1]['firefox_xul_sha256'] != study['firefox_xul_sha256']:
                raise ValueError(f'{name} の試験用Firefoxが一致しません')
            for trial in evidence['trials']:
                folder = run[0] / 'artifacts' / trial['trial']
                if trial['cubeb_capture']:
                    inputs.extend(saved_files(run, folder, ('marker.json', 'firefox-profile.json.gz')))
                    for stream in (folder / 'cubeb').glob('cubeb-output-*'):
                        inputs.extend(saved_files(run, stream, STREAM_FILES))
                yield name, folder, trial


def predict_return(slack, last_gap, first_contiguous):
    if last_gap is None or first_contiguous is None or last_gap >= first_contiguous:
        return None
    if slack <= last_gap:
        return True
    if slack >= first_contiguous:
        return False
    return None


def score(rows, key):
    counts = Counter('undetermined' if row[key] is None else 'correct' if row[key] == row['gap'] else 'incorrect'
                     for row in rows)
    return {name: counts[name] for name in ('correct', 'incorrect', 'undetermined')}


def analyze(study, references, trials, base, browser, marker, frames, engine_marker):
    checks = {}
    reference_rows = []
    for name, label, stream, metadata, target in references:
        row = probe.inspect(stream, metadata, base)
        passed = all(row['checks'].values()) and row.get('target') == target
        checks[f'{name}/{label}/identical_pcm_and_reference_target'] = passed
        if passed:
            reference_rows.append({'run': name, 'trial': label, 'target': target})
    with_gap, without_gap = [], []
    for row in reference_rows:
        target = row['target']
        slack = target['scheduled_host_minus_entry_ms'] - target['callback_ms']
        (with_gap if target['device_sample_gap_frames'] > 0 else without_gap).append(slack)
    last_gap = max(with_gap, default=None)
    first_contiguous = min(without_gap, default=None)
    budget = browser['expected_request_frames'] * 1000 / browser['sample_rate_hz']
    centers, neighbors, saved = [], [], []
    for name, folder, trial in trials:
        if not trial['cubeb_capture']:
            continue
        prior = trial['coreaudio']
        max_offset = max((row['request_offset'] for row in prior.get('split_requests', ())), default=0)
        measured = firefox.inspect(folder, trial, marker, browser, frames, engine_marker, max_offset,
                                   tick_ms=prior['host_tick_ms'])
        key = f"{name}/{trial['trial']}"
        saved.append({'run': name, 'trial': trial['trial'], 'condition': trial['condition'], 'requests': []})
        valid = (measured['valid'] and measured['matched_streams'] == prior['matched_streams'] and
                 measured['graph_marker_window'] == prior['graph_marker_window'] and
                 measured['center_graph_marker_frame'] == prior['center_graph_marker_frame'])
        if valid:
            stream_name, = measured['matched_streams']
            stream = measured['streams'][stream_name]
            original = prior['streams'][stream_name]
            intervals, old = stream['intervals'], original['intervals']
            valid = (stream['pcm'] == original['pcm'] and stream['center_marker_positions'] == original['center_marker_positions']
                     and len(intervals) == len(old) and len(stream['center_intervals']) == 1
                     and all(all(now[k] == value for k, value in then.items()) for now, then in zip(intervals, old)))
        checks[f'{key}/same_aligned_window_and_pcm'] = valid
        if not valid:
            saved[-1]['mismatch'] = measured.get('reason', 'changed_saved_alignment')
            continue
        center, = stream['center_intervals']
        for data in intervals:
            offset = data['block_index'] - center['block_index']
            row = {**data, 'relative_request': offset, 'gap': data['sample_time_gap_frames'] > 0,
                   'period_prediction': data['callback_ms'] > budget,
                   'return_prediction': predict_return(data['scheduled_host_minus_return_ms'], last_gap, first_contiguous)}
            saved[-1]['requests'].append(row)
            (neighbors if offset else centers).append(row)
    checks['all_registered_captures_replayed'] = len(centers) == study['expected_valid_firefox_captures']
    counts = {name: {key: score(rows, key) for key in ('period_prediction', 'return_prediction')}
              for name, rows in (('center', centers), ('neighbors', neighbors))}
    period, slack = (counts['center'][name] for name in ('period_prediction', 'return_prediction'))
    return {'checks': checks, 'reference_rows': reference_rows, 'trials': saved, 'comparison': counts,
            'capture_disabled': sum(not trial['cubeb_capture'] for _, _, trial in trials), 'nominal_period_ms': budget,
            'reference_return_margin_ms': {'largest_with_gap': last_gap, 'smallest_contiguous': first_contiguous,
                                           'with_gap': len(with_gap), 'contiguous': len(without_gap)},
            'supports_hypothesis': all(checks.values()) and slack['correct'] > period['correct'] and
                                   slack['incorrect'] < period['incorrect']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = json.loads(CASE.read_text())
    cases = CASE.parent
    paths = [cases / study['reference_case'], cases / study['firefox_case'], probe.CASE]
    reference, browser, base = (json.loads(path.read_text()) for path in paths)
    shared_path = cases / browser['shared_context_case']
    frame_path = cases / browser['frame_validation_case']
    shared = json.loads(shared_path.read_text())
    phase_path = cases / shared['phase_case']
    phases = json.loads(phase_path.read_text())
    frames = json.loads(frame_path.read_text())
    revision = study['upstream_revision']
    if (any(item['upstream_revision'] != revision for item in (reference, browser, base, shared, phases, frames)) or
            (base['sample_rate_hz'], base['requested_frames'], base['firefox_revision'], base['cubeb_coreaudio_revision']) !=
            (browser['sample_rate_hz'], browser['expected_request_frames'], browser['gecko_revision'], browser['cubeb_revision'])):
        parser.error('試験用Firefoxと既知PCMのケースが一致しません')
    inputs = [CASE, *paths, shared_path, phase_path, frame_path, Path(__file__).resolve(),
              *(Path(module.__file__) for module in (firefox, probe, firefox.tap, firefox.tap.callback))]
    try:
        controls = list(reference_trials(study, reference, base, inputs))
        trials = list(firefox_trials(study, inputs))
    except (OSError, ValueError, KeyError) as error:
        parser.error(f'保存済みの採取を照合できません ({error})')
    marker = shared['measurement']['marker'] | {'stereo_difference': True}
    details = {'case_id': study['id'], 'upstream_revision': revision, 'firefox_xul_sha256': study['firefox_xul_sha256'],
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: analyze(study, controls, trials, base, browser, marker, frames['measurement'],
                                           phases['measurement']['engine_marker']), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
