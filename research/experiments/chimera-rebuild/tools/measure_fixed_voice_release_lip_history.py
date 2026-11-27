"""口端直前の枝の持ち越し圧だけを変えた連続描画を比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import NATIVE_NET
from measure_fixed_voice_pharyngeal_second_cell import (
    ROOT, candidate_patches, listed_input, read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_radiation_balance import validate as validate_radiation
from measure_fixed_voice_release_lip_branch import CASE as BRANCH_CASE, branch_edits, branch_rows, connect
from measure_fixed_voice_release_lip_load import CASE as LIP_CASE, capture_lip_rows, validate as validate_lip
from measure_fixed_voice_release_output import CASE as OUTPUT_CASE, capture_candidate, parse_measurements, validate as validate_output
from measure_fixed_voice_release_radiation import CASE as RADIATION_CASE, components, validate_inputs
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-release-lip-history-48000.json'
NODE_LOOP = '        for (index, (branch, &noise)) in self'
HISTORY = '            let history_rate = if self.research_lung_port_history == Some(index)'
HISTORY_VARIANT = {NATIVE_NET: (
    (NODE_LOOP, '''        let lip_history_node = glottis.and_then(|_| self.radiators.iter().position(Option::is_some));
''' + NODE_LOOP),
    (HISTORY, HISTORY + '''
                || (lip_history_node == Some(right) && left + 1 == right && branch.port.is_none())'''),
)}
KINDS = ('lip-branch', 'lip-branch-geometry', 'lip-load', 'release-component', 'release-wall', 'output', 'tap', 'radiation')


def read_output_csv(path):
    return {int(row['internal_sample']): row for row in read_rows(path)}


def compare_series(a, b, field):
    terms = [(i, a[i][field] - b[i][field]) for i in a if not same(a[i][field], b[i][field])]
    return {'first_sample': terms[0][0] if terms else None, 'different_samples': len(terms),
            'max_absolute_difference': max((abs(delta) for _, delta in terms), default=0.0)}


def pcm_comparison(a, b, source, tolerance):
    report = compare_pcm(a, b, tolerance)
    differences = a.view('<u4') != b.view('<u4')
    start, stop = source['gate_open_frame'], source['gate_close_frame']
    report['different_frames'] = int(differences.sum())
    report['different_frames_by_period'] = {name: int(differences[indices].sum()) for name, indices in (
        ('before_gate', slice(0, start)), ('voiced', slice(start, stop)), ('after_gate_close', slice(stop, None)))}
    return report


def inspect_candidate(folder, side, case, branch, radiation, source):
    fs = source['internal_rate_hz']
    factor = fs // source['output_rate_hz']
    internal_samples = list(range(*branch['branch_window']))
    component_samples = list(range(*radiation['component_window']))
    output_windows = list(range(*source['internal_window']))
    clocks = [(i + 1) * factor - 1 for i in range(*source['output_window'])]
    output = parse_measurements(folder, side, output_windows, clocks, source['fir_taps'])
    term_list, walls = components(folder, side, component_samples)
    terms = {int(row['internal_sample']): row for row in term_list}
    lip = capture_lip_rows(folder, side, internal_samples)
    line, geometry = branch_rows(folder, side, internal_samples, case['branch_nodes'])
    rate, audio = wavfile.read(folder / f'{side}.wav')
    if rate != source['output_rate_hz'] or audio.dtype != np.float32 or audio.shape != (source['full_frames'],):
        raise ValueError(f'PCMの型・レート・長さが事前登録と一致しません ({side})')
    checks = {'branch_and_lip_clock': connect(line, lip, fs, False, multiply_history=folder.name == 'reordered'),
              'lip_equations': validate_lip(lip, terms, fs, False),
              'radiation_balance': validate_radiation(term_list, walls, {}, fs, False, multiply_rate=True)
                and validate_inputs(term_list, output),
              'output_equations': validate_output(output, audio, factor)}
    return checks, {'branch': line, 'geometry': geometry, 'lip': lip, 'components': terms,
                    'radiation': {int(row['internal_sample']): row for row in output['radiation']},
                    'output': {int(row['internal_sample']): row for row in output['output']}, 'audio': audio}


def measure(case, branch, lip, radiation, source, saved, patches, copies, snapshot, out, execute):
    native_edits, _ = branch_edits(branch, lip, radiation)
    blocks = source['blocks']
    names = [f'candidate-{block}' for block in blocks]
    builds, data, checks = {}, {}, {}
    for mode in ('control', 'reordered'):
        folder = out / mode
        folder.mkdir()
        variant = (HISTORY_VARIANT, 'candidate-release-lip-history.patch') if mode == 'reordered' else None
        builds[mode] = capture_candidate(source, saved, patches, copies, snapshot, folder, execute,
                                         extra_edits=native_edits, variant=variant)
        measures = [inspect_candidate(folder, side, case, branch, radiation, source) for side in names]
        checks[f'{mode}_equations'] = all(all(results.values()) for results, _ in measures)
        checks[f'{mode}_host_partition'] = all(
            sha256(folder / f'{names[0]}-{kind}.csv') == sha256(folder / f'{names[1]}-{kind}.csv') for kind in KINDS
        ) and measures[0][1]['audio'].tobytes() == measures[1][1]['audio'].tobytes()
        data[mode] = measures[0][1]
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    archived = [*(f'{side}.wav' for side in names), *(f'{side}-{kind}.csv' for side in names for kind in KINDS)]
    checks['archived_control_reproduced'] = all(sha256(out / 'control' / name) == sha256(saved[name]) for name in archived)
    tag = {'branch': 'lip-branch', 'geometry': 'lip-branch-geometry', 'lip': 'lip-load',
           'components': 'release-component', 'radiation': 'radiation', 'output': 'output'}
    data['upstream'] = {field: read_output_csv(saved[f'upstream-{kind}.csv']) for field, kind in tag.items()}
    data['upstream']['audio'] = np.fromfile(saved['upstream-voice.f32'], dtype='<f4')

    pairs = (('control', 'upstream'), ('reordered', 'upstream'), ('reordered', 'control'))
    pcm, traces = {}, {}
    fields = {'branch_flow': ('branch', 'flow'), 'history_pressure': ('branch', 'history_pressure'),
              'left_pressure': ('branch', 'left_pressure'), 'right_pressure': ('branch', 'right_pressure'),
              'lip_pressure': ('lip', 'new_pressure'), 'lip_flow': ('lip', 'lip_flow'),
              'radiation_derivative': ('radiation', 'value'), 'pre_cast': ('output', 'pre_cast')}
    for left, right in pairs:
        label = f'{left}_{right}'
        a, b = data[left], data[right]
        pcm[label] = pcm_comparison(a['audio'], b['audio'], source, case['pcm_absolute_tolerance'])
        traces[label] = {key: compare_series(a[name], b[name], field) for key, (name, field) in fields.items()}
    checks['pcm_tolerance'] = all(report['first_frame_over_tolerance'] is None for report in pcm.values())
    factor = source['internal_rate_hz'] // source['output_rate_hz']
    frame = case['target_output_frame']
    internal = (frame + 1) * factor - 1
    targets = {str(i): {mode: {key: values[name][i][field] for key, (name, field) in fields.items()
                              if name in ('branch', 'lip', 'radiation')}
                       for mode, values in data.items()}
               for i in case['target_internal_samples']}
    pending = {}
    for i in case['target_internal_samples']:
        a, b = (data[mode]['branch'][i] for mode in ('reordered', 'upstream'))
        if not same(a['flow'], b['flow']):
            pending[str(i)] = flow_substitutions(a, b, source['internal_rate_hz'])
    frame_at = {mode: values['output'][internal] for mode, values in data.items()}
    return {'checks': checks, 'build_sha256': builds, 'traces': traces, 'targets': targets,
            'target_output': {'frame': frame, **frame_at}, 'remaining_branch_events': pending, 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference, _ = verified_artifact(*case['branch_run'], 'artifacts/upstream-voice.f32')
    paths = [listed_input(reference, path.name) for path in (BRANCH_CASE, LIP_CASE, RADIATION_CASE, OUTPUT_CASE)]
    branch, lip, radiation, source = (json.loads(path.read_text()) for path in paths)
    if case['branch_nodes'] != branch['branch_nodes'] or case['target_output_frame'] != source['target_frame']:
        parser.error('対象の枝、出力フレームを先行の比較と揃えてください')
    blocks = source['blocks']
    names = [*(f'candidate-{block}' for block in blocks), 'upstream']
    files = [*(f'{name}-{kind}.csv' for name in names for kind in KINDS),
             *(f'candidate-{block}.wav' for block in blocks), 'upstream-voice.f32']
    saved = {name: verified_artifact(*case['branch_run'], f'artifacts/{name}')[1] for name in files}
    saved['replay-case.json'] = listed_input(reference, 'replay-case.json')
    source_manifest = listed_input(reference, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    patches = candidate_patches(reference)
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, *paths, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              reference, source_manifest, *saved.values(), *patches]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, branch, lip, radiation, source, saved, patches, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
