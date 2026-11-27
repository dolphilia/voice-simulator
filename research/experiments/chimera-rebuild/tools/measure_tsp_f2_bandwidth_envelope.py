"""保存済みのTSP 2語で、F2の帯域幅条件と同じ窓の包絡を比較する。"""

import argparse
import csv
import gzip
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
import scipy
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

import measure_tsp_stressed_vowel_formants as base
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-bandwidth-envelope.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_f2_envelope_probe.rs'


def load_sources(case):
    prior = base.open_run(case['baseline'], case['upstream_revision'])
    root, manifest = prior
    paths = [root / 'manifest.json', base.verified_path(prior, 'summary.json'),
             base.verified_path(prior, 'artifacts/upstream-formants.json')]
    repo = WORKSPACE.parents[2]
    registered_name = base.CASE.relative_to(repo).as_posix()
    registered = root / manifest['source_snapshot'] / registered_name
    inputs = {row['path']: row['sha256'] for row in manifest['inputs']}
    if sha256(registered) != inputs.get(registered_name):
        raise ValueError('先行ケースの定義を照合できません')
    prior_case = base.read(registered)
    aligned = base.open_run(prior_case['alignment'], case['upstream_revision'])
    uid = case['utterance']
    path = base.verified_path(aligned, f'artifacts/corpus/recording/{uid}/{uid}.wav')
    if sha256(path) != inputs.get(path.relative_to(repo).as_posix()):
        raise ValueError('先行計測と同じWAVが必要です')
    return prior_case['measurement'], paths, registered, aligned[0] / 'manifest.json', path


def extract_frames(case, cfg, summary, fixed, wave):
    uid = case['utterance']
    fs = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(cfg['frame_seconds'] * fs)
    lo = base.filtered_wave(wave, 'recording', cfg)
    rows, frames = [], []
    for token in case['tokens']:
        index = token['phone_index']
        saved = next(row['recording'] for row in summary['tokens'][uid] if row['indexes']['recording'] == index)
        reference = next(row for row in fixed[uid]['sources']['recording'] if row['index'] == index)
        interval = saved['interval']
        if saved['word'] != token['word'] or interval[2] != 'IY1' or case['centers'] != cfg['reference_centers']:
            raise ValueError('音素・語・基準窓が先行ケースと一致しません')
        prior_windows = {row['center']: (row, ref) for row, ref in zip(saved['windows'], reference['windows'], strict=True)}
        for q in case['centers']:
            observed = base.window(lo, interval, q, cfg['order'][uid[0]], cfg)
            before, rust_before = prior_windows[q]
            start = observed['start_sample']
            frame = lo[start:start + length]
            if len(frame) != length or start != before['start_sample'] or observed['outside_phone_ms'] > 1e-9:
                raise ValueError(f"窓の標本区間が一致しません ({token['word']}, {q})")
            frames.append(frame)
            rows.append({**token, 'center': q, 'start_sample': start, 'interval': interval,
                         'observed': observed, 'prior_fixed': rust_before})
    return fs, rows, frames


def select(poles, cfg, f2_bandwidth=None):
    f1 = next((p for p in poles if p[0] < cfg['f1_max_frequency_hz'] and p[1] < cfg['f1_max_bandwidth_hz']), None)
    if f1 is None:
        return {'f1': None, 'f2': None, 'reason': 'no_f1'}
    f2 = next((p for p in poles
               if f1[0] + cfg['f2_min_gap_hz'] < p[0] < cfg['f2_max_frequency_hz']
               and (f2_bandwidth is None or p[1] < f2_bandwidth)), None)
    return {'f1': f1, 'f2': f2, 'reason': 'no_f2' if f2 is None else None}


def controls(cfg, limit):
    f1, at_limit, wide, narrow = [350, 80], [900, limit], [1250, limit + 1], [2300, 80]
    definitions = [
        ('no_f1', [[1650, 50]], None, None, 'no_f1'),
        ('at_limit', [f1, at_limit], at_limit, None, 'no_f2'),
        ('next_usable', [f1, [550, 90], at_limit, wide, narrow], at_limit, narrow, None),
        ('upper_limit', [f1, [3500, 50]], None, None, 'no_f2'),
    ]
    return {name: (select(poles, cfg)['f2'] == fixed
                   and select(poles, cfg, limit)['f2'] == expected
                   and select(poles, cfg, limit)['reason'] == reason)
            for name, poles, fixed, expected, reason in definitions}


def fixed_spectra(frames, fs_grid, artifacts, execute, *, orders=(), include_roots=False):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-golden-analysis.log')
    with TemporaryDirectory(prefix='f2-probe-', dir=artifacts) as directory:
        scratch = Path(directory)
        probe = build_upstream_probe(PROBE, scratch, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
        request = scratch / 'input.json'
        request.write_text(json.dumps([fs_grid.tolist(), [frame.tolist() for frame in frames]]))
        output = artifacts / 'upstream-envelopes.json'
        options = ['--roots'] if include_roots else []
        execute([str(probe), str(request), *options, *(str(p) for p in orders)], stdout=output)
    return base.read(output)


def spectrum_db(signal, fs, grid, sigma_hz):
    # 同じ標本と窓で、ゼロ詰めFFTと周波数ごとの直接和を計算する。
    step = grid[1] - grid[0]
    n_fft = int(fs / step)
    transform = np.fft.rfft(signal, n=n_fft)
    direct = np.exp(-2j * np.pi * grid[:, None] / fs * np.arange(signal.size)) @ signal
    power = np.abs(np.stack([transform, direct]))**2 / np.sum(signal**2)
    envelope = 10 * np.log10(gaussian_filter1d(power, sigma_hz / step, axis=1))
    return envelope[0], float(np.max(np.abs(envelope[0] - envelope[1])))


def strongest_peak(curve, grid, interval):
    indexes = [i for i in find_peaks(curve)[0] if interval[0] <= grid[i] <= interval[1]]
    if not indexes:
        return None
    best = max(indexes, key=lambda i: curve[i])
    return {'frequency_hz': float(grid[best]), 'level_db': float(curve[best])}


def summarize_peaks(curve, grid, settings, selected):
    low = strongest_peak(curve, grid, settings['low_peak_search_hz'])
    high = strongest_peak(curve, grid, settings['high_peak_search_hz'])
    return {'low': low, 'high': high,
            'high_minus_low_db': high['level_db'] - low['level_db'] if high and low else None,
            'high_to_candidate_distance_hz': abs(high['frequency_hz'] - selected[0]) if high and selected else None}


def observe(row, frame, fixed, fs, grid, cfg, settings):
    poles = fixed['poles']
    original = select(poles, cfg)
    alternate = select(poles, cfg, settings['candidate_f2_bandwidth_limit_hz'])
    fixed_pair = [original[k][0] for k in ('f1', 'f2')] if original['reason'] is None else None
    saved_error = base.max_error(row['prior_fixed']['poles'], poles)
    independent_error = base.max_error(row['observed']['poles'], poles)
    upstream_error = base.max_error(row['prior_fixed']['f1_f2_hz'], fixed_pair)
    selected_error = base.max_error(row['observed']['f1_f2_hz'], fixed_pair)
    coefficient_response = np.polynomial.polynomial.polyval(
        np.exp(-2j * np.pi * grid / fs), fixed['coefficients'])
    independent_lpc = 10 * np.log10(fixed['prediction_error'] / (abs(coefficient_response)**2 + 1e-30))
    fixed_lpc = np.array(fixed['lpc_envelope_db'])
    emphasized = np.r_[frame[0], frame[1:] - cfg['pre_emphasis'] * frame[:-1]]
    fft, fft_error = spectrum_db(emphasized * np.hamming(len(frame)), fs, grid, settings['gaussian_sigma_hz'])
    result = {key: value for key, value in row.items() if key not in ('observed', 'prior_fixed')}
    result.update(poles=poles, fixed=original, candidate=alternate, errors={
        'prior_poles_hz': saved_error, 'independent_poles_hz': independent_error,
        'prior_selection_hz': upstream_error, 'independent_selection_hz': selected_error,
        'lpc_envelope_db': float(np.max(np.abs(fixed_lpc - independent_lpc))),
        'fft_envelope_db': fft_error,
    }, lpc_peaks=summarize_peaks(fixed_lpc, grid, settings, alternate['f2']),
        periodogram_peaks=summarize_peaks(fft, grid, settings, alternate['f2']))
    return result, (fixed_lpc, fft)


def save_spectra(artifacts, grid, rows, curves):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(('word', 'center', 'frequency_hz', 'lpc_envelope_db', 'smoothed_periodogram_db'))
    for row, (lpc, fft) in zip(rows, curves, strict=True):
        writer.writerows((row['word'], row['center'], int(hz), float(a), float(b))
                         for hz, a, b in zip(grid, lpc, fft, strict=True))
    (artifacts / 'spectra.csv.gz').write_bytes(gzip.compress(output.getvalue().encode(), mtime=0))

    context = matplotlib.rc_context({'font.family': 'Hiragino Sans'})
    with context:
        fig = Figure(figsize=(8, 4.6), layout='constrained')
        FigureCanvasAgg(fig)
        axes = fig.subplots(2, sharex=True, sharey=True)
        middle = [(row, curves[i]) for i, row in enumerate(rows) if row['center'] == 0.5]
        for ax, (row, (lpc, fft)) in zip(axes, middle, strict=True):
            ax.plot(grid, lpc - lpc.max(), color='#204f85', label='LPC包絡')
            ax.plot(grid, fft - fft.max(), color='#4b7462', label='平滑化ピリオドグラム')
            fixed, alternate = row['fixed']['f2'], row['candidate']['f2']
            if fixed:
                ax.axvline(fixed[0], color='#a95529', linestyle='--', label='固定F2')
            if alternate:
                ax.axvline(alternate[0], color='#792f59', linestyle=':', label='帯域幅条件付きF2')
            ax.set(title=row['word'], xlim=(400, 3300), ylim=(-35, 1), ylabel='相対レベル (dB)')
            ax.grid(axis='x', alpha=0.2)
        axes[0].legend(loc='lower right', fontsize=8, ncol=2)
        axes[-1].set_xlabel('周波数 (Hz)')
        fig.savefig(artifacts / 'midpoint-envelopes.png', dpi=140)


def hypotheses(rows, cfg):
    seems = [r for r in rows if r['word'] == 'seems']
    plea = [r for r in rows if r['word'] == 'plea']
    supporting = [r['center'] for r in seems if (p := r['periodogram_peaks'])['high_minus_low_db'] is not None
                  and p['high_minus_low_db'] >= cfg['hypothesis_minimum_peak_difference_db']
                  and p['high_to_candidate_distance_hz'] is not None
                  and p['high_to_candidate_distance_hz'] <= cfg['hypothesis_peak_distance_hz']]
    return {'seems_selects_high_pole': all(r['fixed']['f2'] and 900 < r['fixed']['f2'][0] < 1100 and
                                          r['candidate']['f2'] and 2200 <= r['candidate']['f2'][0] <= 2400 for r in seems),
            'plea_keeps_f2': all(r['fixed']['f2'] == r['candidate']['f2'] for r in plea),
            'same_f1_and_coverage': all(r['fixed']['f1'] == r['candidate']['f1']
                                       and r['fixed']['reason'] == r['candidate']['reason'] for r in rows),
            'seems_periodogram_support': len(supporting) >= cfg['hypothesis_minimum_supported_windows'],
            'supporting_centers': supporting}


def measure(case, cfg, paths, wave, artifacts, execute):
    fs, windows, frames = extract_frames(case, cfg, base.read(paths[1]), base.read(paths[2]), wave)
    settings = case['measurement']
    step = settings['spectrum_grid_hz']
    grid = np.arange(0, fs / 2 + step, step)
    reference = fixed_spectra(frames, grid, artifacts, execute)
    rows, curves = zip(*(observe(row, frame, fixed, fs, grid, cfg, settings)
                         for row, frame, fixed in zip(windows, frames, reference, strict=True)), strict=True)
    save_spectra(artifacts, grid, rows, curves)
    errors = [row['errors'] for row in rows]
    limit_control = controls(cfg, settings['candidate_f2_bandwidth_limit_hz'])
    accuracy = {'pole_and_selection': all(value is not None and value <= settings['pole_tolerance_hz']
                                         for row in errors for key, value in row.items() if key.endswith('_hz')),
                'lpc_envelope': all(row['lpc_envelope_db'] <= settings['lpc_envelope_tolerance_db'] for row in errors),
                'independent_periodogram': all(row['fft_envelope_db'] <= settings['periodogram_direct_dft_tolerance_db']
                                               for row in errors), **limit_control}
    maximum = {key: max((e[key] for e in errors if e[key] is not None), default=None) for key in errors[0]}
    return {'checks': accuracy, 'hypotheses': hypotheses(rows, settings), 'maximum_errors': maximum, 'windows': rows,
            'libraries': {'scipy': scipy.__version__, 'matplotlib': matplotlib.__version__}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = base.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('上流の作業ツリーが登録済みの固定版と一致しません')
    cfg, paths, registered, alignment, wave = load_sources(case)
    sources = [CASE, Path(__file__).resolve(), PROBE, *paths, registered, alignment, wave,
               WORKSPACE / 'tools/measure_tsp_stressed_vowel_formants.py',
               WORKSPACE / 'tools/measure_fan_crossing_allocations.py',
               WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/upstream_baseline.py',
               UPSTREAM / base.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
               UPSTREAM / 'crates/chimera/tests/golden_analysis.rs', UPSTREAM / 'Cargo.lock']
    return record_measurement(args.run_id, CASE, sources, {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'reference_run': case['baseline']['run'],
    }, lambda artifacts, execute: measure(case, cfg, paths, wave, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
