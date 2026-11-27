"""againの3注釈窓でプリエンファシスによるF2採択の差を照合する。"""

import argparse
from collections import Counter
from pathlib import Path
from statistics import median
import subprocess
import wave

import numpy as np

import measure_tsp_f2_annotation_w06_pre_emphasis as w06
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_lpc_lag_window as lag
import measure_tsp_lpc_pre_emphasis as pre
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-annotation-again-pre-emphasis.json'


def classification(change, cfg):
    old = change['root_matches'].get('f2')
    if old is None:
        return 'recovered_selection'
    freq, bandwidth = old['next_pole_hz']
    if old['next_chosen_as'] == 'f1':
        return 'previous_f2_becomes_f1'
    if old['next_chosen_as'] == 'f2':
        return 'same_pole_crosses_band'
    if not old['next_public']:
        if old['next_root_imag'] <= 0:
            return 'pole_leaves_upper_plane'
        if bandwidth > cfg['pole_max_bandwidth_hz']:
            return 'public_bandwidth'
        return 'public_frequency'
    f1 = change['selections'][1]['f1']
    if f1 is None:
        return 'no_f1'
    if freq <= f1[0] + cfg['f2_min_gap_hz']:
        return 'f2_gap'
    return 'f2_frequency_or_priority'


def medians_for_token(settings, coefficients, rows):
    medians = []
    for k, coefficient in enumerate(coefficients):
        selected = [windows[k]['selected']['f2'] for windows in rows.values()]
        f2s = [pole[0] for pole in selected if pole is not None]
        f2 = median(f2s) if f2s else None
        band = w06.selected_band({'f2': [f2] if f2 is not None else None, 'reason': 'no_f2'}, settings)
        medians.append({'coefficient': coefficient, 'f2_hz': f2, 'support': len(f2s), 'band': band})
    return medians


def verify_packet_window(trial, recording, clip, cfg):
    rate = trial['sample_rate_hz']
    first, count = trial['clip_start_sample'], trial['clip_frames']
    with wave.open(str(recording), 'rb') as source, wave.open(str(clip), 'rb') as reviewed:
        source.setpos(first)
        pcm_matches = (source.getparams()[:3] == reviewed.getparams()[:3] == (1, 2, rate)
                       and reviewed.getnframes() == count and source.readframes(count) == reviewed.readframes(count))
    focus = [(sample * cfg['decimation'] - first) * 1000 / rate for sample in trial['analysis_samples']]
    return (pcm_matches and sha256(clip) == trial['wave_sha256']
            and tsp.max_error(focus, trial['focus_ms']) <= 1e-9)


def measure(case, cfg, limits, paths, out, execute):
    settings = case['measurement']
    targets, center = settings['target_trials'], settings['center_trial']
    rate, order = settings['sample_rate_hz'], settings['order']
    if (rate != cfg['sample_rate_hz'] / cfg['decimation'] or order != cfg['order'][settings['utterance'][0]]
            or settings['frame_length'] != int(cfg['frame_seconds'] * rate)):
        raise ValueError('解析レート・LPC次数・窓長が基準と一致しません')
    packet = tsp.read(paths['packet'])
    trials = {name: packet['trials'][name] for name in [*targets, center]}
    center_summary = tsp.read(paths['center_summary'])
    lo = tsp.filtered_wave(paths['recording'], 'recording', cfg)
    frames = {name: lo[trial['analysis_samples'][0]:trial['analysis_samples'][1]] for name, trial in trials.items()}
    saved_frame = np.load(paths['center_frame'], allow_pickle=False)
    expected_identity = ('recording', settings['utterance'], settings['word'])
    matches = all((t['kind'], t['utterance'], t['word']) == expected_identity for t in trials.values())
    aligned = tsp.read(paths['alignment_summary'])['intervals'][settings['utterance']]['phones']
    interval = trials[center]['phone_seconds']
    if [*interval, 'EH1'] not in aligned or any(t['phone_seconds'] != interval for t in trials.values()):
        raise ValueError('注釈窓の母音区間が保存済み整列と一致しません')
    positions = all(
        t['analysis_samples'][0] == int((interval[0] + t['center'] * (interval[1] - interval[0])) * rate)
        - settings['frame_length'] // 2 for t in trials.values())
    if not positions or any(x.shape != (settings['frame_length'],) or not np.isfinite(x).all() for x in frames.values()):
        raise ValueError('注釈窓の開始標本または長さが登録値と違います')
    np.savez_compressed(out / 'frames.npz', **frames)
    coefficients, options = w06.coefficient_options(settings, cfg)
    raw = pre.run_probes([(frames[name], order) for name in targets], rate, np.empty(0), out, execute, coefficients=options)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    rows = {name: w06.sweep_rows(settings, cfg, limits, frames[name], trace)
            for name, trace in zip(targets, raw, strict=True)}
    transitions = {name: w06.transitions(settings, cfg, trace, rows[name])
                   for name, trace in zip(targets, raw, strict=True)}
    for entries in transitions.values():
        for entry in entries:
            entry['cause'] = classification(entry, cfg)
    median_rows = medians_for_token(settings, coefficients, rows | {center: center_summary['rows']})
    median_transitions = [[a['coefficient'], b['coefficient']]
                          for a, b in zip(median_rows, median_rows[1:]) if a['band'] != b['band']]
    switches = [row for row in transitions['W02'] if row['bands'] == ['low', 'high']]
    counts = {name: dict(Counter(row['band'] for row in data)) for name, data in rows.items()}
    return {
        'checks': {
            'packet_windows_and_pcm_match': matches and packet['packet_id'] == case['annotation']['packet_id']
                and all(verify_packet_window(trial, paths['recording'], paths[name], cfg)
                        for name, trial in trials.items()),
            'center_frame_and_grid_replayed': np.array_equal(frames[center], saved_frame)
                and center_summary['annotation']['packet_id'] == packet['packet_id']
                and center_summary['annotation']['trial'] == center
                and center_summary['annotation']['analysis_samples'] == trials[center]['analysis_samples']
                and [row['coefficient'] for row in center_summary['rows']] == coefficients,
            'registered_coefficients_and_default_option': all(
                [v['pre_emphasis_coefficient'] for v in trace] == coefficients
                and [v['pre_emphasis_option'] for v in trace] == options for trace in raw),
            'archived_endpoints_replayed': all(
                w06.archived_ends_match(trace, tsp.read(paths[f'{name}_endpoints']))
                and [rows[name][-1]['selected']['f2'][0], rows[name][0]['selected']['f2'][0]]
                == trials[name]['held_out_lpc_f2_hz'] for name, trace in zip(targets, raw, strict=True)),
            'preprocessing_coefficients_roots_and_selection_agree': all(
                v['first_difference'] is None for group in rows.values() for v in group),
        },
        'predictions': {
            'w07_stays_high': counts['W07'] == {'high': len(coefficients)},
            'w02_switches_low_to_high': bool(switches),
            'w02_low_pole_excluded_from_public_at_switch': bool(switches) and switches[0]['cause'] == 'public_bandwidth',
            'token_f2_median_switches_once': len(median_transitions) == 1
                and median_rows[0]['band'] == 'low' and median_rows[-1]['band'] == 'high',
        },
        'selection_counts': counts, 'transitions': transitions, 'rows': rows,
        'median_rows': median_rows, 'median_transitions': median_transitions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    center, packet, endpoints, reference = (tsp.open_run(case[key], revision)
                                            for key in ('center_reference', 'annotation', 'endpoints', 'baseline'))
    config, cfg_snapshot = saved_case(reference, tsp.CASE)
    endpoint_definition, endpoint_snapshot = saved_case(endpoints, CASE.with_name(case['endpoints']['case'] + '.json'))
    control = tsp.open_run(endpoint_definition['synthetic_control'], revision)
    limit_case, limit_snapshot = saved_case(control, pre.CASE)
    alignment = tsp.open_run(config['alignment'], revision)
    settings = case['measurement']
    uid = settings['utterance']
    paths = {key: tsp.verified_path(run, path) for key, run, path in (
        ('recording', alignment, f'artifacts/corpus/recording/{uid}/{uid}.wav'),
        ('alignment_summary', alignment, 'summary.json'), ('packet', packet, 'artifacts/reference.json'),
        ('center_frame', center, 'artifacts/frame.npy'), ('center_summary', center, 'summary.json'),
        ('endpoint_summary', endpoints, 'summary.json'))}
    trials = tsp.read(paths['packet'])['trials']
    endpoint_windows = tsp.read(paths['endpoint_summary'])['windows']
    for name in [*settings['target_trials'], settings['center_trial']]:
        paths[name] = tsp.verified_path(packet, f'artifacts/review/{name}.wav')
    for name in settings['target_trials']:
        trial = trials[name]
        index, = (i for i, row in enumerate(endpoint_windows)
                  if row['utterance'] == uid and row['word'] == settings['word']
                  and row['center'] == trial['center'] and row['start_sample'] == trial['analysis_samples'][0])
        paths[f'{name}_endpoints'] = tsp.verified_path(endpoints, f'artifacts/upstream-pre-emphasis-{index:02d}.json')
    sources = (tsp.TSP_SOURCE, lag.LPC, 'crates/chimera/tests/golden_analysis.rs')
    inputs = [
        CASE, Path(__file__).resolve(), pre.PROBE, cfg_snapshot, endpoint_snapshot, limit_snapshot, *paths.values(),
        *(run[0] / 'manifest.json' for run in (center, packet, endpoints, reference, alignment, control)),
        *(Path(module.__file__) for module in (tsp, w06, pre, lag)), *(UPSTREAM / name for name in sources),
    ]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    cfg = config['measurement']
    limits = pre.trace_limits(limit_case['measurement'], cfg)
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, cfg, limits, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
