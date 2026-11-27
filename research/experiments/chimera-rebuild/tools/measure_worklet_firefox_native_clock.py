"""Firefox内蔵の音声プロファイルとWorkletの記録を同じ量子で照合する。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_worklet_cross_browser as cross
import measure_worklet_release_alignment as release
import measure_worklet_realtime as realtime


CASE = release.WORKSPACE / 'cases/worklet-realtime-firefox-native-clock-96000.json'


def threads(profile):
    yield from profile.get('threads', ())
    for child in profile.get('processes', ()):
        yield from threads(child)


def thread_intervals(thread, wanted, *, processor=None):
    markers = thread['markers']
    schema = markers['schema']
    strings = thread['stringTable']
    ranges, names, starts = [], Counter(), []
    for entry in markers['data']:
        name = strings[entry[schema['name']]]
        data_index = schema['data']
        payload = (entry[data_index] or {}) if data_index < len(entry) else {}
        names[name] += 1
        if name != wanted and payload.get('name') != wanted:
            continue
        if processor is not None and payload.get('name') != processor:
            continue
        began, ended = (entry[schema[key]] for key in ('startTime', 'endTime'))
        phase = entry[schema['phase']]
        if phase == 1 and began is not None and ended is not None:
            ranges.append((began, ended))
        elif phase == 2 and began is not None:
            starts.append(began)
        elif phase == 3 and ended is not None and starts:
            ranges.append((starts.pop(), ended))
    return sorted(ranges), names


def compare_clocks(profile, report, marker):
    startup = report['startupCallbacks']
    rows = np.asarray(report['observations'], dtype=float)
    expected = len(rows) + startup
    observations, counts = [], []
    for t in threads(profile):
        intervals, names = thread_intervals(t, marker)
        if intervals or any(term in t['name'].lower() for term in ('audio', 'graph')):
            counts.append({'name': t['name'], 'count': len(intervals), 'markers': names.most_common(8)})
        if len(intervals) == expected:
            call_intervals, _ = thread_intervals(t, 'AudioWorkletNodeEngine::CallProcess')
            observations.append((intervals[startup:], call_intervals[startup:] if len(call_intervals) == expected else []))
    result = {'expected_native_markers': expected, 'native_threads': counts, 'matched_threads': len(observations)}
    if len(observations) != 1:
        return result
    blocks, author_calls = observations[0]
    v = np.asarray(blocks)
    if not (np.isfinite(v).all() and (v[:, 1] >= v[:, 0]).all() and (v[:-1, 1] <= v[1:, 0]).all()):
        result['invalid_native_intervals'] = True
        return result
    duration = v[:, 1] - v[:, 0]
    output_start = rows[:, 4] - rows[:, 1]
    voiced = (output_start >= report['startFrame']) & (output_start < report['stopFrame'])
    budget = 1000 * rows[0, 1] / report['sampleRate']
    recorded = rows[:, 2]
    long = np.flatnonzero((recorded > budget) | (duration > budget))
    native_gaps = np.diff(v[:, 0])
    date_gaps = np.diff(rows[:, 3])
    native_edges = np.flatnonzero(native_gaps >= 6)
    date_edges = np.flatnonzero(date_gaps >= 6)
    result.update({'native_all': realtime.timing_summary(duration, budget),
                   'native_voicing': realtime.timing_summary(duration[voiced], budget),
                   'date_voicing': realtime.timing_summary(recorded[voiced], budget),
                   'callback_alignment': {
                       'date_gaps_at_least_6_ms': len(date_edges),
                       'native_gaps_at_least_6_ms': len(native_edges),
                       'all_gap_positions_equal': bool(np.array_equal(date_edges, native_edges)),
                       'relative_start_maximum_error_ms': float(abs(v[:, 0] - v[0, 0] - rows[:, 3]).max()),
                       'gap_mean_absolute_error_ms': float(abs(native_gaps - date_gaps).mean()),
                       'gap_error_when_native_shifted_one_quantum_ms': [
                           float(abs(native_gaps[1:] - date_gaps[:-1]).mean()),
                           float(abs(native_gaps[:-1] - date_gaps[1:]).mean())]},
                   'date_over_but_native_within_budget': int(np.count_nonzero((recorded > budget) & (duration <= budget))),
                   'native_over_budget': int(np.count_nonzero(duration > budget)),
                   'over_budget_quanta': [
                       {'quantum': int(i), 'output_frame': int(output_start[i]), 'date_ms': recorded[i],
                        'native_ms': duration[i], 'voiced': bool(voiced[i])} for i in long]})
    if author_calls:
        calls = np.asarray(author_calls)
        if (calls[:, 0] >= v[:, 0]).all() and (calls[:, 1] <= v[:, 1]).all() and (calls[:, 1] >= calls[:, 0]).all():
            author_ms = calls[:, 1] - calls[:, 0]
            result['author_call_voicing'] = realtime.timing_summary(author_ms[voiced], budget)
            result['author_call_over_budget'] = int(np.count_nonzero(author_ms > budget))
    return result


def measure(study, original, archive, artifacts, execute, bun):
    spec = study['measurement']
    execute([*bun, 'run', 'build'], cwd=release.WEB, stdout=artifacts / 'browser-build.log')
    wasm = release.WORKSPACE / release.wasm.WASM
    wanted_hash = release.sha256(archive['artifacts/vocal_wasm.wasm'])
    expected_rate, expected_audio = wavfile.read(archive['artifacts/browser.wav'])
    expected_report = release.stored.read(archive['artifacts/browser.json'])
    checks = {'same_built_wasm': release.sha256(wasm) == wanted_hash}
    trials = []
    for index in range(1, spec['trials'] + 1):
        folder = artifacts / f'firefox-{index}'
        folder.mkdir()
        capture_case = folder / 'capture-case.json'
        configured = {**original, 'measurement': {**original['measurement'], 'browser_engine': 'firefox'}}
        capture_case.write_text(json.dumps(configured, ensure_ascii=False, indent=2) + '\n')
        profile = folder / 'firefox-profile.json'
        prefix = ['env', 'MOZ_PROFILER_STARTUP=1', 'MOZ_PROFILER_STARTUP_ENTRIES=16777216',
                  'MOZ_PROFILER_STARTUP_FEATURES=' + ','.join(spec['profiler_features']),
                  'MOZ_PROFILER_STARTUP_FILTERS=' + ','.join(spec['thread_filters']),
                  'MOZ_PROFILER_SHUTDOWN=' + str(profile)]
        detail = {'trial': folder.name}
        local = {}
        try:
            execute([*prefix, 'node', str(release.CAPTURE), str(folder), str(capture_case)],
                    stdout=folder / 'browser-command.log')
            report = release.stored.read(folder / 'browser.json')
            run = release.stored.read(folder / 'browser-run.json')
            rate, audio = wavfile.read(folder / 'browser.wav')
            local['same_wasm'] = run['servedWasmSha256'] == wanted_hash
            local['same_pcm'] = rate == expected_rate and release.wasm.compare_pcm(
                audio, expected_audio, 0)['first_bit_difference_frame'] is None
            local['same_observations'] = cross.compare_observations(report, expected_report)[
                'first_observation_bit_difference'] is None
            local['same_context_frames'] = bool(
                np.array_equal(np.diff(np.asarray(report['observations'])[:, 0]),
                               np.full(len(report['observations']) - 1, original['measurement']['expected_quantum_frames'])))
            detail.update({'version': run['version'], 'clock': report['timingClock']})
            local['profile_saved'] = profile.is_file()
            if profile.is_file():
                detail.update(compare_clocks(release.stored.read(profile), report, spec['marker']))
            local['native_intervals_aligned'] = 'native_voicing' in detail
        except (ValueError, OSError, subprocess.CalledProcessError) as error:
            detail['error'] = str(error)
            local['capture_and_comparison_completed'] = False
        for path in (profile, folder / 'browser.wav', folder / 'browser.json'):
            if path.is_file():
                release.stored.compress(path)
        checks.update({f'{folder.name}/{key}': value for key, value in local.items()})
        trials.append(detail)
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = release.stored.read(CASE)
    cross_path = release.WORKSPACE / 'cases' / study['cross_browser_case']
    registered = release.stored.read(cross_path)
    reference_path = release.WORKSPACE / 'cases' / registered['reference_case']
    original = release.stored.read(reference_path)
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (registered, original))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=release.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=release.UPSTREAM, text=True)):
        parser.error('固定上流を照合できません')
    inputs = [CASE, cross_path, reference_path, Path(__file__).resolve(), *release.web_sources(),
              *release.shared.candidate_sources(), *(Path(m.__file__) for m in (cross, release.saved, release.stored,
                release.shared, release.wasm, realtime))]
    for run_id in study['cross_browser_runs']:
        result, source_manifest = release.saved.load_saved_run(run_id, registered['id'], revision, ['summary.json'])
        inputs.extend([source_manifest, *result.values()])
        recorded, = (row['sha256'] for row in release.stored.read(source_manifest)['inputs']
                     if row['path'].endswith('/' + cross_path.name))
        if recorded != release.sha256(cross_path):
            parser.error('ブラウザ比較のケースを照合できません')
    archive, manifest = release.saved.load_saved_run(registered['chromium_run'], original['id'], revision,
        ['artifacts/browser.wav', 'artifacts/browser.json', 'artifacts/vocal_wasm.wasm'])
    inputs.extend([manifest, *archive.values()])
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return release.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda a, run: measure(study, original, archive, a, run, bun), command=None, input_root=release.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
