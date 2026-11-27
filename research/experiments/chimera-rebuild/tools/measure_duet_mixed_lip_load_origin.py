"""混合体型の最初の口端流量差を、R–L負荷に入る状態へさかのぼる。"""

import argparse
from decimal import Decimal, localcontext
import gzip
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_duet_child_glottal_noise_origin as noise
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_duet_mixed_radiation_origin import read_components
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-mixed-lip-load-origin.json'
SHARED_PROBE = noise.TOOLS / 'duet_child_noise_trace.rs'
PATCH_DIR = noise.TOOLS / 'patches'
COLUMNS_PATCH = PATCH_DIR / 'duet-lip-solve-columns.patch'
LOCAL_PATCH = PATCH_DIR / 'candidate-duet-lip-solve.patch'
UPPER_PATCH = PATCH_DIR / 'upstream-duet-lip-solve.patch'
EMBEDDED_DICTIONARY = WORKSPACE / 'data/mandarin.txt.gz'
FIELDS = ('solved', 'area_cm2', 'length_cm', 'compliance_cm5_dyn', 'resistance_dyn_s_cm5', 'inertance_g_cm4',
          'old_pressure_dyn_cm2', 'old_inertance_flow_cm3_s', 'geometry_inflow_cm3_s', 'before_wall_inflow_cm3_s',
          'inflow_cm3_s', 'new_pressure_dyn_cm2', 'new_inertance_flow_cm3_s', 'lip_flow_cm3_s')
SOLVE_INPUTS = ('compliance_cm5_dyn', 'resistance_dyn_s_cm5', 'inertance_g_cm4',
                'old_pressure_dyn_cm2', 'old_inertance_flow_cm3_s', 'inflow_cm3_s')
SOLVE_OUTPUTS = ('new_pressure_dyn_cm2', 'new_inertance_flow_cm3_s', 'lip_flow_cm3_s')


def copy_inputs(paths, target):
    for path in paths:
        copy = target / path.relative_to(WORKSPACE)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, copy)


def build_lip_observers(study, out, execute, scratch):
    local = scratch / 'candidate'
    upper = scratch / 'upstream'
    local.mkdir()
    upper.mkdir()
    copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, SHARED_PROBE, noise.PROBES[0]], local)
    archive = scratch / 'upstream.tar'
    execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=archive)
    execute(['tar', '-xf', str(archive), '-C', str(upper)])
    copy_inputs([SHARED_PROBE, noise.PROBES[1]], upper)
    execute(['git', 'apply', '--verbose', str(COLUMNS_PATCH), str(LOCAL_PATCH)], cwd=local)
    execute(['git', 'apply', '--verbose', str(noise.PATCH), str(noise.OUTPUT_PATCH)], cwd=upper)
    execute(['git', 'apply', '--verbose', str(COLUMNS_PATCH), str(UPPER_PATCH)], cwd=upper)
    for source, name in zip(noise.DICTIONARIES, ('local.dict', 'upper.dict'), strict=True):
        with gzip.open(source, 'rb') as decoded, (scratch / name).open('wb') as output:
            shutil.copyfileobj(decoded, output)
    local_exe = build_upstream_probe(local / 'tools' / noise.PROBES[0].name, out, execute,
                                     upstream=local, lto='off', package='vocal-core', extra_libraries=('serde_json',))
    upper_exe = build_upstream_probe(upper / 'tools' / noise.PROBES[1].name, out, execute,
                                     upstream=upper, extra_libraries=('serde_json',))
    return local_exe, upper_exe


def read_solve_trace(path, lo, hi):
    data = np.genfromtxt(path, names=True, delimiter=',')
    if (data.dtype.names != ('internal_sample', *FIELDS)
            or not np.array_equal(data['internal_sample'], np.arange(lo, hi + 1))
            or not np.isin(data['solved'], [0, 1]).all()
            or not all(np.isfinite(data[field]).all() for field in FIELDS)):
        raise ValueError(f'口端負荷の観測列または内部サンプル番号が不正です ({path.name})')
    return data


def capture(study, references, out, execute):
    lo, hi = study['observation_internal_samples']
    factor = study['internal_sample_rate_hz'] // study['sample_rate_hz']
    if factor != 2 or (lo - 1) % factor or hi % factor:
        raise ValueError('観測区間は2内部分を持つ出力フレームの境界で指定してください')
    ordinary = out / 'candidate-cli.wav'
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
             str(references['mixed-gain.json']), str(ordinary), '--no-trace', '128'])
    execute(['cargo', 'test', '--locked', '-p', 'vocal-core', '--test', 'uniform_tube'],
            stdout=out / 'candidate-tests.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'airway'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    traces, waves, plans = {}, {}, {}
    with TemporaryDirectory(prefix='duet-lip-load-probe-', dir=out.parent) as directory:
        scratch = Path(directory)
        local, upper = build_lip_observers(study, out, execute, scratch)
        for side, exe, case, dictionary, variant in (
            ('candidate', local, 'mixed-gain.json', 'local.dict', ()),
            ('upstream', upper, 'upper-2-input.json', 'upper.dict', ('without_all_three',)),
        ):
            source = read_json(references[case]) | {'probe_first_output_frame': (lo - 1) // factor}
            probe_case = out / f'{side}-probe-input.json'
            probe_case.write_text(json.dumps(source, indent=2, ensure_ascii=False) + '\n')
            trace, pcm, plan = [out / f'{side}-{suffix}' for suffix in ('lip-load.csv', 'pcm.f32le', 'gestures.json')]
            execute([str(exe), str(probe_case), str(scratch / dictionary), str(hi // factor), *variant,
                     str(scratch / f'{side}-noise.csv'), str(pcm), '--radiation-components', str(trace)], stdout=plan)
            traces[side] = read_solve_trace(trace, lo, hi)
            waves[side] = np.fromfile(pcm, dtype='<f4')
            plans[side] = sha256(plan)
    return wavfile.read(ordinary), traces, waves, plans


def midpoint(inputs, rate):
    c, r, l, p0, u0, inflow = (inputs[name] for name in SOLVE_INPUTS)
    compliance_gain = 2 * c * rate
    inertance_gain = 1 / (l * rate)
    admittance = 1 / r + inertance_gain / 2
    p_mid = (compliance_gain * p0 + inflow - u0) / (compliance_gain + admittance)
    return (2 * p_mid - p0, u0 + inertance_gain * p_mid, u0 + admittance * p_mid)


def high_precision_row(row, fields):
    return {field: Decimal.from_float(float(row[field])) for field in fields}


def model_errors(rows, rate):
    peak = dict.fromkeys(SOLVE_OUTPUTS, Decimal(0))
    for row in rows[rows['solved'] != 0]:
        estimated = midpoint(high_precision_row(row, SOLVE_INPUTS), rate)
        observed = high_precision_row(row, SOLVE_OUTPUTS)
        for key, value in zip(SOLVE_OUTPUTS, estimated, strict=True):
            peak[key] = max(peak[key], abs(observed[key] - value))
    return {key: float(value) for key, value in peak.items()}


def contributions(local, upper, rate):
    l, u = (high_precision_row(row, SOLVE_INPUTS) for row in (local, upper))
    actual = Decimal.from_float(float(local['lip_flow_cm3_s'])) - Decimal.from_float(float(upper['lip_flow_cm3_s']))
    local_result, upper_result = [midpoint(inputs, rate)[2] for inputs in (l, u)]
    inflow_first = midpoint(u | {'inflow_cm3_s': l['inflow_cm3_s']}, rate)[2] - upper_result
    inflow_last = local_result - midpoint(l | {'inflow_cm3_s': u['inflow_cm3_s']}, rate)[2]
    inflow = (inflow_first + inflow_last) / 2
    prediction = local_result - upper_result
    return {
        'measured_difference_cm3_s': float(actual),
        'recomputed_difference_cm3_s': float(prediction),
        'inflow_contribution_cm3_s': float(inflow),
        'other_inputs_contribution_cm3_s': float(prediction - inflow),
        'arithmetic_residual_cm3_s': float(actual - prediction),
    }


def first_differences(local, upper):
    result = {}
    for field in FIELDS:
        different = np.flatnonzero(local[field] != upper[field])
        result[field] = int(local['internal_sample'][different[0]]) if different.size else None
    return result


def explore_geometry_inflow(traces, onset_index, rate):
    # 口端が静止していた直後の1ステップなので、二つの平滑器を初期値0から進める。
    alpha = 1.0 - math.exp(-math.tau * 60.0 / rate)
    result, high_precision = {}, {}
    for side, trace in traces.items():
        previous, current = trace[onset_index - 1:onset_index + 1]
        pairs = [(float(row['area_cm2']), float(row['length_cm'])) for row in (previous, current)]
        old, new = [area * length for area, length in pairs]
        exact_old, exact_new = [Decimal.from_float(area) * Decimal.from_float(length) for area, length in pairs]
        raw = (old - new) * rate
        high_precision[side] = (exact_old - exact_new) * rate * Decimal.from_float(alpha)**2
        result[side] = {
            'old_volume_cm3': old, 'new_volume_cm3': new,
            'rounded_volume_change_cm3': old - new, 'raw_outflow_cm3_s': raw,
            'replayed_filtered_flow_cm3_s': alpha * (alpha * raw),
            'observed_filtered_flow_cm3_s': float(current['geometry_inflow_cm3_s']),
        }
    return {'coefficient': alpha, 'sides': result,
            'filtered_flow_difference_with_unrounded_volume_products_cm3_s': float(
                high_precision['candidate'] - high_precision['upstream'])}


def measure(study, references, out, execute):
    (rate, cli), traces, waves, plans = capture(study, references, out, execute)
    lo, hi = study['observation_internal_samples']
    onset = study['first_observed_lip_difference']
    internal_rate = study['internal_sample_rate_hz']
    frames = study['pcm_frames']
    local, upper = traces['candidate'], traces['upstream']
    archives = {side: read_components(references[f'{side}-radiation.csv'], study['reference_traced_internal_samples'])
                for side in traces}
    first = first_differences(local, upper)
    with localcontext() as context:
        context.prec = 70
        errors = {side: model_errors(trace, internal_rate) for side, trace in traces.items()}
        split = contributions(local[onset - lo], upper[onset - lo], internal_rate)
        geometry_exploration = explore_geometry_inflow(traces, onset - lo, internal_rate)
    tol = study['tolerances']
    local_case = read_json(references['mixed-gain.json'])['song_voice']
    upper_case = read_json(references['upper-2-input.json'])
    checks = {
        'same_body_and_rates': local_case['body'] == upper_case['body'] == study['body']
        and rate == local_case['voice']['output_sample_rate_hz'] == upper_case['sample_rate_hz'] == study['sample_rate_hz']
        and local_case['internal_sample_rate_hz'] == internal_rate,
        'pcm_matches_normal_cli_and_archive': noise.bit_equal(cli, waves['candidate'])
        and all(len(waves[side]) == frames and noise.bit_equal(
            waves[side], np.fromfile(references[f'{side}-pcm.f32le'], dtype='<f4')) for side in traces),
        'plans_match_archive': all(plans[side] == sha256(references[f'{side}-gestures.json']) for side in traces),
        'lip_flow_matches_prior': all(np.array_equal(traces[side]['lip_flow_cm3_s'].view('<u8'),
                                                    archives[side]['lip_cm3_s'][lo-1:hi].view('<u8')) for side in traces),
        'open_at_onset': all(trace['solved'][onset - lo] == 1.0 for trace in traces.values()),
        'independent_midpoint_pressure_and_flows': all(
            row['new_pressure_dyn_cm2'] <= tol['pressure_dyn_cm2']
            and max(row[field] for field in SOLVE_OUTPUTS[1:]) <= tol['output_flow_cm3_s'] for row in errors.values()),
    }
    predictions = {
        'matches_first_observed_lip_difference': first['lip_flow_cm3_s'] == onset,
        'zero_prior_pressure_and_inertance_flow_at_onset': all(
            trace[field][onset - lo] == 0.0 for trace in traces.values() for field in SOLVE_INPUTS[3:5]),
        'input_difference_exceeds_arithmetic_residual': (
            abs(split['arithmetic_residual_cm3_s']) <= tol['first_difference_residual_cm3_s']
            and abs(split['recomputed_difference_cm3_s']) > tol['first_difference_residual_cm3_s']),
    }
    snapshots = {sample: {side: {field: float(trace[field][sample - lo]) for field in FIELDS}
                          for side, trace in traces.items()} for sample in (onset - 1, onset, onset + 1)}
    return {'checks': checks, 'predictions': predictions, 'first_unequal_internal_sample': first,
            'midpoint_peak_errors': errors, 'onset_contributions': split, 'snapshots': snapshots,
            'exploratory_geometry_inflow': geometry_exploration,
            'observation_internal_samples': [lo, hi], 'pcm_frames': frames}


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
        ('reference', 'duet-mixed-radiation-origin',
         tuple(f'{side}-{suffix}' for side in ('candidate', 'upstream') for suffix in ('radiation.csv', 'pcm.f32le', 'gestures.json'))),
        ('settings', 'duet-mixed-output-gain', ('mixed-gain.json',)),
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
              COLUMNS_PATCH, LOCAL_PATCH, UPPER_PATCH, SHARED_PROBE, EMBEDDED_DICTIONARY, *noise.PROBES, *noise.DICTIONARIES,
              *manifests, *references.values(), *candidate_sources(), WORKSPACE / 'crates/vocal-core/tests/uniform_tube.rs',
              *(UPSTREAM / name for name in ('crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/src/physics.rs', 'crates/chimera/tests/airway.rs', 'crates/chimera/tests/engine.rs')),
              *(noise.TOOLS / name for name in ('measure_duet_mixed_radiation_origin.py', 'measure_uniform_tube.py',
                  'measure_fan_crossing_allocations.py', 'measure_wasm_fixed.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, references, out, execute), command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
