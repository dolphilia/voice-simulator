"""固定姿勢のアリゲーターを上流の気道と独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy

from measure_seal_airway import first_port_step
from measure_seal_sustain_pcm import columns, first_nonzero, gate_reference, independent_output, waveform
from measure_songbird_syrinx import CLI, compare, read
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASES = {1: WORKSPACE / 'cases/alligator-fixed-voice.json', 2: WORKSPACE / 'cases/alligator-fixed-voice-v2.json'}
PROBE = WORKSPACE / 'tools/upstream_alligator_probe.rs'
PRESSURES = ('lung_pressure_dyn_cm2', 'trachea_inlet_pressure_dyn_cm2', 'trachea_end_pressure_dyn_cm2',
             'pharynx_pressure_dyn_cm2', 'glottis_drive_dyn_cm2')
FLOWS = ('lung_flow_cm3_s', 'glottis_flow_cm3_s', 'velum_flow_cm3_s', 'wall_cm3_s', 'oral_cm3_s', 'nasal_cm3_s')
AREAS = ('glottis_area_cm2', 'velum_area_cm2')
RADIATION = 'radiation_cm3_s2'
FIELDS = ('sample', 'frame', 'gate', PRESSURES[0], FLOWS[0], *PRESSURES[1:], AREAS[0], FLOWS[1],
          'glottis_voicing', 'glottis_phase', 'glottis_f0_hz', AREAS[1], *FLOWS[2:], RADIATION)
CANDIDATE = (*FIELDS, 'decimated', 'dc_removed', 'pcm_f32')
UPPER = (*FIELDS, 'shadow_area_cm2', 'pcm_f32')


def expected_geometry(rate, shape, spec):
    dx_min = spec['sound_speed_cm_s'] / rate / spec['cfl']
    counts = {name + '_cells': min(limit, max(3, int(length / (coarse * dx_min))))
              for name, (length, _, coarse, limit) in spec['tubes'].items()}
    tip = 0.05 + 12.0 * shape['mouth']
    count = counts['oral_cells']
    positions = (np.arange(count - 1) + 0.5) / count
    eligible = np.flatnonzero(positions > spec['oral_tip_from'])
    noise_cell = int(eligible[0]) if eligible.size and tip < spec['oral_noise_threshold_cm2'] else None
    courant = max(spec['sound_speed_cm_s'] / rate / (entry[0] / counts[name + '_cells'])
                  for name, entry in spec['tubes'].items())
    courant = max(courant, spec['sound_speed_cm_s'] / rate / spec['lung_length_cm'])
    return counts | {'oral_tip_area_cm2': tip, 'velum_area_cm2': 0.4 + 1.6 * shape['nostrils'],
                     'oral_noise_cell': noise_cell, 'courant': courant}


def check_geometry(label, data, expected, frames, factor, rate, spec):
    info = data['geometry']
    tolerance = spec['tolerances']['geometry']
    checks = {'inspect_rate': data['internal_rate_hz'] == rate and data['decimation_factor'] == factor,
              'inspect_rows': data['rows'] == frames * factor,
              'inspect_control': data['control_frames'] == spec['control_frames']}
    checks.update({name: info[name] == value if value is None or isinstance(value, int)
                   else abs(info[name] - value) <= tolerance for name, value in expected.items()})
    return {f'geometry.{label}.{name}': passed for name, passed in checks.items()}


def independent_checks(trace, pcm, case, rate, factor, expected, spec):
    tolerance = spec['tolerances']
    gate_settings = {'control_frames': spec['control_frames'], 'attack_seconds': spec['gate_attack_seconds'],
                     'release_seconds': spec['gate_release_seconds']}
    gates, _ = gate_reference(case, gate_settings)
    lung = np.repeat(gates, factor) * (case['shape']['pressure_cm_h2o'] * spec['cm_h2o_to_dyn_cm2'])
    flow_keys = (*FLOWS, RADIATION)
    arrivals = {key: first_nonzero(trace[key]) for key in (*PRESSURES, *flow_keys)}
    pressure_drop = trace[PRESSURES[2]] - trace[PRESSURES[3]]
    comparisons = {
        'gate': compare(trace['gate'], np.repeat(gates, factor), tolerance['gate']),
        'lung_pressure': compare(trace[PRESSURES[0]], lung, tolerance['pressure_dyn_cm2']),
        'previous_state_drive': compare(trace[PRESSURES[4]], np.r_[0.0, pressure_drop[:-1]],
                                        tolerance['pressure_dyn_cm2']),
        'fixed_velum': compare(trace[AREAS[1]], np.full_like(lung, expected['velum_area_cm2']),
                               tolerance['area_cm2']),
    }
    total_flow = trace['wall_cm3_s'] + trace['oral_cm3_s'] + trace['nasal_cm3_s']
    derivative = np.diff(total_flow, prepend=0.0) * rate
    comparisons['sum_then_derivative'] = compare(trace[RADIATION], derivative, tolerance['radiation_cm3_s2'])
    raw = trace[RADIATION]
    decimated, filtered, wanted = independent_output(raw, case['sample_rate_hz'], factor,
                                                    case['level'], spec['output'])
    outputs = slice(factor - 1, None, factor)
    comparisons['decimated'] = compare(trace['decimated'][outputs], decimated, tolerance['radiation_cm3_s2'])
    comparisons['dc_removed'] = compare(trace['dc_removed'][outputs], filtered, tolerance['dc_removed'])
    comparisons['pcm'] = compare(pcm, wanted, tolerance['pcm_f32'])
    start = first_nonzero(lung)
    checks = {'bounded_pcm': bool(np.all(np.abs(pcm) <= 1))}
    earliest_endpoints = None
    if start is None:
        checks['silent_pressure_flow_radiation_and_pcm'] = not any(arrival is not None for arrival in arrivals.values()) and not np.any(pcm)
    else:
        t, p, o, n = (expected[name + '_cells'] for name in ('trachea', 'pharynx', 'oral', 'nasal'))
        glottis = start + t
        arrival_expected = (start, start, start, glottis - 1, glottis, glottis,
                            glottis, glottis + p, glottis + 1)
        names = (PRESSURES[0], FLOWS[0], PRESSURES[1], *PRESSURES[2:], *FLOWS[1:4])
        checks.update({f'onset.{name}': arrivals[name] == wanted
                       for name, wanted in zip(names, arrival_expected, strict=True)})
        earliest_endpoints = {'oral_cm3_s': glottis + p + o - 1, 'nasal_cm3_s': glottis + p + n - 1}
        policy = spec.get('endpoint_arrival')
        delay = 0 if policy is None else policy['maximum_delay_control_blocks'] * spec['control_frames'] * factor
        checks.update({f'onset.{name}': arrivals[name] is not None and earliest <= arrivals[name] <= earliest + delay
                       for name, earliest in earliest_endpoints.items()})
        checks['onset.total_radiation'] = arrivals[RADIATION] == glottis + 1
        length, area, _, _ = spec['tubes']['trachea']
        physical = spec | {'trachea_length_cm': length, 'trachea_area_cm2': area}
        flow, pressure = first_port_step(float(lung[start]), rate, t, physical)
        comparisons['first_lung_flow'] = compare(trace[FLOWS[0]][start:start+1], np.array([flow]),
                                                 tolerance['initial_flow_cm3_s'])
        comparisons['first_inlet_pressure'] = compare(trace[PRESSURES[1]][start:start+1], np.array([pressure]),
                                                      tolerance['initial_pressure_dyn_cm2'])
    hiss = case['shape']['hiss']
    if start is None or hiss == 1.0:
        gap = spec['static_gap_hiss_cm2'] if hiss else spec['static_gap_min_cm2']
        time = (trace['sample'] + 1) / rate
        area = -gap * np.expm1(-time / spec['static_gap_tau_seconds'])
        comparisons['static_gap_exponential'] = compare(trace[AREAS[0]], area, tolerance['static_gap_cm2'])
    checks = {key: bool(passed) for key, passed in checks.items()}
    checks.update({f'independent.{key}': data['passed'] for key, data in comparisons.items()})
    observations = {'first_internal_sample': arrivals, 'first_pcm_frame': first_nonzero(pcm),
                    'pressure_first_sample': start,
                    'earliest_endpoint_start': earliest_endpoints,
                    'peak_glottis_flow_cm3_s': float(np.max(np.abs(trace[FLOWS[1]]))),
                    'peak_glottis_voicing': float(np.max(trace['glottis_voicing'])),
                    'peak_velum_flow_cm3_s': float(np.max(np.abs(trace[FLOWS[2]]))),
                    'peak_nasal_radiation_cm3_s': float(np.max(np.abs(trace['nasal_cm3_s']))),
                    'peak_wall_radiation_cm3_s': float(np.max(np.abs(trace['wall_cm3_s'])))}
    return checks, comparisons, observations


def compare_untrimmed_startup(case, name, spec, folder, probe, execute, factor, observation):
    policy = spec['endpoint_arrival']
    frames = policy['startup_untrimmed_output_frames']
    short = case | {'frames': frames, 'events': [event for event in case['events'] if event['frame'] < frames]}
    capsule = folder / 'startup-case.json'
    trace_csv = folder / 'upstream-startup-untrimmed.csv'
    capsule.write_text(json.dumps({'alligator_voice': short}, indent=2) + '\n')
    execute([str(probe), str(capsule), '--skip-network-block'], cwd=UPSTREAM, stdout=trace_csv)
    series = columns(trace_csv, frames * factor, UPPER)
    notes, checks = {}, {}
    for key, earliest in observation['earliest_endpoint_start'].items():
        actual = observation['first_internal_sample'][key]
        untrimmed = first_nonzero(series[key])
        checks[f'untrimmed.{key}.first_arrival'] = untrimmed == earliest
        if name == policy['require_trim_delay_in']:
            checks[f'untrimmed.{key}.control_delay'] = actual is not None and untrimmed is not None and actual > untrimmed
        notes[key] = {'physical_earliest_sample': earliest, 'normal_first_sample': actual,
                      'untrimmed_first_sample': untrimmed}
    observation['startup_untrimmed'] = notes
    return checks


def measure_variant(case, variant, spec, folder, probe, official_wave, execute):
    folder.mkdir()
    settings = folder / 'case.json'
    case = case | {key: variant[key] for key in ('sample_rate_hz', 'frames', 'events') if key in variant}
    case['shape'] = case['shape'] | variant.get('shape', {})
    settings.write_text(json.dumps({'alligator_voice': case}, indent=2) + '\n')
    inspect, inspect_upper, upper_csv = (folder / name for name in ('inspect.json', 'upstream-inspect.json', 'upstream.csv'))
    execute([*CLI, 'inspect', str(settings)], stdout=inspect)
    execute([str(probe), str(settings), '--inspect'], cwd=UPSTREAM, stdout=inspect_upper)
    execute([str(probe), str(settings)], cwd=UPSTREAM, stdout=upper_csv)
    products = []
    for block in spec['host_block_frames']:
        wav, csv = (folder / f'pcm-{block}.{suffix}' for suffix in ('wav', 'csv'))
        execute([*CLI, 'render-pcm', str(settings), str(wav), str(csv), str(block)])
        products.append((wav, csv))
    wav, csv = products[0]
    frames, output_rate = case['frames'], case['sample_rate_hz']
    factor = 1 if output_rate > 60000 else 2
    rate, rows = factor * output_rate, factor * frames
    pcm = waveform(wav, case)
    candidate, upstream = columns(csv, rows, CANDIDATE), columns(upper_csv, rows, UPPER)
    output = slice(factor - 1, None, factor)
    upper_pcm = upstream['pcm_f32'][output].astype(np.float32)
    indexes = np.arange(rows)
    checks = {'samples_and_output_frames': all(np.array_equal(trace['sample'], indexes)
              and np.array_equal(trace['frame'], indexes // factor) for trace in (candidate, upstream)),
              'host_block_invariance': all(sha256(w) == sha256(wav) and sha256(c) == sha256(csv) for w, c in products),
              'wav_matches_trace': np.array_equal(pcm.view('u4'), candidate['pcm_f32'][output].astype(np.float32).view('u4'))}
    expected = expected_geometry(rate, case['shape'], spec)
    geometry = {'candidate': read(inspect), 'upstream': read(inspect_upper)}
    for label, info in geometry.items():
        checks.update(check_geometry(label, info, expected, frames, factor, rate, spec))
    tolerance = spec['tolerances']
    limits = {key: tolerance['pressure_dyn_cm2'] for key in PRESSURES}
    limits.update({key: tolerance['flow_cm3_s'] for key in FLOWS})
    limits.update({key: tolerance['area_cm2'] for key in AREAS})
    limits.update({'gate': tolerance['gate'], RADIATION: tolerance['radiation_cm3_s2'],
                   **{f'glottis_{key}': tolerance[key] for key in ('voicing', 'phase', 'f0_hz')}})
    direct = {key: compare(candidate[key], upstream[key], bound) for key, bound in limits.items()}
    direct['shadow_area_cm2'] = compare(upstream['shadow_area_cm2'], np.zeros(rows), tolerance['shadow_area_cm2'])
    direct['pcm_f32'] = compare(pcm, upper_pcm, tolerance['pcm_f32'])
    independent, comparisons, observation = independent_checks(candidate, pcm, case, rate, factor, expected, spec)
    if spec.get('endpoint_arrival') and observation['earliest_endpoint_start'] is not None:
        checks.update(compare_untrimmed_startup(case, variant['id'], spec, folder, probe, execute, factor, observation))
    if variant['id'] == 'official-sustain-48000':
        official = waveform(official_wave, case | {'frames': spec['official_demo_frames']})[:frames]
        checks['probe_matches_official_bits'] = np.array_equal(upper_pcm.view('u4'), official.view('u4'))
        direct['official_prefix'] = compare(pcm, official, tolerance['pcm_f32'])
        sustain, tail = (pcm[slice(*spec[f'{key}_window_output_frames'])].astype(float)
                         for key in ('sustain', 'tail'))
        sustain_rms, tail_rms = (float(np.sqrt(np.mean(window**2))) for window in (sustain, tail))
        ratio = tail_rms / sustain_rms if sustain_rms else None
        checks['decay_after_gate_release'] = ratio is not None and ratio <= spec['tail_to_sustain_max_ratio']
        observation['release'] = {'sustain_rms': sustain_rms, 'tail_rms': tail_rms, 'tail_to_sustain_ratio': ratio}
    checks.update(independent)
    checks.update({f'upstream.{key}': value['passed'] for key, value in direct.items()})
    return {'checks': checks, 'frames': frames, 'internal_rate_hz': rate, 'geometry': expected,
            'pcm_different_bits': int(np.count_nonzero(pcm.view('u4') != upper_pcm.view('u4'))),
            'upstream_comparison': direct, 'independent_comparison': comparisons, 'observations': observation}


def measure(config, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'creature_realtime',
             '--test', 'golden_creatures', '--test', 'denormals'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    official = artifacts / 'official-cli'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render', 'creature',
             'alligator', str(official), '--float'], cwd=UPSTREAM, stdout=artifacts / 'upstream-cli.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants = {}, {}
    spec = config['measurement']
    for variant in spec['variants']:
        name = variant['id']
        result = measure_variant(config['alligator_voice'], variant, spec, artifacts / name,
                                 probe, official / 'alligator.wav', execute)
        variants[name] = result
        checks.update({f'{name}.{key}': value for key, value in result['checks'].items()})
    return {'checks': checks, 'variants': variants}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--revision', choices=CASES, type=int, default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = CASES[args.revision]
    config = read(case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'],
                                                                          cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    baseline = WORKSPACE / 'runs/seal-chug-before-alligator-1/manifest.json'
    if read(baseline)['status'] != 'pass':
        raise SystemExit('アザラシの基準ケースが不合格です')
    names = ('LICENSE', 'Cargo.lock', 'crates/chimera/src/physics.rs', 'crates/chimera/src/airway/network.rs',
             'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/creatures/alligator.rs',
             'crates/chimera/src/creatures/mammal.rs', 'crates/chimera/src/creatures/build.rs',
             'crates/chimera/src/creatures/voice.rs', 'crates/chimera-cli/src/render.rs',
             'crates/chimera/tests/creature_realtime.rs', 'crates/chimera/tests/golden_creatures.rs',
             'crates/chimera/tests/denormals.rs', 'crates/chimera/tests/golden/creatures.json')
    details = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / name) for name in names}}
    tools = ('upstream_baseline.py', 'measure_seal_airway.py', 'measure_seal_sustain_pcm.py',
             'measure_songbird_sustain_pcm.py', 'measure_songbird_syrinx.py')
    paths = [case, baseline, PROBE, Path(__file__).resolve(), Path(shared.__file__),
             *(WORKSPACE / 'tools' / name for name in tools), WORKSPACE / 'LICENSE-CHIMERA', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case, paths, details,
                                     lambda artifacts, execute: measure(config, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
