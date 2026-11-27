"""Safariで本番の歌唱状態を予備描画する時間と先行音を比べる。"""

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_song_schedule_drift import read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_safari_song_prepared_pause import CAPTURE, WASM, analyze_trial
from measure_worklet_safari_song_prepared_shared_context import compare_marker
from song_score_preparation_timing import (
    compare_preparation_timing, summarize_initial_blocks, summarize_preparation_timing, summarize_switch_comparison,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-safari-song-split-score-preparation.json'
BLOCK_SIZE_CASE = WORKSPACE / 'cases/worklet-safari-song-score-preparation-block-size.json'
TIMING_CASE = WORKSPACE / 'cases/worklet-safari-song-score-preparation-timing.json'
INITIAL_BLOCKS_CASE = WORKSPACE / 'cases/worklet-safari-song-score-preparation-initial-blocks.json'
SWITCH_CASE = WORKSPACE / 'cases/worklet-safari-song-score-preparation-switch.json'


def preparation_lengths(total, block_frames, initial_blocks):
    if block_frames is None:
        return None
    lengths = []
    remaining = total
    for block in initial_blocks:
        if remaining == 0:
            break
        length = min(block, remaining)
        lengths.append(length)
        remaining -= length
    whole, tail = divmod(remaining, block_frames)
    lengths.extend([block_frames] * whole)
    if tail:
        lengths.append(tail)
    return lengths


def compare_preparation(report, warm_up_frames, quantum, lengths):
    construction_end = report['scoreConstruction']['finishedAtEpochMs']
    if lengths is None:
        return {'preparation_sequence': 'scorePreparation' not in report}, construction_end, None
    preparation = report['scorePreparation']
    live = report['realtime']
    count = len(lengths)
    end = preparation['finishedAtEpochMs']
    checks = {
        'preparation_sequence': (
            preparation['frames'] == warm_up_frames and preparation['callbacks'] == count
            and preparation['discontinuities'] == 0
            and preparation['lastContextFrame'] - preparation['firstContextFrame'] == (count - 1) * quantum
            and construction_end <= preparation['startedAtEpochMs'] <= end <= live['firstOutputEpochMs']),
        'scheduled_after_preparation': (
            preparation['lastContextFrame'] + quantum == live['startupFirstContextFrame']
            <= live['armedContextFrame'] <= live['scheduledContextFrame']),
    }
    return checks, end, preparation


def measure_preparation_gaps(folder, preparation, quantum):
    marker = read_json(folder / 'marker.json')
    times = dict(zip(marker['frames'], marker['callbackEpochMs'], strict=True))
    first, last = preparation['firstContextFrame'], preparation['lastContextFrame']
    if last < first + 2 * quantum:
        raise ValueError('第1片の後に先行信号の間隔を測る量子が不足しています')
    interior = range(first + quantum, last, quantum)
    return {'before_first_block_ms': times[first] - times[first - quantum],
            'after_first_block_ms': times[first + quantum] - times[first],
            'interior_max_ms': max(times[frame + quantum] - times[frame] for frame in interior),
            'after_last_block_ms': times[last + quantum] - times[last]}


def summarize_block_sizes(study, shared, pairs):
    names = sorted(study['block_frames_by_condition'], key=study['block_frames_by_condition'].get)
    small, large = names
    for pair in pairs:
        if small in pair and large in pair:
            first, second = pair[small], pair[large]
            pair.update(startup_reduction_ms=first['startup_ms'] - second['startup_ms'],
                        preparation_reduction_ms=first['preparation_ms'] - second['preparation_ms'],
                        interior_gap_increase_ms=second['interior_max_ms'] - first['interior_max_ms'])
    complete = [pair for pair in pairs if 'startup_reduction_ms' in pair]
    medians = {key: median(pair[key] for pair in complete) if complete else None
               for key in ('startup_reduction_ms', 'preparation_reduction_ms', 'interior_gap_increase_ms')}
    frames = study['warm_up_frames']
    counts = [(frames + block - 1) // block for block in (study['block_frames_by_condition'][name] for name in names)]
    expected = (counts[0] - counts[1]) * shared['marker']['quantum'] * 1000 / shared['sample_rate_hz']
    all_pairs = len(complete) == len(pairs)
    predictions = {
        'earlier_song_start': (all_pairs and medians['startup_reduction_ms'] >= study['minimum_median_startup_reduction_ms']),
        'preparation_reduction_matches_quantum_count': (all_pairs and abs(medians['preparation_reduction_ms'] - expected)
                                                        <= study['preparation_reduction_tolerance_ms']),
        'bounded_interior_gap_increase': (all_pairs and medians['interior_gap_increase_ms']
                                          <= study['maximum_median_interior_gap_increase_ms']),
    }
    return {'predictions': predictions, 'paired_medians': medians, 'expected_preparation_reduction_ms': expected}


def measure(study, shared, pause, reference, order, fields, artifacts, execute):
    execute(['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build'],
            cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    binary_hash = sha256(binary)
    source, wav, report = reference
    _, reference_pcm = wavfile.read(wav)
    reference_report = read_json(report)
    source_case = read_json(source)
    marker_options = shared['marker'] | {'moduleName': 'fixed-processor-entry',
                                         'capture_quanta': study['marker_capture_quanta']}
    shared = shared | {'marker': marker_options}
    trial = {'warm_up_frames': study['warm_up_frames'], 'mode': 'continuous', 'route': 'direct'}
    compare_block_sizes = 'block_frames_by_condition' in study
    timing_settings = study.get('preparation_timing')
    switch = study.get('switch_comparison')
    blocks = study['block_frames_by_condition'] if compare_block_sizes else {'bulk': None, 'split': study['split_block_frames']}
    initial_blocks = study.get('initial_blocks_by_condition', {})
    lengths = {name: preparation_lengths(study['warm_up_frames'], block, initial_blocks.get(name, ()))
               for name, block in blocks.items()}
    checks, trials, pairs = {}, {}, []
    samples = {}
    for number, sequence in enumerate(order, 1):
        pair = {'pair': number}
        for condition in sequence:
            block_frames = blocks[condition]
            label = f'pair-{number}-{condition}'
            folder = artifacts / label
            folder.mkdir()
            options = folder / 'capture-case.json'
            configuration = {'song_preset': 'prepared', 'startup_timeout_seconds': shared['startup_timeout_seconds'],
                             'mid_song_pause': pause['pause'] | {'perform_pause': False},
                             'shared_context_marker': marker_options}
            if block_frames is not None:
                configuration['score_preparation_block_frames'] = block_frames
            if initial_blocks.get(condition):
                configuration['score_preparation_initial_blocks'] = initial_blocks[condition]
            if timing_settings:
                configuration['trace_score_preparation_blocks'] = True
            options.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + '\n')
            try:
                execute(['node', str(CAPTURE), str(folder), str(source), str(options)],
                        cwd=WEB, stdout=folder / 'browser-command.log')
                local, song, _ = analyze_trial(label, trial, pause, source_case, binary_hash, reference_pcm,
                                               reference_report, fields, folder, reference_live=True)
                candidate = read_json(folder / 'browser.json')
                prep_checks, end, prep = compare_preparation(candidate, study['warm_up_frames'],
                                                             marker_options['quantum'], lengths[condition])
                marker_checks, marker = compare_marker(folder, candidate, shared, preparation_end=end)
                if compare_block_sizes:
                    marker.update(measure_preparation_gaps(folder, prep, marker_options['quantum']))
                timing = None
                if timing_settings:
                    local_timing, timing, values = compare_preparation_timing(folder, candidate, prep, lengths[condition],
                                                                             marker_options, timing_settings, switch=switch)
                    prep_checks.update(local_timing)
                    samples.setdefault(condition, {})[number] = values
                checks.update({f'{label}/{key}': bool(value) for key, value in (local | prep_checks | marker_checks).items()})
                trials[label] = {'condition': condition, 'song': song, 'marker': marker, 'preparation': prep}
                if timing is not None:
                    trials[label]['preparation_timing'] = timing
                pair[condition] = {'gap_ms': marker['preparation_window_max_gap_ms'],
                                   'startup_ms': song['click_to_first_output_ms']}
                if compare_block_sizes:
                    pair[condition].update(preparation_ms=end - prep['startedAtEpochMs'],
                                           interior_max_ms=marker['interior_max_ms'])
                if timing and 'startup_marker_max_gap_ms' in timing:
                    pair[condition]['startup_marker_max_gap_ms'] = timing['startup_marker_max_gap_ms']
                if switch:
                    first = timing['switch']['blocks'][0]
                    pair[condition].update(prefix_peak_process_ms=timing['switch']['prefix_peak_process_ms'],
                                           first_full_process_ms=first['process_ms'],
                                           first_full_marker_peak_ms=max(first['marker_gap_before_ms'], first['marker_gap_after_ms']))
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                checks[f'{label}/capture_completed'] = False
                trials[label] = {'condition': condition, 'error': str(error)}
        if 'bulk' in pair and 'split' in pair:
            pair['gap_reduction_ms'] = pair['bulk']['gap_ms'] - pair['split']['gap_ms']
            pair['startup_increase_ms'] = pair['split']['startup_ms'] - pair['bulk']['startup_ms']
        pairs.append(pair)
    if switch:
        return {'checks': checks, 'trials': trials, 'pairs': pairs} | summarize_switch_comparison(
            study, pairs, marker_options['quantum'], shared['sample_rate_hz'])
    if 'initial_block_comparison' in study:
        return {'checks': checks, 'trials': trials, 'pairs': pairs} | summarize_initial_blocks(
            study, pairs, samples, marker_options['quantum'], shared['sample_rate_hz'])
    if compare_block_sizes:
        result = {'checks': checks, 'trials': trials, 'pairs': pairs} | summarize_block_sizes(study, shared, pairs)
        if timing_settings:
            result['preparation_timing'], timing_predictions = summarize_preparation_timing(
                study, samples, marker_options['quantum'], shared['sample_rate_hz'])
            result['predictions'].update(timing_predictions)
        return result
    complete = [pair for pair in pairs if 'gap_reduction_ms' in pair]
    gap_reduction = median(pair['gap_reduction_ms'] for pair in complete) if complete else None
    startup_increase = median(pair['startup_increase_ms'] for pair in complete) if complete else None
    predictions = {'smaller_callback_gap': (len(complete) == len(order)
                       and gap_reduction >= study['minimum_median_gap_reduction_ms']),
                   'longer_startup': (len(complete) == len(order)
                       and startup_increase >= study['minimum_median_startup_increase_ms'])}
    return {'checks': checks, 'predictions': predictions, 'pairs': pairs, 'trials': trials,
            'median_paired_gap_reduction_ms': gap_reduction, 'median_paired_startup_increase_ms': startup_increase}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reverse', action='store_true', help='各ペア内の条件順を逆にする')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--compare-block-sizes', action='store_const', dest='case', const=BLOCK_SIZE_CASE,
                       help='128対256フレームの分割を比較する')
    modes.add_argument('--measure-block-times', action='store_const', dest='case', const=TIMING_CASE,
                       help='128対256フレームの各準備片を計時する')
    modes.add_argument('--compare-initial-blocks', action='store_const', dest='case', const=INITIAL_BLOCKS_CASE,
                       help='256フレーム固定と最初の2片を短くする分割を比較する')
    modes.add_argument('--compare-switch', action='store_const', dest='case', const=SWITCH_CASE,
                       help='同じ256フレームを準備した直後の片を比較する')
    args = parser.parse_args()
    case = args.case or CASE
    study = read_json(case)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    shared_case = case.parent / study['shared_context_case']
    shared = read_json(shared_case)
    pause_case = CASE.parent / shared['reference']['case']
    pause = read_json(pause_case)
    prepared_case = CASE.parent / pause['reference']['case']
    fields = list(read_json(prepared_case)['measurement']['state_tolerance'])
    ref = study['reference']
    reference_case = case.parent / ref['case'] if 'case' in ref else shared_case
    manifest = run_manifest(ref['run'], read_json(reference_case)['id'], revision)
    if manifest[1]['status'] != 'pass':
        parser.error('保存済みのSafari基準が合格していません')
    reference = [verified_path(manifest, f'artifacts/{ref["trial"]}/{name}')
                 for name in ('browser-case.json', 'browser.wav', 'browser.json')]
    if read_json(reference[0])['song_voice']['warm_up_frames'] != study['warm_up_frames']:
        parser.error('基準の予備描画量が登録条件と一致しません')
    inputs = [case, shared_case, pause_case, prepared_case, reference_case, Path(__file__).resolve(), manifest[0] / 'manifest.json',
              verified_path(manifest, 'summary.json'), *reference, CAPTURE, CAPTURE.with_name('safari-webdriver.mjs'),
              *web_sources(), *candidate_sources()]
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_fan_crossing_allocations.py', 'measure_song_schedule_default_source.py',
        'measure_song_schedule_drift.py', 'measure_worklet_fixed.py', 'measure_worklet_safari_song_prepared_pause.py',
        'measure_worklet_safari_song_prepared_shared_context.py', 'measure_worklet_safari_song_resume_order.py',
        'measure_worklet_song.py', 'measure_worklet_song_prepared_source.py', 'measure_uniform_tube.py',
        'song_score_preparation_timing.py', 'upstream_baseline.py'))
    order = study['condition_order']
    if args.reverse:
        order = [pair[::-1] for pair in order]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv], 'reference_run': manifest[0].name,
                'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
                'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, case, inputs, metadata,
        lambda artifacts, execute: measure(study, shared, pause, reference, order, fields, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
