"""開ハイハット tss の単発キットと、摩擦終端の下限を固定上流と照合する。"""

import argparse
import json
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

CASE = WORKSPACE / 'cases/beatbox-open-hat-single.json'


def offsets(length):
    hold = hat.open_hold_offset(length)
    return [
        [-0.076, -0.015], [-0.045, 0.005], [-0.045, 0.005],
        [0.009, hold], [0.017, hold], [-0.025, hold + 0.11], [-0.035, hold],
    ]


def events(trace, pcm, config):
    data = config['beatbox_voice']
    limits = config['measurement']
    clock = (trace['frame'] + 1) / data['voice']['output_sample_rate_hz']
    start, end = limits['closure_window_seconds']
    closed = np.flatnonzero((clock >= start) & (clock < end)
                            & (trace['oral_minimum_cm2'] < limits['closed_area_cm2']))
    start, end = limits['frication_window_seconds']
    frication = np.flatnonzero((clock >= start) & (clock < end))
    if not closed.size or closed[-1] + 1 >= len(trace) or not frication.size:
        return {'closed_then_opened': False}
    released = int(closed[-1] + 1)
    rms = float(np.sqrt(np.mean(pcm[frication].astype('f8')**2)))
    teeth = float(abs(trace['teeth_noise_level'][frication]).max())
    voicing = float(abs(trace['glottal_voicing']).max())
    control = hat.hat_control(data['hit_seconds'], data['accent'], open_length=data['step_seconds'])
    errors = hat.control_errors(trace, data['voice'], [control])
    return {
        'closed_then_opened': bool(trace['oral_minimum_cm2'][released] >= limits['closed_area_cm2']
                                  and released < frication[0]),
        'first_closed_frame': int(closed[0]), 'first_open_frame': released,
        'first_open_seconds': float(clock[released]),
        'burst_frame': int(frication[np.argmax(abs(pcm[frication]))]),
        'frication_rms': rms, 'teeth_noise_peak': teeth, 'maximum_voicing': voicing,
        'control_errors': errors,
        'sustained_frication_without_voicing': (
            rms >= limits['minimum_frication_pcm_rms']
            and teeth >= limits['minimum_teeth_noise_peak']
            and voicing <= limits['maximum_voicing']
        ),
        'independent_gate_and_abduction': max(errors.values()) <= limits['control_absolute_tolerance'],
    }


def check_lower_clamp(config, artifacts, execute):
    registered = config['measurement']['lower_clamp_probe']
    lower = {
        **config,
        'beatbox_voice': {**config['beatbox_voice'], 'step_seconds': registered['step_seconds']},
    }
    case_path = artifacts / 'lower-case.json'
    case_path.write_text(json.dumps(lower, ensure_ascii=False, indent=2) + '\n')
    settings = artifacts / 'lower-settings.json'
    upper_plan = artifacts / 'lower-upstream-plan.json'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--',
             'inspect', str(case_path)], stdout=settings)
    probe = artifacts / f'{single.PROBE.stem}.exe'
    execute([str(probe), str(case_path), str(artifacts / 'lower-upstream.csv'),
             str(artifacts / 'lower-upstream.f32'), str(upper_plan)], cwd=UPSTREAM)
    candidate = timing.read(settings)
    reference = timing.read(upper_plan)
    comparison = single.compare_plans(candidate, reference, lower, offsets(registered['step_seconds']))
    ends = hold_ends(candidate)
    tol = lower['measurement']['gesture_absolute_tolerance']
    passed = (comparison['gesture_difference'] is None and comparison['independent_time_difference'] is None
              and len(ends) == 2 and all(abs(end - registered['expected_hold_end_seconds']) <= tol for end in ends))
    return passed, {'hold_end_seconds': ends, 'step_seconds': registered['step_seconds'], **comparison}


def hold_ends(settings):
    return [g['t1'] for g in settings['gestures'] if g.get('speed') == 1.4 or 'breath' in g['targets']]


def measure(config, artifacts, execute):
    result = single.compare_render(CASE, config, artifacts, execute,
                                   offsets=offsets(config['beatbox_voice']['step_seconds']), observe=events)
    outcomes = (result['candidate_events'], result['upstream_events'])
    for name in ('closed_then_opened', 'sustained_frication_without_voicing', 'independent_gate_and_abduction'):
        result['checks'][name] = all(row.get(name, False) for row in outcomes)
    hold_end = config['measurement']['expected_hold_end_seconds']
    tol = config['measurement']['gesture_absolute_tolerance']
    ends = hold_ends(timing.read(artifacts / 'settings.json'))
    result['checks']['proportional_hold_end'] = len(ends) == 2 and all(abs(end - hold_end) <= tol for end in ends)
    result['hold_end_seconds'] = ends
    result['checks']['lower_clamp'], result['lower_clamp'] = check_lower_clamp(config, artifacts, execute)
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
        'crates/chimera/src/phonetics/beatbox.rs', 'crates/chimera/src/control/beat_player.rs',
        'crates/chimera-cli/src/render.rs',
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
