"""SafariのAudioContext停止と、再開時のプロセスタップを比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_coreaudio_headphone_late_attach_44100 import inspect_resumption, match_anchors
from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_drift_44100 import CASE as DRIFT, compare
from measure_firefox_headphone_response_44100 import CASE as RESPONSE, continuous_blocks, read_stereo
from measure_safari_process_tap_calibration import (
    CASE as CALIBRATION, INSPECTOR, OUTPUT_DEVICE, SAFARI, capture_on_output, identified_process,
)
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WEB, WORKSPACE
from measure_worklet_live_song_process_tap import NATIVE, PLIST, staged_app, stop_tap
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/safari-headphone-context-restart-44100.json'


def inspect(folder, case, spec, route, fixture, period):
    browser = read(folder / 'capture.json')
    suspend = spec['context_study']['suspend']
    result = {'suspend': suspend, 'browser_phase': browser['phase'], 'browser_error': browser.get('error'),
              'context_restart': browser.get('contextRestart'), 'tap_launch': browser.get('tap')}
    checks = {'safari_session': browser.get('capabilities', {}).get('browserName') == 'Safari',
              'trusted_play_and_target': bool(browser.get('restartedTrusted') and identified_process(browser)),
              'capture_completed': browser['phase'] == 'complete',
              'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput']}
    return inspect_context_pcm(folder, case, spec, fixture, period, result, checks, 'context-marker',
                               (browser.get('tap') or {}).get('outputDevice'), (browser.get('confirmedTarget') or {}).get('pid'),
                               browser.get('contextError'))


def comparison_spans(case, spec, resume):
    analysis = spec['analysis']
    hop = analysis['hop_frames']
    start = analysis['first_frames'][0]
    stop = spec['attach_comparison']['analysis_end_frame']
    guard = case['analysis']['post_guard_frames']
    earlier = min(case['analysis']['pre_last_exclusive'], resume - guard)
    later = start + (resume + guard - start + hop - 1) // hop * hop
    return [[start, earlier], [later, stop]]


def inspect_context_pcm(folder, case, spec, fixture, period, result, checks, graph_key, physical, tap_pid, context_error):
    result['checks'] = checks
    if not all(checks.values()):
        return result
    graph_meta, tape = (read(folder / name) for name in (f'{graph_key}.json', 'tap.json'))
    graph = np.fromfile(folder / f'{graph_key}.f32le', dtype='<f4')
    tap_pcm = read_stereo(folder / 'tap.f32le')
    tap = (tap_pcm[:, 0] - tap_pcm[:, 1]) * .5
    rate, quantum = spec['sample_rate_hz'], spec['quantum_frames']
    study = spec['context_study']
    quanta, source_start = study['graph_capture_quanta'], graph_meta['startFrame']
    frames, stamps = (np.asarray(graph_meta[key]) for key in ('frames', 'callbackEpochMs'))
    width = spec['output_device']['expected_frames']
    active, = [d for d in physical['devices'] if d['id'] == physical['defaultOutput']]
    checks.update(device_matches=(active['uid'], active['sampleRate'], active['bufferFrames']) ==
                  (spec['output_device']['uid'], rate, width),
                  graph_rate_matches=graph_meta['rate'] == rate,
                  graph_pcm_bitwise=np.array_equal(graph.view('<u4'), fixture.view('<u4')),
                  graph_frame_numbers_continuous=bool(np.array_equal(frames, source_start + np.arange(quanta) * quantum)
                      and graph_meta['inputFrames'] == [quantum] * quanta),
                  graph_wall_clock_continuous=bool(len(stamps) == quanta and np.isfinite(stamps).all()
                      and np.all(np.diff(stamps) >= 0)),
                  tap_matches_target_and_format=(tape['pid'] == tap_pid
                      and tape['sampleRate'] == rate and tape['frames'] == len(tap_pcm)
                      and not tape['overflow'] and not tape['formatErrors']))
    result['active_output_device'] = active
    result['largest_graph_callback_gap_ms'] = float(np.max(np.diff(stamps), initial=0))
    restart = result['context_restart']
    suspend = result['suspend']
    resume = study['target_frame']
    if suspend and isinstance(restart, dict) and 'resumeReturned' in restart:
        paused, requested = (restart[label] for label in ('suspendReturned', 'resumeRequested'))
        resume = requested['frame'] - source_start
        hold = requested['atEpochMs'] - paused['atEpochMs']
        result['frozen_source_frame'] = resume
        result['suspended_wall_ms'] = hold
        checks['context_suspended_and_resumed'] = (
            paused['state'] == requested['state'] == 'suspended' and restart['resumeReturned']['state'] == 'running'
            and not context_error and paused['frame'] == requested['frame']
            and abs(resume - study['target_frame']) <= study['maximum_stop_offset_frames']
            and abs(hold - study['hold_seconds'] * 1000) <= study['maximum_hold_error_ms']
            and result['largest_graph_callback_gap_ms'] >= study['minimum_callback_gap_ms'])
    else:
        checks['context_suspended_and_resumed'] = not suspend and restart is None
    result['comparison_resume_frame'] = resume
    anchor = match_anchors(tap, spec, spec, False) if np.isfinite(tap).all() else {}
    before = anchor.get('origin_in_pcm')
    after = (anchor['tail_first']['offset'] - spec['attach_comparison']['terminal_anchors'][0]
             if anchor.get('tail_last') else None)
    result.update(anchor=anchor, tap_origins_in_pcm=[before, after])
    checks['front_and_tail_anchors'] = before is not None and after is not None and abs(anchor['tail_integer_advance']) <= 1
    if not all(checks.values()):
        return result
    analysis = spec['analysis']
    result['analyzed_source_spans'] = comparison_spans(case, spec, resume)
    regions = [(*span, origin) for span, origin in zip(result['analyzed_source_spans'], (before, after), strict=True)]
    for label, (lo, hi, origin) in zip(('before', 'after'), regions, strict=True):
        blocks = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', lo + origin, hi + origin, width, len(tap_pcm))
        checks[f'tap_clock_{label}'] = bool(blocks and all('hostTime' in block for block in blocks)
            and all(b['hostTime'] > a['hostTime'] for a, b in zip(blocks, blocks[1:])))
    if not all(checks.values()):
        return result
    measured = []
    for lo, hi, origin in regions:
        options = analysis | {'first_frames': [lo], 'last_exclusive': hi}
        clock = {'cubeb': [], 'tap': tape['blocks'], 'cb_origin': 0, 'tb_origin': origin}
        aligned = tap[origin:] if origin >= 0 else np.pad(tap, (-origin, 0))
        estimate = compare(graph, aligned, period, spec | {'analysis': options}, clock)
        for event in estimate['events'].values():
            event.pop('cubeb')
        for window in estimate['windows']:
            window['graph_residual'] = window.pop('cubeb_residual')
        measured.append(estimate)
    pre, post = measured
    checks['graph_tone_fits'] = pre['checks']['cubeb_tone_fits'] and post['checks']['cubeb_tone_fits']
    ratios = [tone['amplitude_ratio'] for w in pre['windows'] for tone in w['frequencies'] if tone['hz'] == analysis['band_tone_hz']]
    result['pre_windows'] = pre['windows']
    result['post_events'] = post['events']
    result['resumption'] = inspect_resumption(ratios, post, {'enabled': suspend,
        'pre_band_window_count': case['analysis']['pre_window_count']}, spec)
    return result


def collect(folder, execute, case, spec, app, stimulus, fixture, period):
    inspector, probe = (folder / part for part in ('coreaudio-output-processes', 'coreaudio-output-device'))
    for source, executable in ((INSPECTOR, inspector), (OUTPUT_DEVICE, probe)):
        execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(source), '-o', str(executable)])
    options = folder / 'effective-case.json'
    options.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    with staged_app(app, folder) as (local, recording):
        command = ['node', str(SAFARI), str(options), str(folder), str(inspector), str(local), str(recording),
                   'context-restart', str(probe), str(stimulus)]
        try:
            route = capture_on_output(spec, folder, probe, lambda: execute(command, cwd=WEB,
                stdout=folder / 'browser-command.log'))
        finally:
            stop_tap(local, recording)
    return inspect(folder, case, spec, route, fixture, period)


def summarize(case, revision, inputs):
    summaries = {}
    for trial in case['trials']:
        key = trial['run_id']
        folder = WORKSPACE / 'runs' / key
        manifest_file = folder / 'manifest.json'
        manifest = read(manifest_file)
        if (manifest['run_id'], manifest['case_id'], manifest['case_revision'], manifest['upstream_revision']) != (
                key, case['id'], case['revision'], revision):
            raise ValueError(f'{key} は登録した試行と一致しません')
        inputs.append(manifest_file)
        result = {'manifest_status': manifest['status']}
        if any(row['path'] == 'summary.json' for row in manifest['outputs']):
            path = verified_file(folder, manifest, 'summary.json')
            inputs.append(path)
            observed = read(path)
            if observed['suspend'] != trial['suspend']:
                raise ValueError(f'{key} の停止条件が登録と異なります')
            result.update({k: v for k, v in observed.items() if k not in ('pre_windows', 'resumption')})
            if 'resumption' in observed:
                result['resumption'] = {k: v for k, v in observed['resumption'].items() if k != 'windows'}
        summaries[key] = result
    pairs = []
    for steady, paused in case['pairs']:
        a, b = (summaries[name] for name in (steady, paused))
        valid = a['manifest_status'] == b['manifest_status'] == 'pass'
        control, suspended = (row['resumption'] if valid else {} for row in (a, b))
        narrow = valid and control['pre_narrow_in_all_windows'] and suspended['pre_narrow_in_all_windows']
        drop = suspended.get('post_drop_after_wide_center')
        relative = drop - b['comparison_resume_frame'] if drop is not None else None
        criteria = case['analysis']
        pairs.append({'continuous': steady, 'suspended': paused, 'capture_valid': valid, 'initially_narrow': narrow,
                      'continuous_remained_narrow': control.get('post_narrow_in_all_windows'),
                      'suspended_wide_first_center': suspended.get('post_wide_first_center'),
                      'suspended_drop_frames_from_resume': relative,
                      'drop_timing_matches_native': (abs(relative - criteria['native_reference_drop_frame']) <=
                                                     criteria['maximum_post_drop_frame_error']) if relative is not None else None})
    conditioned = [pair for pair in pairs if pair['initially_narrow']]
    return {'checks': {'all_pairs_captured': all(pair['capture_valid'] for pair in pairs)},
            'conditioned_pair_count': len(conditioned),
            'restart_prediction_matched': all(pair['continuous_remained_narrow'] and pair['suspended_wide_first_center'] is not None
                                               for pair in conditioned) if conditioned else None,
            'pairs': pairs, 'trials': summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('app', nargs='?', type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--summarize', action='store_true')
    modes.add_argument('--review', metavar='CAPTURE_RUN', help='保存済みのグラフとタップを再解析する')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
            or revision != read(RESPONSE)['upstream_revision']):
        parser.error('変更のない固定上流が必要です')
    calibration = hydrate_run(case['calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    cal_path = verified_file(*calibration, 'artifacts/effective-case.json')
    long_case = CASE.with_name(case['reference_windows_case'])
    stimulus_run = hydrate_run(case['fixture_run'], read(long_case)['id'], revision)
    stimulus = verified_file(*stimulus_run, 'artifacts/fixture.f32le')
    native = hydrate_run(case['native_reference_run'], 'coreaudio-headphone-drift-44100-output-restart', revision)
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv]}
    sources = [CASE, CALIBRATION, RESPONSE, DRIFT, long_case, Path(__file__).resolve(), calibration[0]/'manifest.json',
               cal_path, stimulus_run[0]/'manifest.json', stimulus, native[0]/'manifest.json',
               verified_file(*native, 'summary.json')]
    if args.summarize:
        result = summarize(case, revision, sources)
        return record_measurement(args.run_id, CASE, sources, metadata, lambda *_: result, command=None, input_root=ROOT)
    original = args.review or args.run_id
    trials = [t for t in case['trials'] if t['run_id'] == original]
    if len(trials) != 1 or (args.review is None and args.app is None):
        parser.error('登録試行のIDと採取アプリを指定してください')
    trial, = trials
    if args.review is None:
        app = args.app.resolve(strict=True)
        subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
        for label, path in (('tap_binary_sha256', 'Contents/MacOS/chimera-process-tap'), ('tap_info_sha256', 'Contents/Info.plist')):
            metadata[label] = sha256(app / path)
            if metadata[label] != calibration[1][label]:
                parser.error('較正と同じ署名済み採取アプリを指定してください')
    metadata['safaridriver'] = subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip()
    metadata['node'] = subprocess.check_output(['node', '--version'], text=True).strip()
    spec, period, comparison_sources = comparison_inputs(case, trial, cal_path, long_case, revision)
    sources.extend([INSPECTOR, OUTPUT_DEVICE, SAFARI, NATIVE, PLIST, *comparison_sources,
                    *(SAFARI.with_name(n) for n in ('safari-webdriver.mjs', 'shared-context-marker.mjs',
                    'shared-context-marker-worklet.js')), *(WORKSPACE/'tools'/n for n in (
                    'measure_firefox_headphone_drift_44100.py', 'measure_firefox_headphone_response_44100.py',
                    'measure_safari_process_tap_calibration.py', 'measure_coreaudio_headphone_late_attach_44100.py',
                    'measure_worklet_live_song_process_tap.py', 'smooth_tap_marker.py'))])
    fixture = np.fromfile(stimulus, dtype='<f4')
    if args.review is not None:
        saved = hydrate_run(original, case['id'], revision)
        if saved[1]['case_revision'] != case['revision'] or args.app is not None:
            parser.error('同じ登録条件で採取済みの試行を指定してください')
        related = [verified_file(*saved, name) for name in ('summary.json', 'artifacts/capture.json',
            'artifacts/output-device.json', 'artifacts/context-marker.json', 'artifacts/context-marker.f32le',
            'artifacts/tap.json', 'artifacts/tap.f32le')]
        summary, capture_file, route_file, *_ = related
        if read(summary)['suspend'] != trial['suspend']:
            parser.error('採取済みの停止条件が登録と一致しません')
        metadata['original_capture'] = original
        sources.extend([saved[0] / 'manifest.json', *related])

        def review(folder, execute):
            value = inspect(capture_file.parent, case, spec, read(route_file), fixture, period)
            return {**value, 'previous_checks': read(summary)['checks'], 'original_capture': original}

        return record_measurement(args.run_id, CASE, sources, metadata, review, command=None, input_root=ROOT)
    return record_measurement(args.run_id, CASE, sources, metadata, lambda folder, execute:
                              collect(folder, execute, case, spec, app, stimulus, fixture, period),
                              command=None, input_root=ROOT)


def comparison_inputs(case, trial, cal_path, long_case, revision):
    spec = read(CALIBRATION) | read(cal_path)
    spec.update(capture_duration_seconds=case['capture_duration_seconds'],
                attach_comparison=read(long_case)['attach_comparison'], trailing_anchor_search_frames=64,
                context_study=case['context_study'] | {'suspend': trial['suspend']})
    response, drift = read(RESPONSE), read(DRIFT)
    spec['output_device'] = response['output_device']
    for key in ('tone_probe', 'analysis', 'anchor'):
        spec[key] = response[key] | drift[key]
    waveform = spec['reference_waveform'] = drift['reference_waveform']
    short = WORKSPACE / 'runs' / waveform['run']
    short_manifest = short / 'manifest.json'
    short_pcm = verified_file(short, read(short_manifest), 'artifacts/tap.f32le')
    short_review = hydrate_run(waveform['review'], response['id'], revision)
    short_summary = verified_file(*short_review, 'summary.json')
    start = read(short_summary)['tap_anchor']['origin_in_pcm'] + waveform['start_frame']
    audio = read_stereo(short_pcm)[start:start + waveform['length_frames']]
    period = ((audio[:, 0] - audio[:, 1]) * .5).reshape(-1, waveform['period_frames']).mean(axis=0)
    return spec, period, [short_manifest, short_pcm, short_review[0] / 'manifest.json', short_summary]


if __name__ == '__main__':
    raise SystemExit(main())
