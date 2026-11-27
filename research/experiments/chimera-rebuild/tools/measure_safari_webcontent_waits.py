"""Safariの描画スレッドの待機区間を、Workletと呼び出し元に照合する。"""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_output_notifications import WAIT, export_inputs, read_json, read_syscalls
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/worklet-safari-song-webcontent-waits.json'
CONDITION_WAIT = 'BSC_psynch_cvwait'
CONDITION_SIGNAL = 'BSC_psynch_cvsignal'


def element_id(element):
    return element.get('ref', element.get('id'))


def read_stacks(path, keys):
    if not keys:
        return {}
    images, frames, stacks = {}, {}, {}
    for event, element in ElementTree.iterparse(path, events=('start', 'end')):
        if event == 'start' and element.tag == 'node':
            node = element
        if event != 'end':
            continue
        identity = element.get('id')
        if element.tag == 'binary' and identity is not None:
            images[identity] = (element.get('name'), element.get('UUID'), element.get('load-addr'))
        elif element.tag == 'frame' and identity is not None:
            binary = element.find('binary')
            frames[identity] = (element.get('name'), element.get('addr'), element_id(binary) if binary is not None else None)
        elif element.tag == 'backtrace' and identity in keys:
            stacks[identity] = [element_id(frame) for frame in element.findall('frame')]
        elif element.tag == 'row':
            node.remove(element)
            if keys <= stacks.keys():
                break

    def unpack(identity):
        symbol, addr, binary = frames.get(identity, (None, None, None))
        image, uuid, load = images.get(binary, (None, None, None))
        return {'symbol': symbol, 'image': image, 'image_uuid': uuid,
                'image_offset': hex(int(addr, 16) - int(load, 16)) if addr and load else None}

    return {identity: [unpack(frame) for frame in stack] for identity, stack in stacks.items()}


def overlap(row, lower, upper):
    return max(0, min(row['end_ns'], upper) - max(row['start_ns'], lower))


def spans_for_window(ends, condition, lower, upper):
    gaps = [(a, b) for a, b in zip(ends, ends[1:]) if a < upper and b > lower]
    start, end = max(gaps, key=lambda pair: pair[1] - pair[0]) if gaps else (None, None)
    waits = [row for row in condition if overlap(row, lower, upper)]
    within_gap = [row for row in waits if start is not None and start <= row['start_ns'] <= row['end_ns'] <= end]
    return {'mach_completions': sum(lower <= time < upper for time in ends), 'longest_mach_gap_ns': [start, end],
            'maximum_mach_gap_ms': (end - start) / 1e6 if start is not None else None,
            'mach_gaps_at_most_100_us': sum(lower <= a < b < upper and b - a <= 100_000 for a, b in gaps),
            'condition_wait_count': len(waits),
            'condition_wait_inside_window_ms': sum(overlap(row, lower, upper) for row in waits) / 1e6,
            'longest_condition_inside_gap': max(within_gap, key=lambda row: row['end_ns'] - row['start_ns'], default=None)}


def analyze(path, window_bounds, pid, minimum):
    _, threads = read_syscalls(path, None, set(), web_pid=pid, retain_wait_stack_ids=True)
    proxies = [row for row in threads if row['role'] == 'proxy']
    worklets = [row for row in threads if row['role'] == 'worklet']
    separate_threads = (len(proxies) == len(worklets) == 1 and proxies[0]['tid'] != worklets[0]['tid'])
    result = {'webcontent_pid': pid, 'window_bounds_ns': window_bounds, 'separate_threads': separate_threads,
              'threads': [{key: val for key, val in row.items() if key != 'events'} for row in threads]}
    if not separate_threads:
        return result
    proxy, worklet = proxies[0], worklets[0]
    ends = sorted(row['end_ns'] for row in proxy['events'] if row['name'] == WAIT and row['return'] == 0)
    conditions = [row for row in proxy['events'] if row['name'] == CONDITION_WAIT and row['return'] == 0]
    stats = {window: spans_for_window(ends, conditions, *bounds) for window, bounds in window_bounds.items()}
    prep_start, prep_end = window_bounds['preparation']
    preparation = stats['preparation']
    long_wait = preparation['longest_condition_inside_gap']
    nearby_signals = []
    if long_wait is not None:
        nearby_signals = [row for row in worklet['events'] if row['name'] == CONDITION_SIGNAL
                          and abs(row['end_ns'] - long_wait['end_ns']) <= 1_000_000]
    longest = [val['longest_condition_inside_gap'] for val in stats.values()]
    keys = {row['stack_id'] for row in nearby_signals + longest if row and row['stack_id'] is not None}
    stacks = read_stacks(path, keys)
    for row in nearby_signals + longest:
        if row is not None:
            row['stack'] = stacks.get(row['stack_id'], [])

    completed_wait = None
    if long_wait is not None:
        address = long_wait['condition_address']
        shared = any((frame['symbol'] or '').startswith('WebCore::SharedAudioDestination::sharedRender(')
                     for frame in long_wait['stack'])
        matching_signals = [row for row in nearby_signals if address and row['condition_address'] == address
                            and long_wait['start_ns'] <= row['start_ns'] <= long_wait['end_ns']
                            and any(frame['symbol'] == 'WTF::BinarySemaphore::signal()' for frame in row['stack'])]
        if shared and matching_signals:
            signal = max(matching_signals, key=lambda row: row['start_ns'])
            completed_wait = {'wait_duration_ms': (long_wait['end_ns'] - long_wait['start_ns']) / 1e6,
                              'minimum_overlap_with_preparation_ms': overlap(long_wait, prep_start + 1_000_000,
                                                                             prep_end - 1_000_000) / 1e6,
                              'signal_to_wait_return_us': (long_wait['end_ns'] - signal['start_ns']) / 1e3,
                              'same_address_signals': len(matching_signals)}

    window_count = all(stats[k]['mach_completions'] >= minimum for k in ('baseline', 'preparation', 'post'))
    bracketed = (bool(ends) and ends[0] <= window_bounds['baseline'][0] and ends[-1] >= window_bounds['post'][1])
    a, b = preparation['longest_mach_gap_ns']
    interrupted = (bracketed and stats['baseline']['mach_completions'] >= minimum and stats['post']['mach_completions'] >= minimum
                   and a is not None and a <= prep_start and b >= prep_end and long_wait is not None)
    result.update(windows=stats, mach_completion_span_ns=[ends[0], ends[-1]] if ends else None,
                  registered_minimum_in_all_windows=window_count,
                  covered_preparation=bracketed and (window_count or interrupted), interrupted_preparation=interrupted,
                  completed_wait_and_signal=completed_wait,
                  worklet_signals_near_end_of_longest_wait=nearby_signals)
    return result


def frame_matches(reference, sample):
    ref_wait, trial_wait = [val.get('windows', {}).get('preparation', {}).get('longest_condition_inside_gap')
                            for val in (reference, sample)]
    if not ref_wait or not trial_wait:
        return []
    expected = {(frame['image_uuid'], frame['image_offset']) for frame in ref_wait['stack']
                if frame['image_uuid'] and frame['image_offset'] is not None}
    return [frame for frame in trial_wait['stack'] if (frame['image_uuid'], frame['image_offset']) in expected]


def measure(study, captures, reference, completed_wait_check, artifacts, execute):
    checks, registered_checks, results, predictions = {}, {}, {}, {}
    minimum = study['minimum_waits_per_window']
    baseline = analyze(*reference, minimum)
    for name, trials in captures.items():
        group = results[name] = {}
        for label, (bundle, browser, item) in trials.items():
            with TemporaryDirectory(dir=artifacts) as tmp:
                toc, _, path = export_inputs(bundle, Path(tmp), False, execute)
                origin = datetime.fromisoformat(ElementTree.parse(toc).findtext('.//start-date')).timestamp() * 1000
                begin = round((browser['scoreConstruction']['startedAtEpochMs'] - origin) * 1e6)
                end = round((browser.get('scorePreparation', browser['scoreConstruction'])['finishedAtEpochMs'] - origin) * 1e6)
                bounds = {'baseline': [begin - 90_000_000, begin - 10_000_000], 'preparation': [begin, end],
                          'post': [end + 10_000_000, end + 90_000_000]}
                result = analyze(path, bounds, item['trace_bridge']['webcontent_attachment']['pid'], minimum)
            result['matching_frames_from_saved_split'] = frame_matches(baseline, result)
            result['graph_maximum_ms'] = item['marker']['preparation_window_max_gap_ms']
            group[label] = result
            registered_checks[f'{name}/{label}/covered_preparation'] = result.get('covered_preparation', False)
            checks[f'{name}/{label}/completed_wait_identified'] = bool(result.get('completed_wait_and_signal'))
        bulk, split = group['pair-1-bulk'], group['pair-1-split']
        witness = bulk.get('completed_wait_and_signal')
        predictions[name] = {'graph_gap_reduction': bulk['graph_maximum_ms'] - split['graph_maximum_ms']
                             >= study['minimum_graph_gap_reduction_ms'],
                             'bulk_proxy_wake_gap_within_limit': bulk['windows']['preparation']['maximum_mach_gap_ms']
                             <= study['maximum_proxy_wake_gap_ms'] if bulk.get('covered_preparation') else None,
                             'bulk_completed_wait_exceeds_predicted_limit': witness['minimum_overlap_with_preparation_ms']
                             > study['maximum_proxy_wake_gap_ms'] if witness else None}
    evidence = {'checks': checks if completed_wait_check else registered_checks, 'registered_checks': registered_checks,
                'predictions': predictions, 'reference_split': baseline, 'captures': results}
    (artifacts / 'waits.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture', nargs='+')
    parser.add_argument('--completed-wait-check', action='store_true', help='同じ条件変数の完了済み待機と通知を照合する')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    paths = [CASE, Path(__file__).resolve(), *[WORKSPACE / 'tools' / f'{name}.py' for name in (
        'measure_safari_output_notifications', 'filter_worklet_audioipc_syscalls', 'measure_uniform_tube')]]

    previous = run_manifest(study['reference_capture'], 'worklet-safari-song-output-notification', revision)
    previous_analysis = run_manifest(study['reference_analysis'], 'worklet-safari-song-output-notification-analysis', revision)
    previous_xml = verified_path(previous, 'artifacts/pair-1-split/syscall.xml')
    previous_summary = verified_path(previous_analysis, 'summary.json')
    paths.extend([previous[0] / 'manifest.json', previous_analysis[0] / 'manifest.json', previous_xml, previous_summary])
    saved = read_json(previous_summary)['captures'][study['reference_capture']]['pair-1-split']
    proxy, = [row for row in saved['thread_identities'] if row['role'] == 'proxy']
    reference = (previous_xml, saved['window_bounds_ns'], proxy['pid'])

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
                parser.error(f'{name}/{label} の歌唱・先行信号・採取を確認できません')
            exports = f'artifacts/{label}/audio-system.trace/'
            paths.extend(verified_path(run, row['path']) for row in run[1]['outputs'] if row['path'].startswith(exports))
            bundle = Path(run[1]['storage']['artifacts_root']) / label / 'audio-system.trace'
            browser = verified_path(run, f'artifacts/{label}/browser.json')
            paths.append(browser)
            trials[label] = bundle, read_json(browser), item
    details = {'case_id': study['id'] + '-analysis', 'capture_runs': args.capture, 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'completed_wait_check': args.completed_wait_check}
    return record_measurement(args.run_id, CASE, paths, details,
                              lambda artifacts, execute: measure(study, captures, reference, args.completed_wait_check, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
