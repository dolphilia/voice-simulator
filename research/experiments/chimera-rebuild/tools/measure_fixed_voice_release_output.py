"""固定発声の停止後に最初に分かれるPCMを出力段から追う。"""

import argparse
from fractions import Fraction
from itertools import combinations
import json
from math import copysign, tanh
from pathlib import Path
import shutil
from struct import iter_unpack, pack, unpack
import subprocess
import sys
from tempfile import TemporaryDirectory

from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import PROBE, apply_edits, f64
from measure_fixed_voice_pharyngeal_second_cell import (
    ROOT, apply_patch, candidate_patches, listed_input, read_rows, record_measurement, same,
    source_inputs, stage_candidate, verified_artifact,
)
from measure_uniform_tube import build_upstream_probe
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-release-output-48000.json'
OUTPUT = ('internal_sample', 'decimated', 'gain', 'input', 'previous_input', 'dc_pole', 'previous_dc',
          'filtered', 'previous_envelope', 'previous_hold', 'hold_duration', 'release', 'envelope', 'hold',
          'pre_cast', 'pcm_bits')
PROBE_NAME = 'upstream_release_probe.rs'
UPPER_VOICE = 'crates/chimera/src/voice/human_voice.rs'
UPPER_DECIMATOR = 'crates/chimera/src/airway/decimator.rs'
NATIVE_OUTPUT = 'crates/vocal-core/src/output.rs'


def rust_range(window):
    start, stop = window
    return f'{start}..{stop}'


def report(fields, tag, indent):
    return '\n'.join(indent + line for line in (
        f'let values = [{", ".join(fields)}];',
        f'print!("{tag},{{sample}}");',
        'for value in values { print!(",{value:?}"); }',
        'println!();',
    ))


def native_edits(case):
    frames = rust_range(case['output_window'])
    samples = rust_range(case['internal_window'])
    first = case['output_window'][0]
    push = '    pub fn push(&mut self, radiation: f64) -> Option<OutputFrame> {'
    dc = '        let highpassed = input - self.previous_input + self.dc_pole * self.previous_dc_removed;'
    details = report(('decimated', 'self.gain', 'input', 'previous_input', 'self.dc_pole', 'previous_dc',
                      'highpassed', 'previous_envelope', 'previous_hold as f64', 'self.hold_duration as f64',
                      'self.release', 'self.envelope', 'self.hold_frames as f64', 'sample_value',
                      'f64::from((sample_value as f32).to_bits())'), 'output', '            ')
    return (
        ('pub struct OutputStage {', 'pub struct OutputStage {\n    research_internal_sample: usize,'),
        ('            previous_dc_removed: 0.0,', '            previous_dc_removed: 0.0,\n            research_internal_sample: 0,'),
        ('        self.previous_dc_removed = 0.0;', '        self.previous_dc_removed = 0.0;\n        self.research_internal_sample = 0;'),
        (push, push + f'''
        let internal_sample = self.research_internal_sample;
        self.research_internal_sample += 1;
        if ({samples}).contains(&internal_sample) {{
            println!("release-radiation,{{internal_sample}},{{radiation:?}}");
        }}'''),
        (dc, '''        let (previous_input, previous_dc, previous_envelope, previous_hold) =
            (self.previous_input, self.previous_dc_removed, self.envelope, self.hold_frames);
''' + dc),
        ('        Some(OutputFrame {', f'''        if ({frames}).contains(&(internal_sample / self.decimator.factor)) {{
            if internal_sample / self.decimator.factor == {first} {{
                for (tap, value) in self.decimator.coefficients.iter().enumerate() {{
                    println!("tap,{{tap}},{{value:?}}");
                }}
            }}
            let sample_value = sample;
            let sample = internal_sample;
{details}
        }}
        Some(OutputFrame {{'''),
    )


def upstream_edits(case):
    frames = rust_range(case['output_window'])
    samples = rust_range(case['internal_window'])
    first = case['output_window'][0]
    start = '                let y = net.step();'
    dc = '                    let hp = v - self.dc_x + self.dc_coef * self.dc_y;'
    details = report(('self.dec.value', 'self.output_gain', 'input', 'previous_input', 'self.dc_coef', 'previous_dc',
                      'hp', 'previous_envelope', 'previous_hold as f64', 'self.lim_hold_n as f64',
                      'self.lim_release', 'self.lim_env', 'self.lim_hold as f64', 'v',
                      'f64::from((v as f32).to_bits())'), 'output', '                        ')
    return {
        UPPER_DECIMATOR: (('impl Decimator {', '''impl Decimator {
    pub(crate) fn research_coefficients(&self) -> &[f64] {
        &self.h
    }
'''),),
        UPPER_VOICE: (
            (start, start + f'''
                if ({samples}).contains(&(self.sub as usize)) {{
                    println!("release-radiation,{{}},{{y:?}}", self.sub);
                }}'''),
            (dc, '''                    let input = v;
                    let (previous_input, previous_dc, previous_envelope, previous_hold) =
                        (self.dc_x, self.dc_y, self.lim_env, self.lim_hold);
''' + dc),
            ('                    *o = v as f32;', f'''                    if ({frames}).contains(&(self.sub as usize / m)) {{
                        if self.sub as usize / m == {first} {{
                            for (tap, value) in self.dec.research_coefficients().iter().enumerate() {{
                                println!("tap,{{tap}},{{value:?}}");
                            }}
                        }}
                        let sample = self.sub;
{details}
                    }}
                    *o = v as f32;'''),
        ),
    }


def capture_candidate(case, saved, patches, copies, snapshot, out, execute, *, extra_edits=None, variant=None):
    with TemporaryDirectory(prefix='release-output-candidate-', dir=out.parent) as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'target'
        stage_candidate(snapshot, copies, source)
        for patch in patches:
            apply_patch(source, patch, execute)
        apply_edits(source, {NATIVE_OUTPUT: native_edits(case)}, out / 'candidate-release-output.patch')
        if extra_edits:
            apply_edits(source, extra_edits, out / 'candidate-release-radiation.patch')
        if variant:
            edits, name = variant
            apply_edits(source, edits, out / name)
        execute(['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)])
        cli = target / 'release/vocal-cli'
        for block in case['blocks']:
            execute([str(cli), 'render-pcm', str(saved['replay-case.json']), str(out / f'candidate-{block}.wav'),
                     '--no-trace', str(block)], stdout=out / f'candidate-{block}-raw.txt')
        return sha256(cli)


def capture_upstream(case, saved, out, execute, *, extra_edits=None):
    with TemporaryDirectory(prefix='release-output-upstream-', dir=out.parent) as temp:
        source = Path(temp)
        archive = source / 'source.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(source)])
        probe_source = source / PROBE_NAME
        shutil.copyfile(PROBE, probe_source)
        anchor = '                let index = (frame + 1) * factor - 1;'
        frames = rust_range(case['output_window'])
        # 全PCMは書き出し、既存のフレームCSVだけを観測区間へ絞る。
        probe_edits = ((anchor, f'                if !({frames}).contains(&frame) {{ continue; }}\n' + anchor),)
        apply_edits(source, {**upstream_edits(case), PROBE_NAME: probe_edits}, out / 'upstream-release-output.patch')
        if extra_edits:
            apply_edits(source, extra_edits, out / 'upstream-release-radiation.patch')
        probe = build_upstream_probe(probe_source, out, execute, upstream=source, cargo_args=('--offline',))
    voice = json.loads(saved['replay-case.json'].read_text())['voice']
    args = ['i', *(case[key] for key in ('internal_rate_hz', 'output_rate_hz', 'full_frames'))]
    args.extend(voice[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain'))
    execute([str(probe), 'render', *map(str, args), str(out), str(saved['gate-events.txt'])],
            cwd=UPSTREAM, stdout=out / 'upstream-raw.txt')
    return sha256(probe)


def parse_measurements(out, name, samples, clocks, taps):
    source = (out / f'{name}-raw.txt').read_text().splitlines(keepends=True)
    tables = {}
    for tag, fields, expected in (('radiation', ('internal_sample', 'value'), samples),
                                  ('tap', ('tap', 'coefficient'), range(taps)), ('output', OUTPUT, clocks)):
        path = out / f'{name}-{tag}.csv'
        prefix = ('release-radiation' if tag == 'radiation' else tag) + ','
        path.write_text(','.join(fields) + '\n' + ''.join(line.removeprefix(prefix) for line in source if line.startswith(prefix)))
        data = read_rows(path)
        if [row[fields[0]] for row in data] != list(expected):
            raise ValueError(f'登録した観測番号に欠測または重複があります ({path.name})')
        tables[tag] = data
    return tables


def pcm_bits(value):
    return unpack('<I', pack('<f', float(value)))[0]


def fir(history, coefficients):
    total = Fraction(0)
    for value, coefficient in zip(history, reversed(coefficients), strict=True):
        total = f64(total + f64(Fraction(value) * Fraction(coefficient)))
    return total


def output_step(row, decimated):
    data = {key: Fraction(value) for key, value in row.items()}
    x = f64(decimated * data['gain'])
    dc = f64(f64(x - data['previous_input']) + f64(data['dc_pole'] * data['previous_dc']))
    edge, hold = data['previous_envelope'], data['previous_hold']
    if abs(dc) >= edge:
        edge, hold = abs(dc), data['hold_duration']
    elif hold > 0:
        hold -= 1
    else:
        edge = f64(edge * data['release'])
    limited = f64(dc * f64(Fraction(0.75) / edge)) if edge > Fraction(0.75) else dc
    if abs(limited) > Fraction(0.85):
        excess = f64(f64(abs(limited) - Fraction(0.85)) / Fraction(0.15))
        limited = Fraction(copysign(float(f64(Fraction(0.85) + f64(Fraction(0.15) * Fraction(tanh(float(excess)))))), float(limited)))
    return {'input': float(x), 'filtered': float(dc), 'envelope': float(edge), 'hold': float(hold),
            'pre_cast': float(limited), 'pcm_bits': pcm_bits(limited)}


def validate(tables, pcm, factor):
    coeffs = [row['coefficient'] for row in tables['tap']]
    incoming = {int(row['internal_sample']): row['value'] for row in tables['radiation']}
    for row in tables['output']:
        sample = int(row['internal_sample'])
        history = [incoming[i] for i in range(sample + 1 - len(coeffs), sample + 1)]
        decimated = fir(history, coeffs)
        if not same(float(decimated), row['decimated']) or any(
                not same(value, row[key]) for key, value in output_step(row, decimated).items()):
            return False
        if pcm_bits(pcm[sample // factor]) != row['pcm_bits']:
            return False
    return True


def difference(left, right, case, target):
    factor = case['internal_rate_hz'] // case['output_rate_hz']
    clock = (target + 1) * factor - 1
    n = case['fir_taps']
    first = {}
    for name, fields in (('radiation', ('value',)), ('tap', ('coefficient',)), ('output', OUTPUT[1:])):
        for field in fields:
            first[field] = next((int(a.get('internal_sample', a.get('tap'))) for a, b in
                                 zip(left[name], right[name], strict=True) if not same(a[field], b[field])), None)
    a, b = [next(row for row in side['output'] if row['internal_sample'] == clock) for side in (left, right)]
    history_a, history_b = ([row['value'] for row in side['radiation'] if clock - n < row['internal_sample'] <= clock]
                            for side in (left, right))
    coef_a, coef_b = ([row['coefficient'] for row in side['tap']] for side in (left, right))
    groups = {'radiation_history': (), 'fir_coefficients': (), 'gain': ('gain',),
              'dc_memory': ('previous_input', 'previous_dc'), 'dc_pole': ('dc_pole',),
              'limiter_memory': ('previous_envelope', 'previous_hold'), 'limiter_parameters': ('hold_duration', 'release')}
    changed = [group for group, fields in groups.items() if any(not same(a[field], b[field]) for field in fields)]
    for key, left_values, right_values in (('radiation_history', history_a, history_b), ('fir_coefficients', coef_a, coef_b)):
        if any(not same(x, y) for x, y in zip(left_values, right_values, strict=True)):
            changed.append(key)

    def substituted(names):
        row = {**a, **{field: b[field] for name in names for field in groups[name]}}
        decimated = fir(history_b if 'radiation_history' in names else history_a,
                        coef_b if 'fir_coefficients' in names else coef_a)
        return {'decimated': float(decimated), **output_step(row, decimated)}

    matches = []
    for count in range(1, len(changed) + 1):
        matches = [names for names in combinations(changed, count) if substituted(names)['pcm_bits'] == b['pcm_bits']]
        if matches:
            break
    if abs(int(a['pcm_bits']) - int(b['pcm_bits'])) != 1:
        raise ValueError('対象PCMが隣接するf32であることを確認できません')
    lower, higher = (min(a['pre_cast'], b['pre_cast']), max(a['pre_cast'], b['pre_cast']))
    midpoint = (Fraction(unpack('<f', pack('<I', int(a['pcm_bits'])))[0])
                + Fraction(unpack('<f', pack('<I', int(b['pcm_bits'])))[0])) / 2
    return {'first_observed_differences': first, 'target': {'frame': target, 'candidate': a, 'upstream': b},
            'different_groups': changed, 'minimum_upstream_substitutions': matches,
            'single_group_substitutions': {group: substituted((group,)) for group in changed},
            'current_fir_with_upstream_inputs_and_coefficients': float(fir(history_b, coef_b)),
            'f32_midpoint': float(midpoint), 'pre_cast_offsets': [float(Fraction(x) - midpoint) for x in (lower, higher)]}


def measure(case, saved, patches, copies, snapshot, out, execute):
    build = {'candidate': capture_candidate(case, saved, patches, copies, snapshot, out, execute),
             'upstream': capture_upstream(case, saved, out, execute)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    factor = case['internal_rate_hz'] // case['output_rate_hz']
    samples = list(range(*case['internal_window']))
    clocks = [(i + 1) * factor - 1 for i in range(*case['output_window'])]
    taps = case['fir_taps']
    if clocks[0] + 1 - taps < samples[0] or clocks[-1] > samples[-1]:
        raise ValueError('採取区間がFIR履歴を覆っていません')
    names = [*(f'candidate-{block}' for block in case['blocks']), 'upstream']
    tables = {name: parse_measurements(out, name, samples, clocks, taps) for name in names}
    pcm = {}
    for name, block in zip(names[:-1], case['blocks'], strict=True):
        rate, data = wavfile.read(out / f'{name}.wav')
        if rate != case['output_rate_hz'] or len(data) != case['full_frames']:
            raise ValueError('研究版PCMのサンプルレートまたは長さが一致しません')
        pcm[name] = data
    upper_pcm = (out / 'upstream-voice.f32').read_bytes()
    pcm['upstream'] = [value for (value,) in iter_unpack('<f', upper_pcm)]
    main, alternate = names[:2]
    target = case['target_frame']
    details = difference(tables[main], tables['upstream'], case, target)
    first = next((i for i, (a, b) in enumerate(zip(pcm[main], pcm['upstream'], strict=True)) if pcm_bits(a) != pcm_bits(b)), None)
    checks = {
        'candidate_archived_full_pcm': all(sha256(out / f'candidate-{block}.wav') == sha256(saved[f'block-{block}.wav'])
                                           for block in case['blocks']),
        'fixed_upstream_archived_full_pcm': sha256(out / 'upstream-voice.f32') == sha256(saved['upstream-voice.f32']),
        'host_partition_pcm_and_observations': pcm[main].tobytes() == pcm[alternate].tobytes()
            and all(sha256(out / f'{main}-{tag}.csv') == sha256(out / f'{alternate}-{tag}.csv') for tag in tables[main]),
        'independent_fir_and_output': all(validate(tables[name], pcm[name], factor) for name in names),
        'registered_first_pcm_difference': first == target and details['pre_cast_offsets'][0] <= 0 <= details['pre_cast_offsets'][1],
        'target_pcm_reconstructed': bool(details['minimum_upstream_substitutions']),
    }
    return {'checks': checks, 'build_sha256': build, 'first_bit_difference_frame': first, **details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    candidate_manifest, changed = verified_artifact(*case['candidate_run'], 'artifacts/candidate-second-cell-history.patch')
    patches = [*candidate_patches(candidate_manifest), changed]
    source_manifest = listed_input(candidate_manifest, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    saved = {'replay-case.json': listed_input(candidate_manifest, 'replay-case.json')}
    for block in case['blocks']:
        name = f'block-{block}.wav'
        _, saved[name] = verified_artifact(*case['candidate_run'], f'artifacts/reordered/{name}')
    for name in ('gate-events.txt', 'upstream-voice.f32'):
        upstream_manifest, saved[name] = verified_artifact(*case['upstream_pcm_run'], f'artifacts/{name}')
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              source_manifest, candidate_manifest, upstream_manifest, *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, saved, patches, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
