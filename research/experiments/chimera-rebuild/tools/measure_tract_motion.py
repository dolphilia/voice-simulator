"""可動声道のサンプル時刻、体積流量、圧力、放射を照合する。"""

import argparse
import csv
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.signal import lfilter

import measure_uniform_tube as shared
from measure_articulation import PROBE, write_upstream_events
from measure_tract_control import read_trace as read_targets
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASES = tuple(f'tract-motion-{name}' for name in ('lips', 'vowels', 'contact'))
GEOMETRY = (
    'pharynx_area_cm2', 'pharynx_minimum_cm2', 'pharynx_dx_cm',
    'oral_center_area_cm2', 'oral_center_minimum_cm2', 'oral_dx_cm',
    'lips_area_cm2', 'lips_minimum_cm2', 'constriction_minimum_cm2', 'velum_area_cm2',
)
ACOUSTICS = (
    'pressure_pharynx', 'pressure_junction', 'pressure_oral_center', 'pressure_lips', 'pressure_nose',
    'flow_center_in', 'flow_center_out', 'flow_wall_center', 'flow_velum', 'flow_lips', 'flow_nose',
    'radiation_derivative',
)
HEADER = ('sample', *GEOMETRY, *ACOUSTICS)


def load_samples(path, samples):
    with path.open() as file:
        header = tuple(next(file, '').strip().split(','))
        if header != HEADER:
            raise ValueError(f'{path.name} の観測列が不正です')
        data = np.loadtxt(file, delimiter=',', ndmin=2)
    if (data.shape != (samples, len(HEADER)) or not np.isfinite(data).all()
            or not np.array_equal(data[:, 0], np.arange(samples))):
        raise ValueError(f'{path.name} のサンプル番号または観測値が不正です')
    return data[:, 1:]


def upstream_samples(case, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'airway_adversarial', '--',
             '--nocapture'], cwd=UPSTREAM, stdout=artifacts / 'upstream-airway-adversarial.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    event_file = artifacts / 'upstream-events.txt'
    write_upstream_events(case, event_file)
    trace = artifacts / 'upstream-trace.csv'
    mode = 'network-with-contact' if case['area_control']['project_contacts'] else 'network'
    execute([str(probe), str(event_file), mode], cwd=UPSTREAM, stdout=trace)
    return trace


def reference_files(case, run_id):
    reference = WORKSPACE / 'runs' / run_id
    manifest_path = reference / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    trace = reference / 'artifacts/trace.csv'
    recorded = next((row['sha256'] for row in manifest['outputs']
                     if row['path'] == 'artifacts/trace.csv'), None)
    if (manifest['status'] != 'pass' or manifest['upstream_revision'] != case['upstream_revision']
            or recorded != sha256(trace)):
        raise ValueError('通過済みの制御目標とその出力ハッシュが必要です')
    case_path = f"cases/{manifest['case_id']}.json"
    snapshot = reference / manifest['source_snapshot'] / case_path
    recorded_case = next((row['sha256'] for row in manifest['inputs'] if row['path'] == case_path), None)
    if recorded_case != sha256(snapshot):
        raise ValueError('制御目標の記録に対応するケースのハッシュが不一致です')
    previous = json.loads(snapshot.read_text())
    if (any(case[k] != previous[k] for k in ('body', 'posture', 'articulators'))
            or case['area_control']['project_contacts'] != previous['area_control']['project_contacts']
            or case['measurement']['frames'] != previous['measurement']['frames']):
        raise ValueError('制御目標の採取に使ったケースと、姿勢と制御の入力をそろえてください')
    return manifest_path, trace


def independent_motion(case, config, target_file):
    settings = case['articulators']
    count = config['observed_tube_cells']
    frames, block, rate = case['measurement']['frames'], settings['control_block_samples'], settings['sample_rate_hz']
    passes, cells = read_targets(target_file, count, frames)
    names = [(-1, 'seed')] + [(frame, 'reapply' if (frame, 'reapply') in passes else 'apply')
                              for frame in range(frames)]
    targets = np.stack([passes[key] for key in names])
    index = {key: i for i, key in enumerate(cells)}
    ph = index['pharynx', 0]
    center = index['oral', count['oral'] // 2 - 1]
    narrow = index['oral', 2 * count['oral'] // 3 - 1]
    lips = index['oral', count['oral'] - 1]
    knots = np.column_stack((
        targets[:, ph, 2:4], targets[:, ph, 5] / count['pharynx'],
        targets[:, center, 2:4], targets[:, center, 5] / count['oral'],
        targets[:, lips, 2:4], targets[:, narrow, 3], targets[:, ph, 10],
    ))
    weight = (np.arange(1, block + 1) / block)[None, :, None]
    path = ((1 - weight) * knots[:-1, None, :] + weight * knots[1:, None, :]).reshape(-1, len(GEOMETRY))

    # セル8に自身や両隣からの押し出し流量の再配分が入らないことを端点で確認する。
    no_spill = np.min(targets[:, center - 1:center + 2, 3]) >= config['center_volume_no_spill_minimum_cm2']
    areas = np.r_[knots[0, 3], path[:, 3]].clip(min=.02)
    lengths = np.r_[knots[0, 5], path[:, 5]]
    volume = areas * lengths
    raw = -np.diff(volume) * rate
    coeff = -np.expm1(-2 * np.pi * config['volume_source_cutoff_hz'] / rate)
    filtered = lfilter([coeff], [1, coeff - 1], lfilter([coeff], [1, coeff - 1], raw))
    length_flow = -areas[1:] * np.diff(lengths) * rate
    return path, volume[1:], filtered, length_flow, bool(no_spill)


def comparison(a, b, columns, limits):
    errors = abs(a - b)
    maxima = errors.max(axis=0)
    failed = np.argwhere(errors >= limits)
    first = None
    if len(failed):
        sample, index = map(int, failed[0])
        first = {'sample': sample, 'column': columns[index],
                 'candidate': float(a[sample, index]), 'reference': float(b[sample, index])}
    return {'maximum_absolute_errors': dict(zip(columns, maxima.tolist(), strict=True)),
            'first_over_tolerance': first}


def inferred_volume_source(data, volume, rate):
    i = {name: index for index, name in enumerate(HEADER[1:])}
    pressure_delta = np.diff(data[:, i['pressure_oral_center']], prepend=0)
    net_flow = pressure_delta * volume * rate / (1.14e-3 * 35000**2)
    return net_flow - data[:, i['flow_center_in']] + data[:, i['flow_center_out']] + data[:, i['flow_wall_center']]


def observations(values, threshold):
    i = {name: index for index, name in enumerate(HEADER[1:])}

    def sample_span(mask):
        span = np.flatnonzero(mask)
        return None if not len(span) else [int(span[0]), int(span[-1]), int(len(span))]

    return {
        'lip_closed_sample_span': sample_span(values[:, i['lips_minimum_cm2']] < threshold),
        'constriction_closed_sample_span': sample_span(values[:, i['constriction_minimum_cm2']] < threshold),
        'velum_open_sample_span': sample_span(values[:, i['velum_area_cm2']] >= threshold),
        'peak_nose_flow_cm3_s': float(abs(values[:, i['flow_nose']]).max()),
        'oral_cell_length_span_cm': float(np.ptp(values[:, i['oral_dx_cm']])),
        'pharynx_cell_length_span_cm': float(np.ptp(values[:, i['pharynx_dx_cm']])),
    }


def within(value, expected):
    if value is None or expected is None:
        return value is expected
    if isinstance(value, list):
        first, last, count = value
        a, b, c, d = expected
        return a <= first <= b and c <= last <= d and count == last - first + 1
    return expected[0] <= value <= expected[1]


def measure(case, config, target_file, artifacts, execute):
    samples = config['internal_samples']
    candidate = load_samples(artifacts / 'trace.csv', samples)
    upper = load_samples(upstream_samples(case, artifacts, execute), samples)
    geometry, volume, source, length_flow, no_spill = independent_motion(case, config, target_file)
    split = len(GEOMETRY)
    limit = config['geometry_absolute_lt']
    base_geometry = comparison(candidate[:, :split], upper[:, :split], GEOMETRY, limit)
    independent = comparison(candidate[:, :split], geometry, GEOMETRY, limit)
    relative_tolerance = config['acoustics_relative_to_upstream_peak_lt']
    upper_peak = abs(upper[:, split:]).max(axis=0)
    # ゼロ系列は小さな絶対差でも検出できるよう、専用の比較幅を使う。
    scales = np.where(upper_peak > 0, upper_peak, 1e-12)
    base_acoustics = comparison(candidate[:, split:], upper[:, split:], ACOUSTICS, relative_tolerance * scales)
    base_acoustics['maximum_error_over_reference_scale'] = dict(zip(
        ACOUSTICS, (abs(candidate[:, split:] - upper[:, split:]).max(axis=0) / scales).tolist(), strict=True))

    rate = case['articulators']['sample_rate_hz']
    inferred = inferred_volume_source(candidate, volume, rate)
    inferred_upper = inferred_volume_source(upper, volume, rate)
    source_errors = {'candidate': float(abs(source - inferred).max()),
                     'upstream': float(abs(source - inferred_upper).max())}
    with (artifacts / 'independent-trace.csv').open('w', newline='') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(('sample', *GEOMETRY, 'volume_cm3', 'source_cm3_s', 'raw_length_contribution_cm3_s',
                         'inferred_candidate_cm3_s', 'inferred_upstream_cm3_s'))
        for i, (values, size, expected, length, a, b) in enumerate(zip(
                geometry, volume, source, length_flow, inferred, inferred_upper, strict=True)):
            writer.writerow((i, *values, size, expected, length, a, b))

    threshold = config['closed_below_cm2']
    measured = observations(candidate, threshold)
    measured['peak_abs_center_volume_source_cm3_s'] = float(abs(inferred).max())
    measured['peak_center_length_contribution_cm3_s'] = float(abs(length_flow).max())
    open_port = candidate[:, GEOMETRY.index('velum_area_cm2')] >= threshold
    velum_flow = candidate[:, HEADER.index('flow_velum') - 1]
    checks = {
        'fixed_upstream_geometry': base_geometry['first_over_tolerance'] is None,
        'fixed_upstream_acoustics': base_acoustics['first_over_tolerance'] is None,
        'independent_sample_interpolation': independent['first_over_tolerance'] is None,
        'center_volume_source_from_pressure_balance': no_spill and max(source_errors.values())
        < config['center_volume_source_absolute_lt_cm3_s'],
        'closed_velum_zero_flow': bool(np.all(velum_flow[~open_port] == 0.0)),
    }
    checks.update({f'registered_{key}': within(value, config[key]) for key, value in measured.items()})
    return {'checks': checks, 'internal_samples': samples, 'observations': measured,
            'upstream_geometry': base_geometry, 'upstream_acoustics': base_acoustics,
            'independent_geometry': independent, 'center_volume_source_error_cm3_s': source_errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    parser.add_argument('--control-run', help='同じ姿勢と制御入力で再生成した断面目標の実行ID')
    args = parser.parse_args()
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    config = case['measurement']['sample_geometry']
    control_run = args.control_run or config['control_reference_run']
    if any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', name) for name in (args.run_id, control_run)):
        parser.error('実行IDは英数字で始め、英数字・ハイフン・アンダースコアで指定してください')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')
    manifest, trace = reference_files(case, control_run)
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__), manifest, trace,
               *(WORKSPACE / f'tools/{name}.py' for name in ('measure_articulation', 'measure_tract_control',
                                                            'upstream_baseline')),
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'],
               'control_run_id': control_run, 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, path, sources, details,
                                     lambda artifacts, execute: measure(case, config, trace, artifacts, execute))


if __name__ == '__main__':
    raise SystemExit(main())
