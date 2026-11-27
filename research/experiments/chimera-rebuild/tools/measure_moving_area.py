"""可動断面を上流の公開系列と、独立した体積収支に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE


def independent_volume_source(case):
    network = case['network']
    fs = network['sample_rate_hz']
    samples = case['measurement']['sample_count']
    tube, = network['tubes']
    baseline = np.asarray(tube['areas_cm2'])
    areas = np.tile(baseline, (samples + 1, 1))
    for ramp in case['area_ramps']:
        start = ramp['start_sample']
        end = start + ramp['sample_count']
        for target in ramp['targets']:
            node = target['node']
            final_area = target['area_cm2']
            areas[start:end + 1, node] = np.linspace(areas[start, node], final_area, end - start + 1)
            areas[end + 1:, node] = final_area
    dx = tube['length_cm'] / baseline.size
    volume = dx * np.maximum(areas, 0.02)
    raw = -fs * np.diff(volume, axis=0)
    # 開閉ケースでは最後のセルの隣接先は一つで、常に開口している。
    if 'outlet_node' in case['measurement']:
        node = case['measurement']['outlet_node']
        ratio = np.minimum(areas[1:, node] / 0.12, 1.0)
        shifted = raw[:, node] * (1 - ratio**2 * (3 - 2 * ratio))
        raw[:, node - 1] += shifted
        raw[:, node] -= shifted
    else:
        shifted = np.zeros(samples)

    # 二段の一次フィルタを状態更新で追わず、解析インパルス応答との畳み込みで求める。
    pole = np.exp(-2 * np.pi * 60 / fs)
    indices = np.arange(samples)
    kernel = (1 - pole)**2 * (indices + 1) * pole**indices
    fft_size = 1 << (2 * samples - 2).bit_length()
    convolution = np.fft.irfft(np.fft.rfft(raw, n=fft_size, axis=0)
                               * np.fft.rfft(kernel, n=fft_size)[:, None], n=fft_size, axis=0)
    return areas[1:], volume, convolution[:samples], shifted


def measure(case, artifacts, reference_path):
    m, observe = case['measurement'], case['observe']
    count = 4 + len(observe['pressure_nodes']) + len(observe['branches']) + len(observe['area_nodes']) + len(case['network']['radiators'])
    volume_columns = [f'volume_source_{node}_cm3_s' for node in observe['volume_source_nodes']]
    header, trace = shared.read_trace(artifacts / 'trace.csv', m['sample_count'], count + len(volume_columns))
    ref_header, upstream = shared.read_trace(reference_path, m['sample_count'], count)
    if header != ref_header + volume_columns:
        raise ValueError('候補と上流の計測列が一致しません')
    tol = m['upstream_series_peak_relative_error_lt']
    compared = {name: shared.compare_series(trace[:, index], upstream[:, index], tol)
                for index, name in enumerate(ref_header[1:], start=1)}

    areas, volume, source, shifted = independent_volume_source(case)
    columns = dict(zip(header, trace.T, strict=True))
    tol = m['independent_series_peak_relative_error_lt']
    independent = {key: shared.compare_series(columns[key], source[:, node], tol)
                   for key, node in zip(volume_columns, observe['volume_source_nodes'], strict=True)}
    independent.update({f'area_{node}_cm2': shared.compare_series(columns[f'area_{node}_cm2'], areas[:, node], tol)
                        for node in observe['area_nodes']})
    area_error = float(max(abs(columns[f'area_{node}_cm2'][-1] - areas[-1, node]) for node in observe['area_nodes']))
    checks = {'finite_samples': True, 'upstream_time_series': all(item['status'] for item in compared.values()),
              'independent_area_and_source': all(item['status'] for item in independent.values()),
              'terminal_area': area_error < m['terminal_area_absolute_error_lt_cm2'],
              'no_external_flow': bool(not np.any(columns['inlet_flow_cm3_s']))}
    summary = {'checks': checks, 'samples': trace.shape[0], 'terminal_area_error_cm2': area_error,
               'upstream_time_series': compared, 'independent_series': independent}
    if 'closed_interval' in m:
        a, b = m['closed_interval']
        start, end = m['reopening_interval']
        node = m['outlet_node']
        branch = columns[f'branch_flow_{node - 1}_{node}_cm3_s']
        radiation = columns[f'radiation_{node}_cm3_s']
        pressure = columns[f'pressure_{node}_dyn_cm2']
        checks.update({
            'closed_branch_zero': bool(np.count_nonzero(branch[a:b]) == 0),
            'reopened_branch_and_radiation': bool(np.any(branch[start:end]) and np.any(radiation[start:end])),
            'squeeze_reaches_neighbor': bool(np.max(shifted) > 0.0 and np.any(columns[f'volume_source_{node - 1}_cm3_s'] > 0.0)),
        })
        summary.update(closed_max_abs_flow_cm3_s=float(np.max(np.abs(branch[a:b]))),
                       reopened_max_abs_flow_cm3_s=float(np.max(np.abs(branch[start:end]))),
                       peak_abs_outlet_pressure_dyn_cm2=float(np.max(np.abs(pressure))),
                       peak_redistributed_injection_cm3_s=float(np.max(shifted)))
    else:
        bulk = 1.14e-3 * 35000.0**2
        fs = case['network']['sample_rate_hz']
        p = np.cumsum(bulk / fs * source / volume[1:], axis=0)
        pressure_names = [f'pressure_{node}_dyn_cm2' for node in observe['pressure_nodes']]
        pressure_series = {name: shared.compare_series(columns[name], p[:, node], tol)
                           for name, node in zip(pressure_names, observe['pressure_nodes'], strict=True)}
        final = float(np.mean([columns[name][-1] for name in pressure_names]))
        analytic = float(bulk * np.log(volume[0].sum() / volume[-1].sum()))
        relative = abs(final / analytic - 1)
        # 同じ離散体積列のままフィルタだけを外した探索的な計算。合否条件は変更しない。
        unfiltered = float(np.mean(np.sum(-bulk * np.diff(volume, axis=0) / volume[1:], axis=0)))
        checks.update(independent_pressure=all(item['status'] for item in pressure_series.values()),
                      no_radiation=bool(not np.any(columns['radiation_flow_derivative_cm3_s2'])),
                      volume_compression_reference=relative < m['reference_pressure_relative_error_lt'])
        summary.update(independent_pressure=pressure_series, terminal_pressure_dyn_cm2=final,
                       continuous_approximation_pressure_dyn_cm2=analytic, relative_pressure_error=relative,
                       unfiltered_discrete_pressure_dyn_cm2=unfiltered,
                       unfiltered_relative_pressure_error=abs(unfiltered / analytic - 1))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=['sealed-cavity-compression', 'moving-aperture-release'])
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行 ID には英数字、ハイフン、アンダースコアを使ってください')
    case_path = WORKSPACE / 'cases' / (args.case + '.json')
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, artifacts, reference.capture_upstream(case, artifacts, execute))

    inputs = [case_path, reference.PROBE, Path(__file__).resolve(), Path(reference.__file__), Path(shared.__file__),
              WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, case_path, inputs,
                                     {'upstream_revision': revision, 'case_id': case['id']}, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
