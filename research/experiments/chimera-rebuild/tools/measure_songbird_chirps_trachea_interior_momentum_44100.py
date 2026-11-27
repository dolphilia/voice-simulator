"""指定した気管内直列枝で前回運動量の換算順を変える。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT, beak_fields
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import FLOW, NECK_FIELDS, PREFIX_PATCHES, TRACHEA_PRESSURE
from measure_songbird_chirps_oec_neck_momentum_44100 import compare_traces, csv_prefix_matches
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_end_balance_44100 import (
    BALANCE_FIELDS, INFLOW, NOISE, PENULTIMATE, WALL_DISPLACEMENT, WALL_FLOW, inlet_diagnosis, pressure_substitutions, replay,
)
from measure_songbird_chirps_trachea_interior_balance_44100 import interior_columns, interior_replay_view
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, PRESSURE, RADIATION
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-trachea-interior-momentum-44100.json'
BASE_ID = 'songbird-chirps-trachea-interior-balance-44100'
LABELS = ('interior-control', 'interior-momentum')


def edit_interior_momentum(workspace, patch, index):
    edits = {
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, None)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, &[])'),
            ('        trachea_momentum_branch: Option<usize>,', '        trachea_momentum_branches: &[usize],'),
            ('                    || trachea_momentum_branch == Some(index),',
             '                    || trachea_momentum_branches.contains(&index),'),
        ),
        SONGBIRD: (
            ('            Some(self.trachea.first_branch + self.trachea.count - 2),',
             f'''            &[
                self.trachea.first_branch + self.trachea.count - 2,
                self.trachea.first_branch + {index - 1},
            ],'''),
        ),
    }
    apply_edits(workspace, patch, edits)


def edit_all_tracheal_momentum(workspace, patch):
    edits = {
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, &[])',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0)'),
            ('        trachea_momentum_branches: &[usize],',
             '        trachea_momentum_branches: std::ops::Range<usize>,'),
        ),
        SONGBIRD: (
            ('''            &[
                self.trachea.first_branch + self.trachea.count - 2,
                self.trachea.first_branch + 13,
            ],''',
             '            self.trachea.first_branch..self.trachea.first_branch + self.trachea.count - 1,'),
        ),
    }
    apply_edits(workspace, patch, edits)


def apply_edits(workspace, patch, edits):
    diff = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = modified = source.read_text()
        for old, new in recipe:
            if modified.count(old) != 1:
                raise ValueError(f'気管内の換算対象の適用位置が1箇所に定まりません ({relative})')
            modified = modified.replace(old, new, 1)
        diff.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                 f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    patch.write_text(''.join(diff))


def configure(case, saved, out):
    configurations = {}
    selection = case.get('trachea_observation_cells', [case['trachea_cell_index']])
    for name in CONDITIONS:
        source = read(saved[f'artifacts/{name}.json'])
        bird = source['songbird_airway']
        start = case['condition_control_samples'][name]
        event, = bird['events']
        prior_selection = bird['observe_trachea_interior_cells']
        if (bird['sample_rate_hz'], bird['control_block_samples'], event['sample'], bird['sample_count'],
                bird['breath_gate'], event['breath_gate'], bird['observe_beak'], bird['observe_oec'],
                bird['observe_oec_neck'], bird['observe_trachea_end_balance']) != (
                case['sample_rate_hz'], start, start, start + case['reference_observation_internal_samples'],
                0, 0, True, True, True, True) or selection[:len(prior_selection)] != prior_selection:
            raise ValueError(f'先行描画の条件と一致しません ({name})')
        bird['sample_count'] = start + case['observation_internal_samples']
        bird['observe_trachea_interior_cells'] = selection
        configurations[name] = out / f'{name}.json'
        write(configurations[name], source)
    return configurations


def capture_prefix_matches(path, archived, lines, extra_columns):
    if not extra_columns:
        return csv_prefix_matches(path, archived, lines)
    previous = archived.read_bytes().splitlines()
    current = path.read_bytes().splitlines()
    return len(previous) == lines and len(current) >= lines and all(
        old == new.rsplit(b',', extra_columns)[0] for old, new in zip(previous, current[:lines], strict=True))


def trachea_causality(effect, cells, interior):
    if not effect:
        return True
    pressure, upper_pressure, inflow, outflow, wall, displacement, *_ = interior
    if inflow not in effect:
        return False
    origin = effect[inflow]['offset']
    delays = {pressure: 0, upper_pressure: 0, outflow: 1, wall: 1, displacement: 1, INFLOW: 1, PENULTIMATE: 0,
              TRACHEA_PRESSURE: 1, WALL_FLOW: 2, WALL_DISPLACEMENT: 2, FLOW: 2, PRESSURE: 2,
              RADIATION: cells + 2, DERIVATIVE: cells + 2}
    for index in range(cells):
        delays[f'beak_{index}_pressure_dyn_cm2'] = index + 3
        delays[f'beak_{index}_inflow_cm3_s'] = index + 3
    return all(key not in effect or effect[key]['offset'] >= origin + lag for key, lag in delays.items())


def all_trachea_causality(effect, beak_cells, trachea_cells, inflows):
    if not effect:
        return True
    earliest_end_pressure = min((effect[field]['offset'] + trachea_cells - 1 - number
                                 for number, field in inflows.items() if field in effect), default=None)
    if earliest_end_pressure is None:
        return False
    delays = {TRACHEA_PRESSURE: 0, WALL_FLOW: 1, WALL_DISPLACEMENT: 1, FLOW: 1, PRESSURE: 1,
              RADIATION: beak_cells + 1, DERIVATIVE: beak_cells + 1}
    for index in range(beak_cells):
        delays[f'beak_{index}_pressure_dyn_cm2'] = index + 2
        delays[f'beak_{index}_inflow_cm3_s'] = index + 2
    return all(key not in effect or effect[key]['offset'] >= earliest_end_pressure + lag
               for key, lag in delays.items())


def verify_site(trace, start, case, side, *, multiply):
    rows, parameters = replay(trace, start, case['sample_rate_hz'], case['trachea_wall'], side,
                              multiply_inlet_momentum=multiply)
    checks = {f'{field}_bit_replayed': all(row[field].hex() == row[f'observed_{field}'].hex() for row in rows)
              for field in ('pressure', 'wall_flow', 'wall_displacement')}
    checks['inflow_bit_replayed'] = all(row['inlet_replay']['inflow'].hex() == row['pressure_inputs']['inflow'].hex()
                                       for row in rows)
    checks['inlet_noise_zero'] = bool((trace[NOISE] == 0).all())
    return rows, parameters, checks


def earliest_observed_difference(delta, observation_by_cell):
    first = min(((delta[column]['offset'], number, column) for number, column in observation_by_cell.items()
                 if column in delta), default=None)
    if first is None:
        return None
    offset, number, column = first
    return {'offset': offset, 'cell': number, 'column': column}


def measure(case, saved, patches, snapshot, copies, out, execute):
    rate, cells, window, index = (case[key] for key in ('sample_rate_hz', 'beak_cells',
                                                       'observation_internal_samples', 'trachea_cell_index'))
    configurations = configure(case, saved, out)
    all_branches = case.get('momentum_scope') == 'all_tracheal_branches'
    trachea_cells = case.get('trachea_cells', 16)
    selection = case.get('trachea_observation_cells', [index])
    baseline_label = case['baseline'].get('candidate_label', 'candidate')
    patch_stem = 'trachea-all-momentum' if all_branches else 'trachea-interior-momentum'
    edit = edit_all_tracheal_momentum if all_branches else lambda work, patch: edit_interior_momentum(work, patch, index)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit, patch_stem=patch_stem, labels=LABELS)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    physical = FIELDS + beak_fields(cells) + OEC
    interior = {number: interior_columns(number) for number in selection}
    pressure, _, inflow, *_ = interior[index]
    new_columns = tuple(column for group in interior.values() for column in group)
    if all_branches and set(selection) != set(range(1, trachea_cells - 1)):
        raise ValueError('全直列枝を照合する場合は全内部セルを指定してください')
    all_inflows = {number: names[2] for number, names in interior.items()} | {trachea_cells - 1: INFLOW}
    all_pressures = ({0: 'trachea_pressure_dyn_cm2'} | {number: names[0] for number, names in interior.items()}
                     | {trachea_cells - 1: TRACHEA_PRESSURE})
    control_multiplied = case.get('baseline_momentum_inlet_cells', ())
    checks = {'only_network_selection_and_songbird_arguments_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'compiled_experimental_version_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'reciprocal_sample_period_equals_sample_rate': (1 / (1 / rate)).hex() == float(rate).hex()}
    results, replays, hypotheses = {}, {}, {}
    for name, config in configurations.items():
        start = case['condition_control_samples'][name]
        prefix = start + case['reference_observation_internal_samples'] + 1
        control, variant = (paths[label][name] for label in LABELS)
        upstream = out / f'{name}-upstream.csv'
        execute([str(probe), str(config)], cwd=UPSTREAM, stdout=upstream)
        prior_selection = read(saved[f'artifacts/{name}.json'])['songbird_airway']['observe_trachea_interior_cells']
        extra_count = (len(selection) - len(prior_selection)) * len(interior[index])
        checks[f'{name}/control_prefix_reproduced'] = capture_prefix_matches(
            control, saved[f'artifacts/{name}-{baseline_label}.csv'], prefix, extra_count)
        checks[f'{name}/upstream_prefix_reproduced'] = capture_prefix_matches(
            upstream, saved[f'artifacts/{name}-upstream.csv'], prefix, extra_count)
        traces, runs, parameters = {}, {}, {}
        for label, path in zip((*LABELS, 'upstream'), (control, variant, upstream), strict=True):
            side = 'upstream' if label == 'upstream' else 'candidate'
            schema = physical + (CANDIDATE_OEC if side == 'candidate' else ()) + NECK_FIELDS + BALANCE_FIELDS + new_columns
            trace = traces[label] = load_trace(path, schema, start + window)
            sites = {number: interior_replay_view(trace, names) for number, names in interior.items()}
            inner = sites[trachea_cells - 2]
            runs[label] = {}
            checks[f'{name}/{label}/matches_shared_outflow_and_pressure'] = (
                same_bits(inner[FLOW], trace[INFLOW]) and same_bits(inner[TRACHEA_PRESSURE], trace[PENULTIMATE]))
            for number, selected in sites.items():
                if number + 1 in sites:
                    following = sites[number + 1]
                    checks[f'{name}/{label}/cell_{number}_matches_next_cell'] = (
                        same_bits(selected[FLOW], following[INFLOW]) and same_bits(selected[TRACHEA_PRESSURE], following[PENULTIMATE]))
                site = 'interior' if number == index else f'cell_{number}'
                multiply = number in control_multiplied or (label == LABELS[1] and (all_branches or number == index))
                runs[label][site], params, local = verify_site(selected, start, case, side, multiply=multiply)
                parameters[label, site] = params
                checks.update((f'{name}/{label}/{site}_{key}', value) for key, value in local.items())
            runs[label]['end'], parameters[label, 'end'], local = verify_site(trace, start, case, side, multiply=True)
            checks.update((f'{name}/{label}/end_{key}', value) for key, value in local.items())
        extra = (PENULTIMATE, INFLOW, WALL_FLOW, WALL_DISPLACEMENT,
                 *(key for columns in interior.values() for key in columns[:6]))
        if all_branches:
            extra += ('trachea_pressure_dyn_cm2', 'trachea_wall_flow_cm3_s')
        def propagation(delta, count):
            return (all_trachea_causality(delta, count, trachea_cells, all_inflows) if all_branches
                    else trachea_causality(delta, count, interior[index]))
        result, _ = compare_traces(name, traces, start, case, case['neck'], checks, momentum_labels=LABELS,
                                   linear_labels=LABELS, extra_observed=extra,
                                   propagation=propagation)
        earliest = case['expected_baseline_inlet_offsets'][name]
        before, after = (result[key] for key in ('control_minus_upstream', 'experiment_minus_upstream'))
        checks[f'{name}/registered_inlet_offset_reproduced'] = before.get(inflow, {}).get('offset') == earliest
        if earliest is not None:
            hypotheses[f'{name}/first_inlet_difference_delayed'] = after.get(inflow, {}).get('offset', window) > earliest
        inner_rows = {'candidate': runs[LABELS[1]]['interior'], 'upstream': runs['upstream']['interior']}
        params = parameters[LABELS[1], 'interior']
        results[name] = result | {'first_residual_interior_pressure': pressure_substitutions(
            inner_rows, after.get(pressure, {}).get('offset'), rate, params['compliance']),
            'first_residual_interior_inflow': inlet_diagnosis(inner_rows, after.get(inflow, {}).get('offset'),
                                                            rate, params, multiply_momentum=True)}
        if all_branches:
            results[name]['first_tracheal_differences'] = {
                view: {'pressure': earliest_observed_difference(result[view], all_pressures),
                       'inflow': earliest_observed_difference(result[view], all_inflows)}
                for view in ('control_minus_upstream', 'experiment_minus_upstream', 'experiment_minus_control')
            }
        replays[name] = {label: {key: value for key, value in sites.items()
                                 if key in ('interior', 'end', f'cell_{trachea_cells - 2}')}
                         for label, sites in runs.items()}
    write(out / 'trachea-interior-momentum-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'conditions': results, 'sample_rate_hz': rate,
            'window': window, 'trachea_cell_index': index, 'build': build}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', *(f'artifacts/{name}{suffix}' for name in CONDITIONS
                               for suffix in ('.json', '-candidate.csv', '-upstream.csv')))
    manifest, saved = registered_artifacts(case['baseline'], case['baseline'].get('case_id', BASE_ID), revision, names)
    entries = read(manifest)['inputs']
    patches = []
    patch_names = (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch', 'oec-neck-momentum.patch',
                   'oec-neck-linear.patch', 'trachea-end-momentum.patch')
    if case.get('momentum_scope') == 'all_tracheal_branches':
        patch_names += ('trachea-interior-momentum.patch',)
    for name in patch_names:
        row, = (item for item in entries if item['path'].endswith(f'/artifacts/{name}'))
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            parser.error(f'対象の先行差分が保存時と一致しません ({name})')
        patches.append(path)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_songbird_chirps_oec_neck_44100.py', 'measure_songbird_chirps_oec_neck_momentum_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_terminal_numerator_44100.py',
        'measure_songbird_chirps_trachea_end_balance_44100.py', 'measure_songbird_chirps_trachea_interior_balance_44100.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [case_path, Path(__file__), PROBE, manifest, *saved.values(), *patches, *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs', UPSTREAM / 'crates/chimera/tests/airway.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, case_path, inputs, details,
                              lambda out, execute: measure(case, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
