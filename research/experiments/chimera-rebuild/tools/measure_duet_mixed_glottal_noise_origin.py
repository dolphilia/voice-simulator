"""混合体型の声門乱流差を、枝の面積・流量と声源の対照から調べる。"""

import argparse
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_duet_child_glottal_noise_origin as noise
from measure_bilabial_stop import KEYS, load_trace
from measure_duet_telemetry import Track, candidate_render
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_speech_timing import compare
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-mixed-glottal-noise-origin.json'
UPPER_BODY_PROBE = noise.TOOLS / 'upstream_duet_body_probe.rs'
ARTIFACTS = ('candidate-2.json', 'upper-2-input.json', 'voice-2.wav', 'duet-turbulence-body/voice-2.tele',
             'upper-2.f32le', 'upper-2-noise.json')
DRIVE = ('drive_area_cm2', 'drive_flow_cm3_s', 'glottal_level_dyn_cm2')


def read_audio(path):
    return np.fromfile(path, dtype='<f4')


def sparse_rows(candidate_track, upstream, count):
    samples = np.asarray([row['sample'] for row in upstream])
    expected = np.arange(candidate_track.rows) * candidate_track.hop
    if not np.array_equal(samples, expected):
        raise ValueError('保存された両版の疎な観測時刻が一致しません')
    inside = (samples > 0) & (samples <= count)
    return samples, samples[inside], inside


def snapshot(trace, index):
    return {name: float(trace[name][index]) for name in (*DRIVE, 'gate', 'f0_hz', 'phase', 'glottal_area_cm2',
                                                       'max_level', 'max_source')}


def measure(study, refs, out, execute):
    case, upper_input, saved_wav, saved_tele, saved_upper_pcm, saved_upper_tele = refs
    settings = out / 'candidate-settings.json'
    now_wav, now_tele = candidate_render(case, 2, out, execute)
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'inspect', str(case)], stdout=settings)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    count = study['trace_output_samples']
    variants = study['upstream_variants']
    traces, pcm, plans = {}, {}, {}
    with TemporaryDirectory(prefix='duet-mixed-probe-', dir=out.parent) as temporary:
        scratch = Path(temporary)
        candidate, upper = noise.build_observers(study['upstream_revision'], out, execute, scratch)
        fixed_dir = out / 'fixed'
        fixed_dir.mkdir()
        fixed = build_upstream_probe(UPPER_BODY_PROBE, fixed_dir, execute, extra_libraries=('serde_json',))
        fixed_pcm = fixed_dir / 'upper-2.f32le'
        fixed_tele = fixed_dir / 'upper-2-noise.json'
        execute([str(fixed), str(upper_input), str(scratch / 'upper.dict'), str(fixed_pcm)], stdout=fixed_tele)
        for name in ('candidate', *variants):
            local = name == 'candidate'
            exe, source = (candidate, case) if local else (upper, upper_input)
            dictionary = scratch / ('local.dict' if local else 'upper.dict')
            trace, wave, plan = (out / f'{name}.{ext}' for ext in ('csv', 'f32le', 'gestures.json'))
            execute([str(exe), str(source), str(dictionary), str(count), *(() if local else (name,)),
                     str(trace), str(wave)], stdout=plan)
            traces[name] = load_trace(trace, count)
            pcm[name] = read_audio(wave)
            plans[name] = read_json(plan)

    baseline = traces['default']
    candidate_trace = traces['candidate']
    old = read_json(saved_upper_tele)
    sparse = Track(now_tele)
    samples, dense_checkpoints, inside = sparse_rows(sparse, old['rows'], count)
    upper_levels = np.asarray([row['noiseLevel'] for row in old['rows']], dtype=np.float32)
    upper_branches = np.asarray([row['noiseNode'] for row in old['rows']])
    sparse_unequal = np.flatnonzero(sparse.values[:, 7] != upper_levels)
    first_sparse = int(samples[sparse_unequal[0]]) if sparse_unequal.size else None
    rate, wav = wavfile.read(now_wav)
    expected = study['expected_glottis_ports']
    important = study['first_prior_difference_sample'] - 1
    inspected = read_json(settings)
    case_input = read_json(case)['song_voice']
    fixed_input = read_json(upper_input)
    formula = study['formula']
    epsilon = formula['absolute_tolerance_dyn_cm2']
    formula_errors = {name: float(np.max(np.abs(row[DRIVE[-1]] - noise.independent_amplitude(
        row[DRIVE[0]], row[DRIVE[1]], row['glottal_gain'], study)))) for name, row in traces.items()}
    swaps = {name: noise.decompose(candidate_trace, traces[name], study['checkpoints_output_samples'], study)
             for name in variants}
    normalized_plan = [{**g, 'targets': {KEYS[key]: val for key, val in g['targets'].items()}}
                       for g in plans['default']]
    first_gesture, gesture_error = compare(plans['candidate'], normalized_plan, 1e-12)
    checks = {
        'registered_body_and_rates': case_input['body'] == fixed_input['body'] == study['body']
        and case_input['internal_sample_rate_hz'] == study['internal_sample_rate_hz']
        and rate == fixed_input['sample_rate_hz'] == sparse.rate == study['sample_rate_hz'],
        'candidate_pcm_matches_cli_and_archive': noise.bit_equal(wav, pcm['candidate'])
        and noise.bit_equal(wav, wavfile.read(saved_wav)[1]),
        'upper_pcm_matches_unmodified_probe_and_archive': noise.bit_equal(pcm['default'], read_audio(fixed_pcm))
        and noise.bit_equal(pcm['default'], read_audio(saved_upper_pcm)),
        'unmodified_sparse_telemetry_matches_archive': sha256(now_tele) == sha256(saved_tele)
        and read_json(fixed_tele) == old,
        'detailed_observers_match_all_available_sparse_rows': noise.checkpoints(candidate_trace, sparse, dense_checkpoints)
        and np.array_equal(baseline['max_level'][dense_checkpoints - 1].astype(np.float32), upper_levels[inside])
        and np.array_equal(baseline['max_source'][dense_checkpoints - 1], upper_branches[inside]),
        'same_glottal_source_at_registered_checkpoint': inspected['noise_branches']['glottis_port']
        == int(candidate_trace['max_source'][important]) == expected['candidate']
        and old['layout']['glottis_port'] == int(baseline['max_source'][important]) == expected['upstream'],
        'recorded_first_sparse_level_difference': first_sparse == study['first_prior_difference_sample'],
        'observed_plans_match_candidate_cli_and_upper_controls': plans['candidate'] == inspected['gestures']
        and all(plans[name] == plans['default'] for name in variants),
        'all_pcm_lengths_and_values_valid': all(len(wave) == study['expected_pcm_frames']
                                              and np.isfinite(wave).all() for wave in pcm.values()),
        'fixed_glottal_gain': all(np.all(trace['glottal_gain'] == formula['expected_glottis_gain'])
                                 for trace in traces.values()),
        'independent_amplitude': all(error <= epsilon for error in formula_errors.values()),
        'area_flow_decomposition_closes': all(abs(row['residual']) <= epsilon for rows in swaps.values() for row in rows),
    }
    lo, hi = study['attention_window_output_samples']
    window = (lo - 1, hi - 1)
    limits = study['gate_geometry_and_flow_tolerances']
    comparisons = {name: noise.compare_series(candidate_trace, traces[name], limits, window) for name in variants}
    source_effects = {name: noise.compare_series(traces[name], baseline, limits, window) for name in variants[1:]}
    original = comparisons['default']
    matched = comparisons['without_all_three']
    first_driver = min(original[key]['first_output_sample'] or count + 1 for key in DRIVE[:2])
    predictions = {
        'same_planned_gestures': first_gesture is None,
        'upstream_driver_differs_at_or_before_noise': first_driver <= (original[DRIVE[-1]]['first_output_sample'] or -1),
        'zeroing_source_variation_reduces_window_maximum': {key: matched[key]['window_maximum_difference']
                                                               < original[key]['window_maximum_difference'] for key in DRIVE},
    }
    return {'checks': checks, 'predictions': predictions, 'pcm_frames': len(wav),
            'planning': {'first_difference': first_gesture, 'maximum_error': gesture_error},
            'sparse': {'first_level_difference_sample': first_sparse, 'checked_rows_per_voice': len(dense_checkpoints),
                       'source_branch': expected},
            'checkpoints': {sample: {name: snapshot(trace, sample - 1) for name, trace in traces.items()}
                            for sample in study['checkpoints_output_samples']},
            'comparisons_to_candidate': comparisons, 'upstream_variant_effects': source_effects,
            'checkpoint_contributions_candidate_minus_upstream': swaps, 'formula_maximum_errors': formula_errors}


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
    artifacts = [verified_path(run, f'artifacts/{name}') for name in ARTIFACTS]
    upstream_sources = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/anatomy/human.rs',
                        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/voice/human_airway.rs',
                        'crates/chimera/src/airway/network.rs', 'crates/chimera/src/physics.rs',
                        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/phonetics/sing.rs',
                        'crates/chimera/tests/body_mix.rs', 'crates/chimera/tests/engine.rs')
    inputs = [CASE, Path(__file__).resolve(), Path(noise.__file__), noise.PATCH, noise.OUTPUT_PATCH,
              noise.TOOLS / 'duet_child_noise_trace.rs', UPPER_BODY_PROBE, *noise.PROBES, *noise.DICTIONARIES,
              manifest, *artifacts, *candidate_sources(), *(UPSTREAM / name for name in upstream_sources),
              *(noise.TOOLS / name for name in ('measure_bilabial_stop.py', 'measure_speech_timing.py',
                'measure_duet_telemetry.py', 'measure_uniform_tube.py', 'measure_wasm_fixed.py',
                'measure_fan_crossing_allocations.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, artifacts, out, execute), command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
