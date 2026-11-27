"""慣性を揃えた声門枝で持ち越し圧の換算順を比較する。"""

import argparse
from fractions import Fraction
from itertools import combinations
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_centerline import first_difference, same, verified_artifact
from measure_fixed_voice_glottal_branch import NATIVE_NET, apply_edits, read_capture, replay, solve
from measure_fixed_voice_pharynx_onset import PRESSURE, pressure_terms, read_rows, restore_pressure
from measure_songbird_chirps_volume_rate_propagation_44100 import stage_candidate
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import compare_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/fixed-voice-glottal-momentum-48000.json'
FILES = {
    'scaled': ('candidate-observation.patch', 'candidate-inertance-scale.patch', 'upstream-branch.csv',
               'scaled-branch.csv', 'scaled-internal.csv', 'scaled-128.wav'),
    'geometry': ('combined.patch',),
    'pressure': ('prefix-case.json', 'upstream-pharynx-balance.csv'),
    'pcm': ('replay-case.json', 'upstream-voice.f32'),
}
UPSTREAM_FILES = ('crates/chimera/src/airway/network.rs', 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/tests/engine.rs',
                  'crates/chimera/tests/airway_adversarial.rs')
MOMENTUM_RECIPE = (
    '        let history = (carried_inertance / dt) * previous_flow;',
    '''        let history = match glottis_rate {
            Some(rate) => (carried_inertance * previous_flow) * rate,
            None => (carried_inertance / dt) * previous_flow,
        };''',
)


def source_inputs(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    snapshot = manifest_path.parent / manifest['source_snapshot']
    entries = {entry['path']: entry['sha256'] for entry in manifest['inputs']}
    copies = [*candidate_sources(), *(WORKSPACE / 'data' / name for name in (
        'cmudict.txt.gz', 'CMUDICT-LICENSE.txt', 'mandarin.txt.gz', 'MANDARIN-PINYIN-LICENSE.txt'))]
    archived = [snapshot / path.relative_to(ROOT) for path in copies]
    if any(sha256(path) != entries.get(str(path.relative_to(snapshot))) for path in archived):
        raise ValueError('先行版のビルド入力を保存ハッシュから再現できません')
    return copies, archived, snapshot


def capture_native(m, paths, copies, snapshot, out, execute):
    with TemporaryDirectory(prefix='glottal-momentum-', dir=out.parent) as temp:
        root = Path(temp)
        source, target = root / 'source', root / 'target'
        stage_candidate(snapshot, copies, source)
        patches = [paths['geometry']['combined.patch'], paths['scaled']['candidate-observation.patch'],
                   paths['scaled']['candidate-inertance-scale.patch']]
        for patch in patches:
            execute(['git', 'apply', '--check', str(patch)], cwd=source)
            execute(['git', 'apply', str(patch)], cwd=source)
        build = ['cargo', 'build', '--release', '--locked', '--offline', '-p', 'vocal-cli',
                 '--manifest-path', str(source / 'Cargo.toml'), '--target-dir', str(target)]
        cli = str(target / 'release/vocal-cli')
        prefix = str(paths['pressure']['prefix-case.json'])
        hashes = {}
        for name in ('control', 'momentum'):
            if name == 'momentum':
                apply_edits(source, {NATIVE_NET: (MOMENTUM_RECIPE,)}, out / 'candidate-momentum-scale.patch')
            execute(build)
            hashes[name] = sha256(Path(cli))
            execute([cli, 'render', prefix, str(out / f'{name}-internal.csv')],
                    stdout=out / f'{name}-branch-values.txt')
        full = str(paths['pcm']['replay-case.json'])
        for block in m['pcm_block_sizes']:
            execute([cli, 'render-pcm', full, str(out / f'momentum-{block}.wav'), '--no-trace', str(block)],
                    stdout=out / f'pcm-{block}-branch-values.txt')
    return hashes


def compare_rows(change, upper, fields, offset):
    return {key: next((i for i, (a, b) in enumerate(zip(change, upper, strict=True), offset)
                      if not same(a[key], b[key])), None) for key in fields}


def substitute_at(row, upper, fields):
    terms = [key for key in fields if not same(row[key], upper[key])]
    for count in range(1, len(terms) + 1):
        matches = []
        for keys in combinations(terms, count):
            values = {**row, **{key: upper[key] for key in keys}}
            reconstructed = solve(Fraction(values['linear']), Fraction(values['drive_pressure']),
                                  Fraction(values['loss']))['flow']
            if same(float(reconstructed), upper['flow']):
                matches.append(keys)
        if matches:
            return matches
    return []


def compare_pcm_runs(m, paths, out):
    rate = m['output_rate_hz']
    frames = m['full_output_frames']
    rendered = [wavfile.read(out / f'momentum-{block}.wav') for block in m['pcm_block_sizes']]
    control = wavfile.read(paths['scaled']['scaled-128.wav'])
    baseline = np.fromfile(paths['pcm']['upstream-voice.f32'], dtype='<f4')
    if any(fs != rate or samples.shape != (frames,) or samples.dtype != np.float32
           for fs, samples in [control, *rendered]):
        raise ValueError('PCMのフレーム数・レート・型が登録と一致しません')
    first, second = (audio for _, audio in rendered)
    evidence = {}
    for name, reference in (('upstream', baseline), ('inertance_scale', control[1])):
        evidence[name] = {**compare_pcm(first, reference, m['pcm_absolute_tolerance']),
                          'different_frames': int(np.count_nonzero(first.view('u4') != reference.view('u4')))}
    checks = {'pcm_partition_invariance': first.tobytes() == second.tobytes(),
              'pcm_within_prior_tolerance': all(p['first_frame_over_tolerance'] is None for p in evidence.values())}
    return checks, evidence


def measure(case, refs, copies, snapshot, out, execute):
    m = case['measurement']
    prefix = json.loads(refs['pressure']['prefix-case.json'].read_text())
    full = json.loads(refs['pcm']['replay-case.json'].read_text())
    fs, rate = m['internal_rate_hz'], m['output_rate_hz']
    event = {'frame': m['gate_open_frame'], 'goal': 1.0}
    end = {'frame': m['gate_close_frame'], 'goal': 0.0}
    if (prefix['fixed_airway']['sample_rate_hz'] != fs or full['fixed_airway']['sample_rate_hz'] != fs
            or prefix['fixed_airway']['sample_count'] != m['prefix_output_frames'] * fs // rate
            or full['fixed_airway']['sample_count'] != m['full_output_frames'] * fs // rate
            or prefix['voice']['output_sample_rate_hz'] != rate or full['voice'] != prefix['voice']
            or prefix['posture'] != full['posture'] or prefix['gate_events'] != [event]
            or full['gate_events'] != [event, end]):
        raise ValueError('保存済み入力のレート・長さ・姿勢・操作時刻が登録範囲外です')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine',
             '--test', 'airway_adversarial'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    build_hashes = capture_native(m, refs, copies, snapshot, out, execute)
    control, attempt = [read_capture(name, m, out) for name in ('control', 'momentum')]
    upstream = read_rows(refs['scaled']['upstream-branch.csv'])
    upstream_pressure = read_rows(refs['pressure']['upstream-pharynx-balance.csv'])
    pressure = read_rows(out / 'momentum-internal.csv')
    start = m['first_internal_sample']
    expected = m['first_control_difference']
    index = expected - start
    earlier = compare_rows(attempt[:index], control[:index], ('flow',), start)
    diffs = compare_rows(attempt, upstream, tuple(column for column in upstream[0] if column != 'internal_sample'), start)
    first_pressure = compare_rows(pressure, upstream_pressure, (PRESSURE,), 0)[PRESSURE]
    checks = {
        'distinct_binaries': build_hashes['control'] != build_hashes['momentum'],
        'control_branch_matches_archive': sha256(out / 'control-branch.csv') == sha256(refs['scaled']['scaled-branch.csv']),
        'control_pressure_matches_archive': sha256(out / 'control-internal.csv')
        == sha256(refs['scaled']['scaled-internal.csv']),
        'control_first_flow_difference_reproduced': compare_rows(control, upstream, ('flow',), start)['flow'] == expected,
        'decreasing_inertance_in_registered_window': all(a['inertance'] < a['previous_inertance'] for a in attempt),
        'earlier_flow_matches_control': earlier['flow'] is None,
        'registered_flow_and_pressure_match_at_8215': (
            same(attempt[index]['flow'], upstream[index]['flow'])
            and same(pressure[expected][PRESSURE], upstream_pressure[expected][PRESSURE])),
        'independent_momentum_and_branch_equation': all(
            same(row['previous_momentum'], float(Fraction(row['previous_inertance']) * Fraction(row['previous_flow'])))
            and all(same(float(value), row[key]) for key, value in replay(row, fs, True).items())
            for row in attempt),
        'independent_pressure_balance_and_clock': all(
            same(row['flow'], pressure[i]['glottal_flow_cm3_s'])
            and same(row['right_pressure'], pressure[i-1][PRESSURE])
            and same(restore_pressure(pressure_terms(pressure[i-1], pressure[i]), fs), pressure[i][PRESSURE])
            for i, row in enumerate(attempt, start)),
    }
    pcm_checks, pcm = compare_pcm_runs(m, refs, out)
    checks.update(pcm_checks)
    residual = None
    if diffs['flow'] is not None:
        i = diffs['flow'] - start
        a, b = attempt[i], upstream[i]
        observed = {key: {'candidate': value, 'upstream': b[key]} for key, value in a.items() if not same(value, b[key])}
        residual = {'sample': diffs['flow'], 'differing_values': observed,
                    'minimum_upstream_substitutions': substitute_at(a, b, ('drive_pressure', 'linear', 'loss'))}
    return {'checks': checks, 'build_sha256': build_hashes, 'initial_flow': attempt[index]['flow'],
            'initial_pressure': pressure[expected][PRESSURE], 'first_pressure_difference': first_pressure,
            'first_difference_by_field': diffs, 'remaining_flow_difference': residual, 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    paths, manifests = {}, {}
    for category, files in FILES.items():
        paths[category] = {}
        for filename in files:
            manifest, path = verified_artifact(*case['references'][category], f'artifacts/{filename}')
            manifests[category] = manifest
            paths[category][filename] = path
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    utilities = [WORKSPACE / 'tools' / name for name in (
        'measure_fixed_voice_centerline.py', 'measure_fixed_voice_glottal_branch.py',
        'measure_fixed_voice_pharynx_onset.py', 'measure_songbird_chirps_volume_rate_propagation_44100.py',
        'measure_uniform_tube.py', 'measure_wasm_fixed.py', 'upstream_baseline.py',
    )]
    inputs = [CASE, Path(__file__), WORKSPACE / 'LICENSE-CHIMERA', *utilities, *archived,
              *manifests.values(), *(path for group in paths.values() for path in group.values())]
    details = {'case_id': case['id'], 'upstream_revision': revision, 'upstream_source_sha256': {
        name: sha256(UPSTREAM / name) for name in UPSTREAM_FILES}}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, run: measure(case, paths, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
