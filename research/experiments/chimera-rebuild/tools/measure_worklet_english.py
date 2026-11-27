"""英語テキストのブラウザ発話をCLI、固定上流、波形からの測定に照合する。"""

import argparse
import gzip
import hashlib
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-english-voice.json'
DICT = WORKSPACE / 'data/cmudict.txt.gz'
UPPER_DICT = UPSTREAM / 'public/data/cmudict.txt.gz'


def observe(pcm, track, limits, rate):
    def wave(start, end):
        return pcm[round(start * rate):round(end * rate)]

    time = (track['frame'] + 1) / rate
    left, right = limits['nasal_seconds']
    nasal_window = (time >= left) & (time < right)
    nasal = {
        'seconds': limits['nasal_seconds'],
        'port_peak_cm2': float(track['velum_port_area_cm2'][nasal_window].max()),
        'nose_peak_cm3_s': float(abs(track['nose_flow_cm3_s'][nasal_window]).max()),
    }
    pitch = []
    for window in limits['pitch_windows']:
        left, right = window['seconds']
        hz, error = vowel.independent_yin(wave(left, right).astype(float), rate, limits)
        lo, hi = window['bounds_hz']
        pitch.append({'seconds': [left, right], 'yin_hz': hz, 'yin_normalized_difference': error,
                      'median_glottal_f0_hz': float(np.median(track['glottal_f0_hz'][(time >= left) & (time < right)])),
                      'passed': hz is not None and lo <= hz <= hi})
    quiet = []
    for window in limits['quiet_windows']:
        peak = float(abs(wave(*window['seconds'])).max())
        quiet.append({**window, 'pcm_peak': peak, 'passed': peak <= window['maximum_pcm']})
    checks = {
        'measured_nasal': nasal['port_peak_cm2'] >= limits['minimum_nasal_port_area_cm2']
                          and nasal['nose_peak_cm3_s'] >= limits['minimum_nose_peak_cm3_s'],
        'measured_pitch': all(p['passed'] for p in pitch),
        'measured_quiet_windows': all(q['passed'] for q in quiet),
    }
    return checks, {'nasal': nasal, 'pitch': pitch, 'quiet': quiet}


def compare_plan(report, cli, upper, limits, original):
    tolerance = limits['plan_numeric_tolerance']
    plan_delta, plan_error = timing.compare(report['speech'], cli['speech'], tolerance)
    gesture_delta, gesture_error = timing.compare(report['gestures'], cli['gestures'], tolerance)
    plan = report['speech']
    phrases = plan['phrases']
    upper_input = {'speech': {'utterances': [p['timing'] for p in phrases]}, 'gestures': report['gestures']}
    _, upper_check = speech.compare_plans(upper_input, upper, tolerance)
    pauses = [right['start_seconds'] - left['end_seconds'] for left, right in zip(phrases, phrases[1:])]
    pitch_targets = [row['pitch'][-1]['targets']['f0_hz'] for row in phrases]
    source = [item for row in phrases for item in row['sources']]
    words = [word for row in phrases for word in row['words']]
    checks = {
        'cli_plan_and_gestures': plan_delta is None and gesture_delta is None,
        'upstream_plan_and_gestures': upper_check['passed'],
        'registered_phrases': (words == limits['expected_words'] and source == ['dictionary'] * len(words)
            and [row['intonation'] for row in phrases] == limits['expected_intonation']
            and plan['shown'] == original['expected_summary']
            and timing.compare(pauses, [limits['inter_phrase_pause_seconds']], tolerance)[0] is None
            and abs(plan['render_end_seconds'] - plan['end_seconds'] - original['tail_seconds']) <= tolerance
            and timing.compare(pitch_targets, original['pitch_targets_hz'], tolerance)[0] is None),
    }
    return checks, {'shown': plan['shown'], 'pitch_targets_hz': pitch_targets, 'pauses_seconds': pauses,
                    'dictionary_sources': source, 'plan_first_difference': plan_delta,
                    'gesture_first_difference': gesture_delta, 'maximum_plan_checked_error': plan_error,
                    'maximum_gesture_checked_error': gesture_error, 'upstream': upper_check}


def compare(source, case, artifacts, execute, bun):
    limits = case['measurement']
    rate, internal, frames, quantum, stride = (
        limits[key] for key in ('output_rate_hz', 'internal_rate_hz', 'output_frames',
                                'expected_render_quantum_frames', 'observation_stride_frames'))
    baseline = wasm.read_json(source)
    original = baseline['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source)])
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')
    cli, native_path, files, upper_path, upper_pcm_path, upper_report = voice.capture(
        source, original['host_block_frames'], artifacts, execute, ('english', 'golden_phonetics_text', 'consonant_artifacts', 'engine'))
    cli_rate, native_audio = wavfile.read(files[0][0])
    upper_audio = np.fromfile(upper_pcm_path, dtype='<f4')
    upper = wasm.read_json(upper_report)
    if any(a.shape != (frames,) or a.dtype != np.float32 or not np.isfinite(a).all() for a in (audio, native_audio, upper_audio)):
        raise ValueError('PCMの長さ、型または有限性が登録条件と一致しません')
    native_pcm = wasm.compare_pcm(audio, native_audio, 0)
    upper_pcm = wasm.compare_pcm(audio, upper_audio, original['pcm_absolute_tolerance'])
    plan_checks, plan = compare_plan(report, cli, upper, limits, original)

    fields = limits['observed_fields']
    columns = report['columns']
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    rows = np.asarray(report['observations'], dtype=float)
    if (columns[:2] != ['context_frame', 'frames_rendered'] or any(k not in columns for k in fields)
            or rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all()):
        raise ValueError('観測列、長さまたは有限性が登録条件と一致しません')
    trace = np.empty(len(points), dtype=[('frame', int), *((name, float) for name in fields)])
    trace['frame'] = points
    for name in fields:
        trace[name] = rows[:, columns.index(name)]
    native_trace, upper_trace = [voice.load_trace(p, frames) for p in (native_path, upper_path)]
    cli_states = wasm.compare_states(np.column_stack([trace[k] for k in fields]),
                                     np.column_stack([native_trace[k][points] for k in fields]),
                                     fields, points, limits['candidate_trace_peak_relative_tolerance'])
    trace_limits = {'geometry_absolute_tolerance': original['geometry_absolute_tolerance'],
                    'audio_state_peak_relative_tolerance': original['trace_peak_relative_tolerance']}
    difference, upper_states = voice.compare_traces(trace, upper_trace[['frame', *fields]][points], trace_limits)
    if difference is not None:
        difference['frame'] = int(points[difference['frame']])
    first = []
    for name in native_trace.dtype.names[1:]:
        index = wasm.first_index(native_trace[name] != upper_trace[name])
        if index is not None:
            first.append((index, name, float(native_trace[name][index] - upper_trace[name][index])))
    first.sort()
    first_trace = [{'frame': index, 'field': name, 'cli_minus_upstream': delta} for index, name, delta in first
                   if index == first[0][0]]

    outcome_checks, evidence = observe(audio, trace, limits, rate)
    compressed = sha256(DICT)
    expanded = hashlib.sha256(gzip.decompress(DICT.read_bytes())).hexdigest()
    reply_hash = compressed if browser['dictionaryResponseIsGzip'] else expanded
    checks = {
        'browser_input_and_assets': (report['input'] == baseline['speech_voice']['input']['text']
            and report['caseId'] == baseline['id'] and browser['shown'] == original['expected_summary']
            and not browser['errors'] and browser['servedWasmSha256'] == sha256(binary)
            and browser['dictionaryResponseSha256'] == reply_hash and compressed == sha256(UPPER_DICT)),
        'format_and_rate': (report['sampleRate'] == report['workletSampleRate'] == browser_rate == cli_rate == rate
            and report['outputFrames'] == report['framesRendered'] == cli['output_frames'] == upper['output_frames'] == frames
            and report['outputChannels'] == 1 and cli['decimation_factor'] * rate == internal),
        'worklet_clock': (report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['firstContextFrame'] == report['discontinuities'] == 0
            and report['callbacks'] == (frames + quantum - 1) // quantum
            and np.array_equal(rows[:, 0], points) and np.array_equal(rows[:, 1], points + 1)),
        'cli_pcm_bit_equality': native_pcm['first_bit_difference_frame'] is None,
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'cli_observed_states': all(value['status'] for value in cli_states.values()),
        'upstream_observed_states': difference is None
            and upper_states['velum_port_area_cm2']['absolute'] <= original['geometry_absolute_tolerance'],
        'cli_partition_invariance': all(sha256(a) == sha256(b) for a, b in zip(*files, strict=True)),
        'unsupported_then_retry': (browser['recovered'] and '未対応' in (browser['rejected'] or '')
                                   and limits['unrenderable_symbol'] in (browser['rejected'] or '')),
        **plan_checks, **outcome_checks,
    }
    return {'checks': checks, 'browser': browser, 'frames': frames, 'observations': len(points),
            'observed_fields': fields, 'plan': plan, 'cli_pcm': native_pcm, 'upstream_pcm': upper_pcm,
            'cli_states': cli_states, 'upstream_states': upper_states, 'first_state_over_tolerance': difference,
            'first_cli_upstream_track_differences': first_trace, 'browser_events': evidence}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['english_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, source, Path(__file__).resolve(), voice.PROBE, *shared.candidate_sources(), *web_sources(),
              *(Path(m.__file__) for m in (voice, speech, timing, shared, vowel, wasm)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                                                       'measure_pcm_output.py', 'measure_junction.py'))]
    upstream_paths = ('src/ui/speech.ts', 'src/wasm/engine.ts', 'crates/chimera-wasm/src/api.rs',
                      'crates/chimera/src/phonetics/english.rs', 'crates/chimera/src/phonetics/planner.rs',
                      'crates/chimera/tests/english.rs', 'crates/chimera/tests/golden_phonetics_text.rs',
                      'crates/chimera/tests/engine.rs', 'crates/chimera/tests/consonant_artifacts.rs',
                      'tests/words.test.ts', 'public/data/cmudict.txt.gz')
    metadata = {'case_id': case['id'], 'case_revision': case.get('revision', 1),
                'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'upstream_source_sha256': {p: sha256(UPSTREAM / p) for p in upstream_paths}}
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
                                     lambda out, run: compare(source, case, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
