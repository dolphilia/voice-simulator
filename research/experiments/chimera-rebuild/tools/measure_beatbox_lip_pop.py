"""唇を使う打音 P! の二重閉鎖、顎・舌背と口端放射を固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np

from measure_beatbox_hat import activation
import measure_beatbox_kick as single
import measure_beatbox_tongue_click as pocket
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-lip-pop.json'
OFFSETS = [[-0.141, -0.018], [-0.143, -0.003], [-0.119, 0.031],
           [-0.119, 0.031], [-0.069, 0.005]]
EVENT_CHECKS = ('dual_seal_and_expansion', 'lip_release_and_inward_burst', 'sealed_radiation_decay')


def control_errors(trace, rate, posture, hits):
    """顎・舌背の運動を、登録時刻と調音器の基準目標から独立に求める。"""
    dt = 64 / rate
    position = np.array([posture['jaw_cm'], posture['dorsum']])
    velocity = np.zeros(2)
    base = np.array([0.4, 0.0])
    angular_rates = 2 * math.pi * np.array([10.0, 9.0])
    pops = [hit for sound, hit in hits if sound == 'P!']
    kicks = [hit for sound, hit in hits if sound == 'B']
    states = []
    for block in range((len(trace) + 63) // 64):
        t = block * dt
        strong = 40 * sum(activation(t, hit - 0.069, hit + 0.005, 0.04, 0.05) for hit in pops)
        velar = 2.2 * sum(activation(t, hit - 0.119, hit + 0.031, 0.05, 0.05) for hit in pops)
        kick = 2.2 * sum(activation(t, hit - 0.085, hit - 0.010, 0.05, 0.05) for hit in kicks)
        weights = np.array([strong + velar + kick, strong])
        desired = (base * 0.05 + [1.6 * strong + 0.7 * velar + 0.3 * kick, strong]) / (0.05 + weights)
        speed_window = any(hit - 0.109 <= t <= hit + 0.055 for hit in pops)
        omega = angular_rates * (1 + (speed_window & (weights > 0)))
        velocity += dt * (omega**2 * (desired - position) - 2 * omega * velocity)
        position += dt * velocity
        states.append(position.copy())
    expected = np.repeat(states, 64, axis=0)[:len(trace)]
    actual = np.column_stack((trace['jaw_cm'], trace['dorsum']))
    jaw, dorsum = abs(actual - expected).max(axis=0)
    return {'jaw_max_abs_error_cm': float(jaw), 'dorsum_max_abs_error': float(dorsum)}


def observe(trace, pcm, hit, rate, internal_rate, limits):
    clock = (trace['frame'] + 1) / rate
    left, right = limits['closure_window_offset_seconds']
    window = np.flatnonzero((clock >= hit + left) & (clock < hit + right))
    areas = pocket.oral_values(trace, 'minimum_cm2')
    pressure = pocket.oral_values(trace, 'pressure_dyn_cm2')
    threshold = limits['closed_area_cm2']
    front = areas.shape[1] - 1
    selected = pocket.sealed_pocket(areas, window, threshold, front_cell=front)
    if selected is None:
        return {'dual_seal_and_expansion': False, 'reason': '唇と奥舌の閉鎖が重なりません'}
    (rear, _), rows = selected
    start, release = int(rows[0]), int(rows[-1]) + 1
    if release >= len(trace):
        return {'dual_seal_and_expansion': False, 'reason': '観測末尾でも唇と奥舌が閉じています'}
    inside = np.s_[rows, rear + 1:front]
    volume_at_cells = pocket.oral_values(trace, 'volume_cm3')[inside]
    volume = volume_at_cells.sum(axis=1)
    inside_pressure = (pressure[inside] * volume_at_cells).sum(axis=1) / volume
    dorsum = float(trace['dorsum'][rows].max())
    jaw_gain = float(trace['jaw_cm'][rows].max() - trace['jaw_cm'][start])
    duration = len(rows) / rate
    growth = float(volume.max() - volume[0])
    low_pressure = float(inside_pressure.min())
    pressure_drop = float(inside_pressure[0] - low_pressure)
    window_after = slice(release, release + round(rate * limits['peak_window_seconds']))
    burst_frame = release + int(abs(pcm[window_after]).argmax())
    pcm_peak = float(abs(pcm[burst_frame]))
    lip_flow = trace['lip_flow_cm3_s']
    min_flow = float(lip_flow[window_after].min())
    lip_first = bool(areas[release, front] >= threshold and areas[release, rear] < threshold)
    lip_closed = np.minimum(trace['lip_area_cm2'], trace['lip_minimum_cm2']) < threshold
    closed_pairs = window[window > 0]
    closed_pairs = closed_pairs[lip_closed[closed_pairs] & lip_closed[closed_pairs - 1]]
    factor = internal_rate // rate
    if not closed_pairs.size:
        return {'sealed_radiation_decay': False, 'reason': '同じ口端閉鎖内で減衰を観測できません'}
    mouth_pressure = pressure[:, front]
    p_error = float(abs(mouth_pressure[closed_pairs] - mouth_pressure[closed_pairs - 1] * 0.98**factor).max())
    flow_error = float(abs(lip_flow[closed_pairs] - lip_flow[closed_pairs - 1] * 0.995**factor).max())
    return {
        'dual_seal_and_expansion': (
            duration >= limits['minimum_dual_seal_seconds'] and dorsum >= limits['minimum_dorsum_during_seal']
            and jaw_gain >= limits['minimum_jaw_opening_during_seal_cm']
            and growth >= limits['minimum_volume_growth_cm3']
            and pressure_drop >= limits['minimum_pressure_drop_dyn_cm2'] and low_pressure < 0
        ),
        'lip_release_and_inward_burst': (
            lip_first and min_flow <= -limits['minimum_inward_lip_flow_cm3_s']
            and pcm_peak >= limits['minimum_burst_pcm']
        ),
        'sealed_radiation_decay': max(p_error, flow_error) <= limits['sealed_radiation_absolute_tolerance'],
        'first_closed_frame': start, 'first_open_frame': release, 'burst_frame': burst_frame,
        'first_closed_seconds': float(clock[start]), 'first_open_seconds': float(clock[release]),
        'closed_seconds': duration, 'lip_releases_first': lip_first, 'seal_cells': [rear, front],
        'maximum_dorsum_during_seal': dorsum, 'jaw_gain_during_seal_cm': jaw_gain,
        'pocket_initial_volume_cm3': float(volume[0]), 'pocket_peak_volume_cm3': float(volume.max()),
        'pocket_minimum_pressure_dyn_cm2': low_pressure,
        'pocket_minimum_pressure_seconds': float(clock[rows[inside_pressure.argmin()]]),
        'lip_pressure_when_pocket_is_lowest_dyn_cm2': float(mouth_pressure[rows[inside_pressure.argmin()]]),
        'pocket_pressure_drop_dyn_cm2': pressure_drop,
        'min_lip_flow_cm3_s': min_flow, 'burst_pcm_peak': pcm_peak,
        'sealed_radiation_pressure_error_dyn_cm2': p_error, 'sealed_radiation_flow_error_cm3_s': flow_error,
        'sealed_radiation_pairs': int(closed_pairs.size),
    }


def events(trace, pcm, config):
    source, limits = config['beatbox_voice'], config['measurement']
    rate = source['voice']['output_sample_rate_hz']
    hit = source['hit_seconds']
    controls = control_errors(trace, rate, source['posture'], [('P!', hit)])
    tail = float(abs(pcm[-round(rate * limits['tail_window_seconds']):]).max())
    return {
        **observe(trace, pcm, hit, rate, source['internal_sample_rate_hz'], limits['lip_pop']),
        'control_errors': controls,
        'independent_jaw_and_dorsum': max(controls.values()) <= limits['control_absolute_tolerance'],
        'no_performer_breath_and_quiet_tail': float(abs(trace['gate']).max()) == 0
                                            and tail <= limits['maximum_tail_pcm'],
        'tail_pcm_peak': tail,
    }


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute, offsets=OFFSETS, observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in (*EVENT_CHECKS, 'independent_jaw_and_dorsum', 'no_performer_breath_and_quiet_tail'):
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
    sources = [
        CASE, *single.PROBE_SOURCES, Path(__file__).resolve(), Path(pocket.__file__),
        WORKSPACE / 'tools/measure_beatbox_hat.py', Path(single.__file__), Path(bilabial.__file__),
        Path(timing.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
        *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/inventory.rs', 'crates/chimera/src/airway/network.rs',
        'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/control/articulators.rs',
        'crates/chimera/tests/airway_adversarial.rs', 'crates/chimera-cli/src/render.rs',
    )
    details = {
        'upstream_revision': revision, 'case_id': config['id'],
        'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper},
    }
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
