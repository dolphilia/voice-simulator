"""CSDの初期幾何を測定線から口端セルと最初の体積変化まで照合する。"""

import argparse
from itertools import combinations
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import measure_csd_en001a_first_lip_load as load
import measure_tsp_fk61_lip_area_origin as area
from measure_tsp_fk61_centerline_length_origin import first_unequal, replay_lengths
import tsp_fk61_centerline_observation as center


prior, lip, radiation, song, tsp = load.prior, load.lip, load.radiation, load.song, load.tsp
observer = area.observer
CASE = radiation.WORKSPACE / 'cases/csd-en001a-initial-oral-geometry.json'
MODES = load.MODES
FILES = ('upstream.jsonl', 'candidate.jsonl', 'pcm-digests.json',
         'upstream-observation.patch', 'candidate-observation.patch')
UPPER_GEOMETRY = ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/voice/human_airway.rs',
                  'crates/chimera/src/airway/network.rs')
CANDIDATE_GEOMETRY = tuple('crates/vocal-core/src/' + name for name in (
    'anatomy/area.rs', 'airway/human.rs', 'airway/tract_control.rs', 'voice.rs'))
CANDIDATE_TEST_CASES = tuple(radiation.WORKSPACE / 'cases' / name
                             for name in ('contour-buffer-reuse.json', 'bilabial-p.json'))


def prepare_geometry(root, fixed):
    geometry = UPPER_GEOMETRY if fixed else CANDIDATE_GEOMETRY
    names = (*geometry, f'tools/{observer.SNAPSHOT.name}')
    snapshot = root / names[-1]
    snapshot.parent.mkdir(exist_ok=True)
    snapshot.write_bytes(observer.SNAPSHOT.read_bytes())
    original = {name: (root / name).read_text() for name in names}
    if fixed:
        observer.observe_upstream(root)
        center.observe_upstream(root)
    else:
        observer.observe_candidate(root)
        center.observe_candidate(root, trial=False)
    observer.edit(snapshot, '''pub fn write(voice: &Voice, completed: usize, requested: &[usize]) -> Result<(), Box<dyn Error>> {
    if requested.contains(&completed) {
        println!("{}", json!({"completed_frames": completed, "tract": snapshot(voice)?}));
    }
    Ok(())
}''', '''pub fn write(voice: &Voice, completed: usize, out: &mut impl std::io::Write) -> Result<(), Box<dyn Error>> {
    writeln!(out, "{}", json!({"completed_frames": completed, "tract": snapshot(voice)?}))?;
    out.flush()?;
    Ok(())
}''')
    return ''.join(prior.diff(original[name], root / name, name) for name in names)


def patch_upstream(path):
    original = path.read_text()
    observer.insert_before(path, 'use chimera::{', 'mod tsp_fk61_lip_area_snapshot;\n\n')
    observer.insert_before(path, '    let mut one = [0.0f32];', '''    let mut shape = std::env::var_os("CHIMERA_CSD_LIP_TRACE")
        .map(File::create_new).transpose()?.map(BufWriter::new);
    if let Some(out) = &mut shape {
        tsp_fk61_lip_area_snapshot::write(&voice, 0, out)?;
    }
''')
    observer.insert_before(path, '        pcm.write_all(&one[0].to_le_bytes())?;', '''        if frame == 0
            && let Some(out) = &mut shape
        {
            tsp_fk61_lip_area_snapshot::write(&voice, 1, out)?;
        }
''')
    return prior.diff(original, path, 'tools/' + song.PROBE.name)


def patch_candidate(path, factor):
    original = path.read_text()
    anchor = '''            pcm::write(
                || {
                    step_audio(&mut voice, &mut pattern)
                        .map(|s| s.radiation.radiation_flow_derivative_cm3_s2)
                },
'''
    observer.edit(path, anchor, f'''            let mut shape = std::env::var_os("CHIMERA_CSD_LIP_TRACE")
                .map(File::create_new).transpose()?.map(BufWriter::new);
            if let Some(out) = &mut shape {{
                tsp_fk61_lip_area_snapshot::write(&voice, 0, out)?;
            }}
            let mut internal_samples = 0;
            pcm::write(
                || {{
                    let sample = step_audio(&mut voice, &mut pattern)?;
                    if let Some(out) = &mut shape {{
                        internal_samples += 1;
                        if internal_samples == {factor} {{
                            tsp_fk61_lip_area_snapshot::write(&voice, 1, out)
                                .map_err(|_| "口端の幾何を書き出せません")?;
                            shape = None;
                        }}
                    }}
                    Ok(sample.radiation.radiation_flow_derivative_cm3_s2)
                }},
''')
    with path.open('a') as stream:
        stream.write('\n#[path = "../../../../tools/tsp_fk61_lip_area_snapshot.rs"]\nmod tsp_fk61_lip_area_snapshot;\n')
    return prior.diff(original, path, prior.RESEARCH)


def capture(study, spec, out, execute):
    m = study['measurement']
    factor = m['internal_sample_rate_hz'] // m['sample_rate_hz']
    proof = {}
    with TemporaryDirectory(prefix='csd-initial-oral-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        for name in MODES:
            fixed = name == 'upstream'
            root = scratch / name
            root.mkdir()
            flags = ('--offline', '--target-dir', str(root / 'target'))
            test_log = out / f'{name}-tests.log'
            if fixed:
                archive = scratch / 'upper.tar'
                execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
                execute(['tar', '-xf', str(archive), '-C', str(root)])
                execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'chimera', '--test',
                         'golden_geometry', '--test', 'geometry_continuity'], cwd=root, stdout=test_log)
                stock = lip.build_upstream_probe(song.PROBE, scratch, execute, upstream=root, cargo_args=flags,
                                                 extra_libraries=('serde_json',))
            else:
                lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                                 radiation.WORKSPACE / 'data/cmudict.txt.gz', *CANDIDATE_TEST_CASES), root)
                execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'vocal-core', '--lib',
                         'resample'], cwd=root, stdout=test_log)
                stock = lip.build_pcm_cli(False, root, flags, execute)
            plain_files = tuple(scratch / f'{name}-normal.{ext}' for ext in ('wav', 'json', 'csv'))
            ordinary = load.run(stock, plain_files, spec, m, execute, fixed)
            diff = prepare_geometry(root, fixed)
            if fixed:
                path = root / 'tools/upstream_csd_initial_geometry_probe.rs'
                path.write_bytes(song.PROBE.read_bytes())
                diff += patch_upstream(path)
                sample = lip.build_upstream_probe(path, scratch, execute, upstream=root, cargo_args=flags,
                                                   extra_libraries=('serde_json',), rustc_args=('--cfg', 'lip_upstream'))
            else:
                diff += patch_candidate(root / prior.RESEARCH, factor)
                sample = lip.build_pcm_cli(False, root, flags, execute)
            (out / f'{name}-observation.patch').write_text(diff)
            observed_files = tuple(scratch / f'{name}-observed.{ext}' for ext in ('wav', 'json', 'csv'))
            observed = load.run(sample, observed_files, spec, m, execute, fixed, trace=out / f'{name}.jsonl')
            proof[name] = {'ordinary': lip.pcm_digest(ordinary), 'observed': lip.pcm_digest(observed),
                           'ordinary_plan': tsp.read(plain_files[1]), 'observed_plan': tsp.read(observed_files[1])}
    load.save(out / 'pcm-digests.json', proof)


def geometry_groups(geometry, fields):
    output = {}
    for target, donor in (MODES, MODES[::-1]):
        lower, upper = geometry[target], geometry[donor]
        lower_grid, upper_grid = lower['grid'], upper['grid']
        if [g[2] for g in lower_grid] != [g[2] for g in upper_grid]:
            raise ValueError('交換する双方の測定線の領域順が異なります')
        own, other = lower['raw'][0], upper['raw'][0]
        gap = abs(own - other)
        rows = {}
        for count in range(len(fields) + 1):
            for groups in combinations(fields, count):
                bounds = upper if 'bounds' in groups else lower
                grid = [[b[0] if 'axial_positions' in groups else a[0], b[1] if 'ray_areas' in groups else a[1]]
                        for a, b in zip(lower_grid, upper_grid, strict=True)]
                model = area.resample(bounds, grid)
                predicted = model['cell']
                rows['+'.join(groups) or 'native'] = {
                    'area_and_minimum_cm2': predicted,
                    'matches_donor': predicted == upper['raw'],
                    'recovery_fraction': 1.0 - abs(predicted[0] - other) / gap if gap else None,
                }
        output[target] = rows
    return output


def first_volume(start, target, floor, block, rate, fixed):
    next_cell = [a + (b - a) * (1.0 / block) for a, b in zip(start, target, strict=True)]
    before = max(floor, start[0]) * start[1]
    after = max(floor, next_cell[0]) * next_cell[1]
    delta = before - after
    return {'area_and_length': next_cell, 'before_cm3': before, 'after_cm3': after,
            'volume_delta_cm3': delta, 'raw_flow_cm3_s': delta * rate if fixed else delta / (1.0 / rate)}


def volume_groups(native, m):
    decisions = {}
    fields = m['first_volume_fields']
    for name, other in (MODES, MODES[::-1]):
        selected, donor = native[name][0], native[other][0]
        start_keys = ('old_area', 'old_length')
        target_keys = ('target_area_cm2', 'target_length_cm')
        rows = {}
        for count in range(len(fields) + 1):
            for swap in combinations(fields, count):
                start = [(donor if field in swap else selected)[key] for field, key in zip(fields, start_keys, strict=True)]
                target = [(donor if field in swap else selected)[key] for field, key in zip(fields, target_keys, strict=True)]
                v = first_volume(start, target, selected['area_floor'], m['control_internal_samples'],
                                 m['internal_sample_rate_hz'], name == 'upstream')
                rows['+'.join(swap) or 'native'] = v | {
                    'matches_donor': [v[k] for k in ('before_cm3', 'after_cm3', 'raw_flow_cm3_s')]
                        == [donor[k] for k in ('old_volume', 'volume', 'spill')],
                    'raw_flow_shift_cm3_s': v['raw_flow_cm3_s'] - selected['spill'],
                }
        decisions[name] = rows
    return decisions


def compare(frame, geom, m):
    lengths = {name: replay_lengths(row, m['internal_sample_rate_hz']) for name, row in geom.items()}
    resampled = {name: area.resample(row, row['grid']) for name, row in geom.items()}
    a, b = (lengths[name] for name in MODES)
    by_grid = {
        field: first_unequal([row[i] for row in geom['upstream']['grid']], [row[i] for row in geom['candidate']['grid']])
        for i, field in enumerate(area.GRID_COLUMNS)
    }
    first = {'grid': by_grid, 'midpoint_pair': first_unequal(a['points'], b['points']),
             'segment_distance': first_unequal(a['steps'], b['steps']),
             'cumulative_distance': first_unequal(a['axial'], b['axial'])}
    used = sorted(set().union(*(details['rays_used'] for details in resampled.values())))
    return {
        'completed_frames': frame, 'first_differences': first, 'contributing_rays': used,
        'geometry': {name: {key: row[key] for key in ('origin_cm', 'end_cm', 'oral_cells', 'raw', 'limited',
                                                     'target', 'current')} for name, row in geom.items()},
        'lengths': {name: {key: row[key] for key in ('oral_length_cm', 'target_cm', 'junction',
                                                   'bounds_and_oral_length_target_match', 'cumulative_matches')}
                     | {'max_step_error_ulp': max(row['step_error_ulp'])} for name, row in lengths.items()},
        'ray_values': {name: [row['grid'][i] for i in used] for name, row in geom.items()},
        'native_resampling': resampled, 'input_exchanges': geometry_groups(geom, m['geometry_fields']),
    }


def analyze(study, out, reference):
    m = study['measurement']
    frames = m['completed_frames']
    observations = {name: area.read_snapshots(out / f'{name}.jsonl', frames) for name in MODES}
    proof = tsp.read(out / 'pcm-digests.json')
    archive = tsp.read(tsp.verified_path(reference, 'artifacts/pcm-digests.json'))
    load_rows = tsp.read(tsp.verified_path(reference, 'artifacts/lip-observations.json'))
    reports = [compare(frame, {name: observations[name][frame] for name in MODES}, m) for frame in frames]
    initially = reports[0]
    exchanges = volume_groups(load_rows, m)
    continuation = {}
    for name, rows in load_rows.items():
        first, second = rows
        initial_shape, stepped_shape = (observations[name][frame] for frame in frames)
        expected_initial = [first[k] for k in ('old_area', 'old_minimum', 'old_length')]
        expected_target = [first[k] for k in ('target_area_cm2', 'target_minimum_cm2', 'target_length_cm')]
        expected_after = [second[k] for k in ('area_cm2', 'minimum', 'length_cm')]
        native = exchanges[name]['native']
        continuation[name] = {
            'initial_geometry': initial_shape['raw'] == initial_shape['limited'] == expected_initial[:2]
                and initial_shape['target'] == initial_shape['current'] == expected_initial,
            'first_control_target': stepped_shape['target'] == expected_target
                and stepped_shape['limited'] == expected_target[:2],
            'geometry_after_first_frame': stepped_shape['current'] == expected_after,
            'first_volume_source': [native[k] for k in ('before_cm3', 'after_cm3', 'raw_flow_cm3_s')]
                == [first[k] for k in ('old_volume', 'volume', 'spill')],
            'full_geometry_swap': exchanges[name]['cell_area+cell_length']['matches_donor'],
        }
    a, b = (initially['geometry'][name] for name in MODES)
    first_axial = initially['first_differences']['cumulative_distance']
    threshold = m['minimum_area_recovery_fraction']
    hypotheses = {
        'cumulative_difference_reaches_terminal_cell': first_axial is not None
            and first_axial <= min(initially['contributing_rays'])
            and any(a[key] != b[key] for key in ('origin_cm', 'end_cm')),
        'axial_inputs_dominate_terminal_initial_area_difference': all(
            rows['bounds+axial_positions']['recovery_fraction'] is not None
            and rows['bounds+axial_positions']['recovery_fraction'] >= threshold
            and rows['ray_areas']['recovery_fraction'] < threshold for rows in initially['input_exchanges'].values()),
        'lengths_are_above_the_stability_floor': all(
            details['oral_length_cm'] / report['geometry'][name]['oral_cells'] == details['target_cm']
            for report in reports for name, details in report['lengths'].items()),
    }
    return {
        'checks': {
            'ordinary_probe_and_prior_pcm_and_plans_match': all(
                row['ordinary'] == row['observed'] == archive[name]['ordinary'] == archive[name]['observed']
                and row['ordinary']['frames'] == m['frames']
                and row['ordinary_plan'] == row['observed_plan'] == archive[name]['observed_plan']
                for name, row in proof.items()),
            'initial_and_control_geometry_and_first_volume_match': all(all(row.values()) for row in continuation.values()),
            'centerline_segments_accumulation_and_cell_length_replay': all(
                row['bounds_and_oral_length_target_match'] and row['cumulative_matches']
                and row['max_step_error_ulp'] <= m['max_segment_distance_error_ulp']
                for report in reports for row in report['lengths'].values()),
            'native_resampling_and_full_input_exchange_replay': all(
                report['native_resampling'][name]['cell'] == report['geometry'][name]['raw']
                and report['input_exchanges'][name]['bounds+axial_positions+ray_areas']['matches_donor']
                for report in reports for name in MODES),
        },
        'hypotheses': hypotheses, 'first_volume_exchanges': exchanges, 'load_archive_agreement': continuation,
        'frames': reports,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    reference, render = (tsp.open_run(study[key], revision) for key in ('lip_load', 'render'))
    spec = tsp.verified_path(render, 'artifacts/candidate-short-128.json')
    tests = tuple('crates/chimera/tests/' + name for name in ('golden_geometry.rs', 'geometry_continuity.rs',
                                                            'common/mod.rs', 'golden/geometry.json'))
    inputs = [CASE, Path(__file__).resolve(), spec, song.PROBE, observer.SNAPSHOT,
              *(Path(module.__file__) for module in (load, prior, area, center, observer)),
              Path(replay_lengths.__code__.co_filename),
              *CANDIDATE_TEST_CASES,
              *prior.prefix.capture_dependencies(),
              *(upper / name for name in (*UPPER_GEOMETRY, *tests, 'crates/chimera/src/math.rs',
                                         'crates/chimera/src/anatomy/geom.rs')),
              *(run[0] / 'manifest.json' for run in (reference, render)),
              *(tsp.verified_path(reference, f'artifacts/{name}') for name in ('lip-observations.json', 'pcm-digests.json'))]

    def measure(out, execute):
        capture(study, spec, out, execute)
        return analyze(study, out, reference)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
