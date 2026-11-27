"""48 kHz歌唱の量子別の割り当てを、描画経路と声道更新の段階に照合する。"""

import argparse
import csv
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import bit_comparison, run_manifest, verified_path
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, UPSTREAM, WORKSPACE
from measure_worklet_realtime import read_quantum_allocations
from measure_speech_timing import read


CASE = WORKSPACE / 'cases/song-render-allocation-phases.json'
GEOMETRY = ('contour', 'contact_grid', 'area_profile', 'resample', 'clone_cells')


def saved_counts(path, spec):
    quantum = spec['quantum_frames']
    report = read_quantum_allocations(path, 'song_render_allocations=', spec['output_frames'], quantum, 32)
    counts = dict((row['output_frame'], row['count']) for row in report['nonzero_quanta'])
    return [counts.get(start, 0) for start in range(0, spec['output_frames'], quantum)]


def render_probe(folder, execute):
    execute(['env', f'CHIMERA_SONG_ALLOCATION_PROBE_OUTPUT={folder}', 'cargo', 'test', '--release', '--locked',
             '--offline', '-p', 'vocal-wasm', '--features', 'render-allocation-probe', '--lib',
             'tests::song_render_allocation_profile', '--', '--exact', '--nocapture'],
            stdout=folder / 'allocation-probe.log')


def compare_pcm_observations(folder, spec, baseline, browser_wave, browser_report):
    plain, traced = (np.fromfile(folder / f'{mode}.f32le', dtype='<f4') for mode in ('plain', 'traced'))
    rate, browser = wavfile.read(browser_wave)
    observations, traced_states = (np.fromfile(folder / f'{mode}-observations.f64le', dtype='<f8').reshape(-1, 23)
                                   for mode in ('plain', 'traced'))
    stride = spec['observation_stride_frames']
    frames = spec['output_frames']
    observed = np.asarray(browser_report['observations'], dtype='<f8')
    ends = np.minimum(np.arange(stride, frames + stride, stride), frames)
    checks = {
        'pcm_format_and_length': rate == spec['output_rate_hz'] and browser.dtype.kind == 'f'
                                 and browser.dtype.itemsize == 4 and browser.shape == (frames,)
                                 and plain.shape == traced.shape == (frames,),
        'pcm_is_finite': bool(all(np.isfinite(signal).all() for signal in (plain, traced, browser))),
        'pcm_probe_does_not_change_bits': plain.tobytes() == traced.tobytes(),
        'pcm_matches_live_browser': plain.tobytes() == browser.astype('<f4', copy=False).tobytes(),
        'all_native_observation_bits_match': bit_comparison(observations, traced_states)['different_values'] == 0,
        'native_observation_frames_match': bool(np.array_equal(observations[:, 0], ends)
            and np.array_equal(observed[:, 0], ends - 1)),
    }
    # 歌唱の画面が保存する12列の最後は声帯開大。
    report = bit_comparison(observations[:, :12], observed[:, 1:])
    checks['live_browser_observations_match'] = report['different_values'] == 0
    checks['baseline_cli_and_upstream_checks_passed'] = all(baseline['checks'].values())
    return checks, report


def analyze_phases(folder, spec, *, allocations_per_geometry_update=8):
    plain, traced = (read(folder / f'{mode}-counts.json') for mode in ('plain', 'traced'))
    columns = traced['phase_names']
    if traced['phase_names'] != plain['phase_names'] or len(set(columns)) != len(columns):
        raise ValueError('計測した段階の列が一致しません')
    total = traced['total_by_quantum']
    quantum = spec['quantum_frames']
    frames = spec['output_frames']
    control_frames = spec['control_output_frames']
    starts = range(0, frames, quantum)
    rows = []
    for index, (frame, count, stages) in enumerate(zip(starts, total, traced['phase_counts'], strict=True)):
        phases = dict(zip(columns, stages, strict=True))
        calls = {phase: item['calls'] for phase, item in phases.items()}
        counts = {phase: item['allocations'] for phase, item in phases.items()}
        geometry = counts['apply'] + counts['reapply']
        control_rest = counts['control'] - geometry - counts['turbulence'] - counts['begin_tract_block']
        rows.append({'quantum': index, 'output_frame': frame, 'output_frames': min(quantum, frames - frame),
                     'allocations': count, 'geometry_other': geometry - sum(counts[phase] for phase in GEOMETRY),
                     'control_other': control_rest, 'outside_control': count - counts['control'],
                     **{f'{phase}_calls': n for phase, n in calls.items()},
                     **{f'{phase}_allocations': n for phase, n in counts.items()}})
    checks = {
        'total_matches_without_probe_by_quantum': total == plain['total_by_quantum'],
        'probe_disabled_has_no_phase_counts': all(item['calls'] == item['allocations'] == 0
                                                 for row in plain['phase_counts'] for item in row),
        'phase_accounting_is_nonnegative': all(value >= 0 for row in rows for value in row.values()),
        'apply_and_control_follow_output_schedule': all(
            row['control_calls'] == row['apply_calls'] == row['begin_tract_block_calls']
            == (row['output_frames'] + control_frames - 1) // control_frames for row in rows),
        'geometry_calls_follow_apply_and_reapply': all(
            row[f'{phase}_calls'] == row['apply_calls'] + row['reapply_calls'] for row in rows for phase in GEOMETRY),
    }
    groups = {label: [row for row in rows if lo <= row['output_frame'] < hi]
              for label, (lo, hi) in spec['review_ranges'].items()}
    boundary = groups['word_boundary']
    half = 2 * allocations_per_geometry_update
    prediction = bool(len(boundary) == 25 and all(
        row['allocations'] == 2 * half and row['apply_allocations'] == row['reapply_allocations'] == half
        and row['apply_calls'] == row['reapply_calls'] == 2 for row in boundary))
    with (folder / 'allocations-by-quantum.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    return checks, {
        'allocations': sum(total),
        'quanta': len(rows),
        'phase_totals': {phase: {field: sum(row[f'{phase}_{field}'] for row in rows)
                                for field in ('calls', 'allocations')} for phase in columns},
        'residuals': {kind: {'total': sum(row[kind] for row in rows),
                             'quanta': [{'output_frame': row['output_frame'], 'count': row[kind]}
                                        for row in rows if row[kind]]}
                      for kind in ('geometry_other', 'control_other', 'outside_control')},
        'focus_ranges': {label: {'quanta': len(items),
                                 'allocations_by_quantum': sorted({row['allocations'] for row in items}),
                                 'apply_allocations_by_quantum': sorted({row['apply_allocations'] for row in items}),
                                 'reapply_allocations_by_quantum': sorted({row['reapply_allocations'] for row in items})}
                         for label, items in groups.items()},
        'word_boundary_prediction_matched': prediction,
    }, traced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    spec = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != spec['upstream_revision']
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    baseline = run_manifest(spec['baseline'], 'worklet-live-song', revision)
    historical = run_manifest(spec['historical_baseline'], 'worklet-live-song', revision)
    if any(record[1]['status'] != 'pass' for record in (baseline, historical)):
        parser.error('合格した通常の歌唱比較が必要です')
    files = [verified_path(baseline, name) for name in (
        'artifacts/native-allocations.log', 'artifacts/browser.wav', 'artifacts/browser.json', 'summary.json')]
    before_log, audio, browser, summary = files
    old_log = verified_path(historical, 'artifacts/native-allocations.log')
    native_case, song = (WORKSPACE / 'cases' / spec[key] for key in ('native_fixture', 'song_fixture'))
    settings = read(native_case)['measurement']
    fields = {'output_frames': 'output_frames', 'output_rate_hz': 'output_rate_hz', 'internal_rate_hz': 'internal_rate_hz',
              'observation_stride_frames': 'observation_stride_frames', 'quantum_frames': 'expected_render_quantum_frames'}
    if any(spec[key] != settings[field] for key, field in fields.items()):
        parser.error('ABIの歌唱条件が事前登録と一致しません')
    sources = [CASE, Path(__file__).resolve(), native_case, song, WORKSPACE / 'data/cmudict.txt.gz',
               WORKSPACE / 'tools/measure_fan_crossing_allocations.py', WORKSPACE / 'tools/measure_worklet_realtime.py',
               baseline[0] / 'manifest.json', historical[0] / 'manifest.json', *files, old_log, *candidate_sources()]
    details = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv]}
    baseline_counts = saved_counts(before_log, spec)
    old_counts = saved_counts(old_log, spec)

    def measure(folder, execute):
        render_probe(folder, execute)
        checks, result, report = analyze_phases(folder, spec)
        checks['native_total_matches_both_baselines_by_quantum'] = (
            report['total_by_quantum'] == baseline_counts == old_counts)
        observations, errors = compare_pcm_observations(folder, spec, read(summary), audio, read(browser))
        return result | {'checks': checks | observations, 'browser_observation_difference': errors}

    return record_measurement(args.run_id, CASE, sources, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
