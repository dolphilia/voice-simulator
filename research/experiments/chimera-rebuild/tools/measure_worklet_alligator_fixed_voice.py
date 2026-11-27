"""アメリカアリゲーターの固定発声を実時間ブラウザで照合する。"""

from pathlib import Path

import numpy as np

import measure_wasm_fixed as wasm
from measure_alligator_fixed_voice import (
    AREAS, CANDIDATE, CASES, FIELDS, FLOWS, PRESSURES, RADIATION, UPPER, expected_geometry, independent_checks,
)
from measure_seal_airway import first_port_step
from measure_seal_sustain_pcm import columns, first_nonzero, gate_reference, waveform
from measure_songbird_syrinx import CLI
from measure_worklet_seal_sustain import capture_health, capture_observations, compare_at, run
from measure_worklet_songbird import read_wave
from upstream_baseline import WORKSPACE


CASE = WORKSPACE / 'cases/worklet-alligator-fixed-voice.json'
SOURCE = CASES[2]
OFFICIAL = 'official-sustain-48000'
FRAME_FIELDS = ('gate_target', 'gate', 'oral_noise', 'decimated', 'dc_removed')
SAMPLE_FIELDS = (*FIELDS[3:], 'oral_tip_area_cm2')
OBSERVATION_FIELDS = (*FRAME_FIELDS, *(f'{name}_{phase}' for phase in range(2) for name in SAMPLE_FIELDS))


def browser_samples(observed, points, factor, fields=SAMPLE_FIELDS):
    indices = (points[:, None] * factor + np.arange(factor)).ravel()
    data = {key: np.column_stack([observed[f'{key}_{phase}'] for phase in range(factor)]).ravel()
            for key in fields}
    return indices, data


def browser_physics(label, source, spec, measurement, observed, points, factor, audio):
    rate = source['sample_rate_hz'] * factor
    tolerance = spec['tolerances']
    geometry = expected_geometry(rate, source['shape'], spec)
    samples, state = browser_samples(observed, points, factor)
    gate_config = {'control_frames': spec['control_frames'], 'attack_seconds': spec['gate_attack_seconds'],
                   'release_seconds': spec['gate_release_seconds']}
    gate, target = gate_reference(source, gate_config)
    pressure = np.repeat(gate[points], factor) * (source['shape']['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2'])
    comparisons = {
        'gate': compare_at(observed['gate'], gate[points], tolerance['gate'], points),
        'gate_target': compare_at(observed['gate_target'], target[points], tolerance['gate'], points),
        'lung_pressure': compare_at(state[PRESSURES[0]], pressure, tolerance['pressure_dyn_cm2'], samples,
                                    coordinate='internal_sample'),
    }
    for key in ('oral_tip_area_cm2', 'velum_area_cm2'):
        comparisons[key] = compare_at(state[key], np.full(len(samples), geometry[key]), tolerance['area_cm2'],
                                      samples, coordinate='internal_sample')

    # 立ち上がりの全内部サンプルを含むため、最初の非ゼロを直接読む。
    arrivals = {}
    for key in measurement['arrival_fields']:
        index = first_nonzero(state[key])
        arrivals[key] = None if index is None else int(samples[index])
    expected = dict(zip(measurement['arrival_fields'],
                        measurement['expected_first_internal_samples'][label], strict=True))
    checks = {
        'browser_arrival_frames': arrivals == expected,
        'browser_oral_noise_registration': bool(np.all(observed['oral_noise'] == (geometry['oral_noise_cell'] is not None))),
    }
    first = arrivals[PRESSURES[0]]
    if first is not None:
        at = int(np.searchsorted(samples, first))
        length, area, _, _ = spec['tubes']['trachea']
        physical = spec | {'trachea_length_cm': length, 'trachea_area_cm2': area}
        flow, inlet = first_port_step(float(pressure[at]), rate, geometry['trachea_cells'], physical)
        checks['browser_first_port_step'] = (
            abs(state['lung_flow_cm3_s'][at] - flow) <= tolerance['initial_flow_cm3_s']
            and abs(state['trachea_inlet_pressure_dyn_cm2'][at] - inlet) <= tolerance['initial_pressure_dyn_cm2'])
        checks['browser_first_total_radiation'] = first_nonzero(state[RADIATION]) == int(
            np.searchsorted(samples, arrivals['wall_cm3_s']))
    if source['shape']['hiss'] == 1 or first is None:
        gap = spec['static_gap_hiss_cm2'] if source['shape']['hiss'] == 1 else spec['static_gap_min_cm2']
        area = -gap * np.expm1(-(samples + 1) / (rate * spec['static_gap_tau_seconds']))
        checks['browser_only_static_gap'] = bool(np.all(state['glottis_voicing'] == 0)
                                                  and np.max(np.abs(state['glottis_area_cm2'] - area))
                                                  <= tolerance['static_gap_cm2'])
    if first is None:
        checks['browser_silent'] = (not np.any(audio)
                                     and all(not np.any(state[key]) for key in (*PRESSURES, *FLOWS, RADIATION)))
    checks['browser_independent_physics'] = all(result['passed'] for result in comparisons.values())
    return {key: bool(value) for key, value in checks.items()}, {
        'observed_first_internal_samples': arrivals, 'geometry_reference': geometry,
        'browser_independent': comparisons, 'first_pcm_frame': first_nonzero(audio),
        'nasal_peak_sampled_cm3_s': float(np.max(np.abs(state['nasal_cm3_s']))),
        'glottis_voicing_peak_sampled': float(np.max(state['glottis_voicing'])),
    }


def compare_variant(label, baseline, config, source, artifacts, execute, browser, module):
    spec, m = source['measurement'], config['measurement']
    variant = next(item for item in spec['variants'] if item['id'] == label)
    base = source['alligator_voice']
    input_ = base | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
    input_['shape'] = base['shape'] | variant.get('shape', {})
    rate, frames = (input_[key] for key in ('sample_rate_hz', 'frames'))
    factor = 2 if rate <= 60000 else 1
    quantum = m['expected_render_quantum_frames']
    upper_dir = baseline / 'artifacts' / label
    replay_path = artifacts / f'{label}-case.json'
    if (wasm.read_json(upper_dir / 'case.json')['alligator_voice'] != input_
            or wasm.read_json(replay_path) != {
                'id': f'worklet-alligator-{label}', 'upstream_revision': config['upstream_revision'],
                'alligator_voice': input_,
            }):
        raise ValueError(f'{label} の固定上流・登録・ブラウザ書き出しの入力が一致しません')

    wave, trace = (artifacts / f'{label}-native.{ext}' for ext in ('wav', 'csv'))
    execute([*CLI, 'render-pcm', str(replay_path), str(wave), str(trace), str(quantum)])
    native, audio = (read_wave(path, rate, frames) for path in (wave, artifacts / f'{label}.wav'))
    candidate = columns(trace, frames * factor, CANDIDATE)
    upper = columns(upper_dir / 'upstream.csv', frames * factor, UPPER)
    upper_pcm = upper['pcm_f32'][factor - 1::factor].astype(np.float32)
    tolerance = spec['tolerances']
    cli_pcm = wasm.compare_pcm(audio, native, m['cli_pcm_absolute_tolerance'])
    upper_pcm_result = wasm.compare_pcm(audio, upper_pcm, tolerance['pcm_f32'])
    upper_pcm_result['different_bits'] = int(np.count_nonzero(audio.view('u4') != upper_pcm.view('u4')))

    report, points, clock, observed = capture_observations(label, m, artifacts, frames, OBSERVATION_FIELDS)
    last_samples = (points + 1) * factor - 1
    cli_states = {key: compare_at(observed[key], candidate[key][last_samples],
                                 m['cli_state_absolute_tolerance'], points)
                  for key in ('gate', 'decimated', 'dc_removed')}
    upper_limits = ({key: tolerance['pressure_dyn_cm2'] for key in PRESSURES}
                    | {key: tolerance['flow_cm3_s'] for key in FLOWS}
                    | {key: tolerance['area_cm2'] for key in AREAS}
                    | {f'glottis_{key}': tolerance[key] for key in ('voicing', 'phase', 'f0_hz')}
                    | {RADIATION: tolerance['radiation_cm3_s2']})
    upper_states = {'gate': compare_at(observed['gate'], upper['gate'][last_samples], tolerance['gate'], points)}
    for phase in range(factor):
        idx = points * factor + phase
        for key in FIELDS[3:]:
            name = f'{key}_{phase}'
            cli_states[name] = compare_at(observed[name], candidate[key][idx], m['cli_state_absolute_tolerance'], points)
            upper_states[name] = compare_at(observed[name], upper[key][idx], upper_limits[key], points)

    physical_checks, physical = browser_physics(label, input_, spec, m, observed, points, factor, audio)
    geometry = physical['geometry_reference']
    native_checks, native_comparisons, _ = independent_checks(candidate, audio, input_, rate * factor, factor,
                                                              geometry, spec)
    health, timing = capture_health(config, report, browser, module, rate, frames, factor)
    checks = {
        'browser_cli_pcm_bits': cli_pcm['first_bit_difference_frame'] is None,
        'fixed_upstream_pcm': upper_pcm_result['first_frame_over_tolerance'] is None,
        'cli_states': all(item['passed'] for item in cli_states.values()),
        'fixed_upstream_states': all(item['passed'] for item in upper_states.values()),
        'observation_clock': (np.array_equal(clock[:, 0], points) and np.array_equal(clock[:, 1], last_samples)
                              and all(np.array_equal(values['frame'][last_samples], points)
                                      for values in (candidate, upper))),
        'unused_internal_slots_zero': factor == 2 or all(np.all(observed[f'{key}_1'] == 0) for key in SAMPLE_FIELDS),
        'native_trace_and_browser_pcm_independent': all(native_checks.values()),
        **physical_checks, **health,
    }
    official_pcm, trim = None, None
    if label == OFFICIAL:
        official = waveform(baseline / 'artifacts/official-cli/alligator.wav',
                            input_ | {'frames': spec['official_demo_frames']})[:frames]
        official_pcm = wasm.compare_pcm(audio, official, tolerance['pcm_f32'])
        checks['official_prefix'] = official_pcm['first_frame_over_tolerance'] is None
        short_frames = spec['endpoint_arrival']['startup_untrimmed_output_frames']
        untrimmed = columns(upper_dir / 'upstream-startup-untrimmed.csv', short_frames * factor, UPPER)
        trim = {}
        for key, earliest in m['standard_untrimmed_endpoint_samples'].items():
            normal = physical['observed_first_internal_samples'][key]
            original = first_nonzero(untrimmed[key])
            checks[f'control_cleanup_delay.{key}'] = original == earliest and normal is not None and normal > original
            trim[key] = {'control_cleanup': normal, 'without_control_block': original,
                         'delay_internal_samples': None if normal is None or original is None else normal - original}
        steady, tail = (audio[slice(*spec[f'{key}_window_output_frames'])].astype(float) for key in ('sustain', 'tail'))
        ratio = float(np.sqrt(np.mean(tail**2)) / np.sqrt(np.mean(steady**2)))
        checks['decay_after_gate_release'] = ratio <= spec['tail_to_sustain_max_ratio']
        physical['tail_to_sustain_rms_ratio'] = ratio

    return {
        'checks': checks, 'frames': frames, 'rate_hz': rate, 'factor': factor, 'observations': len(points),
        'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm_result, 'official_pcm': official_pcm,
        'cli_states': cli_states, 'upstream_states': upper_states, 'native_independent': native_comparisons,
        'first_cli_upstream_difference_internal_sample': {
            key: wasm.first_index(candidate[key] != upper[key]) for key in FIELDS[2:]},
        'control_cleanup': trim, **physical, **timing,
    }


if __name__ == '__main__':
    sources = (Path(__file__).resolve(), *(WORKSPACE / 'tools' / name for name in (
        'measure_alligator_fixed_voice.py', 'measure_seal_airway.py')))
    raise SystemExit(run(CASE, SOURCE, compare_variant, 'alligator_fixed_render_does_not_allocate', (48000,), __doc__,
                         extra_sources=sources, creature='alligator', official_variant=OFFICIAL,
                         reference_files=(f'artifacts/{OFFICIAL}/upstream-startup-untrimmed.csv',),
                         upstream_files=('crates/chimera/src/airway/network.rs', 'crates/chimera/src/creatures/build.rs',
                                         'crates/chimera/tests/denormals.rs')))
