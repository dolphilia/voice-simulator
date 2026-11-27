"""最後の気管内直列枝で前回運動量の換算だけを切り替える。"""

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
from measure_songbird_chirps_trachea_end_balance_44100 import (
    BALANCE_FIELDS, INFLOW, NOISE, PENULTIMATE, WALL_DISPLACEMENT, WALL_FLOW, inlet_diagnosis, pressure_substitutions, replay,
)
from measure_songbird_chirps_volume_rate_propagation_44100 import DERIVATIVE, PRESSURE, RADIATION
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-trachea-end-momentum-44100.json'
BASE_ID = 'songbird-chirps-trachea-end-balance-44100'
LABELS = ('trachea-control', 'trachea-momentum')
OBSERVED = (PENULTIMATE, INFLOW, WALL_FLOW, WALL_DISPLACEMENT)


def edit_trachea_momentum(workspace, patch):
    edits = {
        NETWORK: (
            ('        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None)',
             '        self.step_with_momentum_order(inlet, inlet_flow_cm3_s, prescribed, 0..0, None, None, None, None, None)'),
            ('        neck_momentum_branch: Option<usize>,',
             '        neck_momentum_branch: Option<usize>,\n        trachea_momentum_branch: Option<usize>,'),
            ('                    || neck_momentum_branch == Some(index),',
             '                    || neck_momentum_branch == Some(index)\n                    || trachea_momentum_branch == Some(index),'),
        ),
        SONGBIRD: (
            ('            Some(self.oec_neck),\n        );',
             '            Some(self.oec_neck),\n            Some(self.trachea.first_branch + self.trachea.count - 2),\n        );'),
        ),
    }
    diff = []
    for relative, recipe in edits.items():
        source = workspace / relative
        original = modified = source.read_text()
        for old, new in recipe:
            if modified.count(old) != 1:
                raise ValueError(f'最後の気管内直列枝を指定する位置が1箇所に定まりません ({relative})')
            modified = modified.replace(old, new, 1)
        diff.extend(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                 f'a/{relative}', f'b/{relative}'))
        source.write_text(modified)
    patch.write_text(''.join(diff))


def configure(case, saved, out):
    configurations = {}
    for name in CONDITIONS:
        source = read(saved[f'artifacts/{name}.json'])
        bird = source['songbird_airway']
        start = case['condition_control_samples'][name]
        event, = bird['events']
        original = case['reference_observation_internal_samples']
        if (bird['sample_rate_hz'], bird['control_block_samples'], event['sample'], bird['sample_count'],
                bird['breath_gate'], event['breath_gate'], bird['observe_beak'], bird['observe_oec'],
                bird['observe_oec_neck'], bird['observe_trachea_end_balance']) != (
                case['sample_rate_hz'], start, start, start + original, 0, 0, True, True, True, True):
            raise ValueError(f'先行描画の条件と一致しません ({name})')
        bird['sample_count'] = start + case['observation_internal_samples']
        configurations[name] = out / f'{name}.json'
        write(configurations[name], source)
    return configurations


def trachea_causality(effect, cells):
    if not effect:
        return True
    if INFLOW not in effect:
        return False
    origin = effect[INFLOW]['offset']
    delay = {PENULTIMATE: 0, TRACHEA_PRESSURE: 0, WALL_FLOW: 1, WALL_DISPLACEMENT: 1,
             FLOW: 1, PRESSURE: 1, RADIATION: cells + 1, DERIVATIVE: cells + 1}
    for index in range(cells):
        delay[f'beak_{index}_pressure_dyn_cm2'] = index + 2
        delay[f'beak_{index}_inflow_cm3_s'] = index + 2
    return all(key not in effect or effect[key]['offset'] >= origin + lag for key, lag in delay.items())


def measure(case, saved, patches, snapshot, copies, out, execute):
    rate, cells, window = (case[key] for key in ('sample_rate_hz', 'beak_cells', 'observation_internal_samples'))
    configurations = configure(case, saved, out)
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute, edit=edit_trachea_momentum,
                                   patch_stem='trachea-end-momentum', labels=LABELS)
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    full_fields = FIELDS + beak_fields(cells) + OEC
    checks = {'only_network_selection_and_songbird_call_changed': set(build['changed_paths']) == {NETWORK, SONGBIRD},
              'compiled_experimental_version_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'reciprocal_sample_period_equals_sample_rate': (1 / (1 / rate)).hex() == float(rate).hex()}
    results, replays, hypotheses = {}, {}, {}
    for name, config in configurations.items():
        start = case['condition_control_samples'][name]
        prefix = start + case['reference_observation_internal_samples'] + 1
        control, variant = (paths[label][name] for label in LABELS)
        upstream = out / f'{name}-upstream.csv'
        execute([str(probe), str(config)], cwd=UPSTREAM, stdout=upstream)
        checks[f'{name}/control_prefix_reproduced'] = csv_prefix_matches(
            control, saved[f'artifacts/{name}-candidate.csv'], prefix)
        checks[f'{name}/upstream_prefix_reproduced'] = csv_prefix_matches(
            upstream, saved[f'artifacts/{name}-upstream.csv'], prefix)
        traces = {}
        for label, path in zip((*LABELS, 'upstream'), (control, variant, upstream), strict=True):
            schema = full_fields + (CANDIDATE_OEC if label != 'upstream' else ()) + NECK_FIELDS + BALANCE_FIELDS
            traces[label] = load_trace(path, schema, start + window)
        result, _ = compare_traces(name, traces, start, case, case['neck'], checks, momentum_labels=LABELS,
                                   linear_labels=LABELS, extra_observed=OBSERVED, propagation=trachea_causality)
        replays[name], parameters = {}, {}
        for label, trace in traces.items():
            side = 'upstream' if label == 'upstream' else 'candidate'
            series, parameters[label] = replay(trace, start, rate, case['trachea_wall'], side,
                                               multiply_inlet_momentum=label == LABELS[1])
            replays[name][label] = series
            checks[f'{name}/{label}/no_tracheal_inlet_noise'] = bool((trace[NOISE] == 0).all())
            for field in ('pressure', 'wall_flow', 'wall_displacement'):
                checks[f'{name}/{label}/tracheal_{field}_bit_replayed'] = all(
                    row[field].hex() == row[f'observed_{field}'].hex() for row in series)
            checks[f'{name}/{label}/tracheal_inlet_flow_bit_replayed'] = all(
                row['inlet_replay']['inflow'].hex() == row['pressure_inputs']['inflow'].hex() for row in series)
        earliest = case['expected_baseline_inlet_offsets'][name]
        before, after = (result[label] for label in ('control_minus_upstream', 'experiment_minus_upstream'))
        checks[f'{name}/registered_inlet_offset_reproduced'] = before.get(INFLOW, {}).get('offset') == earliest
        if earliest is not None:
            hypotheses[f'{name}/first_inlet_difference_delayed'] = after.get(INFLOW, {}).get('offset', window) > earliest
        selected = {'candidate': replays[name][LABELS[1]], 'upstream': replays[name]['upstream']}
        results[name] = result | {'first_residual_tracheal_pressure': pressure_substitutions(
            selected, after.get(TRACHEA_PRESSURE, {}).get('offset'), rate, parameters[LABELS[1]]['compliance']),
            'first_residual_tracheal_inflow': inlet_diagnosis(selected, after.get(INFLOW, {}).get('offset'),
                                                           rate, parameters[LABELS[1]], multiply_momentum=True)}
    write(out / 'trachea-momentum-replay.json', replays)
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
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    entries = read(manifest)['inputs']
    patches = []
    for name in (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch', 'oec-neck-momentum.patch',
                 'oec-neck-linear.patch'):
        row, = (line for line in entries if line['path'].endswith(f'/artifacts/{name}'))
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
        'measure_songbird_chirps_trachea_end_balance_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_syrinx.py', 'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), PROBE, manifest, *saved.values(), *patches, *copies, *tools,
              UPPER_NETWORK, UPPER_SONGBIRD, UPSTREAM / 'crates/chimera/src/physics.rs',
              UPSTREAM / 'crates/chimera/tests/airway.rs', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
