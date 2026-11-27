"""軟口蓋と側枝を備えた気道を、上流と独立した周波数領域計算に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


NATIVE_TEST = ('sound_marks_acoustic', 'a_nasalized_vowel_is_nasal_and_an_oral_one_is_not')
CASE_NAMES = ('nasal-network-closed', 'nasal-network-open-detached', 'nasal-network-open')


def linear_elements(network):
    """固定形状の音響素子をCGSで組み立てる。枝の非線形損失は小信号で消える。"""
    rho, mu, c = 1.14e-3, 1.86e-4, 35000.0
    viscosity = np.sqrt(rho * mu * np.pi * 700)
    areas, lengths, halves_r, walls = [], [], [], []
    ordinary_edges = []
    for tube in network['tubes']:
        start = len(areas)
        area = np.asarray(tube['areas_cm2'])
        dx = tube['length_cm'] / area.size
        surface = tube.get('perimeter_factor', 1.0) * 2 * np.sqrt(np.pi * area) * dx
        areas.extend(area)
        lengths.extend([dx] * area.size)
        halves_r.extend(viscosity * 0.5 * surface * tube.get('viscous_factor', 1.0) / area**2)
        ordinary_edges.extend((a, a + 1) for a in range(start, len(areas) - 1))
        if wall := tube.get('wall'):
            walls.extend((start + i, s, wall) for i, s in enumerate(surface))
    ordinary_edges.extend(map(tuple, network['connections']))
    areas, lengths = np.asarray(areas), np.asarray(lengths)
    halves_l = rho * lengths / (2 * areas)
    edges = {(a, b): (halves_l[a] + halves_l[b], halves_r[a] + halves_r[b])
             for a, b in ordinary_edges}
    for port in network['ports']:
        a, b = port['nodes']
        area, length = port['area_cm2'], port['length_cm']
        if area < 0.0002:
            edges[a, b] = (np.inf, 0.0)
            continue
        if port.get('slit_width_cm', 0.0):
            raise ValueError('この比較では円形ポートを使用します')
        inertance = rho * length / area
        if port.get('include_half_sections', True):
            inertance += halves_l[a] + halves_l[b]
        resistance = viscosity * 2 * np.sqrt(np.pi * area) * length / area**2
        edges[a, b] = (inertance, resistance + port.get('extra_resistance', 0.0))

    compliance = areas * lengths / (rho * c**2)
    count = np.zeros(areas.size, dtype=int)
    inverse = np.zeros(areas.size)
    for (a, b), (inertance, _) in edges.items():
        count[[a, b]] += 1
        inverse[[a, b]] += 1 / inertance
    dt = 1 / network['sample_rate_hz']
    compliance = np.where(count >= 3, np.maximum(compliance, dt**2 * inverse / 2.4), compliance)
    return areas, lengths, edges, walls, compliance


def frequency_response(case, elements):
    areas, _, edges, walls, compliance = elements
    cfg, network = (case[name] for name in ('measurement', 'network'))
    fs = network['sample_rate_hz']
    outlets = np.asarray(network['radiators'])
    rho, c = 1.14e-3, 35000.0
    radiation_l = 8 * rho / (3 * np.pi * np.sqrt(np.pi * areas[outlets]))
    radiation_r = 128 * rho * c / (9 * np.pi**2 * areas[outlets])
    forcing = np.zeros(areas.size)
    forcing[case['impulse']['node']] = 1
    output = []
    for frequency in cfg['frequencies_hz']:
        delay = np.exp(-2j * np.pi * frequency / fs)
        difference = 1 - delay
        midpoint = (1 + delay) / 2
        radiation = midpoint * (1 / radiation_r + midpoint / (radiation_l * fs * difference))
        system = np.diag(compliance * difference * fs)
        for (a, b), (inertance, resistance) in edges.items():
            if np.isfinite(inertance):
                admittance = delay / (resistance + inertance * fs * difference)
                system[a, a] += admittance
                system[b, b] += admittance
                system[a, b] -= admittance
                system[b, a] -= admittance
        wall_radiation = np.zeros(areas.size, dtype=complex)
        for node, surface, wall in walls:
            impedance = (wall['mass_g_cm2'] * fs * difference
                         + wall['resistance_dyn_s_cm3'] * midpoint
                         + wall['stiffness_dyn_cm3'] * delay / (fs * difference))
            admittance = surface * delay / impedance
            system[node, node] += admittance
            wall_radiation[node] = admittance * wall['radiation_fraction']
        system[outlets, outlets] += radiation
        pressure = np.linalg.solve(system, forcing)
        radiated = pressure[outlets] * radiation
        skin = wall_radiation @ pressure
        output.append([*radiated, skin, radiated.sum() + skin])
    return np.asarray(output)


def shape_controls(case, run_ids, sources):
    cfg = case['measurement']
    expected = cfg.get('control_cases', [])
    if len(run_ids) != len(expected):
        raise ValueError('開放ケースには閉鎖と側枝切離の通過済みの実行が必要です')
    controls, paths = {}, []
    for run_id, expected_case in zip(run_ids, expected, strict=True):
        run = WORKSPACE / 'runs' / run_id
        manifest_path, summary_path = run / 'manifest.json', run / 'summary.json'
        manifest = json.loads(manifest_path.read_text())
        prior_inputs = {item['path']: item['sha256'] for item in manifest['inputs']}
        expected_inputs = [WORKSPACE / 'cases' / f'{expected_case}.json', *sources]
        if (manifest['status'] != 'pass' or manifest['case_id'] != expected_case
                or manifest['upstream_revision'] != case['upstream_revision']
                or any(prior_inputs.get(str(path.relative_to(WORKSPACE))) != sha256(path)
                       for path in expected_inputs)
                or not any(item['path'] == 'summary.json' and item['sha256'] == sha256(summary_path)
                           for item in manifest['outputs'])):
            raise ValueError('同じ候補ソースと上流版で通過した比較実行が必要です')
        paths.extend([manifest_path, summary_path])
        controls[expected_case] = json.loads(summary_path.read_text())
    return controls, paths


def measure(case, artifacts, upstream_path, controls):
    cfg, net, obs = (case[key] for key in ('measurement', 'network', 'observe'))
    count = cfg['sample_count']
    columns = 5 + len(obs['pressure_nodes']) + len(obs['branches']) + len(net['radiators']) + 3 * len(obs['wall_nodes'])
    header, cand = shared.read_trace(artifacts / 'trace.csv', count, columns)
    upper_header, upstream = shared.read_trace(upstream_path, count, columns)
    if header != upper_header:
        raise ValueError('上流と候補の観測列が一致しません')
    states = dict(zip(header, cand.T, strict=True))
    time_series = {
        name: shared.compare_series(cand[:, i], upstream[:, i], cfg['upstream_series_peak_relative_error_lt'])
        for i, name in enumerate(header) if name != 'sample'
    }
    cfg_f = np.asarray(cfg['frequencies_hz'])
    fs = net['sample_rate_hz']
    bins = np.rint(cfg_f * count / fs).astype(int)
    if not np.array_equal(bins * fs / count, cfg_f):
        raise ValueError('周波数をFFTのビンに合わせてください')
    mouth, nose = cfg['mouth_node'], cfg['nose_node']
    names = [f'radiation_{mouth}_cm3_s', f'radiation_{nose}_cm3_s',
             'wall_radiation_flow_cm3_s', 'radiation_flow_cm3_s']
    spectrum = np.column_stack([np.fft.rfft(states[name]) for name in names])
    drive = np.fft.rfft(states['inlet_flow_cm3_s'])
    measured = spectrum[bins] / drive[bins, None]
    elements = linear_elements(net)
    areas, lengths, edges, _, compliance = elements
    predicted = frequency_response(case, elements)
    spectral_checks = {
        name: shared.compare_series(measured[:, i], predicted[:, i], cfg['discrete_response_peak_relative_error_lt'])
        for i, name in enumerate(names)
    }
    node_checks = {}
    tol = cfg['volume_balance_relative_error_lt']
    for node in cfg['volume_balance_nodes']:
        net_flow = states['inlet_flow_cm3_s'].copy() if node == case['impulse']['node'] else np.zeros(count)
        for a, b in edges:
            if node in [a, b]:
                sign = 1.0 if b == node else -1.0
                net_flow += sign * states[f'branch_flow_{a}_{b}_cm3_s']
        net_flow -= states[f'wall_flow_{node}_cm3_s']
        if node in net['radiators']:
            net_flow -= states[f'radiation_{node}_cm3_s']
        change = np.diff(states[f'pressure_{node}_dyn_cm2'], prepend=0) * fs * compliance[node]
        node_checks[str(node)] = shared.compare_series(change, net_flow, tol)
    component_balance = shared.compare_series(states[names[3]], sum(states[name] for name in names[:3]), tol)
    mouth_peak, nose_peak = (float(np.max(np.abs(states[name]))) for name in names[:2])
    inlet_peak = float(np.max(np.abs(states['inlet_flow_cm3_s'])))
    if not mouth_peak or not inlet_peak:
        raise ValueError('入口流量または口端放射がゼロです')
    nose_ratio = nose_peak / mouth_peak
    port = next(p for p in net['ports'] if p['nodes'] == cfg['velum_branch'])
    a, b = port['nodes']
    velum = states[f'branch_flow_{a}_{b}_cm3_s']
    checks = {
        'upstream_time_series': all(x['status'] for x in time_series.values()),
        'independent_discrete_response': all(x['status'] for x in spectral_checks.values()),
        'volume_balance': all(x['status'] for x in node_checks.values()),
        'radiation_component_balance': component_balance['status'],
        'nose_radiation_matches_velum': (nose_ratio > cfg['nose_over_mouth_peak_gt_when_open'] and bool(np.any(velum)))
        if port['area_cm2'] > 0 else (nose_peak == 0 and not np.any(velum)),
    }
    side_flow = {}
    for a, b in ([5, 58], [46, 61]):
        if (a, b) in edges:
            side_flow[f'{a}_{b}'] = float(np.max(np.abs(states[f'branch_flow_{a}_{b}_cm3_s']))) / inlet_peak
    if side_flow:
        checks['side_branch_flow'] = side_flow['5_58'] > cfg['side_branch_flow_over_inlet_peak_gt'] and (
            side_flow['46_61'] > cfg['side_branch_flow_over_inlet_peak_gt'] if port['area_cm2'] > 0
            else side_flow['46_61'] == 0.0)
    else:
        checks['detached_pockets_are_quiet'] = all(not np.any(states[f'pressure_{node}_dyn_cm2'])
                                                  for node in (58, 61))
    result = {
        'checks': checks, 'upstream_time_series': time_series, 'independent_discrete_response': spectral_checks,
        'volume_balance': node_checks, 'radiation_component_balance': component_balance,
        'mouth_peak_flow_cm3_s': mouth_peak, 'nose_peak_flow_cm3_s': nose_peak,
        'nose_over_mouth_peak': nose_ratio, 'side_flow_over_inlet_peak': side_flow,
        'frequencies_hz': cfg['frequencies_hz'],
        'measured_response': {name: np.column_stack((measured[:, i].real, measured[:, i].imag)).tolist()
                              for i, name in enumerate(names)},
    }
    if controls:
        detached = controls['nasal-network-open-detached']
        closed = controls['nasal-network-closed']
        if detached['frequencies_hz'] != cfg['frequencies_hz']:
            raise ValueError('側枝切離の比較と周波数が一致しません')
        changes = {}
        for i, name in enumerate(names[:2]):
            prior = np.asarray(detached['measured_response'][name])
            baseline = prior[:, 0] + 1j * prior[:, 1]
            delta = np.abs(measured[:, i] - baseline)
            index = int(np.argmax(delta))
            changes[name] = {'max_difference_over_detached_peak': float(delta[index] / np.max(np.abs(baseline))),
                             'frequency_hz': int(cfg_f[index])}
        result['side_branch_effects'] = changes
        checks['side_branches_change_radiation'] = max(
            x['max_difference_over_detached_peak'] for x in changes.values()
        ) > cfg['side_branch_spectral_difference_peak_relative_gt']
        checks['closed_to_open_adds_nose_radiation'] = closed['nose_peak_flow_cm3_s'] == 0 < nose_peak

        throat = next(p for p in net['ports'] if p['nodes'] == [46, 61])
        volume = areas[61] * lengths[61]
        expected_hz = float((35000.0 / (2 * np.pi)) * np.sqrt(throat['area_cm2'] / (throat['length_cm'] * volume)))
        f = np.fft.rfftfreq(count, 1 / fs)
        lower, upper = cfg['sinus_peak_search_hz']
        band = (lower <= f) & (f <= upper)
        neck = np.fft.rfft(states['branch_flow_46_61_cm3_s'])[band]
        pressure = np.fft.rfft(states['pressure_46_dyn_cm2'])[band]
        if np.any(pressure == 0):
            raise ValueError('上顎洞の計測帯域にゼロの駆動周波数があります')
        peak_hz = float(f[band][np.argmax(np.abs(neck / pressure))])
        result['sinus_admittance_peak_hz'] = peak_hz
        result['helmholtz_prediction_hz'] = expected_hz
        checks['sinus_helmholtz_resonance'] = abs(peak_hz - expected_hz) / expected_hz < cfg['sinus_peak_frequency_relative_error_lt']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASE_NAMES)
    parser.add_argument('--controls', nargs=2, metavar=('CLOSED_RUN', 'DETACHED_RUN'))
    args = parser.parse_args()
    for run_id in (args.run_id, *(args.controls or [])):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', run_id):
            parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [reference.PROBE, Path(__file__).resolve(), Path(reference.__file__), Path(shared.__file__),
               WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    controls, inputs = shape_controls(case, args.controls or [], sources)

    def measure_run(artifacts, execute):
        trace = reference.capture_upstream(case, artifacts, execute, NATIVE_TEST)
        return measure(case, artifacts, trace, controls)

    return shared.record_measurement(args.run_id, case_path, [case_path, *sources, *inputs],
                                     {'upstream_revision': revision, 'case_id': case['id'],
                                      'control_run_ids': args.controls or []}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
