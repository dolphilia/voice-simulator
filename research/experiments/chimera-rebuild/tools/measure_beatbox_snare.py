"""スネア Pf の閉鎖・破裂と唇歯摩擦を固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_beatbox_hat as lungs
import measure_beatbox_kick as single
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-snare-pf.json'
REVISED_CASE = WORKSPACE / 'cases/beatbox-snare-pf-v2.json'
OFFSETS = [[-0.1, -0.037], [-0.008, 0.062], [-0.063, 0.117], [-0.073, 0.057]]


def control_errors(trace, source, hits):
    breath = [lungs.PulmonicControl(hit - .073, hit - .063, hit + .057, .04, 1.7 * accent, .45)
              for hit, accent in hits]
    errors = lungs.control_errors(trace, source, breath)
    # 唇歯調音器は初期値0。摩擦目標の合成と二階の運動を制御周期で再計算する。
    dt = 64 / source['output_sample_rate_hz']
    position = velocity = 0.0
    series = []
    for frame in range(0, len(trace), 64):
        t = (frame // 64) * dt
        weight = 40 * sum(lungs.activation(t, hit - .008, hit + .062, .008, .018) for hit, _ in hits)
        target = weight / (.05 + weight)
        omega = 20 * math.pi * (1.6 if weight > 0.0 else 1.0)
        velocity += (omega**2 * (target - position) - 2 * omega * velocity) * dt
        position += velocity * dt
        series.append(position)
    errors['labiodental_max_abs_error'] = float(abs(
        trace['labiodental'] - np.repeat(series, 64)[:len(trace)]
    ).max())
    return errors


def events(trace, pcm, config):
    data = config['beatbox_voice']
    limits = config['measurement']
    rate = data['voice']['output_sample_rate_hz']
    clock = (trace['frame'] + 1) / rate
    start, end = limits['closure_window_seconds']
    mask = (clock >= start) & (clock < end)
    first_closed = np.flatnonzero(mask & (trace['lip_minimum_cm2'] < limits['closed_area_cm2']))
    if not first_closed.size or first_closed[-1] + 1 >= len(trace):
        return {'closed_then_opened': False}
    first, released = int(first_closed[0]), int(first_closed[-1] + 1)
    if trace['lip_minimum_cm2'][released] < limits['closed_area_cm2']:
        return {
            'closed_then_opened': False,
            'first_closed_frame': first,
            'first_closed_seconds': float(clock[first]),
            'closure_window_end_seconds': end,
            'reason': '閉鎖の観測窓が開口より先に終わりました',
        }
    pressure = trace['pressure_supra_dyn_cm2'][first_closed]
    pressure_rise = float(pressure.max() - pressure[0])
    burst_window = abs(pcm[released:released + round(rate * limits['burst_seconds_after_release'])])
    burst = int(burst_window.argmax())
    burst_pcm = float(burst_window[burst])

    start, end = limits['frication_window_seconds']
    frication = (clock >= start) & (clock < end)
    lab = float(np.median(trace['labiodental'][frication]))
    area = float(np.median(trace['oral_minimum_cm2'][frication]))
    distance = float(np.median(trace['noise_teeth_distance_cm'][frication]))
    constriction = float(abs(trace['constriction_noise_level'][frication]).max())
    teeth = float(abs(trace['teeth_noise_level'][frication]).max())
    lower, upper = limits['frication_median_oral_area_cm2']
    gate, opening, voicing = (float(abs(trace[key]).max()) for key in ('gate', 'abduction_cm2', 'glottal_voicing'))
    tail = round(rate * limits['tail_window_seconds'])
    tail_gate, tail_pcm = float(abs(trace['gate'][-tail:]).max()), float(abs(pcm[-tail:]).max())
    errors = control_errors(trace, data['voice'], [(data['hit_seconds'], data['accent'])])
    return {
        'closed_then_opened': bool(
            first_closed.size == released - first
            and (released - first) / rate >= limits['minimum_closed_seconds']
        ),
        'pressure_rise_and_release_burst': pressure_rise >= limits['minimum_pressure_rise_dyn_cm2']
                                           and burst_pcm >= limits['minimum_burst_pcm_peak'],
        'labiodental_frication_after_release': (
            float(clock[released]) < start
            and lab >= limits['minimum_labiodental_median'] and lower <= area <= upper
            and distance <= limits['maximum_median_distance_behind_teeth_cm']
            and constriction >= limits['minimum_constriction_noise_peak']
        ),
        'breath_and_open_glottis_without_voicing': (
            gate >= limits['minimum_peak_gate'] and opening >= limits['minimum_abduction_cm2']
            and voicing <= limits['maximum_voicing']
        ),
        'quiet_tail': tail_gate <= limits['maximum_tail_gate'] and tail_pcm <= limits['maximum_tail_pcm'],
        'independent_controls': max(errors.values()) <= limits['control_absolute_tolerance'],
        'first_closed_frame': first, 'first_open_frame': released, 'burst_frame': released + burst,
        'first_closed_seconds': float(clock[first]), 'first_open_seconds': float(clock[released]),
        'closed_pressure_rise_dyn_cm2': pressure_rise, 'burst_pcm_peak': burst_pcm,
        'frication_labiodental_median': lab, 'frication_median_oral_area_cm2': area,
        'frication_median_distance_behind_teeth_cm': distance,
        'frication_constriction_noise_peak': constriction, 'frication_teeth_noise_peak': teeth,
        'peak_gate': gate, 'peak_abduction_cm2': opening, 'maximum_voicing': voicing,
        'tail_gate': tail_gate, 'tail_pcm': tail_pcm, 'control_errors': errors,
    }


def measure(case_path, config, artifacts, execute):
    result = single.compare_render(case_path, config, artifacts, execute, offsets=OFFSETS, observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in ('closed_then_opened', 'pressure_rise_and_release_burst', 'labiodental_frication_after_release',
                 'breath_and_open_glottis_without_voicing', 'quiet_tail', 'independent_controls'):
        result['checks'][name] = all(row.get(name, False) for row in outcomes)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--version', choices=(1, 2), type=int, default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = CASE if args.version == 1 else REVISED_CASE
    config = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    inputs = [
        case_path, *single.PROBE_SOURCES, Path(__file__).resolve(), Path(lungs.__file__), Path(single.__file__),
        Path(bilabial.__file__), Path(timing.__file__), Path(shared.__file__),
        WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/consonantTargets.generated.json', 'crates/chimera/src/anatomy/human.rs',
        'crates/chimera/src/voice/human_airway.rs', 'crates/chimera-cli/src/render.rs',
    )
    details = {
        'upstream_revision': revision, 'case_id': config['id'],
        'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper},
    }
    return shared.record_measurement(args.run_id, case_path, inputs, details,
                                     lambda artifacts, execute: measure(case_path, config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
