"""通常画面のSqueakを固定上流と照合し、再発音時の弁の状態と実断面を調べる。"""

from pathlib import Path

import numpy as np

from measure_elephant_valve import reed_reference
from measure_worklet_midi_elephant_trumpet import main, read_performance
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-midi-elephant-squeak.json'


def read_squeak(trace, pcm, voice, starts, timing, config, spec):
    checks, observations = read_performance(trace, pcm, voice, starts, timing, config, spec)
    rate = voice['sample_rate_hz']
    mode, free, actual = (trace[key] for key in ('mode', 'reed_opening_cm2', 'trunk_valve_area_cm2'))
    active = mode > spec['threshold_mode']
    floor = np.where(active, spec['trunk_valve_area_cm2'] * (1 - mode), spec['trunk_valve_area_cm2'])
    area_tol = spec['tolerances']['area']
    parameter = spec['reed_parameters']
    drive, pitch = trace['reed_drive_dyn_cm2'], trace['lip_pitch_hz']
    predicted = reed_reference(drive, pitch, active, rate, parameter, spec['height_bounds_cm'])
    winners = []
    for start in starts:
        a, b = (start + round(t * rate) for t in config['reed_winner_window_seconds'])
        if not 0 <= a < b <= len(trace):
            raise ValueError('再発音後の弁の集計窓が出力範囲外です')
        interval = slice(a, b)
        margin = free[interval] - floor[interval]
        winners.append({'frames': [a, b], 'reed_active_frames': int(active[interval].sum()),
                        'free_opening_frames': int(np.count_nonzero(active[interval] & (margin > 0))),
                        'area_floor_frames': int(np.count_nonzero(active[interval] & (margin < 0))),
                        'tied_frames': int(np.count_nonzero(active[interval] & (margin == 0))),
                        'maximum_free_minus_floor_cm2': float(margin.max()),
                        'minimum_effective_area_cm2': float(actual[interval].min()),
                        'nasal_flow_rms_cm3_s': float(np.sqrt(np.mean(trace['nasal_cm3_s'][interval]**2)))})

    second = starts[-1]
    tick = slice(second, second + 1)
    reset = reed_reference(drive[tick], pitch[tick], active[tick], rate, parameter, spec['height_bounds_cm'])
    fields = ('gate_goal', 'gate', 'mode', 'target_mode', 'lip_pitch_hz', 'target_lip_pitch_hz', 'glottis_area_cm2',
              'glottis_phase', 'reed_drive_dyn_cm2', 'reed_height_cm', 'reed_speed_cm_s', 'reed_opening_cm2',
              'trunk_valve_area_cm2', 'trunk_valve_flow_cm3_s', 'oral_cm3_s', 'nasal_cm3_s')
    before, after = ({key: float(trace[key][i]) for key in fields}
                     | {'area_floor_cm2': float(floor[i])} for i in (second - 1, second))
    reset_state = {key: float(val[0]) for key, val in reset.items()}
    reset_state['effective_area_cm2'] = max(reset_state['opening_cm2'], after['area_floor_cm2'])
    expected = np.where(active, np.maximum(predicted['opening_cm2'], floor), floor)
    checks.update({
        'retrigger_reopens_mode_and_lowers_area_floor': (
            active[second - 1] and active[second] and after['target_mode'] == 1.0 and after['gate_goal'] == 0
            and after['mode'] > before['mode'] and 0 < after['gate'] < before['gate']
            and after['area_floor_cm2'] < before['area_floor_cm2']),
        'reed_state_carries_across_retrigger': all(
            abs(after[f'reed_{key}'] - predicted[key][second]) <= spec['reed_tolerances'][key]
            for key in ('height_cm', 'speed_cm_s'))
            and any(abs(after[f'reed_{key}'] - reset_state[key]) > spec['reed_tolerances'][key]
                    for key in ('height_cm', 'speed_cm_s')),
        'independent_opening_and_area_floor': np.max(abs(actual - expected)) <= area_tol
            and all(row['reed_active_frames'] == row['frames'][1] - row['frames'][0] for row in winners),
    })
    observations.update({'valve_area_windows': winners, 'retrigger': {'frame': second, 'before': before, 'after': after,
        'one_sample_reset': reset_state, 'effective_area_difference_from_reset_cm2':
            after['trunk_valve_area_cm2'] - reset_state['effective_area_cm2']},
        'independent_effective_area_maximum_error_cm2': float(np.max(abs(actual - expected)))})
    return checks, observations


if __name__ == '__main__':
    raise SystemExit(main(CASE, read_squeak, driver=Path(__file__), description=__doc__))
