"""体型別の固定発声を上流波形と声門面積・肺境界の独立計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/human-body-fixed-voice.json'
ENDPOINTS = WORKSPACE / 'cases/human-body-geometry.json'
PITCH_PATCH = WORKSPACE / 'tools/patches/upstream-fixed-voice-initial-pitch.patch'


def waveform(phase, openness, skew, sharpness):
    normalized = phase / openness
    closing = (normalized - skew) / (1 - skew)
    rising = np.sin(np.pi * normalized / (2 * skew)) ** 2
    falling = np.cos(np.pi * closing / 2)
    return np.where(normalized >= 1, 0,
                    np.where(normalized < skew, rising, (1 - sharpness) * falling**2 + sharpness * falling))


def source_values(variant, endpoints, settings):
    names = ['male', 'female', 'child']
    anchors = [endpoints[name] for name in names]
    weights = variant['weights']
    blend = lambda key: sum(w * anchor[key] for w, anchor in zip(weights, anchors, strict=True))
    pitch = variant.get('f0_hz', np.exp(np.dot(weights, np.log([anchor['f0_hz'] for anchor in anchors]))))
    scale = blend('scale')
    breathiness, tension = settings['breathiness'], settings['tension']
    abduction = 0.1 * breathiness**2 * scale**2
    gap = abduction + (0.008 + 0.03 * breathiness) * scale**2
    resistance = 1.14e-3 * 35000 / (5 * scale**2) - (0.8 * 980.665 / 1000) / scale**3
    return {
        'scale': scale, 'f0_hz': float(pitch), 'base_open_quotient': 0.78 - 0.36 * tension + blend('open_phase'),
        'abduction_cm2': abduction, 'closed_area_cm2': gap, 'amplitude_coefficient_cm2': 0.17 * blend('fold_length') * scale,
        'lung_compensation_resistance_dyn_s_cm5': resistance,
    }


def independent_area(trace, settings, expected, selection, rate, *, all_internal=False):
    gate = trace['gate'][selection]
    effort = np.clip(settings['pressure_cm_h2o'] * gate - 2.2, 0, 10) / 10
    amplitude = expected['amplitude_coefficient_cm2'] * (0.45 + 0.75 * effort)
    closed = expected['closed_area_cm2']
    former_gap = closed
    if all_internal:
        # 等間隔の内部系列にだけ4 msの一次フィルタを適用できる。
        pole = np.exp(-1 / (rate * 0.004))
        amplitude = lfilter([1 - pole], [1, -pole], amplitude)
        closed = lfilter([1 - pole], [1, -pole], np.full(gate.shape, closed))
        former_gap = np.r_[0, closed[:-1]]
    chink = expected['closed_area_cm2'] - expected['abduction_cm2']
    open_fraction = np.minimum(0.98, np.clip(expected['base_open_quotient'] - 0.18 * (effort - 0.5), 0.25, 0.98)
                               + 0.98 * np.maximum(0, former_gap - chink))
    tension = settings['tension']
    pulse = waveform(trace['glottal_phase'][selection], open_fraction, 0.56 + 0.16 * tension,
                     0.4 * tension + 1.375 * max(0, tension - 0.6))
    area = closed + amplitude * trace['glottal_voicing'][selection] * pulse
    return area, open_fraction


def independent_lung(path, rate, frames, settings, expected):
    observed = np.fromfile(path, dtype='<f8')
    if observed.shape != (frames,) or not np.isfinite(observed).all():
        raise ValueError('上流肺流量の内部サンプル数または有限性が不正です')
    block, position = np.divmod(np.arange(frames), 64)
    attack_hz = 1 / 0.025
    before = settings['gate'] * (-np.expm1(-block * 64 * attack_hz / rate))
    after = settings['gate'] * (-np.expm1(-(block + 1) * 64 * attack_hz / rate))
    base = settings['pressure_cm_h2o'] * 980.665 * (before + (position + 1) / 64 * (after - before))
    resistance = expected['lung_compensation_resistance_dyn_s_cm5']
    pole = np.exp(-resistance * expected['scale'] / (0.0052 * rate))
    compensation = resistance * lfilter([1 - pole], [1, -pole], np.r_[0, observed[:-1]])
    return base + compensation


def compare_variant(config, variant, folder, probe, pose, endpoints, execute):
    cfg = config['measurement']
    internal = variant.get('internal_rate_hz', cfg['internal_rate_hz'])
    rate = variant.get('output_rate_hz', cfg['output_rate_hz'])
    frames, count = round(cfg['duration_s'] * rate), round(cfg['duration_s'] * internal)
    steady = slice(*(round(seconds * rate) for seconds in cfg['steady_window_s']))
    settings = config['voice']
    voice = {**settings, 'output_sample_rate_hz': rate}
    if 'f0_hz' in variant:
        voice['f0_hz'] = variant['f0_hz']
    case = {
        'id': f"{config['id']}-{variant['id']}", 'upstream_revision': config['upstream_revision'],
        'hypothesis': config['hypothesis'], 'body': variant['body'], 'posture': pose['posture'],
        'fixed_airway': {'sample_rate_hz': internal, 'sample_count': count, 'impulse_volume_cm3': 0},
        'voice': voice, 'measurement': {'frames': 1},
    }
    path = folder / 'case.json'
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    cli = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli, 'inspect', str(path)], stdout=folder / 'inspect.json')
    execute([*cli, 'render', str(path), str(folder / 'trace.csv')])
    blocks = pcm.render_blocks(path, cfg, folder, execute)
    wave_path, output_trace_path = next(iter(blocks.values()))
    sample_rate, wave = wavfile.read(wave_path)
    _, output_trace = pcm.read_columns(output_trace_path, frames, len(pcm.OUTPUT_COLUMNS))

    body = variant['body']
    body_arg = body if isinstance(body, str) else ','.join(str(body.get(key, 0)) for key in ('female', 'child'))
    args = [pose['measurement']['voice']['ipa'], internal, rate, frames,
            *(settings[key] for key in ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')),
            folder, body_arg, variant.get('f0_hz', 'default')]
    execute([str(probe), 'render-body', *map(str, args)], cwd=UPSTREAM)
    reference = np.fromfile(folder / 'upstream-voice.f32', dtype='<f4')
    if (wave.shape != (frames,) or wave.dtype != np.float32 or reference.shape != wave.shape
            or not np.isfinite(wave).all() or not np.isfinite(reference).all()):
        raise ValueError('候補と上流のPCMには指定した長さで有限な単精度サンプルが必要です')

    factor = internal // rate
    actual, upper = [read_trace(folder / name, frames, factor) for name in ('trace.csv', 'upstream-trace.csv')]
    comparisons = {key: shared.compare_series(actual[key], upper[key], cfg['maximum_trace_peak_relative_error_lt'])
                   for key in vowel.TRACE[2:]}
    expected = source_values(variant, endpoints, settings)
    f0_from_phase = np.diff(actual['glottal_phase']) % 1 * rate
    area, openness = independent_area(actual, settings, expected, steady, internal)
    errors = {
        'pcm': float(np.max(abs(wave - reference))),
        'pitch_hz': float(np.max(abs(f0_from_phase - expected['f0_hz']))),
        'steady_glottal_area_cm2': float(np.max(abs(actual['glottal_area_cm2'][steady] - area))),
    }
    area_steady = actual['glottal_area_cm2'][steady]
    open_samples = area_steady > expected['closed_area_cm2'] + 1e-8
    observed_open = float(np.max(actual['glottal_phase'][steady][open_samples], initial=0))
    voiced = float(np.min(actual['glottal_voicing'][steady]))
    pcm_peak = float(np.max(abs(wave)))
    failures = np.flatnonzero(abs(wave - reference) >= cfg['maximum_pcm_absolute_error_lt'])
    checks = {
        'sample_rate_and_count': sample_rate == rate and frames * factor == count,
        'pcm_vs_upstream': errors['pcm'] < cfg['maximum_pcm_absolute_error_lt'],
        'all_trace_components_vs_upstream': all(row['status'] for row in comparisons.values()),
        'pitch_from_phase': errors['pitch_hz'] < cfg['maximum_pitch_absolute_error_hz_lt'],
        'steady_glottal_area_from_phase': errors['steady_glottal_area_cm2'] < cfg['maximum_steady_area_absolute_error_cm2_lt'],
        'steady_voicing': voiced >= cfg['minimum_steady_voicing'],
        'bounded_pcm': pcm_peak <= cfg['maximum_pcm_peak'],
        'pcm_trace_matches_wave': np.array_equal(output_trace['pcm_f32'].astype(np.float32), wave),
        'host_block_invariance': all(sha256(wav) == sha256(wave_path) and sha256(csv) == sha256(output_trace_path)
                                     for wav, csv in blocks.values()),
    }
    if factor == 1:
        area_all, _ = independent_area(actual, settings, expected, slice(None), rate, all_internal=True)
        lung = independent_lung(folder / 'upstream-lung-flow.f64', rate, frames, settings, expected)
        errors['direct_glottal_area_cm2'] = float(np.max(abs(actual['glottal_area_cm2'] - area_all)))
        errors['direct_lung_boundary_dyn_cm2'] = float(np.max(abs(actual['lung_boundary_dyn_cm2'] - lung)))
        checks['direct_glottal_area'] = errors['direct_glottal_area_cm2'] < cfg['maximum_direct_area_absolute_error_cm2_lt']
        checks['direct_lung_boundary'] = errors['direct_lung_boundary_dyn_cm2'] < cfg['maximum_direct_lung_boundary_absolute_error_dyn_cm2_lt']
    summary = {
        'frame_count': frames, 'internal_rate_hz': internal, 'output_rate_hz': rate,
        'expected': expected, 'absolute_errors': errors, 'series_vs_upstream': comparisons,
        'first_pcm_frame_over_tolerance': int(failures[0]) if failures.size else None,
        'peak_pcm': pcm_peak, 'steady_pcm_rms': float(np.sqrt(np.mean(wave[steady].astype(float)**2))),
        'steady_minimum_voicing': voiced, 'steady_pitch_hz': float(np.median(f0_from_phase[steady])),
        'steady_expected_open_quotient': float(np.median(openness)), 'steady_last_open_phase': observed_open,
        'steady_peak_to_peak_area_cm2': float(np.ptp(area_steady)),
        'steady_peak_to_peak_flow_cm3_s': float(np.ptp(actual['glottal_flow_cm3_s'][steady])),
    }
    return checks, summary


def read_trace(path, frames, factor):
    header, trace = pcm.read_columns(path, frames, len(vowel.TRACE))
    if tuple(header) != vowel.TRACE or not np.array_equal(trace['internal_sample'], factor * np.arange(1, frames + 1) - 1):
        raise ValueError(f'{path.name} の列または内部サンプル番号が一致しません')
    return trace


def build_fixed_pitch_probe(revision, artifacts, execute):
    with TemporaryDirectory(prefix='upstream-build-', dir=artifacts) as directory:
        scratch = Path(directory)
        upstream = scratch / 'upstream'
        upstream.mkdir()
        archive = scratch / 'upstream.tar'
        execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(upstream)])
        execute(['git', 'init', '--quiet'], cwd=upstream)
        execute(['git', 'apply', '--verbose', str(PITCH_PATCH)], cwd=upstream)
        return shared.build_upstream_probe(vowel.PROBE, artifacts, execute, upstream=upstream,
                                           rustc_args=('--cfg', 'chimera_fixed_pitch_probe'))


def measure(config, pose, endpoints, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'body_source'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-body-source.log')
    probe = build_fixed_pitch_probe(config['upstream_revision'], artifacts, execute)
    checks, rows = {}, {}
    for variant in config['variants']:
        label = variant['id']
        folder = artifacts / label
        folder.mkdir()
        passed, rows[label] = compare_variant(config, variant, folder, probe, pose, endpoints, execute)
        checks.update({f'{label}/{key}': bool(value) for key, value in passed.items()})
    male, female, child, equal_pitch = (rows[label] for label in ('male', 'female', 'child', 'female-110'))
    checks['body_endpoint_area_order'] = (male['steady_peak_to_peak_area_cm2'] > female['steady_peak_to_peak_area_cm2']
                                         > child['steady_peak_to_peak_area_cm2'] > 0)
    opening_change = equal_pitch['steady_last_open_phase'] - male['steady_last_open_phase']
    checks['female_open_phase_increases_at_equal_pitch'] = (
        opening_change >= config['measurement']['minimum_expected_open_quotient_increase_female_110'])
    checks['child_open_phase_increases'] = child['steady_last_open_phase'] > male['steady_last_open_phase']
    checks['body_endpoint_lung_resistance_order'] = (
        male['expected']['lung_compensation_resistance_dyn_s_cm5'] < female['expected']['lung_compensation_resistance_dyn_s_cm5']
        < child['expected']['lung_compensation_resistance_dyn_s_cm5'])
    return {'checks': checks, 'cases': rows, 'female_minus_male_last_open_phase_at_equal_pitch': opening_change}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    run_id = parser.parse_args().run_id
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        parser.error('実行IDは英数字で始めてください')
    config = json.loads(CASE.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    pose_path = WORKSPACE / 'cases' / config['pose_from_case']
    pose = json.loads(pose_path.read_text())
    endpoints = json.loads(ENDPOINTS.read_text())['measurement']['reference_endpoints']
    upstream = ('src/engine.rs', 'src/anatomy/human.rs', 'src/voice/human_airway.rs', 'src/voice/human_voice.rs',
                'src/sources/glottis.rs', 'src/physics.rs', 'tests/body_source.rs')
    metadata = {'case_id': config['id'], 'upstream_revision': revision, 'scipy': scipy.__version__,
                'upstream_vowel_table_sha256': sha256(vowel.TABLE),
                'upstream_source_sha256': {path: sha256(UPSTREAM / 'crates/chimera' / path) for path in upstream}}
    sources = [CASE, ENDPOINTS, pose_path, Path(__file__).resolve(), vowel.PROBE, PITCH_PATCH, *shared.candidate_sources(),
               *(Path(module.__file__) for module in (pcm, shared, vowel)), WORKSPACE / 'tools/upstream_baseline.py',
               WORKSPACE / 'tools/measure_junction.py']
    return shared.record_measurement(run_id, CASE, sources, metadata,
                                     lambda artifacts, execute: measure(config, pose, endpoints, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
