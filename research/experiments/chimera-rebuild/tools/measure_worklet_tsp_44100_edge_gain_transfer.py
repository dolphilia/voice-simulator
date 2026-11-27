"""44.1 kHzのタップで、ある無音出口のゲインを固定して別の出口へ適用する。"""

import argparse
import csv
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_44100_gap_edges import read_stereo
from measure_worklet_tsp_44100_load_repeat import phase_channels
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-gap-edge-gain-transfer.json'


def slice_phases(path, window, edge, first, last):
    start, stop = edge + first, edge + last
    if not 0 <= start < stop <= window[1] - window[0]:
        raise ValueError('登録した解析窓が採取範囲にありません')
    absolute = [window[0] + start, window[0] + stop]
    pcm = read_stereo(path, absolute)
    return np.column_stack(tuple(phase_channels(pcm).values())), absolute


def shared_gain(reference, observed, minimum):
    power = np.sum(reference * reference, axis=1)
    joint = np.sum(reference * observed, axis=1)
    return np.divide(joint, power, out=np.full_like(power, np.nan), where=power >= minimum**2)


def stats(reference, predicted, positions, case):
    usable = np.isfinite(predicted)
    valid = reference[usable]
    error = (predicted - reference)[usable]
    peaks = np.flatnonzero(np.abs(error) > case['absolute_difference_limit'])
    norm = np.linalg.norm(valid)
    return {
        'frames': int(usable.sum()),
        'relative_residual': float(np.linalg.norm(error) / norm) if norm else None,
        'maximum_absolute_error': float(np.max(np.abs(error))) if len(error) else None,
        'first_above_absolute_limit': int(positions[usable][peaks[0]]) if len(peaks) else None,
        'last_above_absolute_limit': int(positions[usable][peaks[-1]]) if len(peaks) else None,
    }


def measure(out, selections, case):
    positions = np.arange(case['first_frame'], case['last_frame_exclusive'])
    edge = (0 <= positions) & (positions < case['fit_last_frame_exclusive'])
    calibration = selections[case['fit_selection']]
    minimum = case['minimum_reference_norm']
    template = np.ones(len(positions))
    template[edge] = shared_gain(calibration['cubeb'][edge], calibration['tap'][edge], minimum)
    names = ('in_phase', 'out_of_phase')
    summary = {}
    columns = ['selection', 'frame', 'fixed_gain', 'local_best_gain']
    columns.extend(f'{model}_{component}' for model in ('cubeb', 'tap', 'fixed', 'local_best') for component in names)
    with (out / 'edge-samples.csv').open('w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(columns)
        for key, event in selections.items():
            reference, tap = event['cubeb'], event['tap']
            local_best = shared_gain(reference, tap, minimum)
            # 事例ごとに再推定した係数は残差下限にだけ使う。
            models = {'unity': reference, 'fixed': reference * template[:, None],
                      'local_best': reference * local_best[:, None]}
            windows = {'whole': np.full(len(positions), True)}
            for window in case['windows']:
                windows[window['id']] = ((window['start_frame'] <= positions) &
                                         (positions < window['end_frame_exclusive']))
            errors = {}
            for window, within in windows.items():
                errors[window] = {model: {channel: stats(tap[within, i], predicted[within, i], positions[within], case)
                                          for i, channel in enumerate(names)}
                                  for model, predicted in models.items()}
            matrices = [reference, tap, models['fixed'], models['local_best']]
            for n, frame in enumerate(positions):
                values = [template[n], local_best[n], *(value for matrix in matrices for value in matrix[n])]
                writer.writerow([key, frame, *(value if np.isfinite(value) else '' for value in values)])
            summary[key] = {'capture_run': event['capture_run'], 'request_index': event['request_index'],
                            'gap_frames': event['gap_frames'], 'cubeb_read_frames': event['cubeb_read_frames'],
                            'tap_read_frames': event['tap_read_frames'], 'errors': errors}

    def fits(key, window, model, limit):
        values = (v['relative_residual'] for v in summary[key]['errors'][window][model].values())
        return all(value is not None and value <= limit for value in values)

    fit_replay = case['maximum_fit_replay_residual']
    limit = case['maximum_relative_residual']
    outside = ('before', 'after', 'far')
    controls = ('continuous_early', 'continuous_late')
    checks = {
        'fit_gain_defined_at_all_edge_frames': bool(np.isfinite(template[edge]).all()),
        'estimation_case_fits': fits('fit_292', 'edge', 'fixed', fit_replay),
        'same_waveform_replay_fits': fits('replay_308', 'edge', 'fixed', fit_replay),
        'same_waveform_replay_matches_pcm': all(np.array_equal(calibration[stream], selections['replay_308'][stream])
                                                for stream in ('cubeb', 'tap')),
        'edge_model_exceeds_limit_on_different_pcm': any(
            v['relative_residual'] is not None and v['relative_residual'] > limit
            for v in summary['different_316']['errors']['edge']['fixed'].values()),
        'controls_match_without_edge_gain': all(fits(key, 'whole', 'unity', limit) for key in controls),
        'controls_mismatch_with_edge_gain': all(not fits(key, 'edge', 'fixed', limit) for key in controls),
        'waveform_recovers_outside_edge': all(
            error['first_above_absolute_limit'] is None for event in summary.values() for w in outside
            for error in event['errors'][w]['unity'].values()),
    }
    usable = template[edge & np.isfinite(template)]
    bounds = [float(usable.min()), float(usable.max())] if len(usable) else None
    return {'checks': checks, 'training_selection': case['fit_selection'], 'training_gain_range': bounds,
            'training_gain_frames_defined': len(usable), 'captures': summary}


def zero_input_review(result, selections, case, review, original):
    positions = np.arange(case['first_frame'], case['last_frame_exclusive'])
    edge = (0 <= positions) & (positions < case['fit_last_frame_exclusive'])
    threshold = review['minimum_tap_signal_at_cubeb_zero']
    controls = review['control_for_gap']
    comparisons = {}
    checks = {'same_registered_transfer_measurement': result == original}
    for key, control_key in controls.items():
        event = selections[key]
        control = selections[control_key]
        checks[key + '/same_cubeb_as_control'] = bool(np.array_equal(event['cubeb'], control['cubeb']))
        checks[key + '/before_edge_is_silent'] = bool(np.all(event['tap'][positions < 0] == 0))
        zeros = (event['cubeb'] == 0) & edge[:, None]
        excess = np.abs(event['tap']) > threshold
        quiet = np.abs(control['tap']) <= threshold
        comparisons[key] = [
            {'frame': int(positions[frame]), 'component': ('in_phase', 'out_of_phase')[i],
             'tap': float(event['tap'][frame, i]), 'control_tap': float(control['tap'][frame, i]),
             'exceeds_control_floor': bool(excess[frame, i] and quiet[frame, i])}
            for frame, i in np.argwhere(zeros)
        ]
    checks['zero_input_disagrees_with_fixed_multiplication'] = any(
        row['exceeds_control_floor'] for rows in comparisons.values() for row in rows)
    checks['post_edge_matches_unscaled_cubeb'] = all(
        metric['first_above_absolute_limit'] is None
        for event in result['captures'].values() for window in ('after', 'far')
        for metric in event['errors'][window]['unity'].values())
    return {**result, 'checks': checks, 'registered_checks': result['checks'], 'zero_input_comparisons': comparisons}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case = read(CASE)
    registered = args.case.resolve()
    fixed = case['alignment']
    alignment_dir = WORKSPACE / 'runs' / fixed['run']
    alignment_manifest = read(alignment_dir / 'manifest.json')
    if (any(alignment_manifest[key] != fixed[key] for key in ('case_id', 'case_revision'))
            or alignment_manifest['run_id'] != fixed['run'] or alignment_manifest['status'] != 'pass'
            or alignment_manifest['upstream_revision'] != case['upstream_revision']):
        parser.error('固定したラグ検証の実行と一致しません')
    alignment_path = verified_file(alignment_dir, alignment_manifest, 'summary.json')
    alignment = read(alignment_path)
    inputs = [CASE, Path(__file__).resolve(), alignment_path, alignment_dir / 'manifest.json',
              WORKSPACE / 'tools/measure_worklet_tsp_44100_gap_edges.py',
              WORKSPACE / 'tools/measure_worklet_tsp_44100_load_repeat.py']
    review = original = None
    if registered != CASE:
        review = read(registered)
        if review['base_case'] != CASE.name or review['id'] != case['id']:
            parser.error('固定ゲインの元のケースと対応していません')
        original_dir = WORKSPACE / 'runs' / review['original_run']
        manifest_path = original_dir / 'manifest.json'
        saved = read(manifest_path)
        if (saved['run_id'] != review['original_run'] or
                saved['upstream_revision'] != case['upstream_revision'] or
                (saved['case_id'], saved['case_revision']) != (case['id'], case['revision'])):
            parser.error('固定ゲインの元の実行と一致しません')
        path = verified_file(original_dir, saved, 'summary.json')
        original = read(path)
        inputs.extend((registered, manifest_path, path))
    verified_hashes = {item['path']: item['sha256'] for item in alignment_manifest['inputs']}
    selections = {}
    for entry in case['selections']:
        capture_run = entry['capture_run']
        folder = WORKSPACE / 'runs' / capture_run
        manifest_path = folder / 'manifest.json'
        manifest = read(manifest_path)
        capture_path = verified_file(folder, manifest, 'summary.json')
        capture = read(capture_path)
        stream, = (s['stream'] for s in capture['cubeb_streams'] if s['valid'])
        cubeb_path = verified_file(folder, manifest, f'artifacts/cubeb/{stream}/pcm.f32le')
        tap_path = verified_file(folder, manifest, 'artifacts/tap.f32le')
        unchanged = [manifest_path, capture_path, cubeb_path, tap_path]
        if any(sha256(p) != verified_hashes.get(p.relative_to(ROOT).as_posix()) for p in unchanged):
            parser.error('ラグの検証で使った収録ファイルと一致しません')
        tape_path = verified_file(folder, manifest, 'artifacts/tap.json')
        format_path = verified_file(folder, manifest, f'artifacts/cubeb/{stream}/format.csv')
        with format_path.open(newline='') as f:
            rate, = csv.DictReader(f)
        if ({float(rate[key]) for key in ('stream_rate_hz', 'buffer_rate_hz')}
                != {case['sample_rate_hz']} or read(tape_path)['sampleRate'] != case['sample_rate_hz']):
            parser.error('登録したサンプルレートに対応しません')
        windows = alignment['captures'][capture_run]
        record, = (event for event in windows['request_records']
                   if event['request_offset_from_load'] == entry['request_offset'])
        side = record['after']
        near, = (window for window in side['windows'] if window['distance_frames'] == 0)
        edge = near['tap_frames'][0]
        lag = side['far_lag_frames']
        if lag is None or record['gap_frames'] != entry['gap_frames']:
            parser.error('保存済みのラグまたは予定番号の飛びが登録と一致しません')
        first, last = case['first_frame'], case['last_frame_exclusive']
        cubeb, cube_frames = slice_phases(cubeb_path, windows['cubeb_window'], edge - lag, first, last)
        tap, tap_frames = slice_phases(tap_path, windows['tap_window'], edge, first, last)
        selections[entry['id']] = {'cubeb': cubeb, 'tap': tap, 'capture_run': capture_run,
                                    'request_index': record['cubeb_index'], 'gap_frames': record['gap_frames'],
                                    'cubeb_read_frames': cube_frames, 'tap_read_frames': tap_frames}
        inputs.extend([*unchanged, tape_path, format_path])
    def perform(out, execute):
        result = measure(out, selections, case)
        return zero_input_review(result, selections, case, review, original) if review is not None else result

    details = {'case_id': case['id'], 'case_revision': (review or case)['revision'],
               'upstream_revision': case['upstream_revision'],
               'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, registered, inputs, details, perform, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
