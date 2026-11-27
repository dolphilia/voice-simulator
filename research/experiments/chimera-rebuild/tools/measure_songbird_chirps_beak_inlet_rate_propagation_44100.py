"""くちばし入口の線形係数だけを揃え、圧力から放射までを照合する。"""

import argparse
from difflib import unified_diff
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_load import DENSITY, ROOT, beak_fields
from measure_songbird_chirps_beak_momentum_propagation_44100 import NETWORK, SONGBIRD, compare_terminal
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, solve, substitutions
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


CASE = WORKSPACE / 'cases/songbird-chirps-beak-inlet-rate-propagation-44100.json'
ENTRY = 'beak_0_inflow_cm3_s'


def apply_inlet_patch(workspace, path):
    edits = {
        NETWORK: (
            ('    fn step(&mut self, dt: f64, pressure_difference: f64, multiply_momentum: bool) -> f64 {',
             '''    fn step(
        &mut self,
        dt: f64,
        pressure_difference: f64,
        multiply_momentum: bool,
        multiply_linear_inertance: bool,
    ) -> f64 {'''),
            ('        let inertance_per_step = self.inertance / dt;',
             '''        let inertance_per_step = if multiply_linear_inertance {
            self.inertance * dt.recip()
        } else {
            self.inertance / dt
        };'''),
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None)'),
            ('        momentum_branches: std::ops::Range<usize>,',
             '        momentum_branches: std::ops::Range<usize>,\n        linear_inertance_branch: Option<usize>,'),
            ('            let flow = branch.step(self.dt, difference, momentum_branches.contains(&index));',
             '''            let flow = branch.step(
                self.dt,
                difference,
                momentum_branches.contains(&index),
                linear_inertance_branch == Some(index),
            );'''),
        ),
        SONGBIRD: (
            ('            first_branch..first_branch + self.beak.count - 1,',
             '            first_branch..first_branch + self.beak.count - 1,\n            Some(self.beak_inlet),'),
        ),
    }
    patches = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = source.read_text()
        modified = original
        for anchor, replacement in recipe:
            if modified.count(anchor) != 1:
                raise ValueError(f'入口の差分の適用位置が1箇所に定まりません ({relative})')
            modified = modified.replace(anchor, replacement, 1)
        patches.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                    f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    path.write_text(''.join(patches))


def compare_archived_build_inputs(manifest, sources):
    entries = {row['path']: row['sha256'] for row in read(manifest)['inputs']}
    return all(entries.get(path.relative_to(ROOT).as_posix()) == sha256(path) for path in sources)


def render_variants(configurations, previous_patches, snapshot, copies, out, execute, *,
                    edit=apply_inlet_patch, patch_stem='beak-inlet-rate', labels=('momentum-control', 'inlet')):
    control_label, variant_label = labels
    paths = {kind: {name: out / f'{name}-{kind}.csv' for name in configurations} for kind in labels}
    patch = out / f'{patch_stem}.patch'
    with TemporaryDirectory(prefix=f'{patch_stem}-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        workspace = scratch / 'candidate'
        target = scratch / 'target'
        stage_candidate(snapshot, copies, workspace)
        for previous_patch in previous_patches:
            execute(['git', 'apply', '--check', str(previous_patch)], cwd=workspace)
            execute(['git', 'apply', str(previous_patch)], cwd=workspace)
        known = {source.relative_to(WORKSPACE): sha256(workspace / source.relative_to(WORKSPACE)) for source in copies}
        control = build_and_render(workspace, target, configurations, paths[control_label], execute)
        edit(workspace, patch)
        changed = [path.as_posix() for path, digest in known.items() if sha256(workspace / path) != digest]
        experimental = build_and_render(workspace, target, configurations, paths[variant_label], execute)
    return paths, {'changed_paths': changed, 'preceding_patch_sha256': [sha256(path) for path in previous_patches],
                   'inlet_patch_sha256': sha256(patch), 'control_binary_sha256': control,
                   'experimental_binary_sha256': experimental}


def inlet_inertance(areas, lengths, upstream):
    if upstream:
        terms = [length * (1 / area) for length, area in zip(lengths, areas, strict=True)]
    else:
        terms = [length / area for length, area in zip(lengths, areas, strict=True)]
    return 0.5 * DENSITY * (terms[0] + terms[1])


def inlet_step(previous, current, length, rate, *, upstream=False, multiply_linear=False, multiply_momentum=False):
    areas = tuple(float(current[key]) for key in ('oec_area_cm2', 'beak_0_area_cm2'))
    prior_areas = tuple(float(previous[key]) for key in ('oec_area_cm2', 'beak_0_area_cm2'))
    lengths = (float(current[OEC[0]]), length)
    inertance = inlet_inertance(areas, lengths, upstream)
    carried = min(inertance, inlet_inertance(prior_areas, lengths, upstream))
    inverse = tuple(1 / area for area in areas)
    old_flow = float(previous[ENTRY])
    pressure_delta = float(previous[PRESSURE]) - float(previous['beak_0_pressure_dyn_cm2'])
    dt = 1 / rate
    if upstream:
        viscosity = math.sqrt(DENSITY * 1.86e-4 * (math.tau * 700) / 2)
        halves = [factor * 2 * math.sqrt(math.pi) * dx * math.sqrt(area) * inv * inv
                  for factor, dx, area, inv in zip((1.2, 1.0), lengths, areas, inverse, strict=True)]
    else:
        viscosity = math.sqrt(DENSITY * 1.86e-4 * math.tau * 700 / 2)
        halves = [2 * math.sqrt(math.pi * area) * dx / (area * area) * factor
                  for factor, dx, area in zip((1.2, 1.0), lengths, areas, strict=True)]
    history = ((carried * old_flow) * rate if upstream or multiply_momentum else (carried / dt) * old_flow)
    resistance = 0.5 * viscosity * (halves[0] + halves[1])
    drive = pressure_delta + history
    expansion = inverse[0] - inverse[1]
    if drive < 0.0:
        expansion = -expansion
    if upstream:
        factor = 0.5 * DENSITY if expansion >= 0.0 else 0.1 * 0.5 * DENSITY
        loss = factor * expansion * expansion
    else:
        factor = 1.0 if expansion >= 0.0 else 0.1
        loss = factor * (0.5 * DENSITY * (expansion * expansion))
    normalized = inertance * rate if upstream or multiply_linear else inertance / dt
    linear = normalized + resistance
    denominator, flow = solve(drive, linear, loss)
    return {'areas_cm2': areas, 'previous_areas_cm2': prior_areas, 'inertance': inertance,
            'pressure_difference': pressure_delta, 'normalized_momentum': history, 'normalized_inertance': normalized,
            'resistance': resistance, 'linear_coefficient': linear, 'quadratic_coefficient': loss,
            'drive': drive, 'denominator': denominator, 'inflow': flow, 'observed_inflow': float(current[ENTRY])}


def measure(case, base, upper, volume, copies, snapshot, out, execute):
    configurations = {name: upper[f'artifacts/{name}.json'] for name in CONDITIONS}
    prior = read(base['summary.json'])
    patches = (volume['artifacts/volume-rate.patch'], base['artifacts/beak-momentum.patch'])
    rate, cells, cutoff = case['sample_rate_hz'], case['beak_cells'], case['volume_source_cutoff_hz']
    window, length = case['observation_internal_samples'], case['beak_length_cm'] / cells
    fields = FIELDS + beak_fields(cells) + OEC
    observed = (PRESSURE, OEC[1], OEC[2], *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')),
                RADIATION, DERIVATIVE)
    if rate != 1 / (1 / rate):
        raise ValueError('実験式の時間換算が登録レートに一致しません')
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute)
    checks = {'only_registered_sources_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'experimental_binary_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'baseline_patches_match_reference': build['preceding_patch_sha256'] ==
              [prior['build']['baseline_volume_patch_sha256'], prior['build']['momentum_patch_sha256']]}
    results, replays = {}, {}
    for name, config in configurations.items():
        settings = read(config)['songbird_airway']
        first, = (event['sample'] for event in settings['events'])
        count = first + window
        if (settings['sample_rate_hz'], settings['sample_count'], settings['control_block_samples'],
                settings['observe_oec'], settings['observe_beak']) != (rate, count, first, True, True):
            raise ValueError('制御周期または観測列が登録と一致しません')
        control_path, variant_path = (paths[kind][name] for kind in ('momentum-control', 'inlet'))
        control = load_trace(control_path, fields + CANDIDATE_OEC, count)
        variant = load_trace(variant_path, fields + CANDIDATE_OEC, count)
        reference = load_trace(upper[f'artifacts/{name}-upstream.csv'], fields, count)
        checks[f'{name}/control_matches_prior_momentum_run'] = sha256(control_path) == sha256(base[f'artifacts/{name}-momentum.csv'])
        checks[f'{name}/geometry_and_injection_preserved'] = all(
            np.array_equal(control[key].view(np.uint64), variant[key].view(np.uint64))
            for key in (*(f'beak_{cell}_area_cm2' for cell in range(cells)), 'oec_area_cm2', OEC[0], INJECTION))
        records = {}
        for label, trace in (('control', control), ('inlet', variant), ('upstream', reference)):
            records[label] = [inlet_step(trace[index - 1], trace[index], length, rate, upstream=label == 'upstream',
                                         multiply_linear=label == 'inlet') for index in range(first, count)]
            checks[f'{name}/{label}/inlet_replayed_bitwise'] = all(
                row['inflow'].hex() == row['observed_inflow'].hex() for row in records[label])
        replays[name] = records
        checks[f'{name}/radiation_derivative_replayed'] = (
            bitwise_derivative(variant, first, rate, multiply=False) and bitwise_derivative(reference, first, rate, multiply=True))
        terminal = compare_terminal(variant[first:], reference[first:], cells - 1, length, rate)
        checks[f'{name}/terminal_pressure_and_radiation_replayed'] = terminal['own_state_replayed']
        pressure = observe(variant, first, rate, cutoff, 'candidate', multiply_volume=True)
        fixed_pressure = observe(reference, first, rate, cutoff, 'upstream')
        checks[f'{name}/cavity_pressure_replayed'] = all(
            row['pressure'].hex() == row['observed_pressure'].hex() for row in [*pressure, *fixed_pressure])
        control_delta = differences(control[first:], reference[first:], observed, left_label='momentum_control', right_label='upstream')
        variant_delta = differences(variant[first:], reference[first:], observed, left_label='inlet', right_label='upstream')
        inlet_offset = variant_delta.get(ENTRY, {}).get('offset')
        remaining = None
        if inlet_offset is not None:
            labels = ('pressure_difference', 'normalized_momentum', 'linear_coefficient', 'quadratic_coefficient')
            left, right = ({key: records[side][inlet_offset][key] for key in labels} for side in ('inlet', 'upstream'))
            remaining = {'offset': inlet_offset, 'term_substitutions': substitutions(
                left, right, records['upstream'][inlet_offset]['observed_inflow'],
                lambda inputs: solve(inputs['pressure_difference'] + inputs['normalized_momentum'],
                                     inputs['linear_coefficient'], inputs['quadratic_coefficient'])[1])}
        results[name] = {'control_minus_upstream': control_delta, 'inlet_minus_upstream': variant_delta,
                         'first_residual_inlet_replay': remaining, 'terminal_load_comparison': terminal,
                         'first_residual_pressure_replay': pressure_at_first_difference(
                             pressure, fixed_pressure, variant_delta.get(PRESSURE, {}).get('offset'), rate),
                         'derivative_replayed_with_upstream_scale': derivative_with_upstream_scale(variant, reference, first, rate),
                         'same_csv_as_momentum_control': sha256(variant_path) == sha256(control_path)}

    matched = results['matched_time']
    before = matched['control_minus_upstream']
    actual = matched['inlet_minus_upstream']
    comparisons = {'first_inlet_flow_difference_delayed': (ENTRY, case['baseline_first_inlet_flow_offset']),
                   'first_radiated_flow_difference_delayed': (RADIATION, case['baseline_first_radiated_flow_offset'])}
    checks['reference_onset_differences_reproduced'] = all(
        before.get(field, {}).get('offset') == offset for field, offset in comparisons.values())
    hypotheses = {key: field not in actual or actual[field]['offset'] > offset
                  for key, (field, offset) in comparisons.items()}
    hypotheses['no_tracking_output_unchanged'] = results['no_tracking']['same_csv_as_momentum_control']
    write(out / 'inlet-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    base_names = ['summary.json', 'artifacts/beak-momentum.patch', *(f'artifacts/{name}-momentum.csv' for name in CONDITIONS)]
    upper_names = [file for name in CONDITIONS for file in (f'artifacts/{name}.json', f'artifacts/{name}-upstream.csv')]
    base_path, base = registered_artifacts(case['baseline'], 'songbird-chirps-beak-momentum-propagation-44100', revision, base_names)
    volume_path, volume = registered_artifacts(case['volume_patch'], 'songbird-chirps-volume-rate-propagation-44100',
                                                revision, ('artifacts/volume-rate.patch',))
    upper_path, upper = registered_artifacts(case['upstream_observations'], 'songbird-chirps-oec-pressure-44100', revision, upper_names)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    analysis_sources = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_syrinx.py', 'measure_songbird_chirps_beak_load.py',
        'measure_songbird_chirps_beak_tip_inflow.py', 'measure_songbird_chirps_beak_tip_inflow_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_chirps_beak_momentum_propagation_44100.py', 'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), base_path, volume_path, upper_path, *base.values(), *volume.values(), *upper.values(),
              *copies, *analysis_sources, UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/tests/airway.rs',
              UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, base, upper, volume, copies, snapshot, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
