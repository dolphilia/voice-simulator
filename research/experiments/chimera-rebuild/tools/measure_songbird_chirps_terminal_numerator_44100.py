"""鳴禽の先端放射負荷の旧圧係数だけを切り替え、反射側の流量を照合する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT, beak_fields, terminal_coefficients, terminal_replay
from measure_songbird_chirps_beak_tip_inflow import INPUTS, UPPER_NETWORK, UPPER_SONGBIRD, step
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_chirps_volume_rate_propagation_44100 import (
    DERIVATIVE, INJECTION, PRESSURE, RADIATION, bitwise_derivative, differences,
)
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-terminal-numerator-44100.json'
BASE_ID = 'songbird-chirps-oec-sum-order-44100'
AIRWAY = 'crates/vocal-core/src/airway.rs'
LABELS = ('sum-control', 'terminal-numerator')
PREFIX_PATCHES = ('volume-rate.patch', 'beak-momentum.patch', 'beak-inlet-rate.patch', 'beak-inlet-momentum.patch')


def edit_numerator(workspace, patch):
    edits = {
        AIRWAY: (
            ('    fn step(&mut self, dt: f64, compliance: f64, old_pressure: f64, inflow: f64) -> f64 {',
             '''    fn step(&mut self, dt: f64, compliance: f64, old_pressure: f64, inflow: f64) -> f64 {
        self.step_with_numerator(dt, compliance, old_pressure, inflow, false)
    }

    fn step_with_numerator(
        &mut self,
        dt: f64,
        compliance: f64,
        old_pressure: f64,
        inflow: f64,
        upstream_numerator: bool,
    ) -> f64 {'''),
            ('        let new_pressure = (old_pressure * (compliance_per_step - load) + inflow - old_load_flow)',
             '''        let pressure_weight = if upstream_numerator {
            compliance_per_step - 0.5 * half_inertance_gain - half_conductance
        } else {
            compliance_per_step - load
        };
        let new_pressure = (old_pressure * pressure_weight + inflow - old_load_flow)'''),
        ),
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None)'),
            ('        cavity_flow_order: Option<(usize, usize, usize)>,',
             '        cavity_flow_order: Option<(usize, usize, usize)>,\n        terminal_numerator_node: Option<usize>,'),
            ('                self.pressure[node] = load.step(self.dt, compliance, self.pressure[node], inflow);',
             '''                self.pressure[node] = load.step_with_numerator(
                    self.dt, compliance, self.pressure[node], inflow, terminal_numerator_node == Some(node),
                );'''),
        ),
        SONGBIRD: (
            ('            Some((self.oec, self.oec_neck, self.beak_inlet)),',
             '            Some((self.oec, self.oec_neck, self.beak_inlet)),\n            Some(self.beak.last()),'),
        ),
    }
    diff = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = modified = source.read_text()
        for anchor, replacement in recipe:
            if modified.count(anchor) != 1:
                raise ValueError(f'放射負荷の差分を適用する位置が1箇所に定まりません ({relative})')
            modified = modified.replace(anchor, replacement, 1)
        diff.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                 f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    patch.write_text(''.join(diff))


def same_bits(left, right):
    return np.array_equal(left.view(np.uint64), right.view(np.uint64))


def first_offset(left, right):
    unequal = np.flatnonzero(left.view(np.uint64) != right.view(np.uint64))
    return int(unequal[0]) if unequal.size else None


def causal_return(change, tip, window):
    first_pressure = change.get(f'beak_{tip}_pressure_dyn_cm2', {}).get('offset', window)
    delays = {PRESSURE: tip + 1, OEC[1]: tip + 2}
    for cell in range(tip + 1):
        delays[f'beak_{cell}_pressure_dyn_cm2'] = tip - cell
        delays[f'beak_{cell}_inflow_cm3_s'] = tip - cell + 1
    return all(change[field]['offset'] >= first_pressure + delay for field, delay in delays.items() if field in change)


def replay_terminal(traces, start, tip, length, rate):
    area = f'beak_{tip}_area_cm2'
    pressure = f'beak_{tip}_pressure_dyn_cm2'
    feed = f'beak_{tip}_inflow_cm3_s'
    control, variant, upstream = traces.values()
    aperture = float(control[area][0])
    capacitance, g, h = terminal_coefficients(aperture, length, rate)
    divided, multiplied = capacitance / (1 / rate), capacitance * rate
    pressure_coefficients = {'sum_control': divided - (g + 0.5 * h),
                             'terminal_numerator': divided - 0.5 * h - g,
                             'upstream': multiplied - 0.5 * h - g}
    denominator = divided + (g + 0.5 * h)
    upstream_denominator = multiplied + 0.5 * h + g
    checks = {'static_aperture_and_resting_initial_load': all(
        (trace[area] == aperture).all() and all((trace[field][:start] == 0).all() for field in (pressure, feed, RADIATION))
        for trace in traces.values()),
        'candidate_and_upstream_denominator_bit_equal': denominator.hex() == upstream_denominator.hex(),
        'numerator_pressure_coefficient_changed': pressure_coefficients['sum_control'].hex() !=
        pressure_coefficients['terminal_numerator'].hex()}
    for label, (trace, scale, grouped, numerator_grouped) in zip(traces, (
        (control, divided, True, True), (variant, divided, True, False), (upstream, multiplied, False, False),
    ), strict=True):
        replay = terminal_replay(trace[feed][start:], scale, g, h, grouped, numerator_grouped=numerator_grouped)
        checks[f'{label}/load_replayed'] = (same_bits(replay['pressure'], trace[pressure][start:])
                                             and same_bits(replay['flow'], trace[RADIATION][start:]))

    feed_offset = first_offset(variant[feed][start:], control[feed][start:])
    prefix = slice(None, feed_offset)
    swapped = {}
    for label, trace in (('control_feed', control), ('upstream_feed', upstream)):
        replay = terminal_replay(trace[feed][start:], divided, g, h, True, numerator_grouped=False)
        swapped[label] = {field: first_offset(replay[field], upstream[key][start:])
                          for field, key in (('pressure', pressure), ('flow', RADIATION))}
        if label == 'control_feed':
            checks['numerator_only_replay_matches_until_return'] = all(
                same_bits(replay[field][prefix], variant[key][start:][prefix])
                for field, key in (('pressure', pressure), ('flow', RADIATION)))
    return checks, {'pressure_coefficients_hex': {key: value.hex() for key, value in pressure_coefficients.items()},
                    'denominator_hex': denominator.hex(), 'upstream_denominator_hex': upstream_denominator.hex(),
                    'first_residual_with_feed_substitution': swapped}


def replay_branch(trace, start, tip, length, rate, arithmetic):
    pressure_left = f'beak_{tip - 1}_pressure_dyn_cm2'
    pressure_tip = f'beak_{tip}_pressure_dyn_cm2'
    flow = f'beak_{tip}_inflow_cm3_s'
    areas = tuple(float(trace[f'beak_{cell}_area_cm2'][0]) for cell in (tip - 1, tip))
    column_names = pressure_left, pressure_tip, flow
    replay = []
    for before, after in zip(trace[start - 1:-1], trace[start:], strict=True):
        inputs = dict(zip(INPUTS, (*(float(before[key]) for key in column_names), arithmetic), strict=True))
        replay.append({'inputs': inputs, 'calculated': step(inputs, areas, length, rate, multiply_momentum=True),
                       'observed_flow': float(after[flow])})
    return replay


def measure(case, saved, patches, snapshot, copies, out, execute):
    rate, cells, window = (case[key] for key in ('sample_rate_hz', 'beak_cells', 'observation_internal_samples'))
    tip, length = cells - 1, case['beak_length_cm'] / cells
    pressure, feed = f'beak_{tip}_pressure_dyn_cm2', f'beak_{tip}_inflow_cm3_s'
    fields = FIELDS + beak_fields(cells) + OEC
    observed = (PRESSURE, OEC[1], *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')), RADIATION, DERIVATIVE)
    configurations = {name: saved[f'artifacts/{name}.json'] for name in CONDITIONS}
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute, edit=edit_numerator,
                                   patch_stem='terminal-numerator', labels=LABELS)
    prior_build = read(saved['summary.json'])['build']
    checks = {'only_registered_sources_changed': set(build['changed_paths']) == {AIRWAY, NETWORK, SONGBIRD},
              'baseline_patch_chain_matches': build['preceding_patch_sha256'] ==
              [*prior_build['preceding_patch_sha256'], prior_build['inlet_patch_sha256']],
              'binaries_differ': build['control_binary_sha256'] != build['experimental_binary_sha256']}
    results = {}
    case_columns = ('oec_area_cm2', OEC[0], INJECTION, *(f'beak_{cell}_area_cm2' for cell in range(cells)))
    for name, definition in configurations.items():
        settings = read(definition)['songbird_airway']
        start = case['condition_control_samples'][name]
        event, = settings['events']
        if (event['sample'], settings['control_block_samples'], settings['sample_rate_hz'],
                settings['sample_count'], settings['observe_beak'], settings['observe_oec'],
                settings['breath_gate'], event['breath_gate']) != (start, start, rate, start + window, True, True, 0, 0):
            raise ValueError(f'観測窓が登録条件と一致しません ({name})')
        control_file, variant_file = (paths[label][name] for label in LABELS)
        reference_file = saved[f'artifacts/{name}-upstream.csv']
        checks[f'{name}/baseline_csv_reproduced'] = sha256(control_file) == sha256(saved[f'artifacts/{name}-neck-first.csv'])
        control, variant = (load_trace(path, fields + CANDIDATE_OEC, start + window) for path in (control_file, variant_file))
        upstream = load_trace(reference_file, fields, start + window)
        traces = {'sum_control': control, 'terminal_numerator': variant, 'upstream': upstream}
        if name == 'no_tracking':
            checks['no_tracking_acoustic_columns_all_zero'] = all(
                (trace[key] == 0).all() for trace in traces.values() for key in observed)
        checks[f'{name}/shape_and_injection_identical'] = all(same_bits(control[key], variant[key]) for key in case_columns)
        checks[f'{name}/pre_key_acoustic_columns_identical'] = all(
            same_bits(control[key][:start], variant[key][:start]) for key in observed)
        local_checks, terminal = replay_terminal(traces, start, tip, length, rate)
        checks.update((f'{name}/{key}', status) for key, status in local_checks.items())
        branches = {}
        for label, trace in traces.items():
            branches[label] = replay_branch(trace, start, tip, length, rate, 'upstream' if label == 'upstream' else 'candidate')
            checks[f'{name}/{label}/last_branch_replayed'] = all(
                row['observed_flow'].hex() == row['calculated']['inflow'].hex() for row in branches[label])
            checks[f'{name}/{label}/radiation_derivative_replayed'] = bitwise_derivative(trace, start, rate, multiply=label == 'upstream')

        before = differences(control[start:], upstream[start:], observed, left_label='sum_control', right_label='upstream')
        after = differences(variant[start:], upstream[start:], observed, left_label='terminal_numerator', right_label='upstream')
        change = differences(variant[start:], control[start:], observed, left_label='terminal_numerator', right_label='sum_control')
        checks[f'{name}/return_does_not_precede_tip_pressure'] = causal_return(change, tip, window)
        return_offset = change.get(feed, {}).get('offset')
        first_return = None
        if return_offset is not None:
            base, experiment = (branches[label][return_offset] for label in ('sum_control', 'terminal_numerator'))
            inputs = base['inputs'] | {'tip_pressure': experiment['inputs']['tip_pressure']}
            areas = tuple(float(control[f'beak_{cell}_area_cm2'][0]) for cell in (tip - 1, tip))
            replay = step(inputs, areas, length, rate, multiply_momentum=True)
            checks[f'{name}/previous_tip_pressure_alone_replays_first_return'] = (
                replay['inflow'].hex() == experiment['observed_flow'].hex())
            first_return = {'offset': return_offset, 'sum_control': base, 'terminal_numerator': experiment,
                            'only_replaced_tip_pressure': replay}
        results[name] = {'event_sample': start, 'sum_control_minus_upstream': before,
                         'terminal_numerator_minus_upstream': after, 'terminal_numerator_minus_sum_control': change,
                         'terminal_load': terminal, 'first_return': first_return}

    matched = results['matched_time']
    before, after = (matched[key] for key in ('sum_control_minus_upstream', 'terminal_numerator_minus_upstream'))
    offsets = case['expected_baseline_matched_time_offsets']
    checks['matched_time_baseline_offsets_reproduced'] = all(
        before.get(key, {}).get('offset') == offsets[label]
        for key, label in ((pressure, 'tip_pressure'), (feed, 'tip_inflow'), (RADIATION, 'radiation_flow')))
    hypotheses = {'matched_time_first_tip_pressure_residual_delayed': after.get(pressure, {}).get('offset', window) > offsets['tip_pressure'],
                  'matched_time_first_radiation_flow_residual_delayed': after.get(RADIATION, {}).get('offset', window) > offsets['radiation_flow']}
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'window': window,
            'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', 'artifacts/oec-sum-order.patch', *(f'artifacts/{name}{suffix}'
             for name in CONDITIONS for suffix in ('.json', '-neck-first.csv', '-upstream.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    registered = read(manifest_path)['inputs']
    patches = []
    for name in PREFIX_PATCHES:
        entry, = (row for row in registered if row['path'].endswith(f'/artifacts/{name}'))
        path = ROOT / entry['path']
        if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
            parser.error(f'先行差分が保存時のサイズまたはSHA-256と一致しません ({name})')
        patches.append(path)
    patches.append(saved['artifacts/oec-sum-order.patch'])
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), manifest_path, *saved.values(), *patches[:-1], *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/tests/airway.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
