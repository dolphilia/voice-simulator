"""固定発声の気管末端セルで圧力を更新する項を採取し、演算ごとに照合する。"""

import argparse
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from measure_fixed_voice_centerline import first_difference, same, verified_artifact
from measure_fixed_voice_glottal_branch import PROBE, NATIVE_NET, UPPER_NET, apply_edits, read_capture
from measure_fixed_voice_glottal_momentum import UPSTREAM_FILES, source_inputs, stage_candidate
from measure_fixed_voice_pharynx_onset import read_rows
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/fixed-voice-subglottal-balance-48000.json'
REFERENCES = {
    'scaled': ('candidate-observation.patch', 'candidate-inertance-scale.patch',
               'upstream-observation.patch', 'upstream-branch.csv'),
    'geometry': ('combined.patch',),
    'pressure': ('prefix-case.json', 'gate-events.txt', 'upstream-trace.csv', 'upstream-voice.f32'),
    'momentum': ('candidate-momentum-scale.patch', 'momentum-branch.csv', 'momentum-internal.csv'),
}
FIELDS = (
    'internal_sample', 'old_pressure', 'new_pressure', 'trachea_inflow', 'glottal_outflow', 'wall_outflow',
    'volume_source', 'net_flow', 'volume', 'compliance', 'inlet_old_pressure', 'wall_old_velocity',
    'wall_old_displacement', 'wall_velocity', 'wall_displacement', 'wall_surface',
)
TERMS = ('old_pressure', 'volume_source', 'trachea_inflow', 'glottal_outflow', 'wall_outflow', 'compliance')
NATIVE_WALL = '        let mut wall_radiation = 0.0;'
NATIVE_PRESSURE = '                self.pressure[node] += self.dt / compliance * inflow;'
UPPER_WALL = '        // 4) walls (velocity at half step from p(n), displacement integrates)'
UPPER_PRESSURE = '                self.p[k] += (t / c) * self.flow_sum[k];'

NATIVE_READ_WALL = '''        let subglottal = research.map(|(glottis, sample)| {
            let node = self.branches[glottis].nodes[0];
            let mut entries = self.branches.iter().filter(|branch| branch.nodes.contains(&node));
            let inlet = entries.next().unwrap();
            assert_eq!(inlet.nodes[1], node);
            assert!(inlet.port.is_none() && entries.next().unwrap().nodes[0] == node);
            assert!(entries.next().is_none());
            (node, sample, inlet.flow, self.pressure[inlet.nodes[0]], self.branches[glottis].flow,
             self.wall_motion[node])
        });
'''
NATIVE_REPORT = '''                let old_pressure = self.pressure[node];
                self.pressure[node] += self.dt / compliance * inflow;
                if let Some((target, sample, incoming, upstream_pressure, outgoing, old_wall)) = subglottal
                    && target == node
                {
                    let wall = self.wall_motion[node];
                    let values = [old_pressure, self.pressure[node], incoming, outgoing, wall.flow_cm3_s,
                        self.volume_source(node), inflow, self.sections[node].volume(), compliance,
                        upstream_pressure, old_wall.velocity_cm_s, old_wall.displacement_cm,
                        wall.velocity_cm_s, wall.displacement_cm, self.sections[node].wall_surface()];
                    print!("subglottal,{sample}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''
UPPER_READ_WALL = '''        let subglottal = research.map(|(glottis, sample)| {
            let node = self.b_a[glottis];
            let mut entries = self.b_a.iter().zip(&self.b_b).enumerate()
                .filter(|&(_, (&a, &b))| a == node || b == node);
            let (inlet, (&a, &b)) = entries.next().unwrap();
            assert_eq!(b, node);
            assert_eq!(self.b_kind[inlet], KIND_SERIES);
            assert_eq!(entries.next().unwrap().0, glottis);
            assert!(entries.next().is_none());
            (node, sample, self.u[inlet], self.p[a], self.u[glottis], self.wall_v[node], self.wall_y[node])
        });
'''
UPPER_REPORT = '''                let old_pressure = self.p[k];
                self.p[k] += (t / c) * self.flow_sum[k];
                if let Some((target, sample, incoming, upstream_pressure, outgoing, old_v, old_y)) = subglottal
                    && target == k
                {
                    let sa = if self.area[k] > min_a { self.sqrt_a[k] } else { sqrt(min_a) };
                    let surface = self.wall_perim[k] * sa * self.dx[k];
                    let values = [old_pressure, self.p[k], incoming, outgoing, self.wall_u[k],
                        self.vol_src2[k], self.flow_sum[k], self.vol[k], c, upstream_pressure,
                        old_v, old_y, self.wall_v[k], self.wall_y[k], surface];
                    print!("subglottal,{sample}");
                    for value in values { print!(",{value:?}"); }
                    println!();
                }'''


def apply_patch(source, patch, execute):
    execute(['git', 'apply', '--check', str(patch)], cwd=source)
    execute(['git', 'apply', str(patch)], cwd=source)


def capture_native(refs, copies, snapshot, out, execute, *, extra_observations=None):
    with TemporaryDirectory(prefix='subglottal-candidate-', dir=out.parent) as temp:
        source = Path(temp) / 'source'
        target = Path(temp) / 'target'
        stage_candidate(snapshot, copies, source)
        for category, name in (('geometry', 'combined.patch'), ('scaled', 'candidate-observation.patch'),
                               ('scaled', 'candidate-inertance-scale.patch'),
                               ('momentum', 'candidate-momentum-scale.patch')):
            apply_patch(source, refs[category][name], execute)
        apply_edits(source, {NATIVE_NET: ((NATIVE_WALL, NATIVE_READ_WALL + NATIVE_WALL),
                                        (NATIVE_PRESSURE, NATIVE_REPORT))}, out / 'candidate-balance.patch')
        if extra_observations is not None:
            apply_edits(source, {NATIVE_NET: extra_observations}, out / 'candidate-extra-observations.patch')
        execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)])
        cli = target / 'release/vocal-cli'
        execute([str(cli), 'render', str(refs['pressure']['prefix-case.json']), str(out / 'candidate-internal.csv')],
                stdout=out / 'candidate-raw.txt')
        return sha256(cli)


def capture_upstream(case, config, refs, out, execute, *, extra_observations=None):
    with TemporaryDirectory(prefix='subglottal-upstream-', dir=out.parent) as temp:
        source = Path(temp)
        tar = source / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        apply_patch(source, refs['scaled']['upstream-observation.patch'], execute)
        apply_edits(source, {UPPER_NET: ((UPPER_WALL, UPPER_READ_WALL + UPPER_WALL),
                                        (UPPER_PRESSURE, UPPER_REPORT))}, out / 'upstream-balance.patch')
        if extra_observations is not None:
            apply_edits(source, {UPPER_NET: extra_observations}, out / 'upstream-extra-observations.patch')
        probe = build_upstream_probe(PROBE, out, execute, upstream=source, cargo_args=('--offline',))
    params = json.loads(refs['pressure']['prefix-case.json'].read_text())['voice']
    arguments = [config[key] for key in ('ipa', 'internal_rate_hz', 'output_rate_hz', 'prefix_output_frames')]
    arguments.extend(params[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))
    execute([str(probe), 'render', *map(str, arguments), str(out), str(refs['pressure']['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-raw.txt')
    return sha256(probe)


def read_balances(name, config, out):
    prefix = 'subglottal,'
    raw = (out / f'{name}-raw.txt').read_text().splitlines(keepends=True)
    (out / f'{name}-branch-values.txt').write_text(''.join(line for line in raw if not line.startswith(prefix)))
    branch = read_capture(name, config, out)
    csv = out / f'{name}-balance.csv'
    csv.write_text(','.join(FIELDS) + '\n' + ''.join(line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
    balance = read_rows(csv)
    if [row['internal_sample'] for row in balance] != [row['internal_sample'] for row in branch]:
        raise ValueError(f'気管末端の観測点と声門枝の観測点が一致しません ({name})')
    return balance, branch


def pressure_update(row, fs):
    old, volume, inlet, glottis, wall, compliance = (Fraction(row[key]) for key in TERMS)
    # 分数を各演算の直後に float へ丸め、蓄積順と dt の換算も再現する。
    inflow = Fraction(float(volume + inlet))
    inflow = Fraction(float(inflow - glottis))
    net = float(inflow - wall)
    dt = Fraction(float(Fraction(1, fs)))
    coefficient = Fraction(float(dt / compliance))
    increment = float(coefficient * Fraction(net))
    return net, increment, float(old + Fraction(increment))


def compare_event(candidate, reference, fs):
    changed = [key for key in TERMS if not same(candidate[key], reference[key])]
    substitutions = []
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            row = {**candidate, **{key: reference[key] for key in keys}}
            net, increment, pressure = pressure_update(row, fs)
            substitutions.append({'terms': keys, 'net_flow': net, 'pressure_increment': increment,
                                  'new_pressure': pressure, 'matches_upstream': same(pressure, reference['new_pressure'])})
    matching = [row['terms'] for row in substitutions if row['matches_upstream']]
    minimum = min(map(len, matching), default=0)
    return {'candidate': candidate, 'upstream': reference, 'differing_terms': changed,
            'replacement_results': substitutions, 'minimum_upstream_substitutions': [
                keys for keys in matching if len(keys) == minimum]}


def check_clock(balances, branches, trace):
    return all(same(row['old_pressure'], branch['left_pressure'])
               and same(row['glottal_outflow'], branch['flow'])
               and (row['internal_sample'] not in trace
                    or same(row['new_pressure'], trace[row['internal_sample']]['pressure_sub_dyn_cm2']))
               and (index == 0 or same(row['old_pressure'], balances[index - 1]['new_pressure']))
               for index, (row, branch) in enumerate(zip(balances, branches, strict=True)))


def measure(case, refs, copies, snapshot, out, execute):
    config = case['measurement']
    hashes = {'candidate': capture_native(refs, copies, snapshot, out, execute),
              'upstream': capture_upstream(case, config, refs, out, execute)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             '--test', 'engine'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    candidate, candidate_branch = read_balances('candidate', config, out)
    upstream, upstream_branch = read_balances('upstream', config, out)
    native_trace, upper_trace = ({row['internal_sample']: row for row in read_rows(out / path)} for path in (
        'candidate-internal.csv', 'upstream-trace.csv'))
    start = config['first_internal_sample']
    fs = config['internal_rate_hz']
    diffs = {}
    for key in FIELDS[1:]:
        index = first_difference([row[key] for row in candidate], [row[key] for row in upstream])
        diffs[key] = None if index is None else start + index
    sample = diffs['new_pressure']
    event = None if sample is None else compare_event(candidate[sample - start], upstream[sample - start], fs)
    expected = config['expected_first_pressure_difference']
    checks = {
        'candidate_branch_unchanged': sha256(out / 'candidate-branch.csv') == sha256(refs['momentum']['momentum-branch.csv']),
        'candidate_render_unchanged': sha256(out / 'candidate-internal.csv') == sha256(refs['momentum']['momentum-internal.csv']),
        'upstream_branch_unchanged': sha256(out / 'upstream-branch.csv') == sha256(refs['scaled']['upstream-branch.csv']),
        'upstream_trace_unchanged': sha256(out / 'upstream-trace.csv') == sha256(refs['pressure']['upstream-trace.csv']),
        'upstream_pcm_unchanged': sha256(out / 'upstream-voice.f32') == sha256(refs['pressure']['upstream-voice.f32']),
        'candidate_clock': check_clock(candidate, candidate_branch, native_trace),
        'upstream_clock': check_clock(upstream, upstream_branch, upper_trace),
        'independent_pressure_and_conservation': all(
            same(net, row['net_flow']) and same(pressure, row['new_pressure'])
            for row in (*candidate, *upstream) for net, _, pressure in (pressure_update(row, fs),)),
        'pressure_difference_first_appears_after_update': sample == expected and diffs['old_pressure'] == expected + 1,
        'glottal_flow_matches_at_pressure_difference': diffs['glottal_outflow'] == expected + 1,
        'pressure_difference_reproduced_from_measured_terms': bool(event and event['minimum_upstream_substitutions']),
    }
    return {'checks': checks, 'build_sha256': hashes, 'verified_internal_rows_each': len(candidate),
            'first_difference_by_field': diffs, 'first_pressure_difference': event}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    refs, manifests = {}, {}
    for group, files in REFERENCES.items():
        refs[group] = {}
        for name in files:
            manifest, path = verified_artifact(*case['references'][group], f'artifacts/{name}')
            manifests[group], refs[group][name] = manifest, path
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    utilities = [WORKSPACE / 'tools' / name for name in (
        'measure_fixed_voice_centerline.py', 'measure_fixed_voice_glottal_branch.py',
        'measure_fixed_voice_glottal_momentum.py', 'measure_fixed_voice_pharynx_onset.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_uniform_tube.py', 'upstream_baseline.py',
    )]
    inputs = [CASE, Path(__file__), PROBE, WORKSPACE / 'LICENSE-CHIMERA', *utilities, *archived,
              *manifests.values(), *(path for group in refs.values() for path in group.values())]
    details = {'case_id': case['id'], 'upstream_revision': revision, 'upstream_source_sha256': {
        name: sha256(UPSTREAM / name) for name in UPSTREAM_FILES}}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, run: measure(case, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
