"""短音を無音のContextと先行信号が鳴るContextで比較する。"""

import argparse
import gzip
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

import measure_worklet_live_song_teeth_lowpass_floor as realtime
from upstream_baseline import sha256


song = realtime.song
READ = realtime.READ
CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-context-lead.json'


def marker_observations(folder, marker, window, clock, spec):
    metadata = READ(folder / 'marker.json')
    frames = np.asarray(metadata['frames'], dtype=np.int64)
    observed = np.fromfile(folder / 'marker.f32le', dtype='<f4')
    quantum, count = marker['quantum'], marker['capture_quanta']
    if frames.shape != (count,) or observed.shape != (count * quantum,) or not np.isfinite(observed).all():
        raise ValueError('先行信号のフレーム数またはPCMの形式が一致しません')
    phase = (frames[:, None] + np.arange(quantum) - metadata['startFrame']) % (count * quantum)
    encoded = (phase * marker['multiplier'] + marker['offset']) % marker['modulus']
    expected = ((encoded - marker['center']) / marker['scale']).astype('<f4').ravel()
    match = song.wasm.compare_pcm(observed, expected, 0)
    start = clock['startup_frame'] - window['before_first_voice_callback'] * quantum
    stop = clock['last_quantum_frame'] + (1 + window['after_final_voice_quantum']) * quantum
    expected_frames = np.arange(start, stop, quantum)
    actual_frames = frames[(frames >= start) & (frames < stop)]
    before = frames[frames < clock['startup_frame']]
    checks = {'marker_pcm_at_context_frames': match['first_bit_difference_frame'] is None,
              'marker_clock_spans_voice': (metadata['sampleRate'] == spec['sample_rate_hz']
                                           and frames[0] >= metadata['startFrame']
                                           and np.all(np.diff(frames) > 0).item()
                                           and np.array_equal(actual_frames, expected_frames)
                                           and len(before) >= marker['ready_quanta'])}
    report = {'first_frame': int(frames[0]), 'last_frame_exclusive': int(frames[-1] + quantum),
              'verified_window_frames': [start, stop], 'marker_callbacks_before_voice': len(before),
              'marker_pcm': match}
    if marker.get('observe_input'):
        input_frames = np.asarray(metadata['inputFrames'])
        if input_frames.shape != (count,):
            raise ValueError('先行信号の入力フレーム数の観測点が不足しています')
        checks['marker_input_has_full_quantum'] = bool(np.all(input_frames == quantum))
        report['input_quanta_by_frame_count'] = {
            int(size): int(total) for size, total in zip(*np.unique(input_frames, return_counts=True), strict=True)}
    return checks, report


def capture_trials(order, markers, window, spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun):
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    copied = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, copied)
    binary = sha256(copied)
    dictionaries = {True: sha256(song.DICTIONARY),
                    False: song.bytes_digest(gzip.decompress(song.DICTIONARY.read_bytes())).hexdigest()}
    upper_pcm = np.fromfile(upper, dtype='<f4')
    checks = {'wasm_matches_offline': binary == sha256(wasm),
              'dictionary_matches_upstream': dictionaries[True] == sha256(song.UPSTREAM_DICTIONARY)}
    trials = []
    for number, pair_order in enumerate(order, 1):
        for mode in pair_order:
            label = f'{number}-{mode}'
            folder = artifacts / label
            options = {'single_song_capture': True, 'skip_invalid_lyrics': True,
                       'output_probe': {'quantum': spec['quantum'], 'captureQuanta': spec['output_probe_quanta']}}
            marker = markers.get(mode)
            if marker is not None:
                options['shared_context_marker'] = marker
            row = {'trial': label, 'pair': number, 'mode': mode}
            local = {}
            try:
                browser, report, rate, pcm = realtime.cross.capture(
                    folder, 'chromium', live, offline['input.json'], '...', execute, options=options, case_path=fixed_path)
                local, result, reference = realtime.compare(browser, report, rate, pcm, folder, offline, fixed,
                                                            upper_pcm, dictionaries, binary, spec)
                row.update(result)
                clock = result['clock']
                probe_checks, probe = realtime.compare_output_probe(folder, clock, reference, spec)
                local.update(probe_checks)
                armed = report['realtime']['armedContextFrame']
                before_arm = [g for g in probe['gaps'] if clock['startup_frame'] <= g['after_frame'] < armed]
                before_song = [g for g in probe['gaps'] if clock['startup_frame'] <= g['after_frame'] < clock['start_frame']]
                local['startup_jumps_agree'] = len(before_arm) == clock['startup_discontinuities']
                row.update(output_probe=probe, gaps_before_song=before_song,
                           missing_frames_before_song=sum(g['missing_frames'] for g in before_song))
                if marker is not None:
                    marker_checks, row['marker'] = marker_observations(folder, marker, window, clock, spec)
                    local.update(marker_checks)
            except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                row['error'] = str(error)
                local['capture_and_comparison_completed'] = False
            checks.update({f'{label}/{k}': value for k, value in local.items()})
            trials.append(row)
    return checks, trials


def measure(study, spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun):
    order = study['condition_order']
    checks, trials = capture_trials(order, {'lead': study['marker']}, study['marker_observation_quanta'],
                                     spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun)

    pairs = []
    for number, pair_order in enumerate(order, 1):
        group = {r['mode']: r for r in trials if r['pair'] == number and 'error' not in r}
        if set(group) == set(pair_order):
            row = {mode: group[mode]['missing_frames_before_song'] for mode in pair_order}
            pairs.append({'pair': number, 'missing_frames': row, 'lead_minus_cold_frames': row['lead'] - row['cold']})
    counts = {mode: sum(row['missing_frames'][mode] > 0 for row in pairs) for mode in ('cold', 'lead')}
    return {'checks': checks, 'predictions': {'fewer_startup_gaps_with_lead': len(pairs) == len(study['condition_order'])
                                            and counts['lead'] < counts['cold']},
            'trials': trials, 'paired_startup': pairs, 'trials_with_startup_gaps': counts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = READ(CASE)
    cases = CASE.parent
    realtime_path = cases / study['realtime_study']
    realtime_case = READ(realtime_path)
    offline_path = cases / realtime_case['offline_study']
    offline_case = READ(offline_path)
    fixed_path = cases / offline_case['capture_case']
    live_path = cases / realtime_case['live_case']
    fixed, live = READ(fixed_path), READ(live_path)
    spec = realtime_case['measurement']
    revision = study['upstream_revision']
    if (any(c['upstream_revision'] != revision for c in (realtime_case, offline_case, fixed, live))
            or study['marker']['quantum'] != spec['quantum']
            or any(sorted(pair) != ['cold', 'lead'] for pair in study['condition_order'])
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流、歌唱または比較の事前登録が一致しません')
    previous = song.run_manifest(study['realtime_reference_run'], realtime_case['id'], revision)
    initial = song.run_manifest(study['previous_run'], study['id'], revision)
    offline = song.run_manifest(realtime_case['offline_run'], offline_case['id'], revision)
    upstream = song.run_manifest(offline_case['reference_run'], 'song-voice-fast-constriction-source', revision)
    if any(run[1]['status'] != 'pass' for run in (previous, offline, upstream)):
        parser.error('保存した歌唱の基準が揃いません')
    label = study['condition']
    reference = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
        'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
    upper = song.verified_path(upstream, 'artifacts/upstream-pcm.f32')
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    prior_summary = song.verified_path(previous, 'summary.json')
    initial_summary = song.verified_path(initial, 'summary.json')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'turbulence_seed': offline_case['noise_seed'],
                'measurement_revision': study['measurement_revision'], 'previous_run': initial[0].name,
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, realtime_path, offline_path, fixed_path, live_path, Path(__file__).resolve(), upper, wasm,
              prior_summary, initial_summary, *reference.values(),
              *(r[0] / 'manifest.json' for r in (previous, offline, upstream, initial)),
              *song.web_sources(), *song.shared.candidate_sources(), *(Path(module.__file__) for module in (
                  realtime, realtime.cross, song, song.wasm, song.shared, song.realtime))]
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, spec, fixed, fixed_path, live, reference, upper, wasm, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
