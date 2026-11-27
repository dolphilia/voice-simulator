"""CSDで不足した /θ/ の舌先と開大を固定上流の歌唱・PCMに照合する。"""

import argparse
import os
from pathlib import Path
import sys

import numpy as np

from measure_csd_continuous_song import delta, samples
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-dental-theta.json'


def pick_gestures(gestures, keys):
    oral, = [g for g in gestures if g.get('label') == 'θ']
    opening, = [g for g in gestures if g.get('label') == 'voiceless']
    fields = ('t0', 't1', 'rampIn', 'rampOut', 'strength')
    return {'oral': {**{k: oral[k] for k in fields}, 'speed': oral['speed'], 'releaseHold': oral['releaseHold'],
                     'x_cm': oral['targets'][keys[0]], 'y_cm': oral['targets'][keys[1]],
                     'targets': len(oral['targets'])},
            'opening': {**{k: opening[k] for k in fields}, 'abduction_cm2': opening['targets'][keys[2]]}}


def expected_gestures(start, end, t):
    return {'oral': {'t0': start-t['oral_start_lead_seconds'], 't1': max(start+.01, end),
                     'rampIn': t['oral_ramps_seconds'][0], 'rampOut': t['oral_ramps_seconds'][1],
                     'strength': t['oral_strength'], 'speed': t['movement_speed'], 'releaseHold': t['oral_hold_seconds'],
                     'x_cm': t['tongue_tip_x_cm'], 'y_cm': t['female_tongue_tip_y_cm'], 'targets': 2},
            'opening': {'t0': start-t['abduction_start_lead_seconds'], 't1': end+t['abduction_end_tail_seconds'],
                        'rampIn': t['abduction_ramps_seconds'][0], 'rampOut': t['abduction_ramps_seconds'][1],
                        'strength': t['abduction_strength'], 'abduction_cm2': t['abduction_cm2']}}


def compare(expected, actual):
    return max(abs(value-actual[stage][key]) for stage, row in expected.items() for key, value in row.items())


def measure(case, base, probe, out, execute):
    rate, frames = (case['render'][k] for k in ('sample_rate_hz', 'frames'))
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    exe = str(WORKSPACE / 'target/release/vocal-cli')
    song = {**base['song_voice'], 'scores': [case['score']], 'render_end_seconds': frames/rate}
    spec = out / 'candidate.json'
    write(spec, {'song_voice': song})
    settings = out / 'candidate-plan.json'
    execute([exe, 'inspect', str(spec)], stdout=settings)
    primary, other = (out / f'candidate-{block}.wav' for block in case['render']['host_block_frames'])
    for path, block in zip((primary, other), case['render']['host_block_frames'], strict=True):
        execute([exe, 'render-pcm', str(spec), str(path), '--no-trace', str(block)])
    native = samples(primary, rate, frames)
    upper, upper_plan = out / 'upstream.f32', out / 'upstream-plan.json'
    upper_trace = out.parent / 'tmp' / 'upstream-state.csv'
    execute([str(probe), str(spec), 'matched', str(upper), str(upper_trace), str(upper_plan)])
    reference = np.fromfile(upper, dtype='<f4')
    if reference.shape != (frames,) or not np.isfinite(reference).all():
        raise ValueError('固定上流の波形が登録した長さまたは形式と一致しません')
    planned, = read(upper_plan)['plans']
    dental, vowel = planned['segments']
    expected = expected_gestures(dental['t0'], dental['t1'], case['targets'])
    candidate_state = read(settings)
    candidate_plan = pick_gestures(candidate_state['gestures'],
                                  ('tongue_tip_x_cm', 'tongue_tip_y_cm', 'abduction_cm2'))
    reference_plan = pick_gestures(planned['gestures'], ('ttX', 'ttY', 'abduction'))
    spec_speech = out / 'ipa-speech.json'
    speech = {k: song[k] for k in ('body', 'posture', 'internal_sample_rate_hz', 'voice')}
    write(spec_speech, {'speech_voice': {**speech, 'input': {'id': 'theta-ipa', 'text': 'ɑθɑ', 'rate': 1}}})
    speech_plan = out / 'ipa-speech-plan.json'
    execute([exe, 'inspect', str(spec_speech)], stdout=speech_plan)
    speech_gestures = read(speech_plan)['gestures']
    tol = case['tolerances']
    levels = delta(native, reference, tolerance=tol['pcm_absolute'])
    result = {
        'checks': {
            'same_mother_vowel_beat': dental['ipa'] == 'θ' and vowel['ipa'] == 'ɑ'
                and abs(vowel['t0']-case['score']['start_seconds']) <= tol['plan_absolute'],
            'oral_and_abduction_match': max(compare(expected, candidate_plan), compare(expected, reference_plan))
                <= tol['plan_absolute'],
            'same_pcm_across_host_blocks': sha256(primary) == sha256(other),
            'same_pcm_with_matched_settings': levels['maximum_absolute_difference'] <= tol['pcm_absolute'],
            'normal_ipa_speech_plans_theta': any(g.get('label') == 'θ' for g in speech_gestures),
        },
        'planned_segments': planned['segments'], 'independent_targets': expected,
        'candidate_targets': candidate_plan, 'upstream_targets': reference_plan, 'pcm_difference': levels,
        'upstream_dense_state_sha256': sha256(upper_trace),
    }
    upper_trace.unlink()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('作業用ディスクを指定してください')
    case = read(CASE)
    root = WORKSPACE / 'runs' / case['settings_run']
    app = root / 'manifest.json'
    original = read(app)
    if original['status'] != 'pass' or original['upstream_revision'] != case['upstream_revision']:
        parser.error('固定上流で照合した歌唱設定を確認できません')
    base = verified_file(root, original, 'artifacts/candidate-short-128.json')
    probe = verified_file(root, original, 'artifacts/upstream_csd_continuous_probe.exe')
    failed_path = WORKSPACE / 'runs' / case['failed_song_run'] / 'manifest.json'
    inputs = [CASE, app, base, probe, failed_path, WORKSPACE / 'tools/upstream_csd_continuous_probe.rs',
              Path(__file__).resolve(), WORKSPACE / 'tools/measure_csd_continuous_song.py',
              WORKSPACE / 'tools/measure_csd_envelope_timing.py', WORKSPACE / 'tools/measure_speech_timing.py',
              UPSTREAM / 'crates/chimera/src/phonetics/inventory.rs', UPSTREAM / 'crates/chimera/src/phonetics/planner.rs',
              *candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, read(base), probe, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
