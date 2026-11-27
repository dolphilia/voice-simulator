"""Safariの歌唱録画でContext停止を挟む音声と映像のPTSを比較する。"""

import argparse
from bisect import bisect_right
from fractions import Fraction
import gzip
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.signal import resample_poly

import measure_worklet_safari_song_resume_order as safari
import measure_worklet_song_recording as recorder
from upstream_baseline import sha256


song = safari.song
realtime = safari.realtime
READ = safari.READ
CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-safari-recording-pause.json'


def decode_recording(path, pcm, output_rate, spec, folder, execute):
    metadata = folder / 'recording-ffprobe.json'
    audio_path = folder / 'recording-audio.f32le'
    bars_path = folder / 'recording-progress.rgb'
    execute(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-show_frames', '-of', 'json', str(path)],
            stdout=metadata)
    report = READ(metadata)
    if sorted(track['codec_type'] for track in report['streams']) != ['audio', 'video']:
        raise ValueError('録画ファイルに音声・映像の1トラックずつが必要です')
    tracks = {track['codec_type']: track for track in report['streams']}
    rate = int(tracks['audio']['sample_rate'])
    execute(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1', '-f', 'f32le', str(audio_path)])
    execute(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0', '-filter_threads', '1',
             '-vf', 'format=rgb24,crop=500:1:110:950', '-fps_mode', 'passthrough',
             '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo', str(bars_path)])
    audio = np.fromfile(audio_path, dtype='<f4')
    stamps = {kind: [frame for frame in report['frames'] if frame['media_type'] == kind] for kind in ('audio', 'video')}
    audio_time_base = Fraction(tracks['audio']['time_base'])
    audio_pts = [int(frame['best_effort_timestamp']) * audio_time_base for frame in stamps['audio']]
    starts = np.r_[0, np.cumsum([int(frame['nb_samples']) for frame in stamps['audio']])]
    if len(audio_pts) < 2 or starts[-1] != len(audio) or not np.isfinite(audio).all():
        raise ValueError('音声PTSを復号PCMに対応づけられません')
    ratio = Fraction(rate, output_rate)
    reference = resample_poly(pcm, ratio.numerator, ratio.denominator) if rate != output_rate else pcm
    windows, _, _, _ = recorder.correlate_audio(audio, reference, rate, 0, {**spec, 'quiet_windows_seconds': []})
    for window in windows:
        source_start = round(window['window_seconds'][0] * rate)
        sample_lag = round(window.pop('lag_seconds') * rate)
        match_index = source_start + sample_lag
        block = bisect_right(starts, match_index) - 1
        tm = float(audio_pts[block] + Fraction(int(match_index - starts[block]), rate))
        window.update(decoded_sample_index=match_index, decoded_sample_lag_seconds=sample_lag / rate,
                      match_pts_seconds=tm, pts_lag_seconds=tm - source_start / rate)
    audio_gaps = [stop - begin - Fraction(int(count), rate)
                  for begin, stop, count in zip(audio_pts, audio_pts[1:], np.diff(starts))]
    greatest_audio_gap = int(np.argmax(audio_gaps))
    audio_summary = {'codec': tracks['audio']['codec_name'], 'rate_hz': rate, 'decoded_samples': len(audio),
                     'first_pts_seconds': float(audio_pts[0]), 'alignment': windows,
                     'lag_shift_seconds': windows[1]['pts_lag_seconds'] - windows[0]['pts_lag_seconds'],
                     'sample_shift_seconds': windows[1]['decoded_sample_lag_seconds'] - windows[0]['decoded_sample_lag_seconds'],
                     'maximum_frame_gap_seconds': float(audio_gaps[greatest_audio_gap]),
                     'maximum_gap_interval_seconds': [float(t) for t in audio_pts[greatest_audio_gap:greatest_audio_gap + 2]]}
    video_time_base = Fraction(tracks['video']['time_base'])
    pts = np.array([float(int(frame['best_effort_timestamp']) * video_time_base) for frame in stamps['video']])
    colors = np.fromfile(bars_path, dtype=np.uint8).reshape(-1, 500, 3)
    if len(pts) != len(colors) or len(pts) < 2:
        raise ValueError('映像PTSと進捗バーの復号フレーム数が一致しません')
    bars = np.count_nonzero(colors[:, :, 1] >= 140, axis=1)
    thresholds = [output_frame * 500 / len(pcm) for output_frame in spec['video_anchors_output_frames']]
    index = [int(np.flatnonzero(bars >= threshold)[0]) for threshold in thresholds if np.any(bars >= threshold)]
    if len(index) != 2:
        raise ValueError('進捗バーが指定の2つの観測位置に届きませんでした')
    greatest_video_gap = int(np.argmax(np.diff(pts)))
    video_summary = {'codec': tracks['video']['codec_name'], 'width': tracks['video']['width'], 'height': tracks['video']['height'],
                     'pts_seconds': pts.tolist(), 'bar_pixels': bars.tolist(), 'anchor_pts_seconds': pts[index].tolist(),
                     'anchor_interval_seconds': float(pts[index[1]] - pts[index[0]]),
                     'maximum_frame_gap_seconds': float(pts[greatest_video_gap + 1] - pts[greatest_video_gap])}
    checks = {'decoded_audio_alignment': all(window['maximum_correlation'] >= spec['minimum_audio_correlation']
                                             for window in windows),
              'ordered_pts': bool(np.all(np.diff(pts) > 0) and all(b > a for a, b in zip(audio_pts, audio_pts[1:])))}
    return checks, audio_summary, video_summary, audio


def measure(study, fixed, spec, reference, upper, wasm, artifacts, execute, bun, image_size):
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    binary_hash = sha256(binary)
    dictionary = {True: sha256(song.DICTIONARY),
                  False: song.bytes_digest(gzip.decompress(song.DICTIONARY.read_bytes())).hexdigest()}
    upper_pcm = np.fromfile(upper, dtype='<f4')
    checks = {'wasm_matches_offline': binary_hash == sha256(wasm),
              'dictionary_matches_upstream': dictionary[True] == sha256(song.UPSTREAM_DICTIONARY)}
    trials = []
    media_spec = study['recording_measurement']
    for number, order in enumerate(study['condition_order'], 1):
        for mode in order:
            label = f'{number}-{mode}'
            folder = artifacts / label
            row = {'trial': label, 'pair': number, 'mode': mode}
            local = {}
            try:
                browser, report, rate, pcm = safari.capture_trial(folder, reference, study, spec, mode, 'direct', execute)
                local, matched, expected = realtime.compare(browser, report, rate, pcm, folder, reference, fixed,
                                                             upper_pcm, dictionary, binary_hash, spec, engine='safari')
                row.update(matched)
                observation = READ(folder / 'startup.json')
                local['trusted_recording_click'] = observation['click']['trusted'] is True
                pause_checks, pause = safari.compare_mid_song_pause(report, observation, mode, study['mid_song_pause'])
                row['pause'] = pause
                local.update(pause_checks)
                recording = report['recording']
                local['recording_complete_on_song_clock'] = (
                    recording['recordingStartContextFrame'] < recording['scheduledContextFrame'] == matched['clock']['start_frame']
                    and recording['recordingEndContextFrame'] >= matched['clock']['start_frame'] + len(expected)
                    and sorted(track['kind'] for track in recording['trackStates']) == ['audio', 'video']
                    and all(track['readyState'] == 'ended' for track in recording['trackStates']))
                media_checks, audio, video, decoded = decode_recording(folder / browser['recordingFilename'], expected, rate,
                                                                      media_spec, folder, execute)
                row.update(recording=recording, audio=audio, video=video)
                local.update(media_checks)
                local['portrait_size_matches'] = (video['width'], video['height']) == image_size
                point = pause.get('pause_output_frame', study['mid_song_pause']['target_output_frame'])
                target_bar = 500 * point / len(pcm)
                matching = np.flatnonzero(np.abs(np.array(video['bar_pixels']) - target_bar) <= media_spec['video_steady_max_pixel_delta'])
                times = video['pts_seconds']
                video['steady_at_pause_pts_seconds'] = [times[i] for i in matching]
                rate = audio['rate_hz']
                sample_point = round(point * rate / spec['sample_rate_hz'])
                split = [sample_point + round(window['decoded_sample_lag_seconds'] * rate) for window in audio['alignment']]
                if 0 <= split[0] < split[1] <= len(decoded):
                    audio['decoded_between_aligned_boundaries_rms'] = float(np.sqrt(np.mean(decoded[split[0]:split[1]] ** 2)))
                audio['aligned_boundary_sample_indices'] = split
            except (OSError, ValueError, TypeError, KeyError, subprocess.CalledProcessError) as error:
                local['capture_and_comparison_completed'] = False
                row['error'] = str(error)
            checks.update({f'{label}/{key}': value for key, value in local.items()})
            trials.append(row)
    pairs = []
    for number, group in safari.startup.complete_pairs(trials, study['condition_order']):
        if not all(checks[f'{row["trial"]}/{key}'] for row in group.values()
                   for key in ('decoded_audio_alignment', 'ordered_pts')):
            continue
        normal, paused = group['continuous'], group['paused']
        pairs.append({'pair': number, 'hold_seconds': paused['pause']['hold_ms'] / 1000,
                      'audio_pts_delta_seconds': paused['audio']['lag_shift_seconds'] - normal['audio']['lag_shift_seconds'],
                      'decoded_sample_delta_seconds': paused['audio']['sample_shift_seconds'] - normal['audio']['sample_shift_seconds'],
                      'video_delta_seconds': paused['video']['anchor_interval_seconds'] - normal['video']['anchor_interval_seconds']})
    complete = len(pairs) == len(study['condition_order'])
    minimum = media_spec['minimum_pause_signature_seconds']
    tolerance = media_spec['maximum_hold_estimate_error_seconds']
    predictions = {f'{key}_preserves_wall_pause': complete and all(
        pair[field] >= minimum and abs(pair[field] - pair['hold_seconds']) <= tolerance for pair in pairs)
        for key, field in (('audio_pts', 'audio_pts_delta_seconds'), ('video', 'video_delta_seconds'))}
    predictions['pre_encoding_pcm_and_states_match_offline'] = complete and all(checks[f'{row["trial"]}/{key}']
        for row in trials for key in ('all_pcm_matches_offline', 'all_sampled_states_and_plan_match_offline'))
    predictions['suspension_frozen_and_resume_consecutive'] = complete and all(
        row['pause']['paused_frame'] == row['pause']['resumed_request_frame']
        and row['pause']['longest_gap_frames'] == [row['pause']['paused_frame'] - spec['quantum'], row['pause']['paused_frame']]
        for row in trials if row['mode'] == 'paused')
    return {'checks': checks, 'predictions': predictions, 'pairs': pairs, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case = args.case.resolve(strict=True)
    study = READ(case)
    cases = CASE.parent
    revision = study['upstream_revision']
    live_path = cases / study['realtime_study']
    live = READ(live_path)
    offline_path = cases / live['offline_study']
    offline_case = READ(offline_path)
    fixed_path = cases / offline_case['capture_case']
    recording_path = cases / study['recording_study']
    pause_path = cases / study['pause_reference']['case']
    fixed, recording, pause_case = (READ(path) for path in (fixed_path, recording_path, pause_path))
    spec = live['measurement']
    if (study['browser_engine'] != 'safari' or study['record_song'] is not True
            or any(item['upstream_revision'] != revision for item in (live, offline_case, fixed, recording, pause_case))
            or any(sorted(pair) != ['continuous', 'paused'] for pair in study['condition_order'])
            or any(pause_case[key] != study[key] for key in ('realtime_study', 'offline_condition', 'mid_song_pause'))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('録画の条件、停止対照、固定上流が一致しません')
    offline = song.run_manifest(live['offline_run'], offline_case['id'], revision)
    upstream = song.run_manifest(offline_case['reference_run'], 'song-voice-fast-constriction-source', revision)
    pause = song.run_manifest(study['pause_reference']['run'], pause_case['id'], revision)
    pause_summary = song.verified_path(pause, 'summary.json')
    if (any(run[1]['status'] != 'pass' for run in (offline, upstream, pause))
            or not READ(pause_summary)['predictions']['observed/wall_gap_at_consecutive_pause_boundary']):
        parser.error('固定上流と生成PCMおよび停止位置の保存結果が揃いません')
    label = study['offline_condition']
    reference = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
        'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
    upper = song.verified_path(upstream, 'artifacts/upstream-pcm.f32')
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    commands = {'safaridriver': ['/usr/bin/safaridriver', '--version'], 'node': ['node', '--version'],
                'bun': [*bun, '--version'], 'ffprobe': ['ffprobe', '-version'], 'ffmpeg': ['ffmpeg', '-version']}
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'browser_engine': 'safari',
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                **{key: subprocess.check_output(command, text=True).splitlines()[0] for key, command in commands.items()}}
    inputs = [case, live_path, offline_path, fixed_path, recording_path, pause_path, pause_summary,
              *(run[0] / 'manifest.json' for run in (offline, upstream, pause)), upper, wasm, *reference.values(),
              Path(__file__).resolve(), safari.CAPTURE, safari.CAPTURE.with_name('safari-webdriver.mjs'),
              *song.web_sources(), *song.shared.candidate_sources(), *(Path(module.__file__) for module in (
                  safari, realtime, recorder, song, song.wasm, song.shared, song.realtime))]
    image_size = tuple(recording['measurement'][key] for key in ('width_px', 'height_px'))
    return song.shared.record_measurement(args.run_id, case, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, spec, reference, upper, wasm, artifacts, execute, bun, image_size),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
