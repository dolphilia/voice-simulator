"""口腔食道腔の流量収支の順序を切り替え、押鍵後64点を比較する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import ENTRY, NETWORK, SONGBIRD, inlet_step, render_variants
from measure_songbird_chirps_beak_load import ROOT, beak_fields, terminal_coefficients, terminal_replay
from measure_songbird_chirps_beak_momentum_propagation_44100 import compare_terminal
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC, observe
from measure_songbird_chirps_volume_rate_propagation_44100 import (
    DERIVATIVE, INJECTION, PRESSURE, RADIATION, bitwise_derivative, derivative_with_upstream_scale, differences,
    pressure_at_first_difference,
)
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-oec-sum-order-44100.json'
LABELS = ('momentum-control', 'neck-first')


def apply_sum_order_patch(workspace, path):
    edits = {
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None)'),
            ('        linear_inertance_branch: Option<usize>,',
             '        linear_inertance_branch: Option<usize>,\n        cavity_flow_order: Option<(usize, usize, usize)>,'),
            ('        for (index, (branch, &noise)) in self',
             '''        let cavity_injection = cavity_flow_order.map(|(cavity, _, _)| self.net_flow[cavity]);
        for (index, (branch, &noise)) in self'''),
            ('        let mut wall_radiation = 0.0;',
             '''        if let (Some((cavity, neck, beak)), Some(injection)) = (cavity_flow_order, cavity_injection) {
            self.net_flow[cavity] = (injection + self.branches[neck].flow) - self.branches[beak].flow;
        }

        let mut wall_radiation = 0.0;'''),
        ),
        SONGBIRD: (
            ('            Some(self.beak_inlet),',
             '            Some(self.beak_inlet),\n            Some((self.oec, self.oec_neck, self.beak_inlet)),'),
            ('            neck_precedes_beak: self.oec_neck < self.beak_inlet,',
             '            neck_precedes_beak: true,'),
        ),
    }
    patches = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = source.read_text()
        modified = original
        for anchor, replacement in recipe:
            if modified.count(anchor) != 1:
                raise ValueError(f'腔の収支順を変更する位置が1箇所に定まりません ({relative})')
            modified = modified.replace(anchor, replacement, 1)
        patches.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                    f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    path.write_text(''.join(patches))


def extend_cases(case, original, out):
    configurations = {}
    for name in CONDITIONS:
        configuration = read(original[f'artifacts/{name}.json'])
        settings = configuration['songbird_airway']
        first, = (event['sample'] for event in settings['events'])
        if (settings['sample_rate_hz'], settings['sample_count'] - first, settings['control_block_samples'],
                settings['observe_oec'], settings['observe_beak']) != (
                case['sample_rate_hz'], case['reference_observation_internal_samples'], first, True, True):
            raise ValueError('先行実行の内部レート、観測窓またはCSV設定が一致しません')
        if not 0 < case['observation_internal_samples'] <= first:
            raise ValueError('延長窓は最初の制御区間内としてください')
        settings['sample_count'] = first + case['observation_internal_samples']
        path = out / f'{name}.json'
        write(path, configuration)
        configurations[name] = path
    return configurations


def compare_prefix(actual, original, lines):
    saved = original.read_bytes().splitlines(keepends=True)
    return len(saved) == lines and actual.read_bytes().splitlines(keepends=True)[:lines] == saved


def terminal_operation_swaps(variant, reference, cells, length, rate):
    tip = f'beak_{cells - 1}_'
    feed = variant[tip + 'inflow_cm3_s']
    area = float(variant[tip + 'area_cm2'][0])
    capacitance, conductance, inertive_gain = terminal_coefficients(area, length, rate)
    divided, multiplied = capacitance / (1 / rate), capacitance * rate
    result = {'normalized_capacitance': {'division': divided.hex(), 'multiplication': multiplied.hex()}}
    for label, scaled, grouped in (('upstream_scale_only', multiplied, True), ('upstream_grouping_only', divided, False)):
        predicted = terminal_replay(feed, scaled, conductance, inertive_gain, grouped)
        result[label] = {}
        for column, field in (('pressure', tip + 'pressure_dyn_cm2'), ('flow', RADIATION)):
            unequal = np.flatnonzero(predicted[column].view(np.uint64) != reference[field].view(np.uint64))
            result[label][column] = int(unequal[0]) if unequal.size else None
    return result


def measure(case, archives, copies, snapshot, out, execute):
    base, upper, patches = archives
    configurations = extend_cases(case, upper, out)
    prior = read(base['summary.json'])
    rate, cutoff, cells = case['sample_rate_hz'], case['volume_source_cutoff_hz'], case['beak_cells']
    window, length = case['observation_internal_samples'], case['beak_length_cm'] / cells
    fields = FIELDS + beak_fields(cells) + OEC
    observed = (PRESSURE, OEC[1], *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')), RADIATION, DERIVATIVE)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=apply_sum_order_patch, patch_stem='oec-sum-order', labels=LABELS)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    checks = {'only_registered_sources_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'baseline_patches_match': build['preceding_patch_sha256'] ==
              [*prior['build']['preceding_patch_sha256'], prior['build']['inlet_patch_sha256']],
              'binaries_differ': build['control_binary_sha256'] != build['experimental_binary_sha256']}
    results, replays = {}, {}
    for name, definition in configurations.items():
        settings = read(definition)['songbird_airway']
        first = settings['events'][0]['sample']
        count = settings['sample_count']
        prefix_lines = first + case['reference_observation_internal_samples'] + 1
        control_file, experimental_file = (paths[label][name] for label in LABELS)
        upstream_file = out / f'{name}-upstream.csv'
        execute([str(probe), str(definition)], cwd=UPSTREAM, stdout=upstream_file)
        checks[f'{name}/control_prefix_reproduced'] = compare_prefix(
            control_file, base[f'artifacts/{name}-inlet-momentum.csv'], prefix_lines)
        checks[f'{name}/upstream_prefix_reproduced'] = compare_prefix(
            upstream_file, upper[f'artifacts/{name}-upstream.csv'], prefix_lines)
        control = load_trace(control_file, fields + CANDIDATE_OEC, count)
        variant = load_trace(experimental_file, fields + CANDIDATE_OEC, count)
        reference = load_trace(upstream_file, fields, count)
        shape = ('oec_area_cm2', OEC[0], *(f'beak_{cell}_area_cm2' for cell in range(cells)), INJECTION)
        checks[f'{name}/same_shape_and_injection'] = all(
            np.array_equal(control[key].view(np.uint64), variant[key].view(np.uint64)) for key in shape)
        checks[f'{name}/cavity_order_confirmed'] = bool(
            (control[OEC[3]] == 0).all() and (variant[OEC[3]] == 1).all() and (reference[OEC[3]] == 1).all())
        series = {}
        for side, trace in zip((*LABELS, 'upstream'), (control, variant, reference), strict=True):
            upper_side = side == 'upstream'
            pressures = observe(trace, first, rate, cutoff, 'upstream' if upper_side else 'candidate', multiply_volume=True)
            series[side] = pressures
            checks[f'{name}/{side}/cavity_pressure_replayed'] = all(
                row['observed_pressure'].hex() == row['pressure'].hex() for row in pressures)
            checks[f'{name}/{side}/inlet_flow_replayed'] = all(
                row['observed_inflow'].hex() == row['inflow'].hex()
                for row in (inlet_step(trace[i - 1], trace[i], length, rate, upstream=upper_side,
                                       multiply_linear=True, multiply_momentum=True) for i in range(first, count)))
            checks[f'{name}/{side}/radiation_derivative_replayed'] = bitwise_derivative(trace, first, rate, multiply=upper_side)
        replays[name] = series
        before = differences(control[first:], reference[first:], observed, left_label='momentum_control', right_label='upstream')
        after = differences(variant[first:], reference[first:], observed, left_label='neck_first', right_label='upstream')
        terminal = compare_terminal(variant[first:], reference[first:], cells - 1, length, rate)
        checks[f'{name}/terminal_pressure_and_flow_replayed'] = terminal['own_state_replayed']
        results[name] = {'event_sample': first, 'control_minus_upstream': before, 'neck_first_minus_upstream': after,
                         'control_local_pressure_replay': pressure_at_first_difference(
                             series[LABELS[0]], series['upstream'], before.get(PRESSURE, {}).get('offset'), rate),
                         'variant_local_pressure_replay': pressure_at_first_difference(
                             series[LABELS[1]], series['upstream'], after.get(PRESSURE, {}).get('offset'), rate),
                         'terminal_load_comparison': terminal,
                         'terminal_operation_swaps': terminal_operation_swaps(variant[first:], reference[first:], cells, length, rate),
                         'derivative_replayed_with_upstream_scale': derivative_with_upstream_scale(variant, reference, first, rate),
                         'control_and_variant_acoustic_columns_equal': all(
                             np.array_equal(control[key].view(np.uint64), variant[key].view(np.uint64)) for key in observed)}

    matched = results['matched_time']
    before, after = (matched[key] for key in ('control_minus_upstream', 'neck_first_minus_upstream'))
    offset = case['baseline_cavity_pressure_first_difference']
    checks['prior_matched_time_pressure_offset_reproduced'] = before.get(PRESSURE, {}).get('offset') == offset
    hypotheses = {
        'first_cavity_pressure_difference_delayed': PRESSURE not in after or after[PRESSURE]['offset'] > offset,
        'earliest_inlet_difference_delayed': ENTRY in before and (ENTRY not in after or after[ENTRY]['offset'] > before[ENTRY]['offset']),
        'earliest_neck_flow_difference_remains': OEC[1] in before and OEC[1] in after and
        before[OEC[1]]['offset'] == after[OEC[1]]['offset'],
        'no_tracking_acoustics_unchanged': results['no_tracking']['control_and_variant_acoustic_columns_equal'],
    }
    write(out / 'cavity-sum-replay.json', replays)
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
    base_id = 'songbird-chirps-beak-inlet-momentum-44100'
    base_names = ['summary.json', 'artifacts/beak-inlet-momentum.patch', *(f'artifacts/{name}-inlet-momentum.csv' for name in CONDITIONS)]
    base_path, base = registered_artifacts(case['baseline'], base_id, revision, base_names)
    recorded = read(base_path)
    saved_case_name = (WORKSPACE / 'cases' / f'{base_id}.json').relative_to(ROOT).as_posix()
    old_case = base_path.parent / recorded['source_snapshot'] / saved_case_name
    expected_hash, = (row['sha256'] for row in recorded['inputs'] if row['path'] == saved_case_name)
    if expected_hash != sha256(old_case):
        parser.error('前回のケース定義が保存時のSHA-256と一致しません')
    prior = read(old_case)
    specs = (('volume_patch', 'songbird-chirps-volume-rate-propagation-44100', 'volume-rate.patch'),
             ('inner_momentum_patch', 'songbird-chirps-beak-momentum-propagation-44100', 'beak-momentum.patch'),
             ('baseline', 'songbird-chirps-beak-inlet-rate-propagation-44100', 'beak-inlet-rate.patch'))
    previous = [registered_artifacts(prior[key], case_id, revision, (f'artifacts/{file}',))
                for key, case_id, file in specs]
    patches = [files[f'artifacts/{file}'] for (_, files), (_, _, file) in zip(previous, specs, strict=True)]
    patches.append(base['artifacts/beak-inlet-momentum.patch'])
    upper_names = [file for name in CONDITIONS for file in (f'artifacts/{name}.json', f'artifacts/{name}-upstream.csv')]
    upper_path, upper = registered_artifacts(prior['upstream_observations'], 'songbird-chirps-oec-pressure-44100', revision, upper_names)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_syrinx.py', 'measure_songbird_chirps_beak_load.py',
        'measure_songbird_chirps_beak_tip_inflow.py', 'measure_songbird_chirps_beak_tip_inflow_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_chirps_beak_momentum_propagation_44100.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), PROBE, base_path, old_case, upper_path, *base.values(), *upper.values(), *patches,
              *(path for path, _ in previous), *copies, *tools, UPPER_NETWORK, UPPER_SONGBIRD,
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs', UPSTREAM / 'crates/chimera/tests/airway.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, (base, upper, patches), copies, snapshot, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
