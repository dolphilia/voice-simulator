"""母音の目標・重み・調音器の状態を固定上流と独立した余弦ランプの計算に照合する。"""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess

import measure_uniform_tube as shared
import measure_speech_timing as timing
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE/'cases/vowel-gesture-score.json'
PROBE = WORKSPACE/'tools/upstream_vowel_gesture_probe.rs'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def compare_registered(example, score, tolerance):
    gestures, frames = score['gestures'], score['frames']
    expected = example['expected']
    actual = {'labels': [g['label'] for g in gestures]}
    for name, index, field in (('first_attack', 0, 'rampIn'), ('first_release', 0, 'rampOut'), ('second_attack', 1, 'rampIn'),
                               ('third_attack', 2, 'rampIn')):
        if name in expected:
            actual[name] = gestures[index][field]
    if 'overlap_seconds' in expected:
        first, second = gestures
        actual['overlap_seconds'] = first['t1'] + first['rampOut'] - (second['t0'] - second['rampIn'])
    if 'tongue_x' in expected:
        actual['tongue_x'] = [g['targets']['tongue_body_x_cm'] for g in gestures]
    if 'overlap_frame' in expected:
        overlap, finish = expected['overlap_frame'], expected['hold_finish_frame']
        actual.update(overlap_frame=overlap, hold_finish_frame=finish,
                      weighted_jaw=frames[overlap]['blend']['jaw_cm']['value'],
                      weight=frames[overlap]['blend']['jaw_cm']['weight'],
                      hold_speed=frames[finish]['blend']['velum_cm2']['speed'],
                      after_hold_speed=frames[finish+1]['blend']['velum_cm2']['speed'])
    failure, _ = timing.compare(actual, expected, tolerance)
    return failure


def compare_entry(example, actual, upper, count, tolerances):
    if example['id'] != actual['id'] or example['id'] != upper['id']:
        raise ValueError('ケース・候補・上流のIDが一致しません')
    actual, reference = actual['score'], upper['score']
    gesture_tol, state_tol = tolerances
    gesture_diff, gesture_max = timing.compare(actual['gestures'], reference['gestures'], gesture_tol)
    frames = actual['frames']
    first_frame = None
    state_max = blend_max = 0.0
    if len(frames) != count or len(reference['frames']) != count:
        raise ValueError('制御フレーム数が設定値と一致しません')
    for i, (a, b) in enumerate(zip(frames, reference['frames'], strict=True)):
        part, part_peak = timing.compare({k: v for k, v in a.items() if k != 'articulators'},
                                         {k: v for k, v in b.items() if k != 'articulators'}, gesture_tol)
        state, state_peak = timing.compare(a['articulators'], b['articulators'], state_tol)
        if first_frame is None and (part or state):
            first_frame = {'frame': i, 'time_seconds': a['time_seconds'], 'difference': part or state}
        blend_max = max(blend_max, part_peak)
        state_max = max(state_max, state_peak)
    prereg = compare_registered(example, actual, gesture_tol)
    return {
        'id': example['id'], 'gestures': len(actual['gestures']), 'frames': len(frames),
        'first_gesture_difference': gesture_diff, 'first_frame_difference': first_frame,
        'first_registered_difference': prereg, 'gesture_max_abs_error': gesture_max,
        'activation_and_blend_max_abs_error': blend_max, 'state_max_abs_error': state_max,
        'passed': not (gesture_diff or first_frame or prereg),
    }


def analytic_checks(entries, observation, tolerance):
    frames = entries['vcv']['frames']
    # 発話区間の検証で得た /ɑ p ɑ/ の時刻を使い、余弦式を sin²・cos² で計算する。
    params = ((.11, .20938024, .07, .0419), (.28913024, .48809024, .0698125, .042))

    def fraction(t, start, end, attack, release):
        if t < start:
            u = max(0, (t - start + attack) / attack)
            return math.sin(.5 * math.pi * u)**2
        u = min(1, max(0, (t - end) / release))
        return math.cos(.5 * math.pi * u)**2 if u < 1 else 0.0

    dt = observation['control_block_samples'] / observation['sample_rate_hz']
    expected_frames = []
    overlap = []
    actual = []
    for i, row in enumerate(frames):
        t = i * dt
        w = [fraction(t, *p) for p in params]
        total = math.fsum(w)
        blended = 2.022 if total > 0 else 0.0
        effective = (.05 * 2.9 + total * 2.022) / (.05 + total)
        if all(a > 0 for a in row['activation']):
            overlap.append(i)
        expected_frames.append([*w, total, blended, effective])
        actual.append([*row['activation'], row['blend']['tongue_body_x_cm']['weight'],
                       row['blend']['tongue_body_x_cm']['value'],
                       row['articulators']['tongue_body_x_cm']['effective']])
    vcv_diff, vcv_max = timing.compare(actual, expected_frames, tolerance)

    synthetic = entries['synthetic']['frames']
    angle_checks = [
        [*synthetic[125]['activation'], synthetic[125]['blend']['f0_hz']['weight'],
         synthetic[125]['blend']['breath']['weight']],
        [synthetic[125]['articulators']['velum_cm2']['effective'],
         synthetic[125]['articulators']['velum_cm2']['applied_speed']],
        [synthetic[275]['blend']['jaw_cm']['weight'], synthetic[275]['blend']['jaw_cm']['speed'],
         synthetic[275]['articulators']['jaw_cm']['applied_speed']],
        [synthetic[300]['blend']['velum_cm2']['weight'], synthetic[300]['blend']['velum_cm2']['speed'],
         synthetic[300]['articulators']['velum_cm2']['applied_speed']],
        [synthetic[301]['blend']['velum_cm2']['speed']],
    ]
    expected = [[1, .5, 1, 1.5], [.4, 2], [1.5, 2, 2], [0, 2, 1], [1]]
    synthetic_diff, synthetic_max = timing.compare(angle_checks, expected, tolerance)

    # 目標が変わる条件で、舌体も十分に異なる位置まで移動する。
    trajectory = entries['transition']['frames']
    early = trajectory[120]['articulators']['tongue_body_x_cm']['position']
    late = trajectory[320]['articulators']['tongue_body_x_cm']['position']
    return {
        'vcv_first_difference': vcv_diff, 'vcv_max_abs_error': vcv_max,
        'vcv_overlap_frames': [overlap[0], overlap[-1]] if overlap else [],
        'vcv_overlap_frame_count': len(overlap),
        'synthetic_first_difference': synthetic_diff, 'synthetic_max_abs_error': synthetic_max,
        'transition_tongue_x_cm': [early, late],
        'passed': vcv_diff is None and synthetic_diff is None and early - late > 0.9,
    }


def candidate_catalog(symbols, body, revision, directory, execute):
    directory.mkdir()
    result = {}
    for index, symbol in enumerate(symbols):
        path = directory / f'{index:02d}-case.json'
        report = directory / f'{index:02d}-inspect.json'
        case = {
            'id': f'vowel-catalog-{index:02d}', 'upstream_revision': revision,
            'hypothesis': '較正済み母音の部分目標を表示できる。',
            'body': body, 'posture': {'vowel': symbol}, 'measurement': {'frames': 1},
        }
        timing.write(path, case)
        execute([*CLI, 'inspect', str(path)], stdout=report)
        result[symbol] = timing.read(report)['vowel_targets']
    return result


def measure(case, artifacts, execute):
    actual_path, reference = artifacts/'vowel-gesture-score.json', artifacts/'upstream-vowel-gesture-score.json'
    execute([*CLI, 'inspect', str(CASE)], stdout=artifacts/'settings.json')
    execute([*CLI, 'render', str(CASE), str(actual_path)])
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--lib', 'control::score'],
            cwd=UPSTREAM, stdout=artifacts/'upstream-score-tests.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'live_control'],
            cwd=UPSTREAM, stdout=artifacts/'upstream-live-control.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_planning',
             'utterances_match_typescript'], cwd=UPSTREAM, stdout=artifacts/'upstream-utterance-golden.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'fast_speech'],
            cwd=UPSTREAM, stdout=artifacts/'upstream-fast-speech.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(CASE)], cwd=UPSTREAM, stdout=reference)
    catalog_path = artifacts/'upstream-catalog.json'
    execute([str(probe), '--catalog'], cwd=UPSTREAM, stdout=catalog_path)

    actual = timing.read(actual_path)['entries']
    upper = timing.read(reference)['entries']
    inputs = case['speech_timing']
    observation = inputs['observe_score']
    measurement = case['measurement']
    tolerances = (measurement['gesture_absolute_tolerance'], measurement['state_absolute_tolerance'])
    rows = [compare_entry(example, candidate, upstream, observation['frames'], tolerances)
            for example, candidate, upstream in zip(inputs['inputs'], actual, upper, strict=True)]
    analytic = analytic_checks({entry['id']: entry['score'] for entry in actual}, observation, tolerances[0])
    catalog = timing.read(catalog_path)
    candidates = candidate_catalog(catalog, 'male', case['upstream_revision'], artifacts / 'catalog', execute)

    return {
        'checks': {
            'all_cases_match_upstream_and_registered_predictions': all(row['passed'] for row in rows),
            'independent_calculations': analytic['passed'],
            'all_calibrated_male_targets_match': catalog == candidates
            and len(catalog) == measurement['vowel_catalog_count'],
        },
        'cases': rows,
        'analytic_checks': analytic,
        'control_period_seconds': observation['control_block_samples'] / observation['sample_rate_hz'],
        'catalog_count': len(catalog),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__), Path(timing.__file__),
               WORKSPACE/'tools/upstream_baseline.py', *shared.candidate_sources()]
    upper = ['phonetics/planner.rs', 'phonetics/vowelTargets.generated.json',
             'control/score.rs', 'control/articulators.rs']
    details = {'upstream_revision': revision, 'case_id': case['id'],
               'upper_source_sha256': {name: sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper}}
    return shared.record_measurement(args.run_id, CASE, sources, details,
                                     lambda artifacts, execute: measure(case, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
