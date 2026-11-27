"""Firefoxの停止・再開をグラフ、cubeb、プロセスタップで比較する。"""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_coreaudio_headphone_late_attach_44100 import match_anchors
from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_firefox_headphone_response_44100 import BROWSER, CASE as RESPONSE, continuous_blocks, read_stereo
from measure_safari_headphone_context_restart_44100 import (
    CALIBRATION, DRIFT, comparison_inputs, comparison_spans, inspect_context_pcm, summarize,
)
from measure_safari_process_tap_calibration import OUTPUT_DEVICE, capture_on_output
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WEB, WORKSPACE
from measure_worklet_live_song_process_tap import NATIVE, PLIST
from measure_worklet_tsp_device_tap import capture_tap, zero_spans
from smooth_tap_marker import chip_values, find_anchor
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/firefox-headphone-context-restart-44100.json'
KEEP = CASE.with_name('firefox-headphone-context-keep-output-44100.json')
SILENT = CASE.with_name('firefox-headphone-context-silent-output-44100.json')


def cubeb_streams(folder, spec, tape, front_limit):
    for path in sorted((folder / 'cubeb').glob(f"cubeb-output-{tape['pid']}-*")):
        pcm = np.fromfile(path / 'pcm.f32le', dtype='<f4').reshape(-1, 2)
        blocks = load_blocks(path)
        for block in blocks:
            block['pcm_frame'] = block['pcm_byte_offset'] // 8
        with (path / 'format.csv').open(newline='') as stream:
            rates, = csv.DictReader(stream)
        meta = {'stream': path.name, 'pcm_frames': len(pcm), 'blocks': len(blocks),
                'sample_rates': rates, 'state': (path / 'state.txt').read_text().strip(),
                'block_widths': sorted({block['frames'] for block in blocks}),
                'first_block': blocks[0] if blocks else None, 'last_block': blocks[-1] if blocks else None}
        if len(pcm) and np.isfinite(pcm).all():
            side = (pcm[:, 0].astype(float) - pcm[:, 1]) / 2
            first = spec['anchor']['first']
            front = find_anchor(side[:front_limit], chip_values(spec['marker']), spec, first)
            tail = match_anchors(side, spec, spec, True)
            meta.update(front=front, tail=tail, before_origin=front['offset'] - first if front else None,
                        after_origin=tail.get('origin_in_pcm') if tail.get('tail_integer_advance') == 0 else None)
        yield meta, pcm, blocks


def keeper_phase(pcm, waveform, start):
    frames = np.arange(start, start + 10 * len(waveform))
    common = pcm[frames].astype(float).mean(axis=1)
    templates = waveform[(frames[None, :] + np.arange(len(waveform))[:, None]) % len(waveform)]
    return int(np.argmin(np.sum((templates - common) ** 2, axis=1)))


def clock_error_ms(rows, time, tick_ms, width, rate):
    if not rows or any(row.get(time) is None for row in rows):
        return None
    return float(np.max(np.abs(np.diff([r[time] for r in rows]) * tick_ms - 1000 * width / rate), initial=0))


def inspect_keeper(case, spec, result, tape, tap_pcm, before, after, waveform):
    options = spec['keep_output']
    silent = options['amplitude'] == 0
    checks = result['checks']
    rate, width = spec['sample_rate_hz'], case['cubeb_expected_frames']
    tick_ms = tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6
    threshold = options['maximum_request_period_error_ms']
    _, front, blocks, early, pcm = before
    _, tail, _, late, _ = after
    frame = result['comparison_resume_frame']
    cb_edges = (frame + front, frame + tail)
    rows = continuous_blocks(blocks, 'pcm_frame', 'sample_time', early['analyzed_span'][0] + front,
                             late['analyzed_span'][1] + tail, width, len(pcm)) if result['cubeb_same_stream'] else None
    error = clock_error_ms(rows, 'host_time', tick_ms, width, rate)
    checks['same_cubeb_clock_across_gap'] = bool(rows and error is not None and error <= threshold
        and all(row['stage'] == 'data' and row['timestamp_flags'] & 3 == 3 for row in rows))
    checks['cubeb_mixed_stereo_matches'] = all(
        segment['mixed_max_absolute_error'] <= options['maximum_mixed_stereo_error'] for segment in (early, late))
    if not silent:
        checks['keeper_phase_unchanged'] = result['cubeb_same_stream'] and early['keeper_phase'] == late['keeper_phase']
    seen = result['keeper_output'] = {
        'cubeb_pcm_edges': list(cb_edges), 'cubeb_maximum_host_period_error_ms': error,
        'cubeb_blocks_across_comparison': len(rows) if rows else 0,
    }
    if not result['suspend']:
        checks['cubeb_control_has_no_gap'] = cb_edges[0] == cb_edges[1]
        return
    start, end = cb_edges
    duration = 1000 * (end - start) / rate
    checks['cubeb_main_track_gap'] = (result['cubeb_same_stream'] and 0 <= start < end <= len(pcm)
        and end - start >= options['minimum_isolated_gap_frames']
        and abs(duration - result['suspended_wall_ms']) <= options['maximum_gap_duration_error_ms'])
    if checks['cubeb_main_track_gap']:
        gap = pcm[start:end]
        seen['cubeb_gap_frames'] = end - start
        if silent:
            seen['cubeb_gap_nonzero_frames'] = int(np.count_nonzero(np.any(gap != 0, axis=1)))
            checks['cubeb_gap_is_digital_zero'] = seen['cubeb_gap_nonzero_frames'] == 0
        else:
            phase = early['keeper_phase']
            expected = waveform[(np.arange(start, end) + phase) % len(waveform)]
            seen['cubeb_gap_keeper_error'] = float(np.max(np.abs(gap.astype(float) - expected[:, None])))
            checks['cubeb_gap_has_only_keeper'] = (np.array_equal(gap[:, 0], gap[:, 1])
                and seen['cubeb_gap_keeper_error'] <= options['maximum_keeper_sample_error'])
    tap_content_check = 'tap_gap_is_digital_zero' if silent else 'tap_keeper_present_across_gap'
    tap_front, tap_tail = result['tap_origins_in_pcm']
    if tap_front is None or tap_tail is None:
        checks[tap_content_check] = False
        return
    tap_width = spec['analysis']['tap_expected_frames']
    start, end = frame + tap_front, frame + tap_tail
    rows = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', start, end, tap_width, len(tap_pcm))
    error = clock_error_ms(rows, 'hostTime', tick_ms, tap_width, rate)
    checks['tap_clock_across_gap'] = error is not None and error <= threshold
    guard = options['tap_gap_guard_frames']
    window, hop = spec['analysis']['window_frames'], spec['analysis']['hop_frames']
    middle = tap_pcm[start + guard:end - guard]
    seen.update(tap_pcm_edges=[start, end], tap_maximum_host_period_error_ms=error)
    if len(middle) < window:
        checks[tap_content_check] = False
        return
    if silent:
        seen.update(tap_gap_center_frames=len(middle),
                    tap_gap_center_nonzero_frames=int(np.count_nonzero(np.any(middle != 0, axis=1))))
        checks[tap_content_check] = seen['tap_gap_center_nonzero_frames'] == 0
        return
    side = (middle[:, 0] - middle[:, 1]) / 2
    common = middle.mean(axis=1)
    windows = np.lib.stride_tricks.sliding_window_view(common, window)[::hop]
    basis = np.exp(-2j * np.pi * np.arange(window) / len(waveform))
    pilot = np.abs(windows @ basis) * 2 / (window * options['amplitude'])
    seen.update(tap_middle_maximum_side=float(np.max(np.abs(side))), tap_pilot_minimum_ratio=float(min(pilot)),
                tap_pilot_median_ratio=float(np.median(pilot)), tap_pilot_windows=len(pilot))
    checks[tap_content_check] = bool(min(pilot) >= options['minimum_tap_pilot_ratio']
        and seen['tap_middle_maximum_side'] <= options['maximum_tap_side_during_gap'])


def inspect_cubeb(folder, case, spec, fixture, result, tape, tap_pcm, waveform=None):
    checks = result['checks']
    front_limit = case.get('cubeb_front_search_end_frame', spec['attach_comparison']['front_search_end_frame'])
    streams = list(cubeb_streams(folder, spec, tape, front_limit))
    result['cubeb_streams'] = [meta for meta, _, _ in streams]
    checks['cubeb_pre_and_post_acquired'] = False
    if not (checks.get('graph_pcm_bitwise') and checks.get('context_suspended_and_resumed')):
        return
    rate, width = spec['sample_rate_hz'], case['cubeb_expected_frames']
    tick_ms = tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6
    resume = result['comparison_resume_frame']
    expected = np.column_stack((fixture, -fixture))
    chosen = {}
    for name, (lo, hi) in zip(('before', 'after'), comparison_spans(case, spec, resume), strict=True):
        candidates = []
        for meta, pcm, blocks in streams:
            origin = meta.get(f'{name}_origin')
            if origin is None or meta['state'] != 'ready' or set(map(float, meta['sample_rates'].values())) != {rate}:
                continue
            rows = continuous_blocks(blocks, 'pcm_frame', 'sample_time', lo + origin, hi + origin, width, len(pcm))
            if not (rows and all(row['stage'] == 'data' and row['timestamp_flags'] & 3 == 3 for row in rows)
                    and all(b['host_time'] > a['host_time'] for a, b in zip(rows, rows[1:]))):
                continue
            # 窓内に加えて停止位置までの描画済み範囲もビット比較する。
            boundary_lo, boundary_hi = (0, resume) if name == 'before' else (resume, len(fixture))
            start, end = max(boundary_lo, -origin), min(boundary_hi, len(pcm) - origin)
            observed = pcm[start + origin:end + origin]
            want = expected[start:end]
            mixture = {}
            if waveform is not None:
                phase = keeper_phase(pcm, waveform, lo + origin) if spec['keep_output']['amplitude'] else None
                pilot = waveform[(np.arange(start, end) + origin + (phase or 0)) % len(waveform)]
                want = want + pilot[:, None]
                max_error = np.max(np.abs(observed[lo-start:hi-start].astype(float) - want[lo-start:hi-start]))
                mixture = {'keeper_phase': phase, 'mixed_max_absolute_error': float(max_error)}
            unequal = np.flatnonzero(np.any(observed.view('<u4') != want.view('<u4'), axis=1)) + start
            segment = {
                'stream': meta['stream'], 'origin_in_pcm': origin, 'clock_blocks': len(rows),
                'analyzed_span': [lo, hi], 'compared_source_span': [start, end],
                'analyzed_bitwise_match': not bool(np.any((lo <= unequal) & (unequal < hi))),
                'differing_frames': len(unequal),
                'first_and_last_differing_frames': [int(unequal[0]), int(unequal[-1])] if len(unequal) else [],
                **mixture,
            }
            candidates.append((meta, origin, blocks, segment, pcm))
        if len(candidates) == 1:
            chosen[name] = candidates[0]
    result['cubeb_segments'] = {name: value[3] for name, value in chosen.items()}
    if len(chosen) < 2:
        return
    before, after = (chosen[name] for name in ('before', 'after'))
    distinct = before[0]['stream'] != after[0]['stream']
    result['cubeb_same_stream'] = not distinct
    if distinct:
        left, right = before[2][-1], after[2][0]
        result['cubeb_boundary'] = {
            'previous_last_block': left, 'next_first_block': right,
            'host_gap_start_to_start_ms': (right['host_time'] - left['host_time']) * tick_ms,
            'next_stream_starts_at_zero': right['sample_time'] == 0,
        }
        checks['cubeb_pre_and_post_acquired'] = right['host_time'] > left['host_time']
    else:
        checks['cubeb_pre_and_post_acquired'] = True
        lo, hi = sorted((resume + before[1], resume + after[1]))
        rows = [row for row in before[2] if lo - width <= row['pcm_frame'] <= hi + width]
        result['cubeb_boundary'] = {
            'origin_advance_frames': after[1] - before[1], 'blocks': rows,
            'sample_clock_step_frames': [b['sample_time'] - a['sample_time'] for a, b in zip(rows, rows[1:])],
            'host_clock_step_ms': [(b['host_time'] - a['host_time']) * tick_ms for a, b in zip(rows, rows[1:])],
        }
    if waveform is not None:
        inspect_keeper(case, spec, result, tape, tap_pcm, before, after, waveform)


def inspect(folder, case, spec, route, fixture, period):
    browser = read(folder / 'browser.json')
    ready, target, gate = (read(folder / f'trace-{name}.json') for name in ('ready', 'target', 'release'))
    result = {'suspend': spec['context_study']['suspend'], 'browser_version': browser.get('browserVersion'),
              'browser_error': browser.get('error'), 'context_restart': browser.get('contextRestart'),
              'tap_pid': target['firefox_pid'], 'tap_release': gate, 'snapshot_blocks': spec['snapshot_blocks']}
    checks = {
        'trusted_play_and_target': ready == {'sampleRate': spec['sample_rate_hz'], 'trustedClick': True}
                                   and gate['tap_ready'] and target['firefox_pid'] > 0,
        'capture_completed': browser.get('complete') is True,
        'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
    }
    inspect_context_pcm(folder, case, spec, fixture, period, result, checks, 'graph', browser.get('output'),
                        target['firefox_pid'], browser.get('contextError'))
    waveform = None
    if 'keep_output' in spec:
        options = spec['keep_output']
        keeper = browser.get('keeper', {})
        waveform = np.asarray(keeper.get('waveform', []), dtype='<f4')
        period_frames = options['period_frames']
        expected = options['amplitude'] * np.sin(2 * np.pi * np.arange(period_frames) / period_frames)
        checks['keeper_context_and_waveform'] = bool(
            (keeper.get('state'), keeper.get('rate')) == ('running', spec['sample_rate_hz'])
            and len(waveform) == period_frames and np.max(np.abs(waveform - expected)) <= options['maximum_keeper_sample_error'])
        if not checks['keeper_context_and_waveform']:
            return result
        if result['suspend'] and checks.get('context_suspended_and_resumed'):
            restart = result['context_restart']
            stop, resume = (restart[label] for label in ('suspendReturned', 'resumeRequested'))
            result['keeper_context_advance_frames'] = resume['keeperFrame'] - stop['keeperFrame']
            checks['keeper_context_advanced_during_suspend'] = (
                stop['keeperState'] == resume['keeperState'] == 'running'
                and result['keeper_context_advance_frames'] >= options['minimum_isolated_gap_frames'])
    tape = read(folder / 'tap.json')
    tap_pcm = read_stereo(folder / 'tap.f32le')
    result['tap_zero_spans_at_least_128'] = [[lo, hi] for lo, hi in zero_spans(tap_pcm) if hi - lo >= 128]
    inspect_cubeb(folder, case, spec, fixture, result, tape, tap_pcm, waveform)
    return result


def collect(folder, execute, case, spec, firefox, app, stimulus, fixture, period):
    probe = folder / 'coreaudio-output-device'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
    options = folder / 'effective-case.json'
    options.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    cubeb = folder / 'cubeb'
    cubeb.mkdir()
    acquire = capture_tap(execute, folder, spec['capture'], app)
    command = ['env', f'CHIMERA_FIREFOX={firefox}', f'CHIMERA_CUBEB_OUTPUT_DIR={cubeb}',
               f"CHIMERA_CUBEB_OUTPUT_BLOCKS={spec['snapshot_blocks']}", 'node', str(BROWSER),
               str(options), str(folder), str(probe), str(stimulus)]
    route = capture_on_output(spec, folder, probe, lambda: acquire(command, cwd=WEB, stdout=folder / 'browser-command.log'))
    return inspect(folder, case, spec, route, fixture, period)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', nargs='?', type=Path)
    parser.add_argument('app', nargs='?', type=Path)
    cases = {'restart': CASE, 'keep-output': KEEP, 'silent-output': SILENT}
    parser.add_argument('--case', choices=cases, default='restart')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--summarize', action='store_true')
    mode.add_argument('--review', metavar='CAPTURE_RUN')
    args = parser.parse_args()
    registered = cases[args.case]
    keeper = registered != CASE
    silent = registered == SILENT
    base = read(CASE)
    case = base
    if keeper:
        extension = read(KEEP)
        if (extension['base_case'], extension['base_case_revision']) != (CASE.name, base['revision']):
            parser.error('出力維持ケースの基準版が一致しません')
        case = base | extension
    if silent:
        sounding_case = case
        extension = read(SILENT)
        if (extension['base_case'], extension['base_case_revision']) != (KEEP.name, sounding_case['revision']):
            parser.error('無音ケースの基準版が一致しません')
        case = sounding_case | extension | {'keep_output': sounding_case['keep_output'] | extension['keep_output']}
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
            or revision != read(RESPONSE)['upstream_revision']):
        parser.error('変更のない固定上流が必要です')
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv]}
    calibration = hydrate_run(case['calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    cal_path = verified_file(*calibration, 'artifacts/effective-case.json')
    long_case = CASE.with_name(case['reference_windows_case'])
    stimulus_run = hydrate_run(case['fixture_run'], read(long_case)['id'], revision)
    stimulus = verified_file(*stimulus_run, 'artifacts/fixture.f32le')
    native = hydrate_run(case['native_reference_run'], 'coreaudio-headphone-drift-44100-output-restart', revision)
    safari = hydrate_run(case['safari_reference_run'], 'safari-headphone-context-restart-44100', revision)
    previous = hydrate_run(case['firefox_reference_run'], 'firefox-process-tap-headphone-drift-44100', revision)
    tools = WORKSPACE / 'tools'
    sources = [CASE, CALIBRATION, RESPONSE, DRIFT, long_case, Path(__file__).resolve(), calibration[0] / 'manifest.json',
               cal_path, stimulus_run[0] / 'manifest.json', stimulus, previous[0] / 'manifest.json',
               native[0] / 'manifest.json', verified_file(*native, 'summary.json'),
               safari[0] / 'manifest.json', verified_file(*safari, 'summary.json'),
               *(tools / name for name in ('measure_safari_headphone_context_restart_44100.py',
                  'measure_firefox_headphone_drift_44100.py', 'measure_firefox_headphone_response_44100.py',
                  'measure_safari_process_tap_calibration.py', 'measure_coreaudio_headphone_late_attach_44100.py',
                  'measure_worklet_tsp_device_tap.py', 'measure_worklet_live_song_process_tap.py',
                  'measure_cubeb_output_callback.py', 'smooth_tap_marker.py',
                  'chimera-cubeb-output-snapshot.patch', 'chimera-cubeb-output-snapshot-long.patch'))]
    if keeper:
        baseline = hydrate_run(case['restart_reference_capture'], base['id'], revision)
        baseline_summary = hydrate_run(case['restart_reference_summary'], base['id'], revision)
        if any(run[1]['case_revision'] != base['revision'] for run in (baseline, baseline_summary)):
            parser.error('停止で出力が切り替わる基準計測の版が一致しません')
        sources.extend([KEEP, baseline[0] / 'manifest.json', baseline_summary[0] / 'manifest.json',
                        verified_file(*baseline_summary, 'summary.json')])
    if silent:
        sounding_capture = hydrate_run(case['sounding_reference_capture'], sounding_case['id'], revision)
        sounding_summary = hydrate_run(case['sounding_reference_summary'], sounding_case['id'], revision)
        if any(run[1]['case_revision'] != sounding_case['revision'] for run in (sounding_capture, sounding_summary)):
            parser.error('同相音ありの基準計測の版が一致しません')
        sounding_path = verified_file(*sounding_summary, 'summary.json')
        sources.extend([SILENT, sounding_capture[0] / 'manifest.json', sounding_summary[0] / 'manifest.json', sounding_path])
    reviews = case.get('capture_reviews', {})
    if args.summarize:
        evaluated = case | {
            'trials': [t | {'run_id': reviews.get(t['run_id'], t['run_id'])} for t in case['trials']],
            'pairs': [[reviews.get(name, name) for name in pair] for pair in case['pairs']],
        }
        result = summarize(evaluated, revision, sources)
        result['safari_reference_pairs'] = read(verified_file(*safari, 'summary.json'))['pairs']
        qualified = [pair for pair in result['pairs'] if pair['initially_narrow']]
        result['qualified_restart_timing_matched'] = (
            all(bool(pair['drop_timing_matches_native']) for pair in qualified) if qualified else None)
        for pair in result['pairs']:
            for label in ('continuous', 'suspended'):
                trial = result['trials'][pair[label]]
                segments = trial.get('cubeb_segments', {})
                pair[f'{label}_cubeb_pcm_matches_in_measurement_windows'] = (
                    all(v['analyzed_bitwise_match'] for v in segments.values()) if len(segments) == 2 else None)
            pair['suspended_cubeb_changed_stream'] = (
                not result['trials'][pair['suspended']]['cubeb_same_stream']
                if 'cubeb_same_stream' in result['trials'][pair['suspended']] else None)
            if keeper:
                measured = result['trials'][pair['suspended']].get('resumption', {})
                pair['suspended_remained_narrow'] = measured.get('post_narrow_in_all_windows')
        if keeper:
            result.pop('restart_prediction_matched')
            result.pop('qualified_restart_timing_matched')
            result['retained_narrow_prediction_matched'] = (
                all(pair['continuous_remained_narrow'] and pair['suspended_remained_narrow'] for pair in qualified)
                if qualified else None)
            result['single_context_reference_pairs'] = read(verified_file(*baseline_summary, 'summary.json'))['pairs']
        if silent:
            sounding = read(sounding_path)
            for pair, reference_pair in zip(result['pairs'], sounding['pairs'], strict=True):
                current = result['trials'][pair['suspended']].get('resumption', {}).get('post_first_ratio')
                reference = sounding['trials'][reference_pair['suspended']]['resumption']['post_first_ratio']
                pair['sounding_reference'] = reference_pair['suspended']
                pair['post_first_ratio_minus_sounding'] = current - reference if current is not None else None
        return record_measurement(args.run_id, registered, sources, metadata, lambda *_: result, command=None, input_root=ROOT)
    registered_trials = case['trials'] if keeper else [*case['trials'], case['pilot']]
    trials = [t for t in registered_trials if t['run_id'] == (args.review or args.run_id)]
    if len(trials) != 1:
        parser.error('登録した試行を指定してください')
    trial, = trials
    spec, period, comparison_sources = comparison_inputs(case, trial, cal_path, long_case, revision)
    spec['snapshot_blocks'] = trial.get('snapshot_blocks', case['snapshot_blocks'])
    if keeper:
        spec['keep_output'] = case['keep_output']
    fixture = np.fromfile(stimulus, dtype='<f4')
    sources.extend(comparison_sources)
    if args.review:
        if args.run_id != reviews.get(args.review) or args.firefox is not None or args.app is not None:
            parser.error('登録した採取IDと再解析IDを指定してください')
        saved = WORKSPACE / 'runs' / args.review
        manifest_file = saved / 'manifest.json'
        manifest = read(manifest_file)
        if (manifest['run_id'], manifest['case_id'], manifest['case_revision'], manifest['upstream_revision']) != (
                args.review, case['id'], case['revision'], revision):
            parser.error('採取済みの試行とケースが一致しません')
        names = ('browser.json', 'trace-ready.json', 'trace-target.json', 'trace-release.json', 'tap.json', 'tap.f32le',
                 'graph.json', 'graph.f32le', 'output-device.json', 'effective-case.json')
        reviewed_paths = [verified_file(saved, manifest, f'artifacts/{name}') for name in names]
        reviewed_paths.extend(verified_file(saved, manifest, row['path']) for row in manifest['outputs']
                              if row['path'].startswith('artifacts/cubeb/'))
        effective = read(saved / 'artifacts/effective-case.json')
        if any(effective.get(key) != value for key, value in spec.items()):
            parser.error('採取時の実効設定と比較設定が一致しません')
        sources.extend([manifest_file, *reviewed_paths])
        metadata['original_capture'] = args.review
        metadata['original_capture_status'] = manifest['status']

        def review(*_):
            folder = saved / 'artifacts'
            result = inspect(folder, case, spec, read(folder / 'output-device.json'), fixture, period)
            return result | {'original_capture': args.review, 'original_capture_status': manifest['status']}

        return record_measurement(args.run_id, registered, sources, metadata, review, command=None, input_root=ROOT)
    if args.firefox is None or args.app is None:
        parser.error('Firefoxと署名済み採取アプリを指定してください')
    firefox, app = args.firefox.resolve(strict=True), args.app.resolve(strict=True)
    binary, xul = sha256(firefox), sha256(firefox.with_name('XUL'))
    if (xul == previous[1]['firefox_xul_sha256']) != (trial == case['pilot']):
        parser.error('予備試行は先行比較と同じXUL、本試行は採取容量を拡張したXULが必要です')
    if keeper and (binary, xul) != (baseline[1]['firefox_binary_sha256'], baseline[1]['firefox_xul_sha256']):
        parser.error('単一Contextの基準計測と同じFirefoxが必要です')
    if silent and (binary, xul) != (sounding_capture[1]['firefox_binary_sha256'], sounding_capture[1]['firefox_xul_sha256']):
        parser.error('同相音ありの基準計測と同じFirefoxが必要です')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    for label, path in (('tap_binary_sha256', 'Contents/MacOS/chimera-process-tap'), ('tap_info_sha256', 'Contents/Info.plist')):
        metadata[label] = sha256(app / path)
        if metadata[label] != calibration[1][label] or metadata[label] != previous[1][label]:
            parser.error('較正および先行比較と同じ署名済み採取アプリを指定してください')
    metadata.update(firefox_binary_sha256=binary, firefox_xul_sha256=xul,
                    node=subprocess.check_output(['node', '--version'], text=True).strip())
    spec['capture'] = read(RESPONSE)['capture'] | {
        'tap_duration_seconds': case['capture_duration_seconds'], 'tap_wait_timeout_seconds': case['capture_duration_seconds'] + 4,
        'publish_trace_target': True,
    }
    sources.extend([BROWSER, OUTPUT_DEVICE, NATIVE, PLIST,
                    *(BROWSER.with_name(name) for name in ('shared-context-marker.mjs', 'shared-context-marker-worklet.js'))])
    return record_measurement(args.run_id, registered, sources, metadata,
                              lambda folder, execute: collect(folder, execute, case, spec, firefox, app, stimulus, fixture, period),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
