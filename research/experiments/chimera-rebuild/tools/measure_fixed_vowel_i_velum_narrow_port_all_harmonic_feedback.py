"""狭い口蓋帆ポートで第1〜22倍音に予測二次損失を一度戻す。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_narrow_port_bandwidth as bandwidth
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-narrow-port-all-harmonic-feedback.json'
READ, COUPLED = bandwidth.READ, bandwidth.COUPLED
feedback, supra, inlet, velum, narrow = bandwidth.feedback, bandwidth.supra, bandwidth.inlet, bandwidth.velum, bandwidth.narrow
EVIDENCE = ()
PORT_HYPOTHESIS = feedback.PORT_HYPOTHESIS
RECOVERY_HYPOTHESIS = 'all_harmonic_feedback_recovers_eighty_percent_and_beats_two_frequency_control'


def archive_inputs(case):
    spec = case['measurement']['reference']
    case_id = 'fixed-vowel-i-velum-narrow-port-bandwidth'
    run, header = record = COUPLED.smoothing.run_manifest(spec['run'], case_id, case['upstream_revision'])
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    rejected = {name for name, passed in READ(summary)['checks'].items() if not passed}
    if sha256(manifest) != spec['manifest_sha256'] or header['status'] != 'fail' or rejected != {bandwidth.HYPOTHESIS}:
        raise ValueError('先行実行のマニフェストと不成立の判定が登録値と一致しません')
    entry, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{case_id}.json')]
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('先行実行の保存ケースがマニフェストと一致しません')
    return {**bandwidth.archive_inputs(READ(definition)), 'narrow-bandwidth-case.json': definition,
            'narrow-bandwidth-manifest.json': manifest, 'narrow-bandwidth-summary.json': summary}


def evaluate(cfg, layout, recording, added, frequencies, archived_two, archived_band):
    pair = cfg['two_frequency_control_hz']
    pair_checks, two = feedback.evaluate_port(
        {**cfg, 'feedback_frequencies_hz': pair}, None, layout, recording, added, None)
    checks, detail = feedback.evaluate_port(
        {**cfg, 'feedback_frequencies_hz': frequencies}, None, layout, recording, added, None,
        include_measured_coefficients=True)
    conditions = detail['conditions']
    baseline = conditions['tangent']
    predicted = conditions['predicted_loss_feedback']
    observed = conditions[feedback.MEASURED_COEFFICIENTS]
    two_control = two['conditions']['predicted_loss_feedback']
    expected_control = archived_band['conditions']['measured_coefficients']
    expected_baseline = archived_band['conditions']['predicted']
    ideal_improvement = 1. - observed['nose_relative_error'] / baseline['nose_relative_error']
    if ideal_improvement <= 0.:
        raise ValueError('実測の22成分の差し替えで鼻端誤差が改善していません')
    recovery = detail['nose_error_reduction_fraction'] / ideal_improvement
    tolerance = cfg['numerical_identity_relative_error_lt']
    measured_loss_control = complex(*conditions['measured_loss_control']['nose_transfer'])
    control_error = float(abs(measured_loss_control / complex(*observed['nose_transfer']) - 1.))
    full_rows = {item['frequency_hz']: item for item in detail['feedback_frequencies']}
    pair_flows = np.array([complex(*item['port_flow_cm3_s']['predicted_loss_feedback']) for item in two['feedback_frequencies']])
    full_flows_at_pair = np.array([complex(*full_rows[f]['port_flow_cm3_s']['predicted_loss_feedback']) for f in pair])
    numerics = detail['numerical_relative_errors']
    numerics.update({
        'archived_unmodified_nose_transfer_matches': float(
            abs(complex(*baseline['nose_transfer']) / complex(*expected_baseline['nose_transfer']) - 1.)),
        'archived_measured_coefficients_control_matches': float(
            abs(complex(*observed['nose_transfer']) / complex(*expected_control['nose_transfer']) - 1.)),
        'archived_two_frequency_control_matches': float(abs(
            complex(*two_control['nose_transfer']) / complex(*archived_two['conditions']['predicted_loss_feedback']['nose_transfer']) - 1.)),
        'two_frequency_port_coefficients_match_full_solve': inlet.relative_l2(pair_flows, full_flows_at_pair),
    })
    checks.update({key: value < tolerance for key, value in numerics.items()})
    checks['two_frequency_control_numerically_verified'] = all(pair_checks.values())
    checks['measured_source_control_agrees_with_measured_coefficients'] = (
        control_error < cfg['measured_source_nose_transfer_relative_error_lt'])
    detail.update({
        'two_frequency_control': {'frequencies_hz': pair, **two_control},
        'measured_coefficients_nose_error_reduction_fraction': ideal_improvement,
        'fraction_of_measured_coefficients_improvement_recovered': recovery,
        'measured_source_control_nose_transfer_relative_error': control_error,
        'hypotheses': {
            PORT_HYPOTHESIS: detail['port_error_reduction_fraction'] >= cfg['minimum_port_error_reduction_fraction'],
            RECOVERY_HYPOTHESIS: (recovery >= cfg['minimum_recovered_nose_improvement_fraction']
                                  and predicted['nose_relative_error'] < two_control['nose_relative_error']),
        },
    })
    return checks, detail


def analyze(case, archive):
    cfg = case['measurement']
    prior_case = READ(archive['narrow-bandwidth-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'frequencies_hz', 'added_harmonics', 'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != prior_case[key] for key in frozen):
        raise ValueError('肺圧、開口、周波数または窓が保存済み実行と一致しません')
    pair_case = READ(archive['narrow-bandwidth-reference-case.json'])['measurement']
    if cfg['two_frequency_control_hz'] != pair_case['feedback_frequencies_hz']:
        raise ValueError('2周波数の対照が先行実行と一致しません')
    fundamental = cfg['fundamental_hz']
    added = [fundamental * j for j in cfg['added_harmonics']]
    frequencies = [fundamental * j for j in cfg['feedback_harmonics']]
    if frequencies != sorted(cfg['frequencies_hz'] + added):
        raise ValueError('補正対象が基準と追加成分を合わせた倍音群に一致しません')
    captured = {**archive, **{name: archive[f'narrow-{name}'] for name in narrow.CAPTURE_FILES},
                'archive-linear-inspect.json': archive['narrow-linear-inspect.json'],
                **{f'archive-{name}': archive[f'narrow-linear-upstream/{name}'] for name in narrow.NETWORK_FILES}}
    layout, recordings = supra.recorded_editions(case, captured)
    archived_two = READ(archive['narrow-bandwidth-reference-summary.json'])['editions']
    archived_band = READ(archive['narrow-bandwidth-summary.json'])['editions']
    checks, editions = {}, {}
    for edition, recording in recordings.items():
        results, editions[edition] = evaluate(cfg, layout, recording, added, frequencies,
                                             archived_two[edition], archived_band[edition])
        checks.update({f'{edition}/{key}': passed for key, passed in results.items()})
    candidate, upstream = (editions[edition] for edition in ('candidate', 'upstream'))
    flows = [np.array([complex(*row['port_flow_cm3_s']['predicted_loss_feedback']) for row in item['feedback_frequencies']])
             for item in (candidate, upstream)]
    noses = [np.array([complex(*row['nose_transfer']) for row in item['conditions'].values()])
             for item in (candidate, upstream)]
    checks['both_editions_agree'] = (max(inlet.relative_l2(*flows), inlet.relative_l2(*noses)) < cfg['edition_relative_error_lt']
                                    and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS):
        checks[hypothesis] = all(detail['hypotheses'][hypothesis] for detail in editions.values())
    return {'checks': checks, 'port_area_cm2': cfg['port_area_cm2'], 'nose_frequency_hz': cfg['frequency_hz'],
            'feedback_frequencies_hz': frequencies, 'editions': editions}


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
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial'],
                cwd=UPSTREAM, stdout=out / 'upstream-airway-adversarial.log')
        return analyze(case, archive)

    preceding = feedback.middle.bandwidth.preceding
    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        bandwidth, narrow, feedback, preceding, preceding.averaged, feedback.steady, inlet, supra,
        feedback.prior, feedback.harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
