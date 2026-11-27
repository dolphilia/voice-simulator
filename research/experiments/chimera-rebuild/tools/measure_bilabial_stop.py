"""固定版の /p b/ と計画、唇閉鎖、声門、PCMを照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

PROBE = WORKSPACE/'tools/upstream_bilabial_probe.rs'
CASES = ('p', 'b', 'p-unaspirated', 'p-fast')
KEYS = dict(zip(
    ('jaw', 'tbX', 'tbY', 'ttX', 'ttY', 'ttCurl', 'root', 'lipAp', 'lipProt', 'lipWidth',
     'labiodental', 'velum', 'larynx', 'epilarynx', 'ventricular', 'lateral', 'dorsum',
     'abduction', 'closure', 'breath', 'f0', 'vibrato'),
    ('jaw_cm', 'tongue_body_x_cm', 'tongue_body_y_cm', 'tongue_tip_x_cm', 'tongue_tip_y_cm',
     'tip_curl', 'tongue_root_cm', 'lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread',
     'labiodental', 'velum_cm2', 'larynx_cm', 'epilarynx', 'ventricular', 'lateral', 'dorsum',
     'abduction_cm2', 'closure', 'breath', 'f0_hz', 'vibrato_cents'),
    strict=True,
))


def load_trace(path, frames):
    data = np.genfromtxt(path, delimiter=',', names=True)
    if len(data) != frames or not np.array_equal(data['frame'], np.arange(frames)):
        raise ValueError('観測された出力フレーム数または連番が一致しません')
    if not all(np.isfinite(data[name]).all() for name in data.dtype.names):
        raise ValueError('観測系列に非有限値があります')
    return data


def compare_traces(left, right, limits):
    names = left.dtype.names
    if names != right.dtype.names:
        raise ValueError('候補と上流の列が一致しません')
    errors = {}
    first = None
    for name in names[1:]:
        delta = abs(left[name] - right[name])
        peak = max(float(abs(right[name]).max()), 1e-6)
        allowance = (limits['geometry_absolute_tolerance'] if name.startswith(
            ('lip_aperture', 'lip_area', 'lip_minimum', 'lip_protrusion', 'lip_spread',
             'tongue_tip_', 'tongue_body_', 'oral_minimum_', 'oral_cell_', 'pharynx_minimum_', 'lateral_')) else
            peak * limits['audio_state_peak_relative_tolerance'])
        hits = np.flatnonzero(delta > allowance)
        if hits.size and (first is None or hits[0] < first['frame']):
            i = int(hits[0])
            first = {'field': name, 'frame': i, 'candidate': left[name][i],
                     'upstream': right[name][i], 'allowance': allowance}
        errors[name] = {'absolute': float(delta.max()), 'relative_to_upstream_peak': float(delta.max()) / peak}
    return first, errors


def stop_gesture_evidence(case, settings, reference):
    measurement = case['measurement']
    expected = measurement['expected']
    tol = measurement['gesture_absolute_tolerance']
    gestures = settings['gestures']
    plans = reference['plans']
    reference_gestures = [{**g, 'targets': {KEYS[key]: value for key, value in g['targets'].items()}}
                          for plan in plans for g in plan['gestures']]
    g_diff, g_error = timing.compare(gestures, reference_gestures, tol)
    candidate_segments = []
    for utterance in settings['speech']['utterances']:
        for part in utterance['segments']:
            s = {'ipa': part['segment']['ipa'], 't0': part['start_seconds'],
                 't1': part['end_seconds'], 'kind': part['manner'] or '?'}
            if s['kind'] == 'vowel':
                s['stress'] = part['segment'].get('stress', 0)
            candidate_segments.append(s)
    segment_diff, _ = timing.compare(candidate_segments, [s for plan in plans for s in plan['segments']], tol)

    stop = next(s for s in candidate_segments if s['ipa'] == expected['stop'])
    lip = next(g for g in gestures if g['label'] == expected['stop'])
    asp = next((g for g in gestures if g['label'] == 'aspiration'), None)
    actual = {key: value for key, value in {
        'stop': stop['ipa'], 'stop_start': stop['t0'], 'stop_end': stop['t1'],
        'lip_start': lip['t0'], 'lip_release': lip['t1'],
        'aspiration_opening': asp['targets']['abduction_cm2'] if asp else None,
        'aspiration_past_seconds': asp['t1'] - stop['t1'] if asp else None,
    }.items() if key in expected}
    prereg, _ = timing.compare(actual, expected, tol)
    rate = settings['speech']['rate']
    scale = max(rate, 1.0)
    independently = [0.03/scale, 0.018/scale, 0.045/scale, 1.55, 40.0, -0.25]
    observed = [lip[k] for k in ('rampIn', 'rampOut', 'releaseHold', 'speed', 'strength')] + [
        lip['targets']['lip_aperture_cm']]
    formula, _ = timing.compare(observed, independently, tol)
    return stop, {
        'gesture_difference': g_diff, 'checked_gesture_max_abs_error': g_error,
        'first_segment_difference': segment_diff, 'registered_difference': prereg,
        'independent_difference': formula, 'observed': actual,
        'passed': not (g_diff or segment_diff or prereg or formula),
    }


def events(data, pcm, settings, stop, limits):
    rate = settings['case']['speech_voice']['voice']['output_sample_rate_hz']
    t = (data['frame'] + 1) / rate
    around = abs(t - 0.5 * (stop['t0'] + stop['t1'])) < (stop['t1'] - stop['t0']) / 2 + 0.03
    indices = np.flatnonzero(around & (data['lip_minimum_cm2'] < limits['closed_area_cm2']))
    if not indices.size:
        return {'passed': False, 'reason': '音素付近に閉鎖を検出できません'}
    left, right = int(indices[0]), int(indices[-1] + 1)
    if right == len(t):
        return {'passed': False, 'reason': '閉鎖後の開口を検出できません'}
    opening = t[right]
    seal_offset, open_offset = t[left] - stop['t0'], opening - stop['t1']
    keep = int(rate * limits['quiet_window_seconds'])
    flow = data['lip_flow_cm3_s'][left:right]
    attenuation = limits['closed_radiation_retention_per_internal_sample'] ** settings['decimation_factor']
    independent = flow[0] * attenuation ** np.arange(len(flow))
    decay_error = float(abs(flow - independent).max())
    remaining = float(abs(flow[-1]) / abs(flow[0])) if flow[0] else 0.0
    reopened = float(abs(pcm[right:right+int(rate * limits['release_window_seconds'])]).max())
    # 破裂の観測値は開放後5 ms内の絶対ピーク。母音を含む40 msの判定窓も保つ。
    burst_samples = pcm[right:right+round(rate * .005)]
    burst_frame = right + int(np.argmax(abs(burst_samples)))
    tail = float(abs(pcm[-keep:]).max())
    def inside(value, bounds):
        return bounds[0] <= value <= bounds[1]
    onset_limits = ([0, stop['t1'] - stop['t0']] if limits.get('closure_inside_stop_span')
                    else limits['closure_offset_seconds'])
    return {
        'first_closed_frame': left, 'first_open_frame': right,
        'closure_offset_seconds': float(seal_offset), 'release_offset_seconds': float(open_offset),
        'closed_frames': int(len(indices)), 'closed_radiation_decay_max_error_cm3_s': decay_error,
        'closed_lip_flow_first_and_last_cm3_s': [float(flow[0]), float(flow[-1])],
        'closed_radiation_remaining_fraction': remaining,
        'release_pcm_peak': reopened,
        'burst_frame_first_5ms': burst_frame,
        'burst_offset_from_release_ms': (burst_frame - right) * 1000 / rate,
        'burst_pcm_peak_first_5ms': float(abs(pcm[burst_frame])),
        'tail_pcm_peak': tail,
        'maximum_abduction_cm2': float(data['abduction_cm2'][indices].max()),
        'passed': bool(inside(seal_offset, onset_limits)
                       and inside(open_offset, limits['release_offset_seconds'])
                       and len(indices) == right - left
                       and decay_error <= limits['closed_radiation_decay_abs_tolerance']
                       and len(indices) >= limits.get('minimum_closed_frames', 1)
                       and remaining <= limits.get('closed_radiation_remaining_fraction_max', 1.0)
                       and reopened >= limits['release_min_peak_pcm']
                       and tail <= limits['quiet_max_peak_pcm']),
    }


def capture_candidate(path, blocks, artifacts, execute):
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    settings_path = artifacts/'settings.json'
    trace = artifacts/'voicing.csv'
    execute([*prefix, 'inspect', str(path)], stdout=settings_path)
    execute([*prefix, 'render', str(path), str(trace)])
    result_files = []
    for n in blocks:
        wave, csv = artifacts/f'pcm-{n}.wav', artifacts/f'pcm-{n}.csv'
        result_files.append((wave,csv))
        execute([*prefix, 'render-pcm', str(path), str(wave), str(csv), str(n)])
    return timing.read(settings_path), trace, result_files


def capture(path, blocks, artifacts, execute, test_suites, *, probe=None):
    settings, trace, result_files = capture_candidate(path, blocks, artifacts, execute)
    if probe is None:
        tests = [argument for suite in test_suites for argument in ('--test', suite)]
        execute(['cargo', 'test', '--locked', '-p', 'chimera', *tests],
                cwd=UPSTREAM, stdout=artifacts/'upstream-tests.log')
        probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    ut, upcm, up = (artifacts/name for name in ('upstream-voicing.csv', 'upstream-pcm.f32', 'upstream-plan.json'))
    execute([str(probe), str(path), str(ut), str(upcm), str(up)], cwd=UPSTREAM)
    return settings, trace, result_files, ut, upcm, up


def measure(path, config, artifacts, execute):
    settings, trace, result_files, ut, upcm, up = capture(
        path, config['measurement']['host_block_frames'], artifacts, execute, ('aspiration', 'fast_speech'),
    )
    frame_count = settings['output_frames']
    raw = timing.read(up)
    candidate, upper = load_trace(trace, frame_count), load_trace(ut, frame_count)
    limits = config['measurement']
    stop, plan = stop_gesture_evidence(config, settings, raw)
    first, trace_errors = compare_traces(candidate, upper, limits)
    wav, csv = result_files[0]
    rate, pcm = wavfile.read(wav)
    upper_pcm = np.fromfile(upcm, dtype='<f4')
    if pcm.shape != upper_pcm.shape or len(pcm) != frame_count:
        raise ValueError('PCMのフレーム数を照合できません')
    pcm_errors = abs(pcm.astype('f8') - upper_pcm)
    event_candidate, event_upstream = (events(data, samples, settings, stop, limits)
                                       for data, samples in ((candidate,pcm),(upper,upper_pcm)))
    first_pcm = np.flatnonzero(pcm_errors > limits['pcm_absolute_tolerance'])
    return {
        'checks': {
            'phoneme_and_gesture_plans': plan['passed'],
            'equal_sample_count': raw['output_frames'] == frame_count and rate == config['speech_voice']['voice']['output_sample_rate_hz'],
            'all_trace_values_within_tolerance': first is None,
            'pcm_agreement': bool(np.isfinite(pcm).all() and np.isfinite(upper_pcm).all() and not first_pcm.size),
            'measured_closure_and_release': event_candidate['passed'] and event_upstream['passed'],
            'same_event_frames': all(event_candidate.get(key) == event_upstream.get(key)
                                     for key in ('first_closed_frame', 'first_open_frame', 'burst_frame_first_5ms')),
            'host_partition_byte_agreement': all(sha256(other_wave)==sha256(wav) and sha256(other_csv)==sha256(csv)
                                                 for other_wave,other_csv in result_files[1:]),
        },
        'frames':frame_count, 'plan':plan, 'first_trace_difference':first, 'trace_errors':trace_errors,
        'pcm_max_absolute_error':float(pcm_errors.max()),
        'pcm_first_difference_frame': int(first_pcm[0]) if first_pcm.size else None,
        'candidate_events':event_candidate, 'upstream_events':event_upstream,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    path = WORKSPACE/f'cases/bilabial-{args.condition}.json'
    config = timing.read(path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__), Path(timing.__file__),
               WORKSPACE/'tools/upstream_baseline.py', *shared.candidate_sources()]
    upper = ['phonetics/planner.rs', 'phonetics/inventory.rs', 'voice/human_voice.rs', 'voice/human_airway.rs']
    info = {'upstream_revision':revision, 'case_id':config['id'],
            'upstream_noise_scale':0.0, 'upstream_pitch_drift_jitter_shimmer':0.0,
            'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper}}
    return shared.record_measurement(args.run_id,path,sources,info,
                                     lambda artifacts,execute:measure(path,config,artifacts,execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
