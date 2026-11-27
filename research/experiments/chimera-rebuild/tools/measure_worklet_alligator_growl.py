"""アリゲーターの growl と手動目標の復帰を実時間ブラウザで照合する。"""

import json
from pathlib import Path

import numpy as np

import measure_alligator_bellow as call
import measure_alligator_growl as growl
import measure_wasm_fixed as wasm
import measure_worklet_alligator_call as common
from measure_seal_sustain_pcm import columns
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-alligator-growl.json'


def compare_switch(case, variant, spec, points, observed, samples, state, audio, config, artifacts, execute):
    measurement = config['measurement']
    control = measurement['switch_control']
    rate, frames = case['sample_rate_hz'], case['frames']
    factor = 2
    dense = (np.array_equal(points, np.arange(frames)) and np.array_equal(samples, np.arange(frames * factor)))
    if not dense:
        raise ValueError('切り替え対照には全内部サンプルのブラウザ観測が必要です')
    scalars = {key: np.repeat(observed[key], factor)
               for key in ('gate', 'gate_target', 'oral_noise', *common.CALL_FIELDS)}
    browser_trace = state | scalars
    checks, boundaries = growl.boundary_checks(browser_trace, case, variant, factor, spec)

    # 他の操作と初期状態を維持し、切り替え前に保留された hiss だけを変更する。
    edit, = [index for index, event in enumerate(case['events']) if event['frame'] == control['edit_frame']]
    events = list(case['events'])
    old = events[edit]
    events[edit] = old | {'params': old['params'] | {'hiss': control['control_hiss']}}
    settings = artifacts / 'switch-hiss-zero-case.json'
    settings.write_text(json.dumps({'alligator_voice': case | {'events': events}}, indent=2) + '\n')
    csv, wav = (artifacts / f'switch-hiss-zero.{suffix}' for suffix in ('csv', 'wav'))
    execute([*CLI, 'render-pcm', str(settings), str(wav), str(csv), str(measurement['expected_render_quantum_frames'])])
    reference = columns(csv, frames * factor, call.CANDIDATE)
    reference_audio = read_wave(wav, rate, frames)
    frame_names = (*control['unchanged_frame_fields'], 'target_hiss', 'hiss')
    frame_deltas = {key: compare_at(observed[key], reference[key][::factor], 0, points) for key in frame_names}
    acoustic_names = (
        *control['unchanged_sample_fields'], 'glottis_area_cm2', 'glottis_voicing', 'glottis_flow_cm3_s',
        'glottis_drive_dyn_cm2', 'wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s', 'radiation_cm3_s2',
    )
    sample_deltas = {key: compare_at(state[key], reference[key], 0, samples, coordinate='internal_sample')
                     for key in acoustic_names}
    pcm = wasm.compare_pcm(audio, reference_audio, control['pcm_threshold'])
    expected_area = control['first_glottis_area_difference_internal_sample']
    first_radiation = sample_deltas['radiation_cm3_s2']['first_difference_internal_sample']
    first_bit = pcm['first_bit_difference_frame']
    first_threshold = pcm['first_frame_over_tolerance']
    checks = {
        **{f'browser_switch.{key}': result for key, result in checks.items()},
        'hiss_target_difference_at_request':
            frame_deltas['target_hiss']['first_difference_output_frame'] == control['first_target_difference_frame'],
        'hiss_smoothing_difference_at_control':
            frame_deltas['hiss']['first_difference_output_frame'] == control['first_smoothed_difference_frame'],
        'glottis_area_difference_at_control':
            sample_deltas['glottis_area_cm2']['first_difference_internal_sample'] == expected_area,
        'gate_pitch_and_other_controls_unchanged':
            all(frame_deltas[key]['passed'] for key in control['unchanged_frame_fields']),
        'lung_pressure_and_tract_geometry_unchanged':
            all(sample_deltas[key]['passed'] for key in control['unchanged_sample_fields']),
        'radiation_and_pcm_after_glottal_change': (first_radiation is not None and first_radiation >= expected_area
                                                  and first_bit is not None and first_bit >= first_radiation // factor
                                                  and first_threshold is not None and first_threshold >= first_bit),
    }
    return checks, {'browser_switch': boundaries, 'hiss_only_control': {
        'frame_differences': frame_deltas, 'internal_sample_differences': sample_deltas, 'pcm': pcm,
    }}


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    def observe(case, variant, spec, points, observed, samples, state, audio):
        if label != config['measurement']['switch_control']['variant']:
            return {}, {}
        return compare_switch(case, variant, spec, points, observed, samples, state, audio, config, artifacts, execute)

    return common.compare_variant(label, baseline, config, source, artifacts, execute, browser, module,
                                  call_name='growl', boundary_checks=growl.boundary_checks, observe=observe)


if __name__ == '__main__':
    sources = (Path(common.__file__), *(WORKSPACE / 'tools' / name for name in (
        'measure_alligator_growl.py', 'measure_alligator_bellow.py', 'measure_alligator_fixed_voice.py',
        'measure_worklet_alligator_fixed_voice.py', 'measure_seal_airway.py', 'measure_turbulence.py')))
    raise SystemExit(run(CASE, growl.CASE, compare_variant, 'alligator_growl_switch_does_not_allocate', (44100,),
                         __doc__, extra_sources=sources, creature='alligator', official_variant=common.OFFICIAL,
                         upstream_files=('crates/chimera/src/creatures/types.rs',
                                         'crates/chimera/src/sources/glottis.rs', 'crates/chimera-cli/src/render.rs')))
