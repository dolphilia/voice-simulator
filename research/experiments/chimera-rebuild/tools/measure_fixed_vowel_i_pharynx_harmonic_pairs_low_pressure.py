"""肺圧を下げた新規収録で、事前に選んだ咽頭の周波数対を検証する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_pharynx_harmonic_pairs as pairs
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-pharynx-harmonic-pairs-low-pressure.json'
READ, COUPLED = pairs.READ, pairs.COUPLED
supra, prior, harmonic, velum = pairs.supra, pairs.prior, pairs.harmonic, pairs.velum
EVIDENCE = prior.EVIDENCE
CAPTURE_INPUTS = ('natural-case.json', 'natural-network.csv', 'upper.f64', 'upper-network.f64')


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-pharynx-harmonic-pairs', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**pairs.archive_inputs(READ(definition)), 'harmonic-pairs-manifest.json': manifest,
            'harmonic-pairs-case.json': definition, 'harmonic-pairs-summary.json': COUPLED.verified_path(record, 'summary.json')}


def low_pressure_input(cfg, archive):
    original = READ(archive['natural-case.json'])
    if original['voice']['pressure_cm_h2o'] != cfg['reference_pressure_cm_h2o']:
        raise ValueError('保存済みの対照肺圧が事前登録値と一致しません')
    return {**original, 'voice': {**original['voice'], 'pressure_cm_h2o': cfg['pressure_cm_h2o']}}


def compare_capture(cfg, archive, out, layout, high_recordings, low_recordings):
    _, low_candidate, _, candidate_edges, candidate_source = low_recordings['candidate']
    _, low_upper, _, upper_edges, upper_source = low_recordings['upstream']
    order = prior.upstream_branch_order(candidate_edges, upper_edges)
    count = layout['node_count']
    aligned = np.column_stack((low_upper[:, :count], low_upper[:, count + order]))
    state_relative = harmonic.max_row_relative(low_candidate.T, aligned.T)
    case = READ(out / 'natural-case.json')
    inspect = READ(out / 'natural-inspect.json')
    rate = case['voice']['output_sample_rate_hz']
    frames = case['fixed_airway']['sample_count'] * rate // cfg['internal_rate_hz']
    native_pcm = COUPLED.read_pcm(out / 'natural.wav', frames, rate)
    upper_pcm = np.fromfile(out / 'upper.f32', dtype='<f4')
    if upper_pcm.shape != (frames,) or not np.isfinite(upper_pcm).all():
        raise ValueError('上流のPCMの標本数または有限性が条件外です')
    previous_pcm = COUPLED.read_pcm(archive['natural.wav'], frames, rate)
    pcm_relative = float(np.max(abs(native_pcm.astype(float) - upper_pcm)) / np.max(abs(upper_pcm)))
    means = {}
    for name, (tracks, *_) in low_recordings.items():
        current = float(tracks[harmonic.GLOTTIS][1:].mean())
        reference = float(high_recordings[name][0][harmonic.GLOTTIS][1:].mean())
        means[name] = {'reference': reference, 'lower_pressure': current, 'change_fraction': current / reference - 1}
    checks = {
        'only_voice_pressure_changes_and_geometry_matches': (
            case == low_pressure_input(cfg, archive)
            and inspect['case'] == case
            and inspect['fixed_airway'] == READ(archive['natural-inspect.json'])['fixed_airway']
            and READ(out / 'upper-columns.json') == list(velum.FIELDS)),
        'both_branches_and_upstream_traces_align': (
            candidate_source == upper_source
            and np.array_equal(candidate_edges[:, :3], upper_edges[order, :3])
            and state_relative < cfg['edition_relative_error_lt']),
        'pcm_matches_upstream_and_changes_with_pressure': (
            pcm_relative < cfg['upstream_pcm_peak_relative_error_lt']
            and not np.array_equal(native_pcm, previous_pcm)),
        'mean_glottal_flow_decreases_in_both_editions': all(value['change_fraction'] < 0. for value in means.values()),
    }
    return checks, {'network_peak_relative_error': state_relative, 'pcm_peak_relative_error': pcm_relative,
                    'mean_glottal_flow_cm3_s': means}


def analyze(case, archive, out):
    cfg = case['measurement']
    old_cfg = READ(archive['harmonic-pairs-case.json'])['measurement']
    frozen = ('pairs_hz', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz',
              'steady_window_internal_samples', 'pharynx_branch_count', 'minimum_nose_error_reduction_fraction')
    if any(cfg[key] != old_cfg[key] for key in frozen):
        raise ValueError('事前に選んだ周波数対または比較条件が変わっています')
    layout, high = supra.recorded_editions(case, archive)
    _, low = supra.recorded_editions(case, {**archive, **{name: out / name for name in CAPTURE_INPUTS}})
    checks, capture = compare_capture(cfg, archive, out, layout, high, low)
    checks['previous_pairs_hypothesis_remains_verified'] = bool(
        READ(archive['harmonic-pairs-summary.json'])['checks'][pairs.HYPOTHESIS])
    editions = {}
    for name, recording in low.items():
        conditions, editions[name] = pairs.inspect_edition(cfg, None, layout, *recording)
        checks.update({f'{name}/{key}': answer for key, answer in conditions.items()})
        checks[f'{name}/full_loss_replays_new_nose'] = (
            editions[name]['nose_relative_error']['all_fft_pairs_and_observed_reversal']
            < cfg['full_loss_nose_relative_error_lt'])
        rows = editions[name]['branches']
        editions[name]['reversal_branch_detection'] = {
            'hits': [row['nodes'] for row in rows if row['observed_reverse_samples'] and row['reconstructed_reverse_samples']],
            'missed': [row['nodes'] for row in rows if row['observed_reverse_samples'] and not row['reconstructed_reverse_samples']],
            'false_positive': [row['nodes'] for row in rows if not row['observed_reverse_samples'] and row['reconstructed_reverse_samples']],
        }
    transfers = [np.array([complex(*value) for value in edition['nose_transfer'].values()]) for edition in editions.values()]
    checks['new_nose_transfers_match_fixed_upstream'] = (
        harmonic.max_row_relative(transfers[0][None, :], transfers[1][None, :]) < cfg['edition_relative_error_lt'])
    decisions = [edition['nose_error_reduction_fraction'] >= cfg['minimum_nose_error_reduction_fraction']
                 for edition in editions.values()]
    checks['both_editions_agree_on_registered_prediction'] = decisions[0] == decisions[1]
    checks[pairs.HYPOTHESIS] = all(decisions)
    return {'checks': checks, 'pressure_cm_h2o': cfg['pressure_cm_h2o'], 'frequency_hz': cfg['frequency_hz'],
            'pairs_hz': cfg['pairs_hz'], 'capture': capture, 'editions': editions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(case)

    def measure(out, execute):
        prior.capture_voice_network(case, low_pressure_input(case['measurement'], archive), out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *COUPLED.SHARED.candidate_sources(), velum.UPPER,
              *(Path(module.__file__) for module in (pairs, pairs.preceding, supra, prior, harmonic, velum, COUPLED, COUPLED.SHARED)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/src/sources/glottis.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
