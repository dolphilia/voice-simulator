"""肺ポートの運動量換算だけを変え、気管と声門の流量およびPCMを比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_HUMAN, NATIVE_NET
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, ONSET_CASE, PATCH_ORDER, REFERENCES, ROOT,
    capture, check_equations, compare_nodes, load_baseline, pcm_report, read_rows, record_measurement,
    same, source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_onset import first_by_cell, first_events, read_path
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from measure_fixed_voice_tracheal_series_momentum import (
    CASE as SERIES_CASE, CONTROL_TRACES, capture_glottis, glottal_events, verify_glottis,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-lung-port-momentum-48000.json'
PORT_EDITS = {
    NATIVE_NET: (
        ('    pub(crate) research_tracheal_history: Option<std::ops::Range<usize>>,',
         '    pub(crate) research_tracheal_history: Option<std::ops::Range<usize>>,\n'
         '    pub(crate) research_lung_port_history: Option<usize>,'),
        ('            research_tracheal_history: None,',
         '            research_tracheal_history: None,\n            research_lung_port_history: None,'),
        ('            let history_rate = if self.research_tracheal_history.as_ref()',
         '            let history_rate = if self.research_lung_port_history == Some(index)\n'
         '                || self.research_tracheal_history.as_ref()'),
    ),
    NATIVE_HUMAN: (
        ('        network.research_tracheal_history = Some(trachea.branches.clone());',
         '        network.research_tracheal_history = Some(trachea.branches.clone());\n'
         '        network.research_lung_port_history = Some(ports_start);'),
    ),
}


def measure(case, common, onset, refs, archives, copies, snapshot, out, execute):
    hashes = capture(common, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single-branch-history.patch', 'series-branch-history.patch'),
                     variant_edits=PORT_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'engine', '--test', 'lung_port'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    observe = onset['observation']
    samples = list(range(observe['first_internal_sample'], observe['end_internal_sample_exclusive']))
    count, fs = observe['tracheal_cells'], common['internal_rate_hz']
    flow_sample, pressure_sample = case['target_flow_sample'], case['target_pressure_sample']
    control = read_path(out / 'control', 'candidate', count, samples)
    revised = read_path(out / 'reordered', 'candidate', count, samples)
    upper_nodes, upper_branches = load_baseline(refs, 'upstream')
    upper_glottis = read_rows(refs['upstream-branch.csv'])
    control_glottis, revised_glottis = (capture_glottis(out / group, observe) for group in ('control', 'reordered'))
    flow_clock = first_by_cell(revised[1], upper_branches, count, samples, 'flow')
    pressure_clock = first_by_cell(revised[0], upper_nodes, count, samples, 'new_pressure')
    prefix = [(cell, sample) for sample in samples if sample < flow_sample for cell in range(count)]
    checks = {
        'control_archived_traces': all(sha256(out / 'control' / name) == sha256(archives[name])
                                      for name in (*CONTROL_TRACES, 'glottal-branch.csv')),
        'control_equations': check_equations(control, fs, history_cells=range(1, count)),
        'port_and_series_equations': check_equations(revised, fs, history_cells=range(count)),
        'glottal_equations_and_clock': verify_glottis(control_glottis, upper_glottis, control[0], count - 1, fs)
            and verify_glottis(revised_glottis, upper_glottis, revised[0], count - 1, fs),
        'preceding_flow_and_pressure_unchanged': all(same(control[i][key][column], revised[i][key][column])
            for i, column in ((0, 'new_pressure'), (1, 'flow')) for key in prefix),
        'target_flow_and_pressure_equal_upstream': same(revised[1][0, flow_sample]['flow'], upper_branches[0, flow_sample]['flow'])
            and same(revised[0][0, pressure_sample]['new_pressure'], upper_nodes[0, pressure_sample]['new_pressure']),
        'lung_port_linear_terms_unchanged': all(same(revised[1][0, sample][key], control[1][0, sample][key])
            for sample in samples for key in ('inertance', 'inertance_per_step', 'resistance', 'linear')),
    }
    pcm_checks, pcm = pcm_report(common, refs, out, archived_control={
        block: archives[f'block-{block}.wav'] for block in common['blocks']})
    checks.update(pcm_checks)
    return {'checks': checks, 'build_sha256': hashes,
            'target': {'flow_sample': flow_sample, 'pressure_sample': pressure_sample,
                       'control_flow': control[1][0, flow_sample]['flow'], 'port_flow': revised[1][0, flow_sample]['flow'],
                       'upstream_flow': upper_branches[0, flow_sample]['flow'],
                       'control_pressure': control[0][0, pressure_sample]['new_pressure'],
                       'port_pressure': revised[0][0, pressure_sample]['new_pressure'],
                       'upstream_pressure': upper_nodes[0, pressure_sample]['new_pressure']},
            'first_branch_flow_difference_by_cell': flow_clock, 'first_node_pressure_difference_by_cell': pressure_clock,
            'first_lung_boundary_pressure_difference': first_by_cell(revised[1], upper_branches, 1, samples, 'left_pressure')[0],
            'earliest_flow_events': first_events(flow_clock, revised[1], upper_branches, flow_substitutions, fs),
            'earliest_pressure_events': first_events(pressure_clock, revised[0], upper_nodes, compare_nodes, fs),
            'glottal_flow_difference': {'control': glottal_events(control_glottis, upper_glottis),
                                        'port': glottal_events(revised_glottis, upper_glottis)},
            'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, common, onset, base, series = (json.loads(path.read_text()) for path in (
        CASE, SINGLE_CASE, ONSET_CASE, BALANCE_CASE, SERIES_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    filenames = {**REFERENCES, 'scaled': (*REFERENCES['scaled'], 'upstream-branch.csv'),
                 'onset': (*REFERENCES['onset'][:2], 'upstream-path-node.csv', 'upstream-path-branch.csv'),
                 'momentum': ('candidate-momentum-scale.patch',)}
    refs, manifests, archives = {}, {}, {}
    for group, names in filenames.items():
        for name in names:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', case['series_run'])):
        manifests[group], refs[f'{group}-branch-history.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    for name in (*CONTROL_TRACES, 'glottal-branch.csv', *(f'block-{block}.wav' for block in common['blocks'])):
        _, archives[name] = verified_artifact(*case['series_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, SINGLE_CASE, ONSET_CASE, BALANCE_CASE, SERIES_CASE, WORKSPACE / 'LICENSE-CHIMERA',
              *archived, *tools, *manifests.values(), *refs.values(), *archives.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, onset, refs, archives, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
