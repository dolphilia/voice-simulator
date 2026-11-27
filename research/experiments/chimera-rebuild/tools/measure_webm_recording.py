"""WebMのヘッダーと音声時刻を、固定MP4と独立した復号結果へ照合する。"""

from fractions import Fraction

import numpy as np

from measure_wasm_fixed import read_json
from upstream_baseline import sha256


def ebml_doc_type(path):
    with path.open('rb') as stream:
        header = stream.read(4096)

    def read_vint(offset, strip_marker):
        first = header[offset]
        if not first:
            raise ValueError('EBMLの可変長整数の先頭が0です')
        width = 9 - first.bit_length()
        value = int.from_bytes(header[offset:offset + width], 'big')
        if strip_marker:
            value ^= 1 << (7 * width)
        return value, offset + width

    kind, offset = read_vint(0, False)
    if kind != 0x1A45DFA3:
        return None
    size, offset = read_vint(offset, True)
    end = offset + size
    if end > len(header):
        raise ValueError('EBMLヘッダーが採取範囲を超えています')
    while offset < end:
        kind, offset = read_vint(offset, False)
        size, offset = read_vint(offset, True)
        if offset + size > end:
            raise ValueError('EBMLヘッダーの要素が境界を超えています')
        if kind == 0x4282:
            return header[offset:offset + size].decode('ascii')
        offset += size
    return None


def decoded_audio_clock(clip, media, quantum_samples, artifacts, execute):
    report = read_json(artifacts / f'{clip.stem}-ffprobe.json')
    track = next(stream for stream in report['streams'] if stream['codec_type'] == 'audio')
    rate = int(track['sample_rate'])
    frames = [frame for frame in report['frames'] if frame['media_type'] == 'audio']
    sizes = np.asarray([int(frame['nb_samples']) for frame in frames])
    tick = float(Fraction(track['time_base']))
    pts = np.asarray([int(frame['best_effort_timestamp']) for frame in frames]) * tick
    offsets = np.r_[0, np.cumsum(sizes[:-1])]
    errors = pts - (pts[0] + offsets / rate)
    quantum = quantum_samples / rate
    maximum_error = 2 * quantum + tick
    first_bad = next(({'decoder_frame': i, 'sample': int(offsets[i]), 'error_seconds': float(error)}
                      for i, error in enumerate(errors) if abs(error) > maximum_error), None)
    step_errors = np.diff(pts) - sizes[:-1] / rate
    maximum_step_error = float(np.max(np.abs(step_errors), initial=0))
    end_error = media['audio_end_seconds'] - media['audio_end_from_sample_count_seconds']
    passed = (maximum_step_error <= quantum + tick and first_bad is None and abs(end_error) <= maximum_error
              and int(sizes.sum()) == media['audio_samples_after_decode']
              and bool((sizes > 0).all() and (np.diff(pts) > 0).all()))
    packet_path = artifacts / f'{clip.stem}-audio-packets.json'
    execute(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_packets', '-of', 'json', str(clip)],
            stdout=packet_path)
    packets = read_json(packet_path)['packets']
    return passed, {
        'audio_sample_rate_hz': rate, 'audio_pts_time_base': track['time_base'], 'audio_pts_tick_seconds': tick,
        'packet_count': len(packets), 'first_packet': packets[0], 'last_packet': packets[-1],
        'first_decoded_audio_frame': frames[0], 'last_decoded_audio_frame': frames[-1],
        'video_minus_audio_start_seconds': media['video_start_seconds'] - media['audio_start_seconds'],
        'first_decoded_minus_first_packet_seconds': float(pts[0]) - float(packets[0]['pts_time']),
        'decoded_audio_pts_step_error_max_seconds': maximum_step_error,
        'decoded_audio_pts_error_max_seconds': float(np.max(np.abs(errors))),
        'decoded_audio_end_error_seconds': end_error, 'first_decoded_audio_pts_difference': first_bad,
    }


def canvas_draw_clock(page, rate):
    canvases = page.get('capturedCanvases')
    if not canvases or len(canvases[0]['frames']) < 2:
        return None
    canvas = canvases[0]
    frames = canvas['frames']
    drawn = np.asarray([(entry['contextFrame'] - canvas['startedContextFrame']) / rate for entry in frames])
    gap = int(np.diff(drawn).argmax())
    return {
        'observed_frames': len(drawn),
        'largest_gap_interval_seconds_since_capture': drawn[gap:gap + 2].tolist(),
        'largest_gap_seconds': float(drawn[gap + 1] - drawn[gap]),
        'wall_seconds_in_same_interval': (frames[gap + 1]['atMs'] - frames[gap]['atMs']) / 1000,
    }


def measure_webm_clips(case, browser, evidence, mp4, mp4_wav, artifacts, execute):
    spec = case['measurement']
    expected_mime = spec['file_mime_type']
    rejected = spec.get('suppressed_mime_types', ['video/mp4;codecs=avc1.42E01E,mp4a.40.2', 'video/mp4'])
    requested = spec['requested_mime_type']
    queries = [*rejected, requested]
    expected_cycle = list(zip(queries, [False] * len(rejected) + [True], strict=True))
    checks = {'webm_raw_pcm_exact_to_mp4': sha256(artifacts / 'recorded-input.wav') == sha256(mp4_wav)}
    details = {'mp4_run': case['reference']['mp4_run'], 'clips': {}}
    for name, filename in [('candidate', browser['candidate']['name']), ('upstream', browser['upstream']['saved']['name'])]:
        page = browser[name]
        clip = artifacts / filename
        media = evidence[name]
        capabilities = page['capabilityChecks']
        observed = [(check['type'], check['reported']) for check in capabilities]
        query_cycles = len(observed) // len(expected_cycle)
        native_supported = {check['type'] for check in capabilities if check['nativeSupported']}
        required = {requested, *(mime for mime in rejected if mime.startswith('video/webm;'))}
        doc_type = ebml_doc_type(clip)
        checks[f'webm_{name}_fallback'] = (
            query_cycles > 0 and observed == expected_cycle * query_cycles and required <= native_supported
            and any(mime.split(';')[0] == 'video/mp4' for mime in native_supported.intersection(rejected))
            and bool(page['takes']) and all(take['requestedMime'] == requested
                and take['chunkMimes'] and all(mime.split(';')[0] == expected_mime for mime in take['chunkMimes'])
                for take in page['takes'])
        )
        checks[f'webm_{name}_container_and_codecs'] = (
            clip.suffix == '.webm' and doc_type == spec['ebml_doc_type'] and 'webm' in media['container'].split(',')
            and (media['video_codec'], media['audio_codec']) == (spec['video_codec'], spec['audio_codec'])
        )
        contiguous, clock = decoded_audio_clock(clip, media, spec['audio_capture_quantum_samples'], artifacts, execute)
        checks[f'webm_{name}_decoded_audio_clock'] = (
            contiguous and clock['audio_pts_tick_seconds'] == spec['expected_audio_timestamp_tick_seconds'])
        checks[f'webm_{name}_decoded_track_start'] = (
            abs(clock['video_minus_audio_start_seconds']) <= spec['maximum_track_start_difference_seconds']
            and max(media['video_start_seconds'], media['audio_start_seconds']) <= media['lag_seconds']
        )
        beat_deltas = [a - b if a is not None and b is not None else None for a, b in zip(
            media['visual_minus_audio_beat_seconds'], mp4['codec_comparison'][name]['visual_minus_audio_beat_seconds'], strict=True)]
        checks[f'webm_{name}_beat_error_change_from_mp4'] = all(
            delta is not None and abs(delta) <= spec['maximum_marker_error_change_from_mp4_seconds'] for delta in beat_deltas)
        details['clips'][name] = {
            'doc_type': doc_type, 'requested_mime': page['takes'][0]['requestedMime'],
            'completed_mime_query_cycles': query_cycles, 'native_supported_mime_types': sorted(native_supported),
            **clock,
            'beat_error_change_from_mp4_seconds': beat_deltas,
        }
        draw = canvas_draw_clock(page, clock['audio_sample_rate_hz'])
        if draw:
            details['clips'][name]['canvas_draw_clock'] = draw
    playback = browser['candidate']['playback']
    checks['webm_browser_playback'] = (
        playback.get('mimeType') == expected_mime and playback.get('audioVideoError') is None
        and playback.get('playedSeconds', 0) >= spec['minimum_browser_playback_seconds']
        and browser['upstream']['saved']['type'] == expected_mime
    )
    details['candidate_playback'] = playback
    return checks, details


def compare_vp9(case, evidence, vp9, vp9_wav, artifacts):
    limit = case['measurement']['maximum_marker_error_change_from_vp9_seconds']
    checks = {'vp8_raw_pcm_exact_to_vp9': sha256(artifacts / 'recorded-input.wav') == sha256(vp9_wav)}
    details = {'vp9_run': case['reference']['vp9_run'], 'clips': {}}
    for name, media in evidence.items():
        control = vp9['codec_comparison'][name]
        beat_deltas = [a - b if a is not None and b is not None else None for a, b in zip(
            media['visual_minus_audio_beat_seconds'], control['visual_minus_audio_beat_seconds'], strict=True)]
        checks[f'vp8_{name}_beat_error_change_from_vp9'] = all(
            delta is not None and abs(delta) <= limit for delta in beat_deltas)
        details['clips'][name] = {
            'beat_error_change_seconds': beat_deltas,
            'effective_video_fps_change': media['effective_video_fps'] - control['effective_video_fps'],
            'largest_video_gap_change_seconds': media['maximum_video_gap_seconds'] - control['maximum_video_gap_seconds'],
            'audio_end_relative_to_source_change_seconds':
                media['audio_end_relative_to_source_seconds'] - control['audio_end_relative_to_source_seconds'],
        }
    return checks, details
