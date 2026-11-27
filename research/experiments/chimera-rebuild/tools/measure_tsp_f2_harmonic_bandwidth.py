"""同じ7種類の周期励振で、F2の帯域幅が推定と採択へ与える影響を測る。"""

import argparse
from collections import Counter
import math
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case, selection_error
import measure_tsp_f2_harmonic_spacing as spacing
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-harmonic-bandwidth.json'


def root_poles(roots, rate):
    return sorted([math.atan2(imaginary, real) * rate / (2 * math.pi),
                   -math.log(math.hypot(real, imaginary)) * rate / math.pi]
                  for real, imaginary in roots if imaginary > 0)


def association(selection, reference, tolerance):
    chosen = selection['f2']
    if chosen is None:
        return selection['reason']
    return next((label for label, frequency in zip(('F1', 'F2', 'F3'), reference, strict=True)
                 if abs(chosen[0] - frequency) <= tolerance), 'outside_model_modes')


def inspect_window(frame, fixed, rate, cfg, reference, case, meta):
    near_f2 = case['association_tolerance_hz']
    added_limit = case['comparison_f2_bandwidth_limit_hz']
    f2 = reference[1]
    raw = root_poles(fixed['roots'], rate)
    visible = [p for p in raw if p[0] >= cfg['pole_min_frequency_hz'] and p[1] <= cfg['pole_max_bandwidth_hz']]
    close_before = [p for p in raw if abs(p[0] - f2) <= near_f2]
    close_after = [p for p in fixed['poles'] if abs(p[0] - f2) <= near_f2]
    default = envelope.select(fixed['poles'], cfg)
    limited = envelope.select(fixed['poles'], cfg, added_limit)
    selected = association(default, reference, near_f2)
    selected_limited = association(limited, reference, near_f2)
    if selected == 'F2':
        first = None
    elif not close_before:
        first = 'root_estimation'
    elif not close_after:
        first = 'public_pole_filter'
    elif default['f1'] is None:
        first = 'f1_selection'
    else:
        first = 'f2_selection'

    independent, negative = tsp.independent_poles(frame, rate, meta['order'], cfg)
    _, exported_error, axial = tsp.compare_poles({'poles': independent, 'negative_real_roots': negative}, fixed, cfg)
    # 独立計算の近傍比較では帯域幅上限を外し、公開推定器が落とした根も確認する。
    independent_raw, _ = tsp.independent_poles(frame, rate, meta['order'],
        {**cfg, 'pole_min_frequency_hz': 0, 'pole_max_bandwidth_hz': math.inf})
    independent_near = [p for p in independent_raw if abs(p[0] - f2) <= near_f2]
    return {**meta, 'f2_near_unfiltered_poles_hz': close_before, 'f2_near_public_poles_hz': close_after,
            'fixed_selection': default, 'limited_selection': limited, 'fixed_association': selected,
            'limited_association': selected_limited, 'default_first_difference': first,
            'lost_f2_with_added_limit': selected == 'F2' and selected_limited != 'F2',
            'selection_errors_hz': {
                'fixed': selection_error(default, envelope.select(independent, cfg)),
                'limited': selection_error(limited, envelope.select(independent, cfg, added_limit)),
            },
            'public_filter_error_hz': tsp.max_error(visible, fixed['poles']),
            'independent_public_error_hz': exported_error,
            'independent_near_root_error_hz': tsp.max_error(close_before, independent_near),
            'nyquist_axis_matches': axial}


def window_totals(windows):
    return {'fixed': dict(Counter(row['fixed_association'] for row in windows)),
            'limited': dict(Counter(row['limited_association'] for row in windows)),
            'default_first_difference': dict(Counter(row['default_first_difference'] or 'within_f2'
                                                     for row in windows)),
            'lost_f2_due_to_added_limit': sum(row['lost_f2_with_added_limit'] for row in windows)}


def measure(case, prior_case, source_case, config, files, out, execute):
    spec, tune = source_case['signal'], source_case['measurement']
    rate, pulse = spec['sample_rate_hz'], spec['excitation']['pulse_amplitude']
    variants = case['f2_bandwidths_hz']
    pitches = prior_case['f0_hz']
    fixed_truth = prior_case['fixed_poles_hz']
    truth = {band: [fixed_truth[0], [fixed_truth[1][0], band], fixed_truth[2]] for band in variants}
    frequency = [pole[0] for pole in fixed_truth]
    baseline = tsp.read(files['source_summary'])
    if (variants != [fixed_truth[1][1], baseline['model_poles_hz']['wide-f2'][1][1]]
            or truth[variants[1]] != baseline['model_poles_hz']['wide-f2']
            or tune['candidate_f2_bandwidth_limit_hz'] != case['comparison_f2_bandwidth_limit_hz']
            or tune['known_pole_association_max_hz'] != case['association_tolerance_hz']
            or rate != config['sample_rate_hz'] / config['decimation']):
        raise ValueError('帯域幅以外の条件が先行実行と一致しません')

    grid = np.arange(0, rate / 2 + 5, 5)
    metrics, frames, metadata, waveforms = [], [], [], {}
    length = int(config['frame_seconds'] * rate)
    for band in variants:
        for f0 in pitches:
            period, remainder = divmod(rate, f0)
            if remainder:
                raise ValueError(f'整数標本で周期を表せません ({f0} Hz)')
            excitation = np.zeros(int(rate * spec['duration_seconds']))
            excitation[::period] = pulse
            wave, _, design = known.design_wave(excitation, rate, truth[band], grid)
            waveforms[f'b{band}_f0_{f0}_hz'] = wave
            harmonic, harmonic_error = spacing.harmonic_observation(wave, design['sections'], period, pulse, rate,
                (1500, 2500))
            metrics.append({'bandwidth_hz': band, 'f0_hz': f0, 'design': design,
                            'theoretical_f2_band_harmonic_hz': harmonic, 'periodic_error': harmonic_error})
            for order in tune['orders']:
                for center in tune['centers']:
                    start = int(center * spec['duration_seconds'] * rate) - length // 2
                    frames.append(wave[start:start + length])
                    metadata.append({'bandwidth_hz': band, 'f0_hz': f0, 'order': order, 'center': center,
                                     'start_sample': start})
    np.savez_compressed(out / 'waveforms.npz', **waveforms)
    fixed = envelope.fixed_spectra(frames, grid, out, execute, orders=[m['order'] for m in metadata],
                                   include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = [inspect_window(frame, poles, rate, config, frequency, case, meta)
            for frame, poles, meta in zip(frames, fixed, metadata, strict=True)]

    narrow, wide = [[r for r in rows if r['bandwidth_hz'] == band] for band in variants]
    public_records = [{key: value for key, value in probe.items() if key != 'roots'} for probe in fixed]
    narrow_probe, wide_probe = public_records[:len(narrow)], public_records[len(narrow):]
    anchor = rate // spec['excitation']['period_samples']
    older_wide_rows = [r for r in baseline['windows'] if r['variant'] == 'wide-f2']
    anchor_rows = [r for r in wide if r['f0_hz'] == anchor]
    anchor_probe = [probe for r, probe in zip(wide, wide_probe, strict=True) if r['f0_hz'] == anchor]
    archived_probe = [probe for row, probe in zip(baseline['windows'], tsp.read(files['source_poles']), strict=True)
                      if row['variant'] == 'wide-f2']
    with np.load(files['spacing_waves'], allow_pickle=False) as archived:
        narrow_waves_agree = set(archived.files) == {f'f0_{f0}_hz' for f0 in pitches} and all(
            np.array_equal(waveforms[f'b{variants[0]}_{key}'], archived[key]) for key in archived.files)

    limit = config['frequency_bandwidth_agreement_hz']
    checks = {
        'all_pairs_and_window_lengths': len(narrow) == len(wide) == len(pitches) * len(tune['orders']) * len(tune['centers'])
        and all(len(frame) == length and np.isfinite(frame).all() for frame in frames),
        'narrow_archive_matches': narrow_waves_agree
        and narrow_probe == tsp.read(files['spacing_poles']),
        'wide_125hz_archive_matches': np.array_equal(waveforms[f'b{variants[1]}_f0_{anchor}_hz'],
            np.load(files['source_wave'], allow_pickle=False)) and anchor_probe == archived_probe
        and [(r['order'], r['center'], r['fixed_selection'], r['limited_selection']) for r in anchor_rows]
        == [(r['order'], r['center'], r['fixed'], r['bandwidth_limited']) for r in older_wide_rows],
        'design_and_harmonics_reconstructed': all(m['design']['max_wave_error'] <= tune['design_wave_tolerance']
            and m['design']['max_pole_error_hz'] <= tune['design_pole_tolerance_hz']
            and m['design']['max_response_error_db'] <= tune['design_response_tolerance_db']
            and m['periodic_error'] <= prior_case['harmonic_response_relative_tolerance'] for m in metrics),
        'independent_roots_filter_and_selection': all(value is not None and value <= limit for r in rows for value in
            (r['independent_near_root_error_hz'], r['public_filter_error_hz'], r['independent_public_error_hz'],
             *r['selection_errors_hz'].values())),
    }
    by_pitch = {band: {f0: window_totals([row for row in rows if row['bandwidth_hz'] == band and row['f0_hz'] == f0])
                       for f0 in pitches} for band in variants}
    increased = [f0 for f0 in pitches if by_pitch[variants[1]][f0]['fixed'].get('F2', 0)
                 < by_pitch[variants[0]][f0]['fixed'].get('F2', 0)]
    missed = [r for r in wide if r['default_first_difference'] in {'root_estimation', 'public_pole_filter'}]
    lost = sorted({r['f0_hz'] for r in wide if r['lost_f2_with_added_limit']})
    return {'checks': checks, 'predictions': {'wide_f2_changes_default_results_at_multiple_f0': len(increased) >= 2,
            'wide_f2_can_be_lost_before_tsp_selection': bool(missed),
            'additional_gate_loses_default_hits_at_multiple_f0': len(lost) >= 2},
            'comparison': {'default_f2_decreased_at_f0_hz': increased, 'added_limit_lost_f2_at_f0_hz': lost,
                           'by_pitch': by_pitch, 'all_windows': {variants[0]: window_totals(narrow),
                                                               variants[1]: window_totals(wide)}},
            'designs': metrics, 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    prior, source, upstream = (tsp.open_run(case[name], revision)
                              for name in ('spacing_reference', 'filter_reference', 'tsp_reference'))
    prior_case, prior_path = saved_case(prior, spacing.CASE)
    source_case, source_path = saved_case(source, known.CASE)
    config, config_path = saved_case(upstream, tsp.CASE)
    files = {'spacing_waves': tsp.verified_path(prior, 'artifacts/waveforms.npz'),
             'spacing_poles': tsp.verified_path(prior, 'artifacts/upstream-envelopes.json'),
             'source_wave': tsp.verified_path(source, 'artifacts/wide-f2.npy'),
             'source_poles': tsp.verified_path(source, 'artifacts/upstream-envelopes.json'),
             'source_summary': tsp.verified_path(source, 'summary.json')}
    inputs = [CASE, Path(__file__).resolve(), prior_path, source_path, config_path, *files.values(), envelope.PROBE,
              *(r[0] / 'manifest.json' for r in (prior, source, upstream)),
              *(Path(module.__file__) for module in (envelope, spacing, known, tsp)),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_f2_annotation', 'measure_fan_crossing_allocations',
                  'measure_tsp_f2_bandwidth_held_out', 'measure_uniform_tube', 'upstream_baseline')),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, prior_case, source_case, config['measurement'], files, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
