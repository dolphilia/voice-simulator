"""ブラウザのIPA計画と発声をCLI、固定上流の音素区間・声道・PCMに照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_bilabial_stop as stop
import measure_glottal_scope as scope
import measure_ipa_timeline as timeline
import measure_pcm_spectrum as spectrum
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
import measure_worklet_live_ipa as live_ipa
import measure_worklet_realtime as realtime
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-ipa-voice.json'
TIMELINE_CASE = WORKSPACE / 'cases/worklet-ipa-timeline.json'
SCOPE_CASE = WORKSPACE / 'cases/worklet-glottal-scope.json'
SPECTRUM_CASE = WORKSPACE / 'cases/worklet-pcm-spectrum.json'
LIVE_CASE = WORKSPACE / 'cases/worklet-live-ipa.json'
SPECTRUM_PROBE = WEB / 'tools/probe-pcm-spectrum.ts'


def compare(source, case, artifacts, execute, bun, display_case=None):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    capture = ['node', str(CAPTURE), str(artifacts), str(CASE)]
    if display_case is not None:
        capture.append(str(display_case))
    execute(capture)
    return compare_capture(source, case, artifacts, execute, bun, display_case, binary=binary)


def compare_capture(source, case, artifacts, execute, bun, display_case=None, *,
                    binary, references=None, allocation_log=None):
    m = case['measurement']
    live = display_case == LIVE_CASE
    rate, internal, frames, quantum, stride = (
        m[k] for k in ('output_rate_hz', 'internal_rate_hz', 'output_frames',
                       'expected_render_quantum_frames', 'observation_stride_frames'))
    report = wasm.read_json(artifacts / 'browser.json')
    browser = wasm.read_json(artifacts / 'browser-run.json')
    browser_rate, audio = wavfile.read(artifacts / 'browser.wav')

    config = wasm.read_json(source)
    limits = config['measurement']
    suites = ('aspiration', 'fast_speech', 'engine')
    if display_case == SPECTRUM_CASE:
        suites += ('airway',)
    if references is None:
        references = stop.capture(source, limits['host_block_frames'], artifacts, execute, suites)
    cli, trace, paths, upper_trace, upper_pcm, upper_plan = references
    reference = timing.read(upper_plan)
    first_rate, native = wavfile.read(paths[0][0])
    upper = np.fromfile(upper_pcm, dtype='<f4')
    if any(signal.shape != (frames,) or signal.dtype != np.float32 for signal in (audio, native, upper)):
        raise ValueError('発話PCMの型またはフレーム数が条件と一致しません')
    pcm_cli = wasm.compare_pcm(audio, native, limits['pcm_absolute_tolerance'])
    pcm_upstream = wasm.compare_pcm(audio, upper, limits['pcm_absolute_tolerance'])

    keys = ('utterances', 'rate', 'render_end_seconds')
    front_end, _ = timing.compare(report['speech'], {k: cli['speech'][k] for k in keys},
                                 m['gesture_absolute_tolerance'])
    gestures, gesture_error = timing.compare(report['gestures'], cli['gestures'],
                                             m['gesture_absolute_tolerance'])
    browser_plan = {**cli, 'speech': report['speech'], 'gestures': report['gestures']}
    stop_span, upstream_plan = stop.stop_gesture_evidence(config, browser_plan, reference)
    cli_state, upstream_state = (stop.load_trace(path, frames) for path in (trace, upper_trace))
    first_upstream_difference = {}
    for field in cli_state.dtype.names[1:]:
        first = wasm.first_index(cli_state[field] != upstream_state[field])
        if first is not None:
            first_upstream_difference[field] = {
                'frame': first,
                'absolute_error': float(abs(cli_state[field][first] - upstream_state[field][first])),
            }
    native_events = stop.events(cli_state, native, cli, stop_span, limits)
    upstream_events = stop.events(upstream_state, upper, cli, stop_span, limits)

    columns = report['columns']
    fields = m['observed_fields']
    clock_column = 'output_frame' if live else 'context_frame'
    if columns[:2] != [clock_column, 'frames_rendered'] or any(key not in columns for key in fields):
        raise ValueError('ブラウザの観測列が登録条件と一致しません')
    points = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    rows = np.asarray(report['observations'], dtype=float)
    if rows.shape != (len(points), len(columns)) or not np.isfinite(rows).all():
        raise ValueError('ブラウザの観測点数または有限性が条件と一致しません')
    state = rows[:, [columns.index(key) for key in fields]]
    cli_cmp = wasm.compare_states(state, np.column_stack([cli_state[k][points] for k in fields]),
                                  fields, points, m['candidate_trace_peak_relative_tolerance'])
    subset = ['frame', *fields]
    observed = np.empty(len(points), dtype=upstream_state[subset].dtype)
    observed['frame'] = points
    for i, key in enumerate(fields):
        observed[key] = state[:, i]
    upper_diff, upper_errors = stop.compare_traces(observed, upstream_state[subset][points], limits)
    closed = observed['lip_minimum_cm2'] < m['closed_area_cm2']
    onset = wasm.first_index(closed)
    release = wasm.first_index(~closed & np.r_[False, closed[:-1]])
    actual_events = [int(points[i]) if i is not None else None for i in (onset, release)]
    expected_events = [m['expected_cli_closure_frame'], m['expected_cli_release_frame']]
    event_delay = m['maximum_sampled_event_delay_frames']

    checks = {
        'browser_input_format_and_wasm': (report['input'] == m['expected_ipa'] and report['caseId'] == config['id']
                   and browser['servedWasmSha256'] == sha256(binary) and not browser['errors']
                   and report['sampleRate'] == report['workletSampleRate'] == browser_rate == first_rate == rate
                   and report['outputFrames'] == report['framesRendered'] == cli['output_frames'] == frames
                   and report['outputChannels'] == 1
                   and cli['decimation_factor'] * rate == internal),
        'cli_ipa_plan': front_end is None and gestures is None,
        'upstream_ipa_plan_and_independent_closure_targets': upstream_plan['passed'],
        'cli_pcm': (pcm_cli['first_bit_difference_frame'] is None if m['require_cli_pcm_bit_equality']
                    else pcm_cli['first_frame_over_tolerance'] is None),
        'upstream_pcm': pcm_upstream['first_frame_over_tolerance'] is None,
        'worklet_clock_and_observations': bool(
            report['shortestQuantum'] == report['longestQuantum'] == quantum
            and (live or report['firstContextFrame'] == 0) and report['discontinuities'] == 0
            and report['callbacks'] == (frames + quantum - 1) // quantum
            and np.array_equal(rows[:, 0], points) and np.array_equal(rows[:, 1], points + 1)),
        'cli_observed_state': all(value['status'] for value in cli_cmp.values()),
        'upstream_observed_state': upper_diff is None,
        'native_and_upstream_stop_events': native_events['passed'] and upstream_events['passed']
            and [native_events.get(k) for k in ('first_closed_frame', 'first_open_frame')] == expected_events,
        'sampled_lip_events': all(v is not None and 0 <= v - expected <= event_delay
                                  for v, expected in zip(actual_events, expected_events, strict=True)),
        'cli_host_partition_invariance': all(sha256(a)==sha256(b) for a,b in zip(*paths, strict=True)),
    }
    if m['check_unrenderable_ipa_then_recover']:
        checks['unrenderable_ipa_then_recover'] = bool(browser['rejected']) and browser['recovered']
    extra = {}
    if display_case == TIMELINE_CASE:
        timeline_checks, evidence = timeline.compare(
            wasm.read_json(artifacts / 'timeline.json'), wasm.read_json(display_case), reference, observed, audio, rate,
            m['closed_area_cm2'])
        checks.update(timeline_checks)
        extra['timeline'] = evidence
    elif display_case == SCOPE_CASE:
        scope_checks, evidence = scope.compare(
            wasm.read_json(display_case)['measurement'], report, wasm.read_json(artifacts / 'glottal-scope.json'),
            cli_state, upstream_state, observed, rate, m['closed_area_cm2'])
        checks.update(scope_checks)
        extra['glottal_scope'] = evidence
    elif display_case == SPECTRUM_CASE:
        execute([*bun, 'run', str(SPECTRUM_PROBE), str(artifacts / 'analytic-spectrum.json')], cwd=WEB)
        spectrum_checks, evidence = spectrum.compare(
            wasm.read_json(display_case)['measurement'], artifacts, wasm.read_json(artifacts / 'pcm-spectrum.json'),
            audio, native, upper, rate, cli_state, m['closed_area_cm2'])
        checks.update(spectrum_checks)
        extra['pcm_spectrum'] = evidence
    elif live:
        if allocation_log is None:
            allocation_log = artifacts / 'native-allocations.log'
            execute(['cargo', 'test', '--locked', '-p', 'vocal-wasm', 'ipa_render_allocation_profile', '--', '--nocapture'],
                    stdout=allocation_log)
        live_checks, evidence = live_ipa.compare(
            wasm.read_json(display_case)['measurement'], case, artifacts, browser, report, audio, actual_events,
            allocation_log=allocation_log)
        checks.update(live_checks)
        extra['realtime'] = evidence
    return {'checks': checks, 'browser': browser['version'], 'frames': frames, 'observations': len(points),
            'wasm_memory_growths': report['wasmMemoryGrowths'], 'cli_pcm': pcm_cli,
            'upstream_pcm': pcm_upstream, 'cli_plan_first_difference': front_end,
            'cli_gestures_first_difference': gestures, 'cli_gestures_max_abs_error': gesture_error,
            'upstream_plan': upstream_plan, 'cli_states': cli_cmp, 'upstream_states': upper_errors,
            'upstream_first_state_difference_over_tolerance': upper_diff,
            'upstream_cli_first_difference_by_field': first_upstream_difference,
            'native_events': native_events, 'upstream_events': upstream_events,
            'browser_closed_and_released_frames': actual_events, **extra}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    display = parser.add_mutually_exclusive_group()
    display.add_argument('--timeline', dest='display_case', action='store_const', const=TIMELINE_CASE,
                         help='発話の時系列表示も照合する')
    display.add_argument('--scope', dest='display_case', action='store_const', const=SCOPE_CASE,
                         help='声門の波形表示も照合する')
    display.add_argument('--spectrum', dest='display_case', action='store_const', const=SPECTRUM_CASE,
                         help='選択時刻のPCMスペクトルも照合する')
    display.add_argument('--live', dest='display_case', action='store_const', const=LIVE_CASE,
                         help='実時間AudioContextの発話を照合する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = wasm.read_json(CASE)
    display_case = args.display_case
    registration = wasm.read_json(display_case) if display_case else case
    if display_case and (registration['ipa_case'] != CASE.name
                         or registration['upstream_revision'] != case['upstream_revision']):
        raise SystemExit('表示ケースが参照する基準を確認してください')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git','status','--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / case['speech_voice_case']
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [source, CASE, Path(__file__).resolve(), stop.PROBE, *shared.candidate_sources(), *web_sources(),
              *(Path(tool.__file__) for tool in (stop, shared, scope, spectrum, timeline, timing, wasm, live_ipa, realtime)),
              *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_worklet_fixed.py',
                 'measure_pcm_output.py', 'measure_vowel_voice.py', 'measure_junction.py'))]
    upper_paths = ['crates/chimera-wasm/src/lib.rs', 'crates/chimera-wasm/src/api.rs', 'src/wasm/wire.ts',
                   'src/worklet/processor.ts', 'crates/chimera/src/phonetics/planner.rs',
                   'crates/chimera/tests/aspiration.rs', 'tests/wasm-engine.test.ts']
    if display_case == TIMELINE_CASE:
        inputs.append(display_case)
        upper_paths.extend(['src/ui/components/SpeakPanel.tsx', 'src/ui/components/ScoreView.tsx',
                            'src/ui/speech.ts', 'src/audio/AudioEngine.ts', 'tools/e2e.ts',
                            'crates/chimera/tests/fast_speech.rs', 'crates/chimera/tests/engine.rs'])
    if display_case == SCOPE_CASE:
        inputs.append(display_case)
        upper_paths.extend(['src/ui/components/Stroboscope.tsx', 'src/audio/AudioEngine.ts', 'tests/tele.test.ts',
                            'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/sources/glottis.rs',
                            'crates/chimera/tests/engine.rs'])
    if display_case == SPECTRUM_CASE:
        inputs.append(SPECTRUM_PROBE)
        upper_paths.extend(['src/ui/components/SpectrumView.tsx', 'src/ui/components/Spectrogram.tsx',
                            'src/audio/AudioEngine.ts', 'crates/chimera/src/analysis/fft.rs',
                            'crates/chimera/tests/airway.rs', 'crates/chimera/tests/engine.rs'])
    if display_case == LIVE_CASE:
        upper_paths.extend(['src/ui/speech.ts', 'src/audio/AudioEngine.ts',
                            'crates/chimera/src/engine.rs', 'crates/chimera/src/voice/human_voice.rs',
                            'crates/chimera/tests/engine.rs'])
    metadata = {'case_id': registration['id'], 'upstream_revision': revision, 'input_root': '$REPOSITORY',
                'scipy': scipy.__version__,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'web_diff_status': subprocess.check_output(
                    ['git','status','--porcelain','--',str(WEB)], cwd=ROOT, text=True).strip(),
                'upstream_source_sha256': {p: sha256(UPSTREAM / p) for p in upper_paths}}
    return shared.record_measurement(args.run_id, display_case or CASE, inputs, metadata,
                                     lambda out, run: compare(source, case, out, run, bun, display_case),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
