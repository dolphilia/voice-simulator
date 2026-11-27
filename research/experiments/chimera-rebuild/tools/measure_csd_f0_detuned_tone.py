"""既知の音高を用いて、譜面基準の探索上限を狭めた場合を調べる。"""

import argparse
import math
import os
from pathlib import Path
import sys

import numpy as np

from measure_csd_f0_search_sensitivity import agree, estimate_both, score_cents
from measure_csd_song_f0 import NotePitch, midi_to_hz
from measure_speech_timing import read
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/csd-f0-search-detuned-tone.json'


def measure(case, settings, pitch, _out, _execute):
    rate = case['sample_rate_hz']
    time = np.arange(round(case['duration_seconds']*rate))/rate
    reference = midi_to_hz(case['midi'])
    ratios = [math.exp2(semis/12) for semis in settings['upper_semitones']]
    observations = []
    for offset in case['cents_offsets']:
        base = reference*math.exp2(offset/1200)
        for amps in case['harmonic_amplitudes']:
            samples = case['relative_amplitude']*sum(a*np.sin(2*np.pi*base*time*h)
                                                     for h, a in enumerate(amps, 1))
            estimator = NotePitch(samples, rate, case['midi'], pitch)
            power, observed = estimate_both(estimator, case['center_seconds'], reference, ratios)
            direct = []
            for ratio, value in zip(ratios, observed, strict=True):
                status, hz, energy, aper = estimator.at(case['center_seconds'], reference, upper_ratio=ratio,
                                                         include_gated_aperiodicity=True)
                direct.append(energy == power and agree(value, status, hz, aper, settings))
            observations.append({'target_hz': reference, 'known_hz': base, 'input_offset_cents': offset,
                'relative_amplitudes': amps, 'same_on_score': observed[0] == observed[1],
                'wide_matches_known': observed[0].hz is not None
                    and abs(observed[0].hz-base) <= case['wide_pitch_tolerance_hz'],
                'independent_check': all(direct),
                'results': [{**r._asdict(), 'cents_vs_score': score_cents(r.hz, reference),
                             'cents_vs_known': score_cents(r.hz, base)} for r in observed]})
    return {'checks': {
        'wide_measures_known_frequency': all(row['wide_matches_known'] for row in observations),
        'same_on_score': all(row['same_on_score'] for row in observations if row['input_offset_cents'] == 0),
        'independent_measures': all(row['independent_check'] for row in observations),
    }, 'observations': observations}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('run_id')
    args = cli.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        cli.error('計測結果は作業用ディスクを指定してください')
    case = read(CASE)
    comparison, pitch = (CASE.parent / case[k] for k in ('baseline_case', 'pitch_case'))
    baseline = read(comparison)
    inputs = [CASE, comparison, pitch, Path(__file__).resolve(),
              *(WORKSPACE/'tools'/name for name in ('measure_csd_f0_search_sensitivity.py', 'measure_csd_song_f0.py',
                                                     'measure_vowel_voice.py', 'measure_speech_timing.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': baseline['upstream_revision'],
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, exe: measure(case, baseline['measurement'], read(pitch)['measurement'], out, exe),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
