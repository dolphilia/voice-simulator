"""吸気スネア ^K の閉鎖、符号付きの呼気と乱流を固定上流に照合する。"""

import argparse
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

CASE = WORKSPACE / 'cases/beatbox-inward-snare-v2.json'
OFFSETS = [[-0.07, -0.02], [-0.046, 0.014], [-0.046, 0.014], [0.018, 0.099],
           [0.026, 0.099], [-0.036, 0.099], [-0.021, 0.099]]
EVENT_CHECKS = ('dorsal_closure_and_release', 'suction_precedes_release', 'reverse_frication')


def control_errors(trace, voice, hits):
    """観測開始から64フレームごとに、登録した時刻と係数でゲート・開大を計算する。"""
    dt = 64 / voice['output_sample_rate_hz']
    gate = hold = 0.0
    gate_series, area_series = [], []
    for block in range((len(trace) + 63) // 64):
        t = block * dt
        breath = [(2 * activation(t, hit - 0.021, hit + 0.099, 0.015, 0.05), -1.7 * accent)
                  for hit, accent in hits]
        total = sum(weight for weight, _ in breath)
        requested = sum(weight * level for weight, level in breath) / max(1.0, total)
        target = requested if requested < 0 else voice['gate']
        hold = 0.15 if total > 0 else max(0.0, hold - dt)
        tau = 0.025 if target > gate else (0.02 if hold > 0 else 0.07)
        gate = target + (gate - target) * math.exp(-dt / tau)
        gate_series.append(gate)
        opening = 6 * sum(activation(t, hit - 0.036, hit + 0.099, 0.02, 0.04) for hit, _ in hits)
        area_series.append(0.1 * voice['breathiness']**2 + 0.5 * min(1.0, opening / 2))
    return {
        'gate_max_abs_error': float(abs(trace['gate'] - np.repeat(gate_series, 64)[:len(trace)]).max()),
        'abduction_max_abs_error_cm2': float(abs(
            trace['abduction_cm2'] - np.repeat(area_series, 64)[:len(trace)]).max()),
    }


def observe(trace, pcm, hit, rate, limits):
    clock = (trace['frame'] + 1) / rate
    left, right = limits['closure_window_offset_seconds']
    area = np.minimum(trace['oral_minimum_cm2'], trace['pharynx_minimum_cm2'])
    closed = np.flatnonzero((clock >= hit + left) & (clock < hit + right)
                            & (area < limits['closed_area_cm2']))
    if not closed.size or closed[-1] + 1 >= len(trace):
        return {'dorsal_closure_and_release': False, 'reason': '閉鎖の始点と終点を採取できません'}
    start, release = int(closed[0]), int(closed[-1] + 1)
    before = float(trace['lung_boundary_dyn_cm2'][closed].min())
    left, right = limits['frication_window_offset_seconds']
    frication = (clock >= max(clock[release], hit + left)) & (clock < hit + right)
    if not np.any(frication):
        return {'dorsal_closure_and_release': False, 'reason': '開口後の摩擦窓に試料がありません'}
    lip_area = float(trace['lip_minimum_cm2'][closed].min())
    duration = (release - start) / rate
    gate = float(trace['gate'][frication].min())
    max_voicing = float(abs(trace['glottal_voicing'][frication]).max())
    flow = {name: float(trace[f'{name}_flow_cm3_s'][frication].min())
            for name in ('glottal', 'lip', 'constriction_jet')}
    constriction = float(abs(trace['constriction_noise_level'][frication]).max())
    forward = float(abs(trace['constriction_noise_forward_pressure'][frication]).max())
    # 逆向きの枝全体への注入を採る。噴流が吸気方向を向く出力フレームを選ぶ。
    reverse = float(abs(trace['constriction_noise_reverse_pressure'][
        frication & (trace['constriction_jet_flow_cm3_s'] < -limits['minimum_inward_jet_flow_cm3_s'])]).max(initial=0))
    rms = float(np.sqrt(np.mean(pcm[frication].astype('f8')**2)))
    peak_frame = int(np.flatnonzero(frication)[abs(pcm[frication]).argmax()])
    return {
        'dorsal_closure_and_release': bool(
            release - start == len(closed) and area[release] >= limits['closed_area_cm2']
            and duration >= limits['minimum_closed_seconds']
            and lip_area >= limits['minimum_lip_area_during_closure_cm2']),
        'suction_precedes_release': (before <= -limits['minimum_suction_before_release_dyn_cm2']
                                     and gate <= -limits['minimum_suction_gate']),
        'reverse_frication': (
            flow['glottal'] <= -limits['minimum_inward_glottal_flow_cm3_s']
            and flow['lip'] <= -limits['minimum_inward_lip_flow_cm3_s']
            and flow['constriction_jet'] <= -limits['minimum_inward_jet_flow_cm3_s']
            and constriction >= limits['minimum_constriction_noise_peak']
            and reverse >= limits['minimum_reverse_injection_peak_dyn_cm2']
            and rms >= limits['minimum_frication_pcm_rms']
            and max_voicing <= limits['maximum_voicing']),
        'first_closed_frame': start, 'first_open_frame': release, 'burst_frame': peak_frame,
        'first_closed_seconds': float(clock[start]), 'first_open_seconds': float(clock[release]),
        'closed_duration_seconds': duration, 'minimum_lip_area_during_closure_cm2': lip_area,
        'min_lung_boundary_before_release_dyn_cm2': before,
        'min_lung_boundary_during_frication_dyn_cm2': float(trace['lung_boundary_dyn_cm2'][frication].min()),
        'min_gate_during_frication': gate, 'maximum_voicing_during_frication': max_voicing,
        'minimum_flows_cm3_s': flow, 'constriction_noise_peak': constriction,
        'reverse_branch_pressure_peak_dyn_cm2': reverse, 'forward_branch_pressure_peak_dyn_cm2': forward,
        'frication_pcm_rms': rms,
    }


def events(trace, pcm, config):
    source, limits = config['beatbox_voice'], config['measurement']
    rate = source['voice']['output_sample_rate_hz']
    hit = source['hit_seconds']
    result = observe(trace, pcm, hit, rate, limits['inward_snare'])
    controls = control_errors(trace, source['voice'], [(hit, source['accent'])])
    tail = slice(-round(rate * limits['tail_window_seconds']), None)
    above = np.flatnonzero(abs(trace['gate']) > limits['maximum_tail_gate_magnitude'])
    settled = int(above[-1]) + 1 if above.size else 0
    recovered = (settled + 1) / rate if settled < len(trace) else None
    tail_pcm = float(abs(pcm[tail]).max())
    return {
        **result, 'control_errors': controls, 'gate_recovery_seconds': recovered, 'tail_pcm_peak': tail_pcm,
        'independent_signed_control': max(controls.values()) <= limits['control_absolute_tolerance'],
        'decayed_tail': (recovered is not None and recovered <= limits['maximum_tail_recovery_seconds']
                         and tail_pcm <= limits['maximum_tail_pcm']),
    }


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute, offsets=OFFSETS, observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in (*EVENT_CHECKS, 'independent_signed_control', 'decayed_tail'):
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
        WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/inventory.rs', 'crates/chimera/src/airway/network.rs',
        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/voice/human_airway.rs',
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
