"""TSPの録音と2実装の合成を、同じ出力サンプル区間で測る。"""

import argparse
import csv
from hashlib import sha256 as digest
import io
import json
import os
from pathlib import Path
import random
import subprocess
import wave
from zipfile import BadZipFile, ZipFile

import numpy as np
import scipy
from scipy.io import wavfile

from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-active-duration-supported.json'
TRANSCRIPTS = UPSTREAM / 'tools/tsp/sentences.tsv'


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def windows(samples, size, hop):
    if samples.ndim != 1 or samples.size < size or not np.isfinite(samples).all():
        raise ValueError('PCMは窓長以上かつ有限なモノラルが必要です')
    frames = np.lib.stride_tricks.sliding_window_view(samples, size)[::hop]
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    if not np.isfinite(rms).all() or rms.max() == 0:
        raise ValueError('窓ごとのRMSが非有限か全区間が無音です')
    return rms


def active_interval(rms, size, hop, db):
    active = rms >= rms.max() * 10**(db / 20)
    consecutive = np.flatnonzero(active[:-2] & active[1:-1] & active[2:])
    if not consecutive.size:
        raise ValueError(f'{db} dB以上の窓が3点連続していません')
    return int(consecutive[0]) * hop, (int(consecutive[-1]) + 2) * hop + size


def padding_control(config, size, hop, rate, thresholds):
    leading, nonzero, trailing = (config[key] for key in ('leading_frames', 'nonzero_frames', 'trailing_frames'))
    extra = config['extra_frames_at_either_end']
    signal = np.zeros(leading + nonzero + trailing)
    signal[leading:leading + nonzero] = config['amplitude']
    # ホップ格子に整列した矩形では、最初と最後に重なる窓にちょうど1ホップ分の入力が入る。
    expected = (leading - size + hop, leading + nonzero - hop + size)
    checks = {}
    results = {}
    for db in thresholds:
        measured = active_interval(windows(signal, size, hop), size, hop, db)
        padded = active_interval(windows(np.pad(signal, extra), size, hop), size, hop, db)
        duration_delta = (padded[1] - padded[0]) - (measured[1] - measured[0])
        checks[str(db)] = (measured == expected and padded == tuple(i + extra for i in expected)
                           and abs(duration_delta) <= rate * 0.005)
        results[str(db)] = {'expected': expected, 'unpadded': measured, 'padded': padded,
                            'duration_delta_frames': duration_delta}
    return all(checks.values()), results


def read_recording(archive, member, rate):
    payload = archive.read(member)
    with wave.open(io.BytesIO(payload), 'rb') as source:
        if (source.getframerate(), source.getnchannels(), source.getsampwidth()) != (rate, 1, 2):
            raise ValueError(f'録音が所定のモノラルPCM16ではありません ({member})')
        frames = source.getnframes()
        samples = np.frombuffer(source.readframes(frames), dtype='<i2')
    if samples.size != frames:
        raise ValueError(f'録音のフレーム数がヘッダーと一致しません ({member})')
    return samples.astype(np.float64) / 32768.0, digest(payload).hexdigest()


def read_generated(path, rate):
    wave_rate, samples = wavfile.read(path)
    if wave_rate != rate or samples.dtype != np.float32 or samples.ndim != 1:
        raise ValueError(f'合成音が所定のモノラルfloat32ではありません ({path.name})')
    return samples


def measure_waves(signals, path, size, hop, rate, thresholds):
    measurements = {}
    with path.open('x', newline='') as target:
        writer = csv.writer(target, lineterminator='\n')
        writer.writerow(('source', 'start_frame', 'rms'))
        for name, samples in signals.items():
            rms = windows(samples, size, hop)
            writer.writerows((name, index * hop, float(value)) for index, value in enumerate(rms))
            durations = {}
            for db in thresholds:
                start, end = active_interval(rms, size, hop, db)
                durations[str(db)] = {'start_frame': start, 'end_frame_exclusive': end,
                                      'duration_ms': (end - start) * 1000 / rate}
            measurements[name] = {'pcm_frames': samples.size, 'maximum_window_rms': float(rms.max()),
                                  'thresholds': durations}
    return measurements


def compare_pcm(upstream, candidate):
    length = min(upstream.size, candidate.size)
    diff = np.flatnonzero(upstream[:length].view(np.uint32) != candidate[:length].view(np.uint32))
    return {'common_frames': length, 'different_bits': int(diff.size),
            'first_bit_difference': int(diff[0]) if diff.size else None,
            'maximum_absolute_difference': float(np.max(np.abs(upstream[:length].astype(float) - candidate[:length])))}


def track_matches(path, samples):
    trace = np.loadtxt(path, delimiter=',', skiprows=1, ndmin=2)
    indices = np.arange(samples.size)
    return bool(trace.shape == (samples.size, 7) and np.isfinite(trace).all()
                and np.array_equal(trace[:, 0], indices) and np.array_equal(trace[:, 1], indices * 2 + 1)
                and np.array_equal(trace[:, 6].astype(np.float32).view(np.uint32), samples.view(np.uint32)))


def listening_pair(folder, number, rng, config, rate, signals, measures, primary):
    pair = {}
    for name in ('recording', 'candidate'):
        interval = measures[name]['thresholds'][str(primary)]
        pair[name] = signals[name][interval['start_frame']:interval['end_frame_exclusive']].astype(np.float64)
    levels = {name: float(np.sqrt(np.mean(samples**2))) for name, samples in pair.items()}
    cap = 10**(config['peak_ceiling_dbfs'] / 20)
    target = min(10**(config['maximum_rms_dbfs'] / 20),
                 *(cap * levels[name] / float(np.max(np.abs(samples))) for name, samples in pair.items()))
    choices = list(pair)
    rng.shuffle(choices)
    levels_match = []
    for label, name in zip(('A', 'B'), choices, strict=True):
        output = (pair[name] * (target / levels[name])).astype(np.float32)
        wavfile.write(folder / f'{number:02d}-{label}.wav', rate, output)
        levels_match.append(abs(float(np.sqrt(np.mean(output.astype(float)**2))) - target) <= 1e-7
                            and float(np.max(np.abs(output))) <= cap + 1e-7)
    return dict(zip(('A', 'B'), choices, strict=True)), all(levels_match)


def measure(scope, base, support, settings, pose, artifacts, execute):
    config = scope['implementation']
    metric = base['measurement']
    rate = base['synthesis']['sample_rate_hz']
    size, hop = (round(metric[key] * rate / 1000) for key in ('window_ms', 'hop_ms'))
    primary = metric['threshold_db_relative_to_maximum_window_rms']
    thresholds = (primary, metric['sensitivity_threshold_db'])
    control_ok, control = padding_control(config['zero_padding_control'], size, hop, rate, thresholds)
    if not control_ok:
        return {'checks': {'known_padding_control': False}, 'padding_control': control}

    reference = base['reference']
    archive_path = Path(reference['archive_path'])
    if archive_path.stat().st_size != reference['archive_bytes'] or sha256(archive_path) != reference['sha256']:
        raise ValueError('録音アーカイブが登録した版と一致しません')
    with TRANSCRIPTS.open(newline='') as stream:
        text_by_id = {record_id: (speaker, text) for record_id, speaker, text in csv.reader(stream, delimiter='\t')}
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    candidate = WORKSPACE / 'target/release/vocal-cli'
    upstream = UPSTREAM / 'target/release/chimera'
    rng = random.Random(config['listening']['order_seed'])
    listening = artifacts / 'listening'
    listening.mkdir()
    (listening / 'README.md').write_text(
        '# TSPの比較試聴\n\n同じ番号のAとBを続けて聴き、テンポ、間、気付いた点を記録します。'
        '音声を照合する鍵は別のファイルにあります。\n\n'
        '録音の出典はTSP Speech Database v2、Copyright (c) 2018 Peter Kabal。'
        '利用条件は同梱の TSP-licence.txt にあります。\n')
    licence = (UPSTREAM / 'tools/tsp/README.md').read_text().split('The Harvard sentences', 1)[0]
    (listening / 'TSP-licence.txt').write_text(licence.split('## Licences', 1)[1].strip() + '\n')
    splits = {'calibration': {}, 'held_out': {}}
    key = {}
    with ZipFile(archive_path) as archive:
        for split, rows in splits.items():
            for record_id in scope[f'{split}_ids']:
                folder = artifacts / record_id
                folder.mkdir()
                speaker, text = text_by_id[record_id]
                body = 'female' if speaker.startswith('F') else 'male'
                member = f'48k/{speaker}/{record_id}.wav'
                path = folder / 'candidate.json'
                input_case = {'speech_voice': {
                    'input': {'id': record_id, 'text': text, 'rate': base['synthesis']['speech_rate']},
                    'body': body, 'language': 'english', 'posture': pose,
                    'internal_sample_rate_hz': settings['internal_sample_rate_hz'], 'voice': settings['voice'],
                    'turbulence': {'scale': 1.0},
                }}
                # 入力の可否を事前確認したときと同じJSON表現を保存する。
                path.write_text(json.dumps(input_case, ensure_ascii=False) + '\n')
                try:
                    expected = support['observations'][record_id]
                    if sha256(path) != expected['input_sha256'] or expected['exit_code'] != 0:
                        raise ValueError('事前確認した発話入力と一致しません')
                    execute([str(candidate), 'inspect', str(path)], stdout=folder / 'inspect.json')
                    plan = load(folder / 'inspect.json')
                    execute([str(candidate), 'render-pcm', str(path), str(folder / 'candidate.wav'),
                             str(folder / 'candidate.csv'), str(config['block_frames'])])
                    execute([str(upstream), 'render', 'text', str(folder / 'upstream'), text, body, '--float'],
                            cwd=UPSTREAM, stdout=folder / 'upstream.log')
                    recording, recording_hash = read_recording(archive, member, rate)
                    cand = read_generated(folder / 'candidate.wav', rate)
                    upper = read_generated(folder / 'upstream.wav', rate)
                    signals = {'recording': recording, 'upstream': upper, 'candidate': cand}
                    measures = measure_waves(signals, folder / 'windows.csv', size, hop, rate, thresholds)
                    duration = {name: result['thresholds'][str(primary)]['duration_ms'] for name, result in measures.items()}
                    raw_duration = {name: samples.size * 1000 / rate for name, samples in signals.items()}
                    number = len(key) + 1
                    choices, listening_ok = listening_pair(listening, number, rng, config['listening'],
                                                           rate, signals, measures, primary)
                    key[f'{number:02d}'] = {'split': split, 'recording_id': record_id, **choices}
                    rows[record_id] = {'recording_archive_member': member, 'recording_sha256': recording_hash,
                                       'body': body, 'windows': measures, 'raw_duration_ms': raw_duration,
                                       'duration_delta_ms': {'candidate_minus_recording': duration['candidate'] - duration['recording'],
                                                             'upstream_minus_recording': duration['upstream'] - duration['recording'],
                                                             'candidate_minus_upstream': duration['candidate'] - duration['upstream']},
                                       'pcm_comparison': compare_pcm(upper, cand), 'listening_pair': f'{number:02d}',
                                       'checks': {
                                           'sample_counts_and_plan': upper.size == cand.size == plan['output_frames'] == expected['output_frames'],
                                           'candidate_trace_and_pcm': track_matches(folder / 'candidate.csv', cand),
                                           'synthetic_duration': abs(duration['candidate'] - duration['upstream'])
                                           <= metric['synthetic_pair_duration_tolerance_ms'],
                                           'listening_levels': listening_ok,
                                       }}
                except (OSError, ValueError, KeyError, wave.Error, BadZipFile, subprocess.CalledProcessError) as error:
                    rows[record_id] = {'error': str(error), 'recording_archive_member': member}
    save(artifacts / 'listening-key.json', key)
    with (listening / 'observations.csv').open('x', newline='') as target:
        writer = csv.writer(target, lineterminator='\n')
        writer.writerow(('pair', 'tempo', 'pauses', 'observations'))
        writer.writerows((number, '', '', '') for number in key)
    all_rows = [row for rows in splits.values() for row in rows.values()]
    checks = {'known_padding_control': control_ok, 'all_recordings_measured': all('checks' in row for row in all_rows)}
    for name in ('sample_counts_and_plan', 'candidate_trace_and_pcm', 'synthetic_duration', 'listening_levels'):
        checks[name] = all(row.get('checks', {}).get(name, False) for row in all_rows)
    return {'checks': checks, 'padding_control': control, 'sample_rate_hz': rate,
            'window_frames': size, 'hop_frames': hop, 'archive_sha256': reference['sha256'],
            'binaries': {'candidate_sha256': sha256(candidate), 'upstream_sha256': sha256(upstream)},
            'splits': splits}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='測定するケースのJSON')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('合成の時系列は CHIMERA_RUN_STORAGE=rtl9210b で作業用ディスクに出力してください')
    case_path = args.case.resolve()
    scope = load(case_path)
    base_path = case_path.parent / scope['base_case']
    base = load(base_path)
    settings_path = case_path.parent / scope['implementation']['settings_case']
    settings = load(settings_path)
    pose_path = case_path.parent / settings['neutral_case']
    pose = load(pose_path)['posture']
    selected = WORKSPACE / 'runs' / scope['input_support_run']
    support = load(selected / 'summary.json')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != base['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    sources = [Path(__file__).resolve(), case_path, base_path, settings_path, pose_path, TRANSCRIPTS,
               UPSTREAM / 'tools/tsp/README.md', UPSTREAM / 'Cargo.lock', selected / 'manifest.json',
               selected / 'summary.json', *candidate_sources()]
    return record_measurement(args.run_id, case_path, sources,
                              {'case_id': scope['id'], 'revision': scope['revision'], 'upstream_revision': revision,
                               'invoked_from': str(Path.cwd()), 'scipy_version': scipy.__version__},
                              lambda out, execute: measure(scope, base, support, settings, pose, out, execute),
                              command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
