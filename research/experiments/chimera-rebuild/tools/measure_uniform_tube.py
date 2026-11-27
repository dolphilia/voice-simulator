"""CLI の固定管レンダーを独立した線形計算および上流テストと比較する。"""

import argparse
import gzip
import json
from pathlib import Path
import platform
import re
import subprocess
import wave

import numpy as np

from run_storage import RunStorage
from trace_retention import RetainedTraces
from upstream_baseline import TUBE_CASE, UPSTREAM, WORKSPACE, describe, sha256


SOFT_WALL_CASE = WORKSPACE / 'cases/uniform-tube-soft-wall.json'
UPSTREAM_PROBE = WORKSPACE / 'tools/upstream_wall_probe.rs'


def linear_response(frequencies, tube, wall=None):
    # 離散時間の実装を呼ばず、終端から C と R–L の縦続回路を解く。
    area = tube['area_cm2']
    rho, speed, mu = 1.14e-3, 35000.0, 1.86e-4
    radius = np.sqrt(area / np.pi)
    dx = tube['length_cm'] / tube['cells']
    omega = 2 * np.pi * frequencies
    resistance = np.sqrt(rho * mu * np.pi * 700.0) * 2 * np.pi * radius * dx / area**2
    series = resistance + 1j * omega * rho * dx / area
    compliance = 1j * omega * dx * area / (rho * speed**2)
    radiation_l = 8 * rho / (3 * np.pi**2 * radius)
    radiation_r = 128 * rho * speed / (9 * np.pi**2 * area)
    radiation_admittance = 1 / radiation_r + 1 / (1j * omega * radiation_l)
    wall_admittance = 0.0
    if wall is not None:
        wall_impedance = wall['resistance_dyn_s_cm3'] + 1j * (
            omega * wall['mass_g_cm2'] - wall['stiffness_dyn_cm3'] / omega
        )
        wall_admittance = 2 * np.pi * radius * dx / wall_impedance
    shunt = compliance + wall_admittance

    # 口端圧力 1 における流量を、各セルの手前へ戻す。
    pressure = np.ones(frequencies.size, dtype=complex)
    flow = radiation_admittance + shunt
    sum_pressure = pressure.copy()
    for _ in range(tube['cells'] - 1):
        pressure += series * flow
        flow += shunt * pressure
        sum_pressure += pressure
    source = radiation_admittance
    if wall is not None:
        source = source + wall['radiation_fraction'] * sum_pressure * wall_admittance
    return np.abs(source / flow)


def peaks(frequencies, magnitude, minimum_hz, cutoff_hz):
    db = 20 * np.log10(np.maximum(magnitude, 1e-30))
    indices = np.flatnonzero((db[1:-1] > db[:-2]) & (db[1:-1] >= db[2:])) + 1
    left, mid, right = db[indices - 1], db[indices], db[indices + 1]
    offset = 0.5 * (left - right) / (left - 2 * mid + right)
    refined = frequencies[indices] + offset * (frequencies[1] - frequencies[0])
    return refined[(minimum_hz <= refined) & (refined < cutoff_hz)]


def read_trace(path, sample_count, columns):
    stream = gzip.open(path, 'rt') if path.suffix == '.gz' else path.open()
    with stream:
        header = stream.readline().strip().split(',')
        trace = np.loadtxt(stream, delimiter=',', ndmin=2)
    if len(header) != columns or trace.shape != (sample_count, columns) or not np.isfinite(trace).all():
        raise ValueError(f'{path.name} の系列の長さまたは有限性が条件外です ({trace.shape})')
    if not np.array_equal(trace[:, 0], np.arange(sample_count)):
        raise ValueError(f'{path.name} のサンプル番号が連続していません')
    return header, trace


def compare_series(candidate, reference, tolerance):
    error = np.abs(candidate - reference)
    peak = np.max(np.abs(reference))
    if peak == 0.0:
        failing = np.flatnonzero(error)
        relative = 0.0 if not failing.size else None
    else:
        failing = np.flatnonzero(error >= tolerance * peak)
        relative = float(np.max(error) / peak)
    return {
        'max_absolute_difference': float(np.max(error)),
        'max_abs_diff_over_reference_peak': relative,
        'first_sample_over_tolerance': int(failing[0]) if failing.size else None,
        'status': bool(relative is not None and relative < tolerance),
    }


def measure_wall(path, header, trace, case, fdtd, linear, upstream_peaks, rigid_summary):
    m, tube = case['measurement']['wall_checks'], case['tube']
    upstream_header, upstream_trace = read_trace(path, trace.shape[0], trace.shape[1])
    if header != upstream_header:
        raise ValueError('候補と上流の時系列の列が一致しません')
    comparisons = {
        name: compare_series(trace[:, i], upstream_trace[:, i], m['upstream_trace_peak_relative_error_lt'])
        for i, name in enumerate(header[1:], start=1)
    }
    columns = dict(zip(header, trace.T, strict=True))
    compliance = tube['area_cm2'] * tube['length_cm'] / (tube['cells'] * 1.14e-3 * 35000.0**2)
    pressure_to_flow = compliance * tube['sample_rate_hz']
    mouth_flow = columns['radiation_flow_cm3_s'] - columns['wall_radiation_flow_cm3_s']
    inlet_balance = columns['inlet_flow_cm3_s'] - columns['inlet_branch_flow_cm3_s'] - columns['inlet_wall_flow_cm3_s']
    outlet_balance = columns['outlet_branch_flow_cm3_s'] - columns['outlet_wall_flow_cm3_s'] - mouth_flow
    balance = {
        end: compare_series(np.diff(columns[f'{end}_pressure_dyn_cm2'], prepend=0.0) * pressure_to_flow,
                            predicted, m['endpoint_balance_peak_relative_error_lt'])
        for end, predicted in (('inlet', inlet_balance), ('outlet', outlet_balance))
    }
    shift = float(fdtd[0] - rigid_summary['fdtd_peaks_hz'][0])
    peak_error = np.max(np.abs(np.column_stack((fdtd, linear)) - upstream_peaks))
    checks = {
        'first_mode_shift': shift >= m['first_mode_shift_min_hz'],
        'upstream_peaks': bool(fdtd.size == m['peak_count'] and peak_error < m['upstream_peak_absolute_error_lt_hz']),
        'upstream_time_series': all(item['status'] for item in comparisons.values()),
        'wall_moves': bool(np.any(columns['inlet_wall_flow_cm3_s'] != 0.0)),
        'wall_radiation': bool(np.array_equal(columns['wall_radiation_flow_cm3_s'],
                                             case['wall']['radiation_fraction'] * columns['total_wall_flow_cm3_s'])),
        'endpoint_volume_balance': all(item['status'] for item in balance.values()),
    }
    return checks, {
        'first_fdtd_mode_shift_hz': shift,
        'maximum_absolute_upstream_peak_difference_hz': float(peak_error),
        'upstream_time_series': comparisons,
        'endpoint_volume_balance': balance,
        'peak_total_wall_flow_cm3_s': float(np.max(np.abs(columns['total_wall_flow_cm3_s']))),
    }


def measure(path, case, upstream_log, upstream_trace=None, rigid_summary=None):
    m, tube = case['measurement'], case['tube']
    fs = tube['sample_rate_hz']
    wall = case.get('wall')
    header, trace = read_trace(path, m['sample_count'], 12 if wall else 6)
    inlet = trace[:, 1]
    impulse = case['impulse']
    if np.count_nonzero(inlet) != 1 or inlet[impulse['sample']] != impulse['volume_cm3'] * fs:
        raise ValueError('入口流量と登録した体積インパルスが一致しません')

    derivative = trace[:, 5]
    nonzero = np.flatnonzero(derivative)
    first = int(nonzero[0]) if nonzero.size else None
    expected_first = impulse['sample'] + (1 if wall and wall['radiation_fraction'] > 0.0 else tube['cells'] - 1)
    full_peak = np.max(np.abs(derivative))
    tail_peak = np.max(np.abs(derivative[-m['tail_sample_count']:]))
    tail_ratio = float(tail_peak / full_peak) if full_peak > 0 else None

    nfft = 1 << (m['sample_count'] - 1).bit_length()
    bins = np.fft.rfftfreq(nfft, d=1 / fs)
    # 上流の計測と同様に、放射流量の微分を 2πf で戻す。
    recovered_flow = np.abs(np.fft.rfft(derivative, n=nfft)) / (2 * np.pi * np.maximum(bins, 1.0))
    cutoff = m['observed_peaks_below_hz']
    fdtd = peaks(bins, recovered_flow, 100.0, cutoff)
    sweep = np.linspace(m['sweep_start_hz'], m['sweep_end_hz'], m['sweep_points'])
    linear = peaks(sweep, linear_response(sweep, tube, wall), 80.0, cutoff)

    relative = np.abs(fdtd / linear - 1) if fdtd.size == linear.size else np.array([])
    wall_mode = 'true' if wall else 'false'
    upstream_peaks = np.asarray(re.findall(rf'walls={wall_mode}: ([0-9.]+) vs ([0-9.]+) Hz', upstream_log), dtype=float)
    if upstream_peaks.shape != (fdtd.size, 2) or upstream_peaks.shape != (linear.size, 2):
        raise ValueError('上流ログと候補で対応するピークの件数が一致しません')

    checks = {
        'causal_support': first == expected_first,
        'finite_samples': True,
        'decay': tail_ratio is not None and tail_ratio < m['tail_over_peak_lt'],
    }
    if wall is None:
        mode_count = m['quarter_wave_modes']
        end_correction = 8 * np.sqrt(tube['area_cm2'] / np.pi) / (3 * np.pi)
        quarter = (2 * np.arange(mode_count) + 1) * 35000.0 / (4 * (tube['length_cm'] + end_correction))
        quarter_error = np.abs(linear[:mode_count] / quarter - 1) if linear.size >= mode_count else np.array([])
        checks['quarter_wave'] = quarter_error.size == mode_count and bool(np.all(quarter_error < m['quarter_wave_relative_error_lt']))
        extra = {'quarter_wave_hz': quarter.tolist(), 'quarter_wave_relative_error': quarter_error.tolist()}
    else:
        mode_count = m['wall_checks']['peak_count']
        wall_checks, extra = measure_wall(upstream_trace, header, trace, case, fdtd, linear, upstream_peaks, rigid_summary)
        checks.update(wall_checks)
    checks['fdtd_vs_linear'] = relative.size >= mode_count and bool(np.all(relative < m['fdtd_vs_linear_relative_error_lt']))
    return {
        'checks': checks,
        'samples': m['sample_count'],
        'fft_size': nfft,
        'first_radiation_sample': first,
        'expected_first_radiation_sample': expected_first,
        'tail_over_peak': tail_ratio,
        'linear_peaks_hz': linear.tolist(),
        'fdtd_peaks_hz': fdtd.tolist(),
        'fdtd_vs_linear_relative_error': relative.tolist(),
        'upstream_fdtd_peaks_hz': upstream_peaks[:, 0].tolist(),
        'upstream_linear_peaks_hz': upstream_peaks[:, 1].tolist(),
        'fdtd_minus_upstream_hz': (fdtd - upstream_peaks[:, 0]).tolist(),
        'linear_minus_upstream_hz': (linear - upstream_peaks[:, 1]).tolist(),
        **extra,
    }


def build_upstream_probe(source, artifacts, execute, *, extra_libraries=(), upstream=UPSTREAM,
                         rustc_args=(), package='chimera', lto='fat', cargo_args=()):
    target = package.replace('-', '_')
    build_message = artifacts / ('upstream-build.jsonl' if package == 'chimera' else f'{package}-build.jsonl')
    suffix = '.exe' if package == 'chimera' else f'-{package}.exe'
    probe = artifacts / (source.stem + suffix)
    execute(['cargo', 'build', '--locked', '--release', '-p', package, *cargo_args, '--message-format=json'],
            cwd=upstream, stdout=build_message)
    toolchains = [json.loads(line) for line in build_message.read_text().splitlines()]
    externs = []
    primary_library = None
    for name in (target, *extra_libraries):
        libraries = [Path(filename) for event in toolchains
                     if event.get('reason') == 'compiler-artifact' and event['target']['name'] == name
                     for filename in event['filenames'] if filename.endswith('.rlib')]
        if len(libraries) != 1:
            raise ValueError(f'cargo build のライブラリ {name} を特定できません')
        library, = libraries
        externs.extend(('--extern', f'{name}={library}'))
        if name == target:
            primary_library = library
    execute(['rustc', '--edition=2024', '-C', 'opt-level=3', '-C', 'panic=abort',
             '-C', f'lto={lto}', '-C', 'codegen-units=1', *rustc_args, *externs, '-L',
             f'dependency={primary_library.parent / "deps"}', str(source), '-o', str(probe)])
    return probe


def capture_upstream(case, artifacts, execute):
    probe = build_upstream_probe(UPSTREAM_PROBE, artifacts, execute)
    tube, impulse, measure, wall = (case[key] for key in ('tube', 'impulse', 'measurement', 'wall'))
    arguments = [tube['sample_rate_hz'], tube['length_cm'], tube['area_cm2'], tube['cells'],
                 impulse['sample'], impulse['volume_cm3'], measure['sample_count'], wall['mass_g_cm2'],
                 wall['resistance_dyn_s_cm3'], wall['stiffness_dyn_cm3'], wall['radiation_fraction']]
    path = artifacts / 'upstream-trace.csv'
    execute([str(probe), *map(str, arguments)], cwd=UPSTREAM, stdout=path)
    return path


def candidate_sources():
    return [WORKSPACE / 'Cargo.toml', WORKSPACE / 'Cargo.lock',
            *sorted(WORKSPACE.glob('crates/*/Cargo.toml')), *sorted(WORKSPACE.glob('crates/*/src/**/*.rs')),
            *sorted(WORKSPACE.glob('crates/*/src/**/*.json'))]


def run_measurement(run_id, upstream_id, rigid_run_id=None):
    case_path = SOFT_WALL_CASE if rigid_run_id else TUBE_CASE
    case = json.loads(case_path.read_text())
    rigid_case = json.loads(TUBE_CASE.read_text())
    if any(case[key] != rigid_case[key] for key in ('tube', 'impulse', 'upstream_revision')):
        raise ValueError('軟壁の管と駆動条件は比較用の剛体ケースと一致する必要があります')
    upstream_run = WORKSPACE / 'runs' / upstream_id
    baseline_path = upstream_run / 'manifest.json'
    baseline = json.loads(baseline_path.read_text())
    if baseline['upstream_revision'] != case['upstream_revision']:
        raise ValueError('上流のコミットがケースと一致しません')
    baseline_input = next(item for item in baseline['inputs'] if item['path'] == str(TUBE_CASE.relative_to(WORKSPACE)))
    if baseline_input['sha256'] != sha256(TUBE_CASE):
        raise ValueError('上流実行時のケース定義と一致しません')
    airway = next(item for item in baseline['cases'] if item['id'] == 'airway')
    log_path = upstream_run / airway['log']['path']
    if airway['status'] != 'pass' or sha256(log_path) != airway['log']['sha256']:
        raise ValueError('上流の一様管テスト結果を確認できません')

    cargo_sources = candidate_sources()
    input_paths = [case_path, TUBE_CASE, baseline_path, log_path, Path(__file__).resolve(),
                   WORKSPACE / 'tools/upstream_baseline.py', *cargo_sources]
    rigid_summary = None
    if rigid_run_id:
        rigid_run = WORKSPACE / 'runs' / rigid_run_id
        rigid_manifest_path = rigid_run / 'manifest.json'
        rigid_summary_path = rigid_run / 'summary.json'
        rigid_manifest = json.loads(rigid_manifest_path.read_text())
        prior_sources = {item['path']: item['sha256'] for item in rigid_manifest['inputs']}
        summary_digest = next((item['sha256'] for item in rigid_manifest['outputs'] if item['path'] == 'summary.json'), None)
        if (rigid_manifest['status'] != 'pass' or rigid_manifest['upstream_run_id'] != upstream_id
                or prior_sources.get(str(TUBE_CASE.relative_to(WORKSPACE))) != sha256(TUBE_CASE)
                or any(prior_sources.get(str(path.relative_to(WORKSPACE))) != sha256(path) for path in cargo_sources)
                or summary_digest != sha256(rigid_summary_path)):
            raise ValueError('同じ候補ソースと上流基準で通過した剛体ケースが必要です')
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
        local_diff = subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
        if revision != case['upstream_revision'] or local_diff:
            raise ValueError('時系列の取得には変更のない固定上流版が必要です')
        rigid_summary = json.loads(rigid_summary_path.read_text())
        input_paths.extend((rigid_manifest_path, rigid_summary_path, UPSTREAM_PROBE))

    def measure_run(artifacts, execute):
        upstream_trace = capture_upstream(case, artifacts, execute) if rigid_run_id else None
        return measure(artifacts / 'trace.csv', case, log_path.read_text(), upstream_trace, rigid_summary)

    details = {'upstream_run_id': upstream_id, 'upstream_revision': case['upstream_revision']}
    if rigid_run_id:
        details['rigid_run_id'] = rigid_run_id
    return record_measurement(run_id, case_path, input_paths, details, measure_run)


def record_measurement(run_id, case_path, input_paths, details, measure_run, *, command='render',
                       input_root=WORKSPACE):
    retained_traces = RetainedTraces(case_path)
    storage = RunStorage(WORKSPACE / 'runs', run_id)
    storage.create()
    run = storage.run
    artifacts = storage.artifacts
    source_snapshot = storage.logical / 'source'
    inputs = []
    storage_inputs = (WORKSPACE / 'tools/run_storage.py', WORKSPACE / 'tools/trace_retention.py')
    for path in dict.fromkeys([*input_paths, *storage_inputs]):
        entry = describe(path, input_root)
        relative = Path(entry['path'])
        if not path.is_relative_to(WORKSPACE / 'runs'):
            storage.snapshot_source(path, source_snapshot / relative, entry['sha256'])
        inputs.append(entry)
    trace = artifacts / 'trace.csv'
    inspect = artifacts / 'settings.json'
    cargo_log = artifacts / 'cargo.log'
    prefix = ['cargo', 'run', '--locked', '--release', '--manifest-path', str(WORKSPACE / 'Cargo.toml'), '-p', 'vocal-cli', '--']
    manifest = {
        'schema_version': 1,
        'run_id': run_id,
        **details,
        'candidate_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=WORKSPACE, text=True).strip(),
        'candidate_diff_status': subprocess.check_output(['git', 'status', '--porcelain', '--', '.'], cwd=WORKSPACE, text=True).strip(),
        'environment': {
            'platform': platform.platform(),
            'numpy': np.__version__,
            'python': platform.python_version(),
            'rustc': subprocess.check_output(['rustc', '-V'], text=True).strip(),
        },
        'inputs': inputs,
        'source_snapshot': str(source_snapshot.relative_to(run)),
        'commands': [],
        'status': 'fail',
    }
    if storage.metadata is not None:
        manifest['storage'] = storage.metadata

    def execute(command, cwd=WORKSPACE, stdout=None):
        env = storage.subprocess_env()
        argv = [arg.replace(str(artifacts), '$ARTIFACTS').replace(str(UPSTREAM), '$UPSTREAM')
                .replace(str(WORKSPACE), '$WORKSPACE') for arg in command]
        if input_root != WORKSPACE:
            argv = [arg.replace(str(input_root), '$REPOSITORY') for arg in argv]
        if cwd == UPSTREAM:
            location = '$UPSTREAM'
        elif cwd == WORKSPACE:
            location = '$WORKSPACE'
        elif input_root != WORKSPACE and cwd.is_relative_to(input_root):
            location = '$REPOSITORY/' + str(cwd.relative_to(input_root))
        else:
            location = str(cwd)
        execution = {'argv': argv, 'cwd': location}
        manifest['commands'].append(execution)
        with cargo_log.open('ab') as log:
            if stdout is None:
                process = subprocess.run(command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env=env)
            else:
                with stdout.open('wb') as stream:
                    process = subprocess.run(command, cwd=cwd, stdout=stream, stderr=log, env=env)
        execution['exit_code'] = process.returncode
        process.check_returncode()

    try:
        if command is not None:
            execute([*prefix, 'inspect', str(case_path)], stdout=inspect)
            execute([*prefix, command, str(case_path), str(trace)])
        result = measure_run(artifacts, execute)
        (run / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        if all(result['checks'].values()):
            retained_traces.apply(artifacts, describe, manifest)
            manifest['status'] = 'pass'
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as error:
        manifest['error'] = str(error)
    manifest['outputs'] = []
    try:
        storage.publish()
        for path in sorted(run.rglob('*')):
            if path.is_file() and source_snapshot not in path.parents:
                manifest['outputs'].append(describe(path, run))
        storage.assert_connected(artifacts)
    except (OSError, EOFError, ValueError, wave.Error) as error:
        if storage.metadata is None:
            raise
        manifest['status'] = 'fail'
        manifest['storage_error'] = str(error)
    (run / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'{run_id}: {manifest["status"]}')
    return int(manifest['status'] != 'pass')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('upstream_id')
    parser.add_argument('--rigid-run', help='軟壁を測定し、指定した剛体の実行と比較する')
    args = parser.parse_args()
    if any(not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', name)
           for name in (args.run_id, args.upstream_id, args.rigid_run) if name is not None):
        parser.error('実行 ID は英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    return run_measurement(args.run_id, args.upstream_id, args.rigid_run)


if __name__ == '__main__':
    raise SystemExit(main())
