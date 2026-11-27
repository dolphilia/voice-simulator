"""セル体積差の展開式を通常レンダーと厳密分数に照合する。"""

import argparse
from fractions import Fraction
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
import measure_duet_mixed_lip_load_origin as lip
import measure_moving_area as moving
from measure_fan_crossing_allocations import bit_comparison, run_manifest, verified_path
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import compare_pcm, read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-mixed-volume-difference.json'
EXPANSION = lip.PATCH_DIR / 'candidate-expanded-volume-difference.patch'
DICTIONARY = noise.DICTIONARIES[0]
REGRESSIONS = ('moving-aperture-release', 'sealed-cavity-compression')
SHAPE = ('area_cm2', 'length_cm')


def capture(study, references, sources, out, execute, scratch, expanded):
    out.mkdir()
    scratch.mkdir()
    lip.copy_inputs(sources, scratch)
    if expanded:
        execute(['git', 'apply', '--verbose', str(EXPANSION)], cwd=scratch)

    # 通常CLIの後で計測差分を適用し、観測器がPCMを変えないことも判定する。
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    wav = out / 'cli.wav'
    execute([*prefix, 'render-pcm', str(references['input']), str(wav), '--no-trace', '128'], cwd=scratch)
    regressions = {}
    for name in REGRESSIONS:
        target = out / name
        target.mkdir()
        case_path = WORKSPACE / 'cases' / f'{name}.json'
        execute([*prefix, 'render', str(case_path), str(target / 'trace.csv')], cwd=scratch)
        regressions[name] = moving.measure(read_json(case_path), target, references[name])

    execute(['git', 'apply', '--verbose', str(lip.COLUMNS_PATCH), str(lip.LOCAL_PATCH)], cwd=scratch)
    probe = build_upstream_probe(scratch / 'tools' / noise.PROBES[0].name, out, execute,
                                 upstream=scratch, lto='off', package='vocal-core', extra_libraries=('serde_json',))
    lo, hi = study['observation_internal_samples']
    case = out / 'probe-input.json'
    settings = read_json(references['input']) | {'probe_first_output_frame': (lo - 1) // 2}
    case.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + '\n')
    dictionary = scratch / 'local.dict'
    with gzip.open(DICTIONARY, 'rb') as src, dictionary.open('wb') as dst:
        shutil.copyfileobj(src, dst)
    trace, pcm, plan = (out / name for name in ('lip-load.csv', 'pcm.f32le', 'gestures.json'))
    execute([str(probe), str(case), str(dictionary), str(hi // 2), str(scratch / 'noise.csv'),
             str(pcm), '--radiation-components', str(trace)], stdout=plan)
    rate, samples = wavfile.read(wav)
    return {'rate': rate, 'pcm': samples, 'observed_pcm': np.fromfile(pcm, dtype='<f4'),
            'trace': lip.read_solve_trace(trace, lo, hi), 'plan': sha256(plan), 'regressions': regressions}


def volume_flows(previous, current, dt):
    old_area, new_area = (max(float(row[SHAPE[0]]), 0.02) for row in (previous, current))
    old_length, new_length = (float(row[SHAPE[1]]) for row in (previous, current))
    rounded = (old_area * old_length - new_area * new_length) / dt
    expanded = ((old_area - new_area) * old_length + new_area * (old_length - new_length)) / dt
    exact_old, exact_new = [Fraction(area) * Fraction(length)
                            for area, length in ((old_area, old_length), (new_area, new_length))]
    exact = (exact_old - exact_new) / Fraction(dt)
    return rounded, expanded, exact


def error_stats(values):
    absolute_errors = [float(abs(Fraction(value) - exact)) for value, exact in values]
    return {'peak_cm3_s': max(absolute_errors), 'rms_cm3_s': math.sqrt(math.fsum(
        error * error for error in absolute_errors) / len(absolute_errors))}


def model(traces, study):
    onset = study['first_observed_lip_difference']
    dt = 1.0 / study['internal_sample_rate_hz']
    alpha = 1.0 - math.exp(-math.tau * 60.0 * dt)
    onset_results = {}
    for side, data in traces.items():
        idx = int(onset - data[0]['internal_sample'])
        previous, current = data[idx - 1:idx + 1]
        if any(row['solved'] != 1.0 for row in (previous, current)):
            raise ValueError('初出点と直前の口端が開いている必要があります')
        rounded, expanded, exact = volume_flows(previous, current, dt)
        onset_results[side] = {
            'raw_cm3_s': {'rounded': rounded, 'expanded': expanded, 'exact': float(exact)},
            'raw_absolute_errors_cm3_s': {'rounded': float(abs(Fraction(rounded) - exact)),
                                         'expanded': float(abs(Fraction(expanded) - exact))},
            'from_rest_cm3_s': {'rounded': alpha * (alpha * rounded), 'expanded': alpha * (alpha * expanded),
                                'exact': float(exact * Fraction(alpha)**2)},
            'prior_observed_source_cm3_s': float(previous['geometry_inflow_cm3_s']),
            'observed_source_cm3_s': float(current['geometry_inflow_cm3_s']),
            'observed_lip_cm3_s': float(current['lip_flow_cm3_s']),
        }
    lo, hi = study['additional_interval']
    rows = traces['baseline']
    series = [volume_flows(previous, current, dt) for previous, current in zip(rows[:-1], rows[1:], strict=True)
              if lo <= current['internal_sample'] <= hi and previous['solved'] == current['solved'] == 1.0
              and any(previous[field] != current[field] for field in SHAPE)]
    if not series:
        raise ValueError('後続区間に連続開口かつ形状が変わった点がありません')
    later = {'moving_open_steps': len(series),
             'rounded': error_stats((a, c) for a, _, c in series),
             'expanded': error_stats((b, c) for _, b, c in series)}
    return onset_results, later


def measure(study, references, sources, out, execute):
    lo, hi = study['observation_internal_samples']
    if study['internal_sample_rate_hz'] != 2 * study['output_sample_rate_hz'] or (lo - 1) % 2 or hi % 2:
        raise ValueError('観測の始点・終点は2内部サンプルを含む出力フレームの境界に指定してください')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-adversarial.log')
    with TemporaryDirectory(prefix='duet-volume-difference-', dir=out.parent) as directory:
        renders = {side: capture(study, references, sources, out / side, execute, Path(directory) / side, expanded)
                   for side, expanded in (('baseline', False), ('expanded', True))}
    prior_lo, prior_hi = study['prior_observation_internal_samples']
    traces = {side: value['trace'] for side, value in renders.items()}
    traces['upstream'] = lip.read_solve_trace(references['upstream-trace'], prior_lo, prior_hi)
    before = renders['baseline']
    after = renders['expanded']
    onset, later = model(traces, study)
    archived = lip.read_solve_trace(references['candidate-trace'], prior_lo, prior_hi)
    captured = before['trace'][prior_lo-lo:prior_hi-lo+1]
    allowed = study['pcm_absolute_tolerance']
    upper = np.fromfile(references['upstream-pcm'], dtype='<f4')
    pcm = {'expanded_vs_baseline': compare_pcm(after['pcm'], before['pcm'], allowed),
           'baseline_vs_upstream': compare_pcm(before['pcm'], upper, allowed),
           'expanded_vs_upstream': compare_pcm(after['pcm'], upper, allowed)}
    observation_diffs = lip.first_differences(before['trace'], after['trace'])
    ratio = study['minimum_peak_error_reduction']
    raw = onset['baseline']['raw_absolute_errors_cm3_s']
    regressions = {side: item['regressions'] for side, item in renders.items()}
    comparisons = {label: onset[label]['observed_source_cm3_s'] - onset['upstream']['observed_source_cm3_s']
                   for label in renders}
    comparisons['both_expanded_recomputed'] = (onset['expanded']['from_rest_cm3_s']['expanded']
                                                - onset['upstream']['from_rest_cm3_s']['expanded'])
    checks = {
        'normal_cli_agrees_with_observer': all(item['rate'] == study['output_sample_rate_hz']
            and len(item['pcm']) == study['pcm_frames'] and item['pcm'].dtype == np.float32
            and noise.bit_equal(item['pcm'], item['observed_pcm']) for item in renders.values()),
        'baseline_matches_archive': noise.bit_equal(before['pcm'], np.fromfile(references['candidate-pcm'], dtype='<f4'))
            and before['plan'] == sha256(references['candidate-plan'])
            and all(bit_comparison(captured[field], archived[field])['different_values'] == 0 for field in lip.FIELDS),
        'same_plan_and_observed_geometry': before['plan'] == after['plan']
            and all(bit_comparison(before['trace'][field], after['trace'][field])['different_values'] == 0
                    for field in ('solved', *SHAPE)),
        'onset_raw_error_reduction': raw['rounded'] > 0 and raw['expanded'] * ratio <= raw['rounded'],
        'additional_raw_error_reduction': later['moving_open_steps'] >= study['minimum_moving_open_steps_additional']
            and later['rounded']['peak_cm3_s'] > 0
            and later['expanded']['peak_cm3_s'] * ratio <= later['rounded']['peak_cm3_s'],
        'onset_source_recomputed': all(onset[side]['prior_observed_source_cm3_s'] == 0.0
            and abs(onset[side]['observed_source_cm3_s'] - onset[side]['from_rest_cm3_s'][formula])
            <= study['onset_source_absolute_tolerance_cm3_s']
            for side, formula in (('baseline', 'rounded'), ('expanded', 'expanded'), ('upstream', 'rounded'))),
        'pcm_within_existing_limit': all(item['first_frame_over_tolerance'] is None for item in pcm.values()),
        'moving_area_regressions': all(all(result['checks'].values())
            for side in regressions.values() for result in side.values()),
    }
    return {'checks': checks, 'onset': onset, 'additional_interval_raw_errors': later,
            'onset_source_difference_vs_upstream_cm3_s': comparisons, 'pcm': pcm,
            'first_differing_observed_internal_sample': observation_diffs, 'regressions': regressions}


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
    refs, manifests = {}, []
    for key, (run_id, case_id, digest) in study['references'].items():
        run = run_manifest(run_id, case_id, revision)
        manifest = run[0] / 'manifest.json'
        if run[1]['status'] != 'pass' or sha256(manifest) != digest:
            parser.error(f'先行実行 {run_id} が登録と一致しません')
        manifests.append(manifest)
        refs[key] = run
    files = {'input': verified_path(refs['settings'], 'artifacts/mixed-gain.json'),
             'candidate-plan': verified_path(refs['lip'], 'artifacts/candidate-gestures.json')}
    for side in ('candidate', 'upstream'):
        files[f'{side}-pcm'] = verified_path(refs['lip'], f'artifacts/{side}-pcm.f32le')
        files[f'{side}-trace'] = verified_path(refs['lip'], f'artifacts/{side}-lip-load.csv')
    for name in REGRESSIONS:
        files[name] = verified_path(refs[name], 'artifacts/upstream-trace.csv')
    sources = [*candidate_sources(), lip.EMBEDDED_DICTIONARY, DICTIONARY, lip.SHARED_PROBE, noise.PROBES[0]]
    inputs = [CASE, Path(__file__).resolve(), EXPANSION, lip.LOCAL_PATCH, lip.COLUMNS_PATCH,
              *sources, *manifests, *files.values(), *(WORKSPACE / 'cases' / f'{name}.json' for name in REGRESSIONS),
              *(UPSTREAM / path for path in ('crates/chimera/src/airway/network.rs', 'crates/chimera/tests/airway_adversarial.rs')),
              *(noise.TOOLS / f'{name}.py' for name in ('measure_duet_mixed_lip_load_origin', 'measure_moving_area',
                  'measure_uniform_tube', 'measure_duet_child_glottal_noise_origin', 'measure_fan_crossing_allocations',
                  'measure_wasm_fixed', 'upstream_baseline'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, files, sources, out, execute),
                              command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
