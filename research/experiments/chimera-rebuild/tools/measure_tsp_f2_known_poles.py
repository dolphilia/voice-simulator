"""既知の共役極を持つ対照波形で、F2の帯域幅条件を検証する。"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess

import numpy as np
from scipy import signal

import measure_tsp_f2_bandwidth_envelope as envelope
import measure_tsp_f2_bandwidth_held_out as held_out
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-bandwidth-known-poles.json'


def parameters(case, cfg, settings):
    spec, measure = case['signal'], case['measurement']
    frequencies = spec['pole_frequencies_hz']
    variants = [entry['bandwidths_hz'] for entry in spec['variants']]
    fs = spec['sample_rate_hz']
    if (fs != cfg['sample_rate_hz'] / cfg['decimation'] or measure['centers'] != cfg['reference_centers'] or
            set(measure['orders']) != set(cfg['order'].values()) or
            measure['candidate_f2_bandwidth_limit_hz'] != settings['candidate_f2_bandwidth_limit_hz']):
        raise ValueError('先行のTSP計測と標本化・次数・F2条件が一致しません')
    if (len(variants) != 2 or len(frequencies) != 3 or not 0 < frequencies[0] < frequencies[1] < frequencies[2] < fs / 2
            or any(len(bands) != 3 or min(bands) <= 0 for bands in variants)
            or [i for i, (a, b) in enumerate(zip(*variants, strict=True)) if a != b] != [1]):
        raise ValueError('対照2波形ではF2の帯域幅だけを変える必要があります')
    return fs


def design_wave(input_, fs, truth, grid):
    f, b = np.asarray(truth, dtype=float).T
    radius = np.exp(-np.pi * b / fs)
    angle = 2 * np.pi * f / fs
    sections = np.column_stack([np.ones(f.size), np.zeros(f.size), np.zeros(f.size),
                                np.ones(f.size), -2 * radius * np.cos(angle), radius**2])
    pcm = signal.sosfilt(sections, input_)
    known = radius * np.exp(1j * angle)
    complex_poles = np.r_[known, np.conj(known)]
    direct_coefficients = np.poly(complex_poles).real
    recursive = signal.lfilter([1.0], direct_coefficients, input_)
    cascaded_coefficients = np.array([1.0])
    for section in sections:
        cascaded_coefficients = np.convolve(cascaded_coefficients, section[3:])
    roots = np.roots(cascaded_coefficients)
    found = sorted([[float(np.angle(p) * fs / (2 * np.pi)), float(-np.log(abs(p)) * fs / np.pi)]
                    for p in roots if p.imag > 0])
    z_inverse = np.exp(-2j * np.pi * grid / fs)
    analytic = -20 * np.log10(abs(np.prod(1 - complex_poles[:, None] * z_inverse, axis=0)))
    polynomial = -20 * np.log10(abs(np.polynomial.polynomial.polyval(z_inverse, cascaded_coefficients)))
    return pcm, analytic, {'poles_hz': found, 'pole_radii': radius.tolist(), 'sections': sections.tolist(),
                           'max_wave_error': float(np.max(abs(pcm - recursive))),
                           'max_pole_error_hz': tsp.max_error(truth, found),
                           'max_response_error_db': float(np.max(abs(analytic - polynomial)))}


def local_peak(curve, grid, frequency, width):
    return envelope.strongest_peak(curve, grid, (frequency - width, frequency + width))


def evaluate_window(frame, fixed, observed, fs, grid, truth, cfg, tune, settings):
    poles = fixed['poles']
    original = envelope.select(poles, cfg)
    alternate = envelope.select(poles, cfg, tune['candidate_f2_bandwidth_limit_hz'])
    independent = envelope.select(observed['poles'], cfg, tune['candidate_f2_bandwidth_limit_hz'])
    _, roots_error, axial = tsp.compare_poles(observed, fixed, cfg)
    candidate_distance = tune['known_pole_association_max_hz']
    f2_expected = truth[1][0]
    close = min(poles, key=lambda p: abs(p[0] - f2_expected), default=None)
    nearby = close if close is not None and abs(close[0] - f2_expected) <= candidate_distance else None
    lpc = np.asarray(fixed['lpc_envelope_db'])
    response = np.polynomial.polynomial.polyval(np.exp(-2j * np.pi * grid / fs), fixed['coefficients'])
    computed = 10 * np.log10(fixed['prediction_error'] / (abs(response)**2 + 1e-30))
    emphasized = np.r_[frame[0], frame[1:] - cfg['pre_emphasis'] * frame[:-1]]
    fft, fft_error = envelope.spectrum_db(emphasized * np.hamming(len(frame)), fs, grid, settings['gaussian_sigma_hz'])
    modes = [{'model_pole_hz': f, 'lpc': local_peak(lpc, grid, f, candidate_distance),
              'periodogram': local_peak(fft, grid, f, candidate_distance)} for f, _ in truth]
    onset = None
    if nearby is None:
        onset = 'no_eligible_estimated_pole_near_model_f2'
    elif original['f2'] != nearby:
        onset = 'fixed_pole_selection'
    elif alternate['f2'] != nearby:
        onset = 'f2_bandwidth_selection'
    result = {'fixed': original, 'bandwidth_limited': alternate, 'poles': poles,
              'estimated_pole_near_known_f2': nearby, 'first_difference_from_known_f2': onset,
              'nyquist_axis_matches': axial, 'local_peaks': modes,
              'errors': {'poles_hz': roots_error, 'fixed_selection_hz': tsp.max_error(held_out.pair(original), observed['f1_f2_hz']),
                         'limited_selection_hz': held_out.selection_error(alternate, independent),
                         'lpc_envelope_db': float(np.max(abs(lpc - computed))), 'periodogram_db': fft_error}}
    return result, {'lpc_envelope_db': lpc.tolist(), 'periodogram_db': fft.tolist()}


def aggregate(rows, truth, tolerance):
    result = {}
    for variant in truth:
        result[variant] = {}
        for order in dict.fromkeys(row['order'] for row in rows if row['variant'] == variant):
            related = [row for row in rows if row['variant'] == variant and row['order'] == order]
            methods = {}
            for name in ('fixed', 'bandwidth_limited'):
                paired = [pair for row in related if (pair := held_out.pair(row[name])) is not None]
                median = np.median(paired, axis=0).tolist() if paired else None
                associated = next((f'F{i}' for i, (freq, _) in enumerate(truth[variant], 1)
                                   if median and abs(median[1] - freq) <= tolerance), None)
                methods[name] = {'complete_windows': len(paired), 'median_f1_f2_hz': median,
                                 'matched_model_mode': associated,
                                 'signed_f2_error_hz': median[1] - truth[variant][1][0] if median else None}
            result[variant][str(order)] = methods
    return result


def measure(case, cfg, settings, artifacts, execute):
    spec, tune = case['signal'], case['measurement']
    fs = parameters(case, cfg, settings)
    grid = np.arange(0, fs / 2 + settings['spectrum_grid_hz'], settings['spectrum_grid_hz'])
    source = np.zeros(int(fs * spec['duration_seconds']))
    source[::spec['excitation']['period_samples']] = spec['excitation']['pulse_amplitude']
    truth, designs, analytic, frames, windows = {}, {}, {}, [], []
    for entry in spec['variants']:
        variant = entry['id']
        truth[variant] = list(zip(spec['pole_frequencies_hz'], entry['bandwidths_hz'], strict=True))
        wave, exact, designs[variant] = design_wave(source, fs, truth[variant], grid)
        np.save(artifacts / f'{variant}.npy', wave, allow_pickle=False)
        analytic[variant] = exact.tolist()
        designs[variant]['analytic_local_peaks'] = [local_peak(exact, grid, f, tune['known_pole_association_max_hz'])
                                                   for f, _ in truth[variant]]
        for order in tune['orders']:
            for q in tune['centers']:
                window = tsp.window(wave, [0.0, spec['duration_seconds'], 'IY1'], q, order, cfg)
                start = window['start_sample']
                frame = wave[start:start + int(cfg['frame_seconds'] * fs)]
                frames.append(frame)
                windows.append((variant, order, q, window))
    fixed = envelope.fixed_spectra(frames, grid, artifacts, execute, orders=[row[1] for row in windows])
    rows, curves = [], []
    for (variant, order, q, observed), frame, rust in zip(windows, frames, fixed, strict=True):
        row, curve = evaluate_window(frame, rust, observed, fs, grid, truth[variant], cfg, tune, settings)
        info = {'variant': variant, 'order': order, 'center': q, 'start_sample': observed['start_sample']}
        rows.append({**info, **row})
        curves.append({**info, **curve})
    spectra = {'frequency_hz': grid.tolist(), 'analytic_transfer_db': analytic, 'windows': curves}
    payload = json.dumps(spectra, separators=(',', ':')).encode()
    (artifacts / 'spectra.json.gz').write_bytes(gzip.compress(payload, mtime=0))
    medians = aggregate(rows, truth, tune['known_pole_association_max_hz'])
    narrow, wide = medians['narrow-f2'], medians['wide-f2']
    predictions = {
        'narrow_f2_retained': all(method['matched_model_mode'] == 'F2' for order in narrow.values() for method in order.values()),
        'wide_f2_retained_by_fixed': all(order['fixed']['matched_model_mode'] == 'F2' for order in wide.values()),
        'wide_f2_skipped_by_limit': any(order['bandwidth_limited']['matched_model_mode'] == 'F3' for order in wide.values()),
    }
    threshold = cfg['frequency_bandwidth_agreement_hz']
    checks = {
        'all_windows': len(rows) == 12 and all(len(frame) == round(fs * cfg['frame_seconds']) for frame in frames),
        'analytic_design': all(d['max_wave_error'] <= tune['design_wave_tolerance'] and
                               d['max_pole_error_hz'] is not None and d['max_pole_error_hz'] <= tune['design_pole_tolerance_hz'] and
                               d['max_response_error_db'] <= tune['design_response_tolerance_db'] for d in designs.values()),
        'independent_poles_and_selection': all(error is not None and error <= threshold for row in rows
                                               for field, error in row['errors'].items() if field.endswith('_hz')),
        'independent_envelopes': all(row['errors']['lpc_envelope_db'] <= settings['lpc_envelope_tolerance_db'] and
                                     row['errors']['periodogram_db'] <= settings['periodogram_direct_dft_tolerance_db'] for row in rows),
        'only_f2_selection_changes': all(row['fixed']['f1'] == row['bandwidth_limited']['f1'] for row in rows),
    }
    return {'checks': checks, 'hypotheses': predictions, 'model_poles_hz': truth, 'designs': designs,
            'medians': medians, 'windows': rows, 'scipy': envelope.scipy.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    previous = tsp.open_run(case['held_out'], revision)
    registered, previous_case = held_out.saved_case(previous, held_out.CASE)
    baseline, pilot = (tsp.open_run(registered[k], revision) for k in ('baseline', 'pilot'))
    cfg_case, baseline_case = held_out.saved_case(baseline, tsp.CASE)
    settings_case, pilot_case = held_out.saved_case(pilot, envelope.CASE)
    sources = [CASE, Path(__file__).resolve(), envelope.PROBE, previous_case, baseline_case, pilot_case,
               tsp.verified_path(previous, 'summary.json'), Path(envelope.__file__), Path(tsp.__file__), Path(held_out.__file__),
               UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
               UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', UPSTREAM / 'Cargo.lock',
               WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
               WORKSPACE / 'tools/upstream_baseline.py']
    sources.extend(path / 'manifest.json' for path, _ in (previous, baseline, pilot))
    return record_measurement(args.run_id, CASE, sources, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'held_out_reference': previous[0].name,
    }, lambda artifacts, execute: measure(case, cfg_case['measurement'], settings_case['measurement'], artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
