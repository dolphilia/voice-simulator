"""設計F2を保ち、追加の低域共鳴によるTSPの採択変化を調べる。"""

import argparse
from collections import Counter
from pathlib import Path
import subprocess

import numpy as np
from scipy.optimize import linear_sum_assignment

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case, selection_error
import measure_tsp_f2_harmonic_bandwidth as bandwidth
import measure_tsp_f2_harmonic_spacing as spacing
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-intervening-resonance.json'


def inspect_window(frame, fixed, rate, cfg, f2, tolerance, metadata):
    public = fixed['poles']
    raw = bandwidth.root_poles(fixed['roots'], rate)
    fixed_pair = envelope.select(public, cfg)
    before_filter = [pole for pole in raw if abs(pole[0] - f2) <= tolerance]
    after_filter = [pole for pole in public if abs(pole[0] - f2) <= tolerance]
    first = fixed_pair['f1']
    lower = first[0] + cfg['f2_min_gap_hz'] if first is not None else None
    eligible = [pole for pole in after_filter if lower is not None and lower < pole[0] < cfg['f2_max_frequency_hz']]
    added = metadata['added_pole_hz']
    chosen = fixed_pair['f2']
    added_candidate = min((pole for pole in public if pole != first and added is not None
                           and abs(pole[0] - added) <= tolerance),
                          key=lambda pole: abs(pole[0] - added), default=None)
    if chosen is None:
        association = fixed_pair['reason']
    elif abs(chosen[0] - f2) <= tolerance:
        association = 'model_f2'
    elif added is not None and abs(chosen[0] - added) <= tolerance:
        association = 'added_mode'
    else:
        association = 'other_pole'
    if association == 'model_f2':
        first_difference = None
    elif not before_filter:
        first_difference = 'root_estimation'
    elif not after_filter:
        first_difference = 'public_pole_filter'
    elif first is None:
        first_difference = 'f1_selection'
    elif not eligible:
        first_difference = 'f2_eligibility'
    else:
        first_difference = 'f2_selection'

    def visible(poles):
        return [pole for pole in poles if pole[0] >= cfg['pole_min_frequency_hz']
                and pole[1] <= cfg['pole_max_bandwidth_hz']]

    independent_roots = tsp.independent_roots(frame, rate, metadata['order'], cfg)
    independent = visible(bandwidth.root_poles(zip(independent_roots.real, independent_roots.imag, strict=True), rate))
    observed = {'poles': independent,
                'negative_real_roots': [float(root.real) for root in independent_roots if root.imag == 0 and root.real < 0]}
    _, independent_error, axial = tsp.compare_poles(observed, fixed, cfg)
    real, imaginary = np.asarray(fixed['roots']).T
    distance = abs((real + 1j * imaginary)[:, None] - independent_roots[None, :])
    rows, columns = linear_sum_assignment(distance)
    return {**metadata, 'selection': fixed_pair, 'association': association,
            'f2_lower_hz': lower, 'f2_near_raw_poles': before_filter,
            'f2_near_public_poles': after_filter, 'f2_near_eligible_poles': eligible,
            'added_mode_nearest_public_pole': added_candidate,
            'added_mode_gap_from_selected_f1_hz': added_candidate[0] - first[0] if added_candidate and first else None,
            'first_difference_from_model_f2': first_difference, 'nyquist_axis_matches': axial,
            'errors': {'complex_roots': float(distance[rows, columns].max()),
                       'published_poles_hz': tsp.max_error(visible(raw), public),
                       'independent_poles_hz': independent_error,
                       'independent_selection_hz': selection_error(fixed_pair, envelope.select(independent, cfg))}}


def switches(rows, orders, centers):
    transitions = []
    for order in orders:
        for center in centers:
            previous = None
            for row in rows:
                if row['order'] != order or row['center'] != center:
                    continue
                if row['added_pole_hz'] is not None and row['association'] == 'added_mode' and row['f2_near_eligible_poles']:
                    transitions.append({'order': order, 'center': center,
                                        'first_added_pole_hz': row['added_pole_hz'],
                                        'previous_added_pole_hz': previous['added_pole_hz'],
                                        'previous_association': previous['association'],
                                        'f1_hz': row['selection']['f1'][0], 'f2_hz': row['selection']['f2'][0],
                                        'f2_near_eligible_poles': row['f2_near_eligible_poles']})
                    break
                previous = row
    return transitions


def measure(case, cfg, prior, paths, out, execute):
    spec, settings = case['signal'], case['measurement']
    rate, f0 = spec['sample_rate_hz'], spec['f0_hz']
    period, remainder = divmod(rate, f0)
    centers, orders = settings['centers'], settings['orders']
    if (remainder or rate != cfg['sample_rate_hz'] / cfg['decimation']
            or centers != cfg['reference_centers'] or set(orders) != set(cfg['order'].values())
            or settings['pre_emphasis_coefficient'] != cfg['pre_emphasis']
            or settings['comparison_gap_hz'] != cfg['f2_min_gap_hz']):
        raise ValueError('固定TSPとの標本化、窓、次数、前処理または採択間隔が一致しません')

    base = spec['fixed_poles_hz']
    tolerance = settings['association_tolerance_hz']
    length = round(cfg['frame_seconds'] * rate)
    grid = np.arange(0, rate / 2 + 5, 5)
    pulse = spec['pulse_amplitude']
    excitation = np.zeros(rate * spec['duration_seconds'])
    excitation[::period] = pulse
    frequencies = [None, *spec['added_pole_frequencies_hz']]
    waveforms, designs, frames, metadata = {}, [], [], []
    for frequency in frequencies:
        truth = base if frequency is None else [base[0], [frequency, spec['added_pole_bandwidth_hz']], *base[1:]]
        wave, _, design = known.design_wave(excitation, rate, truth, grid)
        _, harmonics_error = spacing.harmonic_observation(wave, design['sections'], period, pulse, rate, (1500, 2500))
        name = 'baseline' if frequency is None else f'added-{frequency}-hz'
        waveforms[name] = wave
        designs.append({'added_pole_hz': frequency, 'design_poles_hz': truth, 'computed_poles_hz': design['poles_hz'],
                        'sections': design['sections'], 'design_pole_error_hz': design['max_pole_error_hz'],
                        'design_wave_relative_error': design['max_wave_error'] / float(np.max(abs(wave))),
                        'design_response_error_db': design['max_response_error_db'], 'harmonic_error': harmonics_error})
        for order in orders:
            for center in centers:
                start = int(center * len(wave)) - length // 2
                frames.append(wave[start:start + length])
                metadata.append({'added_pole_hz': frequency, 'order': order, 'center': center, 'start_sample': start})
    np.savez_compressed(out / 'waveforms.npz', **waveforms)
    fixed = envelope.fixed_spectra(frames, grid, out, execute, orders=[row['order'] for row in metadata], include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = [inspect_window(frame, sample, rate, cfg, base[1][0], tolerance, row)
            for frame, sample, row in zip(frames, fixed, metadata, strict=True)]

    archived = [(row, probe) for row, probe in zip(prior['windows'], tsp.read(paths['probes']), strict=True)
                if row['bandwidth_hz'] == base[1][1] and row['f0_hz'] == f0]
    base_rows = rows[:len(orders) * len(centers)]
    with np.load(paths['waves'], allow_pickle=False) as waves:
        same_wave = np.array_equal(waves[f'b{base[1][1]}_f0_{f0}_hz'], waveforms['baseline'])
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    checks = {
        'registered_window_count_length_and_finiteness':
            len(rows) == len(frequencies) * len(orders) * len(centers)
            and all(frame.shape == (length,) and np.isfinite(frame).all() for frame in frames),
        'fixed_control_matches_archived_wave_and_upstream': same_wave
        and fixed[:len(base_rows)] == [probe for _, probe in archived]
        and [(row['order'], row['center'], row['selection']) for row in base_rows]
        == [(row['order'], row['center'], row['fixed_selection']) for row, _ in archived],
        'analytic_design_and_periodic_response': all(
            row['design_pole_error_hz'] is not None and row['design_pole_error_hz'] <= settings['design_pole_error_limit_hz']
            and row['design_wave_relative_error'] <= settings['design_wave_relative_error_limit']
            and row['design_response_error_db'] <= settings['design_response_error_limit_db']
            and row['harmonic_error'] <= settings['harmonic_error_limit'] for row in designs),
        'independent_roots_and_selection': all(
            row['errors']['complex_roots'] <= settings['raw_root_distance_limit']
            and all(value is not None and value <= pole_limit for key, value in row['errors'].items()
                    if key != 'complex_roots') for row in rows),
    }
    comparisons = [row for row in rows if row['added_pole_hz'] is not None]
    nominal_gap = cfg['f2_min_gap_hz']
    transitions = switches(rows, orders, centers)
    return {'checks': checks,
            'predictions': {
                'some_windows_switch_to_added_mode_with_f2_still_eligible':
                    any(row['added_pole_hz'] - base[0][0] > nominal_gap and row['association'] == 'added_mode'
                        and row['f2_near_eligible_poles'] for row in comparisons),
                'some_close_modes_do_not_replace_f2':
                    any(row['added_pole_hz'] - base[0][0] <= nominal_gap and row['association'] == 'model_f2'
                        for row in comparisons),
                'model_gap_does_not_predict_every_window':
                    any((row['added_pole_hz'] - base[0][0] > nominal_gap) != (row['association'] == 'added_mode')
                        for row in comparisons),
            },
            'first_switches_with_model_f2_still_eligible': transitions,
            'counts_by_added_pole_hz': {name: dict(Counter(row['association'] for row in rows if row['added_pole_hz'] == f))
                                       for f, name in zip(frequencies, waveforms, strict=True)},
            'designs': designs, 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference, upstream = (tsp.open_run(case[name], revision) for name in ('harmonic_reference', 'tsp_reference'))
    config, config_path = saved_case(upstream, tsp.CASE)
    paths = {'waves': tsp.verified_path(reference, 'artifacts/waveforms.npz'),
             'probes': tsp.verified_path(reference, 'artifacts/upstream-envelopes.json'),
             'summary': tsp.verified_path(reference, 'summary.json')}
    modules = (bandwidth, envelope, known, spacing, tsp)
    inputs = [CASE, Path(__file__).resolve(), config_path, *paths.values(), envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (reference, upstream)),
              *(Path(module.__file__) for module in modules),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_f2_bandwidth_held_out', 'measure_tsp_f2_annotation',
                   'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, config['measurement'], tsp.read(paths['summary']), paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
