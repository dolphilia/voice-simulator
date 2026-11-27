"""同じ唇閉鎖で声帯の駆動圧差だけを差し替え、流量との因果順を調べる。"""

import argparse
import csv
import difflib
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import lfilter

import measure_articulation as artic
import measure_glottal_coupling as source
import measure_lip_crossing_thickness as saved_run
import measure_lip_tuck_radiation as voice
import measure_uniform_tube as shared
import measure_voiced_vowel_motion as voiced
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/glottal-pressure-feedback.json'
UPPER_VOICE = 'crates/chimera/src/voice/human_voice.rs'
PRESSURE_COLUMNS = ('glottal_physical_pressure_dyn_cm2', 'glottal_input_pressure_dyn_cm2',
                    'glottal_filtered_pressure_dyn_cm2', 'glottal_effort',
                    'glottal_abduction_cm2', 'glottal_closure_command')
PATCHES = (
    ('    pub glottis: crate::sources::glottis::ParametricGlottis,\n',
     '    pub research_glottal_pressure: Option<(usize, Vec<f64>)>,\n'
     '    pub research_glottal_pressure_trace: Option<Vec<[f64; 2]>>,\n'),
    ('            glottis: crate::sources::glottis::ParametricGlottis::new(fs),\n',
     '            research_glottal_pressure: None,\n'
     '            research_glottal_pressure_trace: None,\n'),
)


def build_pressure_reference(revision, artifacts, execute):
    with TemporaryDirectory(prefix='upstream-pressure-', dir=artifacts) as directory:
        scratch = Path(directory)
        archive, code = scratch / 'source.tar', scratch / 'code'
        code.mkdir()
        execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(code)])
        path = code / UPPER_VOICE
        before = path.read_text()
        after = before
        for anchor, addition in PATCHES:
            if after.count(anchor) != 1:
                raise ValueError('固定上流の声門の構造体または初期化位置が一意ではありません')
            after = after.replace(anchor, anchor + addition)
        anchor = '                let a = self.glottis.next(net.p[sub_node] - net.p[supra]);\n'
        if after.count(anchor) != 1:
            raise ValueError('固定上流で声門の圧差入力箇所が一意ではありません')
        after = after.replace(anchor, """                let physical_dp = net.p[sub_node] - net.p[supra];
                let input_dp = if let Some(trace) = &mut self.research_glottal_pressure_trace {
                    let input = self.research_glottal_pressure.as_ref()
                        .and_then(|(start, samples)| trace.len().checked_sub(*start)
                            .and_then(|offset| samples.get(offset)))
                        .copied().unwrap_or(physical_dp);
                    trace.push([physical_dp, input]);
                    input
                } else {
                    physical_dp
                };
                let a = self.glottis.next(input_dp);
""")
        patch = difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                     fromfile=f'a/{UPPER_VOICE}', tofile=f'b/{UPPER_VOICE}')
        (artifacts / 'upstream-glottal-pressure.patch').write_text(''.join(patch))
        path.write_text(after)
        return shared.build_upstream_probe(artic.PROBE, artifacts, execute, upstream=code,
                                           rustc_args=('--cfg', 'research_glottal_pressure'))


def run_arm(tag, base, plan, executable, folder, config, execute, candidate_input=None, upper_input=None):
    cfg = config['measurement']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    factor, period = fs // rate, base['articulators']['control_block_samples']
    indices = np.arange(base['measurement']['frames'] * period)
    selected = indices[factor - 1::factor]
    folder.mkdir()
    path = folder / 'case.json'
    case = {**base, 'id': f"{config['id']}-{tag}", 'measurement': {**base['measurement'], 'glottal_pressure': True}}
    start = config['start_sample']
    if candidate_input is not None:
        case['glottal_pressure_override'] = {'start_sample': start,
                                             'values_dyn_cm2': list(map(repr, candidate_input.tolist()))}
    voice.write_json(path, case)
    cells = case['measurement']['voiced_tract_oral_cells']
    blocks = cfg['host_block_frames'] if candidate_input is not None else cfg['host_block_frames'][:1]
    result = voice.capture_candidate(path, folder, blocks, indices, period, cells, execute,
                                     extra_columns=PRESSURE_COLUMNS)
    native, wave, actual_rate, output, settings, same_blocks = result

    upper_path = folder / 'upstream-pressure.csv'
    environment = [f'CHIMERA_RESEARCH_PRESSURE_TRACE={upper_path}']
    if upper_input is not None:
        pressure_path = folder / 'upstream-drive.txt'
        pressure_path.write_text(f'{start}\n' + ''.join(f'{value!r}\n' for value in upper_input.tolist()))
        environment.append(f'CHIMERA_RESEARCH_PRESSURE_INPUT={pressure_path}')

    def run_upper(command, **options):
        execute(['env', *environment, *command], **options)

    upper, upper_wave, _ = voice.capture_upstream(executable, case, plan, 'upstream', folder, blocks[0],
                                                 selected, period, cells, run_upper)
    header, samples = shared.read_trace(upper_path, len(indices), 3)
    if header != ['internal_sample', *PRESSURE_COLUMNS[:2]]:
        raise ValueError('固定上流で声門に渡した圧差を照合できません')
    if (actual_rate != rate or wave.dtype != np.float32 or upper_wave.dtype != np.float32
            or wave.shape != selected.shape or upper_wave.shape != selected.shape
            or not np.isfinite(wave).all() or not np.isfinite(upper_wave).all()):
        raise ValueError('PCMのフレーム数、型、レートを照合できません')
    pressure = dict(zip(PRESSURE_COLUMNS[:2], samples[:, 1:].T, strict=True))
    common = {name: series[selected] for name, series in native.items() if name not in PRESSURE_COLUMNS}
    upper_compare = voice.compare_samples(common, upper, {
        'geometry_absolute_lt': cfg['reference_geometry_abs_lt'],
        'component_peak_relative_error_lt': cfg['reference_states_peak_relative_lt']})
    compared_pcm = voiced.compare(wave, upper_wave, cfg['reference_pcm_abs_lt'])
    out_compare = voiced.independently_render(native, output, wave, rate, factor, case['voice']['output_gain'],
                                               settings, {'pcm_absolute_lt': cfg['reference_pcm_abs_lt'],
                                                          'output_state_peak_relative_error_lt': cfg['independent_source_peak_relative_lt']})
    pressure_compare = {field: shared.compare_series(native[field], pressure[field], cfg['reference_states_peak_relative_lt'])
                        for field in pressure}
    for file in [folder / f'{name}-samples.csv' for name in ('candidate', 'upstream')] + [upper_path]:
        saved_run.compress(file)
    check = {
        'native_and_reference': upper_compare['first_over_tolerance'] is None and compared_pcm['status']
            and all(value['status'] for value in pressure_compare.values()),
        'host_partitions_and_independent_pcm': same_blocks and all(value['status'] for value in out_compare.values()),
    }
    detail = {'state_comparison': upper_compare, 'pressure_comparison': pressure_compare,
              'pcm_comparison': compared_pcm, 'output_comparison': out_compare}
    return native, upper, pressure, wave, upper_wave, check, detail


def slit_case(baseline, fs):
    with (baseline / 'targets.csv').open(newline='') as series:
        pharynx = [row for row in csv.DictReader(series) if row['tube'] == 'pharynx']
    count = len({int(row['cell']) for row in pharynx})
    entrance = {(float(row['area_cm2']), float(row['simulation_length_cm']) / count)
                for row in pharynx if row['cell'] == '0'}
    if len(entrance) != 1:
        raise ValueError('この声門の対照では咽頭入口の形状を一定にしてください')
    area, width = entrance.pop()
    return {
        'network': {'sample_rate_hz': fs, 'tubes': [
            {'length_cm': 12 / 13, 'areas_cm2': [2.5]}, {'length_cm': width, 'areas_cm2': [area]}],
            'ports': [{'nodes': [0, 1], 'length_cm': 0.3, 'slit_width_cm': 1.4,
                       'entrance_loss': 0.37, 'expansion_loss': 1.0}]},
        'glottis': {'port': [0, 1]},
    }


def independent_source(base, track, slit, tolerance, radiation_tolerance):
    fs = base['articulators']['sample_rate_hz']
    settings = base['voice']
    breathiness, tension = settings['breathiness'], settings['tension']
    effort = np.clip((abs(settings['pressure_cm_h2o'] * track['gate']) - 2.2) / 10, 0, 1)
    abduction = 0.1 * breathiness**2
    inputs = {
        'network': {'sample_rate_hz': fs},
        'glottis': {
            'abduction_steps': [(0, abduction)],
            'params': {'f0_hz': settings['f0_hz'], 'amplitude_cm2': .17, 'chink_cm2': .008 + .03 * breathiness,
                       'open_quotient': .78 - .36 * tension, 'open_with_abduction': .98, 'skew': .56 + .16 * tension,
                       'closure_sharpness': .4 * tension + 1.375 * max(0, tension - .6),
                       'threshold_dyn_cm2': 2.5 * 980.665, 'closure': 0.0}
        },
    }
    physical = source.earlier(track['pressure_sub_dyn_cm2'] - track['pressure_supra_dyn_cm2'])
    drive = track[PRESSURE_COLUMNS[1]]
    pole = np.exp(-2 * np.pi * 30 / fs)
    filtered = lfilter([1 - pole], [1, -pole], drive)
    area, gate, phase = source.reconstruct_source(inputs, drive, effort)
    checks = {name: shared.compare_series(native, reference, tolerance) for name, native, reference in (
        ('physical_pressure', track[PRESSURE_COLUMNS[0]], physical),
        ('filtered_pressure', track[PRESSURE_COLUMNS[2]], filtered),
        ('glottal_effort', track['glottal_effort'], effort),
        ('glottal_abduction', track['glottal_abduction_cm2'], np.full(len(physical), abduction)),
        ('area', track['glottal_area_cm2'], area),
        ('voicing', track['glottal_voicing'], gate),
        ('phase', np.exp(2j * np.pi * track['glottal_phase']), np.exp(2j * np.pi * phase)),
    )}
    radiation = track['wall_radiation_cm3_s'] + track['lip_flow_cm3_s'] + track['nose_flow_cm3_s']
    checks['radiation_from_flows'] = voiced.compare(track['radiation_derivative_cm3_s2'],
                                                   np.diff(radiation, prepend=0.0) * fs, radiation_tolerance)
    if not np.all(track['pharynx_dx_cm'] == slit['network']['tubes'][1]['length_cm']):
        raise ValueError('咽頭入口のセル長が運動量の独立計算と一致しません')
    balance, open_port = source.pressure_from_slit_flow(slit, track['glottal_area_cm2'],
                                                     track['glottal_flow_cm3_s'])
    checks['slit_momentum_from_physical_pressure'] = shared.compare_series(balance, physical[open_port], tolerance)
    measured = {'open_glottis_samples': int(open_port.sum()),
                'max_difference_from_glottal_input_pressure_dyn_cm2': float(abs(balance - drive[open_port]).max())}
    return checks, measured


def bounds(window, rate):
    return slice(*(round(t * rate / 1000) for t in window))


def window_stats(track, pcm, window, fs, rate):
    selection = bounds(window, fs)
    output = bounds(window, rate)
    rows = {name: track[name][selection] for name in (*PRESSURE_COLUMNS[:3], 'glottal_voicing',
                 'glottal_area_cm2', 'glottal_flow_cm3_s', 'lip_flow_cm3_s', 'radiation_derivative_cm3_s2')}
    rows['pcm'] = pcm[output].astype(float)
    return {name: {'mean': float(np.mean(data)), 'rms_ac': source.rms_ac(data),
                   'peak': float(abs(data).max())} for name, data in rows.items()}


def identical(a, b, end=None):
    return a.keys() == b.keys() and all(np.array_equal(x[:end].view('u8'), b[k][:end].view('u8')) for k, x in a.items())


def compare_arms(config, arm_data, fixed_pressure, baseline, artifacts):
    cfg = config['measurement']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    start, factor = config['start_sample'], fs // rate
    normal, fixed, replay = (arm_data[key] for key in ('normal', 'fixed', 'replay'))
    stats = {tag: {name: window_stats(track, pcm, cfg[name + '_ms'], fs, rate)
                   for name in ('open_reference', 'closed', 'reopening')}
             for tag, (track, _, _, pcm, *_) in arm_data.items()}
    left, right = normal[0], fixed[0]
    first = {field: voice.onset_difference(right[field] - left[field], limit)
             for field, limit in cfg['detection_floors'].items()}
    first['pcm'] = voice.onset_difference(fixed[3].astype(float) - normal[3], cfg['pcm_detection_floor'])
    core_fields = (*voiced.GEOMETRY, *voiced.ARTICULATION, 'labiodental', 'glottal_effort',
                   'glottal_abduction_cm2', 'glottal_closure_command', 'glottal_f0_hz', 'glottal_phase')
    a, b = [stats[label]['closed'] for label in ('normal', 'fixed')]
    def ratio(tag, field, metric):
        return stats[tag]['closed'][field][metric] / stats[tag]['open_reference'][field][metric]

    geometry_mask = left['lip_minimum_cm2'] < cfg['network_closed_lt_cm2']
    closed = bounds(cfg['closed_ms'], fs)
    source_sequence = [first[field] for field in ('glottal_input_pressure_dyn_cm2',
                       'glottal_filtered_pressure_dyn_cm2', 'glottal_voicing', 'glottal_area_cm2',
                       'glottal_flow_cm3_s', 'glottal_physical_pressure_dyn_cm2')]
    block = cfg['host_block_frames'][0]
    normal_file = artifacts / 'normal' / f'block-{block}.wav'
    upper_file = artifacts / 'normal/upstream.f32'
    only_network = PRESSURE_COLUMNS[:2]
    checks = {
        'ordinary_wave_matches_saved_run': sha256(normal_file) == sha256(baseline / f'block-{block}.wav')
            and sha256(upper_file) == sha256(baseline / 'upstream.f32'),
        'identical_before_intervention': identical(left, right, start)
            and np.array_equal(normal[3][:start // factor].view('u4'), fixed[3][:start // factor].view('u4'))
            and identical(normal[2], fixed[2], start),
        'replay_bitwise_same_as_normal': identical(normal[0], replay[0]) and identical(normal[1], replay[1])
            and identical(normal[2], replay[2]) and np.array_equal(normal[3].view('u4'), replay[3].view('u4'))
            and np.array_equal(normal[4].view('u4'), replay[4].view('u4')),
        'only_drive_pressure_is_substituted': all(np.array_equal(value[only_network[1]][:start], value[only_network[0]][:start])
                                                and np.all(value[only_network[1]][start:] == fixed_pressure)
                                                for value in (right, fixed[2])),
        'same_geometry_and_source_controls': all(np.array_equal(left[key], right[key]) for key in core_fields)
            and bool(geometry_mask[closed].all()) and int(np.flatnonzero(geometry_mask)[0]) == start,
        'continued_voicing_and_area_when_pressure_fixed': a['glottal_voicing']['mean'] < cfg['original_closed_voicing_lt']
            and b['glottal_voicing']['mean'] > cfg['fixed_closed_voicing_gt']
            and ratio('normal', 'glottal_area_cm2', 'rms_ac') < cfg['original_area_ac_over_open_lt']
            and ratio('fixed', 'glottal_area_cm2', 'rms_ac') > cfg['fixed_area_ac_over_open_gt'],
        'flow_still_reduced_during_closure': abs(ratio('fixed', 'glottal_flow_cm3_s', 'mean'))
            < cfg['fixed_closed_flow_mean_over_open_lt'] and all(
            row['lip_flow_cm3_s']['peak'] < cfg['closed_lip_flow_peak_lt_cm3_s'] for row in (a, b)),
        'changes_propagate_from_glottal_model': source_sequence[0] == start
            and all(value is not None for value in source_sequence)
            and source_sequence == sorted(source_sequence)
            and first['radiation_derivative_cm3_s2'] is not None and first['pcm'] is not None,
    }
    return checks, stats, first


def measure(config, baseline, artifacts, execute):
    cfg = config['measurement']
    base = saved_run.read(baseline / 'case.json')
    if base['area_control']['oral_cells'] != config['oral_cells']:
        raise ValueError('実行の口腔格子をケースに照合できません')
    for suite in ('lung_port', 'voice_source'):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite],
                cwd=UPSTREAM, stdout=artifacts / f'upstream-{suite}-tests.log')
    executable = build_pressure_reference(config['upstream_revision'], artifacts, execute)
    plan = artifacts / 'upstream-events.txt'
    artic.write_upstream_events(base, plan)
    arm_data = {}
    run = lambda tag, **args: run_arm(tag, base, plan, executable, artifacts / tag, config, execute, **args)
    arm_data['normal'] = run('normal')
    normal, _, reference = arm_data['normal'][:3]
    index = config['start_sample']
    field = PRESSURE_COLUMNS[0]
    constant = float(np.mean(normal[field][bounds(cfg['open_reference_ms'], cfg['internal_rate_hz'])]))
    fixed = np.full(len(normal[field]) - index, constant)
    arm_data['fixed'] = run('fixed', candidate_input=fixed, upper_input=fixed)
    arm_data['replay'] = run('replay', candidate_input=normal[field][index:], upper_input=reference[field][index:])
    checks, measurements, first = compare_arms(config, arm_data, constant, baseline, artifacts)
    arm_summary = {}
    slit = slit_case(baseline, cfg['internal_rate_hz'])
    for tag, (track, _, _, _, _, verdict, detail) in arm_data.items():
        independent, momentum = independent_source(base, track, slit, cfg['independent_source_peak_relative_lt'],
                                                   cfg['radiation_derivative_abs_lt'])
        checks.update({f'{tag}/{key}': value for key, value in verdict.items()})
        checks[f'{tag}/independent_pressure_and_source'] = all(item['status'] for item in independent.values())
        arm_summary[tag] = {**detail, 'independent': independent, 'momentum': momentum}
    return {'checks': {key: bool(value) for key, value in checks.items()},
            'fixed_pressure_dyn_cm2': constant, 'start_sample': index, 'arms': arm_summary,
            'window_metrics': measurements, 'first_fixed_vs_normal_over_threshold': first}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = saved_run.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    selected = f"artifacts/oral-{config['oral_cells']}"
    root, paths = saved_run.saved({'baseline': config['trajectory_reference_run']},
                                 ['summary.json', *(f'{selected}/{file}' for file in
                                                    ('case.json', 'block-128.wav', 'upstream.f32', 'targets.csv'))],
                                 revision)
    closure = saved_run.read(root / 'summary.json')['grids'][str(config['oral_cells'])]['acoustic_samples']['close']
    if closure != config['start_sample']:
        parser.error('介入の開始位置は以前の閉鎖位置と一致しません')
    inputs = [CASE, Path(__file__).resolve(), *paths, artic.PROBE, *shared.candidate_sources(),
              *(Path(module.__file__) for module in (artic, source, saved_run, voice, shared, voiced)),
              *(UPSTREAM / file for file in (UPPER_VOICE, 'crates/chimera/src/sources/glottis.rs',
                    'crates/chimera/tests/voice_source.rs', 'crates/chimera/tests/lung_port.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda artifacts, execute: measure(config, root / selected, artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
