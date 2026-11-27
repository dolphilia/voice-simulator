"""アザラシのMIDIコールを固定上流のブラウザ、ネイティブ、独立計算と照合する。"""

import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_seal_sustain_pcm import independent_output
from measure_seal_trill import ideal_controls
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_seal import ACOUSTIC_FIELDS, BASE, CAPTURE, PROBE, TRACE_FIELDS
from measure_worklet_midi_songbird import midi_targets, read_trace, rms
from measure_worklet_midi_songbird_call import normalized_events, pitch_error_rows
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-seal-call.json'
SUSTAIN_CASE = WORKSPACE / 'cases/seal-sustain-pcm.json'
CHUG = WORKSPACE / 'cases/seal-chug-v2.json'
TRILL = WORKSPACE / 'cases/seal-trill.json'
EXTRA_NATIVE_STATE = ('control_clock_seconds', 'call_id', 'target_pulse_depth')


def observe_browser(browser, timeline, expected, case, rate):
    source = browser['upstream']
    observed = source['events']
    calls = source['calls']
    config = case['measurement']
    sound = case['input']['call_id']
    if len(observed) != len(timeline) or len(calls) != len(expected):
        raise ValueError('固定版ブラウザのMIDIまたはコールの数が一致しません')
    held = []
    browser_held = []
    releases = []
    rows = source['telemetry']
    for event, upper in zip(timeline, observed, strict=True):
        note = event['note']
        if event['type'] == 'note-on':
            held.append(note)
        else:
            held.remove(note)
            a, b = (upper['clock'] + t for t in config['browser_release_window_seconds'])
            selection = [row for row in rows if a <= row['clock'] < b]
            if not selection:
                raise ValueError('固定版テレメトリの解放後の計測窓が空です')
            releases.append({'notes_held': upper['held'], 'count': len(selection),
                'gate_max': max(t['gate'] for t in selection), 'call_ids': sorted({t['call'] for t in selection}, key=str)})
        browser_held.append(held.copy())
    return {
        'both_browser_midi_paths': rate == source['rate'] and browser['candidate']['afterDisconnect'] == 0
            and all(browser[key]['requests'] == [{'sysex': False}] and not browser[key]['errors']
                    for key in ('candidate', 'upstream')),
        'fixed_browser_maps_presses_and_keeps_call_on_release': [e['held'] for e in observed] == browser_held
            and all(e['creature'] == 'seal' and e['keyCall'] == sound and not e['hold'] for e in observed)
            and all(e['id'] == sound and abs(e['pitch'] - pitch) <= 1e-9
                    for e, pitch in zip(calls, expected, strict=True))
            and all(row['call_ids'] == [sound] and row['gate_max'] >= config['browser_release_gate_minimum_peak']
                    for row in releases)
            and rows[-1]['call'] is None,
    }, {'calls': calls, 'release_windows': releases}


def independent_config(definition, case):
    first, pitch_end, gate_end = definition['keys']
    if ([first['t'], first['v']['gate'], gate_end['v']['gate']] != [0.0, 1.0, 0.0]
        or pitch_end.get('curve') != 'exp' or definition['id'] != case['input']['call_id']):
        raise ValueError('固定版の下降コール定義を確認してください')
    return {**read_json(TRILL)['measurement'], 'pitch_limits_hz': case['input']['pitch_range_hz'],
            'roughness_smoothing_seconds': read_json(CHUG)['measurement']['roughness_smoothing_seconds'],
            'zap_keys': {'initial_pitch_hz': first['v']['pitch'], 'final_pitch_hz': pitch_end['v']['pitch'],
                'reference_pitch_hz': definition['pitchRef'], 'sweep_seconds': pitch_end['t'],
                'release_seconds': gate_end['t'], 'ownership_tail_seconds': 0.05, 'pulse_depth': first['v']['pulse']}}


def intervals(trace, pcm, events, rate, config):
    begins, releases = [], []
    for event in events:
        frame = event['frame']
        if event['midi_call']['pressed']:
            begins.append({'frame': frame, 'note': event['midi_call']['note'],
                           'pitch_target_hz': float(trace['target_pitch_hz'][frame]),
                           'actual_pitch_hz': float(trace['pitch_hz'][frame]),
                           'preceding_pitch_hz': float(trace['pitch_hz'][frame - 1]),
                           'gate_target': float(trace['gate_target'][frame]),
                           'actual_gate': float(trace['gate'][frame]),
                           'preceding_gate': float(trace['gate'][frame - 1])})
        else:
            a, b = [frame + round(rate * t) for t in config['release_window_seconds']]
            sample = trace[a:b]
            releases.append({'frame': frame, 'frames': [a, b], 'pitch_hz': float(np.median(sample['pitch_hz'])),
                             'pcm_rms': rms(pcm[a:b]), 'gate_min': float(sample['gate'].min()),
                             'gate_max': float(sample['gate'].max()),
                             'glottis_peak_cm2': float(sample['glottis_area_cm2_0'].max()),
                             'call_ids': sorted(set(sample['call_id'].astype(int).tolist()))})
    stops = np.flatnonzero(np.diff(trace['call_id']) < 0)
    return begins, releases, [int(i + 1) for i in stops]


def zap_performance(candidate, pcm, voice, events, expected, config, independent):
    rate = voice['breath']['sample_rate_hz']
    begins, releases, ends = intervals(candidate, pcm, events, rate, config)
    end = ends[-1] if ends else None
    control = config['control_frames']
    keys = independent['zap_keys']
    sweep_frames = math.ceil(keys['sweep_seconds'] * rate / control) * control
    endpoint = float(candidate['target_pitch_hz'][begins[-1]['frame'] + sweep_frames])
    end_target = expected[-1] * keys['final_pitch_hz'] / keys['reference_pitch_hz']
    tail = rms(pcm[-round(config['tail_window_seconds'] * rate):])
    checks = {
        'zap_sweep_endpoint_matches_transposition': abs(endpoint - end_target)
            <= config['independent_tolerances']['target_pitch_hz'],
        'release_preserves_call_and_phonation': all(row['call_ids'] == [2]
            and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['glottis_peak_cm2'] >= config['minimum_open_glottis_peak_cm2'] for row in releases),
        'restart_resets_target_and_continues_glide': all(
            abs(info['pitch_target_hz'] - f0) <= 1e-9 and info['gate_target'] == 1.0
            for info, f0 in zip(begins, expected, strict=True))
            and config['minimum_restart_previous_gate'] <= begins[-1]['preceding_gate'] <= config['maximum_restart_previous_gate']
            and begins[-1]['preceding_gate'] < begins[-1]['actual_gate'] < 1.0
            and begins[-1]['preceding_pitch_hz'] < begins[-1]['actual_pitch_hz'] < begins[-1]['pitch_target_hz'],
        'automatic_end_restores_performer': len(ends) == 1
            and abs((end - begins[-1]['frame']) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
                <= control / rate + 1e-10
            and np.all(candidate['target_pitch_hz'][end:] == voice['shape']['pitch_hz'])
            and tail <= config['maximum_tail_pcm_rms'],
    }
    return checks, {'start_windows': begins, 'release_windows': releases, 'natural_end_frame': end,
                    'second_sweep_endpoint_hz': endpoint, 'expected_sweep_endpoint_hz': end_target,
                    'tail_pcm_rms': tail}


def measure(case_path, case, definition, artifacts, execute, bun, performance, prepare_spec, additional_state):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(case_path), str(UPSTREAM)], cwd=WEB)
    path = artifacts / 'midi-seal-case.json'
    browser = read_json(artifacts / 'midi-seal-browser.json')
    report = read_json(artifacts / 'midi-seal.json')
    voice = read_json(path)['seal_voice']
    rate, pcm = wavfile.read(artifacts / 'midi-seal.wav')
    config = case['measurement']
    fixture = case['input']
    events, timeline = voice['events'], fixture['events']
    pressed = [row['note'] for row in timeline if row['type'] == 'note-on']
    octaves, pitch = midi_targets(set(pressed), fixture['pitch_range_hz'])
    expected = [pitch[n] for n in pressed]
    checks, browser_data = observe_browser(browser, timeline, expected, case, rate)

    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*cli, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    baseline_events = normalized_events(events, [e['pitch'] for e in browser['upstream']['calls']])
    upstream_path = artifacts / 'upstream-case.json'
    upstream_path.write_text(json.dumps({'seal_voice': {**voice, 'events': baseline_events}}) + '\n')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(probe), str(upstream_path)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')
    base_fields = (*TRACE_FIELDS, *EXTRA_NATIVE_STATE, *additional_state)
    candidate = read_trace(artifacts / 'cli.csv', (*base_fields, 'gate_target', 'dc_removed', 'pulse_phase'))
    upper = read_trace(artifacts / 'upstream.csv', (*base_fields, 'shadow_area_error_0', 'shadow_area_error_1'))
    native_fields = (*EXTRA_NATIVE_STATE, *additional_state, 'gate', 'pitch_hz', 'target_pitch_hz',
                     'lung_pressure_dyn_cm2', *ACOUSTIC_FIELDS)
    native_deltas = {
        key: pitch_error_rows(candidate[key], upper[key], config['native_state_absolute_tolerance']
            + config['native_state_relative_tolerance'] * max(abs(upper[key]))) for key in native_fields
    }
    upper_pcm = upper['pcm_f32'].astype(np.float32)
    pcm_difference = pitch_error_rows(pcm, upper_pcm, config['native_pcm_tolerance'])
    max_pcm_delta = pcm_difference['max_delta']
    shadow_area = max(float(max(upper[f'shadow_area_error_{i}'])) for i in range(report['factor']))
    independent = prepare_spec(definition, case)
    mapped = normalized_events(events, expected)
    theory = ideal_controls({**voice, 'events': mapped}, independent)
    timers = {}
    for name, limit in config['independent_tolerances'].items():
        actual, reference = candidate[name], theory[name]
        if name == 'pulse_phase':
            actual, reference = (actual - reference + .5) % 1.0 - .5, np.zeros_like(reference)
        timers[name] = pitch_error_rows(actual, reference, limit)
    factor = report['factor']
    raw = np.column_stack([candidate[f'radiation_{i}'] for i in range(factor)]).ravel()
    limits = read_json(SUSTAIN_CASE)['measurement']
    _, dc, synthesized = independent_output(raw, rate, factor, voice['level'], limits)
    output_delta = float(max(abs(synthesized - pcm)))
    dc_delta = float(max(abs(dc - candidate['dc_removed'])))

    strides = config['observation_stride_frames']
    quant = config['quantum_frames']
    observations = np.asarray(report['observations'])
    cols = {key: i for i, key in enumerate(report['columns'])}
    points = observations[:, cols['output_frame']].astype(int)
    worklet_delta = {k: float(max(abs(observations[:, cols[k]] - candidate[k][points])))
                     for k in (*native_fields, 'gate_target', 'internal_sample', 'pulse_phase')}
    emitted = [{'id': x['call'], 'note': x['note'], 'pressed': x['pressed']} for x in report['midiEvents']]
    adopted = np.array([e['frame'] for e in events])
    diffs = list((adopted - adopted[0]) / rate - [x['seconds'] - timeline[0]['seconds'] for x in timeline])
    origin = report['timing'][0][0]
    performance_checks, performance_data = performance(candidate, pcm, voice, events, expected, config, independent)
    checks.update({
        'ordered_live_midi_uses_render_quantum': emitted == [e['midi_call'] for e in events] ==
            [{'id': fixture['call_id'], 'note': e['note'], 'pressed': e['type'] == 'note-on'} for e in timeline]
            and [e['frame'] for e in report['midiEvents']] == adopted.tolist()
            and all(e['frame'] % quant == 0 and e['contextFrame'] == origin + e['frame'] for e in report['midiEvents'])
            and max(map(abs, diffs)) <= config['maximum_relative_input_error_seconds'],
        'continuous_worklet_clock_and_states': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['breath']['frames'] == len(candidate) == len(upper)
            and np.array_equal(points, np.minimum(np.arange(strides - 1, len(pcm) + strides - 1, strides), len(pcm) - 1))
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quant)
            and max(worklet_delta.values()) <= 1e-12,
        'downloaded_case_cli_pcm_bit_equal': (artifacts / 'midi-seal.wav').read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'fixed_upper_without_release_matches_states_and_pcm': max_pcm_delta <= config['native_pcm_tolerance']
            and all(row['first_outside_tolerance'] is None for row in native_deltas.values()) and shadow_area <= 1e-12,
        'independent_transposition_breath_and_pulse': octaves == config['octave_shift']
            and all(row['first_outside_tolerance'] is None for row in timers.values()),
        'independent_radiation_to_pcm': output_delta <= config['native_pcm_tolerance']
            and dc_delta <= limits['dc_absolute_tolerance'],
        'finite_pcm_and_states': all(np.isfinite(trace[key]).all()
            for trace in (candidate, upper) for key in trace.dtype.names) and np.isfinite(pcm).all(),
    })
    checks.update(performance_checks)
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'sample_rate_hz': rate, 'audio_frames': len(pcm),
            'observations': len(points), 'chromium': browser['chromium'], 'events': events, 'browser': browser_data,
            **performance_data, 'upstream_pcm_difference': pcm_difference,
            'upstream_pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            'upstream_maximum_pcm_difference': max_pcm_delta, 'relative_midi_errors_seconds': diffs,
            'worklet_maximum_state_deltas': worklet_delta, 'upstream_native_deltas': native_deltas,
            'independent_control_deltas': timers, 'independent_pcm_max_delta': output_delta, 'independent_dc_max_delta': dc_delta}


def main(case_path=CASE, *, performance=zap_performance, prepare_spec=independent_config,
         additional_state=(), description=__doc__, driver=Path(__file__), extra_inputs=()):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の状態を確認してください')
    settings = case['measurement']
    reference = WORKSPACE / 'runs' / settings['reference_definition_run']
    definition = reference / f"artifacts/upstream-{case['input']['call_id']}.json"
    manifest = reference / 'manifest.json'
    regression = WORKSPACE / 'runs' / (settings.get('baseline_run') or settings['reference_regression_run']) / 'manifest.json'
    record, last = read_json(manifest), read_json(regression)
    signature = sha256(definition)
    if any(run['status'] != 'pass' or run['upstream_revision'] != revision for run in (record, last)) or not any(
            e['path'] == definition.relative_to(reference).as_posix() and e['sha256'] == signature for e in record['outputs']):
        parser.error('コール定義または回帰のハッシュを確認してください')
    if 'baseline_case_id' in settings:
        source = WORKSPACE / 'cases' / case['source_case']
        source_entries = {str(source.relative_to(ROOT)), str(source.relative_to(WORKSPACE))}
        if (last['case_id'] != settings['baseline_case_id'] or record['case_id'] != read_json(source)['id']
                or not all(any(row['path'] in source_entries and row['sha256'] == sha256(source) for row in run['inputs'])
                           for run in (record, last))):
            parser.error('比較基準のケースとハッシュを確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / name for name in ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/seal.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs', 'tests/creature-abi.test.ts',
        'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden_creatures.rs')]
    inputs = [case_path, BASE, TRILL, CHUG, PROBE, CAPTURE, Path(__file__), driver, definition, manifest, regression,
              *extra_inputs, *web_sources(), *shared.candidate_sources(), *upstream]
    inputs.extend(WORKSPACE / 'tools' / name for name in ('measure_seal_trill.py', 'measure_worklet_midi_seal.py',
                  'measure_seal_sustain_pcm.py', 'measure_worklet_midi_songbird.py', 'measure_worklet_midi_songbird_call.py'))
    return shared.record_measurement(args.run_id, case_path, inputs, {'case_id': case['id'], 'revision': case['revision'],
        'upstream_revision': revision, 'definition_sha256': signature, 'invoked_from': str(Path.cwd())},
        lambda out, execute: measure(case_path, case, read_json(definition), out, execute, bun,
                                     performance, prepare_spec, additional_state), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
