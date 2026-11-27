"""体型別の較正済み母音目標・固定気道・発声を照合する。"""

import argparse
import json
import math
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile

import measure_body_airway as airway
import measure_body_fixed_voice as fixed_voice
import measure_fixed_airway as fixed
import measure_pcm_output as pcm
import measure_sagittal as sagittal
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_vowel_gesture_score as gestures
import measure_vowel_transfer as transfer
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-calibrated-vowels.json'
TABLE = WORKSPACE / 'crates/vocal-core/src/phonetics/vowel-targets.generated.json'
CLI = gestures.CLI
UPPER_AXES = {
    'jaw': 'jaw_cm', 'tbX': 'tongue_body_x_cm', 'tbY': 'tongue_body_y_cm',
    'ttX': 'tongue_tip_x_cm', 'ttY': 'tongue_tip_y_cm', 'ttCurl': 'tip_curl',
    'root': 'tongue_root_cm', 'lipAp': 'lip_aperture_cm', 'lipProt': 'lip_protrusion_cm',
    'lipWidth': 'lip_spread', 'labiodental': 'labiodental', 'velum': 'velum_cm2',
    'larynx': 'larynx_cm', 'epilarynx': 'epilarynx', 'ventricular': 'ventricular',
    'lateral': 'lateral', 'dorsum': 'dorsum',
}
PAIRED_AXES = {'tongue_body_cm': ('tongue_body_x_cm', 'tongue_body_y_cm'),
               'tongue_tip_cm': ('tongue_tip_x_cm', 'tongue_tip_y_cm')}


def expected_patch(ipa, weights, table, tips):
    parts = {key: [] for key in UPPER_AXES.values()}
    for (preset, weight) in zip(('male', 'female', 'child'), weights, strict=True):
        if weight == 0:
            continue
        entry = table[preset].get(ipa, table['male'][ipa])['artic']
        for key, value in entry.items():
            if key not in ('ttX', 'ttY') or ipa in tips:
                parts[UPPER_AXES[key]].append((weight, value))
    return {key: math.fsum(w * v for w, v in values) / math.fsum(w for w, _ in values)
            for key, values in parts.items() if values}


def neutral_axes(neutral):
    result = {key: neutral.get(key, 0.0) for key in UPPER_AXES.values()}
    for pair, axes in PAIRED_AXES.items():
        result.update(zip(axes, neutral[pair], strict=True))
    return result


def explicit_posture(upper_axes):
    values = {UPPER_AXES[key]: value for key, value in upper_axes.items()}
    for pair, (x, y) in PAIRED_AXES.items():
        values[pair] = [values.pop(x), values.pop(y)]
    return values


def match_values(left, right, tolerance):
    if left.keys() != right.keys():
        return False, None
    error = max((abs(value - right[key]) for key, value in left.items()), default=0.0)
    return bool(error <= tolerance), error


def compare_catalog(config, variant, folder, catalog_probe, table, neutral, execute):
    revision = config['upstream_revision']
    reference_path = folder / 'upstream-catalog.json'
    execute([str(catalog_probe), '--catalog-body', json.dumps(variant['body'])], cwd=UPSTREAM, stdout=reference_path)
    references = timing.read(reference_path)
    candidates = gestures.candidate_catalog(references, variant['body'], revision, folder / 'catalog', execute)
    tips = set(config['explicit_tip_targets'])
    tolerance = config['measurement']['target_absolute_tolerance']
    rows = {}
    for ipa, values in candidates.items():
        upper = references[ipa]
        expected = expected_patch(ipa, variant['weights'], table, tips)
        upper_matches, upper_error = match_values(values, upper['targets'], tolerance)
        math_matches, math_error = match_values(values, expected, tolerance)
        upper_pose = {UPPER_AXES[key]: value for key, value in upper['posture'].items()}
        pose_matches, pose_error = match_values(upper_pose, {**neutral, **expected}, tolerance)
        rows[ipa] = {
            'upstream': upper_matches, 'independent': math_matches, 'upstream_pose_from_neutral': pose_matches,
            'maximum_absolute_upstream_error': upper_error, 'maximum_absolute_independent_error': math_error,
            'maximum_absolute_pose_error': pose_error,
        }
    checks = {
        'registered_catalog_size': len(candidates) == config['catalog_size'] and set(candidates) == set(table['male']),
        'explicit_tip_selection': tips == {ipa for ipa, targets in candidates.items()
                                           if {'tongue_tip_x_cm', 'tongue_tip_y_cm'} <= targets.keys()},
    }
    for ipa, row in rows.items():
        for key in ('upstream', 'independent', 'upstream_pose_from_neutral'):
            checks[f'{ipa}/{key}'] = row[key]
    return checks, rows, references


def compare_geometry(inspect, folder, cfg):
    resolved = inspect['fixed_airway']
    tubes = {node: tube for tube in resolved['tubes']
             for node in range(tube['first_node'], tube['first_node'] + tube['cells'])}
    sections = resolved['sections']
    names = [tubes[s['node']]['name'] for s in sections]
    upper_rows, reference = fixed.read_upper_geometry(folder / 'upstream-geometry.csv')
    if names != [row['tube'] for row in upper_rows] or [s['node'] for s in sections] != list(range(len(sections))):
        return False, {'candidate_tubes_by_node': names, 'upstream_tubes_by_node': [row['tube'] for row in upper_rows]}
    values = np.asarray([[tubes[s['node']][key] if key in tubes[s['node']] else s[key] for key in fixed.FIELDS]
                         for s in sections], dtype=float)
    absolute = abs(values - reference)
    relative = absolute[:, 5] / reference[:, 5]
    limits = [cfg['length_absolute_tolerance_cm']] * 3 + [cfg['area_absolute_tolerance_cm2']] * 2
    bad = np.flatnonzero(np.any(absolute[:, :5] > limits, axis=1) | (relative > cfg['relative_compliance_tolerance']))
    checks = np.isfinite(values).all() and not bad.size
    return bool(checks), {
        'maximum_absolute_error_by_field': dict(zip(fixed.FIELDS, absolute.max(axis=0).tolist(), strict=True)),
        'maximum_relative_compliance_error': float(relative.max()),
        'first_node_over_tolerance': int(bad[0]) if bad.size else None,
    }


def compare_voice(config, variant, folder, path, body_arg, voice_probe, execute):
    cfg, settings = config['measurement'], config['voice']
    internal, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    frames = round(cfg['duration_s'] * rate)
    blocks = pcm.render_blocks(path, cfg, folder, execute)
    wave_path, output_trace_path = next(iter(blocks.values()))
    observed_rate, wave = wavfile.read(wave_path)
    execute([str(voice_probe), 'render-calibrated', config['vowel_with_fixed_airway_and_voice'],
             str(internal), str(rate), str(frames), *(str(settings[k]) for k in
             ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), str(folder), body_arg, 'default'],
            cwd=UPSTREAM)
    upper_pcm = np.fromfile(folder / 'upstream-voice.f32', dtype='<f4')
    if (wave.shape != (frames,) or observed_rate != rate or wave.dtype != np.float32 or wave.shape != upper_pcm.shape
            or not np.isfinite(wave).all() or not np.isfinite(upper_pcm).all()):
        raise ValueError(f'候補と上流のPCMの型・長さ・有限性が一致しません ({variant["id"]})')
    execute([*CLI, 'render', str(path), str(folder / 'trace.csv')])
    actual, upper = (fixed_voice.read_trace(folder / name, frames, internal // rate)
                     for name in ('trace.csv', 'upstream-trace.csv'))
    components = {key: shared.compare_series(actual[key], upper[key], cfg['maximum_trace_peak_relative_error_lt'])
                  for key in vowel.TRACE[2:]}
    _, output_trace = pcm.read_columns(output_trace_path, frames, len(pcm.OUTPUT_COLUMNS))
    error = abs(wave - upper_pcm)
    tolerance = cfg['maximum_pcm_absolute_error_lt']
    bad = np.flatnonzero(error >= tolerance)
    window = slice(*(round(seconds * rate) for seconds in cfg['steady_window_s']))
    rms = float(np.sqrt(np.mean(wave[window].astype(float)**2)))
    return {
        'pcm_vs_upstream': not bad.size,
        'internal_trace_vs_upstream': all(entry['status'] for entry in components.values()),
        'host_block_invariance': all(sha256(wav) == sha256(wave_path) and sha256(csv) == sha256(output_trace_path)
                                     for wav, csv in blocks.values()),
        'pcm_trace_matches_wave': np.array_equal(output_trace['pcm_f32'].astype(np.float32), wave),
        'minimum_steady_rms': rms >= cfg['minimum_steady_pcm_rms'],
    }, {
        'pcm_absolute_error': float(error.max()), 'steady_pcm_rms': rms,
        'first_pcm_frame_over_tolerance': int(bad[0]) if bad.size else None,
        'f0_hz': float(np.median(actual['glottal_f0_hz'][window])), 'series_vs_upstream': components,
    }


def compare_acoustic(config, variant, folder, references, probes, execute):
    cfg = config['measurement']
    ipa = config['vowel_with_fixed_airway_and_voice']
    case = {
        'id': config['id'] + '-' + variant['id'], 'upstream_revision': config['upstream_revision'],
        'body': variant['body'], 'posture': {'vowel': ipa}, 'hypothesis': config['hypothesis'],
        'fixed_airway': {'sample_rate_hz': cfg['internal_rate_hz'], 'impulse_volume_cm3': 0,
                         'sample_count': round(cfg['duration_s'] * cfg['internal_rate_hz'])},
        'transfer': {key: config['transfer'][key] for key in ('start_hz', 'end_hz', 'points')},
        'measurement': {'frames': 1, 'peak_search_min_hz': config['transfer']['peak_search_min_hz']},
        'voice': {**config['voice'], 'output_sample_rate_hz': cfg['output_rate_hz']},
    }
    path = folder / 'acoustic-case.json'
    timing.write(path, case)
    execute([*CLI, 'inspect', str(path)], stdout=folder / 'inspect.json')
    execute([*CLI, 'transfer', str(path), str(folder / 'transfer.csv')])
    inspect = timing.read(folder / 'inspect.json')
    upper_case = {**case, 'posture': explicit_posture(references[ipa]['posture'])}
    explicit_path = folder / 'upstream-case.json'
    timing.write(explicit_path, upper_case)
    body = variant['body']
    body_arg = body if isinstance(body, str) else ','.join(str(body.get(key, 0)) for key in ('female', 'child'))
    execute([str(probes['geometry']), '--body', body_arg, '--fixed-airway', str(cfg['internal_rate_hz']),
             '0', '0', *sagittal.pose_controls(upper_case)],
            cwd=UPSTREAM, stdout=folder / 'upstream-geometry.csv')
    execute([str(probes['transfer']), '--case', str(explicit_path), str(folder)], cwd=UPSTREAM)
    geometry_ok, geometry = compare_geometry(inspect, folder, cfg)
    frequency_checks, frequency = airway.frequency(config, inspect, folder)
    voice_folder = folder / 'voice'
    voice_folder.mkdir()
    voice_checks, voice = compare_voice(config, variant, voice_folder, path, body_arg, probes['voice'], execute)
    checks = {'fixed_sections_vs_upstream': geometry_ok, **frequency_checks, **voice_checks}
    return checks, {'geometry': geometry, 'frequency': frequency, 'voice': voice}


def rejects_diphthong(config, artifacts, execute):
    path = artifacts / 'unsupported-fixed-vowel.json'
    timing.write(path, {
        'id': 'not-a-fixed-vowel', 'upstream_revision': config['upstream_revision'],
        'body': 'female', 'posture': {'vowel': config['unsupported_fixed_vowel']},
        'hypothesis': '二重母音は固定単母音の姿勢として解決できない。', 'measurement': {'frames': 1},
    })
    try:
        execute([*CLI, 'inspect', str(path)], stdout=artifacts / 'unsupported-inspect.json')
    except subprocess.CalledProcessError:
        return '固定姿勢に使える較正済み単母音がありません' in (artifacts / 'cargo.log').read_text()
    return False


def measure(config, neutral, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_mix', '--test', 'geometry_continuity'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probes = {}
    for name, path in (('catalog', gestures.PROBE), ('geometry', sagittal.PROBE), ('transfer', transfer.PROBE)):
        folder = artifacts / f'{name}-probe'
        folder.mkdir()
        libraries = () if name == 'geometry' else ('serde_json',)
        probes[name] = shared.build_upstream_probe(path, folder, execute, extra_libraries=libraries)
    voice_folder = artifacts / 'voice-probe'
    voice_folder.mkdir()
    probes['voice'] = fixed_voice.build_fixed_pitch_probe(config['upstream_revision'], voice_folder, execute)
    table = timing.read(vowel.TABLE)
    checks = {'embedded_table_matches_pinned_upstream': sha256(TABLE) == sha256(vowel.TABLE)}
    rows = {}
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        target_checks, target_rows, references = compare_catalog(config, variant, folder, probes['catalog'], table, neutral, execute)
        acoustic_checks, acoustic = compare_acoustic(config, variant, folder, references, probes, execute)
        checks.update({f'{label}/{name}': bool(result) for name, result in {**target_checks, **acoustic_checks}.items()})
        rows[label] = {'targets': target_rows, **acoustic}
    male, middle, child = (rows[label]['frequency']['peaks_hz'] for label in ('male', 'child-mid', 'child'))
    checks['first_two_resonances_between_male_and_child'] = min(map(len, (male, middle, child))) >= 2 and all(
        start < mid < end for start, mid, end in zip(male[:2], middle[:2], child[:2], strict=True))
    checks['diphthong_requires_a_sequence'] = rejects_diphthong(config, artifacts, execute)
    return {'checks': checks, 'cases': rows}


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
    neutral = neutral_axes(timing.read(neutral_path)['posture'])
    upper = ('crates/chimera-cli/src/calibrate.rs', 'crates/chimera/src/phonetics/planner.rs',
             'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/voice/human_airway.rs',
             'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/body_mix.rs',
             'crates/chimera/tests/geometry_continuity.rs')
    metadata = {'case_id': config['id'], 'upstream_revision': revision, 'scipy': scipy.__version__,
                'upstream_vowel_table_sha256': sha256(vowel.TABLE),
                'upstream_source_sha256': {path: sha256(UPSTREAM / path) for path in upper}}
    modules = (airway, fixed_voice, fixed, pcm, sagittal, timing, shared, gestures, transfer, vowel)
    sources = [CASE, neutral_path, Path(__file__).resolve(), fixed_voice.PITCH_PATCH,
               gestures.PROBE, sagittal.PROBE, transfer.PROBE, vowel.PROBE, *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    return shared.record_measurement(run_id, CASE, sources, metadata,
                                     lambda artifacts, execute: measure(config, neutral, artifacts, execute), command=None)


if __name__ == '__main__':
    raise SystemExit(main())
