"""くちばし入口の直列枝だけで半セル慣性を上流順に組み立てる。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import (
    ENTRY, NETWORK, inlet_inertance, inlet_step, render_variants,
)
from measure_songbird_chirps_beak_load import DENSITY, ROOT, terminal_coefficients, terminal_replay
from measure_songbird_chirps_beak_tip_inflow import solve, substitutions
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_left_syrinx_half_inertance_44100 import configure
from measure_songbird_chirps_left_syrinx_port_44100 import stored_trace
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS
from measure_songbird_chirps_radiation_derivative_scale_44100 import BASE_CASE as SAC_CASE, CASE as DERIVATIVE_CASE, UPPER_CASE
from measure_songbird_chirps_right_syrinx_half_inertance_44100 import restore_patches
from measure_songbird_chirps_terminal_numerator_44100 import first_offset, same_bits
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, RADIATION, bitwise_derivative, differences
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-beak-inlet-half-inertance-44100.json'
BASE_LABEL = 'derivative-scale'
LABEL = 'beak-inlet-half-inertance'
TERMS = ('pressure_difference', 'normalized_momentum', 'linear_coefficient', 'quadratic_coefficient')


def edit_inlet_half_inertance(workspace, patch):
    apply_edits(workspace, patch, {
        NETWORK: (
            ('    multiply_left_half: bool,\n) -> (f64, f64) {',
             '    multiply_left_half: bool,\n    multiply_right_half: bool,\n) -> (f64, f64) {'),
            ('    let half_sections = 0.5 * AIR_DENSITY * (left_half + right.length_cm / right.area_cm2.max(1e-6));',
             '''    let right_area = right.area_cm2.max(1e-6);
    let right_half = if multiply_right_half {
        right.length_cm * right_area.recip()
    } else {
        right.length_cm / right_area
    };
    let half_sections = 0.5 * AIR_DENSITY * (left_half + right_half);'''),
            ('        multiply_left_half: bool,\n    ) -> Self {',
             '        multiply_left_half: bool,\n        multiply_right_half: bool,\n    ) -> Self {'),
            ('branch_impedance(left, right, port, viscosity, multiply_left_half)',
             'branch_impedance(left, right, port, viscosity, multiply_left_half, multiply_right_half)'),
            ('''    fn update_geometry(&mut self, sections: &[Section], viscosity: f64, multiply_left_half: bool) {
        let next = Self::new(self.nodes, self.port, sections, viscosity, multiply_left_half);''',
             '''    fn update_geometry(
        &mut self, sections: &[Section], viscosity: f64, multiply_left_half: bool, multiply_right_half: bool,
    ) {
        let next = Self::new(self.nodes, self.port, sections, viscosity, multiply_left_half, multiply_right_half);'''),
            ('Branch::new([left, right], port, sections, viscosity, false)',
             'Branch::new([left, right], port, sections, viscosity, false, false)'),
            ('branch_impedance(left, right, branch.port, viscosity, false)',
             'branch_impedance(left, right, branch.port, viscosity, false, false)'),
            ('''                    branch.update_geometry(
                        &self.sections,
                        viscosity,
                        left_half_branch == Some(index) || right_half_branch == Some(index),
                    );''',
             '''                    let beak_inlet = linear_inertance_branch == Some(index);
                    branch.update_geometry(
                        &self.sections,
                        viscosity,
                        beak_inlet || left_half_branch == Some(index) || right_half_branch == Some(index),
                        beak_inlet,
                    );'''),
        ),
    })


def predicted_flow(terms):
    drive = terms['pressure_difference'] + terms['normalized_momentum']
    return solve(drive, terms['linear_coefficient'], terms['quadratic_coefficient'])[1]


def replay_inlet(trace, start, length, rate, *, upper=False, multiply_halves=False):
    rows = []
    for previous, current in zip(trace[start - 1:-1], trace[start:], strict=True):
        row = inlet_step(previous, current, length, rate, upstream=upper, multiply_linear=True, multiply_momentum=True)
        lengths = (float(current['oec_length_cm']), length)
        reciprocal = upper or multiply_halves
        now, old = (inlet_inertance(row[key], lengths, reciprocal) for key in ('areas_cm2', 'previous_areas_cm2'))
        row['current_inertance'], row['previous_inertance'] = now, old
        if multiply_halves:
            momentum = (min(now, old) * float(previous[ENTRY])) * rate
            linear = now * rate + row['resistance']
            drive = row['pressure_difference'] + momentum
            ia, ib = (1 / area for area in row['areas_cm2'])
            expansion = ia - ib if drive >= 0 else ib - ia
            loss = (1.0 if expansion >= 0 else 0.1) * (0.5 * DENSITY * (expansion * expansion))
            row.update(normalized_momentum=momentum, linear_coefficient=linear, quadratic_coefficient=loss,
                       normalized_inertance=now * rate, inertance=now, drive=drive)
            row['denominator'], row['inflow'] = solve(drive, linear, loss)
        rows.append(row)
    return rows


def compare_terminal(traces, start, tip, length, rate):
    pressure, feed, area = (f'beak_{tip}_{field}' for field in ('pressure_dyn_cm2', 'inflow_cm3_s', 'area_cm2'))
    experiment, upper = (traces[label] for label in (LABEL, 'upstream'))
    aperture = float(experiment[area][start])
    c, g, h = terminal_coefficients(aperture, length, rate)
    divided, multiplied = c / (1 / rate), c * rate

    def offsets(calculated, reference):
        return {
            'tip_pressure': first_offset(calculated['pressure'], reference[pressure][start:]),
            'radiation_flow': first_offset(calculated['flow'], reference[RADIATION][start:]),
        }

    checks = {'fixed_aperture_and_initial_rest': all(
        (trace[area] == aperture).all() and all((trace[field][:start] == 0).all() for field in (pressure, feed, RADIATION))
        for trace in traces.values())}
    for label, trace in traces.items():
        upstream = label == 'upstream'
        result = terminal_replay(trace[feed][start:], multiplied if upstream else divided, g, h,
                                 not upstream, numerator_grouped=False)
        checks[f'{label}/load_replayed'] = all(value is None for value in offsets(result, trace).values())
    swaps = {}
    for label, trace, scale, grouped in (('upstream_feed', upper, divided, True),
                                          ('upstream_load', experiment, multiplied, False)):
        result = terminal_replay(trace[feed][start:], scale, g, h, grouped, numerator_grouped=False)
        swaps[label] = offsets(result, upper)
    return checks, swaps


def measure(case, saved, fixed, patches, snapshot, copies, out, execute):
    configurations = configure(case, saved, out)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit_inlet_half_inertance, patch_stem=LABEL, labels=('control', LABEL))
    checks = {
        'only_network_patched': build['changed_paths'] == [NETWORK],
        'experiment_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
        'control_binary_reproduced':
            build['control_binary_sha256'] == read(saved['summary.json'])['build']['experimental_binary_sha256'],
    }
    rate, window, cells = (case[key] for key in ('sample_rate_hz', 'observation_internal_samples', 'beak_cells'))
    length = case['beak_length_cm'] / cells
    results = {}
    distances = {f'beak_{cell}_{field}': cell for cell in range(cells)
                 for field in ('inflow_cm3_s', 'pressure_dyn_cm2')}
    distances.update({RADIATION: cells - 1, DERIVATIVE: cells - 1})
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        traces = {label: stored_trace(paths[label][name], start + window) for label in paths}
        traces['upstream'] = stored_trace(fixed[f'artifacts/{name}-upstream.csv'], start + window)
        control, experiment, upstream = traces.values()
        observed = tuple(field for field in control.dtype.names if field.endswith(('_dyn_cm2', '_cm3_s', '_cm3_s2')))
        shared = tuple(field for field in observed if field in upstream.dtype.names)
        fixed_columns = tuple(field for field in control.dtype.names if field.endswith(('_area_cm2', '_length_cm', '_opening')))
        before = differences(control[start:], upstream[start:], shared, left_label='control', right_label='upstream')
        after = differences(experiment[start:], upstream[start:], shared, left_label=LABEL, right_label='upstream')
        effects = differences(experiment[start:], control[start:], observed, left_label=LABEL, right_label='control')
        candidate_prediction = replay_inlet(control, start, length, rate, multiply_halves=True)
        predicted = next(({'offset': i, 'flow_hex': row['inflow'].hex()} for i, row in enumerate(candidate_prediction)
                          if row['inflow'].hex() != row['observed_inflow'].hex()), None)
        actual = effects.get(ENTRY)
        measured = {'offset': actual['offset'], 'flow_hex': actual[LABEL].hex()} if actual else None
        registered = case['predicted_first_inlet_effect'][name]
        checks.update({
            f'{name}/control_csv_reproduced': sha256(paths['control'][name]) == sha256(saved[f'artifacts/{name}-{BASE_LABEL}.csv']),
            f'{name}/geometry_unchanged': all(same_bits(control[field], experiment[field]) for field in fixed_columns),
            f'{name}/pre_onset_unchanged': all(same_bits(control[field][:start], experiment[field][:start]) for field in observed),
            f'{name}/first_effect_matches_registration': measured == predicted == registered,
        })
        if registered is None:
            checks[f'{name}/control_csv_unchanged'] = sha256(paths['control'][name]) == sha256(paths[LABEL][name])
        else:
            origin = registered['offset']
            checks[f'{name}/first_inlet_difference_removed'] = (
                before.get(ENTRY, {}).get('offset') == origin and after.get(ENTRY, {}).get('offset', window) > origin)
            checks[f'{name}/effect_respects_propagation'] = all(
                effect['offset'] >= origin + distances.get(field, 0) for field, effect in effects.items())
        inlet = {}
        for label, trace in traces.items():
            rows = replay_inlet(trace, start, length, rate, upper=label == 'upstream', multiply_halves=label == LABEL)
            inlet[label] = rows
            checks[f'{name}/{label}/inlet_replayed'] = all(
                row['inflow'].hex() == row['observed_inflow'].hex() for row in rows)
            checks[f'{name}/{label}/derivative_replayed'] = bitwise_derivative(trace, start, rate, multiply=True)
        terminal_checks, terminal = compare_terminal(traces, start, cells - 1, length, rate)
        checks.update({f'{name}/{key}': value for key, value in terminal_checks.items()})
        residual = None
        if ENTRY in after:
            index = after[ENTRY]['offset']
            a, b = inlet[LABEL][index], inlet['upstream'][index]
            residual = {'offset': index, 'experiment': a, 'upstream': b, 'term_substitutions': substitutions(
                {key: a[key] for key in TERMS}, {key: b[key] for key in TERMS}, b['observed_inflow'], predicted_flow)}
        results[name] = {'control_minus_upstream': before, 'experiment_minus_upstream': after,
                         'experiment_minus_control': effects, 'first_inlet_effect': measured,
                         'inlet_residual': residual, 'terminal_substitutions': terminal}
    return {'checks': checks, 'sample_rate_hz': rate, 'window': window, 'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, baseline, observation = (read(path) for path in (CASE, DERIVATIVE_CASE, UPPER_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if any(case[key] != baseline[key] or case[key] != observation[key] for key in (
            'upstream_revision', 'sample_rate_hz', 'output_rate_hz', 'condition_control_samples',
            'observation_internal_samples')):
        parser.error('先行実行と今回の比較条件が一致しません')
    names = ('summary.json', f'artifacts/{BASE_LABEL}.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', f'-{BASE_LABEL}.csv')))
    base_manifest, saved = registered_artifacts(case['baseline'], baseline['id'], revision, names)
    upper_manifest, fixed = registered_artifacts(case['upstream_observation'], observation['id'], revision,
        tuple(f'artifacts/{name}-upstream.csv' for name in CONDITIONS))
    manifest = read(base_manifest)
    indexed = {row['path']: row['sha256'] for row in manifest['inputs']}
    references = [DERIVATIVE_CASE, UPPER_CASE, SAC_CASE, upper_manifest, *fixed.values()]
    if any(indexed.get(path.relative_to(ROOT).as_posix()) != sha256(path) for path in references):
        parser.error('先行実行が使用したケースと固定上流CSVが必要です')
    patches = restore_patches(manifest, saved, BASE_LABEL)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    sources = [ROOT / path for path in indexed
               if (ROOT / path).parent == WORKSPACE / 'tools' or (ROOT / path).is_relative_to(UPSTREAM)]
    inputs = [CASE, Path(__file__).resolve(), base_manifest, *saved.values(), *references, *patches, *copies, *sources]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, saved, fixed, patches, snapshot, copies, out, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
