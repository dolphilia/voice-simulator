"""狭窄の乱流を上流、離散フィルタ、枝の運動量収支と照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


AFFRICATE_TEST = ('affricates',
                  'a_voiceless_affricates_frication_runs_into_the_vowel_with_no_h_after_it')


def mulberry32(seed, count):
    """32ビット整数剰余で書いた、比較用の参照乱数列。"""
    modulus = 2**32
    seed = seed or 1
    for _ in range(count):
        seed = (seed + 0x6d2b79f5) % modulus
        stage = ((seed ^ (seed >> 15)) * (seed | 1)) % modulus
        stage ^= (stage + ((stage ^ (stage >> 7)) * (stage | 61))) % modulus
        yield (stage ^ (stage >> 14)) / modulus


def reconstruct_noise(case, trace, seed):
    cfg, net = (case[name] for name in ('measurement', 'network'))
    fs = net['sample_rate_hz']
    model = net['turbulence']
    spec, = model['sources']
    left, right = spec['source']
    section, = net['tubes']
    area = np.r_[section['areas_cm2'][left], trace[f'area_{left}_cm2'][:-1]]
    area = np.minimum(area, section['areas_cm2'][right])
    flow = np.r_[0.0, trace[f'branch_flow_{left}_{right}_cm3_s'][:-1]]
    viable = area > cfg['closed_area_cm2']
    reynolds = np.divide(np.abs(flow) * 2 * 1.14e-3, 1.86e-4 * np.sqrt(np.pi * area),
                         out=np.zeros_like(flow), where=viable)
    threshold = cfg['positive_reynolds_threshold']
    saturation = cfg['saturation_reynolds']**2 - threshold**2
    excess = np.maximum(0.0, reynolds**2 - threshold**2)
    level = spec['gain'] * model['scale'] * np.sqrt(96000 / fs) * excess / (1 + excess / saturation)

    white = (2 * np.fromiter(mulberry32(seed, flow.size), dtype=float, count=flow.size) - 1) * 1.732
    low = np.exp(-2 * np.pi * spec['lowpass_hz'] / fs)
    high = np.exp(-2 * np.pi * spec['highpass_hz'] / fs)
    bandpassed = lfilter([high, -high], [1, -high], white)
    for _ in range(2):
        bandpassed = lfilter([1 - low], [1, -low], bandpassed)
    injected = {tuple(spec['forward']): np.where(flow >= 0, level * bandpassed, 0),
                tuple(spec['reverse']): np.where(flow < 0, -level * bandpassed, 0)}
    return level, injected, viable, reynolds, flow


def injection_from_momentum(case, columns, a, b):
    network = case['network']
    tube, = network['tubes']
    area = tube['areas_cm2'][a]
    if area != tube['areas_cm2'][b]:
        raise ValueError('圧力源の独立計算には同一断面の枝が必要です')
    dx = tube['length_cm'] / len(tube['areas_cm2'])
    rho, mu = 1.14e-3, 1.86e-4
    inertance = rho * dx / area
    resistance = np.sqrt(rho * mu * np.pi * 700) * 2 * np.sqrt(np.pi * area) * dx / area**2
    u = columns[f'branch_flow_{a}_{b}_cm3_s']
    dp = columns[f'pressure_{a}_dyn_cm2'] - columns[f'pressure_{b}_dyn_cm2']
    return inertance * network['sample_rate_hz'] * np.diff(u, prepend=0) + resistance * u - np.r_[0, dp[:-1]]


def measure(case, artifacts, reference_path):
    cfg, net, observe = (case[key] for key in ('measurement', 'network', 'observe'))
    model = net['turbulence']
    seed, upstream_seed = model['seed'], cfg['upstream_seed']
    count = cfg['sample_count']
    num_common = 4 + sum(len(observe[key]) for key in ('pressure_nodes', 'branches', 'area_nodes', 'noise_sources'))
    num_common += len(net['radiators'])
    header, candidate = shared.read_trace(artifacts / 'trace.csv', count, num_common + len(observe['noise_branches']))
    upper_header, upper_trace = shared.read_trace(reference_path, count, num_common)
    if header[:num_common] != upper_header:
        raise ValueError('上流と候補の共通観測列が一致しません')
    columns, upstream = (dict(zip(names, data.T, strict=True))
                         for names, data in ((header, candidate), (upper_header, upper_trace)))
    level, expected, viable, reynolds, flow = reconstruct_noise(case, columns, seed)
    upper_level, upper_expected, _, _, _ = reconstruct_noise(case, upstream, upstream_seed)
    recorded_level = columns['noise_level_0_dyn_cm2']
    tolerance = cfg['independent_noise_peak_relative_error_lt']
    independent = {
        'candidate_level': shared.compare_series(recorded_level, level, tolerance),
        'upstream_level': shared.compare_series(upstream['noise_level_0_dyn_cm2'], upper_level, tolerance),
    }
    momentum = {}
    peak_scale = max(float(np.max(np.abs(wave))) for wave in expected.values())
    upper_scale = max(float(np.max(np.abs(wave))) for wave in upper_expected.values())
    if peak_scale == 0 or upper_scale == 0:
        raise ValueError('圧力源の注入を観測できません')
    for [a, b] in observe['noise_branches']:
        key = f'noise_pressure_{a}_{b}_dyn_cm2'
        independent[key] = shared.compare_series(columns[key], expected[a, b], tolerance)
        tests = {}
        for label, states, pressure, scale in (
            ('candidate', columns, columns[key], peak_scale),
            ('upstream', upstream, upper_expected[a, b], upper_scale),
        ):
            balance = np.abs(injection_from_momentum(case, states, a, b) - pressure) / scale
            failures = np.flatnonzero(balance >= cfg['pressure_balance_peak_relative_error_lt'])
            tests[label] = {'max_error_over_injection_peak': float(np.max(balance)),
                            'first_sample_over_tolerance': int(failures[0]) if failures.size else None,
                            'status': failures.size == 0}
        momentum[key] = tests
    reference_comparisons = {key: shared.compare_series(columns[key], upstream[key],
                                                       cfg['upstream_series_peak_relative_error_lt'])
                             for key in upper_header[1:]}
    logs = (artifacts / 'upstream-rng-test.log').read_text()
    match = re.search(r'^\[[^\n]+\] (\[[^\n]+\])$', logs, re.MULTILINE)
    if match is None:
        raise ValueError('上流の乱数テストの出力を読み取れません')
    native = json.loads(match[1])
    native_matches = native == list(mulberry32(upstream_seed, len(native)))

    stable = slice(*cfg['steady_window_samples'])
    closed = slice(*cfg['closed_window_samples'])
    steady_active = int(np.count_nonzero(recorded_level[stable]))
    subcritical = viable & (reynolds < cfg['positive_reynolds_threshold'])
    checks = {
        'upstream_native_rng': native_matches,
        'noise_law_and_filter': all(result['status'] for result in independent.values()),
        'branch_momentum_balance': all(result['status'] for group in momentum.values() for result in group.values()),
        'subcritical_while_open': (int(np.count_nonzero(subcritical)) >= cfg['minimum_open_subcritical_samples']
                                   and not np.any(recorded_level[subcritical])),
        'active_in_expected_direction': (steady_active >= cfg['minimum_active_samples_in_window']
                                         and bool(np.all(flow[stable] * cfg['expected_flow_sign'] > 0))),
        'closed_source_is_silent': not (
            np.any(viable[closed]) or np.any(recorded_level[closed])
            or any(np.any(columns[f'noise_pressure_{a}_{b}_dyn_cm2'][closed]) for a, b in observe['noise_branches'])),
    }
    output = {
        'checks': checks,
        'candidate_seed': seed,
        'upstream_seed': upstream_seed,
        'upstream_first_rng_values': native,
        'first_active_sample': int(np.flatnonzero(recorded_level)[0]),
        'steady_mean_reynolds': float(np.mean(reynolds[stable])),
        'steady_peak_level_dyn_cm2': float(np.max(recorded_level[stable])),
        'steady_active_samples': steady_active,
        'open_subcritical_samples': int(np.count_nonzero(subcritical)),
        'candidate_peak_injected_pressure_dyn_cm2': peak_scale,
        'independent_noise': independent,
        'branch_momentum_balance': momentum,
        'upstream_time_series': reference_comparisons,
    }
    if seed == upstream_seed:
        checks['upstream_time_series'] = all(result['status'] for result in reference_comparisons.values())
    else:
        selected = tuple(model['sources'][0]['forward' if cfg['expected_flow_sign'] > 0 else 'reverse'])
        a, b = selected
        candidate_wave = columns[f'noise_pressure_{a}_{b}_dyn_cm2'][stable]
        upstream_wave = upper_expected[selected][stable]
        relative_rms = float(np.linalg.norm(candidate_wave - upstream_wave) / np.linalg.norm(upstream_wave))
        checks['alternate_seed_changes_pressure'] = relative_rms > cfg['alternate_seed_injection_relative_rms_gt']
        output['steady_injection_relative_rms_vs_upstream_seed'] = relative_rms
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=['turbulence-forward', 'turbulence-reverse', 'turbulence-alternate-seed'])
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--lib', 'mulberry32_matches_typescript',
                 '--', '--nocapture'], cwd=UPSTREAM, stdout=artifacts / 'upstream-rng-test.log')
        trace = reference.capture_upstream(case, artifacts, execute, AFFRICATE_TEST)
        return measure(case, artifacts, trace)

    inputs = [case_path, reference.PROBE, Path(__file__).resolve(), Path(reference.__file__),
              Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__,
               'candidate_seed': case['network']['turbulence']['seed'], 'upstream_seed': case['measurement']['upstream_seed']}
    return shared.record_measurement(args.run_id, case_path, inputs, details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
