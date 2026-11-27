"""固定上流の歌唱録画を停止付きで取得し、加工前PCMと音声・映像PTSに照合する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

import measure_safari_recording_pause_clock_split as clock
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import sha256


CASE = clock.WORKSPACE / 'cases/upstream-safari-song-recording-pause.json'
CAPTURE = clock.WEB / 'tools/capture-upstream-safari-recording-pause.mjs'


def graph(report, mode, pcm, score, spec, wasm_hash):
    rate, quantum = spec['output_rate_hz'], spec['quantum_frames']
    rows = np.array(report['rows'], dtype=np.int64)
    if rows.ndim != 2 or rows.shape[1] != 4 or len(rows) < 2:
        raise ValueError('描画量子の観測が不足しています')
    before, held, request, resumed = (next(event for event in report['events'] if event['phase'] == phase)
        for phase in ('hold_requested', 'held', 'resume_requested', 'resumed'))
    armed = report['armed']
    plan_start = round(armed['offset'] * rate)
    trim = plan_start - armed['engineFrame']
    if not 0 <= trim < len(pcm):
        raise ValueError('録画内で譜面の開始サンプルを特定できません')
    wall_time = held['wallMs'], request['wallMs']
    hold_ms = wall_time[1] - wall_time[0]
    planned_context = armed['contextFrame'] + trim
    candidate_equivalent = (held['frame'] - planned_context
                            + round((score['candidate_first_beat_seconds'] - score['first_beat_seconds']) * rate))
    i = int(np.argmax(np.diff(rows[:, 3])))
    clip_events = [event['type'] for event in report['recorderEvents']]
    midi = report['midi']
    checks = {
        'trusted_safari_record_video': (report['clickTrusted'] is True and report['capabilities']['browserName'] == 'Safari'
                                       and Path(report['saved']).suffix == '.mp4'),
        'fixed_wasm_and_output_rate': report['sampleRate'] == rate and report['wasmSha256'] == wasm_hash,
        'expected_melody_and_beat_anchor': (
            [note['midi'] for note in midi] == [note[0] for note in score['notes']]
            and abs(midi[0]['t0'] - armed['offset'] - score['first_beat_seconds']) < 1e-6
            and abs(midi[1]['t0'] - midi[0]['t0'] - 60 * score['notes'][0][1] / score['bpm']) < 1e-6
            and report['input']['lyrics'] == score['lyrics']),
        'two_tracks_and_ordinary_stop': (report['recordTracks'] == ['audio', 'video'] and clip_events == ['start', 'stop']
                                          and report['captureFps'] == 30),
        'stop_at_requested_musical_position': (
            before['frame'] >= report['targetFrame'] and before['state'] == 'running'
            and abs(candidate_equivalent - spec['candidate_target_output_frames']) <= spec['target_tolerance_frames']
            and abs(hold_ms - spec['hold_ms']) <= spec['maximum_hold_error_ms']
            and resumed['state'] == 'running' and held['recorderState'] == request['recorderState'] == 'recording'
            and held['state'] == request['state'] == ('suspended' if mode == 'paused' else 'running')),
        'complete_finite_worklet_copy': (np.isfinite(pcm).all() and rows[:, 2].sum() == len(pcm)
                                         and np.all(rows[:-1, 2] == quantum) and 0 < rows[-1, 2] <= quantum
                                         and rows[0, :2].tolist() == [armed['contextFrame'], armed['engineFrame']]),
    }
    result = {'hold_wall_ms': list(wall_time), 'hold_ms': hold_ms,
              'suspend_frame': held['frame'], 'resume_request_frame': request['frame'],
              'pause_candidate_frame': candidate_equivalent, 'plan_start_context_frame': planned_context,
              'maximum_callback_gap_ms': int(rows[i + 1, 3] - rows[i, 3]),
              'maximum_gap_context_frames': rows[i:i + 2, 0].tolist(),
              'context_contiguous': bool(np.all(np.diff(rows[:, 0]) == quantum)),
              'engine_contiguous': bool(np.all(np.diff(rows[:, 1]) == quantum)),
              'trimmed_samples': len(pcm) - trim, 'pcm_start_trim_samples': trim}
    return checks, result, pcm[trim:]


def controlled_states(report, control, spec, target, study):
    rate = spec['output_rate_hz']
    received, applied = report['scheduleReceived'], report['scheduleApplied']
    lead = round(0.03 * rate)
    input_samples = control['trimmed_samples'] + control['pcm_start_trim_samples']
    frames_and_states = [(round(state['clock'] * rate), state) for state in report['stateSnapshots']]
    selected = [(frame, state) for frame, state in frames_and_states if target < frame <= target + input_samples]
    frames = [frame for frame, _ in selected]
    states = [state for _, state in selected]
    fields = ('artic', 'phAreas', 'orAreas', 'pressureRms', 'flow', 'glottalArea', 'glottalFlow',
              'f0', 'voicing', 'pLung', 'outRms', 'noiseLevel', 'noiseNode', 'gate', 'velumPort')
    finite = all(np.isfinite(np.asarray(state[key], dtype=float)).all() for state in states for key in fields)
    checks = {
        'schedule_waited_for_exact_engine_frame': (
            received['receivedFrame'] <= received['target'] == applied['appliedFrame'] == target
            and report['armed']['engineFrame'] == target
            and round(report['armed']['offset'] * rate) == target + lead),
        'complete_state_snapshots': (len(frames) >= study['minimum_state_snapshots'] and finite
                                     and all(b - a == 6 * spec['quantum_frames'] for a, b in zip(frames, frames[1:]))),
        'registered_pcm_length': control['trimmed_samples'] == study['expected_pcm_samples'],
    }
    details = {'received_engine_frame': received['receivedFrame'], 'scheduled_engine_frame': applied['appliedFrame'],
               'lead_frames': control['pcm_start_trim_samples'], 'snapshot_engine_frames': frames}
    return checks, details, states


def measure(case_path, study, candidate, wasm_hash, artifacts, execute):
    spec = {**study['measurement'], 'sample_rate_hz': study['measurement']['output_rate_hz']}
    frame_targets = study.get('schedule_engine_frames')
    if frame_targets is not None:
        case_path = artifacts / 'capture-input.json'
        case_path.write_text(json.dumps(study, ensure_ascii=False, indent=2) + '\n')
    execute(['node', str(CAPTURE), str(case_path), str(artifacts), str(clock.UPSTREAM)], stdout=artifacts / 'safari.log')
    trials, checks, pairs = [], {}, []
    controlled = {}
    for index, order in enumerate(study['condition_order'], 1):
        results = {}
        for mode in order:
            label = f'{index}-{mode}'
            folder = artifacts / label
            row = {'trial': label, 'mode': mode, 'pair': index}
            local = {}
            try:
                report = read_json(folder / 'browser.json')
                if report.get('error'):
                    raise ValueError(report['error'])
                pcm = np.fromfile(folder / 'worklet.f32le', dtype='<f4')
                local, control, reference = graph(report, mode, pcm, study['score'], spec, wasm_hash)
                row['graph'] = control
                states = []
                if frame_targets is not None:
                    state_checks, row['fixed_schedule'], states = controlled_states(
                        report, control, spec, frame_targets[index - 1], study)
                    local.update(state_checks)
                tracks, frames = clock.decode_media_files(folder / 'recording.mp4', folder, execute)
                audio_checks, audio = clock.decode_audio(frames['audio'], tracks['audio'], reference, folder, spec)
                video_checks, video = clock.decode_video(frames['video'], tracks['video'], folder, report, control, spec,
                                                        size=(720, 1280))
                local.update(audio_checks, **video_checks)
                row.update(audio=audio, video=video)
                if all(local.values()):
                    results[mode] = row, reference, states
            except (OSError, KeyError, ValueError, TypeError, StopIteration, subprocess.CalledProcessError) as error:
                local['completed'] = False
                row['error'] = str(error)
            checks.update({f'{label}/{key}': bool(value) for key, value in local.items()})
            trials.append(row)
        if len(results) == 2:
            (normal, a, normal_states), (paused, b, paused_states) = (results[mode] for mode in ('continuous', 'paused'))
            samples = min(len(a), len(b))
            pcm_diff = np.flatnonzero(a[:samples].view('<u4') != b[:samples].view('<u4'))
            g, video = paused['graph'], paused['video']
            a_lag, b_lag = normal['audio'], paused['audio']
            deltas = {key: b_lag[key] - a_lag[key] for key in ('sample_lag_shift_seconds', 'pts_lag_shift_seconds')}
            pair = {'pair': index, 'compared_pcm_samples': samples, 'pcm_bit_differences': len(pcm_diff),
                          'first_pcm_bit_difference': int(pcm_diff[0]) if len(pcm_diff) else None,
                          'maximum_pcm_difference': float(np.max(np.abs(a[:samples] - b[:samples]))),
                          'audio_pause_delta_seconds': deltas, 'predictions': {
                              'continued_graph_after_hold': (g['context_contiguous'] and g['engine_contiguous']
                                  and g['suspend_frame'] == g['resume_request_frame']
                                  and g['maximum_gap_context_frames'] == [g['suspend_frame'] - spec['quantum_frames'],
                                                                          g['suspend_frame']]),
                              'audio_clock_omits_hold': all(abs(delta) <= spec['audio_pause_tolerance_seconds']
                                                            for delta in deltas.values()),
                              'video_clock_shortens_hold': (video['hold_distinct_wall_codes'] >= spec['video_minimum_context_hold_frames']
                                  and video['hold_distinct_context_codes'] == 1
                                  and video['hold_pts_span_seconds'] <= spec['video_maximum_retained_hold_seconds'])}}
            if frame_targets is not None:
                frame = frame_targets[index - 1]
                control = min(row['graph']['pause_candidate_frame'] for row in (normal, paused))
                shift = round((study['score']['candidate_first_beat_seconds'] - study['score']['first_beat_seconds'])
                              * spec['sample_rate_hz'])
                controlled[frame] = a, control - shift
                pair.update(scheduled_engine_frame=frame, compared_state_snapshots=len(normal_states))
                pair['predictions'].update(
                    pcm_bit_equal_after_hold=len(a) == len(b) and not len(pcm_diff),
                    state_snapshots_equal=normal_states == paused_states)
            pairs.append(pair)
    result = {'checks': checks, 'trials': trials, 'pairs': pairs, 'candidate_reference': candidate}
    if frame_targets is not None:
        control = None
        if len(controlled) == 2:
            (early, hold_a), (late, hold_b) = (controlled[target] for target in sorted(controlled))
            differences = np.flatnonzero(np.abs(early - late) > study['positive_control_pcm_difference'])
            first = int(differences[0]) if len(differences) else None
            control = {'first_sample_over_tolerance': first, 'earliest_hold_sample': min(hold_a, hold_b),
                       'prediction': first is not None and first < min(hold_a, hold_b)}
        result['one_quantum_control'] = control
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = read_json(case_path)
    revision = study['upstream_revision']
    control_inputs = []
    if frames := study.get('schedule_engine_frames'):
        reference_info = study['reference']
        original_path = CASE.parent / reference_info['case']
        original_case = read_json(original_path)
        observed_run = run_manifest(reference_info['run'], original_case['id'], revision)
        baseline = verified_path(observed_run, 'summary.json')
        original = read_json(baseline)['pairs']
        quantum = original_case['measurement']['quantum_frames']
        if (observed_run[1]['status'] != 'pass' or len(frames) != len(study['condition_order']) or len(frames) != 2
                or any(frame <= 0 or frame % quantum for frame in frames) or frames[1] - frames[0] != quantum
                or not any(p['pcm_bit_differences'] == 0 for p in original)
                or not any(p['pcm_bit_differences'] > 0 for p in original)):
            parser.error('固定位置の条件または上流の前回結果が揃いません')
        study = {**original_case, **study}
        control_inputs = [original_path, observed_run[0] / 'manifest.json', baseline]
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=clock.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=clock.UPSTREAM, text=True)
            or not study['condition_order'] or any(sorted(order) != ['continuous', 'paused'] for order in study['condition_order'])):
        parser.error('上流または対照の条件が一致しません')
    ref = study['candidate_reference']
    reference_case = CASE.parent / ref['case']
    original = read_json(reference_case)
    run = run_manifest(ref['run'], original['id'], revision)
    reference = verified_path(run, 'summary.json')
    result = read_json(reference)
    if (run[1]['status'] != 'pass' or result['predictions']['audio_pts_preserves_wall_pause']
            or not result['predictions']['suspension_frozen_and_resume_consecutive']
            or study['measurement']['candidate_target_output_frames'] != original['mid_song_pause']['target_output_frame']
            or study['measurement']['hold_ms'] != original['mid_song_pause']['hold_ms']):
        parser.error('研究版の停止付き録画を照合できません')
    candidate = {'run': ref['run'], 'pairs': result['pairs'], 'paused_video_steady_pts_spans': [
        values[-1] - values[0] for trial in result['trials'] if trial['mode'] == 'paused'
        and (values := trial['video']['steady_at_pause_pts_seconds'])]}
    upstream_sources = ['src/ui/components/SingPanel.tsx', 'src/ui/singing.ts', 'src/audio/AudioEngine.ts',
                        'src/song/record.ts', 'src/worklet/processor.ts', 'src/wasm/chimera.wasm', 'bun.lock']
    sources = [clock.UPSTREAM / source for source in upstream_sources]
    wasm_hash = sha256(clock.UPSTREAM / 'src/wasm/chimera.wasm')
    commands = {'safaridriver': ['/usr/bin/safaridriver', '--version'], 'node': ['node', '--version'],
                'ffmpeg': ['ffmpeg', '-version'], 'ffprobe': ['ffprobe', '-version']}
    details = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv], 'fixed_wasm_sha256': wasm_hash,
               **{k: subprocess.check_output(v, text=True).splitlines()[0] for k, v in commands.items()}}
    inputs = [case_path, reference_case, run[0] / 'manifest.json', reference, Path(__file__).resolve(), CAPTURE,
              CAPTURE.with_name('safari-webdriver.mjs'), Path(clock.__file__), Path(clock.recording.__file__),
              *control_inputs, *sources]
    return record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case_path, study, candidate, wasm_hash, artifacts, execute),
        command=None, input_root=clock.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
