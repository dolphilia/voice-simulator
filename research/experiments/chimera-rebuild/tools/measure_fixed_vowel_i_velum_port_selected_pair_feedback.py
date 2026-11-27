"""鼻端の誤差から選んだ2倍音を、予測二次損失で一度補正する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_complex_pair as complex_pair
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-selected-pair-feedback.json'
sensitivity = complex_pair.sensitivity
feedback = sensitivity.feedback
READ, COUPLED = feedback.READ, feedback.COUPLED
inlet, supra, velum = feedback.inlet, feedback.supra, feedback.velum
EVIDENCE = ()
PORT_HYPOTHESIS = feedback.PORT_HYPOTHESIS
RECOVERY_HYPOTHESIS = 'one_feedback_recovers_eighty_percent_of_measured_pair_improvement'


def archive_inputs(case):
    spec = case['measurement']['reference']
    prior_case_id = 'fixed-vowel-i-velum-port-complex-pair'
    run, header = record = COUPLED.smoothing.run_manifest(spec['run'], prior_case_id, case['upstream_revision'])
    manifest = run / 'manifest.json'
    summary = COUPLED.verified_path(record, 'summary.json')
    rejected = {name for name, passed in READ(summary)['checks'].items() if not passed}
    if sha256(manifest) != spec['manifest_sha256'] or header['status'] != 'fail' or rejected != {complex_pair.TRANSFER_HYPOTHESIS}:
        raise ValueError('先行実行のマニフェストと不成立の判定が登録値と一致しません')
    entry, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{prior_case_id}.json')]
    definition = run / header['source_snapshot'] / entry['path']
    if sha256(definition) != entry['sha256']:
        raise ValueError('先行実行の保存ケースがマニフェストと一致しません')
    return {**complex_pair.archive_inputs(READ(definition)), 'complex-pair-manifest.json': manifest,
            'complex-pair-case.json': definition, 'complex-pair-summary.json': summary}


def evaluate_pair(cfg, baseline, saved_coefficients, measured_pair, layout, recording, added):
    by_frequency = {row['frequency_hz']: complex(*row['predicted_flow_cm3_s']) for row in saved_coefficients['harmonics']}
    archived_coefficients = np.array([by_frequency[f] for f in cfg['feedback_frequencies_hz']])
    checks, detail = feedback.evaluate_port(cfg, baseline, layout, recording, added, archived_coefficients)

    expected = measured_pair['fixed_selected_pair']
    ideal_improvement = expected['finite_nose_error_reduction_fraction']
    if ideal_improvement <= 0.:
        raise ValueError('実測差し替え対照に正の改善がありません')
    recovery = detail['nose_error_reduction_fraction'] / ideal_improvement
    archived_target = complex(*saved_coefficients['baseline_nose_transfer']) + complex(*expected['finite_nose_transfer_change'])
    measured_control = complex(*detail['conditions']['measured_loss_control']['nose_transfer'])
    control_difference = float(abs(measured_control - archived_target) / abs(archived_target))
    checks['measured_loss_control_matches_finite_pair_replacement'] = (
        control_difference < cfg['measured_source_nose_transfer_relative_error_lt'])
    detail.update({
        'finite_measured_pair_nose_error_reduction_fraction': ideal_improvement,
        'fraction_of_finite_measured_pair_improvement_recovered': recovery,
        'measured_source_control_nose_transfer_relative_error': control_difference,
        'hypotheses': {
            PORT_HYPOTHESIS: detail['port_error_reduction_fraction'] >= cfg['minimum_port_error_reduction_fraction'],
            RECOVERY_HYPOTHESIS: recovery >= cfg['minimum_recovered_nose_improvement_fraction'],
        },
    })
    return checks, detail


def analyze(case, archive):
    cfg = case['measurement']
    earlier_case = READ(archive['complex-pair-case.json'])['measurement']
    initial_case = READ(archive['loss-sensitivity-case.json'])['measurement']
    frozen = ('pressure_cm_h2o', 'internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
              'port_nodes', 'port_area_cm2', 'supraglottal_branch_count')
    if any(cfg[key] != earlier_case[key] for key in frozen):
        raise ValueError('観測条件が保存済みの実行と一致しません')
    if any(cfg[key] != initial_case[key] for key in ('frequencies_hz', 'added_harmonics')):
        raise ValueError('基準の周波数群が保存済みの実行と一致しません')
    saved = READ(archive['complex-pair-summary.json'])
    chosen = cfg['feedback_frequencies_hz']
    if chosen != saved['selected_pair_hz']:
        raise ValueError('補正対象が先行する計測で選んだ2成分と一致しません')
    added = [cfg['fundamental_hz'] * j for j in cfg['added_harmonics']]
    baseline = READ(archive['middle-harmonics-summary.json'])['pressures']
    coefficients = READ(archive['loss-sensitivity-summary.json'])['pressures']
    low = {**archive, **{name: archive[f'low-{name}'] for name in inlet.lower.CAPTURE_INPUTS}}
    checks, pressures = {}, {}
    for pressure, inputs in (('reference', archive), ('lower', low)):
        if READ(inputs['natural-case.json'])['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o'][pressure]:
            raise ValueError('収録の肺圧が事前登録値と一致しません')
        layout, recordings = supra.recorded_editions(case, inputs)
        pressures[pressure] = {}
        for edition, recording in recordings.items():
            results, pressures[pressure][edition] = evaluate_pair(
                cfg, baseline[pressure][edition], coefficients[pressure][edition],
                saved['pressures'][pressure][edition], layout, recording, added)
            checks.update({f'{pressure}/{edition}/{key}': passed for key, passed in results.items()})
        candidate, upstream = (pressures[pressure][edition] for edition in ('candidate', 'upstream'))
        port_vectors = [
            np.array([complex(*value) for row in result['feedback_frequencies'] for value in row['port_flow_cm3_s'].values()])
            for result in (candidate, upstream)]
        nose_vectors = [
            np.array([complex(*row['nose_transfer']) for row in result['conditions'].values()])
            for result in (candidate, upstream)]
        checks[f'{pressure}/both_editions_agree'] = (
            max(inlet.relative_l2(*port_vectors), inlet.relative_l2(*nose_vectors)) < cfg['edition_relative_error_lt']
            and candidate['hypotheses'] == upstream['hypotheses'])
    for hypothesis in (PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS):
        checks[hypothesis] = all(detail['hypotheses'][hypothesis] for group in pressures.values() for detail in group.values())
    return {'checks': checks, 'port_nodes': cfg['port_nodes'], 'feedback_frequencies_hz': chosen,
            'nose_frequency_hz': cfg['frequency_hz'], 'pressures': pressures}


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

    middle = feedback.middle
    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        complex_pair, sensitivity, feedback, middle, middle.bandwidth.preceding, middle.bandwidth.preceding.averaged,
        feedback.steady, inlet, supra, feedback.prior, feedback.harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
