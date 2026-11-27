"""アリゲーターのBellowを仮想MIDIで再発音し、独立計算と固定上流に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_alligator_bellow as bellow
import measure_uniform_tube as shared
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_songbird import CAPTURE, midi_targets, read_trace, rms
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-alligator-call.json'
PROBE = WORKSPACE / 'tools/upstream_alligator_probe.rs'


def browser_evidence(browser, timeline, pitches, sound, rate, config, *, creature='alligator'):
    source = browser['upstream']
    observed = source['events']
    calls = source['calls']
    release_windows = []
    for received, event in zip(observed, timeline, strict=True):
        if event['type'] == 'note-off':
            start, end = (received['clock'] + t for t in config['release_window_seconds'])
            rows = [row for row in source['telemetry'] if start <= row['clock'] < end]
            release_windows.append({'samples': len(rows), 'calls': sorted({row['call'] or '' for row in rows}),
                                    'lowest_gate': min((row['gate'] for row in rows), default=0)})
    checks = {
        'normal_midi_through_both_browser_uis': source['rate'] == rate
            and browser['candidate']['afterDisconnect'] == 0
            and all(browser[key]['requests'] == [{'sysex': False}] and not browser[key]['errors']
                    and [{field: row[field] for field in fixture} for row, fixture
                         in zip(browser[key]['events'], timeline, strict=True)] == timeline
                    for key in ('candidate', 'upstream')),
        'fixed_browser_selects_and_triggers_call': [row['held'] for row in observed] == [
            [e['note']] if e['type'] == 'note-on' else [] for e in timeline]
            and all(row['creature'] == creature and row['keyCall'] == sound and not row['hold'] for row in observed)
            and len(calls) == len(pitches)
            and all(row['id'] == sound and row.get('amplitude') is None
                    and abs(row['pitch'] - pitch) <= config['browser_target_tolerance_hz']
                    for row, pitch in zip(calls, pitches, strict=True)),
        'fixed_browser_call_outlasts_release_and_ends': all(
            row['calls'] == [sound] and row['lowest_gate'] >= config['minimum_release_gate'] for row in release_windows)
            and bool(source['telemetry']) and source['telemetry'][-1]['call'] is None,
    }
    return checks, {'calls': calls, 'release_windows': release_windows}


def play_events(starts, pitches, sound):
    return [{'frame': frame, 'play_call': {'id': sound, 'pitch_hz': pitch}}
            for frame, pitch in zip(starts, pitches, strict=True)]


def acoustic_window(candidate, pcm, frame, offsets, rate, factor):
    start, end = (frame + round(t * rate) for t in offsets)
    if not 0 <= start < end <= len(pcm):
        raise ValueError(f'{frame} フレームの計測窓が出力範囲外です')
    rows = candidate[start * factor:end * factor]
    return {'frames': [start, end], 'gate_min': float(min(rows['gate'])), 'gate_max': float(max(rows['gate'])),
            'call_ids': np.unique(rows['call_id']).astype(int).tolist(), 'pcm_rms': rms(pcm[start:end]),
            'glottis_area_peak_cm2': float(max(rows['glottis_area_cm2'])),
            'wall_flow_rms_cm3_s': rms(rows['wall_cm3_s']), 'oral_flow_rms_cm3_s': rms(rows['oral_cm3_s']),
            'nasal_flow_rms_cm3_s': rms(rows['nasal_cm3_s'])}


def bounds(candidate, pcm, voice, events, starts, pitches, factor, config, spec):
    rate = voice['sample_rate_hz']
    keys = spec['keys']
    snapshot_fields = ('call_id', 'pitch_hz', 'target_pitch_hz', 'gate', 'gate_target', 'chaos', 'target_chaos',
                       'glottis_f0_hz', 'glottis_phase', 'glottis_area_cm2', 'radiation_cm3_s2')
    transitions = []
    for frame in starts:
        i = frame * factor
        transitions.append({'frame': frame, 'before': {key: float(candidate[key][i - 1]) for key in snapshot_fields},
                            'after': {key: float(candidate[key][i]) for key in snapshot_fields}})

    def window(frame, offsets):
        return acoustic_window(candidate, pcm, frame, offsets, rate, factor)

    releases = [window(event['frame'], config['release_window_seconds']) for event in events
                if not event['midi_call']['pressed']]
    ends = (np.flatnonzero(np.diff(candidate['call_id']) < 0) + 1).tolist()
    end = ends[0] // factor if len(ends) == 1 else None
    tail = window(end, config['end_window_seconds']) if end is not None else None
    late_tail = window(end, config['late_end_window_seconds']) if end is not None else None
    second = transitions[-1]
    before, after = second['before'], second['after']
    checks = {
        'release_keeps_call_and_phonation': all(row['call_ids'] == [bellow.CALL_IDS['bellow']]
            and row['gate_min'] >= config['minimum_release_gate']
            and row['glottis_area_peak_cm2'] >= config['minimum_release_glottis_peak_cm2']
            and row['pcm_rms'] >= config['minimum_release_pcm_rms'] for row in releases),
        'retrigger_resets_control_targets_and_preserves_smoothing': all(
            abs(row['after']['target_pitch_hz'] - keys['pitch_first_hz'] * pitch / keys['reference_pitch_hz'])
            <= config['control_tolerance'] and row['after']['gate_target'] == 0
            and row['after']['target_chaos'] == keys['chaos_first'] for row, pitch in zip(transitions, pitches, strict=True))
            and before['gate_target'] == 1 and before['gate'] >= config['minimum_retrigger_gate_before']
            and config['minimum_retrigger_gate_after'] <= after['gate'] < before['gate']
            and before['pitch_hz'] < after['pitch_hz'] < after['target_pitch_hz']
            and after['target_chaos'] < after['chaos'] < before['chaos'],
        'natural_end_returns_to_performer_and_decays': tail is not None and ends[0] % factor == 0
            and abs((end - starts[-1]) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= config['control_frames'] / rate + config['clock_tolerance_seconds']
            and all(np.all(candidate['target_' + key][end * factor:] == voice['shape'][key]) for key in bellow.OWNED)
            and np.all(candidate['gate_target'][end * factor:] == 0) and tail['call_ids'] == [0]
            and tail['gate_max'] <= config['maximum_post_end_gate']
            and tail['pcm_rms'] <= config['maximum_post_end_pcm_ratio'] * releases[-1]['pcm_rms'],
        'late_post_end_gate_decays_below_original_limit': late_tail is not None
            and late_tail['gate_max'] <= config['maximum_late_post_end_gate'],
    }
    return checks, {'start_transitions': transitions, 'release_windows': releases,
                    'natural_end_frame': end, 'post_end_window': tail, 'late_post_end_window': late_tail}


def bellow_definition_matches(definition, keys):
    expected = [
        {'t': 0, 'v': {'gate': 0, 'pitch': keys['pitch_first_hz'], 'chaos': keys['chaos_first'],
                       'mouth': keys['mouth'], 'hiss': keys['hiss']}},
        {'t': keys['gate_rise_seconds'], 'v': {'gate': 1}},
        {'t': keys['hold_seconds'], 'v': {'gate': 1, 'pitch': keys['pitch_last_hz'], 'chaos': keys['chaos_last']}},
        {'t': keys['release_seconds'], 'v': {'gate': 0}},
    ]
    return definition['pitchRef'] == keys['reference_pitch_hz'] and definition['keys'] == expected


def measure(case_path, case, spec, artifacts, execute, bun, performance_checks, definition_matches,
            extra_measurement, counterfactuals):
    execute([*bun, 'test', 'tests/creature-abi.test.ts'], cwd=UPSTREAM, stdout=artifacts / 'upstream-abi.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime', '--test', 'golden_creatures'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(case_path), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-alligator-browser.json')
    report = read_json(artifacts / 'midi-alligator.json')
    path = artifacts / 'midi-alligator-case.json'
    payload = read_json(path)
    voice = payload['alligator_voice']
    wav = artifacts / 'midi-alligator.wav'
    rate, pcm = wavfile.read(wav)
    fixture, config = case['input'], case['measurement']
    sound, timeline = fixture['call_id'], fixture['events']
    events = voice['events']
    notes = [row['note'] for row in timeline if row['type'] == 'note-on']
    octaves, folded = midi_targets(set(notes), fixture['pitch_range_hz'])
    pitches = [folded[n] for n in notes]
    checks, browser_data = browser_evidence(browser, timeline, pitches, sound, rate, config)
    starts = [row['frame'] for row in events if row['midi_call']['pressed']]
    expected = [{'id': sound, 'note': row['note'], 'pressed': row['type'] == 'note-on'} for row in timeline]

    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'inspect', str(path)], stdout=artifacts / 'cli-inspect.json')
    execute([*cli, 'render-pcm', str(path), str(artifacts / 'cli.wav'), str(artifacts / 'cli.csv'), '109'])
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / f'{sound}-definition.json'
    execute([str(probe), f'--{sound}-definition'], cwd=UPSTREAM, stdout=definition_path)
    definition = read_json(definition_path)
    upstream_case = artifacts / 'upstream-case.json'
    upstream_events = play_events(starts, [call['pitch'] for call in browser_data['calls']], sound)
    upstream_case.write_text(json.dumps({**payload, 'alligator_voice': {**voice, 'events': upstream_events}}) + '\n')
    execute([str(probe), str(upstream_case)], cwd=UPSTREAM, stdout=artifacts / 'upstream.csv')

    noise_fields = bellow.NOISE_FIELDS if voice.get('observe_noise') else ()
    candidate = read_trace(artifacts / 'cli.csv', (*bellow.CANDIDATE, *noise_fields))
    upper = read_trace(artifacts / 'upstream.csv', (*bellow.UPPER, *noise_fields))
    factor, stride, quantum = report['factor'], config['observation_stride_frames'], config['quantum_frames']
    observed = dict(zip(report['columns'], np.asarray(report['observations']).T, strict=True))
    points = observed['output_frame'].astype(int)
    last_subsamples = (points + 1) * factor - 1
    worklet_deltas = {}
    for field, values in observed.items():
        if field in ('output_frame', 'internal_sample'):
            continue
        name, _, sub = field.rpartition('_')
        native = candidate[name][points * factor + int(sub)] if sub.isdigit() else candidate[field][last_subsamples]
        worklet_deltas[field] = float(max(abs(values - native)))

    adopted = np.array([e['frame'] for e in events])
    relative_errors = list((adopted - adopted[0]) / rate - [e['seconds'] - timeline[0]['seconds'] for e in timeline])
    origin = report['timing'][0][0]
    applied = report['midiEvents']
    keys = spec[bellow.KEY_GROUPS[sound]]
    checks.update({
        'fixed_envelope_definition_matches_reference': definition['id'] == sound
            and definition_matches(definition, keys),
        'live_midi_events_use_audio_clock': octaves == config['octave_shift']
            and [row['midi_call'] for row in events] == expected
            and [{'id': row['call'], 'note': row['note'], 'pressed': row['pressed']} for row in applied] == expected
            and [row['frame'] for row in applied] == adopted.tolist()
            and all(row['contextFrame'] == origin + row['frame'] and row['frame'] % quantum == 0 for row in applied)
            and max(map(abs, relative_errors)) <= config['maximum_relative_input_error_seconds'],
        'continuous_worklet_clock': rate == fixture['sample_rate_hz'] == report['workletSampleRate']
            and len(pcm) == voice['frames'] and factor == 2 and len(candidate) == len(upper) == len(pcm) * factor
            and np.array_equal(points, np.minimum(np.arange(stride - 1, len(pcm) + stride - 1, stride), len(pcm) - 1))
            and np.array_equal(observed['internal_sample'], last_subsamples)
            and np.all(np.diff(np.array(report['timing'])[:, 0]) == quantum),
        'finite_pcm_and_observations': np.isfinite(pcm).all()
            and all(np.isfinite(series).all() for series in observed.values())
            and all(np.isfinite(trace[field]).all() for trace in (candidate, upper) for field in trace.dtype.names),
        'replay_wav_bit_equal': wav.read_bytes() == (artifacts / 'cli.wav').read_bytes(),
        'replay_observations_match': max(worklet_deltas.values()) <= config['worklet_tolerance'],
    })

    def evaluate(trace, *_):
        return performance_checks(trace, pcm, voice, events, starts, pitches, factor, config, spec)

    independent_case = {**voice, 'events': play_events(starts, pitches, sound)}
    variant = {'first_control': starts[0]}
    result, upper_pcm = bellow.examine(candidate, upper, pcm, independent_case, variant, spec, evaluate)
    checks.update(result['checks'])
    if extra_measurement is not None:
        label, observe = extra_measurement
        extra_variant = variant | {'midi_measurement': config}
        extra_checks, result[label] = observe(candidate, upper, pcm, independent_case, extra_variant, spec)
        checks.update({f'{label}.{key}': value for key, value in extra_checks.items()})
    if counterfactuals is not None:
        extra_checks, result['counterfactuals'] = counterfactuals(artifacts, execute, probe, cli, result, upper_pcm, config)
        checks.update(extra_checks)
    result['checks'] = {key: bool(value) for key, value in checks.items()}
    return result | {'sample_rate_hz': rate, 'chromium': browser['chromium'], 'events': events,
                     'midi_target_hz': folded, 'relative_midi_errors_seconds': relative_errors,
                     'browser': browser_data, 'worklet_observations': len(points), 'worklet_deltas': worklet_deltas,
                     'difference_coordinates': 'internal_sample except pcm_f32, independent decimated and independent dc_removed'}


def main(case_path=CASE, performance_checks=bounds, definition_matches=bellow_definition_matches, *,
         driver=Path(__file__), description=__doc__, extra_inputs=(), extra_measurement=None, counterfactuals=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(case_path)
    config = case['measurement']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('固定上流の取得状態を確認してください')
    case_dir = WORKSPACE / 'cases'
    source = case_dir / case['source_case']
    source_data = read_json(source)
    inherited = source_data.get('inherits_measurement', [])
    if isinstance(inherited, str):
        inherited = [inherited]
    definitions = list(dict.fromkeys([case_dir / config['native_tolerance_source'],
                                     *(case_dir / name for name in inherited), source]))
    baseline = WORKSPACE / 'runs' / config['baseline_run'] / 'manifest.json'
    baseline_data = read_json(baseline)
    if (baseline_data['status'], baseline_data['upstream_revision'], baseline_data['case_id']) != (
            'pass', revision, config.get('baseline_case_id', 'worklet-alligator-bellow')):
        parser.error('コールの基準実行を確認してください')
    baseline_hashes = {item['path']: item['sha256'] for item in baseline_data['inputs']}
    if any(baseline_hashes.get(str(path.relative_to(ROOT))) != sha256(path) for path in definitions):
        parser.error('基準実行と計測定義のハッシュを確認してください')
    spec = {}
    for path in definitions:
        spec.update(read_json(path)['measurement'])
    spec.update(control_frames=config['control_frames'], control_absolute_tolerance=config['control_tolerance'],
                clock_absolute_tolerance_seconds=config['clock_tolerance_seconds'])
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream_files = ('src/ui/store.ts', 'src/ui/midi.ts', 'src/ui/components/BestiaryPanel.tsx',
        'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/creatures/alligator.rs',
        'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/mammal.rs',
        'crates/chimera/src/sources/glottis.rs', 'tests/creature-abi.test.ts',
        'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden_creatures.rs')
    tools = ('measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py', 'measure_worklet_midi_songbird.py',
             'measure_seal_sustain_pcm.py', 'measure_songbird_syrinx.py', 'measure_turbulence.py')
    inputs = list(dict.fromkeys([case_path, *definitions, baseline, PROBE, CAPTURE, Path(__file__), driver,
        *extra_inputs, *web_sources(),
        *shared.candidate_sources(), *(UPSTREAM / name for name in upstream_files),
        *(WORKSPACE / 'tools' / name for name in tools)]))
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'baseline_manifest_sha256': sha256(baseline), 'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, inputs, details,
        lambda artifacts, execute: measure(case_path, case, spec, artifacts, execute, bun,
                                           performance_checks, definition_matches, extra_measurement, counterfactuals),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
