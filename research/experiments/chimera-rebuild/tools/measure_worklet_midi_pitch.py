"""手動MIDIの音高切り替えを固定上流、候補CLI、制御の独立計算で照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np

from measure_articulation import PROBE
from measure_pcm_output import OUTPUT_COLUMNS, read_columns
import measure_uniform_tube as shared
from measure_voiced_vowel_motion import (
    ARTICULATION, GEOMETRY, VOICE, capture_upstream, first_exact_difference, independently_render, load_track,
)
from measure_wasm_fixed import WASM, compare_pcm, first_index, read_json
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_midi import reference_controls
from measure_worklet_realtime import timing_summary
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-voice-pitch.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def render(case_path, name, artifacts, execute, block):
    wave, output, state = (artifacts / suffix for suffix in (f'{name}.wav', f'{name}.csv', f'{name}-state.csv'))
    execute([*CLI, 'render-pcm', str(case_path), str(wave), str(output), str(block)])
    execute([*CLI, 'render', str(case_path), str(state)])
    return wave, output, state


def control_errors(track, reference, samples_per_row, internal_rate):
    # 声門位相は1周期で折り返す。観測点ごとの位相増分を独立に照合する。
    advance = np.diff(track['glottal_phase'], prepend=0.0) % 1.0
    return {
        'gate': float(abs(track['gate'] - reference[:, 0]).max()),
        'pitch_hz': float(abs(track['glottal_f0_hz'] - reference[:, 1]).max()),
        'phase_increment_cycles': float(abs(advance - reference[:, 1] * samples_per_row / internal_rate).max()),
    }


def pitch_only_control(replay, trace, audio, adoption, m, rate, factor, artifacts, execute):
    controls = replay['articulators']
    events = [{**event, **({'f0_hz': replay['voice']['f0_hz']} if 'f0_hz' in event else {})}
              for event in controls['events']]
    path = artifacts / 'constant-pitch-case.json'
    path.write_text(json.dumps(replay | {'articulators': controls | {'events': events}}, ensure_ascii=False, indent=2) + '\n')
    wav, _, state = render(path, 'constant-pitch', artifacts, execute, m['host_block_sizes'][0])
    baseline = load_track(state, np.arange(len(audio) * factor), factor * m['control_frames'])
    quiet_pitch = read_wave(wav, rate, len(audio))
    changed = compare_pcm(audio, quiet_pitch, m['pitch_only_pcm_threshold'])
    internal = {field: first_index(trace[field] != baseline[field]) for field in
                ('glottal_f0_hz', 'glottal_phase', 'glottal_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')}
    first_pcm = changed['first_frame_over_tolerance']
    delay = first_pcm - adoption if first_pcm is not None else None
    checks = {
        'pitch_only_preserves_breath_and_articulation': all(
            np.array_equal(trace[field], baseline[field]) for field in (*GEOMETRY, *ARTICULATION, 'gate'))
            and np.array_equal(audio[:adoption].view('u4'), quiet_pitch[:adoption].view('u4')),
        'pitch_only_first_changes_f0_phase_then_pcm': (
            internal['glottal_f0_hz'] == internal['glottal_phase'] == adoption * factor
            and delay is not None and 0 <= delay <= m['maximum_pitch_only_pcm_delay_frames']),
    }
    return checks, {'first_internal_differences': internal, 'pcm': changed, 'pcm_delay_frames': delay}


def measure(case, settings, bun, artifacts, execute):
    m, fixture = case['measurement'], case['input']
    rate, stride, quantum = fixture['sample_rate_hz'], m['control_frames'], m['render_quantum_frames']
    factor = m['internal_sample_rate_hz'] // rate
    execute([*bun, 'test', 'tests/live-control.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upstream-midi-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    shutil.copyfile(WORKSPACE / WASM, artifacts / 'vocal_wasm.wasm')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'browser-run.json')
    report = read_json(artifacts / 'midi.json')
    replay_path = artifacts / 'midi-case.json'
    replay = read_json(replay_path)
    execute([*CLI, 'inspect', str(replay_path)], stdout=artifacts / 'native-inspect.json')
    wav, output, state = render(replay_path, 'native', artifacts, execute, m['host_block_sizes'][0])
    frames, stop = (report[key] for key in ('outputFrames', 'stopFrame'))
    points = np.arange(quantum - 1, frames, quantum)
    ticks = (points + 1) * factor - 1
    indices = np.arange(frames * factor)
    audio = read_wave(artifacts / 'midi.wav', rate, frames)
    native = read_wave(wav, rate, frames)
    trace = load_track(state, indices, stride * factor)
    header, stage = read_columns(output, frames, len(OUTPUT_COLUMNS))
    if header != OUTPUT_COLUMNS:
        raise ValueError('PCM出力段の観測列が不正です')
    upper_wave, upper_host = capture_upstream(replay, m, artifacts, execute)
    upper = load_track(artifacts / 'upstream-trace.csv', indices[factor - 1::factor], stride * factor)
    end_samples = slice(factor - 1, None, factor)
    common = (*GEOMETRY, *VOICE, *ARTICULATION)
    state_results = {name: shared.compare_series(trace[name][end_samples], upper[name], m['upstream_state_peak_relative_tolerance'])
                     for name in common}
    stages = {
        'geometry': (*GEOMETRY, *ARTICULATION), 'breath': VOICE[:2], 'glottis': VOICE[2:9],
        'airflow_and_radiation': VOICE[9:],
    }
    first = {name: first_exact_difference(trace, upper, fields, end_samples) for name, fields in stages.items()}
    upstream_pcm = compare_pcm(audio, upper_wave, m['upstream_pcm_absolute_tolerance'])
    candidate_pcm = compare_pcm(audio, native, 0)
    independence = independently_render(
        trace, stage, native, rate, factor, replay['voice']['output_gain'],
        read_json(artifacts / 'native-inspect.json')['voice'], m)

    notes = report['midiNotes']
    if len(notes) != len(m['expected_held_notes']):
        raise ValueError('採用したMIDIイベント数が登録条件と一致しません')
    adopted = [entry['frame'] for entry in notes]
    expected = [
        {'frame': frame // stride, 'gate': gate, **({'f0_hz': f0} if note is not None else {})}
        for frame, note, gate, f0 in zip(adopted, m['expected_held_notes'], m['expected_gate_goals'],
                                         m['expected_pitch_goals_hz'], strict=True)
    ]
    expected.append({'frame': stop // stride, 'gate': 0})
    events = replay['articulators']['events']
    theoretical = reference_controls(frames, stride, rate, settings, m['f0_glide_seconds'],
                                     fixture['initial_f0_hz'], expected)
    internal_ref = theoretical[indices // (factor * stride)]
    internal_rate = m['internal_sample_rate_hz']
    controls = {'candidate': control_errors(trace, internal_ref, 1, internal_rate),
                'fixed_upstream': control_errors(upper, internal_ref[end_samples], factor, internal_rate)}
    observations = np.asarray(report['observations'])
    columns = dict(zip(report['columns'], observations.T, strict=True))
    worklet_fields = ('gate', 'glottal_f0_hz', 'glottal_phase', 'glottal_area_cm2',
                      'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')
    worklet = {field: float(abs(columns[field] - trace[field][ticks]).max()) for field in worklet_fields}
    worklet['smoothed_f0_hz'] = float(abs(columns['smoothed_f0_hz'] - theoretical[points // stride, 1]).max())
    times = [event['seconds'] for event in fixture['events']]
    relative = [(frame - adopted[0]) / rate - (seconds - times[0]) for frame, seconds in zip(adopted, times, strict=True)]
    peak = float(abs(audio[adopted[0]:adopted[-1]]).max())
    tail = float(abs(audio[-m['final_silence_frames']:]).max())
    upper_ui = browser['upstream']['states']
    constant_checks, constant = pitch_only_control(replay, trace, audio, adopted[1], m, rate, factor, artifacts, execute)
    checks = {
        'both_screens_select_same_held_notes': all(
            [row['note'] for row in browser[engine]['states']] == m['expected_held_notes']
            and not browser[engine]['errors'] and browser[engine]['requests'] == [{'sysex': False}]
            and browser[engine]['remainingListeners'] == 0 for engine in ('candidate', 'upstream'))
            and browser['candidate']['servedWasmSha256'] == sha256(artifacts / 'vocal_wasm.wasm'),
        'upstream_manual_pitch_and_gate_goals': [row['held'] for row in upper_ui] == [[45], [45, 57], [45], []]
            and all(row['mode'] == 'play' and abs(row['targetHz'] - hz) <= m['pitch_absolute_tolerance_hz']
                    and row['gate'] == gate
                    for row, hz, gate in zip(upper_ui, m['expected_pitch_goals_hz'], m['expected_gate_goals'], strict=True)),
        'same_adopted_frames_and_targets': [entry['note'] for entry in notes] == m['expected_held_notes']
            and all(entry % quantum == 0 for entry in adopted) and adopted == sorted(set(adopted))
            and max(map(abs, relative)) <= m['maximum_relative_input_error_seconds'] and events == expected,
        'continuous_output_at_registered_rate': report['workletSampleRate'] == rate
            and report['internalSampleRate'] == m['internal_sample_rate_hz']
            and report['controlIntervalOutputFrames'] == stride and report['stableWasmBuffers']
            and frames == stop + m['release_frames'] and report['stopReason'] == 'manual'
            and np.all(columns['quantum_frames'] == quantum) and np.all(np.diff(columns['context_frame']) == quantum)
            and np.array_equal(columns['frames_rendered'], points + 1) and np.isfinite(observations).all(),
        'worklet_and_cli_pcm_bit_exact': candidate_pcm['first_bit_difference_frame'] is None,
        'worklet_and_cli_internal_states': all(worklet[key] == 0 for key in worklet_fields)
            and worklet['smoothed_f0_hz'] <= m['pitch_absolute_tolerance_hz'],
        'both_engines_follow_independent_glide_gate_and_phase': all(
            row['gate'] <= m['gate_absolute_tolerance'] and row['pitch_hz'] <= m['pitch_absolute_tolerance_hz']
            and row['phase_increment_cycles'] <= m['phase_increment_absolute_tolerance_cycles'] for row in controls.values()),
        'fixed_upstream_internal_traces_and_pcm': all(row['status'] for row in state_results.values())
            and upstream_pcm['first_frame_over_tolerance'] is None,
        'fixed_upstream_host_block_pcm': upper_host,
        'independent_output_stage': all(row['status'] for row in independence.values()),
        'voiced_and_releases_to_quiet': peak >= m['minimum_voiced_pcm_peak'] and tail <= m['final_silence_peak_max'],
        **constant_checks,
    }
    transitions = [{
        'frame': frame, 'f0_before_hz': float(trace['glottal_f0_hz'][frame * factor - 1]),
        'f0_after_hz': float(trace['glottal_f0_hz'][frame * factor]),
        'gate_before': float(trace['gate'][frame * factor - 1]), 'gate_after': float(trace['gate'][frame * factor]),
        'phase_before_cycles': float(trace['glottal_phase'][frame * factor - 1]),
        'phase_after_cycles': float(trace['glottal_phase'][frame * factor]),
    } for frame in adopted]
    warm = settings['timing_exclude_first_blocks']
    return {'checks': {name: bool(value) for name, value in checks.items()}, 'frames': frames, 'rate_hz': rate,
            'observations': len(points), 'applied_notes': notes, 'stop_frame': stop, 'relative_timing_errors_seconds': relative,
            'transitions': transitions, 'fixed_upstream_ui': upper_ui, 'candidate_pcm': candidate_pcm, 'upstream_pcm': upstream_pcm,
            'upstream_pcm_different_bits': int(np.count_nonzero(audio.view('u4') != upper_wave.view('u4'))),
            'worklet_max_errors': worklet, 'independent_controls_max_errors': controls, 'fixed_upstream_series': state_results,
            'first_fixed_upstream_differences_by_stage': first, 'pitch_only_control': constant, 'independent_output': independence,
            'voiced_peak': peak, 'tail_peak': tail, 'timing': timing_summary(columns['process_ms'][warm:], 1000 * quantum / rate),
            'chromium': browser['candidate']['version']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    m = case['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    baseline = WORKSPACE / 'runs' / m['baseline_run'] / 'manifest.json'
    baseline_manifest = read_json(baseline)
    if (revision != case['upstream_revision'] or baseline_manifest['upstream_revision'] != revision
            or baseline_manifest['status'] != 'pass' or baseline_manifest['case_id'] != 'worklet-midi-voice'
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流と基準実行を確認してください')
    dependencies = [WORKSPACE / 'cases' / name for name in (case['source_case'], m['fixed_voice_case'], m['realtime_case'])]
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_sources = [UPSTREAM / path for path in (
        'src/ui/midi.ts', 'src/ui/store.ts', 'src/ui/components/Keys.tsx', 'src/audio/AudioEngine.ts',
        'src/worklet/processor.ts', 'crates/chimera/src/voice/human_voice.rs',
        'crates/chimera/src/sources/glottis.rs', 'tests/live-control.test.ts', 'crates/chimera/tests/engine.rs')]
    tools_used = [WORKSPACE / 'tools' / f'{name}.py' for name in (
        'measure_articulation', 'measure_voiced_vowel_motion', 'measure_pcm_output', 'measure_worklet_midi',
        'measure_worklet_realtime', 'measure_worklet_songbird', 'measure_wasm_fixed')]
    sources = [CASE, Path(__file__), PROBE, CAPTURE, baseline, *dependencies, *tools_used,
               *web_sources(), *shared.candidate_sources(), *upstream_sources]
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(args.run_id, CASE, sources, details,
        lambda out, run: measure(case, read_json(dependencies[-1])['measurement'], bun, out, run),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
