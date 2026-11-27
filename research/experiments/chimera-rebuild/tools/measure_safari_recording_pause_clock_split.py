"""録画の時刻を、AudioContextだけの停止とMediaRecorderだけの一時停止で比較する。"""

import argparse
from bisect import bisect_right
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

import numpy as np

import measure_worklet_song_recording as recording
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, UPSTREAM, WEB, WORKSPACE
from upstream_baseline import sha256


CASE = WORKSPACE / 'cases/safari-recording-pause-clock-split.json'
CAPTURE = WEB / 'tools/capture-safari-recording-clock-split.mjs'
MODES = {'continuous', 'context', 'recorder'}


def graph(report, mode, spec, *, include_audio=True):
    events = {event['phase']: event for event in report['events']}
    start, end = (events[key] for key in ('held', 'resume_requested'))
    context_state = 'suspended' if mode == 'context' else 'running'
    recorder_state = 'paused' if mode == 'recorder' else 'recording'
    rate = spec['sample_rate_hz']
    hold_ms = end['wallMs'] - start['wallMs']
    frame_delta = end['frame'] - start['frame']
    hold_delta = frame_delta / rate
    hold_position = (start['frame'] - report['signalStartFrame']) / rate
    draws = [draw for draw in report['draws'] if start['wallMs'] <= draw['wallMs'] <= end['wallMs']]
    track_kinds = ['audio', 'video'] if include_audio else ['video']
    track_check = 'two_tracks_closed' if include_audio else 'video_track_closed'
    checks = {
        'trusted_safari_on_macos': (report['trusted'] and report['capabilities']['browserName'] == 'Safari'
                                   and report['capabilities']['platformName'] == 'macOS'),
        track_check: sorted((track['kind'], track['readyState']) for track in report['trackStates'])
                     == [(kind, 'ended') for kind in track_kinds],
        'planned_hold_and_resume': (all(mark['context'] == context_state and mark['recorder'] == recorder_state
                                       for mark in (start, end))
                                    and events['resumed']['context'] == 'running'
                                    and events['resumed']['recorder'] == 'recording'
                                    and abs(hold_position - spec['hold_at_signal_seconds']) <= 0.04
                                    and spec['hold_ms'] - 2 <= hold_ms <= spec['hold_ms'] + 50),
        'both_clocks_drawn_while_held': (len(draws) >= 3 and report['sampleRate'] == rate
                                        and len({draw['wallCode'] for draw in draws}) >= 3),
    }
    observation = {'hold_ms': hold_ms, 'hold_position_seconds': hold_position, 'held_context_frames': frame_delta,
                   'held_context_seconds': hold_delta, 'held_context_codes': sorted({d['contextCode'] for d in draws}),
                   'hold_wall_ms': [start['wallMs'], end['wallMs']], 'draws_during_hold': len(draws)}
    return checks, observation


def signal_reference(signal_path, spec):
    signal = np.fromfile(signal_path, dtype='<f4')
    rate = spec['sample_rate_hz']
    t = np.arange(round(rate * spec['signal_seconds'])) / rate
    reference = spec['signal_gain'] * np.sin(2 * np.pi *
        (spec['signal_initial_hz'] * t + spec['signal_sweep_hz_per_second'] * t ** 2 / 2))
    matches = (len(signal) == len(reference) and np.isfinite(signal).all()
               and float(np.max(np.abs(signal - reference))) < 1e-7)
    return reference, matches


def decode_audio(frames, track, reference, folder, spec):
    rate = spec['sample_rate_hz']
    if int(track['sample_rate']) != rate:
        raise ValueError('AACのレートが登録した信号のレートと一致しません')
    if any(round(end * rate) > len(reference) for _, end in spec['audio_alignment_windows_seconds']):
        raise ValueError('加工前PCMが登録した音声測定窓の末尾に届いていません')
    audio = np.fromfile(folder / 'recording-audio.f32le', dtype='<f4')
    base = Fraction(track['time_base'])
    stamps = [int(frame['best_effort_timestamp']) * base for frame in frames]
    counts = [int(frame['nb_samples']) for frame in frames]
    starts = np.r_[0, np.cumsum(counts)]
    if len(stamps) < 2 or starts[-1] != len(audio) or not np.isfinite(audio).all():
        raise ValueError('音声の復号サンプルとPTSを対応づけられません')
    windows, _, _, _ = recording.correlate_audio(audio, reference, rate, 0, {**spec, 'quiet_windows_seconds': []})
    for window in windows:
        a = round(window['window_seconds'][0] * rate)
        matched = a + round(window['lag_seconds'] * rate)
        block = bisect_right(starts, matched) - 1
        stamp = float(stamps[block] + Fraction(int(matched - starts[block]), rate))
        window.update(decoded_sample_index=matched, matched_pts_seconds=stamp, pts_lag_seconds=stamp - a / rate)
    gaps = [float(b - a - Fraction(count, rate)) for a, b, count in zip(stamps, stamps[1:], counts)]
    checks = {
        'audio_track_and_alignment': (track['codec_name'] == 'aac' and all(b > a for a, b in zip(stamps, stamps[1:]))
                                      and all(w['maximum_correlation'] >= spec['minimum_audio_correlation'] for w in windows)),
    }
    result = {'first_pts_seconds': float(stamps[0]), 'samples': len(audio), 'windows': windows,
              'largest_pts_gap_seconds': max(gaps), 'largest_pts_overlap_seconds': min(gaps),
              'sample_lag_shift_seconds': windows[1]['lag_seconds'] - windows[0]['lag_seconds'],
              'pts_lag_shift_seconds': windows[1]['pts_lag_seconds'] - windows[0]['pts_lag_seconds']}
    return checks, result


def decode_video(frames, track, folder, report, control, spec, *, size=(224, 80)):
    base = Fraction(track['time_base'])
    stamps = [float(int(frame['best_effort_timestamp']) * base) for frame in frames]
    pixels = np.fromfile(folder / 'video-codes.gray', dtype=np.uint8).reshape(-1, 4, 12)
    if len(stamps) != len(pixels) or len(stamps) < 2:
        raise ValueError('映像の復号フレームとPTSを対応づけられません')
    codes = np.sum((pixels[:, (1, 3), :] >= 128) * (1 << np.arange(12)), axis=2).tolist()
    decoded = [{'pts_seconds': stamp, 'wall_ms': wall, 'context_ms': ctx}
               for stamp, (wall, ctx) in zip(stamps, codes)]
    source = {(draw['wallCode'], draw['contextCode']) for draw in report['draws']}
    start, stop = control['hold_wall_ms']
    margin = spec['video_hold_margin_ms']
    held = [frame for frame in decoded if start + margin <= frame['wall_ms'] <= stop - margin]
    before = next((frame for frame in reversed(decoded) if frame['wall_ms'] < start), None)
    after = next((frame for frame in decoded if frame['wall_ms'] > stop), None)
    if before is None or after is None:
        raise ValueError('停止前後を挟む映像フレームがありません')
    checks = {
        'video_track_and_ordered_pts': (track['codec_name'] == 'h264'
                                        and (track['width'], track['height']) == size
                                        and all(b > a for a, b in zip(stamps, stamps[1:]))),
        'video_clocks_match_draws': (all(tuple(code) in source for code in codes)
                                     and all(b[0] >= a[0] and b[1] >= a[1] for a, b in zip(codes, codes[1:]))),
    }
    wall_span = (after['wall_ms'] - before['wall_ms']) / 1000
    context_span = (after['context_ms'] - before['context_ms']) / 1000
    pts_span = after['pts_seconds'] - before['pts_seconds']
    result = {'decoded': decoded, 'during_hold': held, 'before_hold': before, 'after_hold': after,
              'hold_distinct_wall_codes': len({f['wall_ms'] for f in held}),
              'hold_distinct_context_codes': len({f['context_ms'] for f in held}),
              'hold_pts_span_seconds': held[-1]['pts_seconds'] - held[0]['pts_seconds'] if held else None,
              'bracket_wall_span_seconds': wall_span, 'bracket_pts_span_seconds': pts_span,
              'bracket_context_span_seconds': context_span,
              'wall_minus_pts_seconds': wall_span - pts_span}
    return checks, result


def decode_media_files(media, folder, execute, *, include_audio=True):
    metadata = folder / 'ffprobe.json'
    execute(['ffprobe', '-v', 'error', '-show_streams', '-show_frames', '-of', 'json', str(media)], stdout=metadata)
    probe = read_json(metadata)
    expected_kinds = ['audio', 'video'] if include_audio else ['video']
    if sorted(track['codec_type'] for track in probe['streams']) != expected_kinds:
        raise ValueError('予約した動画と実際のトラック構成が一致しません')
    tracks = {track['codec_type']: track for track in probe['streams']}
    frames = {kind: [frame for frame in probe['frames'] if frame['media_type'] == kind] for kind in tracks}
    if include_audio:
        execute(['ffmpeg', '-v', 'error', '-i', str(media), '-map', '0:a:0', '-ac', '1', '-f', 'f32le',
                 str(folder / 'recording-audio.f32le')])
    execute(['ffmpeg', '-v', 'error', '-i', str(media), '-map', '0:v:0', '-filter_threads', '1',
             '-vf', 'crop=192:64:16:0,scale=12:4:flags=neighbor,format=gray', '-fps_mode', 'passthrough',
             '-enc_time_base', 'filter', '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo',
             str(folder / 'video-codes.gray')])
    return tracks, frames


def inspect(capture_folder, folder, report, control, spec, execute, *, include_audio=True):
    tracks, frames = decode_media_files(capture_folder / 'recording.mp4', folder, execute, include_audio=include_audio)
    reference, signal_matches = signal_reference(capture_folder / 'signal.f32le', spec)
    audio_checks, audio = {}, None
    if include_audio:
        audio_checks, audio = decode_audio(frames['audio'], tracks['audio'], reference, folder, spec)
    video_checks, video = decode_video(frames['video'], tracks['video'], folder, report, control, spec)
    return {'signal_matches_equation': signal_matches, **audio_checks, **video_checks}, audio, video


def predictions(row, spec):
    mode, clock, audio, video = (row[k] for k in ('mode', 'graph', 'audio', 'video'))
    tolerance = spec['audio_pause_tolerance_seconds']
    context_hold = clock['held_context_seconds']
    removed_signal = context_hold if mode == 'recorder' else 0
    graph_prediction = (clock['held_context_frames'] == 0 if mode == 'context'
                        else abs(context_hold - clock['hold_ms'] / 1000) <= tolerance)
    result = {'context_clock': graph_prediction,
              'audio_source_lag': all(abs(audio[k] + removed_signal) <= tolerance
                                      for k in ('sample_lag_shift_seconds', 'pts_lag_shift_seconds'))}
    if mode != 'recorder':
        result['video_frames_during_hold'] = video['hold_distinct_wall_codes'] >= spec['video_minimum_context_hold_frames']
    else:
        result['video_frames_during_hold'] = video['hold_distinct_wall_codes'] <= spec['video_maximum_recorder_hold_frames']
    if mode == 'context':
        span = video['hold_pts_span_seconds']
        result['video_shortens_context_hold'] = (span is not None and video['hold_distinct_context_codes'] == 1
                                                 and span <= spec['video_maximum_retained_context_hold_seconds'])
    return result


def measure(case_path, study, capture_root, artifacts, execute):
    if capture_root is None:
        execute(['node', str(CAPTURE), str(case_path), str(artifacts)], stdout=artifacts / 'safari.log')
        capture_root = artifacts
    spec = study['measurement']
    checks, trials = {}, []
    for index, order in enumerate(study['condition_order'], 1):
        for mode in order:
            label = f'{index}-{mode}'
            folder = artifacts / label
            capture_folder = capture_root / label
            row = {'trial': label, 'mode': mode, 'block': index}
            local = {}
            try:
                folder.mkdir(exist_ok=True)
                report = read_json(capture_folder / 'browser.json')
                if report.get('error') or report['stage'] != 'complete':
                    raise ValueError(report.get('error', 'Safariの録画が完了しませんでした'))
                local, row['graph'] = graph(report, mode, spec)
                media_checks, row['audio'], row['video'] = inspect(capture_folder, folder, report, row['graph'], spec, execute)
                local.update(media_checks)
                if all(local.values()):
                    row['predictions'] = predictions(row, spec)
            except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
                local['completed'] = False
                row['error'] = str(error)
            checks.update({f'{label}/{key}': value for key, value in local.items()})
            trials.append(row)
    return {'checks': checks, 'predictions': {row['trial']: row.get('predictions') for row in trials}, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    parser.add_argument('--from-run', help='指定した実行で保存した録画を再解析する')
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = read_json(case_path)
    revision = study['upstream_revision']
    if (not study['condition_order'] or any(len(order) != len(MODES) or set(order) != MODES for order in study['condition_order'])
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('録画条件または固定上流が一致しません')
    previous = study['recording_reference']
    previous_case_path = CASE.parent / previous['case']
    run = run_manifest(previous['run'], read_json(previous_case_path)['id'], revision)
    reference = verified_path(run, 'summary.json')
    summary = read_json(reference)
    if (run[1]['status'] != 'pass' or summary['predictions']['audio_pts_preserves_wall_pause']
            or not summary['predictions']['suspension_frozen_and_resume_consecutive']):
        parser.error('停止を含む歌唱録画の基準結果が揃いません')
    commands = {'safaridriver': ['/usr/bin/safaridriver', '--version'], 'node': ['node', '--version'],
                'ffmpeg': ['ffmpeg', '-version'], 'ffprobe': ['ffprobe', '-version']}
    details = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv],
               **{key: subprocess.check_output(cmd, text=True).splitlines()[0] for key, cmd in commands.items()}}
    inputs = [case_path, previous_case_path, run[0] / 'manifest.json', reference, Path(__file__).resolve(),
              CAPTURE, CAPTURE.with_name('safari-webdriver.mjs'), Path(recording.__file__),
              Path(read_json.__code__.co_filename)]
    capture_root = None
    if args.from_run:
        captured = run_manifest(args.from_run, study['id'], revision)
        if not any(entry['path'] == str(case_path.relative_to(ROOT)) and entry['sha256'] == sha256(case_path)
                   for entry in captured[1]['inputs']):
            parser.error('取得した時点のケース定義と一致しません')
        details['capture_run'] = args.from_run
        inputs.append(captured[0] / 'manifest.json')
        for index, order in enumerate(study['condition_order'], 1):
            for mode in order:
                for name in ('browser.json', 'recording.mp4', 'signal.f32le'):
                    inputs.append(verified_path(captured, f'artifacts/{index}-{mode}/{name}'))
        capture_root = captured[0] / 'artifacts'
    return record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case_path, study, capture_root, artifacts, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
