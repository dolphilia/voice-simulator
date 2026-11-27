"""固定 /i/ の口蓋帆ポートを0.30 cm²にして、同じ44倍音の補正を照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_narrow_port_upper_harmonics as upper
import measure_fixed_vowel_i_velum_port_selected_pair_feedback as selected_pair
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-wide-port-upper-harmonics.json'
READ, COUPLED = upper.READ, upper.COUPLED
feedback, inlet, supra, velum, pair = upper.feedback, upper.inlet, upper.supra, upper.velum, upper.pair
EVIDENCE = ()
PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS = upper.PORT_HYPOTHESIS, upper.RECOVERY_HYPOTHESIS
MODEL_SETTINGS = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples',
                  'frequencies_hz', 'added_harmonics', 'port_nodes', 'supraglottal_branch_count')


def archive_inputs(case):
    cfg = case['measurement']
    archive = {}
    for label, module, spec in (
        ('wide-pair', selected_pair, cfg['reference']),
        ('narrow-upper', upper, cfg['narrow_reference']),
    ):
        record, manifest, definition = COUPLED.smoothing.verified_reference(
            {'run': spec['run'], 'case': module.CASE.stem, 'sha256': spec['manifest_sha256']},
            case['upstream_revision'])
        archive.update({f'{label}-case.json': definition, f'{label}-manifest.json': manifest,
                        f'{label}-summary.json': COUPLED.verified_path(record, 'summary.json')})
        prior_inputs = module.archive_inputs(READ(definition))
        if label == 'wide-pair':
            archive.update(prior_inputs)
        else:
            archive['narrow-natural-case.json'] = prior_inputs['narrow-natural-case.json']
    return archive


def verify_settings(cfg, archive):
    wide = READ(archive['wide-pair-case.json'])['measurement']
    narrow = READ(archive['narrow-upper-case.json'])['measurement']
    if (any(cfg[key] != wide[key] or cfg[key] != narrow[key] for key in MODEL_SETTINGS)
            or cfg['upper_harmonics'] != narrow['upper_harmonics']
            or cfg['pressure_cm_h2o'] != wide['pressure_cm_h2o']['reference']
            or cfg['pressure_cm_h2o'] != narrow['pressure_cm_h2o']
            or cfg['port_area_cm2'] != wide['port_area_cm2']
            or narrow['port_area_cm2'] >= cfg['port_area_cm2']):
        raise ValueError('開口、肺圧、周波数または観測窓が登録済みの比較と一致しません')
    for name, area in (('natural-case.json', cfg['port_area_cm2']), ('narrow-natural-case.json', narrow['port_area_cm2'])):
        capture = READ(archive[name])
        override = capture['fixed_voice_probe'].pop('velum_area_override_cm2')
        if override != area or capture['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o']:
            raise ValueError('保存収録の音響ポートまたは肺圧が登録値と一致しません')
        if name == 'natural-case.json':
            wide_setup = capture
        elif wide_setup != capture:
            raise ValueError('音響ポートの開口以外の収録設定が一致しません')


def compare_nose(detail):
    conditions = detail['conditions']
    baseline = complex(*conditions[upper.LOW_ONLY]['nose_transfer'])
    control = conditions[feedback.MEASURED_COEFFICIENTS]
    measured = complex(*control['nose_transfer'])
    return {
        'measured_addition_nose_error_reduction': conditions[upper.LOW_ONLY]['nose_relative_error'] - control['nose_relative_error'],
        'measured_addition_complex_nose_transfer_change': pair(measured - baseline),
        'relative_nose_transfer_difference_from_measured_addition': {
            name: float(abs(complex(*conditions[name]['nose_transfer']) / measured - 1.))
            for name in ('tangent', upper.PREDICTED)},
    }


def analyze(case, archive):
    cfg = case['measurement']
    verify_settings(cfg, archive)
    fundamental = cfg['fundamental_hz']
    lower = [fundamental * k for k in range(1, 23)]
    high = [fundamental * k for k in cfg['upper_harmonics']]
    added = [fundamental * k for k in cfg['added_harmonics']]
    if sorted(cfg['frequencies_hz'] + added) != lower or high != [fundamental * k for k in range(23, 45)]:
        raise ValueError('周波数の構成が第1〜44倍音と一致しません')
    layout, recordings = supra.recorded_editions(case, archive)
    baseline = READ(archive['middle-harmonics-summary.json'])['pressures']['reference']
    sensitivity = READ(archive['loss-sensitivity-summary.json'])['pressures']['reference']
    narrow = READ(archive['narrow-upper-summary.json'])['editions']
    checks, editions = {}, {}
    tol = cfg['numerical_identity_relative_error_lt']
    for edition, recording in recordings.items():
        saved = {row['frequency_hz']: complex(*row['predicted_flow_cm3_s']) for row in sensitivity[edition]['harmonics']}
        saved_flow = np.array([saved[f] for f in lower])
        mean = baseline[edition]['conditions']['predicted_with_predicted_middle']['port_mean_flow_cm3_s']
        # 第1〜22倍音の補正を先に確定し、そのポート係数を上位倍音の比較に渡す。
        low_checks, low = feedback.evaluate_port(
            {**cfg, 'feedback_frequencies_hz': lower}, baseline[edition], layout, recording, added, saved_flow,
            include_measured_coefficients=True)
        high_checks, high_result = upper.evaluate(cfg, layout, recording, lower, high, low, mean)
        checks.update({f'{edition}/lower/{key}': passed for key, passed in low_checks.items()})
        checks.update({f'{edition}/upper/{key}': passed for key, passed in high_checks.items()})
        checks[f'{edition}/lower/measured_source_nose_matches_measured_coefficients'] = abs(
            complex(*low['conditions']['measured_loss_control']['nose_transfer'])
            / complex(*low['conditions'][feedback.MEASURED_COEFFICIENTS]['nose_transfer']) - 1.
        ) < cfg['measured_source_nose_transfer_relative_error_lt']
        checks[f'{edition}/narrow_uses_same_frequency_grid'] = (
            [row['frequency_hz'] for row in narrow[edition]['feedback_frequencies']] == high
            and narrow[edition]['numerical_relative_errors']['predicted_upper_loss_matches_fft'] < tol)
        editions[edition] = {'lower': low, 'upper': high_result, 'wide_nose_change': compare_nose(high_result),
                             'narrow_nose_change': compare_nose(narrow[edition])}
    candidate, upstream = (editions[edition] for edition in ('candidate', 'upstream'))
    for band in ('lower', 'upper'):
        results = (candidate[band], upstream[band])
        flows = [np.array([complex(*value) for row in result['feedback_frequencies']
                           for value in row['port_flow_cm3_s'].values()]) for result in results]
        noses = [np.array([complex(*row['nose_transfer']) for row in result['conditions'].values()]) for result in results]
        checks[f'{band}/both_editions_agree'] = max(inlet.relative_l2(*flows), inlet.relative_l2(*noses)) < cfg['edition_relative_error_lt']
    for hypothesis in (PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS):
        checks[hypothesis] = all(result['upper']['hypotheses'][hypothesis] for result in editions.values())
    return {'checks': checks, 'port_area_cm2': cfg['port_area_cm2'], 'nose_frequency_hz': cfg['frequency_hz'],
            'added_frequencies_hz': high, 'editions': editions}


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

    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        upper, upper.previous, selected_pair, feedback, upper.preceding, upper.preceding.averaged,
        upper.steady, inlet, supra, upper.prior, upper.harmonic, velum, COUPLED, COUPLED.SHARED)),
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
