"""44.1 kHzのプロセスタップの無音前後をcubebのPCMへ局所的に対応づける。"""

import argparse
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_44100_load_repeat import phase_channels
from smooth_tap_marker import fit_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-gap-edges.json'


def gain_fit(observed, reference):
    if not np.any(observed) or not np.any(reference):
        return {'residual': None, 'gain': None}
    residual, gain = fit_wave(observed, reference)
    return {'residual': residual, 'gain': gain}


def local_alignment(reference, observed, frames, nominal_lag, limits):
    side = 'out_of_phase'
    radius = limits['maximum_local_lag_frames']
    ranks = []
    for lag in range(nominal_lag - radius, nominal_lag + radius + 1):
        fit = gain_fit(observed[side][frames], reference[side][frames - lag])
        if fit['residual'] is not None and fit['gain'] > 0:
            ranks.append((fit['residual'], lag))
    if not ranks:
        return {'accepted': False, 'reason': '正のゲインで照合できる逆相信号がありません'}
    residual, best = min(ranks)
    other = min((score for score, lag in ranks if abs(lag - best) >= 2), default=None)
    margin = other - residual if other is not None else None
    valid = (residual <= limits['maximum_relative_residual'] and margin is not None
             and margin >= limits['minimum_other_lag_margin'])
    return {'best_lag_frames': best, 'accepted': valid, 'next_distinct_lag_margin': margin,
            'at_best_lag': {name: gain_fit(observed[name][frames], values[frames - best])
                            for name, values in reference.items()}}


def cross_gain(reference, observed, frames, lag, limits):
    values = np.column_stack([sig[frames - lag] for sig in reference.values()])
    output = np.column_stack([sig[frames] for sig in observed.values()])
    mask = np.min(np.abs(values), axis=1) >= limits['minimum_reference_amplitude']
    count = int(mask.sum())
    if count < limits['minimum_informative_frames']:
        return {'informative_frames': count, 'missing': '両成分の振幅が条件を満たす標本が不足'}
    values, output = values[mask], output[mask]
    ratios = output / values
    models = {}
    names = list(reference)
    for train, test in ((0, 1), (1, 0)):
        measured = output[:, test]
        if np.any(measured):
            predicted = ratios[:, train] * values[:, test]
            residual = float(np.linalg.norm(measured - predicted) / np.linalg.norm(measured))
        else:
            residual = None
        models[f'{names[train]}_to_{names[test]}'] = {
            'residual': residual, 'within_residual_limit': None if residual is None else residual <= limits['maximum_relative_residual'],
            'gain_minimum': float(ratios[:, train].min()),
            'gain_maximum': float(ratios[:, train].max())}
    return {'informative_frames': count, 'models': models}


def observe_side(reference, observed, edge, is_before, nominal_lag, limits):
    radius = limits['maximum_local_lag_frames']
    width = limits['window_frames']
    windows = []
    for distance in limits['distances_frames']:
        start = edge - distance - width if is_before else edge + distance
        frames = np.arange(start, start + width)
        if (start < 0 or start + width > len(observed['out_of_phase']) or start - nominal_lag - radius < 0
                or start + width - nominal_lag + radius > len(reference['out_of_phase'])):
            raise ValueError('境界の64フレーム窓とラグ探索に十分なPCMがありません')
        window = local_alignment(reference, observed, frames, nominal_lag, limits)
        windows.append({'distance_frames': distance, 'tap_frames': [start, start + width], **window})
    distances = limits.get('far_anchor_distances_frames', [windows[-1]['distance_frames']])
    far_frames = np.concatenate([np.arange(*window['tap_frames']) for window in windows
                                 if window['distance_frames'] in distances])
    far = local_alignment(reference, observed, far_frames, nominal_lag, limits)
    if not far['accepted']:
        return {'nominal_lag_frames': nominal_lag, 'windows': windows, 'far_lag_frames': None, 'far_alignment': far}
    lag = far['best_lag_frames']
    for window in windows:
        frames = np.arange(*window['tap_frames'])
        window['at_far_lag'] = {name: gain_fit(observed[name][frames], values[frames - lag])
                                for name, values in reference.items()}
    near_frames = np.arange(*windows[0]['tap_frames'])
    return {'nominal_lag_frames': nominal_lag, 'far_lag_frames': lag, 'windows': windows, 'far_alignment': far,
            'near_cross_gain_at_far_lag': cross_gain(reference, observed, near_frames, lag, limits)}


def read_stereo(path, window):
    data = np.fromfile(path, '<f4').reshape(-1, 2)[slice(*window)].astype(float)
    if len(data) != window[1] - window[0] or not np.isfinite(data).all():
        raise ValueError('PCM窓のフレーム数または有限値の条件が一致しません')
    return data


def measure_capture(group, summary, files, case):
    native, = (s for s in summary['cubeb_streams'] if s['valid'])
    cw, tw = native['marker']['tap_window'], summary['tap']['pcm']['tap_window']
    blocks = load_blocks(files['blocks.csv'].parent)
    raw = read_stereo(files['pcm.f32le'], cw)
    tap = read_stereo(files['tap.f32le'], tw)
    zero = np.all(tap == 0, axis=1)
    edges = np.flatnonzero(np.diff(np.r_[False, zero, False])).reshape(-1, 2).tolist()
    reference, observed = phase_channels(raw), phase_channels(tap)
    origin = summary['requests']['last_draw']['cubeb_index']
    limits = case['limits']
    gaps = {}
    for i, (row, after) in enumerate(zip(blocks, blocks[1:])):
        if cw[0] <= row['pcm_byte_offset'] // 8 and after['pcm_byte_offset'] // 8 < cw[1]:
            missing = after['sample_time'] - row['sample_time'] - row['frames']
            if missing != int(missing):
                raise ValueError('予定サンプル番号の飛びが整数ではありません')
            gaps[i] = int(missing)
    if len(tap) - len(raw) != sum(gaps.values()):
        raise ValueError('タップ窓の正味増加と予定サンプル番号の飛びが一致しません')
    records = []
    for offset, expected in zip(group['request_offsets'], group['expected_gaps'], strict=True):
        i = origin + offset
        row = blocks[i]
        gap = gaps[i]
        before = sum(n for j, n in gaps.items() if j < i)
        first = row['pcm_byte_offset'] // 8 - cw[0]
        if row['frames'] != case['request_frames'] or gap != expected:
            raise ValueError('登録された収録の要求幅または飛びが一致しません')
        target_start = first + before + limits['edge_offset_frames']
        target_end = target_start + gap + limits['trailing_boundary_extra_frames']
        spans = [span for span in edges if first + before <= span[0] < first + before + row['frames']]
        record = {'request_offset_from_load': offset, 'cubeb_index': i, 'gap_frames': gap,
                  'earlier_gap_frames': before, 'cubeb_request_start_frame': first,
                  'expected_edges_in_tap_window': [target_start, target_end], 'stereo_zero_spans': spans}
        if gap:
            record['edge_pattern_matches'] = spans == [[target_start, target_end]]
            if len(spans) != 1:
                record['missing'] = '対象要求内の完全ゼロ区間が一意に決まりません'
                records.append(record)
                continue
            start, end = spans[0]
        else:
            record['edge_pattern_matches'] = not spans
            start, end = target_start, target_end
        leading = observe_side(reference, observed, start, True, before, limits)
        trailing = observe_side(reference, observed, end, False, before + gap, limits)
        before_lag, after_lag = leading['far_lag_frames'], trailing['far_lag_frames']
        delta = None if before_lag is None or after_lag is None else after_lag - before_lag
        record.update(before=leading, after=trailing, far_lag_difference_frames=delta)
        records.append(record)
    return {'request_records': records, 'cubeb_window': cw, 'tap_window': tw,
            'all_stereo_zero_spans': edges, 'tap_growth_frames': len(tap) - len(raw)}


def score_events(results, case):
    limits = case['limits']
    maximum = limits['maximum_relative_residual']
    checks = {}
    near_changes = []
    for run, capture in results.items():
        for record in capture['request_records']:
            label = f"{run}/request-{record['cubeb_index']}"
            gap = record['gap_frames']
            checks[label + '/edge_pattern'] = record['edge_pattern_matches']
            delta = record.get('far_lag_difference_frames')
            far_matches = delta is not None and abs(delta - gap) <= limits['maximum_lag_difference_error_frames']
            sides = [record[key] for key in ('before', 'after')] if delta is not None else []
            far_matches = far_matches and all(
                abs(side['far_lag_frames'] - side['nominal_lag_frames']) <= limits['maximum_far_alignment_error_frames']
                for side in sides)
            checks[label + '/far_alignment'] = far_matches
            if not gap:
                checks[label + '/continuous_waveform'] = far_matches and all(
                    fit['residual'] is not None and fit['residual'] <= maximum
                    for side in sides for window in side['windows'] for fit in window['at_far_lag'].values())
            elif delta is not None:
                near_changes.extend(fit['residual'] is not None and fit['residual'] > maximum
                                    for side in sides for fit in side['windows'][0]['at_far_lag'].values())
    checks['near_boundary_difference_seen'] = any(near_changes)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case = read(CASE)
    inputs = [CASE, Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_worklet_tsp_44100_load_repeat.py', 'measure_cubeb_output_callback.py', 'smooth_tap_marker.py'))]
    registered = args.case.resolve()
    if registered != CASE:
        child = read(registered)
        distances = child['far_anchor_distances_frames']
        if (child['base_case'] != CASE.name or child['id'] != case['id'] or not distances
                or len(set(distances)) != len(distances) or not set(distances) <= set(case['limits']['distances_frames'])):
            parser.error('登録済みの窓を使う補足ケースを指定してください')
        case.update(revision=child['revision'])
        case['limits']['far_anchor_distances_frames'] = distances
        inputs.append(registered)
    captures = {}
    for group in case['capture_groups']:
        run = group['run']
        folder = WORKSPACE / 'runs' / run
        manifest = read(folder / 'manifest.json')
        required = (run, group['case_id'], group['case_revision'], case['upstream_revision'])
        if tuple(manifest[k] for k in ('run_id', 'case_id', 'case_revision', 'upstream_revision')) != required:
            parser.error('登録された収録の実行・ケース・版と一致しません')
        summary_path = verified_file(folder, manifest, 'summary.json')
        summary = read(summary_path)
        if not summary['checks'].get('tap_pcm_and_sample_clock'):
            parser.error('タップのPCMと時計を照合できた収録を指定してください')
        stream, = (row['stream'] for row in summary['cubeb_streams'] if row['valid'])
        files = {name: verified_file(folder, manifest, f'artifacts/cubeb/{stream}/{name}')
                 for name in ('blocks.csv', 'pcm.f32le')}
        files['tap.f32le'] = verified_file(folder, manifest, 'artifacts/tap.f32le')
        inputs.extend((folder / 'manifest.json', summary_path, *files.values()))
        captures[run] = (group, summary, files)

    def measure(out, execute):
        results = {run: measure_capture(group, summary, files, case) for run, (group, summary, files) in captures.items()}
        return {'checks': score_events(results, case), 'captures': results}

    metadata = {'case_id': case['id'], 'case_revision': case['revision'],
                'upstream_revision': case['upstream_revision'], 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, registered, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
