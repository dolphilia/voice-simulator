"""隔離ビルドで対象の枝だけを接線化し、口端応答を再計測する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_fixed_alpha_branch_loss as losses
from measure_fan_crossing_allocations import run_manifest, verified_path
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-alpha-loss-tangent.json'
UPPER = 'crates/chimera/src/airway/network.rs'
CORE = 'crates/vocal-core/src/airway/network.rs'
CLI = 'crates/vocal-cli/src/geometry_case.rs'
PROBE = losses.MEAN.sagittal.PROBE
CANDIDATE_DATA = [WORKSPACE / 'data' / name for name in
                  ('cmudict.txt.gz', 'mandarin.txt.gz', 'CMUDICT-LICENSE.txt', 'MANDARIN-PINYIN-LICENSE.txt')]
READ = losses.READ
ARMS = losses.ARMS
EDITIONS = losses.EDITIONS
VARIANTS = ('baseline', 'one_branch', 'three_branches')
EVIDENCE = ('tangent-observations.npz', 'trace-hashes.json', 'dc.json',
            'upstream-tangent.patch', 'candidate-tangent.patch', 'probe-tangent.patch')
SMOOTH_SOLVER = """    fn research_smoothed_flow(drive: f64, linear: f64, loss: f64, width: f64) -> f64 {
        if drive == 0.0 {
            return drive;
        }
        // 正の流量の大きさで単調な圧力式を解き、最後に符号を戻す。
        let mut low = 0.0;
        let mut high = width;
        for _ in 0..56 {
            let mid = low + 0.5 * (high - low);
            let x = mid / width;
            let g = x * (3.0 + x * (x - 3.0));
            if linear * mid + loss * mid * mid * g < drive.abs() {
                low = mid;
            } else {
                high = mid;
            }
        }
        (low + 0.5 * (high - low)).copysign(drive)
    }

"""


def smoothing_setter(setter):
    return (setter.replace('research_set_loss_tangent', 'research_set_loss_smoothing')
            .replace('q0', 'width').replace('接線', '平滑化').replace('基準流量', '流量幅'))


def archive_inputs(study):
    spec = study['reference']
    run, header = record = run_manifest(spec['run'], spec['case'], study['upstream_revision'])
    manifest = run / 'manifest.json'
    if header['status'] != 'pass' or sha256(manifest) != spec['sha256']:
        raise ValueError('枝ごとの損失を照合した保存実行が登録値と一致しません')
    row, = [item for item in header['inputs'] if item['path'].endswith(f'/cases/{spec["case"]}.json')]
    case = run / header['source_snapshot'] / row['path']
    if sha256(case) != row['sha256']:
        raise ValueError('保存された枝損失ケースのハッシュが一致しません')
    reference = losses.archive_inputs(READ(case))
    paths = {'manifest.json': manifest, 'reference-case.json': case,
             **{name: verified_path(record, name) for name in
                ('summary.json', 'artifacts/branch-states.npz', *(f'artifacts/{arm}.json' for arm in ARMS))},
             **{name: reference[name] for name in ('upstream-geometry.csv', *losses.IMPULSE.harmonic.NETWORK_FILES)}}
    first_spec = study['initial_dc_comparison']
    first_run, first_header = first = run_manifest(first_spec['run'], study['id'], study['upstream_revision'])
    first_manifest = first_run / 'manifest.json'
    if first_header['status'] != 'fail' or sha256(first_manifest) != first_spec['sha256']:
        raise ValueError('最初の定常流判定の保存状態が一致しません')
    paths.update({'initial-manifest.json': first_manifest, 'initial-summary.json': verified_path(first, 'summary.json'),
                  'initial-traces.npz': verified_path(first, 'artifacts/tangent-observations.npz')})
    return paths


def patch_upstream(source, *, law='tangent'):
    signature = ('    /// Advance one internal sample. Returns radiated pressure (arbitrary units ∝ dU_rad/dt).\n'
                 '    pub fn step(&mut self) -> f64 {')
    setter = """    pub fn research_set_loss_tangent(&mut self, edges: &[[usize; 2]], q0: f64) -> Result<(), &'static str> {
        if !q0.is_finite() || q0 <= 0.0 {
            return Err("接線の基準流量には有限の正値を指定してください");
        }
        self.research_loss_references.resize(self.n_branches, None);
        for &[a, b] in edges {
            let j = (0..self.n_branches).find(|&j| self.b_a[j] == a && self.b_b[j] == b
                    && self.b_kind[j] == KIND_SERIES)
                .ok_or("接線の対象に指定した直列枝が見つかりません")?;
            self.research_loss_references[j] = Some(q0);
        }
        Ok(())
    }

"""
    marker = '                let u = if c >= 0.0 {'
    update = """                let u = if let Some(q0) = self.research_loss_references.get(j).copied().flatten() {
                    let slope = 2.0 * kf * q0;
                    (c + kf * q0 * q0) / (bq + slope)
                } else if c >= 0.0 {"""
    if law in ('passive', 'low_flow'):
        update = """                let u = if let Some(q0) = self.research_loss_references.get(j).copied().flatten().filter(|_| c > 0.0) {
                    if c <= bq * (0.5 * q0) {
                        c / bq
                    } else {
                        let slope = 2.0 * kf * q0;
                        (c + kf * q0 * q0) / (bq + slope)
                    }
                } else if c >= 0.0 {"""
        if law == 'low_flow':
            update = update.replace('c > 0.0)', 'c > 0.0 && c <= bq * q0 + kf * q0 * q0)')
            update = update.replace('.filter(|_|', '.filter(|&q0|')
    elif law == 'high_flow':
        update = update.replace('.flatten() {',
                                '.flatten().filter(|&q0| c > bq * q0 + kf * q0 * q0) {')
    elif law == 'smooth':
        setter = smoothing_setter(setter) + SMOOTH_SOLVER
        update = """                let kinetic = if c >= 0.0 { kf } else { kb };
                let width = self.research_loss_references.get(j).copied().flatten()
                    .filter(|&width| kinetic > 0.0 && c.abs() < bq * width + kinetic * width * width);
                let u = if let Some(width) = width {
                    Self::research_smoothed_flow(c, bq, kinetic, width)
                } else if c >= 0.0 {"""
    return losses.periodic.LF.patch_source(source, UPPER, (
        ('    pub n_branches: usize,\n    b_a: Vec<usize>,',
         '    pub n_branches: usize,\n    research_loss_references: Vec<Option<f64>>,\n    b_a: Vec<usize>,'),
        ('            branch_area: Vec::new(),', '            branch_area: Vec::new(),\n            research_loss_references: Vec::new(),'),
        (signature, setter + signature),
        (marker, update),
    ))


def patch_core(source, *, law='tangent'):
    method = '    pub fn branch_flow(&self, branch: usize) -> f64 {'
    setter = """    pub fn research_set_loss_tangent(&mut self, edges: &[[usize; 2]], q0: f64) -> Result<(), &'static str> {
        if !q0.is_finite() || q0 <= 0.0 {
            return Err("接線の基準流量には有限の正値を指定してください");
        }
        for &nodes in edges {
            let branch = self.branches.iter_mut().find(|branch| branch.nodes == nodes
                    && branch.port.is_none() && branch.inertance > 0.0)
                .ok_or("接線の対象に指定した直列枝が見つかりません")?;
            branch.research_loss_reference = Some(q0);
        }
        Ok(())
    }

"""
    marker = '        self.flow = if loss == 0.0 {'
    update = """        self.flow = if let Some(q0) = self.research_loss_reference {
            let slope = 2.0 * self.forward_loss * q0;
            (drive + self.forward_loss * q0 * q0) / (linear + slope)
        } else if loss == 0.0 {"""
    if law in ('passive', 'low_flow'):
        update = """        self.flow = if let Some(q0) = self.research_loss_reference.filter(|_| drive > 0.0) {
            if drive <= linear * (0.5 * q0) {
                drive / linear
            } else {
                let slope = 2.0 * self.forward_loss * q0;
                (drive + self.forward_loss * q0 * q0) / (linear + slope)
            }
        } else if loss == 0.0 {"""
        if law == 'low_flow':
            update = update.replace('.filter(|_| drive > 0.0)',
                                    '.filter(|&q0| drive > 0.0 && drive <= linear * q0 + self.forward_loss * q0 * q0)')
    elif law == 'high_flow':
        update = update.replace(
            'self.research_loss_reference {',
            'self.research_loss_reference.filter(|&q0| drive > linear * q0 + self.forward_loss * q0 * q0) {')
    elif law == 'smooth':
        setter = smoothing_setter(setter)
        update = """        let width = self.research_loss_reference
            .filter(|&width| loss > 0.0 && drive.abs() < linear * width + loss * width * width);
        self.flow = if let Some(width) = width {
            Self::research_smoothed_flow(drive, linear, loss, width)
        } else if loss == 0.0 {"""
    changes = (
        ('    reverse_loss: f64,', '    reverse_loss: f64,\n    research_loss_reference: Option<f64>,'),
        ('                reverse_loss: 0.0,', '                reverse_loss: 0.0,\n                research_loss_reference: None,'),
        ('            reverse_loss,', '            reverse_loss,\n            research_loss_reference: None,'),
        (method, setter + method),
        (marker, update),
    )
    if law == 'smooth':
        signature = '    fn step(&mut self, dt: f64, pressure_difference: f64) -> f64 {'
        changes += ((signature, SMOOTH_SOLVER + signature),)
    return losses.periodic.LF.patch_source(source, CORE, changes)


def patch_driver(source, file, loop, advance, network, bias, skip, *, setter='research_set_loss_tangent'):
    config = """
fn research_loss_request() -> io::Result<(usize, usize, Vec<[usize; 2]>)> {
    let read = |key| std::env::var(key).map_err(io::Error::other);
    let parse = |text: &str| text.parse::<usize>().map_err(io::Error::other);
    let start = parse(&read("CHIMERA_TANGENT_START")?)?;
    let early_end = parse(&read("CHIMERA_TANGENT_EARLY_END")?)?;
    let pairs = read("CHIMERA_TANGENT_EDGES")?;
    let edges = pairs.split(',').filter(|piece| !piece.is_empty()).map(|piece| {
        let (a, b) = piece.split_once(':')
            .ok_or_else(|| io::Error::other("枝の向きを始点:終点で指定してください"))?;
        Ok([parse(a)?, parse(b)?])
    }).collect::<io::Result<Vec<_>>>()?;
    if start == 0 || start >= early_end {
        return Err(io::Error::other("観測する早期区間を空にできません"));
    }
    Ok((start, early_end, edges))
}
"""
    enable = f"""        if sample == research_start && !research_edges.is_empty() {{
            {network}.{setter}(&research_edges, {bias}).map_err(io::Error::other)?;
        }}
"""
    window = """    let (research_start, research_early_end, research_edges) = research_loss_request()?;
    let research_early = research_start - 1..research_early_end;
"""
    marker = 'fn write_grid<const N: usize>(' if file == CLI else 'fn write_resampled('
    return losses.periodic.LF.patch_source(source, file, (
        (loop, window + loop), (advance, enable + advance), (marker, config + '\n' + marker),
        (skip, skip[:-1].rstrip() + ' && !research_early.contains(&sample) {'),
    ))


def build_probes(study, out, scratch, execute, *, law):
    upper_dir = scratch / 'upstream'
    upper_dir.mkdir()
    tar = scratch / 'upper.tar'
    execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=tar)
    execute(['tar', '-xf', str(tar), '-C', str(upper_dir)])
    (out / 'upstream-tangent.patch').write_text(patch_upstream(upper_dir, law=law))
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial',
             'steady_flow_through_a_short_constriction_obeys_bernoulli_with_jet_loss'],
            cwd=UPSTREAM, stdout=out / 'pristine-upstream-kinetic-test.log')
    probe = scratch / PROBE.name
    shutil.copyfile(PROBE, probe)
    control = {'setter': 'research_set_loss_smoothing'} if law == 'smooth' else {}
    width = repr(float(study['measurement']['smoothing_width_cm3_s'])) if law == 'smooth' else None
    (out / 'probe-tangent.patch').write_text(patch_driver(
        scratch, probe.name, '    for sample in 0..samples {', '        let radiation = net.step();',
        'net', width or 'steady_flow',
        '        if trace_state_samples\n            .as_ref()\n            .is_some_and(|range| !range.contains(&sample))\n        {',
        **control))
    upstream = losses.MEAN.shared.build_upstream_probe(
        probe, scratch, execute, upstream=upper_dir, cargo_args=('--offline', '--target-dir', str(scratch / 'upper-target')))
    candidate_dir = scratch / 'candidate'
    for path in [*losses.MEAN.shared.candidate_sources(), *CANDIDATE_DATA]:
        target = candidate_dir / path.relative_to(WORKSPACE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    core_patch = patch_core(candidate_dir, law=law)
    cli_patch = patch_driver(
        candidate_dir, CLI, '    for sample in 0..settings.sample_count.get() {',
        '        let radiation = network.step(airway.pharynx_entry, excitation);',
        'network', width or 'settings.steady_flow_cm3_s',
        '        if trace.as_ref().is_some_and(|range| !range.contains(&sample)) {', **control)
    (out / 'candidate-tangent.patch').write_text(core_patch + cli_patch)
    target = scratch / 'candidate-target'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--target-dir', str(target)],
            cwd=candidate_dir)
    return {'upstream': upstream, 'candidate': target / 'release/vocal-cli'}


def dc_case(study, archive):
    cfg = study['measurement']
    case = READ(archive['artifacts/coupled.json'])
    case['id'] = f'{study["id"]}-dc'
    case['fixed_airway']['sample_count'] = cfg['dc_window_samples'][1]
    case['fixed_airway']['trace_state_samples'] = cfg['dc_window_samples']
    case['fixed_airway_periodic_flow']['flow_cm3_s'] = [repr(cfg['reference_flow_cm3_s'])]
    return case


def read_states(path, indices, nodes, branches):
    header = ('sample', *losses.TRACE, *(f'pressure_node_{i}' for i in range(nodes)),
              *(f'flow_branch_{i}' for i in range(branches)))
    with path.open() as stream:
        if tuple(stream.readline().strip().split(',')) != header:
            raise ValueError(f'節点と枝の観測列が不正です ({path.name})')
        data = np.loadtxt(stream, delimiter=',', ndmin=2)
    if data.shape != (len(indices), len(header)) or not np.array_equal(data[:, 0], indices):
        raise ValueError('保存された観測窓が登録した標本番号と一致しません')
    if not np.isfinite(data).all():
        raise ValueError('節点と枝の系列に非有限値が含まれます')
    return data[:, 1:]


def capture(study, archive, out, execute, *, law='tangent', arms=ARMS):
    if law not in ('tangent', 'passive', 'high_flow', 'low_flow', 'smooth'):
        raise ValueError('未知の圧力損失式です')
    cfg = study['measurement']
    variants = tuple(cfg['variants'])
    early, steady = [np.arange(*cfg[key]) for key in ('early_window_samples', 'steady_window_samples')]
    dc = out / 'dc.json'
    dc.write_text(json.dumps(dc_case(study, archive), ensure_ascii=False, indent=2) + '\n')
    nodes, branches, _ = losses.IMPULSE.source_elements(archive)
    arrays, baselines = {}, {}
    with TemporaryDirectory(prefix='tangent-build-', dir=out) as temp:
        scratch = Path(temp)
        binaries = build_probes(study, out, scratch, execute, law=law)
        for arm in (*arms, 'dc'):
            path = dc if arm == 'dc' else archive[f'artifacts/{arm}.json']
            case = READ(path)
            gauge = cfg['dc_window_samples'] if arm == 'dc' else [int(steady[0]) - 1, int(steady[-1]) + 1]
            history = np.arange(*gauge) if arm == 'dc' else np.r_[early, np.arange(*gauge)]
            drive = case['fixed_airway_periodic_flow']
            fixed = case['fixed_airway']
            stimulus = scratch / 'flow.txt'
            stimulus.write_text('\n'.join(drive['flow_cm3_s']) + '\n')
            args = [fixed['sample_rate_hz'], fixed['sample_count'], drive['start_sample'],
                    fixed['steady_flow_cm3_s'], stimulus, *gauge]
            for variant in (('baseline', variants[-1]) if arm == 'dc' else variants):
                edges = ','.join(f'{a}:{b}' for a, b in cfg['variants'][variant])
                command = ['env', f'CHIMERA_TANGENT_START={cfg["activation_sample"]}',
                           f'CHIMERA_TANGENT_EARLY_END={early[-1]+1}', f'CHIMERA_TANGENT_EDGES={edges}']
                for edition in EDITIONS:
                    key = f'{arm}_{variant}_{edition}'
                    trace = scratch / f'{key}.csv'
                    if edition == 'upstream':
                        execute([*command, str(binaries[edition]), '--fixed-airway-state', *map(str, args),
                                 *losses.MEAN.sagittal.pose_controls(case)], cwd=UPSTREAM, stdout=trace)
                    else:
                        execute([*command, str(binaries[edition]), 'render', str(path), str(trace)])
                    series = read_states(trace, history, len(nodes), len(branches))
                    trace.unlink()
                    if arm != 'dc' and variant == 'baseline':
                        baselines[key] = losses.MEAN.sha_array(series[len(early):])
                        arrays[key] = series[:len(early)].copy()
                    else:
                        arrays[key] = series
    np.savez_compressed(out / 'tangent-observations.npz', **arrays)
    (out / 'trace-hashes.json').write_text(json.dumps(baselines, indent=2) + '\n')


def kinetic_terms(states, nodes, links, global_indices, geometry, rate, q0):
    left, right = links[:, :2].astype(int).T
    n_fields = len(losses.TRACE)
    p = states[:, n_fields:n_fields + len(nodes)]
    velocity = states[:, n_fields + len(nodes):][:, global_indices]
    inertance, resistance = links[:, 3:5].T
    indexed = np.column_stack((left, right, np.arange(len(links))))
    k_forward = losses.MEAN.drag_on_path(indexed, geometry)
    k_reverse = losses.MEAN.drag_on_path(indexed[:, [1, 0, 2]], geometry)
    u = velocity[1:]
    actual = p[:-1, left] - p[:-1, right] - rate * inertance * np.diff(velocity, axis=0) - resistance * u
    reference = k_forward * q0 * (2 * u - q0)
    quadratic = np.where(u >= 0, k_forward, k_reverse) * u * abs(u)
    return u, actual, quadratic, reference


def kinetic_residual(states, nodes, links, global_indices, geometry, rate, q0, tangent):
    _, actual, quadratic, reference = kinetic_terms(states, nodes, links, global_indices, geometry, rate, q0)
    expected = np.where(tangent, reference, quadratic)
    error = float(abs(actual - expected).max() / abs(expected).max())
    return np.where(tangent, 0, quadratic - reference), error


def state_response(cfg, states, stimulus, model, tangent):
    nodes, topology, source, geometry, compliance, active, connected, main, linear = model
    frequencies = np.array(cfg['frequencies_hz'])
    fs = cfg['internal_rate_hz']
    projection = np.exp(-2j * np.pi / fs * np.outer(frequencies, np.arange(len(stimulus))))
    q = projection @ stimulus / len(stimulus)
    remainder, law = kinetic_residual(states, nodes, topology[connected], connected, geometry,
                                      fs, main * cfg['reference_flow_cm3_s'], tangent)
    residual = projection @ remainder / len(stimulus) / q[:, None]
    measured = projection @ states[1:, losses.TRACE.index('flow_lips')] / len(stimulus) / q
    contributions = []
    for f, change in zip(frequencies, residual, strict=True):
        lip, _, _ = losses.responses(f, fs, nodes, linear, compliance, active, connected, source, change)
        contributions.append(lip)
    return measured, np.asarray(contributions), law


def peak_error(candidate, upper):
    peak = abs(upper).max(axis=0)
    return float((abs(candidate - upper) / np.where(peak > 0, peak, 1)).max())


def dc_stationarity(cfg, fields, original, trial):
    differences = abs(trial - original).max(axis=0)
    pressure = float(differences[[i for i, key in enumerate(fields) if key.startswith('pressure_')]].max())
    flow = float(differences[[i for i, key in enumerate(fields) if key.startswith('flow_')]].max())
    derivative = float(differences[fields.index('radiation_derivative')])
    inlet_pressure = float(abs(original[:, fields.index('pressure_pharynx_entry')]).max())
    flow_scale = cfg['reference_flow_cm3_s']
    return {'max_pressure_change_dyn_cm2': pressure, 'max_flow_change_cm3_s': flow,
            'max_radiation_derivative_change_cm3_s2': derivative, 'inlet_pressure_scale_dyn_cm2': inlet_pressure,
            'relative_error_at_stationary_scales': max(pressure / inlet_pressure, flow / flow_scale,
                                                       derivative / (flow_scale * cfg['internal_rate_hz']))}


def first_response(cfg, base, trial, scale, fields):
    threshold = cfg['first_response_peak_relative_threshold']
    absolute = abs(trial - base)
    changed = np.argwhere(absolute > threshold * np.maximum(scale, abs(base).max(axis=0)))
    if not changed.size:
        return None
    row = int(changed[0, 0])
    return {'sample': cfg['early_window_samples'][0] + row,
            'fields': [fields[i] for i in changed[changed[:, 0] == row, 1]]}


def complex_rows(cfg, baseline, interposed, local, reference_rows):
    original, base_terms, _ = baseline
    changed, trial_terms, _ = interposed
    measured = changed - original
    predicted = -base_terms[:, 1:][:, local].sum(axis=1)
    remaining = (trial_terms[:, 1:] - base_terms[:, 1:])[:, ~local].sum(axis=1)
    scale = abs(measured)
    agree = abs(measured - predicted - remaining) / scale
    reference = original - base_terms[:, 0]
    rows = []
    for i, frequency in enumerate(cfg['frequencies_hz']):
        stored = -sum(complex(item['lip_transfer_contribution_real'], item['lip_transfer_contribution_imag'])
                      for item in reference_rows[frequency])
        rows.append({
            'frequency_hz': frequency, 'measured_change': losses.IMPULSE.harmonic.pair(measured[i]),
            'predicted_from_removed_terms': losses.IMPULSE.harmonic.pair(predicted[i]),
            'other_branches_change': losses.IMPULSE.harmonic.pair(remaining[i]),
            'projected_fraction_of_original_difference_removed': float(
                -(measured[i] * reference[i].conjugate()).real / abs(reference[i])**2),
            'prediction_relative_error': float(abs(measured[i] - predicted[i]) / abs(predicted[i])),
            'relative_reconstruction_error': float(agree[i]),
            'archived_prediction_relative_error': float(abs(predicted[i] - stored) / abs(stored)),
        })
    return rows


def measurement_model(cfg, archive, archived):
    nodes, topology, source = losses.IMPULSE.source_elements(archive)
    _, geometry = losses.MEAN.fixed.read_upper_geometry(archive['upstream-geometry.csv'])
    fs = cfg['internal_rate_hz']
    compliance, active = losses.IMPULSE.compliance_floor(nodes, topology, source, fs)
    connected = losses.connected_links(topology, active, source['inject'])
    path = losses.MEAN.airway_path(topology, active, source)
    main = np.isin(connected, path[:, 2])
    mapping = np.arange(len(topology))
    for item in archived['realigned_branches']:
        mapping[item['upstream']] = item['candidate']
    offset = len(losses.TRACE) + len(nodes)
    indices = np.r_[np.arange(offset), offset + mapping]
    nominal = topology.copy()
    nominal[path[:, 2], 4] += 2 * cfg['reference_flow_cm3_s'] * losses.MEAN.drag_on_path(path, geometry)
    model = (nodes, topology, source, geometry, compliance, active, connected, main, nominal)
    addresses = [tuple(row[:2].astype(int)) for row in topology[connected]]
    selected = {name: np.isin(connected, [connected[addresses.index(tuple(edge))] for edge in edges])
                for name, edges in cfg['variants'].items()}
    fields = (*losses.TRACE, *(f'pressure_node_{i}' for i in range(len(nodes))),
              *(f'flow_branch_{i}' for i in range(len(topology))))
    return model, indices, selected, fields


def analyze(study, archive, out):
    cfg = study['measurement']
    archived = READ(archive['summary.json'])
    baseline_hashes = READ(out / 'trace-hashes.json')
    model, indices, selected, fields = measurement_model(cfg, archive, archived)
    connected = model[6]
    initial = READ(archive['initial-summary.json'])
    failures = sorted(key for key, ok in initial['checks'].items() if not ok)
    checks = {
        'dc_control_is_registered': READ(out / 'dc.json') == dc_case(study, archive),
        'initial_dc_judgment_retained': failures == study['initial_dc_comparison']['failed_checks'],
        'raw_observations_match_first_capture': sha256(out / 'tangent-observations.npz') == sha256(archive['initial-traces.npz']),
    }
    result, dc = {}, {}
    early_n = cfg['early_window_samples'][1] - cfg['early_window_samples'][0]
    with (
        np.load(out / 'tangent-observations.npz', allow_pickle=False) as traces,
        np.load(archive['artifacts/branch-states.npz'], allow_pickle=False) as base,
    ):
        for edition in EDITIONS:
            original = traces[f'dc_baseline_{edition}']
            trial = traces[f'dc_three_branches_{edition}']
            dc[edition] = dc_stationarity(cfg, fields, original, trial)
            checks[f'dc/{edition}/stationary_at_the_tangent_point'] = (
                dc[edition]['relative_error_at_stationary_scales'] < cfg['dc_stationarity_peak_relative_error_lt'])
            checks[f'dc/{edition}/initial_normalization_reproduced'] = (
                peak_error(trial, original) == initial['dc_peak_relative_errors'][edition])
        for arm in ARMS:
            result[arm] = {}
            source_case = READ(archive[f'artifacts/{arm}.json'])
            stimulus = np.array([float(x) for x in source_case['fixed_airway_periodic_flow']['flow_cm3_s']])
            checks[f'{arm}/registered_clock_and_flow'] = (
                cfg['reference_flow_cm3_s'] == source_case['fixed_airway']['steady_flow_cm3_s']
                and cfg['activation_sample'] == source_case['fixed_airway_periodic_flow']['start_sample']
                and cfg['activation_sample'] - 1 == cfg['early_window_samples'][0]
                and cfg['steady_window_samples'][1] - cfg['steady_window_samples'][0] == len(stimulus))
            baselines, peaks = {}, {}
            for edition in EDITIONS:
                saved = base[f'{arm}_{edition}']
                name = f'{arm}_baseline_{edition}'
                checks[f'{arm}/{edition}/pristine_baseline_reproduced'] = (
                    baseline_hashes[name] == losses.MEAN.sha_array(saved))
                aligned = saved[:, indices] if edition == 'candidate' else saved
                baselines[edition] = state_response(cfg, aligned, stimulus, model, selected['baseline'])
                peaks[edition] = abs(saved).max(axis=0)
            for variant in VARIANTS[1:]:
                prefix = f'{arm}/{variant}'
                result[arm][variant] = {}
                raw = {edition: traces[f'{arm}_{variant}_{edition}'] for edition in EDITIONS}
                comparison = peak_error(raw['candidate'][:, indices], raw['upstream'])
                checks[f'{prefix}/matches_upstream_series'] = comparison < cfg['series_peak_relative_error_lt']
                selection = selected[variant]
                ref = {freq: [row for row in archived['branch_contributions']
                              if row['arm'] == arm and row['frequency_hz'] == freq and row['branch'] in connected[selection]]
                       for freq in cfg['frequencies_hz']}
                for edition in EDITIONS:
                    key = f'{prefix}/{edition}'
                    prelude = traces[f'{arm}_baseline_{edition}']
                    trial = raw[edition][early_n:]
                    aligned = trial[:, indices] if edition == 'candidate' else trial
                    intervention = state_response(cfg, aligned, stimulus, model, selection)
                    checks[f'{key}/selected_and_remaining_pressure_laws'] = intervention[2] < cfg['branch_pressure_law_peak_relative_error_lt']
                    first = first_response(cfg, prelude, raw[edition][:early_n], peaks[edition], fields)
                    checks[f'{key}/unchanged_before_activation'] = np.array_equal(prelude[0], raw[edition][0])
                    checks[f'{key}/early_response_observed'] = first is not None and first['sample'] >= cfg['activation_sample']
                    rows = complex_rows(cfg, baselines[edition], intervention, selection, ref)
                    checks[f'{key}/previous_branch_predictions_reproduced'] = all(
                        row['archived_prediction_relative_error'] < cfg['archived_contribution_relative_error_lt'] for row in rows)
                    checks[f'{key}/reconstructed_complex_changes'] = all(
                        row['relative_reconstruction_error'] < cfg['complex_change_reconstruction_error_lt'] for row in rows)
                    result[arm][variant][edition] = {'frequencies': rows, 'first_response': first,
                                                    'pressure_law_peak_relative_error': intervention[2]}
                outcome = result[arm][variant]
                outcome['upstream_series_peak_relative_error'] = comparison
                outcome['prediction_hypothesis'] = all(
                    row['prediction_relative_error'] < cfg['open_loop_prediction_relative_error_hypothesis_lt']
                    for row in outcome['candidate']['frequencies'])
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'dc_changes': dc,
            'initial_failed_checks': failures, 'conditions': result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)

    def measure(out, execute):
        capture(study, archive, out, execute)
        return analyze(study, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *losses.MEAN.shared.candidate_sources(), *CANDIDATE_DATA, PROBE,
              *(Path(module.__file__) for module in (losses, losses.IMPULSE, losses.MEAN, losses.MEAN.shared)),
              UPSTREAM / UPPER, UPSTREAM / 'Cargo.lock', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs']
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return losses.MEAN.shared.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                                input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
