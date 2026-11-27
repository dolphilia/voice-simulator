"""WorkletのIPC待ちをFirefoxの親メインスレッドのスタックで観測する。"""

import argparse
from bisect import bisect_right
from collections import defaultdict
from functools import cache
import json
import os
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import sys

import measure_worklet_song_firefox_ipc_queue as queue


song = queue.song
CASE = song.WORKSPACE / 'cases/worklet-song-firefox-ipc-stack.json'
ADDRESS = re.compile(r'0x[0-9a-f]+', re.IGNORECASE | re.ASCII)


def column(row, schema, name):
    index = schema.get(name, len(row))
    return row[index] if index < len(row) else None


def stack_reader(profile, thread):
    frames = thread['frameTable']
    stacks = thread['stackTable']
    strings = thread['stringTable']
    categories = profile['meta']['categories']
    libs = sorted(profile['libs'], key=lambda lib: lib['start'])
    starts = [lib['start'] for lib in libs]

    @cache
    def frame(index):
        row = frames['data'][index]
        schema = frames['schema']
        location = strings[row[schema['location']]]
        number = column(row, schema, 'category')
        category = categories[number]['name'] if number is not None else None
        sub_index = column(row, schema, 'subcategory')
        subcategory = categories[number]['subcategories'][sub_index] if number is not None and sub_index is not None else None
        result = {'location': location, 'category': category, 'subcategory': subcategory}
        if ADDRESS.fullmatch(location):
            address = int(location, 16)
            lib_idx = bisect_right(starts, address) - 1
            if lib_idx >= 0 and address < libs[lib_idx]['end']:
                lib = libs[lib_idx]
                result.update({'library': lib['name'], 'debug_id': lib.get('breakpadId'),
                               'offset': address - lib['start'] + lib['offset']})
            result['kind'] = 'native_address'
        elif location == '(root)':
            result['kind'] = 'root'
        else:
            result['kind'] = 'named'
        return result

    @cache
    def stack(index):
        if index is None:
            return ()
        row = stacks['data'][index]
        prefix = column(row, stacks['schema'], 'prefix')
        return (*stack(prefix), frame(row[stacks['schema']['frame']]))

    return stack


def summarize_window(samples, cpu_scale, read_stack, start, stop, spec):
    totals = defaultdict(float)
    categories = defaultdict(float)
    libraries = defaultdict(float)
    weights = defaultdict(float)
    examples = {}
    observer_ms = browser_ms = stack_ms = cpu_ms = covered = 0.0
    count = 0
    schema = samples['schema']
    for previous, row in zip(samples['data'], samples['data'][1:]):
        begin, end = (r[schema['time']] for r in (previous, row))
        delta = column(row, schema, 'threadCPUDelta')
        if not start <= begin < end <= stop or delta is None:
            continue
        weight = delta / cpu_scale
        covered += end - begin
        cpu_ms += weight
        stack_id = column(row, schema, 'stack')
        frames = read_stack(stack_id)
        named = [frame for frame in frames if frame['kind'] == 'named']
        native = [frame for frame in frames if frame['kind'] == 'native_address']
        if not (named or native):
            continue
        count += 1
        stack_ms += end - begin
        leaf = named[-1] if named else None
        categories[leaf['category'] or '分類なし' if leaf else '名前なし'] += weight
        totals[leaf['location'] if leaf else '名前なし'] += weight
        if native:
            libraries[native[-1].get('library', '対応するライブラリなし')] += weight
        activity = any(frame['category'] in spec['browser_activity_categories'] for frame in frames)
        browser_js = any(any(prefix in frame['location'] for prefix in spec['browser_js_origin_prefixes'])
                         and frame['category'] == 'JavaScript' for frame in named)
        if activity or browser_js:
            browser_ms += weight
        if any(spec['network_observer_origin'] in frame['location'] for frame in named):
            observer_ms += weight
        weights[stack_id] += weight
        examples[stack_id] = frames
    return {'interval_ms': [start, stop], 'cpu_sample_covered_ms': covered, 'stack_sample_covered_ms': stack_ms,
            'sampled_cpu_ms': cpu_ms, 'sample_count_with_stack': count, 'browser_activity_weight_ms': browser_ms,
            'browser_activity_fraction': browser_ms / cpu_ms if cpu_ms else None,
            'network_observer_weight_ms': observer_ms,
            'network_observer_fraction': observer_ms / cpu_ms if cpu_ms else None,
            'cpu_weight_by_last_named_category_ms': sorted(categories.items(), key=lambda x: (-x[1], x[0])),
            'cpu_weight_by_last_named_frame_ms': sorted(totals.items(), key=lambda x: (-x[1], x[0]))[:20],
            'cpu_weight_by_last_address_library_ms': sorted(libraries.items(), key=lambda x: (-x[1], x[0]))[:12],
            'heaviest_stacks': [{'cpu_weight_ms': weights[key], 'frames': examples[key]}
                                for key in sorted(weights, key=lambda key: (-weights[key], key))[:8]]}


def analyze(profile, previous, spec, asset_timing=None):
    info = previous['IPC_message']
    thread, _ = queue.markers_on(profile, info['parent_pid'], 'GeckoMain')
    unit = profile['meta'].get('sampleUnits', {}).get('threadCPUDelta')
    scale = {'ns': 1_000_000, 'µs': 1000, 'ms': 1}.get(unit)
    features = profile['meta']['configuration']['features']
    confirmed = all(feature in features for feature in spec['enable_features'])
    checks = {'features_active': confirmed and all(feature not in features for feature in spec['disable_features'])}
    if 'queue_to_handler_ms' not in previous:
        return checks, {'reason': '対象の投入を識別できない', 'profile_features': features}
    if scale is None:
        return checks, {'reason': 'CPU時間の単位を取得できない', 'profile_features': features}
    start = previous['queue_candidates'][0][1]
    stop = info['handled_ms']
    width = spec['context_window_ms']
    reader = stack_reader(profile, thread)
    windows = {key: summarize_window(thread['samples'], scale, reader, lower, upper, spec)
               for key, lower, upper in (('before', start - width, start), ('queued', start, stop), ('after', stop, stop + width))}
    if asset_timing is not None:
        begin, end = (asset_timing[key] - profile['meta']['startTime'] for key in ('startedAtEpochMs', 'finishedAtEpochMs'))
        windows['asset_body_read'] = summarize_window(thread['samples'], scale, reader, begin, end, spec)
        checks['asset_timing_is_ordered'] = begin <= end
        if asset_timing['deferred']:
            checks['deferred_body_read_follows_ipc'] = begin >= stop - spec['body_read_control']['cross_clock_tolerance_ms']
    independent = queue.sampled_cpu(profile, thread, start, stop)
    active = windows['queued']
    checks['stack_cpu_sum_matches'] = abs(active['sampled_cpu_ms'] - (independent['cpu_ms'] or 0.0)) <= 1e-9
    duration = stop - start
    eligible = (confirmed and duration >= 100 and active['stack_sample_covered_ms'] >= duration * spec['minimum_long_window_coverage']
                and active['browser_activity_fraction'] is not None)
    return checks, {'profile_features': features, 'queue_to_handler_ms': duration, 'windows': windows,
                    'long_window_has_coverage': eligible, 'prediction_met': (
                        active['browser_activity_fraction'] >= spec['minimum_browser_activity_fraction'] if eligible else None)}


def analyze_browser_trial(profile_path, run_path, spec, order, prior_queue=None):
    profile = queue.read_profile(profile_path)
    browser_run = song.wasm.read_json(run_path)
    checks = {}
    if prior_queue is None:
        request = queue.http.only(browser_run['workletRequests'], 'WorkletのHTTP要求')
        http_spec = song.wasm.read_json(queue.http.CASE)['measurement']
        checks, channel = queue.http.compare_channel(profile, request, http_spec)
        prior_queue = queue.analyze(profile, channel, song.wasm.read_json(queue.CASE)['measurement'])
    checks.update({'IPC_endpoints': True})
    stack_checks, stacks = analyze(profile, prior_queue, spec, browser_run.get('assetEvidenceTiming'))
    checks.update(stack_checks)
    if order != 'serial':
        stacks['prediction_met'] = None
    return checks, {'queue': prior_queue, 'stacks': stacks, 'asset_evidence_timing': browser_run.get('assetEvidenceTiming')}


def measure(study, fixed, live, source, reference, comparison, archived, deferred, artifacts, execute, bun):
    spec = study['measurement']
    prior = song.wasm.read_json(queue.CASE)
    prior['measurement']['condition_order'] = spec['condition_order']

    def sample_stacks(command, cwd=song.WORKSPACE, stdout=None):
        adjusted = []
        for arg in command:
            if arg.startswith('MOZ_PROFILER_STARTUP_FEATURES='):
                features = arg.split('=', 1)[1].split(',')
                features = [f for f in features if f not in spec['disable_features']] + spec['enable_features']
                arg = 'MOZ_PROFILER_STARTUP_FEATURES=' + ','.join(features)
            if arg.startswith('MOZ_PROFILER_STARTUP_FILTERS='):
                arg = 'MOZ_PROFILER_STARTUP_FILTERS=' + ','.join(spec['thread_filters'])
            adjusted.append(arg)
        return execute(adjusted, cwd=cwd, stdout=stdout)

    options = {'record_asset_evidence_timing': True, **({} if deferred else {'defer_asset_evidence': False})}
    live = {**live, 'measurement': {**live['measurement'], **options}}
    captured = queue.measure(prior, fixed, live, source, reference, (), artifacts, sample_stacks, bun)
    checks = captured['checks']
    for trial in captured['trials']:
        label = trial['trial']
        if 'queue' not in trial:
            continue
        try:
            folder = artifacts / label
            stack_checks, evidence = analyze_browser_trial(folder / 'firefox-profile.json.gz',
                folder / 'browser-run.json', spec, trial['order'], trial['queue'])
            trial.update(evidence)
            checks.update({f'{label}/stack/{name}': value for name, value in stack_checks.items()})
        except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
            checks[f'{label}/stack/analysis_completed'] = False
            trial['stack_error'] = str(error)
    recovered = []
    for label, order, profile_path, run_path in archived:
        try:
            local, evidence = analyze_browser_trial(profile_path, run_path, spec, order)
            recovered.append({'trial': label, 'order': order, **evidence})
            checks.update({f'archived/{label}/{name}': value for name, value in local.items()})
        except (OSError, EOFError, KeyError, TypeError, ValueError) as error:
            checks[f'archived/{label}/analysis_completed'] = False
            recovered.append({'trial': label, 'order': order, 'error': str(error)})
    result = {'checks': checks, 'trials': captured['trials'], 'reanalyzed_reference_trials': recovered,
              'comparison_run': comparison['run_id'], 'deferred': deferred}
    if deferred:
        before = [t['stacks']['queue_to_handler_ms'] for t in recovered if t['order'] == 'serial' and 'queue_to_handler_ms' in t.get('stacks', {})]
        after = [t['stacks']['queue_to_handler_ms'] for t in captured['trials'] if t['order'] == 'serial'
                 and 'queue_to_handler_ms' in t.get('stacks', {})]
        settings = spec['body_read_control']
        if len(before) == len(after) == len(spec['condition_order']):
            reduction = median(before) - median(after)
            result['body_read_control'] = {'reference_serial_ms': before, 'deferred_serial_ms': after,
                'serial_median_reduction_ms': reduction,
                'serial_reduction_prediction_met': reduction >= settings['minimum_serial_median_reduction_ms'],
                'deferred_wait_prediction_met': all(
                    'queue_to_handler_ms' in t.get('stacks', {}) and t['stacks']['queue_to_handler_ms'] <= settings['maximum_deferred_queue_ms']
                    for t in captured['trials'])}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--defer-asset-evidence', action='store_true', help='応答本文のハッシュ検証を歌唱完了後に行う')
    args = parser.parse_args()
    study, fixed, live = (song.wasm.read_json(p) for p in (CASE, song.CASE, song.LIVE_CASE))
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流または歌唱のケースが一致しません')
    prior = song.run_manifest(study['reference_run'], queue.registration.cross.CASE.stem, revision)
    compared = song.run_manifest(study['queue_comparison_run'], queue.CASE.stem, revision)
    if prior[1]['status'] != 'pass' or compared[1]['status'] != 'pass' or compared[1]['reference_run'] != prior[0].name:
        parser.error('音声またはIPCの保存済み比較が合格条件を満たしません')
    reference = {name: song.verified_path(prior, name) for name in queue.http.REFERENCE}
    compared_summary = song.verified_path(compared, 'summary.json')
    inputs = [CASE, queue.CASE, queue.registration.CASE, queue.http.CASE, song.CASE, song.LIVE_CASE, source, prior[0] / 'manifest.json',
              compared[0] / 'manifest.json', compared_summary, *reference.values(), Path(__file__).resolve(),
              *song.web_sources(), *song.shared.candidate_sources()]
    inputs.extend(Path(module.__file__) for module in (queue, queue.http, queue.registration, song, song.shared, song.wasm,
        queue.registration.cross, queue.registration.native, queue.registration.evaluation, queue.registration.evaluation.registration,
        queue.registration.evaluation.registration.startup, queue.registration.cross.clocks, queue.registration.cross.clocks.release.stored))
    archived = []
    if args.defer_asset_evidence:
        raw = song.run_manifest(study['measurement']['body_read_control']['reference_run'], CASE.stem, revision)
        previous = song.verified_path(raw, 'summary.json')
        if raw[1]['reference_run'] != prior[0].name:
            parser.error('初回採取の固定CLI基準が一致しません')
        previous_checks = song.wasm.read_json(previous)['checks']
        if not all(passed for check, passed in previous_checks.items() if check.startswith('capture/')):
            parser.error('初回採取の歌唱または資産の照合が不合格です')
        inputs.extend((raw[0] / 'manifest.json', previous))
        for t in song.wasm.read_json(previous)['trials']:
            label = t['trial']
            paths = [song.verified_path(raw, f'artifacts/{label}/{name}')
                     for name in ('firefox-profile.json.gz', 'browser-run.json')]
            inputs.extend(paths)
            archived.append((label, t['order'], *paths))
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    details = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
               'queue_comparison_run': compared[0].name, 'analysis_command': [sys.executable, *sys.argv],
               'analysis_directory': str(Path.cwd()), 'firefox_override': os.environ.get('CHIMERA_FIREFOX'),
               'deferred_asset_evidence': args.defer_asset_evidence}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, compared[1], archived, args.defer_asset_evidence,
                                           artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
