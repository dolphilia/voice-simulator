"""固定LFの声門流量の基本波を合わせ、口端と放射の変化を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_periodic_flow as periodic
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-lf-fundamental.json'
READ = periodic.READ
JOBS = ('coupled-periodic', 'lf-periodic', 'lf-matched-fundamental')
EVIDENCE = ('replay-traces.npz', 'capture.json', *(f'{job}.json' for job in JOBS))
FIELDS = periodic.FIELDS
MEAN = periodic.mean
PAIR = MEAN.impulse.harmonic.pair
LIP = FIELDS.index('flow_lips')
INLET = FIELDS.index('pressure_pharynx_entry')
RADIATION = FIELDS.index('radiation_derivative')
OUTFLOWS = [FIELDS.index(field) for field in ('flow_lips', 'flow_nose', 'flow_walls')]


def archive_inputs(study):
    archive = {}
    for name, spec in study['references'].items():
        run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        manifest = run / 'manifest.json'
        if header['status'] != spec['status'] or sha256(manifest) != spec['sha256']:
            raise ValueError(f'保存実行の判定またはハッシュが一致しません ({run.name})')
        archive[f'{name}-manifest.json'] = manifest
        archive[f'{name}-summary.json'] = verified_path(record, 'summary.json')
        if name != 'periodic':
            continue
        row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
        definition = run / header['source_snapshot'] / row['path']
        if sha256(definition) != row['sha256']:
            raise ValueError('周期入力の保存ケースのハッシュが一致しません')
        prior = periodic.archive_inputs(READ(definition))
        archive['periodic-case.json'] = definition
        for path in ('large-case.json', 'upstream-geometry.csv', *MEAN.impulse.harmonic.NETWORK_FILES):
            archive[path] = prior[path]
        for path in ('replay-traces.npz', 'capture.json', *(f'{job}.json' for job in JOBS[:2])):
            archive[path] = verified_path(record, f'artifacts/{path}')
    return archive


def flow_series(case):
    return np.array([float(x) for x in case['fixed_airway_periodic_flow']['flow_cm3_s']])


def drive_cases(study, archive):
    cases = {job: READ(archive[f'{job}.json']) for job in JOBS[:2]}
    normal, lf = (flow_series(cases[job]) for job in JOBS[:2])
    cfg = study['measurement']
    angle = 2j * np.pi * cfg['cycles_per_block'] * np.arange(len(lf)) / len(lf)
    coefficient = np.exp(-angle) @ (normal - lf) / len(lf)
    wave = lf + 2 * (coefficient * np.exp(angle)).real
    reference = cases['lf-periodic']
    cases[JOBS[-1]] = {**reference, 'id': study['id'], 'hypothesis': study['hypothesis'],
                      'fixed_airway_periodic_flow': {**reference['fixed_airway_periodic_flow'],
                                                     'flow_cm3_s': [repr(float(x)) for x in wave]}}
    return cases


def peak_relative(observed, expected):
    return float(abs(observed - expected).max() / max(float(abs(expected).max()), np.finfo(float).tiny))


def output_measurements(cfg, traces, probes, wave, bins, model, compliance, hops):
    rate = cfg['internal_rate_hz']
    block = len(wave[JOBS[0]])
    latest = {job: data[-block:] for job, data in traces.items()}
    measured = {job: values[:, [LIP, RADIATION]] for job, values in latest.items()}
    spectrum = {job: np.fft.rfft(values, axis=0) / block for job, values in measured.items()}
    angle = np.exp(-2j * np.pi * np.outer(bins, np.arange(block)) / block)
    fft_error = max(peak_relative((angle @ values / block)[:, col], spectrum[job][bins, col])
                    for job, values in measured.items() for col in range(values.shape[1]))
    weights = np.full(block // 2 + 1, 2.)
    weights[0] = 0
    if block % 2 == 0:
        weights[-1] = 1
    power = {job: weights[:, None] * abs(values)**2 for job, values in spectrum.items()}
    time_power = {job: values.var(axis=0) for job, values in measured.items()}
    parseval_error = max(float(abs(power[job].sum(axis=0) / values - 1).max()) for job, values in time_power.items())
    rms = {job: np.sqrt(values) for job, values in time_power.items()}
    normal, lf, hybrid = JOBS
    f0 = bins[0]
    output_replacement = np.sqrt(time_power[lf][0] - power[lf][f0, 0] + power[normal][f0, 0])
    source_fft = {job: np.fft.rfft(values) / block for job, values in wave.items()}
    predicted = model[0, MEAN.RESPONSE_FIELDS.index('flow_lips')] * (source_fft[hybrid][f0] - source_fft[lf][f0])
    measured_delta = spectrum[hybrid][f0, 0] - spectrum[lf][f0, 0]
    delta_power = power[hybrid][:, 0] - power[lf][:, 0]
    previous = np.diff(traces[hybrid][:, OUTFLOWS].sum(axis=1)) * rate
    rise = probes[hybrid] - probes[lf]
    expected_pressure = (wave[hybrid][0] - wave[lf][0]) / (compliance * rate)
    first_pressure = peak_relative(np.array([rise[0, INLET]]), np.array([expected_pressure]))
    first_samples = {
        field: periodic.first_difference(probes[hybrid][:, col], probes[lf][:, col],
                                         cfg['first_difference_peak_relative_threshold'])['first_sample']
        for col, field in enumerate(FIELDS)}
    harmonic_rows = [{
        'frequency_hz': frequency,
        'source_coefficient_cm3_s': {job: PAIR(values[bin_index]) for job, values in source_fft.items()},
        'lip_coefficient_cm3_s': {job: PAIR(values[bin_index, 0]) for job, values in spectrum.items()},
        'radiation_coefficient_cm3_s2': {job: PAIR(values[bin_index, 1]) for job, values in spectrum.items()},
        'lip_change_relative_to_lf': float(abs(spectrum[hybrid][bin_index, 0] / spectrum[lf][bin_index, 0] - 1)),
    } for frequency, bin_index in zip(cfg['frequencies_hz'], bins, strict=True)]
    report = {
        'lip_ac_rms_cm3_s': {job: float(value[0]) for job, value in rms.items()},
        'radiation_ac_rms_cm3_s2': {job: float(value[1]) for job, value in rms.items()},
        'relative_lip_reduction': float(1 - rms[hybrid][0] / rms[normal][0]),
        'relative_lip_reduction_unmodified_lf': float(1 - rms[lf][0] / rms[normal][0]),
        'relative_lip_reduction_if_replaced_in_output': float(1 - output_replacement / rms[normal][0]),
        'lip_power_change_cm6_s2': {'fundamental': float(delta_power[f0]),
                                   'other_bins': float(delta_power.sum() - delta_power[f0])},
        'measured_fundamental_change': PAIR(measured_delta),
        'linear_fundamental_change': PAIR(predicted),
        'relative_complex_error_of_linear_change': float(abs(measured_delta - predicted) / abs(measured_delta)),
        'first_inlet_pressure_change_dyn_cm2': float(rise[0, INLET]),
        'predicted_first_inlet_pressure_change_dyn_cm2': float(expected_pressure),
        'first_changed_offsets': first_samples,
        'frequencies': harmonic_rows,
    }
    tolerance = cfg['spectral_identity_peak_relative_error_lt']
    checks = {
        'rms_parseval': parseval_error < tolerance,
        'direct_dft_matches_fft': fft_error < tolerance,
        'radiation_from_discrete_difference': peak_relative(previous[-block:], traces[hybrid][-block:, RADIATION]) < tolerance,
        'same_prefix_physics_and_causal_arrival': (
            first_pressure < cfg['first_inlet_pressure_relative_error_lt']
            and not np.any(rise[:hops, LIP]) and np.any(rise[hops:, LIP])),
        'last_two_blocks_converge': all(
            peak_relative(data[:block, col], data[block:, col]) < cfg['late_block_peak_relative_error_lt']
            for data in traces.values() for col in (LIP, RADIATION)),
    }
    report['hypotheses'] = {
        'lip_reduction_reaches_five_percent': report['relative_lip_reduction'] >= cfg['hypothesis_lip_rms_reduction_ge'],
        'lip_reduction_close_to_output_replacement': abs(
            report['relative_lip_reduction'] - report['relative_lip_reduction_if_replaced_in_output'])
        < cfg['hypothesis_rms_gap_to_output_replacement_lt'],
        'lip_overtones_change_with_fundamental_only_input': any(
            row['lip_change_relative_to_lf'] > cfg['hypothesis_nonfundamental_relative_change_gt'] for row in harmonic_rows[1:]),
    }
    return checks, report


def analyze(study, archive, out):
    cfg = study['measurement']
    prior_cfg = READ(archive['periodic-case.json'])['measurement']
    common = ('internal_rate_hz', 'f0_hz', 'steady_window_samples', 'cycles_per_block', 'steady_flow_cm3_s',
              'warmup_samples', 'periodic_blocks', 'after_onset_samples_to_keep')
    cases = {job: READ(out / f'{job}.json') for job in JOBS}
    wave = {job: flow_series(case) for job, case in cases.items()}
    normal, lf, hybrid = JOBS
    block = cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
    bins = np.array(cfg['frequencies_hz']) * block // cfg['internal_rate_hz']
    spectra = {job: np.fft.rfft(values) / block for job, values in wave.items()}
    expected = spectra[lf].copy()
    expected[bins[0]] = spectra[normal][bins[0]]
    meta = READ(out / 'capture.json')
    prior_meta = READ(archive['capture.json'])
    old = READ(archive['legacy-summary.json'])
    voiced = READ(archive['voiced-summary.json'])
    checks = {
        'same_registered_rate_posture_and_clock': all(cfg[key] == prior_cfg[key] for key in common)
            and cases == drive_cases(study, archive)
            and bins[0] == cfg['cycles_per_block']
            and np.array_equal(bins * cfg['internal_rate_hz'], np.array(cfg['frequencies_hz']) * block)
            and all(case['fixed_airway']['sample_rate_hz'] == cfg['internal_rate_hz']
                    and case['fixed_airway']['sample_count'] == cfg['warmup_samples'] + block * cfg['periodic_blocks']
                    and case['fixed_airway']['steady_flow_cm3_s'] == cfg['steady_flow_cm3_s']
                    and case['fixed_airway_periodic_flow']['start_sample'] == cfg['warmup_samples']
                    for case in cases.values()),
        'input_only_fundamental_coefficient_changes': all(v.shape == (block,) and np.isfinite(v).all() for v in wave.values())
            and peak_relative(spectra[hybrid], expected) < cfg['spectral_identity_peak_relative_error_lt'],
        'original_failed_level_decision_preserved': (
            old['checks']['lf_acoustic_level_difference'] is False and voiced['legacy_decision'] is False),
    }
    for job in JOBS:
        checks[f'{job}/matches_upstream_full_series'] = (
            meta[job]['first_sample_over_tolerance'] is None
            and meta[job]['samples'] == cases[job]['fixed_airway']['sample_count'])
    model, compliance, hops = periodic.linear_prediction(study, archive)
    results = {}
    with (
        np.load(out / 'replay-traces.npz', allow_pickle=False) as current,
        np.load(archive['replay-traces.npz'], allow_pickle=False) as previous,
    ):
        for edition in periodic.EDITIONS:
            checks[f'{edition}/baseline_replays_match_archive'] = (
                all(np.array_equal(current[f'{job}_{edition}{suffix}'].view(np.uint64),
                                   previous[f'{job}_{edition}{suffix}'].view(np.uint64))
                    for job in JOBS[:2] for suffix in ('', '_start'))
                and all(meta[job] == prior_meta[job] for job in JOBS[:2]))
            checks[f'{edition}/same_state_before_drive'] = (
                len({meta[job]['prefix_sha256'][edition] for job in JOBS}) == 1)
            traces = {job: current[f'{job}_{edition}'] for job in JOBS}
            probes = {job: current[f'{job}_{edition}_start'] for job in JOBS}
            checks[f'{edition}/finite_registered_windows'] = (
                all(x.shape == (2 * block, len(FIELDS)) and np.isfinite(x).all() for x in traces.values())
                and all(x.shape == (cfg['after_onset_samples_to_keep'], len(FIELDS)) and np.isfinite(x).all()
                        for x in probes.values()))
            decision, results[edition] = output_measurements(cfg, traces, probes, wave, bins, model, compliance, hops)
            checks.update({f'{edition}/{name}': ok for name, ok in decision.items()})
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': results,
            'input_peak_relative_spectral_error': peak_relative(spectra[hybrid], expected),
            'legacy_original_lip_rms_relative_change': old['lf_minus_coupled_relative_ac_rms']['lip_flow_cm3_s'],
            'original_output_only_relative_change': voiced['lip_fundamental_replaced_relative_rms'],
            'all_trace_comparisons': meta}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        periodic.capture_cases(study, archive, out, execute, drive_cases(study, archive).items())
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(), MEAN.sagittal.PROBE,
              *(Path(module.__file__) for module in (periodic, MEAN, MEAN.impulse, MEAN.fixed, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
