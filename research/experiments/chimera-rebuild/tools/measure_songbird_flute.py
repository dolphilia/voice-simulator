"""鳴禽のコールのキー、目標・平滑値、放射、PCMを固定上流と比較する。"""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

import measure_uniform_tube as shared
from measure_songbird_sustain_pcm import FIELDS, PARAMS, fir_tolerance, independent_output, internal, waveform
from measure_songbird_syrinx import CLI, compare, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-flute.json'
PROBE = WORKSPACE / 'tools/upstream_songbird_voice_probe.rs'
TARGETS = tuple(f'target_{name}' for name in PARAMS)
CALL_FIELDS = ('control_clock_seconds', 'active_call', *TARGETS)
ALIASES = {'pitch': 'pitch_hz', 'interval': 'interval_semitones'}
CALL_CODES = {'flute': 1, 'trill': 2, 'chirps': 3, 'buzz': 4}


def curves(definition):
    tracks = {}
    for key in definition['keys']:
        for name, value in key['v'].items():
            field = ALIASES.get(name, name)
            tracks.setdefault(field, []).append((key['t'], value, key.get('curve')))
    return tracks


def interpolate(entries, elapsed):
    end = next((index for index, key in enumerate(entries) if key[0] > elapsed), len(entries))
    if end == 0:
        return None
    t0, v0, _ = entries[end - 1]
    if end == len(entries) or entries[end][2] == 'step':
        return v0
    t1, v1, curve = entries[end]
    fraction = (elapsed - t0) / (t1 - t0)
    if curve == 'exp' and v0 > 0 and v1 > 0:
        return math.exp((1 - fraction) * math.log(v0) + fraction * math.log(v1))
    return (1 - fraction) * v0 + fraction * v1


def control_reference(source, definitions, config):
    dt = config['control_frames'] / source['sample_rate_hz']
    performers = source['controls'].copy()
    targets = performers.copy()
    current = performers.copy()
    plans = {key: (definition, curves(definition)) for key, definition in definitions.items()}
    log = set(config['logarithmic_parameters'])
    retention = {name: math.exp(-dt / tau) for name, tau in config['parameter_time_constants_seconds'].items()}
    events = {event['frame']: event for event in source['events']}
    points = sorted(set(events) | set(range(0, source['frames'], config['control_frames'])) | {source['frames']})
    series = {key: np.empty(source['frames']) for key in
              ('gate', 'gate_target', 'sac_pressure_dyn_cm2', *PARAMS, *CALL_FIELDS)}
    if source.get('observe_call_id', False):
        series['call_id'] = np.empty(source['frames'])
    active = None
    gate = manual = automatic = clock = 0.0
    for frame, end in zip(points[:-1], points[1:], strict=True):
        event = events.get(frame, {})
        if 'gate' in event:
            manual = event['gate']
        for name, value in event.get('controls', {}).items():
            performers[name] = value
            if active is None or name not in plans[active[0]][1]:
                targets[name] = value
        if event.get('stop_call') or 'play_call' in event:
            targets = performers.copy()
            automatic = 0.0
            active = None
        if 'play_call' in event:
            op = event['play_call']
            pitch = op.get('pitch_hz')
            reference = plans[op['id']][0]['pitchRef']
            active = (op['id'], clock, pitch / reference if pitch else 1.0, op.get('amplitude', 1.0))
        if frame % config['control_frames'] == 0:
            if active is not None:
                call_id, started, pitch_ratio, amplitude = active
                definition, tracks = plans[call_id]
                elapsed = clock - started
                if elapsed > definition['keys'][-1]['t'] + 0.05:
                    active, automatic = None, 0.0
                    targets = performers.copy()
                else:
                    automatic = interpolate(tracks['gate'], elapsed) * amplitude
                    for name in tracks.keys() - {'gate'}:
                        value = interpolate(tracks[name], elapsed)
                        if value is not None:
                            targets[name] = (max(400.0, min(9000.0, value * pitch_ratio))
                                             if name == 'pitch_hz' else value)
            goal = max(manual, automatic)
            tau = config['attack_seconds'] if goal > gate else config['release_seconds']
            gate = goal + (gate - goal) * math.exp(-dt / tau)
            for name, target in targets.items():
                old = current[name]
                weight = retention[name]
                current[name] = (math.exp(weight * math.log(old) + (1 - weight) * math.log(target))
                                 if name in log else target + (old - target) * weight)
            clock += dt
        payload = {'gate': gate, 'gate_target': max(manual, automatic),
                   'control_clock_seconds': clock, 'active_call': int(active is not None),
                   'sac_pressure_dyn_cm2': current['pressure_kpa'] * gate * 1e4, **current,
                   **{f'target_{name}': value for name, value in targets.items()}}
        if 'call_id' in series:
            payload['call_id'] = CALL_CODES[active[0]] if active else 0
        for name, value in payload.items():
            series[name][frame:end] = value
    return series


def trace(path, frames, fields):
    header, arrays = shared.read_trace(path, frames, len(fields))
    if tuple(header) != fields:
        raise ValueError(f'{path.name} の観測列が一致しません')
    return dict(zip(fields, arrays.T, strict=True))


def bit_difference(left, right):
    return int(np.count_nonzero(left.view(np.uint32) != right.view(np.uint32)))


def measure_events(name, candidate, pcm, case, config, m):
    start_command, = [event['frame'] for event in case['events'] if 'play_call' in event]
    period, rate = config['control_frames'], case['sample_rate_hz']
    start = ((start_command + period - 1) // period) * period
    start_pitch = candidate['target_pitch_hz'][start]
    finish, = np.flatnonzero(np.diff(candidate['active_call']) == -1) + 1
    lo, hi = (start + round(rate * seconds) for seconds in m['active_window_relative_seconds'])
    rms = lambda data: float(np.sqrt(np.mean(data.astype(float)**2)))
    steady = rms(pcm[lo:hi])
    window = round(rate * m['tail_window_seconds'])
    windows = pcm[:(len(pcm) // window) * window].astype(float).reshape((-1, window))
    peak_rms = float(np.sqrt(np.mean(windows**2, axis=1).max()))
    tail = rms(pcm[-window:])
    events = {'start_command': start_command, 'first_control_frame': start, 'first_pitch_target_hz': float(start_pitch),
              'end_frame': int(finish), 'active_rms': steady, 'tail_rms': tail,
              'tail_to_peak_rms': tail / max(peak_rms, np.finfo(float).tiny)}
    checks = {'active_rms': steady >= m['minimum_active_pcm_rms'],
              'tail_rms': events['tail_to_peak_rms'] <= m['tail_to_peak_rms_maximum']}
    tol = m['control_and_target_absolute_tolerance']
    if name == 'offgrid-48000':
        expected = m['default_control_frames']
        checks['timing'] = bool(start == expected['start'] and finish == expected['natural_end'])
        checks['start_pitch'] = bool(abs(start_pitch - 2000) <= tol)
    elif name in ('stopped-48000', 'pitched-96000'):
        checks['pitch_scaling'] = bool(abs(start_pitch - 2000 * m['pitch_scale']) <= tol)
    if name == 'stopped-48000':
        expected = m['stopped_control_frames']
        stop, update = expected['stop'], expected['next_control']
        handoff = next(event for event in case['events'] if 'controls' in event)
        restored_pitch = handoff['controls']['pitch_hz']
        events.update({
            'target_pitch_before_stop_hz': float(candidate['target_pitch_hz'][stop - 1]),
            'target_pitch_after_stop_hz': float(candidate['target_pitch_hz'][stop]),
            'pitch_before_stop_hz': float(candidate['pitch_hz'][stop - 1]),
            'pitch_at_stop_hz': float(candidate['pitch_hz'][stop]),
            'pitch_at_next_control_hz': float(candidate['pitch_hz'][update]),
            'gate_target_at_stop': float(candidate['gate_target'][stop]),
            'manual_pressure_target_during_call_kpa': float(candidate['target_pressure_kpa'][handoff['frame']]),
        })
        checks.update({
            'restored_at_stop': bool(finish == stop and candidate['target_pitch_hz'][stop] == restored_pitch),
            'smoothed_only_on_boundary': bool(np.all(candidate['pitch_hz'][stop:update] == candidate['pitch_hz'][stop - 1])
                and abs(candidate['pitch_hz'][update] - restored_pitch) < abs(candidate['pitch_hz'][stop] - restored_pitch)),
            'manual_breath_remains': bool(candidate['gate_target'][stop] == handoff['gate']),
            'unowned_pressure_immediate': bool(candidate['target_pressure_kpa'][handoff['frame']]
                                                == handoff['controls']['pressure_kpa']),
        })
    return events, checks


def capture(name, source, out, execute, probe, definitions, config, m, official,
            *, event_verifier=measure_events):
    out.mkdir()
    path = out / 'case.json'
    path.write_text(json.dumps({'songbird_voice': source}, indent=2) + '\n')
    settings, upper_path = (out / name for name in ('settings.json', 'upstream.csv'))
    execute([*CLI, 'inspect', str(path)], stdout=settings)
    execute([str(probe), str(path)], cwd=UPSTREAM, stdout=upper_path)
    products = []
    for block in config['host_block_frames']:
        wave, csv = out / f'pcm-{block}.wav', out / f'pcm-{block}.csv'
        execute([*CLI, 'render-pcm', str(path), str(wave), str(csv), str(block)])
        products.append((wave, csv))
    wave, csv = products[0]
    frames, rate = source['frames'], source['sample_rate_hz']
    factor = 2 if rate > 60000 else 4
    pcm = waveform(wave, source)
    id_fields = ('call_id',) if source.get('observe_call_id', False) else ()
    candidate = trace(csv, frames, (*FIELDS, *CALL_FIELDS, 'gate_target', *id_fields))
    upstream = trace(upper_path, frames, (*FIELDS, *CALL_FIELDS, *id_fields))
    upper_pcm = upstream['pcm_f32'].astype(np.float32)
    settings = read(settings)
    checks = {
        'frame_layout': bool(len(pcm) == frames and settings['decimation_factor'] == factor
                             and settings['internal_rate_hz'] == rate * factor and settings['control_frames'] == 64),
        'wav_trace': bit_difference(pcm, candidate['pcm_f32'].astype(np.float32)) == 0,
        'host_blocks': all(sha256(wav) == sha256(wave) and sha256(track) == sha256(csv) for wav, track in products),
    }
    tol = m['control_and_target_absolute_tolerance']
    comparison = {
        key: compare(candidate[key], upstream[key], m['clock_absolute_tolerance_seconds'] if key == 'control_clock_seconds' else tol)
        for key in ('gate', *PARAMS, 'left_opening', 'right_opening', 'sac_pressure_dyn_cm2', *CALL_FIELDS, *id_fields)
    }
    raw, upper_raw = internal(candidate, factor), internal(upstream, factor)
    comparison.update({
        'radiation_internal_samples': compare(raw, upper_raw, np.max(np.abs(upper_raw)) *
            config['acoustic_peak_relative_tolerance'] + config['acoustic_absolute_floor']),
        'decimated': compare(candidate['decimated'], upstream['decimated'], fir_tolerance(upstream['decimated'], config)),
        'dc_removed': compare(candidate['dc_removed'], upstream['dc_removed'], config['dc_absolute_tolerance']),
        'pcm_f32': compare(pcm, upper_pcm, m['pcm_absolute_tolerance']),
    })
    checks.update({f'upstream.{key}': result['passed'] for key, result in comparison.items()})
    independent = {}
    truth = control_reference(source, definitions, config)
    for label, data, signal in (('candidate', candidate, raw), ('upstream', upstream, upper_raw)):
        calculation = independent_output(signal, source, factor, config)
        independent[label] = {
            key: compare(data[key], expected, m['clock_absolute_tolerance_seconds'] if key == 'control_clock_seconds' else tol)
            for key, expected in truth.items() if key in data
        }
        independent[label].update({
            'decimated': compare(data['decimated'], calculation['decimated'], fir_tolerance(calculation['decimated'], config)),
            'dc_removed': compare(data['dc_removed'], calculation['dc_removed'], config['dc_absolute_tolerance']),
            'pcm_f32': compare(data['pcm_f32'].astype(np.float32), calculation['pcm_f32'], m['pcm_absolute_tolerance']),
        })
        checks.update({f'independent.{label}.{key}': item['passed'] for key, item in independent[label].items()})
    event_summary, event_checks = event_verifier(name, candidate, pcm, source, config, m)
    checks.update(event_checks)
    details = {'frames': frames, 'rate_hz': rate, 'events': event_summary, 'comparison': comparison,
               'independent': independent, 'different_pcm_bit_patterns': bit_difference(pcm, upper_pcm)}
    if official is not None:
        official_pcm = waveform(official, source)[:frames]
        details['different_official_pcm_bit_patterns'] = bit_difference(pcm, official_pcm)
        comparison['official_cli'] = compare(pcm, official_pcm, m['pcm_absolute_tolerance'])
        checks['official_cli'] = comparison['official_cli']['passed']
        checks['probe_matches_official'] = bit_difference(upper_pcm, official_pcm) == 0
    return details, checks


def measure(case, sustain, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'songbird', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    definition_path = artifacts / 'flute-definition.json'
    execute([str(probe), '--flute-definition'], cwd=UPSTREAM, stdout=definition_path)
    definition = read(definition_path)
    m = case['measurement']
    variants, checks = {}, {}
    for entry in m['variants']:
        name = entry['id']
        source = case['songbird_voice'] | entry['overrides']
        wav = official / 'songbird.wav' if name == 'upper-cli' else None
        variants[name], flags = capture(name, source, artifacts / name, execute, probe,
                                       {definition['id']: definition}, sustain, m, wav)
        checks.update({f'{name}.{key}': value for key, value in flags.items()})
    return {'checks': checks, 'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read(CASE)
    sustain = CASE.with_name(case['measurement']['output_reference'])
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    paths = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/creatures/voice.rs',
             'crates/chimera/src/creatures/types.rs', 'crates/chimera/src/creatures/songbird.rs',
             'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    metadata = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
                'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
                'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in paths}}
    inputs = [CASE, sustain, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              WORKSPACE / 'tools/measure_songbird_syrinx.py', WORKSPACE / 'tools/measure_songbird_sustain_pcm.py',
              WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(case, read(sustain)['measurement'], artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
