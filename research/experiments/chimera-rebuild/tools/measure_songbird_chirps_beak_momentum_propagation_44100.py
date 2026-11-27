"""くちばし内部5枝の運動量の計算順を切り替え、放射までを比較する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_load import ROOT, beak_fields, inlet_replay, terminal_coefficients, terminal_replay
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, compare_steps, diagnose_difference
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC, observe
from measure_songbird_chirps_volume_rate_propagation_44100 import (
    DERIVATIVE, INJECTION, PRESSURE, RADIATION, bitwise_derivative, build_and_render,
    derivative_with_upstream_scale, differences, pressure_at_first_difference, stage_candidate,
)
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-beak-momentum-propagation-44100.json'
NETWORK = 'crates/vocal-core/src/airway/network.rs'
SONGBIRD = 'crates/vocal-core/src/airway/songbird.rs'


def momentum_patch(workspace, path):
    edits = {
        NETWORK: (
            ('fn step(&mut self, dt: f64, pressure_difference: f64) -> f64 {',
             'fn step(&mut self, dt: f64, pressure_difference: f64, multiply_momentum: bool) -> f64 {'),
            ('        let drive = pressure_difference + (carried_inertance / dt) * self.flow;',
             '''        let history = if multiply_momentum {
            (carried_inertance * self.flow) * dt.recip()
        } else {
            (carried_inertance / dt) * self.flow
        };
        let drive = pressure_difference + history;'''),
            ('        // 乱流が読むのは、断面を変更する前の枝面積と最後に解いた流量。',
             '''        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0)
    }

    pub(crate) fn step_with_momentum_order(
        &mut self,
        inlet: usize,
        inlet_flow_cm3_s: f64,
        prescribed: Option<(usize, f64)>,
        momentum_branches: std::ops::Range<usize>,
    ) -> NetworkSample {
        // 乱流が読むのは、断面を変更する前の枝面積と最後に解いた流量。'''),
            ('            let flow = branch.step(self.dt, difference);',
             '            let flow = branch.step(self.dt, difference, momentum_branches.contains(&index));'),
        ),
        SONGBIRD: (
            ('        let acoustic = self.net.step(self.sac, 0.0);',
             '''        let first_branch = self.beak.first_branch;
        let acoustic = self.net.step_with_momentum_order(
            self.sac,
            0.0,
            None,
            first_branch..first_branch + self.beak.count - 1,
        );'''),
        ),
    }
    patches = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = source.read_text()
        modified = original
        for anchor, replacement in recipe:
            if modified.count(anchor) != 1:
                raise ValueError(f'差分の適用位置が1箇所に定まりません ({relative})')
            modified = modified.replace(anchor, replacement, 1)
        patches.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                    f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    path.write_text(''.join(patches))


def render_variants(configurations, volume_patch, snapshot, copies, out, execute):
    paths = {kind: {name: out / f'{name}-{kind}.csv' for name in CONDITIONS}
             for kind in ('volume-control', 'momentum')}
    patch = out / 'beak-momentum.patch'
    with TemporaryDirectory(prefix='beak-momentum-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        workspace = scratch / 'candidate'
        target = scratch / 'target'
        stage_candidate(snapshot, copies, workspace)
        execute(['git', 'apply', '--check', str(volume_patch)], cwd=workspace)
        execute(['git', 'apply', str(volume_patch)], cwd=workspace)
        known = {source.relative_to(WORKSPACE): sha256(workspace / source.relative_to(WORKSPACE)) for source in copies}
        control = build_and_render(workspace, target, configurations, paths['volume-control'], execute)
        momentum_patch(workspace, patch)
        changed = [path.as_posix() for path, digest in known.items() if sha256(workspace / path) != digest]
        variant = build_and_render(workspace, target, configurations, paths['momentum'], execute)
    return paths, {'changed_paths': changed, 'baseline_volume_patch_sha256': sha256(volume_patch),
                   'momentum_patch_sha256': sha256(patch), 'control_binary_sha256': control,
                   'experimental_binary_sha256': variant}


def compare_terminal(variant, upper, tip, length, rate):
    prefix = f'beak_{tip}_'
    feed = prefix + 'inflow_cm3_s'
    pressure = prefix + 'pressure_dyn_cm2'
    capacitance, conductance, inertive_gain = terminal_coefficients(float(variant[prefix + 'area_cm2'][0]), length, rate)
    divided, multiplied = capacitance / (1 / rate), capacitance * rate
    candidate = terminal_replay(variant[feed], divided, conductance, inertive_gain, True)
    upstream = terminal_replay(upper[feed], multiplied, conductance, inertive_gain, False)
    only_upper_feed = terminal_replay(upper[feed], divided, conductance, inertive_gain, True)
    only_upper_load = terminal_replay(variant[feed], multiplied, conductance, inertive_gain, False)

    def offsets(calculated, reference):
        fields = {'tip_pressure': ('pressure', pressure), 'radiated_flow': ('flow', RADIATION)}
        result = {}
        for label, (computed, observed) in fields.items():
            diff = np.flatnonzero(calculated[computed].view(np.uint64) != reference[observed].view(np.uint64))
            result[label] = int(diff[0]) if diff.size else None
        return result

    own_reference = offsets(candidate, variant), offsets(upstream, upper)
    return {'own_state_replayed': all(offset is None for side in own_reference for offset in side.values()),
            'first_differences_after_only_upstream_feed': offsets(only_upper_feed, upper),
            'first_differences_after_only_upstream_load': offsets(only_upper_load, upper)}


def measure(case, base, upper, copies, snapshot, out, execute):
    configurations = {name: upper[f'artifacts/{name}.json'] for name in CONDITIONS}
    prior = read(base['summary.json'])
    rate, cutoff = case['sample_rate_hz'], case['volume_source_cutoff_hz']
    window, cells = case['observation_internal_samples'], case['beak_cells']
    length = case['beak_length_cm'] / cells
    fields = FIELDS + beak_fields(cells) + OEC
    measured = (PRESSURE, OEC[1], OEC[2], *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')),
                RADIATION, DERIVATIVE)
    if rate != 1 / (1 / rate):
        raise ValueError('実験式の時間換算が登録レートに一致しません')
    paths, build = render_variants(configurations, base['artifacts/volume-rate.patch'], snapshot, copies, out, execute)
    checks = {'only_registered_sources_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'experimental_binary_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'volume_patch_matches_reference': build['baseline_volume_patch_sha256'] == prior['build']['patch_sha256']}
    results = {}
    for name, config in configurations.items():
        settings = read(config)['songbird_airway']
        first, = (event['sample'] for event in settings['events'])
        count = first + window
        if (settings['sample_rate_hz'], settings['control_block_samples'], settings['sample_count'],
                settings['observe_oec'], settings['observe_beak']) != (rate, first, count, True, True):
            raise ValueError('内部レート、制御刻み、観測列が登録と一致しません')
        control_path, variant_path = (paths[kind][name] for kind in ('volume-control', 'momentum'))
        control = load_trace(control_path, fields + CANDIDATE_OEC, count)
        variant = load_trace(variant_path, fields + CANDIDATE_OEC, count)
        reference = load_trace(upper[f'artifacts/{name}-upstream.csv'], fields, count)
        checks[f'{name}/control_matches_prior_volume_run'] = sha256(control_path) == sha256(base[f'artifacts/{name}-multiply.csv'])
        checks[f'{name}/geometry_and_volume_injection_preserved'] = all(
            np.array_equal(control[key].view(np.uint64), variant[key].view(np.uint64))
            for key in (*[f'beak_{cell}_area_cm2' for cell in range(cells)], 'oec_area_cm2', OEC[0], INJECTION))
        checks[f'{name}/radiation_derivative_replayed'] = (
            bitwise_derivative(variant, first, rate, multiply=False) and bitwise_derivative(reference, first, rate, multiply=True))
        candidate_pressure = observe(variant, first, rate, cutoff, 'candidate', multiply_volume=True)
        fixed_pressure = observe(reference, first, rate, cutoff, 'upstream')
        checks[f'{name}/cavity_pressure_replayed'] = all(row['pressure'].hex() == row['observed_pressure'].hex()
                                                      for row in [*candidate_pressure, *fixed_pressure])

        trace_pair = {'candidate': variant, 'upstream': reference}
        branches, failures = [], []
        for cell in range(1, cells):
            areas, rows = compare_steps(trace_pair, first, count, cell, length, rate, multiply_momentum=True)
            failures.extend([cell, side, row['offset']] for row in rows for side in trace_pair
                            if row['replayed'][side]['inflow'].hex() != row['observed'][side].hex())
            branches.append({'entering_cell': cell, **diagnose_difference(rows, areas, length, rate, multiply_momentum=True)})
        checks[f'{name}/interior_branches_replayed_bitwise'] = not failures

        base_delta = differences(control[first:], reference[first:], measured, left_label='volume_control', right_label='upstream')
        variant_delta = differences(variant[first:], reference[first:], measured, left_label='momentum', right_label='upstream')
        change = differences(variant[first:], control[first:], measured, left_label='momentum', right_label='volume_control')
        pressure_offset = variant_delta.get(PRESSURE, {}).get('offset')
        terminal = compare_terminal(variant[first:], reference[first:], cells - 1, length, rate)
        checks[f'{name}/terminal_pressure_and_radiation_replayed'] = terminal['own_state_replayed']
        results[name] = {
            'event_sample': first, 'control_minus_upstream': base_delta,
            'momentum_minus_upstream': variant_delta, 'momentum_minus_control': change,
            'interior_branches': branches, 'branch_replay_mismatches': failures,
            'terminal_load_comparison': terminal,
            'first_residual_pressure_replay': pressure_at_first_difference(candidate_pressure, fixed_pressure, pressure_offset, rate),
            'derivative_replayed_with_upstream_scale': derivative_with_upstream_scale(variant, reference, first, rate),
            'control_and_momentum_csv_equal': sha256(control_path) == sha256(variant_path),
        }
        if name == 'matched_time' and OEC[2] in variant_delta:
            offset = variant_delta[OEC[2]]['offset']
            passed, normalizations = inlet_replay(variant[first:], reference[first:], offset, length,
                                                 float(variant[OEC[0]][first]), rate)
            results[name]['first_beak_inlet_replay'] = {'both_flows_replayed': passed, **normalizations}

    baseline = results['matched_time']['control_minus_upstream']
    remaining = results['matched_time']['momentum_minus_upstream']
    first_branch = 'beak_1_inflow_cm3_s'
    first_terminal = f'beak_{cells - 1}_inflow_cm3_s'
    checks['reference_onset_differences_reproduced'] = all(
        baseline.get(key, {}).get('offset') == expected for key, expected in (
            (first_branch, case['baseline_first_inner_flow_offset']), (RADIATION, case['baseline_first_radiated_flow_offset'])))
    hypotheses = {key: field not in remaining or remaining[field]['offset'] > baseline[field]['offset']
                  for key, field in (('first_inner_branch_difference_removed', first_branch),
                                     ('first_terminal_inflow_difference_delayed', first_terminal),
                                     ('first_radiated_flow_difference_delayed', RADIATION))}
    hypotheses['no_tracking_output_unchanged'] = results['no_tracking']['control_and_momentum_csv_equal']
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate,
            'changed_beak_cells': list(range(1, cells)), 'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    base_names = ['summary.json', 'artifacts/volume-rate.patch', *(f'artifacts/{name}-multiply.csv' for name in CONDITIONS)]
    upper_names = [file for name in CONDITIONS for file in (f'artifacts/{name}.json', f'artifacts/{name}-upstream.csv')]
    base, base_files = registered_artifacts(case['baseline'], 'songbird-chirps-volume-rate-propagation-44100', revision, base_names)
    upper, upper_files = registered_artifacts(case['upstream_observations'], 'songbird-chirps-oec-pressure-44100', revision, upper_names)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    inputs = [CASE, Path(__file__), base, upper, *base_files.values(), *upper_files.values(), *copies,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/tests/airway.rs',
              UPSTREAM / 'crates/chimera/tests/creature_realtime.rs',
              *(WORKSPACE / 'tools' / file for file in ('measure_songbird_airway.py', 'measure_songbird_syrinx.py',
                  'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
                  'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
                  'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_uniform_tube.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, base_files, upper_files, copies, snapshot, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
