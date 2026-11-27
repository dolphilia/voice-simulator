"""気管側首部の線形慣性項だけを乗算に替え、64点の伝搬を比較する。"""

import argparse
from difflib import unified_diff
from pathlib import Path
import subprocess
import sys

from measure_songbird_airway import FIELDS
from measure_songbird_chirps_beak_inlet_rate_propagation_44100 import NETWORK, render_variants
from measure_songbird_chirps_beak_load import ROOT, beak_fields
from measure_songbird_chirps_beak_tip_inflow_44100 import registered_artifacts
from measure_songbird_chirps_oec_neck_44100 import FLOW, NECK_FIELDS, PREFIX_PATCHES
from measure_songbird_chirps_oec_neck_momentum_44100 import compare_traces
from measure_songbird_chirps_oec_pressure_44100 import CANDIDATE_OEC, CONDITIONS, OEC
from measure_songbird_syrinx import load_trace
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/songbird-chirps-oec-neck-linear-44100.json'
BASE_ID = 'songbird-chirps-oec-neck-momentum-44100'
LABELS = ('momentum-control', 'neck-linear')


def edit_linear_inertance(work, patch):
    path = work / NETWORK
    original = path.read_text()
    anchor = '                linear_inertance_branch == Some(index),'
    if original.count(anchor) != 1:
        raise ValueError('首部の線形慣性項を切り替える位置が1箇所に定まりません')
    modified = original.replace(anchor, '                linear_inertance_branch == Some(index) || neck_momentum_branch == Some(index),', 1)
    path.write_text(modified)
    patch.write_text(''.join(unified_diff(original.splitlines(keepends=True), modified.splitlines(keepends=True),
                                         f'a/{NETWORK}', f'b/{NETWORK}')))


def measure(case, prior, saved, patches, snapshot, copies, out, execute):
    rate, cells, window = (case[field] for field in ('sample_rate_hz', 'beak_cells', 'observation_internal_samples'))
    fields = FIELDS + beak_fields(cells) + OEC
    configurations = {name: saved[f'artifacts/{name}.json'] for name in CONDITIONS}
    paths, build = render_variants(configurations, patches, snapshot, copies, out, execute,
                                   edit=edit_linear_inertance, patch_stem='oec-neck-linear', labels=LABELS)
    prior_build = read(saved['summary.json'])['build']
    checks = {'only_network_source_changed': set(build['changed_paths']) == {NETWORK},
              'baseline_patch_chain_matches': build['preceding_patch_sha256'] ==
              [*prior_build['preceding_patch_sha256'], prior_build['inlet_patch_sha256']],
              'compiled_experimental_version_differs': build['control_binary_sha256'] != build['experimental_binary_sha256'],
              'reciprocal_sample_period_equals_sample_rate': (1 / (1 / rate)).hex() == float(rate).hex()}
    results, replays, hypotheses = {}, {}, {}
    for name, config in configurations.items():
        settings = read(config)['songbird_airway']
        start = prior['condition_control_samples'][name]
        event, = settings['events']
        if (settings['sample_rate_hz'], settings['control_block_samples'], event['sample'], settings['sample_count'],
                settings['breath_gate'], event['breath_gate'],
                settings['observe_beak'], settings['observe_oec'], settings['observe_oec_neck']) != (
                rate, start, start, start + window, 0, 0, True, True, True):
            raise ValueError(f'固定上流の描画条件と一致しません ({name})')
        control, experiment = (paths[label][name] for label in LABELS)
        upper = saved[f'artifacts/{name}-upstream.csv']
        checks[f'{name}/control_csv_matches_previous_experiment'] = sha256(control) == sha256(
            saved[f'artifacts/{name}-neck-momentum.csv'])
        traces = {label: load_trace(path, fields + (CANDIDATE_OEC if label != 'upstream' else ()) + NECK_FIELDS, start + window)
                  for label, path in zip((*LABELS, 'upstream'), (control, experiment, upper), strict=True)}
        result, replays[name] = compare_traces(name, traces, start, case, prior['neck'], checks,
                                              momentum_labels=LABELS, linear_labels=(LABELS[1],))
        results[name] = result
        earliest = case['expected_baseline_neck_offsets'][name]
        checks[f'{name}/known_neck_offset_reproduced'] = result['control_minus_upstream'].get(FLOW, {}).get('offset') == earliest
        if earliest is not None:
            hypotheses[f'{name}/first_neck_difference_delayed'] = result['experiment_minus_upstream'].get(
                FLOW, {}).get('offset', window) > earliest
    write(out / 'neck-linear-replay.json', replays)
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
    names = ('summary.json', 'artifacts/oec-neck-momentum.patch',
             *(f'artifacts/{name}{suffix}' for name in CONDITIONS for suffix in ('.json', '-neck-momentum.csv', '-upstream.csv')))
    manifest, saved = registered_artifacts(case['baseline'], BASE_ID, revision, names)
    registered = read(manifest)['inputs']
    required = ('/cases/songbird-chirps-oec-neck-44100.json',
                *(f'/artifacts/{name}' for name in (*PREFIX_PATCHES, 'oec-sum-order.patch', 'terminal-numerator.patch')))
    baseline_inputs = []
    for suffix in required:
        row, = (row for row in registered if row['path'].endswith(suffix))
        path = ROOT / row['path']
        if path.stat().st_size != row['bytes'] or sha256(path) != row['sha256']:
            parser.error(f'対象の先行入力が保存時と一致しません ({suffix})')
        baseline_inputs.append(path)
    prior_path, *patches = baseline_inputs
    patches.append(saved['artifacts/oec-neck-momentum.patch'])
    copies = [*candidate_sources(), WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/mandarin.txt.gz']
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_songbird_airway.py', 'measure_songbird_chirps_beak_load.py', 'measure_songbird_chirps_beak_tip_inflow.py',
        'measure_songbird_chirps_beak_tip_inflow_44100.py', 'measure_songbird_chirps_beak_inlet_rate_propagation_44100.py',
        'measure_songbird_chirps_oec_neck_44100.py', 'measure_songbird_chirps_oec_neck_momentum_44100.py',
        'measure_songbird_chirps_oec_pressure_44100.py', 'measure_songbird_chirps_terminal_numerator_44100.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_songbird_syrinx.py',
        'measure_speech_timing.py', 'measure_uniform_tube.py')]
    inputs = [CASE, Path(__file__), manifest, prior_path, *saved.values(), *patches[:-1], *copies, *tools,
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/src/creatures/songbird.rs',
              UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, read(prior_path), saved, patches, snapshot, copies, out, execute),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
