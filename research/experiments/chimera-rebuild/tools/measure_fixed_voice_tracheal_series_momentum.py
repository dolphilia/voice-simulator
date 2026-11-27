"""気管の直列枝すべてに同じ運動量換算を適用し、声門とPCMを比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_HUMAN, NATIVE_NET, read_capture, replay
from measure_fixed_voice_glottal_momentum import substitute_at
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, ONSET_CASE, PATCH_ORDER, REFERENCES, ROOT,
    capture, check_equations, compare_nodes, load_baseline, pcm_report, read_rows, record_measurement,
    same, source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_onset import first_by_cell, first_events, read_path
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-tracheal-series-momentum-48000.json'
CONTROL_TRACES = ('candidate-internal.csv', 'candidate-raw.txt', 'candidate-path-node.csv', 'candidate-path-branch.csv')
SERIES_EDITS = {
    NATIVE_NET: (
        ('research_tracheal_history: Option<usize>', 'research_tracheal_history: Option<std::ops::Range<usize>>'),
        ('            let history_rate = if self.research_tracheal_history == Some(index) {',
         '''            let history_rate = if self.research_tracheal_history.as_ref()
                .is_some_and(|branches| branches.contains(&index))
            {'''),
    ),
    NATIVE_HUMAN: (
        ('Some(trachea.branches.start);', 'Some(trachea.branches.clone());'),
    ),
}


def capture_glottis(directory, observation):
    raw = (directory / 'candidate-raw.txt').read_text().splitlines(keepends=True)
    (directory / 'glottal-branch-values.txt').write_text(''.join(line for line in raw if line[:1].isdigit()))
    return read_capture('glottal', observation, directory)


def verify_glottis(glottis, upper, nodes, terminal, fs):
    return all(same(row['flow'], nodes[terminal, row['internal_sample']]['trachea_outflow'])
               and same(row['left_pressure'], nodes[terminal, row['internal_sample']]['old_pressure'])
               and row['internal_sample'] == ref['internal_sample']
               and all(same(float(value), row[key]) for key, value in replay(row, fs, True).items())
               for row, ref in zip(glottis, upper, strict=True))


def glottal_events(rows, reference):
    for current, upstream in zip(rows, reference, strict=True):
        if not same(current['flow'], upstream['flow']):
            return {'sample': current['internal_sample'], 'candidate': current, 'upstream': upstream,
                    'minimum_upstream_substitutions': substitute_at(
                        current, upstream, ('drive_pressure', 'linear', 'loss'))}
    return None


def measure(case, common, onset, refs, archives, copies, snapshot, out, execute):
    hashes = capture(common, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single-branch-history.patch'), variant_edits=SERIES_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'engine', '--test', 'lung_port'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    observe = onset['observation']
    samples = list(range(observe['first_internal_sample'], observe['end_internal_sample_exclusive']))
    count, fs = observe['tracheal_cells'], common['internal_rate_hz']
    target, point = case['target_incoming_branch'], case['target_internal_sample']
    control = read_path(out / 'control', 'candidate', count, samples)
    revised = read_path(out / 'reordered', 'candidate', count, samples)
    upper_nodes, upper_branches = load_baseline(refs, 'upstream')
    upper_glottis = read_rows(refs['upstream-branch.csv'])
    control_glottis, revised_glottis = (capture_glottis(out / group, observe) for group in ('control', 'reordered'))
    flow_clock = first_by_cell(revised[1], upper_branches, count, samples, 'flow')
    pressure_clock = first_by_cell(revised[0], upper_nodes, count, samples, 'new_pressure')
    prefix = [(cell, sample) for sample in samples if sample < point for cell in range(count)]
    checks = {
        'control_archived_traces': all(sha256(out / 'control' / name) == sha256(archives[name]) for name in CONTROL_TRACES),
        'control_equations': check_equations(control, fs, history_cells=(1,)),
        'series_equations': check_equations(revised, fs, history_cells=range(1, count)),
        'glottal_equations_and_clock': verify_glottis(control_glottis, upper_glottis, control[0], count - 1, fs)
            and verify_glottis(revised_glottis, upper_glottis, revised[0], count - 1, fs),
        'preceding_flow_and_pressure_unchanged': all(same(control[i][key][column], revised[i][key][column])
            for i, column in ((0, 'new_pressure'), (1, 'flow')) for key in prefix),
        'target_flow_and_pressure_equal_upstream': same(revised[1][target, point]['flow'], upper_branches[target, point]['flow'])
            and same(revised[0][target - 1, point]['new_pressure'], upper_nodes[target - 1, point]['new_pressure']),
        'tracheal_linear_terms_unchanged': all(same(row[key], control[1][cell, sample][key])
            for (cell, sample), row in revised[1].items() for key in ('inertance', 'inertance_per_step', 'resistance', 'linear')),
    }
    checks_pcm, pcm = pcm_report(common, refs, out, archived_control={
        block: archives[f'block-{block}.wav'] for block in common['blocks']})
    checks.update(checks_pcm)
    return {'checks': checks, 'build_sha256': hashes, 'target': {'branch': target, 'sample': point,
                'control_flow': control[1][target, point]['flow'], 'series_flow': revised[1][target, point]['flow'],
                'upstream_flow': upper_branches[target, point]['flow'],
                'control_pressure': control[0][target - 1, point]['new_pressure'],
                'series_pressure': revised[0][target - 1, point]['new_pressure'],
                'upstream_pressure': upper_nodes[target - 1, point]['new_pressure']},
            'first_branch_flow_difference_by_cell': flow_clock, 'first_node_pressure_difference_by_cell': pressure_clock,
            'first_lung_boundary_pressure_difference': first_by_cell(revised[1], upper_branches, 1, samples, 'left_pressure')[0],
            'earliest_flow_events': first_events(flow_clock, revised[1], upper_branches, flow_substitutions, fs),
            'earliest_pressure_events': first_events(pressure_clock, revised[0], upper_nodes, compare_nodes, fs),
            'glottal_flow_difference': {'control': glottal_events(control_glottis, upper_glottis),
                                        'series': glottal_events(revised_glottis, upper_glottis)},
            'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    common = json.loads(SINGLE_CASE.read_text())
    onset = json.loads(ONSET_CASE.read_text())
    base = json.loads(BALANCE_CASE.read_text())
    if case['tracheal_series_branches'] + 1 != onset['observation']['tracheal_cells']:
        parser.error('気管のセルと直列枝の登録数が一致しません')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    names_by_group = {**REFERENCES, 'scaled': (*REFERENCES['scaled'], 'upstream-branch.csv'),
                      'onset': (*REFERENCES['onset'][:2], 'upstream-path-node.csv', 'upstream-path-branch.csv'),
                      'momentum': ('candidate-momentum-scale.patch',)}
    refs, manifests, archives = {}, {}, {}
    for group, names in names_by_group.items():
        for name in names:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    manifests['single'], refs['single-branch-history.patch'] = verified_artifact(
        *case['single_branch_run'], 'artifacts/candidate-tracheal-history.patch')
    for name in (*CONTROL_TRACES, *(f'block-{block}.wav' for block in common['blocks'])):
        _, archives[name] = verified_artifact(*case['single_branch_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, SINGLE_CASE, ONSET_CASE, BALANCE_CASE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              *manifests.values(), *refs.values(), *archives.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, onset, refs, archives, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
