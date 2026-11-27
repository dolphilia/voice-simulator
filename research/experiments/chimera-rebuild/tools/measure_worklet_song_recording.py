"""歌唱の録画をデコードし、加工前PCMと固定上流のClipへ照合する。"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-song-recording.json'
TRACT_CASE = WORKSPACE / 'cases/worklet-song-tract-recording.json'
WEBM_CASE = WORKSPACE / 'cases/worklet-song-recording-webm.json'
VP8_CASE = WORKSPACE / 'cases/worklet-song-recording-vp8.json'
FIREFOX_CASE = WORKSPACE / 'cases/worklet-song-recording-firefox.json'
CAPTURE = WEB / 'tools/capture-song-recording.mjs'


def correlate_audio(audio, reference, rate, audio_start, spec):
    lo, hi = (round(t * rate) for t in spec['audio_offset_search_seconds'])
    windows = []
    for start, stop in spec['audio_alignment_windows_seconds']:
        a, b = round(start * rate), round(stop * rate)
        source = reference[a:b].astype(float)
        first, last = max(0, a + lo), min(len(audio) - len(source), a + hi)
        if not len(source) or first > last or not np.any(source):
            raise ValueError('デコード音声に比較する観測区間がありません')
        search = audio[first:last + len(source)].astype(float)
        width = len(source)
        # 累積和の差では、振幅が大きく変わる録音の無音付近で桁落ちが起きる。
        energy = np.convolve(search ** 2, np.ones(width), mode='valid')
        normalization = np.sqrt(energy * np.dot(source, source))
        dot = np.correlate(search, source, mode='valid')
        corr = np.divide(dot, normalization, out=np.zeros_like(dot), where=normalization > 0)
        best = int(np.argmax(corr))
        active_rms = float(np.sqrt(np.mean(search[best:best + width] ** 2)))
        windows.append({'window_seconds': [start, stop], 'maximum_correlation': float(np.clip(corr[best], -1, 1)),
                        'lag_seconds': (first + best - a) / rate + audio_start, 'decoded_rms': active_rms})
    lags = [w['lag_seconds'] for w in windows]
    lag = float(np.median(lags))
    active = float(np.mean([w['decoded_rms'] for w in windows]))
    quiet = []
    for start, stop in spec['quiet_windows_seconds']:
        a, b = [round((t + lag - audio_start) * rate) for t in (start, stop)]
        ratio = float(np.sqrt(np.mean(audio[a:b].astype(float) ** 2)) / active) if 0 <= a < b <= len(audio) and active else None
        quiet.append({'window_seconds': [start, stop], 'rms_ratio_to_active': ratio})
    return windows, lag, max(lags) - min(lags), quiet


def decode_clip(path, reference, spec, artifacts, execute):
    name = path.stem
    probe = artifacts / f'{name}-ffprobe.json'
    wave = artifacts / f'{name}-decoded.f32'
    video = artifacts / f'{name}-marker.rgb'
    execute(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-show_frames',
             '-of', 'json', str(path)], stdout=probe)
    report = wasm.read_json(probe)
    streams = report['streams']
    if sorted(s['codec_type'] for s in streams) != ['audio', 'video']:
        raise ValueError(f'{name} に音声と映像が1トラックずつ必要です')
    tracks = {s['codec_type']: s for s in streams}
    rate = int(tracks['audio']['sample_rate'])
    if rate != spec['output_rate_hz']:
        raise ValueError(f'{name} のデコード音声のレートが事前登録と違います')
    execute(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:a:0', '-ac', '1',
             '-f', 'f32le', str(wave)])
    execute(['ffmpeg', '-v', 'error', '-i', str(path), '-map', '0:v:0',
             '-vf', 'crop=32:32:200:578,scale=1:1:flags=area,format=rgb24', '-fps_mode', 'passthrough',
             '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo', str(video)])
    samples = np.fromfile(wave, dtype='<f4')
    if not np.isfinite(samples).all():
        raise ValueError(f'{name} のデコード音声に非有限値があります')
    stamp = {kind: [frame for frame in report['frames'] if frame['media_type'] == kind]
             for kind in ('audio', 'video')}
    times = np.array([float(frame['best_effort_timestamp_time']) for frame in stamp['video']])
    rgb = np.fromfile(video, dtype=np.uint8).astype(int).reshape(-1, 3)
    if len(times) != len(rgb) or len(times) < 2:
        raise ValueError(f'{name} の画像と映像タイムスタンプの個数が一致しません')
    r, g, b = rgb.T
    phases = np.where((g - r > 40) & (g - b > 30), 1,
                      np.where((r - g > 40) & (r - b > 80), 2, 0))
    edges = np.r_[0, 1 + np.flatnonzero(phases[1:] != phases[:-1])]
    observed = [int(phases[i]) for i in edges]
    marker_times = {phase: float(times[i]) for i, phase in zip(edges, observed, strict=True) if phase}
    audio_start = float(stamp['audio'][0]['best_effort_timestamp_time'])
    audio_last = stamp['audio'][-1]
    audio_end = float(audio_last['best_effort_timestamp_time']) + int(audio_last['nb_samples']) / rate
    gaps = np.diff(times)
    largest_gap = int(gaps.argmax())
    first_late = np.flatnonzero(gaps > spec['maximum_video_frame_gap_seconds'])
    video_end = float(times[-1] + np.median(gaps))
    effective_fps = len(gaps) / (times[-1] - times[0])
    windows, lag, variation, quiet = correlate_audio(samples, reference, rate, audio_start, spec)
    marker_errors = [marker_times.get(i + 1) - lag - beat if i + 1 in marker_times else None
                     for i, beat in enumerate(spec['beat_seconds'])]
    bounds = spec['relative_audio_end_seconds_bounds']
    checks = {
        'portrait_video': (tracks['video']['width'], tracks['video']['height']) == (spec['width_px'], spec['height_px']),
        'video_cadence': bool(effective_fps >= spec['minimum_effective_video_fps']
                              and gaps.min() > 0 and gaps.max() <= spec['maximum_video_frame_gap_seconds']),
        'audio_matches_source': all(w['maximum_correlation'] >= spec['minimum_audio_correlation'] for w in windows)
            and variation <= spec['maximum_audio_lag_variation_seconds'],
        'quiet_regions': all(q['rms_ratio_to_active'] is not None
                             and q['rms_ratio_to_active'] <= spec['maximum_quiet_to_active_rms_ratio'] for q in quiet),
        'two_markers_in_order': observed == [0, 1, 2],
        'av_sync': all(e is not None and abs(e) <= spec['maximum_marker_error_seconds'] for e in marker_errors),
        'decoded_ends': (bounds[0] <= audio_end - lag <= bounds[1]
                         and abs(audio_end - video_end) <= spec['maximum_audio_video_end_difference_seconds']),
    }
    return checks, {
        'container': report['format']['format_name'],
        'video_codec': tracks['video']['codec_name'], 'audio_codec': tracks['audio']['codec_name'],
        'audio_channels': tracks['audio']['channels'], 'audio_samples_after_decode': len(samples),
        'audio_start_seconds': audio_start, 'audio_end_seconds': audio_end,
        'video_start_seconds': float(times[0]), 'video_end_seconds': video_end,
        'audio_end_from_sample_count_seconds': audio_start + len(samples) / rate,
        'audio_end_relative_to_source_seconds': audio_end - lag,
        'video_frames': len(times), 'effective_video_fps': float(effective_fps), 'maximum_video_gap_seconds': float(gaps.max()),
        'maximum_video_gap_interval_seconds': times[largest_gap:largest_gap + 2].tolist(),
        'first_video_gap_over_limit_interval_seconds': times[first_late[0]:first_late[0] + 2].tolist() if len(first_late) else None,
        'alignment_windows': windows, 'lag_seconds': lag, 'lag_variation_seconds': variation, 'quiet_windows': quiet,
        'video_marker_pts_seconds': marker_times, 'visual_minus_audio_beat_seconds': marker_errors,
    }


def measure(case, song, source, prior, bun, artifacts, execute, *, tract=None, recording_prior=None,
            webm=None, mp4_prior=None, vp8=None, vp9_prior=None, firefox=None, chrome_prior=None):
    spec = case['measurement']
    execute([*bun, 'test', 'tests/singing-live.test.ts', '-t', "a run's hooks"],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-singing-hooks.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    module = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, module)
    fixed_pcm = verified_path(prior, 'artifacts/upstream-pcm.f32')
    capture = ['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM), str(fixed_pcm)]
    if tract:
        capture.append(str(TRACT_CASE))
    if webm:
        capture.append(str(WEBM_CASE))
    if vp8:
        capture.append(str(VP8_CASE))
    if firefox:
        capture.extend(['--firefox-case', str(FIREFOX_CASE)])
    execute(capture)
    browser = wasm.read_json(artifacts / 'recording-browser.json')
    recording = wasm.read_json(artifacts / 'recorded-input.json')
    cli = artifacts / 'cli.wav'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
             'render-pcm', str(source), str(cli), str(artifacts / 'cli.csv'), '128'])
    rate, pcm = wavfile.read(artifacts / 'recorded-input.wav')
    cli_rate, cli_pcm = wavfile.read(cli)
    upper_pcm = np.fromfile(fixed_pcm, dtype='<f4')
    if rate != cli_rate or rate != spec['output_rate_hz'] or any(
            data.shape != (spec['output_frames'],) or data.dtype != np.float32 or not np.isfinite(data).all()
            for data in (pcm, cli_pcm, upper_pcm)):
        raise ValueError('加工前PCMのレート・長さ・型・有限性が事前登録と違います')
    clocks = recording['recording']
    actual = recording['realtime']
    candidate = browser['candidate']
    upper = browser['upstream']
    coded = {}
    evidence = {}
    for name, filename, raw in [('candidate', candidate['name'], pcm), ('upstream', upper['saved']['name'], upper_pcm)]:
        coded[name], evidence[name] = decode_clip(artifacts / filename, raw, spec, artifacts, execute)
    media = evidence['candidate']
    upper_encoded = evidence['upstream']
    beats = np.asarray(spec['beat_seconds']) * rate
    actual_frames = [b['contextFrame'] - clocks['scheduledContextFrame'] for b in clocks['drawnBeats']]
    guard = 2 * rate / spec['target_video_fps']
    pcm_comparison = wasm.compare_pcm(pcm, cli_pcm, 0)
    upper_comparison = wasm.compare_pcm(pcm, upper_pcm, wasm.read_json(source)['measurement']['pcm_absolute_tolerance'])
    tracks = candidate['takes']
    cancelled = tracks[1]
    upper_takes = upper['takes']
    n_track_ids = len({t['id'] for take in tracks for t in take['tracks']})
    upstream_audio_ids = {t['id'] for take in upper_takes for t in take['tracks'] if t['kind'] == 'audio'}
    marker_deltas = [a - b if a is not None and b is not None else None for a, b in zip(
        media['visual_minus_audio_beat_seconds'], upper_encoded['visual_minus_audio_beat_seconds'], strict=True)]
    reference_wav = verified_path(prior, 'artifacts/pcm-128.wav')
    result = {
        'checks': {
            'raw_pcm_exact': pcm_comparison['first_bit_difference_frame'] is None
                and sha256(artifacts / 'recorded-input.wav') == sha256(reference_wav),
            'raw_upstream_pcm': upper_comparison['first_frame_over_tolerance'] is None,
            'input_output_clock': (recording['input']['lyrics'] == wasm.read_json(source)['song_voice']['score']['lyrics']
                and [n['beat_seconds'] for n in recording['song']['plan']['notes']] == spec['beat_seconds']
                and clocks['scheduledContextFrame'] == actual['scheduledContextFrame'] == recording['firstContextFrame']
                and recording['discontinuities'] == 0 and recording['framesRendered'] == spec['output_frames']
                and recording['shortestQuantum'] == recording['longestQuantum']
                    == song['measurement']['expected_render_quantum_frames']),
            'marker_render_clock': len(actual_frames) == len(beats)
                and bool(np.all(np.asarray(actual_frames) - beats >= 0)
                         and np.all(np.asarray(actual_frames) - beats < guard)),
            'browser_and_file': (not candidate['errors'] and not upper['errors'] and candidate['playback']['error'] is None
                and candidate['playback']['width'] == spec['width_px'] and candidate['playback']['height'] == spec['height_px']
                and candidate['servedWasmSha256'] == sha256(module) and clocks['targetVideoFps'] == spec['target_video_fps']),
            'candidate_finish_cancel_and_restart': (candidate['cancelledWithoutFile'] and n_track_ids == 6
                and candidate['contexts'] == ['closed'] * 3
                and all(take['stopped'] is not None and take['state'] == 'inactive' and sum(take['chunks']) > 0
                        and sorted((t['kind'], t['readyState']) for t in take['tracks']) == [('audio', 'ended'), ('video', 'ended')]
                        for take in tracks)
                and cancelled['requested'] - cancelled['started'] >= 1000 * spec['cancel_after_recording_seconds']),
            'candidate_cancel_during_prepare': (candidate['cancelledWhileStarting'] and len(tracks) == 3
                and candidate['closedContexts'] == ['closed'] * 4),
            'upstream_releases_only_owned_tracks': (upper['saved']['ownerCleared'] and upper['cancelled']['ownerCleared']
                and len(upper_takes) == 2 and all(take['state'] == 'inactive'
                        and take['stopped'] is not None
                        and sorted((t['kind'], t['readyState']) for t in take['tracks']) == [('audio', 'live'), ('video', 'ended')]
                        for take in upper_takes)
                and len(upstream_audio_ids) == 1),
            'av_sync_matches_upstream': all(e is not None and abs(e) <= spec['maximum_candidate_upstream_marker_difference_seconds']
                                             for e in marker_deltas),
            **{f'{name}_{key}': value for name, results in coded.items() for key, value in results.items()},
        },
        'browser': browser['version'], 'raw_pcm': pcm_comparison, 'raw_upstream_pcm': upper_comparison,
        'recording_clock': clocks, 'marker_context_deltas_frames': (np.asarray(actual_frames) - beats).tolist()
            if len(actual_frames) == len(beats) else None,
        'codec_comparison': evidence, 'candidate_minus_upstream_marker_error_seconds': marker_deltas,
        'upstream_drain_wait_ms': upper['drainMs'],
        'cancel_elapsed_seconds': (cancelled['requested'] - cancelled['started']) / 1000,
    }
    if tract:
        from measure_recorded_tract import compare_recorded_tract

        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'geometry_continuity'],
                cwd=UPSTREAM, stdout=artifacts / 'upstream-geometry.log')
        checks, shape = compare_recorded_tract(
            tract, source, recording, artifacts / candidate['name'], media, fixed_pcm, artifacts, execute)
        no_tract_wave = verified_path(recording_prior, 'artifacts/recorded-input.wav')
        checks['tract_recording_keeps_baseline_pcm'] = sha256(no_tract_wave) == sha256(artifacts / 'recorded-input.wav')
        result['checks'].update(checks)
        result['recorded_tract'] = shape
    if webm:
        from measure_webm_recording import compare_vp9, measure_webm_clips

        summary, wave = (verified_path(mp4_prior, name) for name in ('summary.json', 'artifacts/recorded-input.wav'))
        settings = webm['measurement'] | (vp8['measurement'] if vp8 else {})
        checks, result['webm'] = measure_webm_clips(
            {**webm, 'measurement': settings}, browser, evidence, wasm.read_json(summary), wave, artifacts, execute)
        result['checks'].update(checks)
    if vp8:
        summary, wave = (verified_path(vp9_prior, name) for name in ('summary.json', 'artifacts/recorded-input.wav'))
        checks, result['vp8_against_vp9'] = compare_vp9(vp8, evidence, wasm.read_json(summary), wave, artifacts)
        result['checks'].update(checks)
    if firefox:
        from measure_firefox_recording import measure_firefox_clips

        wave, observation = (verified_path(chrome_prior, f'artifacts/recorded-input.{suffix}') for suffix in ('wav', 'json'))
        checks, result['firefox'] = measure_firefox_clips(firefox, browser, evidence, recording, wave, observation, artifacts, execute)
        result['checks'].update(checks)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--tract', action='store_true', help='動画内の三次元断面を同じ時刻の測定線と比較する')
    formats = parser.add_mutually_exclusive_group()
    formats.add_argument('--webm', action='store_true', help='三次元断面を含むVP9/Opusの録画を固定MP4と比較する')
    formats.add_argument('--vp8', action='store_true', help='三次元断面を含むVP8/Opusの録画を固定VP9・MP4と比較する')
    formats.add_argument('--firefox', action='store_true', help='Firefoxが選ぶ形式で三次元断面を録画し、Chromiumと照合する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    song_path, live_path = (WORKSPACE / 'cases' / case[key] for key in ('song_case', 'live_case'))
    song, live = (wasm.read_json(path) for path in (song_path, live_path))
    prior = run_manifest(case['reference']['run'], live['id'], rev)
    manifest = prior[0] / 'manifest.json'
    if prior[1]['status'] != 'pass' or sha256(manifest) != case['reference']['manifest_sha256']:
        parser.error('登録した実時間歌唱の基準マニフェストを照合できません')
    source = WORKSPACE / 'cases' / song['song_voice_case']
    fixed_pcm, reference_wav = (verified_path(prior, path) for path in ('artifacts/upstream-pcm.f32', 'artifacts/pcm-128.wav'))
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_paths = ['src/song/record.ts', 'src/ui/render/vector.ts', 'src/ui/colors.ts',
                      'src/ui/components/SingPanel.tsx', 'src/ui/singing.ts', 'src/audio/AudioEngine.ts',
                      'tests/singing-live.test.ts']
    inputs = [CASE, song_path, live_path, source, CAPTURE, CAPTURE.with_name('observe-song-recorder.mjs'),
              manifest, fixed_pcm, reference_wav,
              Path(__file__), Path(shared.__file__), Path(wasm.__file__), *web_sources(), *shared.candidate_sources()]
    webm_path = VP8_CASE if args.vp8 else WEBM_CASE if args.webm else None
    tract = wasm.read_json(TRACT_CASE) if args.tract or webm_path or args.firefox else None
    recording_prior = None
    if tract:
        if tract['recording_case'] != CASE.name or tract['upstream_revision'] != rev:
            parser.error('録画の声道比較ケースが参照する固定版がありません')
        recording_prior = run_manifest(tract['reference']['recording_run'], case['id'], rev)
        baseline = recording_prior[0] / 'manifest.json'
        if recording_prior[1]['status'] != 'pass' or sha256(baseline) != tract['reference']['manifest_sha256']:
            parser.error('登録した録画の基準マニフェストを照合できません')
        inputs.extend([TRACT_CASE, baseline, verified_path(recording_prior, 'artifacts/recorded-input.wav'),
                       *(WORKSPACE / 'tools' / filename for filename in (
                           'measure_recorded_tract.py', 'measure_worklet_tract_3d.py', 'measure_worklet_tract_profile.py',
                           'measure_grid.py', 'measure_sagittal.py', 'measure_bilabial_stop.py', 'upstream_bilabial_probe.rs'))])
        upstream_paths.extend(['src/ui/components/AnatomyView3D.tsx', 'src/worklet/processor.ts',
                               'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/anatomy/human.rs',
                               'crates/chimera/tests/geometry_continuity.rs'])
    webm = wasm.read_json(WEBM_CASE) if webm_path else None
    mp4_prior = None
    if webm:
        if (webm['recording_case'], webm['tract_case'], webm['upstream_revision']) != (CASE.name, TRACT_CASE.name, rev):
            parser.error('WebMケースの録画・声道・上流版が一致しません')
        mp4_prior = run_manifest(webm['reference']['mp4_run'], tract['id'], rev)
        mp4_manifest = mp4_prior[0] / 'manifest.json'
        if mp4_prior[1]['status'] != 'pass' or sha256(mp4_manifest) != webm['reference']['manifest_sha256']:
            parser.error('登録したMP4の基準マニフェストを照合できません')
        inputs.extend([WEBM_CASE, Path(__file__).with_name('measure_webm_recording.py'), mp4_manifest,
                       *(verified_path(mp4_prior, name) for name in ('summary.json', 'artifacts/recorded-input.wav'))])
    vp8 = wasm.read_json(VP8_CASE) if args.vp8 else None
    vp9_prior = None
    if vp8:
        if (vp8['base_case'], vp8['upstream_revision']) != (WEBM_CASE.name, rev):
            parser.error('VP8ケースの基準ケースと上流版が一致しません')
        vp9_prior = run_manifest(vp8['reference']['vp9_run'], webm['id'], rev)
        vp9_manifest = vp9_prior[0] / 'manifest.json'
        if vp9_prior[1]['status'] != 'pass' or sha256(vp9_manifest) != vp8['reference']['manifest_sha256']:
            parser.error('登録したVP9の基準マニフェストを照合できません')
        inputs.extend([VP8_CASE, vp9_manifest,
                       *(verified_path(vp9_prior, name) for name in ('summary.json', 'artifacts/recorded-input.wav'))])
    firefox = wasm.read_json(FIREFOX_CASE) if args.firefox else None
    chrome_prior = None
    if firefox:
        if (firefox['recording_case'], firefox['tract_case'], firefox['upstream_revision'], firefox['browser_engine']) != (
                CASE.name, TRACT_CASE.name, rev, 'firefox'):
            parser.error('Firefoxケースの録画・声道・上流版またはブラウザが一致しません')
        chrome_prior = run_manifest(firefox['reference']['chromium_run'], wasm.read_json(VP8_CASE)['id'], rev)
        chrome_manifest = chrome_prior[0] / 'manifest.json'
        if chrome_prior[1]['status'] != 'pass' or sha256(chrome_manifest) != firefox['reference']['manifest_sha256']:
            parser.error('登録したChromiumの基準マニフェストを照合できません')
        inputs.extend([FIREFOX_CASE, Path(__file__).with_name('measure_firefox_recording.py'),
                       Path(__file__).with_name('measure_webm_recording.py'), chrome_manifest,
                       *(verified_path(chrome_prior, f'artifacts/recorded-input.{suffix}') for suffix in ('wav', 'json'))])
    details = {
        'case_id': (firefox or vp8 or webm or tract or case)['id'], 'upstream_revision': rev, 'input_root': '$REPOSITORY',
        'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upstream_paths},
        'browser_launch': {'executable_override': os.environ.get('CHIMERA_CHROMIUM'),
                           'graphics_override': os.environ.get('CHIMERA_RECORDING_GRAPHICS'),
                           'playwright_browsers_path': os.environ.get('PLAYWRIGHT_BROWSERS_PATH')},
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
        'ffmpeg': subprocess.check_output(['ffmpeg', '-version'], text=True).splitlines()[0],
        'ffprobe': subprocess.check_output(['ffprobe', '-version'], text=True).splitlines()[0],
    }
    return shared.record_measurement(
        args.run_id, FIREFOX_CASE if firefox else webm_path or (TRACT_CASE if tract else CASE), inputs, details,
        lambda out, run: measure(case, song, source, prior, bun, out, run, tract=tract, recording_prior=recording_prior,
                                 webm=webm, mp4_prior=mp4_prior, vp8=vp8, vp9_prior=vp9_prior,
                                 firefox=firefox, chrome_prior=chrome_prior),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
