"""英語歌唱の調音・呼気・F0・PCMを固定版と独立計算に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as alveolar
import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('long', 'flat', 'fast', 'stop')
SUITES = ('sung_release', 'sing_fast', 'engine')


def compare_plans(settings, reference, limits):
    score = settings['song']['plan']
    phrases = score['phrases']
    report = {'utterances': [{'segments': p['timing']['segments']} for p in phrases]}
    tolerance = limits['gesture_absolute_tolerance']
    segments, evidence = speech.compare_plans({**settings, 'speech': report}, reference, tolerance)
    labeled = {label: [g for g in settings['gestures'] if g['label'] == label]
               for label in ('breath', 'exhale', 'vibrato')}
    count = limits['expected_breath_and_release_count']
    last_opening = labeled['exhale'][-1]
    registered, _ = timing.compare({
        'symbols': [s['ipa'] for s in segments],
        'phrase_end_seconds': phrases[-1]['timing']['end_seconds'],
        'first_breath_hold_seconds': labeled['breath'][0]['t0'],
        'final_release': {
            'breath_end_seconds': labeled['breath'][-1]['t1'],
            'abduction_ramp_start_seconds': last_opening['t0'] - last_opening['rampIn'],
            'ramp_in_seconds': last_opening['rampIn'],
            'strength': last_opening['strength'],
        },
        'counts': [len(gs) for gs in labeled.values()],
    }, {
        'symbols': limits['expected_symbols'],
        'phrase_end_seconds': limits['expected_phrase_end_seconds'],
        'first_breath_hold_seconds': limits['first_breath_hold_seconds'],
        'final_release': limits['expected_final_release'],
        'counts': [count, count, limits['expected_vibrato_count']],
    }, tolerance)
    return segments, {**evidence, 'registered_difference': registered,
                      'segments': segments, 'notes': score['notes'], 'final_gestures': labeled,
                      'unavailable_speech_symbols': score['unavailable_speech_symbols'],
                      'passed': evidence['passed'] and registered is None and not score['unavailable_speech_symbols']}


def independent_controls(trace, settings, case, rate, *, body_scale=1.0):
    stride = settings['control_block_internal_samples'] // settings['decimation_factor']
    clock = np.arange(0, len(trace), stride) / rate
    dt = stride / rate
    contributions = {}
    for key in ('f0_hz', 'abduction_cm2'):
        weights = np.zeros_like(clock)
        targets = np.zeros_like(clock)
        for gesture in settings['gestures']:
            if key not in gesture['targets']:
                continue
            a, b = gesture['t0'], gesture['t1']
            rise = np.clip((clock - a) / gesture['rampIn'] + 1, 0, 1)
            fall = np.clip(1 - (clock - b) / gesture['rampOut'], 0, 1)
            w = gesture['strength'] * np.sin(.5 * np.pi * np.minimum(rise, fall))**2
            weights += w
            targets += w * gesture['targets'][key]
        contributions[key] = weights, targets
    base = 440 * 2**((case['song_voice']['score']['notes'][0]['midi'] - 69) / 12)
    weights, targets = contributions['f0_hz']
    target = (.02 * base + targets) / (.02 + weights)
    memory = np.exp(-dt / np.where(weights > 0, .03, .06))
    pitch = np.empty_like(clock)
    log_frequency = math.log(110)
    for i, (goal, retain) in enumerate(zip(np.log(target), memory, strict=True)):
        log_frequency = retain * log_frequency + (1 - retain) * goal
        pitch[i] = math.exp(log_frequency)
    weights, targets = contributions['abduction_cm2']
    # 重み2までは開大への寄与が増え、それ以上では目標の加重平均になる。
    abduction = body_scale**2 * (.1 * case['song_voice']['voice']['breathiness']**2 + targets / np.maximum(2, weights))
    def expanded(values):
        return np.repeat(values, stride)[:len(trace)]

    errors = {
        'f0_hz': float(abs(trace['smoothed_f0_hz'] - expanded(pitch)).max()),
        'abduction_cm2': float(abs(trace['abduction_cm2'] - expanded(abduction)).max()),
    }
    limits = case['measurement']
    return {'maximum_errors': errors, 'passed': errors['f0_hz'] <= limits['independent_f0_tolerance_hz']
            and errors['abduction_cm2'] <= limits['geometry_absolute_tolerance']}


def observe(trace, pcm, segments, rate, limits):
    time = (trace['frame'] + 1) / rate

    def window(bounds):
        return (time >= bounds[0]) & (time < bounds[1])

    def first_time(mask):
        indices = np.flatnonzero(mask)
        return float(time[indices[0]]) if indices.size else None

    def within(value, bounds):
        return value is not None and bounds[0] <= value <= bounds[1]

    closed = trace['lip_minimum_cm2'] < limits['closed_area_cm2']
    closed_at = first_time(closed)
    released_at = first_time(~closed & np.r_[False, closed[:-1]])
    voiced_at = first_time((time >= segments[0]['t0']) & (trace['glottal_voicing'] >= .5))
    opening = limits['expected_final_release']['abduction_ramp_start_seconds']
    end = limits['expected_phrase_end_seconds']
    tail_peak = float(abs(pcm[-round(limits['final_silence_seconds'] * rate):]).max())
    pitch = []
    for left, right, note in limits['f0_windows']:
        hz, error = vowel.independent_yin(pcm[round(left * rate):round(right * rate)].astype(float), rate, limits)
        target = 440 * 2**((note - 69) / 12)
        pitch.append({'window_seconds': [left, right], 'target_hz': target, 'pcm_yin_hz': hz,
                      'yin_normalized_difference': error,
                      'median_glottal_hz': float(np.median(trace['glottal_f0_hz'][window((left, right))])),
                      'passed': within(hz, (target - limits['yin_midi_tolerance_hz'], target + limits['yin_midi_tolerance_hz']))})
    cents = 1200 * np.log2(trace['glottal_f0_hz'] / trace['smoothed_f0_hz'])
    max_cents = float(abs(cents).max())
    transition = None
    if limits['transition_window_seconds']:
        threshold = math.sqrt(pitch[0]['target_hz'] * pitch[1]['target_hz'])
        transition = first_time(trace['smoothed_f0_hz'] >= threshold)
    vowel_peaks = [float(abs(pcm[window((s['t0'], s['t1']))]).max()) for s in segments if s['kind'] == 'vowel']
    stops = []
    for s in (p for p in segments if p['kind'] == 'stop'):
        area = trace['lip_minimum_cm2' if s['ipa'] == 'p' else 'oral_minimum_cm2']
        mask = window((s['t0'] - .015, s['t1'] + .015))
        edges = np.flatnonzero(np.diff(area < limits['closed_area_cm2'], prepend=False, append=False))
        complete = [(int(a), int(b)) for a, b in edges.reshape(-1, 2)
                    if time[a] < s['t1'] + .015 and time[b - 1] >= s['t0'] - .015]
        closure = min(complete, key=lambda span: abs(time[span[1] - 1] - s['t1']), default=None)
        stops.append({'ipa': s['ipa'], 'observed_area': 'lips' if s['ipa'] == 'p' else 'oral_minimum',
                      'planned_span_seconds': [s['t0'], s['t1']],
                      'minimum_area_cm2': float(area[mask].min()),
                      'first_contact_seconds': float(time[closure[0]]) if closure else None,
                      'release_seconds': float(time[closure[1]]) if closure and closure[1] < len(time) else None})
    checks = {
        'first_lip_closure_and_release': within(closed_at, limits['first_lip_closed_window_seconds'])
                                        and within(released_at, limits['first_lip_release_window_seconds']),
        'voiced_onset': not limits['first_voiced_window_seconds'] or within(voiced_at, limits['first_voiced_window_seconds']),
        'pitch_in_pcm': all(p['passed'] for p in pitch),
        'pitch_transition': not limits['transition_window_seconds'] or within(transition, limits['transition_window_seconds']),
        'vibrato_depth': within(max_cents, limits['vibrato_abs_max_cents_bounds']),
        'audible_vowels_and_quiet_tail': min(vowel_peaks) >= limits['minimum_vowel_pcm_peak']
                                         and tail_peak <= limits['final_max_peak_pcm'],
    }
    if limits.get('first_vowel_continuously_closed'):
        first_vowel = next(p for p in segments if p['kind'] == 'vowel')
        checks['lip_closure_spans_first_vowel'] = bool(closed[window((first_vowel['t0'], first_vowel['t1']))].all())
    sample_times = [opening, end - .03, end, end + .05, end + .15]
    samples = [{key: float(trace[key][i]) for key in ('gate', 'abduction_cm2', 'glottal_voicing')}
               for i in np.clip(np.round(np.array(sample_times) * rate).astype(int) - 1, 0, len(trace) - 1)]
    return {'checks': checks, 'passed': all(checks.values()), 'stops': stops,
            'first_lip_closed_seconds': closed_at, 'first_lip_release_seconds': released_at,
            'first_voice_seconds': voiced_at, 'pitch_midpoint_seconds': transition, 'pitch': pitch,
            'vibrato_max_abs_cents': max_cents, 'vowel_pcm_peaks': vowel_peaks, 'tail_pcm_peak': tail_peak,
            'final_control_samples': [{'seconds': t, **s} for t, s in zip(sample_times, samples, strict=True)]}


def measure(path, config, artifacts, execute):
    limits = config['measurement']
    settings, local_trace, files, upper_trace, upper_pcm, reference_path = voice.capture(
        path, limits['host_block_frames'], artifacts, execute, SUITES)
    return compare_outputs(config, settings, local_trace, files, upper_trace, upper_pcm, reference_path)


def compare_outputs(config, settings, local_trace, files, upper_trace, upper_pcm, reference_path, *, body_scale=1.0):
    limits = config['measurement']
    reference = timing.read(reference_path)
    segments, plan = compare_plans(settings, reference, limits)
    frames = settings['output_frames']
    local, upper = [voice.load_trace(p, frames) for p in (local_trace, upper_trace)]
    fields = [field for field in local.dtype.names if field != 'oral_minimum_cell']
    first, errors = voice.compare_traces(local[fields], upper[fields], limits)
    cells = alveolar.compare_cell_minima(local, upper, limits) if 'oral_minimum_cell' in local.dtype.names else None
    wav, output = files[0]
    rate, pcm = wavfile.read(wav)
    baseline = np.fromfile(upper_pcm, dtype='<f4')
    if pcm.shape != (frames,) or baseline.shape != (frames,) or not all(np.isfinite(a).all() for a in (pcm, baseline)):
        raise ValueError('PCMのフレーム数または有限性が基準と異なります')
    delta = abs(pcm.astype(float) - baseline)
    outliers = np.flatnonzero(delta > limits['pcm_absolute_tolerance'])
    controls = [independent_controls(t, settings, config, rate, body_scale=body_scale) for t in (local, upper)]
    events = [observe(t, p, segments, rate, limits) for t, p in ((local, pcm), (upper, baseline))]
    return {
        'checks': {'plan': plan['passed'], 'trace': first is None and (cells is None or cells['passed']),
                   'pcm': not outliers.size,
                   'same_frame_count_and_rate': frames == reference['output_frames'] == limits['expected_frames']
                   and rate == config['song_voice']['voice']['output_sample_rate_hz'],
                   'same_host_partitions': all(sha256(w) == sha256(wav) and sha256(c) == sha256(output) for w, c in files[1:]),
                   'independent_f0_and_abduction': all(c['passed'] for c in controls),
                   'measured_events': all(e['passed'] for e in events)},
        'measurement_revision': limits['revision'], 'frames': frames, 'plan': plan, 'candidate_and_upstream_controls': controls,
        'candidate_and_upstream_events': events, 'first_trace_difference': first, 'trace_errors': errors,
        'oral_cells': cells, 'pcm_max_abs_error': float(delta.max()),
        'first_pcm_frame_over_tolerance': int(outliers[0]) if outliers.size else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    path = WORKSPACE / f'cases/song-voice-{args.condition}.json'
    case = timing.read(path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [path, Path(__file__).resolve(), voice.PROBE, *(Path(module.__file__) for module in
               (voice, alveolar, speech, timing, shared, vowel)), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt', *shared.candidate_sources()]
    upper_paths = ['crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/sing.rs',
                   'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/control/score.rs',
                   'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/sources/glottis.rs',
                   'public/data/cmudict.txt.gz']
    metadata = {'case_id': case['id'], 'upstream_revision': revision,
                'upstream_pitch_drift_jitter_shimmer': 0, 'turbulence_seed': 12345,
                'turbulence_scale': case['song_voice'].get('turbulence', {}).get('scale', 1),
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_paths}}
    return shared.record_measurement(args.run_id, path, sources, metadata,
                                     lambda artifacts, execute: measure(path, case, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
