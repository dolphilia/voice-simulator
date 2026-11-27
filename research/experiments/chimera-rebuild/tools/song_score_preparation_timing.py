"""歌唱の予備描画片と同じContext上の先行信号を照合する。"""

import csv
from statistics import median

import numpy as np

from measure_song_schedule_drift import read_json


COLUMNS = ['context_frame', 'quantum_frames', 'prepared_frames', 'callback_start_ms',
           'wasm_start_ms', 'wasm_end_ms', 'silence_ready_ms']


def duration_stats(values, budget, step):
    median, p95, p99 = (float(x) for x in np.percentile(values, [50, 95, 99]))
    below = int(np.count_nonzero(values + step <= budget))
    above = int(np.count_nonzero(values - step > budget))
    return {'count': int(values.size), 'minimum_ms': float(values.min()), 'mean_ms': float(values.mean()),
            'median_ms': median, 'p95_ms': p95, 'p99_ms': p99, 'maximum_ms': float(values.max()),
            'measured_over_budget': int(np.count_nonzero(values > budget)),
            'within_budget_upper_bound': below, 'over_budget_lower_bound': above,
            'uncertain_at_clock_step': int(values.size) - below - above}


def compare_preparation_timing(folder, report, preparation, expected_lengths, marker_options, settings, *, switch=None):
    trace = report['scorePreparationTrace']
    rows = np.asarray(trace['blocks'], dtype=np.float64)
    quantum = marker_options['quantum']
    if (trace['columns'] != COLUMNS or trace['omittedCallbacks'] != 0 or trace['clock'] != settings['clock']
            or rows.shape != (preparation['callbacks'], len(COLUMNS)) or not np.isfinite(rows).all()
            or rows.shape[0] < 2):
        raise ValueError('予備描画片の時計または採取形式が登録と一致しません')
    marker = read_json(folder / 'marker.json')
    times = dict(zip(marker['frames'], marker['callbackEpochMs'], strict=True))
    frames, quanta, lengths, began, wasm_start, wasm_end, ready = rows.T
    step = settings['clock_step_ms']
    checks = {
        'block_trace_frames': bool(np.array_equal(frames, preparation['firstContextFrame'] + np.arange(len(rows)) * quantum)
                                   and np.all(quanta == quantum) and np.array_equal(lengths, expected_lengths)
                                   and lengths.sum() == preparation['frames']),
        'block_trace_clock': bool(np.all(np.diff(rows[:, 3:], axis=1) >= 0)
                                  and np.all(began[1:] >= ready[:-1]) and np.all(rows[:, 3:] % step == 0)
                                  and wasm_start[0] == preparation['startedAtEpochMs']
                                  and wasm_end[-1] == preparation['finishedAtEpochMs']),
    }
    preceding, parallel, following = (np.array([times[frame + offset] for frame in frames])
                                      for offset in (-quantum, 0, quantum))
    wasm = wasm_end - wasm_start
    through_silence = ready - began
    before, after = parallel - preceding, following - parallel
    with (folder / 'preparation-blocks.csv').open('w', newline='') as output:
        writer = csv.writer(output)
        writer.writerow(COLUMNS + ['wasm_ms', 'process_through_silence_ms', 'marker_previous_epoch_ms',
                                   'marker_same_epoch_ms', 'marker_next_epoch_ms', 'marker_gap_before_ms',
                                   'marker_gap_after_ms'])
        writer.writerows(np.column_stack((rows, wasm, through_silence, preceding, parallel, following, before, after)))
    budget = 1000 * quantum / marker['sampleRate']
    slowest = int(np.argmax(through_silence))
    points = {'first': 0, 'slowest': slowest}

    def block_details(index):
        return {'block': index + 1, 'context_frame': int(frames[index]), 'prepared_frames': int(lengths[index]),
                'process_ms': float(through_silence[index]), 'wasm_ms': float(wasm[index]),
                'marker_gap_before_ms': float(before[index]), 'marker_gap_after_ms': float(after[index])}

    details = {'clock': trace['clock'], 'budget_ms': budget,
               'first_wasm_ms': float(wasm[0]), 'later_wasm': duration_stats(wasm[1:], budget, step),
               'first_process_ms': float(through_silence[0]),
               'later_process': duration_stats(through_silence[1:], budget, step),
               'marker_relation': {key: block_details(index) for key, index in points.items()}}
    window = settings.get('startup_window_blocks')
    if window:
        details['startup_blocks'] = [block_details(index) for index in range(window)]
        details['startup_marker_max_gap_ms'] = float(max(before[:window].max(), after[:window].max()))
    if switch:
        edges = np.flatnonzero(np.cumsum(lengths) == switch['frames_before_switch'])
        if len(edges) != 1:
            raise ValueError('切り替え時点の予備描画フレームを特定できません')
        index = int(edges[0]) + 1
        stop = index + switch['blocks_at_switch']
        expected_index = np.flatnonzero(np.cumsum(expected_lengths) == switch['frames_before_switch'])
        checks['switch_at_registered_frame'] = bool(
            len(expected_index) == 1 and index == expected_index[0] + 1 and stop <= len(rows)
            and np.array_equal(lengths[index:stop], expected_lengths[index:stop]))
        if stop > len(rows):
            raise ValueError('切り替え後に計時する準備片が不足しています')
        details['switch'] = {'frames_before': int(lengths[:index].sum()),
                             'prefix_peak_process_ms': float(through_silence[:index].max()),
                             'blocks': [block_details(i) for i in range(index, stop)]}
    return checks, details, (wasm, through_silence)


def summarize_initial_blocks(study, pairs, samples, quantum, rate):
    comparison = study['initial_block_comparison']
    control, candidate = comparison['control'], comparison['candidate']
    settings = study['preparation_timing']
    window, budget, step = settings['startup_window_blocks'], 1000 * quantum / rate, settings['clock_step_ms']
    complete = [pair for pair in pairs if control in pair and candidate in pair]
    for pair in complete:
        first, second = (samples[condition][pair['pair']][1] for condition in (control, candidate))
        pair.update(first_two_peak_reduction_ms=float(first[:2].max() - second[:2].max()),
                    first_window_peak_reduction_ms=float(first[:window].max() - second[:window].max()),
                    first_window_marker_gap_reduction_ms=(pair[control]['startup_marker_max_gap_ms']
                                                         - pair[candidate]['startup_marker_max_gap_ms']),
                    startup_increase_ms=pair[candidate]['startup_ms'] - pair[control]['startup_ms'])
    keys = ('first_two_peak_reduction_ms', 'first_window_peak_reduction_ms',
            'first_window_marker_gap_reduction_ms', 'startup_increase_ms')
    medians = {key: median(pair[key] for pair in complete) if complete else None for key in keys}
    covered = len(complete) == len(pairs)
    predictions = {
        'lower_first_two_peak': covered and medians['first_two_peak_reduction_ms'] >= comparison['minimum_median_first_two_peak_reduction_ms'],
        'lower_first_window_peak': covered and medians['first_window_peak_reduction_ms'] >= comparison['minimum_median_first_six_peak_reduction_ms'],
        'startup_increase_within_limit': covered and medians['startup_increase_ms'] <= comparison['maximum_median_startup_increase_ms'],
    }
    distributions = {}
    for condition, trials in samples.items():
        values = [trace[1] for trace in trials.values()]
        groups = {'first_two': [x[:2] for x in values], 'third_through_window': [x[2:window] for x in values],
                  'after_window': [x[window:] for x in values]}
        distributions[condition] = {name: duration_stats(np.concatenate(group), budget, step)
                                    for name, group in groups.items()}
    return {'paired_medians': medians, 'predictions': predictions, 'process_distributions': distributions}


def summarize_switch_comparison(study, pairs, quantum, rate):
    comparison = study['switch_comparison']
    control, candidate = comparison['control'], comparison['candidate']
    budget, step = 1000 * quantum / rate, study['preparation_timing']['clock_step_ms']
    complete = [pair for pair in pairs if control in pair and candidate in pair]
    for pair in complete:
        first, second = pair[control], pair[candidate]
        pair.update(prefix_peak_reduction_ms=first['prefix_peak_process_ms'] - second['prefix_peak_process_ms'],
                    first_full_difference_ms=second['first_full_process_ms'] - first['first_full_process_ms'],
                    first_full_marker_gap_difference_ms=second['first_full_marker_peak_ms'] - first['first_full_marker_peak_ms'],
                    startup_increase_ms=second['startup_ms'] - first['startup_ms'])
    keys = ('prefix_peak_reduction_ms', 'first_full_difference_ms', 'first_full_marker_gap_difference_ms', 'startup_increase_ms')
    medians = {key: median(pair[key] for pair in complete) if complete else None for key in keys}
    distributions = {name: duration_stats(np.array([pair[name]['first_full_process_ms'] for pair in complete]), budget, step)
                     for name in (control, candidate)} if complete else {}
    covered = len(complete) == len(pairs)
    predictions = {
        'lower_prefix_peak': covered and medians['prefix_peak_reduction_ms'] >= comparison['minimum_median_prefix_peak_reduction_ms'],
        'small_median_difference_at_switch': (covered and abs(medians['first_full_difference_ms'])
                                             <= comparison['maximum_absolute_median_first_full_difference_ms']),
        'bounded_median_first_full_time': covered and all(
            stats['median_ms'] <= comparison['maximum_median_first_full_ms'] for stats in distributions.values()),
        'startup_increase_within_limit': covered and medians['startup_increase_ms'] <= comparison['maximum_median_startup_increase_ms'],
    }
    return {'paired_medians': medians, 'predictions': predictions, 'first_full_distributions': distributions}


def summarize_preparation_timing(study, samples, quantum, rate):
    settings = study['preparation_timing']
    budget, step = 1000 * quantum / rate, settings['clock_step_ms']
    small, large = sorted(study['block_frames_by_condition'], key=study['block_frames_by_condition'].get)
    covered = set(samples) == {small, large} and all(len(group) == len(study['condition_order']) for group in samples.values())
    summaries = {}
    for condition, trials in samples.items():
        summaries[condition] = {}
        for column, label in enumerate(('wasm', 'process')):
            first = np.array([series[column][0] for series in trials.values()])
            later = np.concatenate([series[column][1:] for series in trials.values()])
            summaries[condition][label] = {'first': duration_stats(first, budget, step),
                                          'later': duration_stats(later, budget, step)}
    paired_increase = None
    if covered:
        paired_increase = float(np.median([samples[large][p][0][1:].mean() - samples[small][p][0][1:].mean()
                                          for p in samples[small]]))
    probe = [series[0] for trials in samples.values() for series in trials.values()]
    first_at_least_later = sum(bool(x[0] >= np.median(x[1:])) for x in probe)
    predictions = {
        'longer_later_wasm_calls_at_256': covered and paired_increase >= settings['minimum_paired_later_mean_increase_ms'],
        'first_at_least_later_median': covered and first_at_least_later / len(probe) >= settings['minimum_first_at_least_later_median_fraction'],
        'bounded_later_overruns': covered and all(
            summaries[key]['process']['later']['over_budget_lower_bound'] / summaries[key]['process']['later']['count']
            <= limit for key, limit in settings['maximum_later_over_budget_lower_bound_fraction'].items()),
    }
    return {'distributions': summaries, 'paired_median_later_wasm_mean_increase_ms': paired_increase,
            'first_wasm_at_least_later_median': first_at_least_later}, predictions
