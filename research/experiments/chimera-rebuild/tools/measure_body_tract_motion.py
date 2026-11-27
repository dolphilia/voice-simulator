"""体型別の断面目標、内部補間、形状変化による流量、有声出力を照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_articulation as articulation
import measure_body_calibrated_vowels as calibrated
import measure_pcm_output as pcm
import measure_speech_timing as timing
import measure_tract_control as control
import measure_tract_motion as motion
import measure_uniform_tube as shared
import measure_voiced_vowel_motion as voiced
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-tract-motion.json'
ENDPOINTS = WORKSPACE / 'cases/human-body-geometry.json'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def build_case(config, variant, neutral, contact, table, tips):
    rate = variant['rate_hz']
    spec = config[variant['trajectory']]
    body = variant['body']
    if isinstance(body, str):
        weights = tuple(float(body == anchor) for anchor in ('male', 'female', 'child'))
    else:
        female, child = (body.get(axis, 0.0) for axis in ('female', 'child'))
        adult = 1.0 - child
        weights = (adult * (1.0 - female), adult * female, child)
    if not math.isclose(math.fsum(weights), 1.0):
        raise ValueError("体型の補間重みの和が1ではありません")

    def targets(ipa):
        return calibrated.expected_patch(ipa, weights, table, tips)

    pose = {**neutral, **targets(spec['initial'])} if 'initial' in spec else contact
    posture = dict(pose)
    for pair, (x, y) in calibrated.PAIRED_AXES.items():
        posture[pair] = [posture.pop(x), posture.pop(y)]
    events = []
    for event in spec['events']:
        axes = targets(event['vowel']) if 'vowel' in event else {}
        events.append({'frame': event['frame'], 'targets': {**axes, **event.get('targets', {})}})
    cfg = config['articulators']
    case = {
        'id': config['id'] + '-' + variant['id'],
        'upstream_revision': config['upstream_revision'],
        'hypothesis': config['hypothesis'],
        'body': variant['body'],
        'posture': posture,
        'articulators': {
            'sample_rate_hz': rate, 'control_block_samples': cfg['control_block_samples'],
            'base_weight': cfg['base_weight'], 'tip_free': variant['trajectory'] == 'vowels', 'events': events,
        },
        'area_control': {'project_contacts': True},
        'measurement': {'frames': cfg['frames']},
    }
    return case, weights


def measure_targets(case, weights, variant, endpoints, cfg, folder, probe, events, execute):
    path = folder / 'targets-case.json'
    timing.write(path, case)
    execute([*CLI, 'inspect', str(path)], stdout=folder / 'settings.json')
    actual_path = folder / 'targets.csv'
    upper_path = folder / 'upstream-targets.csv'
    execute([*CLI, 'render', str(path), str(actual_path)])
    execute([str(probe), str(events), 'tract-with-contact'], cwd=UPSTREAM, stdout=upper_path)

    rate = variant['rate_hz']
    block = case['articulators']['control_block_samples']
    frames = case['measurement']['frames']
    cells = dict(zip(('pharynx', 'oral'), variant['cells'], strict=True))
    anchors = ('male', 'female', 'child')
    scale, pharynx = (math.fsum(w * endpoints[name][axis] for name, w in zip(anchors, weights, strict=True))
                      for axis in ('scale', 'pharynx'))
    minimum = (8.7 * scale * (0.55 + 0.45 * pharynx) - 1.6 * scale, 7.3 * scale)
    counts = [max(8, math.floor(length * rate * 0.93 / 35000)) for length in minimum]
    candidate, ids = control.read_trace(actual_path, cells, frames)
    upper, _ = control.read_trace(upper_path, cells, frames)
    comparison = control.compare(candidate, upper, ids, cfg)
    independent = control.independent_trace(candidate, ids, block / rate, rate,
                                            folder / 'independent-targets.csv', body_scale=scale)
    reapplied = [f for f, stage in candidate if stage == 'reapply']
    checks = {
        'registered_cell_counts_from_body': counts == variant['cells'],
        'sampled_targets_match_upstream': comparison['first_over_tolerance'] is None,
        'independent_simulation_length': independent['simulation_length_error_cm'] < cfg['length_absolute_lt_cm'],
        'independent_slew_and_baseline': independent['limited_area_error_cm2'] < cfg['area_absolute_lt_cm2'],
        'lips_from_teeth_position': independent['lip_cells_match_from_teeth_distance'],
    }
    if variant['trajectory'] == 'contact':
        checks['contact_reapply_requires_previous_frame'] = (bool(reapplied) and
            independent['using_first_pass_as_baseline_max_error_cm2'] > cfg['minimum_reapply_baseline_error_cm2'])
    return checks, {
        'body_scale': scale, 'cell_counts': cells, 'number_of_reapplies': len(reapplied),
        'first_reapply_frame': reapplied[0] if reapplied else None,
        'vs_upstream': comparison, 'independent': independent,
    }, actual_path


def measure_motion(case, variant, cfg, folder, probe, events, target_path, execute):
    acoustic_case = {**case, 'area_control': {**case['area_control'], 'acoustics': True}}
    path = folder / 'motion-case.json'
    timing.write(path, acoustic_case)
    actual_path = folder / 'motion.csv'
    upper_path = folder / 'upstream-motion.csv'
    execute([*CLI, 'render', str(path), str(actual_path)])
    execute([str(probe), str(events), 'network-with-contact'], cwd=UPSTREAM, stdout=upper_path)
    block = case['articulators']['control_block_samples']
    samples = case['measurement']['frames'] * block
    actual, upper = (motion.load_samples(path, samples) for path in (actual_path, upper_path))

    interpolation_input = {
        'observed_tube_cells': dict(zip(('pharynx', 'oral'), variant['cells'], strict=True)),
        'center_volume_no_spill_minimum_cm2': 0.12, 'volume_source_cutoff_hz': cfg['volume_source_cutoff_hz'],
    }
    geometry, volume, source, _, no_spill = motion.independent_motion(case, interpolation_input, target_path)
    split = len(motion.GEOMETRY)
    geom = motion.comparison(actual[:, :split], upper[:, :split], motion.GEOMETRY, cfg['geometry_absolute_lt'])
    interpolated = motion.comparison(actual[:, :split], geometry, motion.GEOMETRY, cfg['geometry_absolute_lt'])
    acoustics = {name: shared.compare_series(a, b, cfg['acoustics_relative_to_upstream_peak_lt'])
                 for name, a, b in zip(motion.ACOUSTICS, actual[:, split:].T, upper[:, split:].T, strict=True)}
    rate = variant['rate_hz']
    inferred = motion.inferred_volume_source(actual, volume, rate)
    inferred_upper = motion.inferred_volume_source(upper, volume, rate)
    np.savetxt(folder / 'independent-motion.csv', np.column_stack((
        np.arange(samples), geometry, volume, source, inferred, inferred_upper)),
        delimiter=',', comments='', header=','.join(('sample', *motion.GEOMETRY, 'volume_cm3',
                                                      'unredistributed_volume_source_cm3_s',
                                                      'inferred_cm3_s', 'inferred_upstream_cm3_s')))
    measured = motion.observations(actual, 0.0002)
    max_flow = float(np.max(abs(inferred)))
    checks = {
        'internal_geometry_vs_upstream': geom['first_over_tolerance'] is None,
        'sample_interpolation_from_control_targets': interpolated['first_over_tolerance'] is None,
        'all_acoustic_series_vs_upstream': all(row['status'] for row in acoustics.values()),
        'nonzero_pressure_source_from_motion': max_flow > cfg['minimum_center_volume_source_cm3_s'],
    }
    if variant['trajectory'] == 'vowels':
        checks['changes_both_tube_lengths'] = all(
            measured[f'{tube}_cell_length_span_cm'] > cfg['minimum_cell_length_span_cm']
            for tube in ('pharynx', 'oral'))
        checks['nasal_radiation_at_open_velum'] = measured['peak_nose_flow_cm3_s'] > 0
    return checks, {
        'internal_samples': samples, 'geometry_vs_upstream': geom, 'independent_interpolation': interpolated,
        'acoustics_vs_upstream': acoustics, 'observations': measured, 'peak_center_source_cm3_s': max_flow,
        'center_volume_source_absolute_difference_without_spill': (
            float(abs(inferred - source).max()) if no_spill else None),
    }


def measure_voice(case, settings, cfg, folder, probe, events, execute):
    folder.mkdir()
    rate = case['articulators']['sample_rate_hz'] // 2
    block = case['articulators']['control_block_samples']
    frames = case['measurement']['frames'] * block // 2
    voice_settings = {**settings, 'output_sample_rate_hz': rate}
    path = folder / 'case.json'
    timing.write(path, {**case, 'voice': voice_settings})
    candidate_trace, upper_trace = (folder / name for name in ('trace.csv', 'upstream-trace.csv'))
    execute([*CLI, 'render', str(path), str(candidate_trace)])
    raw = folder / 'upstream.f32'
    args = [voice_settings[name] for name in ('output_sample_rate_hz', 'pressure_cm_h2o', 'gate', 'f0_hz',
                                              'breathiness', 'tension', 'output_gain')]
    execute([str(probe), str(events), 'voice', *map(str, args), '1', str(raw), str(upper_trace)], cwd=UPSTREAM)
    blocks = pcm.render_blocks(path, cfg, folder, execute)
    wave_path, trace_path = next(iter(blocks.values()))
    observed_rate, wave = wavfile.read(wave_path)
    reference = np.fromfile(raw, dtype='<f4')
    if (observed_rate != rate or wave.dtype != np.float32 or wave.shape != (frames,) or wave.shape != reference.shape
            or not np.isfinite(wave).all() or not np.isfinite(reference).all()):
        raise ValueError('有声出力のレート・フレーム数・有限性が不正です')
    indices = np.arange(frames * 2)
    output_samples = slice(1, None, 2)
    actual = voiced.load_track(candidate_trace, indices, block)
    upper = voiced.load_track(upper_trace, indices[output_samples], block)
    geometry = {name: voiced.compare(actual[name][output_samples], upper[name], cfg['geometry_absolute_lt'])
                for name in (*voiced.GEOMETRY, *voiced.ARTICULATION)}
    components = {name: shared.compare_series(actual[name][output_samples], upper[name],
                                             cfg['voice_trace_relative_to_upstream_peak_lt'])
                  for name in voiced.VOICE}
    error = voiced.compare(wave, reference, cfg['pcm_absolute_lt'])
    return {
        'voiced_geometry_matches_upstream': all(row['status'] for row in geometry.values()),
        'voiced_trace_matches_upstream': all(row['status'] for row in components.values()),
        'pcm_matches_upstream': error['status'],
        'host_partition_preserves_pcm_and_trace': all(sha256(wav) == sha256(wave_path) and sha256(csv) == sha256(trace_path)
                                                      for wav, csv in blocks.values()),
    }, {
        'output_rate_hz': rate,
        'pcm': error, 'geometry': geometry, 'source_and_radiation': components,
        'first_nonzero_difference_geometry': voiced.first_exact_difference(
            actual, upper, (*voiced.GEOMETRY, *voiced.ARTICULATION), output_samples),
        'first_nonzero_difference_sound': voiced.first_exact_difference(actual, upper, voiced.VOICE, output_samples),
    }


def measure(config, neutral, contact, table, endpoints, tips, artifacts, execute):
    for suite in ('airway_adversarial', 'body_mix', 'geometry_continuity'):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite],
                cwd=UPSTREAM, stdout=artifacts / f'upstream-{suite}.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'speech_quality',
             'the_contact_model_engages_smoothly'], cwd=UPSTREAM, stdout=artifacts / 'upstream-contact.log')
    probe = shared.build_upstream_probe(articulation.PROBE, artifacts, execute)
    results, checks = {}, {}
    cfg = config['measurement']
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        case, weights = build_case(config, variant, neutral, contact, table, tips)
        events = folder / 'upstream-events.txt'
        articulation.write_upstream_events(case, events)
        target_checks, targets, path = measure_targets(case, weights, variant, endpoints, cfg, folder, probe, events, execute)
        motion_checks, acoustics = measure_motion(case, variant, cfg, folder, probe, events, path, execute)
        results[label] = {'targets': targets, 'motion': acoustics}
        voice_checks = {}
        if variant['voice']:
            voice_checks, results[label]['voice'] = measure_voice(
                case, config['voice'], cfg, folder / 'voice', probe, events, execute)
        checks.update({f'{label}/{name}': bool(status)
                       for name, status in {**target_checks, **motion_checks, **voice_checks}.items()})
    return {'checks': checks, 'cases': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    run_id = parser.parse_args().run_id
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    neutral_path = WORKSPACE / 'cases' / config['neutral_case']
    contact_path = WORKSPACE / 'cases' / config['contact']['initial_case']
    catalog = calibrated.CASE
    neutral, contact = (calibrated.neutral_axes(timing.read(path)['posture']) for path in (neutral_path, contact_path))
    tips = set(timing.read(catalog)['explicit_tip_targets'])
    table = timing.read(vowel.TABLE)
    endpoints = timing.read(ENDPOINTS)['measurement']['reference_endpoints']
    modules = (articulation, calibrated, pcm, timing, control, motion, shared, voiced, vowel)
    inputs = [CASE, neutral_path, contact_path, catalog, ENDPOINTS, Path(__file__).resolve(), articulation.PROBE,
              *shared.candidate_sources(), *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    upper_paths = ('src/voice/human_airway.rs', 'src/voice/human_voice.rs', 'src/airway/network.rs',
                   'src/control/articulators.rs', 'src/phonetics/vowelTargets.generated.json',
                   'tests/airway_adversarial.rs', 'tests/speech_quality.rs', 'tests/body_mix.rs', 'tests/geometry_continuity.rs')
    details = {'case_id': config['id'], 'upstream_revision': revision, 'scipy': scipy.__version__,
               'upstream_source_sha256': {name: sha256(UPSTREAM / 'crates/chimera' / name) for name in upper_paths}}
    return shared.record_measurement(run_id, CASE, inputs, details,
                                     lambda artifacts, execute: measure(config, neutral, contact, table, endpoints, tips,
                                                                        artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
