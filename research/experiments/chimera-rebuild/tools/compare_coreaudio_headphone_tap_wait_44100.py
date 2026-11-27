"""タップの準備から出力を始めるまでの待機を変えた3組を比較する。"""

import argparse
from pathlib import Path
import sys

from compare_coreaudio_headphone_leading_silence_44100 import load_trials
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WORKSPACE


CASE = WORKSPACE / 'cases/coreaudio-headphone-drift-44100-tap-wait.json'


def compare_pair(short, long, spec):
    if not (short['capture_pass'] and long['capture_pass']):
        return {'classification': 'capture_failed'}
    gap = long['start_host_gap_ms'] - short['start_host_gap_ms']
    separated = spec['minimum_start_gap_change_ms'] <= gap <= spec['maximum_start_gap_change_ms']
    result = {'start_gap_change_ms': gap, 'start_clocks_separated': separated}
    if not separated:
        return {**result, 'classification': 'start_gap_outside_range'}
    before, after = (t['events']['waveform_departure'] for t in (short, long))
    if before['output_frame'] is None or after['output_frame'] is None:
        return {**result, 'classification': 'departure_missing'}
    frames_limit = spec['maximum_departure_deviation_frames']
    maximum_error = spec['maximum_timing_residual_ms']
    output_delta = after['output_frame'] - before['output_frame']
    elapsed = {clock: after[f'ms_from_first_{clock}_timestamp'] - before[f'ms_from_first_{clock}_timestamp']
               for clock in ('output', 'tap')}
    if abs(before['output_frame'] - spec['reference_waveform_departure_output_frame']) > frames_limit:
        classification = 'control_outside_reference'
    elif abs(output_delta) <= frames_limit and abs(elapsed['tap'] - gap) <= maximum_error:
        classification = 'output_start'
    elif abs(elapsed['tap']) <= maximum_error and abs(elapsed['output'] + gap) <= maximum_error:
        classification = 'tap_start'
    else:
        classification = 'neither'
    return {**result, 'classification': classification, 'output_delta_frames': output_delta,
            'departure_elapsed_change_ms': elapsed}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    registered = args.case.resolve()
    spec, phase_spec, trials, inputs = load_trials(registered, ('leading_frames', 'tap_lead_seconds'))

    def measure(folder, execute):
        pairs = [{'short_wait': short, 'long_wait': long, **compare_pair(trials[short], trials[long], spec)}
                 for short, long in spec['pairs']]
        counts = {condition: sum(pair['classification'] == condition for pair in pairs)
                  for condition in sorted({pair['classification'] for pair in pairs})}
        plateaus = [p for trial in trials.values() for p in trial.get('plateaus', ())]
        return {
            'checks': {'captures_valid': all(t['capture_pass'] for t in trials.values()),
                       'start_clocks_separated': all(pair.get('start_clocks_separated', False) for pair in pairs)},
            'predictions': {'output_start_in_at_least_two_pairs': counts.get('output_start', 0) >= 2,
                            'all_plateau_clocks_match': bool(plateaus) and all(
                                abs(row['error_ppm']) <= phase_spec['maximum_slope_error_ppm'] for row in plateaus)},
            'pair_counts': counts, 'pairs': pairs, 'trials': trials,
        }

    metadata = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': phase_spec['upstream_revision'],
                'analysis_command': [sys.executable, *sys.argv]}
    return record_measurement(args.run_id, registered, [*inputs, Path(__file__).resolve()], metadata, measure,
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
