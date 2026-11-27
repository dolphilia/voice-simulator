"""アザラシの固定肺圧を上流レンダーと独立計算に照合する。"""

import argparse
from math import exp, log, pi
from pathlib import Path
import json
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_songbird_syrinx import CLI, compare, read
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/seal-breath.json'
PROBE = WORKSPACE / 'tools/upstream_seal_breath_probe.rs'
PARAMETERS = ('pulse_rate_hz', 'pulse_depth', 'duty', 'pressure_cm_h2o')
UPSTREAM_FIELDS = ('control', 'frame', 'gate', *PARAMETERS, 'lung_pressure_dyn_cm2')
CANDIDATE_FIELDS = ('control', 'frame', 'phase', 'half_sine', 'pulse_gain', 'gate_target',
                    'gate', *PARAMETERS, 'base_pressure_dyn_cm2', 'lung_pressure_dyn_cm2')


def load_trace(path, rows, fields):
    header, trace = shared.read_trace(path, rows, len(fields))
    if tuple(header) != fields:
        raise ValueError(f'{path.name} の列名が一致しません')
    return dict(zip(fields, trace.T, strict=True))


def independent(source, frames, limits):
    dt = limits['control_frames'] / source['sample_rate_hz']
    initial = source['controls']
    target = initial
    current = initial.copy()
    retain = {key: exp(-dt / tau) for key, tau in limits['parameter_time_constants_seconds'].items()}
    attack = exp(-dt / limits['attack_seconds'])
    release = exp(-dt / limits['release_seconds'])
    records = {key: [] for key in ('gate_target', 'gate', *PARAMETERS)}
    gate = goal = 0.0
    events = iter(source['events'])
    event = next(events, None)
    for frame in frames:
        while event is not None and event['frame'] <= frame:
            target = event.get('controls', target)
            goal = min(1.5, max(0.0, event.get('gate', goal)))
            event = next(events, None)
        for key, old in current.items():
            new, decay = target[key], retain[key]
            if old != new:
                if key == 'pulse_rate_hz':
                    current[key] = exp(decay * log(old) + (1 - decay) * log(new))
                else:
                    current[key] = new + (old - new) * decay
            records[key].append(current[key])
        gate = goal + (gate - goal) * (attack if goal > gate else release)
        records['gate_target'].append(goal)
        records['gate'].append(gate)

    expected = {key: np.asarray(values) for key, values in records.items()}
    # 毎回折り返すレンダーとは独立に、補償加算で積分した位相の小数部を取る。
    prime = limits['initial_control_count'] * initial['pulse_rate_hz'] * dt
    total, compensation = prime, 0.0
    phase = np.empty_like(expected['pulse_rate_hz'])
    for index, delta in enumerate(expected['pulse_rate_hz'] * dt):
        corrected = delta - compensation
        updated = total + corrected
        compensation = (updated - total) - corrected
        total = updated
        phase[index] = total % 1
    half_sine = np.where(phase < expected['duty'], np.sin(pi * phase / expected['duty']), 0)
    gain = 1 - expected['pulse_depth'] * (1 - half_sine)
    base = expected['pressure_cm_h2o'] * expected['gate'] * limits['cm_h2o_to_dyn_cm2']
    return prime % 1, expected | {'phase': phase, 'half_sine': half_sine, 'pulse_gain': gain,
                                 'base_pressure_dyn_cm2': base, 'lung_pressure_dyn_cm2': base * gain}


def measure_variant(name, source, folder, probe, limits, execute):
    folder.mkdir()
    case, candidate_path, upstream_path, inspect_path = (
        folder / filename for filename in ('case.json', 'candidate.csv', 'upstream.csv', 'inspect.json'))
    case.write_text(json.dumps({'seal_breath': source}, indent=2) + '\n')
    execute([*CLI, 'inspect', str(case)], stdout=inspect_path)
    execute([*CLI, 'render', str(case), str(candidate_path)])
    execute([str(probe), str(case)], cwd=UPSTREAM, stdout=upstream_path)

    stride = limits['control_frames']
    frames = np.arange(0, source['frames'], stride)
    candidate = load_trace(candidate_path, len(frames), CANDIDATE_FIELDS)
    upstream = load_trace(upstream_path, len(frames), UPSTREAM_FIELDS)
    initial_phase, expected = independent(source, frames, limits)
    metadata = compare_render(name, frames, candidate, upstream, expected, limits)
    checks = metadata['checks']
    settings = read(inspect_path)
    checks['inspect'] = (settings['control_frames'] == stride and settings['rows'] == len(frames)
                         and settings['control_seconds'] == stride / source['sample_rate_hz']
                         and abs(settings['initial_phase'] - initial_phase)
                         <= limits['independent_phase_circular_tolerance'])
    metadata['initial_phase'] = settings['initial_phase']
    return metadata


def compare_render(name, frames, candidate, upstream, expected, limits):
    phase, peak, gain = (candidate[key] for key in ('phase', 'half_sine', 'pulse_gain'))
    pressure = 'lung_pressure_dyn_cm2'
    direct = {key: compare(candidate[key], upstream[key], limits['upstream_control_absolute_tolerance'])
              for key in ('gate', *PARAMETERS)}
    direct[pressure] = compare(candidate[pressure], upstream[pressure],
                               limits['upstream_pressure_absolute_tolerance_dyn_cm2'])
    circular_error = (phase - expected['phase'] + 0.5) % 1 - 0.5
    analytic = {'phase_circular': compare(circular_error, np.zeros_like(phase),
                                         limits['independent_phase_circular_tolerance'])}
    for key in ('half_sine', 'pulse_gain'):
        analytic[key] = compare(candidate[key], expected[key], limits['independent_envelope_absolute_tolerance'])
    for label, array, key in (('base_pressure', candidate, 'base_pressure_dyn_cm2'),
                              ('candidate_pressure', candidate, pressure),
                              ('upstream_pressure', upstream, pressure)):
        analytic[label] = compare(array[key], expected[key], limits['independent_pressure_absolute_tolerance_dyn_cm2'])

    checks = {f'upstream.{key}': item['passed'] for key, item in direct.items()}
    checks.update({f'independent.{key}': item['passed'] for key, item in analytic.items()})
    checks['frame_grid'] = np.array_equal(candidate['frame'], frames) and np.array_equal(upstream['frame'], frames)
    checks['gate_target'] = np.array_equal(candidate['gate_target'], expected['gate_target'])
    checks['range'] = bool(np.all((phase >= 0) & (phase < 1))
                           and np.all((peak >= 0) & (peak <= 1)) and np.all((gain >= 0) & (gain <= 1)))
    result = {'checks': checks, 'candidate_vs_upstream': direct, 'vs_independent': analytic,
              'rows': len(frames), 'first_phase': float(phase[0]), 'wraps': int(np.count_nonzero(np.diff(phase) < 0)),
              'first_pressure_dyn_cm2': float(candidate[pressure][0]),
              'peak_pressure_dyn_cm2': float(np.max(candidate[pressure]))}
    if name in ('nominal-48000', 'narrow', 'wide'):
        start, stop = limits['mean_window_control_indices']
        window = slice(start, stop)
        depth, duty = candidate['pulse_depth'][start], candidate['duty'][start]
        expected_mean = 1 - depth + 2 * depth * duty / pi
        mean = float(np.mean(gain[window]))
        active = float(np.mean(phase[window] < candidate['duty'][window]))
        checks['cycle_mean'] = bool(abs(mean - expected_mean) <= limits['mean_multiplier_absolute_tolerance'])
        checks['active_fraction'] = bool(abs(active - duty) <= limits['active_fraction_absolute_tolerance'])
        result['steady'] = {'mean': mean, 'continuous_mean': float(expected_mean),
                            'active_fraction': active, 'duty': float(duty)}
    if name == 'depth-zero':
        checks['unit_multiplier'] = bool(np.all(gain == 1))
        checks['pressure_equals_base'] = np.array_equal(candidate[pressure], candidate['base_pressure_dyn_cm2'])
    if name == 'phase-boundary':
        result['boundary_counts'] = {}
        for point, expected_gain in zip(limits['boundary_phases'], (0.0, 1.0, 0.0), strict=True):
            indices = expected['phase'] == point
            count = int(np.count_nonzero(indices))
            checks[f'boundary.{point}'] = count > 0 and bool(np.all(phase[indices] == point)
                                                           and np.all(gain[indices] == expected_gain))
            result['boundary_counts'][str(point)] = count
    if name == 'changed-44100':
        gate_changes = frames[1:][np.diff(candidate['gate_target']) != 0].tolist()
        rate_changes = frames[1:][np.diff(candidate['pulse_rate_hz']) != 0]
        changes = sorted(gate_changes + rate_changes[:1].tolist())
        checks['event_grid'] = changes == limits['changed_event_control_frames']
        result['changed_event_control_frames'] = changes
        result['event_rows'] = [
            {key: float(candidate[key][index]) for key in ('frame', 'phase', 'gate_target', 'gate',
                                                            'pulse_rate_hz', pressure)}
            for index in np.flatnonzero(np.isin(frames, changes))
        ]
    if name == 'silent-96000':
        checks['silent_pressure'] = bool(np.all(candidate[pressure] == 0) and np.all(upstream[pressure] == 0))
        checks['silent_gate'] = bool(np.all(candidate['gate'] == 0))
        checks['phase_runs_in_silence'] = result['wraps'] > 0
    return result


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    reference = artifacts / 'reference-seal'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'seal', str(reference), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-seal.log')
    rate, pcm = wavfile.read(reference / 'seal.wav')
    peak = float(np.max(np.abs(pcm)))
    checks = {'upstream_cli_wav': rate == 48000 and pcm.ndim == 1 and pcm.dtype == np.float32
              and bool(np.isfinite(pcm).all()) and peak > 0}
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    base, limits = config['seal_breath'], config['measurement']
    variants = {}
    for variant in limits['variants']:
        name, overrides = variant['id'], variant['overrides']
        source = base | overrides | {'controls': base['controls'] | overrides.get('controls', {})}
        result = measure_variant(name, source, artifacts / name, probe, limits, execute)
        variants[name] = result
        checks.update({f'{name}.{key}': passed for key, passed in result['checks'].items()})
    return {'checks': checks, 'thresholds': {key: value for key, value in limits.items() if key != 'variants'},
            'upstream_cli_wav': {'sample_rate_hz': rate, 'frames': len(pcm), 'peak': peak},
            'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    references = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/creatures/seal.rs',
                  'crates/chimera/src/creatures/voice.rs', 'crates/chimera/src/creatures/build.rs',
                  'crates/chimera/src/creatures/mammal.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/golden_creatures.rs',
                  'crates/chimera/tests/creature_realtime.rs')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in references}}
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__),
              *(WORKSPACE / 'tools' / path for path in ('upstream_baseline.py', 'measure_songbird_syrinx.py')),
              WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
