"""TSPの確認用結果を保存注釈と固定上流のRustプローブで独立に照合する。"""

import argparse
import csv
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-phone-boundaries-held-out.json'
SAVED = UPSTREAM / 'tools/tsp/alignment.tsv.gz'
NOISE_RUN = WORKSPACE / 'runs/tsp-phone-boundaries-20261121-noise-rust'
CALIBRATION = WORKSPACE / 'runs/tsp-phone-boundaries-20261121-final/summary.json'


def read(path):
    return json.loads(path.read_text())


def verify(case, run, regression, wave_pairs, probe, artifacts, execute):
    summary = read(run / 'summary.json')
    ids = [uid for row in case['transcripts'] for uid in row['recording_ids']]
    labels = {uid: {'words': [], 'phones': []} for uid in ids}
    with gzip.open(SAVED, 'rt', newline='') as stream:
        for uid, tier, start, end, text in csv.reader(stream, delimiter='\t'):
            if uid in labels:
                labels[uid][tier + 's'].append([round(float(start) * 1000), round(float(end) * 1000), text])

    recorded = {}
    for uid, kinds in labels.items():
        word_phone = summary['intervals'][uid]
        recorded[uid] = {
            kind: expected == [[round(a * 1000), round(b * 1000), text] for a, b, text in word_phone[kind]]
            for kind, expected in kinds.items()
        }

    noise = {}
    for tag, clean, used in wave_pairs:
        with TemporaryDirectory(dir=artifacts.parent / 'tmp', prefix=f'{tag}-') as tmp:
            source, result = Path(tmp) / 'source.f32', Path(tmp) / 'expected.i16'
            rate, raw = wavfile.read(clean)
            align_rate, aligned = wavfile.read(used)
            raw.astype('<f4').tofile(source)
            execute([str(probe), str(source), str(result)])
            expected = np.fromfile(result, dtype='<i2')
            if rate != align_rate or expected.shape != aligned.shape or aligned.dtype != np.int16:
                raise ValueError(f'ノイズ床照合のWAV形式が一致しません ({tag})')
            mismatches = int(np.count_nonzero(expected != aligned))
            if mismatches:
                (artifacts / f'{tag}-expected.i16').write_bytes(result.read_bytes())
            noise[tag] = {'frames': len(aligned), 'mismatching_frames': mismatches}

    previous, repeated = read(CALIBRATION), read(regression)
    calibration = {key: previous.get(key) == repeated.get(key) for key in previous.keys() | repeated.keys()}
    return {
        'checks': {
            'saved_recording_millisecond_boundaries': all(x for row in recorded.values() for x in row.values()),
            'pcm16_bit_exact': all(not row['mismatching_frames'] for row in noise.values()),
            'calibration_summary_unchanged': all(calibration.values()),
        },
        'saved_recording_millisecond_boundaries': recorded,
        'noise': noise,
        'total_pcm16_frames': sum(row['frames'] for row in noise.values()),
        'calibration': calibration,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('alignment_run')
    parser.add_argument('calibration_run')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case = read(case_path)
    run = WORKSPACE / 'runs' / args.alignment_run
    regression = WORKSPACE / 'runs' / args.calibration_run / 'summary.json'
    manifest = NOISE_RUN / 'manifest.json'
    probe = NOISE_RUN / 'artifacts/upstream-noise.exe'
    upper = read(manifest)
    saved_probe = next(row for row in upper['outputs'] if row['path'] == 'artifacts/upstream-noise.exe')
    if upper['upstream_revision'] != case['upstream_revision'] or sha256(probe) != saved_probe['sha256']:
        parser.error('Rustプローブが登録版と一致しません')
    baseline = WORKSPACE / 'runs' / case['baseline_run']
    wave_pairs = []
    for row in case['transcripts']:
        for uid in row['recording_ids']:
            for voice in ('upstream', 'candidate'):
                tag = f'{uid}-{voice}'
                clean = baseline / 'artifacts' / uid / f'{voice}.wav'
                used = run / 'artifacts/corpus/synth' / tag / f'{tag}.wav'
                wave_pairs.append((tag, clean, used))
    inputs = [case_path, Path(__file__).resolve(), SAVED, manifest, probe, CALIBRATION, regression, run / 'summary.json']
    inputs.extend(path for _, clean, used in wave_pairs for path in (clean, used))
    return record_measurement(
        args.run_id, case_path, inputs,
        {'upstream_revision': upper['upstream_revision'], 'alignment_run': args.alignment_run},
        lambda out, execute: verify(case, run, regression, wave_pairs, probe, out, execute),
        command=None, input_root=WORKSPACE.parents[2],
    )


if __name__ == '__main__':
    raise SystemExit(main())
