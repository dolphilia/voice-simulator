"""固定上流の3D歌唱録画を、描画・調音の時計と照合する。"""

import argparse
import base64
import os
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.signal import correlate, find_peaks

import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-song-recording-upstream-head.json'
CAPTURE = WEB / 'tools/capture-upstream-head-recording.mjs'


def active_pitch(samples, rate):
    signal = samples.astype(float) - np.mean(samples, dtype=np.float64)
    periodic = correlate(signal, signal, mode='full', method='fft')[len(signal) - 1:]
    if periodic[0] <= 0:
        return None
    # 比較対象のテレメトリに依存せず、成人男性の発声範囲で最初の強い周期を求める。
    lo, hi = round(rate / 360), round(rate / 70)
    peaks, _ = find_peaks(periodic[lo - 1:hi + 2])
    peaks += lo - 1
    if not len(peaks) or periodic[peaks].max() < periodic[0] * 0.5:
        return None
    lag = int(peaks[periodic[peaks] >= periodic[peaks].max() * 0.92][0])
    left, center, right = periodic[lag - 1:lag + 2]
    fraction = (left - right) / (2 * (left - 2 * center + right))
    return float(rate / (lag + fraction))


def align_audio(samples, rate, audio_start, browser, spec):
    probe = [row for row in browser['telemetry'] if row['owner'] == 1]
    clock, engine_rms = np.array([(row['clock'], row['outRms']) for row in probe]).T
    origin = dict(browser['origins'])[1]['voiceClock']
    if origin is None:
        origin = clock[0] - (probe[0]['atMs'] - dict(browser['origins'])[1]['atMs']) / 1000
    # 同じ長さの固定窓で、復号波形の包絡をWorkletが報告する出力RMSに整列する。
    hop = round(rate * 0.02)
    chunks = samples[:len(samples) // hop * hop].reshape(-1, hop)
    audio_rms = np.sqrt(np.mean(chunks.astype(float) ** 2, axis=1))
    elapsed = audio_start + (np.arange(len(chunks)) + 0.5) * hop / rate
    bound = spec['maximum_envelope_shift_seconds']
    offsets = np.arange(-bound, bound + 0.002, 0.002)
    valid = (origin + elapsed - bound >= clock[0]) & (origin + elapsed + bound <= clock[-1])
    if not valid.any():
        raise ValueError('音声とテレメトリに共通の比較区間がありません')
    correlations = np.array([
        np.corrcoef(audio_rms[valid], np.interp(origin + elapsed[valid] - shift, clock, engine_rms))[0, 1]
        for shift in offsets
    ])
    if not np.isfinite(correlations).all():
        raise ValueError('復号音声またはテレメトリの包絡が定数です')
    peak = int(correlations.argmax())
    shift = float(offsets[peak])
    heads = [row['tele'] for row in browser['head'] if row['owner'] == 1 and row['tele']]
    notes = browser['plans'][0]['notes']
    comparisons = []
    for index in spec['pitch_notes']:
        note = notes[index]
        voice_time = (note['t0'] + note['t1']) / 2
        duration = 0.12
        begin, end = [round((voice_time - origin + shift + t - audio_start) * rate)
                      for t in (-duration / 2, duration / 2)]
        selected = [row for row in heads if abs(row['clock'] - voice_time) <= duration / 2 and row['voicing'] >= 0.8]
        f0 = float(np.median([row['f0'] for row in selected])) if selected else None
        decoded = active_pitch(samples[begin:end], rate) if 0 <= begin < end <= len(samples) else None
        cents = float(1200 * np.log2(decoded / f0)) if decoded and f0 else None
        comparisons.append({'note_index': index, 'midi': note['midi'], 'head_samples': len(selected),
                            'voice_clock_seconds': voice_time, 'decoded_pts_seconds': voice_time - origin + shift,
                            'head_f0_hz': f0, 'decoded_f0_hz': decoded, 'difference_cents': cents})
    return {'voice_clock_at_first_copy': origin, 'decoded_audio_delay_seconds': shift,
            'envelope_windows': int(valid.sum()), 'envelope_correlation': float(correlations[peak]),
            'peak_interior': 0 < peak < len(offsets) - 1, 'pitch_windows': comparisons}


def video_comparison(images, pts, samples, spec):
    width, height = spec['frame_comparison_size_px']
    # Clipの下部150画素には別にロゴが付く。頭部の領域だけを比較する。
    limit = round(height * (1280 - 150) / 1280)
    comparisons = []
    snapshots = []
    for item in samples:
        expected = np.frombuffer(base64.b64decode(item['rgba']), dtype=np.uint8).reshape(height, width, 4)[:limit, :, :3]
        region = np.flatnonzero(np.abs(pts - pts[0] - item['elapsed']) <= spec['frame_search_tolerance_seconds'])
        if not len(region):
            raise ValueError('Canvasの採取時刻付近に復号画像がありません')
        distances = np.mean(np.abs(images[region, :limit].astype(float) - expected), axis=(1, 2, 3))
        best = int(distances.argmin())
        frame = int(region[best])
        comparisons.append({'copy_elapsed_seconds': item['elapsed'], 'head_frame': item['head'],
                            'video_frame': frame, 'video_pts_seconds': float(pts[frame]),
                            'mean_rgb_error': float(distances[best]), 'head_nonblack_pixels': int((expected.max(axis=2) > 32).sum())})
        snapshots.append(expected)
    changed = any(np.mean(np.abs(a.astype(float) - b)) >= 0.5 for a, b in zip(snapshots, snapshots[1:]))
    return comparisons, changed


def clip_lifecycle(browser, settings):
    head = browser['head']
    takes = browser['recorder']['takes']
    copies = browser['copies']
    copied_by_take = [[row for row in copies if row['take'] == take] for take in (1, 2)]
    phases = browser['phase']

    def clean(row):
        return not (row['calipers'] or row['grid'] or row['readouts'])

    def visible(first, last):
        return any(row['owner'] is None and row['calipers'] and row['grid'] and 'F1' in row['readouts']
                   for row in head[first:last])

    def expected_placement(item):
        w, h = item['source']
        scale = min(720 / w, (1280 - 150) / h)
        return np.allclose(item['placement'], [(720 - w * scale) / 2, (1280 - 150 - h * scale) / 2, w * scale, h * scale],
                           rtol=0, atol=1e-9)

    audio_tracks = [track['id'] for take in takes for track in take['tracks'] if track['kind'] == 'audio']
    video_tracks = [track['id'] for take in takes for track in take['tracks'] if track['kind'] == 'video']
    lead = [next((i for i, copy in enumerate(trial) if head[copy['head']]['owner'] == take), len(trial))
            for take, trial in enumerate(copied_by_take, start=1)]
    checks = {
        'same_audio_track_and_released_video': len(takes) == 2 and len(audio_tracks) == len(video_tracks) == 2
            and len(set(audio_tracks)) == 1 and len(set(video_tracks)) == 2
            and all(take['state'] == 'inactive' and take['started'] is not None and take['stopped'] >= take['requested']
                    and sorted((x['kind'], x['readyState']) for x in take['tracks']) == [('audio', 'live'), ('video', 'ended')]
                    for take in takes),
        'finish_then_cancel': browser['cancelledWithoutFile'] and phases['finished']['owner'] is None
            and phases['beforeCancel']['owner'] == 2 and phases['cancelled']['owner'] is None
            and bool(copied_by_take[1]) and copied_by_take[1][-1]['elapsed'] >= settings['cancel_after_seconds'],
        'visible_before_after_and_after_cancel': visible(0, phases['before']['headFrames'])
            and visible(phases['finished']['headFrames'] - 1, phases['restored']['headFrames'])
            and visible(phases['cancelled']['headFrames'] - 1, len(head)),
        'owned_heads_hide_measurements': all(any(row['owner'] == take for row in head) for take in (1, 2))
            and all(clean(row) for row in head if row['owner'] is not None),
        'clip_copies_actual_head_and_keeps_fit': bool(copies) and all(expected_placement(row) for row in copies)
            and all(start < len(trial) and all(head[row['head']]['owner'] == take and clean(head[row['head']])
                    for row in trial[start:]) for take, (start, trial) in enumerate(zip(lead, copied_by_take, strict=True), start=1)),
    }
    return checks, {'head_draws': len(head), 'copies_per_take': [len(trial) for trial in copied_by_take],
                    'copies_before_first_clean_head': lead,
                    'first_copy_heads': [head[trial[0]['head']] if trial else None for trial in copied_by_take],
                    'first_clean_copy_elapsed_seconds': [trial[i]['elapsed'] if i < len(trial) else None
                                                         for i, trial in zip(lead, copied_by_take, strict=True)],
                    'phases': phases}


def measure(spec, bun, artifacts, execute):
    settings = spec['measurement']
    execute([*bun, 'run', 'build'], cwd=UPSTREAM, stdout=artifacts / 'upstream-build.log')
    execute([*bun, 'test', 'tests/singing-live.test.ts', '-t', "a run's hooks"], cwd=UPSTREAM)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'head-recording-browser.json')
    clip = artifacts / browser['filename']
    probe_path = artifacts / 'decoded-probe.json'
    execute(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-show_frames', '-of', 'json', str(clip)], stdout=probe_path)
    probe = read_json(probe_path)
    audio, video = sorted(probe['streams'], key=lambda s: s['codec_type'])
    rate = int(audio['sample_rate'])
    af = [row for row in probe['frames'] if row['media_type'] == 'audio']
    vf = [row for row in probe['frames'] if row['media_type'] == 'video']
    pts = np.array([float(row['best_effort_timestamp_time']) for row in vf])
    audio_start = float(af[0]['best_effort_timestamp_time'])
    audio_end = float(af[-1]['best_effort_timestamp_time']) + int(af[-1]['nb_samples']) / rate
    video_end = float(pts[-1] + np.median(np.diff(pts)))
    fps = (len(pts) - 1) / (pts[-1] - pts[0])
    width, height = settings['frame_comparison_size_px']
    pcm = artifacts / 'decoded-audio.f32'
    rgb = artifacts / 'decoded-small.rgb'
    execute(['ffmpeg', '-v', 'error', '-i', str(clip), '-map', '0:a:0', '-ac', '1', '-f', 'f32le', str(pcm)])
    execute(['ffmpeg', '-v', 'error', '-i', str(clip), '-map', '0:v:0',
             '-vf', f'scale={width}:{height}:flags=area,format=rgb24', '-fps_mode', 'passthrough',
             '-threads', '1', '-c:v', 'rawvideo', '-f', 'rawvideo', str(rgb)])
    execute(['ffmpeg', '-v', 'error', '-i', str(clip), '-frames:v', '2', str(artifacts / 'decoded-lead-%02d.png')])
    images = np.fromfile(rgb, dtype=np.uint8).reshape(-1, height, width, 3)
    decoded = np.fromfile(pcm, dtype='<f4')
    if len(images) != len(pts) or not np.isfinite(decoded).all():
        raise ValueError('復号された映像・音声が観測列と一致しません')
    life, drawing = clip_lifecycle(browser, settings)
    pixels, changed = video_comparison(images, pts, browser['samples'], settings)
    timing = align_audio(decoded, rate, audio_start, browser, settings)
    plan = browser['plans'][0]
    tune = browser['tune']
    notes = plan['notes']
    score = sum(tune['phrases'], [])
    starts = plan['t0'] + 0.35 + np.r_[0, np.cumsum([beats for _, beats in score[:-1]])] * 60 / tune['bpm']
    main_heads = [row['tele'] for row in browser['head'] if row['owner'] == 1 and row['tele']]
    key = browser['input']['key']
    voice = browser['input']
    inputs = spec['input']
    guards = {
        'served_wasm_matches_build': browser['wasmSha256'] == sha256(UPSTREAM / 'src/wasm/chimera.wasm'),
        'normal_song_and_view': voice['mode'] == inputs['upstream_mode'] and voice['tune'] == inputs['upstream_tune']
            and voice['view']['threeD'] and voice['lyrics'] == inputs['lyrics']
            and voice['tempo'] == inputs['tempo_multiplier'] and key == 0
            and voice['body'] == {'female': 0, 'child': 0} and not browser['errors'] and browser['engineError'] is None,
        'schedule_matches_score': len(browser['plans']) == 2 and [trial['owner'] for trial in browser['plans']] == [1, 2]
            and [note['midi'] for note in notes] == [midi + 12 * tune['octave']['male'] + key for midi, _ in score]
            and np.allclose([note['t0'] for note in notes], starts, atol=1e-10, rtol=0)
            and np.allclose([note['t1'] - note['t0'] for note in notes],
                            [beats * 60 / tune['bpm'] - 0.02 for _, beats in score], atol=1e-10, rtol=0),
        'head_uses_live_articulation': sum(row['voicing'] >= 0.8 for row in main_heads) > 50
            and len({tuple(row['artic']) for row in main_heads}) > 50
            and all(len(row['artic']) == 17 and all(np.isfinite(row['artic'])) for row in main_heads),
        'decoded_portrait_with_audio': (video['width'], video['height']) == (720, 1280)
            and len(decoded) == sum(int(row['nb_samples']) for row in af) and fps >= settings['minimum_decoded_fps']
            and abs(audio_end - video_end) <= settings['maximum_av_end_difference_seconds'] and bool((np.diff(pts) > 0).all()),
        'decoded_actual_head_pixels': len(pixels) == len(settings['frame_sample_seconds']) and changed
            and all(row['head_nonblack_pixels'] > 200 and row['mean_rgb_error'] <= settings['maximum_mean_rgb_error'] for row in pixels),
        'decoded_voice_tracks_engine_envelope': timing['peak_interior']
            and timing['envelope_correlation'] >= settings['minimum_envelope_correlation'],
        'decoded_pitch_matches_drawn_voice': sum(row['difference_cents'] is not None
            and abs(row['difference_cents']) <= settings['maximum_pitch_difference_cents']
            for row in timing['pitch_windows']) >= settings['minimum_voiced_vowels'],
    }
    return {'checks': {**life, **guards}, 'browser': browser['browser'], 'served_wasm_sha256': browser['wasmSha256'],
            'drawing': drawing, 'audio_alignment': timing,
            'first_plan': {'id': plan['id'], 't0': plan['t0'], 'end': plan['end'], 'notes': notes},
            'video_matches': pixels, 'decoded': {'file': clip.name, 'container': probe['format']['format_name'],
                'video_codec': video['codec_name'], 'audio_codec': audio['codec_name'], 'audio_rate': rate,
                'audio_end_seconds': audio_end, 'video_end_seconds': video_end, 'effective_fps': fps,
                'first_audio_pts_seconds': audio_start, 'first_video_pts_seconds': float(pts[0]), 'video_frames': len(pts)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    spec = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/App.tsx', 'src/ui/components/SingPanel.tsx',
        'src/ui/components/AnatomyView3D.tsx', 'src/ui/render/anatomy3d.ts', 'src/ui/render/readouts.ts',
        'src/audio/AudioEngine.ts', 'src/ui/singing.ts', 'src/song/record.ts', 'src/song/fit.ts', 'src/song/tunes.ts',
        'src/worklet/processor.ts', 'src/wasm/chimera.ts', 'tests/singing-live.test.ts', 'bun.lock')]
    inputs = [CASE, Path(__file__), Path(shared.__file__), CAPTURE, CAPTURE.with_name('observe-song-recorder.mjs'),
              WEB / 'bun.lock', *upstream]
    detail = {'case_id': spec['id'], 'upstream_revision': revision,
              'browser_launch': {'executable_override': os.environ.get('CHIMERA_CHROMIUM'),
                                 'graphics_override': os.environ.get('CHIMERA_RECORDING_GRAPHICS')},
              **{tool: subprocess.check_output(command, text=True).splitlines()[0] for tool, command in (
                  ('node', ['node', '--version']), ('bun', [*bun, '--version']),
                  ('ffmpeg', ['ffmpeg', '-version']), ('ffprobe', ['ffprobe', '-version']))}}
    return shared.record_measurement(args.run_id, CASE, inputs, detail, lambda out, run: measure(spec, bun, out, run),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
