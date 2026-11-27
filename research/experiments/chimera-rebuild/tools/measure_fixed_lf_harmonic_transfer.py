"""固定 /ɑ/ の第6・第7倍音で、声門入力と口端伝達の変化を照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_lf as lf
import measure_vowel_transfer as vowel
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_vowel_open_o_high_bandwidth import source_elements
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-lf-harmonic-transfer.json'
FREQUENCY = 'crates/chimera/src/airway/frequency.rs'
NETWORK_FILES = ('upstream-linear-nodes.csv', 'upstream-linear-branches.csv', 'upstream-vowel-settings.csv')
EVIDENCE = ('linear-case.json', 'candidate-linear.csv', 'upstream-complex.csv', 'upstream-trace.csv',
            'upstream-observation.patch', *NETWORK_FILES)


def read(path):
    return json.loads(path.read_text())


def archive_inputs(study):
    paths = {}
    for arm, spec in study['references'].items():
        run, manifest = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
        header = run / 'manifest.json'
        if manifest['status'] != spec['status'] or sha256(header) != spec['manifest_sha256']:
            raise ValueError(f'保存した実行のハッシュまたは判定が不一致です ({run.name})')
        definition, = (item for item in manifest['inputs']
                       if Path(item['path']).name == f'{spec["case"]}.json')
        case = run / manifest['source_snapshot'] / definition['path']
        if sha256(case) != definition['sha256']:
            raise ValueError(f'保存したケースを照合できません ({run.name})')
        paths[arm] = {'manifest.json': header, 'case.json': case,
                      'summary.json': verified_path(record, 'summary.json')}
        outputs = {
            'radiation': ('radiation-observations.npz',),
            'legacy': ('coupled/case.json', 'lf/case.json'),
            'linear': NETWORK_FILES,
        }
        paths[arm].update({name: verified_path(record, f'artifacts/{name}') for name in outputs[arm]})
    return paths


def linear_case(study, archive):
    start, end = study['measurement']['frequencies_hz']
    case = read(archive['linear']['case.json'])
    case['transfer'] = {'start_hz': start, 'end_hz': end, 'points': 2}
    return case


def patch_complex_radiation(code):
    opening = '            if rad_of[k].is_some() {\n'
    total = '        mag[f] = hypot(ur, ui);\n'
    return lf.patch_source(code, FREQUENCY, (
        (opening, opening +
         '                println!("{},{},{},{}", freqs[f], k,\n'
         '                    pr[k] * rad_yr[k] - pi[k] * rad_yi[k], pr[k] * rad_yi[k] + pi[k] * rad_yr[k]);\n'),
        (total, '        println!("{},-1,{ur},{ui}", freqs[f]);\n' + total),
    ))


def capture(study, archive, out, execute):
    case = linear_case(study, archive)
    path = out / 'linear-case.json'
    path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--',
             'transfer', str(path), str(out / 'candidate-linear.csv')])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis',
             'analysis_matches_typescript'], cwd=UPSTREAM, stdout=out / 'upstream-analysis-test.log')

    with TemporaryDirectory(prefix='lf-transfer-', dir=out) as temporary:
        scratch = Path(temporary)
        code = scratch / 'source'
        code.mkdir()
        snapshot = scratch / 'upstream.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=snapshot)
        execute(['tar', '-xf', str(snapshot), '-C', str(code)])
        (out / 'upstream-observation.patch').write_text(patch_complex_radiation(code))
        binary = build_upstream_probe(vowel.PROBE, scratch, execute, upstream=code,
                                      extra_libraries=('serde_json',),
                                      cargo_args=('--offline', '--target-dir', str(scratch / 'target')))
        sweep = case['transfer']
        args = [case['measurement']['transfer']['ipa'], case['fixed_airway']['sample_rate_hz'],
                sweep['start_hz'], sweep['end_hz'], sweep['points'],
                case['measurement']['transfer']['peak_search_min_hz'], case['posture']['velum_cm2'], out]
        execute([str(binary), *map(str, args)], cwd=UPSTREAM, stdout=out / 'upstream-complex.csv')


def relative(actual, expected):
    return float(abs(actual - expected) / abs(expected))


def pair(values):
    return [float(values.real), float(values.imag)]


def fixed_network(study, archive, out, checks):
    cfg = study['measurement']
    frequencies = np.array(cfg['frequencies_hz'])
    nodes, edges, source = source_elements({name: out / name for name in NETWORK_FILES})
    checks['linear_geometry_matches_archive'] = all(
        sha256(out / name) == sha256(archive['linear'][name]) for name in NETWORK_FILES)
    checks['derived_case_matches_registered_sweep'] = read(out / 'linear-case.json') == linear_case(study, archive)
    independent = vowel.independent_response(frequencies, nodes, edges, source)
    observed = np.loadtxt(out / 'upstream-complex.csv', delimiter=',', ndmin=2)
    allowed = {-1, source['lips'], source['nose']}
    if (observed.shape[1] != 4 or not np.isfinite(observed).all()
            or not np.isin(observed[:, 0], frequencies).all() or not np.isin(observed[:, 1], list(allowed)).all()):
        raise ValueError('上流の複素口端流量と全放射の列が不正です')
    upstream = []
    for frequency in frequencies:
        rows = observed[observed[:, 0] == frequency]
        flow = {int(node): complex(real, imag) for _, node, real, imag in rows}
        if len(rows) != len(flow) or not {-1, source['lips']} <= flow.keys():
            raise ValueError(f'上流の複素口端流量または全放射が重複・欠落しました ({frequency} Hz)')
        lips, nose, total = flow[source['lips']], flow.get(source['nose'], 0j), flow[-1]
        upstream.append((lips, nose, total - lips - nose, total))
    upstream = np.array(upstream)
    amplitude = vowel.read_numeric_csv(out / 'upstream-trace.csv', vowel.UPSTREAM_FIELDS)
    cli = vowel.read_numeric_csv(out / 'candidate-linear.csv', vowel.CANDIDATE_FIELDS)
    checks['both_frequencies_exact'] = all(np.array_equal(a[:, 0], frequencies) for a in (cli, amplitude))
    cli_complex = cli[:, [5, 7, 9, 1]] + 1j * cli[:, [6, 8, 10, 2]]
    scale = abs(upstream[:, :1])
    error = {name: float((abs(value - upstream) / scale).max())
             for name, value in (('cli', cli_complex), ('independent', independent))}
    tol = cfg['linear_relative_error_lt']
    checks['complex_linear_upstream_cli_and_independent_match'] = all(val < tol for val in error.values())
    checks['upstream_public_magnitude_matches_observation'] = bool(
        np.all(abs(amplitude[:, 1] - abs(upstream[:, -1])) / amplitude[:, 1] < tol))
    return upstream[:, 0], error


def observed_spectra(study, archive, checks):
    cfg = study['measurement']
    start, end = cfg['steady_window_samples']
    count = end - start
    fs = cfg['internal_rate_hz']
    bins = cfg['cycles'] * np.array(cfg['harmonics'])
    tolerance = cfg['complex_identity_relative_error_lt']
    checks['window_is_registered_integer_cycles'] = (
        end > start > 0 and count * cfg['f0_hz'] == cfg['cycles'] * fs
        and np.array_equal(bins * fs / count, cfg['frequencies_hz']))
    radiation = read(archive['radiation']['case.json'])['measurement']
    checks['same_window_as_radiation_budget'] = (
        all(radiation[key] == cfg[key] for key in ('conditions', 'internal_rate_hz', 'f0_hz',
                                                   'steady_window_samples', 'cycles'))
        and radiation['priority_harmonics'] == cfg['harmonics'])
    definition = read(archive['linear']['case.json'])
    source = np.exp(-2j * np.pi / count * np.outer(bins, np.arange(count)))
    difference = fs * (1 - np.exp(-2j * np.pi / count * bins))
    spectra = {}
    columns = [lf.OBSERVED.index(name) for name in cfg['source_csv_columns']]
    with np.load(archive['radiation']['radiation-observations.npz'], allow_pickle=False) as arrays:
        for arm in cfg['conditions']:
            case = read(archive['legacy'][f'{arm}/case.json'])
            checks[f'{arm}/same_fixed_posture_and_rate'] = (
                case['posture'] == definition['posture'] and case['body'] == definition['body']
                and cfg['f0_hz'] == case['voice']['f0_hz']
                and fs == case['fixed_airway']['sample_rate_hz'] == definition['fixed_airway']['sample_rate_hz'])
            upper, candidate = (arrays[f'{arm}_{key}'][:, columns] for key in ('upstream', 'candidate'))
            if any(a.shape != (end, 2) or not np.isfinite(a).all() for a in (upper, candidate)):
                raise ValueError(f'保存した声門流量と口端流量の標本数が不一致です ({arm})')
            signals = upper[start:end]
            dft = source @ signals / count
            fft = np.fft.rfft(signals, axis=0)[bins] / count
            cli = np.fft.rfft(candidate[start:end], axis=0)[bins] / count
            checks[f'{arm}/direct_dft_and_candidate_match_fft'] = bool(
                np.all(abs(dft - fft) < tolerance * abs(fft))
                and np.all(abs(cli - fft) < tolerance * abs(fft)))

            lip = upper[:, 1]
            derivative = source @ (np.diff(lip[start-1:end]) * fs) / count
            boundary = fs * (lip[end-1] - lip[start-1]) / count
            checks[f'{arm}/finite_window_difference_formula'] = bool(
                np.all(abs(difference * dft[:, 1] + boundary - derivative) < tolerance * abs(derivative)))
            spectra[arm] = (dft[:, 0], dft[:, 1], derivative, boundary)
    return spectra, difference


def analyze(study, archive, out):
    cfg = study['measurement']
    checks = {}
    linear, errors = fixed_network(study, archive, out, checks)
    spectra, difference = observed_spectra(study, archive, checks)
    legacy = read(archive['legacy']['summary.json'])
    budget = read(archive['radiation']['summary.json'])
    failures = sorted(key for key, ok in legacy['checks'].items() if not ok)
    checks['legacy_failed_decision_retained'] = (
        failures == cfg['legacy_failed_checks'] and budget['legacy_decision'] is False)
    old_power = {r['harmonic']: r for r in budget['harmonic_power_deltas']}
    rows = []
    for index, (h, f) in enumerate(zip(cfg['harmonics'], cfg['frequencies_hz'], strict=True)):
        normal, driven = ([value[index] if np.ndim(value) else value for value in spectra[arm]]
                          for arm in cfg['conditions'])
        q, u, deriv, boundary = normal
        q_lf, u_lf, deriv_lf, boundary_lf = driven
        h_normal, h_lf = u / q, u_lf / q_lf
        source = (h_normal + h_lf) / 2 * (q_lf - q)
        transfer = (q + q_lf) / 2 * (h_lf - h_normal)
        change = u_lf - u
        ratio = abs(transfer) / abs(change)
        shift = relative(h_lf, h_normal)
        power = 2 * (abs(deriv_lf)**2 - abs(deriv)**2)
        terms = (difference[index] * source, difference[index] * transfer, boundary_lf - boundary)
        power_terms = [float(2 * ((deriv_lf + deriv) * np.conj(term)).real) for term in terms]
        tol = cfg['complex_identity_relative_error_lt']
        prior = [complex(*legacy['stats'][arm][lf.LIP]['over_glottal_flow'][h-1]) for arm in cfg['conditions']]
        checks.update({
            f'{f}Hz/legacy_complex_ratios': max(relative(h_normal, prior[0]), relative(h_lf, prior[1])) < tol,
            f'{f}Hz/complex_lip_change_factorization': relative(source + transfer, change) < tol,
            f'{f}Hz/source_dominates_lip_change': (
                shift < cfg['observed_transfer_relative_change_lt']
                and ratio < cfg['complex_transfer_term_fraction_lt']),
            f'{f}Hz/finite_window_power_budget': (
                relative(sum(power_terms), power) < tol and relative(power, old_power[h]['lip']) < tol
                and relative(2 * (abs(u_lf)**2 - abs(u)**2), old_power[h]['lip_flow']) < tol),
        })
        rows.append({
            'frequency_hz': f, 'harmonic': h,
            'glottal_flow_coupled_lf_cm3_s': [pair(q), pair(q_lf)],
            'lip_flow_coupled_lf_cm3_s': [pair(u), pair(u_lf)],
            'observed_transfer_coupled_lf': [pair(h_normal), pair(h_lf)],
            'continuous_linear_lip_transfer': pair(linear[index]),
            'observed_over_linear_magnitude': [float(abs(value / linear[index])) for value in (h_normal, h_lf)],
            'observed_minus_linear_phase_deg': [float(np.angle(value / linear[index], deg=True))
                                                for value in (h_normal, h_lf)],
            'source_magnitude_relative_change': float(abs(q_lf) / abs(q) - 1),
            'lip_magnitude_relative_change': float(abs(u_lf) / abs(u) - 1),
            'complex_transfer_relative_change': shift, 'transfer_term_fraction': float(ratio),
            'lip_derivative_mean_square_delta_cm6_s4': float(power),
            'lip_derivative_mean_square_terms_cm6_s4': dict(zip(('source', 'transfer', 'window_edge'), power_terms)),
        })
    return {'checks': {key: bool(val) for key, val in checks.items()}, 'frequencies': rows,
            'linear_relative_errors': errors, 'legacy_failed_checks': failures}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        capture(study, archive, out, execute)
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *(path for arm in archive.values() for path in arm.values()),
              Path(lf.__file__), Path(vowel.__file__), Path(vowel.shared.__file__),
              Path(source_elements.__code__.co_filename), vowel.PROBE, *candidate_sources(),
              UPSTREAM / FREQUENCY, UPSTREAM / lf.UPPER_NETWORK, UPSTREAM / lf.UPPER_VOICE,
              UPSTREAM / 'crates/chimera/tests/golden_analysis.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                              input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
