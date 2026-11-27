"""仮想MIDIでGrowlを再発音し、呼気・口先・声門の状態を比較する。"""

from pathlib import Path

import numpy as np

from measure_alligator_bellow import CALL_IDS, OWNERSHIP
from measure_alligator_growl import growl_definition_matches
from measure_worklet_midi_alligator_call import acoustic_window, main
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-alligator-growl.json'


def bounds(candidate, pcm, voice, events, starts, pitches, factor, config, spec):
    rate = voice['sample_rate_hz']
    keys = spec['growl_keys']
    fields = ('call_id', 'gate_target', 'gate', 'target_pitch_hz', 'pitch_hz', 'target_chaos', 'target_mouth',
              'oral_tip_area_cm2', 'oral_noise', 'lung_pressure_dyn_cm2', 'glottis_phase',
              'glottis_flow_cm3_s', 'oral_cm3_s', 'nasal_cm3_s', 'radiation_cm3_s2')
    transitions = []
    for frame in starts:
        sample = frame * factor
        transitions.append({'frame': frame, 'before': {key: float(candidate[key][sample - 1]) for key in fields},
                            'after': {key: float(candidate[key][sample]) for key in fields}})
    before, after = (transitions[-1][side] for side in ('before', 'after'))
    phase_advance = (after['glottis_phase'] - before['glottis_phase']) % 1.0
    gate_low, gate_high = config['retrigger_old_goal_range']
    tip_target = 0.05 + 12.0 * keys['mouth']

    releases = [acoustic_window(candidate, pcm, event['frame'], config['release_window_seconds'], rate, factor)
                for event in events if not event['midi_call']['pressed']]
    ends = (np.flatnonzero(np.diff(candidate['call_id']) < 0) + 1).tolist()
    end = ends[0] // factor if len(ends) == 1 else None
    tail = (acoustic_window(candidate, pcm, end, config['end_window_seconds'], rate, factor)
            if end is not None else None)
    checks = {
        'release_keeps_call_and_phonation': all(
            row['call_ids'] == [CALL_IDS['growl']] and row['gate_min'] >= config['minimum_release_gate']
            and row['glottis_area_peak_cm2'] >= config['minimum_release_glottis_peak_cm2']
            and row['pcm_rms'] >= config['minimum_release_pcm_rms']
            and row['oral_flow_rms_cm3_s'] > 0 and row['nasal_flow_rms_cm3_s'] > 0 for row in releases),
        'each_start_sets_pitch_and_growl_targets': all(
            row['after']['call_id'] == CALL_IDS['growl'] and row['after']['gate_target'] == 1
            and row['after']['target_chaos'] == keys['chaos'] and row['after']['target_mouth'] == keys['mouth']
            and abs(row['after']['target_pitch_hz'] - keys['pitch_first_hz'] * pitch / keys['reference_pitch_hz'])
            <= config['control_tolerance'] for row, pitch in zip(transitions, pitches, strict=True)),
        'retrigger_raises_smoothed_gate_and_lung_pressure': gate_low <= before['gate_target'] <= gate_high
            and before['gate_target'] < before['gate'] < after['gate'] < 1
            and after['lung_pressure_dyn_cm2'] > before['lung_pressure_dyn_cm2'],
        'retrigger_keeps_oral_geometry_and_glottis_phase': before['target_mouth'] == after['target_mouth']
            and transitions[0]['after']['oral_tip_area_cm2'] < config['minimum_retrigger_oral_tip_area_cm2']
            <= before['oral_tip_area_cm2'] <= after['oral_tip_area_cm2'] <= tip_target
            and 0 < phase_advance < spec['pitch_hz_limits'][1] / (rate * factor),
        'natural_end_returns_to_performer_and_decays': tail is not None and ends[0] % factor == 0
            and abs((end - starts[-1]) / rate - (keys['release_seconds'] + keys['ownership_tail_seconds']))
            <= config['control_frames'] / rate + config['clock_tolerance_seconds']
            and all(np.all(candidate['target_' + key][end * factor:] == voice['shape'][key])
                    for key in OWNERSHIP['growl'])
            and np.all(candidate['gate_target'][end * factor:] == 0) and tail['call_ids'] == [0]
            and tail['gate_max'] <= config['maximum_post_end_gate']
            and tail['pcm_rms'] <= config['maximum_post_end_pcm_ratio'] * releases[-1]['pcm_rms'],
    }
    return checks, {'start_transitions': transitions, 'release_windows': releases, 'natural_end_frame': end,
                    'post_end_window': tail, 'retrigger_glottis_phase_advance_cycles': phase_advance}


if __name__ == '__main__':
    raise SystemExit(main(CASE, bounds, growl_definition_matches, driver=Path(__file__), description=__doc__,
                          extra_inputs=(WORKSPACE / 'tools/measure_alligator_growl.py',)))
