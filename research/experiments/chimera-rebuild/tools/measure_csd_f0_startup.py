"""CSDの確認用曲で、全曲の先頭のPCM差を発声状態へ遡る。"""

import argparse
import math
import os
from pathlib import Path

import numpy as np

from measure_csd_continuous_song import delta, pcm_bits_equal, samples, state
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-acoustic-f0-en005a-startup.json'
FIELDS = ('frame', 'gate', 'smoothed_f0_hz', 'glottal_f0_hz', 'lip_flow_cm3_s', 'radiation_derivative_cm3_s2')


def measurement(case, paths, runs, out, execute):
    rate, frames = case['sample_rate_hz'], case['frames']
    candidate_case = out / 'startup-case.json'
    spec = read(paths['input'])
    spec['song_voice']['render_end_seconds'] = frames/rate
    write(candidate_case, spec)
    cli = WORKSPACE / 'target/release/vocal-cli'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    wave = out / 'candidate.wav'
    series = out / 'candidate.csv'
    execute([str(cli), 'render-pcm', str(candidate_case), str(wave), '--no-trace'])
    execute([str(cli), 'render', str(candidate_case), str(series)])
    native = samples(wave, rate, frames)
    physical = state(series, FIELDS, frames)
    full_native, full_reference = (samples(paths[k], rate, runs[k]['frames']) for k in ('candidate', 'upstream'))
    reference = {}
    for mode in ('standard', 'matched'):
        audio, trace, plan = (out / f'{mode}.{suffix}' for suffix in ('f32', 'csv', 'json'))
        execute([str(paths['probe']), str(candidate_case), mode, str(audio), str(trace), str(plan)])
        reference[mode] = (np.fromfile(audio, dtype='<f4'), state(trace, FIELDS, frames))
    differences = {mode: {'pcm': delta(native, audio, tolerance=case['pcm_tolerance']),
                          'state': {field: delta(physical[field], trace[field], tolerance=case['minimum_trace_difference'])
                                    for field in FIELDS[1:]}}
                   for mode, (audio, trace) in reference.items()}
    observed = {'candidate': {key: float(physical[key][0]) for key in FIELDS[1:]}}
    observed.update({mode: {key: float(trace[key][0]) for key in FIELDS[1:]}
                     for mode, (_, trace) in reference.items()})
    standard = observed['standard']
    drift = 1200 * math.log2(standard['glottal_f0_hz'] / standard['smoothed_f0_hz'])
    state_diffs = differences['standard']['state']
    return {
        'checks': {
            'prefixes_match_whole_song_pcm': (pcm_bits_equal(native, full_native[:frames])
                                             and pcm_bits_equal(reference['standard'][0], full_reference[:frames])),
            'first_difference_reaches_glottal_f0_and_lip_flow': all(
                state_diffs[key]['first_above_tolerance_frame'] == 0
                for key in ('glottal_f0_hz', 'lip_flow_cm3_s', 'radiation_derivative_cm3_s2')),
            'same_smoothed_f0_and_gate': all(state_diffs[key]['first_above_tolerance_frame'] is None
                                             for key in ('smoothed_f0_hz', 'gate')),
            'same_drift_as_independent_calibration': abs(drift-case['upstream_first_drift_cents']) <= case['drift_tolerance_cents'],
            'matched_settings_pcm': differences['matched']['pcm']['maximum_absolute_difference'] <= case['pcm_tolerance'],
        },
        'first_frame': observed, 'upstream_first_drift_cents': drift, 'differences': differences,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case = read(CASE)
    normal, source, probe = (WORKSPACE / 'runs' / case[k] for k in ('normal_run', 'source_run', 'probe_run'))
    wanted = {'input': (normal, 'artifacts/candidate-case.json'), 'candidate': (normal, 'artifacts/candidate.wav'),
              'upstream': (source, f"artifacts/csd/{case['song']}-synth.wav"),
              'probe': (probe, 'artifacts/upstream_csd_continuous_probe.exe')}
    manifests = {r: read(r / 'manifest.json') for r in (normal, source, probe)}
    paths, metadata = {}, {}
    for key, (root, name) in wanted.items():
        if manifests[root]['status'] != 'pass':
            parser.error(f'基準実行の判定が合格ではありません ({root.name})')
        record, = [f for f in manifests[root]['outputs'] if f['path'] == name]
        paths[key], metadata[key] = root / name, record
        if sha256(paths[key]) != record['sha256']:
            parser.error(f'計測入力が基準実行のハッシュと一致しません ({name})')
    revision = manifests[source]['upstream_revision']
    if any(m['upstream_revision'] != revision for m in manifests.values()):
        parser.error('固定上流の版が一致しません')
    inputs = [CASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_csd_continuous_song.py',
              *paths.values(), *(r / 'manifest.json' for r in manifests)]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
        lambda out, execute: measurement(case, paths, metadata, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
