"""気管側首部の運動量の換算順を揃えて、差の伝搬を追う。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import FIELDS, PROBE
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, SONGBIRD, render_variants
from measure_songbird_chirps_beak_load import ROOT, beak_fields, terminal_coefficients, terminal_replay
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import (
    FLOW, NECK_FIELDS, PREFIX_PATCHES, TRACHEA_PRESSURE, diagnose, replay,
)
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC, observe
from measure_songbird_chirps_terminal_numerator_44100 import same_bits
from measure_songbird_chirps_volume_rate_propagation_44100 import (
    DERIVATIVE, INJECTION, PRESSURE, RADIATION, bitwise_derivative, differences, pressure_at_first_difference,
)
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-oec-neck-momentum-44100.json'
BASE_ID = 'songbird-chirps-oec-neck-44100'
LABELS = ('neck-control', 'neck-momentum')


def edit_neck_momentum(work, patch):
    edits = {
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None)'),
            ('        terminal_numerator_node: Option<usize>,',
             '        terminal_numerator_node: Option<usize>,\n        neck_momentum_branch: Option<usize>,'),
            ('                momentum_branches.contains(&index) || linear_inertance_branch == Some(index),',
             '''                momentum_branches.contains(&index)
                    || linear_inertance_branch == Some(index)
                    || neck_momentum_branch == Some(index),'''),
        ),
        SONGBIRD: (
            ('            Some(self.beak.last()),',
             '            Some(self.beak.last()),\n            Some(self.oec_neck),'),
        ),
    }
    diff = []
    for relative, recipe in edits.items():
        path = work / relative
        original = modified = path.read_text()
        for old, new in recipe:
            if modified.count(old) != 1:
                raise ValueError(f'首部の運動量順を切り替える位置が1箇所に定まりません ({relative})')
            modified = modified.replace(old, new, 1)
        diff.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                 f'a/{relative}', f'b/{relative}'))
        path.write_text(modified)
    patch.write_text(''.join(diff))


def configure(case, prior, saved, out):
    configurations = {}
    for name in CONDITIONS:
        source = read(saved[f'artifacts/{name}.json'])
        settings = source['songbird_airway']
        start = prior['condition_control_samples'][name]
        event, = settings['events']
        original = case['reference_observation_internal_samples']
        if (settings['sample_rate_hz'], settings['control_block_samples'], event['sample'],
                settings['sample_count'], settings['observe_beak'], settings['observe_oec'], settings['observe_oec_neck'],
                settings['breath_gate'], event['breath_gate']) != (case['sample_rate_hz'], start, start,
                                                                  start + original, True, True, True, 0, 0):
            raise ValueError(f'前回と描画条件が一致しません ({name})')
        settings['sample_count'] = start + case['observation_internal_samples']
        out_path = out / f'{name}.json'
        write(out_path, source)
        configurations[name] = out_path
    return configurations


def csv_prefix_matches(path, archived, lines):
    baseline = archived.read_bytes().splitlines(keepends=True)
    return len(baseline) == lines and path.read_bytes().splitlines(keepends=True)[:lines] == baseline


def terminal_matches(trace, start, cells, length, rate, upstream):
    prefix = f'beak_{cells - 1}_'
    area = trace[prefix + 'area_cm2']
    feed = trace[prefix + 'inflow_cm3_s']
    pressure = trace[prefix + 'pressure_dyn_cm2']
    if not (area == area[0]).all() or any((series[:start] != 0).any() for series in (feed, pressure, trace[RADIATION])):
        return False
    compliance, g, h = terminal_coefficients(float(area[0]), length, rate)
    scale = compliance * rate if upstream else compliance / (1 / rate)
    prediction = terminal_replay(feed[start:], scale, g, h, not upstream, numerator_grouped=False)
    return same_bits(prediction['pressure'], pressure[start:]) and same_bits(prediction['flow'], trace[RADIATION][start:])


def causality(delta, cells):
    if not delta:
        return True
    if FLOW not in delta:
        return False
    neck = delta[FLOW]['offset']
    minimum_delays = {TRACHEA_PRESSURE: 0, PRESSURE: 0, RADIATION: cells, DERIVATIVE: cells}
    for cell in range(cells):
        minimum_delays.update({f'beak_{cell}_pressure_dyn_cm2': cell + 1, f'beak_{cell}_inflow_cm3_s': cell + 1})
    return all(field not in delta or delta[field]['offset'] >= neck + delay
               for field, delay in minimum_delays.items())


def compare_traces(name, traces, start, case, neck, checks, *, momentum_labels, linear_labels=(),
                   extra_observed=(), propagation=causality):
    rate, cells = case['sample_rate_hz'], case['beak_cells']
    length = case['beak_length_cm'] / cells
    cutoff = case['volume_source_cutoff_hz']
    control_label, variant_label, _ = traces
    control, variant, upper = traces.values()
    observed = (FLOW, TRACHEA_PRESSURE, PRESSURE, *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')),
                RADIATION, DERIVATIVE, *extra_observed)
    shape_fields = (*(key for key in NECK_FIELDS if key != TRACHEA_PRESSURE), INJECTION,
                    'oec_area_cm2', OEC[0], *(f'beak_{index}_area_cm2' for index in range(cells)))
    checks[f'{name}/geometry_and_injection_bit_identical'] = all(
        same_bits(control[key], variant[key]) for key in shape_fields)
    checks[f'{name}/before_key_observations_identical'] = all(
        same_bits(control[key][:start], variant[key][:start]) for key in observed)
    series, cavities = {}, {}
    for label, trace in traces.items():
        upstream = label == 'upstream'
        flows = series[label] = replay(trace, start, rate, neck, upstream=upstream,
                                       multiply_momentum=label in momentum_labels, multiply_linear=label in linear_labels)
        pressures = cavities[label] = observe(trace, start, rate, cutoff,
                                              'upstream' if upstream else 'candidate', multiply_volume=True)
        checks[f'{name}/{label}/neck_flow_bit_replayed'] = all(
            row['observed'].hex() == row['result']['flow'].hex() for row in flows)
        checks[f'{name}/{label}/cavity_pressure_bit_replayed'] = all(
            row['observed_pressure'].hex() == row['pressure'].hex() for row in pressures)
        checks[f'{name}/{label}/terminal_pressure_and_flow_bit_replayed'] = terminal_matches(
            trace, start, cells, length, rate, upstream)
        checks[f'{name}/{label}/radiation_derivative_bit_replayed'] = bitwise_derivative(trace, start, rate, multiply=upstream)

    base, experiment = control_label.replace('-', '_'), variant_label.replace('-', '_')
    before = differences(control[start:], upper[start:], observed, left_label=base, right_label='upstream')
    after = differences(variant[start:], upper[start:], observed, left_label=experiment, right_label='upstream')
    effect = differences(variant[start:], control[start:], observed, left_label=experiment, right_label=base)
    checks[f'{name}/propagation_follows_update_order'] = propagation(effect, cells)
    if name == 'no_tracking':
        checks[f'{name}/acoustics_all_zero'] = all((trace[key] == 0).all() for trace in traces.values() for key in observed)
    result = {'event_sample': start, 'control_minus_upstream': before, 'experiment_minus_upstream': after,
              'experiment_minus_control': effect,
              'first_residual_neck_flow': diagnose(series[variant_label], series['upstream'],
                                                   after.get(FLOW, {}).get('offset'), rate),
              'first_residual_cavity_pressure': pressure_at_first_difference(
                  cavities[variant_label], cavities['upstream'], after.get(PRESSURE, {}).get('offset'), rate)}
    return result, series


def measure(case, prior, saved, patches, snapshot, copies, out, execute):
    rate, window, cells = (case[key] for key in ('sample_rate_hz', 'observation_internal_samples', 'beak_cells'))
    configurations = configure(case, prior, saved, out)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit_neck_momentum, patch_stem='oec-neck-momentum', labels=LABELS)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    checks = {'only_registered_sources_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'compiled_experimental_version_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'reciprocal_sample_period_equals_sample_rate': (1 / (1 / rate)).hex() == float(rate).hex()}
    common = FIELDS + beak_fields(cells) + OEC
    results, all_replays = {}, {}
    for name, definition in configurations.items():
        start = prior['condition_control_samples'][name]
        control_path, experiment_path = (paths[label][name] for label in LABELS)
        upper_path = out / f'{name}-upstream.csv'
        execute([str(probe), str(definition)], cwd=UPSTREAM, stdout=upper_path)
        prefix_lines = start + case['reference_observation_internal_samples'] + 1
        checks[f'{name}/control_prefix_reproduced'] = csv_prefix_matches(
            control_path, saved[f'artifacts/{name}-candidate.csv'], prefix_lines)
        checks[f'{name}/upstream_prefix_reproduced'] = csv_prefix_matches(
            upper_path, saved[f'artifacts/{name}-upstream.csv'], prefix_lines)
        control, variant = (load_trace(path, common + CANDIDATE_OEC + NECK_FIELDS, start + window)
                            for path in (control_path, experiment_path))
        upper = load_trace(upper_path, common + NECK_FIELDS, start + window)
        traces = dict(zip((*LABELS, 'upstream'), (control, variant, upper), strict=True))
        result, all_replays[name] = compare_traces(name, traces, start, case, prior['neck'], checks,
                                                  momentum_labels=(LABELS[1],))
        results[name] = result
        prior_offset = prior['expected_first_flow_differences'][name]
        checks[f'{name}/known_neck_offset_reproduced'] = result['control_minus_upstream'].get(FLOW, {}).get('offset') == prior_offset
        if prior_offset is not None:
            checks[f'{name}/neck_change_at_first_expected_offset'] = result['experiment_minus_control'].get(
                FLOW, {}).get('offset') == prior_offset
    hypotheses = {f'{name}/first_neck_difference_delayed': result['experiment_minus_upstream'].get(
        FLOW, {}).get('offset', window) > prior['expected_first_flow_differences'][name]
        for name, result in results.items() if prior['expected_first_flow_differences'][name] is not None}
    write(out / 'neck-momentum-replay.json', all_replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'conditions': results, 'sample_rate_hz': rate,
            'window': window, 'build': build}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    names = ('summary.json', *(f'artifacts/{name}{suffix}' for name in CONDITIONS
                               for suffix in ('.json', '-candidate.csv', '-upstream.csv')))
    manifest_path, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    manifest = read(manifest_path)
    prior_rel = (WORKSPACE / 'cases' / f'{BASE_ID}.json').relative_to(ROOT)
    prior_path = manifest_path.parent / manifest['source_snapshot'] / prior_rel
    prior_hash, = (row['sha256'] for row in manifest['inputs'] if row['path'] == prior_rel.as_posix())
    if sha256(prior_path) != prior_hash:
        parser.error('前回のケース定義が保存時と一致しません')
    prior = read(prior_path)
    patches = []
    for name in (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch'):
        row, = (row for row in manifest['inputs'] if row['path'].endswith(f'/artifacts/{name}'))
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            parser.error(f'先行実験の差分が保存時と一致しません ({name})')
        patches.append(path)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_songbird_chirps_oec_neck_44100.py', 'measure_songbird_chirps_oec_pressure_44100.py',
        'measure_songbird_chirps_terminal_numerator_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_syrinx.py', 'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), PROBE, manifest_path, prior_path, *saved.values(), *patches, *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, prior, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
