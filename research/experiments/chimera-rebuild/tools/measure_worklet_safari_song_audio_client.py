"""Safari歌唱の予備描画とCore AudioクライアントのI/O時刻を比較する。"""

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys
import time
from xml.etree import ElementTree

import numpy as np
from scipy.io import wavfile

from capture_worklet_system_pair import darwin_notification, recording
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_safari_audio_client_trace import inspect_trace
from measure_safari_process_tap_calibration import INSPECTOR, read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, WEB, UPSTREAM, WORKSPACE, web_sources
from measure_worklet_safari_song_prepared_pause import CAPTURE, WASM, analyze_trial
from measure_worklet_safari_song_prepared_shared_context import compare_marker
from measure_worklet_safari_song_split_score_preparation import compare_preparation, preparation_lengths
from song_score_preparation_timing import compare_preparation_timing
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/worklet-safari-song-audio-client.json'
WEBKIT_THREADS = WORKSPACE / 'tools/chimera_webkit_audio_threads.swift'
WEB_AUDIO_ROLES = {'RemoteAudioDestinationProxy render thread', 'WebCore: AudioWorklet'}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def bridge(folder, inspector, options, target):
    ready = folder / 'trace-ready.json'
    result = {}

    def snapshot():
        return json.loads(subprocess.check_output([str(inspector), *options['candidate_bundle_ids']], timeout=4, text=True))

    def webkit_snapshot():
        binary = inspector.with_name('webkit-audio-threads')
        return json.loads(subprocess.check_output([str(binary)], timeout=4, text=True))

    def release(data):
        tmp = folder / 'trace-release.tmp'
        write_json(tmp, data | {'release_epoch_ns': time.time_ns()})
        tmp.rename(folder / 'trace-release.json')

    result['before'] = snapshot()
    webcontent = options.get('capture_target') == 'webcontent'
    if webcontent:
        result['webcontent_before'] = webkit_snapshot()
    with subprocess.Popen(target) as browser:
        try:
            deadline = time.monotonic() + 14
            while not ready.is_file():
                if browser.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError('Safariから先行信号の準備通知が届きません')
                time.sleep(0.02)
            result['at_gate'] = snapshot()
            active_before = {row['pid'] for row in result['before'] if row['runningOutput']}
            eligible = [row for row in result['at_gate'] if row['runningOutput'] and row['pid'] not in active_before]
            if len(eligible) != 1:
                raise RuntimeError('試験音によって出力を始めたCore Audioプロセスを一意に特定できません')
            result['target'] = eligible[0]
            instruments = [value for name in options.get('instruments', ['Audio Client']) for value in ('--instrument', name)]
            attach_pid = None if options.get('capture_all_processes') else eligible[0]['pid']
            if webcontent:
                result['webcontent_at_gate'] = webkit_snapshot()
                already_active = {row['pid'] for row in result['webcontent_before'] if WEB_AUDIO_ROLES <= set(row['names'])}
                candidates = [row for row in result['webcontent_at_gate']
                              if row['pid'] not in already_active and WEB_AUDIO_ROLES <= set(row['names'])]
                if len(candidates) != 1:
                    raise RuntimeError('先行音の描画を始めたWebContentのプロセスを一意に特定できません')
                result['webcontent_attachment'] = candidates[0]
                attach_pid = candidates[0]['pid']
            with darwin_notification() as notice:
                with recording(folder, instruments, f"{options['duration_seconds']}s", notice,
                               attach_pid=attach_pid, output_wait=options.get('output_wait_seconds', 25)) as (epoch, monotonic):
                    deadline = monotonic + options['release_after_notification_ms'] * 1_000_000
                    time.sleep(max(0, (deadline - time.monotonic_ns()) / 1_000_000_000))
                    release({'trace_notice_epoch_ns': epoch})
            result['trace_recorded'] = True
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            result['trace_recorded'] = False
            result['error'] = str(error)
            if ready.is_file() and not (folder / 'trace-release.json').is_file():
                release({'error': str(error)})
        write_json(folder / 'trace-bridge.json', result)
        try:
            return browser.wait(timeout=28)
        finally:
            if browser.poll() is None:
                browser.terminate()
                try:
                    browser.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait()


def compare_io(folder, pid, report, preparation_end, spec, execute):
    trace = inspect_trace('audio-system', folder, pid, execute)
    starts = np.array([row['start_ns'] for row in trace['cycles']], dtype=np.float64) / 1e6
    durations = np.array([row['duration_ns'] for row in trace['cycles']], dtype=np.float64) / 1e6
    gaps = np.diff(starts)
    origin = trace['trace_start_epoch_ms']
    begin = report['scoreConstruction']['startedAtEpochMs'] - origin
    end = preparation_end - origin
    windows = {'baseline': (begin - spec['baseline_from_ms'], begin - spec['baseline_to_ms']),
               'preparation': (begin, end), 'post': (end + spec['post_from_ms'], end + spec['post_to_ms'])}
    stats = {}
    for label, (a, b) in windows.items():
        # 処理窓にまたがる開始間隔と、その窓で始まるコールバックを別々に数える。
        intervals = np.flatnonzero((starts[:-1] <= b) & (starts[1:] >= a))
        active = durations[(a <= starts) & (starts <= b)]
        item = {'epoch_ms': [float(a + origin), float(b + origin)], 'intervals': len(intervals),
                'callback_count': len(active)}
        if len(intervals):
            index = intervals[np.argmax(gaps[intervals])]
            item.update(median_interval_ms=float(np.median(gaps[intervals])), maximum_interval_ms=float(gaps[index]),
                        maximum_interval_epoch_ms=[float(starts[index] + origin), float(starts[index + 1] + origin)])
        if len(active):
            item.update(median_callback_ms=float(np.median(active)), maximum_callback_ms=float(active.max()))
        stats[label] = item
    checks = {'client_thread_ordered': (len(starts) > 1 and len({x['tid'] for x in trace['cycles']}) == 1
                                        and bool(np.all(gaps > 0))),
              'client_windows_observed': (len(starts) > 1 and bool(starts[0] < windows['baseline'][0]
                  and starts[-1] > windows['post'][1]) and all(w['intervals'] >= spec['minimum_window_intervals'] for w in stats.values()))}
    return checks, {'trace_start_epoch_ms': origin, 'cycles': len(starts), 'windows': stats}


def measure(study, shared, pause, reference, fields, order, bundles, artifacts, execute):
    execute(['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build'],
            cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    binary_hash = sha256(binary)
    inspector = artifacts / 'coreaudio-output-processes'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(INSPECTOR), '-o', str(inspector)])
    if study['trace'].get('capture_target') == 'webcontent':
        execute(['xcrun', 'swiftc', '-O', str(WEBKIT_THREADS), '-o', str(artifacts / 'webkit-audio-threads')])
    source, wav, report = reference
    _, pcm = wavfile.read(wav)
    source_case, reference_report = read_json(source), read_json(report)
    marker_spec = shared['marker'] | {'moduleName': 'fixed-processor-entry', 'waitForSystemTrace': True,
                                    'capture_quanta': study['marker_capture_quanta']}
    shared = shared | {'marker': marker_spec}
    trace = study['trace'] | {'candidate_bundle_ids': bundles}
    warm_up = study['warm_up_frames']
    trial = {'warm_up_frames': warm_up, 'mode': 'continuous', 'route': 'direct'}
    checks, trials, pairs = {}, {}, []
    for index, sequence in enumerate(order, 1):
        pair = {'pair': index}
        for condition in sequence:
            label = f'pair-{index}-{condition}'
            folder = artifacts / label
            folder.mkdir()
            options = folder / 'capture-case.json'
            config = {'song_preset': 'prepared', 'startup_timeout_seconds': study['startup_timeout_seconds'],
                      'mid_song_pause': pause['pause'] | {'perform_pause': False},
                      'shared_context_marker': marker_spec, 'audio_client_trace': trace}
            if 'output_clock_observation' in study:
                config['output_clock_observation'] = study['output_clock_observation']
            split = condition == 'split'
            if split:
                config.update(score_preparation_block_frames=study['split_block_frames'],
                              score_preparation_initial_blocks=study['split_initial_blocks'], trace_score_preparation_blocks=True)
            write_json(options, config)
            item = trials[label] = {'condition': condition}
            local = {}
            try:
                execute([sys.executable, str(Path(__file__).resolve()), '--bridge', str(folder), str(inspector),
                         str(options), 'node', str(CAPTURE), str(folder), str(source), str(options)],
                        cwd=WEB, stdout=folder / 'browser-command.log')
                local, song, _ = analyze_trial(label, trial, pause, source_case, binary_hash, pcm, reference_report,
                                               fields, folder, reference_live=True)
                item['song'] = song
                document = read_json(folder / 'browser.json')
                lengths = preparation_lengths(warm_up, study['split_block_frames'], study['split_initial_blocks']) if split else None
                checked, end, preparation = compare_preparation(document, warm_up, marker_spec['quantum'], lengths)
                local.update(checked)
                marker_checks, item['marker'] = compare_marker(folder, document, shared, preparation_end=end)
                local.update(marker_checks)
                if split:
                    detail, item['preparation_timing'], _ = compare_preparation_timing(
                        folder, document, preparation, lengths, marker_spec, study['preparation_timing'])
                    local.update(detail)
                native = read_json(folder / 'trace-bridge.json')
                item['trace_bridge'] = native
                local['trace_recorded'] = native['trace_recorded']
                if native['trace_recorded']:
                    gate = read_json(folder / 'trace-release.json')
                    browser_gate = read_json(folder / 'browser-trace-gate.json')
                    local['construction_after_trace_gate'] = (gate['trace_notice_epoch_ns'] <= gate['release_epoch_ns']
                        and gate['release_epoch_ns'] // 1_000_000 <= browser_gate['releaseEpochMs']
                        <= document['scoreConstruction']['startedAtEpochMs'])
                    instruments = trace.get('instruments', ['Audio Client'])
                    io_checks = {}
                    if 'Audio Client' in instruments:
                        io_checks, item['audio_client'] = compare_io(folder, native['target']['pid'], document, end, trace, execute)
                    else:
                        execute(['xcrun', 'xctrace', 'export', '--input', str(folder / 'audio-system.trace'), '--toc',
                                 '--output', str(folder / 'audio-system-toc.xml')])
                    local.update(io_checks)
                    if 'System Call Trace' in instruments and trace.get('export_syscall_xml', True):
                        execute(['xcrun', 'xctrace', 'export', '--input', str(folder / 'audio-system.trace'), '--xpath',
                                 '/trace-toc/run/data/table[@schema="syscall"]', '--output', str(folder / 'syscall.xml')])
                    if io_checks and all(io_checks.values()):
                        windows = item['audio_client']['windows']
                        pair[condition] = {'marker_max_gap_ms': item['marker']['preparation_window_max_gap_ms'],
                                           'io_max_gap_ms': windows['preparation']['maximum_interval_ms']}
            except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError, subprocess.CalledProcessError) as error:
                local['capture_and_analysis_complete'] = False
                item['error'] = str(error)
            checks.update({f'{label}/{key}': bool(value) for key, value in local.items()})
        pairs.append(pair)
    matched = [pair for pair in pairs if 'bulk' in pair and 'split' in pair]
    marker_reduction = median(pair['bulk']['marker_max_gap_ms'] - pair['split']['marker_max_gap_ms'] for pair in matched) if matched else None
    maxima = {condition: median(pair[condition]['io_max_gap_ms'] for pair in matched)
              for condition in ('bulk', 'split')} if matched else {}
    covered = len(matched) == len(order)
    predictions = ({'split_reduces_graph_gap': covered and marker_reduction >= trace['minimum_marker_gap_reduction_ms'],
                    'both_io_gaps_below_limit': covered and all(value <= trace['maximum_median_io_gap_ms'] for value in maxima.values())}
                   if 'Audio Client' in trace.get('instruments', ['Audio Client']) else {})
    return {'checks': checks, 'predictions': predictions, 'trials': trials, 'pairs': pairs,
            'median_marker_gap_reduction_ms': marker_reduction, 'median_maximum_io_gap_ms': maxima}


def main():
    if sys.argv[1:2] == ['--bridge']:
        folder, inspector, options = map(Path, sys.argv[2:5])
        return bridge(folder, inspector, read_json(options)['audio_client_trace'], sys.argv[5:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--attach-gpu-only', action='store_true', help='同時採取の対象をWebKit GPUのPIDに限る')
    parser.add_argument('--system-calls-only', action='store_true', help='System Call Traceだけを採取する')
    parser.add_argument('--release-delay-ms', type=int, help='トレース開始通知から歌唱の解放までの待機時間')
    parser.add_argument('--defer-syscall-export', action='store_true', help='生のトレースを保存し、syscall表は解析時に展開する')
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    received = read_json(case_path)
    base = CASE.parent / received['base_case'] if 'base_case' in received else case_path
    study = read_json(base)
    study |= received | {'trace': study['trace'] | received['trace']}
    if args.attach_gpu_only:
        study['trace']['capture_all_processes'] = False
        study['trace']['capture_target'] = 'gpu'
    if args.system_calls_only:
        study['trace']['instruments'] = ['System Call Trace']
    if args.release_delay_ms is not None:
        if args.release_delay_ms < 0:
            parser.error('解放までの待機時間は0以上を指定してください')
        study['trace']['release_after_notification_ms'] = args.release_delay_ms
    if args.defer_syscall_export:
        study['trace']['export_syscall_xml'] = False
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    shared_case = CASE.parent / study['shared_context_case']
    shared = read_json(shared_case)
    pause_case = CASE.parent / shared['reference']['case']
    pause = read_json(pause_case)
    prepared_case = CASE.parent / pause['reference']['case']
    fields = list(read_json(prepared_case)['measurement']['state_tolerance'])
    client_case = CASE.parent / study['audio_client_case']
    client = read_json(client_case)
    playback_case = CASE.parent / client['playback_case']
    bundles = read_json(playback_case)['candidate_bundle_ids']
    client_reference = run_manifest(study['audio_client_reference_run'], client['id'], revision)
    ref = study['reference']
    ref_case = CASE.parent / ref['case']
    reference = run_manifest(ref['run'], read_json(ref_case)['id'], revision)
    if any(run[1]['status'] != 'pass' for run in (reference, client_reference)):
        parser.error('歌唱とAudio Clientの保存基準が必要です')
    paths = [verified_path(reference, f'artifacts/{ref["trial"]}/{name}')
             for name in ('browser-case.json', 'browser.wav', 'browser.json')]
    if read_json(paths[0])['song_voice']['warm_up_frames'] != study['warm_up_frames']:
        parser.error('保存基準の予備描画量が登録条件と一致しません')
    files = [case_path, base, shared_case, pause_case, prepared_case, client_case, playback_case, ref_case, Path(__file__).resolve(),
             reference[0] / 'manifest.json', client_reference[0] / 'manifest.json',
             verified_path(client_reference, 'summary.json'), *paths, INSPECTOR, CAPTURE,
             CAPTURE.with_name('safari-webdriver.mjs'), *web_sources(), *candidate_sources()]
    if study['trace'].get('capture_target') == 'webcontent':
        files.append(WEBKIT_THREADS)
    files.extend(WORKSPACE / 'tools' / name for name in (
        'capture_worklet_system_pair.py', 'measure_safari_audio_client_trace.py',
        'measure_worklet_safari_song_prepared_pause.py', 'measure_worklet_safari_song_prepared_shared_context.py',
        'measure_worklet_safari_song_split_score_preparation.py', 'filter_worklet_audioipc_syscalls.py',
        'song_score_preparation_timing.py', 'measure_uniform_tube.py'))
    order = [pair[::-1] for pair in study['condition_order']] if args.reverse else study['condition_order']
    details = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv], 'safari_reference': reference[0].name,
               'audio_client_reference': client_reference[0].name,
               'xctrace': subprocess.check_output(['xcrun', 'xctrace', 'version'], text=True).strip(),
               'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, case_path, files, details,
                              lambda artifacts, execute: measure(study, shared, pause, paths, fields, order, bundles, artifacts, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
