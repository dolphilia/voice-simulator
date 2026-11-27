"""口腔セル数だけを変え、同じ唇の閉鎖を形状・圧力・放射で比較する。"""

import argparse
import difflib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_articulation as artic
import measure_grid as grid
import measure_lip_crossing_thickness as prior
import measure_lip_tuck_radiation as voice
import measure_resample as resample
import measure_sagittal as sagittal
import measure_tract_control as tract
import measure_uniform_tube as shared
import measure_voiced_vowel_motion as voiced
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tract-grid-lip-closure.json'
UPPER_GEOMETRY = 'crates/chimera/src/voice/human_airway.rs'
ORAL_ENV = 'CHIMERA_GRID_EXPERIMENT_ORAL_CELLS'


def override_probe(revision, artifacts, execute):
    """固定版の一時展開へ、口腔のセル数を指定できる差分だけを適用する。"""
    with TemporaryDirectory(prefix='upstream-grid-', dir=artifacts) as directory:
        scratch = Path(directory)
        archive, source = scratch / 'upstream.tar', scratch / 'code'
        source.mkdir()
        execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(source)])
        path = source / UPPER_GEOMETRY
        start = path.read_text()
        line = '        let n_or = (8.0f64).max((or_min_len / dx_min).floor()) as usize;\n'
        if start.count(line) != 1 or start != (UPSTREAM / UPPER_GEOMETRY).read_text():
            raise ValueError('上流の固定版で口腔セルの初期化を一意に確認できません')
        replacement = (line + f'        let n_or = std::env::var("{ORAL_ENV}").ok()\n'
                       '            .map_or(n_or, |value| value.parse::<usize>().unwrap());\n')
        end = start.replace(line, replacement)
        delta = difflib.unified_diff(start.splitlines(keepends=True), end.splitlines(keepends=True),
                                     fromfile=f'a/{UPPER_GEOMETRY}', tofile=f'b/{UPPER_GEOMETRY}')
        (artifacts / 'upstream-oral-count.patch').write_text(''.join(delta))
        path.write_text(end)
        return shared.build_upstream_probe(artic.PROBE, artifacts, execute, upstream=source)


def variant_case(registered, base, cells):
    lead = registered['preroll_control_frames']
    clock = base['articulators']
    events = [{**item, 'frame': item['frame'] + lead} for item in clock['events']]
    return {**base, 'id': f"{registered['id']}-{cells}",
            'articulators': {**clock, 'events': events},
            'area_control': {'project_contacts': True, 'oral_cells': cells},
            'voice': registered['voice'], 'measurement': {'frames': base['measurement']['frames'] + lead,
                                                        'voiced_tract_oral_cells': [cells - 1]}}


def output_windows(track, wave, rate, factor, start, edges, windows):
    rows = []
    for lo_ms, hi_ms in windows:
        lo, hi = (start + round(value * rate / 1000) for value in (lo_ms, hi_ms))
        if not 0 <= lo < hi <= len(wave):
            raise ValueError('観測区間がPCM出力の範囲外です')
        selected = wave[lo:hi].astype(float)
        internal = slice(lo * factor, hi * factor)
        band = voice.band_rms(selected, rate, edges)
        rows.append({'offset_window_ms': [lo_ms, hi_ms], 'output_frames': [lo, hi],
                     'supra_peak_dyn_cm2': float(abs(track['pressure_supra_dyn_cm2'][internal]).max()),
                     'lip_peak_dyn_cm2': float(abs(track['lip_pressure_dyn_cm2'][internal]).max()),
                     'lip_flow_peak_cm3_s': float(abs(track['lip_flow_cm3_s'][internal]).max()),
                     'radiation_peak_cm3_s2': float(abs(track['radiation_derivative_cm3_s2'][internal]).max()),
                     'pcm_rms': float(np.sqrt(np.mean(selected**2))),
                     'pcm_peak': float(abs(selected).max()),
                     'pcm_band_rms_dbfs': [float(20 * np.log10(max(x, 1e-12))) for x in band]})
    return rows


def closure(mask, start, release):
    before = np.flatnonzero(mask[start:release])
    after = np.flatnonzero(~mask[release:]) if mask[release] else np.array([], dtype=int)
    first = int(start + before[0]) if before.size else None
    last = int(release + after[0]) if after.size else None
    return {'close': first, 'reopen': last,
            'continuous': bool(first is not None and last is not None and np.all(mask[first:last]))}


def independent_profiles(config, base, position, executable, folder, execute):
    cfg = config['measurement']
    reference = {}
    for frame in cfg['profile_source_frames']:
        target = folder / f'profile-{frame}.csv'
        aperture = base['posture']['lip_aperture_cm'] if frame == -1 else float(position[frame])
        pose = {**base['posture'], 'lip_aperture_cm': aperture}
        args = sagittal.pose_controls({'posture': pose})
        execute([str(executable), '--area', *args], cwd=UPSTREAM, stdout=target)
        reference[frame] = grid.read_grid(target, columns=resample.PROFILE_COLUMNS), pose
    return reference


def check_profiles(config, profiles, cells, geometry, folder):
    settings = config['measurement']
    lead = config['preroll_control_frames']
    rows = {}
    for source_frame, (profile, pose) in profiles.items():
        frame = source_frame + lead if source_frame >= 0 else -1
        observed = geometry[(frame, 'seed' if frame < 0 else 'apply')]
        comparison = {'cells': cells, 'posture': pose,
                      'measurement': {'resample': {'closure_threshold_cm2': settings['closed_geometry_cm2']}}}
        values = resample.estimate_cells(profile, comparison, folder / f'independent-cells-{source_frame}.csv')
        expected = np.concatenate([values[name][0][:, 2:] for name in resample.TUBES])
        rows[str(source_frame)] = {
            'max_error_cm2': float(abs(observed[:, :2] - expected).max()),
            'lip_cell_closed_by_geometry_points_only': bool(cells['oral'] - 1 in values['oral'][1]),
            'lip_midpoint_min_cm2': float(values['oral'][2][-1]),
        }
    return rows


def variant(config, case, profiles, upstream, built_override, folder, execute):
    cfg = config['measurement']
    clock, wave_rate = case['articulators'], config['voice']['output_sample_rate_hz']
    fs, period = clock['sample_rate_hz'], clock['control_block_samples']
    factor = fs // wave_rate
    frames = case['measurement']['frames']
    indices = np.arange(frames * period)
    aligned_indices = indices[factor - 1::factor]
    count = case['area_control']['oral_cells']
    cells = {'pharynx': config['pharynx_cells'], 'oral': count}
    trace_cols = [count - 1]
    block = cfg['host_block_size']
    path, event_path = folder / 'case.json', folder / 'upstream-events.txt'
    voice.write_json(path, case)
    artic.write_upstream_events(case, event_path)
    full, pcm, rate, _, _, _ = voice.capture_candidate(path, folder, [block], indices,
                                                     period, trace_cols, execute)
    aligned = {name: rows[aligned_indices] for name, rows in full.items()}

    def run_upper(command, **options):
        execute(['env', f'{ORAL_ENV}={count}', *command] if built_override else command, **options)

    upper, reference, _ = voice.capture_upstream(upstream, case, event_path, 'upstream', folder, block,
                                               aligned_indices, period, trace_cols, run_upper)
    if rate != wave_rate or pcm.dtype != np.float32 or pcm.shape != reference.shape or len(pcm) != len(aligned_indices):
        raise ValueError('口腔分割のPCM形式が一致しません')
    compare = voice.compare_samples(aligned, upper, {
        'geometry_absolute_lt': cfg['geometry_absolute_lt'], 'component_peak_relative_error_lt': cfg['audio_peak_relative_lt']})
    compared_pcm = voiced.compare(pcm, reference, cfg['pcm_absolute_lt'])

    target, input_path, fixed = [folder / name for name in ('targets.csv', 'targets-case.json', 'upstream-targets.csv')]
    voice.write_json(input_path, {**{k: v for k, v in case.items() if k != 'voice'}, 'measurement': {'frames': frames}})
    execute([*voice.CLI, 'render', str(input_path), str(target)])
    run_upper([str(upstream), str(event_path), 'tract-with-contact'], cwd=UPSTREAM, stdout=fixed)
    geometry, names = tract.read_trace(target, cells, frames)
    before, _ = tract.read_trace(fixed, cells, frames)
    compared_geometry = tract.compare(geometry, before, names, {k: cfg['geometry_absolute_lt'] for k in (
        'length_absolute_lt_cm', 'area_absolute_lt_cm2')})
    expected = tract.independent_trace(geometry, names, period / fs, fs, folder / 'independent-targets.csv')
    profiles_check = check_profiles(config, profiles, cells, geometry, folder)
    ramp = voice.applied_error(geometry, full, trace_cols, period, config['pharynx_cells'], 1)
    has_contact_reapply = any(stage == 'reapply' for _, stage in geometry)
    table = np.stack([geometry[frame, 'apply'] for frame in range(frames)])
    limit = cfg['closed_network_cm2']
    start, release = [event['frame'] for event in clock['events']]
    applied_min = full['lip_minimum_cm2']
    applied_mean = full[f'oral_{count-1}_applied_area_cm2']
    raw = closure(table[:, -1, 1] <= cfg['closed_geometry_cm2'], start, release)
    limited = closure(table[:, -1, 3] < limit, start, release)
    effective = closure(applied_min < limit, start * period, release * period)
    average_only = closure(applied_mean < limit, start * period, release * period)
    if any(event['reopen'] is None for event in (raw, limited, effective, average_only)):
        raise ValueError(f'{count}セルで閉鎖の後の再開口を取得できません')
    # 出力フレームiは、内部のfactor*iからfactor*(i+1)-1までを進めて確定する。
    reopened = effective['reopen'] // factor
    largest_pressure = float(abs(full['pressure_supra_dyn_cm2']).max())
    courant = float((cfg['sound_speed_cm_s'] / fs / full['oral_dx_cm']).max())
    length_correction = float(abs(table[:, :, 4] - table[:, :, 5]).max())
    close = effective['close']
    finite = bool(np.isfinite(pcm).all() and np.isfinite(reference).all())
    checks = {
        'upper_geometry_and_voice': compared_geometry['first_over_tolerance'] is None
            and compare['first_over_tolerance'] is None and compared_pcm['status'],
        'independent_cells_limits_and_applied': not has_contact_reapply
            and max(row['max_error_cm2'] for row in profiles_check.values()) < cfg['geometry_absolute_lt']
            and expected['limited_area_error_cm2'] < cfg['geometry_absolute_lt']
            and max(ramp.values()) < cfg['geometry_absolute_lt'],
        'finite_and_no_courant_length_extension': finite and largest_pressure < cfg['stability_peak_pressure_lt_dyn_cm2']
            and courant <= cfg['maximum_courant'] + 1e-12 and length_correction < cfg['geometry_absolute_lt'],
        'closure_and_average_vs_minimum': all(x['continuous'] for x in (raw, limited, effective, average_only))
            and effective['close'] <= average_only['close'] and effective['reopen'] >= average_only['reopen'],
    }
    summary = {'raw_control_frames': raw, 'limited_control_frames': limited, 'acoustic_samples': effective,
               'if_average_only_samples': average_only, 'acoustic_reopening_output_frame': reopened,
               'min_and_mean_at_acoustic_close_cm2': [float(applied_min[close]), float(applied_mean[close])],
               'start_sample': start * period, 'release_sample': release * period,
               'geometry_to_upper': compared_geometry, 'audio_to_upper': compare, 'pcm_to_upper': compared_pcm,
               'independent_ramp_errors': ramp, 'independent_geometry': profiles_check, 'independent_area_limits': expected,
               'pcm_bitwise_to_upper': bool(np.array_equal(pcm.view('u4'), reference.view('u4'))),
               'supra_pressure_absolute_max_dyn_cm2': largest_pressure, 'maximum_oral_courant': courant,
               'tract_length_correction_cm': length_correction,
               'command_aligned': output_windows(full, pcm, rate, factor, release * period // factor,
                                                 cfg['band_edges_hz'], cfg['command_windows_ms']),
               'reopening_aligned': output_windows(full, pcm, rate, factor, reopened, cfg['band_edges_hz'],
                                                   [cfg['reopen_windows_ms']])[0]}
    for path in folder.glob('*-samples.csv'):
        prior.compress(path)
    return checks, summary, table, full, pcm


def measure(config, case, old, artifacts, execute):
    original, warped, shape = [artifacts / name for name in ('original', 'oral-width', 'profiles')]
    for folder in (original, warped, shape):
        folder.mkdir()
    for suite, name in (('geometry_continuity', 'no_area_jumps_as_the_lower_lip_tucks_for_f'),
                        ('airway_adversarial', 'fast_but_articulator_limited_closure_gives_bounded_piston_pressure')):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite, name],
                cwd=UPSTREAM, stdout=original / f'{suite}.log')
    probe = shared.build_upstream_probe(artic.PROBE, original, execute)
    area_probe = shared.build_upstream_probe(sagittal.PROBE, shape, execute)
    override = override_probe(config['upstream_revision'], warped, execute)
    rate, period = case['articulators']['sample_rate_hz'], case['articulators']['control_block_samples']
    pose = artic.independent_trace(case, period / rate, artifacts / 'independent-articulators.csv')[1]
    position = pose[:, artic.KEYS.index('lip_aperture_cm'), 0]
    profiles = independent_profiles(config, case, position, area_probe, shape, execute)
    count_std = config['default_oral_cells']
    checks, rows, traces, waves = {}, {}, {}, {}
    lead = config['preroll_control_frames']
    for n in config['oral_cells']:
        folder = artifacts / f'oral-{n}'
        folder.mkdir()
        standard = n == count_std
        verdict, summary, table, trace, pcm = variant(
            config, variant_case(config, case, n), profiles, probe if standard else override, not standard, folder, execute)
        checks.update({f'oral_{n}/{key}': bool(value) for key, value in verdict.items()})
        rows[n], traces[n], waves[n] = summary, trace, pcm
        if standard:
            before, _ = tract.read_trace(old, {'pharynx': config['pharynx_cells'], 'oral': n}, case['measurement']['frames'])
            original = np.stack([data for (frame, stage), data in before.items() if stage == 'apply'])
            checks['normal_grid_matches_saved_closure'] = bool(
                abs(original - table[lead:]).max() < config['measurement']['geometry_absolute_lt'])
            unset = variant_case(config, case, n)
            del unset['area_control']['oral_cells']
            unset_path, saved = folder / 'default-case.json', folder / 'default.wav'
            voice.write_json(unset_path, unset)
            execute([*voice.CLI, 'render-pcm', str(unset_path), str(saved), '--no-trace',
                     str(config['measurement']['host_block_size'])])
            checks['default_pcm_with_or_without_explicit_grid'] = shared.sha256(saved) == shared.sha256(
                folder / f"block-{config['measurement']['host_block_size']}.wav")
    diff = {n: {'aperture_to_independent_cm': float(abs(t['lip_aperture_cm'][::period][lead:] - position).max()),
                'aperture_to_same_trajectory_cm': float(abs(t['lip_aperture_cm'] - traces[count_std]['lip_aperture_cm']).max()),
                'first_pcm_delta_over_1e-6_frame': voice.onset_difference(waves[n].astype(float) - waves[count_std], 1e-6)}
            for n, t in traces.items()}
    raw = [(r['raw_control_frames']['close'], r['raw_control_frames']['reopen']) for r in rows.values()]
    checks['same_continuous_trajectory'] = max(max(v['aperture_to_independent_cm'], v['aperture_to_same_trajectory_cm'])
                                              for v in diff.values()) < config['measurement']['geometry_absolute_lt']
    if config['measurement']['require_same_raw_closure_frames']:
        checks['raw_closure_frames_identical'] = len(set(raw)) == 1
    return {'checks': checks, 'grids': rows, 'comparisons_to_18': diff}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = prior.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    root, saved = prior.saved({'baseline': config['trajectory_reference_run']}, ['artifacts/trace.csv'], revision)
    case_path = WORKSPACE / 'cases' / config['trajectory_case']
    code = [Path(m.__file__) for m in (artic, grid, prior, voice, resample, sagittal, tract, shared, voiced)]
    inputs = [CASE, case_path, Path(__file__).resolve(), *saved, *code, artic.PROBE, sagittal.PROBE,
              *shared.candidate_sources(), *(UPSTREAM / path for path in (UPPER_GEOMETRY,
                  'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/tests/geometry_continuity.rs', 'crates/chimera/tests/airway_adversarial.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda artifacts, execute: measure(config, prior.read(case_path),
                                                                         root / 'artifacts/trace.csv', artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
