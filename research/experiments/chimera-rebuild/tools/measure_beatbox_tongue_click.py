"""舌打ち音 ! の閉鎖、空洞圧と放出音を固定上流に照合する。"""

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

CASE = WORKSPACE / 'cases/beatbox-tongue-click-v2.json'
OFFSETS = [[-0.144, -0.013], [-0.137, 0.008], [-0.113, 0.042],
           [-0.113, 0.042], [-0.023, 0.013]]
EVENT_CHECKS = ('dual_seal', 'growing_pocket_and_falling_pressure', 'front_release_and_burst')


def control_error(trace, rate, hits):
    """舌背の無次元変位を、調音器の外で制御周期ごとに復元する。"""
    dt = 64 / rate
    state = velocity = 0.0
    series = []
    for block in range((len(trace) + 63) // 64):
        t = block * dt
        strength = 40 * sum(activation(t, hit - 0.023, hit + 0.013, 0.04, 0.03) for hit in hits)
        target = strength / (0.05 + strength)
        angular_rate = 2 * math.pi * 9 * (2 if strength > 0 else 1)
        velocity += dt * (angular_rate**2 * (target - state) - 2 * angular_rate * velocity)
        state += dt * velocity
        series.append(state)
    return float(abs(trace['dorsum'] - np.repeat(series, 64)[:len(trace)]).max())


def oral_values(trace, field):
    cells = sum(bool(re.fullmatch(r'oral_cell_\d+_minimum_cm2', name)) for name in trace.dtype.names)
    return np.column_stack([trace[f'oral_cell_{cell}_{field}'] for cell in range(cells)])


def sealed_pocket(areas, frames, threshold, *, front_cell=None):
    """閉鎖した二つのセルの間が開く同じ組を探し、連続時間が最長のものを選ぶ。"""
    pairs = {}
    for frame in frames:
        closed = np.flatnonzero(areas[frame] < threshold)
        for back, front in zip(closed, closed[1:]):
            if front - back > 1 and (front_cell is None or front == front_cell):
                pairs.setdefault((int(back), int(front)), []).append(int(frame))
    periods = ((pair, run) for pair, rows in pairs.items()
               for run in np.split(rows, np.flatnonzero(np.diff(rows) != 1) + 1))
    return max(periods, key=lambda item: len(item[1]), default=None)


def observe(trace, pcm, hit, rate, limits):
    clock = (trace['frame'] + 1) / rate
    left, right = limits['closure_window_offset_seconds']
    window = np.flatnonzero((clock >= hit + left) & (clock < hit + right))
    areas = oral_values(trace, 'minimum_cm2')
    threshold = limits['closed_area_cm2']
    selected = sealed_pocket(areas, window, threshold)
    if selected is None:
        return {'dual_seal': False, 'reason': '閉鎖した2セル間に開いた区間が見つかりません'}
    (back, front), rows = selected
    start, release = int(rows[0]), int(rows[-1]) + 1
    if release >= len(trace):
        return {'dual_seal': False, 'reason': '観測の末尾でも二重閉鎖が続いています'}
    inside = np.s_[rows, back + 1:front]
    volumes = oral_values(trace, 'volume_cm3')[inside]
    volume = volumes.sum(axis=1)
    pressure = (oral_values(trace, 'pressure_dyn_cm2')[inside] * volumes).sum(axis=1) / volume
    dorsum = trace['dorsum'][rows]
    duration = len(rows) / rate
    opening_window = slice(release, release + round(rate * limits['peak_window_seconds']))
    peak_frame = release + int(abs(pcm[opening_window]).argmax())
    peak = float(abs(pcm[peak_frame]))
    flow = float(abs(trace['lip_flow_cm3_s'][opening_window]).max())
    front_first = bool(areas[release, front] >= threshold and areas[release, back] < threshold)
    lip_area = float(trace['lip_minimum_cm2'][rows].min())
    growth = float(volume.max() - volume[0])
    pressure_minimum = float(pressure.min())
    pressure_drop = float(pressure[0] - pressure_minimum)
    return {
        'dual_seal': (duration >= limits['minimum_dual_seal_seconds']
                      and lip_area >= limits['minimum_lip_area_cm2']),
        'growing_pocket_and_falling_pressure': (
            float(dorsum.max()) >= limits['minimum_dorsum_during_seal']
            and growth >= limits['minimum_volume_growth_cm3']
            and pressure_drop >= limits['minimum_pressure_drop_dyn_cm2'] and pressure_minimum < 0),
        'front_release_and_burst': (front_first and peak >= limits['minimum_burst_pcm']
                                    and flow >= limits['minimum_lip_flow_magnitude_cm3_s']),
        'first_closed_frame': start, 'first_open_frame': release, 'burst_frame': peak_frame,
        'first_closed_seconds': float(clock[start]), 'first_open_seconds': float(clock[release]),
        'closed_seconds': duration, 'seal_cells': [back, front], 'front_releases_first': front_first,
        'lip_minimum_cm2': lip_area, 'maximum_dorsum_during_seal': float(dorsum.max()),
        'pocket_initial_volume_cm3': float(volume[0]), 'pocket_peak_volume_cm3': float(volume.max()),
        'pocket_volume_growth_cm3': growth, 'pocket_pressure_drop_dyn_cm2': pressure_drop,
        'pocket_minimum_pressure_dyn_cm2': pressure_minimum,
        'pocket_minimum_pressure_seconds': float(clock[rows[pressure.argmin()]]),
        'maximum_lip_flow_magnitude_cm3_s': flow, 'burst_pcm_peak': peak,
    }


def events(trace, pcm, config):
    source, limits = config['beatbox_voice'], config['measurement']
    rate = source['voice']['output_sample_rate_hz']
    hit = source['hit_seconds']
    peak_tail = float(abs(pcm[-round(rate * limits['tail_window_seconds']):]).max())
    error = control_error(trace, rate, [hit])
    return {
        **observe(trace, pcm, hit, rate, limits['tongue_click']),
        'dorsum_max_abs_error': error, 'independent_dorsum': error <= limits['control_absolute_tolerance'],
        'no_performer_breath_and_quiet_tail': float(abs(trace['gate']).max()) == 0
                                            and peak_tail <= limits['maximum_tail_pcm'],
        'tail_pcm_peak': peak_tail,
    }


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute, offsets=OFFSETS, observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in (*EVENT_CHECKS, 'independent_dorsum', 'no_performer_breath_and_quiet_tail'):
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
        'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/control/articulators.rs',
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
