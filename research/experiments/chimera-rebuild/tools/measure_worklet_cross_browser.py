"""通常の96 kHz固定発声をFirefox、Chromium、固定上流、CLIで照合する。"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_worklet_release_alignment as release
import measure_worklet_realtime as realtime


CASE = release.WORKSPACE / 'cases/worklet-realtime-cross-browser-96000.json'


def sound_rows(report):
    # Contextの絶対位置と処理時計を除き、累計フレームと音響観測を同じ表現にする。
    return np.ascontiguousarray(np.asarray(report['observations'], dtype='<f8')[:, 4:])


def compare_observations(report, archive):
    current, expected = sound_rows(report), sound_rows(archive)
    if report['columns'][4:] != archive['columns'][4:] or current.shape != expected.shape:
        raise ValueError('保存Chromiumとの観測列または行数が一致しません')
    differences = np.argwhere(current.view('<u8') != expected.view('<u8'))
    first = None
    if len(differences):
        row, column = differences[0]
        first = {'quantum_index': int(row), 'field': report['columns'][int(column) + 4],
                 'current': float(current[row, column]), 'archive': float(expected[row, column])}
    return {
        'sound_observations_sha256': hashlib.sha256(current).hexdigest(),
        'first_observation_bit_difference': first,
    }


def clock_evidence(report):
    values = np.asarray(report['observations'], dtype=float)
    processing = values[:, 2]
    gaps = np.diff(values[:, 3])
    ticks = np.rint(np.r_[processing, gaps] * 1000).astype('i8')
    observed = int(np.gcd.reduce(ticks))
    return {'observed_time_step_ms': observed / 1000 if observed else None,
            'minimum_positive_process_ms': min((float(v) for v in processing if v > 0), default=None),
            'process_histogram_ms': [[ms, int(count)] for ms, count in sorted(Counter(map(float, processing)).items())],
            'startup_clock_discontinuities': report['startupDiscontinuities'],
            'base_latency_seconds': report.get('baseLatencySeconds'),
            'output_latency_seconds': report.get('outputLatencySeconds')}


def measure(study, original, source, archive, artifacts, execute, bun):
    spec = original['measurement']
    settings = (spec['pre_roll_frames'], spec['expected_stop_frame'], spec['expected_output_frames'])
    execute([*bun, 'run', 'build'], cwd=release.WEB, stdout=artifacts / 'browser-build.log')
    wasm = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(release.WORKSPACE / release.wasm.WASM, wasm)
    reference_rate, archive_audio = wavfile.read(archive['artifacts/browser.wav'])
    archive_report = realtime.wasm.read_json(archive['artifacts/browser.json'])
    same_binary = release.sha256(wasm) == release.sha256(archive['artifacts/vocal_wasm.wasm'])
    checks = {'same_wasm_as_archived_chromium': same_binary}
    trials = []
    with TemporaryDirectory(prefix='native-and-upstream-', dir=artifacts) as td:
        renderer = Path(td)
        replay = realtime.render_replay(source, original, renderer, execute, *settings)
        _, blocks, _, _, _, states = replay
        for filename in ('replay-case.json', 'native-inspect.json', 'upstream-engine.log', 'upstream-build.jsonl'):
            shutil.copyfile(renderer / filename, artifacts / filename)
        shutil.copyfile(blocks[spec['expected_quantum_frames']][0], artifacts / 'cli-128.wav')
        shutil.copyfile(renderer / 'upstream-voice.f32', artifacts / 'upstream-voice.f32')
        points = np.arange(spec['expected_quantum_frames'] - 1, settings[2], spec['expected_quantum_frames'])
        fields = spec['observed_fields']
        np.savez_compressed(artifacts / 'reference-observations.npz', output_frame=points, fields=fields,
                            cli=np.column_stack([states[0][name][points] for name in fields]),
                            upstream=np.column_stack([states[1][name][points] for name in fields]))
        for round_number, order in enumerate(study['measurement']['browser_order'], start=1):
            for engine in order:
                name = f'{round_number}-{engine}'
                folder = artifacts / name
                folder.mkdir()
                capture_case = folder / 'capture-case.json'
                case = {**original, 'measurement': {**spec, 'browser_engine': engine}}
                capture_case.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
                log = folder / 'browser-command.log'
                result = {'trial': name, 'round': round_number, 'engine': engine}
                try:
                    execute(['node', str(release.CAPTURE), str(folder), str(capture_case)], stdout=log)
                    normal = realtime.compare_capture(source, original, folder, execute, wasm, replay=replay)
                    report = realtime.wasm.read_json(folder / 'browser.json')
                    browser_run = realtime.wasm.read_json(folder / 'browser-run.json')
                    actual_rate, audio = wavfile.read(folder / 'browser.wav')
                    pcm = realtime.wasm.compare_pcm(audio, archive_audio, 0)
                    observations = compare_observations(report, archive_report)
                    result.update(normal)
                    result.update({'archived_chromium_pcm': pcm, **observations, 'clock_evidence': clock_evidence(report),
                                   'pcm_sha256': hashlib.sha256(audio.astype('<f4', copy=False)).hexdigest()})
                    local = {**normal['checks'], 'requested_browser_launched': browser_run['engine'] == engine,
                             'archived_chromium_pcm_bit_equal': actual_rate == reference_rate
                             and pcm['first_bit_difference_frame'] is None,
                             'archived_chromium_sound_states_bit_equal': observations['first_observation_bit_difference'] is None}
                except (OSError, ValueError, subprocess.CalledProcessError) as error:
                    result['error'] = str(error)
                    local = {'capture_and_comparison_completed': False}
                checks.update({f'{name}/{key}': value for key, value in local.items()})
                trials.append(result)
                for filename in ('browser.wav', 'browser.json'):
                    path = folder / filename
                    if path.is_file():
                        release.stored.compress(path)
    for value in ('pcm_sha256', 'sound_observations_sha256'):
        values = {row.get(value) for row in trials}
        checks[f'all_current_{value}_equal'] = len(values) == 1 and None not in values
    return {'checks': checks, 'chromium_archive': study['chromium_run'], 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = release.stored.read(CASE)
    reference_path = release.WORKSPACE / 'cases' / study['reference_case']
    original = release.stored.read(reference_path)
    source = release.WORKSPACE / 'cases' / original['fixed_voice_case']
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=release.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=release.UPSTREAM, text=True)
            or original['upstream_revision'] != revision or release.sha256(source) != original['fixed_voice_sha256']):
        parser.error('固定上流または固定発声の入力を照合できません')
    if any(sorted(row) != ['chromium', 'firefox'] for row in study['measurement']['browser_order']):
        parser.error('試行順序はChromiumとFirefoxを各回含めてください')
    archive, manifest = release.saved.load_saved_run(
        study['chromium_run'], original['id'], revision,
        ['summary.json', 'artifacts/browser.wav', 'artifacts/browser.json', 'artifacts/vocal_wasm.wasm'])
    prior = release.stored.read(manifest)
    reference_sha, = (row['sha256'] for row in prior['inputs'] if row['path'].endswith('/' + reference_path.name))
    if (prior['status'] != 'pass' or reference_sha != release.sha256(reference_path)
            or not all(release.stored.read(archive['summary.json'])['checks'].values())):
        parser.error('Chromiumの基準実行を照合できません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    paths = [CASE, reference_path, source, Path(__file__).resolve(), manifest, *archive.values(),
             *release.web_sources(), *release.shared.candidate_sources(), release.vowel.PROBE,
             *(Path(module.__file__) for module in (realtime, release, release.stored, release.saved,
               release.shared, realtime.pcm, release.wasm, release.vowel))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return release.shared.record_measurement(args.run_id, CASE, paths, metadata,
        lambda a, run: measure(study, original, source, archive, a, run, bun), command=None, input_root=release.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
