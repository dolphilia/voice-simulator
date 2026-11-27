"""前方測定線の組織厚さによる補正を、固定の再現版と比較する。"""

import argparse
import gzip
import itertools
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_area as area
import measure_bilabial_stop as stop
import measure_grid as grid
import measure_labiodental_fricatives as labio
import measure_lip_tuck_continuity as static
import measure_lip_tuck_radiation as radiation
import measure_resample as resample
import measure_sagittal as sagittal
import measure_tract_control as tract
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/lip-tuck-crossing-thickness.json'
CLI = radiation.CLI


def read(path):
    return json.loads(path.read_text())


def saved(config, paths, revision):
    root = WORKSPACE / 'runs' / config['baseline']
    manifest = root / 'manifest.json'
    info = read(manifest)
    by_path = {row['path']: row for row in info['outputs']}
    if info['status'] != 'pass' or info['upstream_revision'] != revision:
        raise ValueError(f'{root.name} の基準実行を照合できません')
    for path in paths:
        wanted = by_path[path]
        whole = root / path
        if whole.stat().st_size != wanted['bytes'] or sha256(whole) != wanted['sha256']:
            raise ValueError(f'{whole} の保存内容を照合できません')
    return root, [manifest, *(root / path for path in paths)]


def cargo_feature(execute, feature):
    def run(command, **options):
        if command[:2] == ['cargo', 'run'] and '-p' in command and command[command.index('-p') + 1] == 'vocal-cli':
            split = command.index('--')
            command = [*command[:split], '--features', f'vocal-core/{feature}', *command[split:]]
        execute(command, **options)
    return run


def compress(path):
    with path.open('rb') as source, path.with_suffix(path.suffix + '.gz').open('wb') as stream:
        with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as target:
            shutil.copyfileobj(source, target)
    path.unlink()


def independent_front(parts, profile, posture, scale):
    # 元の輪郭をxで内分し、交差の符号は輪郭の向きから独立して読む。
    rows = static.front_rays(parts, profile, posture['labiodental'], scale)
    out = profile.copy()
    lip_start = len(parts['inner']) - 7
    folds = []
    for row in rows:
        index, roof, floor = (row[key] for key in ('grid_index', 'roof_y_cm', 'floor_y_cm'))
        crossings = sorted(row['inner_crossings'], key=lambda crossing: crossing[1])
        if not row['lip_extension'] and len(crossings) == 3:
            bottom, first, last = crossings
            directions = np.diff(parts['inner'][:, 0])
            if directions[last[0]] < 0:
                first, last = last, first
            if (directions[bottom[0]] > 0 > directions[first[0]] and directions[last[0]] > 0
                    and min(first[0], last[0]) >= lip_start and first[1] <= last[1] < roof):
                thickness = last[1] - first[1]
                floor = bottom[1] + thickness
                folds.append({'grid_index': index, 'segments': [first[0], last[0]],
                              'thickness_cm': thickness, 'inner_y_cm': floor})
        out[index, [1, 2, 4, 6, 7, 8]] = row['x_cm'], floor, roof, (floor + roof) / 2, roof - floor, roof - floor
    return out, folds


def verify_known_brackets(case, cache, baseline, artifacts, run):
    events = read(baseline / 'summary.json')['events']
    rows = []
    for index, event in enumerate(events, 1):
        group = tuple(event['group'])
        body, protrusion, spread = group
        body_name = static.BODIES[body]
        params = case['body_parameters'][body_name]
        scale = params['scale']
        epi = 2.4 * scale * params['pharynx']
        errors, folds = [], []
        for end, tuck in zip(static.ENDS, event['u'], strict=True):
            dest = artifacts / f'event-{index:02}-{end}'
            dest.mkdir()
            path = baseline / f'artifacts/event-{index:02}/{end}/upstream-geometry.csv'
            parts = sagittal.read_points(path)
            posture = {**case['base_posture'], 'lip_protrusion_cm': protrusion,
                       'lip_spread': spread, 'labiodental': tuck}
            version = {k: case[k] for k in ('id', 'upstream_revision', 'hypothesis', 'cells')}
            version.update({'body': body_name, 'posture': posture, 'measurement': {'frames': 1}})
            target = dest / 'case.json'
            radiation.write_json(target, version)
            output = dest / 'area.csv'
            run([*CLI, 'area', str(target), str(output)])
            actual = grid.read_grid(output, columns=area.COLUMNS)
            expected, paired = independent_front(parts, actual, posture, scale)
            calculated, distance, *_ = area.independent_profile(
                parts, expected[:, :-2], posture, scale=scale, epilarynx_cm=epi,
                full_lip_width=params['lip_width_cm_at_full_spread_before_scaling'])
            expected[:, -2:] = np.column_stack((calculated, distance))
            tubes = resample.estimate_cells(expected, {**version, 'measurement': case['measurement']},
                                           dest / 'independent-cells.csv', scale=scale, epilarynx_cm=epi)
            cells = np.concatenate([tubes[key][0][:, 2:] for key in resample.TUBES])
            observed = cache['candidate'][(*group, tuck)].reshape(2, -1).T
            delta = abs(expected - actual)
            errors.append({'cm': float(np.delete(delta, -2, axis=1).max()),
                           'cm2': float(max(delta[:, -2].max(), abs(cells - observed).max()))})
            folds.append(paired)
        count = sum(case['cells'].values())
        lo, hi = [cache['candidate'][(*group, endpoint)][:count] for endpoint in event['u']]
        rows.append({'group': group, 'u': event['u'], 'before_cm2': event['jump_cm2'],
                     'after_cm2': float(abs(lo - hi).max()), 'pairs': folds, 'errors': errors})
    return rows


def geometry(config, baseline, artifacts, execute, run, feature):
    registered = config['static']
    case = read(WORKSPACE / 'cases' / registered['case'])
    probes = {'upstream': shared.build_upstream_probe(static.SWEEP, artifacts, execute,
                                                     rustc_args=('--cfg', 'fixed_upstream')),
              'candidate': shared.build_upstream_probe(static.SWEEP, artifacts, execute,
                                                       upstream=WORKSPACE, package='vocal-core', lto='off',
                                                       cargo_args=('--features', feature))}
    cache, events, coverage = static.sweep(case, probes, artifacts, execute)
    rows = verify_known_brackets(case, cache, baseline, artifacts, run)
    limit = registered['ordinary_labiodental']
    comparison = []
    for jaw, opening in itertools.product(limit['jaw_cm'], limit['lip_aperture_cm']):
        folder = artifacts / f'ordinary-jaw-{jaw}-opening-{opening}'
        folder.mkdir()
        pose = {**case['base_posture'], 'jaw_cm': jaw, 'lip_aperture_cm': opening}
        regular = {**case, 'base_posture': pose, 'lip_protrusions_cm': [limit['lip_protrusion_cm']],
                   'lip_spreads': [limit['lip_spread']]}
        series, ordinary, counts = static.sweep(regular, probes, folder, execute)
        zeros = sum(np.count_nonzero((left == 0.0) != (series['candidate'][point] == 0.0))
                    for point, left in series['upstream'].items())
        comparison.append({'jaw_cm': jaw, 'lip_aperture_cm': opening,
                           'events': ordinary, 'zero_section_mismatches': int(zeros), 'coverage': counts})
    core_unchanged = len(events['upstream']) == len(rows) and all(
        entry['u'] == list(measured['u']) and entry['group'] == tuple(measured['group'])
        for entry, measured in zip(rows, events['upstream'], strict=True)
    )
    checks = {
        'fixed_upstream_known_brackets': core_unchanged,
        'eliminates_all_registered_bracket_steps':
            max(row['after_cm2'] for row in rows) < registered['maximum_step_at_known_brackets_cm2'],
        'no_other_refined_steps_in_protruded_sweeps': len(events['candidate']) <= registered['maximum_new_detected_steps'],
        'independent_fold_gap_area_and_cell':
            all(errors['cm'] < registered['independent_cm_tolerance'] and errors['cm2'] < registered['independent_cm2_tolerance']
                for row in rows for errors in row['errors']),
        'ordinary_tuck_continuity': all(len(row['events']['candidate']) <= limit['maximum_detected_steps'] for row in comparison),
        'ordinary_tuck_zero_sections': not any(row['zero_section_mismatches'] for row in comparison),
    }
    return checks, {'known': rows, 'protruded_sweeps': events, 'coverage': coverage, 'ordinary': comparison}


def dynamic(config, baseline, folder, execute, run):
    registered = config['dynamic']
    path = WORKSPACE / 'cases' / registered['case']
    case = read(path)
    cfg = case['measurement']['dynamic_lip_tuck']
    rate, fs = case['voice']['output_sample_rate_hz'], case['articulators']['sample_rate_hz']
    block, frames = case['articulators']['control_block_samples'], case['measurement']['frames']
    factor = fs // rate
    indices = np.arange(block * frames)
    output = indices[factor - 1::factor]
    host = cfg['host_block_sizes'][0]
    fixed = read(baseline / 'summary.json')
    at = fixed['crossing']['output_frame']
    cells = case['measurement']['voiced_tract_oral_cells']
    streams, waves = {}, {}
    for name in ('hold', 'cross'):
        child = folder / name
        child.mkdir(parents=True)
        probe = baseline / f'artifacts/{name}/case.json'
        full, wave, observed, *_ = radiation.capture_candidate(
            probe, child, [host], indices, block, cells, run)
        if observed != rate or len(wave) != len(output):
            raise ValueError('動的ケースのPCM形式が基準と一致しません')
        streams[name] = {k: v[output] for k, v in full.items()}
        waves[name] = wave
        compress(child / 'candidate-samples.csv')
    fresh = folder / 'default-cross.wav'
    execute([*CLI, 'render-pcm', str(path), str(fresh), '--no-trace', str(host)])
    default_wave = baseline / f'artifacts/cross/block-{host}.wav'
    hold_wave = wavfile.read(baseline / f'artifacts/hold/block-{host}.wav')[1]
    stats = radiation.contrasts(streams['cross'], streams['hold'], waves['cross'], waves['hold'], cfg, at, rate)
    old = fixed['contrasts']['candidate_cross_minus_hold']
    first20, original = (r['windows'][2]['rms'] for r in (stats, old))
    ratios = {key: first20[key] / original[key] for key in first20}
    source = baseline / 'artifacts/cross/geometry-case.json'
    target = folder / 'experimental-targets.csv'
    run([*CLI, 'render', str(source), str(target)])
    table, _ = tract.read_trace(target, cfg['tube_cells'], frames)
    cell = cfg['tube_cells']['pharynx'] + cfg['affected_cell']
    step = cfg['first_crossing_control_frame']
    jump = (table[step, 'apply'][cell, :4] - table[step - 1, 'apply'][cell, :4]).tolist()
    checks = {
        'unselected_default_and_hold_match_saved_wave': sha256(fresh) == sha256(default_wave)
            and np.array_equal(waves['hold'].view('u4'), hold_wave.view('u4'))
            and np.array_equal(waves['cross'][:at].view('u4'), hold_wave[:at].view('u4')),
        'dynamic_raw_mean_step': abs(jump[0]) < registered['maximum_raw_mean_step_cm2'],
        'dynamic_reduces_pcm_residual': ratios['pcm'] < registered['maximum_pcm_residual_rms_ratio_first_20ms'],
        'dynamic_reduces_pressure_and_lip_flow_residual': all(
            ratios[key] < registered['maximum_pressure_and_flow_residual_rms_ratio_first_20ms']
            for key in ('oral_pressure', 'lip_pressure', 'lip_flow')),
    }
    return checks, {'new': stats, 'baseline': old, 'rms_ratios_0_20_ms': ratios, 'area_steps_cm2': jump}


def stops(config, folder, run):
    folder.mkdir()
    cfg = config['stops']
    rows = {}
    for file in cfg['cases']:
        path = WORKSPACE / 'cases' / file
        output = folder / path.stem
        output.mkdir()
        measured = stop.measure(path, read(path), output, run)
        actual, reference = [measured[name + '_events'] for name in ('candidate', 'upstream')]
        keys = ('first_closed_frame', 'first_open_frame', 'burst_frame_first_5ms')
        shifts = {k: actual[k] - reference[k] if k in actual and k in reference else None for k in keys}
        peak = (actual.get('burst_pcm_peak_first_5ms'), reference.get('burst_pcm_peak_first_5ms'))
        passed = (measured['checks']['measured_closure_and_release']
                  and all(value is not None and abs(value) <= cfg['maximum_shift_frames'] for value in shifts.values())
                  and None not in peak and abs(peak[0] - peak[1]) <= cfg['maximum_burst_peak_absolute_delta'])
        rows[path.stem] = {'passed': passed, 'frames_delta': shifts, 'burst_peak': peak, 'detail': measured}
        for item in output.glob('*voicing.csv'):
            compress(item)
    return {'stop_closure_release_and_burst': all(row['passed'] for row in rows.values())}, rows


def fricatives(config, baseline, output, run):
    cfg = config['fricatives']
    original = read(WORKSPACE / 'cases' / cfg['case'])
    rows = {}
    for kind in ('speech', 'song'):
        for variant in original[kind]:
            label = variant['id']
            if label not in cfg['variants']:
                continue
            source = baseline / 'artifacts' / label
            folder = output / label
            folder.mkdir(parents=True)
            path = source / 'case.json'
            settings = read(source / 'settings.json')
            _, _, vowel, span = labio.compare_plan(original, variant, settings,
                                                   read(source / 'upstream-plan.json'), kind == 'song')
            ref_pcm_path, speech_trace = source / 'pcm-128.wav', folder / 'voicing.csv'
            wave_path = folder / 'pcm.wav'
            run([*CLI, 'render', str(path), str(speech_trace)])
            run([*CLI, 'render-pcm', str(path), str(wave_path), '--no-trace', '128'])
            old_rate, old = wavfile.read(ref_pcm_path)
            rate, samples = wavfile.read(wave_path)
            if old_rate != rate or samples.shape != old.shape or not np.isfinite(samples).all():
                raise ValueError(f'{label} の前後のPCM条件が一致しません')
            data = [stop.load_trace(p, len(samples)) for p in (source / 'voicing.csv', speech_trace)]
            observations = [labio.observe(d, signal, rate, vowel, span, original, variant, kind == 'song')
                            for d, signal in zip(data, (old, samples), strict=True)]
            first, second = [obs[1] for obs in observations]
            left, right = span['t0'], span['t1']
            times = [left + (right - left) * f for f in original['measurement']['center_fraction']]
            for observed, track in zip((first, second), data, strict=True):
                t = track['frame'] / rate
                selected = (times[0] <= t) & (t < times[1])
                if not selected.any():
                    raise ValueError(f'{label} の子音中央区間に計測フレームがありません')
                observed['central_oral_minimum_median_cm2'] = float(np.median(track['oral_minimum_cm2'][selected]))
            area_diff = abs(second['central_oral_minimum_median_cm2'] - first['central_oral_minimum_median_cm2'])
            activity_diff = abs(second['sources']['constriction_noise']['active_fraction']
                                - first['sources']['constriction_noise']['active_fraction'])
            low_key = 'vowel_relative_low_band_db'
            low_diff = abs(second[low_key] - first[low_key]) if low_key in first else None
            lo, hi = [round(rate * t) for t in times]
            first_band, second_band = [radiation.band_rms(x[lo:hi], rate, [2000, 8000])[1] for x in (old, samples)]
            band_delta = float(20 * np.log10(max(second_band, 1e-10) / max(first_band, 1e-10)))
            rows[label] = {'passed': (all(observations[1][0].values())
                                     and area_diff <= cfg['maximum_oral_minimum_median_delta_cm2']
                                     and activity_diff <= cfg['maximum_active_fraction_delta']
                                     and (low_diff is None or low_diff <= cfg['maximum_relative_low_band_delta_db'])
                                     and abs(band_delta) <= cfg['maximum_2_to_8khz_level_delta_db']),
                           'aperture_delta_cm2': area_diff, 'constriction_activity_delta': activity_diff,
                           'relative_low_band_delta_db': low_diff, 'band_2_to_8khz_candidate_minus_baseline_db': band_delta,
                           'first_pcm_frame_different': radiation.onset_difference(samples.astype(float) - old, 0),
                           'pcm_bitwise': np.array_equal(samples.view('u4'), old.view('u4')),
                           'acoustic_checks': observations[1][0], 'baseline': first, 'experimental': second}
            compress(speech_trace)
    return {'fricative_narrowing_and_noise': set(rows) == set(cfg['variants'])
            and all(row['passed'] for row in rows.values())}, rows


def measure(config, baselines, artifacts, execute):
    feature = config['feature']
    run = cargo_feature(execute, feature)
    execute(['cargo', 'test', '--locked', '-p', 'vocal-core', '--features', feature, 'anatomy::grid'],
            stdout=artifacts / 'geometry-tests.log')
    checks, result = {}, {}
    for name, observe in (
            ('static', lambda: geometry(config, baselines['static'], artifacts, execute, run, feature)),
            ('dynamic', lambda: dynamic(config, baselines['dynamic'], artifacts / 'voice', execute, run)),
            ('stops', lambda: stops(config, artifacts / 'stops', run)),
            ('fricatives', lambda: fricatives(config, baselines['fricatives'], artifacts / 'fricatives', run))):
        try:
            verdict, values = observe()
        except KeyError as error:
            raise ValueError(f'{name} の計測に必要な項目がありません ({error})') from error
        checks.update(verdict)
        result[name] = values
        radiation.write_json(artifacts / f'{name}-report.json', values)
    return {'checks': {k: bool(v) for k, v in checks.items()}, **result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    reference_files = {
        'static': ['summary.json', *(f'artifacts/event-{i:02}/{end}/upstream-geometry.csv'
                                     for i in range(1, 19) for end in static.ENDS)],
        'dynamic': ['summary.json', 'artifacts/cross/geometry-case.json',
                    *(f'artifacts/{name}/{f}' for name in ('cross', 'hold') for f in ('case.json', 'block-128.wav'))],
        'fricatives': [f'artifacts/{variant}/{f}' for variant in config['fricatives']['variants']
                       for f in ('case.json', 'settings.json', 'upstream-plan.json', 'voicing.csv', 'pcm-128.wav')],
    }
    root, paths = {}, [CASE, Path(__file__).resolve(), static.SWEEP, stop.PROBE, *shared.candidate_sources()]
    paths.extend(Path(tool.__file__) for tool in (area, stop, grid, labio, static, radiation, resample,
                                                sagittal, tract, shared))
    for scope, files in reference_files.items():
        root[scope], inputs = saved(config[scope], files, revision)
        paths.extend([*inputs, WORKSPACE / 'cases' / config[scope]['case']])
    paths.extend(WORKSPACE / 'cases' / file for file in config['stops']['cases'])
    paths.extend(UPSTREAM / 'crates/chimera' / p for p in ('src/anatomy/human.rs', 'src/anatomy/geom.rs',
                    'src/voice/human_airway.rs', 'tests/geometry_continuity.rs'))
    return shared.record_measurement(args.run_id, CASE, paths,
                                     {'case_id': config['id'], 'upstream_revision': revision, 'feature': config['feature']},
                                     lambda artifacts, execute: measure(config, root, artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
