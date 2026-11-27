"""左鳴管ポートの気管支側半セルの慣性だけを切り替えて再描画する。"""

import argparse
from pathlib import Path
import subprocess
import sys

from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import DENSITY, ROOT, SPEED
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_left_syrinx_port_44100 import (
    AREA, BASE_ID, BRONCHUS, CASE as PORT_CASE, FLOW, TRACHEA, replay, stored_trace,
)
from measure_songbird_chirps_oec_neck_44100 import PREFIX_PATCHES, diagnose
from measure_songbird_chirps_oec_neck_momentum_44100 import compare_traces
from measure_songbird_chirps_oec_pressure_44100 import CONDITIONS, OEC
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_trachea_interior_balance_44100 import interior_columns
from measure_songbird_chirps_trachea_interior_momentum_44100 import apply_edits
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, PRESSURE, RADIATION
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-left-syrinx-half-inertance-44100.json'
LABELS = ('port-control', 'bronchus-half')
PATCH = 'left-syrinx-half-inertance'
FIRST_TRACHEAL_FLOW = interior_columns(1)[2]
RIGHT_FLOW = 'right_flow_cm3_s'
WALL_FLOW = 'trachea_wall_flow_cm3_s'


def edit_left_half(workspace, patch):
    edits = {
        NETWORK: (
            ('''    viscosity: f64,
) -> (f64, f64) {
    let half_sections = 0.5
        * AIR_DENSITY
        * (left.length_cm / left.area_cm2.max(1e-6) + right.length_cm / right.area_cm2.max(1e-6));''',
             '''    viscosity: f64,
    multiply_left_half: bool,
) -> (f64, f64) {
    let left_area = left.area_cm2.max(1e-6);
    let left_half = if multiply_left_half {
        left.length_cm * left_area.recip()
    } else {
        left.length_cm / left_area
    };
    let half_sections = 0.5 * AIR_DENSITY * (left_half + right.length_cm / right.area_cm2.max(1e-6));'''),
            ('''    fn new(nodes: [usize; 2], port: Option<Port>, sections: &[Section], viscosity: f64) -> Self {
        let [left, right]''',
             '''    fn new(
        nodes: [usize; 2],
        port: Option<Port>,
        sections: &[Section],
        viscosity: f64,
        multiply_left_half: bool,
    ) -> Self {
        let [left, right]'''),
            ('branch_impedance(left, right, port, viscosity)',
             'branch_impedance(left, right, port, viscosity, multiply_left_half)'),
            ('''    fn update_geometry(&mut self, sections: &[Section], viscosity: f64) {
        let next = Self::new(self.nodes, self.port, sections, viscosity);''',
             '''    fn update_geometry(&mut self, sections: &[Section], viscosity: f64, multiply_left_half: bool) {
        let next = Self::new(self.nodes, self.port, sections, viscosity, multiply_left_half);'''),
            ('Branch::new([left, right], port, sections, viscosity)',
             'Branch::new([left, right], port, sections, viscosity, false)'),
            ('branch_impedance(left, right, branch.port, viscosity)',
             'branch_impedance(left, right, branch.port, viscosity, false)'),
            ('self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0)',
             '''self.step_with_momentum_order(
            inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, 0..0, None,
        )'''),
            ('        trachea_momentum_branches: std::ops::Range<usize>,',
             '        trachea_momentum_branches: std::ops::Range<usize>,\n        left_half_branch: Option<usize>,'),
            ('            for (branch, &increment) in self.branches.iter_mut().zip(&self.port_area_increments_cm2)\n            {',
             '''            for (index, (branch, &increment)) in self.branches
                .iter_mut()
                .zip(&self.port_area_increments_cm2)
                .enumerate()
            {'''),
            ('                    branch.update_geometry(&self.sections, viscosity);',
             '''                    branch.update_geometry(&self.sections, viscosity, left_half_branch == Some(index));'''),
        ),
        SONGBIRD: (
            ('            self.trachea.first_branch..self.trachea.first_branch + self.trachea.count - 1,',
             '''            self.trachea.first_branch..self.trachea.first_branch + self.trachea.count - 1,
            Some(self.syrinx_ports[0]),'''),
        ),
    }
    apply_edits(workspace, patch, edits)


def baseline_patches(manifest, saved):
    names = (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch', 'oec-neck-momentum.patch',
             'oec-neck-linear.patch', 'trachea-end-momentum.patch', 'trachea-interior-momentum.patch')
    entries = read(manifest)['inputs']
    patches = []
    for name in names:
        entry, = (item for item in entries if item['path'].endswith(f'/artifacts/{name}'))
        path = ROOT / entry['path']
        if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
            raise ValueError(f'先行実行の差分が保存時と一致しません ({name})')
        patches.append(path)
    patches.append(saved['artifacts/trachea-all-momentum.patch'])
    build = read(saved['summary.json'])['build']
    if [sha256(path) for path in patches] != [*build['preceding_patch_sha256'], build['inlet_patch_sha256']]:
        raise ValueError('復元する差分の内容または適用順が先行実行と異なります')
    return patches


def configure(case, saved, out):
    configurations = {}
    for name in CONDITIONS:
        source = saved[f'artifacts/{name}.json']
        bird = read(source)['songbird_airway']
        event, = bird['events']
        start = case['condition_control_samples'][name]
        if (bird['sample_rate_hz'], bird['sample_count'], bird['control_block_samples'], event['sample'],
                bird['breath_gate'], event['breath_gate']) != (
                case['sample_rate_hz'], start + case['observation_internal_samples'], start, start, 0, 0):
            raise ValueError(f'保存した描画条件が事前登録と一致しません ({name})')
        configurations[name] = out / f'{name}.json'
        configurations[name].write_bytes(source.read_bytes())
    return configurations


def propagate(effect, distances, *, source_field=FLOW):
    if not effect:
        return True
    if source_field not in effect:
        return False
    origin = effect[source_field]['offset']
    return all(key not in effect or effect[key]['offset'] >= origin + delay for key, delay in distances.items())


def inlet_pressure(trace, start, port_case):
    geometry = port_case['geometry']
    length = geometry['trachea_length_cm'] / geometry['trachea_cells']
    area = geometry['trachea_area_cm2']
    dt = 1 / port_case['sample_rate_hz']
    compliance = area * length / (DENSITY * SPEED * SPEED)
    gain = dt / compliance
    rows = []
    for previous, current in zip(trace[start - 1:-1], trace[start:], strict=True):
        flows = {key: float(current[key]) for key in (FIRST_TRACHEAL_FLOW, FLOW, RIGHT_FLOW, WALL_FLOW)}
        pressure = float(previous[TRACHEA])
        predicted = update_inlet_pressure(pressure, flows, gain)
        rows.append({'previous_pressure': pressure, 'flows': flows, 'gain': gain,
                     'predicted': predicted, 'observed': float(current[TRACHEA])})
    return rows


def update_inlet_pressure(pressure, flows, gain):
    inflow = ((-flows[FIRST_TRACHEAL_FLOW] + flows[FLOW]) + flows[RIGHT_FLOW]) - flows[WALL_FLOW]
    return pressure + gain * inflow


def pressure_residual(local, offset, *, candidate_label=LABELS[1]):
    if offset is None:
        return None
    candidate, upstream = (local[label]['inlet_pressure'][offset] for label in (candidate_label, 'upstream'))
    replacements = {}
    for key, value in upstream['flows'].items():
        if candidate['flows'][key].hex() != value.hex():
            pressure = update_inlet_pressure(candidate['previous_pressure'], candidate['flows'] | {key: value},
                                             candidate['gain'])
            replacements[key] = {'pressure': pressure, 'matches_upstream': pressure.hex() == upstream['observed'].hex()}
    previous = update_inlet_pressure(upstream['previous_pressure'], candidate['flows'], candidate['gain'])
    replacements['previous_pressure'] = {'pressure': previous, 'matches_upstream': previous.hex() == upstream['observed'].hex()}
    return {'offset': offset, 'candidate': candidate, 'upstream': upstream, 'single_substitutions': replacements}


def measure(case, port_case, port_reference, saved, patches, snapshot, copies, out, execute):
    configurations = configure(case, saved, out)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit_left_half, patch_stem=PATCH, labels=LABELS)
    checks = {'edited_only_network_and_songbird': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'binary_changed': build['control_binary_sha256'] != build['experimental_binary_sha256']}
    results, replays, hypotheses = {}, {}, {}
    rate, window = case['sample_rate_hz'], case['observation_internal_samples']
    distances = case['distances_from_port_in_samples'] | {
        FIRST_TRACHEAL_FLOW: 1, WALL_FLOW: 1, PRESSURE: 16, DERIVATIVE: 22,
    }
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        archived = saved[f'artifacts/{name}-interior-momentum.csv']
        checks[f'{name}/control_reproduced'] = sha256(paths[LABELS[0]][name]) == sha256(archived)
        traces = {label: stored_trace(paths[label][name], start + window) for label in LABELS}
        traces['upstream'] = stored_trace(saved[f'artifacts/{name}-upstream.csv'], start + window)
        local = replays[name] = {}
        for label, trace in traces.items():
            flow = replay(trace, start, port_case, upstream=label == 'upstream', multiply_left_half=label == LABELS[1])
            pressure = inlet_pressure(trace, start, port_case)
            local[label] = {'port_flow': flow, 'inlet_pressure': pressure}
            checks[f'{name}/{label}/closed_flow_zero'] = all(row['observed'] == 0 for row in flow if row['closed'])
            checks[f'{name}/{label}/port_flow_bit_replayed'] = all(
                row['observed'].hex() == row['result']['flow'].hex() for row in flow)
            checks[f'{name}/{label}/inlet_pressure_bit_replayed'] = all(
                row['observed'].hex() == row['predicted'].hex() for row in pressure)
        control, variant, upper = traces.values()
        checks[f'{name}/left_and_right_port_geometry_identical'] = all(
            same_bits(control[key], variant[key]) and same_bits(control[key], upper[key])
            for key in (AREA, 'right_port_area_cm2'))
        result, _ = compare_traces(name, traces, start, case, case['neck'], checks, momentum_labels=LABELS,
                                   linear_labels=LABELS,
                                   extra_observed=(FLOW, BRONCHUS, TRACHEA, FIRST_TRACHEAL_FLOW, RIGHT_FLOW, WALL_FLOW),
                                   propagation=lambda effect, _: propagate(effect, distances))
        before, after, effect = (result[key] for key in ('control_minus_upstream', 'experiment_minus_upstream',
                                                        'experiment_minus_control'))
        original, remaining = (item.get(FLOW, {}).get('offset') for item in (before, after))
        checks[f'{name}/matches_registered_port_offset'] = (
            original == case['expected_control_flow_offsets'][name]
            == port_reference['conditions'][name]['first_differences'][FLOW])
        if original is not None:
            checks[f'{name}/first_port_difference_removed'] = remaining is None or remaining > original
            hypotheses[f'{name}/effect_starts_at_expected_port_offset'] = effect.get(FLOW, {}).get('offset') == original
        results[name] = result | {
            'first_residual_port_flow': diagnose(local[LABELS[1]]['port_flow'], local['upstream']['port_flow'],
                                                 remaining, rate, pressure_keys=('bronchus_pressure', 'trachea_pressure')),
            'first_residual_inlet_pressure': pressure_residual(local, after.get(TRACHEA, {}).get('offset')),
        }
    write(out / 'left-syrinx-half-inertance-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window,
            'conditions': results, 'build': build}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, port_case = read(CASE), read(PORT_CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', 'artifacts/trachea-all-momentum.patch',
             *(f'artifacts/{name}{suffix}' for name in CONDITIONS
               for suffix in ('.json', '-interior-momentum.csv', '-upstream.csv')))
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    port_manifest, port_saved = registered_artifacts(case['port_analysis'], port_case['id'], revision, ('summary.json',))
    if any(case[key] != port_case[key] for key in ('upstream_revision', 'sample_rate_hz', 'condition_control_samples')):
        parser.error('ポート初差の解析とケースの条件が一致しません')
    if not any(entry['path'] == PORT_CASE.relative_to(ROOT).as_posix() and entry['sha256'] == sha256(PORT_CASE)
               for entry in read(port_manifest)['inputs']):
        parser.error('解析時のポート定義が必要です')
    patches = baseline_patches(manifest, saved)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py',
        'measure_songbird_chirps_beak_tip_inflow.py', 'measure_songbird_chirps_beak_tip_inflow_44100.py',
        'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_songbird_chirps_beak_momentum_propagation_44100.py',
        'measure_songbird_chirps_left_syrinx_port_44100.py', 'measure_songbird_chirps_oec_neck_44100.py',
        'measure_songbird_chirps_oec_neck_momentum_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
        'measure_songbird_chirps_terminal_numerator_44100.py', 'measure_songbird_chirps_trachea_end_balance_44100.py',
        'measure_songbird_chirps_trachea_interior_balance_44100.py',
        'measure_songbird_chirps_trachea_interior_momentum_44100.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py', 'upstream_baseline.py')]
    inputs = [CASE, PORT_CASE, Path(__file__), manifest, *saved.values(), port_manifest, *port_saved.values(),
              *patches, *copies, *tools, UPPER_NETWORK, UPPER_SONGBIRD,
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs',
              UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, port_case, read(port_saved['summary.json']), saved,
                                                           patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
