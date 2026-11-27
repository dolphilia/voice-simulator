"""F0と共鳴を固定し、窓内の励振位相とTSPのF2採択を比較する。"""

import argparse
from collections import Counter
from itertools import product
from pathlib import Path
import subprocess

import numpy as np
from scipy.signal import sosfilt

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case, selection_error
import measure_tsp_f2_intervening_excitation as excitation
import measure_tsp_f2_intervening_resonance as resonance
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-intervening-phase.json'


def render_windows(case, reference, cfg, period, out):
    spec, settings = reference['signal'], reference['measurement']
    rate, pulse = spec['sample_rate_hz'], spec['pulse_amplitude']
    length = round(cfg['frame_seconds'] * rate)
    base = spec['fixed_poles_hz']
    added = case['signal']['added_pole_hz']
    truth = [base[0], [added, spec['added_pole_bandwidth_hz']], *base[1:]]
    source = np.zeros(rate * spec['duration_seconds'])
    source[::period] = pulse
    frequency = np.fft.rfftfreq(period, 1 / rate)
    anchor, _, design = known.design_wave(source, rate, truth, frequency)
    sections = np.asarray(design['sections'])
    f, bandwidth = np.asarray(truth).T
    poles = np.exp((-np.pi * bandwidth + 2j * np.pi * f) / rate)
    poles = np.r_[poles, poles.conj()]
    z_inverse = np.exp(-2j * np.pi * frequency / rate)
    transfer = 1 / np.prod(1 - poles[:, None] * z_inverse, axis=0)
    frames, metadata, responses = [], [], []
    for offset in range(period):
        shifted = np.zeros_like(source)
        shifted[offset::period] = pulse
        wave = sosfilt(sections, shifted)
        delayed = np.zeros_like(anchor)
        delayed[offset:] = anchor[:len(anchor) - offset]
        measured = np.fft.rfft(wave[-period:]) / pulse
        expected = transfer * np.exp(-2j * np.pi * frequency * offset / rate)
        responses.append({'pulse_offset_samples': offset, 'exact_delay': np.array_equal(wave, delayed),
                          'harmonic_error': float(np.max(abs(measured - expected)) / np.max(abs(expected)))})
        for order, center in product(settings['orders'], settings['centers']):
            start = int(center * len(wave)) - length // 2
            frames.append(wave[start:start + length].copy())
            metadata.append({'order': order, 'center': center, 'start_sample': start, 'added_pole_hz': added,
                             'pulse_offset_samples': offset, 'excitation_phase_samples': (start - offset) % period})
    np.savez_compressed(out / 'waveform-windows.npz', anchor_wave=anchor, frames=np.stack(frames))
    return anchor, frames, metadata, responses, design


def anchor_matches(case, paths, anchor, rows, fixed):
    spec = case['signal']
    name = excitation.wave_name(spec['f0_hz'], spec['added_pole_hz'])
    with np.load(paths['waves'], allow_pickle=False) as archive:
        same_wave = anchor.tobytes() == archive[name].tobytes()
    reference = {(old['order'], old['center']): (old, probe)
                 for old, probe in zip(tsp.read(paths['summary'])['windows'], tsp.read(paths['probes']), strict=True)
                 if old['f0_hz'] == spec['f0_hz'] and old['added_pole_hz'] == spec['added_pole_hz']}
    controls = [(row, probe) for row, probe in zip(rows, fixed, strict=True) if row['pulse_offset_samples'] == 0]
    for row, probe in controls:
        previous, previous_probe = reference[row['order'], row['center']]
        if (any(row[name] != value for name, value in previous.items() if name != 'f0_hz')
                or any(probe[name] != value for name, value in previous_probe.items() if name != 'lpc_envelope_db')):
            return False
    return same_wave and len(controls) == len(reference)


def compare_phases(rows, frames, fixed, settings, cfg, period):
    centers, orders = settings['centers'], settings['orders']
    observed = {(r['order'], r['center'], r['excitation_phase_samples']): (r, frame, probe)
                for r, frame, probe in zip(rows, frames, fixed, strict=True)}
    scale = max(float(np.max(abs(frame))) for frame in frames)
    max_sample_difference, same_analysis = 0.0, True
    counts, gaps, transitions, displaced = {}, {}, {}, {}
    boundary = cfg['f2_min_gap_hz']
    for order in orders:
        canonical = [observed[order, centers[0], phase] for phase in range(period)]
        for phase, (r, frame, probe) in enumerate(canonical):
            for center in centers[1:]:
                other, copy, other_probe = observed[order, center, phase]
                max_sample_difference = max(max_sample_difference, float(np.max(abs(frame - copy))) / scale)
                pole_error = tsp.max_error(probe['poles'], other_probe['poles'])
                pair_error = selection_error(r['selection'], other['selection'])
                same_analysis = (same_analysis and r['association'] == other['association']
                                 and pole_error is not None and pair_error is not None
                                 and max(pole_error, pair_error) <= cfg['frequency_bandwidth_agreement_hz'])
        canonical_rows = [r for r, _, _ in canonical]
        key = str(order)
        counts[key] = dict(Counter(r['association'] for r in canonical_rows))
        available = [r['added_mode_gap_from_selected_f1_hz'] for r in canonical_rows
                     if r['added_mode_gap_from_selected_f1_hz'] is not None]
        gaps[key] = [min(available), max(available)] if available else None
        displaced[key] = sum(r['association'] != 'model_f2' and bool(r['f2_near_eligible_poles']) for r in canonical_rows)
        transitions[key] = []
        for phase, after in enumerate(canonical_rows):
            before = canonical_rows[phase - 1]
            if before['association'] == after['association']:
                continue
            left, right = (r['added_mode_gap_from_selected_f1_hz'] for r in (before, after))
            crosses = left is not None and right is not None and (left > boundary) != (right > boundary)
            transitions[key].append({'phases_samples': [(phase - 1) % period, phase],
                                     'associations': [before['association'], after['association']],
                                     'gaps_from_selected_f1_hz': [left, right], 'crosses_gap': crosses,
                                     'model_f2_eligible_in_both': bool(before['f2_near_eligible_poles']
                                                                       and after['f2_near_eligible_poles'])})
    return {'counts_by_order': counts, 'gap_range_hz_by_order': gaps, 'transitions_by_order': transitions,
            'displaced_with_model_f2_available_by_order': displaced, 'max_same_phase_sample_relative_error': max_sample_difference,
            'same_phase_analysis': same_analysis}


def measure_cycle(case, reference, cfg, out, execute):
    spec, settings = reference['signal'], reference['measurement']
    pitch = case['signal']['f0_hz']
    rate = spec['sample_rate_hz']
    period, remainder = divmod(rate, pitch)
    if (remainder or (rate * spec['duration_seconds']) % period or pitch != spec['f0_hz']
            or rate != cfg['sample_rate_hz'] / cfg['decimation'] or settings['centers'] != cfg['reference_centers']
            or set(settings['orders']) != set(cfg['order'].values())
            or settings['pre_emphasis_coefficient'] != cfg['pre_emphasis']
            or settings['comparison_gap_hz'] != cfg['f2_min_gap_hz']
            or case['signal']['pulse_offsets'] != 'all_integer_samples_in_one_period'):
        raise ValueError('固定した励振周期またはTSPの設定が一致しません')
    anchor, frames, metadata, responses, design = render_windows(case, reference, cfg, period, out)
    fixed = envelope.fixed_spectra(frames, np.empty(0), out, execute,
                                   orders=[r['order'] for r in metadata], include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = [resonance.inspect_window(frame, probe, rate, cfg, spec['fixed_poles_hz'][1][0],
                                     settings['association_tolerance_hz'], r)
            for frame, probe, r in zip(frames, fixed, metadata, strict=True)]
    phase = compare_phases(rows, frames, fixed, settings, cfg, period)
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    checks = {
        'registered_windows_and_finiteness':
            len(rows) == period * len(settings['orders']) * len(settings['centers'])
            and all(len(frame) == round(cfg['frame_seconds'] * rate) and np.isfinite(frame).all() for frame in frames),
        'fixed_filter_and_delayed_complex_harmonics':
            design['max_pole_error_hz'] is not None and design['max_pole_error_hz'] <= settings['design_pole_error_limit_hz']
            and design['max_wave_error'] / float(np.max(abs(anchor))) <= settings['design_wave_relative_error_limit']
            and design['max_response_error_db'] <= settings['design_response_error_limit_db']
            and all(r['exact_delay'] and r['harmonic_error'] <= settings['harmonic_error_limit'] for r in responses),
        'independent_roots_and_selection': all(
            row['errors']['complex_roots'] <= settings['raw_root_distance_limit']
            and all(value is not None and value <= pole_limit for key, value in row['errors'].items()
                    if key != 'complex_roots') for row in rows),
        'same_relative_phase_across_centers': phase['same_phase_analysis']
            and phase['max_same_phase_sample_relative_error'] <= settings['design_wave_relative_error_limit'],
    }
    return {'checks': checks, 'period_samples': period, 'signal_design': design,
            'phase_results': phase, 'responses': responses, 'windows': rows}, anchor, fixed


def measure(case, reference, cfg, paths, out, execute):
    report, anchor, fixed = measure_cycle(case, reference, cfg, out, execute)
    phase = report['phase_results']
    checks = report['checks']
    # 基準実行と照合するため、従来の要約の項目順も保つ。
    report['checks'] = {'registered_windows_and_finiteness': checks['registered_windows_and_finiteness'],
                        'zero_delay_matches_archived_wave_and_upstream':
                            anchor_matches(case, paths, anchor, report['windows'], fixed),
                        **checks}
    predictions = {
        'phase_changes_order_12_selection': {'model_f2', 'added_mode'} <= phase['counts_by_order']['12'].keys(),
        'phase_switch_preserves_model_f2_and_crosses_gap':
            any(r['model_f2_eligible_in_both'] and r['crosses_gap'] and set(r['associations']) == {'model_f2', 'added_mode'}
                for r in phase['transitions_by_order']['12']),
    }
    return {'checks': report.pop('checks'), 'predictions': predictions, **report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    prior = tsp.open_run(case['excitation_reference'], revision)
    prior_case, prior_path = saved_case(prior, excitation.CASE)
    reference = tsp.open_run(prior_case['resonance_reference'], revision)
    definition, reference_path = saved_case(reference, resonance.CASE)
    registered = tsp.open_run(definition['tsp_reference'], revision)
    cfg, cfg_path = saved_case(registered, tsp.CASE)
    paths = {'waves': tsp.verified_path(prior, 'artifacts/waveforms.npz'),
             'probes': tsp.verified_path(prior, 'artifacts/upstream-envelopes.json'),
             'summary': tsp.verified_path(prior, 'summary.json')}
    modules = (envelope, excitation, known, resonance, tsp)
    inputs = [CASE, Path(__file__).resolve(), prior_path, reference_path, cfg_path, *paths.values(), envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (prior, reference, registered)),
              *(Path(module.__file__) for module in modules),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_f2_bandwidth_held_out', 'measure_tsp_f2_annotation',
                   'measure_tsp_f2_harmonic_bandwidth', 'measure_tsp_f2_harmonic_spacing',
                   'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, definition, cfg['measurement'], paths, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
