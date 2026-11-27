"""固定声道で声門の面積・圧力差・実流量を上流と独立計算に照合する。"""

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


NATIVE_TEST = ('lung_port', 'folds_held_apart_meet_for_less_of_the_cycle')
CASES = ('glottal-abduction', 'glottal-oral-closure')


def earlier(values):
    return np.r_[0.0, values[:-1]]


def pulse_shape(phase, quotient, skew, sharpness):
    t = phase / quotient
    closing = (t - skew) / (1 - skew)
    gradual = 0.5 + 0.5 * np.cos(np.pi * closing)
    abrupt = np.cos(np.pi * closing / 2)
    shaped = np.where(t < skew, 0.5 - 0.5 * np.cos(np.pi * t / skew),
                      gradual + sharpness * (abrupt - gradual))
    return np.where((phase >= 0) & (phase < quotient), shaped, 0)


def reconstruct_source(case, drive, effort=None, *, phase=None, amplitude_scale=1.0):
    fs = case['network']['sample_rate_hz']
    source = case['glottis']
    p = source['params']
    if effort is None:
        effort = p['effort']
    samples = np.arange(drive.size)
    times, targets = map(np.asarray, zip(*source['abduction_steps'], strict=True))
    abduction = targets[np.searchsorted(times, samples, side='right') - 1]

    def filtered(signal, pole):
        return lfilter([1 - pole], [1, -pole], signal)

    def gate(low, high, signal):
        t = np.clip((signal - low) / (high - low), 0, 1)
        return t**2 * (3 - 2 * t)

    pole = np.exp(-1 / (0.004 * fs))
    gap = filtered(abduction + p['chink_cm2'], pole)
    closure = filtered(np.full(drive.size, p['closure']), pole)
    amplitude = filtered(np.broadcast_to(p['amplitude_cm2'] * (0.45 + 0.75 * effort), drive.shape), pole)
    pressure = filtered(drive, np.exp(-2 * np.pi * 30 / fs))
    parting = earlier(gap) - p['chink_cm2']
    threshold = p['threshold_dyn_cm2']
    voicing = filtered(gate(0.8 * threshold, 1.6 * threshold, pressure)
                       * (1 - gate(0.08, 0.22, parting)) * (1 - earlier(closure)),
                       np.exp(-2 * np.pi * 25 / fs))
    fry = p.get('fry', 0.0)
    if phase is None:
        frequency = p['f0_hz'] - fry * max(0, p['f0_hz'] - 48)
        phase = ((samples + 1) * frequency / fs) % 1.0
    quotient = np.clip(p['open_quotient'] - 0.18 * (effort - 0.5), 0.25, 0.98)
    quotient = np.minimum(0.98, quotient + p['open_with_abduction'] * np.maximum(0, parting))
    if fry:
        quotient = quotient + fry * (0.28 - quotient)
    skew = np.clip(p['skew'], 0.3, 0.9)
    sharpness = p['closure_sharpness']
    pulse = pulse_shape(phase, quotient, skew, sharpness)
    if fry > 0.3:
        pulse += 0.55 * gate(0.3, 0.8, fry) * pulse_shape(
            phase - 0.38, 0.8 * quotient, skew, sharpness)
    area = np.maximum(0, amplitude * amplitude_scale * voicing * pulse + gap * (1 - 0.92 * closure))
    return area, voicing, phase


def pressure_from_slit_flow(case, areas, flows):
    network = case['network']
    fs = network['sample_rate_hz']
    a, b = case['glottis']['port']
    port = next(port for port in network['ports'] if port['nodes'] == [a, b])
    cells = [(tube['length_cm'] / len(tube['areas_cm2']), area)
             for tube in network['tubes'] for area in tube['areas_cm2']]
    rho, mu = 1.14e-3, 1.86e-4
    open_port = areas >= 0.0002
    area = areas[open_port]
    inertia = np.zeros_like(areas)
    inertia[open_port] = rho * (port['length_cm'] / area + (
        sum(cells[i][0] / cells[i][1] for i in (a, b)) / 2
        if port.get('include_half_sections', True) else 0.0))
    resistance = (12 * mu * port['length_cm'] * port['slit_width_cm']**2 / area**3
                  + port.get('extra_resistance', 0.0))
    flow = flows[open_port]
    exit_area = np.where(flow >= 0, cells[b][1], cells[a][1])
    kinetic = 0.5 * rho * (port['entrance_loss'] / area**2 + port['expansion_loss']
                          * np.maximum(0, 1 / area - 1 / exit_area)**2)
    carried = np.minimum(inertia, earlier(inertia)) * earlier(flows)
    reconstructed = fs * (inertia[open_port] * flow - carried[open_port]) + resistance * flow + kinetic * flow * np.abs(flow)
    return reconstructed, open_port


def rms_ac(values):
    return float(np.sqrt(np.mean((values - np.mean(values))**2)))


def measure(case, artifacts, upstream_path):
    cfg, network, obs = (case[key] for key in ('measurement', 'network', 'observe'))
    columns = 8 + len(obs['pressure_nodes']) + len(obs['branches']) + len(network['radiators']) + len(obs['area_nodes'])
    header, trace = shared.read_trace(artifacts / 'trace.csv', cfg['sample_count'], columns)
    upper_header, upstream = shared.read_trace(upstream_path, cfg['sample_count'], columns)
    if header != upper_header:
        raise ValueError('上流と候補の観測列が一致しません')
    data = dict(zip(header, trace.T, strict=True))
    comparisons = {name: shared.compare_series(trace[:, i], upstream[:, i], cfg['upstream_series_peak_relative_error_lt'])
                   for i, name in enumerate(header) if name != 'sample'}
    a, b = case['glottis']['port']
    pressure = data['glottal_pressure_drop_dyn_cm2']
    area = data['glottal_area_cm2']
    flow = data[f'branch_flow_{a}_{b}_cm3_s']
    voicing = data['glottal_voicing']
    tol = cfg['independent_area_and_gate_peak_relative_error_lt']
    area_ref, gate_ref, phase_ref = reconstruct_source(case, pressure)
    balance, open_port = pressure_from_slit_flow(case, area, flow)
    independent = {
        'pre_step_pressure': shared.compare_series(pressure,
                                                  earlier(data[f'pressure_{a}_dyn_cm2'] - data[f'pressure_{b}_dyn_cm2']), tol),
        'area': shared.compare_series(area, area_ref, tol),
        'voicing': shared.compare_series(voicing, gate_ref, tol),
        'phase': shared.compare_series(np.exp(2j * np.pi * data['glottal_phase']),
                                       np.exp(2j * np.pi * phase_ref), tol),
        'slit_momentum_balance': shared.compare_series(balance, pressure[open_port],
                                                       cfg['momentum_pressure_peak_relative_error_lt']),
    }
    quiet = slice(*cfg['quiet_window_samples'])
    voiced = slice(*cfg['voiced_window_samples'])
    late = slice(*cfg['late_window_samples'])
    quiet_gate = float(np.max(voicing[quiet]))
    voiced_gate, late_gate = (float(np.mean(voicing[w])) for w in (voiced, late))
    voiced_area, late_area = (float(np.mean(area[w])) for w in (voiced, late))
    voiced_flow, late_flow = (float(np.mean(flow[w])) for w in (voiced, late))
    voiced_pressure, late_pressure = (float(np.mean(np.abs(pressure[w]))) for w in (voiced, late))
    area_ratio, flow_ratio = (rms_ac(x[late]) / rms_ac(x[voiced]) if rms_ac(x[voiced]) else None for x in (area, flow))
    active = np.flatnonzero(voicing)
    checks = {
        'upstream_time_series': all(item['status'] for item in comparisons.values()),
        'independent_source_and_slit_flow': all(item['status'] for item in independent.values()),
        'initial_gate_is_quiet': quiet_gate <= cfg['initial_voicing_max'],
        'pressure_ramp_starts_voicing': voiced_gate > cfg['voiced_mean_gate_gt'],
        'late_voicing_gate_falls': late_gate < cfg['late_mean_gate_lt'],
        'area_pulse_is_suppressed': area_ratio is not None and area_ratio < cfg['late_area_ac_over_voiced_lt'],
        'flow_pulse_is_suppressed': flow_ratio is not None and flow_ratio < cfg['late_flow_ac_over_voiced_lt'],
        'closed_slit_blocks_flow': bool(np.any(~open_port)) and not np.any(flow[~open_port]),
    }
    if cfg['condition'] == 'abduction':
        checks['open_folds_keep_a_gap_and_mean_flow'] = (
            late_area > cfg['abducted_mean_area_over_voiced_gt'] * voiced_area
            and late_flow > cfg['abducted_mean_flow_over_voiced_gt'] * voiced_flow)
    else:
        mouth, = network['radiators']
        checks['oral_closure_reduces_pressure_drop'] = (
            bool(np.all(data[f'area_{mouth}_cm2'][late] < 0.0002))
            and late_pressure < cfg['occluded_mean_abs_pressure_drop_over_voiced_lt'] * voiced_pressure)
    return {
        'checks': checks,
        'first_voicing_sample': int(active[0]) if active.size else None,
        'mean_voicing': {'voiced': voiced_gate, 'late': late_gate},
        'mean_area_cm2': {'voiced': voiced_area, 'late': late_area},
        'mean_flow_cm3_s': {'voiced': voiced_flow, 'late': late_flow},
        'mean_abs_pressure_drop_dyn_cm2': {'voiced': voiced_pressure, 'late': late_pressure},
        'late_area_ac_over_voiced': area_ratio, 'late_flow_ac_over_voiced': flow_ratio,
        'closed_slit_samples': int(np.count_nonzero(~open_port)),
        'independent': independent, 'upstream_time_series': comparisons,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        trace = reference.capture_upstream(case, artifacts, execute, NATIVE_TEST)
        return measure(case, artifacts, trace)

    inputs = [case_path, reference.PROBE, Path(__file__).resolve(), Path(reference.__file__),
              Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, inputs, details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
