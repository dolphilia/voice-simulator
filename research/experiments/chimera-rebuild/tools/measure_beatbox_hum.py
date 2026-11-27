"""鼻音の打音 m の閉唇、音高、呼気、鼻端放射を固定上流に照合する。"""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np

from measure_beatbox_hat import activation
import measure_beatbox_kick as single
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-hum.json'


def held_end(length):
    return max(0.06, length * 0.92) - 0.0056


def f0_hz(note):
    return 440.0 * 2**((note - 69) / 12)


def offsets(length):
    end = held_end(length)
    return [[-0.0576, end - 0.019], [-0.0256, end], [-0.0856, -0.0356],
            [-0.0156, end], [-0.0256, end]]


def registered_pitch_and_hold(gestures, end, note, tol):
    selected = [g for g in gestures if any(k in g['targets'] for k in ('breath', 'velum_cm2', 'f0_hz'))]
    notes = [g['targets']['f0_hz'] for g in selected if 'f0_hz' in g['targets']]
    return (len(selected) == 3 and len(notes) == 1
            and abs(notes[0] - f0_hz(note)) <= tol
            and all(abs(g['t1'] - end) <= tol for g in selected))


def control_errors(trace, voice, initial_f0, initial_velum, hits):
    """制御イベントから音高、呼気、開大と軟口蓋の目標を別に積分する。"""
    rate = voice['output_sample_rate_hz']
    dt = 64 / rate
    gate = hold = velocity = 0.0
    pitch, position = initial_f0, initial_velum
    angular_rate = 24 * math.pi
    rows = []
    planned = [(hit, accent, f0_hz(note), hit + held_end(length))
               for hit, accent, note, length in hits]
    for b in range((len(trace) + 63) // 64):
        now = b * dt
        pitch_weights = [(8 * activation(now, hit - 0.0256, end, 0.015, 0.02), target)
                         for hit, _, target, end in planned]
        pitch_weight = sum(w for w, _ in pitch_weights)
        base_f0 = voice['f0_hz']
        target = (base_f0 * 0.02 + sum(w * f for w, f in pitch_weights)) / (0.02 + pitch_weight)
        tau = 0.03 if pitch_weight > 0 else 0.06
        pitch = math.exp(math.log(target) + (math.log(pitch) - math.log(target)) * math.exp(-dt / tau))

        breath = [(activation(now, hit - 0.0156, end, 0.02, 0.04), 0.95 * accent)
                  for hit, accent, _, end in planned]
        breath_weight = sum(w for w, _ in breath)
        gate_target = max(voice['gate'], sum(w * gain for w, gain in breath) / max(1.0, breath_weight))
        hold = 0.15 if breath_weight > 0 else max(0.0, hold - dt)
        tau = 0.025 if gate_target > gate else (0.02 if hold > 0 else 0.07)
        gate = gate_target + (gate - gate_target) * math.exp(-dt / tau)

        opening = 5 * sum(activation(now, hit - 0.0856, hit - 0.0356, 0.02, 0.02)
                          for hit, _, _, _ in planned)
        abduction = 0.1 * voice['breathiness']**2 + 0.3 * min(1.0, opening / 2)
        nasal = 4 * sum(activation(now, hit - 0.0256, end, 0.03, 0.03)
                        for hit, _, _, end in planned)
        velum = initial_velum + min(1.0, nasal / 2) * (0.9 - initial_velum)
        velocity += dt * (angular_rate**2 * (velum - position) - 2 * angular_rate * velocity)
        position += dt * velocity
        rows.append((pitch, gate, abduction, velum, position))
    expected = np.repeat(rows, 64, axis=0)[:len(trace)]
    fields = ('smoothed_f0_hz', 'gate', 'abduction_cm2', 'velum_effective_cm2', 'velum_position_cm2')
    return {name: float(abs(trace[name] - expected[:, i]).max()) for i, name in enumerate(fields)}


def rms(values):
    return float(np.sqrt(np.mean(values.astype('f8')**2)))


def pcm_pitch(audio, rate, note):
    """指定音高の周辺で、正規化自己相関の最大ラグからPCMの周期を測る。"""
    signal = audio.astype('f8')
    signal -= signal.mean()
    target = f0_hz(note)
    lags = range(math.ceil(rate / (1.2 * target)), math.floor(rate / (0.8 * target)) + 1)
    best = max(
        ((float(np.dot(signal[:-lag], signal[lag:])) /
          max(float(np.linalg.norm(signal[:-lag]) * np.linalg.norm(signal[lag:])), 1e-24), lag)
         for lag in lags if lag < len(signal)),
        default=(0.0, 0),
    )
    return (rate / best[1] if best[1] > 0 else 0.0), best[0]


def observe(trace, pcm, rate, window, note, limits):
    clock = (trace['frame'] + 1) / rate
    begin, end = window
    frames = (clock >= begin) & (clock < end)
    target = f0_hz(note)
    median = float(np.median(trace['smoothed_f0_hz'][frames]))
    estimated, correlation = pcm_pitch(pcm[frames], rate, note)
    nose, lip = (rms(trace[f'{part}_flow_cm3_s'][frames]) for part in ('nose', 'lip'))
    ratio = nose / max(lip, 1e-12)
    voicing = float(np.mean(trace['glottal_voicing'][frames]))
    area = float(np.median(trace['velum_port_area_cm2'][frames]))
    amplitude = rms(pcm[frames])
    return {
        'nasal_voicing': (float(trace['lip_minimum_cm2'][frames].max()) < limits['closed_area_cm2']
                          and nose >= limits['minimum_nose_flow_rms_cm3_s']
                          and ratio >= limits['minimum_nose_to_lip_rms_ratio']
                          and area >= limits['minimum_velum_area_cm2']
                          and voicing >= limits['minimum_steady_voicing']
                          and amplitude >= limits['minimum_pcm_rms']),
        'registered_pcm_pitch': (
            max(abs(median - target), abs(estimated - target)) <= target * limits['pitch_relative_tolerance']
            and correlation >= limits['minimum_pcm_pitch_correlation']),
        'midi_note': note, 'expected_f0_hz': target, 'smoothed_f0_median_hz': median,
        'pcm_f0_hz': estimated, 'pcm_pitch_correlation': correlation,
        'nose_flow_rms_cm3_s': nose, 'lip_flow_rms_cm3_s': lip, 'nose_to_lip_rms_ratio': ratio,
        'velum_port_median_cm2': area, 'voicing_mean': voicing, 'pcm_rms': amplitude,
    }


def events(trace, pcm, config):
    source, limits = config['beatbox_voice'], config['measurement']
    voice, spec = source['voice'], limits['hum']
    rate = voice['output_sample_rate_hz']
    hit, note = source['hit_seconds'], spec['expected_midi_note']
    clock = (trace['frame'] + 1) / rate
    active = np.flatnonzero(trace['glottal_voicing'] >= spec['voicing_threshold'])
    closed = np.flatnonzero(trace['lip_minimum_cm2'] < spec['closed_area_cm2'])
    onset = {}
    if closed.size and active.size and closed[-1] + 1 < len(trace):
        onset = {
            'first_closed_frame': int(closed[0]), 'first_open_frame': int(closed[-1]) + 1,
            'burst_frame': int(np.argmax(abs(pcm))),
            'first_closed_seconds': float(clock[closed[0]]), 'first_voiced_seconds': float(clock[active[0]]),
            'first_open_seconds': float(clock[closed[-1] + 1]),
        }
    errors = control_errors(trace, voice, source['initial_f0_hz'], source['posture']['velum_cm2'],
                            [(hit, source['accent'], note, source['step_seconds'])])
    start, end = spec['tail_window_seconds']
    tail = float(trace['gate'][(clock >= start) & (clock <= end)].mean())
    return {
        **observe(trace, pcm, rate, spec['steady_windows_seconds'][0], note, spec), **onset,
        'closure_before_voicing': bool(onset and closed[0] < active[0] <= closed[-1]),
        'tail_breath_decay': tail <= spec['maximum_tail_mean_gate'], 'tail_mean_gate': tail,
        'control_errors': errors,
        'independent_controls': max(errors.values()) <= limits['control_absolute_tolerance'],
    }


def minimum_hold(config, artifacts, execute):
    spec = config['measurement']['hum']['minimum_hold_probe']
    sample = {**config, 'beatbox_voice': {**config['beatbox_voice'], 'step_seconds': spec['step_seconds']}}
    case_path = artifacts / 'minimum-hold-case.json'
    case_path.write_text(json.dumps(sample, ensure_ascii=False, indent=2) + '\n')
    settings = artifacts / 'minimum-hold-settings.json'
    plan = artifacts / 'minimum-hold-upstream-plan.json'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
             'inspect', str(case_path)], stdout=settings)
    executable = artifacts / f'{single.PROBE.stem}.exe'
    execute([str(executable), str(case_path), str(artifacts / 'minimum-hold-upstream.csv'),
             str(artifacts / 'minimum-hold-upstream.f32'), str(plan)], cwd=UPSTREAM)
    candidate = timing.read(settings)
    comparison = single.compare_plans(candidate, timing.read(plan), sample, offsets(spec['step_seconds']))
    limits = config['measurement']
    checks = (comparison['gesture_difference'] is None and comparison['independent_time_difference'] is None
              and registered_pitch_and_hold(candidate['gestures'], spec['expected_hold_end_seconds'],
                                            limits['hum']['expected_midi_note'], limits['gesture_absolute_tolerance']))
    ends = [g['t1'] for g in candidate['gestures'] if 'f0_hz' in g['targets']]
    return checks, {'comparison': comparison, 'step_seconds': spec['step_seconds'], 'pitch_hold_ends_seconds': ends}


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute,
                                   offsets=offsets(config['beatbox_voice']['step_seconds']), observe=events)
    labels = ('nasal_voicing', 'registered_pcm_pitch', 'closure_before_voicing',
              'tail_breath_decay', 'independent_controls')
    for key in labels:
        result['checks'][key] = all(result[label].get(key, False) for label in ('candidate_events', 'upstream_events'))
    limits = config['measurement']
    spec = limits['hum']
    settings = timing.read(artifacts / 'settings.json')
    result['checks']['default_midi_and_hold'] = registered_pitch_and_hold(
        settings['gestures'], spec['expected_hold_end_seconds'], spec['expected_midi_note'],
        limits['gesture_absolute_tolerance'])
    result['checks']['minimum_hold'], result['minimum_hold'] = minimum_hold(config, artifacts, execute)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [
        CASE, *single.PROBE_SOURCES, Path(__file__).resolve(), WORKSPACE / 'tools/measure_beatbox_hat.py',
        Path(single.__file__), Path(bilabial.__file__), Path(timing.__file__), Path(shared.__file__),
        WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/inventory.rs', 'crates/chimera/src/control/beat_player.rs',
        'crates/chimera/src/math.rs', 'crates/chimera/src/voice/human_voice.rs',
        'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/anatomy/human.rs',
        'crates/chimera-cli/src/render.rs',
    )
    details = {'upstream_revision': revision, 'case_id': config['id'],
               'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper}}
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
