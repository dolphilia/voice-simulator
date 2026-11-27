"""44.1 kHzで一定の負荷を繰り返した収録から予定時刻・機器Write・タップを照合する。"""

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
from measure_worklet_tsp_44100_late_write import map_late_requests, waveform_models
from measure_worklet_tsp_44100_load import request_info
from measure_worklet_tsp_device_io import CLIENT, HARDWARE, SERVER
from smooth_tap_marker import fit_wave
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100-headphone-load-416-repeat.json'
SCHEMAS = (CLIENT, HARDWARE, SERVER)


def phase_channels(pcm):
    return {'in_phase': (pcm[:, 0] + pcm[:, 1]) / 2,
            'out_of_phase': (pcm[:, 0] - pcm[:, 1]) / 2}


def wide_write_windows(timing, writes, request, start, spans, tap_frames, width):
    anchor, following = timing[1:3]
    windows = []
    if 'write' not in anchor or 'server' not in following:
        return None, windows
    first_sample = anchor['write']['start_sample_time']
    next_sample = following['server']['output_sample_time']
    matches_cubeb = next_sample - first_sample == request['request_frames'] + request['gap_frames']
    for write in writes:
        delta = next_sample - write['start_sample_time']
        if write['frames'] != width or not 0 <= delta < width:
            continue
        a = start + write['start_sample_time'] - first_sample
        b = a + width
        overlaps = [[lo, hi, min(b, hi) - max(a, lo)] for lo, hi in spans if a < hi and lo < b]
        windows.append({'device_sample_time': write['start_sample_time'], 'next_server_offset_frames': delta,
                        'tap_frames_relative_to_window': [a, b], 'overlapping_zero_spans': overlaps,
                        'window_complete': 0 <= a < b <= tap_frames})
    return matches_cubeb, windows


def compare_pcm(files, native, prior, stream, request, timing, writes, other_gaps, case):
    cw, tw = stream['marker']['tap_window'], prior['tap']['pcm']['tap_window']
    raw = np.fromfile(files[native + '/pcm.f32le'], dtype='<f4').reshape(-1, 2)[slice(*cw)].astype(float)
    tap = np.fromfile(files['artifacts/tap.f32le'], dtype='<f4').reshape(-1, 2)[slice(*tw)].astype(float)
    if len(raw) != cw[1] - cw[0] or len(tap) != tw[1] - tw[0]:
        raise ValueError('登録されたPCM窓の長さを取得できません')
    extra = len(tap) - len(raw)
    gaps = prior['gaps']
    size = request['gap_frames']

    def tap_start(row):
        prior_jumps = sum(gap['gap_frames'] for gap in gaps if gap['cubeb_index'] < row['cubeb_index'])
        return row['cubeb_pcm_frame'] - cw[0] + prior_jumps

    start = tap_start(request)
    edges = np.flatnonzero(np.diff(np.r_[False, np.all(tap == 0, axis=1), False])).reshape(-1, 2)
    spans = edges.tolist()
    width = case['wide_write_frames']
    clock_match, windows = wide_write_windows(timing, writes, request, start, spans, len(tap), width)
    result = {'tap_window': tw, 'cubeb_window': cw, 'tap_growth_frames': extra, 'stereo_zero_spans': spans,
              'growth_matches_gaps': extra == sum(row['gap_frames'] for row in gaps), 'wide_write_windows': windows,
              'next_server_sample_matches_cubeb': clock_match, 'other_gaps': []}
    for gap, gap_timing, gap_writes in other_gaps:
        observed, windows = wide_write_windows(gap_timing, gap_writes, gap, tap_start(gap), spans, len(tap), width)
        result['other_gaps'].append({'cubeb_index': gap['cubeb_index'], 'gap_frames': gap['gap_frames'],
            'timing': gap_timing[1:3], 'intermediate_writes': gap_writes,
            'next_server_sample_matches_cubeb': observed, 'wide_write_windows': windows})
    references, observed = phase_channels(raw), phase_channels(tap)
    if size == 0 and not gaps and extra == 0:
        result['continuous_residuals'] = {name: fit_wave(observed[name], reference)[0]
                                          for name, reference in references.items()}
    elif len(gaps) == 1 and gaps[0]['cubeb_index'] == request['cubeb_index'] and size == extra > 0:
        end = start + request['request_frames']
        flank = case['model']['flank_frames']
        if size <= flank and start >= flank and end + flank <= len(raw):
            result['models'] = {name: waveform_models(reference, observed[name], start, end, size, case['model'])
                                for name, reference in references.items()}
        else:
            result['model_missing'] = '局所モデルの前後に必要なPCM窓が不足しています'
    elif size > 0:
        result['model_missing'] = '単一の飛びと対応するPCM窓がそろいません'
    return result


def analyze_trial(prior, files, case, uid):
    checks = {'canonical_speech_and_registered_offsets': False, 'audio_client_and_device_write': False,
              'tap_clock_and_pcm_length': False}
    result = {'checks': checks, 'original_checks': prior.get('checks', {}),
              'target_over_budget': None, 'target_gap_frames': None, 'reproduced': None}
    if 'last_draw' not in prior.get('requests', {}):
        result['missing'] = '対象のcubeb要求を同定できません'
        return result
    last, speech = prior['requests']['last_draw'], prior['requests'].get('speech_render_start')
    checks['canonical_speech_and_registered_offsets'] = bool(speech
        and prior['checks']['canonical_speech_pcm_and_states'] and prior['checks']['registered_preparation']
        and last['cubeb_index'] == speech['cubeb_index']
        and (last['request_frame_offset'], speech['request_frame_offset']) == (0, case['request_frames'] // 2))
    stream, = [row for row in prior['cubeb_streams'] if row['valid']]
    native = 'artifacts/cubeb/' + stream['stream']
    tick_ns = host_tick_ms() * 1e6
    blocks = load_blocks(files[native + '/blocks.csv'].parent)
    pivot = last['cubeb_index']
    request = request_info(blocks, pivot, tick_ns, case['sample_rate_hz'])
    if request['request_frames'] != case['request_frames'] or request['gap_frames'] != last['gap_frames']:
        raise ValueError('保存したcubeb要求と収録時の判定が一致しません')
    result.update(request=request, target_gap_frames=request['gap_frames'],
                  scheduled_gaps=[{'cubeb_index': row['cubeb_index'], 'gap_frames': row['gap_frames']}
                                  for row in prior['gaps']],
                  cubeb_over_budget=request['callback_ns'] > request['budget_ns'])
    tables = {key: files[f'artifacts/{key}.xml'] for key in SCHEMAS if f'artifacts/{key}.xml' in files}
    timing, writes, other_gaps = [{}, {}, {}], [], []
    if len(tables) == len(SCHEMAS) and 0 < pivot < len(blocks) - 2:
        tape = read(files['artifacts/tap.json'])
        timing, writes = map_late_requests(tables, blocks, tape, pivot, uid, case, tick_ns, same_write_thread=False)
        for gap in prior['gaps']:
            i = gap['cubeb_index']
            if i != pivot and gap['gap_frames'] > 0 and 0 < i < len(blocks) - 2:
                other_gaps.append((gap, *map_late_requests(tables, blocks, tape, i, uid, case, tick_ns,
                                                         same_write_thread=False)))
        anchor = timing[1]
        checks['audio_client_and_device_write'] = 'audio_client' in anchor and 'write' in anchor
        result.update(timing=timing, intermediate_writes=writes)
        if checks['audio_client_and_device_write']:
            result['target_over_budget'] = (result['cubeb_over_budget']
                and anchor['audio_client']['duration_ns'] > request['budget_ns'])
    else:
        result['timing_missing'] = 'トレース表または前後の要求が不足しています'
    if prior['checks'].get('tap_pcm_and_sample_clock') and prior['checks'].get('registered_tap_width'):
        pcm = compare_pcm(files, native, prior, stream, request, timing, writes, other_gaps, case)
        result['pcm'] = pcm
        checks['tap_clock_and_pcm_length'] = pcm['growth_matches_gaps']
        if all(checks.values()) and pcm.get('next_server_sample_matches_cubeb'):
            result['reproduced'] = (request['gap_frames'] > 0 and any(
                row['window_complete'] and any(hi - lo >= case['minimum_stereo_zero_frames']
                                               for lo, hi, _ in row['overlapping_zero_spans'])
                for row in pcm['wide_write_windows']))
    else:
        result['pcm_missing'] = prior.get('tap', {}).get('pcm', {}).get(
            'reason', 'タップのPCMまたは時計の照合に失敗')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--tap-review', help='先頭アンカーだけを短縮した既存の再解析を併記する')
    args = parser.parse_args()
    registration = read(CASE)
    base = CASE.with_name(registration['base_case'])
    onset = CASE.with_name(read(base)['base_case'])
    case = registration['repeat_analysis']
    uid = read(onset)['output_device']['uid']
    case_path = str(CASE.relative_to(ROOT))
    case_digest = sha256(CASE)
    inputs = [CASE, base, onset, Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_worklet_tsp_44100_load.py', 'measure_worklet_tsp_44100_late_write.py',
        'measure_worklet_tsp_44100_onset.py', 'measure_worklet_tsp_device_io.py', 'measure_cubeb_output_callback.py',
        'inspect_firefox_cubeb_output.py', 'measure_safari_audio_client_trace.py', 'smooth_tap_marker.py'))]
    sources = []
    names = {'summary.json', 'artifacts/tap.f32le', 'artifacts/tap.json',
             *(f'artifacts/{key}.xml' for key in SCHEMAS)}
    for trial, run_id in enumerate(case['capture_runs'], start=1):
        folder = WORKSPACE / 'runs' / run_id
        manifest_file = folder / 'manifest.json'
        saved = read(manifest_file)
        identity = (saved['run_id'], saved['case_id'], saved['case_revision'], saved['upstream_revision'],
                    saved['trial'], saved['last_preparation_frames'])
        if identity != (run_id, registration['id'], registration['revision'], case['upstream_revision'],
                        trial, registration['load']['order'][trial - 1]):
            parser.error('登録された収録のケース・版・試行番号と一致しません')
        if [row['sha256'] for row in saved['inputs'] if row['path'] == case_path] != [case_digest]:
            parser.error('収録した時点の事前登録とケースの内容が一致しません')
        files = {name: verified_file(folder, saved, name) for row in saved['outputs']
                 if (name := row['path']) in names or name.startswith('artifacts/cubeb/')}
        inputs.extend([manifest_file, *files.values()])
        sources.append((saved, files))

    review_run, review_summary = None, None
    if args.tap_review:
        review_folder = WORKSPACE / 'runs' / args.tap_review
        review_manifest = review_folder / 'manifest.json'
        saved = read(review_manifest)
        review_run = saved['capture_run']
        capture, files = next((item for item in sources if item[0]['run_id'] == review_run), (None, {}))
        identity = ('case_id', 'case_revision', 'upstream_revision', 'trial', 'last_preparation_frames')
        if (saved['run_id'] != args.tap_review or capture is None
                or any(saved[key] != capture[key] for key in identity)):
            parser.error('登録された収録のタップ再解析ではありません')
        path = verified_file(review_folder, saved, 'summary.json')
        original, review_summary = read(files['summary.json']), read(path)
        trim = review_summary['trimmed_leading_anchor_frames']
        request_fields = ('cubeb_index', 'sample_time', 'gap_frames', 'context_frame', 'request_frame_offset')
        same_requests = all(original['requests'][target][key] == review_summary['requests'][target][key]
                            for target in ('last_draw', 'speech_render_start') for key in request_fields)
        before, after = (data['graph_window'] for data in (original, review_summary))
        if (original['tap']['pcm'].get('reason') != 'smooth_anchor_not_unique'
                or not (0 < trim <= 1024 and trim % case['request_frames'] == 0)
                or not review_summary['checks']['tap_pcm_and_sample_clock']
                or (before['first'] + trim, before['last_exclusive']) != (after['first'], after['last_exclusive'])
                or not same_requests):
            parser.error('先頭アンカーの欠測を補う再解析ではありません')
        inputs.extend((review_manifest, path))

    def measure(out, execute):
        trials = {}
        for saved, files in sources:
            summary = files.get('summary.json')
            prior = read(summary) if summary else {}
            trial = analyze_trial(prior, files, case, uid)
            trial.update(original_status=saved['status'], original_error=saved.get('error'))
            if saved['run_id'] == review_run:
                review = analyze_trial(review_summary, files, case, uid)
                review.update(review_run=args.tap_review, original_tap_missing=trial.get('pcm_missing'),
                              original_checks=trial['original_checks'], original_status=trial['original_status'])
                trial = review
            trials[saved['run_id']] = trial
        rows = trials.values()
        counts = {'trials': len(trials), 'both_over_budget': sum(row['target_over_budget'] is True for row in rows),
                  'audio_client_and_write': sum(row['checks']['audio_client_and_device_write'] for row in rows),
                  'positive_target_gap': sum((row['target_gap_frames'] or 0) > 0 for row in rows),
                  'continuous_target_clock': sum(row['target_gap_frames'] == 0 for row in rows),
                  'reproduced': sum(row['reproduced'] is True for row in rows),
                  'event_unclassified': sum(row['reproduced'] is None for row in rows)}
        checks = {run + '/' + name: value for run, row in trials.items() for name, value in row['checks'].items()}
        checks.update(all_over_budget=counts['both_over_budget'] == counts['trials'],
                      observed_repeat=counts['reproduced'] > 0,
                      observed_continuous=counts['continuous_target_clock'] > 0,
                      all_events_classified=counts['event_unclassified'] == 0)
        return {'trials': trials, 'counts': counts, 'checks': checks}

    metadata = {'case_id': registration['id'], 'case_revision': registration['revision'],
                'upstream_revision': case['upstream_revision'], 'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, CASE, inputs, metadata, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
