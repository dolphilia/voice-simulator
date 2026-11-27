"""下気道の直流・交流抵抗と、呼気制御の時系列を照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

import measure_glottal_coupling as glottal
import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE_IDS = ('lung-uncompensated', 'lung-compensated', 'lung-voiced')
NATIVE_TEST = ('lung_port', 'a_fricative_keeps_the_lungs_pressure_at_its_folds')
CM_H2O = 980.665


def breath_controls(case, count):
    """制御点から区分的な指数応答とブロック内補間を計算する。"""
    cfg = case['breath']
    fs = case['network']['sample_rate_hz']
    block = cfg['control_block_samples']
    starts = np.arange(0, count, block)
    times, performer, score, activity = np.asarray(cfg['steps']).T
    selection = np.searchsorted(times, starts, side='right') - 1
    score = score[selection] * activity[selection]
    goals = np.where(score < 0, score, np.maximum(score, performer[selection]))
    active = activity[selection] > 0
    gate, last_activity = 0.0, -fs
    targets = []
    for start, goal, score_active in zip(starts, goals, active, strict=True):
        if score_active:
            last_activity = start
        tau = 0.025 if goal > gate else (0.02 if (start - last_activity) / fs < 0.15 else 0.07)
        gate = goal + (gate - goal) * np.exp(-block / (fs * tau))
        targets.append(gate)
    gate = np.repeat(targets, block)[:count]
    pressure = np.interp(np.arange(1, count + 1), np.r_[0, starts + block],
                         np.r_[0, np.asarray(targets) * cfg['pressure_cm_h2o'] * CM_H2O])
    effort = np.clip((np.abs(cfg['pressure_cm_h2o'] * gate) - 2.2) / 10, 0, 1)
    return gate, pressure, effort


def momentum_loss(case, table, flow):
    """肺ポートの差圧から、円管固有の抵抗と半区間を含む慣性の差圧を除く。"""
    network = case['network']
    port = next(port for port in network['ports'] if port['nodes'] == case['breath']['port'])
    node = port['nodes'][1]
    sections = [(tube['length_cm'] / len(tube['areas_cm2']), a)
                for tube in network['tubes'] for a in tube['areas_cm2']]
    length, area = port['length_cm'], port['area_cm2']
    rho, mu = 1.14e-3, 1.86e-4
    inertance = rho * length / area
    if port.get('include_half_sections', True):
        dx, a = sections[node]
        inertance += rho * (dx / a + 1 / 100) / 2
    duct = 2 * np.sqrt(rho * mu * np.pi * 700) * np.sqrt(np.pi * area) * length / area**2
    rate = network['sample_rate_hz']
    downstream = glottal.earlier(table[f'pressure_{node}_dyn_cm2'])
    return (table['breath_base_pressure_dyn_cm2'] - downstream
            - inertance * rate * np.diff(flow, prepend=0.0) - duct * flow), port['extra_resistance']


def reference_control(case, run_id, sources):
    expected = case['measurement'].get('control_case')
    if bool(expected) != bool(run_id):
        raise ValueError('補償ありの固定開口には補償なしの比較実行を指定してください')
    if not expected:
        return None, []
    folder = WORKSPACE / 'runs' / run_id
    manifest_path = folder / 'manifest.json'
    summary_path = folder / 'summary.json'
    manifest = json.loads(manifest_path.read_text())
    prior = {item['path']: item['sha256'] for item in manifest['inputs']}
    inputs = [WORKSPACE / 'cases' / f'{expected}.json', *sources]
    if (manifest['status'] != 'pass' or manifest['case_id'] != expected
            or manifest['upstream_revision'] != case['upstream_revision']
            or any(prior.get(str(path.relative_to(WORKSPACE))) != sha256(path) for path in inputs)
            or not any(item['path'] == 'summary.json' and item['sha256'] == sha256(summary_path)
                       for item in manifest['outputs'])):
        raise ValueError('同じ候補ソースと上流版で通過した補償なしの実行が必要です')
    return json.loads(summary_path.read_text()), [manifest_path, summary_path]


def measure(case, artifacts, upstream_path, control):
    m, net, obs, breath = (case[key] for key in ('measurement', 'network', 'observe', 'breath'))
    count, fs = m['sample_count'], net['sample_rate_hz']
    width = 9 + len(obs['pressure_nodes']) + len(obs['branches']) + len(net['radiators']) + (4 if 'glottis' in case else 0)
    header, trace = shared.read_trace(artifacts / 'trace.csv', count, width)
    upper_header, upper = shared.read_trace(upstream_path, count, width)
    if header != upper_header:
        raise ValueError('上流と候補の観測列が一致しません')
    table = dict(zip(header, trace.T, strict=True))
    comparisons = {
        name: shared.compare_series(trace[:, i], upper[:, i], m['reference_series_peak_relative_error_lt'])
        for i, name in enumerate(header) if name != 'sample'
    }
    a, b = breath['port']
    flow = table[f'branch_flow_{a}_{b}_cm3_s']
    loss, r_ac = momentum_loss(case, table, flow)
    scale = breath['body_scale']
    dc = 0.8 * CM_H2O / (1000 * scale**3) if breath['compensate'] else r_ac
    excess = r_ac - dc
    pole = np.exp(-excess / (fs * (0.0052 / scale)))
    filtered = lfilter([1 - pole], [1, -pole], glottal.earlier(flow))
    gate, base, effort = breath_controls(case, count)
    expected = {
        'breath_gate': gate, 'breath_base_pressure_dyn_cm2': base, 'breath_filtered_flow_cm3_s': filtered,
        'breath_boundary_pressure_dyn_cm2': base + excess * filtered, 'breath_effort': effort,
        f'pressure_{a}_dyn_cm2': base + excess * filtered,
    }
    if 'glottis' in case:
        glottal_area, glottal_gate, _ = glottal.reconstruct_source(case, table['glottal_pressure_drop_dyn_cm2'], effort)
        expected.update(glottal_area_cm2=glottal_area, glottal_voicing=glottal_gate)
    tol = m['independent_series_peak_relative_error_lt']
    independent = {name: shared.compare_series(table[name], values, tol) for name, values in expected.items()}
    independent['momentum_resistance'] = shared.compare_series(loss, r_ac * flow - excess * filtered, tol)

    steady = slice(*m['steady_window_samples'])
    ingressive = slice(*m['ingressive_window_samples'])
    amount = float(np.mean(flow[steady]))
    if amount <= 0:
        raise ValueError('定常窓で正の肺ポート流量を確認できません')
    dc_measured = float(np.mean(loss[steady]) / amount)
    hz = np.asarray(m['frequencies_hz'])
    bins = np.rint(hz * count / fs).astype(int)
    if not np.array_equal(bins * fs / count, hz):
        raise ValueError('周波数をFFTのビンに合わせてください')
    delay = np.exp(-2j * np.pi * hz / fs)
    u = np.fft.rfft(flow)[bins]
    if np.any(u == 0):
        raise ValueError('交流抵抗の測定周波数で流量がゼロです')
    # DFTで系列を一周させたときの、末尾の流量とフィルタ状態に相当する項を除く。
    denominator = 1 - pole * delay
    end_correction = excess * (pole * filtered[-1] + (1 - pole) * flow[-1]) / denominator
    ac_measured = (np.fft.rfft(loss)[bins] - end_correction) / u
    ac_reference = r_ac - excess * (1 - pole) * delay / denominator
    response_error = np.abs(ac_measured - ac_reference) / np.abs(ac_reference)

    cp = breath['control_block_samples']
    observed_gate = table['breath_gate']
    constants = {}
    for label, start, goal, tau in (
        ('attack', 0, breath['steps'][0][1], 0.025),
        ('performer_release', breath['steps'][1][0], 0.0, 0.07),
        ('scored_release', breath['steps'][-1][0], 0.0, 0.02),
    ):
        prev = observed_gate[start - cp] if start else 0
        decay = (observed_gate[start] - goal) / (prev - goal)
        estimate = float(-cp / (fs * np.log(decay))) if 0 < decay < 1 else None
        constants[label] = {'measured_seconds': estimate, 'expected_seconds': tau,
                            'status': estimate is not None and abs(estimate - tau) / tau < m['control_time_constant_relative_error_lt']}
    sub_node = net['ports'][1]['nodes'][0]
    subglottal = float(np.mean(table[f'pressure_{sub_node}_dyn_cm2'][steady]) / CM_H2O)
    negative_gate = float(np.mean(observed_gate[ingressive]))
    negative_flow = float(np.mean(flow[ingressive]))
    checks = {
        'upstream_time_series': all(item['status'] for item in comparisons.values()),
        'independent_control_and_momentum': all(item['status'] for item in independent.values()),
        'attack_and_release_time_constants': all(item['status'] for item in constants.values()),
        'dc_resistance': abs(dc_measured - dc) / dc < m['dc_resistance_relative_error_lt'],
        'ac_resistance': bool(np.all(response_error < m['frequency_response_relative_error_lt'])),
        'high_frequency_resistance': bool(ac_measured[-1].real / r_ac > m['high_frequency_real_resistance_over_ac_gt']),
        'score_can_drive_ingressive_flow': (negative_gate < m['ingressive_gate_mean_lt']
                                            and negative_flow < m['ingressive_flow_mean_lt_cm3_s']),
        'gate_returns_to_rest': bool(abs(observed_gate[-1]) < m['final_gate_abs_lt']),
    }
    result = {
        'checks': checks, 'time_constants': constants, 'independent_series': independent, 'upstream_time_series': comparisons,
        'dc_resistance_cgs': dc_measured, 'dc_resistance_reference_cgs': dc,
        'ac_impedance': [{'frequency_hz': int(f), 'measured_real_cgs': float(z.real), 'measured_imaginary_cgs': float(z.imag),
                          'relative_error': float(err)} for f, z, err in zip(hz, ac_measured, response_error, strict=True)],
        'mean_steady_subglottal_cm_h2o': subglottal, 'mean_steady_flow_cm3_s': amount,
        'mean_ingressive_gate': negative_gate, 'mean_ingressive_flow_cm3_s': negative_flow,
        'final_gate': float(observed_gate[-1]),
    }
    if control is not None:
        improvement = subglottal - control['mean_steady_subglottal_cm_h2o']
        checks['compensation_recovers_subglottal_pressure'] = (
            subglottal > m['compensated_subglottal_pressure_gt_cm_h2o']
            and improvement > m['compensation_subglottal_improvement_gt_cm_h2o'])
        result['subglottal_improvement_cm_h2o'] = improvement
    if 'glottis' in case:
        mean_voicing = float(np.mean(table['glottal_voicing'][steady]))
        checks['coupled_voice_starts'] = mean_voicing > m['voiced_mean_gate_gt']
        result['mean_steady_voicing'] = mean_voicing
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASE_IDS)
    parser.add_argument('--uncompensated-run')
    args = parser.parse_args()
    for identifier in filter(None, [args.run_id, args.uncompensated_run]):
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', identifier):
            parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [reference.PROBE, Path(__file__).resolve(), Path(reference.__file__), Path(shared.__file__),
               Path(glottal.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    control, inputs = reference_control(case, args.uncompensated_run, sources)

    def measure_run(artifacts, execute):
        trace = reference.capture_upstream(case, artifacts, execute, NATIVE_TEST)
        return measure(case, artifacts, trace, control)

    return shared.record_measurement(
        args.run_id, case_path, [case_path, *sources, *inputs],
        {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__,
         'uncompensated_run': args.uncompensated_run}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
