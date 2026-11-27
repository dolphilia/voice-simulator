"""Firefoxが選んだ録画形式を、保存ファイルとChromiumの基準に照合する。"""

from measure_wasm_fixed import read_json
from measure_webm_recording import canvas_draw_clock, decoded_audio_clock, ebml_doc_type
from upstream_baseline import sha256

CODEC_NAMES = {'avc1': 'h264', 'mp4a': 'aac', 'vp9': 'vp9', 'vp8': 'vp8', 'opus': 'opus'}


def mime_essence(value):
    return value.split(';', 1)[0].strip().lower()


def measure_firefox_clips(case, browser, evidence, recording, chrome_wav, chrome_recording, artifacts, execute):
    spec = case['measurement']
    formats = spec['format_priority']
    control = read_json(chrome_recording)['tract']
    checks = {
        'firefox_engine': browser['engine'] == case['browser_engine'],
        'firefox_raw_pcm_exact_to_chromium': sha256(artifacts / 'recorded-input.wav') == sha256(chrome_wav),
        'firefox_grid_exact_to_chromium': recording['tract']['grid'] == control['grid'],
    }
    details = {'chromium_run': case['reference']['chromium_run'], 'clips': {}}
    for name, filename in [('candidate', browser['candidate']['name']), ('upstream', browser['upstream']['saved']['name'])]:
        page = browser[name]
        clip = artifacts / filename
        media = evidence[name]
        capabilities = page['nativeCapabilities']
        cycle = []
        for record in capabilities:
            cycle.append((record['type'], record['supported'], record['supported']))
            if record['supported']:
                break
        selected, supported, _ = cycle[-1]
        queried = [(row['type'], row['nativeSupported'], row['reported']) for row in page['capabilityChecks']]
        cycles = len(queried) // len(cycle)
        essence = mime_essence(selected)
        checks[f'firefox_{name}_native_selection'] = (
            [record['type'] for record in capabilities] == formats and supported and cycles > 0
            and queried == cycle * cycles and bool(page['takes'])
            and all(take['requestedMime'] == selected and take['chunkMimes']
                    and all(mime_essence(chunk) == essence for chunk in take['chunkMimes']) for take in page['takes'])
        )
        container = essence.split('/')[1]
        actual_container = media['container'].split(',')
        doc_type = ebml_doc_type(clip) if container == 'webm' else None
        codec_text = selected.partition('codecs=')[2]
        expected_codecs = [CODEC_NAMES[token.split('.')[0]] for token in codec_text.split(',')] if codec_text else []
        decoded_codecs = [media['video_codec'], media['audio_codec']]
        checks[f'firefox_{name}_actual_format'] = (
            container in ('mp4', 'webm') and clip.suffix == f'.{container}' and container in actual_container
            and (container != 'webm' or doc_type == 'webm') and (not expected_codecs or expected_codecs == decoded_codecs)
        )
        contiguous, clock = decoded_audio_clock(clip, media, spec['audio_capture_quantum_samples'], artifacts, execute)
        checks[f'firefox_{name}_decoded_audio_clock'] = contiguous
        checks[f'firefox_{name}_decoded_track_start'] = (
            abs(clock['video_minus_audio_start_seconds']) <= spec['maximum_track_start_difference_seconds']
            and max(media['video_start_seconds'], media['audio_start_seconds']) <= media['lag_seconds']
        )
        details['clips'][name] = {
            'native_capabilities': capabilities, 'selected_mime': selected, 'completed_mime_query_cycles': cycles,
            'doc_type': doc_type, 'decoded_codecs': decoded_codecs, **clock,
        }
        draw = canvas_draw_clock(page, clock['audio_sample_rate_hz'])
        if draw:
            details['clips'][name]['canvas_draw_clock'] = draw
    candidate, upstream = (details['clips'][name] for name in ('candidate', 'upstream'))
    checks['firefox_same_native_choice'] = candidate['native_capabilities'] == upstream['native_capabilities']
    playback = browser['candidate']['playback']
    checks['firefox_browser_playback'] = (
        playback.get('mimeType') == mime_essence(candidate['selected_mime'])
        and playback.get('audioVideoError') is None
        and playback.get('playedSeconds', 0) >= spec['minimum_browser_playback_seconds']
        and browser['upstream']['saved']['type'] == mime_essence(upstream['selected_mime'])
    )
    details['candidate_playback'] = playback
    return checks, details
