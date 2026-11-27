"""実機のAudioUnitに遅い出力コールバックを渡し、次の要求時刻を測る。"""

import argparse
from pathlib import Path

from measure_worklet_live_song_process_tap import song


CASE = song.WORKSPACE / 'cases/coreaudio-output-deadline-probe.json'
SOURCE = Path(__file__).with_name('chimera_output_deadline_probe.swift').resolve()


def inspect(source, case):
    marks = source['frameMarks']
    index = case['overrun_callback_index']
    radius = case['window_radius_callbacks']
    if index + radius >= len(marks):
        return {'checks': {'enough_callbacks': False}, 'observed_callbacks': len(marks)}
    window = marks[index - radius:index + radius + 1]
    rate = case['sample_rate_hz']
    tick_ms = source['timebaseNumer'] / source['timebaseDenom'] / 1e6
    checks = {'output_rate': source['sampleRate'] == rate,
              'output_buffers_valid': source['invalidBuffers'] == 0,
              'sample_and_host_clock_valid': all(mark.get('sampleTime') is not None and mark.get('hostTime') is not None
                                                 for mark in window),
              'submitted_marker_order': all(a['markerOffset'] + a['frames'] == b['markerOffset']
                                            for a, b in zip(window, window[1:]))}
    if not all(checks.values()):
        return {'checks': checks, 'observed_callbacks': len(marks)}
    intervals = []
    for offset, (current, following) in enumerate(zip(window, window[1:]), -radius):
        requested = current['frames']
        budget = 1000 * requested / rate
        intervals.append({'offset': offset, 'requested_frames': requested, 'budget_ms': budget,
                          'callback_ms': (current['emitted'] - current['entered']) * tick_ms,
                          'host_start_interval_ms': (following['hostTime'] - current['hostTime']) * tick_ms,
                          'actual_entry_interval_ms': (following['entered'] - current['entered']) * tick_ms,
                          'device_sample_gap_frames': following['sampleTime'] - current['sampleTime'] - requested})
    center = intervals[radius]
    return {'checks': checks, 'observed_callbacks': len(marks), 'center': center, 'intervals': intervals,
            'over_budget': center['callback_ms'] > center['budget_ms']}


def measure(case, binary, artifacts, execute):
    result = {}
    checks = {}
    for label, delay in [('control', 0), ('overrun', case['delay_ms'])]:
        out = artifacts / f'{label}.json'
        execute([str(binary), str(case['overrun_callback_index']), str(delay), str(case['sample_rate_hz']),
                 str(case['duration_seconds'])], stdout=out)
        result[label] = inspect(song.wasm.read_json(out), case)
        checks.update({f'{label}/{key}': value for key, value in result[label]['checks'].items()})
    return {'checks': checks, 'conditions': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('binary', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    case = song.wasm.read_json(case_path)
    binary = args.binary.resolve(strict=True)
    inputs = [case_path, SOURCE, Path(__file__).resolve()]
    if 'previous_run' in case:
        previous = song.run_manifest(case['previous_run'], Path(case['previous_case']).stem, case['upstream_revision'])
        inputs.extend([case_path.parent / case['previous_case'], previous[0] / 'manifest.json',
                       song.verified_path(previous, 'summary.json')])
    details = {'case_id': case['id'], 'upstream_revision': case['upstream_revision'],
               'probe_binary': str(binary), 'probe_binary_sha256': song.sha256(binary)}
    return song.shared.record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case, binary, artifacts, execute), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
