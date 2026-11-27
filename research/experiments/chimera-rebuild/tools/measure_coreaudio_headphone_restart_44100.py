"""同じAudioUnitの停止と再開を、出力を維持した無音と比較する。"""

import argparse
from pathlib import Path
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_coreaudio_headphone_late_attach_44100 import inspect_resumption, match_anchors
from measure_csd_envelope_timing import verified_file
from measure_firefox_headphone_drift_44100 import clock_boundary, compare
from measure_firefox_headphone_response_44100 import continuous_blocks, read_stereo
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-output-restart.json'


def inspect_restart(folder, case, calibration, route, captured, fixture, period):
    direct, tape = (read(folder / label) for label in ('native.json', 'tap.json'))
    pcm, tap_pcm = (read_stereo(folder / label) for label in ('native.f32le', 'tap.f32le'))
    rate = case['sample_rate_hz']
    width = case['capture_direct']['observed_output_expected_frames']
    settings, silence, setup, analysis = (case[key] for key in
        ('restart_comparison', 'silence_comparison', 'attach_comparison', 'analysis'))
    restart = direct['restart']
    split = restart['recordedFramesAtStop']
    split_block = restart['recordedBlocksAtStop']
    resume = restart['resumeSourceFrame']
    skipped = resume - split
    tick = host_tick_ms()
    stopped_ms = (restart['startRequestedHostTicks'] - restart['stopReturnedHostTicks']) * tick
    expected_ms = settings['pause_frames_at_nominal_rate'] * 1e3 / rate
    active = captured['during_playback']
    device, = [row for row in active['devices'] if row['id'] == active['defaultOutput']]
    out_marks = direct['frameMarks']
    last_source = setup['terminal_anchors'][-1] + calibration['window_frames']
    first_source = analysis['first_frames'][0]
    before_last, after_first = (silence[key] for key in ('pre_last_exclusive', 'post_first_frame'))
    output_indices = np.r_[0:split, resume:resume + len(pcm) - split]
    wanted = fixture[output_indices % len(fixture)]
    tap_side = (tap_pcm[:, 0] - tap_pcm[:, 1]) * .5
    anchor = match_anchors(tap_side, calibration, case, False) if np.isfinite(tap_side).all() else {}
    before_origin = anchor.get('origin_in_pcm')
    after_origin = (anchor['tail_first']['offset'] - setup['terminal_anchors'][0]
                    if anchor.get('tail_last') else None)
    checks = {
        'capture_completed': captured['tap_started'] and captured['output_exit_code'] == captured['tap_exit_code'] == 0,
        'tap_pid_matches': captured['output_pid'] == direct['pid'] == tape['pid'],
        'device_rate_and_width': (device['uid'], device['sampleRate'], device['bufferFrames']) ==
                                 (case['output_device']['uid'], rate, width),
        'default_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput'],
        'raw_pcm_matches_both_fixture_segments': (folder / 'native.f32le').read_bytes() ==
                                                 np.column_stack((wanted, -wanted)).astype('<f4').tobytes(),
        'output_ok': direct['sampleRate'] == rate and direct['delayMs'] == 0 and not direct['invalidBuffers']
                     and all(mark.get('status') == 0 for mark in out_marks),
        'tap_ok': tape['sampleRate'] == rate and tape['frames'] == len(tap_pcm)
                  and not tape['overflow'] and not tape['formatErrors'],
        'stop_and_resume_as_registered': (
            settings['stop_after_source_frame'] <= split <=
                settings['stop_after_source_frame'] + settings['maximum_stop_overshoot_frames']
            and resume == settings['resume_source_frame'] and 0 < split_block < len(out_marks)
            and out_marks[split_block]['markerOffset'] == split
            and abs(stopped_ms - expected_ms) <= settings['maximum_pause_error_ms']),
        'both_tap_anchors': before_origin is not None and after_origin is not None
                            and abs(anchor['tail_integer_advance']) <= 1,
    }
    result = {'checks': checks, 'restart': restart, 'stopped_ms': stopped_ms, 'active_output_device': device,
              'anchor': anchor, 'tap_origins_in_pcm': [before_origin, after_origin]}
    if not all(checks.values()):
        return result
    for label, rows, meta, field, first, last, length in (
            ('before_direct', out_marks, direct, 'markerOffset', first_source, split, len(pcm)),
            ('after_direct', out_marks, direct, 'markerOffset', split, last_source - skipped, len(pcm)),
            ('before_tap', tape['blocks'], tape, 'offset', before_origin + first_source,
                before_origin + before_last, len(tap_pcm)),
            ('after_tap', tape['blocks'], tape, 'offset', after_origin + after_first,
                after_origin + last_source, len(tap_pcm))):
        selected = continuous_blocks(rows, field, 'sampleTime', first, last, width, length)
        checks[f'{label}_clock'] = bool(selected and all('hostTime' in row for row in selected)
            and all(y['hostTime'] > x['hostTime'] for x, y in zip(selected, selected[1:]))
            and np.isclose(meta['timebaseNumer'] / meta['timebaseDenom'] / 1e6, tick, rtol=1e-12, atol=0))
    if not all(checks.values()):
        return result
    old, new = out_marks[split_block - 1:split_block + 1]
    out_gap_ms = (new['hostTime'] - old['hostTime']) * tick - old['frames'] * 1e3 / rate
    result['clock_transition'] = {
        'last_direct_before_stop': old, 'first_direct_after_restart': new,
        'direct_scheduled_gap_ms': out_gap_ms,
        'direct_sample_time_jump_excluding_last_width': new['sampleTime'] - old['sampleTime'] - old['frames'],
        'tap_marker_origin_change_frames': after_origin - before_origin,
        'tap_before_gap': clock_boundary(tape['blocks'], 'offset', 'sampleTime', 'hostTime',
                                         before_last - 1, before_origin, rate),
        'tap_after_gap': clock_boundary(tape['blocks'], 'offset', 'sampleTime', 'hostTime',
                                        after_first, after_origin, rate),
    }
    source = (pcm[:, 0] - pcm[:, 1]) * .5
    # 比較窓は停止部分を含まない。空いた位置は入力ファイル上の座標を保つために置く。
    source = np.concatenate((source[:split], np.zeros(skipped), source[split:]))
    normalized = [{'pcm_frame': mark['markerOffset'] + (skipped if i >= split_block else 0),
                   'sample_time': mark['sampleTime'], 'host_time': mark['hostTime'], 'frames': mark['frames']}
                  for i, mark in enumerate(out_marks)]
    parts = []
    for first, last, origin in ((first_source, before_last, before_origin),
                                (after_first, setup['analysis_end_frame'], after_origin)):
        aligned = tap_side[origin:] if origin >= 0 else np.pad(tap_side, (-origin, 0))
        clock = {'cubeb': normalized, 'tap': tape['blocks'], 'cb_origin': 0, 'tb_origin': origin}
        options = analysis | {'first_frames': [first], 'last_exclusive': last}
        rendered = compare(source, aligned, period, case | {'analysis': options}, clock)
        for event in rendered['events'].values():
            event['direct'] = event.pop('cubeb')
        parts.append(rendered)
    before, after = parts
    for label, estimate in (('before', before), ('after', after)):
        checks[f'{label}_direct_tone_fits'] = estimate['checks']['cubeb_tone_fits']
    pre_ratios = [tone['amplitude_ratio'] for row in before['windows'] for tone in row['frequencies']
                  if tone['hz'] == analysis['band_tone_hz']]
    result['resumption'] = inspect_resumption(pre_ratios, after, silence, case)
    result['pre_windows'] = before['windows']
    result['post_events'] = after['events']
    return result


def main():
    from measure_firefox_headphone_clock_plateaus_44100 import CASE as CLOCK_CASE, track

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    silence_case = CASE.with_name(case['silence_reference_case'])
    ref = WORKSPACE / 'runs' / case['reference_run']
    ref_manifest = read(ref / 'manifest.json')
    if (ref_manifest['run_id'], ref_manifest['case_id'], ref_manifest['status']) != (
            case['reference_run'], read(silence_case)['id'], 'pass'):
        parser.error('無音対照の基準実行が一致しません')
    previous = verified_file(ref, ref_manifest, 'summary.json')
    control = read(previous)['trials']
    revision = ref_manifest['upstream_revision']
    clock_spec = read(CLOCK_CASE) | {'clock_reference': 'direct'}
    inputs = [CASE, silence_case, CASE.with_name(case['attach_reference_case']), CLOCK_CASE,
              Path(__file__).resolve(), Path(__file__).with_name('measure_firefox_headphone_clock_plateaus_44100.py'),
              ref / 'manifest.json', previous]
    reports = {}
    for row in case['trials']:
        key = row['run_id']
        folder = WORKSPACE / 'runs' / key
        path = folder / 'manifest.json'
        manifest = read(path)
        if (manifest['run_id'], manifest['case_id'], manifest['case_revision'], manifest['upstream_revision']) != (
                key, case['id'], case['revision'], revision):
            parser.error(f'{key} は登録した再開の収録と一致しません')
        inputs.append(path)
        result = {'manifest_status': manifest['status']}
        if any(record['path'] == 'summary.json' for record in manifest['outputs']):
            saved = verified_file(folder, manifest, 'summary.json')
            inputs.append(saved)
            result.update({k: v for k, v in read(saved).items() if k != 'pre_windows'})
        if manifest['status'] == 'pass':
            direct_path, tap_path = (verified_file(folder, manifest, f'artifacts/native/{key}.json')
                                     for key in ('native', 'tap'))
            inputs.extend((direct_path, tap_path))
            direct, tape = map(read, (direct_path, tap_path))
            restart = result['restart']
            skipped = restart['resumeSourceFrame'] - restart['recordedFramesAtStop']
            origin = result['tap_origins_in_pcm'][1]
            clock = {'direct': [(r['markerOffset'] + skipped, r['hostTime'])
                                for r in direct['frameMarks'][restart['recordedBlocksAtStop']:]],
                     'tap': [(r['offset'] - origin, r['hostTime']) for r in tape['blocks'] if 'hostTime' in r],
                     'tick': tape['timebaseNumer'] / tape['timebaseDenom']}
            result['post_clock_plateaus'] = track(clock, result['resumption'], clock_spec)
            result['resumption'].pop('windows')
        reports[key] = result

    def measure(folder, execute):
        pairs = []
        settings = case['restart_comparison']
        for gap, key in case['pairs']:
            found = reports[key]
            previous = control[gap]['resumption']
            valid = found['manifest_status'] == 'pass' and control[gap]['checks']['capture_completed']
            resumed = found['resumption'] if valid else {}
            pre = valid and previous['pre_narrow_in_all_windows'] and resumed['pre_narrow_in_all_windows']
            wide, drop = (resumed.get(k) for k in ('post_wide_first_center', 'post_drop_after_wide_center'))
            relative_drop = drop - settings['resume_source_frame'] if drop is not None else None
            pairs.append({'continuous_silence': gap, 'restart': key, 'capture_valid': valid,
                          'pre_narrow': pre, 'reference_resumed_first_ratio': previous['post_first_ratio'],
                          'restart_resumed_first_ratio': resumed.get('post_first_ratio'), 'wide_frame': wide,
                          'drop_frame_from_restart': relative_drop,
                          'drop_near_predicted_frame': (abs(relative_drop - settings['expected_first_drop_frames_after_resume']) <=
                              settings['maximum_drop_position_error_frames'] if relative_drop is not None else None)})
        return {'checks': {'all_pairs_captured': all(row['capture_valid'] for row in pairs),
                           'all_pairs_initially_narrow': all(row['pre_narrow'] for row in pairs)},
                'wide_prediction_matched': all(row['pre_narrow'] and row['wide_frame'] is not None for row in pairs),
                'drop_timing_prediction_matched': all(row['drop_near_predicted_frame'] is True for row in pairs),
                'pairs': pairs, 'trials': reports}

    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
