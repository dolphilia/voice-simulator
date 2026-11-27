"""クラッシュ音 kch の奥舌閉鎖、摩擦位置と持続時間を固定上流に照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_beatbox_hat as hat
import measure_beatbox_kick as single
import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/beatbox-crash.json'
EVENT_CHECKS = ('closed_then_opened', 'constriction_shifts_forward', 'rounded_sustained_frication',
                'independent_gate_and_abduction')


def hold_offset(length):
    return 0.013 + max(0.14, min(0.34, 2 * length))


def offsets(length):
    end = hold_offset(length)
    return [[-0.071, -0.021], [-0.047, 0.013], [-0.047, 0.013], [0.007, 0.058],
            [0.015, 0.058], [0.030, end], [-0.022, end + 0.16], [-0.032, end]]


def breath_control(hit, accent, length):
    return hat.PulmonicControl(hit - 0.032, hit - 0.022, hit + hold_offset(length), 0.14,
                               1.75 * accent, 0.45)


def held_ends(gestures):
    return [g['t1'] for g in gestures if 'lip_protrusion_cm' in g['targets'] or 'breath' in g['targets']]


def rms(audio):
    return float(np.sqrt(np.mean(audio.astype('f8')**2)))


def events(trace, pcm, config):
    voice, limits = config['beatbox_voice'], config['measurement']
    rate = voice['voice']['output_sample_rate_hz']
    times = (trace['frame'] + 1) / rate
    hit = voice['hit_seconds']

    def window(name):
        start, end = limits[name + '_window_offset_seconds']
        return (times >= hit + start) & (times < hit + end)

    threshold = limits['closed_area_cm2']
    closed_area = np.minimum(trace['oral_minimum_cm2'], trace['pharynx_minimum_cm2'])
    closed = np.flatnonzero(window('closure') & (closed_area < threshold))
    if not closed.size or closed[-1] + 1 >= len(trace):
        return {'closed_then_opened': False, 'reason': '奥舌の閉鎖と解除を観測できません'}
    release = int(closed[-1]) + 1
    noise = trace['constriction_noise_level']
    cells = trace['constriction_noise_tract_cell']
    active = (noise >= limits['minimum_constriction_noise_level']) & (cells >= 0)
    early = np.flatnonzero(window('early_frication') & active & (trace['frame'] >= release))
    late_window = window('late_frication')
    late = np.flatnonzero(late_window & active)
    if not early.size or not late.size:
        return {'constriction_shifts_forward': False, 'reason': 'どちらかの窓で狭窄乱流がありません'}
    early_first = int(early[0])
    late_cell = float(np.median(cells[late]))
    shift = late_cell - float(cells[early_first])
    lip_median = float(np.median(trace['lip_protrusion_cm'][late]))
    sustained_rms = rms(pcm[late_window])
    burst = release + int(abs(pcm[release:early[-1] + 1]).argmax())
    control = breath_control(hit, voice['accent'], voice['step_seconds'])
    errors = hat.control_errors(trace, voice['voice'], [control])
    return {
        'closed_then_opened': bool(closed_area[release] >= threshold and release < late[0]),
        'constriction_shifts_forward': shift >= limits['minimum_forward_shift_cells'],
        'rounded_sustained_frication': (lip_median >= limits['minimum_rounded_lip_protrusion_cm']
                                       and sustained_rms >= limits['minimum_frication_pcm_rms']),
        'independent_gate_and_abduction': max(errors.values()) <= limits['control_absolute_tolerance'],
        'first_closed_frame': int(closed[0]), 'first_open_frame': release, 'burst_frame': burst,
        'first_open_seconds': float(times[release]),
        'first_constriction_noise_seconds': float(times[early_first]),
        'first_constriction_cell': int(cells[early_first]),
        'late_median_constriction_cell': late_cell, 'forward_shift_cells': shift,
        'early_constriction_noise_peak': float(noise[early].max()),
        'late_constriction_noise_peak': float(noise[late].max()),
        'late_teeth_noise_peak': float(trace['teeth_noise_level'][late_window].max()),
        'late_median_lip_protrusion_cm': lip_median,
        'late_median_lip_spread': float(np.median(trace['lip_spread'][late])),
        'late_pcm_rms': sustained_rms, 'control_errors': errors,
    }


def measure_pattern(result, config, scheduled, independent, streams):
    settings = config['beatbox_pattern']['voice']
    limits = config['measurement']
    registered = limits['crash']
    tol = limits['seconds_absolute_tolerance']
    first = next(row for row in scheduled if row['step']['sound'] == 'kch')
    ends = held_ends(first['gestures'])
    length = first['step']['length_seconds']
    checks = result['checks']
    checks['crash_holds_match_registered_duration'] = (
        abs(length - registered['expected_first_length_seconds']) <= tol
        and len(ends) == 2
        and all(abs(end - registered['expected_first_hold_end_seconds']) <= tol for end in ends)
    )
    controls = [breath_control(row['hit_seconds'], row['accent'], row['length_seconds'])
                for row in independent if row['sound'] == 'kch']
    observations = {}
    for name, trace, audio in streams:
        clock = (trace['frame'] + 1) / settings['output_sample_rate_hz']
        start, end = registered['late_window_seconds']
        window = (clock >= start) & (clock < end)
        observations[name] = {
            'control_errors': hat.control_errors(trace, settings, controls),
            'late_mean_gate': float(trace['gate'][window].mean()),
            'late_pcm_rms': rms(audio[window]),
            'late_constriction_noise_peak': float(trace['constriction_noise_level'][window].max()),
        }
    minimum, maximum = registered['late_gate_mean_range']
    checks['crash_late_breath_and_pcm'] = all(
        minimum <= row['late_mean_gate'] <= maximum and row['late_pcm_rms'] >= registered['minimum_late_pcm_rms']
        for row in observations.values()
    )
    checks['crash_independent_gate_and_abduction'] = all(
        max(row['control_errors'].values()) <= limits['control_absolute_tolerance']
        for row in observations.values()
    )
    result['crash'] = {'first_step_length_seconds': length,
                       'frication_and_breath_hold_end_seconds': ends, **observations}


def measure(config, artifacts, execute):
    length = config['beatbox_voice']['step_seconds']
    result = single.compare_render(CASE, config, artifacts, execute, offsets=offsets(length), observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in EVENT_CHECKS:
        result['checks'][name] = all(row.get(name, False) for row in outcomes)
    ends = held_ends(timing.read(artifacts / 'settings.json')['gestures'])
    limits = config['measurement']
    result['checks']['proportional_hold_end'] = len(ends) == 2 and all(
        abs(end - limits['expected_hold_end_seconds']) <= limits['gesture_absolute_tolerance'] for end in ends
    )
    result['frication_and_breath_hold_end_seconds'] = ends
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
        CASE, *single.PROBE_SOURCES, Path(__file__).resolve(), Path(hat.__file__), Path(single.__file__),
        Path(bilabial.__file__), Path(timing.__file__), Path(shared.__file__),
        WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources(),
    ]
    upper = (
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/phonetics/planner.rs',
        'crates/chimera/src/phonetics/inventory.rs', 'crates/chimera/src/control/beat_player.rs',
        'crates/chimera/src/phonetics/consonantTargets.generated.json',
        'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/airway/network.rs',
        'crates/chimera-cli/src/render.rs',
    )
    details = {'upstream_revision': revision, 'case_id': config['id'],
               'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper}}
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
