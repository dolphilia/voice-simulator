"""アメリカアリゲーターの bellow を実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_alligator_bellow as call
import measure_worklet_alligator_call as common
from measure_alligator_fixed_voice import CASES
from measure_worklet_seal_sustain import run
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-alligator-bellow.json'


def dense_measurements(observed, points, samples, state, case, variant, factor, spec, measurement):
    stop, tick = variant['end'], measurement['manual_stop']['first_smoothing_frame']
    edit, override = variant['manual_edit'], variant['gate_override']
    manual_patch, = [event['params'] for event in case['events'] if event['frame'] == edit]
    control_frames = spec['control_frames']
    gate_tick = (override + control_frames - 1) // control_frames * control_frames
    gate, = [event['gate'] for event in case['events'] if event['frame'] == override]
    cycle_state = state | {'chaos': np.repeat(observed['chaos'], factor)}
    cycles = call.cycle_comparison(cycle_state, case['sample_rate_hz'] * factor, spec['cycle_model'],
                                   spec['seeds']['cycles'], variant['first_control'] * factor,
                                   variant.get('cycle_windows', []))

    switches = (np.flatnonzero(np.diff(observed['oral_noise']) != 0) + 1) * factor
    threshold = spec['oral_noise_threshold_cm2']
    area = state['oral_tip_area_cm2']
    noise = []
    for sample in switches:
        registered = bool(observed['oral_noise'][sample // factor])
        block = area[sample:sample + control_frames * factor]
        crossed = np.flatnonzero((block < threshold) == registered)
        crossing = int(sample + crossed[0]) if crossed.size else None
        noise.append({
            'registered': registered, 'switch_internal_sample': int(sample), 'first_area_crossing': crossing,
            'advance_internal_samples': None if crossing is None else crossing - int(sample),
            'area_at_switch_cm2': float(block[0]), 'area_at_block_end_cm2': float(block[-1]),
        })

    checks = {
        'dense_observation': (np.array_equal(points, np.arange(case['frames']))
                              and np.array_equal(samples, np.arange(case['frames'] * factor))),
        'browser_cycles_independent': cycles['period_scale']['passed'],
        'manual_unowned_targets_at_edit': all(observed['target_' + key][edit] == manual_patch[key]
                                              for key in ('pressure_cm_h2o', 'nostrils')),
        'call_targets_retained_at_edit': all(observed['target_' + key][edit] == observed['target_' + key][edit - 1]
                                             and observed['target_' + key][edit] != manual_patch[key]
                                             for key in call.OWNED),
        'manual_gate_at_control_tick': bool(observed['gate_target'][gate_tick] == gate),
        'targets_return_at_stop': all(observed['target_' + key][stop] == manual_patch[key]
                                      for key in call.OWNED),
        'smoothing_resumes_at_control_tick': all(np.all(observed[key][stop:tick] == observed[key][stop - 1])
                                                 and observed[key][tick] != observed[key][stop - 1]
                                                 for key in call.OWNED),
        'oral_noise_switches': switches.tolist() == measurement['manual_stop']['noise_switch_internal_samples'],
        'oral_noise_switch_precedes_area': ([item['registered'] for item in noise] == [True, False]
                                           and all((item['advance_internal_samples'] or 0) > 0 for item in noise)),
    }
    snapshots = {str(frame): {key: float(observed[key][frame]) for key in
                              (*call.PARAMETERS, *call.TARGETS, 'gate_target', 'call_id')}
                 for frame in (edit - 1, edit, override, gate_tick, stop - 1, stop, tick - 1, tick)}
    return {key: bool(value) for key, value in checks.items()}, {
        'cycles': cycles, 'manual_state': snapshots, 'requested_stop_frame': stop, 'first_smoothing_frame': tick,
        'oral_noise': noise, 'oral_noise_threshold_cm2': threshold,
    }


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    measurement = config['measurement']

    def observe(case, variant, spec, points, observed, samples, state, _audio):
        if label != measurement['dense_cycle_variant']:
            return {}, {'dense_browser': None}
        factor = len(samples) // len(points)
        checks, details = dense_measurements(observed, points, samples, state, case, variant, factor, spec, measurement)
        return checks, {'dense_browser': details}

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  call_name='bellow', boundary_checks=call.boundary_checks, observe=observe)


if __name__ == '__main__':
    sources = (CASES[2], Path(common.__file__), *(WORKSPACE / 'tools' / name for name in (
        'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py', 'measure_worklet_alligator_fixed_voice.py',
        'measure_seal_airway.py', 'measure_turbulence.py')))
    raise SystemExit(run(CASE, call.CASE, compare_variant, 'alligator_bellow_render_does_not_allocate', (44100,),
                         __doc__, extra_sources=sources, creature='alligator', official_variant=common.OFFICIAL,
                         upstream_files=('crates/chimera/src/sources/glottis.rs', 'crates/chimera-cli/src/render.rs')))
