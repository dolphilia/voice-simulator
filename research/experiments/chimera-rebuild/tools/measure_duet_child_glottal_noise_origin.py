"""子ども声部で、声門の乱流振幅の差を面積と流量へたどる。"""

import argparse
import gzip
import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_bilabial_stop import KEYS, load_trace
from measure_duet_telemetry import Track, candidate_render, upper_render
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_speech_timing import compare
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-child-glottal-noise-origin.json'
TOOLS = WORKSPACE / 'tools'
PATCH = TOOLS / 'patches/upstream-duet-child-noise-drive.patch'
OUTPUT_PATCH = TOOLS / 'patches/upstream-duet-child-output-stage.patch'
PROBES = [TOOLS / f'{side}_duet_child_noise_probe.rs' for side in ('candidate', 'upstream')]
DICTIONARIES = [WORKSPACE / 'data/cmudict.txt.gz', UPSTREAM / 'public/data/cmudict.txt.gz']
ROOT = WORKSPACE.parents[2]
REFERENCE = ('candidate-1.json', 'upper-1-input.json', 'voice-1.wav', 'duet-turbulence-body/voice-1.tele',
             'upper-1.wav', 'upper-1.tele', 'upper-1-noise.json')


def independent_amplitude(area, flow, gain, study):
    cfg = study['formula']
    opened = area > cfg['closed_area_cm2']
    nu = cfg['dynamic_viscosity_poise'] / cfg['density_g_cm3']
    radius = np.sqrt(np.pi * np.where(opened, area, 1.0))
    re = np.where(opened, 2 * np.abs(flow) / (nu * radius), 0.0)
    critical = cfg['critical_reynolds']**2
    excess = np.maximum(0.0, re**2 - critical)
    saturation = cfg['saturation_reynolds']**2 - critical
    fs = study['internal_sample_rate_hz']
    return gain * np.sqrt(96000.0 / fs) * excess / (1 + excess / saturation)


def compare_series(left, right, limits, window):
    result = {}
    lo, hi = window
    for field, tolerance in limits.items():
        difference = left[field] - right[field]
        if field == 'phase':
            difference = (difference + 0.5) % 1 - 0.5
        delta = np.abs(difference)
        hits = np.flatnonzero(delta > tolerance)
        peak = lo + int(delta[lo:hi].argmax())
        first = int(hits[0]) if hits.size else None
        result[field] = {'first_output_sample': first + 1 if first is not None else None,
                         'first_values': [float(left[field][first]), float(right[field][first])] if first is not None else None,
                         'window_maximum_difference': float(delta[peak]), 'window_peak_sample': peak + 1}
    return result


def decompose(left, right, samples, study):
    indices = np.asarray(samples) - 1
    first, second = left[indices], right[indices]
    a, b = [row['drive_area_cm2'] for row in (first, second)]
    u, v = [row['drive_flow_cm3_s'] for row in (first, second)]
    gain = second['glottal_gain']
    reference, only_area, only_flow, both = (independent_amplitude(x, y, gain, study)
                                             for x, y in ((b, v), (a, v), (b, u), (a, u)))
    area = ((only_area - reference) + (both - only_flow)) * 0.5
    flow = ((only_flow - reference) + (both - only_area)) * 0.5
    measured = first['glottal_level_dyn_cm2'] - second['glottal_level_dyn_cm2']
    fields = ('drive_area_cm2', 'drive_flow_cm3_s', 'glottal_level_dyn_cm2')
    return [{'output_sample': sample, 'candidate': {k: float(first[k][i]) for k in fields},
             'upstream': {k: float(second[k][i]) for k in fields}, 'measured_level_difference': float(measured[i]),
             'area_contribution': float(area[i]), 'flow_contribution': float(flow[i]),
             'residual': float(measured[i] - area[i] - flow[i])}
            for i, sample in enumerate(samples)]


def bit_equal(a, b):
    return (a.shape == b.shape and a.dtype == b.dtype == np.float32 and np.isfinite(a).all()
            and np.array_equal(a.view(np.uint32), b.view(np.uint32)))


def checkpoints(trace, tele, samples):
    if any(sample % tele.hop for sample in samples):
        raise ValueError('CHTLの観測周期と一致しないサンプルです')
    rows = np.asarray(samples) // tele.hop
    state = trace[np.asarray(samples) - 1]
    return (np.array_equal(state['max_level'].astype(np.float32), tele.values[rows, 7])
            and np.array_equal(state['max_source'], tele.values[rows, 8]))


def build_observers(revision, out, execute, scratch):
    candidate = build_upstream_probe(PROBES[0], out, execute, upstream=WORKSPACE, lto='off',
                                     package='vocal-core', extra_libraries=('serde_json',))
    checkout = scratch / 'upstream'
    checkout.mkdir()
    archive = scratch / 'upstream.tar'
    execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
    execute(['tar', '-xf', str(archive), '-C', str(checkout)])
    execute(['git', 'apply', '--verbose', str(PATCH), str(OUTPUT_PATCH)], cwd=checkout)
    upstream = build_upstream_probe(PROBES[1], out, execute, upstream=checkout, extra_libraries=('serde_json',))
    for source, file in zip(DICTIONARIES, ('local.dict', 'upper.dict'), strict=True):
        with gzip.open(source, 'rb') as original, (scratch / file).open('wb') as decoded:
            shutil.copyfileobj(original, decoded)
    return candidate, upstream


def measure(study, reference, out, execute):
    score_path, upper_path, candidate_ref, candidate_tele, upper_ref, upper_tele, older_noise = reference
    song = read_json(score_path)['song_voice']
    score = song['score']
    count = study['trace_output_samples']
    samples = study['checkpoints_output_samples']
    candidate_wave, candidate_tele_now = candidate_render(score_path, 1, out, execute)
    upper_wave, upper_tele_now, pcm_kept = upper_render(
        {'start_seconds': score['start_seconds'], 'body': 'child', 'midi': [n['midi'] for n in score['notes']]},
        song, 1, out, execute)
    settings_path = out / 'candidate-settings.json'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'inspect', str(score_path)], stdout=settings_path)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    traces, pcm = {}, {}
    with TemporaryDirectory(prefix='duet-child-probe-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        candidate, upstream = build_observers(study['upstream_revision'], out, execute, scratch)
        for name in ['candidate', *study['upstream_variants']]:
            local = name == 'candidate'
            exe, case = (candidate, score_path) if local else (upstream, upper_path)
            dictionary = scratch / ('local.dict' if local else 'upper.dict')
            trace, wave = out / f'{name}.csv', out / f'{name}.f32le'
            command = [str(exe), str(case), str(dictionary), str(count), *([] if local else [name]), str(trace), str(wave)]
            execute(command, stdout=out / f'{name}-gestures.json')
            traces[name] = load_trace(trace, count)
            pcm[name] = np.fromfile(wave, dtype='<f4')

    settings = read_json(settings_path)
    candidate_rate, candidate_samples = wavfile.read(candidate_wave)
    upper_rate, upper_samples = wavfile.read(upper_wave)
    nondefault = study['upstream_variants'][1:]
    candidate_gestures = read_json(out / 'candidate-gestures.json')
    reference_gestures = read_json(out / 'default-gestures.json')
    gestures_diff, gestures_error = compare(candidate_gestures,
        [{**g, 'targets': {KEYS[k]: v for k, v in g['targets'].items()}} for g in reference_gestures], 1e-12)
    formula = study['formula']
    epsilon = formula['absolute_tolerance_dyn_cm2']
    formula_error = {name: float(np.max(np.abs(row['glottal_level_dyn_cm2'] - independent_amplitude(
        row['drive_area_cm2'], row['drive_flow_cm3_s'], row['glottal_gain'], study)))) for name, row in traces.items()}
    output_samples = study['sample_rate_hz']
    captured_tele = [Track(path) for path in (candidate_tele_now, upper_tele_now)]
    recorded_upper_rows = {row['sample']: row for row in read_json(older_noise)['rows']}
    checks = {
        'ordinary_entries_match_recorded_pcm': candidate_rate == upper_rate == output_samples and pcm_kept
        and bit_equal(candidate_samples, wavfile.read(candidate_ref)[1]) and bit_equal(upper_samples, wavfile.read(upper_ref)[1]),
        'diagnostic_entries_match_ordinary_pcm': bit_equal(candidate_samples, pcm['candidate']) and bit_equal(upper_samples, pcm['default']),
        'ordinary_entries_match_recorded_tele': sha256(candidate_tele_now) == sha256(candidate_tele)
        and sha256(upper_tele_now) == sha256(upper_tele),
        'noise_observer_matches_tele_checkpoints': all(checkpoints(traces[name], tele, samples)
            for name, tele in zip(('candidate', 'default'), captured_tele, strict=True)),
        'checkpoint_is_glottal_in_both': all(traces[name]['max_source'][samples[1] - 1] == branch for name, branch in (
            ('candidate', settings['noise_branches']['glottis_port']), ('default', 57)))
        and recorded_upper_rows[samples[1]]['noiseNode'] == 57,
        'same_independently_recomputed_candidate_plan': candidate_gestures == settings['gestures'],
        'upper_variants_retain_original_plan': all(read_json(out / f'{name}-gestures.json') == reference_gestures for name in nondefault),
        'variant_pcm_lengths_and_finiteness': all(values.shape == upper_samples.shape and bool(np.isfinite(values).all()) for values in pcm.values()),
        'same_glottal_gain': all(bool(np.all(t['glottal_gain'] == formula['expected_glottis_gain'])) for t in traces.values()),
        'independent_amplitude_each_variant': all(error <= epsilon for error in formula_error.values()),
    }
    lo, hi = study['attention_window_output_samples']
    window = (lo - 1, hi - 1)
    limits = study['gate_geometry_and_flow_tolerances']
    comparisons = {name: compare_series(traces['candidate'], traces[name], limits, window) for name in study['upstream_variants']}
    driver_swaps = {name: decompose(traces['candidate'], traces[name], samples, study) for name in study['upstream_variants']}
    checks['area_flow_decomposition_closes'] = all(abs(row['residual']) <= epsilon for result in driver_swaps.values() for row in result)
    baseline = comparisons['default']
    combined = comparisons['without_all_three']
    metrics = ('drive_area_cm2', 'drive_flow_cm3_s', 'glottal_level_dyn_cm2')
    predictions = {
        'same_planned_gestures': gestures_diff is None,
        'source_settings_explain_part_of_difference': {field: combined[field]['window_maximum_difference'] < baseline[field]['window_maximum_difference']
                                                      for field in metrics},
        'upstream_driver_differs_at_or_before_noise': min(baseline[k]['first_output_sample'] or count + 1 for k in metrics[:2])
        <= (baseline[metrics[2]]['first_output_sample'] or -1),
    }
    return {'checks': checks, 'predictions': predictions, 'comparisons_to_candidate': comparisons,
            'upstream_variant_effects': {name: compare_series(traces[name], traces['default'], limits, window) for name in nondefault},
            'checkpoint_contributions_candidate_minus_upstream': driver_swaps, 'formula_maximum_errors': formula_error,
            'planning': {'first_difference': gestures_diff, 'maximum_error': gestures_error},
            'pcm_frames': len(candidate_samples), 'input_recipe': study['reference_run']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDに使用できる文字を確認してください')
    study = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    run = run_manifest(study['reference_run'], 'duet-head-turbulence-body', revision)
    manifest = run[0] / 'manifest.json'
    if run[1]['status'] != 'pass' or sha256(manifest) != study['reference_manifest_sha256']:
        parser.error('先行実行が登録と一致しません')
    artifacts = [verified_path(run, f'artifacts/{name}') for name in REFERENCE]
    upper_sources = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/voice/human_voice.rs',
                     'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/airway/network.rs',
                     'crates/chimera/src/physics.rs', 'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/phonetics/sing.rs')
    inputs = [CASE, TOOLS / 'duet_child_noise_trace.rs', Path(__file__).resolve(), PATCH, OUTPUT_PATCH, manifest,
              *PROBES, *DICTIONARIES, *artifacts, *candidate_sources(), *(UPSTREAM / k for k in upper_sources),
              *(TOOLS / name for name in ('measure_bilabial_stop.py', 'measure_speech_timing.py', 'measure_duet_telemetry.py',
                'measure_uniform_tube.py', 'measure_wasm_fixed.py', 'measure_fan_crossing_allocations.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, artifacts, out, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
