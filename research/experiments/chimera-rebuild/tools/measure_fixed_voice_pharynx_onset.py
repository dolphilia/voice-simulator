"""通常CLIと固定上流で、発声開始時の咽頭セル0の圧力収支を照合する。"""

import argparse
import csv
import difflib
from fractions import Fraction
from itertools import combinations, islice
import json
import math
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharynx-onset-48000.json'
PROBE = WORKSPACE / 'tools/upstream_vowel_voice_probe.rs'
VOICE = 'crates/chimera/src/voice/human_voice.rs'
NETWORK = 'crates/chimera/src/airway/network.rs'
PRESSURE = 'pressure_supra_dyn_cm2'
BALANCE = ('pharynx_compliance_cgs', 'pharynx_volume_source_cm3_s', 'pharynx_outflow_cm3_s',
           'glottal_flow_cm3_s', 'pharynx_wall_flow_cm3_s')
ARCHIVE_FILES = ('replay-case.json', 'native-trace.csv', 'upstream-trace.csv', 'block-128.wav', 'upstream-voice.f32')


def build_reference(revision, artifacts, execute):
    edits = {
        VOICE: [
            ('    pub airway: HumanAirway,\n', '    pub research_pharynx_balance: Option<Vec<[f64; 10]>>,\n'),
            ('            sub: 0,\n', '            research_pharynx_balance: None,\n'),
            ('                let y = net.step();\n', """                if let Some(rows) = &mut self.research_pharynx_balance {
                    let [volume_flow, compliance] = net.research_pharynx_pressure_terms(supra);
                    rows.push([
                        net.p[supra], a, net.u[gp], net.p[supra + 1],
                        net.u[self.airway.pharynx.branch(0)], net.wall_u[supra], volume_flow,
                        net.area[supra], net.dx[supra], compliance,
                    ]);
                }
"""),
        ],
        NETWORK: [('    /// Advance one internal sample. Returns radiated pressure (arbitrary units ∝ dU_rad/dt).\n',
                   """    pub fn research_pharynx_pressure_terms(&self, node: usize) -> [f64; 2] {
        [self.vol_src2[node], self.vol[node] / RHO_C2]
    }

""")],
    }
    with TemporaryDirectory(prefix='fixed-voice-upstream-', dir=artifacts) as directory:
        code = Path(directory)
        tar = code / 'source.tar'
        execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(code)])
        patch = []
        for name, changes in edits.items():
            path = code / name
            before = after = path.read_text()
            for anchor, addition in changes:
                if after.count(anchor) != 1:
                    raise ValueError(f'固定上流の計測位置を一意に特定できません ({name})')
                # 更新前の説明コメントと関数宣言は隣接させたままにする。
                replacement = addition + anchor if name == NETWORK else anchor + addition
                after = after.replace(anchor, replacement)
            patch.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                              fromfile=f'a/{name}', tofile=f'b/{name}'))
            path.write_text(after)
        (artifacts / 'upstream-pharynx-balance.patch').write_text(''.join(patch))
        return shared.build_upstream_probe(PROBE, artifacts, execute, upstream=code,
                                           rustc_args=('--cfg', 'chimera_pharynx_balance_probe'))


def read_rows(path, limit=None):
    with path.open(newline='') as stream:
        rows = [{key: float(value) for key, value in row.items()}
                for row in islice(csv.DictReader(stream), limit)]
    if not rows or any(not math.isfinite(value) for row in rows for value in row.values()):
        raise ValueError(f'観測値が空、または非有限です ({path.name})')
    return rows


def bits(value):
    return struct.pack('<d', value)


def same_rows(left, right):
    return len(left) == len(right) and all(
        all(key in a and bits(a[key]) == bits(value) for key, value in b.items())
        for a, b in zip(left, right, strict=True))


def pressure_terms(previous, current):
    return {'previous': previous[PRESSURE], **{name: current[name] for name in BALANCE}}


def restore_pressure(terms, fs):
    # 実装と独立に有理数で演算し、演算ごとにf64へ丸める。
    previous, compliance, volume, outflow, glottis, wall = (
        Fraction(terms[key]) for key in ('previous', *BALANCE)
    )
    dt = Fraction(float(Fraction(1, fs)))
    toward_glottis = Fraction(float(volume - outflow))
    inflow = Fraction(float(toward_glottis + glottis))
    remaining = Fraction(float(inflow - wall))
    scale = Fraction(float(dt / compliance))
    increment = Fraction(float(scale * remaining))
    return float(previous + increment)


def compare_pressure(native, upstream, m):
    start, end, rate = (m[k] for k in ('window_first_sample', 'window_end_exclusive', 'internal_rate_hz'))
    index = range(start, end)
    differences = {key: next((i for i in index if bits(native[i][key]) != bits(upstream[i][key])), None)
                   for key in upstream[0] if key != 'internal_sample'}
    mismatch = differences[PRESSURE]
    checks = {
        'registered_first_pressure_difference': mismatch in m['predicted_first_pressure_samples']
        and all(bits(native[i][PRESSURE]) == bits(upstream[i][PRESSURE]) for i in range(start)),
    }
    for name, rows in (('candidate', native), ('upstream', upstream)):
        checks[f'{name}_independent_pressure_update'] = all(
            bits(restore_pressure(pressure_terms(rows[i-1], rows[i]), rate)) == bits(rows[i][PRESSURE])
            for i in index)
        checks[f'{name}_geometry_sets_compliance'] = all(
            bits((max(rows[i]['pharynx_area_cm2'], 0.02) * rows[i]['pharynx_length_cm']) / (0.00114 * 35000.0 * 35000.0))
            == bits(rows[i]['pharynx_compliance_cgs']) for i in index)
    first = None
    if mismatch is not None:
        actual = pressure_terms(native[mismatch-1], native[mismatch])
        reference = pressure_terms(upstream[mismatch-1], upstream[mismatch])
        different = [name for name in actual if bits(actual[name]) != bits(reference[name])]
        substitutions = []
        for size in range(1, len(different) + 1):
            substitutions = [group for group in combinations(different, size) if
                             bits(restore_pressure({**actual, **{key: reference[key] for key in group}}, rate))
                             == bits(upstream[mismatch][PRESSURE])]
            if substitutions:
                break
        checks['recorded_terms_explain_first_difference'] = bool(substitutions)
        first = {'sample': mismatch, 'candidate': native[mismatch][PRESSURE],
                 'upstream': upstream[mismatch][PRESSURE],
                 'terms': {name: {'candidate': actual[name], 'upstream': reference[name]} for name in different},
                 'minimal_upstream_substitutions': substitutions}
    return checks, {'window': [start, end], 'first_difference_by_field': differences, 'initial_pressure_difference': first}


def measure(case, folder, artifacts, execute):
    m = case['measurement']
    frames, internal, rate = (m[k] for k in ('prefix_output_frames', 'internal_rate_hz', 'output_rate_hz'))
    factor = internal // rate
    count = frames * factor
    source = json.loads((folder / 'replay-case.json').read_text())
    if (source['fixed_airway']['sample_rate_hz'] != internal or source['voice']['output_sample_rate_hz'] != rate
            or source['gate_events'][0] != {'frame': m['gate_open_frame'], 'goal': 1.0}):
        raise ValueError('保存した描画のレートまたは発声開始時刻が異なります')
    source['fixed_airway']['sample_count'] = count
    source['gate_events'] = [event for event in source['gate_events'] if event['frame'] < frames]
    source['fixed_voice_probe'] = {'internal_trace': True, 'pharynx_entry_balance': True}
    input_path = artifacts / 'prefix-case.json'
    input_path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + '\n')
    commands = artifacts / 'gate-events.txt'
    commands.write_text(''.join(f"{event['frame']} {event['goal']}\n" for event in source['gate_events']))
    trace_path = artifacts / 'candidate-pharynx-balance.csv'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render', str(input_path), str(trace_path)])
    blocks = pcm.render_blocks(input_path, {'block_frames': m['pcm_block_sizes']}, artifacts, execute)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = build_reference(case['upstream_revision'], artifacts, execute)
    arguments = [m['ipa'], internal, rate, frames, *(source['voice'][k] for k in
                 ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), artifacts, commands]
    execute([str(probe), 'render', *map(str, arguments)], cwd=UPSTREAM)
    native = read_rows(trace_path)
    upper = read_rows(artifacts / 'upstream-pharynx-balance.csv')
    upper_frames = read_rows(artifacts / 'upstream-trace.csv')
    baseline_native = read_rows(folder / 'native-trace.csv', frames)
    baseline_upper = read_rows(folder / 'upstream-trace.csv', frames)
    selected = list(range(factor - 1, count, factor))
    if any([row['internal_sample'] for row in track] != list(range(count)) for track in (native, upper)):
        raise ValueError('内部サンプルの採取区間が登録と異なります')
    first_block, second_block = m['pcm_block_sizes']
    rate_a, audio = wavfile.read(blocks[first_block][0])
    rate_ref, baseline_audio = wavfile.read(folder / 'block-128.wav')
    upper_audio = np.fromfile(artifacts / 'upstream-voice.f32', dtype='<f4')
    upper_baseline = np.fromfile(folder / 'upstream-voice.f32', dtype='<f4', count=frames)
    comparison = wasm.compare_pcm(audio, upper_audio, m['pcm_upstream_absolute_tolerance'])
    checks, result = compare_pressure(native, upper, m)
    checks.update({
        'candidate_observation_prefix': same_rows(
            [{**native[i], 'frame': frame} for frame, i in enumerate(selected)], baseline_native),
        'upstream_observation_prefix': same_rows(upper_frames, baseline_upper)
        and all(all(bits(upper_frames[n][key]) == bits(upper[i][key])
                    for key in ('internal_sample', PRESSURE, 'glottal_area_cm2', 'glottal_flow_cm3_s'))
                for n, i in enumerate(selected)),
        'candidate_pcm_prefix': rate == rate_a == rate_ref and audio.tobytes() == baseline_audio[:frames].tobytes(),
        'upstream_pcm_prefix': upper_audio.tobytes() == upper_baseline.tobytes(),
        'cli_partition_invariance': all(sha256(left) == sha256(right)
                                        for left, right in zip(blocks[first_block], blocks[second_block], strict=True)),
        'upstream_pcm_tolerance': comparison['first_frame_over_tolerance'] is None,
        'archived_pressure_offset': next((i for i in selected if bits(native[i][PRESSURE]) != bits(upper[i][PRESSURE])),
                                         None) == m['first_archived_pressure_sample'],
    })
    return {'checks': checks, 'prefix_frames': frames, 'pcm_upstream': comparison, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference = WORKSPACE / 'runs' / case['reference_run']
    manifest = reference / 'manifest.json'
    saved = json.loads(manifest.read_text())
    entries = {entry['path']: entry['sha256'] for entry in saved['outputs']}
    indexed = [f'artifacts/{name}' for name in ARCHIVE_FILES]
    if (saved['status'] != 'pass' or sha256(manifest) != case['reference_manifest_sha256']
            or any(sha256(reference / name) != entries.get(name) for name in indexed)):
        parser.error('保存済みの根拠実行とその成果のハッシュが不一致です')
    inputs = [CASE, manifest, *(reference / name for name in indexed), Path(__file__).resolve(), PROBE,
              *(Path(module.__file__) for module in (shared, pcm, wasm)), *shared.candidate_sources()]
    details = {'case_id': case['id'], 'upstream_revision': revision,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in (VOICE, NETWORK)}}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
                                     lambda out, run: measure(case, reference / 'artifacts', out, run),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
