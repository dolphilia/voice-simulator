"""声門スリット抵抗の乗算順だけを揃え、声門の流量とPCMを比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET, f64
from measure_fixed_voice_lung_port_momentum import CASE as LUNG_CASE
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


CASE = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
GEOMETRY_LOOP = '            for (branch, &increment) in self.branches.iter_mut().zip(&self.port_area_increments_cm2)'
UPDATE = '                    branch.update_geometry(&self.sections, viscosity);'
SLIT_EDITS = {
    NATIVE_NET: (
        (GEOMETRY_LOOP, '            for (index, (branch, &increment)) in self.branches.iter_mut()\n'
         '                .zip(&self.port_area_increments_cm2).enumerate()'),
        (UPDATE, UPDATE + '''
                    if glottis == Some(index) && branch.inertance > 0.0
                        && let Some(port) = branch.port && port.slit_width_cm > 0.0
                    {
                        let inverse = 1.0 / port.area_cm2;
                        let width = port.slit_width_cm;
                        let duct_resistance = (12.0 * DYNAMIC_VISCOSITY * port.length_cm * width * width)
                            * inverse * inverse * inverse;
                        branch.resistance = duct_resistance + port.extra_resistance;
                    }'''),
    ),
}


def verify_resistance(case, rows, ordered):
    length, width, viscosity = (f64(case[key]) for key in ('slit_length_cm', 'slit_width_cm', 'dynamic_viscosity_cgs'))
    base = f64(f64(12 * viscosity) * length)
    for row in rows:
        inverse = f64(1 / f64(row['area_cm2']))
        if ordered:
            resistance = base
            for factor in (width, width, inverse, inverse, inverse):
                resistance = f64(resistance * factor)
        else:
            inverse_cube = f64(f64(inverse * inverse) * inverse)
            resistance = f64(f64(base * f64(width * width)) * inverse_cube)
        if not same(float(resistance), row['resistance']):
            return False
    return True


def measure(case, common, onset, refs, archives, copies, snapshot, out, execute):
    hashes = capture(common, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single-branch-history.patch', 'series-branch-history.patch',
                                  'lung-branch-history.patch'), variant_edits=SLIT_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'engine', '--test', 'lung_port'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    observe = onset['observation']
    start, end = (observe[key] for key in ('first_internal_sample', 'end_internal_sample_exclusive'))
    samples = list(range(start, end))
    count, fs = observe['tracheal_cells'], common['internal_rate_hz']
    target = case['target_internal_sample']
    control = read_path(out / 'control', 'candidate', count, samples)
    revised = read_path(out / 'reordered', 'candidate', count, samples)
    upper_nodes, upper_branches = load_baseline(refs, 'upstream')
    upper_glottis = read_rows(refs['upstream-branch.csv'])
    control_glottis, revised_glottis = (capture_glottis(out / group, observe) for group in ('control', 'reordered'))
    a, b, u = (rows[target - start] for rows in (control_glottis, revised_glottis, upper_glottis))
    flow_clock = first_by_cell(revised[1], upper_branches, count, samples, 'flow')
    pressure_clock = first_by_cell(revised[0], upper_nodes, count, samples, 'new_pressure')
    checks = {
        'control_archived_traces': all(sha256(out / 'control' / name) == sha256(archives[name])
                                      for name in (*CONTROL_TRACES, 'glottal-branch.csv')),
        'control_equations': check_equations(control, fs, history_cells=range(count)),
        'reordered_equations': check_equations(revised, fs, history_cells=range(count)),
        'glottal_equations_and_clock': verify_glottis(control_glottis, upper_glottis, control[0], count - 1, fs)
            and verify_glottis(revised_glottis, upper_glottis, revised[0], count - 1, fs),
        'independent_slit_resistance': verify_resistance(case, control_glottis, False)
            and verify_resistance(case, revised_glottis, True) and verify_resistance(case, upper_glottis, True),
        'preceding_glottal_flow_unchanged': all(same(left['flow'], right['flow'])
            for left, right in zip(control_glottis[:target - start], revised_glottis[:target - start], strict=True)),
        'target_resistance_linear_and_flow_equal_upstream': all(same(b[key], u[key]) for key in ('resistance', 'linear', 'flow')),
        'target_pressure_and_inertance_unchanged': all(same(b[key], a[key])
            for key in ('left_pressure', 'right_pressure', 'inertance', 'inertance_per_step')),
    }
    pcm_checks, pcm = pcm_report(common, refs, out, archived_control={block: archives[f'block-{block}.wav']
                                                                   for block in common['blocks']})
    checks.update(pcm_checks)
    fields = ('resistance', 'linear', 'flow')
    return {'checks': checks, 'build_sha256': hashes, 'target_internal_sample': target,
            'target': {name: {key: row[key] for key in fields} for name, row in (('control', a), ('slit', b), ('upstream', u))},
            'first_branch_flow_difference_by_cell': flow_clock, 'first_node_pressure_difference_by_cell': pressure_clock,
            'first_lung_boundary_pressure_difference': first_by_cell(revised[1], upper_branches, 1, samples, 'left_pressure')[0],
            'earliest_flow_events': first_events(flow_clock, revised[1], upper_branches, flow_substitutions, fs),
            'earliest_pressure_events': first_events(pressure_clock, revised[0], upper_nodes, compare_nodes, fs),
            'glottal_flow_difference': {'control': glottal_events(control_glottis, upper_glottis),
                                        'slit': glottal_events(revised_glottis, upper_glottis)},
            'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case, common, onset, base, series, lung = (json.loads(path.read_text()) for path in (
        CASE, SINGLE_CASE, ONSET_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE))
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
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']), ('lung', case['lung_run'])):
        manifests[group], refs[f'{group}-branch-history.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    for name in (*CONTROL_TRACES, 'glottal-branch.csv', *(f'block-{block}.wav' for block in common['blocks'])):
        _, archives[name] = verified_artifact(*case['lung_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, SINGLE_CASE, ONSET_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, WORKSPACE / 'LICENSE-CHIMERA',
              *archived, *tools, *manifests.values(), *refs.values(), *archives.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, onset, refs, archives, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
