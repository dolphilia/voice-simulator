"""発話開始の予定時刻が飛んだ試行を、生PCMで無音と反復の候補に照合する。"""

import argparse
import sys
from pathlib import Path

import numpy as np

from inspect_firefox_cubeb_output import resolve_output_window
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import snapshot_case
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_io_deadline import rejoin
from measure_worklet_tsp_io_thread_state import trial_files
from measure_worklet_tsp_io_trace_instruments import inspect_joined_tap
from smooth_tap_marker import chip_values, fit_wave, waveform
from upstream_baseline import WORKSPACE


def fit(data, basis):
    residual, gain = fit_wave(data.ravel(), basis.ravel())
    return {'relative_rms_residual': residual, 'gain': gain}


def compare_component(ref, tap, start, stop, early, late, added, limits):
    frames = late - early
    local = tap[start + added:stop + added + frames]
    templates = {
        'zero': np.zeros(frames),
        'previous_block': ref[early - frames:early],
        'current_block': ref[early:late],
        'following_block': ref[late:late + frames],
    }
    models = {}
    for label, position in (('preceding_request', early), ('next_sample_position', late)):
        for name, values in templates.items():
            # 当該要求の複製はその前に置いても直後に置いても同じ波形になる。
            if name == 'current_block' and position == late:
                continue
            models[f'{name}/{label}'] = fit(local, np.r_[ref[start:position], values, ref[position:stop]])
    first, second, *_ = sorted(models, key=lambda name: models[name]['relative_rms_residual'])
    best = models[first]['relative_rms_residual']
    separated = models[second]['relative_rms_residual'] - best >= limits['minimum_residual_difference']
    selected = first if best <= limits['maximum_relative_residual'] and separated else None
    return {'models': models, 'selected': selected}


def compare_gap(reference, observed, gap, tap_start, added, limits, expected_common=None):
    frames = gap['sample_time_gap_frames']
    candidates = gap['candidate_pcm']
    early, late = (candidates[k]['tap_pcm_window'][0] - tap_start - added
                   for k in ('preceding_request', 'next_sample_position'))
    start, stop = gap['local_insertion_models']['reference_window']
    if late - early != frames or not 0 <= start <= early - frames < early < late < late + frames <= stop <= len(reference):
        raise ValueError('無音と反復の比較に必要な前後のPCMがそろっていません')
    if stop + added + frames > len(observed):
        raise ValueError('タップPCMの比較窓が収録範囲外です')

    ref_difference = (reference[:, 0] - reference[:, 1]) / 2
    tap_difference = (observed[:, 0] - observed[:, 1]) / 2
    difference = compare_component(ref_difference, tap_difference, start, stop, early, late, added, limits)

    stereo_ref = reference[early:late]
    blocks = {}
    for label in ('preceding_request', 'next_sample_position'):
        left, right = candidates[label]['tap_pcm_window']
        chunk = observed[left - tap_start:right - tap_start]
        blocks[label] = fit(chunk, stereo_ref) | {
            'tap_pcm_window': [left, right],
            'in_phase_rms': float(np.sqrt(np.mean(np.mean(chunk, axis=1)**2))),
        }
    result = {'request_offset': gap['request_offset'], 'frames': frames, 'reference_window': [start, stop],
              'cubeb_block_in_window': [early, late], **difference, 'stereo_blocks': blocks,
              'current_cubeb_block_in_phase_rms': float(np.sqrt(np.mean(np.mean(stereo_ref, axis=1)**2))),
              'second_block_matches_device_write': any(
                  row['tap_pcm_window'] == blocks['next_sample_position']['tap_pcm_window'] for row in gap['server_pcm'])}
    if expected_common is not None:
        ref_common = np.mean(reference, axis=1)
        tap_common = np.mean(observed, axis=1)
        common = compare_component(ref_common, tap_common, start, stop, early, late, added, limits)
        common['registered_signal_fit'] = fit(ref_common[early:late], expected_common[early:late])
        for block in blocks.values():
            left, right = block['tap_pcm_window']
            block['in_phase_fit'] = fit(tap_common[left - tap_start:right - tap_start], ref_common[early:late])
        result['in_phase_comparison'] = common
    return result


def examine(capture, trial, cubeb_file, tap_file, case):
    core = capture['device']
    stream, = core['matched_streams']
    cubeb_start, cubeb_end = core['streams'][stream]['pcm']['tap_window']
    tap = trial['tap_pcm']
    tap_start, tap_end = tap['pcm']['tap_window']
    reference = np.fromfile(cubeb_file, dtype='<f4').reshape(-1, 2)[cubeb_start:cubeb_end].astype(float)
    observed = np.fromfile(tap_file, dtype='<f4').reshape(-1, 2)[tap_start:tap_end].astype(float)
    gaps = tap['gaps']
    if len(observed) - len(reference) != sum(g['sample_time_gap_frames'] for g in gaps):
        raise ValueError('PCMの増分とcubebの予定位置の飛びが一致しません')
    onset = {g['offset']: g for g in trial['covered_onset_gaps']}
    common = case['tap'].get('in_phase_marker')
    expected_common = None
    if common:
        start = core['graph_marker_window'][0]
        fraction = core['streams'][stream]['pcm']['anchors'][0]['fraction']
        expected_common = waveform(chip_values(common), common, start + np.arange(len(reference)) + fraction)
    added = 0
    reports = []
    for gap in gaps:
        offset = gap['request_offset']
        if offset in onset:
            reports.append(onset[offset] | compare_gap(
                reference, observed, gap, tap_start, added, case['local_pcm'], expected_common))
        added += gap['sample_time_gap_frames']
    return reports


def trim_anchor(raw, trial, files, case, frames):
    core = raw['device']
    stream, = core['matched_streams']
    layout = core['streams'][stream]
    start, stop = core['graph_marker_window']
    start += frames
    if start >= stop:
        raise ValueError('補足で使う先行音の開始位置が収録範囲外です')
    marker = read(files['marker-settings.json'])
    cubeb = np.fromfile(files['cubeb_pcm'], dtype='<f4').reshape(-1, 2)
    aligned = resolve_output_window(cubeb, marker, case['tap'], start, stop - 1)
    if not aligned['valid']:
        return raw, trial, {'reason': 'trimmed_cubeb_anchor_unverified'}
    moved = core | {'graph_marker_window': [start, stop],
                    'streams': core['streams'] | {stream: layout | {'pcm': aligned}}}
    bounds = case['comparison']['local_onset_offsets'] if trial['alignment_scope'] == 'onset' else None
    offsets = range(bounds[0], bounds[1] + 1) if bounds else (g['offset'] for g in core['graph_rows'])
    indices = {offset: index for index, offset in enumerate(offsets)}
    joined = rejoin(stream, core, raw['system_io'], core['host_tick_ms'] * 1e6,
                    case['system_io'], files, offset_bounds=bounds)
    capture = raw | {'device': moved}
    checks, tap = inspect_joined_tap(capture, files, case, joined, indices)
    inspection = {'checks': checks, 'graph_marker_window': [start, stop],
                  'cubeb_pcm_window': aligned['tap_window'], 'tap': tap}
    if all(checks.values()):
        return capture, trial | {'tap_pcm': tap}, inspection
    return raw, trial, inspection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('capture_run')
    parser.add_argument('io_analysis')
    parser.add_argument('--trim-invalid-anchor', type=int,
                        help='登録済みのタップ窓が不成立だった試行の前端を指定フレーム数短くする')
    args = parser.parse_args()
    capture = WORKSPACE / 'runs' / args.capture_run
    analysis = WORKSPACE / 'runs' / args.io_analysis
    source_manifest = read(capture / 'manifest.json')
    analysis_manifest = read(analysis / 'manifest.json')
    case_id = source_manifest['case_id']
    if (analysis_manifest.get('capture_run'), analysis_manifest['case_id'], analysis_manifest['upstream_revision']) != (
            args.capture_run, case_id, source_manifest['upstream_revision']):
        parser.error('同じ収録の音声I/O解析を指定してください')
    source = verified_file(capture, source_manifest, 'summary.json')
    evidence = verified_file(analysis, analysis_manifest, 'summary.json')
    case_path = WORKSPACE / 'cases' / f'{case_id}.json'
    snapshot = snapshot_case((capture, source_manifest), case_id)
    case = read(snapshot)
    if read(case_path) != case:
        parser.error('登録された収録とケースが一致しません')
    inputs = [case_path, snapshot, source, evidence, capture / 'manifest.json', analysis / 'manifest.json',
              Path(__file__).resolve(), WORKSPACE / 'tools/smooth_tap_marker.py', WORKSPACE / 'tools/measure_uniform_tube.py']
    trim = args.trim_invalid_anchor
    if trim is not None:
        if trim <= 0 or trim % 256 != 0:
            parser.error('補足の前端移動は256フレーム単位の正の値を指定してください')
        tap = case['tap']
        calibration = WORKSPACE / 'runs' / tap['calibration_run']
        cal_manifest = read(calibration / 'manifest.json')
        cal_case = verified_file(calibration, cal_manifest, 'artifacts/effective-case.json')
        tap.update(smooth_alignment=read(cal_case), local_pcm=case['local_pcm'])
        inputs.extend([calibration / 'manifest.json', cal_case])
        inputs.extend(WORKSPACE / 'tools' / name for name in (
            'inspect_firefox_cubeb_output.py', 'measure_worklet_tsp_io_deadline.py',
            'measure_worklet_tsp_io_thread_state.py', 'measure_worklet_tsp_io_trace_instruments.py',
            'measure_worklet_tsp_device_io.py', 'measure_worklet_tsp_device_tap.py', 'measure_cubeb_output_callback.py'))
    data = []
    for raw, trial in zip(read(source)['trials'], read(evidence)['trials'], strict=True):
        label = trial['pair'], trial['condition']
        if label != (raw['pair'], raw['condition']):
            parser.error('タップの試行識別子が一致しません')
        if not trial.get('joint_onset_covered') or not trial['covered_onset_gaps']:
            continue
        recover = trim is not None and trial['tap_pcm'].get('reason') == 'tap_window_unverified'
        if not trial['tap_pcm'].get('valid') and not recover:
            continue
        prefix = f'artifacts/{label[0]}-{label[1]}'
        stream, = raw['device']['matched_streams']
        cubeb = verified_file(capture, source_manifest, f'{prefix}/{stream}/pcm.f32le')
        tape = verified_file(capture, source_manifest, f'{prefix}/tap.f32le')
        inputs.extend((cubeb, tape))
        files = None
        if recover:
            files = trial_files((capture, source_manifest), raw)
            files.update({name: verified_file(capture, source_manifest, f'{prefix}/{name}')
                          for name in ('marker-settings.json', 'tap.json', 'trace-release.json')})
            files['cubeb_pcm'] = cubeb
            files['tap.f32le'] = tape
            inputs.extend(files.values())
        data.append((raw, trial, cubeb, tape, files))

    def measure(out, execute):
        events, inspections = [], []
        for raw, trial, cubeb, tape, files in data:
            if files is not None:
                raw, trial, inspection = trim_anchor(raw, trial, files, case, trim)
                inspections.append({'trial': trial['pair'], **inspection})
            if trial['tap_pcm'].get('valid'):
                events.extend(event | {'trial': trial['pair'], 'condition': trial['condition']}
                              for event in examine(raw, trial, cubeb, tape, case))
        checks = {'matched_onset_pcm_available': bool(events)}
        if case['tap'].get('in_phase_marker'):
            checks['registered_in_phase_marker'] = bool(events) and all(
                event['in_phase_comparison']['registered_signal_fit']['relative_rms_residual']
                <= case['local_pcm']['maximum_relative_residual'] for event in events)
        result = {'checks': checks, 'analysis_kind': 'exploratory',
                  'events': events, 'within_budget_count': sum(event['within_budget'] for event in events)}
        if trim is not None:
            result['anchor_inspection'] = {'trimmed_start_frames': trim, 'trials': inspections}
        return result

    details = {'case_id': case_id, 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'capture_run': args.capture_run, 'io_analysis': args.io_analysis,
               'analysis_command': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, case_path, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
