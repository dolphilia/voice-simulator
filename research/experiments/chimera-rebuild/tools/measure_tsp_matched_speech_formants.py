"""音源をそろえた合成を、保存したMFA境界と共通窓で再計測する。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-matched-speech-formants.json'
ROUTES = {
    'same_window': ('upstream', 'candidate_common'),
    'saved_mfa_windows': ('upstream', 'candidate'),
    'window_only': ('candidate_common', 'candidate'),
    'waveform_only': ('prior_candidate', 'candidate'),
}


def source_data(case, archive, paths, directory):
    adjusted = deepcopy(archive)
    pcm_matches = {}
    rate = case['measurement']['sample_rate_hz']
    with np.load(paths, allow_pickle=False) as matched:
        for uid, row in adjusted.items():
            wave = directory / f'{uid}-matched.wav'
            reference_rate, archived_upper = wavfile.read(row['source']['upstream']['wave'])
            candidate_rate, archived_candidate = wavfile.read(row['source']['candidate']['wave'])
            upper = matched[f'{uid}_upstream']
            candidate = matched[f'{uid}_candidate']
            if (reference_rate != rate or candidate_rate != rate or not bit_equal(upper, archived_upper)
                    or candidate.dtype != np.float32 or candidate.shape != archived_candidate.shape
                    or not np.isfinite(candidate).all()):
                raise ValueError(f'設定合わせ後のPCMを登録済み波形へ照合できません ({uid})')
            pcm_matches[uid] = {'upstream_same_bits': True, 'candidate_frames': len(candidate),
                                'max_candidate_minus_upstream': float(np.max(abs(candidate.astype(float) - upper)))}
            # 録音と固定上流は保存済みの実体を参照し、研究版だけをWAVに戻す。
            wavfile.write(wave, rate, candidate)
            row['source']['candidate']['wave'] = wave
            row['source']['candidate_common'] = row['source']['upstream'] | {'wave': wave}
            for token in row['tokens']:
                token['candidate_common'] = token['upstream']
    return adjusted, pcm_matches


def comparable_poles(row, python_comparison):
    axial = [matched['fixed_pole_hz'] for matched in python_comparison['nyquist_axis_matches']]
    remaining = []
    for pole in row['poles']:
        if pole in axial:
            axial.remove(pole)
        else:
            remaining.append(pole)
    return remaining


def compare_row(left, right, left_python, right_python, cfg):
    limit = cfg['frequency_bandwidth_agreement_hz']
    a = comparable_poles(left, left_python)
    b = comparable_poles(right, right_python)
    comparable_error = tsp.max_error(a, b)
    pair_error = tsp.max_error(left['f1_f2_hz'], right['f1_f2_hz'])
    rank = []
    for row, poles in ((left, a), (right, b)):
        described = tsp.describe_f2_candidates(row | {'poles': poles}, cfg)
        rank.append([(p['selected_f1'], p['f2_rank'], p['f2_decision']) for p in described['poles']])
    start_delta = right['start_sample'] - left['start_sample']
    classification = {
        'window_start': start_delta == 0,
        'public_poles': comparable_error is not None and comparable_error <= limit,
        'selection': pair_error is not None and pair_error <= limit and left['reason'] == right['reason'] and rank[0] == rank[1],
    }
    pair = [left['f1_f2_hz'], right['f1_f2_hz']]
    return {
        'start_delta_samples': start_delta,
        'raw_public_pole_delta_hz': tsp.max_error(left['poles'], right['poles']),
        'public_pole_delta_hz': comparable_error, 'selection_delta_hz': pair_error,
        'same_candidate_order': rank[0] == rank[1],
        'missing_reasons': [left['reason'], right['reason']],
        'f2_hz': [values[1] if values is not None else None for values in pair],
        'first_different_stage': next((name for name, okay in classification.items() if not okay), None),
    }


def per_token_comparisons(current, current_fixed, previous, previous_fixed, cfg):
    pairs = {route: [] for route in ROUTES}
    medians = {route: [] for route in ROUTES}
    controls = {}
    for uid, tokens in current['tokens'].items():
        for index, observed in enumerate(tokens):
            local = observed | {'prior_candidate': previous['tokens'][uid][index]['candidate']}
            fixed = {voice: rows[index] for voice, rows in current_fixed[uid]['sources'].items()}
            before = {voice: rows[index] for voice, rows in previous_fixed[uid]['sources'].items()}
            fixed['prior_candidate'] = before['candidate']
            for voice in ('upstream', 'recording'):
                controls[f'{uid}/{index}/{voice}'] = fixed[voice] == before[voice]
            key = {'utterance': uid, 'token_index': index, 'word': observed['upstream']['word'], 'ipa': observed['ipa']}
            for route, (left, right) in ROUTES.items():
                base_pair, changed_pair = (fixed[voice]['baseline_hz'] for voice in (left, right))
                medians[route].append({**key, 'pair_hz': [base_pair, changed_pair],
                                       'max_delta_hz': None if None in base_pair + changed_pair else
                                       float(np.max(abs(np.asarray(base_pair) - changed_pair)))})
                values = zip(local[left]['windows'], fixed[left]['windows'], local[left]['window_comparison'],
                             fixed[right]['windows'], local[right]['window_comparison'], strict=True)
                for window, first, first_check, second, second_check in values:
                    pairs[route].append({**key, 'center': window['center'],
                                         **compare_row(first, second, first_check, second_check, cfg)})
    return pairs, medians, controls


def aggregate(rows, medians, cfg):
    gaps = [abs(b - a) for a, b in (row['f2_hz'] for row in rows) if a is not None and b is not None]
    window_changes = [row for row in rows if row['start_delta_samples']]
    f2_changes = [row for row in rows if (None in row['f2_hz'] and row['f2_hz'][0] != row['f2_hz'][1])
                  or (None not in row['f2_hz'] and
                      abs(row['f2_hz'][0] - row['f2_hz'][1]) > cfg['frequency_bandwidth_agreement_hz'])]
    pole_errors = [row['public_pole_delta_hz'] for row in rows if row['public_pole_delta_hz'] is not None]
    return {
        'windows': len(rows), 'different_starts': len(window_changes),
        'max_start_delta_samples': max(abs(row['start_delta_samples']) for row in rows),
        'different_candidate_orders': sum(not row['same_candidate_order'] for row in rows),
        'different_missing_reasons': sum(len(set(row['missing_reasons'])) > 1 for row in rows),
        'different_f2_selections': len(f2_changes), 'raw_public_pole_count_mismatches':
            sum(row['raw_public_pole_delta_hz'] is None for row in rows),
        'max_public_pole_delta_hz': max(pole_errors, default=None),
        'max_f2_delta_hz': max(gaps, default=None),
        'max_token_median_delta_hz': max((row['max_delta_hz'] for row in medians if row['max_delta_hz'] is not None), default=None),
        'first_different_stage_counts': {stage: sum(row['first_different_stage'] == stage for row in rows)
                                         for stage in ('window_start', 'public_poles', 'selection')},
        'first_f2_selection_change': f2_changes[0] if f2_changes else None,
    }


def reference_gap(case, current, fixed):
    target = case['recording_gap']
    uid, center = target['utterance'], target['center']
    index = next(i for i, row in enumerate(current['tokens'][uid]) if row['upstream']['word'] == target['word'])
    root = current['tokens'][uid][index]
    window = next(i for i, row in enumerate(root['upstream']['windows']) if row['center'] == center)
    f2 = {}
    window_start = {}
    for voice, rows in fixed[uid]['sources'].items():
        measurement = rows[index]['windows'][window]
        pair = measurement['f1_f2_hz']
        f2[voice] = None if pair is None else pair[1]
        window_start[voice] = measurement['start_sample']
    differences = {voice: value - f2['recording'] for voice, value in f2.items()
                   if voice != 'recording' and f2['recording'] is not None and value is not None}
    return {'f2_hz': f2, 'synth_minus_recording_hz': differences, 'start_samples': window_start, **target}


def measure(case, base, aligned, matched, before, out, execute):
    with TemporaryDirectory(prefix='matched-tsp-', dir=out.parent / 'tmp') as folder:
        data, pcm_matches = source_data(base, aligned, matched, Path(folder))
        evaluated = tsp.measure(base, data, out, execute, f2_candidates=True)
    fixed = tsp.read(out / 'upstream-formants.json')
    cfg = base['measurement']
    pairs, medians, controls = per_token_comparisons(evaluated, fixed, before['summary'], before['fixed'], cfg)
    aggregates = {route: aggregate(rows, medians[route], cfg) for route, rows in pairs.items()}
    gap = reference_gap(case, evaluated, fixed)
    counts = case['counts']
    common = aggregates['same_window']
    known_alignment = aggregates['window_only']
    checks = {
        **evaluated['checks'],
        'registered_window_coverage': len(data) == counts['utterances']
            and sum(len(row['tokens']) for row in data.values()) == counts['vowels']
            and all(len(rows) == counts['vowels'] * counts['centers'] for rows in pairs.values()),
        'unchanged_recording_and_upstream_measurements': all(controls.values()),
        'same_pcm_samples_for_upstream': all(row['upstream_same_bits'] for row in pcm_matches.values()),
    }
    synth = gap['f2_hz']['upstream'], gap['f2_hz']['candidate_common']
    predictions = {
        'shared_windows_agree_after_matching_pcm': all(row['first_different_stage'] is None for row in pairs['same_window'])
            and all(row['max_delta_hz'] is not None and row['max_delta_hz'] <= cfg['frequency_bandwidth_agreement_hz']
                    for row in medians['same_window']),
        'saved_boundary_offsets_remain_visible': known_alignment['different_starts'] == counts['different_saved_window_starts']
            and known_alignment['different_f2_selections'] > 0,
        'seems_recording_gap_persists': None not in synth and abs(synth[0] - synth[1]) <= cfg['frequency_bandwidth_agreement_hz']
            and abs(gap['synth_minus_recording_hz'].get('upstream', 0)) >= gap['minimum_f2_difference_hz'],
    }
    (out / 'window-comparisons.json').write_text(json.dumps(
        {'windows': pairs, 'medians': medians}, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    return {'checks': checks, 'predictions': predictions, 'independent_comparison': evaluated['comparison'],
            'route_summary': aggregates, 'common_windows': common['windows'],
            'f2_recording_comparison': gap, 'pcm': pcm_matches}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline = tsp.open_run(case['reference'], revision)
    report = tsp.open_run(case['previous_report'], revision)
    pcm_run = tsp.open_run(case['matched_pcm'], revision)
    base, base_path = saved_case(baseline, tsp.CASE)
    before_paths = {key: tsp.verified_path(report, name) for key, name in
                    (('summary', 'summary.json'), ('fixed', 'artifacts/upstream-formants.json'))}
    baseline_fixed = tsp.verified_path(baseline, 'artifacts/upstream-formants.json')
    if sha256(before_paths['fixed']) != sha256(baseline_fixed):
        parser.error('先行の候補レポートと登録済み計測の固定出力が一致しません')
    alignment, render = (tsp.open_run(base[key], revision) for key in ('alignment', 'render'))
    aligned = tsp.load_inputs(base, alignment, render)
    matched = tsp.verified_path(pcm_run, 'artifacts/matched-pcm.npz')
    inputs = [CASE, Path(__file__).resolve(), base_path, matched, baseline_fixed, *before_paths.values(), tsp.PROBE,
              WORKSPACE / 'tools/measure_tsp_stressed_vowel_formants.py',
              WORKSPACE / 'tools/measure_duet_child_glottal_noise_origin.py',
              *(run[0] / 'manifest.json' for run in (baseline, report, pcm_run, alignment, render)),
              *((run[0] / 'summary.json') for run in (alignment, render)),
              *(values['wave'] for row in aligned.values() for values in row['source'].values()),
              *(UPSTREAM / name for name in (tsp.TSP_SOURCE, 'crates/chimera/src/analysis/lpc.rs',
                                             'crates/chimera-cli/src/main.rs', 'crates/chimera/tests/golden_analysis.rs'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, base, aligned, matched, {key: tsp.read(path) for key, path in before_paths.items()}, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
