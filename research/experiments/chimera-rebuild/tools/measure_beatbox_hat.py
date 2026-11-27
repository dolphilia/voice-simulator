"""単発ハイハット t の閉鎖、呼気、声門開大、摩擦を固定上流と照合する。"""

import argparse
from dataclasses import dataclass
import math
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_beatbox_kick as single
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-hat-t.json'
# 読解ノートに記した打音からの保持区間。単位は秒。
OFFSETS = [
    [-0.076, -0.015], [-0.045, 0.005], [-0.045, 0.005], [0.009, 0.035],
    [0.017, 0.035], [-0.025, 0.071], [-0.035, 0.031],
]


def activation(time, start, end, rise, fall):
    if start <= time <= end:
        return 1.0
    if start - rise < time < start:
        return 0.5 * (1.0 - math.cos(math.pi * (time - start + rise) / rise))
    if end < time < end + fall:
        return 0.5 * (1.0 + math.cos(math.pi * (time - end) / fall))
    return 0.0


@dataclass(frozen=True)
class PulmonicControl:
    breath_start: float
    opening_start: float
    breath_end: float
    breath_tail: float
    breath_goal: float
    opening_cm2: float


def open_hold_offset(length):
    return 0.005 + min(0.26, max(0.09, 1.6 * length))


def hat_control(hit, accent, *, open_length=None):
    if open_length is None:
        return PulmonicControl(hit - 0.035, hit - 0.025, hit + 0.031, 0.02, 1.25 * accent, 0.36)
    return PulmonicControl(
        hit - 0.035, hit - 0.025, hit + open_hold_offset(open_length), 0.09, 1.2 * accent, 0.4,
    )


def control_errors(trace, source, sounds):
    """登録した時間と時定数から制御周期ごとの呼気・開大を独立に求める。"""
    dt = 64 / source['output_sample_rate_hz']
    block = np.arange(0, len(trace), 64)
    gate = release_time = 0.0
    gate_series, opening_series = [], []
    for i, _ in enumerate(block):
        t = i * dt
        breath_weights = [
            (activation(t, sound.breath_start, sound.breath_end, 0.02, sound.breath_tail), sound.breath_goal)
            for sound in sounds
        ]
        total_breath = sum(weight for weight, _ in breath_weights)
        breath = sum(weight * goal for weight, goal in breath_weights) / max(1.0, total_breath)
        release_time = 0.15 if total_breath > 0.0 else max(0.0, release_time - dt)
        target = max(source['gate'], breath)
        tau = 0.025 if target > gate else (0.02 if release_time > 0.0 else 0.07)
        gate = target + (gate - target) * math.exp(-dt / tau)
        gate_series.append(gate)
        opening_weights = [
            (6 * activation(t, sound.opening_start, sound.breath_end + sound.breath_tail + 0.02, 0.02, 0.03),
             sound.opening_cm2)
            for sound in sounds
        ]
        opening = (sum(weight * area for weight, area in opening_weights)
                   / max(2.0, sum(weight for weight, _ in opening_weights)))
        opening_series.append(0.1 * source['breathiness']**2 + opening)
    return {
        'gate_max_abs_error': float(abs(trace['gate'] - np.repeat(gate_series, 64)[:len(trace)]).max()),
        'abduction_max_abs_error_cm2': float(abs(
            trace['abduction_cm2'] - np.repeat(opening_series, 64)[:len(trace)]
        ).max()),
    }


def events(trace, pcm, config):
    limits = config['measurement']
    data = config['beatbox_voice']
    rate = data['voice']['output_sample_rate_hz']
    clock = (trace['frame'] + 1) / rate
    hit = data['hit_seconds']

    def window(key):
        start, end = limits[key]
        return (clock >= hit + start) & (clock <= hit + end)

    closed = np.flatnonzero(window('closure_window_offset_seconds')
                            & (trace['oral_minimum_cm2'] < limits['closed_area_cm2']))
    if not closed.size or closed[-1] + 1 >= len(trace):
        return {'closed_then_opened': False}
    start, end = int(closed[0]), int(closed[-1] + 1)
    window_start, window_end = limits['closure_window_offset_seconds']
    dur, release = (end - start) / rate, float(clock[end] - hit)
    lip_area = float(trace['lip_minimum_cm2'][closed].min())
    open_area = float(trace['oral_minimum_cm2'][end])
    noise = window('frication_window_offset_seconds') & (trace['frame'] >= end)
    if not np.any(noise):
        return {'closed_then_opened': False, 'reason': '開口後の摩擦窓に試料がありません'}
    noise_fields = ('glottis_noise_level', 'constriction_noise_level', 'teeth_noise_level')
    noise_peaks = {field: float(abs(trace[field][noise]).max()) for field in noise_fields}
    rows = np.flatnonzero(noise)
    burst_frame = int(rows[np.argmax(abs(pcm[noise]))])
    rms = float(np.sqrt(np.mean(pcm[noise].astype('f8')**2)))
    tail_count = round(rate * limits['tail_window_seconds'])
    tail_gate = float(abs(trace['gate'][-tail_count:]).max())
    tail_pcm = float(abs(pcm[-tail_count:]).max())
    peak_gate = float(trace['gate'].max())
    peak_opening = float(trace['abduction_cm2'].max())
    max_voicing = float(abs(trace['glottal_voicing']).max())
    control = control_errors(trace, data['voice'], [hat_control(hit, data['accent'])])
    return {
        'closed_then_opened': bool(
            len(closed) == end - start and hit + window_start < clock[start] < hit + window_end
            and dur >= limits['minimum_closed_seconds']
            and open_area >= limits['closed_area_cm2']
            and limits['release_offset_seconds'][0] <= release <= limits['release_offset_seconds'][1]
            and lip_area >= limits['minimum_lip_area_during_closure_cm2']
        ),
        'oral_frication_after_release': (
            noise_peaks['constriction_noise_level'] >= limits['minimum_constriction_noise_peak']
            and noise_peaks['teeth_noise_level'] >= limits['minimum_teeth_noise_peak']
            and rms >= limits['minimum_event_rms_pcm']
        ),
        'breath_and_open_glottis_without_voicing': (
            peak_gate >= limits['minimum_gate_peak'] and peak_opening >= limits['minimum_peak_abduction_cm2']
            and max_voicing <= limits['maximum_voicing']
        ),
        'quiet_tail': tail_gate <= limits['maximum_tail_gate'] and tail_pcm <= limits['maximum_tail_pcm'],
        'independent_gate_and_abduction': max(control.values()) <= limits['control_absolute_tolerance'],
        'first_closed_frame': start, 'first_open_frame': end, 'burst_frame': burst_frame,
        'first_closed_seconds': float(clock[start]), 'first_open_seconds': float(clock[end]),
        'closed_cell': int(trace['oral_minimum_cell'][start]),
        'closed_seconds': dur, 'minimum_lip_area_during_closure_cm2': lip_area,
        'area_at_release_cm2': open_area, 'event_rms_pcm': rms,
        'frication_noise_peaks': noise_peaks, 'tail_gate': tail_gate, 'tail_pcm': tail_pcm,
        'peak_gate': peak_gate, 'peak_abduction_cm2': peak_opening, 'maximum_voicing': max_voicing,
        'control_errors': control,
    }


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute, offsets=OFFSETS, observe=events)
    current, target = result['candidate_events'], result['upstream_events']
    for check in ('closed_then_opened', 'oral_frication_after_release', 'breath_and_open_glottis_without_voicing',
                  'quiet_tail', 'independent_gate_and_abduction'):
        result['checks'][check] = current.get(check, False) and target.get(check, False)
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
        CASE, *single.PROBE_SOURCES, Path(__file__).resolve(), Path(single.__file__), Path(bilabial.__file__),
        Path(timing.__file__), Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py',
        *shared.candidate_sources(),
    ]
    upper_sources = [
        'crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/beatbox.rs',
        'crates/chimera/src/phonetics/consonantTargets.generated.json',
        'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/voice/human_voice.rs',
        'crates/chimera/src/voice/human_airway.rs',
    ]
    details = {
        'upstream_revision': revision, 'case_id': config['id'],
        'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_sources},
    }
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
