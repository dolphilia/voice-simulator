"""固定 /i/ の口蓋帆の開閉を、通常CLI・Wasm・固定上流で比較する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import firwin

import measure_fixed_vowel_i_radiation_screen as screen
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-radiation.json'
UPPER = WORKSPACE / 'tools/upstream_fixed_i_velum.rs'
HOST = WORKSPACE / 'tools/capture_fixed_i_velum_wasm.ts'
NETWORK = 'crates/chimera/src/airway/network.rs'
VOICE = 'crates/chimera/src/voice/human_voice.rs'
READ = screen.READ
coupled = screen.prior.cli.coupled
wasm = screen.prior.wasm
radiation = screen.prior.cli.radiation
RAD = screen.FIELDS
PORT = ('velum_area_cm2', 'velum_flow_cm3_s', 'velum_pharynx_pressure_dyn_cm2', 'velum_nasal_pressure_dyn_cm2')
GLOTTIS = ('pressure_sub_dyn_cm2', 'pressure_supra_dyn_cm2', 'glottal_area_cm2', 'glottal_flow_cm3_s')
FIELDS = (*GLOTTIS, *RAD, *PORT)
LABELS = ('closed', 'open')
EVIDENCE = ('upper-network.patch', 'upper-voice.patch', 'upper-columns.json', 'vocal_wasm.wasm',
            *(f'{label}-{name}' for label in LABELS for name in (
                'internal.json', 'frame.json', 'reference.json', 'inspect.json', 'reference-inspect.json',
                'internal.csv', 'frame.csv', 'reference.csv', 'pcm.wav', 'reference.wav',
                'upper.f32', 'upper.f64', 'upper-plain.f32', 'wasm.json',
                *(f'wasm-{block}.{ext}' for block in (128, 77) for ext in ('f32', 'f64')))))


def archive_inputs(case):
    info = case['measurement']['screen_reference']
    record, manifest, definition = coupled.smoothing.verified_reference(info, case['upstream_revision'])
    return {**screen.archive_inputs(READ(definition)), 'screen-manifest.json': manifest, 'screen-case.json': definition,
            **{f'closed-{name}': coupled.verified_path(record, f'artifacts/{name}')
               for name in ('native-internal.csv', 'native-frame.csv', 'native-pcm.wav')}}


def build_upstream(case, out, scratch, execute, *, port_override=False, network_trace=False):
    code = scratch / 'upstream'
    code.mkdir()
    tar = scratch / 'upstream.tar'
    execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
    execute(['tar', '-xf', str(tar), '-C', str(code)])
    patch = coupled.PATCH(code, NETWORK, (
        ('    rad_prev_total: f64,', '    rad_prev_total: f64,\n    pub research_wall_radiation: f64,'),
        ('            rad_prev_total: 0.0,', '            rad_prev_total: 0.0,\n            research_wall_radiation: 0.0,'),
        ('        let mut rad_total = wall_rad_sum;', '        self.research_wall_radiation = wall_rad_sum;\n'
         '        let mut rad_total = wall_rad_sum;'),
        ('    pub fn radiated_flow(&self, r: usize) -> f64 {', '''    pub fn research_radiation_total(&self) -> f64 {
        self.rad_prev_total
    }

    pub fn research_port_area(&self, port: usize) -> f64 {
        self.port_area[port]
    }

    pub fn radiated_flow(&self, r: usize) -> f64 {'''),
    ))
    (out / 'upper-network.patch').write_text(patch)
    marker = '    pub glottis: crate::sources::glottis::ParametricGlottis,'
    init = '            glottis: crate::sources::glottis::ParametricGlottis::new(fs),'
    step = '                let y = net.step();'
    port_field = '\n    pub research_velum_area_override: Option<f64>,' if port_override else ''
    port_init = '\n            research_velum_area_override: None,' if port_override else ''
    begin = '        self.airway.net.begin_block(self.ctrl_every);'
    control_edit = ((begin, '''        if let Some(area) = self.research_velum_area_override {
            self.airway.net.set_port_target(self.airway.velum_port, area);
        }
''' + begin),) if port_override else ()
    network_fields = '''
    pub research_network_trace: Option<(std::ops::Range<usize>, Vec<f64>)>,
    research_network_sample: usize,''' if network_trace else ''
    network_init = '''
            research_network_trace: None,
            research_network_sample: 0,''' if network_trace else ''
    network_step = '''
                if let Some((range, state)) = &mut self.research_network_trace {
                    if range.contains(&self.research_network_sample) {
                        state.extend_from_slice(&net.p[..net.n_nodes]);
                        state.extend_from_slice(&net.u[..net.n_branches]);
                    }
                    self.research_network_sample += 1;
                }
''' if network_trace else ''
    patch = coupled.PATCH(code, VOICE, (
        (marker, marker + f'\n    pub research_velum_radiation: Option<Vec<[f64; {len(FIELDS)}]>>,' + port_field + network_fields),
        (init, init + '\n            research_velum_radiation: None,' + port_init + network_init),
        (step, step + '''
                if let Some(rows) = &mut self.research_velum_radiation {
                    let port = self.airway.velum_port;
                    rows.push([
                        net.p[sub_node], net.p[supra], a, net.u[gp],
                        net.research_wall_radiation, net.radiated_flow(self.airway.rad_lips),
                        net.radiated_flow(self.airway.rad_nose), net.research_radiation_total(), y,
                        net.research_port_area(port), net.u[port],
                        net.p[self.airway.pharynx.last_node()], net.p[self.airway.nasal.first_node()],
                    ]);
                }
''' + network_step),
        *control_edit,
    ))
    (out / 'upper-voice.patch').write_text(patch)
    (out / 'upper-columns.json').write_text(json.dumps(FIELDS) + '\n')
    rustc_args = ('--cfg', 'research_fixed_velum_port') if port_override else ()
    if network_trace:
        rustc_args += ('--cfg', 'research_fixed_network_trace')
    return coupled.SHARED.build_upstream_probe(
        UPPER, out, execute, upstream=code, cargo_args=('--offline',), rustc_args=rustc_args)


def case_inputs(base, cfg, name):
    content = {**base, 'posture': {**base['posture'], 'velum_cm2': cfg[f'{name}_input_cm2']}}
    probe = {'radiation_components': True, 'velum_port': True}
    return {
        'internal': {**content, 'fixed_voice_probe': {**probe, 'internal_trace': True}},
        'frame': {**content, 'fixed_voice_probe': probe},
        'reference': {**content, 'fixed_voice_probe': {'radiation_components': True}},
    }


def capture(case, archive, out, execute):
    cfg = case['measurement']
    base = READ(archive['source.json'])
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    count = cfg['comparison_internal_samples'][1]
    frames = count // (fs // rate)
    blocks = list(map(str, cfg['host_block_frames']))
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-wasm', '--target=wasm32-unknown-unknown'])
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'sound_marks_acoustic',
             'a_nasalized_vowel_is_nasal_and_an_oral_one_is_not'], cwd=UPSTREAM, stdout=out / 'upstream-nasality-test.log')
    with TemporaryDirectory(prefix='velum-upstream-', dir=out.parent) as tmp:
        upper = build_upstream(case, out, Path(tmp), execute)
        for name in LABELS:
            for mode, content in case_inputs(base, cfg, name).items():
                path = out / f'{name}-{mode}.json'
                path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
                execute([*cli, 'render', str(path), str(out / f'{name}-{mode}.csv')])
                if mode != 'internal':
                    target = f'{name}-inspect.json' if mode == 'frame' else f'{name}-reference-inspect.json'
                    execute([*cli, 'inspect', str(path)], stdout=out / target)
            frame = out / f'{name}-frame.json'
            reference = out / f'{name}-reference.json'
            execute([*cli, 'render-pcm', str(frame), str(out / f'{name}-pcm.wav'), '--no-trace', blocks[0]])
            execute([*cli, 'render-pcm', str(reference), str(out / f'{name}-reference.wav'), '--no-trace', blocks[1]])
            execute(['node', '--experimental-transform-types', str(HOST), str(binary), str(frame), str(out), name, *blocks])
            source = tuple(base['voice'][field] for field in (
                'pressure_cm_h2o', 'gate', 'f0_hz', 'breathiness', 'tension', 'output_gain'))
            args = list(map(str, (cfg[f'{name}_input_cm2'], fs, rate, frames, *source)))
            execute([str(upper), *args, str(out / f'{name}-upper'), 'observer'])
            execute([str(upper), *args, str(out / f'{name}-upper-plain'), 'plain'])


def port_residual(geometry, tracks, fs):
    """固定ポートの二次式に測定流量を代入し、圧力単位で残差を取る。"""
    tubes = {tube['name']: tube for tube in geometry['tubes']}
    pharynx = tubes['pharynx']
    a = geometry['sections'][pharynx['first_node'] + pharynx['cells'] - 1]
    b = geometry['sections'][tubes['nasal']['first_node']]
    area = geometry['velum_port_cm2']
    rho, mu, length = 1.14e-3, 1.86e-4, 1.0
    inertance = rho * (length / area + 0.5 * sum(s['cell_length_cm'] / s['area_cm2'] for s in (a, b)))
    resistance = 2 * length * np.sqrt(rho * mu * np.pi**2 * 700) / area**1.5
    contraction = 0.3 * rho / (2 * area**2)
    expansion = [0.8 * rho / 2 * max(0., 1 / area - 1 / s['area_cm2'])**2 for s in (b, a)]
    flow = tracks[PORT[1]]
    pressure = tracks[PORT[2]] - tracks[PORT[3]]
    before = np.roll(pressure, 1)
    before[0] = 0.
    required = (inertance * fs * np.diff(flow, prepend=0.) + resistance * flow
                + (contraction + np.where(flow >= 0., *expansion)) * flow * abs(flow))
    return float(abs(required - before).max() / abs(before).max())


def trace_comparison(case, collection, waves, taps, pole, factor, gain, edition):
    cfg = case['measurement']
    lo, hi = cfg['steady_output_frames']
    steady = slice(lo, hi)
    closed, opened = (collection[name] for name in LABELS)
    early = {key: coupled.first_difference(closed[key], opened[key]) for key in FIELDS}
    difference = np.column_stack([opened[key] - closed[key] for key in RAD[:3]])
    derivative = radiation.derivative(difference, cfg['internal_rate_hz'], edition)
    component = radiation.linear_pcm(derivative, taps, pole, factor, gain)
    total = radiation.linear_pcm(opened[RAD[4]] - closed[RAD[4]], taps, pole, factor, gain)
    error = float(abs(total - component.sum(axis=1)).max())
    steady_total = total[steady]
    projections = (component[steady].T @ steady_total) / np.dot(steady_total, steady_total)
    nose = opened[RAD[2]][factor - 1::factor][steady]
    nose_rms = float(np.sqrt(np.mean(nose**2)))
    pcm_rms = float(np.sqrt(np.mean((waves['open'][steady].astype(float) - waves['closed'][steady])**2)))
    checks = {
        'closed_port_and_nose_flow_zero': not np.any(closed[PORT[1]]) and not np.any(closed[RAD[2]]),
        'open_port_has_steady_nose_flow': nose_rms > cfg['minimum_steady_nose_rms_cm3_s'],
        'nose_follows_velum_and_wall_or_lip': (
            early[PORT[1]] is not None and early[RAD[2]] is not None and early[PORT[1]] < early[RAD[2]]
            and any(early[key] is not None and early[key] < early[RAD[2]] for key in RAD[:2])),
        'steady_pcm_differs_and_components_sum': (
            pcm_rms > cfg['minimum_steady_pcm_delta_rms'] and error < cfg['part_sum_linear_pcm_absolute_error_lt']),
    }
    return checks, {'first_difference_internal_samples': early,
                    'first_pcm_difference_frame': coupled.first_difference(waves['closed'], waves['open']),
                    'nasal_steady_rms_cm3_s': nose_rms, 'pcm_steady_difference_rms': pcm_rms,
                    'component_projections_on_linear_difference': dict(zip(RAD[:3], projections.tolist())),
                    'component_sum_max_absolute_error': error}


def analyze(case, archive, out):
    cfg = case['measurement']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    count = cfg['comparison_internal_samples'][1]
    factor = fs // rate
    frames = count // factor
    end_samples = np.arange(factor - 1, count, factor)
    base = READ(archive['source.json'])
    tools = coupled.pcm
    read_csv = tools.read_columns
    same = coupled.same_bits
    taps = firwin(24 * factor + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    pole = np.exp(-2 * np.pi * 25 / rate)
    gain = base['voice']['output_gain']
    checks = {'scope_and_upper_fields_registered': (
        cfg['comparison_internal_samples'] == [0, base['fixed_airway']['sample_count']]
        and [fs, rate] == [base['fixed_airway']['sample_rate_hz'], base['voice']['output_sample_rate_hz']]
        and cfg['closed_input_cm2'] == base['posture']['velum_cm2']
        and READ(out / 'upper-columns.json') == list(FIELDS))}
    tracks = {name: {} for name in ('candidate', 'upstream')}
    waves = {name: {} for name in tracks}
    comparison = {}
    geometry = {}
    for name in LABELS:
        _, internal = read_csv(out / f'{name}-internal.csv', count)
        header, frame = read_csv(out / f'{name}-frame.csv', frames)
        reference_header, reference = read_csv(out / f'{name}-reference.csv', frames)
        inspect = READ(out / f'{name}-inspect.json')
        unobserved = READ(out / f'{name}-reference-inspect.json')
        geometry[name] = inspect['fixed_airway']
        native = coupled.read_pcm(out / f'{name}-pcm.wav', frames, rate)
        upper = np.fromfile(out / f'{name}-upper.f32', dtype='<f4')
        observed = wasm.read_json(out / f'{name}-wasm.json')
        upper_table = screen.prior.binary_trace(out / f'{name}-upper.f64', count, len(FIELDS))
        upper_trace = {field: upper_table[:, i] for i, field in enumerate(FIELDS)}
        tracks['candidate'][name], tracks['upstream'][name] = internal, upper_trace
        waves['candidate'][name], waves['upstream'][name] = native, upper
        linked = case_inputs(base, cfg, name)
        expected_inspect = {**unobserved, 'case': linked['frame'],
                            'voice': {**unobserved['voice'],
                                      'probe': {**unobserved['voice']['probe'], 'velum_port': True}}}
        checks[f'{name}/cli_observation_opt_in_and_clock'] = (
            all(READ(out / f'{name}-{mode}.json') == content for mode, content in linked.items())
            and tuple(header) == (*reference_header, *PORT) and not set(PORT).intersection(reference_header)
            and unobserved['case'] == linked['reference'] and 'velum_port' not in unobserved['voice']['probe']
            and inspect == expected_inspect
            and np.array_equal(frame['internal_sample'], end_samples)
            and np.array_equal(internal['internal_sample'], np.arange(count))
            and all(same(frame[key], internal[key][end_samples]) for key in header if key != 'frame')
            and all(same(frame[key], reference[key]) for key in reference_header)
            and same(native, coupled.read_pcm(out / f'{name}-reference.wav', frames, rate)))
        mat = np.column_stack([frame[key] for key in RAD])
        checks[f'{name}/wasm_bitwise_with_two_partitions'] = (
            observed['fields'] == list(RAD) and observed['results'] == [
                {'block': block, 'stable': True, 'outputFrames': frames} for block in cfg['host_block_frames']]
            and all(same(mat, screen.prior.binary_trace(out / f'{name}-wasm-{block}.f64', frames, len(RAD)))
                    and same(native, np.fromfile(out / f'{name}-wasm-{block}.f32', dtype='<f4'))
                    for block in cfg['host_block_frames']))
        checks[f'{name}/upper_observation_keeps_pcm'] = (
            same(upper, np.fromfile(out / f'{name}-upper-plain.f32', dtype='<f4')))
        area = max(0., cfg[f'{name}_input_cm2'])
        checks[f'{name}/registered_velum_area'] = (
            geometry[name]['velum_port_cm2'] == area
            and np.all(internal[PORT[0]] == area) and np.all(upper_trace[PORT[0]] == area))
        for edition in tracks:
            series = tracks[edition][name]
            total = (series[RAD[0]] + series[RAD[1]]) + series[RAD[2]]
            derivative = radiation.derivative(total, fs, edition)
            prelimit = radiation.linear_pcm(derivative, taps, pole, factor, gain)
            derived = tools.independent_limiter(prelimit, rate)[2]
            checks[f'{edition}/{name}/independent_sum_derivative_and_pcm'] = (
                same(total, series[RAD[3]]) and same(derivative, series[RAD[4]])
                and same(derived, waves[edition][name]))
        series = wasm.compare_states(np.column_stack([internal[key] for key in FIELDS]), upper_table,
                                     FIELDS, np.arange(count), cfg['upstream_series_peak_relative_error_lt'])
        pcm = wasm.compare_pcm(native, upper, cfg['upstream_pcm_absolute_error_lt'])
        comparison[name] = {'series': series, 'pcm': pcm}
        checks[f'{name}/fixed_upstream_tolerances'] = (
            all(item['status'] for item in series.values())
            and pcm['maximum_absolute_error'] < cfg['upstream_pcm_absolute_error_lt'])
    old_native = coupled.read_pcm(archive['closed-native-pcm.wav'], frames, rate)
    old_trace = read_csv(archive['closed-native-internal.csv'], count)[1]
    old_upper = np.fromfile(archive['upstream-voice.f32'], dtype='<f4')
    old_upper_trace = read_csv(archive['upstream-trace.csv'], frames)[1]
    checks['closed_reproduces_existing_screen_and_upper'] = (
        same(old_native, waves['candidate']['closed']) and same(old_upper, waves['upstream']['closed'])
        and all(same(old_trace[key], tracks['candidate']['closed'][key]) for key in (*GLOTTIS, *RAD))
        and all(np.array_equal(old_upper_trace[key], tracks['upstream']['closed'][key][end_samples])
                for key in (*GLOTTIS, RAD[1], RAD[2], RAD[4])))
    oral_changed = [a['node'] for a, b in zip(geometry['closed']['sections'], geometry['open']['sections'], strict=True)
                    if a['area_cm2'] != b['area_cm2']]
    checks['velum_pose_also_changes_supraglottal_geometry'] = bool(oral_changed)
    residual = {edition: port_residual(geometry['open'], state['open'], fs) for edition, state in tracks.items()}
    checks['independent_open_port_pressure_balance'] = all(
        value < cfg['independent_port_residual_relative_lt'] for value in residual.values())
    contrast = {}
    for edition, state in tracks.items():
        conditions, contrast[edition] = trace_comparison(case, state, waves[edition], taps, pole, factor, gain, edition)
        checks.update({f'{edition}/{name}': value for name, value in conditions.items()})
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'internal_samples': count, 'frames': frames,
            'wasm_sha256': sha256(out / 'vocal_wasm.wasm'), 'changed_section_nodes': oral_changed,
            'fixed_upstream_comparisons': comparison, 'port_balance_peak_relative_residual': residual,
            'contrast': contrast}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(case)
    source = WORKSPACE / 'cases' / case['fixed_voice_case']
    if sha256(source) != sha256(archive['source.json']):
        parser.error('現在の固定発声ケースが保存済み基準と一致しません')

    def measure(out, execute):
        capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, source, Path(__file__), HOST, UPPER, *archive.values(), *coupled.SHARED.candidate_sources(),
              WORKSPACE / 'crates/vocal-wasm/host/fixed-voice.ts',
              *(Path(module.__file__) for module in (screen, wasm, radiation, coupled, coupled.pcm, coupled.fixed_lf)),
              *(UPSTREAM / name for name in (NETWORK, VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/sound_marks_acoustic.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return coupled.SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
