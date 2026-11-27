"""実ブラウザの鳴禽コールを、固定上流と独立した包絡の計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_songbird_flute import control_reference
from measure_songbird_sustain_pcm import independent_output, internal
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_songbird import CAPTURE, PROBE, SYRINX_FIELDS, midi_targets, read_trace, rms
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-songbird-call.json'
CONTROL_CASE = WORKSPACE / 'cases/songbird-sustain-pcm.json'
OBS_FIELDS = ('gate', 'pitch_hz', 'target_pitch_hz', 'control_clock_seconds', 'call_id', 'sac_pressure_dyn_cm2',
              *SYRINX_FIELDS)
TRACE_FIELDS = ('frame', 'internal_sample', *OBS_FIELDS, 'pcm_f32')
OUTPUT_FIELDS = (*(f'radiation_{i}' for i in range(4)), 'decimated', 'dc_removed')


def pitch_error_rows(actual, expected, tolerance, *, coordinate='frame'):
    delta = abs(actual - expected)
    first = np.flatnonzero(delta)
    outside = np.flatnonzero(delta > tolerance)
    return {'max_delta': float(delta.max()), 'tolerance': float(tolerance),
            f'first_nonzero_{coordinate}': int(first[0]) if first.size else None,
            'first_outside_tolerance': int(outside[0]) if outside.size else None}


def compare_browser(browser, spec, sound, folded, timeline, rate):
    source = browser['upstream']
    states = source['events']
    triggers = source['calls']
    on = [event for event in timeline if event['type'] == 'note-on']
    pitches = [folded[event['note']] for event in on]
    if len(states) != len(timeline) or len(triggers) != len(on):
        raise ValueError('固定版のコール数またはMIDIイベント数が登録条件と一致しません')
    held = []
    expected = []
    for event in timeline:
        if event['type'] == 'note-on':
            held.append(event['note'])
        else:
            held.remove(event['note'])
        expected.append(held.copy())
    telemetry = source['telemetry']
    releases = []
    for row, event in zip(states, timeline, strict=True):
        if event['type'] == 'note-off':
            left, right = [row['clock'] + d for d in spec['browser_release_window_seconds']]
            window = [t for t in telemetry if left <= t['clock'] < right]
            if not window:
                raise ValueError('固定版ブラウザのキー解放後の計測窓が空です')
            releases.append({'sample_count': len(window), 'gate_max': max(t['gate'] for t in window),
                             'call_ids': sorted(set(t['call'] for t in window), key=str)})
    restart = triggers[-1]['clock']
    left, right = (restart + off for off in spec['browser_restart_window_seconds'])
    restarted = [t for t in telemetry if t['call'] == sound and left <= t['clock'] < right]
    if not restarted:
        raise ValueError('固定版ブラウザの再発音の観測点がありません')
    restart_pitch = float(np.median([t['pitch'] for t in restarted]))
    expected_start = spec['first_pitch_key_hz'] * pitches[-1] / spec['pitch_reference_hz']
    if 'browser_restart_pitch_ratios' in spec:
        low, high = (ratio * pitches[-1] for ratio in spec['browser_restart_pitch_ratios'])
        restart_matches = low <= restart_pitch <= high
    else:
        restart_matches = abs(restart_pitch - expected_start) <= spec['browser_maximum_restart_pitch_error_hz']
    info = {'upper_triggers': triggers, 'upper_release_windows': releases, 'upper_restart_pitch_hz': restart_pitch}
    checks = {
        'actual_browser_midi_routing': source['rate'] == rate and browser['candidate']['afterDisconnect'] == 0
            and all(browser[name]['requests'] == [{'sysex': False}] and not browser[name]['errors']
                    for name in ('candidate', 'upstream')),
        'upper_only_presses_trigger_transposition': [event['held'] for event in states] == expected
            and all(event['keyCall'] == sound and event['hold'] is False for event in states)
            and [event['id'] for event in triggers] == [sound] * len(on)
            and all(abs(event['pitch'] - pitch) <= 1e-9 for event, pitch in zip(triggers, pitches, strict=True)),
        'upper_browser_release_restart_and_end': all(row['gate_max'] >= spec['browser_release_gate_minimum_peak']
            and row['call_ids'] == [sound] for row in releases)
            and restart_matches
            and telemetry[-1]['call'] is None,
    }
    return checks, info


def normalized_events(events, pitches):
    return [{'frame': event['frame'],
             'play_call': {'id': event['midi_call']['id'], 'pitch_hz': pitch, 'amplitude': 1.0}}
            for event, pitch in zip((e for e in events if e['midi_call']['pressed']), pitches, strict=True)]


def describe_intervals(trace, pcm, events, spec, rate):
    starts = []
    releases = []
    for event in events:
        frame = event['frame']
        if event['midi_call']['pressed']:
            starts.append({'frame': frame, 'note': event['midi_call']['note'],
                           'target_hz': float(trace['target_pitch_hz'][frame]),
                           'gate_goal': float(trace['gate_target'][frame]),
                           'preceding_gate': float(trace['gate'][frame - 1]) if frame else 0.0,
                           'previous_pitch_target_hz': float(trace['target_pitch_hz'][frame - 1]) if frame else None})
        else:
            left, right = [frame + round(rate * edge) for edge in spec['post_release_pcm_window_seconds']]
            window = slice(left, right)
            flows = {side: rms(trace[f'{side}_port_flow_cm3_s'][window]) for side in ('left', 'right')}
            releases.append({'frame': frame, 'window': [left, right], 'flows_rms_cm3_s': flows,
                             'call_ids': sorted(set(trace['call_id'][window].astype(int).tolist())),
                             'pcm_rms': rms(pcm[window])})
    index = np.flatnonzero((np.diff(trace['call_id']) < 0))
    end_frame = int(index[-1] + 1) if index.size else None
    return starts, releases, end_frame


def flute_performance(trace, pcm, voice, events, pitches, spec, definition, configs, **_context):
    rate = voice['sample_rate_hz']
    starts, releases, end = describe_intervals(trace, pcm, events, spec, rate)
    active = 1
    pitch_first = [definition['keys'][0]['v']['pitch'] * pitch / definition['pitchRef'] for pitch in pitches]
    tail = rms(pcm[-round(rate * spec['tail_window_seconds']):])
    checks = {
        'restarts_at_first_key_with_continuous_glide': all(
            abs(row['target_hz'] - f0) <= 1e-9 and row['gate_goal'] == 0.0
            and trace['call_id'][row['frame']] == active for row, f0 in zip(starts, pitch_first, strict=True))
            and starts[-1]['preceding_gate'] >= spec['minimum_active_gate_before_restart']
            and abs(trace['pitch_hz'][starts[-1]['frame']] - pitch_first[-1]) > 1.0,
        'released_keys_leave_call_and_both_syrinxes_active': all(
            row['call_ids'] == [active] and row['pcm_rms'] >= spec['minimum_post_release_pcm_rms']
            and min(row['flows_rms_cm3_s'].values()) >= spec['minimum_both_syrinx_rms_cm3_s'] for row in releases),
        'natural_end_restores_performer_and_pcm_decays': end is not None
            and abs((end - starts[-1]['frame']) / rate - (definition['keys'][-1]['t'] + 0.05))
            <= spec['control_frames'] / rate + 1e-10
            and np.all(trace['target_pitch_hz'][end:] == voice['controls']['pitch_hz'])
            and tail <= spec['maximum_tail_pcm_rms'],
    }
    return checks, {'post_release': releases, 'starts': starts, 'automatic_end_frame': end, 'tail_pcm_rms': tail}


def measure(case_path, case, definition, artifacts, execute, bun, performance, additional_state):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(case_path), str(UPSTREAM)], cwd=WEB)
    path = artifacts / 'midi-songbird-case.json'
    report = read_json(artifacts / 'midi-songbird.json')
    browser = read_json(artifacts / 'midi-songbird-browser.json')
    voice = read_json(path)['songbird_voice']
    spec = case['measurement']
    fixture = case['input']
    call = fixture['call_id']
    timeline = fixture['events']
    events = voice['events']
    rate, pcm = wavfile.read(artifacts / 'midi-songbird.wav')
    notes = {e['note'] for e in timeline}
    octaves, folded = midi_targets(notes, spec['pitch_range_hz'])
    checks, browser_data = compare_browser(browser, spec, call, folded, timeline, rate)

    command = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*command, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*command, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '113'])
    normalized = normalized_events(events, [row['pitch'] for row in browser['upstream']['calls']])
    upper_path = artifacts / 'upstream-case.json'
    upper_path.write_text(json.dumps({'songbird_voice': {**voice, 'events': normalized}}) + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upper_path), '--observe-syrinx'], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')

    states = (*OBS_FIELDS, *additional_state)
    trace_fields = (*TRACE_FIELDS, *additional_state, *OUTPUT_FIELDS)
    cli = read_trace(artifacts / 'cli.csv', (*trace_fields, 'gate_target'))
    upper = read_trace(artifacts / 'upstream.csv', trace_fields)
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    upstream_pcm = pitch_error_rows(pcm, upper_pcm, spec['native_pcm_absolute_tolerance'])
    configs = read_json(CONTROL_CASE)['measurement']
    independent_events = normalized_events(events, [folded[e['note']] for e in timeline if e['type'] == 'note-on'])
    theory = control_reference({**voice, 'events': independent_events}, {call: definition}, configs)
    reference_data = {}
    for name, tol in spec['independent_absolute_tolerances'].items():
        reference_data[name] = pitch_error_rows(cli[name], theory[name], tol)
    native_data = {}
    for name in (*states, 'decimated', 'dc_removed'):
        tolerance = spec['native_state_absolute_floor'] + spec['native_state_peak_relative_tolerance'] * np.max(abs(upper[name]))
        native_data[name] = pitch_error_rows(cli[name], upper[name], tolerance)
    factor = report['factor']
    cli_radiation, upper_radiation = (internal(trace, factor) for trace in (cli, upper))
    radiation_tolerance = (spec['native_state_absolute_floor']
                           + spec['native_state_peak_relative_tolerance'] * np.max(abs(upper_radiation)))
    native_data['radiation'] = pitch_error_rows(cli_radiation, upper_radiation, radiation_tolerance,
                                               coordinate='internal_sample')
    regenerated = independent_output(cli_radiation, voice, factor, configs)
    output_reference = {
        'decimated': pitch_error_rows(cli['decimated'], regenerated['decimated'],
                                      configs['fir_absolute_floor'] + configs['fir_peak_relative_tolerance']
                                      * np.max(abs(cli['decimated']))),
        'dc_removed': pitch_error_rows(cli['dc_removed'], regenerated['dc_removed'], configs['dc_absolute_tolerance']),
        'pcm_f32': pitch_error_rows(pcm, regenerated['pcm_f32'], configs['pcm_absolute_tolerance']),
    }
    raw = np.asarray(report['observations'])
    width = {name: i for i, name in enumerate(report['columns'])}
    points = raw[:, width['output_frame']].astype(int)
    worklet = {name: float(max(abs(cli[name][points] - raw[:, width[name]]))) for name in (*states, 'gate_target')}

    adopted = np.array([event['frame'] for event in events])
    expected = [{'id': call, 'note': row['note'], 'pressed': row['type'] == 'note-on'} for row in timeline]
    performed = [{'id': row['call'], 'note': row['note'], 'pressed': row['pressed']} for row in report['midiEvents']]
    errors = list((adopted - adopted[0]) / rate - [e['seconds'] - timeline[0]['seconds'] for e in timeline])
    quantum = spec['quantum_frames']
    origin = report['timing'][0][0]
    stride = spec['observation_stride_frames']
    performance_checks, performance_data = performance(
        cli, pcm, voice, events, [item['play_call']['pitch_hz'] for item in independent_events],
        spec, definition, configs, declared=theory, upstream_trace=upper, artifacts=artifacts, execute=execute)
    checks.update({
        'all_key_operations_recorded_on_quantum_boundaries':
            performed == [e['midi_call'] for e in events] == expected
            and [e['frame'] for e in report['midiEvents']] == adopted.tolist()
            and all(row['contextFrame'] == origin + row['frame'] and row['frame'] % quantum == 0
                    for row in report['midiEvents'])
            and max(map(abs, errors)) <= spec['maximum_relative_input_error_seconds'],
        'continuous_render_and_observations': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['frames'] == len(cli) == len(upper)
            and factor == 4 and np.array_equal(raw[:, width['internal_sample']], (points + 1) * factor - 1)
            and np.array_equal(points, np.minimum(np.arange(stride - 1, len(pcm) + stride - 1, stride), len(pcm) - 1))
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quantum),
        'replayed_wav_bit_exact': (artifacts / 'midi-songbird.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'worklet_state_matches_cli': max(worklet.values()) <= 1e-12,
        'independent_transposed_phrase_and_breath': octaves == 3 and definition['pitchRef'] == spec['pitch_reference_hz']
            and all(row['first_outside_tolerance'] is None for row in reference_data.values()),
        'upper_native_control_and_pcm_without_release_operations':
            all(row['first_outside_tolerance'] is None for row in native_data.values())
            and upstream_pcm['first_outside_tolerance'] is None,
        'independent_radiation_to_pcm': all(row['first_outside_tolerance'] is None for row in output_reference.values()),
        'finite_pcm_and_observations': np.isfinite(pcm).all() and np.isfinite(raw).all()
            and all(np.isfinite(trace[name]).all() for trace in (cli, upper) for name in trace.dtype.names),
    })
    checks.update(performance_checks)
    return {'checks': {name: bool(value) for name, value in checks.items()}, 'chromium': browser['chromium'],
            'audio_frames': len(pcm), 'observations': len(points), 'events': events, 'pitch_hz': folded,
            'relative_event_errors_seconds': errors, 'worklet_maximum_state_deltas': worklet,
            'independent_control_deltas': reference_data, 'upstream_native_deltas': native_data,
            'independent_output_deltas': output_reference, 'upstream_pcm_max_delta': upstream_pcm['max_delta'],
            'upstream_pcm_difference': upstream_pcm,
            'upstream_pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            **performance_data, 'browser': browser_data}


def main(case_path=CASE, *, performance=flute_performance, additional_state=(),
         description=__doc__, driver=Path(__file__), extra_inputs=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(case_path)
    spec = case['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    known = WORKSPACE / 'runs' / spec['reference_definition_run']
    regression = WORKSPACE / 'runs' / (spec.get('baseline_run') or spec['reference_regression_run']) / 'manifest.json'
    definition_file = known / 'artifacts' / spec.get('reference_definition_file', 'flute-definition.json')
    manifest_file = known / 'manifest.json'
    baseline = read_json(manifest_file)
    definition_hash = sha256(definition_file)
    last = read_json(regression)
    if (any(entry['status'] != 'pass' or entry['upstream_revision'] != revision for entry in (baseline, last))
            or not any(row['path'] == definition_file.relative_to(known).as_posix() and row['sha256'] == definition_hash
                       for row in baseline['outputs'])):
        parser.error('固定上流のコール定義と基準計測を確認してください')
    if 'baseline_case_id' in spec:
        source = WORKSPACE / 'cases' / case['source_case']
        names = {str(source.relative_to(ROOT)), str(source.relative_to(WORKSPACE))}
        if (last['case_id'] != spec['baseline_case_id'] or baseline['case_id'] != read_json(source)['id']
                or not all(any(row['path'] in names and row['sha256'] == sha256(source) for row in entry['inputs'])
                           for entry in (baseline, last))):
            parser.error('基準実行とケース定義のハッシュを確認してください')
    definitions = read_json(definition_file)
    call = case['input']['call_id']
    definition = next((item for item in definitions if item['id'] == call), None) if isinstance(definitions, list) else definitions
    if definition is None or definition['id'] != call:
        parser.error('固定上流の指定コールを取得できません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/songbird.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/airway/network.rs', 'tests/creature-abi.test.ts',
        'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden_creatures.rs')]
    sources = [case_path, CONTROL_CASE, PROBE, CAPTURE, Path(__file__), driver, manifest_file, regression, definition_file,
               WORKSPACE / 'tools/measure_songbird_flute.py', WORKSPACE / 'tools/measure_worklet_midi_songbird.py',
               WORKSPACE / 'tools/measure_songbird_sustain_pcm.py', *extra_inputs,
               *web_sources(), *shared.candidate_sources(), *upstream]
    return shared.record_measurement(args.run_id, case_path, sources, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': revision, 'definition_sha256': definition_hash, 'invoked_from': str(Path.cwd())},
        lambda out, execute: measure(case_path, case, definition, out, execute, bun, performance, additional_state),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
