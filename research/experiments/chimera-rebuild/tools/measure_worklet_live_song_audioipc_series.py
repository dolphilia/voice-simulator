"""保存した4組のAudioIPC採取を、登録したソケット時刻の条件で検証する。"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

import filter_worklet_audioipc_syscalls as syscalls
import measure_worklet_live_song_audioipc as timing


callback = timing.callback
song = callback.song
CASE = callback.shared.AUDIOIPC_SERIES_CASE
XCTRACE = ('/usr/bin/xcrun', 'xctrace')


def add_frame_checks(result, profile, marker, trial, spec, outer_marker, limits):
    prior = trial.get('timing')
    if not prior:
        start, end = result['constructor_ms']
        prior = {'thread': result['graph_thread'], 'preparation': {'constructor_ms': end - start}}
    frames, data = callback.reconcile(profile, prior, marker['frames'], spec, outer_marker)
    radius = limits['window_radius_requests']
    expected = limits['expected_frames']
    frame_checks = {
        **{key: bool(value) for key, value in frames.items()},
        'registered_sample_rate': marker['sampleRate'] == limits['sample_rate_hz'],
        'registered_window_and_request_length': len(data['rows']) == 2 * radius + 1
        and all(row['requested_frames'] == row['graph_advance_frames'] == expected
                and len(row['reference_frame_starts']) == expected // spec['worklet_quantum_frames']
                for row in data['rows']),
    }
    result['frame_checks'] = frame_checks
    result['frame_alignment_passed'] = all(frame_checks.values())
    result['frame_alignment'] = data


def rationale(result, limits):
    if not result['capture_checks_passed']:
        return 'capture_checks'
    if not result.get('frame_alignment_passed'):
        return 'frame_alignment'
    if not result['timing_comparable']:
        return 'instrumentation_increase'
    if not result.get('full_window') or len(result.get('matched', ())) != 2 * limits['window_radius_requests'] + 1:
        return 'socket_alignment'
    return None


def add_prediction(result, limits):
    reason = rationale(result, limits)
    result['excluded_reason'] = reason
    result['eligible'] = reason is None
    result['meets_socket_prediction'] = False
    if 'next_interval_ms' not in result:
        return
    requests = {row['offset']: row for row in result['matched']}
    central, following = requests[0], requests[1]
    a = central['server_send']['start_ns']
    b = central['server_receive']['end_ns']
    c = following['server_send']['start_ns']
    budget_ms = 1000 * limits['expected_frames'] / limits['sample_rate_hz']
    excess_ms = (c - a) / 1e6 - budget_ms
    interval_gap = result['next_interval_ms']['server_minus_client']
    result['prediction_values_ms'] = {
        'budget': budget_ms, 'excess': excess_ms, 'absolute_interval_gap': abs(interval_gap),
        'central_rpc_roundtrip': (b - a) / 1e6, 'reply_until_next_send': (c - b) / 1e6,
    }
    result['meets_socket_prediction'] = (
        reason is None and excess_ms >= limits['minimum_delayed_interval_excess_ms']
        and abs(interval_gap) <= limits['maximum_server_client_interval_difference_ms'])


def compare_pairs(results):
    pairs = {}
    for result in results:
        number, _, condition = result['trial'].partition('-')
        pairs.setdefault(number, {})[condition] = result
    differences = {}
    for number, pair in pairs.items():
        control, drawn = (pair[name] for name in ('control', 'draw192'))
        if control['eligible'] and drawn['eligible']:
            a, b = (row['prediction_values_ms'] for row in (control, drawn))
            differences[number] = {key: b[key] - a[key] for key in ('excess', 'central_rpc_roundtrip', 'reply_until_next_send')}
    return differences


def evaluate(source, capture_summary, traces, baseline, limits, spec, outer_marker, artifacts, execute):
    def one(trial):
        label, condition = trial['trial'], trial['condition']
        target = artifacts / label
        target.mkdir()
        result = {'trial': label, 'condition': condition, 'eligible': False, 'meets_socket_prediction': False}
        flags = {name.removeprefix(f'{label}/'): status for name, status in capture_summary['checks'].items()
                 if name.startswith(f'{label}/')}
        try:
            trace = traces[label]
            toc = target / 'toc.xml'
            execute([*XCTRACE, 'export', '--input', str(trace), '--toc', '--output', str(toc)])
            # XMLは生トレースから再生成できるため、抽出後に一時領域を解放する。
            with TemporaryDirectory(prefix=f'{label}-', dir=artifacts) as tmp:
                exports = Path(tmp)
                work = exports / label
                work.mkdir()
                (work / 'toc.xml').symlink_to(toc)
                execute([*XCTRACE, 'export', '--input', str(trace), '--xpath',
                         '/trace-toc/run/data/table[@schema="syscall"]', '--output', str(work / 'syscall.xml')])
                result.update(timing.analyze_trial(source[0], exports, trial, baseline[condition], limits,
                                                   bool(flags) and all(flags.values())))
            files = source[0] / 'artifacts' / label
            if (files / 'marker.json').is_file():
                add_frame_checks(result, callback.read_json(files / 'firefox-profile.json.gz'),
                                 callback.read_json(files / 'marker.json'), trial, spec, outer_marker, limits)
            add_prediction(result, limits)
        except (OSError, EOFError, KeyError, TypeError, ValueError, ElementTree.ParseError,
                subprocess.CalledProcessError) as error:
            result.update(eligible=False, meets_socket_prediction=False, excluded_reason='missing_or_unreadable_input',
                          error=str(error))
        result['capture_checks'] = flags
        (target / 'comparison.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
        fields = ('trial', 'condition', 'eligible', 'excluded_reason', 'meets_socket_prediction',
                  'next_interval_ms', 'prediction_values_ms', 'instrumentation_increase_ms', 'clock_residual_ms')
        return ({key: result[key] for key in fields if key in result} | {
            'matched_requests': len(result.get('matched', ())), 'artifact': f'artifacts/{label}/comparison.json'})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(one, capture_summary['trials']))
    drawn = [row for row in results if row['condition'] == 'draw192']
    accepted = sum(row['meets_socket_prediction'] for row in drawn)
    return {'checks': {'minimum_draw_trials_meeting_socket_prediction': accepted >= limits['minimum_trials_meeting_prediction']},
            'draw_trials': len(drawn), 'draw_trials_meeting_prediction': accepted, 'trials': results,
            'eligible_pair_differences_ms': compare_pairs(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture_run')
    args = parser.parse_args()
    study = callback.read_json(CASE)
    rev = study['upstream_revision']
    case_folder = CASE.parent
    cases = [case_folder / study[key] for key in ('audioipc_case', 'correlation_case', 'frame_validation_case')]
    ipc, correlation, frames = map(callback.read_json, cases)
    limits = ipc['analysis'] | correlation['correlation']
    frame_spec = frames['measurement']
    phase = callback.read_json(callback.phases.CASE)['measurement']
    if (any(case['upstream_revision'] != rev for case in (ipc, correlation, frames))
            or frame_spec['window_radius_callbacks'] != limits['window_radius_requests']
            or frame_spec['output_rate_hz'] != limits['sample_rate_hz']):
        parser.error('時刻照合ケースとフレーム検証ケースの条件が一致しません')
    source = song.run_manifest(args.capture_run, study['id'], rev)
    summary_path = song.verified_path(source, 'summary.json')
    capture_summary = callback.read_json(summary_path)
    expected = [(f'{n}-{condition}', condition) for n, pair in enumerate(study['condition_order'], 1) for condition in pair]
    if [(row['trial'], row['condition']) for row in capture_summary['trials']] != expected:
        parser.error('採取した試行順が登録ケースと一致しません')
    stored_case = source[0] / 'artifacts/source' / CASE.relative_to(song.ROOT)
    if not stored_case.is_file() or stored_case.read_bytes() != CASE.read_bytes():
        parser.error('採取時のケースが現在の登録ケースと一致しません')

    reference = song.run_manifest(study['perturbation_reference_run'], ipc['id'], rev)
    reference_summary = song.verified_path(reference, 'summary.json')
    baseline = {}
    inputs = [CASE, *cases, callback.phases.CASE, Path(__file__).resolve(),
              *(Path(module.__file__).resolve() for module in (timing, callback, syscalls, callback.shared, callback.native,
                                                              callback.phases, song.shared)),
              source[0] / 'manifest.json', summary_path, reference[0] / 'manifest.json', reference_summary]
    helper = callback.shared.SYSTEM_PAIR_CAPTURE
    inputs.extend([helper, source[0] / 'artifacts/source' / helper.relative_to(song.ROOT)])
    for trial in callback.read_json(reference_summary)['trials']:
        profile = song.verified_path(reference, f"artifacts/{trial['trial']}/firefox-profile.json.gz")
        ctor, _, _, calls, i = callback.locate_callbacks(callback.read_json(profile), trial['timing'])
        baseline[trial['condition']] = {'constructor': ctor[1] - ctor[0], 'next_interval': calls[i + 1][0] - calls[i][0]}
        inputs.append(profile)

    traces = {}
    for label, _ in expected:
        prefix = f'artifacts/{label}/'
        paths = [entry['path'] for entry in source[1]['outputs'] if entry['path'].startswith(prefix)
                 and (entry['path'][len(prefix):].startswith('audio-system.trace/')
                      or entry['path'][len(prefix):] in ('firefox-profile.json.gz', 'marker.json', 'trace-release.json'))]
        for path in paths:
            file = song.verified_path(source, path)
            if path.endswith('/audio-system.trace/form.template'):
                traces[label] = file.resolve().parent
            inputs.append(file)

    metadata = {'case_id': study['id'], 'upstream_revision': rev, 'capture_run': args.capture_run,
                'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
                'xctrace': subprocess.check_output([*XCTRACE, 'version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: evaluate(source, capture_summary, traces, baseline, limits, frame_spec,
                                            phase['engine_marker'], artifacts, execute),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
