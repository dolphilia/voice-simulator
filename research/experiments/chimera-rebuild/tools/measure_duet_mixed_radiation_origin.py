"""混合体型の波形の微小差を、放射流量の成分までたどる。"""

import argparse
import math
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_duet_child_glottal_noise_origin as noise
from measure_duet_child_output_gain import trace_input
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-mixed-radiation-origin.json'
COMPONENTS = ('lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s')
FIELDS = (*COMPONENTS, 'total_cm3_s', 'derivative_cm3_s2', 'velum_branch_area_cm2')


def read_components(path, count):
    trace = np.genfromtxt(path, names=True, delimiter=',')
    if (trace.dtype.names != ('internal_sample', *FIELDS)
            or not np.array_equal(trace['internal_sample'], np.arange(1, count + 1))
            or not all(np.isfinite(trace[key]).all() for key in FIELDS)):
        raise ValueError(f'放射の観測列、内部サンプル番号または有限性が不正です ({path.name})')
    return trace


def sum_components(trace):
    return np.asarray([math.fsum(row) for row in zip(*(trace[key] for key in COMPONENTS), strict=True)])


def differentiate(flow, rate):
    return np.diff(flow, prepend=0.0, axis=0) * rate


def max_absolute(values):
    return float(np.max(np.abs(values)))


def first_unequal(values):
    changed = np.flatnonzero(values)
    return int(changed[0]) + 1 if changed.size else None


def capture(study, references, out, execute):
    candidate_case = references['mixed-gain.json']
    upper_case = references['upper-2-input.json']
    ordinary = out / 'candidate-cli.wav'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
             str(candidate_case), str(ordinary), '--no-trace', '128'])
    execute(['cargo', 'test', '--locked', '-p', 'vocal-core', '--test', 'uniform_tube'],
            stdout=out / 'candidate-tests.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'airway'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    count = study['trace_output_frames']
    factor = study['internal_sample_rate_hz'] // study['sample_rate_hz']
    traces, waves, plans = {}, {}, {}
    with TemporaryDirectory(prefix='duet-radiation-probe-', dir=out.parent) as directory:
        scratch = Path(directory)
        local, upper = noise.build_observers(study['upstream_revision'], out, execute, scratch)
        for name, exe, case, variant, dictionary in (
            ('candidate', local, candidate_case, (), 'local.dict'),
            ('upstream', upper, upper_case, ('without_all_three',), 'upper.dict'),
        ):
            components, pcm, plan = [out / f'{name}-{suffix}' for suffix in ('radiation.csv', 'pcm.f32le', 'gestures.json')]
            execute([str(exe), str(case), str(scratch / dictionary), str(count), *variant,
                     str(scratch / f'{name}-noise.csv'), str(pcm), '--radiation-components', str(components)], stdout=plan)
            traces[name] = read_components(components, count * factor)
            waves[name] = np.fromfile(pcm, dtype='<f4')
            plans[name] = sha256(plan)
    return wavfile.read(ordinary), traces, waves, plans


def compare_components(left, right, study):
    internal_rate = study['internal_sample_rate_hz']
    factor = internal_rate // study['sample_rate_hz']
    lo, hi = study['attention_output_frames']
    window = slice((lo - 1) * factor, hi * factor)
    delta = {field: left[field] - right[field] for field in FIELDS}
    first = {field: first_unequal(values) for field, values in delta.items()}
    rate_by_component = {field: differentiate(delta[field], internal_rate) for field in COMPONENTS}
    component_sum = sum_components(delta)
    time_component_sum = sum_components(rate_by_component)
    rounding = delta['total_cm3_s'] - component_sum
    derivative_delta = delta['derivative_cm3_s2']
    accounted_difference = differentiate(delta['total_cm3_s'], internal_rate)
    snapshots = []
    critical = study['expected_first_unequal_internal_sample']
    for sample in (critical - 1, critical, critical + 1):
        j = sample - 1
        snapshots.append({
            'internal_sample': sample, 'output_frame': j // factor + 1,
            'candidate': {field: float(left[field][j]) for field in FIELDS},
            'upstream': {field: float(right[field][j]) for field in FIELDS},
            'candidate_minus_upstream': {field: float(delta[field][j]) for field in FIELDS},
            'component_derivative_differences_cm3_s2': {field: float(value[j]) for field, value in rate_by_component.items()},
            'summation_residual_cm3_s': float(rounding[j]),
            'time_difference_residual_cm3_s2': float(derivative_delta[j] - accounted_difference[j]),
        })
    return {'first_unequal_internal_sample': first, 'snapshots': snapshots,
            'window_peak_differences': {field: max_absolute(values[window]) for field, values in delta.items()},
            'window_component_derivative_peaks_cm3_s2': {
                field: max_absolute(values[window]) for field, values in rate_by_component.items()},
            'window_summation_residual_cm3_s': max_absolute(rounding[window]),
            'window_time_difference_residual_cm3_s2': max_absolute(derivative_delta[window] - accounted_difference[window]),
            'window_unexplained_after_components_cm3_s2': max_absolute(derivative_delta[window] - time_component_sum[window])}


def measure(study, references, out, execute):
    (rate, cli), traces, waves, plans = capture(study, references, out, execute)
    internal_rate = study['internal_sample_rate_hz']
    frames = study['expected_pcm_frames']
    count = study['trace_output_frames']
    archive_prefixes = {'candidate': 'matched', 'upstream': 'upstream'}
    independent = {}
    archive_pcm, archive_radiation = {}, {}
    for name, prefix in archive_prefixes.items():
        trace = traces[name]
        total = sum_components(trace)
        independent[name] = {
            'sum_error_cm3_s': max_absolute(total - trace['total_cm3_s']),
            'derivative_from_total_error_cm3_s2': max_absolute(differentiate(trace['total_cm3_s'], internal_rate)
                                                               - trace['derivative_cm3_s2']),
            'derivative_from_components_error_cm3_s2': max_absolute(differentiate(total, internal_rate)
                                                                    - trace['derivative_cm3_s2']),
        }
        archive_pcm[name] = np.fromfile(references[f'{prefix}.f32le'], dtype='<f4')
        archive_radiation[name] = trace_input(references[f'{prefix}-output.f64le'], frames)[:count, :2].ravel()

    local_input = read_json(references['mixed-gain.json'])['song_voice']
    upper_input = read_json(references['upper-2-input.json'])
    comparison = compare_components(traces['candidate'], traces['upstream'], study)
    first = comparison['first_unequal_internal_sample']
    critical = study['expected_first_unequal_internal_sample']
    factor = internal_rate // study['sample_rate_hz']
    tol = study['tolerances']
    checks = {
        'saved_body_and_rates': local_input['body'] == upper_input['body'] == study['body']
        and local_input['internal_sample_rate_hz'] == internal_rate
        and rate == local_input['voice']['output_sample_rate_hz'] == upper_input['sample_rate_hz'] == study['sample_rate_hz'],
        'full_pcm_matches_prior_and_cli': noise.bit_equal(cli, waves['candidate']) and all(
            len(waves[name]) == frames and noise.bit_equal(waves[name], archive_pcm[name]) for name in archive_prefixes),
        'plans_match_archive': all(plans[name] == sha256(references[f'{prefix}-gestures.json'])
                                   for name, prefix in archive_prefixes.items()),
        'internal_radiation_matches_archived_pairs': all(np.array_equal(
            traces[name]['derivative_cm3_s2'].view('<u8'), archive_radiation[name].view('<u8')) for name in archive_prefixes),
        'independent_sum_and_time_difference': all(row['sum_error_cm3_s'] <= tol['flow_sum_cm3_s']
            and max(row['derivative_from_total_error_cm3_s2'], row['derivative_from_components_error_cm3_s2'])
            <= tol['time_difference_cm3_s2'] for row in independent.values()),
    }
    predictions = {
        'first_difference_matches_index': first['derivative_cm3_s2'] == critical
        and (critical - 1) // factor + 1 == study['expected_first_unequal_output_frame'],
        'closed_velum_and_no_nasal_flow_until_onset': all(
            not np.any(trace[key][:critical]) for trace in traces.values() for key in ('velum_branch_area_cm2', 'nose_cm3_s')),
        'component_difference_precedes_or_matches_output': any(
            first[key] is not None and first[key] <= critical for key in ('lip_cm3_s', 'wall_cm3_s')),
    }
    return {'checks': checks, 'predictions': predictions, 'frames': frames, 'traced_internal_samples': count * factor,
            'independent': independent, 'comparison': comparison}


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
    dependencies = (
        ('reference', 'duet-mixed-output-gain', ('mixed-gain.json', 'matched-output.f64le', 'upstream-output.f64le',
                                               'matched.f32le', 'upstream.f32le', 'matched-gestures.json', 'upstream-gestures.json')),
        ('input', 'duet-head-turbulence-body', ('upper-2-input.json',)),
    )
    references, manifests = {}, []
    for key, case_id, files in dependencies:
        run = run_manifest(study[f'{key}_run'], case_id, revision)
        manifest = run[0] / 'manifest.json'
        if run[1]['status'] != 'pass' or sha256(manifest) != study[f'{key}_manifest_sha256']:
            parser.error(f'先行実行 {run[0].name} が登録と一致しません')
        references.update({name: verified_path(run, f'artifacts/{name}') for name in files})
        manifests.append(manifest)
    inputs = [CASE, Path(__file__).resolve(), Path(noise.__file__), noise.PATCH, noise.OUTPUT_PATCH,
              *noise.PROBES, *noise.DICTIONARIES, noise.TOOLS / 'duet_child_noise_trace.rs', *manifests,
              *references.values(), *candidate_sources(), WORKSPACE / 'crates/vocal-core/tests/uniform_tube.rs',
              *(UPSTREAM / name for name in ('crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/src/voice/human_airway.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/airway.rs', 'crates/chimera/tests/engine.rs')),
              *(noise.TOOLS / name for name in ('measure_duet_child_output_gain.py', 'measure_uniform_tube.py',
                  'measure_fan_crossing_allocations.py', 'measure_wasm_fixed.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, references, out, execute), command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
