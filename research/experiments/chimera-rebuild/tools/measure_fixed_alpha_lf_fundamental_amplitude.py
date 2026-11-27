"""固定LFに加える基本波の振幅を変え、口端の奇成分と偶成分を測る。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_fixed_alpha_lf_fundamental as fundamental
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-lf-fundamental-amplitude.json'
PERIODIC = fundamental.periodic
MEAN = fundamental.MEAN
READ = fundamental.READ
PAIR = fundamental.PAIR
BASE, MATCHED = fundamental.JOBS[1:]
JOBS = {0: BASE, 1: MATCHED, -1: 'lf-negative-full', 0.5: 'lf-positive-half', -0.5: 'lf-negative-half'}
EVIDENCE = ('replay-traces.npz', 'capture.json', *(f'{name}.json' for name in JOBS.values()))
OUTPUTS = ('flow_lips', 'flow_walls', 'radiation_derivative')


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('基本波変更の保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    definition = run / header['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('基本波変更の保存ケースのハッシュが一致しません')
    saved = fundamental.archive_inputs(READ(definition))
    sources = ('large-case.json', 'upstream-geometry.csv', *MEAN.impulse.harmonic.NETWORK_FILES)
    return {**{name: saved[name] for name in sources},
            'fundamental-manifest.json': manifest, 'fundamental-case.json': definition,
            **{name: verified_path(record, f'artifacts/{name}')
               for name in ('replay-traces.npz', 'capture.json', f'{BASE}.json', f'{MATCHED}.json')}}


def drive_cases(study, archive):
    original, matched = (READ(archive[f'{job}.json']) for job in (BASE, MATCHED))
    base = fundamental.flow_series(original)
    step = fundamental.flow_series(matched) - base
    cases = {BASE: original, MATCHED: matched}
    for scale, job in JOBS.items():
        if job in cases:
            continue
        wave = base + scale * step
        cases[job] = {**original, 'id': f'{study["id"]}-{job}', 'hypothesis': study['hypothesis'],
                      'fixed_airway_periodic_flow': {**original['fixed_airway_periodic_flow'],
                                                     'flow_cm3_s': [repr(float(x)) for x in wave]}}
    return cases


def parity(values, amplitude):
    positive = values[amplitude] - values[0]
    negative = values[-amplitude] - values[0]
    return (positive - negative) / 2, (positive + negative) / 2


def output_analysis(cfg, traces, projection, bins):
    count = projection.shape[1]
    last = {scale: data[-count:] for scale, data in traces.items()}
    prior = {scale: data[:count] for scale, data in traces.items()}
    coefficients = {scale: np.fft.rfft(data, axis=0)[bins] / count for scale, data in last.items()}
    direct = {scale: tuple(projection @ term / count for term in parity(last, scale)) for scale in (1, 0.5)}
    agreement, convergence = {}, {}
    for scale, (odd, even) in direct.items():
        with_fft = parity(coefficients, scale)
        penultimate = tuple(projection @ term / count for term in parity(prior, scale))
        agreement[scale] = max(float((abs(a - b) / abs(odd)).max()) for a, b in zip((odd, even), with_fft, strict=True))
        convergence[scale] = max(float((abs(a - b) / abs(odd)).max()) for a, b in zip((odd, even), penultimate, strict=True))
    odd, even = direct[1]
    half_odd, half_even = direct[0.5]
    odd_scaling = abs(2 * half_odd - odd) / abs(odd)
    even_scaling = abs(4 * half_even - even) / abs(even)
    rows = {}
    for col, name in enumerate(OUTPUTS):
        items = []
        for i, frequency in enumerate(cfg['frequencies_hz']):
            index = (i, col)
            base = coefficients[0][index]
            interpolation = {}
            for scale in (-0.5, 0.5):
                observed = coefficients[scale][index] - base
                prediction = scale * odd[index] + scale**2 * even[index]
                interpolation[str(scale)] = {'observed': PAIR(observed), 'predicted': PAIR(prediction),
                                             'relative_error': float(abs(observed - prediction) / abs(observed))}
            items.append({
                'frequency_hz': frequency,
                'baseline_coefficient': PAIR(base),
                'odd_full': PAIR(odd[index]), 'even_full': PAIR(even[index]),
                'odd_half': PAIR(half_odd[index]), 'even_half': PAIR(half_even[index]),
                'even_over_odd_full': float(abs(even[index]) / abs(odd[index])),
                'even_over_odd_half': float(abs(half_even[index]) / abs(half_odd[index])),
                'half_over_full_odd_magnitude': float(abs(half_odd[index]) / abs(odd[index])),
                'half_over_full_even_magnitude': float(abs(half_even[index]) / abs(even[index])),
                'odd_scaling_complex_error': float(odd_scaling[index]),
                'even_scaling_complex_error': float(even_scaling[index]),
                'half_amplitude_quadratic_prediction': interpolation,
            })
        rows[name] = items
    return rows, max(agreement.values()), max(convergence.values())


def analyze(study, archive, out):
    cfg = study['measurement']
    previous_cfg = READ(archive['fundamental-case.json'])['measurement']
    common = ('internal_rate_hz', 'f0_hz', 'frequencies_hz', 'steady_window_samples', 'cycles_per_block',
              'steady_flow_cm3_s', 'warmup_samples', 'periodic_blocks', 'after_onset_samples_to_keep')
    cases = {job: READ(out / f'{job}.json') for job in JOBS.values()}
    waves = {scale: fundamental.flow_series(cases[job]) for scale, job in JOBS.items()}
    count = len(waves[0])
    rate = cfg['internal_rate_hz']
    frequencies = np.array(cfg['frequencies_hz'])
    bins = frequencies * count // rate
    projection = np.exp(-2j * np.pi * np.outer(bins, np.arange(count)) / count)
    source = {scale: np.fft.rfft(wave) / count for scale, wave in waves.items()}
    f0 = cfg['cycles_per_block']
    step = source[1][f0] - source[0][f0]
    spectral_errors = {}
    for scale, coefficient in source.items():
        expected = source[0].copy()
        expected[f0] += scale * step
        spectral_errors[scale] = fundamental.peak_relative(coefficient, expected)
    meta = READ(out / 'capture.json')
    previous_meta = READ(archive['capture.json'])
    _, compliance, hops = PERIODIC.linear_prediction(study, archive)
    checks = {
        'registered_waveforms_and_clock': (
            cases == drive_cases(study, archive) and cfg['amplitude_scales'] == sorted(JOBS)
            and all(cfg[key] == previous_cfg[key] for key in common)
            and count == cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
            and all(wave.shape == (count,) and np.isfinite(wave).all() for wave in waves.values())
            and bins[0] == f0 and np.array_equal(bins * rate, frequencies * count)),
        'scaled_source_fundamental_and_other_bins': (
            max(spectral_errors.values()) < cfg['input_spectral_identity_relative_error_lt']),
    }
    end = cfg['warmup_samples'] + count * cfg['periodic_blocks']
    for job, case in cases.items():
        checks[f'{job}/matches_upstream_full_series_and_pinned_pose'] = (
            meta[job]['samples'] == end == case['fixed_airway']['sample_count']
            and meta[job]['first_sample_over_tolerance'] is None
            and case['body'] == cases[BASE]['body'] and case['posture'] == cases[BASE]['posture']
            and case['fixed_airway'] == cases[BASE]['fixed_airway']
            and case['fixed_airway_periodic_flow']['start_sample'] == cfg['warmup_samples'])
    output_columns = [PERIODIC.FIELDS.index(name) for name in OUTPUTS]
    results = {}
    with (
        np.load(out / 'replay-traces.npz', allow_pickle=False) as current,
        np.load(archive['replay-traces.npz'], allow_pickle=False) as previous,
    ):
        for edition in PERIODIC.EDITIONS:
            prefix = f'{edition}/'
            checks[prefix + 'reference_series_and_prefixes_match_archive'] = (
                all(np.array_equal(current[f'{job}_{edition}{suffix}'].view(np.uint64),
                                   previous[f'{job}_{edition}{suffix}'].view(np.uint64))
                    for job in (BASE, MATCHED) for suffix in ('', '_start'))
                and all(meta[job] == previous_meta[job] for job in (BASE, MATCHED))
                and len({meta[job]['prefix_sha256'][edition] for job in JOBS.values()}) == 1)
            traces = {scale: current[f'{job}_{edition}'][:, output_columns] for scale, job in JOBS.items()}
            probes = {scale: current[f'{job}_{edition}_start'] for scale, job in JOBS.items()}
            checks[prefix + 'finite_registered_windows'] = (
                all(data.shape == (2 * count, len(OUTPUTS)) and np.isfinite(data).all() for data in traces.values())
                and all(data.shape == (cfg['after_onset_samples_to_keep'], len(PERIODIC.FIELDS))
                        and np.isfinite(data).all() for data in probes.values()))
            checks[prefix + 'late_output_blocks_converge'] = all(
                fundamental.peak_relative(data[:count, col], data[count:, col]) < cfg['late_block_peak_relative_error_lt']
                for data in traces.values() for col in range(len(OUTPUTS)))
            first = {}
            for scale, probe in probes.items():
                if scale == 0:
                    continue
                difference = probe - probes[0]
                expected = (waves[scale][0] - waves[0][0]) / (compliance * rate)
                pressure = difference[0, fundamental.INLET]
                lip_changes = np.flatnonzero(difference[:, fundamental.LIP])
                error = float(abs(pressure / expected - 1))
                arrival = int(lip_changes[0]) if lip_changes.size else None
                checks[f'{prefix}scale_{scale}/first_inlet_pressure_and_lip_arrival'] = (
                    error < cfg['first_inlet_pressure_relative_error_lt'] and arrival == hops)
                first[str(scale)] = {'pressure_change_dyn_cm2': float(pressure), 'expected_dyn_cm2': float(expected),
                                     'relative_pressure_error': error, 'lip_arrival_offset': arrival}
            outputs, dft_error, convergence = output_analysis(cfg, traces, projection, bins)
            checks[prefix + 'components_match_independent_fft'] = dft_error < cfg['component_dft_relative_error_lt']
            checks[prefix + 'late_components_stable_relative_to_odd'] = convergence < cfg['late_component_error_relative_to_odd_lt']
            hypotheses = {}
            for row in outputs['flow_lips'][1:]:
                hypotheses[str(row['frequency_hz'])] = {
                    'odd_dominates': row['even_over_odd_full'] < cfg['hypothesis_even_over_odd_lt'],
                    'odd_scales_linearly': row['odd_scaling_complex_error'] < cfg['hypothesis_odd_scaling_complex_error_lt'],
                    'even_scales_quadratically': row['even_scaling_complex_error'] < cfg['hypothesis_even_scaling_complex_error_lt'],
                }
            results[edition] = {'outputs': outputs, 'first_changes': first, 'component_dft_relative_error': dft_error,
                                'component_convergence_relative_to_odd': convergence, 'hypotheses': hypotheses}
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'conditions': results,
            'source_coefficient_change_at_f0': PAIR(step),
            'input_spectral_relative_errors': {str(scale): error for scale, error in spectral_errors.items()},
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
        PERIODIC.capture_cases(study, archive, out, execute, drive_cases(study, archive).items())
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *MEAN.shared.candidate_sources(), MEAN.sagittal.PROBE,
              *(Path(module.__file__) for module in (
                  fundamental, PERIODIC, MEAN, MEAN.impulse, MEAN.fixed, MEAN.sagittal, MEAN.shared)),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/voice/human_voice.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                          input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
