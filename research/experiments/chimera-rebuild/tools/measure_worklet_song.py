"""ブラウザの英語歌唱をCLI、固定上流、音高と開大の独立計算に照合する。"""

import argparse
import gzip
from hashlib import sha256 as bytes_digest
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as voice
import measure_song_voice as song
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
import measure_wasm_fixed as wasm
import measure_worklet_realtime as realtime
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-song-voice.json'
LIVE_CASE = WORKSPACE / 'cases/worklet-live-song.json'
DICTIONARY = WORKSPACE / 'data/cmudict.txt.gz'
UPSTREAM_DICTIONARY = UPSTREAM / 'public/data/cmudict.txt.gz'
EMPTY_LYRICS_ERROR = '音符に割り当てる歌詞の音節がありません'


def read_observations(report, limits, frames, live=False):
    columns = report['columns']
    fields = limits['observed_fields']
    clock = 'output_frame' if live else 'context_frame'
    if columns[:2] != [clock, 'frames_rendered'] or any(field not in columns for field in fields):
        raise ValueError('ブラウザの観測列が登録条件と一致しません')
    stride = limits['observation_stride_frames']
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    rows = np.asarray(report['observations'], dtype=float)
    if rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all():
        raise ValueError('ブラウザの観測点数または有限性が登録条件と一致しません')
    if not np.array_equal(rows[:, 0], points) or not np.array_equal(rows[:, 1], points + 1):
        raise ValueError('ブラウザの観測時刻が登録条件と一致しません')
    trace = np.empty(len(points), dtype=[('frame', int), *((field, float) for field in fields)])
    trace['frame'] = points
    for field in fields:
        trace[field] = rows[:, columns.index(field)]
    return trace


def acoustic_evidence(audio, trace, rate, limits, release):
    pitches = []
    for left, right, midi in limits['f0_windows']:
        wave = audio[round(left * rate):round(right * rate)].astype(float)
        hz, error = vowel.independent_yin(wave, rate, limits)
        target = 440 * 2**((midi - 69) / 12)
        pitches.append({'window_seconds': [left, right], 'midi': midi, 'target_hz': target,
                        'pcm_yin_hz': hz, 'yin_normalized_difference': error,
                        'passed': hz is not None and abs(hz - target) <= limits['yin_midi_tolerance_hz']})
    cents = 1200 * np.log2(trace['glottal_f0_hz'] / trace['smoothed_f0_hz'])
    max_cents = float(abs(cents).max())
    tail_peak = float(abs(audio[-round(limits['final_silence_seconds'] * rate):]).max())
    time = (trace['frame'] + 1) / rate
    samples = []
    for target in (release['held_breath_at_seconds'], release['released_breath_at_seconds']):
        i = time.searchsorted(target)
        samples.append({'requested_seconds': target, 'observed_seconds': float(time[i]),
                        'gate': float(trace['gate'][i]), 'abduction_cm2': float(trace['abduction_cm2'][i])})
    held, stopped = samples
    lo, hi = limits['vibrato_abs_max_cents_bounds']
    checks = {
        'browser_pitch': all(pitch['passed'] for pitch in pitches),
        'browser_vibrato': lo <= max_cents <= hi,
        'browser_release_and_silence': (
            held['gate'] >= release['minimum_gate_during_opening']
            and held['abduction_cm2'] >= release['minimum_abduction_cm2_during_opening']
            and stopped['gate'] <= release['maximum_released_gate']
            and tail_peak <= limits['final_max_peak_pcm']),
    }
    return checks, {'pitch': pitches, 'vibrato_max_abs_cents': max_cents,
                    'tail_pcm_peak': tail_peak, 'release': samples}


def first_differences(candidate, reference, fields):
    differences = {}
    for field in fields:
        first = wasm.first_index(candidate[field] != reference[field])
        if first is not None:
            differences[field] = {'frame': int(candidate['frame'][first]),
                                  'absolute_error': float(abs(candidate[field][first] - reference[field][first]))}
    return differences


def live_evidence(case, live_case, prior, artifacts, execute, browser, report, audio, expected_input, cli_states,
                  *, allocation_log=None):
    m = case['measurement']
    spec = live_case['measurement']
    stop = browser['stop']
    stopped = (stop['contextState'] == 'closed' and stop['ready'] and stop['replayed']
               and stop['connectedSeconds'] >= spec['stop_after_connected_seconds'])
    checks, result = realtime.compare_scored_capture(
        spec, case, artifacts, browser, report, audio, ('input', 'song', 'gestures'), stopped)
    checks['registered_last_quantum'] = (
        report['callbacks'] == spec['expected_active_callbacks']
        and result['last_quantum_padded_frames'] == spec['expected_last_quantum_padded_frames'])
    baseline_wave = verified_path(prior, 'artifacts/browser.wav')
    baseline_observation = wasm.read_json(verified_path(prior, 'artifacts/browser.json'))
    offline_observation = wasm.read_json(artifacts / 'offline.json')
    # 旧形式で体型が暗黙だった成人男性を補い、全観測値と構成を厳密に照合する。
    baseline_defaulted = 'body' not in baseline_observation
    baseline_observation.setdefault('body', 'male')
    wave_matches = sha256(baseline_wave) == sha256(artifacts / 'offline.wav')
    observations_match = baseline_observation == offline_observation
    checks['fixed_offline_baseline'] = wave_matches and observations_match
    result['fixed_offline_reference'] = {
        'wave_byte_equal': wave_matches,
        'observation_equal': observations_match,
        'legacy_body_defaulted': baseline_defaulted,
    }
    checks['live_cli_state_equality'] = all(
        field['first_difference_frame'] is None for field in cli_states.values())

    if allocation_log is None:
        allocation_log = artifacts / 'native-allocations.log'
        capture_allocations(execute, allocation_log)
    result['native_allocations'] = realtime.read_quantum_allocations(
        allocation_log, 'song_render_allocations=', m['output_frames'], m['expected_render_quantum_frames'],
        spec['timing_exclude_first_blocks'])
    # 拍の位置はスコアの入力を秒に換算し、AudioContextの起点へ独立に写す。
    beat_seconds = expected_input['start_seconds'] + (
        np.cumsum([0.0, *(n['beats'] for n in expected_input['notes'][:-1])]) * 60 / expected_input['bpm'])
    frames = np.rint(beat_seconds * m['output_rate_hz']).astype(int)
    result['beat_output_frames'] = frames.tolist()
    result['beat_context_frames'] = (frames + result['context_start_frame']).tolist()
    planned = [note['beat_seconds'] for note in report['song']['plan']['notes']]
    checks['independent_absolute_beat_positions'] = (
        len(planned) == len(frames)
        and np.array_equal(np.rint(np.asarray(planned) * m['output_rate_hz']).astype(int), frames))
    return checks, result


def capture_allocations(execute, log):
    execute(['cargo', 'test', '--locked', '-p', 'vocal-wasm', 'song_render_allocation_profile',
             '--', '--nocapture'], stdout=log)


def compare(source, case, artifacts, execute, bun, raw_dictionary, live_case, prior, case_path=CASE, turbulence_scale=None):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    if turbulence_scale is not None:
        settings = wasm.read_json(source)
        settings['song_voice']['turbulence'] = {'scale': turbulence_scale}
        source = artifacts / 'turbulence-input.json'
        source.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
    browser_command = ['node', str(CAPTURE), str(artifacts), str(case_path), str(source)]
    if raw_dictionary:
        browser_command.append(str(DICTIONARY))
    if live_case:
        browser_command.append(f'--live={LIVE_CASE}')
    execute(browser_command)
    result = compare_capture(source, case, artifacts, execute, raw_dictionary, live_case, prior, binary=binary)
    if turbulence_scale is not None:
        replay = wasm.read_json(artifacts / 'browser-case.json')['song_voice']
        result['checks']['replayed_turbulence_scale'] = replay['turbulence']['scale'] == turbulence_scale
    return result


def compare_capture(source, case, artifacts, execute, raw_dictionary, live_case, prior, *, binary,
                    references=None, allocation_log=None, rejection_contains=EMPTY_LYRICS_ERROR):
    m = case['measurement']
    rate, frames, quantum = (m[k] for k in ('output_rate_hz', 'output_frames', 'expected_render_quantum_frames'))
    config = wasm.read_json(source)
    limits = config['measurement']
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')
    if references is None:
        references = voice.capture(source, limits['host_block_frames'], artifacts, execute, song.SUITES)
    cli, cli_path, files, upper_path, upper_pcm, upper_plan_path = references
    reference = timing.read(upper_plan_path)
    native_rate, native = wavfile.read(files[0][0])
    upper = np.fromfile(upper_pcm, dtype='<f4')
    for signal in (audio, native, upper):
        if signal.shape != (frames,) or signal.dtype != np.float32 or not np.isfinite(signal).all():
            raise ValueError('歌唱PCMの型・フレーム数・有限性が登録条件と一致しません')
    pcm_cli = wasm.compare_pcm(audio, native, limits['pcm_absolute_tolerance'])
    pcm_upper = wasm.compare_pcm(audio, upper, limits['pcm_absolute_tolerance'])

    tolerance = m['score_numeric_tolerance']
    score = config['song_voice']['score']
    expected_input = {key: score[key] for key in ('lyrics', 'notes', 'bpm', 'start_seconds', 'id')}
    expected_input['vibrato_cents'] = config['song_voice']['vibrato_cents']
    input_difference, _ = timing.compare(report['input'], expected_input, tolerance)
    plan_difference, plan_error = timing.compare(report['song'], cli['song'], tolerance)
    gesture_difference, gesture_error = timing.compare(report['gestures'], cli['gestures'], tolerance)
    beats = [note['beat_seconds'] for note in report['song']['plan']['notes']]
    beat_difference, _ = timing.compare(beats, m['expected_beat_seconds'], tolerance)
    browser_score = {**cli, 'song': report['song'], 'gestures': report['gestures']}
    segments, upper_plan = song.compare_plans(browser_score, reference, limits)

    trace = read_observations(report, m, frames, live=bool(live_case))
    fields = m['observed_fields']
    points = trace['frame']
    native_trace, upper_trace = [voice.load_trace(p, frames) for p in (cli_path, upper_path)]
    cli_states = wasm.compare_states(np.column_stack([trace[k] for k in fields]),
                                     np.column_stack([native_trace[k][points] for k in fields]),
                                     fields, points, m['candidate_trace_peak_relative_tolerance'])
    # 共通比較器に渡す系列は採取した点だけなので、差の添字を出力フレームに戻す。
    sampled_upper = upper_trace[['frame', *fields]][points]
    upper_first, upper_states = voice.compare_traces(trace, sampled_upper, limits)
    if upper_first is not None:
        upper_first['frame'] = int(points[upper_first['frame']])
    dense_fields = [*fields, 'lip_area_cm2', 'lip_flow_cm3_s', 'oral_cell_0_minimum_cm2']
    # 独立式は制御更新の全区間を確認し、Workletとは同じフレームの状態を照合する。
    controls = song.independent_controls(native_trace, browser_score, config, rate)
    upper_events = song.observe(upper_trace, upper, segments, rate, limits)
    acoustic_checks, measured = acoustic_evidence(audio, trace, rate, limits, m['expected_release_checks'])
    compressed_hash = sha256(DICTIONARY)
    expanded_hash = bytes_digest(gzip.decompress(DICTIONARY.read_bytes())).hexdigest()
    received_gzip = browser['dictionaryResponseIsGzip']
    expected_dictionary_hash = compressed_hash if received_gzip else expanded_hash
    checks = {
        'browser_input_and_assets': (input_difference is None and not browser['errors']
            and browser['servedWasmSha256'] == sha256(binary)
            and browser['dictionaryResponseSha256'] == expected_dictionary_hash
            and compressed_hash == sha256(UPSTREAM_DICTIONARY)),
        'sample_format': (report['sampleRate'] == report['workletSampleRate'] == browser_rate == native_rate == rate
            and report['outputFrames'] == report['framesRendered'] == cli['output_frames']
            == reference['output_frames'] == frames and report['outputChannels'] == 1
            and cli['decimation_factor'] * rate == m['internal_rate_hz']),
        'cli_plan_and_gestures': plan_difference is None and gesture_difference is None and beat_difference is None,
        'upstream_and_registered_plan': upper_plan['passed'],
        'worklet_clock': (report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['discontinuities'] == 0
            and report['firstContextFrame'] == (report['realtime']['scheduledContextFrame'] if live_case else 0)
            and report['callbacks'] == (frames + quantum - 1) // quantum),
        'cli_pcm_bit_equality': pcm_cli['first_bit_difference_frame'] is None,
        'upstream_pcm': pcm_upper['first_frame_over_tolerance'] is None,
        'cli_observed_state': all(value['status'] for value in cli_states.values()),
        'upstream_observed_state': upper_first is None,
        'independent_controls_and_upstream_events': controls['passed'] and upper_events['passed'],
        'cli_partitions': all(sha256(a) == sha256(b) for a, b in zip(*files, strict=True)),
        **acoustic_checks,
    }
    if m['check_unrenderable_lyric_then_recover']:
        rejected = browser['rejected'] or ''
        checks['unrenderable_lyric_then_recover'] = rejection_contains in rejected and browser['recovered']
    if raw_dictionary:
        checks['raw_gzip_dictionary'] = received_gzip and browser['dictionaryContentEncoding'] is None
    live = {}
    if live_case:
        live_checks, evidence = live_evidence(
            case, live_case, prior, artifacts, execute, browser, report, audio, expected_input, cli_states,
            allocation_log=allocation_log)
        checks.update(live_checks)
        live['realtime'] = evidence
    return {'checks': checks, 'browser': browser, 'frames': frames, 'observations': len(points),
            'dictionary_sha256': {'compressed': compressed_hash, 'expanded': expanded_hash},
            'callbacks': report['callbacks'], 'wasm_memory_growths': report['wasmMemoryGrowths'],
            'beats_seconds': beats, 'input_difference': input_difference,
            'cli_plan_first_difference': plan_difference, 'cli_plan_max_abs_error': plan_error,
            'cli_gesture_first_difference': gesture_difference, 'cli_gesture_max_abs_error': gesture_error,
            'upstream_plan': upper_plan, 'cli_pcm': pcm_cli, 'upstream_pcm': pcm_upper,
            'cli_states': cli_states, 'upstream_states': upper_states,
            'upstream_first_state_difference_over_tolerance': upper_first,
            'upstream_first_difference_by_field': first_differences(trace, sampled_upper, fields),
            'upstream_cli_first_difference_by_field': first_differences(native_trace, upper_trace, dense_fields),
            'independent_cli_controls': controls, 'upstream_events': upper_events, 'browser_events': measured,
            **live}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='歌唱Workletの比較ケースを指定する')
    parser.add_argument('--turbulence-scale', type=float, help='同じ歌唱入力の乱流係数だけを変更する')
    parser.add_argument('--live', action='store_true', help='AudioContextでの開始予約・歌唱・停止も検査する')
    parser.add_argument('--raw-dictionary', action='store_true',
                        help='ブラウザにContent-Encodingなしのgzip辞書を渡す')
    args = parser.parse_args()
    if args.turbulence_scale is not None and (not math.isfinite(args.turbulence_scale) or args.turbulence_scale < 0):
        parser.error('乱流係数は有限で0以上の値を指定してください')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = args.case.resolve(strict=True)
    case = wasm.read_json(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['song_voice_case']
    live_case = wasm.read_json(LIVE_CASE) if args.live else None
    prior = None
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [source, case_path, Path(__file__).resolve(), voice.PROBE, *shared.candidate_sources(), *web_sources(),
              *(Path(tool.__file__) for tool in (voice, song, timing, shared, vowel, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                 'measure_pcm_output.py', 'measure_junction.py', 'measure_sibilant.py', 'measure_alveolar_stop.py'))]
    upper_paths = ['public/data/cmudict.txt.gz', 'src/ui/singing.ts', 'src/wasm/engine.ts',
                   'crates/chimera-wasm/src/api.rs', 'crates/chimera/src/phonetics/sing.rs',
                   'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/engine.rs',
                   'crates/chimera/tests/sung_release.rs', 'crates/chimera/tests/sing_fast.rs',
                   'crates/chimera/tests/engine.rs']
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'raw_dictionary': args.raw_dictionary,
                'turbulence_seed': 12345,
                'turbulence_scale': (args.turbulence_scale if args.turbulence_scale is not None else
                                     wasm.read_json(source)['song_voice'].get('turbulence', {}).get('scale', 1)),
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'web_diff_status': subprocess.check_output(
                    ['git', 'status', '--porcelain', '--', str(WEB)], cwd=ROOT, text=True).strip(),
                'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upper_paths}}
    if live_case:
        if live_case['upstream_revision'] != revision or live_case['song_case'] != case_path.name:
            parser.error('実時間のケースと固定上流版または歌唱ケースが一致しません')
        ref = live_case['reference']
        prior = run_manifest(ref['offline_run'], case['id'], revision)
        manifest_path = prior[0] / 'manifest.json'
        if sha256(manifest_path) != ref['offline_manifest_sha256'] or prior[1]['status'] != 'pass':
            parser.error('オフラインの基準マニフェストを照合できません')
        inputs.extend([manifest_path, *(verified_path(prior, f'artifacts/browser.{suffix}')
                                      for suffix in ('wav', 'json')),
                       Path(realtime.__file__), WORKSPACE / 'tools/measure_fan_crossing_allocations.py'])
        metadata.update(case_id=live_case['id'], reference_offline=ref['offline_run'])
    return shared.record_measurement(args.run_id, LIVE_CASE if live_case else case_path, inputs, metadata,
                                     lambda out, run: compare(
                                         source, case, out, run, bun, args.raw_dictionary, live_case, prior, case_path,
                                         args.turbulence_scale),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
