"""FK61_02の初期舌先だけを旧値へ戻し、冒頭PCMとtallの整列境界を照合する。"""

import argparse
import math
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_stressed_vowel_formants as formants
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_tall_output_gain_mfa import measure_formants
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-tall-initial-tip-mfa.json'
ROUTES = {
    'upstream': ('upstream', 'matched'),
    'matched': ('matched', 'matched'),
    'old_tip_fixed_window': ('old_tip', 'matched'),
    'old_tip_realigned': ('old_tip', 'old_tip'),
    'prior_render': ('prior', 'prior'),
}


def source_settings(case, paths):
    control, prior = (formants.read(paths[name])['speech_voice'] for name in ('matched_case', 'prior_case'))
    intervention, cfg = case['intervention'], case['measurement']
    tip, old_tip = (voice['posture']['tongue_tip_cm'] for voice in (control, prior))
    # 旧ケースで省略された3係数は既定値0として照合する。
    expected = control | {'posture': control['posture'] | {'tongue_tip_cm': old_tip}}
    old_defaults = {'source_variation': intervention['source_variation']} | prior
    return (control['input']['id'] == case['utterance']
            and control['voice']['output_gain'] == intervention['old_gain']
            and control['voice']['output_sample_rate_hz'] == cfg['sample_rate_hz']
            and control['internal_sample_rate_hz'] == cfg['internal_sample_rate_hz']
            and control['source_variation'] == intervention['source_variation']
            and tip == intervention['control_tip_cm'] and old_tip == intervention['historical_tip_cm']
            and expected == old_defaults)


def independent_tip_differences(case, posture):
    intervention, cfg = case['intervention'], case['measurement']
    position = np.subtract(intervention['historical_tip_cm'], intervention['control_tip_cm'])
    velocity = np.zeros_like(position)
    dt = cfg['control_frames'] / cfg['sample_rate_hz']
    omega = math.tau * cfg['tip_frequency_hz']
    block = -1
    rows = []
    for frame in cfg['independent_profile_frames']:
        while block < frame // cfg['control_frames']:
            velocity = (1 - 2 * omega * dt) * velocity - omega**2 * dt * position
            position = position + dt * velocity
            block += 1
        sample = posture[frame]
        observed = np.subtract(sample['old_tip_cm'], sample['matched_cm'])
        rows.append({'frame': frame, 'expected_delta_cm': position.tolist(), 'observed_delta_cm': observed.tolist(),
                     'max_axis_error_cm': float(np.max(np.abs(position - observed)))})
    return rows


def wave_difference(left, right):
    stats = aligned.describe_delta(left, right)
    changed = np.flatnonzero(left != right)
    return stats | {'last_changed_sample': int(changed[-1]) if changed.size else None}


def measure(case, align_case, analysis_case, paths, out, execute):
    cfg = case['measurement']
    if not source_settings(case, paths):
        raise ValueError('保存ケースが登録した初期舌先・固定条件と一致しません')
    waves, audio, points, checks = single.render(case, paths, out, execute, single.MODES)
    control, altered = (formants.read(out / f'{name}-case.json')['speech_voice'] for name in single.MODES)
    expected = control | {'posture': control['posture'] | {'tongue_tip_cm': case['intervention']['historical_tip_cm']}}
    posture = {row['frame']: row for row in points}
    independent = independent_tip_differences(case, posture)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'upstream-golden-analysis.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    tiers, align_checks, noise, _ = single.align(case, align_case, paths, waves, out, execute, single.MODES)
    indices = {mode: single.phone_at_word(tier, cfg) for mode, tier in tiers.items()}
    boundary = {mode: tier['phones'][indices[mode]][1] for mode, tier in tiers.items()}
    lpc = measure_formants(case, analysis_case, waves, tiers, indices, out, execute, routes=ROUTES)
    uid = case['utterance']
    samples = {'prior': aligned.wave_samples(paths['prior_mfa_wav'], cfg['sample_rate_hz'], np.int16)}
    for mode, tag in (('matched', f'{uid}-candidate'), ('old_tip', f'{uid}-old_tip')):
        samples[mode] = aligned.wave_samples(out / 'corpus' / tag / f'{tag}.wav', cfg['sample_rate_hz'], np.int16)
    begin, end = cfg['local_frames']
    early = cfg['preroll_frames']
    pcm = {'tip_change': wave_difference(audio['matched'], audio['old_tip']),
           'tip_change_preroll': wave_difference(audio['matched'][:early], audio['old_tip'][:early]),
           'tip_change_near_tall': wave_difference(audio['matched'][begin:end], audio['old_tip'][begin:end]),
           'old_tip_to_old_render': wave_difference(audio['old_tip'], audio['prior']),
           'matched_to_upstream': wave_difference(audio['matched'], audio['upstream']),
           'old_tip_to_upstream': wave_difference(audio['old_tip'], audio['upstream'])}
    mfa_pcm = {f'{mode}_to_old_render': wave_difference(samples[mode], samples['prior']) for mode in single.MODES}
    checks |= align_checks | {
        'only_initial_tip_is_changed': altered == expected,
        'independent_preroll_tip_differences': all(row['max_axis_error_cm'] <= cfg['tip_coordinate_tolerance_cm']
                                                   for row in independent),
        'registered_boundary_endpoints': boundary['matched'] == cfg['baseline_end_seconds']
                                         and boundary['prior'] == cfg['old_end_seconds'],
        'fixed_and_independent_formants_agree': all(row['agrees'] for rows in lpc.values() for row in rows),
    }
    predictions = {
        'preroll_pcm_changes': pcm['tip_change_preroll']['max_absolute_delta'] > cfg['early_pcm_difference_minimum'],
        'late_tip_positions_converge': all(row['maximum_axis_delta_cm'] <= cfg['maximum_late_tip_difference_cm']
                                           for row in points if row['frame'] >= begin - 1),
        'historical_mfa_pcm_reproduced': mfa_pcm['old_tip_to_old_render']['changed_frames'] == 0,
        'historical_tall_boundary_reproduced': boundary['old_tip'] == boundary['prior'],
        'historical_intervals_reproduced': tiers['old_tip'] == tiers['prior'],
    }
    return {'checks': checks, 'predictions': predictions, 'tall_vowel_end_seconds': boundary,
            'alignment_vs_control': aligned.compare_intervals(tiers['matched'], tiers['old_tip']),
            'alignment_vs_old': aligned.compare_intervals(tiers['prior'], tiers['old_tip']),
            'pcm': pcm, 'mfa_pcm': mfa_pcm, 'noise': noise, 'posture': points,
            'independent_preroll_tip': independent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline, reference, prior, archive, report = (formants.open_run(case[key], revision) for key in
        ('baseline', 'matched_render', 'previous_render', 'previous_alignment', 'formants'))
    align_case, align_snapshot = saved_case(archive, CASE.with_name(f"{case['previous_alignment']['case']}.json"))
    analysis, analysis_snapshot = saved_case(report, formants.CASE)
    uid = case['utterance']
    tag, old_tag = f'{uid}-old_gain', f'{uid}-candidate'
    paths = {key: formants.verified_path(run, 'artifacts/' + name) for key, run, name in (
        ('matched_case', baseline, 'old_gain-case.json'), ('matched_plan', baseline, 'old_gain-plan.json'),
        ('baseline_wav', baseline, 'old_gain-clean.wav'), ('matched_pcm', reference, 'matched-pcm.npz'),
        ('dictionary', baseline, 'synth.dict'), ('lab', baseline, f'corpus/{tag}/{tag}.lab'),
        ('matched_alignment_wav', baseline, f'corpus/{tag}/{tag}.wav'),
        ('matched_alignment', baseline, f'aligned/{tag}/{tag}.json'),
        ('prior_case', prior, f'{uid}/candidate.json'), ('prior_wav', prior, f'{uid}/candidate.wav'),
        ('prior_mfa_wav', archive, f'corpus/synth/{old_tag}/{old_tag}.wav'),
        ('prior_alignment', archive, f'aligned-1-synth/{old_tag}/{old_tag}.json'))}
    files = ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/control/articulators.rs',
             'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/analysis/lpc.rs',
             'crates/chimera-cli/src/main.rs', 'crates/chimera-cli/src/render.rs', formants.TSP_SOURCE,
             'crates/chimera/tests/apical.rs', 'crates/chimera/tests/golden_voice.rs',
             'crates/chimera/tests/golden_analysis.rs', 'tools/tsp/mfa.yaml')
    helpers = ('measure_tsp_active_duration.py', 'measure_tsp_again_initial_tip_mfa.py',
               'measure_tsp_f2_bandwidth_held_out.py', 'measure_tsp_held_out_matched_speech.py',
               'measure_tsp_matched_speech_mfa.py', 'measure_tsp_phone_boundaries.py',
               'measure_tsp_startup.py', 'measure_tsp_stressed_vowel_formants.py', 'measure_tsp_tall_output_gain_mfa.py')
    inputs = [CASE, Path(__file__).resolve(), align_snapshot, analysis_snapshot, *paths.values(), *candidate_sources(),
              *(run[0] / 'manifest.json' for run in (baseline, reference, prior, archive, report)), formants.PROBE,
              *(UPSTREAM / name for name in files), *(WORKSPACE / 'tools' / name for name in helpers)]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'aligner': align_case['aligner']}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, align_case, analysis, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
