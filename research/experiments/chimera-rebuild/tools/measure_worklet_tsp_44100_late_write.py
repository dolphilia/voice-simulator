"""44.1 kHzの遅いWriteと、要求幅と異なる飛びのタップPCMを再解析する。"""

import argparse
from pathlib import Path
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT
from measure_worklet_tsp_44100_onset import headphone_write_times
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER, match_server, read_cycles, server_rows
from smooth_tap_marker import fit_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-late-write-review.json'


def map_late_requests(tables, blocks, tape, pivot, uid, case, tick_ns, *, same_write_thread=True):
    server = list(server_rows(tables[SERVER], SERVER, intervals=True))
    writes = list(server_rows(tables[HARDWARE], HARDWARE, intervals=True))
    device = headphone_write_times(tables[HARDWARE], uid)
    writes = [row for row in writes if (row['start_ns'], row['start_sample_time']) in device]
    client, _ = read_cycles(tables[CLIENT], tape['pid'], include_overloads=True)
    tolerance = case['maximum_server_host_error_us'] / 1000
    period = case['request_frames'] * 1e9 / case['sample_rate_hz']
    evidence = []
    for i in range(pivot - 1, pivot + 3):
        block = blocks[i]
        matches = match_server([block], server, tape['pid'], tick_ns, tolerance)
        profiles = [(candidate['cycles'][0], write)
                    for candidate in matches for write in writes
                    if write['tid'] == candidate['tid'] and write['frames'] == block['frames']
                    and write['start_sample_time'] == candidate['cycles'][0]['output_sample_time']
                    and 0 <= write['start_ns'] - candidate['cycles'][0]['start_ns']
                    <= period * case['maximum_write_delay_periods']]
        row = {'cubeb_index': i, 'server_candidates': len(matches), 'device_candidates': len(profiles),
               'callback_ns': (block['returned'] - block['entered']) * tick_ns,
               'buffer_sample_time': block['sample_time'], 'budget_ns': period}
        snapped = profiles[0][0] if len(profiles) == 1 else matches[0]['cycles'][0] if len(matches) == 1 else None
        if snapped:
            row['server'] = snapped
        if len(profiles) == 1:
            cycle, write = profiles[0]
            origin = round(write['current_host_ticks'] * tick_ns) - write['start_ns']
            entry, returned = (round(block[key] * tick_ns) - origin for key in ('entered', 'returned'))
            related = [event for event in client if event['start_ns'] <= entry + 1000
                       and returned <= event['start_ns'] + event['duration_ns'] + 1000]
            row.update(write=write, write_delay_ns=write['start_ns'] - cycle['start_ns'],
                       matching_audio_client=len(related))
            if len(related) == 1:
                row['audio_client'] = related[0]
                row['within_budget'] = max(related[0]['duration_ns'], row['callback_ns']) <= period
        evidence.append(row)
    first, following = evidence[1:3]
    between = []
    if 'write' in first and 'server' in following:
        lo = first['write']['start_sample_time'] + first['write']['frames']
        hi = following['server']['output_sample_time']
        between = [row for row in writes if lo <= row['start_sample_time'] < hi
                   and (not same_write_thread or row['tid'] == first['write']['tid'])
                   and row['engine_id'] == first['write']['engine_id']
                   and row['stream_index'] == first['write']['stream_index']]
    return evidence, between


def waveform_models(reference, observed, early, late, extra, limits):
    flank = limits['flank_frames']
    a, b = early - flank, late + flank
    focus = observed[a:b + extra]
    if a < 0 or b > len(reference) or b + extra > len(observed) or extra > flank:
        raise ValueError('飛びを調べる波形窓が不足しています')
    best = {}
    for pos in range(early, late + 1):
        for name, inserted in (('zeros', np.zeros(extra)), ('repeat_before', reference[pos - extra:pos]),
                               ('repeat_after', reference[pos:pos + extra])):
            waveform = np.r_[reference[a:pos], inserted, reference[pos:b]]
            residual, gain = fit_wave(focus, waveform)
            if name not in best or residual < best[name]['relative_rms_residual']:
                best[name] = {'insertion_frame_in_window': pos, 'relative_rms_residual': residual, 'gain': gain}
    first, second, *_ = sorted(best, key=lambda name: best[name]['relative_rms_residual'])
    margin = best[second]['relative_rms_residual'] - best[first]['relative_rms_residual']
    selected = (first if best[first]['relative_rms_residual'] <= limits['maximum_relative_residual']
                and margin >= limits['minimum_other_family_margin'] else None)
    return {'best_by_model': best, 'margin': margin, 'selected': selected}


def analyze_trial(folder, prior, case):
    stream, = [row for row in prior['cubeb_streams'] if row['valid']]
    native = folder / 'cubeb' / stream['stream']
    blocks = load_blocks(native)
    tape = read(folder / 'tap.json')
    tables = {schema: folder / (schema + '.xml') for schema in (CLIENT, SERVER, HARDWARE)}
    tick_ns = host_tick_ms() * 1e6
    pivot = prior['requests']['last_draw']['cubeb_index']
    rows, missing_period_writes = map_late_requests(tables, blocks, tape, pivot,
        'BuiltInHeadphoneOutputDevice', case, tick_ns)
    anchor = rows[1]
    checks = {'load_request_verified': 'audio_client' in anchor and 'write' in anchor}
    observed = {'checks': checks, 'timing': rows, 'writes_inside_scheduled_gap': missing_period_writes,
                'prior_checks': prior['checks']}
    gaps = prior['gaps']
    if not gaps:
        return observed
    gap, = gaps
    if gap['cubeb_index'] != pivot or not prior['checks']['tap_length_matches_scheduled_gaps']:
        raise ValueError('負荷要求とタップPCMの単一の飛びを照合できません')
    cw, tw = stream['marker']['tap_window'], prior['tap']['pcm']['tap_window']
    raw = np.fromfile(native / 'pcm.f32le', dtype='<f4').reshape(-1, 2)[slice(*cw)].astype(float)
    tap = np.fromfile(folder / 'tap.f32le', dtype='<f4').reshape(-1, 2)[slice(*tw)].astype(float)
    early = gap['cubeb_pcm_frame'] - cw[0]
    size = gap['gap_frames']
    late = early + case['request_frames']
    mid = waveform_models(raw.mean(axis=1), tap.mean(axis=1), early, late, size, case['model'])
    side = waveform_models((raw[:, 0] - raw[:, 1]) / 2, (tap[:, 0] - tap[:, 1]) / 2,
                           early, late, size, case['model'])
    edges = np.flatnonzero(np.diff(np.r_[False, np.all(tap == 0, axis=1), False])).reshape(-1, 2)
    observed['gap_pcm'] = {'gap_frames': size, 'request_start_frame_in_window': early, 'tap_window_start_frame': tw[0],
                           'stereo_zero_spans': edges.tolist(), 'in_phase': mid, 'out_of_phase': side}
    checks['waveform_model_validated'] = mid['selected'] is not None and mid['selected'] == side['selected']
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    trials = {}
    inputs = [CASE, Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_worklet_tsp_44100_onset.py', 'measure_worklet_tsp_device_io.py', 'measure_cubeb_output_callback.py',
        'inspect_firefox_cubeb_output.py', 'measure_safari_audio_client_trace.py', 'smooth_tap_marker.py'))]
    for run in case['capture_runs']:
        folder = WORKSPACE / 'runs' / run
        manifest = folder / 'manifest.json'
        vendor = read(manifest)
        if (vendor['run_id'], vendor['case_id'], vendor['upstream_revision']) != (
                run, case['expected_capture_case'], case['upstream_revision']):
            parser.error('登録された負荷計測の実行を指定してください')
        paths = [row['path'] for row in vendor['outputs']]
        names = {'summary.json', 'artifacts/tap.f32le', 'artifacts/tap.json',
                 *(f'artifacts/{key}.xml' for key in (CLIENT, HARDWARE, SERVER))}
        names.update(name for name in paths if name.startswith('artifacts/cubeb/'))
        verified = {name: verified_file(folder, vendor, name) for name in sorted(names)}
        inputs.extend((manifest, *verified.values()))
        trials[run] = (folder / 'artifacts', read(verified['summary.json']))

    def measure(out, execute):
        result = {run: analyze_trial(folder, prior, case) for run, (folder, prior) in trials.items()}
        return {'trials': result, 'checks': {run + '/' + name: value for run, row in result.items()
                                            for name, value in row['checks'].items()}}

    metadata = {'case_id': case['id'], 'case_revision': case['revision'],
                'upstream_revision': case['upstream_revision'], 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
