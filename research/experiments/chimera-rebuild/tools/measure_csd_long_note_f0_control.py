"""確認用長音で、F0探索上限だけがビブラート判定に与える影響を測る。"""

import argparse
import csv
import math
import os
from pathlib import Path
import sys

from measure_csd_envelope_timing import verified_file, waveforms
from measure_csd_f0_third_harmonic import spectrum_and_lags
from measure_csd_long_notes import load_sources
from measure_csd_song_f0 import NotePitch, midi_to_hz
from measure_csd_vibrato_aperiodicity import load_frames, vibrato
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/csd-long-note-vibrato-f0-control.json'


def cents(hz, target):
    return None if hz is None else 1200 * math.log2(hz / target)


def measure(case, song, published, pitch, periodicity, waves, saved_f0, out, _execute):
    index = case['note_index']
    note = published['notes'][index]
    target = midi_to_hz(note['midi'])
    minimum = min(n['midi'] for n in published['notes'])
    rate = math.exp2(case['search_upper_semitones'] / 12)
    gate = case['high_error_cents']
    stored = load_frames(saved_f0)
    estimates = {}
    checks = {}
    with (out / 'note-frames.csv').open('w', newline='') as stream:
        lines = csv.writer(stream)
        lines.writerow(('signal', 'seconds', 'normal_status', 'control_status', 'normal_f0_hz',
                        'control_f0_hz', 'normal_cents', 'control_cents', 'mean_square',
                        'normal_aperiodicity', 'control_aperiodicity'))
        for label, (pcm, fs) in waveforms(waves, song['wave_frames']).items():
            estimator = NotePitch(pcm, fs, minimum, pitch)
            a, b, high_centers = [], [], []
            same_base, same_power = True, True
            for frame in stored[index, label]:
                t = frame.time
                old = estimator.at(t, target)
                new = estimator.at(t, target, upper_ratio=rate)
                same_base &= old == (frame.status, frame.hz, frame.power, frame.aper)
                same_power &= old[2] == new[2] and (old[0] == 'below_energy_gate') == (new[0] == 'below_energy_gate')
                pre, post = cents(old[1], target), cents(new[1], target)
                a.append(pre)
                b.append(post)
                if pre is not None and pre >= gate:
                    high_centers.append(t)
                lines.writerow((label, t, old[0], new[0], old[1], new[1], pre, post, old[2], old[3], new[3]))
            wide, limited = vibrato(a, periodicity), vibrato(b, periodicity)
            reference = song['notes'][index]['signals'][label]
            checks[label] = (same_base and same_power and len(a) == case['expected_grid_frames']
                             and all(value == reference[k] for k, value in wide.items()))
            observed = None
            if high_centers:
                params = {**case, 'spectrum_center_seconds': high_centers[0]}
                observed = spectrum_and_lags(params, estimator, target, rate)
            estimates[label] = {'wide': wide, 'limited': limited, 'same_voiced_centers':
                 all((before is None) == (after is None) for before, after in zip(a, b, strict=True)),
                 'changed_f0_frames': sum(before != after for before, after in zip(a, b, strict=True)),
                 'wide_high_frames': len(high_centers), 'limited_high_frames': sum(x is not None and x >= gate for x in b),
                 'first_high_spectrum': observed}
    return {'checks': checks, 'song': case['song'], 'note_index': index, 'measurements': estimates}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('作業用ディスクを指定してください')
    case = read(CASE)
    baseline = WORKSPACE / 'runs' / case['baseline_run']
    manifest_path = baseline / 'manifest.json'
    manifest = read(manifest_path)
    if manifest['status'] != 'pass':
        parser.error('通常の測定を通過した実行が必要です')
    base, pitch, config = (CASE.parent / case[key] for key in ('base_case', 'pitch_case', 'periodicity_case'))
    prefix = case['song']
    summary = verified_file(baseline, manifest, 'summary.json')
    standard = verified_file(baseline, manifest, 'artifacts/upstream/report.json')
    f0 = verified_file(baseline, manifest, f'artifacts/{prefix}/note-f0-frames.csv')
    fixed, candidate = (verified_file(baseline, manifest, name) for name in (
        f'artifacts/upstream/{prefix}-synth.wav', f'artifacts/{prefix}/candidate.wav'))
    inputs = [CASE, base, pitch, config, manifest_path, summary, standard, f0, fixed, candidate, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in ('select_csd_long_notes.py', 'measure_csd_long_notes.py',
                  'measure_csd_song_f0.py', 'measure_csd_f0_third_harmonic.py', 'measure_csd_vibrato_aperiodicity.py',
                  'measure_csd_envelope_timing.py', 'measure_vowel_voice.py'))]
    recordings = load_sources(read(base), manifest['selection_run'], manifest['recording_run'], inputs)
    recording, = [item[3] for item in recordings if item[1]['id'] == prefix]
    published, = [s for s in read(standard)['songs'] if s['summary']['id'] == prefix]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': manifest['upstream_revision'],
               'baseline_run': case['baseline_run'], 'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, CASE, inputs, details,
         lambda out, exe: measure(case, read(summary)['songs'][prefix], published, read(pitch)['measurement'],
                                 read(config)['measurement'], (recording, fixed, candidate), f0, out, exe),
         command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
