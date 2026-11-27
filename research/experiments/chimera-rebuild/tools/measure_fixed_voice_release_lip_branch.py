"""停止後の口端へ入る直列枝を採り、流量差と口端負荷への影響を調べる。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import FIELDS as BRANCH_FIELDS, NATIVE_NET, PROBE, UPPER_NET, replay
from measure_fixed_voice_pharyngeal_second_cell import (
    ROOT, candidate_patches, listed_input, read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_radiation_balance import derivative, sum_flow
from measure_fixed_voice_release_lip_load import CASE as LIP_CASE, capture_lip_rows, lip_edits, replay as load_replay
from measure_fixed_voice_release_output import (
    CASE as OUTPUT_CASE, capture_candidate, capture_upstream, fir, output_step, parse_measurements, rust_range,
)
from measure_fixed_voice_release_radiation import CASE as RADIATION_CASE, components, output_values
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-release-lip-branch-48000.json'
GEOMETRY = ('internal_sample', 'left_node', 'right_node', 'left_area', 'right_area', 'left_minimum',
            'right_minimum', 'left_length', 'right_length')
NATIVE_LOOP = '        for (index, (branch, &noise)) in self'
NATIVE_RATE = '            let rate = (glottis == Some(index)).then_some(self.research_rate_hz);'
UPPER_LOOP = '        let enable_energy_safe = self.energy_safe;'
UPPER_FLOW = '                u_arr[j] = u;'


def branch_edits(case, lip, radiation):
    local, upper = lip_edits(lip, radiation)
    window = rust_range(case['branch_window'])
    endpoints = ', '.join(map(str, case['branch_nodes']))
    native_lookup = f'''        let release_branch = self.research_glottis.and_then(|(_, next)| next.checked_sub(1))
            .filter(|sample| ({window}).contains(sample)).map(|sample| {{
                let lip = self.radiators.iter().position(Option::is_some).unwrap();
                assert_eq!(self.neighbors[lip].len(), 1);
                let from = self.neighbors[lip][0];
                assert_eq!([from, lip], [{endpoints}]);
                let index = self.branches.iter().position(|branch| branch.nodes == [from, lip] && branch.port.is_none()).unwrap();
                (sample, index)
            }});
'''
    native_observe = '''            let observation = if let Some((sample, watched)) = release_branch && watched == index {
                let [a, b] = branch.nodes.map(|node| self.sections[node]);
                let geometry = [a.area_cm2, b.area_cm2, a.minimum_area_cm2, b.minimum_area_cm2, a.length_cm, b.length_cm];
                print!("release-lip-branch-geometry,{sample},{left},{right}");
                for value in geometry { print!(",{value:?}"); }
                println!();
                Some((sample, self.pressure[left], self.pressure[right], noise, (Some("release-lip-branch,"), None)))
            } else {
                observation
            };
'''
    upper_lookup = f'''        let release_branch = ({window}).contains(&self.research_release_sample).then(|| {{
            let lip = self.rad_of.iter().position(|&index| index >= 0).unwrap();
            let mut feeds = self.b_b.iter().enumerate().filter(|&(_, &end)| end == lip);
            let (index, _) = feeds.next().unwrap();
            assert!(feeds.next().is_none() && self.b_kind[index] == KIND_SERIES);
            assert_eq!([self.b_a[index], lip], [{endpoints}]);
            index
        }});
'''
    upper_observe = '''                if release_branch == Some(j) {
                    let sample = self.research_release_sample;
                    let geometry = [area[a], area[b], amin[a], amin[b], self.dx[a], self.dx[b]];
                    print!("release-lip-branch-geometry,{sample},{a},{b}");
                    for value in geometry { print!(",{value:?}"); }
                    println!();
                    let loss = if c >= 0.0 { kf } else { kb };
                    let (discriminant, root, numerator, denominator) = if loss > 0.0 {
                        let discriminant = bq * bq + 4.0 * loss * c.abs();
                        let root = sqrt(discriminant);
                        (discriminant, root, 2.0 * c, bq + root)
                    } else {
                        (0.0, 0.0, c, bq)
                    };
                    let values = [a_eff, p[a], p[b], psrc[j], u_arr[j], lp, l, r, kf, kb,
                        mom[j], m0, m0 * inv_t, c, l * inv_t, bq, loss, discriminant, root, numerator, denominator, u];
                    print!("release-lip-branch,{sample}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }
'''
    return ({NATIVE_NET: (*local[NATIVE_NET], (NATIVE_LOOP, native_lookup + NATIVE_LOOP),
                          (NATIVE_RATE, native_observe + NATIVE_RATE))},
            {UPPER_NET: (*upper[UPPER_NET], (UPPER_LOOP, upper_lookup + UPPER_LOOP),
                         (UPPER_FLOW, upper_observe + UPPER_FLOW))})


def branch_rows(out, name, samples, endpoints):
    lines = (out / f'{name}-raw.txt').read_text().splitlines(keepends=True)
    series = []
    for tag, fields in (('lip-branch', BRANCH_FIELDS), ('lip-branch-geometry', GEOMETRY)):
        prefix = f'release-{tag},'
        path = out / f'{name}-{tag}.csv'
        path.write_text(','.join(fields) + '\n' + ''.join(line.removeprefix(prefix) for line in lines if line.startswith(prefix)))
        rows = read_rows(path)
        if [row['internal_sample'] for row in rows] != samples:
            raise ValueError(f'口端の枝の採取区間が一致しません ({path.name})')
        series.append({int(row['internal_sample']): row for row in rows})
    if any([row['left_node'], row['right_node']] != endpoints for row in series[1].values()):
        raise ValueError(f'口端の枝の両端番号が一致しません ({name})')
    return series


def connect(branches, lip_load, fs, upper, *, multiply_history=False):
    previous = None
    for index, row in branches.items():
        load = lip_load[index]
        if not all(same(row[key], load[field]) for key, field in (('left_pressure', 'upstream_cell_pressure'),
                    ('right_pressure', 'old_pressure'), ('flow', 'branch_inflow'))):
            return False
        if previous is not None and not (same(row['previous_flow'], previous['flow'])
                                         and same(row['previous_inertance'], previous['inertance'])):
            return False
        predicted = replay(row, fs, upper, multiply_history=multiply_history)
        if any(not same(float(value), row[key]) for key, value in predicted.items()):
            return False
        previous = row
    return True


def project_lip(index, flow, lip, radiation, render, fs):
    load = lip[index]
    recovered_inflow = (load['volume_source'] + flow) - load['wall_outflow']
    projection = load_replay({**load, 'inflow': recovered_inflow}, fs, False)
    current, following = radiation[index], radiation[index + 1]
    total = float(sum_flow({**current, 'lip': projection['lip_flow']}))
    bits = render({index: derivative(total, current['previous_total'], fs, True),
                   index + 1: derivative(following['total'], total, fs, True)})
    return {'branch_flow': flow, 'lip_inflow': recovered_inflow, 'lip_load': projection, 'pcm_bits': bits}


def measure(case, lip, radiation, source, saved, patches, copies, snapshot, out, execute):
    native, upper = branch_edits(case, lip, radiation)
    builds = {'candidate': capture_candidate(source, saved, patches, copies, snapshot, out, execute, extra_edits=native),
              'upstream': capture_upstream(source, saved, out, execute, extra_edits=upper)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = source['internal_rate_hz']
    factor = fs // source['output_rate_hz']
    samples = list(range(*case['branch_window']))
    names = [*(f'candidate-{block}' for block in source['blocks']), 'upstream']
    main, alternate, fixed = names
    branches, geometry, loads = {}, {}, {}
    for name in names:
        branches[name], geometry[name] = branch_rows(out, name, samples, case['branch_nodes'])
        # 既存の負荷の項も新しい生ログから取り出し、同じ計算時刻で照合する。
        loads[name] = capture_lip_rows(out, name, samples)
    indices = list(range(*radiation['component_window']))
    internal_window = list(range(*source['internal_window']))
    output_clocks = [(i + 1) * factor - 1 for i in range(*source['output_window'])]
    for name in names:
        components(out, name, indices)
        parse_measurements(out, name, internal_window, output_clocks, source['fir_taps'])
    radiation_rows = {int(row['internal_sample']): row for row in read_rows(saved[f'{main}-release-component.csv'])}
    observations = {key: read_rows(saved[f'{main}-{key}.csv']) for key in ('output', 'tap', 'radiation')}
    output_row, taps, history = output_values(observations, source['target_frame'], factor)
    upper_output, = [row for row in read_rows(saved[f'{fixed}-output.csv'])
                     if int(row['internal_sample']) // factor == source['target_frame']]

    def render(replacements):
        values = [replacements.get(index, value) for index, value in history.items()]
        return output_step(output_row, fir(values, taps))['pcm_bits']

    events = {}
    for index in case['target_internal_samples']:
        a, b = (branches[name][index] for name in (main, fixed))
        event = flow_substitutions(a, b, fs)
        events[str(index)] = {**event, 'candidate_geometry': geometry[main][index], 'upstream_geometry': geometry[fixed][index],
                              'original_branch_projection': project_lip(index, a['flow'], loads[main], radiation_rows, render, fs),
                              'branch_flow_only': project_lip(index, b['flow'], loads[main], radiation_rows, render, fs)}
    checks = {
        'archived_pcm_and_traces': all(sha256(out / name) == sha256(path)
            for name, path in saved.items() if name.endswith(('.wav', '.f32', '.csv'))),
        'host_partition_branch_trace': all(sha256(out / f'{main}-{name}.csv') == sha256(out / f'{alternate}-{name}.csv')
                                           for name in ('lip-branch', 'lip-branch-geometry')),
        'branch_equations_and_lip_clock': all(connect(branches[name], loads[name], fs, name == fixed) for name in names),
        'both_targets_explained': all(bool(event['minimum_upstream_substitutions']) for event in events.values()),
        'original_lip_and_pcm_reconstructed': render({}) == output_row['pcm_bits'] and all(
            event['original_branch_projection']['pcm_bits'] == output_row['pcm_bits']
            and same(event['original_branch_projection']['lip_load']['lip_flow'], loads[main][int(index)]['lip_flow'])
            for index, event in events.items()),
    }
    first = {key: next((sample for sample in samples if not same(branches[main][sample][key], branches[fixed][sample][key])), None)
             for key in BRANCH_FIELDS[1:]}
    return {'checks': checks, 'build_sha256': builds, 'first_observed_differences': first, 'events': events,
            'candidate_pcm_bits': output_row['pcm_bits'], 'upstream_pcm_bits': upper_output['pcm_bits']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference, _ = verified_artifact(*case['lip_run'], 'artifacts/upstream-voice.f32')
    case_inputs = [listed_input(reference, path.name) for path in (LIP_CASE, RADIATION_CASE, OUTPUT_CASE)]
    lip, radiation, source = (json.loads(path.read_text()) for path in case_inputs)
    if case['branch_window'] != lip['lip_window']:
        parser.error('枝と口端負荷の採取区間を揃えてください')
    names = [*(f'candidate-{block}' for block in source['blocks']), 'upstream']
    files = [*(f'{name}-{tag}.csv' for name in names for tag in ('lip-load', 'output', 'tap', 'radiation',
                                                               'release-component', 'release-wall')),
             *(f'{name}.wav' for name in names[:-1]), 'upstream-voice.f32']
    saved = {name: verified_artifact(*case['lip_run'], f'artifacts/{name}')[1] for name in files}
    for name in ('gate-events.txt', 'replay-case.json'):
        saved[name] = listed_input(reference, name)
    source_manifest = listed_input(reference, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    patches = candidate_patches(reference)
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, *case_inputs, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              reference, source_manifest, *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, lip, radiation, source, saved, patches, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
