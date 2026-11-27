"""TSPの共通母音で、録音と合成のF2の採択差を候補の段階まで追う。"""

import argparse
from collections import Counter
from itertools import product
from pathlib import Path
from statistics import median
import subprocess

import numpy as np

import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_lpc_order_recordings as recording_order
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-source-comparison.json'
VOICES = ('recording', 'upstream', 'candidate')


def reference_pair(selection):
    first, second = selection['f1'], selection['f2']
    return [first[0], second[0]] if first is not None and second is not None else None


def compare_bands(case, observed, cfg):
    eligible = recording_order.eligible_f2(observed['public_poles_hz'], observed['selected']['f1'], cfg)
    bands = {}
    for name, field in (('low', 'low_band_hz'), ('high', 'shared_high_band_hz')):
        lower, upper = case[field]
        bands[name] = {label: [pole for pole in poles if lower <= pole[0] <= upper]
                       for label, poles in (('raw', observed['raw_poles_hz']),
                                            ('public', observed['public_poles_hz']), ('eligible', eligible))}
        bands[name]['candidate_ranks'] = [i for i, pole in enumerate(eligible, 1)
                                          if lower <= pole[0] <= upper]
    return bands


def compare_pair(human, synth, cfg):
    low = synth['bands']['low']
    if not low['raw']:
        stage = 'pole_estimation'
    elif not low['public']:
        stage = 'public_pole_filter'
    elif not low['eligible']:
        stage = 'f1_or_f2_eligibility'
    else:
        stage = 'eligible'
    forced = recording_order.eligible_f2(synth['public_poles_hz'], human['selected']['f1'], cfg)
    forced_f2 = forced[0] if forced else None
    selected = [row['selected']['f2'] for row in (human, synth)]
    high = [next(iter(row['bands']['high']['eligible']), None) for row in (human, synth)]
    if None in [*selected, *high]:
        return {'synth_low_band_stage': stage, 'synth_f2_with_recording_f1_hz': forced_f2,
                'frequency_difference': None}
    recorded, synthetic = (p[0] for p in selected)
    recorded_high, synthetic_high = (p[0] for p in high)
    terms = {'selected_synth_minus_recording_hz': synthetic - recorded,
             'high_band_synth_minus_recording_hz': synthetic_high - recorded_high,
             'recording_high_minus_selected_hz': recorded_high - recorded,
             'synth_selected_minus_high_hz': synthetic - synthetic_high}
    reconstructed = (terms['high_band_synth_minus_recording_hz'] + terms['recording_high_minus_selected_hz']
                     + terms['synth_selected_minus_high_hz'])
    return {'synth_low_band_stage': stage, 'synth_f2_with_recording_f1_hz': forced_f2,
            'frequency_difference': {**terms, 'reconstruction_error_hz': abs(synthetic - recorded - reconstructed)}}


def measure(case, prior, cfg, source, fixed_path, report_path, summary_path, out, execute):
    target = case['target']
    uid = target['utterance']
    indexes = target['indexes']
    order = cfg['order'][uid[0]]
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(cfg['frame_seconds'] * rate)
    if rate != 12000 or order not in prior['orders'] or cfg['pre_emphasis'] != prior['pre_emphasis']:
        raise ValueError('固定上流の標本化、次数またはプリエンファシスと一致しません')
    fixed_source = tsp.read(fixed_path)[uid]['sources']
    trace = {(r['source'], r['center']): r for r in tsp.read(report_path)['windows']
             if r['utterance'] == uid and r['phone_index'] == indexes.get(r['source'])}
    summary, = (row for row in tsp.read(summary_path)['tokens'][uid] if row['indexes'] == indexes)
    frames, metadata = [], []
    centers = case['centers']
    reference_centers = cfg['reference_centers']
    for voice in VOICES:
        spec = source[voice]
        a, b, _ = spec['phones'][indexes[voice]]
        archive, = (row for row in fixed_source[voice] if row['index'] == indexes[voice])
        wave = tsp.filtered_wave(spec['wave'], voice, cfg)
        if summary[voice]['word'] != target['word'] or summary['ipa'] != target['ipa'] or summary[voice]['interval'][:2] != [a, b]:
            raise ValueError(f'保存済みの語・音素・時刻と一致しません ({voice})')
        for center, fixed in zip(centers, archive['windows'], strict=True):
            start = int((a + center * (b - a)) * rate) - length // 2
            observed = trace[voice, center]
            if not 0 <= start <= len(wave) - length or start != fixed['start_sample'] or start != observed['start_sample']:
                raise ValueError(f'保存済みの窓の標本位置と一致しません ({voice}/{center})')
            if observed['interval_seconds'] != [a, b] or observed['used_in_median'] != (center in reference_centers):
                raise ValueError(f'音素区間または中央値の集計条件が一致しません ({voice}/{center})')
            metadata.append((voice, center, fixed))
            frames.append(wave[start:start + length])
    np.savez_compressed(out / 'analysis-windows.npz', samples=np.stack(frames))
    probes = envelope.fixed_spectra(frames, np.empty(0), out, execute, orders=[order] * len(frames), include_roots=True)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')

    rows = {}
    pole_limit = cfg['frequency_bandwidth_agreement_hz']
    archived_matches = []
    for (voice, center, saved), frame, probe in zip(metadata, frames, probes, strict=True):
        current = recording_order.observe(frame, rate, order, probe, cfg)
        independent, negative = tsp.independent_poles(frame, rate, order, cfg)
        _, pole_error, axes = tsp.compare_poles({'poles': independent, 'negative_real_roots': negative}, saved, cfg)
        pair = reference_pair(current['selected'])
        pair_error = tsp.max_error(pair, saved['f1_f2_hz'])
        saved_poles = [[p['frequency_hz'], p['bandwidth_hz']] for p in trace[voice, center]['poles']]
        archived_matches.append(pole_error is not None and pole_error <= pole_limit
                                and pair_error is not None and pair_error <= pole_limit and saved_poles == saved['poles'])
        rows[voice, center] = {'source': voice, 'center': center, 'start_sample': saved['start_sample'],
                               'outside_phone_ms': trace[voice, center]['outside_phone_ms'], **current,
                               'bands': compare_bands(case, current, cfg),
                               'saved_probe_agreement_hz': {'poles': pole_error, 'selection': pair_error},
                               'saved_probe_nyquist_matches': axes}

    comparison = [{'source': voice, 'center': center,
                   **compare_pair(rows['recording', center], rows[voice, center], cfg)}
                  for voice, center in product(VOICES[1:], centers)]
    baseline = [r for r in comparison if r['center'] in reference_centers]
    medians, median_matches = {}, []
    for voice in VOICES:
        base = [rows[voice, q] for q in reference_centers]
        selected_values = [r['selected']['f2'][0] for r in base if r['selected']['f2'] is not None]
        high_values = [r['bands']['high']['eligible'][0][0] for r in base if r['bands']['high']['eligible']]
        selected = median(selected_values) if selected_values else None
        high = median(high_values) if high_values else None
        expected = summary[voice]['baseline_hz'][1]
        median_matches.append((selected is None and expected is None)
                              or (selected is not None and expected is not None and abs(selected - expected) <= pole_limit))
        medians[voice] = {'selected_hz': selected, 'high_band_hz': high, 'selected_windows': len(selected_values),
                          'high_band_windows': len(high_values)}

    checks = {
        'registered_windows_are_finite': len(rows) == len(VOICES) * len(centers)
            and all(len(frame) == length and np.isfinite(frame).all() for frame in frames),
        'matches_archived_tsp_poles_selections_and_medians': all(archived_matches) and all(median_matches),
        'independent_roots_public_poles_and_selection': all(
            row['raw_complex_max_distance'] <= prior['raw_complex_distance_tolerance']
            and row['errors_hz']['raw'] <= prior['raw_root_comparison_hz']
            and all(row['errors_hz'][name] is not None and row['errors_hz'][name] <= pole_limit
                    for name in ('public', 'public_filter', 'selected')) for row in rows.values()),
        'frequency_difference_decomposition': bool(comparison) and all(
            r['frequency_difference'] is not None
            and r['frequency_difference']['reconstruction_error_hz'] <= case['decomposition_tolerance_hz'] for r in comparison),
    }
    predictions = {
        'large_reference_center_differences_follow_candidate_order': all(
            r['frequency_difference'] is not None
            and r['frequency_difference']['selected_synth_minus_recording_hz'] >= case['large_selected_difference_hz']
            and abs(r['frequency_difference']['high_band_synth_minus_recording_hz']) <= case['high_band_delta_limit_hz']
            for r in baseline),
        'low_candidate_difference_is_before_f1_gap': all(
            bool(rows['recording', r['center']]['bands']['low']['eligible'])
            and r['synth_low_band_stage'] in ('pole_estimation', 'public_pole_filter')
            and r['synth_f2_with_recording_f1_hz'] == rows[r['source'], r['center']]['selected']['f2']
            for r in baseline),
        'at_least_one_synth_window_has_no_low_raw_pole':
            any(r['synth_low_band_stage'] == 'pole_estimation' for r in baseline),
    }
    return {'checks': checks, 'predictions': predictions, 'token_medians': medians, 'comparisons': comparison,
            'reference_center_low_band_stages': dict(Counter(r['synth_low_band_stage'] for r in baseline)),
            'windows': list(rows.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archived = tsp.open_run(case['diagnostic'], revision)
    prior = tsp.open_run(case['order_reference'], revision)
    definition, cfg_path = saved_case(archived, tsp.CASE)
    tolerances, tolerance_path = saved_case(prior, recording_order.CASE)
    alignment, render = (tsp.open_run(definition[name], revision) for name in ('alignment', 'render'))
    uid = case['target']['utterance']
    data = tsp.load_inputs({**definition, 'recording_ids': [uid]}, alignment, render)[uid]['source']
    input_root = WORKSPACE.parents[2]
    waves = [data[voice]['wave'] for voice in VOICES]
    previous = {entry['path']: entry['sha256'] for entry in archived[1]['inputs']}
    if any(previous.get(path.relative_to(input_root).as_posix()) != sha256(path) for path in waves):
        parser.error('録音または合成のWAVが先行の評価と一致しません')
    paths = [tsp.verified_path(archived, name) for name in
             ('artifacts/upstream-formants.json', 'artifacts/f2-candidates.json', 'summary.json')]
    modules = ('measure_tsp_stressed_vowel_formants', 'measure_tsp_lpc_order_recordings', 'measure_tsp_f2_bandwidth_envelope',
               'measure_tsp_f2_harmonic_bandwidth', 'measure_tsp_f2_bandwidth_held_out',
               'measure_fan_crossing_allocations', 'measure_uniform_tube', 'upstream_baseline')
    inputs = [CASE, Path(__file__).resolve(), cfg_path, tolerance_path, *waves, *paths, envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (archived, prior, alignment, render)),
              tsp.verified_path(alignment, 'summary.json'), tsp.verified_path(render, 'summary.json'),
              *(WORKSPACE / f'tools/{name}.py' for name in modules),
              UPSTREAM / tsp.TSP_SOURCE, UPSTREAM / 'crates/chimera/src/analysis/lpc.rs',
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, tolerances, definition['measurement'], data, *paths, out, execute),
        command=None, input_root=input_root)


if __name__ == '__main__':
    raise SystemExit(main())
