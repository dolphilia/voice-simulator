"""鳴禽の片側の振動を固定上流、独立積分、TypeScriptの開口列と比較する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.signal import find_peaks

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-syrinx.json'
PROBE = WORKSPACE / 'tools/upstream_syrinx_probe.rs'
TABLE = 'crates/chimera/src/sources/syrinxTable.generated.json'
FIXTURE = 'crates/chimera/tests/golden/creature-units.json'
CONTROL_NAMES = ('drive', 'tension', 'f0_hz', 'gate')
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def read(path):
    return json.loads(path.read_text())


def schedule(source):
    return [{'sample': 0, 'controls': source['controls']}, *source['events']]


def load_trace(path, fields, sample_count):
    trace = np.genfromtxt(path, delimiter=',', names=True)
    if (trace.dtype.names != fields or trace.shape != (sample_count,)
            or not np.array_equal(trace['sample'], np.arange(sample_count))
            or any(not np.isfinite(trace[field]).all() for field in fields)):
        raise ValueError(f'観測値の列、件数、連番または有限性が不正です ({path.name})')
    return trace


def compare(candidate, reference, tolerance, *, relative=False):
    delta = np.abs(candidate - reference)
    difference = np.flatnonzero(delta != 0)
    error = delta / np.maximum(np.maximum(np.abs(candidate), np.abs(reference)), 1e-12) if relative else delta
    failures = np.flatnonzero(error > tolerance)
    first = int(difference[0]) if difference.size else None
    return {
        'first_difference_sample': first,
        'first_difference_values': None if first is None else [float(candidate[first]), float(reference[first])],
        'first_over_tolerance_sample': int(failures[0]) if failures.size else None,
        'maximum_absolute_error': float(np.max(delta)),
        'maximum_compared_error': float(np.max(error)),
        'passed': not bool(failures.size),
    }


def reference_table():
    source = read(UPSTREAM / TABLE)
    values = np.asarray([source[key] for key in ('T', 'lo', 'hi')], dtype=float)
    for row in range(values.shape[1]):
        for col in np.flatnonzero(np.isnan(values[0, row]))[::-1]:
            if col + 1 < values.shape[2]:
                values[:, row, col] = values[:, row, col + 1]
            else:
                below = values[0, row + 1, col] if row + 1 < values.shape[1] else np.nan
                values[:, row, col] = (below if np.isfinite(below) else 10.0, -1.0, 1.0)
    return np.asarray(source['alphas']), np.asarray(source['betas']), np.nan_to_num(values)


def expected_tuning(table, controls, rate):
    alpha = float(np.interp(controls['drive'], [0, 1], [0.09, 0.6]))
    beta = float(np.interp(controls['tension'], [0, 1], [0.2, 1.3]))
    alphas, betas, grid = table
    col, row = [float(np.clip(np.interp(value, axis, np.arange(axis.size)), 0, axis.size - 1.0001))
                for value, axis in ((alpha, alphas), (beta, betas))]
    j, i = int(col), int(row)
    u, v = col - j, row - i
    period, low, high = np.einsum('krc,r,c->k', grid[:, i:i+2, j:j+2], [1-v, v], [1-u, u])
    delta = period * controls['f0_hz'] / rate
    steps = max(1, int(np.ceil(delta / 0.06)))
    return {'alpha': alpha, 'beta': beta, 'period_tau': float(period),
            'displacement_low': float(low), 'displacement_high': float(high),
            'substeps': steps, 'step_tau': float(delta / steps)}


def capture(source, path, execute, probe, table, limits):
    path.mkdir()
    input_path = path / 'case.json'
    input_path.write_text(json.dumps({'syrinx_labia': source}, ensure_ascii=False, indent=2) + '\n')
    settings_path, candidate_path, upstream_path = (path / name for name in
                                                   ('settings.json', 'candidate.csv', 'upstream.csv'))
    execute([*CLI, 'inspect', str(input_path)], stdout=settings_path)
    execute([*CLI, 'render', str(input_path), str(candidate_path)])
    rate, count, seed = (source[key] for key in ('sample_rate_hz', 'sample_count', 'seed'))
    events = schedule(source)
    command = [str(probe), str(rate), str(count), str(seed)]
    for event in events:
        command.extend([str(event['sample']), *(str(event['controls'][key]) for key in CONTROL_NAMES)])
    execute(command, cwd=UPSTREAM, stdout=upstream_path)
    candidate = load_trace(candidate_path, ('sample', 'displacement', 'velocity_tau', 'gate_smoothed', 'opening'), count)
    upstream = load_trace(upstream_path, ('sample', 'opening'), count)

    settings = read(settings_path)
    inspected = [{'sample': 0, 'tuning': settings['initial_tuning']}, *settings['event_tunings']]
    tunings = [expected_tuning(table, event['controls'], rate) for event in events]
    first_error = None
    tuning_errors = dict.fromkeys(tunings[0], 0.0)
    gate_expected, opening_expected = np.empty(count), np.empty(count)
    gate_previous = 0.0
    if [item['sample'] for item in inspected] != [item['sample'] for item in events]:
        raise ValueError('検査された制御時刻が入力と一致しません')
    for index, (event, tuning, observed) in enumerate(zip(events, tunings, inspected, strict=True)):
        start = event['sample']
        stop = events[index + 1]['sample'] if index + 1 < len(events) else count
        for key, value in tuning.items():
            error = abs(value - observed['tuning'][key])
            tuning_errors[key] = max(tuning_errors[key], error)
            if first_error is None and error > limits['interpolation_absolute_tolerance']:
                first_error = {'sample': start, 'field': key, 'error': error}
        gate = event['controls']['gate']
        gate_expected[start:stop] = gate + (gate_previous - gate) * 0.998 ** np.arange(1, stop - start + 1)
        gate_previous = gate_expected[stop - 1]
        lo, hi = tuning['displacement_low'], tuning['displacement_high']
        displacement = candidate['displacement'][start:stop]
        opening_expected[start:stop] = np.clip((displacement - lo) / max(0.001, hi - lo), 0, 1)**2 * gate_expected[start:stop]
    tolerance = limits['gate_and_projection_absolute_tolerance']
    outcome = {
        'samples': count,
        'sample_rate_hz': rate,
        'initial_tuning': settings['initial_tuning'],
        'first_tuning_error': first_error,
        'maximum_tuning_errors': tuning_errors,
        'opening_vs_upstream': compare(candidate['opening'], upstream['opening'], limits['upstream_opening_absolute_tolerance']),
        'gate_vs_closed_form': compare(candidate['gate_smoothed'], gate_expected, tolerance),
        'opening_from_displacement': compare(candidate['opening'], opening_expected, tolerance),
        'opening_in_range': bool(np.all((candidate['opening'] >= 0) & (candidate['opening'] <= 1))),
    }
    return candidate, upstream, tunings[0], outcome


def independent_oscillator(trace, source, tuning, limits):
    alpha, beta = tuning['alpha'], tuning['beta']

    def equation(_tau, state):
        x, velocity = state
        return (velocity, -alpha + x * (x * (1 - x) - beta) - x * (1 + x) * velocity)

    def peak(_tau, state):
        return state[1]

    peak.direction = -1
    init = (0.2 + 0.05 * source['seed'], 0.0)
    count = limits['independent_trajectory_samples']
    rate, f0 = source['sample_rate_hz'], source['controls']['f0_hz']
    if f0 == 0:
        return {'held_displacement_passed': bool(np.all(trace['displacement'] == init[0])
                                                 and np.all(trace['velocity_tau'] == 0))}
    sync_tau = (np.arange(count) + 1) * tuning['period_tau'] * f0 / rate
    result = solve_ivp(equation, (0.0, limits['independent_period_end_tau']), init, method='DOP853',
                       t_eval=sync_tau, events=peak, rtol=limits['independent_ode_rtol'],
                       atol=limits['independent_ode_atol'], max_step=limits['independent_max_step_tau'])
    if not result.success:
        raise ValueError('独立積分が失敗しました')
    peak_tau = result.t_events[0][result.t_events[0] >= limits['independent_period_start_tau']]
    if len(peak_tau) < 3:
        raise ValueError('独立計算の定常区間に周期が3回以上見つかりません')
    period = (peak_tau[-1] - peak_tau[0]) / (len(peak_tau) - 1)
    physical_frequency = tuning['period_tau'] * f0 / period
    begin = round(limits['steady_start_seconds'] * rate)
    signal = trace['displacement'][begin:]
    maxima, _ = find_peaks(signal, distance=rate / (2 * f0))
    if len(maxima) < 3:
        raise ValueError('候補の定常区間に周期が3回以上見つかりません')
    before, at, after = signal[maxima - 1], signal[maxima], signal[maxima + 1]
    refined = maxima + (before - after) / (2 * (before - 2 * at + after))
    measured = rate * (len(refined) - 1) / (refined[-1] - refined[0])
    return {
        'early_displacement_vs_dop853': compare(trace['displacement'][:count], result.y[0],
                                                limits['trajectory_displacement_absolute_tolerance']),
        'early_velocity_vs_dop853': compare(trace['velocity_tau'][:count], result.y[1],
                                           limits['trajectory_velocity_absolute_tolerance']),
        'period_tau_dop853': float(period),
        'frequency_hz_dop853': float(physical_frequency),
        'frequency_hz_measured': float(measured),
        'frequency_vs_dop853_passed': bool(abs(measured / physical_frequency - 1)
                                           <= limits['frequency_vs_independent_relative_tolerance']),
        'frequency_vs_nominal_passed': bool(abs(measured / f0 - 1)
                                            <= limits['frequency_vs_nominal_relative_tolerance']),
        'steady_displacement_range': [float(np.min(signal)), float(np.max(signal))],
    }


def fixture_source(spec):
    def at(sample):
        controls = dict(spec['initial'])
        for key in ('drive', 'tension', 'gate'):
            if sample >= spec[f'{key}_change_sample']:
                controls[key] = spec[f'{key}_after']
        controls['f0_hz'] += spec['pitch_step_hz'] * sample
        return controls

    return {**{key: spec[key] for key in ('sample_rate_hz', 'sample_count', 'seed')},
            'controls': at(0), 'events': [{'sample': n, 'controls': at(n)}
                                         for n in range(1, spec['sample_count'])]}


def gate_tau(trace, rate):
    first, last = trace['gate_smoothed'][[0, 500]]
    return float(-500 / (rate * np.log((1 - last) / (1 - first))))


def measure(config, artifacts, execute):
    limits = config['measurement']
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_creatures',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--lib', 'sources::syrinx::tests::table_is_filled'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-table.log')
    dest = artifacts / 'reference-songbird'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'songbird', str(dest)], cwd=UPSTREAM, stdout=artifacts / 'upstream-songbird.log')
    if not (dest / 'songbird.wav').is_file():
        raise ValueError('固定上流の鳴禽WAVが生成されませんでした')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    checks = {}
    cases = {item['id']: config['syrinx_labia'] | item['overrides'] for item in limits['variants']}
    cases['typescript-fixture'] = fixture_source(limits['typescript_fixture'])
    traces, observations = {}, {}
    table = reference_table()
    for variant, source in cases.items():
        trace, upstream, tuning, observed = capture(source, artifacts / variant, execute, probe, table, limits)
        traces[variant], observations[variant] = trace, observed
        checks[f'{variant}.tuning'] = observed['first_tuning_error'] is None
        checks[f'{variant}.opening_in_range'] = observed['opening_in_range']
        for key in ('opening_vs_upstream', 'gate_vs_closed_form', 'opening_from_displacement'):
            checks[f'{variant}.{key}'] = observed[key]['passed']
        if variant == 'typescript-fixture':
            reference = np.asarray(read(UPSTREAM / FIXTURE)['syrinx'])
            if reference.shape != trace.shape:
                raise ValueError('TypeScriptフィクスチャの件数が登録値と一致しません')
            for label, values in [('candidate', trace), ('upstream', upstream)]:
                key = f'{label}_vs_typescript'
                observed[key] = compare(values['opening'], reference, limits['typescript_fixture_relative_tolerance'],
                                        relative=True)
                checks[key] = observed[key]['passed']
        else:
            observed['independent'] = independent_oscillator(trace, source, tuning, limits)
            for key, value in observed['independent'].items():
                if key.endswith('_passed'):
                    checks[f'{variant}.{key}'] = value
                if key.endswith('_vs_dop853'):
                    checks[f'{variant}.{key}'] = value['passed']

    nominal, gated = traces['nominal'], traces['gated']
    stop = cases['gated']['events'][1]['sample']
    checks['gated.same_trajectory'] = all(np.array_equal(nominal[key], gated[key])
                                          for key in ('displacement', 'velocity_tau'))
    gate_residual = float(gated['gate_smoothed'][stop - 1])
    checks['gated.residual'] = gate_residual <= limits['maximum_gate_residual_after_closed_window']
    octave, baseline = (observations[key]['independent']['frequency_hz_measured']
                        for key in ('octave', 'nominal'))
    octave_ratio = octave / baseline
    checks['octave_ratio'] = abs(octave_ratio / 2 - 1) <= limits['octave_ratio_relative_tolerance']
    taus = {key: gate_tau(traces[key], cases[key]['sample_rate_hz']) for key in ('nominal', 'rate-48000')}
    rate_ratio = taus['rate-48000'] / taus['nominal']
    checks['gate_tau_ratio'] = abs(rate_ratio / 4 - 1) <= limits['gate_tau_rate_ratio_relative_tolerance']
    return {'checks': checks, 'variants': observations, 'octave_ratio': octave_ratio,
            'gate_residual_before_reopen': gate_residual, 'gate_tau_seconds': taus,
            'gate_tau_rate_ratio': rate_ratio}


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
    references = (TABLE, FIXTURE, 'LICENSE', 'tools/gen-syrinx-table.ts',
                  'crates/chimera/src/sources/syrinx.rs', 'crates/chimera/src/creatures/songbird.rs',
                  'crates/chimera/src/creatures/voice.rs', 'crates/chimera-cli/src/render.rs',
                  'crates/chimera/tests/golden_creatures.rs', 'crates/chimera/tests/creature_realtime.rs')
    meta = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
            'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
            'upper_source_sha256': {name: sha256(UPSTREAM / name) for name in references}}
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(shared.__file__), WORKSPACE / 'LICENSE-CHIMERA',
              WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs, meta,
        lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
