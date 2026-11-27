"""固定した声道極で、周期励振の間隔がF2の観測に与える差を測る。"""

import argparse
import math
from pathlib import Path
import subprocess

import numpy as np
from scipy import signal
from scipy.io import wavfile

import measure_tsp_f2_annotation as annotation
import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case, selection_error
import measure_tsp_f2_known_poles as known
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-harmonic-spacing.json'


def display_peak(config, wave, rate):
    # 注釈ページと同じ切り出し位置、量子化、窓、探索帯域を使う。
    begin, end = config['synthetic_phone_seconds']
    context = config['phone_context_ms'] / 1000
    first, stop = math.floor((begin - context) * rate), math.ceil((end + context) * rate)
    x = annotation.control_pcm(wave)[first:stop].astype(float) / 32768
    frequency, power = annotation.average_spectrum(x, rate, config['analysis_window_samples'],
        (begin - first / rate, end - first / rate), round(rate * config['hop_ms'] / 1000))
    lower, upper = config['synthetic_peak_search_hz']
    band = (frequency >= lower) & (frequency <= upper)
    return float(frequency[band][np.argmax(power[band])])


def harmonic_observation(wave, sections, period, pulse, rate, band):
    # 末尾の1周期は入力の位相0で始まる。入力DFTは全ビンで単発パルスの振幅になる。
    frequency = np.fft.rfftfreq(period, 1 / rate)
    _, theory = signal.sosfreqz(sections, worN=frequency, fs=rate)
    measured = np.fft.rfft(wave[-period:]) / pulse
    relative = float(np.max(abs(measured - theory)) / np.max(abs(theory)))
    inside = (frequency >= band[0]) & (frequency <= band[1])
    index = np.argmax(abs(theory[inside]))
    return float(frequency[inside][index]), relative


def analyze_lpc(windows, fixed, cfg, truth, association):
    results = []
    for (meta, observed), rust in zip(windows, fixed, strict=True):
        selected = envelope.select(rust['poles'], cfg)
        independent = envelope.select(observed['poles'], cfg)
        _, pole_error, axis = tsp.compare_poles(observed, rust, cfg)
        error = selected['f2'][0] - truth if selected['f2'] is not None else None
        near = [p for p in rust['poles'] if abs(p[0] - truth) <= association]
        if error is not None and abs(error) <= association:
            first = None
        elif not near:
            first = 'no_estimated_pole_near_model_f2'
        else:
            first = 'f2_selection'
        results.append({**meta, 'selected': selected, 'signed_f2_error_hz': error,
                        'nearest_f2_candidates': near, 'first_difference_from_model_f2': first,
                        'independent_poles_error_hz': pole_error, 'nyquist_axis_matches': axis,
                        'independent_selection_error_hz': selection_error(selected, independent)})
    return results


def save_plot(path, measurements, windows, truth):
    fig, ax = annotation.plt.subplots(figsize=(9, 4.5), layout='constrained')
    x = [row['f0_hz'] for row in measurements]
    ax.axhline(truth, color='#3c4147', linestyle='--', label=r'$F_2$')
    ax.plot(x, [row['theoretical_harmonic_hz'] for row in measurements], '^', color='#247b96', label=r'$kF_0$')
    ax.plot(x, [row['display_peak_hz'] for row in measurements], 'x', color='#111111', label=r'$argmax_f P(f)$')
    for order, color, offset in ((12, '#b35026', -3), (14, '#7e4c9e', 3)):
        pairs = [(row['f0_hz'] + offset, row['selected']['f2'][0]) for row in windows
                 if row['order'] == order and row['selected']['f2']]
        if pairs:
            ax.scatter(*zip(*pairs, strict=True), s=25, alpha=.65, color=color, label=f'LPC {order}')
    ax.set(xlabel=r'$F_0$ [Hz]', ylabel=r'$f$ [Hz]', xticks=x)
    ax.grid(alpha=.25)
    ax.legend(ncols=2, loc='best')
    fig.savefig(path, dpi=150)
    annotation.plt.close(fig)


def measure(case, cfg, original, review, references, out, execute):
    spec, tune = original['signal'], original['measurement']
    rate = spec['sample_rate_hz']
    pulse = spec['excitation']['pulse_amplitude']
    material = tsp.read(references['original_summary'])
    truth = case['fixed_poles_hz']
    if (truth != material['model_poles_hz']['narrow-f2'] or rate != review['analysis_rate_hz']
            or rate != cfg['sample_rate_hz'] / cfg['decimation'] or tune['centers'] != cfg['reference_centers']
            or set(tune['orders']) != set(cfg['order'].values())):
        raise ValueError('上流と先行実行の計測条件または共鳴が一致しません')
    known_f2 = truth[1][0]
    grid = np.arange(0, rate / 2 + 5, 5)
    waves, metrics, frames, windows = {}, [], [], []
    for pitch in case['f0_hz']:
        period, remainder = divmod(rate, pitch)
        if remainder:
            raise ValueError(f'周期を整数標本で表せません ({pitch} Hz)')
        source = np.zeros(int(rate * spec['duration_seconds']))
        source[::period] = pulse
        wave, _, design = known.design_wave(source, rate, truth, grid)
        waves[f'f0_{pitch}_hz'] = wave
        wavfile.write(out / f'f0-{pitch}.wav', rate, annotation.control_pcm(wave))
        expected, harmonic_error = harmonic_observation(wave, design['sections'], period, pulse, rate,
                                                        review['synthetic_peak_search_hz'])
        observed_peak = display_peak(review, wave, rate)
        metrics.append({'f0_hz': pitch, 'period_samples': period, 'theoretical_harmonic_hz': expected,
                        'harmonic_response_relative_error': harmonic_error, 'display_peak_hz': observed_peak,
                        'absolute_peak_to_harmonic_error_hz': abs(observed_peak - expected), 'design': design})
        for order in tune['orders']:
            for center in tune['centers']:
                observed = tsp.window(wave, [0.0, spec['duration_seconds'], 'IY1'], center, order, cfg)
                start = observed['start_sample']
                frames.append(wave[start:start + review['analysis_window_samples']])
                windows.append(({'f0_hz': pitch, 'order': order, 'center': center, 'start_sample': start}, observed))
    np.savez_compressed(out / 'waveforms.npz', **waves)
    fixed = envelope.fixed_spectra(frames, grid, out, execute, orders=[meta['order'] for meta, _ in windows])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = analyze_lpc(windows, fixed, cfg, known_f2, case['lpc_known_f2_association_hz'])

    baseline = rate // spec['excitation']['period_samples']
    archived_wave = np.load(references['original_wave'], allow_pickle=False)
    archived_rows = [item for item in material['windows'] if item['variant'] == 'narrow-f2']
    base_rows = [row for row in rows if row['f0_hz'] == baseline]
    annotation_peak = tsp.read(references['annotation_summary'])['control_peak_hz']
    base_peak = next(row['display_peak_hz'] for row in metrics if row['f0_hz'] == baseline)
    design_errors = [row['design'] for row in metrics]
    limit = cfg['frequency_bandwidth_agreement_hz']
    checks = {
        'existing_pulse_control_matches': np.array_equal(waves[f'f0_{baseline}_hz'], archived_wave)
        and base_peak == annotation_peak
        and [(r['order'], r['center'], r['selected']) for r in base_rows]
        == [(r['order'], r['center'], r['fixed']) for r in archived_rows],
        'fixed_filter_agrees_with_independent_calculation': all(
            d['max_wave_error'] <= tune['design_wave_tolerance'] and d['max_pole_error_hz'] <= tune['design_pole_tolerance_hz']
            and d['max_response_error_db'] <= tune['design_response_tolerance_db'] for d in design_errors),
        'periodic_harmonics_match_filter_response': all(row['harmonic_response_relative_error']
            <= case['harmonic_response_relative_tolerance'] for row in metrics),
        'upstream_poles_and_selections_match_independent_lpc': all(
            error is not None and error <= limit for row in rows for error in
            (row['independent_poles_error_hz'], row['independent_selection_error_hz'])),
    }
    peaks = [row['display_peak_hz'] for row in metrics]
    span = max(peaks) - min(peaks)
    close_harmonics = sum(row['absolute_peak_to_harmonic_error_hz'] <= case['display_peak_match_tolerance_hz'] for row in metrics)
    different = [row for row in rows if row['first_difference_from_model_f2']]
    save_plot(out / 'f2-harmonics.png', metrics, rows, known_f2)
    return {'checks': checks, 'predictions': {'display_peak_tracks_sampled_response': (
                close_harmonics >= case['minimum_peak_matches'] and span > case['minimum_display_peak_span_hz']),
                'lpc_occasionally_misses_known_pole': bool(different)},
            'fixed_f2_hz': known_f2, 'reference_f0_hz': baseline, 'display_span_hz': span,
            'matched_harmonics': close_harmonics, 'windows_outside_f2_association': len(different),
            'pitch_conditions': metrics, 'windows': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    original, annotation_run, tsp_run = (tsp.open_run(case[tag], rev)
                                        for tag in ('filter_reference', 'annotation_reference', 'tsp_reference'))
    source, original_case = saved_case(original, known.CASE)
    review, review_case = saved_case(annotation_run, annotation.CASE)
    config, tsp_case = saved_case(tsp_run, tsp.CASE)
    references = {'original_summary': tsp.verified_path(original, 'summary.json'),
                  'original_wave': tsp.verified_path(original, 'artifacts/narrow-f2.npy'),
                  'annotation_summary': tsp.verified_path(annotation_run, 'summary.json')}
    inputs = [CASE, Path(__file__).resolve(), original_case, review_case, tsp_case, *references.values(),
              *(run[0] / 'manifest.json' for run in (original, annotation_run, tsp_run)), envelope.PROBE,
              *(Path(module.__file__) for module in (annotation, envelope, known, tsp)),
              *(WORKSPACE / f'tools/{name}.py' for name in ('measure_tsp_f2_bandwidth_held_out', 'measure_fan_crossing_allocations',
                                                          'measure_uniform_tube', 'upstream_baseline')),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda out, execute: measure(case, config['measurement'], source, review, references, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
