"""停止後のPCM差を壁・口端・鼻端と前回の放射流量和に分ける。"""

import argparse
from itertools import combinations
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET, PROBE, UPPER_NET
from measure_fixed_voice_pharyngeal_second_cell import (
    ROOT, candidate_patches, listed_input, read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_radiation_balance import (
    OUTPUT_FIELDS, WALL_FIELDS, derivative, sum_flow, upstream_edits as upstream_radiation_edits,
    validate as validate_radiation,
)
from measure_fixed_voice_release_output import (
    CASE as OUTPUT_CASE, capture_candidate, capture_upstream, fir, output_step, parse_measurements, rust_range,
)
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-release-radiation-48000.json'
TERMS = ('wall', 'lip', 'nose', 'previous_total')
CURRENT_TERMS = TERMS[:3]


def component_edits(window):
    old_window = '(8188..8240).contains(sample) || (9598..9610).contains(sample)'
    current_window = rust_range(window)
    native = ((old_window, f'({current_window}).contains(sample)'),
              ('println!("radiation,{sample}', 'println!("release-component,{sample}'),
              ('print!("radiating-wall,{sample}', 'print!("release-wall,{sample}'))
    upper = upstream_radiation_edits([window])
    mark = '        let mut wall_rad_sum = 0.0;'
    upper_selector = f'''        let release_index = self.research_release_sample;
        self.research_release_sample += 1;
        let radiation_sample = ({current_window}).contains(&release_index).then_some(release_index);
''' + mark
    upstream = (('    rad_prev_total: f64,', '    rad_prev_total: f64,\n    research_release_sample: usize,'),
                ('            rad_prev_total: 0.0,', '            rad_prev_total: 0.0,\n            research_release_sample: 0,'),
                (mark, upper_selector),
                *((anchor, replacement.replace('"radiation,', '"release-component,').replace('"radiating-wall,', '"release-wall,'))
                  for anchor, replacement in upper[1:]))
    return {NATIVE_NET: native}, {UPPER_NET: upstream}


def components(out, side, samples):
    raw = (out / f'{side}-raw.txt').read_text().splitlines(keepends=True)
    contents = []
    for name, fields in (('release-component', OUTPUT_FIELDS), ('release-wall', WALL_FIELDS)):
        path = out / f'{side}-{name}.csv'
        prefix = name + ','
        path.write_text(','.join(fields) + '\n' + ''.join(line.removeprefix(prefix) for line in raw if line.startswith(prefix)))
        contents.append(read_rows(path))
    terms, walls = contents
    wall_nodes = {row['node'] for row in walls}
    identified = {(row['internal_sample'], row['node']) for row in walls}
    if ([row['internal_sample'] for row in terms] != samples or not wall_nodes or len(identified) != len(walls)
            or identified != {(sample, node) for sample in samples for node in wall_nodes}):
        raise ValueError(f'放射成分の内部番号または壁の番号が不足しています ({side})')
    return terms, walls


def output_values(output, pcm_target, factor):
    clock = (pcm_target + 1) * factor - 1
    taps = [row['coefficient'] for row in output['tap']]
    inputs = {int(row['internal_sample']): row['value'] for row in output['radiation']}
    history_start = clock - len(taps) + 1
    row, = [row for row in output['output'] if row['internal_sample'] == clock]
    return row, taps, {index: inputs[index] for index in range(history_start, clock + 1)}


def evaluate_sample(sample, candidate, upstream, fs, render, upper_bits):
    a, b = candidate[sample], upstream[sample]
    changed = [key for key in TERMS if not same(a[key], b[key])]
    history = {sample: b['derivative']}
    result = {'candidate': a, 'upstream': b, 'different_terms': changed,
              'whole_radiation': render(history), 'local': [], 'shared_total': []}
    for size in range(1, len(changed) + 1):
        for keys in combinations(changed, size):
            values = {**a, **{key: b[key] for key in keys}}
            current = sum_flow(values)
            y = derivative(current, values['previous_total'], fs, True)
            local = render({sample: y})
            result['local'].append({'terms': keys, 'derivative': y, 'reproduces_derivative': same(y, b['derivative']),
                                    'reproduces_pcm': local['pcm_bits'] == upper_bits, **local})
            # 置換した流量和を共有する隣接微分にも反映する。
            modified = {sample: y}
            if 'previous_total' in keys:
                modified[sample - 1] = derivative(values['previous_total'], candidate[sample - 1]['previous_total'], fs, True)
            if any(key in CURRENT_TERMS for key in keys):
                modified[sample + 1] = derivative(candidate[sample + 1]['total'], float(current), fs, True)
            simultaneous = render(modified)
            result['shared_total'].append({'terms': keys, 'affected_derivatives': modified,
                                           'reproduces_pcm': simultaneous['pcm_bits'] == upper_bits, **simultaneous})
    for group, key in (('local', 'reproduces_derivative'), ('local', 'reproduces_pcm'), ('shared_total', 'reproduces_pcm')):
        matches = [attempt['terms'] for attempt in result[group] if attempt[key]]
        size = min(map(len, matches), default=0)
        result[f'minimum_{group}_{key}'] = [terms for terms in matches if len(terms) == size]
    return result


def validate_inputs(terms, outputs):
    source = {row['internal_sample']: row['value'] for row in outputs['radiation']}
    return all(same(row['derivative'], source[row['internal_sample']]) for row in terms)


def measure(case, output_case, saved, patches, copies, snapshot, out, execute):
    native, upstream = component_edits(case['component_window'])
    builds = {'candidate': capture_candidate(output_case, saved, patches, copies, snapshot, out, execute, extra_edits=native),
              'upstream': capture_upstream(output_case, saved, out, execute, extra_edits=upstream)}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = output_case['internal_rate_hz']
    factor = fs // output_case['output_rate_hz']
    windows = list(range(*output_case['internal_window']))
    clocks = [(i + 1) * factor - 1 for i in range(*output_case['output_window'])]
    samples = list(range(*case['component_window']))
    names = [*(f'candidate-{block}' for block in output_case['blocks']), 'upstream']
    tables = {name: parse_measurements(out, name, windows, clocks, output_case['fir_taps']) for name in names}
    captures = {name: components(out, name, samples) for name in names}
    main, alternate = names[:2]
    term_table = {name: {int(row['internal_sample']): row for row in data[0]} for name, data in captures.items()}
    row, taps, history = output_values(tables[main], output_case['target_frame'], factor)
    upper_row, _, _ = output_values(tables['upstream'], output_case['target_frame'], factor)

    def render(replacements):
        new_history = [replacements.get(index, value) for index, value in history.items()]
        raw = fir(new_history, taps)
        return {'decimated': float(raw), **output_step(row, raw)}

    result = {str(sample): evaluate_sample(sample, term_table[main], term_table['upstream'], fs, render, upper_row['pcm_bits'])
              for sample in case['target_internal_samples']}
    previous_files = [*(f'candidate-{block}.wav' for block in output_case['blocks']), 'upstream-voice.f32',
                      *(f'{name}-{kind}.csv' for name in names for kind in ('output', 'tap', 'radiation'))]
    checks = {
        'archived_pcm_and_output_observations': all(sha256(out / name) == sha256(saved[name]) for name in previous_files),
        'component_equations_and_fir_inputs': all(
            validate_radiation(*captures[name], {}, fs, name == 'upstream', multiply_rate=True)
            and validate_inputs(captures[name][0], tables[name]) for name in names),
        'host_partition_components': all(sha256(out / f'{main}-{tag}.csv') == sha256(out / f'{alternate}-{tag}.csv')
                                         for tag in ('release-component', 'release-wall')),
        'original_pcm_reconstructed': render({})['pcm_bits'] == row['pcm_bits'],
        'each_registered_point_reproduces_upstream_pcm': all(event['whole_radiation']['pcm_bits'] == upper_row['pcm_bits']
                                                            for event in result.values()),
        'each_registered_point_has_component_explanation': all(event['minimum_local_reproduces_derivative']
                                                              and event['minimum_local_reproduces_pcm'] for event in result.values()),
    }
    return {'checks': checks, 'build_sha256': builds, 'target_frame': output_case['target_frame'],
            'candidate_pcm_bits': row['pcm_bits'], 'upstream_pcm_bits': upper_row['pcm_bits'], 'events': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    output_manifest, _ = verified_artifact(*case['output_run'], 'artifacts/upstream-voice.f32')
    output_path = listed_input(output_manifest, OUTPUT_CASE.name)
    output_case = json.loads(output_path.read_text())
    names = [*(f'candidate-{block}' for block in output_case['blocks']), 'upstream']
    files = [*(f'{name}-{tag}.csv' for name in names for tag in ('output', 'tap', 'radiation')),
             *(f'{name}.wav' for name in names[:-1]), 'upstream-voice.f32']
    saved = {name: verified_artifact(*case['output_run'], f'artifacts/{name}')[1] for name in files}
    for name in ('gate-events.txt', 'replay-case.json'):
        saved[name] = listed_input(output_manifest, name)
    source_manifest = listed_input(output_manifest, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    patches = candidate_patches(output_manifest)
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, output_path, PROBE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              output_manifest, source_manifest, *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, output_case, saved, patches, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
