"""初期マニフェストとPCM16の保存済み比較を、固定上流の出力と独立計算に照合する。"""

import argparse
from pathlib import Path
import re
import subprocess
import wave

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_saved_voice_compare import CLI, load, write
from upstream_baseline import UPSTREAM, WORKSPACE, describe, sha256

CASE = WORKSPACE / 'cases/compare-upstream-pcm16.json'
UPPER_CLI = ['cargo', 'run', '--offline', '--locked', '--release', '-p', 'chimera-cli', '--']


def read_pcm16(path, rate, frames):
    # 標準ライブラリでコンテナを読み、16ビットの符号の解釈と換算をRustから独立させる。
    with wave.open(str(path), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getnframes()) != (1, 2, rate, frames):
            raise ValueError(f'{path.name} のPCM16のヘッダーが条件外です')
        pcm = np.frombuffer(source.readframes(frames), dtype='<i2')
    if len(pcm) != frames:
        raise ValueError(f'{path.name} のフレームが欠けています')
    return pcm


def manifest(directory, name, revision, waves):
    return write(directory / 'manifest.json', {'run_id': name, 'upstream_revision': revision,
        'status': 'pass', 'outputs': [describe(directory / wave, directory) for wave in waves]})


def measure(case, run, record, artifacts, execute):
    limits, expected, source = (case[key] for key in ('measurement', 'expected', 'input'))
    rate, frames, divisor = (limits[key] for key in ('sample_rate_hz', 'output_frames', 'independent_decode_divisor'))
    archive = run / source['reference_wave']
    revision = case['upstream_revision']
    original_manifest_hash = sha256(run / 'manifest.json')
    original_wave_hash = sha256(archive)
    actual = read_pcm16(archive, rate, frames)
    decoded = (actual.astype(float) / divisor).astype(np.float32)
    execute(['cargo', 'build', '--offline', '--locked', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'test', '--offline', '--locked', '-p', 'chimera-cli', '--test', 'cli',
             'render_speech_writes_a_sounding_wav_of_the_planned_length'], cwd=UPSTREAM,
            stdout=artifacts / 'upstream-wav-test.log')

    generated = artifacts / 'generated'
    generated.mkdir()
    pcm = generated / 'vowels-pcm16.wav'
    raw = generated / 'vowels-original-float32.wav'
    wavfile.write(generated / 'vowels-decoded-float32.wav', rate, decoded)
    for path, switches in ((pcm, []), (raw, ['--float'])):
        execute([*UPPER_CLI, 'render', 'vowels', 'male', str(path), *switches], cwd=UPSTREAM,
                stdout=artifacts / (path.stem + '.log'))
    current_manifest = manifest(generated, 'generated-vowel-controls', revision,
                                ['vowels-pcm16.wav', 'vowels-original-float32.wav', 'vowels-decoded-float32.wav'])

    def compare(name, left, right, spec, *, cwd=WORKSPACE, reject=False):
        result = artifacts / f'{name}.json'
        status = 0
        try:
            execute([str(CLI), 'compare', str(left), str(right), str(spec)], cwd=cwd, stdout=result)
        except subprocess.CalledProcessError as error:
            if not reject:
                raise
            status = error.returncode
        return status, load(result) if result.stat().st_size else None

    def derived(name, candidate_name, **settings):
        return write(artifacts / f'{name}-case.json', case | {
            'input': source | {'candidate_wave': candidate_name},
            'measurement': limits | settings,
        })

    _, same = compare('archive-self', run, run / 'manifest.json', CASE)
    _, relocated = compare('archive-from-tmp', run / 'manifest.json', run, CASE, cwd=Path('/tmp'))
    _, repeated = compare('archive-vs-rerendered', run, current_manifest,
                          derived('fresh-pcm16', pcm.name))
    exact_case = derived('independent-decode', 'vowels-decoded-float32.wav', require_pcm_bit_exact=False)
    _, exact = compare('archive-vs-decoded', run, current_manifest, exact_case)
    raw_case = derived('raw-float', raw.name, require_pcm_bit_exact=False,
                       pcm_absolute_tolerance=expected['quantized_vs_engine_pcm_absolute_tolerance'])
    _, quantized = compare('archive-vs-raw-float', run, current_manifest, raw_case)
    bit_status, bit_report = compare('mixed-exactness', run, current_manifest,
                                    derived('mixed-exactness', 'vowels-decoded-float32.wav'), reject=True)

    small = artifacts / 'endpoints'
    small.mkdir()
    values = np.asarray(expected['conversion_endpoints'], dtype='<i2')
    wavfile.write(small / 'endpoints.wav', rate, values)
    wavfile.write(small / 'endpoints-float.wav', rate, (values.astype(float) / divisor).astype(np.float32))
    small_manifest = manifest(small, 'boundary-values', revision, ['endpoints.wav', 'endpoints-float.wav'])
    small_spec = write(small / 'case.json', case | {
        'input': {'reference_wave': 'endpoints.wav', 'candidate_wave': 'endpoints-float.wav'},
        'measurement': limits | {'require_pcm_bit_exact': False, 'output_frames': len(values),
                                   'output_frame_range': [0, len(values)]},
    })
    _, boundary = compare('signed-endpoints', small, small_manifest, small_spec)
    original_entry = next(entry for item in record['cases'] for entry in item['outputs']
                          if entry['path'] == source['reference_wave'])
    duplicate = write(artifacts / 'duplicate-manifest.json', {
        'run_id': 'ambiguous-path', 'upstream_revision': revision, 'cases': [
            {'id': ident, 'status': 'pass', 'outputs': [original_entry]} for ident in ('first', 'second')],
    })
    duplicate_status, duplicate_report = compare('duplicate-path', duplicate, run, CASE, reject=True)

    render_rate, unquantized = wavfile.read(raw)
    if render_rate != rate or unquantized.shape != (frames,) or unquantized.dtype != np.float32:
        raise ValueError('固定上流のfloat32再レンダーの形式が一致しません')
    clipped = np.clip(unquantized.astype(float), -1, 1)
    scaled = clipped * 32767
    lower = np.floor(scaled)
    predicted = (lower + (scaled - lower >= .5)).astype(np.int16)
    delta = abs(unquantized.astype(float) - decoded)
    first = np.flatnonzero(delta)
    maximum = int(np.argmax(delta))
    oracle = {'first_difference_frame': int(first[0]) if first.size else None,
              'maximum_difference_frame': maximum, 'maximum_absolute_error': float(delta[maximum]),
              'raw_peak': float(abs(unquantized).max()), 'decoded_peak': float(abs(decoded).max()),
              'raw_value_at_maximum': float(unquantized[maximum]), 'decoded_value_at_maximum': float(decoded[maximum]),
              'pcm16_at_maximum': int(actual[maximum]),
              'rounding_mismatch_frames': int(np.count_nonzero(actual != predicted))}
    log = (artifacts / 'cargo.log').read_text()

    def exact_values(report):
        return report['status'] == 'pass' and report['pcm']['maximum_absolute_error'] == 0.0             and report['pcm']['first_numeric_difference_frame'] is None

    checks = {
        'archive_manifest_and_wave_unchanged': original_wave_hash == sha256(archive) == expected['archived_wave_sha256']
            and original_manifest_hash == sha256(run / 'manifest.json'),
        'legacy_case_provenance_and_encoding': all(side['recorded_case_id'] == expected['archived_case_id']
            and side['recorded_status'] == 'pass' and side['sample_format'] == 'pcm16'
            and side['wave']['sha256'] == original_wave_hash for side in (same['reference'], same['candidate'])),
        'same_archived_pcm16_bits': exact_values(same) and same['pcm']['different_bits'] == expected['same_format_different_bits'],
        'fresh_fixed_pcm16_matches_archive_bits': exact_values(repeated) and repeated['pcm']['different_bits'] == 0
            and sha256(pcm) == original_wave_hash,
        'normalized_pcm16_equals_independent_float32': exact_values(exact) and exact['candidate']['sample_format'] == 'float32'
            and exact['pcm']['different_bits'] is expected['mixed_format_different_bits']
            and exact['pcm']['first_bit_difference_frame'] is None,
        'signed_conversion_endpoints': exact_values(boundary) and boundary['pcm']['different_bits'] is None
            and int(actual.min()) == expected['minimum_pcm16'] and int(actual.max()) == expected['maximum_pcm16'],
        'float32_render_quantizes_to_archived_integers': oracle['rounding_mismatch_frames'] == 0,
        'quantization_bound_and_observed_first_difference': quantized['status'] == 'pass'
            and quantized['pcm']['first_numeric_difference_frame'] == oracle['first_difference_frame']
            and quantized['pcm']['maximum_absolute_error'] == oracle['maximum_absolute_error']
            and np.all(delta <= np.abs(unquantized.astype(float)-clipped) + (0.5 + abs(clipped)) / divisor),
        'mixed_format_bit_exactness_rejected': bit_status == 1 and bit_report is None
            and 'ビット一致の比較には同じ保存形式のWAVを指定してください' in log,
        'duplicate_legacy_path_rejected': duplicate_status == 1 and duplicate_report is None
            and 'マニフェストの成果パスが重複しています' in log,
        'relocated_report_is_byte_identical': relocated == same and (artifacts / 'archive-self.json').read_bytes()
            == (artifacts / 'archive-from-tmp.json').read_bytes(),
    }
    return {'checks': {name: bool(value) for name, value in checks.items()},
            'archive': same, 'independent_decode': exact['pcm'], 'quantized_vs_float': quantized['pcm'],
            'independent_quantization': oracle, 'archive_manifest_sha256': original_manifest_hash,
            'input_validation_exit_codes': {'mixed_exactness': bit_status, 'duplicate_path': duplicate_status}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = load(CASE)
    run = WORKSPACE / 'runs' / case['input']['run']
    archive = run / 'manifest.json'
    record = load(archive)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or record['upstream_revision'] != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流の取得状態と保存済み基準を確認してください')
    upstream = [UPSTREAM / name for name in ('crates/chimera-cli/src/main.rs','crates/chimera-cli/src/render.rs',
        'crates/chimera-cli/src/wav.rs','crates/chimera-cli/src/compare.rs','crates/chimera-cli/tests/cli.rs',
        'crates/chimera/src/math.rs')]
    sources = [CASE, Path(__file__), archive, run / case['input']['reference_wave'], *upstream,
               *(WORKSPACE / 'tools' / name for name in ('measure_saved_voice_compare.py','measure_uniform_tube.py','upstream_baseline.py')),
               *shared.candidate_sources()]
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return shared.record_measurement(args.run_id, CASE, sources, details,
        lambda artifacts, execute: measure(case, run, record, artifacts, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
