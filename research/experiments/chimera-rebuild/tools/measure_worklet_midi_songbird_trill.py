"""Canary trillのWeb MIDI再発音、パルス時刻と左右の鳴管を照合する。"""

from fractions import Fraction
import math
from pathlib import Path

import numpy as np

from measure_worklet_midi_songbird import rms
from measure_worklet_midi_songbird_call import describe_intervals, main
from measure_worklet_songbird_call import rising_frames
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-songbird-trill.json'
SOURCE = WORKSPACE / 'cases/songbird-calls.json'
LABIAL_CONTROLS = ('voices', 'drive', 'target_voices', 'target_drive')


def trill_performance(trace, pcm, voice, events, pitches, spec, definition, configs, **_context):
    rate = voice['sample_rate_hz']
    stride = spec['control_frames']
    dt = stride / rate
    tolerance = spec['independent_absolute_tolerances']
    starts, releases, end = describe_intervals(trace, pcm, events, spec, rate)
    restart = starts[-1]['frame']
    pulse_rises = rising_frames(trace['frame'].astype(int), trace['gate_target'], spec['gate_crossing_threshold'])
    period = Fraction(1, spec['pulse_rate_hz'])
    attack = Fraction(str(spec['first_rise_offset_seconds']))
    relative_rises = [stride * math.ceil((i * period + attack) * rate / stride) for i in range(spec['pulse_count'])]
    ranges = []
    for press, stop, pitch in zip(starts, (restart, end or len(trace)), pitches, strict=True):
        frame = press['frame']
        predicted = [frame + tick for tick in relative_rises if frame + tick < stop]
        observed = pulse_rises[(pulse_rises >= frame) & (pulse_rises < stop)].tolist()
        errors = [got - want for got, want in zip(observed, predicted, strict=True)] if len(observed) == len(predicted) else None
        first = trace['target_pitch_hz'][frame:frame + int(period * rate)]
        ranges.append({'frame': frame, 'expected_pulse_rises': predicted, 'observed_pulse_rises': observed,
                       'timing_errors_frames': errors, 'intervals_frames': np.diff(observed).tolist(),
                       'first_pitch_min_max_hz': [float(min(first)), float(max(first))],
                       'expected_pitch_min_max_hz': [pitch * ratio for ratio in spec['pitch_key_ratios']]})
    for row in releases:
        a, b = row['window']
        row['pulse_rises'] = pulse_rises[(pulse_rises >= a) & (pulse_rises < b)].tolist()
        left, right = (rms(trace[f'{side}_opening'][a:b]) for side in ('left', 'right'))
        row['opening_rms'] = {'left': left, 'right': right}
        row['right_to_left_opening_rms'] = right / left if left > 0 else None

    fields = ('gate', 'gate_target', 'pitch_hz', 'target_pitch_hz', 'left_opening', 'right_opening',
              'left_port_flow_cm3_s', 'right_port_flow_cm3_s', 'sac_pressure_dyn_cm2')
    before, after = [{key: float(trace[key][frame]) for key in fields} for frame in (restart - 1, restart)]
    expected_gate = before['gate'] * math.exp(-dt / configs['release_seconds'])
    weight = math.exp(-dt / configs['parameter_time_constants_seconds']['pitch_hz'])
    expected_pitch = math.exp(weight * math.log(before['pitch_hz']) + (1 - weight) * math.log(after['target_pitch_hz']))
    area_errors = {side: float(np.max(abs(trace[f'{side}_port_area_cm2']
                                         - spec['maximum_syrinx_port_area_cm2'] * trace[f'{side}_opening'])))
                   for side in ('left', 'right')}
    low, high = spec['right_to_left_opening_rms_ratio']
    head = definition['keys'][0]['v']
    tail = rms(pcm[-round(rate * spec['tail_window_seconds']):])
    checks = {
        'canary_trill_pulse_clock_matches_analytic_grid': all(
            row['timing_errors_frames'] is not None and bool(row['timing_errors_frames'])
            and max(map(abs, row['timing_errors_frames'])) <= spec['maximum_pulse_timing_error_frames']
            for row in ranges) and len(ranges[-1]['observed_pulse_rises']) == spec['pulse_count'],
        'each_canary_upsweep_transposes_both_ends': all(
            abs(actual - wanted) <= tolerance['target_pitch_hz']
            for row in ranges for actual, wanted in zip(row['first_pitch_min_max_hz'],
                                                       row['expected_pitch_min_max_hz'], strict=True)),
        'release_retains_pulses_and_both_syrinx_flows': all(
            row['call_ids'] == [2] and len(row['pulse_rises']) >= spec['minimum_release_pulse_count']
            and row['pcm_rms'] >= spec['minimum_post_release_pcm_rms']
            and min(row['flows_rms_cm3_s'].values()) >= spec['minimum_both_syrinx_rms_cm3_s']
            and row['right_to_left_opening_rms'] is not None
            and low <= row['right_to_left_opening_rms'] <= high for row in releases),
        'canary_retrigger_preserves_smoothed_state': after['gate_target'] == 0
            and abs(after['gate'] - expected_gate) <= tolerance['gate']
            and abs(after['pitch_hz'] - expected_pitch) <= tolerance['pitch_hz']
            and all(trace['target_' + name][restart] == head[name] for name in ('voices', 'drive')),
        'syrinx_port_area_matches_opening': max(area_errors.values()) <= spec['port_area_absolute_tolerance_cm2'],
        'natural_end_restores_performer_and_pcm_decays': end is not None
            and abs((end - restart) / rate - (definition['keys'][-1]['t'] + 0.05)) <= dt + 1e-10
            and np.all(trace['gate_target'][end:] == 0)
            and all(np.all(trace['target_' + name][end:] == voice['controls'][name])
                    for name in ('pitch_hz', 'voices', 'drive'))
            and tail <= spec['maximum_tail_pcm_rms'],
    }
    return checks, {'pulse_windows': ranges, 'post_release': releases, 'starts': starts, 'automatic_end_frame': end,
                    'retrigger': {'frame': restart, 'before': before, 'after': after,
                                  'independent_gate': expected_gate, 'independent_pitch_hz': expected_pitch},
                    'port_area_errors_cm2': area_errors, 'tail_pcm_rms': tail}


if __name__ == '__main__':
    raise SystemExit(main(CASE, performance=trill_performance, additional_state=LABIAL_CONTROLS,
                          description=__doc__, driver=Path(__file__),
                          extra_inputs=(SOURCE, WORKSPACE / 'tools/measure_worklet_songbird_call.py')))
