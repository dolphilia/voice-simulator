"""共有Contextの確認用07をcubebが返したPCMと要求時計へ結びつける。"""

from csv import DictReader
from itertools import islice
import os
from pathlib import Path
from statistics import median

import inspect_firefox_cubeb_output as cubeb_output
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_worklet_shared_context import marker_signal
from upstream_baseline import WORKSPACE, sha256


def device_inputs(study, revision):
    spec = study['device']
    reference = hydrate_run(spec['browser_run'], spec['browser_case'], revision)
    firefox_value = os.environ.get('CHIMERA_FIREFOX')
    if not firefox_value:
        raise ValueError('CHIMERA_FIREFOX に採取機能付きFirefoxを指定してください')
    firefox = Path(firefox_value).resolve(strict=True)
    xul = firefox.with_name('XUL')
    hashes = {'firefox_binary_sha256': sha256(firefox), 'firefox_xul_sha256': sha256(xul)}
    if any(value != reference[1].get(key) for key, value in hashes.items()):
        raise ValueError('歌唱の既存採取と同じFirefoxおよびXULが必要です')
    backend_case = WORKSPACE / 'cases' / spec['backend_case']
    backend = read(backend_case) | {'window_radius_requests': spec['window_radius_requests']}
    if spec.get('variable_requests'):
        backend |= {key: spec[key] for key in ('variable_requests', 'minimum_request_frames', 'maximum_request_frames')}
    shared_case = backend_case.with_name(backend['shared_context_case'])
    frame_case = backend_case.with_name(backend['frame_validation_case'])
    probe_case = backend_case.with_name(backend['probe_case'])
    frame = read(frame_case)['measurement'] | {'window_radius_callbacks': spec['window_radius_requests']}
    marker = read(shared_case)['measurement']['marker'] | {'stereo_difference': True}
    if marker['quantum'] != frame['worklet_quantum_frames'] or marker['ready_quanta'] <= 2 * frame['window_radius_callbacks']:
        raise ValueError('先行音の量子と機器出力の観測窓が対応しません')
    inputs = [backend_case, shared_case, frame_case, probe_case, reference[0] / 'manifest.json',
              verified_file(*reference, 'summary.json'), Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in (
                  'inspect_firefox_cubeb_output.py', 'measure_worklet_live_song_output_callback.py',
                  'measure_worklet_live_song_process_tap.py', 'measure_worklet_live_song_shared_context.py',
                  'measure_worklet_shared_context.py', 'measure_cubeb_output_callback.py', 'smooth_tap_marker.py',
                  'chimera-cubeb-output-snapshot.patch', 'prepare_firefox_cubeb_source.sh'))]
    return (backend, frame, marker), {'firefox_binary': str(firefox), **hashes}, inputs


def capture_cubeb(execute, folder, backend):
    def run(command, **options):
        target = folder / 'cubeb'
        target.mkdir()
        return execute(['env', f'CHIMERA_CUBEB_OUTPUT_DIR={target}',
                        f"CHIMERA_CUBEB_OUTPUT_BLOCKS={backend['capture']['snapshot_blocks']}", *command],
                       **options)
    return run


def compare_device(folder, condition, result, clock, device):
    backend, frame, marker = device
    valid, signal, _ = marker_signal(marker, folder, frame['worklet_quantum_frames'], frame['output_rate_hz'])
    chosen = result['mapping'].get('selected_thread')
    preparation = result['preparation']
    if not chosen or 'constructor_ms' not in preparation:
        return valid | {'device_worklet_timing_identified': False}, {'reference_signal': signal}
    timing = {'thread': f"{chosen['name']}/{chosen['pid']}", 'preparation': preparation}
    if condition == 'split':
        timing['split_preparation'] = preparation['split']
    expected_gap = backend['expected_request_frames'] if condition == 'draw' else 0
    output = cubeb_output.inspect(folder, {'condition': condition, 'timing': timing}, marker, backend, frame,
                                  clock['engine_marker'], expected_clock_gap_frames=expected_gap)
    output['reference_signal'] = signal
    valid['unique_device_stream_and_graph_window'] = output['valid']
    if condition == 'split':
        valid['split_pieces_match_device_requests'] = output.get('split_requests_valid', False)
    if not all(valid.values()):
        return valid, output

    stream = output['streams'][output['matched_streams'][0]]
    pcm = stream['pcm']
    gap_rows = [row for row in stream['intervals'] if row['sample_time_gap_frames']]
    center, = stream['center_intervals'] if len(stream['center_intervals']) == 1 else (None,)
    limit = center['budget_ms'] if center else 1000 * backend['expected_request_frames'] / backend['sample_rate_hz']
    preparation_calls = output.get('split_requests', [])
    query = [row['cubeb_callback_ms'] for row in preparation_calls]
    output['observations'] = {
        'budget_ms': limit,
        'constructor_callback_ms': center['callback_ms'] if center else None,
        'constructor_clock_gap_frames': center['sample_time_gap_frames'] if center else None,
        'clock_gap_frames': [row['sample_time_gap_frames'] for row in gap_rows],
        'pcm_continuous': pcm['continuous'] if 'smooth_alignment' in backend else not any(
            pcm[k] for k in ('missing_marker_frames', 'repeated_marker_frames', 'undecoded_frames', 'silent_frames')),
        'maximum_preparation_callback_ms': max(query) if query and all(t is not None for t in query) else None,
        'preparation_callbacks_within_budget': bool(query) and all(
            t is not None and t <= row.get('budget_ms', limit) for row, t in zip(preparation_calls, query, strict=True)),
    }
    return valid, output


def device_hypothesis(trials, spec):
    by_condition = {name: [t['device']['observations'] for t in trials if t['condition'] == name
                          and 'observations' in t.get('device', {})] for name in ('draw', 'split')}
    draw = by_condition['draw']
    split = by_condition['split']
    if min(len(draw), len(split)) < len({t['pair'] for t in trials}):
        return {}
    exceeds = sum(r['constructor_callback_ms'] is not None and r['constructor_callback_ms'] > r['budget_ms']
                  for r in draw)
    gaps = sum(r['constructor_clock_gap_frames'] == 256 and r['clock_gap_frames'] == [256] for r in draw)
    safe = sum(not r['clock_gap_frames'] and r['pcm_continuous'] and r['preparation_callbacks_within_budget'] for r in split)
    draw_with_gap = [r for r in draw if r['clock_gap_frames']]
    return {'draw_constructor_budget_overruns': exceeds, 'draw_trials_with_one_256_frame_gap': gaps,
            'split_trials_with_continuous_pcm_and_within_budget': safe,
            'draw_budget_target': exceeds >= spec['minimum_draw_trials_exceeding_constructor_budget'],
            'draw_clock_gap_target': gaps >= spec['minimum_draw_trials_with_one_construction_clock_gap'],
            'split_target': safe >= spec['minimum_split_trials_with_continuous_pcm_and_within_budget'],
            'draw_pcm_continuous_despite_clock_gap': all(r['pcm_continuous'] for r in draw_with_gap) if draw_with_gap else None}


def measure_onset_requests(folder, output, count):
    if not output['valid']:
        return {'onset_quanta_match_device_requests': False}, []
    with (folder / 'aligned-quanta.csv').open(newline='') as source:
        quanta = list(islice(DictReader(source), count))
    stream = output['streams'][output['matched_streams'][0]]
    requests = {}
    matched = 0
    for graph, callback in zip(output['graph_rows'], stream['intervals'], strict=True):
        start, end = graph['graph_span_ms']
        selected = [q for q in quanta if int(q['context_frame']) in graph['reference_frame_starts']
                    and start <= float(q['engine_start_ms']) <= float(q['engine_end_ms']) <= end]
        if not selected:
            continue
        matched += len(selected)
        requests[graph['offset']] = {
            'offset': graph['offset'],
            'context_frames': [int(q['context_frame']) for q in selected],
            'speech_output_frames': [int(q['output_frame']) for q in selected],
            'worklet_ms': sum(float(q['engine_ms']) for q in selected),
            'requested_frames': callback['request_frames'],
            'graph_advance_frames': graph['graph_advance_frames'],
            'callback_ms': callback['callback_ms'],
            'budget_ms': callback['budget_ms'],
            'duration_minus_budget_ms': callback['callback_ms'] - callback['budget_ms'],
            'clock_gap_frames': callback['sample_time_gap_frames'],
        }
    return {'onset_quanta_match_device_requests': len(quanta) == matched == count}, list(requests.values())


def summarize_onset_requests(trials, spec):
    groups = {}
    for name in ('split', 'split-late'):
        requests = [t['device_onset_requests'] for t in trials if t['condition'] == name
                    and t['checks'].get('onset_quanta_match_device_requests')]
        if len(requests) != len(spec['condition_order']):
            return groups, {}
        groups[name] = {
            'trials': len(requests),
            'onset_in_one_request': sum(len(rows) == 1 for rows in requests),
            'median_maximum_duration_minus_budget_ms': median(
                max(r['duration_minus_budget_ms'] for r in rows) for rows in requests),
            'over_budget_requests': sum(r['duration_minus_budget_ms'] > 0 for rows in requests for r in rows),
            'clock_gaps_in_onset_requests': [r['clock_gap_frames'] for rows in requests for r in rows
                                             if r['clock_gap_frames']],
        }
    baseline, late = groups['split'], groups['split-late']
    return groups, {
        'fewer_starts_grouped_in_one_request': late['onset_in_one_request'] < baseline['onset_in_one_request'],
        'lower_median_maximum_duration_minus_budget':
            late['median_maximum_duration_minus_budget_ms'] < baseline['median_maximum_duration_minus_budget_ms'],
    }
