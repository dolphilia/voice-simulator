"""気管の最初の直列枝の運動量換算だけを変えて連続描画を比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import NATIVE_HUMAN, NATIVE_NET, apply_edits, f64, replay, solve
from measure_fixed_voice_glottal_momentum import stage_candidate
from measure_fixed_voice_subglottal_balance import (
    CASE as BALANCE_CASE, ROOT, apply_patch, compare_event, pressure_update, read_rows,
    record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_onset import CASE as ONSET_CASE, first_by_cell, first_events, read_path
from measure_fixed_voice_tracheal_penultimate import flow_substitutions, pressure_row
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-tracheal-momentum-48000.json'
REFERENCES = {
    'geometry': ('combined.patch',),
    'scaled': ('candidate-observation.patch', 'candidate-inertance-scale.patch'),
    'momentum': ('candidate-momentum-scale.patch', 'momentum-128.wav', 'momentum-77.wav'),
    'pressure': ('prefix-case.json',),
    'onset': ('candidate-balance.patch', 'candidate-extra-observations.patch', 'candidate-internal.csv', 'candidate-raw.txt',
              'candidate-path-node.csv', 'candidate-path-branch.csv', 'upstream-path-node.csv', 'upstream-path-branch.csv'),
    'pcm': ('replay-case.json', 'upstream-voice.f32'),
}
PATCH_ORDER = ('combined.patch', 'candidate-observation.patch', 'candidate-inertance-scale.patch',
               'candidate-momentum-scale.patch', 'candidate-balance.patch', 'candidate-extra-observations.patch')
RECIPE = {
    NATIVE_NET: (
        ('glottis_rate: Option<f64>) -> f64 {', 'glottis_rate: Option<f64>,\n            history_rate: Option<f64>) -> f64 {'),
        ('let history = match glottis_rate {', 'let history = match history_rate {'),
        ('    research_rate_hz: f64,', '    research_rate_hz: f64,\n    pub(crate) research_tracheal_history: Option<usize>,'),
        ('            research_rate_hz: f64::from(sample_rate_hz),',
         '            research_rate_hz: f64::from(sample_rate_hz),\n            research_tracheal_history: None,'),
        ('            let flow = branch.step(self.dt, difference, observation, rate);',
         '''            let history_rate = if self.research_tracheal_history == Some(index) {
                Some(self.research_rate_hz)
            } else {
                rate
            };
            let flow = branch.step(self.dt, difference, observation, rate, history_rate);'''),
    ),
    NATIVE_HUMAN: (
        ('        network.research_glottis = Some((ports_start + 1, 0));',
         '        network.research_glottis = Some((ports_start + 1, 0));\n'
         '        network.research_tracheal_history = Some(trachea.branches.start);'),
    ),
}


def capture(case, refs, copies, snapshot, out, execute, *, patch_order=PATCH_ORDER, variant_edits=RECIPE,
            variant_patch_name='candidate-tracheal-history.patch'):
    hashes = {}
    with TemporaryDirectory(prefix='tracheal-momentum-', dir=out.parent) as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'target'
        stage_candidate(snapshot, copies, source)
        for name in patch_order:
            apply_patch(source, refs[name], execute)
        build = ['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)]
        cli = target / 'release/vocal-cli'
        for name in ('control', 'reordered'):
            run = out / name
            run.mkdir()
            if name == 'reordered':
                apply_edits(source, variant_edits, out / variant_patch_name)
            execute(build)
            hashes[name] = sha256(cli)
            execute([str(cli), 'render', str(refs['prefix-case.json']), str(run / 'candidate-internal.csv')],
                    stdout=run / 'candidate-raw.txt')
            for block in case['blocks']:
                execute([str(cli), 'render-pcm', str(refs['replay-case.json']), str(run / f'block-{block}.wav'),
                         '--no-trace', str(block)], stdout=run / f'block-{block}-probe.txt')
    return hashes


def load_baseline(refs, side):
    return [{(row['cell'], row['internal_sample']): row for row in read_rows(refs[f'{side}-path-{tag}.csv'])}
            for tag in ('node', 'branch')]


def check_equations(path, fs, history_cells=()):
    nodes, branches = path
    for row in nodes.values():
        net, _, pressure = pressure_update(pressure_row(row), fs)
        if not (same(net, row['net_flow']) and same(pressure, row['new_pressure'])):
            return False
    for (cell, _), row in branches.items():
        expected = replay(row, fs, False)
        if cell in history_cells:
            history = f64(expected['carried_momentum'] * fs)
            pressure = f64(f64(f64(row['left_pressure']) - f64(row['right_pressure'])) + f64(row['noise_pressure']))
            drive = f64(pressure + history)
            loss = f64(row['forward_loss'] if drive >= 0 else row['reverse_loss'])
            expected.update({'history_pressure': history, 'drive_pressure': drive, 'loss': loss,
                             **solve(expected['linear'], drive, loss)})
        if any(not same(float(value), row[key]) for key, value in expected.items()):
            return False
    return True


def pcm_report(case, refs, out, *, archived_control=None):
    controls, partitions = ([wavfile.read(out / name / f'block-{block}.wav') for block in case['blocks']]
                            for name in ('control', 'reordered'))
    rate, frames = case['sample_rate_hz'], case['full_frames']
    if any(actual != rate or audio.shape != (frames,) or audio.dtype != np.float32
           for actual, audio in (*controls, *partitions)):
        raise ValueError('PCMの型・サンプルレート・長さが登録と一致しません')
    control, attempt = controls[0][1], partitions[0][1]
    upper = np.fromfile(refs['upstream-voice.f32'], dtype='<f4')
    results = {}
    windows = (0, case['gate_open_frame'], case['gate_close_frame'], frames)
    for name, left, right in (('control_upstream', control, upper), ('reordered_upstream', attempt, upper),
                              ('reordered_control', attempt, control)):
        different = left.view('u4') != right.view('u4')
        results[name] = {**compare_pcm(left, right, case['pcm_absolute_tolerance']),
                         'different_frames': int(np.count_nonzero(different)),
                         'different_frames_by_period': dict(zip(
                             ('before_gate', 'voiced', 'after_gate_close'),
                             (int(np.count_nonzero(different[a:b])) for a, b in zip(windows, windows[1:])), strict=True))}
    if archived_control is None:
        archived_control = {block: refs[f'momentum-{block}.wav'] for block in case['blocks']}
    checks = {
        'control_archived_pcm': all(sha256(out / 'control' / f'block-{block}.wav') == sha256(archived_control[block])
                                    for block in case['blocks']),
        'host_block_invariance': all(a.tobytes() == b.tobytes() for (_, a), (_, b) in (controls, partitions)),
        'pcm_tolerance': all(comparison['first_frame_over_tolerance'] is None for comparison in results.values()),
    }
    return checks, results


def compare_nodes(left, right, fs):
    return compare_event(pressure_row(left), pressure_row(right), fs)


def measure(case, setup, refs, copies, snapshot, out, execute):
    hashes = capture(case, refs, copies, snapshot, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'lung_port'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    observation = setup['observation']
    count = observation['tracheal_cells']
    samples = list(range(observation['first_internal_sample'], observation['end_internal_sample_exclusive']))
    fs = case['internal_rate_hz']
    cell, point = (case[key] for key in ('target_cell', 'target_internal_sample'))
    control = read_path(out / 'control', 'candidate', count, samples)
    revised = read_path(out / 'reordered', 'candidate', count, samples)
    upper_nodes, upper_branches = load_baseline(refs, 'upstream')
    pressure_clock = first_by_cell(revised[0], upper_nodes, count, samples, 'new_pressure')
    flow_clock = first_by_cell(revised[1], upper_branches, count, samples, 'flow')
    prefix = [(node, sample) for sample in samples if sample < point for node in range(count)]
    checks = {
        'control_archived_traces': all(sha256(out / 'control' / name) == sha256(refs[name]) for name in (
            'candidate-internal.csv', 'candidate-raw.txt', 'candidate-path-node.csv', 'candidate-path-branch.csv')),
        'control_equations': check_equations(control, fs),
        'reordered_equations': check_equations(revised, fs, history_cells=(cell,)),
        'preceding_flow_and_pressure_unchanged': all(same(control[i][key][column], revised[i][key][column])
            for i, column in ((0, 'new_pressure'), (1, 'flow')) for key in prefix),
        'target_flow_and_pressure_equal_upstream': same(revised[1][cell, point]['flow'], upper_branches[cell, point]['flow'])
            and same(revised[0][cell, point]['new_pressure'], upper_nodes[cell, point]['new_pressure']),
        'target_linear_terms_unchanged': all(same(revised[1][cell, point][key], control[1][cell, point][key])
            for key in ('inertance', 'inertance_per_step', 'resistance', 'linear')),
    }
    pcm_checks, pcm = pcm_report(case, refs, out)
    checks.update(pcm_checks)
    return {'checks': checks, 'build_sha256': hashes, 'target': {'cell': cell, 'sample': point,
                'control_flow': control[1][cell, point]['flow'], 'reordered_flow': revised[1][cell, point]['flow'],
                'upstream_flow': upper_branches[cell, point]['flow'], 'reordered_pressure': revised[0][cell, point]['new_pressure']},
            'first_branch_flow_difference_by_cell': flow_clock, 'first_node_pressure_difference_by_cell': pressure_clock,
            'earliest_flow_events': first_events(flow_clock, revised[1], upper_branches, flow_substitutions, fs),
            'earliest_pressure_events': first_events(pressure_clock, revised[0], upper_nodes, compare_nodes, fs),
            'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    setup = json.loads(ONSET_CASE.read_text())
    base = json.loads(BALANCE_CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': case['onset_run'], 'pcm': case['pcm_input_run']}
    refs, manifests = {}, {}
    for group, names in REFERENCES.items():
        for name in names:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    full = json.loads(refs['replay-case.json'].read_text())
    if (full['fixed_airway']['sample_rate_hz'] != case['internal_rate_hz']
            or full['fixed_airway']['sample_count'] * case['sample_rate_hz'] != case['full_frames'] * case['internal_rate_hz']
            or full['voice']['output_sample_rate_hz'] != case['sample_rate_hz']
            or full['gate_events'] != [{'frame': case['gate_open_frame'], 'goal': 1.0},
                                      {'frame': case['gate_close_frame'], 'goal': 0.0}]):
        parser.error('PCM入力の条件が登録と一致しません')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, ONSET_CASE, BALANCE_CASE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              *manifests.values(), *refs.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, setup, refs, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
