"""入口枝の前回運動量の換算だけを切り替え、終端までを比較する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_load import ROOT, beak_fields
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import ENTRY, NETWORK, inlet_step, render_variants
from measure_songbird_chirps_beak_momentum_propagation_44100 import compare_terminal
from measure_songbird_chirps_beak_tip_inflow import UPPER_NETWORK, UPPER_SONGBIRD, solve, substitutions
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC, observe
from measure_songbird_chirps_volume_rate_propagation_44100 import (
    DERIVATIVE, INJECTION, PRESSURE, RADIATION, bitwise_derivative, derivative_with_upstream_scale,
    differences, pressure_at_first_difference,
)
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-beak-inlet-momentum-44100.json'
LABELS = ('inlet-control', 'inlet-momentum')


def apply_history_patch(workspace, path):
    source = workspace / NETWORK
    original = source.read_text()
    anchor = '                momentum_branches.contains(&index),'
    if original.count(anchor) != 1:
        raise ValueError('入口の運動量を指定する位置が1箇所に定まりません')
    changed = original.replace(anchor, '                momentum_branches.contains(&index) || linear_inertance_branch == Some(index),', 1)
    path.write_text(''.join(unified_diff(original.splitlines(keepends=True), changed.splitlines(keepends=True),
                                         f'a/{NETWORK}', f'b/{NETWORK}')))
    source.write_text(changed)


def entry_comparison(records, offset):
    if offset is None:
        return None
    fields = ('pressure_difference', 'normalized_momentum', 'linear_coefficient', 'quadratic_coefficient')
    left, right = ({key: records[side][offset][key] for key in fields} for side in ('inlet-momentum', 'upstream'))
    swapped = substitutions(left, right, records['upstream'][offset]['observed_inflow'],
                            lambda terms: solve(terms['pressure_difference'] + terms['normalized_momentum'],
                                                terms['linear_coefficient'], terms['quadratic_coefficient'])[1])
    return {'offset': offset, 'initial_terms': left, 'upstream_terms': right, 'term_substitutions': swapped}


def measure(case, base, inner, volume, upper, copies, snapshot, out, execute):
    definitions = {name: upper[f'artifacts/{name}.json'] for name in CONDITIONS}
    patches = [volume['artifacts/volume-rate.patch'], inner['artifacts/beak-momentum.patch'],
               base['artifacts/beak-inlet-rate.patch']]
    previous_build = read(base['summary.json'])['build']
    rate, cells = case['sample_rate_hz'], case['beak_cells']
    cutoff, window = case['volume_source_cutoff_hz'], case['observation_internal_samples']
    length = case['beak_length_cm'] / cells
    fields = FIELDS + beak_fields(cells) + OEC
    observed = (PRESSURE, OEC[1], OEC[2], *(key for key in beak_fields(cells) if not key.endswith('_area_cm2')),
                RADIATION, DERIVATIVE)
    if rate != 1 / (1 / rate):
        raise ValueError('時間換算に使う逆数と内部レートが一致しません')
    paths, build = render_variants(definitions, patches, snapshot, copies, out, execute,
                                   edit=apply_history_patch, patch_stem='beak-inlet-momentum', labels=LABELS)
    checks = {'only_registered_source_changed': build['changed_paths'] == [NETWORK],
              'experimental_binary_differs': build['experimental_binary_sha256'] != build['control_binary_sha256'],
              'baseline_patch_chain_matches_reference': build['preceding_patch_sha256'] ==
              [*previous_build['preceding_patch_sha256'], previous_build['inlet_patch_sha256']]}
    results, replays = {}, {}
    for name, definition in definitions.items():
        settings = read(definition)['songbird_airway']
        first, = (event['sample'] for event in settings['events'])
        count = first + window
        if (settings['sample_rate_hz'], settings['sample_count'], settings['control_block_samples'],
                settings['observe_beak'], settings['observe_oec']) != (rate, count, first, True, True):
            raise ValueError('登録の内部レート、制御周期、観測列と一致しません')
        control_path, variant_path = (paths[label][name] for label in LABELS)
        control = load_trace(control_path, fields + CANDIDATE_OEC, count)
        variant = load_trace(variant_path, fields + CANDIDATE_OEC, count)
        reference = load_trace(upper[f'artifacts/{name}-upstream.csv'], fields, count)
        checks[f'{name}/control_matches_prior_inlet_run'] = sha256(control_path) == sha256(base[f'artifacts/{name}-inlet.csv'])
        checks[f'{name}/geometry_and_injection_preserved'] = all(
            np.array_equal(control[field].view(np.uint64), variant[field].view(np.uint64))
            for field in (*(f'beak_{cell}_area_cm2' for cell in range(cells)), 'oec_area_cm2', OEC[0], INJECTION))
        entries = {
            label: [inlet_step(trace[index - 1], trace[index], length, rate, upstream=label == 'upstream',
                               multiply_linear=True, multiply_momentum=label == 'inlet-momentum')
                    for index in range(first, count)]
            for label, trace in zip((*LABELS, 'upstream'), (control, variant, reference), strict=True)
        }
        for label, rows in entries.items():
            checks[f'{name}/{label}/inlet_replayed_bitwise'] = all(
                row['observed_inflow'].hex() == row['inflow'].hex() for row in rows)
        replays[name] = entries
        terminal = compare_terminal(variant[first:], reference[first:], cells - 1, length, rate)
        checks[f'{name}/terminal_pressure_and_radiation_replayed'] = terminal['own_state_replayed']
        checks[f'{name}/radiation_derivative_replayed'] = (
            bitwise_derivative(variant, first, rate, multiply=False) and bitwise_derivative(reference, first, rate, multiply=True))
        pressure = observe(variant, first, rate, cutoff, 'candidate', multiply_volume=True)
        fixed_pressure = observe(reference, first, rate, cutoff, 'upstream')
        checks[f'{name}/cavity_pressure_replayed'] = all(
            row['pressure'].hex() == row['observed_pressure'].hex() for row in [*pressure, *fixed_pressure])
        earlier = differences(control[first:], reference[first:], observed, left_label='inlet_control', right_label='upstream')
        current = differences(variant[first:], reference[first:], observed, left_label='inlet_momentum', right_label='upstream')
        results[name] = {
            'control_minus_upstream': earlier, 'inlet_momentum_minus_upstream': current,
            'first_residual_inlet_replay': entry_comparison(entries, current.get(ENTRY, {}).get('offset')),
            'first_residual_pressure_replay': pressure_at_first_difference(
                pressure, fixed_pressure, current.get(PRESSURE, {}).get('offset'), rate),
            'terminal_load_comparison': terminal,
            'derivative_replayed_with_upstream_scale': derivative_with_upstream_scale(variant, reference, first, rate),
            'control_and_variant_csv_equal': sha256(control_path) == sha256(variant_path),
        }
    matched = results['matched_time']
    before, actual = (matched[key] for key in ('control_minus_upstream', 'inlet_momentum_minus_upstream'))
    comparisons = {'first_inlet_flow_difference_delayed': (ENTRY, case['baseline_inlet_first_difference']),
                   'first_terminal_inflow_difference_delayed': (f'beak_{cells - 1}_inflow_cm3_s',
                                                               case['baseline_terminal_inflow_first_difference']),
                   'first_radiated_flow_difference_delayed': (RADIATION, case['baseline_radiated_flow_first_difference'])}
    checks['reference_onset_differences_reproduced'] = all(
        before.get(field, {}).get('offset') == offset for field, offset in comparisons.values())
    hypotheses = {label: field not in actual or actual[field]['offset'] > offset
                  for label, (field, offset) in comparisons.items()}
    hypotheses['no_tracking_output_unchanged'] = results['no_tracking']['control_and_variant_csv_equal']
    write(out / 'inlet-momentum-replay.json', replays)
    return {'checks': checks, 'hypotheses': hypotheses, 'sample_rate_hz': rate, 'build': build, 'conditions': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    base_names = ['summary.json', 'artifacts/beak-inlet-rate.patch', *(f'artifacts/{name}-inlet.csv' for name in CONDITIONS)]
    upper_names = [file for name in CONDITIONS for file in (f'artifacts/{name}.json', f'artifacts/{name}-upstream.csv')]
    base_path, base = registered_artifacts(case['baseline'], 'songbird-chirps-beak-inlet-rate-propagation-44100', revision, base_names)
    inner_path, inner = registered_artifacts(case['inner_momentum_patch'], 'songbird-chirps-beak-momentum-propagation-44100',
                                             revision, ('artifacts/beak-momentum.patch',))
    volume_path, volume = registered_artifacts(case['volume_patch'], 'songbird-chirps-volume-rate-propagation-44100',
                                               revision, ('artifacts/volume-rate.patch',))
    upper_path, upper = registered_artifacts(case['upstream_observations'], 'songbird-chirps-oec-pressure-44100', revision, upper_names)
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_syrinx.py', 'measure_songbird_chirps_beak_load.py',
        'measure_songbird_chirps_beak_tip_inflow.py', 'measure_songbird_chirps_beak_tip_inflow_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_songbird_chirps_beak_momentum_propagation_44100.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), base_path, volume_path, inner_path, upper_path, *base.values(), *volume.values(),
              *inner.values(), *upper.values(), *copies, *tools, UPPER_NETWORK, UPPER_SONGBIRD,
              UPSTREAM / 'crates/chimera/tests/airway.rs', UPSTREAM / 'crates/chimera/tests/creature_realtime.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, base, inner, volume, upper, copies, snapshot, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
