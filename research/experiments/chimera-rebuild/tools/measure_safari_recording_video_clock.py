"""AudioContext停止時の映像PTSを、録画に音声トラックを含める場合と比べる。"""

import argparse
from pathlib import Path
import subprocess
import sys

import measure_safari_recording_pause_clock_split as clock
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement
from measure_wasm_fixed import read_json


CASE = clock.WORKSPACE / 'cases/safari-recording-video-clock.json'
MODES = ('audiovisual', 'video_only')


def compare(folder, mode, spec, execute):
    report = read_json(folder / 'browser.json')
    if report.get('error') or report['stage'] != 'complete':
        raise ValueError(report.get('error', 'Safariの録画が完了しませんでした'))
    include_audio = mode == 'audiovisual'
    checks, graph = clock.graph(report, 'context', spec, include_audio=include_audio)
    media_checks, audio, video = clock.inspect(folder, folder, report, graph, spec, execute, include_audio=include_audio)
    during = video['during_hold']
    wall_span = (during[-1]['wall_ms'] - during[0]['wall_ms']) / 1000 if during else 0
    span = video['hold_pts_span_seconds']
    checks.update(media_checks, context_stayed_at_one_frame=graph['held_context_frames'] == 0,
                  video_has_matching_held_clock=video['hold_distinct_context_codes'] == 1,
                  video_hold_is_observable=video['hold_distinct_wall_codes'] >= spec['video_minimum_context_hold_frames']
                  and wall_span >= spec['video_minimum_measured_wall_span_seconds'])
    prediction = {}
    if all(checks.values()):
        if include_audio:
            prediction['video_follows_frozen_audio_clock'] = span <= spec['video_maximum_audio_hold_pts_span_seconds']
            prediction['audio_spans_remain_contiguous'] = all(
                abs(audio[key]) <= spec['audio_pause_tolerance_seconds']
                for key in ('sample_lag_shift_seconds', 'pts_lag_shift_seconds'))
        else:
            prediction['video_follows_wall_clock'] = abs(span - wall_span) <= spec['video_maximum_wall_pts_error_seconds']
    video.update(hold_wall_span_seconds=wall_span, hold_pts_per_wall=(span / wall_span if wall_span else None))
    return checks, {'graph': graph, 'video': video, 'audio': audio, 'predictions': prediction,
                    'reported_mime_type': report['mimeType'], 'mime_fallback': report.get('mimeFallback')}


def measure(case_path, study, artifacts, execute):
    execute(['node', str(clock.CAPTURE), str(case_path), str(artifacts)], stdout=artifacts / 'safari.log')
    checks, trials, pairs = {}, [], []
    spec = study['measurement']
    for index, order in enumerate(study['condition_order'], 1):
        results = {}
        for mode in order:
            label = f'{index}-{mode}'
            row = {'trial': label, 'condition': mode, 'pair': index}
            try:
                local, result = compare(artifacts / label, mode, spec, execute)
                row.update(result)
                if all(local.values()):
                    results[mode] = result['video']['hold_pts_span_seconds']
            except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
                local = {'completed': False}
                row['error'] = str(error)
            checks.update({f'{label}/{key}': value for key, value in local.items()})
            trials.append(row)
        difference = results['video_only'] - results['audiovisual'] if len(results) == len(MODES) else None
        pairs.append({'pair': index, 'video_only_minus_audiovisual_pts_span_seconds': difference,
                      'prediction': difference >= spec['video_minimum_paired_pts_span_difference_seconds']
                      if difference is not None else None})
    return {'checks': checks, 'trials': trials, 'pairs': pairs}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (study['audio_track_comparison'] is not True
            or not study['condition_order'] or any(sorted(order) != list(MODES) for order in study['condition_order'])
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clock.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=clock.UPSTREAM, text=True)):
        parser.error('動画の条件または固定上流が一致しません')
    info = study['clock_reference']
    reference_case = CASE.parent / info['case']
    original = read_json(reference_case)
    run = run_manifest(info['run'], original['id'], revision)
    reference = verified_path(run, 'summary.json')
    context = [row for row in read_json(reference)['trials'] if row['mode'] == 'context']
    common = set(study['measurement']) & set(original['measurement'])
    if (run[1]['status'] != 'pass' or not context
            or any(not row['predictions']['video_shortens_context_hold'] for row in context)
            or any(study['measurement'][key] != original['measurement'][key] for key in common)):
        parser.error('先行ケースの結果または共通の入力設定が一致しません')
    commands = {'safaridriver': ['/usr/bin/safaridriver', '--version'], 'node': ['node', '--version'],
                'ffmpeg': ['ffmpeg', '-version'], 'ffprobe': ['ffprobe', '-version']}
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv],
                **{key: subprocess.check_output(cmd, text=True).splitlines()[0] for key, cmd in commands.items()}}
    inputs = [CASE, reference_case, run[0] / 'manifest.json', reference, Path(__file__).resolve(),
              clock.CAPTURE, clock.CAPTURE.with_name('safari-webdriver.mjs'), Path(clock.__file__),
              Path(clock.recording.__file__), Path(read_json.__code__.co_filename)]
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(CASE, study, artifacts, execute), command=None, input_root=clock.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
