"""通常描画の声門枝1本を観測し、運動量式を丸めの段ごとに照合する。"""

import argparse
from decimal import Decimal, localcontext
from difflib import unified_diff
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_centerline import first_difference, same, verified_artifact
from measure_fixed_voice_pharynx_onset import read_rows
from measure_songbird_chirps_volume_rate_propagation_44100 import stage_candidate
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/fixed-voice-glottal-branch-48000.json'
PROBE = WORKSPACE / 'tools/upstream_vowel_voice_probe.rs'
NATIVE_NET = 'crates/vocal-core/src/airway/network.rs'
NATIVE_HUMAN = 'crates/vocal-core/src/airway/human.rs'
UPPER_NET = 'crates/chimera/src/airway/network.rs'
UPPER_HUMAN = 'crates/chimera/src/voice/human_airway.rs'
FIELDS = (
    'internal_sample', 'area_cm2', 'left_pressure', 'right_pressure', 'noise_pressure',
    'previous_flow', 'previous_inertance', 'inertance', 'resistance', 'forward_loss', 'reverse_loss',
    'previous_momentum', 'carried_momentum', 'history_pressure', 'drive_pressure', 'inertance_per_step',
    'linear', 'loss', 'discriminant', 'root', 'numerator', 'denominator', 'flow',
)
FILES = {
    'combined': ('combined.patch', 'combined/internal.csv', 'combined/block-128.wav'),
    'upstream': ('prefix-case.json', 'gate-events.txt', 'upstream-trace.csv',
                 'upstream-voice.f32', 'upstream-pharynx-balance.csv'),
    'pcm': ('replay-case.json', 'upstream-voice.f32'),
}
NATIVE_STEP = '''    fn step(&mut self, dt: f64, pressure_difference: f64) -> f64 {
        let inertance_per_step = self.inertance / dt;
        // 慣性が増すときは運動量、減るときは流量を引き継ぐ。
        let carried_inertance = self.previous_inertance.min(self.inertance);
        let drive = pressure_difference + (carried_inertance / dt) * self.flow;
        let linear = inertance_per_step + self.resistance;
        let loss = if drive >= 0.0 {
            self.forward_loss
        } else {
            self.reverse_loss
        };
        self.flow = if loss == 0.0 {
            drive / linear
        } else {
            2.0 * drive / (linear + (linear * linear + 4.0 * loss * drive.abs()).sqrt())
        };
        self.previous_inertance = self.inertance;
        self.flow
    }'''
NATIVE_PROBE = '''    fn step(&mut self, dt: f64, pressure_difference: f64,
            trace: Option<(usize, f64, f64, f64)>) -> f64 {
        let previous_flow = self.flow;
        let inertance_per_step = self.inertance / dt;
        let carried_inertance = self.previous_inertance.min(self.inertance);
        let history = (carried_inertance / dt) * previous_flow;
        let drive = pressure_difference + history;
        let linear = inertance_per_step + self.resistance;
        let loss = if drive >= 0.0 { self.forward_loss } else { self.reverse_loss };
        let (discriminant, root, numerator, denominator) = if loss == 0.0 {
            (0.0, 0.0, drive, linear)
        } else {
            let discriminant = linear * linear + 4.0 * loss * drive.abs();
            let root = discriminant.sqrt();
            (discriminant, root, 2.0 * drive, linear + root)
        };
        self.flow = numerator / denominator;
        if let Some((sample, left, right, noise)) = trace {
            let values = [self.area_cm2, left, right, noise, previous_flow,
                self.previous_inertance, self.inertance, self.resistance, self.forward_loss,
                self.reverse_loss, self.previous_inertance * previous_flow, carried_inertance * previous_flow,
                history, drive, inertance_per_step, linear, loss, discriminant, root, numerator,
                denominator, self.flow];
            print!("{sample}");
            for value in values {
                print!(",{value}");
            }
            println!();
        }
        self.previous_inertance = self.inertance;
        self.flow
    }'''
UPSTREAM_STEP = '''                let c = p[a] - p[b] + psrc[j] + m0 * inv_t;
                let bq = l * inv_t + r;
                let u = if c >= 0.0 {
                    if kf > 0.0 { (2.0 * c) / (bq + sqrt(bq * bq + 4.0 * kf * c)) } else { c / bq }
                } else if kb > 0.0 {
                    (2.0 * c) / (bq + sqrt(bq * bq - 4.0 * kb * c))
                } else {
                    c / bq
                };'''
UPSTREAM_PROBE = '''                let history = m0 * inv_t;
                let c = p[a] - p[b] + psrc[j] + history;
                let inertance_per_step = l * inv_t;
                let bq = inertance_per_step + r;
                let loss = if c >= 0.0 { kf } else { kb };
                let (discriminant, root, numerator, denominator) = if loss > 0.0 {
                    let discriminant = if c >= 0.0 {
                        bq * bq + 4.0 * loss * c
                    } else {
                        bq * bq - 4.0 * loss * c
                    };
                    let root = sqrt(discriminant);
                    (discriminant, root, 2.0 * c, bq + root)
                } else {
                    (0.0, 0.0, c, bq)
                };
                let u = numerator / denominator;
                if let Some((_, sample)) = research.filter(|&(branch, _)| branch == j) {
                    let values = [a_eff, p[a], p[b], psrc[j], u_arr[j], lp, l, r, kf, kb,
                        mom[j], m0, history, c, inertance_per_step, bq, loss, discriminant, root,
                        numerator, denominator, u];
                    print!("{sample}");
                    for value in values {
                        print!(",{value}");
                    }
                    println!();
                }'''


def counter_code(cfg):
    first, end = (cfg[key] for key in ('first_internal_sample', 'end_internal_sample_exclusive'))
    return f'''        let research = self.research_glottis.as_mut().and_then(|(branch, next)| {{
            let sample = *next;
            *next += 1;
            ({first}..{end}).contains(&sample).then_some((*branch, sample))
        }});'''


def apply_edits(workspace, recipes, patch_file):
    diff = []
    for name, recipe in recipes.items():
        path = workspace / name
        before = after = path.read_text()
        for anchor, replacement in recipe:
            if after.count(anchor) != 1:
                raise ValueError(f'声門観測の差分を1箇所に特定できません ({name})')
            after = after.replace(anchor, replacement, 1)
        diff.extend(unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                 fromfile=f'a/{name}', tofile=f'b/{name}'))
        path.write_text(after)
    patch_file.write_text(''.join(diff))


def capture_native(m, followup, paths, copies, snapshot, artifacts, execute):
    recipes = {
        NATIVE_NET: (
            ('pub struct AirwayNetwork {', 'pub struct AirwayNetwork {\n    pub(crate) research_glottis: Option<(usize, usize)>,'),
            ('            previous_radiation_flow: 0.0,',
             '            previous_radiation_flow: 0.0,\n            research_glottis: None,'),
            ('        // 乱流が読むのは、断面を変更する前の枝面積と最後に解いた流量。',
             counter_code(m) + '\n        // 乱流が読むのは、断面を変更する前の枝面積と最後に解いた流量。'),
            (NATIVE_STEP, NATIVE_PROBE),
            ('            let flow = branch.step(self.dt, difference);', '''            let observation = research.filter(|&(watched, _)| watched == index)
                .map(|(_, sample)| (sample, self.pressure[left], self.pressure[right], noise));
            let flow = branch.step(self.dt, difference, observation);'''),
        ),
        NATIVE_HUMAN: (('        network.reserve_noise_sources(frication::MAX_TURBULENCE_SOURCES);',
                        '        network.reserve_noise_sources(frication::MAX_TURBULENCE_SOURCES);\n'
                        '        network.research_glottis = Some((ports_start + 1, 0));'),),
    }
    with TemporaryDirectory(prefix='glottis-native-', dir=artifacts.parent) as temp:
        directory = Path(temp)
        source = directory / 'source'
        stage_candidate(snapshot, copies, source)
        patch = paths['combined']['combined.patch']
        execute(['git', 'apply', '--check', str(patch)], cwd=source)
        execute(['git', 'apply', str(patch)], cwd=source)
        apply_edits(source, recipes, artifacts / 'candidate-observation.patch')
        target = directory / 'target'
        build = ['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)]
        cli = str(target / 'release/vocal-cli')
        execute(build)
        execute([cli, 'render', str(paths['upstream']['prefix-case.json']),
                 str(artifacts / 'candidate-internal.csv')], stdout=artifacts / 'candidate-branch-values.txt')
        scaled_recipes = {
            NATIVE_NET: (
                ('    pub(crate) research_glottis: Option<(usize, usize)>,',
                 '    pub(crate) research_glottis: Option<(usize, usize)>,\n    research_rate_hz: f64,'),
                ('            research_glottis: None,',
                 '            research_glottis: None,\n            research_rate_hz: f64::from(sample_rate_hz),'),
                ('trace: Option<(usize, f64, f64, f64)>) -> f64 {',
                 'trace: Option<(usize, f64, f64, f64)>, glottis_rate: Option<f64>) -> f64 {'),
                ('        let inertance_per_step = self.inertance / dt;',
                 '''        let inertance_per_step = match glottis_rate {
            Some(rate) => self.inertance * rate,
            None => self.inertance / dt,
        };'''),
                ('        let research = self.research_glottis.as_mut()', '''        let glottis = self.research_glottis.map(|(branch, _)| branch);
        let research = self.research_glottis.as_mut()'''),
                ('            let flow = branch.step(self.dt, difference, observation);',
                 '''            let rate = (glottis == Some(index)).then_some(self.research_rate_hz);
            let flow = branch.step(self.dt, difference, observation, rate);'''),
            ),
        }
        apply_edits(source, scaled_recipes, artifacts / 'candidate-inertance-scale.patch')
        execute(build)
        execute([cli, 'render', str(paths['upstream']['prefix-case.json']),
                 str(artifacts / 'scaled-internal.csv')], stdout=artifacts / 'scaled-branch-values.txt')
        for block in followup['pcm_block_sizes']:
            execute([cli, 'render-pcm', str(paths['pcm']['replay-case.json']),
                     str(artifacts / f'scaled-{block}.wav'), '--no-trace', str(block)])


def capture_upstream(case, cfg, refs, out, execute):
    recipes = {
        UPPER_NET: (
            ('pub struct AirwayNetwork {', 'pub struct AirwayNetwork {\n    pub research_glottis: Option<(usize, usize)>,'),
            ('            inv_t: fs,', '            inv_t: fs,\n            research_glottis: None,'),
            ('    pub fn step(&mut self) -> f64 {', '    pub fn step(&mut self) -> f64 {\n' + counter_code(cfg)),
            (UPSTREAM_STEP, UPSTREAM_PROBE),
        ),
        UPPER_HUMAN: (('        net.finalize();', '        net.finalize();\n        net.research_glottis = Some((glottis_port, 0));'),),
    }
    with TemporaryDirectory(prefix='glottis-upstream-', dir=out.parent) as temp:
        workspace = Path(temp)
        tar = workspace / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(workspace)])
        apply_edits(workspace, recipes, out / 'upstream-observation.patch')
        probe = build_upstream_probe(PROBE, out, execute, upstream=workspace)
    prefix = json.loads(refs['prefix-case.json'].read_text())
    arguments = [cfg[key] for key in ('ipa', 'internal_rate_hz', 'output_rate_hz', 'prefix_output_frames')]
    arguments.extend(prefix['voice'][key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))
    execute([str(probe), 'render', *map(str, arguments), str(out), str(refs['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-branch-values.txt')


def f64(number):
    return Fraction(float(number))


def solve(linear, drive, loss):
    if loss:
        square = f64(linear * linear)
        term = f64(f64(4 * loss) * abs(drive))
        discriminant = f64(square + term)
        with localcontext() as context:
            context.prec = 105
            root = f64((Decimal(discriminant.numerator) / Decimal(discriminant.denominator)).sqrt())
        denominator, numerator = f64(linear + root), f64(2 * drive)
    else:
        discriminant, root = Fraction(0), Fraction(0)
        denominator, numerator = linear, drive
    return {'discriminant': discriminant, 'root': root, 'numerator': numerator,
            'denominator': denominator, 'flow': f64(numerator / denominator)}


def replay(row, fs, upstream, *, scale_inertance=False, multiply_history=False):
    observed = {key: Fraction(value) for key, value in row.items()}
    current, previous, flow = (observed[key] for key in ('inertance', 'previous_inertance', 'previous_flow'))
    time = f64(Fraction(1, fs))
    inertia = min(current, previous)
    momentum = (observed['previous_momentum'] if upstream and current >= previous else f64(inertia * flow))
    history = f64(momentum * fs) if upstream or multiply_history else f64(f64(inertia / time) * flow)
    inertance_step = f64(current * fs) if upstream or scale_inertance else f64(current / time)
    pressure = f64(f64(observed['left_pressure'] - observed['right_pressure']) + observed['noise_pressure'])
    drive = f64(pressure + history)
    linear = f64(inertance_step + observed['resistance'])
    loss = observed['forward_loss'] if drive >= 0 else observed['reverse_loss']
    values = {'carried_momentum': momentum, 'history_pressure': history, 'inertance_per_step': inertance_step,
              'drive_pressure': drive, 'linear': linear, 'loss': loss, **solve(linear, drive, loss)}
    return values


def read_capture(name, m, artifacts):
    staging = artifacts / f'{name}-branch-values.txt'
    csv = artifacts / f'{name}-branch.csv'
    csv.write_text(','.join(FIELDS) + '\n' + staging.read_text())
    rows = read_rows(csv)
    if (list(rows[0]) != list(FIELDS)
            or [row['internal_sample'] for row in rows] != list(range(m['first_internal_sample'], m['end_internal_sample_exclusive']))):
        raise ValueError(f'測定した声門枝の列または内部サンプル番号が登録と一致しません ({name})')
    return rows


def compare_captures(native, upper, m, native_state, upper_state):
    start = m['first_internal_sample']
    fs = m['internal_rate_hz']
    firsts = {key: first_difference([row[key] for row in native], [row[key] for row in upper])
              for key in FIELDS[1:]}
    firsts = {key: None if index is None else index + start for key, index in firsts.items()}
    difference = m['first_flow_difference']
    index = difference - start
    actual, reference = native[index], upper[index]
    checks = {
        'recorded_flow_first_difference': firsts['flow'] == difference,
        'upstream_and_candidate_same_input_pressure_and_previous_flow': all(same(actual[key], reference[key])
            for key in ('left_pressure', 'right_pressure', 'previous_flow', 'area_cm2', 'noise_pressure')),
    }
    for name, rows, state in (('candidate', native, native_state), ('upstream', upper, upper_state)):
        checks[f'{name}_observed_at_correct_branch_and_sample'] = all(
            same(row['flow'], state[i]['glottal_flow_cm3_s'])
            and same(row['area_cm2'], state[i]['glottal_area_cm2'])
            and same(row['previous_flow'], state[i-1]['glottal_flow_cm3_s'])
            and same(row['right_pressure'], state[i-1]['pressure_supra_dyn_cm2'])
            for i, row in enumerate(rows, start))
        checks[f'{name}_independent_branch_equation'] = all(
            all(same(float(value), row[key]) for key, value in replay(row, fs, name == 'upstream').items())
            for row in rows)
    choices = ('drive_pressure', 'linear', 'loss')
    different = [key for key in choices if not same(actual[key], reference[key])]
    swaps = []
    for size in range(1, len(different) + 1):
        for keys in combinations(different, size):
            mixed = {**actual, **{key: reference[key] for key in keys}}
            result = solve(*(Fraction(mixed[key]) for key in ('linear', 'drive_pressure', 'loss')))['flow']
            if same(float(result), reference['flow']):
                swaps.append(keys)
        if swaps:
            break
    checks['causal_terms_reproduce_upstream_flow'] = bool(swaps)
    return checks, {'first_difference_by_field': firsts, 'window': [start, m['end_internal_sample_exclusive']],
                    'registered_first_flow_difference': {'sample': difference,
                        'candidate': actual, 'upstream': reference, 'minimal_upstream_substitutions': swaps}}


def compare_scaled(standard, upper, scaled, m, followup, paths, out, upper_state):
    first, sample = (m[key] for key in ('first_internal_sample', 'first_flow_difference'))
    index = sample - first
    native, reference = standard[index], upper[index]
    alternatives = {}
    for key, description in (('inertance_per_step', 'inertance_only'), ('resistance', 'resistance_only')):
        coefficients = {**native, key: reference[key]}
        linear = f64(Fraction(coefficients['inertance_per_step']) + Fraction(coefficients['resistance']))
        solution = solve(linear, Fraction(coefficients['drive_pressure']), Fraction(coefficients['loss']))
        alternatives[description] = {'linear': float(linear), 'flow': float(solution['flow'])}
    fs = m['internal_rate_hz']
    state = read_rows(out / 'scaled-internal.csv')
    checks = {
        'isolated_inertance_scale_explains_first_difference': (
            same(alternatives['inertance_only']['flow'], reference['flow'])
            and same(alternatives['resistance_only']['flow'], native['flow'])),
        'scaled_independent_branch_equation': all(
            all(same(float(value), row[key]) for key, value in replay(row, fs, False, scale_inertance=True).items())
            for row in scaled),
        'scaled_flow_rejoins_upstream_at_8210': (
            all(same(a['flow'], b['flow']) for a, b in zip(standard[:index], scaled[:index], strict=True))
            and same(scaled[index]['flow'], reference['flow'])
            and same(state[sample]['pressure_supra_dyn_cm2'], upper_state[sample]['pressure_supra_dyn_cm2'])),
        'scaled_rows_are_aligned_with_pressure': all(
            same(row['flow'], state[i]['glottal_flow_cm3_s'])
            and same(row['right_pressure'], state[i-1]['pressure_supra_dyn_cm2'])
            for i, row in enumerate(scaled, first)),
    }
    result = {'flow_at_original_first_difference': scaled[index]['flow'],
              'pressure_at_original_first_difference': state[sample]['pressure_supra_dyn_cm2'],
              'local_substitutions': alternatives}
    result['first_flow_difference'] = next((i for i, (a, b) in enumerate(zip(scaled, upper, strict=True), first)
                                            if not same(a['flow'], b['flow'])), None)
    result['first_pressure_difference'] = first_difference([row['pressure_supra_dyn_cm2'] for row in state],
                                                            [row['pressure_supra_dyn_cm2'] for row in upper_state])
    rates_and_signals = [wavfile.read(out / f'scaled-{block}.wav') for block in followup['pcm_block_sizes']]
    control_rate, control = wavfile.read(paths['combined']['combined/block-128.wav'])
    upper_pcm = np.fromfile(paths['pcm']['upstream-voice.f32'], dtype='<f4')
    expected = m['output_rate_hz']
    frames = followup['full_output_frames']
    if control_rate != expected or any(rate != expected or audio.shape != (frames,) or audio.dtype != np.float32
                                       for rate, audio in [*rates_and_signals, (control_rate, control)]):
        raise ValueError('全区間のWAVのレート・長さ・型を登録条件へ対応付けられません')
    wave, second = (signal for _, signal in rates_and_signals)
    tolerance = followup['pcm_absolute_tolerance']
    result['pcm'] = {key: {**compare_pcm(wave, reference, tolerance),
                         'different_frames': int(np.count_nonzero(wave.view('u4') != reference.view('u4')))}
                     for key, reference in (('upstream', upper_pcm), ('combined', control))}
    checks['scaled_pcm_block_partitions_agree'] = wave.tobytes() == second.tobytes()
    checks['scaled_pcm_in_tolerance'] = all(record['first_frame_over_tolerance'] is None
                                           for record in result['pcm'].values())
    return checks, result


def measure(case, refs, copies, snapshot, out, execute):
    m = case['measurement']
    followup = case['inertance_scale_followup']
    prefix = json.loads(refs['upstream']['prefix-case.json'].read_text())
    if ((prefix['voice']['output_sample_rate_hz'], prefix['fixed_airway']['sample_rate_hz'], prefix['fixed_airway']['sample_count'])
            != (m['output_rate_hz'], m['internal_rate_hz'],
                m['prefix_output_frames'] * m['internal_rate_hz'] // m['output_rate_hz'])
            or prefix['gate_events'][0] != {'frame': m['gate_open_frame'], 'goal': 1.0}):
        raise ValueError('先行実行の発声開始とサンプルレートが登録値と異なります')
    full = json.loads(refs['pcm']['replay-case.json'].read_text())
    expected_stop = {'frame': followup['gate_close_frame'], 'goal': 0.0}
    if (full['fixed_airway']['sample_rate_hz'] != m['internal_rate_hz']
            or full['fixed_airway']['sample_count'] != followup['full_output_frames'] * m['internal_rate_hz'] // m['output_rate_hz']
            or full['voice'] != prefix['voice'] or full['posture'] != prefix['posture']
            or full['gate_events'] != [*prefix['gate_events'], expected_stop]):
        raise ValueError('先行実行の全区間と短区間で発声条件が一致しません')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine',
             '--test', 'airway_adversarial'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    capture_native(m, followup, refs, copies, snapshot, out, execute)
    capture_upstream(case, m, refs['upstream'], out, execute)
    native_state = read_rows(refs['combined']['combined/internal.csv'])
    upper_state = read_rows(refs['upstream']['upstream-pharynx-balance.csv'])
    native, upstream = [read_capture(name, m, out) for name in ('candidate', 'upstream')]
    checks, values = compare_captures(native, upstream, m, native_state, upper_state)
    checks.update(
        candidate_observation_did_not_change_render=sha256(out / 'candidate-internal.csv')
        == sha256(refs['combined']['combined/internal.csv']),
        upstream_observation_did_not_change_render=all(sha256(out / name) == sha256(refs['upstream'][name])
                                                     for name in ('upstream-trace.csv', 'upstream-voice.f32')),
    )
    prior = json.loads(refs['first_capture']['summary.json'].read_text())
    checks['revision_1_checks_reproduced'] = all(checks.get(name) is status for name, status in prior['checks'].items())
    followup_checks, changed = compare_scaled(native, upstream, read_capture('scaled', m, out),
                                              m, followup, refs, out, upper_state)
    checks.update(followup_checks)
    return {'checks': checks, **values, 'inertance_scale_experiment': changed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    refs, inputs = {}, [CASE, Path(__file__), PROBE, WORKSPACE / 'LICENSE-CHIMERA']
    for label, names in FILES.items():
        refs[label] = {}
        for name in names:
            manifest, artifact = verified_artifact(*case['references'][label], f'artifacts/{name}')
            refs[label][name] = artifact
            inputs.extend((manifest, artifact))
    initial_manifest, initial_summary = verified_artifact(*case['references']['first_capture'], 'summary.json')
    refs['first_capture'] = {'summary.json': initial_summary}
    inputs.extend((initial_manifest, initial_summary))
    copies = [*candidate_sources(), *(WORKSPACE / 'data' / name for name in (
        'cmudict.txt.gz', 'CMUDICT-LICENSE.txt', 'mandarin.txt.gz', 'MANDARIN-PINYIN-LICENSE.txt'))]
    tools = [WORKSPACE / 'tools' / name for name in (
        'measure_fixed_voice_centerline.py', 'measure_fixed_voice_pharynx_onset.py',
        'measure_songbird_chirps_volume_rate_propagation_44100.py', 'measure_uniform_tube.py',
        'measure_wasm_fixed.py', 'upstream_baseline.py',
    )]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'upstream_source_sha256': {
        name: sha256(UPSTREAM / name) for name in (UPPER_NET, UPPER_HUMAN,
                                                 'crates/chimera/src/voice/human_voice.rs',
                                                 'crates/chimera/tests/airway_adversarial.rs',
                                                 'crates/chimera/tests/engine.rs')}}
    snapshot = WORKSPACE / 'runs' / args.run_id / 'artifacts/source'
    return record_measurement(args.run_id, CASE, [*inputs, *tools, *copies], details,
                              lambda out, run: measure(case, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
