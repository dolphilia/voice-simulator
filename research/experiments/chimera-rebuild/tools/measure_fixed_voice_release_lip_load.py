"""停止後の口端を採取し、中点式の入力から流量とPCMを再計算する。"""

import argparse
from fractions import Fraction
from itertools import combinations
import json
from math import pi, sqrt
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET, PROBE, UPPER_NET, f64
from measure_fixed_voice_pharyngeal_second_cell import (
    ROOT, candidate_patches, listed_input, read_rows, record_measurement, same, source_inputs,
    verified_artifact,
)
from measure_fixed_voice_radiation_balance import derivative, sum_flow
from measure_fixed_voice_release_output import (
    CASE as OUTPUT_CASE, capture_candidate, capture_upstream, fir, output_step, parse_measurements, rust_range,
)
from measure_fixed_voice_release_radiation import CASE as RADIATION_CASE, component_edits, components, output_values
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-release-lip-load-48000.json'
FIELDS = ('internal_sample', 'node', 'area', 'length', 'compliance', 'inertance', 'resistance',
          'old_pressure', 'old_inertance_flow', 'upstream_cell_pressure', 'volume_source', 'branch_inflow',
          'before_wall', 'wall_outflow', 'inflow', 'new_pressure', 'new_inertance_flow', 'lip_flow')
INPUTS = ('compliance', 'inertance', 'resistance', 'old_pressure', 'old_inertance_flow', 'inflow')
OUTPUTS = ('new_pressure', 'new_inertance_flow', 'lip_flow')
NATIVE_WALL = '        let mut wall_radiation = 0.0;'
NATIVE_LOAD = '                self.pressure[node] = load.step(self.dt, compliance, self.pressure[node], inflow);'
UPPER_WALL = '        let mut wall_rad_sum = 0.0;'
UPPER_LOAD = '                self.rad_u[r] = ur;'


def lip_edits(case, radiation):
    native, upper = component_edits(radiation['component_window'])
    clock = rust_range(case['lip_window'])
    native_capture = f'''        let lip_observation = self.research_glottis.and_then(|(_, next)| next.checked_sub(1))
            .filter(|sample| ({clock}).contains(sample)).map(|sample| {{
                let node = self.radiators.iter().position(Option::is_some).unwrap();
                let neighbors = &self.neighbors[node];
                assert_eq!(neighbors.len(), 1);
                let upstream = neighbors[0];
                let branch = self.branches.iter().find(|edge| edge.nodes == [upstream, node]).unwrap();
                (sample, node, self.pressure[upstream], self.volume_source(node),
                    branch.flow, self.net_flow[node])
            }});
'''
    native_report = '''                let old_pressure = self.pressure[node];
                let old_inertance_flow = load.inertance_flow;
''' + NATIVE_LOAD + '''
                if let Some((sample, observed, upstream_pressure, volume, branch_inflow, before_wall)) = lip_observation
                    && observed == node
                {
                    let section = self.sections[node];
                    let values = [section.area_cm2, section.length_cm, compliance, load.inertance, load.resistance,
                        old_pressure, old_inertance_flow, upstream_pressure, volume, branch_inflow, before_wall,
                        self.wall_motion[node].flow_cm3_s, inflow, self.pressure[node], load.inertance_flow, load.flow];
                    print!("release-lip,{sample},{node}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''
    upper_capture = f'''        let lip_observation = ({clock}).contains(&release_index).then(|| {{
            let node = self.rad_of.iter().position(|&index| index >= 0).unwrap();
            let mut feeding = self.b_b.iter().enumerate().filter(|&(_, &end)| end == node);
            let (branch, _) = feeding.next().unwrap();
            assert!(feeding.next().is_none() && self.b_kind[branch] == KIND_SERIES);
            (node, self.p[self.b_a[branch]], self.vol_src2[node], self.u[branch], self.flow_sum[node])
        }});
'''
    upper_report = UPPER_LOAD + '''
                if let Some((observed, upstream_pressure, volume, branch_inflow, before_wall)) = lip_observation
                    && observed == k
                {
                    let values = [a, self.dx[k], c, lr, rr, p_old, ul_prev, upstream_pressure, volume, branch_inflow,
                        before_wall, self.wall_u[k], self.flow_sum[k], p_new, ul, ur];
                    print!("release-lip,{release_index},{k}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''
    return ({NATIVE_NET: (*native[NATIVE_NET], (NATIVE_WALL, native_capture + NATIVE_WALL),
                          (NATIVE_LOAD, native_report))},
            {UPPER_NET: (*upper[UPPER_NET], (UPPER_WALL, upper_capture + UPPER_WALL),
                         (UPPER_LOAD, upper_report))})


def capture_lip_rows(out, name, samples):
    lines = (out / f'{name}-raw.txt').read_text().splitlines(keepends=True)
    path = out / f'{name}-lip-load.csv'
    prefix = 'release-lip,'
    path.write_text(','.join(FIELDS) + '\n' + ''.join(line.removeprefix(prefix) for line in lines if line.startswith(prefix)))
    rows = read_rows(path)
    if [row['internal_sample'] for row in rows] != samples or len({row['node'] for row in rows}) != 1:
        raise ValueError(f'口端負荷の節点や採取区間を確認できません ({name})')
    return {int(row['internal_sample']): row for row in rows}


def replay(row, fs, upper):
    c, l, r, pressure, previous, inflow = (Fraction(row[key]) for key in INPUTS)
    dt = f64(Fraction(1, fs))
    scaled_c = f64(c * fs) if upper else f64(c / dt)
    h = f64(dt / f64(2 * l))
    g = f64(Fraction(1, 2) / r)
    half_h = f64(h / 2)
    if upper:
        left = f64(f64(scaled_c - half_h) - g)
        right = f64(f64(scaled_c + half_h) + g)
    else:
        load = f64(g + half_h)
        left = f64(scaled_c - load)
        right = f64(scaled_c + load)
    numerator = f64(f64(f64(pressure * left) + inflow) - previous)
    p1 = f64(numerator / right)
    pressure_sum = f64(pressure + p1)
    u1 = f64(previous + f64(h * pressure_sum))
    flow = f64(f64(f64(previous + u1) / 2) + f64(g * pressure_sum))
    return {'compliance_per_step': float(scaled_c), 'half_inertance_gain': float(h), 'half_conductance': float(g),
            'pressure_factor': float(left), 'denominator': float(right), 'numerator': float(numerator),
            **dict(zip(OUTPUTS, map(float, (p1, u1, flow)), strict=True))}


def validate(rows, radiation, fs, upper):
    density, speed = 0.00114, 35000.0
    previous = None
    for index, row in rows.items():
        area = row['area']
        inertia = (8 * density) / (3 * pi * sqrt(pi * area))
        resistance = (128 * density * speed) / (9 * pi * pi * area)
        compliance = (area * row['length']) / (density * speed * speed)
        terms = ((row['before_wall'], row['volume_source'] + row['branch_inflow']),
                 (row['inflow'], row['before_wall'] - row['wall_outflow']),
                 (row['inertance'], inertia), (row['resistance'], resistance), (row['compliance'], compliance))
        if not all(same(left, right) for left, right in terms):
            return False
        observed = replay(row, fs, upper)
        if any(not same(observed[key], row[key]) for key in OUTPUTS):
            return False
        if index in radiation and not same(row['lip_flow'], radiation[index]['lip']):
            return False
        if previous and not (same(previous['new_pressure'], row['old_pressure'])
                             and same(previous['new_inertance_flow'], row['old_inertance_flow'])):
            return False
        previous = row
    return True


def compare(a, b, fs, sample, components_both, render, expected_pcm):
    changed = [key for key in INPUTS if not same(a[key], b[key])] + ['rounding_order']
    current = components_both[sample]
    following = components_both[sample + 1]
    attempts = []
    for count in range(1, len(changed) + 1):
        for keys in combinations(changed, count):
            values = {**a, **{key: b[key] for key in keys if key != 'rounding_order'}}
            prediction = replay(values, fs, 'rounding_order' in keys)
            combined = float(sum_flow({**current, 'lip': prediction['lip_flow']}))
            restored_pcm = render({sample: derivative(combined, current['previous_total'], fs, True),
                                   sample + 1: derivative(following['total'], combined, fs, True)})
            attempts.append({'inputs': keys, 'projection': prediction, 'paired_pcm_bits': restored_pcm,
                             'matches_upstream_flow': same(prediction['lip_flow'], b['lip_flow']),
                             'matches_upstream_pcm': restored_pcm == expected_pcm})
    minimum = {}
    for match in ('matches_upstream_flow', 'matches_upstream_pcm'):
        choices = [event['inputs'] for event in attempts if event[match]]
        smallest = min(map(len, choices), default=0)
        minimum[match] = [keys for keys in choices if len(keys) == smallest]
    return {'candidate': a, 'upstream': b, 'candidate_intermediates': replay(a, fs, False),
            'upstream_intermediates': replay(b, fs, True), 'differing_inputs': changed[:-1], 'minimum': minimum,
            'single_substitutions': [event for event in attempts if len(event['inputs']) == 1]}


def measure(case, radiation, source, saved, patches, copies, snapshot, out, execute):
    native, upper = lip_edits(case, radiation)
    builds = {'candidate': capture_candidate(source, saved, patches, copies, snapshot, out, execute, extra_edits=native),
              'upstream': capture_upstream(source, saved, out, execute, extra_edits=upper)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = source['internal_rate_hz']
    factor = fs // source['output_rate_hz']
    samples = list(range(*case['lip_window']))
    capture_samples = list(range(*radiation['component_window']))
    windows = list(range(*source['internal_window']))
    clocks = [(i + 1) * factor - 1 for i in range(*source['output_window'])]
    names = [*(f'candidate-{block}' for block in source['blocks']), 'upstream']
    rows, terms, output = {}, {}, {}
    for name in names:
        rows[name] = capture_lip_rows(out, name, samples)
        terms[name] = {int(row['internal_sample']): row for row in components(out, name, capture_samples)[0]}
        output[name] = parse_measurements(out, name, windows, clocks, source['fir_taps'])
    main, alternate, fixed = names
    target_frame = source['target_frame']
    row, taps, history = output_values(output[main], target_frame, factor)
    upstream_row, _, _ = output_values(output[fixed], target_frame, factor)

    def render(replacements):
        return output_step(row, fir([replacements.get(index, value) for index, value in history.items()], taps))['pcm_bits']

    results = {str(index): compare(rows[main][index], rows[fixed][index], fs, index, terms[main], render, upstream_row['pcm_bits'])
               for index in case['target_internal_samples']}
    measured = [*(f'candidate-{block}.wav' for block in source['blocks']), 'upstream-voice.f32',
                *(f'{name}-{kind}.csv' for name in names for kind in ('output', 'tap', 'radiation', 'release-component', 'release-wall'))]
    first = {key: next((sample for sample in samples if not same(rows[main][sample][key], rows[fixed][sample][key])), None)
             for key in FIELDS[2:]}
    checks = {
        'archived_pcm_and_traces': all(sha256(out / name) == sha256(saved[name]) for name in measured),
        'host_partition_lip_trace': sha256(out / f'{main}-lip-load.csv') == sha256(out / f'{alternate}-lip-load.csv'),
        'equations_and_flow_balance': all(validate(rows[name], terms[name], fs, name == fixed) for name in names),
        'both_targets_explained': all(bool(result['minimum']['matches_upstream_flow']) for result in results.values()),
        'output_projection': render({}) == row['pcm_bits']
            and all(result['minimum']['matches_upstream_pcm'] for result in results.values()),
    }
    return {'checks': checks, 'build_sha256': builds, 'first_observed_differences': first, 'events': results,
            'candidate_pcm_bits': row['pcm_bits'], 'upstream_pcm_bits': upstream_row['pcm_bits']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference, _ = verified_artifact(*case['radiation_run'], 'artifacts/upstream-voice.f32')
    radiation_path, output_path = (listed_input(reference, path.name) for path in (RADIATION_CASE, OUTPUT_CASE))
    radiation, source = (json.loads(path.read_text()) for path in (radiation_path, output_path))
    names = [*(f'candidate-{block}' for block in source['blocks']), 'upstream']
    files = [*(f'{name}-{tag}.csv' for name in names for tag in ('output', 'tap', 'radiation', 'release-component', 'release-wall')),
             *(f'{name}.wav' for name in names[:-1]), 'upstream-voice.f32']
    saved = {name: verified_artifact(*case['radiation_run'], f'artifacts/{name}')[1] for name in files}
    for name in ('gate-events.txt', 'replay-case.json'):
        saved[name] = listed_input(reference, name)
    source_manifest = listed_input(reference, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    patches = candidate_patches(reference)
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, radiation_path, output_path, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              reference, source_manifest, *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, radiation, source, saved, patches, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
