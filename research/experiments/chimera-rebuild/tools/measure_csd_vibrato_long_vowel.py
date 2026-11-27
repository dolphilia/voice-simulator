"""同じ長母音のビブラート深さだけを変え、波形と声門F0の応答を測る。"""

import argparse
import csv
import math
import os
from pathlib import Path
import sys

import numpy as np

from measure_csd_continuous_song import delta, samples, state
from measure_csd_envelope_timing import error, verified_file, within
from measure_csd_song_f0 import NotePitch, measurement_windows, midi_to_hz
from measure_csd_vibrato_aperiodicity import check_independence, vibrato
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-vibrato-long-vowel.json'
FIELDS = ('frame', 'smoothed_f0_hz', 'glottal_f0_hz')


def analyze(case, pcm, trace, label, measurements, pitch_config, writer):
    rate = case['render']['sample_rate_hz']
    score = case['score']
    midi = score['notes'][0]['midi']
    target = midi_to_hz(midi)
    start = score['start_seconds']
    note = {'start': start, 'end': start + 60*score['notes'][0]['beats']/score['bpm'], 'melisma': False}
    _, centers = measurement_windows(note, pitch_config)
    tracks = {key: [] for key in ('upstream', 'candidate', 'glottis')}
    estimators = {key: NotePitch(data, rate, midi, pitch_config) for key, data in pcm.items()}
    for t in centers:
        frame = int(t*rate)
        for key, estimator in estimators.items():
            status, hz, power, aper = estimator.at(t, target, include_gated_aperiodicity=True)
            cents = None if hz is None else 1200*math.log2(hz/target)
            tracks[key].append(cents)
            writer.writerow((label, key, t, frame, status, hz, cents, power, aper))
        glottis = float(trace['glottal_f0_hz'][frame])
        smooth = float(trace['smoothed_f0_hz'][frame])
        modulation = 1200*math.log2(glottis/smooth)
        tracks['glottis'].append(modulation)
        writer.writerow((label, 'glottis', t, frame, 'state', glottis, modulation, None, None))
    stats = {k: {**vibrato(c, measurements), 'voiced_share': sum(x is not None for x in c)/len(c)}
             for k, c in tracks.items()}
    return {'notes': stats, 'seconds': [centers[0], centers[-1]], 'centers': len(centers)}


def measurement(case, original, probe, measurements, pitch_config, out, run):
    rate, length = (case['render'][name] for name in ('sample_rate_hz', 'frames'))
    limits = case['limits']
    run(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    executable = WORKSPACE / 'target/release/vocal-cli'
    report = {}
    variants = {}
    with (out / 'stable-frames.csv').open('w', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(('depth_setting_cents', 'signal', 'seconds', 'center_frame', 'status', 'f0_hz', 'cents',
                         'mean_square', 'aperiodicity'))
        for depth in case['render']['depths_cents']:
            config = out / f'candidate-{depth}.json'
            write(config, {'song_voice': {**original['song_voice'], 'scores': [case['score']],
                                         'render_end_seconds': length/rate, 'vibrato_cents': depth}})
            wave, upper, plan = (out / name for name in
                                  (f'candidate-{depth}.wav', f'upstream-{depth}.f32', f'upstream-{depth}-plan.json'))
            trace = out.parent / 'tmp' / f'upstream-{depth}.csv'
            run([str(executable), 'render-pcm', str(config), str(wave), '--no-trace'])
            run([str(probe), str(config), case['render']['probe_mode'], str(upper), str(trace), str(plan)])
            reference = np.fromfile(upper, dtype='<f4')
            if reference.shape != (length,) or not np.isfinite(reference).all():
                raise ValueError('固定上流のPCMが登録した形式と長さに一致しません')
            pcm = {'upstream': reference, 'candidate': samples(wave, rate, length)}
            observations = state(trace, FIELDS, length)
            stats = analyze(case, pcm, observations, depth, measurements, pitch_config, writer)
            stats['raw_trace'] = {'sha256': sha256(trace), 'bytes': trace.stat().st_size, 'retained_frames': stats['centers']}
            stats['pcm_delta'] = delta(reference, pcm['candidate'], tolerance=limits['pcm_absolute_tolerance'])
            variants[depth] = pcm
            report[str(depth)] = stats
            trace.unlink()
    enabled, disabled = (report[str(x)]['notes'] for x in case['render']['depths_cents'])
    checks = {
        'all_runs_eligible': all(x['eligible'] and x['voiced_share'] >= limits['minimum_voiced_share']
                                 for rows in (enabled, disabled) for x in rows.values()),
        'enabled_pitch_modulation': all(x['status'] == 'detected'
            and within(error(x['rate_hz'], limits['expected_rate_hz']), limits['rate_tolerance_hz'])
            and within(error(x['depth_cents'], case['render']['depths_cents'][0]), limits['depth_tolerance_cents'])
            for x in enabled.values()),
        'disabled_pitch_is_flat': all(within(x['residual_rms_cents'], limits['maximum_flat_residual_rms_cents'])
                                      for x in disabled.values()),
        'matched_pcm': all(r['pcm_delta']['maximum_absolute_difference'] <= limits['pcm_absolute_tolerance']
                           for r in report.values()),
        'matched_observation': all(r['upstream']['status'] == r['candidate']['status']
            and all(within(error(r['upstream'][k], r['candidate'][k]), limits['matched_measure_tolerance'])
                    for k in ('depth_cents', 'rate_hz', 'residual_rms_cents')) for r in (enabled, disabled)),
    }
    independent = check_independence([*enabled.values(), *disabled.values()], measurements)
    checks['independent_regression_and_correlation'] = independent['matches']
    on, off = case['render']['depths_cents']
    depth_difference = {key: delta(variants[off][key], variants[on][key], tolerance=limits['pcm_absolute_tolerance'])
                        for key in ('upstream', 'candidate')}
    return {'checks': checks, 'depths': report, 'depth_control_pcm_delta': depth_difference, 'independent': independent}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case = read(CASE)
    root = WORKSPACE / 'runs' / case['base_run']
    manifest_path = root / 'manifest.json'
    base = read(manifest_path)
    if base['status'] != 'pass' or base['upstream_revision'] != case['upstream_revision']:
        parser.error('固定上流の観測プローブを確認できません')
    score = verified_file(root, base, 'artifacts/candidate-short-128.json')
    probe = verified_file(root, base, 'artifacts/upstream_csd_continuous_probe.exe')
    calc, pitch = (CASE.parent / case[key] for key in ('analysis_case', 'pitch_case'))
    inputs = [CASE, manifest_path, score, probe, calc, pitch, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in ('measure_csd_continuous_song.py',
                  'measure_csd_envelope_timing.py', 'measure_csd_vibrato_aperiodicity.py',
                  'measure_csd_song_f0.py', 'measure_vowel_voice.py', 'measure_speech_timing.py',
                  'measure_uniform_tube.py', 'upstream_baseline.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], 'base_run': case['base_run']}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, run: measurement(case, read(score), probe, read(calc)['measurement'], read(pitch)['measurement'],
                                     out, run), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
