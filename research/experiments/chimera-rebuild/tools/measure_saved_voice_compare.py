"""保存済みの手動MIDI実行から、Rustの比較CLIと独立した計算を照合する。"""

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, describe, sha256

CASE = WORKSPACE / 'cases/compare-saved-voice-run.json'
CLI_SOURCES = WORKSPACE / 'crates/vocal-cli/src'
CLI = WORKSPACE / 'target/release/vocal-cli'


def load(path):
    return json.loads(path.read_text())


def write(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
    return path


def independently_measure(run, case):
    measurement = case['measurement']
    start, stop = measurement['output_frame_range']
    start_sample, step = measurement['internal_samples_per_output_frame'] - 1, measurement['internal_samples_per_output_frame']
    input_ = case['input']
    _, ref = wavfile.read(run / input_['reference_wave'])
    _, cand = wavfile.read(run / input_['candidate_wave'])
    ref, cand = ref[start:stop], cand[start:stop]
    difference = abs(cand.astype(float) - ref)
    first = np.flatnonzero(cand.view(np.uint32) != ref.view(np.uint32))
    pcm = {'different_bits': int(first.size),
           'first_bit_difference_frame': start + int(first[0]) if first.size else None,
           'maximum_absolute_error': float(difference.max())}

    columns = ('internal_sample', *measurement['observation_fields'])
    values = []
    for key in ('reference_trace', 'candidate_trace'):
        raw = np.genfromtxt(run / input_[key], delimiter=',', names=True, usecols=columns)
        coordinates = raw['internal_sample']
        selected = (coordinates % step == start_sample) & (coordinates // step >= start) & (coordinates // step < stop)
        chosen = raw[selected]
        if not np.array_equal(chosen['internal_sample'], np.arange(start, stop) * step + start_sample):
            raise ValueError('独立計算の観測位置が揃っていません')
        values.append(chosen)
    reference, candidate = values
    state = {}
    for field in columns[1:]:
        delta = abs(candidate[field] - reference[field])
        indexes = np.flatnonzero(delta)
        first_sample = int(reference['internal_sample'][indexes[0]]) if indexes.size else None
        peak = float(abs(reference[field]).max())
        maximum = float(delta.max())
        state[field] = {'reference_peak': peak, 'max_absolute_difference': maximum,
                        'max_abs_diff_over_reference_peak': maximum / peak if peak else (0.0 if maximum == 0 else None),
                        'first_internal_sample': first_sample}
    return {'pcm': pcm, 'states': state}


def matches(result, independent):
    return all(result['pcm'][key] == value for key, value in independent['pcm'].items()) and all(
        all(result['states'][field][key] == value for key, value in metrics.items() if key != 'first_internal_sample')
        and (result['states'][field]['first_difference'] or {}).get('internal_sample') == metrics['first_internal_sample']
        for field, metrics in independent['states'].items())


def synthetic_pair(parent, revision):
    for name, samples, trace in (
        ('reference', [0., .125, .25, .5], 'internal_sample,flow\n1,0\n3,0\n5,0\n7,0\n'),
        ('candidate', [-0., .125, .25, .5], 'frame,flow\n0,0\n1,0\n2,1\n3,0\n'),
    ):
        directory = parent / name
        directory.mkdir(parents=True)
        wavfile.write(directory / 'small.wav', 48000, np.asarray(samples, dtype=np.float32))
        (directory / 'small.csv').write_text(trace)
        write(directory / 'manifest.json', {'run_id': name, 'upstream_revision': revision, 'status': 'pass',
              'outputs': [describe(directory / file, directory) for file in ('small.wav', 'small.csv')]})
    case = {'id': 'saved-compare-coordinate-fixture', 'revision': 1, 'upstream_revision': revision,
            'input': {'reference_wave': 'small.wav', 'candidate_wave': 'small.wav',
                      'reference_trace': 'small.csv', 'candidate_trace': 'small.csv'},
            'measurement': {'sample_rate_hz': 48000, 'output_frames': 4, 'internal_samples_per_output_frame': 2,
                            'pcm_absolute_tolerance': 0, 'state_peak_relative_tolerance': 1e-8,
                            'require_pcm_bit_exact': True, 'observation_fields': ['flow'],
                            'reference_trace_coordinate': 'internal_sample', 'candidate_trace_coordinate': 'frame'}}
    return parent / 'reference', parent / 'candidate', case


def measure(case, run, artifacts, execute):
    execute(['cargo', 'build', '--offline', '--locked', '--release', '-p', 'vocal-cli'])

    def compare(label, reference, candidate, spec, *, cwd=WORKSPACE, reject=False):
        destination = artifacts / f'{label}.json'
        status = 0
        try:
            execute([str(CLI), 'compare', str(reference), str(candidate), str(spec)], cwd=cwd, stdout=destination)
        except subprocess.CalledProcessError as error:
            if not reject:
                raise
            status = error.returncode
        value = load(destination) if destination.stat().st_size else None
        return status, value

    _, result = compare('full', run, run / 'manifest.json', CASE)
    _, second = compare('from-tmp', run / 'manifest.json', run, CASE, cwd=Path('/tmp'))
    window = deepcopy(case)
    frame_range = case['expected']['window_control']
    window['measurement']['output_frame_range'] = frame_range
    _, subset = compare('window', run, run, write(artifacts / 'window-case.json', window))

    exact = deepcopy(case)
    exact['input']['reference_wave'] = exact['measurement']['same_pcm_control']
    exact['input'].pop('reference_trace')
    exact['input'].pop('candidate_trace')
    exact['measurement']['observation_fields'] = []
    exact['measurement']['require_pcm_bit_exact'] = True
    _, bit_exact = compare('exact', run, run, write(artifacts / 'exact-case.json', exact))

    reference, candidate, synthetic = synthetic_pair(artifacts / 'small-fixture', case['upstream_revision'])
    synthetic_path = write(artifacts / 'small-fixture' / 'case.json', synthetic)
    mismatch_status, mismatch = compare('zero-and-sign', reference, candidate, synthetic_path, reject=True)
    measurement = deepcopy(synthetic['measurement'])
    measurement['output_frames'] = 3
    bad_length = write(artifacts / 'bad-length-case.json', synthetic | {'measurement': measurement})
    length_status, length_report = compare('bad-length', reference, candidate, bad_length, reject=True)

    # 各異常は別の実行フォルダに作り、元の計測や他の対照は更新しない。
    gap = artifacts / 'small-fixture' / 'gap'
    shutil.copytree(candidate, gap)
    trace = gap / 'small.csv'
    trace.write_text('frame,flow\n0,0\n1,0\n3,0\n')
    gap_manifest = load(gap / 'manifest.json')
    gap_manifest['outputs'][1] = describe(trace, gap)
    write(gap / 'manifest.json', gap_manifest)
    gap_status, gap_report = compare('gap', reference, gap, synthetic_path, reject=True)

    changed = artifacts / 'small-fixture' / 'changed'
    shutil.copytree(candidate, changed)
    trace = changed / 'small.csv'
    trace.write_text(trace.read_text().replace('2,1', '2,2'))
    checksum_status, checksum_report = compare('changed', reference, changed, synthetic_path, reject=True)

    restricted = synthetic | {'measurement': synthetic['measurement'] | {'output_frame_range': [1, 2]}}
    restricted_path = write(artifacts / 'small-fixture' / 'restricted-case.json', restricted)
    _, aligned = compare('aligned-different-runs', reference, candidate, restricted_path)
    outside_status, outside_report = compare(
        'changed-outside-interval', reference, changed, restricted_path, reject=True)

    known = case['expected']
    oracle = independently_measure(run, case)
    oracle_window = independently_measure(run, window)
    recorded = load(run / 'summary.json')
    log = (artifacts / 'cargo.log').read_text()
    mismatched_flow = mismatch['states']['flow']
    checks = {
        'all_input_hashes_verified_and_previous_pcm_reproduced': result['status'] == 'pass'
            and result['pcm']['different_bits'] == known['pcm_different_bits'] == recorded['upstream_pcm_different_bits']
            and result['pcm']['first_bit_difference_frame'] == known['first_pcm_bit_difference_frame']
            and result['pcm']['maximum_absolute_error'] == known['pcm_max_abs_diff'],
        'previous_state_metrics_reproduced': all(
            all(result['states'][name][key] == value for key, value in expected.items())
            for name, expected in known['full_trace_values'].items()),
        'independent_full_comparison': matches(result, oracle),
        'independent_interval_and_coordinate_alignment': subset['output_frame_range'] == frame_range
            and subset['status'] == 'pass' and matches(subset, oracle_window)
            and subset['states']['radiation_derivative_cm3_s2']['reference_peak']
                < result['states']['radiation_derivative_cm3_s2']['reference_peak'],
        'bit_exact_browser_and_cli_control': bit_exact['status'] == 'pass'
            and bit_exact['pcm']['different_bits'] == known['same_pcm_different_bits'] and not bit_exact['states'],
        'location_independent_report': second == result
            and (artifacts / 'from-tmp.json').read_bytes() == (artifacts / 'full.json').read_bytes(),
        'signed_zero_and_zero_reference_peak_fail_with_report': mismatch_status == 1 and mismatch['status'] == 'fail'
            and mismatch['pcm']['different_bits'] == 1 and mismatch['pcm']['maximum_absolute_error'] == 0
            and mismatch['pcm']['first_bit_difference_frame'] == 0 and not mismatch['pcm']['status']
            and mismatched_flow['reference_peak'] == 0 and mismatched_flow['first_frame_over_tolerance'] == 2
            and mismatched_flow['first_difference']['internal_sample'] == 5
            and mismatched_flow['max_abs_diff_over_reference_peak'] is None,
        'invalid_wave_length_rejected': length_status == 1 and length_report is None
            and 'WAVのレートまたは長さが比較条件と異なります' in log,
        'missing_coordinate_rejected': gap_status == 1 and gap_report is None and '観測座標 2 がありません' in log,
        'same_size_tampering_rejected': checksum_status == 1 and checksum_report is None
            and 'のサイズまたはSHA-256が記録と異なります' in log,
        'align_different_run_ids_and_coordinate_systems': aligned['status'] == 'pass'
            and aligned['reference']['run_id'] == 'reference' and aligned['candidate']['run_id'] == 'candidate'
            and aligned['output_frame_range'] == [1, 2] and aligned['pcm']['different_bits'] == 0
            and aligned['states']['flow']['first_difference'] is None,
        'same_size_tampering_outside_interval_rejected': outside_status == 1 and outside_report is None,

    }
    return {'checks': checks, 'pcm': result['pcm'], 'states': result['states'], 'interval': subset['output_frame_range'],
            'window_metrics': subset, 'independent': oracle, 'independent_window': oracle_window,
            'input_validation_status': {'gap': gap_status, 'length': length_status, 'checksum': checksum_status,
                                        'checksum_outside_interval': outside_status,
                                        'outside_tolerance': mismatch_status},
            'reference_manifest_sha256': sha256(run / 'manifest.json')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = load(CASE)
    ref = WORKSPACE / 'runs' / case['input']['run']
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or load(ref / 'manifest.json')['upstream_revision'] != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流と保存済み基準のリビジョンを確認してください')
    files = [ref / 'manifest.json', ref / 'summary.json',
             *(ref / value for key, value in case['input'].items() if key.endswith(('_wave', '_trace'))),
             ref / case['measurement']['same_pcm_control']]
    scripts = [WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'upstream_baseline.py')]
    sources = [CASE, Path(__file__), *files, *scripts, *shared.candidate_sources()]
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return shared.record_measurement(args.run_id, CASE, sources, details,
        lambda out, execute: measure(case, ref, out, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
