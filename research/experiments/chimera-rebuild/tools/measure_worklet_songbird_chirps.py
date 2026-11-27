"""鳴禽chirpsのキー順と波形を実時間ブラウザ、固定上流、独立対照で照合する。"""

from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np

from measure_songbird_calls import CASE as SOURCE
from measure_songbird_flute import control_reference, trace
from measure_songbird_sustain_pcm import FIELDS
from measure_songbird_syrinx import CLI
from measure_wasm_fixed import compare_pcm
from measure_worklet_songbird import read_wave
from measure_worklet_songbird_call import first_synthesis_differences, run
from upstream_baseline import WORKSPACE

CASE = WORKSPACE / 'cases/worklet-songbird-chirps.json'


def replay_targets(label, source, targets, block, quantum, artifacts, execute):
    frames, rate = (source[key] for key in ('frames', 'sample_rate_hz'))
    events = [
        {'frame': frame, 'gate': float(targets['gate_target'][frame]),
         'controls': {key: float(targets[f'target_{key}'][frame]) for key in source['controls']}}
        for frame in range(0, frames, block)
    ]
    config = {'songbird_voice': {
        'sample_rate_hz': rate, 'frames': frames, 'level': source['level'],
        'controls': source['controls'], 'events': events,
    }}
    case, wave, trace_path = (artifacts / f'{label}.{ext}' for ext in ('json', 'wav', 'csv'))
    case.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    execute([*CLI, 'render-pcm', str(case), str(wave), str(trace_path), str(quantum)])
    return read_wave(wave, rate, frames), trace(trace_path, frames, FIELDS)


def evaluate(points, states, audio, source, measurement, *, declared, definitions, control, artifacts, execute, **_context):
    limits = measurement['chirps']
    tol = measurement['independent_control_absolute_tolerance']
    block = limits['control_interval_frames']
    rate, frames = (source[key] for key in ('sample_rate_hz', 'frames'))
    request = next(event['frame'] for event in source['events'] if 'play_call' in event)
    first = math.ceil(request / block) * block
    lo, hi = limits['overlap_window_seconds']
    overlap = first + math.ceil(Fraction(str(lo)) * rate / block) * block
    elapsed = (overlap - first) / rate
    overlap_index = int(np.searchsorted(points, overlap))
    ids = states['call_id']
    changes = np.flatnonzero(ids != np.r_[0, ids[:-1]])
    transitions = [[int(points[i]), int(ids[i])] for i in changes]
    before_key, first_key = (int(np.searchsorted(points, frame)) for frame in (first - 1, first))

    definition = definitions['chirps']
    chronological = definition | {'keys': sorted(definition['keys'], key=lambda key: key['t'])}
    sorted_controls = control_reference(source, {'chirps': chronological}, control)
    comparisons = {}
    for field in ('gate_target', 'target_pitch_hz', 'gate', 'pitch_hz'):
        reference = sorted_controls[field][points]
        differences = np.flatnonzero(abs(states[field] - reference) > tol)
        index = int(differences[0]) if differences.size else None
        comparisons[field] = {
            'first_difference_frame': int(points[index]) if index is not None else None,
            'first_declared': float(states[field][index]) if index is not None else None,
            'first_chronological': float(reference[index]) if index is not None else None,
            'at_overlap_declared': float(states[field][overlap_index]),
            'at_overlap_chronological': float(reference[overlap_index]),
        }

    quantum = measurement['expected_render_quantum_frames']
    declared_wave, declared_trace = replay_targets('declared-targets', source, declared, block, quantum, artifacts, execute)
    sorted_wave, sorted_trace = replay_targets('chronological-targets', source, sorted_controls, block, quantum, artifacts, execute)
    replay_pcm = compare_pcm(audio, declared_wave, limits['declared_replay_pcm_tolerance'])
    order_pcm = compare_pcm(sorted_wave, declared_wave, limits['order_replay_pcm_difference_threshold'])
    pcm_first = order_pcm['first_frame_over_tolerance']
    gate_first = comparisons['gate_target']['first_difference_frame']
    pcm_delay = pcm_first - gate_first if pcm_first is not None and gate_first is not None else None
    gate = comparisons['gate_target']
    pitch = comparisons['target_pitch_hz']
    peak = float(np.max(abs(audio)))
    checks = {
        'measures_every_control_boundary': np.array_equal(points[points % block == 0], np.arange(0, frames, block)),
        'requested_start_and_natural_end': transitions == [[request, limits['call_id']],
                                                            [limits['expected_natural_end_frame'], 0]],
        'first_key_on_registered_boundary': bool(
            first == limits['expected_first_control_frame']
            and points[before_key] == first - 1 and points[first_key] == first
            and states['target_pitch_hz'][before_key] == source['controls']['pitch_hz']
            and abs(states['target_pitch_hz'][first_key] - limits['first_pitch_target_hz']) <= tol),
        'overlap_in_window': bool(points[overlap_index] == overlap and lo <= elapsed <= hi),
        'declared_gate_and_order_effect': (abs(gate['at_overlap_declared'] - limits['gate_in_overlap']) <= tol
                                           and abs(gate['at_overlap_declared'] - gate['at_overlap_chronological'])
                                           >= limits['minimum_order_effect_on_gate']),
        'pitch_order_effect': abs(pitch['at_overlap_declared'] - pitch['at_overlap_chronological']) >=
                              limits['minimum_order_effect_on_pitch_hz'],
        'target_order_divergence': all(comparisons[key]['first_difference_frame'] == value
                                       for key, value in limits['expected_first_order_difference'].items()),
        'pcm_has_a_signal': peak >= limits['minimum_pcm_peak'],
        'declared_targets_replay_browser_pcm': replay_pcm['first_frame_over_tolerance'] is None,
        'ordering_changes_pcm_after_target_change': (pcm_delay is not None
                                                    and 0 <= pcm_delay <= limits['maximum_order_pcm_delay_frames']
                                                    and order_pcm['maximum_absolute_error'] >=
                                                    limits['minimum_order_pcm_peak_difference']),
    }
    return checks, {
        'events': {'call_transitions': transitions, 'first_control_frame': first, 'overlap_frame': overlap,
                   'overlap_elapsed_seconds': elapsed, 'control_order_comparison': comparisons},
        'peak_pcm': peak, 'declared_targets_replay_pcm': replay_pcm, 'target_order_pcm': order_pcm,
        'target_order_pcm_delay_frames': pcm_delay,
        'target_order_first_synthesis_differences': first_synthesis_differences(
            declared_trace, sorted_trace, 4 if rate <= 60000 else 2),
    }


if __name__ == '__main__':
    raise SystemExit(run(CASE, SOURCE, 'definitions.json', evaluate, Path(__file__).resolve(), __doc__))
