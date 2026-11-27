"""CSDの最初の中心線で測定線4・5のx座標を往復交換する。"""

import argparse
from fractions import Fraction
import os
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_en001a_initial_oral_geometry as geometry
from measure_tsp_fk61_centerline_length_origin import midpoint_report


load, prior, lip, area, tsp = geometry.load, geometry.prior, geometry.lip, geometry.area, geometry.tsp
radiation, song, observer, center = geometry.radiation, geometry.song, geometry.observer, geometry.center
CASE = radiation.WORKSPACE / 'cases/csd-en001a-centerline-coordinate-swap.json'
MODES = geometry.MODES
FILES = ('observations.json', 'pcm-digests.json', 'pcm.npz', 'upstream-observation.patch', 'candidate-observation.patch')
MASK = 'CHIMERA_CSD_CENTER_MASK'


def patch_distances(root, fixed, donor):
    name = geometry.UPPER_GEOMETRY[0] if fixed else geometry.CANDIDATE_GEOMETRY[0]
    model = 'HumanVocalTract' if fixed else 'SagittalModel'
    path = root / name
    original = path.read_text()
    cases = ''
    for index, value in donor.items():
        bits, = struct.unpack('<Q', struct.pack('<d', value))
        cases += f'        {index} if mask & (1 << {index}) != 0 => f64::from_bits(0x{bits:016x}),\n'
    observer.edit(path, f'impl {model} {{', f'''std::thread_local! {{
    static PROBE_AXIAL_MASK: std::cell::Cell<u64> = const {{ std::cell::Cell::new(0) }};
}}

fn probe_axial_x(index: usize, default: f64) -> f64 {{
    let mask = PROBE_AXIAL_MASK.get();
    match index {{
{cases}        _ => default,
    }}
}}

impl {model} {{
    pub fn probe_axial_swap(mask: u64) {{
        PROBE_AXIAL_MASK.set(mask);
    }}
''')
    snapshot = root / 'tools' / observer.SNAPSHOT.name
    old_snapshot = snapshot.read_text()
    if fixed:
        observer.edit(path, '    pub probe_axial_distances: Vec<f64>,',
                      '    pub probe_axial_distances: Vec<f64>,\n    #[serde(skip)]\n    pub probe_axial_centers: Vec<Vec2>,')
        observer.edit(path, '''        let mut s = epi_len;
        f.probe_axial_distances.clear();
        for i in 0..grid.len() {
            let step = if i == 0 { 0.0 } else { dist(grid[i].mid, grid[i - 1].mid) };
            if i > 0 {
                s += step;
            }
            grid[i].s = s;
            f.probe_axial_distances.push(step);
        }''', '''        let mut s = epi_len;
        let mut previous = None;
        f.probe_axial_distances.clear();
        f.probe_axial_centers.clear();
        for (i, g) in grid.iter_mut().enumerate() {
            let center = v(probe_axial_x(i, g.mid.x), g.mid.y);
            let step = previous.map_or(0.0, |last| dist(center, last));
            if previous.is_some() {
                s += step;
            }
            previous = Some(center);
            g.s = s;
            f.probe_axial_distances.push(step);
            f.probe_axial_centers.push(center);
        }''')
        observer.edit(snapshot, '''frame.grid.iter().zip(&frame.probe_axial_distances).map(|(g, &step)| {
            [g.mid.x, g.mid.y, step]''', '''frame.probe_axial_centers.iter().zip(&frame.probe_axial_distances).map(|(g, &step)| {
            [g.x, g.y, step]''')
    else:
        observer.edit(path, '''        samples.extend(contacts.iter().copied().map(|contact| {
            let mid = contact.ray.mid;
            let axial_mid = mid;''', '''        samples.extend(contacts.iter().copied().enumerate().map(|(i, contact)| {
            let mid = contact.ray.mid;
            let axial_mid = Point::new(probe_axial_x(i, mid.x), mid.y);''')
        observer.edit(path, 'use super::{BodyParameters, ContactSample, Region, SagittalFrame, SagittalModel};',
                      'use super::{BodyParameters, ContactSample, Point, Region, SagittalFrame, SagittalModel};')
    air = 'voice.airway' if fixed else 'voice.airway()'
    network = 'air.net' if fixed else 'air.network'
    lips = 'air.oral.last_node()' if fixed else 'air.lips'
    observer.edit(snapshot, '''    writeln!(out, "{}", json!({"completed_frames": completed, "tract": snapshot(voice)?}))?;''',
                  f'''    let mut tract = snapshot(voice)?;
    if completed == 1 {{
        let air = &{air};
        let net = &{network};
        let lips = {lips};
        tract["load_pair"] = json!((0..2).map(|i| net.probe_lip_pair[i].iter()
            .chain(&net.probe_lip_geometry[i]).copied().chain([lips as f64])
            .chain(net.probe_lip_target).collect::<Vec<_>>()).collect::<Vec<_>>());
    }}
    writeln!(out, "{{}}", json!({{"completed_frames": completed, "tract": tract}}))?;''')
    return prior.diff(original, path, name) + prior.diff(old_snapshot, snapshot, 'tools/' + snapshot.name)


def patch_entry(path, fixed, factor, reset_frame):
    original = path.read_text()
    masks = f'std::env::var("{MASK}").ok().and_then(|value| value.parse().ok()).unwrap_or(0)'
    if fixed:
        geometry.patch_upstream(path)
        model = 'chimera::anatomy::human::HumanVocalTract'
        observer.insert_before(path, '        voice.airway.apply(&voice.artic.x, 0.0);',
                               f'        {model}::probe_axial_swap({masks});\n')
        observer.insert_before(path, '    let mut one = [0.0f32];',
                               '    voice.airway.net.probe_lip_node = Some(voice.airway.oral.last_node());\n')
        observer.edit(path, '''        if frame == 0
            && let Some(out) = &mut shape
        {
            tsp_fk61_lip_area_snapshot::write(&voice, 1, out)?;
        }''', f'''        if (frame == 0 || frame + 1 == {reset_frame})
            && let Some(out) = &mut shape
        {{
            tsp_fk61_lip_area_snapshot::write(&voice, frame + 1, out)?;
        }}
        if frame == 0 {{
            {model}::probe_axial_swap(0);
        }}''')
        name = 'tools/' + song.PROBE.name
    else:
        geometry.patch_candidate(path, factor)
        model = 'vocal_core::anatomy::SagittalModel'
        observer.insert_before(path, '    let mut voice = ArticulatedVoice::for_speech_with_body(',
                               f'    {model}::probe_axial_swap({masks});\n')
        observer.insert_before(path, '            let mut shape = std::env::var_os("CHIMERA_CSD_LIP_TRACE")',
                               '            voice.enable_lip_load_observation();\n')
        observer.edit(path, f'''                        if internal_samples == {factor} {{
                            tsp_fk61_lip_area_snapshot::write(&voice, 1, out)
                                .map_err(|_| "口端の幾何を書き出せません")?;
                            shape = None;
                        }}''', f'''                        if internal_samples == {factor} || internal_samples == {reset_frame * factor} {{
                            tsp_fk61_lip_area_snapshot::write(&voice, internal_samples / {factor}, out)
                                .map_err(|_| "口端の幾何を書き出せません")?;
                        }}
                        if internal_samples == {factor} {{
                            {model}::probe_axial_swap(0);
                        }}''')
        name = prior.RESEARCH
    return prior.diff(original, path, name)


def references(run):
    return {name: area.read_snapshots(tsp.verified_path(run, f'artifacts/{name}.jsonl'), [0, 1]) for name in MODES}


def capture(study, spec, geometry_run, out, execute):
    m = study['measurement']
    frames, exchanges = m['completed_frames'], m['exchanges']
    factor = m['internal_sample_rate_hz'] // m['sample_rate_hz']
    snapshots, proof, pcm = {}, {}, {}
    base = references(geometry_run)
    rays = sorted({i for group in exchanges.values() for i in group})
    with TemporaryDirectory(prefix='csd-centerline-swap-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        for name, source in (MODES, MODES[::-1]):
            fixed = name == 'upstream'
            root = scratch / name
            root.mkdir()
            flags = ('--offline', '--target-dir', str(root / 'target'))
            log = out / f'{name}-tests.log'
            if fixed:
                archive = scratch / 'upper.tar'
                execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
                execute(['tar', '-xf', str(archive), '-C', str(root)])
                execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'chimera', '--test',
                         'golden_geometry', '--test', 'geometry_continuity'], cwd=root, stdout=log)
            else:
                lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                                 radiation.WORKSPACE / 'data/cmudict.txt.gz', *geometry.CANDIDATE_TEST_CASES), root)
                execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'vocal-core', '--lib',
                         'resample'], cwd=root, stdout=log)
            diff = load.patch_network(root, fixed, execute)
            diff += geometry.prepare_geometry(root, fixed)
            donor = {index: base[source][0]['centerline'][index][0] for index in rays}
            if any(base[source][1]['centerline'][index][0] != x for index, x in donor.items()):
                raise ValueError('交換元のx座標が最初の制御更新で変わりました')
            diff += patch_distances(root, fixed, donor)
            if fixed:
                path = root / 'tools/upstream_csd_centerline_swap_probe.rs'
                path.write_bytes(song.PROBE.read_bytes())
                diff += patch_entry(path, True, factor, frames[-1])
                exe = lip.build_upstream_probe(path, scratch, execute, upstream=root, cargo_args=flags,
                                                extra_libraries=('serde_json',), rustc_args=('--cfg', 'lip_upstream'))
            else:
                diff += patch_entry(root / prior.RESEARCH, False, factor, frames[-1])
                exe = lip.build_pcm_cli(False, root, flags, execute)
            (out / f'{name}-observation.patch').write_text(diff)
            snapshots[name], proof[name] = {}, {}
            for condition, indexes in exchanges.items():
                mask = sum(1 << index for index in indexes)
                key = f'{name}_{condition}'
                paths = tuple(scratch / f'{key}.{ext}' for ext in ('wav', 'json', 'csv'))
                trace = scratch / f'{key}.jsonl'

                def run_command(command, *, stdout=None):
                    if command[0] == 'env':
                        command = [command[0], f'{MASK}={mask}', *command[1:]]
                    execute(command, stdout=stdout)

                pcm[key] = load.run(exe, paths, spec, m, run_command, fixed, trace=trace)
                snapshots[name][condition] = area.read_snapshots(trace, frames)
                proof[name][condition] = {'pcm': lip.pcm_digest(pcm[key]), 'plan': tsp.read(paths[1])}
    load.save(out / 'observations.json', snapshots)
    load.save(out / 'pcm-digests.json', proof)
    np.savez_compressed(out / 'pcm.npz', **pcm)


def analyze_trials(study, observed, archived, baseline_load):
    m = study['measurement']
    rate, frames = m['internal_sample_rate_hz'], m['completed_frames']
    axial_checks, load_checks, coordinate_checks = [], [], []
    cases = {}
    for name, donor in (MODES, MODES[::-1]):
        native = observed[name]['native']
        fixed = name == 'upstream'
        cases[name] = {}
        for condition, rays in m['exchanges'].items():
            rows = [observed[name][condition][str(frame)] for frame in frames]
            samples = [dict(zip(load.FIELDS, row, strict=True)) for row in rows[1]['load_pair']]
            local = [geometry.replay_lengths(row, rate) for row in rows]
            cells = [area.resample(row, row['grid']) for row in rows]
            first = samples[0]
            initial = [first[k] for k in ('old_area', 'old_minimum', 'old_length')]
            target = [first[k] for k in ('target_area_cm2', 'target_minimum_cm2', 'target_length_cm')]
            current = [samples[1][k] for k in ('area_cm2', 'minimum', 'length_cm')]
            reset = native[str(frames[-1])]
            coordinate_checks.append(rows[-1]['centerline'] == reset['centerline'] and rows[-1]['grid'] == reset['grid'])
            for row, frame in zip(rows[:2], frames[:2], strict=True):
                base = archived[name][frame]
                expected = [[archived[donor][frame]['centerline'][i][0] if i in rays else entry[0], entry[1]]
                            for i, entry in enumerate(base['centerline'])]
                coordinate_checks.append(
                    [entry[:2] for entry in row['centerline']] == expected
                    and [entry[1:] for entry in row['grid']] == [entry[1:] for entry in base['grid']])
            axial_checks.append(all(
                model['cumulative_matches'] and model['bounds_and_oral_length_target_match']
                and max(model['step_error_ulp']) <= m['max_segment_distance_error_ulp']
                and resampled['cell'] == row['raw'] for row, model, resampled in zip(rows, local, cells, strict=True)))
            flows = [lip.geometry(sample, rate, fixed) for sample in samples]
            load_checks.append(
                rows[0]['current'] == initial and rows[1]['target'] == target and rows[1]['current'] == current
                and all(data['matches_dimensions_and_volume'] and data['matches_filter'] and data['matches_geometry_inflow']
                        and data['spill_minus_retained_local'] == 0.0
                        and load.load_coefficients(sample) and lip.solve_matches(sample, rate, fixed)
                        for sample, data in zip(samples, flows, strict=True))
                and (condition != 'native' or samples == baseline_load[name]))
            focus = m['first_accumulation_difference_ray']
            reduced = [
                {'step_at_4_cm': model['steps'][m['first_distance_difference_ray']],
                 's_at_4_cm': model['axial'][m['first_distance_difference_ray']],
                 'step_at_6_cm': model['steps'][focus], 's_at_6_cm': model['axial'][focus],
                 'pre_round_sum_at_6_cm': str(Fraction(model['axial'][focus-1]) + Fraction(model['steps'][focus])),
                 'pharynx_end_cm': row['origin_cm'], 'lip_end_cm': row['end_cm'],
                 'lip_cell_cm': model['target_cm'], 'cell_area_cm2': row['raw'][0],
                 'max_distance_error_ulp': max(model['step_error_ulp'])}
                for row, model in zip(rows, local, strict=True)]
            cases[name][condition] = {'frames': reduced, 'first_raw_volume_flow_cm3_s': first['spill'],
                                      'first_lip_flow_cm3_s': first['lip_flow_cm3_s'],
                                      'second_lip_flow_cm3_s': samples[1]['lip_flow_cm3_s']}
    return cases, {
        'coordinate_exchange_is_exact_and_released_at_next_control': all(coordinate_checks),
        'distance_accumulation_and_resampling_replayed': all(axial_checks),
        'first_volume_and_radiation_load_replayed': all(load_checks),
    }


def analyze(study, out, geometry_run, lip_run):
    m = study['measurement']
    base = references(geometry_run)
    baseline = tsp.read(tsp.verified_path(geometry_run, 'artifacts/pcm-digests.json'))
    baseline_load = tsp.read(tsp.verified_path(lip_run, 'artifacts/lip-observations.json'))
    proof = tsp.read(out / 'pcm-digests.json')
    captures = tsp.read(out / 'observations.json')
    trials, checks = analyze_trials(study, captures, base, baseline_load)
    comparisons = {}
    pcm_checks = []
    with np.load(out / 'pcm.npz', allow_pickle=False) as waves:
        for name in MODES:
            pcm_checks.append(proof[name]['native']['pcm'] == baseline[name]['observed'])
            ordinary = waves[f'{name}_native'].astype(np.float64)
            for condition in m['exchanges']:
                wave = waves[f'{name}_{condition}']
                info = proof[name][condition]
                pcm_checks.append(
                    len(wave) == m['frames'] and wave.dtype == np.dtype('<f4') and bool(np.isfinite(wave).all())
                    and info['pcm'] == lip.pcm_digest(wave) and info['plan'] == baseline[name]['observed_plan'])
                trials[name][condition]['pcm_to_native'] = prior.full.metrics(wave - ordinary)
        for condition in m['exchanges']:
            delta = waves[f'candidate_{condition}'].astype(np.float64) - waves[f'upstream_{condition}']
            comparisons[condition] = prior.full.metrics(delta)
    hypotheses = {
        'ray4_matches_first_distance_without_moving_its_accumulation': all(
            a['step_at_4_cm'] == b['step_at_4_cm'] and a['s_at_4_cm'] == c['s_at_4_cm']
            for name, other in (MODES, MODES[::-1]) for a, b, c in zip(
                trials[name]['ray4']['frames'][:2], trials[other]['native']['frames'][:2],
                trials[name]['native']['frames'][:2], strict=True)),
        'ray5_matches_first_differing_accumulation': all(
            (a['step_at_6_cm'], a['s_at_6_cm']) == (b['step_at_6_cm'], b['s_at_6_cm'])
            for name, other in (MODES, MODES[::-1]) for a, b in zip(
                trials[name]['ray5']['frames'][:2], trials[other]['native']['frames'][:2], strict=True)),
        'both_coordinates_leave_some_terminal_length_gap': any(
            trials[name]['rays4_and_5']['frames'][0]['lip_cell_cm'] != trials[other]['native']['frames'][0]['lip_cell_cm']
            for name, other in (MODES, MODES[::-1])),
    }
    midpoint = midpoint_report(m['first_accumulation_difference_ray'],
                               {name: geometry.replay_lengths(base[name][0], m['internal_sample_rate_hz']) for name in MODES})
    return {'checks': checks | {'full_pcm_and_plan_verified': all(pcm_checks),
                                'native_rounding_midpoint_verified': all(
                                    midpoint[key] for key in ('adjacent_float64_values', 'straddles', 'rounded_sums_match'))},
            'hypotheses': hypotheses, 'native_midpoint_at_ray6': midpoint, 'trials': trials,
            'paired_pcm_difference': comparisons}


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
    geom, load_run, render = (tsp.open_run(study[key], revision) for key in ('geometry', 'lip_load', 'render'))
    spec = tsp.verified_path(render, 'artifacts/candidate-short-128.json')
    inputs = [CASE, Path(__file__).resolve(), spec, song.PROBE, observer.SNAPSHOT,
              *(Path(module.__file__) for module in (geometry, load, prior, area, center, observer, load.observer)),
              Path(midpoint_report.__code__.co_filename), load.observer.UPPER_PATCH, load.observer.LOCAL_PATCH,
              *geometry.CANDIDATE_TEST_CASES, *prior.prefix.capture_dependencies(),
              *(upper / name for name in geometry.UPPER_GEOMETRY),
              *(upper / 'crates/chimera/tests' / name for name in
                ('golden_geometry.rs', 'geometry_continuity.rs', 'common/mod.rs', 'golden/geometry.json')),
              *(run[0] / 'manifest.json' for run in (geom, load_run, render)),
              *(tsp.verified_path(geom, f'artifacts/{name}') for name in ('upstream.jsonl', 'candidate.jsonl', 'pcm-digests.json')),
              tsp.verified_path(load_run, 'artifacts/lip-observations.json')]

    def measure(out, execute):
        capture(study, spec, geom, out, execute)
        return analyze(study, out, geom, load_run)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
