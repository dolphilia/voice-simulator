"""実時間のMIDI入力を固定上流の選択音とCLIのPCMに照合する。"""

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-voice.json'
UPSTREAM_CHECK = WEB / 'tools/check-midi-upstream.mjs'


def frequency(note):
    return 440 * np.exp2((note - 69) / 12)


def reference_controls(frames, interval, rate, limits, glide, initial_pitch, events):
    dt = interval / rate
    retain = np.exp(-dt / glide)
    attack, release = (np.exp(-dt / limits[key]) for key in
                       ('attack_time_constant_seconds', 'release_time_constant_seconds'))
    updates = {item['frame']: item for item in events}
    goal = gate = 0.0
    target = pitch = np.log(initial_pitch)
    values = []
    for frame in range(frames // interval):
        if event := updates.get(frame):
            goal = event['gate']
            target = np.log(event['f0_hz']) if 'f0_hz' in event else target
        gate = goal + (gate - goal) * (attack if goal > gate else release)
        pitch = target + (pitch - target) * retain
        values.append((gate, np.exp(pitch)))
    return np.asarray(values)


def measure(case, fixed, live, bun, artifacts, execute):
    m = case['measurement']
    settings = live['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    shutil.copyfile(WORKSPACE / wasm.WASM, artifacts / 'vocal_wasm.wasm')
    execute([*bun, str(UPSTREAM_CHECK), str(UPSTREAM / 'src/ui/midi.ts'), str(CASE)],
            stdout=artifacts / 'upstream-midi.json')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE)])
    browser = wasm.read_json(artifacts / 'browser-run.json')
    upper = wasm.read_json(artifacts / 'upstream-midi.json')
    report = wasm.read_json(artifacts / 'midi.json')
    replay_path = artifacts / 'midi-case.json'
    replay = wasm.read_json(replay_path)
    notes = report['midiNotes']
    rate = settings['output_rate_hz']
    internal = settings['internal_rate_hz']
    interval = settings['control_interval_output_frames']
    quantum = m['render_quantum_frames']
    frames, start, stop = (report[key] for key in ('outputFrames', 'startFrame', 'stopFrame'))
    points = np.arange(quantum - 1, frames, quantum)
    events = []
    for entry in notes:
        note = entry['note']
        changes = {'gate': 0} if note is None else {'gate': 1, 'f0_hz': float(frequency(note))}
        events.append({'frame': entry['frame'] // interval, **changes})
    events.append({'frame': stop // interval, 'gate': 0})
    actual = replay['articulators']['events']
    expected_notes = [action['note'] for action in m['actions']]
    browser_notes = [item['note'] for item in browser['states']]
    topology = list(m['ports'])
    expected_inputs = []
    for action in m['actions']:
        if action.get('change') == 'unplug':
            topology.remove(action['port'])
        elif action.get('change') == 'replug':
            topology.append(action['port'])
        expected_inputs.append(topology.copy())

    wave = artifacts / 'native.wav'
    trace = artifacts / 'native.csv'
    state_trace = artifacts / 'native-state.csv'
    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'render-pcm', str(replay_path), str(wave), str(trace), str(quantum)])
    execute([*cli, 'render', str(replay_path), str(state_trace)])
    audio = read_wave(artifacts / 'midi.wav', rate, frames)
    native = read_wave(wave, rate, frames)
    pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    first_note = notes[0]['frame']
    no_notes = replay | {'articulators': replay['articulators'] | {'events': []},
                         'measurement': {'frames': first_note // interval}}
    no_notes_case = artifacts / 'no-notes-case.json'
    no_notes_case.write_text(json.dumps(no_notes, ensure_ascii=False, indent=2) + '\n')
    no_notes_wave = artifacts / 'no-notes.wav'
    execute([*cli, 'render-pcm', str(no_notes_case), str(no_notes_wave), str(artifacts / 'no-notes.csv'), str(quantum)])
    no_notes_pcm = wasm.compare_pcm(audio[:first_note], read_wave(no_notes_wave, rate, first_note), 0)
    rows = np.asarray(report['observations'])
    if rows.shape != (len(points), len(report['columns'])) or not np.isfinite(rows).all():
        raise ValueError('Workletの観測点数または有限性が条件外です')
    columns = dict(zip(report['columns'], rows.T, strict=True))
    reference = reference_controls(frames, interval, rate, settings, m['pitch_glide_time_constant_seconds'],
                                   fixed['voice']['f0_hz'], events)[points // interval]
    gate_error = float(abs(columns['gate'] - reference[:, 0]).max())
    pitch_error = float(abs(columns['smoothed_f0_hz'] - reference[:, 1]).max())
    fields = ('gate', 'glottal_f0_hz', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')
    states = np.genfromtxt(state_trace, delimiter=',', names=True, usecols=('internal_sample', *fields))
    ticks = (points + 1) * (internal // rate) - 1
    state_diff = {name: float(abs(columns[name] - states[name][ticks]).max()) for name in fields}
    segment_end = [*(entry['frame'] for entry in notes[1:]), stop]
    spans = [end - event['frame'] for event, end in zip(notes, segment_end, strict=True)]
    peaks = [float(np.max(np.abs(audio[event['frame']:end])))
             for event, end in zip(notes, segment_end, strict=True) if event['note'] is not None]
    silence_peak = float(np.max(np.abs(audio[-settings['final_silence_window_frames']:])))
    pre_note_peak = float(np.max(np.abs(audio[:first_note])))
    pre_note_gate = float(np.max(np.abs(columns['gate'][points < first_note])))
    checks = {
        'upstream_midi_selection': upper['notes'] == expected_notes and upper['inputs'] == m['expected_final_inputs'],
        'browser_midi_selection': browser_notes == expected_notes,
        'port_unplug_and_replug': [state['inputs'] for state in browser['states']] == expected_inputs,
        'browser_request_and_cleanup': browser['requests'] == [{'sysex': False}]
        and browser['readyAgain'] and browser['remainingListeners'] == 0 and not browser['errors'],
        'served_wasm': browser['servedWasmSha256'] == sha256(artifacts / 'vocal_wasm.wasm'),
        'only_effective_changes_reach_audio': [entry['note'] for entry in notes] == m['expected_notes'],
        'note_holds_and_quantum_boundaries': all(span >= m['minimum_note_frames'] for span in spans)
        and start <= notes[0]['frame'] and all(entry['frame'] % quantum == 0 for entry in notes),
        'export_has_applied_times_and_targets': len(actual) == len(events)
        and all(a.keys() == x.keys() and all(abs(x[key] - a[key]) <= m['pitch_absolute_tolerance_hz']
                                            for key in x) for a, x in zip(actual, events, strict=True)),
        'output_and_render_quanta': bool(report['caseId'] == case['id'] and start == settings['pre_roll_frames']
        and stop + settings['release_frames'] == frames and report['stopReason'] == 'manual'
        and report['workletSampleRate'] == rate and report['internalSampleRate'] == internal
        and report['stableWasmBuffers'] and np.all(columns['quantum_frames'] == quantum)
        and np.all(np.diff(columns['context_frame']) == quantum)
        and np.array_equal(states['internal_sample'], np.arange(frames * (internal // rate)))),
        'pcm_matches_cli_bits': pcm['first_bit_difference_frame'] is None,
        'cli_internal_states': all(value == 0 for value in state_diff.values()),
        'independent_gate': gate_error <= m['gate_absolute_tolerance'],
        'independent_pitch': pitch_error <= m['pitch_absolute_tolerance_hz'],
        'pre_note_is_quiet_without_gate': pre_note_gate == 0 and pre_note_peak <= m['pre_note_peak_max'],
        'pre_note_matches_no_midi_control': no_notes_pcm['first_bit_difference_frame'] is None,
        'voicing_and_decay': bool(peaks and min(peaks) >= m['minimum_voiced_pcm_peak']
                                  and silence_peak <= settings['final_silence_peak_max']),
    }
    return {'checks': checks, 'browser': browser['version'], 'frames': frames, 'output_rate_hz': rate,
            'observations': len(points), 'browser_note_sequence': browser_notes, 'upper_midi_callbacks': upper['callbacks'],
            'applied_notes': notes, 'note_span_frames': spans, 'replay_events': actual,
            'cli_pcm': pcm, 'cli_state_maximum_absolute_differences': state_diff,
            'independent_errors': {'gate': gate_error, 'pitch_hz': pitch_error},
            'voiced_peaks': peaks, 'final_silence_peak': silence_peak,
            'pre_note': {'frames': first_note, 'peak_pcm': pre_note_peak, 'maximum_gate': pre_note_gate,
                         'no_midi_control_pcm': no_notes_pcm},
            'stop_output_frame': stop, 'measurements': m}


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
    fixed, live = (WORKSPACE / 'cases' / case[key] for key in ('fixed_voice_case', 'realtime_case'))
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    sources = [CASE, fixed, live, Path(__file__).resolve(), UPSTREAM_CHECK, *web_sources(), *shared.candidate_sources(),
               *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'measure_wasm_fixed.py',
                   'measure_worklet_fixed.py', 'measure_worklet_songbird.py', 'upstream_baseline.py'))]
    upper_files = ('src/ui/midi.ts', 'src/ui/store.ts', 'src/ui/components/Keys.tsx', 'src/audio/AudioEngine.ts',
                   'src/worklet/processor.ts', 'crates/chimera/src/voice/human_voice.rs', 'tests/live-control.test.ts')
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'input_root': '$REPOSITORY', 'midi_source': '仮想入力2台',
               'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in upper_files}}
    return shared.record_measurement(args.run_id, CASE, sources, details, lambda out, run:
                                     measure(case, wasm.read_json(fixed), wasm.read_json(live), bun, out, run),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
