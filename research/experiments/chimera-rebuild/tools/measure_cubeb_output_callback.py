"""cubebがCore Audioへ返すPCMと、機器が要求した時刻を照合する。"""

import argparse
import csv
import json
import math
from pathlib import Path
import struct
import subprocess
import sys

from measure_worklet_live_song_process_tap import song


TOOLS = Path(__file__).resolve().parent
CASE = song.WORKSPACE / 'cases/cubeb-output-callback-probe.json'


def load_blocks(directory):
    with (directory / 'blocks.csv').open(newline='') as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        for column in ('pcm_byte_offset', 'frames', 'host_time', 'timestamp_flags', 'entered', 'returned'):
            row[column] = int(row[column])
        row['sample_time'] = float(row['sample_time'])
    return rows


def expected_pcm(start, count):
    pcm = bytearray()
    for frame in range(start, start + count):
        value = (((421 * frame + 173) % 65_521) - 32_760) / 8_388_608
        pcm.extend(struct.pack('<ff', value, -value))
    return pcm


def inspect(directory, metadata, case, late=None, *, reference_pcm=None):
    blocks = load_blocks(directory)
    pcm = (directory / 'pcm.f32le').read_bytes()
    radius = case['window_radius_callbacks']
    index = case['overrun_callback_index']
    requested = case['requested_frames']
    first = index - radius
    window = blocks[first:index + radius + 1]
    frame_bytes = case['channels'] * 4
    offsets = []
    size = 0
    for block in blocks:
        offsets.append(size)
        size += block['frames'] * frame_bytes
    checks = {
        'rust_backend': metadata['backend'] == 'audiounit-rust',
        'all_blocks_recorded': len(blocks) == case['observation_callbacks'],
        'valid_buffer': (directory / 'state.txt').read_text().strip() == 'ready',
        'pcm_size_and_offsets': offsets == [block['pcm_byte_offset'] for block in blocks] and size == len(pcm),
        'centered_window': len(window) == 2 * radius + 1,
        'requested_block_size': bool(window) and all(row['frames'] == requested for row in window),
        'valid_clock_flags': bool(window) and all(
            row['timestamp_flags'] & 3 == 3 and math.isfinite(row['sample_time']) for row in window),
        'data_path': bool(window) and all(row['stage'] == 'data' for row in blocks[:index + radius + 1]),
        'positive_clock_scale': metadata['timebase_numer'] > 0 and metadata['timebase_denom'] > 0,
    }
    result = {'blocks': len(blocks), 'block_sizes': sorted({row['frames'] for row in blocks}), 'checks': checks}
    if not all(checks.values()):
        return result

    start = offsets[first] // frame_bytes
    samples = len(window) * requested
    stop = (start + samples) * frame_bytes
    expected = expected_pcm(start, samples) if reference_pcm is None else reference_pcm[offsets[first]:stop]
    checks['pcm_bit_exact'] = pcm[offsets[first]:stop] == expected
    tick_ms = metadata['timebase_numer'] / metadata['timebase_denom'] / 1e6
    rate = case['sample_rate_hz']
    budget = 1000 * requested / rate
    intervals = []
    for offset, (current, following) in enumerate(zip(window, window[1:]), -radius):
        intervals.append({
            'offset': offset,
            'callback_ms': (current['returned'] - current['entered']) * tick_ms,
            'host_interval_ms': (following['host_time'] - current['host_time']) * tick_ms,
            'actual_entry_interval_ms': (following['entered'] - current['entered']) * tick_ms,
            'device_sample_gap_frames': following['sample_time'] - current['sample_time'] - requested,
        })
        if late is None:
            intervals[-1].update({
                'return_to_next_entry_ms': (following['entered'] - current['returned']) * tick_ms,
                'scheduled_host_minus_entry_ms': (current['host_time'] - current['entered']) * tick_ms,
            })
        else:
            intervals[-1]['expected_gap_frames'] = case['expected_overrun_gap_frames'] if late and offset == 0 else 0
    if late is None:
        checks['device_sample_clock'] = all(row['device_sample_gap_frames'] + requested > 0 for row in intervals)
        checks['valid_callback_order'] = (all(row['callback_ms'] >= 0 and row['return_to_next_entry_ms'] >= 0
                                             for row in intervals) and window[-1]['returned'] >= window[-1]['entered'])
        gap_key = 'device_sample_gap_frames'
    else:
        checks['device_sample_clock'] = all(
            row['device_sample_gap_frames'] == row['expected_gap_frames'] for row in intervals)
        checks['target_callback_budget'] = (intervals[radius]['callback_ms'] > budget) == late
        gap_key = 'expected_gap_frames'
    checks['scheduled_host_clock'] = all(
        row['host_interval_ms'] > 0 and
        abs(row['host_interval_ms'] - budget - 1000 * row[gap_key] / rate) <= case['host_clock_tolerance_ms']
        for row in intervals)
    result.update({'matched_pcm_frames': samples if checks['pcm_bit_exact'] else 0,
                   'budget_ms': budget, 'target': intervals[radius], 'intervals': intervals})
    return result


def capture(case, binary, directory, execute, delay_us, late):
    directory.mkdir()
    metadata = directory / 'probe.json'
    try:
        execute(['env', f'CHIMERA_CUBEB_OUTPUT_DIR={directory}',
                 f'CHIMERA_CUBEB_OUTPUT_BLOCKS={case["observation_callbacks"]}', str(binary),
                 str(case['sample_rate_hz']), str(case['requested_frames']), str(case['overrun_callback_index']),
                 str(delay_us), str(case['observation_callbacks'] + 2)], stdout=metadata)
        streams = list(directory.glob('cubeb-output-*'))
        if len(streams) != 1:
            return {'checks': {'one_stream': False}, 'streams': len(streams)}
        result = inspect(streams[0], json.loads(metadata.read_text()), case, late)
        result['checks']['one_stream'] = True
        return result
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        return {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}


def summarize_sweep(conditions, sweep, case):
    groups, with_gap, without_gap = {}, [], []
    for delay in sweep['delay_us']:
        trials = [t for t in conditions.values() if t['delay_us'] == delay and all(t['checks'].values())]
        times = [t['target']['callback_ms'] for t in trials]
        gaps = [t['target']['device_sample_gap_frames'] for t in trials]
        groups[str(delay)] = {'valid_trials': len(trials), 'callback_ms_range': [min(times), max(times)] if times else None,
                              'next_request_gap_frames': gaps, 'positive_gap_count': sum(gap > 0 for gap in gaps),
                              'other_request_gaps': [{'trial': t['trial'], 'offset': row['offset'],
                                                      'gap_frames': row['device_sample_gap_frames']}
                                                     for t in trials for row in t['intervals']
                                                     if row['offset'] != 0 and row['device_sample_gap_frames'] != 0]}
        with_gap.extend(ms for ms, gap in zip(times, gaps) if gap > 0)
        without_gap.extend(ms for ms, gap in zip(times, gaps) if gap == 0)
    shortest_gap = min(with_gap, default=None)
    longest_contiguous = max(without_gap, default=None)
    budget = 1000 * case['requested_frames'] / case['sample_rate_hz']
    runs = len(sweep['round_order'])
    control, overrun = (groups[str(delay)]['next_request_gap_frames'] for delay in (0, round(case['delay_ms'] * 1000)))
    return {'budget_ms': budget, 'groups': groups, 'shortest_callback_with_gap_ms': shortest_gap,
            'longest_callback_without_gap_ms': longest_contiguous,
            'duration_ranges_overlap': shortest_gap is not None and longest_contiguous is not None and
            shortest_gap <= longest_contiguous,
            'predictions': {'no_wait_controls_contiguous': control == [0] * runs,
                            'overrun_controls_skip_one_request': overrun == [case['expected_overrun_gap_frames']] * runs,
                            'gap_below_nominal_budget_observed': shortest_gap is not None and shortest_gap < budget}}


def compare_sweeps(current, references, tolerance):
    lower = max(ref['longest_callback_without_gap_ms'] for ref in references)
    upper = min(ref['shortest_callback_with_gap_ms'] for ref in references)
    reference_period = references[0]['budget_ms']
    current_period = current['budget_ms']
    delta = current_period - reference_period
    ratio = current_period / reference_period
    predictions = {'constant_margin_ms': [lower + delta - tolerance, upper + delta + tolerance],
                   'proportional_margin_ms': [lower * ratio - tolerance, upper * ratio + tolerance]}
    actual = [current['longest_callback_without_gap_ms'], current['shortest_callback_with_gap_ms']]
    separated = None not in actual and actual[0] < actual[1]
    matches = [name for name, (start, end) in predictions.items() if separated and actual[0] <= end and start <= actual[1]]
    return {'reference_bracket_ms': [lower, upper], 'reference_period_ms': reference_period,
            'observed_bracket_ms': actual, 'predicted_brackets_ms': predictions, 'matching_predictions': matches,
            'distinguished_prediction': matches[0] if len(matches) == 1 else None}


def read_reference_sweeps(comparison, baseline, revision, binary_hash):
    inputs, summaries = [], []
    reference_period = 1000 * baseline['requested_frames'] / baseline['sample_rate_hz']
    for name in comparison['reference_runs']:
        run = song.run_manifest(name, comparison['reference_case_id'], revision)
        root, manifest = run
        summary_file = song.verified_path(run, 'summary.json')
        sweep = json.loads(summary_file.read_text())['sweep']
        if (manifest['status'] != 'pass' or manifest['probe_binary_sha256'] != binary_hash or
                sweep['budget_ms'] != reference_period or sweep['duration_ranges_overlap'] or
                None in (sweep['longest_callback_without_gap_ms'], sweep['shortest_callback_with_gap_ms'])):
            raise ValueError(f'{name} の256フレーム基準を照合できません')
        summaries.append(sweep)
        inputs.extend([root / 'manifest.json', summary_file])
    if (not summaries or max(s['longest_callback_without_gap_ms'] for s in summaries) >=
            min(s['shortest_callback_with_gap_ms'] for s in summaries)):
        raise ValueError('保存済みの基準実行で連続と飛びを分けられません')
    return summaries, inputs


def measure(case, binary, artifacts, execute, sweep=None, reference_sweeps=()):
    conditions = {}
    checks = {}
    late_delay = round(case['delay_ms'] * 1000)
    order = [('control-1', 0, False), ('overrun-1', late_delay, True),
             ('overrun-2', late_delay, True), ('control-2', 0, False)]
    if sweep:
        order = [(f'{number}-{delay}us', delay, None) for number, direction in enumerate(sweep['round_order'], 1)
                 for delay in sorted(sweep['delay_us'], reverse=direction == 'descending')]
    for label, delay, late in order:
        result = capture(case, binary, artifacts / label, execute, delay, late)
        if sweep:
            result.update({'trial': label, 'delay_us': delay})
            if 'target' in result:
                result['checks']['elapsed_for_requested_delay'] = (
                    result['target']['callback_ms'] + sweep['maximum_early_return_ms'] >= delay / 1000)
        conditions[label] = result
        checks.update({f'{label}/{key}': value for key, value in result['checks'].items()})
    result = {'checks': checks, 'conditions': conditions}
    if sweep:
        result['sweep'] = summarize_sweep(conditions, sweep, case)
        if reference_sweeps:
            result['comparison'] = compare_sweeps(result['sweep'], reference_sweeps,
                                                  sweep['comparison']['prediction_tolerance_ms'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('binary', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    binary = args.binary.resolve(strict=True)
    case_path = args.case.resolve(strict=True)
    study = json.loads(case_path.read_text())
    sweep = study if 'base_case' in study else None
    case = json.loads(CASE.read_text()) if sweep else study
    inputs = [case_path, Path(__file__).resolve(), TOOLS / 'chimera-cubeb-output-probe.rs',
              TOOLS / 'chimera-cubeb-output-snapshot.patch']
    binary_hash = song.sha256(binary)
    reference_sweeps = ()
    if sweep:
        delays = sweep['delay_us']
        requested = sweep.get('requested_frames', case['requested_frames'])
        overrun_us = sweep.get('overrun_control_us', round(case['delay_ms'] * 1000))
        if (sweep['base_case'] != CASE.name or sweep['upstream_revision'] != case['upstream_revision'] or
                type(requested) is not int or not 128 <= requested <= 512 or
                type(overrun_us) is not int or overrun_us <= 1e6 * requested / case['sample_rate_hz'] or
                not delays or sorted(set(delays)) != delays or not all(type(delay) is int and delay >= 0 for delay in delays) or
                0 not in delays or overrun_us not in delays or
                sorted(sweep['round_order']) != ['ascending', 'ascending', 'descending', 'descending'] or
                not 0 <= sweep['maximum_early_return_ms'] < 0.1):
            parser.error('待機範囲またはcubebの基準ケースに不一致があります')
        inputs.append(CASE)
        comparison = sweep.get('comparison')
        if comparison:
            if not comparison['prediction_tolerance_ms'] > 0:
                parser.error('予測範囲の許容幅は正の値にしてください')
            try:
                reference_sweeps, reference_inputs = read_reference_sweeps(
                    comparison, case, case['upstream_revision'], binary_hash)
            except (OSError, TypeError, ValueError, KeyError) as error:
                parser.error(f'比較基準を利用できません ({error})')
            inputs.extend(reference_inputs)
        case.update({'requested_frames': requested, 'delay_ms': overrun_us / 1000,
                     'expected_overrun_gap_frames': requested})
    details = {'case_id': study['id'], 'upstream_revision': case['upstream_revision'],
               'cubeb_coreaudio_revision': case['cubeb_coreaudio_revision'],
               'firefox_revision': case['firefox_revision'],
               'probe_binary': str(binary), 'probe_binary_sha256': binary_hash}
    if sweep:
        details.update({'analysis_command': [sys.executable, *sys.argv],
                        'analysis_directory': str(Path.cwd())})
    return song.shared.record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case, binary, artifacts, execute, sweep, reference_sweeps),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
