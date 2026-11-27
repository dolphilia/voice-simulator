"""固定 /i/ の音響ポートだけを狭め、同じ2倍音の予測補正を検証する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_vowel_i_velum_port_selected_pair_feedback as selected_pair
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-narrow-port-feedback.json'
READ, COUPLED = selected_pair.READ, selected_pair.COUPLED
feedback, supra, inlet, velum = selected_pair.feedback, selected_pair.supra, selected_pair.inlet, selected_pair.velum
prior, harmonic = feedback.prior, feedback.harmonic
NETWORK_FILES = harmonic.harmonic.NETWORK_FILES
CAPTURE_FILES = ('natural-case.json', 'natural-network.csv', 'upper.f64', 'upper-network.f64')
EVIDENCE = (*prior.EVIDENCE, 'linear-case.json', 'linear-inspect.json',
            *(f'linear-upstream/{name}' for name in NETWORK_FILES))
MEAN_HYPOTHESIS = 'narrowing_increases_port_impedance_and_reduces_mean_flow'
PORT_HYPOTHESIS = feedback.PORT_HYPOTHESIS
RECOVERY_HYPOTHESIS = selected_pair.RECOVERY_HYPOTHESIS


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(
        {'run': spec['run'], 'case': 'fixed-vowel-i-velum-port-selected-pair-feedback', 'sha256': spec['manifest_sha256']},
        case['upstream_revision'])
    return {**selected_pair.archive_inputs(READ(definition)), 'selected-pair-feedback-manifest.json': manifest,
            'selected-pair-feedback-case.json': definition,
            'selected-pair-feedback-summary.json': COUPLED.verified_path(record, 'summary.json')}


def narrow_input(cfg, archive):
    base = READ(archive['natural-case.json'])
    probe = base['fixed_voice_probe']
    if (base['voice']['pressure_cm_h2o'] != cfg['pressure_cm_h2o']
            or probe['velum_area_override_cm2'] != cfg['reference_port_area_cm2']):
        raise ValueError('基準の肺圧または開口面積が事前登録値と一致しません')
    return {**base, 'fixed_voice_probe': {**probe, 'velum_area_override_cm2': cfg['port_area_cm2']}}


def linear_case(cfg, natural):
    return {**natural, 'transfer': {'start_hz': min(cfg['feedback_frequencies_hz']),
                                   'end_hz': max(cfg['feedback_frequencies_hz']), 'points': 2},
            'measurement': {**natural['measurement'], 'peak_search_min_hz': min(cfg['feedback_frequencies_hz'])}}


def capture(case, archive, out, execute):
    cfg = case['measurement']
    natural = narrow_input(cfg, archive)
    prior.capture_voice_network(case, natural, out, execute)
    path = out / 'linear-case.json'
    prior.harmonic.port.write_case(path, linear_case(cfg, natural))
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--', 'inspect', str(path)],
            stdout=out / 'linear-inspect.json')
    upper = out / 'linear-upstream'
    upper.mkdir()
    binary = COUPLED.SHARED.build_upstream_probe(harmonic.vowel.PROBE, upper, execute,
                                                extra_libraries=('serde_json',), cargo_args=('--offline',))
    execute([str(binary), '--case', str(path), str(upper)], cwd=UPSTREAM)


def compare_geometry(cfg, old_layout, layout, old, current):
    _, _, before_nodes, before_edges, before_source = old
    tracks, _, nodes, edges, source = current
    port, old_k = prior.tangent.port_parameters(old_layout)
    _, new_k = prior.tangent.port_parameters(layout)
    if list(port) != cfg['port_nodes']:
        raise ValueError('ポートの節点が事前登録値と一致しません')
    edge, = np.flatnonzero((edges[:, :2] == port).all(axis=1))
    unchanged = np.arange(len(edges)) != edge
    ratio = edges[edge, 4] / before_edges[edge, 4]
    expected_ratio = (cfg['reference_port_area_cm2'] / cfg['port_area_cm2'])**1.5
    area_trace = tracks[velum.PORT[0]][1:]
    mean_flow = float(tracks[velum.PORT[1]][1:].mean())
    old_mean = float(old[0][velum.PORT[1]][1:].mean())
    checks = {
        'only_port_linear_elements_change': (
            source == before_source and np.array_equal(nodes, before_nodes)
            and np.array_equal(edges[:, :3], before_edges[:, :3])
            and np.array_equal(edges[unchanged], before_edges[unchanged])),
        'observed_port_area_matches_input': bool(
            np.max(abs(area_trace / cfg['port_area_cm2'] - 1.)) < cfg['numerical_identity_relative_error_lt']),
        'resistance_ratio_matches_area_power_law': bool(
            abs(ratio / expected_ratio - 1.) < cfg['numerical_identity_relative_error_lt']),
    }
    return checks, {
        'port_inertance_ratio': float(edges[edge, 3] / before_edges[edge, 3]),
        'port_resistance_ratio': float(ratio),
        'port_kinetic_coefficient_ratios': [new / old for old, new in zip(old_k, new_k)],
        'mean_port_flow_cm3_s': {'reference': old_mean, 'narrow': mean_flow},
        'mean_flow_reduction_fraction': 1. - mean_flow / old_mean,
    }


def compare_recordings(cfg, out, natural, layout, recordings):
    candidate, upstream = (recordings[key] for key in ('candidate', 'upstream'))
    _, candidate_state, candidate_nodes, candidate_branches, candidate_source = candidate
    _, upstream_state, upstream_nodes, upstream_branches, upstream_source = upstream
    order = prior.upstream_branch_order(candidate_branches, upstream_branches)
    count = layout['node_count']
    aligned = np.column_stack((upstream_state[:, :count], upstream_state[:, count + order]))
    state_error = harmonic.max_row_relative(candidate_state.T, aligned.T)
    rate = natural['voice']['output_sample_rate_hz']
    frames = natural['fixed_airway']['sample_count'] * rate // cfg['internal_rate_hz']
    native_pcm = COUPLED.read_pcm(out / 'natural.wav', frames, rate)
    upper_pcm = np.fromfile(out / 'upper.f32', dtype='<f4')
    if upper_pcm.shape != (frames,) or not np.isfinite(upper_pcm).all():
        raise ValueError('固定上流PCMの標本数または有限性が条件に一致しません')
    pcm_error = float(np.max(abs(native_pcm.astype(float) - upper_pcm)) / np.max(abs(upper_pcm)))
    tolerance = cfg['edition_relative_error_lt']
    return {
        'independently_extracted_linear_models_match': (
            candidate_source == upstream_source
            and np.array_equal(candidate_branches[:, :3], upstream_branches[order, :3])
            and inlet.relative_l2(candidate_branches[:, 3:], upstream_branches[order, 3:]) < tolerance
            and inlet.relative_l2(candidate_nodes, upstream_nodes) < tolerance),
        'network_trace_aligns_between_editions': state_error < tolerance,
        'pcm_matches_fixed_upstream': pcm_error < cfg['upstream_pcm_peak_relative_error_lt'],
    }, {'network_peak_relative_error': state_error, 'pcm_peak_relative_error': pcm_error}


def evaluate_feedback(cfg, before, layout, recording, added):
    checks, detail = feedback.evaluate_port(cfg, None, layout, recording, added, None, include_measured_coefficients=True)
    conditions = detail['conditions']
    baseline_error = conditions['tangent']['nose_relative_error']
    target_error = conditions[feedback.MEASURED_COEFFICIENTS]['nose_relative_error']
    ideal_improvement = 1. - target_error / baseline_error
    recovery = detail['nose_error_reduction_fraction'] / ideal_improvement if ideal_improvement > 0. else None
    exact = complex(*conditions[feedback.MEASURED_COEFFICIENTS]['nose_transfer'])
    measured_source = complex(*conditions['measured_loss_control']['nose_transfer'])
    control_error = float(abs((measured_source - exact) / exact))
    checks['measured_source_matches_measured_coefficients_control'] = (
        control_error < cfg['measured_source_nose_transfer_relative_error_lt'])
    detail.update({
        'reference_aperture_nose_error_reduction_fraction': before['nose_error_reduction_fraction'],
        'measured_coefficients_nose_error_reduction_fraction': ideal_improvement,
        'fraction_of_measured_coefficients_improvement_recovered': recovery,
        'measured_source_control_nose_transfer_relative_error': control_error,
        'hypotheses': {
            PORT_HYPOTHESIS: detail['port_error_reduction_fraction'] >= cfg['minimum_port_error_reduction_fraction'],
            RECOVERY_HYPOTHESIS: recovery is not None and recovery >= cfg['minimum_recovered_nose_improvement_fraction'],
        },
    })
    return checks, detail


def analyze(case, archive, out):
    cfg = case['measurement']
    reference = READ(archive['selected-pair-feedback-case.json'])['measurement']
    frozen = ('internal_rate_hz', 'frequency_hz', 'fundamental_hz', 'steady_window_internal_samples', 'frequencies_hz',
              'added_harmonics', 'feedback_frequencies_hz', 'port_nodes', 'supraglottal_branch_count')
    if (any(cfg[key] != reference[key] for key in frozen)
            or cfg['reference_port_area_cm2'] != reference['port_area_cm2']
            or cfg['pressure_cm_h2o'] != reference['pressure_cm_h2o']['reference']):
        raise ValueError('固定する比較条件が保存済みの実行と一致しません')
    previous = READ(archive['selected-pair-feedback-summary.json'])['pressures']['reference']
    old_layout, old = supra.recorded_editions(case, archive)
    captured = {**archive, **{name: out / name for name in CAPTURE_FILES},
                'archive-linear-inspect.json': out / 'linear-inspect.json',
                **{f'archive-{name}': out / 'linear-upstream' / name for name in NETWORK_FILES}}
    layout, recordings = supra.recorded_editions(case, captured)
    expected = narrow_input(cfg, archive)
    natural = READ(out / 'natural-case.json')
    inspect = READ(out / 'natural-inspect.json')
    checks, capture_summary = compare_recordings(cfg, out, natural, layout, recordings)
    checks['only_audio_port_area_changes_in_input_and_geometry'] = (
        natural == expected and READ(out / 'linear-case.json') == linear_case(cfg, expected)
        and inspect['case'] == natural and inspect['fixed_airway'] == layout
        and layout == {**old_layout, 'velum_port_cm2': cfg['port_area_cm2']}
        and inspect['coordinates'] == READ(archive['natural-inspect.json'])['coordinates']
        and READ(out / 'upper-columns.json') == list(velum.FIELDS))
    added = [cfg['fundamental_hz'] * j for j in cfg['added_harmonics']]
    editions = {}
    for edition, recording in recordings.items():
        geometry_checks, geometry = compare_geometry(cfg, old_layout, layout, old[edition], recording)
        feedback_checks, detail = evaluate_feedback(cfg, previous[edition], layout, recording, added)
        checks.update({f'{edition}/{key}': value for key, value in {**geometry_checks, **feedback_checks}.items()})
        detail['hypotheses'][MEAN_HYPOTHESIS] = (
            min(geometry['port_inertance_ratio'], geometry['port_resistance_ratio'],
                *geometry['port_kinetic_coefficient_ratios']) > 1. and geometry['mean_flow_reduction_fraction'] > 0.)
        editions[edition] = {**detail, 'opening_change': geometry}
    for hypothesis in (MEAN_HYPOTHESIS, PORT_HYPOTHESIS, RECOVERY_HYPOTHESIS):
        checks[hypothesis] = all(result['hypotheses'][hypothesis] for result in editions.values())
    candidate, upstream = (editions[edition] for edition in ('candidate', 'upstream'))
    transfer = [np.array([complex(*row['nose_transfer']) for row in result['conditions'].values()])
                for result in (candidate, upstream)]
    checks['feedback_agrees_between_editions'] = (
        inlet.relative_l2(*transfer) < cfg['edition_relative_error_lt'] and candidate['hypotheses'] == upstream['hypotheses'])
    return {'checks': checks, 'pressure_cm_h2o': cfg['pressure_cm_h2o'], 'port_area_cm2': cfg['port_area_cm2'],
            'feedback_frequencies_hz': cfg['feedback_frequencies_hz'], 'capture': capture_summary, 'editions': editions}


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
        capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *(Path(module.__file__) for module in (
        selected_pair, feedback, feedback.middle, feedback.middle.bandwidth.preceding, feedback.middle.bandwidth.preceding.averaged,
        feedback.steady, inlet, supra, prior, harmonic, harmonic.harmonic, harmonic.vowel, velum, COUPLED, COUPLED.SHARED)),
        *COUPLED.SHARED.candidate_sources(), velum.UPPER, harmonic.vowel.PROBE,
        *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
          'crates/chimera/src/airway/frequency.rs', 'crates/chimera/tests/airway_adversarial.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
