"""リムショット K の舌体閉鎖、加圧、声門と口端の開放を固定上流と照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np

from measure_beatbox_hat import activation
import measure_beatbox_kick as single
import measure_bilabial_stop as bilabial
import measure_glottal_coupling as glottal
import measure_glottal_cycle as cycles
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_turbulence as random_reference
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-rimshot-k-v2.json'
REFERENCE_SOURCES = tuple(Path(module.__file__) for module in (glottal, cycles, random_reference))
OFFSETS = [[-0.0875, -0.0175], [-0.0635, 0.0165], [-0.0635, 0.0165],
           [-0.0755, 0.0465], [-0.0335, 0.0205]]


def vibrating_area(trace, source, gap_goal):
    """観測したF0と振動ゲートから面積の振動項を復元する（演奏の呼気0）。"""
    voice = source['voice']
    rate = source['internal_sample_rate_hz']
    ratio = rate // voice['output_sample_rate_hz']
    f0 = trace['glottal_f0_hz']
    cycle_count = math.ceil(f0.sum() * ratio / (rate * 0.55))
    period, amplitude = cycles.cycle_factors(
        {'cycle_seed': 777, 'jitter': 0.00455, 'shimmer': 0.042}, cycle_count)
    phase = 0.0
    cycle = 0
    phases = np.empty(f0.size)
    scales = np.empty(f0.size)
    # 観測フレームの境界は32内部サンプルごとのピッチ更新をまたがない。
    for frame, hz in enumerate(f0):
        for _ in range(ratio):
            phase += hz / rate / period[cycle]
            if phase >= 1.0:
                phase -= 1.0
                cycle += 1
        phases[frame] = phase
        scales[frame] = amplitude[cycle]
    samples = ratio * (trace['frame'] + 1)
    gap_before = gap_goal * -np.expm1(-(samples - 1) / (rate * 0.004))
    amplitude_now = 0.17 * 0.45 * -np.expm1(-samples / (rate * 0.004))
    tension = voice['tension']
    chink = 0.008 + 0.03 * voice['breathiness']
    quotient = np.minimum(0.98, 0.78 - 0.36 * tension + 0.09
                          + 0.98 * np.maximum(0, gap_before - chink))
    pulse = glottal.pulse_shape(phases, quotient, 0.56 + 0.16 * tension,
                                0.4 * tension + 1.375 * max(0, tension - 0.6))
    return amplitude_now * scales * trace['glottal_voicing'] * pulse


def control_errors(trace, source, hits):
    """打音時刻から喉頭と声門の静的面積を積分し、声門面積に振動項を足す。"""
    voice = source['voice']
    rate = voice['output_sample_rate_hz']
    dt = 64 / rate
    retention = math.exp(-1 / (rate * 0.004))
    base_larynx = 0.149
    gap_goal = 0.1 * voice['breathiness']**2 + 0.008 + 0.03 * voice['breathiness']
    # 同じ制御区間内の指数緩和を、各出力フレームの末尾で解析的に合成する。
    position = source['posture']['larynx_cm']
    velocity = gap = closed = closure_goal = 0.0
    larynx_series, area_series = [], []
    planned = [
        (hit + (0.0165 if sound == 'K' else -0.01), -0.08 if sound == 'K' else -0.075,
         min(1.6, 1.25 + 0.3 * accent))
        for sound, hit, accent in hits
    ]
    for frame in range(len(trace)):
        if frame % 64 == 0:
            t = (frame // 64) * dt
            upright = [
                (40 * activation(t, start - 0.05, start + 0.004, 0.03, 0.08), height)
                for start, _, height in planned
            ]
            weight = sum(w for w, _ in upright)
            target = (0.05 * base_larynx + sum(w * height for w, height in upright)) / (0.05 + weight)
            omega = 16 * math.pi * (3.0 if weight > 0.0 else 1.0)
            velocity += (omega**2 * (target - position) - 2 * omega * velocity) * dt
            position += velocity * dt
            closure_goal = min(1.0, 4 * sum(
                activation(t, start + close - 0.012, start + 0.03, 0.012, 0.03)
                for start, close, _ in planned
            ))
        gap = gap_goal + (gap - gap_goal) * retention
        closed = closure_goal + (closed - closure_goal) * retention
        larynx_series.append(position)
        area_series.append(gap * (1 - 0.92 * closed))
    return {
        'larynx_max_abs_error_cm': float(abs(trace['larynx_cm'] - larynx_series).max()),
        'glottal_area_max_abs_error_cm2': float(abs(
            trace['glottal_area_cm2'] - (area_series + vibrating_area(trace, source, gap_goal))).max()),
    }


def observe_voicing(trace, rate, limits):
    voicing = abs(trace['glottal_voicing'])
    clock = (trace['frame'] + 1) / rate
    threshold = limits['voicing_event_threshold']
    active = clock[voicing > threshold]
    seconds = active.size / rate
    peak = float(voicing.max())
    tail = float(voicing[clock >= limits['voicing_tail_start_seconds']].max())
    return {
        'transient_voicing_with_gate_closed': (
            float(abs(trace['gate']).max()) == 0 and peak <= limits['maximum_voicing']
            and limits['minimum_active_voicing_seconds'] <= seconds <= limits['maximum_active_voicing_seconds']
            and tail <= threshold
        ),
        'maximum_voicing': peak, 'active_voicing_seconds': seconds, 'tail_maximum_voicing': tail,
        'first_active_voicing_seconds': float(active[0]) if active.size else None,
    }


def events(trace, pcm, config):
    data, limits = config['beatbox_voice'], config['measurement']
    rate = data['voice']['output_sample_rate_hz']
    clock = (trace['frame'] + 1) / rate
    area = np.minimum(trace['oral_minimum_cm2'], trace['pharynx_minimum_cm2'])
    threshold = limits['closed_area_cm2']
    start, end = limits['closure_window_seconds']
    closed = np.flatnonzero((clock >= start) & (clock < end) & (area < threshold))
    if not closed.size or closed[-1] + 1 >= len(trace):
        return {'dorsal_closure_and_release': False, 'reason': '閉鎖と開口を特定できません'}
    first, released = int(closed[0]), int(closed[-1] + 1)
    if area[released] < threshold:
        return {'dorsal_closure_and_release': False, 'reason': '観測窓の末尾でも閉鎖しています'}
    peak_idx = first + int(trace['pressure_supra_dyn_cm2'][first:released].argmax())
    rise = float(trace['pressure_supra_dyn_cm2'][peak_idx] - trace['pressure_supra_dyn_cm2'][first])
    larynx = float(trace['larynx_cm'][closed].max())
    glottal_area = float(trace['glottal_area_cm2'][peak_idx])
    lip_area = float(trace['lip_minimum_cm2'][closed].min())
    burst_end = released + round(rate * limits['burst_window_seconds'])
    burst = released + int(abs(pcm[released:burst_end]).argmax())
    burst_pcm = float(abs(pcm[burst]))
    burst_flow = float(abs(trace['lip_flow_cm3_s'][released:burst_end]).max())
    duration = (released - first) / rate
    max_gate = float(abs(trace['gate']).max())
    quiet = float(abs(pcm[-round(rate * limits['tail_window_seconds']):]).max())
    errors = control_errors(trace, data, [('K', data['hit_seconds'], data['accent'])])
    return {
        'dorsal_closure_and_release': (
            len(closed) == released - first and duration >= limits['minimum_closed_seconds']
            and lip_area >= limits['minimum_lip_area_during_closure_cm2']
        ),
        'compression_behind_closure': (rise >= limits['minimum_closed_pressure_rise_dyn_cm2']
                                       and larynx >= limits['minimum_closed_larynx_peak_cm']
                                       and glottal_area <= limits['maximum_glottal_area_at_pressure_peak_cm2']),
        'release_burst_and_decay': (burst_pcm >= limits['minimum_burst_pcm_peak']
                                    and burst_flow >= limits['minimum_burst_lip_flow_cm3_s']
                                    and quiet <= limits['maximum_tail_pcm']),
        **observe_voicing(trace, rate, limits),
        'independent_ejective_controls': max(errors.values()) <= limits['control_absolute_tolerance'],
        'first_closed_frame': first, 'first_open_frame': released, 'burst_frame': burst,
        'first_closed_seconds': float(clock[first]), 'first_open_seconds': float(clock[released]),
        'closed_seconds': duration, 'minimum_lip_area_during_closure_cm2': lip_area,
        'minimum_pharynx_area_during_closure_cm2': float(trace['pharynx_minimum_cm2'][closed].min()),
        'first_closed_oral_cell': int(trace['oral_minimum_cell'][first]),
        'closed_pressure_peak_dyn_cm2': float(trace['pressure_supra_dyn_cm2'][peak_idx]),
        'closed_pressure_rise_dyn_cm2': rise, 'closed_larynx_peak_cm': larynx,
        'glottal_area_at_pressure_peak_cm2': glottal_area, 'burst_pcm_peak': burst_pcm,
        'burst_lip_flow_cm3_s': burst_flow, 'tail_pcm_peak': quiet,
        'maximum_gate': max_gate, 'control_errors': errors,
    }


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute, offsets=OFFSETS, observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in ('dorsal_closure_and_release', 'compression_behind_closure', 'release_burst_and_decay',
                 'transient_voicing_with_gate_closed', 'independent_ejective_controls'):
        result['checks'][name] = all(row.get(name, False) for row in outcomes)
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
    inputs = [
        CASE, *single.PROBE_SOURCES, Path(__file__).resolve(), WORKSPACE / 'tools/measure_beatbox_hat.py',
        Path(single.__file__), Path(bilabial.__file__), Path(timing.__file__), Path(shared.__file__),
        WORKSPACE / 'tools/upstream_baseline.py', *REFERENCE_SOURCES, *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/inventory.rs', 'crates/chimera/src/airway/network.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/voice/human_voice.rs',
        'crates/chimera-cli/src/render.rs',
    )
    details = {
        'upstream_revision': revision, 'case_id': config['id'],
        'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper},
    }
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
