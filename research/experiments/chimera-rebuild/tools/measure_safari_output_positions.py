"""Safariが公開する出力位置の進みを、歌唱準備と描画スレッドに照合する。"""

import argparse
from datetime import datetime
from itertools import groupby
from math import isfinite
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import NamedTuple
from xml.etree import ElementTree

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_output_notifications import WAIT, export_inputs, read_json, read_syscalls
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/worklet-safari-song-output-position.json'


class Reading(NamedTuple):
    before: float
    after: float
    graph_before: float
    graph_after: float
    output: float
    published_at: float

    @property
    def unclamped(self):
        return self.output + 0.5 < min(self.graph_before, self.graph_after)


def valid_steps(readings, quantum):
    for a, b in zip(readings, readings[1:]):
        if a.unclamped and b.unclamped and b.published_at > a.published_at and b.output > a.output:
            delta = round(b.output - a.output)
            aligned = all(abs(x - round(x)) < 1e-5 for x in (a.output, b.output)) and delta % quantum == 0
            yield a, b, delta, aligned


def grouped_recovery_step(readings, duration, quantum):
    publications = []
    for stamp, rows in groupby(readings, key=lambda row: row.published_at):
        exposed = [r for r in rows if r.unclamped]
        unique = {r.output for r in exposed}
        publications.append((stamp, exposed[0] if len(unique) == 1 else None))
    largest = None
    for (_, a), (_, b) in zip(publications, publications[1:]):
        if a is None or b is None or not 0 <= b.before <= duration + 90:
            continue
        for step in valid_steps((a, b), quantum):
            if largest is None or step[2] > largest[2]:
                largest = step
    return step_in_summary(largest)


def step_in_summary(step):
    if step is None:
        return None
    a, b, frames, aligned = step
    return {'frames': frames, 'quantum_aligned': aligned, 'published_ms_from_preparation': [a.published_at, b.published_at],
            'read_ms_from_preparation': [a.before, b.before], 'positions_frames': [round(a.output), round(b.output)],
            'graph_frames_at_read': [round(a.graph_before), round(b.graph_before)]}


def same_position_duration(readings, end):
    intervals = []
    for _, group in groupby(readings, key=lambda row: (row.output, row.published_at)):
        first = last = next(group)
        for reading in group:
            last = reading
        start, finish = max(0, first.after), min(end, last.before)
        if start < finish:
            intervals.append((finish - start, start, finish))
    return max(intervals, default=(0, None, None))


def summarize_clock(study, clock, begin, duration):
    checks = {'supported_rate': bool(clock and clock['supported'] and clock['sample_rate_hz'] == study['sample_rate_hz'])}
    if not checks['supported_rate']:
        return checks, {'sample_count': len(clock['samples']) if clock else 0}
    rate = clock['sample_rate_hz']
    offset = clock['time_origin_epoch_ms'] - begin
    readings = [Reading(a + offset, b + offset, g0 * rate, g1 * rate, out * rate, stamp + offset)
                for a, b, g0, g1, out, stamp in clock['samples'] if stamp > 0]
    ordered = (bool(readings) and all(all(isfinite(x) for x in r) and r.before <= r.after for r in readings)
               and all(a.after <= b.before for a, b in zip(readings, readings[1:])))
    checks['ordered_finite_readings'] = ordered
    if not ordered:
        return checks, {'sample_count': len(readings)}
    windows = {'baseline': (-90, -10), 'preparation': (0, duration), 'post': (duration + 10, duration + 90)}
    steps = list(valid_steps(readings, study['quantum_frames']))
    metrics = {}
    for label, (lower, upper) in windows.items():
        inside = [r for r in readings if lower <= r.before < upper]
        gaps = [b.before - a.before for a, b in zip(readings, readings[1:]) if a.before <= upper and b.before >= lower]
        observed_steps = [step for step in steps if lower <= step[0].before and step[1].before < upper]
        metrics[label] = {'readings': len(inside), 'unclamped_readings': sum(r.unclamped for r in inside),
                          'maximum_read_gap_ms': max(gaps, default=None), 'maximum_call_ms': max((r.after - r.before for r in inside), default=None),
                          'eligible_steps': len(observed_steps), 'aligned_steps': sum(s[3] for s in observed_steps),
                          'largest_step': step_in_summary(max(observed_steps, key=lambda step: step[2], default=None))}
    checks['sampling_windows_covered'] = (readings[0].before <= windows['baseline'][0] and readings[-1].before >= windows['post'][1]
        and all(m['readings'] and m['maximum_read_gap_ms'] <= study['maximum_sampling_gap_ms']
                and m['maximum_call_ms'] <= study['maximum_clock_lock_call_ms'] for m in metrics.values()))
    base = metrics['baseline']
    checks['baseline_steps_calibrated'] = (base['readings'] >= study['minimum_baseline_readings']
        and base['aligned_steps'] == base['eligible_steps'] >= study['minimum_baseline_unclamped_steps'])
    recovery = [step for step in steps if 0 <= step[1].before <= windows['post'][1]]
    unchanged, a, b = same_position_duration(readings, duration)
    return checks, {'sample_count': len(readings), 'windows': metrics,
                    'unchanged_position_in_preparation_ms': unchanged, 'unchanged_bounds_ms_from_preparation': [a, b],
                    'largest_recovery_step': step_in_summary(max(recovery, key=lambda step: step[2], default=None)),
                    'largest_grouped_recovery_step': grouped_recovery_step(readings, duration, study['quantum_frames'])}


def compare_trace(bundle, browser, item, marker_timeline, step, execute, folder):
    with TemporaryDirectory(dir=folder) as tmp:
        toc, _, path = export_inputs(bundle, Path(tmp), False, execute)
        origin = datetime.fromisoformat(ElementTree.parse(toc).findtext('.//start-date')).timestamp() * 1000
        web_pid = item['trace_bridge']['webcontent_attachment']['pid']
        _, threads = read_syscalls(path, None, set(), web_pid=web_pid)
    proxy = [row for row in threads if row['role'] == 'proxy']
    worklet = [row for row in threads if row['role'] == 'worklet']
    same_context_threads = len(proxy) == len(worklet) == 1 and proxy[0]['tid'] != worklet[0]['tid']
    result = {'matched_webcontent_threads': same_context_threads, 'webcontent_pid': web_pid}
    if same_context_threads and step:
        begin = browser['scoreConstruction']['startedAtEpochMs']
        offset = origin - begin
        returns = sorted(row['end_ns'] / 1e6 + offset for row in proxy[0]['events'] if row['name'] == WAIT and row['return'] == 0)
        first, last = step['published_ms_from_preparation']
        marker = [t - begin for t in marker_timeline['callbackEpochMs']]
        result.update(web_proxy_span_ms_from_preparation=[returns[0], returns[-1]] if returns else None,
                      mach_returns_between_published_times=sum(first <= x < last for x in returns),
                      mach_returns_within_1ms_of_published_range=[x - first for x in returns if first - 1 <= x < last + 1],
                      graph_callbacks_between_published_times=sum(first <= x < last for x in marker),
                      graph_callback_count_range_with_1ms_boundary_margin=[
                          sum(first + 1 <= x < last - 1 for x in marker),
                          sum(first - 1 <= x < last + 1 for x in marker)])
    return result


def analyze(study, captures, prior, publication_groups, artifacts, execute):
    checks, registered_checks, reports, predictions = {}, {}, {}, {}
    key = 'largest_grouped_recovery_step' if publication_groups else 'largest_recovery_step'
    for name, trials in captures.items():
        results = reports[name] = {}
        for label, (bundle, output_clock, marker, browser, item) in trials.items():
            begin = browser['scoreConstruction']['startedAtEpochMs']
            end = browser.get('scorePreparation', browser['scoreConstruction'])['finishedAtEpochMs']
            local, result = summarize_clock(study, output_clock, begin, end - begin)
            result['native'] = compare_trace(bundle, browser, item, marker, result.get(key), execute, artifacts)
            local['webcontent_threads_identified'] = result['native']['matched_webcontent_threads']
            result['graph_maximum_gap_ms'] = item['marker']['preparation_window_max_gap_ms']
            result['preparation_ms'] = end - begin
            result['sampling_checks'] = local
            registered_checks.update({f'{name}/{label}/{check}': bool(value) for check, value in local.items()})
            checks.update({f'{name}/{label}/{check}': bool(value) for check, value in local.items()
                           if check != 'baseline_steps_calibrated'})
            if label.endswith('-bulk'):
                checks[f'{name}/{label}/grouped_positions_observed'] = bool(result.get(key) and result[key]['quantum_aligned'])
            results[label] = result
        bulk, split = results['pair-1-bulk'], results['pair-1-split']
        eligible = all(all(t['sampling_checks'].values()) for t in results.values())
        a, b = bulk.get('largest_recovery_step'), split.get('largest_recovery_step')
        predictions[name] = {
            'bulk_stops_publishing': bulk['unchanged_position_in_preparation_ms'] >= study['minimum_bulk_unchanged_ms']
            if eligible else None,
            'bulk_catchup_has_large_unclamped_jump': (a['quantum_aligned'] and b['quantum_aligned']
                and a['frames'] >= study['minimum_bulk_jump_frames'] and a['frames'] >= b['frames'] * study['minimum_bulk_to_split_jump_ratio'])
            if eligible and a and b else None,
        }
        if publication_groups:
            sampled = all(all(value for check, value in t['sampling_checks'].items() if check != 'baseline_steps_calibrated')
                          for t in results.values())
            a, b = bulk.get(key), split.get(key)
            predictions[name].update(
                bulk_public_plateau_observed=(bulk['unchanged_position_in_preparation_ms'] >= study['minimum_bulk_unchanged_ms'])
                if sampled else None,
                bulk_grouped_jump_above_minimum=(a['quantum_aligned'] and a['frames'] >= study['minimum_bulk_jump_frames'])
                if sampled and a else None,
                grouped_paired_ratio=(a['frames'] / b['frames']) if sampled and a and b else None,
            )
    return {'checks': checks if publication_groups else registered_checks, 'registered_checks': registered_checks,
            'predictions': predictions, 'captures': reports, 'prior_graph_maximum_gap_ms': prior}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture', nargs='+')
    parser.add_argument('--publication-groups', action='store_true', help='同じ公開時刻内の切り詰めのない値を照合する')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    paths = [CASE, Path(__file__).resolve(), *[WORKSPACE / 'tools' / f'{name}.py' for name in (
        'measure_safari_output_notifications', 'filter_worklet_audioipc_syscalls', 'measure_uniform_tube')]]
    prior = {}
    for name in study['prior_wait_runs']:
        run = run_manifest(name, 'worklet-safari-song-webcontent-waits', revision)
        summary_path = verified_path(run, 'summary.json')
        paths.extend([run[0] / 'manifest.json', summary_path])
        prior[name] = {t['condition']: t['marker']['preparation_window_max_gap_ms'] for t in read_json(summary_path)['trials'].values()}

    captures = {}
    for name in args.capture:
        run = run_manifest(name, study['id'], revision)
        summary = verified_path(run, 'summary.json')
        paths.extend([run[0] / 'manifest.json', summary])
        report = read_json(summary)
        trials = captures[name] = {}
        for label, item in report['trials'].items():
            if not all(report['checks'].get(f'{label}/{key}') for key in (
                'pcm_bits', 'marker_pcm_bits', 'observed_state_and_plan', 'preparation_sequence', 'trace_recorded'
            )):
                parser.error(f'{name}/{label} の歌唱・先行音・採取を確認できません')
            exports = f'artifacts/{label}/audio-system.trace/'
            paths.extend(verified_path(run, row['path']) for row in run[1]['outputs'] if row['path'].startswith(exports))
            bundle = Path(run[1]['storage']['artifacts_root']) / label / 'audio-system.trace'
            files = [verified_path(run, f'artifacts/{label}/{f}') for f in ('output-clock.json', 'marker.json', 'browser.json')]
            paths.extend(files)
            trials[label] = bundle, *map(read_json, files), item
    details = {'case_id': study['id'] + '-analysis', 'capture_runs': args.capture, 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'publication_groups': args.publication_groups}
    return record_measurement(args.run_id, CASE, paths, details,
                              lambda artifacts, execute: analyze(study, captures, prior, args.publication_groups, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
