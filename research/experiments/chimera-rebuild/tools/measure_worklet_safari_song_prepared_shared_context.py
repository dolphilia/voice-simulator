"""Safariで既に鳴っている先行音と、予備描画付き歌唱の構築を照合する。"""

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_song_schedule_default_source import pcm_difference
from measure_song_schedule_drift import read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_safari_song_prepared_pause import CAPTURE, WASM, analyze_trial
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-safari-song-prepared-shared-context.json'


def compare_marker(folder, report, study, *, preparation_end=None, expected_pcm=None, maximum_zero_error=0):
    if (folder / 'marker-error.json').exists():
        raise ValueError(read_json(folder / 'marker-error.json')['error'])
    marker = study['marker']
    document = read_json(folder / 'marker.json')
    frames = np.asarray(document['frames'], dtype=np.int64)
    input_lengths = np.asarray(document['inputFrames'])
    times = np.asarray(document['callbackEpochMs'], dtype=np.float64)
    pcm = np.fromfile(folder / 'marker.f32le', dtype='<f4')
    quantum, count = marker['quantum'], marker['capture_quanta']
    if (frames.shape != times.shape or frames.shape != input_lengths.shape or frames.shape != (count,)
            or pcm.shape != (quantum * count,) or not np.isfinite(times).all() or not np.isfinite(pcm).all()
            or np.any(np.diff(times) < 0)):
        raise ValueError('先行信号の時刻またはPCMの形式が登録と一致しません')
    expected_frames = document['startFrame'] + np.arange(count) * quantum
    if expected_pcm is None:
        samples = np.arange(quantum * count, dtype=np.int64)
        x = (samples * marker['multiplier'] + marker['offset']) % marker['modulus']
        expected_pcm = ((x - marker['center']) / marker['scale']).astype('<f4')
    compare = pcm_difference(expected_pcm, pcm, 0)
    construction = report['scoreConstruction']
    begin, end = construction['startedAtEpochMs'], construction['finishedAtEpochMs']
    scheduled = report['realtime']['scheduledContextFrame']
    first_output = report['realtime']['firstOutputEpochMs']
    start_index = int(np.searchsorted(times, begin, side='left'))
    baseline_end = start_index - 1
    baseline_start = baseline_end - study['constructor_baseline_gaps']
    overlapping = np.flatnonzero((times[:-1] <= end) & (times[1:] >= begin))
    checks = {
        'marker_pcm_bits': compare['bit_differences'] == 0,
        'marker_continuous_frames': (document['sampleRate'] == study['sample_rate_hz']
                                     and np.array_equal(frames, expected_frames)
                                     and bool(np.all(input_lengths == quantum))),
        'marker_spans_construction_and_song': bool(
            times[marker['ready_quanta'] - 1] <= begin <= end <= first_output <= times[-1]
            and baseline_start >= 0 and len(overlapping) > 0
            and frames[0] < scheduled and frames[-1] + quantum >= scheduled + report['outputFrames']),
    }
    gaps = np.diff(times)
    timing = {'start_frame': int(frames[0]), 'end_frame': int(frames[-1] + quantum),
              'marker_pcm': compare, 'constructing_ms': end - begin,
              'callbacks_strictly_inside_construction': int(np.count_nonzero((times > begin) & (times < end)))}
    if maximum_zero_error:
        zero = expected_pcm == 0
        error = float(np.max(np.abs(pcm[zero]), initial=0))
        mismatch = int(np.count_nonzero(pcm[~zero].view('<u4') != expected_pcm[~zero].view('<u4')))
        del checks['marker_pcm_bits']
        checks['marker_pcm_with_zero_tolerance'] = mismatch == 0 and error <= maximum_zero_error
        timing.update(nonzero_reference_bit_differences=mismatch, maximum_zero_error=error)
    if len(overlapping):
        index = overlapping[np.argmax(gaps[overlapping])]
        timing.update(max_overlapping_gap_ms=float(gaps[index]),
                      max_gap_frames=[int(frames[index]), int(frames[index + 1])],
                      gap_contains_construction=bool(times[index] <= begin and end <= times[index + 1]))
    if baseline_start >= 0:
        baseline = gaps[baseline_start:baseline_end]
        timing.update(baseline_median_ms=float(np.median(baseline)), baseline_max_ms=float(baseline.max()))
    if preparation_end is not None:
        window = np.flatnonzero((times[:-1] <= preparation_end) & (times[1:] >= begin))
        checks['marker_spans_preparation'] = bool(end <= preparation_end <= first_output and len(window) > 0)
        if len(window):
            index = window[np.argmax(gaps[window])]
            timing.update(preparation_window_max_gap_ms=float(gaps[index]),
                          preparation_window_max_gap_frames=[int(frames[index]), int(frames[index + 1])],
                          callbacks_strictly_inside_preparation_window=int(
                              np.count_nonzero((times > begin) & (times < preparation_end))))
    return checks, timing


def measure(study, pause_study, references, order, fields, artifacts, execute):
    execute(['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build'],
            cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    binary_hash = sha256(binary)
    checks, trials, pairs = {}, {}, []
    for number, sequence in enumerate(order, 1):
        pair = {'pair': number}
        for warm in sequence:
            label = f'pair-{number}-warm-{warm}'
            folder = artifacts / label
            folder.mkdir()
            case, wav, report = references[warm]
            configuration = {'song_preset': 'prepared', 'startup_timeout_seconds': study['startup_timeout_seconds'],
                             'shared_context_marker': study['marker'] | {'moduleName': 'fixed-processor-entry'},
                             'mid_song_pause': pause_study['pause'] | {'perform_pause': False}}
            options = folder / 'capture-case.json'
            options.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + '\n')
            trial = {'warm_up_frames': warm, 'mode': 'continuous', 'route': 'direct'}
            try:
                execute(['node', str(CAPTURE), str(folder), str(case), str(options)],
                        cwd=WEB, stdout=folder / 'browser-command.log')
                _, pcm = wavfile.read(wav)
                local, singing, _ = analyze_trial(label, trial, pause_study, read_json(case), binary_hash, pcm,
                                                   read_json(report), fields, folder, reference_live=True)
                marker_checks, marker = compare_marker(folder, read_json(folder / 'browser.json'), study)
                checks.update({f'{label}/{key}': value for key, value in (local | marker_checks).items()})
                trials[label] = trial | {'song': singing, 'marker': marker}
                if 'max_overlapping_gap_ms' in marker:
                    pair[str(warm)] = marker['max_overlapping_gap_ms']
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                checks[f'{label}/capture_completed'] = False
                trials[label] = trial | {'error': str(error)}
        names = [str(warm) for warm in study['warm_up_frames']]
        if all(name in pair for name in names):
            pair['gap_increase_ms'] = pair[names[1]] - pair[names[0]]
        pairs.append(pair)
    increases = [pair['gap_increase_ms'] for pair in pairs if 'gap_increase_ms' in pair]
    prepared = [trial['marker'] for trial in trials.values() if trial['warm_up_frames'] > 0 and 'marker' in trial]
    predictions = {'larger_callback_gap': (len(increases) == len(order)
                                           and median(increases) >= study['minimum_paired_gap_increase_ms']),
                   'prepared_construction_enclosed_by_one_gap': (len(prepared) == len(order)
                       and all(marker.get('gap_contains_construction') for marker in prepared))}
    return {'checks': checks, 'predictions': predictions, 'trials': trials, 'pairs': pairs,
            'median_paired_gap_increase_ms': median(increases) if increases else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reverse', action='store_true', help='各ペア内の予備描画条件の順を逆にする')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    ref = study['reference']
    source_case = CASE.parent / ref['case']
    pause_study = read_json(source_case)
    reference = run_manifest(ref['run'], pause_study['id'], revision)
    if reference[1]['status'] != 'pass':
        parser.error('比較用のSafari保存実行が合格していません')
    prepared_case = CASE.parent / pause_study['reference']['case']
    fields = list(read_json(prepared_case)['measurement']['state_tolerance'])
    inputs = [CASE, source_case, prepared_case, Path(__file__).resolve(), reference[0] / 'manifest.json',
              verified_path(reference, 'summary.json'), CAPTURE, CAPTURE.with_name('safari-webdriver.mjs'),
              *web_sources(), *candidate_sources()]
    references = {}
    for warm in study['warm_up_frames']:
        label = 'direct-zero-before' if warm == 0 else f'direct-{warm}-continuous'
        paths = [verified_path(reference, f'artifacts/{label}/{name}')
                 for name in ('browser-case.json', 'browser.wav', 'browser.json')]
        if read_json(paths[0])['song_voice']['warm_up_frames'] != warm:
            parser.error(f'保存基準の予備描画量が一致しません ({label})')
        references[warm] = paths
        inputs.extend(paths)
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_fan_crossing_allocations.py', 'measure_song_schedule_default_source.py',
        'measure_worklet_fixed.py', 'measure_worklet_safari_song_prepared_pause.py',
        'measure_worklet_safari_song_resume_order.py', 'measure_worklet_song.py',
        'measure_worklet_song_prepared_source.py', 'measure_uniform_tube.py'))
    order = study['condition_order']
    if args.reverse:
        order = [pair[::-1] for pair in order]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv], 'reference_run': reference[0].name,
                'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
                'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, pause_study, references, order, fields, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
