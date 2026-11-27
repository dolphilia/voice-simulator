"""くちばし最後の直列枝を、記録済みの入力と演算順から再計算する。"""

import argparse
from itertools import combinations
import math
from pathlib import Path
import subprocess
import sys

from measure_csd_envelope_timing import verified_file
from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_load import DENSITY, ROOT, SIDES, SPEED, VARIANTS, beak_fields
from measure_songbird_syrinx import CLI, load_trace, read
from measure_speech_timing import write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-beak-tip-inflow.json'
UPPER_NETWORK = UPSTREAM / 'crates/chimera/src/airway/network.rs'
UPPER_SONGBIRD = UPSTREAM / 'crates/chimera/src/creatures/songbird.rs'
INPUTS = ('left_pressure', 'tip_pressure', 'previous_inflow', 'arithmetic')


def choose_impedance(areas, length, rate, arithmetic):
    left, right = areas
    dt = 1 / rate
    inverse_left, inverse_right = 1 / left, 1 / right
    half_density = 0.5 * DENSITY
    opening = inverse_left - inverse_right
    positive, negative = max(opening, 0.0), max(-opening, 0.0)
    if arithmetic == 'upstream':
        viscosity = math.sqrt(DENSITY * 1.86e-4 * (math.tau * 700) / 2)
        half_left, half_right = (length * inverse for inverse in (inverse_left, inverse_right))
        left_r, right_r = (2 * math.sqrt(math.pi) * length * math.sqrt(a) * inv * inv
                           for a, inv in zip(areas, (inverse_left, inverse_right), strict=True))
        forward_loss = half_density * positive * positive + 0.1 * half_density * negative * negative
        reverse_loss = half_density * negative * negative + 0.1 * half_density * positive * positive
    else:
        viscosity = math.sqrt(DENSITY * 1.86e-4 * math.tau * 700 / 2)
        half_left, half_right = length / left, length / right
        left_r, right_r = (2 * math.sqrt(math.pi * a) * length / (a * a) for a in areas)
        forward, reverse = half_density * (positive * positive), half_density * (negative * negative)
        forward_loss, reverse_loss = forward + 0.1 * reverse, reverse + 0.1 * forward
    inertance = half_density * (half_left + half_right)
    resistance = 0.5 * viscosity * (left_r + right_r)
    inertance_per_step = inertance * rate if arithmetic == 'upstream' else inertance / dt
    return inertance, resistance, inertance_per_step, forward_loss, reverse_loss


def solve(drive, linear, loss):
    denominator = linear + math.sqrt(linear * linear + 4 * loss * abs(drive))
    inflow = drive / linear if loss == 0.0 else 2 * drive / denominator
    return denominator, inflow


def step(inputs, areas, length, rate, *, multiply_momentum=False, linear_inertance=None, momentum_inertance=None):
    arithmetic = inputs['arithmetic']
    inertance, resistance, scaled_inertance, forward_loss, reverse_loss = choose_impedance(
        areas, length, rate, arithmetic)
    previous = inputs['previous_inflow']
    if momentum_inertance is not None:
        history = (momentum_inertance * previous) * rate
    else:
        history = ((inertance * previous) * rate if arithmetic == 'upstream' or multiply_momentum
                   else scaled_inertance * previous)
    pressure_difference = inputs['left_pressure'] - inputs['tip_pressure']
    drive = pressure_difference + history
    denominator_inertance = scaled_inertance if linear_inertance is None else linear_inertance
    linear = denominator_inertance + resistance
    loss = forward_loss if drive >= 0.0 else reverse_loss
    denominator, inflow = solve(drive, linear, loss)
    return {'inertance': inertance, 'resistance': resistance, 'normalized_inertance': denominator_inertance,
            'pressure_difference': pressure_difference, 'normalized_momentum': history, 'drive': drive,
            'linear_coefficient': linear, 'quadratic_coefficient': loss, 'denominator': denominator,
            'inflow': inflow}


def compare_steps(traces, start, count, tip, length, rate, *, multiply_momentum=False):
    inflow = f'beak_{tip}_inflow_cm3_s'
    columns = [f'beak_{i}_pressure_dyn_cm2' for i in (tip - 1, tip)] + [inflow]
    area_cols = [f'beak_{i}_area_cm2' for i in (tip - 1, tip)]
    areas = tuple(float(traces['candidate'][key][start]) for key in area_cols)
    fixed = all(tuple(float(row[key]) for key in area_cols) == areas
                for rows in traces.values() for row in rows[start - 1:count])
    if not fixed:
        raise ValueError('最後の直列枝の断面と前回の慣性を固定できません')
    series = []
    for index in range(start, count):
        inputs = {side: dict(zip(INPUTS, (*(float(rows[key][index - 1]) for key in columns), side), strict=True))
                  for side, rows in traces.items()}
        predicted = {side: step(inputs[side], areas, length, rate, multiply_momentum=multiply_momentum)
                     for side in SIDES}
        observed = {side: float(rows[inflow][index]) for side, rows in traces.items()}
        series.append({'offset': index - start, 'inputs': inputs, 'replayed': predicted, 'observed': observed})
    return areas, series


def substitutions(base, reference, target, evaluate):
    changed = [key for key in base if base[key] != reference[key]]
    results = []
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            flow = evaluate(base | {key: reference[key] for key in keys})
            results.append({'inputs_from_upstream': keys, 'inflow': flow,
                            'inflow_hex': flow.hex(), 'matches_upstream': flow == target})
    return results


def diagnose_difference(series, areas, length, rate, *, multiply_momentum=False, candidate_linear_inertance=None,
                        candidate_momentum_inertance=None):
    first = next((row for row in series if len(set(row['observed'].values())) > 1), None)
    if first is None:
        return {'first_difference': None, 'substitutions': [], 'term_substitutions': []}
    left, right = (first['inputs'][side] for side in SIDES)
    target = first['observed']['upstream']
    def calculate(values):
        candidate = values['arithmetic'] == 'candidate'
        return step(values, areas, length, rate, multiply_momentum=multiply_momentum,
                    linear_inertance=candidate_linear_inertance if candidate else None,
                    momentum_inertance=candidate_momentum_inertance if candidate else None)['inflow']

    changes = substitutions(left, right, target, calculate)
    fields = ('pressure_difference', 'normalized_momentum', 'linear_coefficient', 'quadratic_coefficient')
    candidate, upstream = ({key: first['replayed'][side][key] for key in fields} for side in SIDES)
    term_changes = substitutions(candidate, upstream, target,
                                 lambda terms: solve(terms['pressure_difference'] + terms['normalized_momentum'],
                                                     terms['linear_coefficient'], terms['quadratic_coefficient'])[1])
    return {'first_difference': first, 'substitutions': changes, 'term_substitutions': term_changes}


def capture_traces(definition, out, prefix, probe, execute, cells, count):
    candidate, upstream = (out / f'{prefix}-{side}.csv' for side in SIDES)
    execute([*CLI, 'render', str(definition), str(candidate)])
    execute([str(probe), str(definition)], cwd=UPSTREAM, stdout=upstream)
    paths = dict(zip(SIDES, (candidate, upstream), strict=True))
    return paths, {side: load_trace(path, FIELDS + beak_fields(cells), count) for side, path in paths.items()}


def measure(case, inputs, out, execute):
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway',
             '--test', 'creature_realtime'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '--workspace'], stdout=out / 'candidate-tests.log')
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    rate, start = case['sample_rate_hz'], case['event_sample']
    count = start + case['observation_internal_samples']
    total_length = case['beak_length_cm']
    cells = math.floor(total_length * rate * 0.93 / SPEED)
    length = total_length / cells
    checks, series = {}, {}
    for variant in VARIANTS:
        definition = inputs[f'{variant}.json']
        settings = read(definition)['songbird_airway']
        if (settings['sample_rate_hz'], settings['sample_count'], settings['events'][0]['sample'],
                settings['observe_beak']) != (rate, count, start, True):
            raise ValueError('保存済みの鳴禽ケースと観測窓が一致しません')
        paths, traces = capture_traces(definition, out, variant, probe, execute, cells, count)
        for side, path in paths.items():
            saved = inputs[path.name]
            checks[f'{variant}/{side}/matches_archived_csv'] = sha256(path) == sha256(saved)
        areas, series[variant] = compare_steps(traces, start, count, cells - 1, length, rate)
        for side in SIDES:
            checks[f'{variant}/{side}/inflow_replayed_bitwise'] = all(
                row['replayed'][side]['inflow'].hex() == row['observed'][side].hex() for row in series[variant])
        if variant == 'archived':
            archived_areas = areas

    quiet = all(value == 0.0 for row in series['no-tracking'] for value in row['observed'].values())
    diagnosis = diagnose_difference(series['archived'], archived_areas, length, rate)
    first = diagnosis['first_difference']
    checks.update(no_tracking_quiet=quiet,
                  first_terminal_inflow_difference=bool(first and first['offset'] == case['first_terminal_inflow_difference']))
    prediction = False
    if first is not None:
        left, right = (first['inputs'][side] for side in SIDES)
        prediction = all(left[key] == right[key] for key in ('left_pressure', 'previous_inflow')) and any(
            item['inputs_from_upstream'] == ('tip_pressure',) and item['matches_upstream']
            for item in diagnosis['substitutions'])
    write(out / 'terminal-branch-steps.json', series)
    return {'checks': checks, 'hypotheses': {'tip_pressure_alone_replays_upstream': prediction},
            'sample_rate_hz': rate, 'event_sample': start, 'beak_cells': cells, 'cell_length_cm': length,
            'terminal_branch_areas_cm2': archived_areas, **diagnosis}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    run = WORKSPACE / 'runs' / case['baseline']['run']
    manifest_file = run / 'manifest.json'
    manifest = read(manifest_file)
    if (sha256(manifest_file) != case['baseline']['manifest_sha256']
            or (manifest['status'], manifest['case_id'], manifest['upstream_revision'])
            != ('pass', 'songbird-chirps-beak-load', revision)):
        parser.error('登録済みのくちばしの比較を使用してください')
    names = [f'{variant}.json' for variant in VARIANTS]
    names += [f'{variant}-{side}.csv' for variant in VARIANTS for side in SIDES]
    inputs = {name: verified_file(run, manifest, f'artifacts/{name}') for name in names}
    sources = [CASE, Path(__file__), PROBE, manifest_file, *inputs.values(), *candidate_sources(),
               *(WORKSPACE / 'tools' / name for name in ('measure_songbird_airway.py', 'measure_songbird_syrinx.py',
                                                        'measure_songbird_chirps_beak_load.py', 'measure_uniform_tube.py')),
               UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs',
               UPSTREAM / 'crates/chimera/tests/airway.rs', UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, sources, details, lambda out, execute: measure(case, inputs, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
