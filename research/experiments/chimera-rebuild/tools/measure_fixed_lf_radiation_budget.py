"""固定 /ɑ/ の通常発声とLF駆動の放射差を、倍音と放射成分ごとに照合する。"""

import argparse
import csv
import gzip
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
import measure_fixed_lf as lf
import measure_vowel_voice as vowel
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-lf-radiation-harmonic-budget.json'
ROOT = WORKSPACE.parents[2]
FIELDS = ('sample', 'wall', 'lip', 'nose', 'total', 'previous_total', 'derivative')
FILES = ('case.json', 'trace.csv.gz', 'block-128.wav', 'upstream-internal.f64', 'upstream-voice.f32')


def read(path):
    return json.loads(path.read_text())


def archive_inputs(study):
    spec = study['reference']
    run, manifest = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    header = run / 'manifest.json'
    if manifest['status'] != 'fail' or sha256(header) != spec['manifest_sha256']:
        raise ValueError('固定LFの保存実行が登録した判定およびハッシュと一致しません')
    summary = verified_path((run, manifest), 'summary.json')
    observed_failed = sorted(key for key, ok in read(summary)['checks'].items() if not ok)
    if observed_failed != spec['expected_failed_checks']:
        raise ValueError('保存実行の不合格項目が登録と一致しません')
    row, = (item for item in manifest['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json'))
    definition = run / manifest['source_snapshot'] / row['path']
    if sha256(definition) != row['sha256']:
        raise ValueError('保存した固定LFケースのSHA-256を照合できません')
    paths = {'manifest': header, 'definition': definition, 'summary': summary,
             'patch': verified_path((run, manifest), 'artifacts/upstream-fixed-flow.patch')}
    for arm in study['measurement']['conditions']:
        files = (*FILES, 'upstream-input.f64') if arm == 'lf' else FILES
        paths.update({f'{arm}/{name}': verified_path((run, manifest), f'artifacts/{arm}/{name}') for name in files})
    return paths


def native_trace(path, count):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt') as stream:
        header = tuple(stream.readline().strip().split(','))
        values = np.loadtxt(stream, delimiter=',')
    if header != vowel.TRACE or values.shape != (count, len(header)) or not np.isfinite(values).all():
        raise ValueError(f'研究版の固定発声の観測列または長さが不正です ({path.name})')
    index = header.index('internal_sample')
    if not np.array_equal(values[:, index], np.arange(count)):
        raise ValueError('研究版の内部標本番号が連続していません')
    return np.column_stack([values[:, header.index(key)] for key in lf.OBSERVED])


def read_pcm(path, rate, frames):
    found_rate, samples = wavfile.read(path)
    if found_rate != rate or samples.shape != (frames,) or samples.dtype != np.float32 or not np.isfinite(samples).all():
        raise ValueError(f'出力PCMのレートまたは標本形式が一致しません ({path.name})')
    return samples


def wall_capture_edits(start, end):
    mark = '        self.rad_prev_total = rad_total;'
    capture = f"""        let sample = self.research_radiation_sample;
        self.research_radiation_sample += 1;
        if ({start - 1}..{end}).contains(&sample) {{
            let lip = self.rad_u[0];
            let nose = self.rad_u[1];
            println!("{{sample}},{{wall_rad_sum:?}},{{lip:?}},{{nose:?}},{{rad_total:?}},{{:?}},{{out:?}}",
                self.rad_prev_total);
        }}
"""
    return (('    rad_prev_total: f64,', '    rad_prev_total: f64,\n    research_radiation_sample: usize,'),
            ('            rad_prev_total: 0.0,', '            rad_prev_total: 0.0,\n            research_radiation_sample: 0,'),
            (mark, capture + mark))


def capture(study, paths, out, execute):
    cfg = study['measurement']
    base = read(paths['definition'])
    fs, rate, count = cfg['internal_rate_hz'], cfg['output_rate_hz'], base['duration_samples']
    frames = count * rate // fs
    begin, end = cfg['steady_window_samples']
    expected = (base['internal_rate_hz'], base['output_rate_hz'], base['steady_window_samples'], base['f0_hz'])
    if (fs, rate, [begin, end], cfg['f0_hz']) != expected or (end - begin) * cfg['f0_hz'] != cfg['cycles'] * fs:
        raise ValueError('22周期の定常窓、レートまたは基本周波数が保存実行と異なります')
    for test in ('voice_source', 'lung_port'):
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', test],
                cwd=UPSTREAM, stdout=out / f'upstream-{test}.log')

    arrays = {}
    with TemporaryDirectory(prefix='lf-radiation-', dir=out) as directory:
        scratch = Path(directory)
        source = scratch / 'source'
        source.mkdir()
        tar = scratch / 'upstream.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        execute(['git', 'apply', str(paths['patch'])], cwd=source)
        side_patch = lf.patch_source(source, lf.UPPER_NETWORK, wall_capture_edits(begin, end))
        (out / 'wall-observation.patch').write_text(side_patch)
        binary = build_upstream_probe(vowel.PROBE, scratch, execute, upstream=source,
                                      rustc_args=('--cfg', 'research_fixed_glottal_flow'),
                                      cargo_args=('--offline', '--target-dir', str(scratch / 'target')))

        for arm in cfg['conditions']:
            folder = scratch / arm
            folder.mkdir()
            definition = paths[f'{arm}/case.json']
            native_path = folder / 'native.csv'
            wave_path = folder / 'native.wav'
            execute([*lf.CLI, 'render', str(definition), str(native_path)])
            execute([*lf.CLI, 'render-pcm', str(definition), str(wave_path), '--no-trace', '128'])
            arrays[f'{arm}_candidate'] = native_trace(native_path, count)
            arrays[f'{arm}_candidate_pcm'] = read_pcm(wave_path, rate, frames)

            spec = read(definition)
            voice = spec['voice']
            output = folder / 'radiation.csv'
            args = [spec['measurement']['voice']['ipa'], fs, rate, frames, *(voice[key] for key in
                    ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), folder]
            if arm == 'lf':
                args.append(paths['lf/upstream-input.f64'])
            execute([str(binary), 'render-research-flow', *map(str, args)], cwd=UPSTREAM, stdout=output)
            arrays[f'{arm}_upstream'] = np.fromfile(folder / 'upstream-internal.f64', dtype='<f8').reshape(count, len(lf.OBSERVED))
            arrays[f'{arm}_upstream_pcm'] = np.fromfile(folder / 'upstream-voice.f32', dtype='<f4')
            arrays[f'{arm}_terms'] = np.loadtxt(output, delimiter=',')
    np.savez_compressed(out / 'radiation-observations.npz', **arrays)


def complex_spectrum(values):
    return np.fft.rfft(values) / len(values)


def weights(count):
    result = np.full(count // 2 + 1, 2.0)
    result[0] = 0.0
    if count % 2 == 0:
        result[-1] = 1.0
    return result


def relative_error(actual, expected):
    peak = np.max(np.abs(expected))
    return float(np.max(np.abs(actual - expected)) / peak) if peak else (0.0 if np.array_equal(actual, expected) else float('inf'))


def signals_in_window(terms, fs):
    rows = dict(zip(FIELDS, terms.T, strict=True))
    steady = lambda name: rows[name][1:]
    lip, nose, wall = (np.diff(rows[key]) * fs for key in ('lip', 'nose', 'wall'))
    return {'lip_flow': steady('lip'), 'lip': lip, 'nose': nose, 'wall': wall, 'total': steady('derivative')}


def analyze_arm(terms, source, cfg, bins):
    fs = cfg['internal_rate_hz']
    positions = {name: i for i, name in enumerate(FIELDS)}
    start, end = cfg['steady_window_samples']
    if (terms.shape != (end - start + 1, len(FIELDS)) or not np.isfinite(terms).all()
            or not np.array_equal(terms[:, 0], np.arange(start-1, end))):
        raise ValueError('壁・開口を含む上流の放射観測の長さまたは標本番号が不正です')
    raw = source[start-1:end]
    same_fields = all(np.array_equal(terms[:, positions[name]], raw[:, lf.OBSERVED.index(src)])
                      for name, src in (('lip', lf.LIP), ('nose', 'nose_flow_cm3_s'), ('derivative', lf.RAD)))
    flow_sum = terms[:, positions['wall']] + terms[:, positions['lip']] + terms[:, positions['nose']]
    total = terms[:, positions['total']]
    prior = terms[:, positions['previous_total']]
    derivative = terms[:, positions['derivative']]
    current_laws = {'observation_matches_source': same_fields,
                    'wall_and_openings_sum': bool(np.array_equal(flow_sum, total)),
                    'prior_total_is_previous_sample': bool(np.array_equal(prior[1:], total[:-1])),
                    'backward_difference_reconstructs_output': bool(np.array_equal((total-prior)*fs, derivative))}
    signals = signals_in_window(terms, fs)
    spectra = {name: complex_spectrum(values) for name, values in signals.items()}
    count = end - start
    scale = weights(count)
    power = {name: scale * np.square(np.abs(values)) for name, values in spectra.items()}
    for a, b in (('lip', 'wall'), ('lip', 'nose'), ('nose', 'wall')):
        power[f'{a}_{b}_cross'] = 2 * scale * np.real(spectra[a] * np.conj(spectra[b]))
    component_sum = sum(values for name, values in power.items() if name not in ('total', 'lip_flow'))
    relative = cfg['relative_identity_tolerance']
    parseval = {name: relative_error(np.var(values), power[name].sum()) for name, values in signals.items()}
    spectral_errors, endpoint_corrections = {}, {}
    factor = -fs * np.expm1(-2j * np.pi * np.arange(len(scale)) / count)
    for key, signal in (('lip', 'lip'), ('nose', 'nose'), ('wall', 'wall'), ('total', 'total')):
        flow = terms[:, positions[key]]
        correction = fs * (flow[-1] - flow[0]) / count
        endpoint_corrections[key] = float(correction)
        predicted = factor * complex_spectrum(flow[1:]) + correction
        spectral_errors[key] = relative_error(predicted, spectra[signal])
    covariance_error = relative_error(component_sum, power['total'])
    direct_sum_error = relative_error(signals['lip'] + signals['wall'] + signals['nose'], signals['total'])
    current_laws.update(parseval=all(x < relative for x in parseval.values()),
                        exact_discrete_difference_frequency_response=all(x < relative for x in spectral_errors.values()),
                        radiation_covariance_closes=covariance_error < relative and direct_sum_error < relative)
    stats = {'ac_rms': {name: float(values.std()) for name, values in signals.items()},
             'parseval_relative_errors': parseval, 'difference_response_relative_errors': spectral_errors,
             'endpoint_bin_corrections': endpoint_corrections, 'covariance_relative_error': covariance_error,
             'component_time_sum_relative_error': direct_sum_error,
             'first_12_harmonic_amplitude': {key: (2 * abs(spectra[key][bins])).tolist()
                                            for key in ('lip_flow', 'lip', 'wall', 'total')}}
    return current_laws, stats, power


def compare_to_legacy(capture, paths, study, bins):
    cfg = study['measurement']
    base = read(paths['definition'])
    count = base['duration_samples']
    rate = cfg['output_rate_hz']
    frames = count * rate // cfg['internal_rate_hz']
    prior = read(paths['summary'])
    checks = {}
    for arm in cfg['conditions']:
        candidate, upstream = (capture[f'{arm}_{name}'] for name in ('candidate', 'upstream'))
        old_candidate = native_trace(paths[f'{arm}/trace.csv.gz'], count)
        old_upper = np.fromfile(paths[f'{arm}/upstream-internal.f64'], dtype='<f8').reshape(count, len(lf.OBSERVED))
        cp, up = (capture[f'{arm}_{name}_pcm'] for name in ('candidate', 'upstream'))
        old_cp = read_pcm(paths[f'{arm}/block-128.wav'], rate, frames)
        old_up = np.fromfile(paths[f'{arm}/upstream-voice.f32'], dtype='<f4')
        close = cfg['relative_trace_tolerance']
        checks[f'{arm}/fresh_native_pcm_and_internal_matches_archive'] = (
            np.array_equal(cp.view('<u4'), old_cp.view('<u4'))
            and all(relative_error(a, b) < close for a, b in zip(candidate.T, old_candidate.T, strict=True)))
        checks[f'{arm}/fresh_upstream_pcm_and_internal_matches_archive'] = (
            np.array_equal(up.view('<u4'), old_up.view('<u4'))
            and all(relative_error(a, b) < close for a, b in zip(upstream.T, old_upper.T, strict=True)))
        start, end = cfg['steady_window_samples']
        signals = dict(zip(lf.OBSERVED, candidate.T, strict=True))
        lip = np.diff(signals[lf.LIP], prepend=0) * cfg['internal_rate_hz']
        nose = np.diff(signals[lf.OBSERVED[4]], prepend=0) * cfg['internal_rate_hz']
        signals |= {'lip_derivative_cm3_s2': lip, 'wall_derivative_cm3_s2': signals[lf.RAD] - (lip+nose)}
        checks[f'{arm}/legacy_levels_and_harmonics'] = all(
            relative_error(values[start:end].std(), prior['stats'][arm][key]['ac_rms']) < cfg['relative_legacy_measurement_tolerance']
            and relative_error(2 * abs(complex_spectrum(values[start:end])[bins]),
                               prior['stats'][arm][key]['harmonics']) < cfg['relative_legacy_measurement_tolerance']
            for key, values in signals.items())
    return checks


def partition(power, bins, cycles):
    base = np.arange(cycles, len(power), cycles)
    other = np.ones(len(power), dtype=bool)
    other[0] = False
    other[base] = False
    return {'fundamental': float(power[bins[0]]), 'harmonics_2_to_report_limit': float(power[bins[1:]].sum()),
            'remaining_harmonics': float(power[base[base > bins[-1]]].sum()), 'non_harmonic_bins': float(power[other].sum())}


def analyze(study, paths, out):
    cfg = study['measurement']
    with np.load(out / 'radiation-observations.npz', allow_pickle=False) as archive:
        capture = dict(archive)
    harmonics = np.arange(1, cfg['reported_harmonics'] + 1)
    bins = cfg['cycles'] * harmonics
    count = cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0]
    checks = compare_to_legacy(capture, paths, study, bins[:cfg['original_harmonics']])
    stats, powers = {}, {}
    for arm in cfg['conditions']:
        result, stats[arm], powers[arm] = analyze_arm(capture[f'{arm}_terms'], capture[f'{arm}_upstream'],
                                                      cfg, bins[:cfg['original_harmonics']])
        checks.update({f'{arm}/{key}': value for key, value in result.items()})
    normal, driven = (powers[key] for key in ('coupled', 'lf'))
    delta = {key: driven[key] - normal[key] for key in normal}
    group_deltas = {key: partition(values, bins, cfg['cycles']) for key, values in delta.items()}
    totals = {key: float(np.sum(values)) for key, values in delta.items()}
    full_loss = totals['total']
    lip_fraction = totals['lip'] / full_loss
    priority = cfg['cycles'] * np.asarray(cfg['priority_harmonics'])
    weighted_fraction = float(delta['lip'][priority].sum() / totals['lip'])
    fundamental_change = group_deltas['lip_flow']['fundamental']
    raw_lip = capture['lf_terms'][1:, FIELDS.index('lip')]
    swapped = complex_spectrum(raw_lip)
    swapped[0] = 0.0
    ordinary_lip = capture['coupled_terms'][1:, FIELDS.index('lip')]
    swapped[bins[0]] = complex_spectrum(ordinary_lip)[bins[0]]
    replaced_rms = float(np.fft.irfft(swapped * count, n=count).std())
    expected_rms = float(np.sqrt(driven['lip_flow'].sum() - fundamental_change))
    relative_swap = replaced_rms / stats['coupled']['ac_rms']['lip_flow'] - 1
    checks['fundamental_replacement_matches_power_budget'] = relative_error(replaced_rms, expected_rms) < cfg['relative_identity_tolerance']
    hypotheses = {
        'increased_fundamental_offsets_lip_ac_loss': fundamental_change > 0
        and totals['lip_flow'] - fundamental_change < 0 and relative_swap <= -cfg['legacy_relative_rms_threshold'],
        'time_difference_weights_sixth_and_seventh_harmonics': weighted_fraction >= cfg['minimum_priority_fraction_of_lip_derivative_loss'],
        'lip_derivative_explains_most_of_total_radiation_loss': lip_fraction >= cfg['minimum_lip_fraction_of_radiation_loss'],
    }
    table = [{'harmonic': int(h), 'frequency_hz': float(h * cfg['f0_hz']),
              **{key: float(values[index]) for key, values in delta.items()}}
             for h, index in zip(harmonics, bins, strict=True)]
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'hypotheses': {key: bool(value) for key, value in hypotheses.items()}, 'conditions': stats,
            'harmonic_power_deltas': table, 'partitioned_power_deltas': group_deltas, 'all_bin_power_deltas': totals,
            'lip_derivative_fraction_of_radiation_loss': lip_fraction,
            'priority_fraction_of_lip_derivative_loss': weighted_fraction,
            'lip_fundamental_replaced_rms': replaced_rms, 'lip_fundamental_replaced_relative_rms': relative_swap,
            'legacy_decision': read(paths['summary'])['checks']['lf_acoustic_level_difference']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    paths = archive_inputs(study)

    def measure(out, execute):
        capture(study, paths, out, execute)
        result = analyze(study, paths, out)
        with (out / 'harmonic-power-deltas.csv').open('w', newline='') as stream:
            rows = result['harmonic_power_deltas']
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        return result

    inputs = [CASE, Path(__file__), *paths.values(), Path(lf.__file__), Path(vowel.__file__),
              Path(vowel.shared.__file__), vowel.PROBE, *candidate_sources(), UPSTREAM / lf.UPPER_NETWORK,
              UPSTREAM / lf.UPPER_VOICE, *(UPSTREAM / f'crates/chimera/tests/{name}.rs'
                                           for name in ('voice_source', 'lung_port'))]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
