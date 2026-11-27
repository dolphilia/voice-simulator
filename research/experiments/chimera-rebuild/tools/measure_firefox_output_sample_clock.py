"""44.1 kHzの欠測した時刻照合を機器とタップのサンプル時計で再解析する。"""

import argparse
from pathlib import Path
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_firefox_output_marker import CLIENT, HARDWARE, SERVER, longest_joint, trace_candidates
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_cubeb_output_callback import load_blocks
from inspect_firefox_cubeb_output import host_tick_ms
from smooth_tap_marker import chip_values, find_anchor, fit_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/firefox-process-tap-sample-clock-44100.json'


def measure(tables, spec, prior, case, calibration, tape, cubeb, tap, blocks):
    marker = next(row['marker'] for row in prior['cubeb_streams'] if row['valid'])
    tap_marker = prior['tap']['pcm']
    cw, tw = marker['tap_window'], tap_marker['tap_window']
    rate = case['sample_rate_hz']
    rows = trace_candidates(tables, blocks, tape, cw, tw, cubeb, tap,
                            prior['tap']['tap_minus_cubeb_host_time_at_window_ends_ms'],
                            case['trace'], host_tick_ms() * 1e6, rate)
    if rows != [{key: value for key, value in row.items() if key != 'matched'} for row in prior['joint_writes']]:
        raise ValueError('生のトレースから照合したWriteが保存判定と一致しません')
    if not rows or not marker['continuous'] or not tap_marker['continuous']:
        raise ValueError('cubeb、タップ、Writeの連続した共通区間を確認できません')
    tap_origins = {block['sampleTime'] - block['offset'] for block in tape['blocks']
                   if block['offset'] < tw[1] and block['offset'] + block['frames'] > tw[0]}
    device_origins = {row['server_sample_time'] - row['cubeb_pcm_frame'] for row in rows}
    if len(tap_origins) != 1 or len(device_origins) != 1:
        raise ValueError('観測窓内でタップまたは機器のサンプル原点が一定ではありません')

    # 最初の波形からサンプル時計同士の原点差を決め、以降は機器のサンプル番号だけで進める。
    tap_origin, = tap_origins
    device_origin, = device_origins
    first = case['anchor']['first']
    offset = tw[0] - cw[0]
    anchors = []
    clips = [np.diff(stereo.astype(float), axis=1).ravel() / -2 for stereo in (cubeb, tap)]
    chips = chip_values(calibration['marker'])
    for frame in spec['verification_marker_frames']:
        matches = [find_anchor(clip, chips, calibration, frame) for clip in clips]
        row = {'marker_frame': frame, 'expected_cubeb': cw[0] + frame - first,
               'expected_tap': tw[0] + frame - first, 'observed_cubeb': matches[0], 'observed_tap': matches[1]}
        if all(matches):
            left, right = matches
            row['relative_position_error_frames'] = (right['offset'] - right['fraction']
                                                      - left['offset'] + left['fraction'] - offset)
        anchors.append(row)
    for row in rows:
        sample = row['server_sample_time']
        position = sample - device_origin + offset + tap_origin
        frame = round(position - tap_origin)
        expected = tw[0] + row['cubeb_pcm_frame'] - cw[0]
        row['tap_host_clock_pcm_frame'] = row['tap_pcm_frame']
        row['tap_host_clock_position_error_frames'] = row['tap_position_error_frames']
        row['tap_pcm_frame'] = frame
        row['tap_position_error_frames'] = frame - expected
        f = row['cubeb_pcm_frame']
        length = row['frames']
        row['relative_pcm_residual'], row['pcm_gain'] = fit_wave(clips[1][frame:frame + length], clips[0][f:f + length])
    rules = {'maximum_write_position_error_frames': spec['maximum_anchor_position_error_frames'],
             'maximum_relative_residual': spec['maximum_relative_pcm_residual']}
    longest = longest_joint(rows, rules, case['trace'])
    checks = {'independent_pcm_anchors': all('relative_position_error_frames' in row
              and row['expected_cubeb'] == row['observed_cubeb']['offset']
              and row['expected_tap'] == row['observed_tap']['offset']
              and abs(row['relative_position_error_frames']) <= spec['maximum_anchor_position_error_frames']
              for row in anchors),
              'registered_joint_writes': longest >= spec['minimum_joint_writes']}
    return {'checks': checks, 'host_alignment_passed_in_capture': prior['checks']['stable_pcm_clock_alignment'],
            'sample_clock_origins': {'device_minus_cubeb_file_frames': device_origin,
                                     'tap_clock_minus_tap_file_frames': tap_origin, 'tap_file_minus_cubeb_file_frames': offset},
            'verification_anchors': anchors, 'longest_joint_writes': longest, 'joint_writes': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--capture-run', help='同じ収録ケースの再実行を同じ条件で照合する')
    args = parser.parse_args()
    spec = read(CASE)
    registered = WORKSPACE / 'runs' / spec['capture_run']
    capture_id = args.capture_run or spec['capture_run']
    folder = WORKSPACE / 'runs' / capture_id
    original_manifest = read(registered / 'manifest.json')
    saved = read(folder / 'manifest.json')
    if (saved['run_id'], saved['upstream_revision']) != (capture_id, spec['upstream_revision']):
        parser.error('収録の識別子と上流版が一致しません')
    inputs = [CASE, Path(__file__).resolve(), folder / 'manifest.json',
              *(WORKSPACE / 'tools' / name for name in (
                  'measure_firefox_output_marker.py', 'smooth_tap_marker.py', 'measure_worklet_tsp_device_io.py',
                  'measure_cubeb_output_callback.py', 'inspect_firefox_cubeb_output.py',
                  'measure_worklet_tsp_device_tap.py', 'measure_safari_audio_client_trace.py'))]

    def original(name):
        result = verified_file(folder, saved, name)
        inputs.append(result)
        return result

    case = read(original('artifacts/effective-case.json'))
    if args.capture_run:
        expected = verified_file(registered, original_manifest, 'artifacts/effective-case.json')
        if (case != read(expected) or any(saved[key] != original_manifest[key]
                for key in ('case_id', 'case_revision', 'firefox_xul_sha256', 'tap_binary_sha256', 'tap_info_sha256'))):
            parser.error('同じ収録ケース、Firefoxおよびタップのバイナリが必要です')
        inputs.extend((registered / 'manifest.json', expected))
    prior = read(original('summary.json'))
    reference, meta = hydrate_run(case['safari_calibration_run'], case['safari_calibration_case'], spec['upstream_revision'])
    calibration = verified_file(reference, meta, 'artifacts/effective-case.json')
    if case['marker'] != read(calibration)['marker']:
        parser.error('収録時と同じ校正信号が必要です')
    inputs += [reference / 'manifest.json', calibration]
    stream, = [row['stream'] for row in prior['cubeb_streams'] if row['valid']]
    cb = original(f'artifacts/cubeb/{stream}/pcm.f32le')
    tb = original('artifacts/tap.f32le')
    tape = read(original('artifacts/tap.json'))
    blocks = load_blocks(original(f'artifacts/cubeb/{stream}/blocks.csv').parent)
    tables = {schema: original('artifacts/' + schema + '.xml') for schema in (CLIENT, SERVER, HARDWARE)}
    details = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': spec['upstream_revision'],
               'capture_run': capture_id, 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        tables, spec, prior, case, read(calibration), tape, np.fromfile(cb, dtype='<f4').reshape(-1, 2),
        np.fromfile(tb, dtype='<f4').reshape(-1, 2), blocks), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
