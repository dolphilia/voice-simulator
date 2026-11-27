"""CSDの咽頭セル7へ渡す初期面積と最初の目標面積を切り分ける。"""

import argparse
import os
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_csd_en001a_centerline_coordinate_swap as centerline


geometry, load, prior = centerline.geometry, centerline.load, centerline.prior
lip, tsp, radiation, song, area = geometry.lip, geometry.tsp, geometry.radiation, geometry.song, geometry.area
edit, insert = geometry.observer.edit, geometry.observer.insert_before
CASE = radiation.WORKSPACE / 'cases/csd-en001a-pharynx-cell7-source.json'
MODES, FILES = centerline.MODES, centerline.FILES
AREA_MASK = 'CHIMERA_CSD_PHARYNX_MASK'


def target_cell(row, cell, count):
    bounds = {'origin_cm': 0.0, 'end_cm': row['origin_cm'], 'oral_cells': count}
    return area.resample(bounds, row['grid'], index_from_end=count - cell)['cell']


def area_injection(cell, donor, array):
    values = [struct.unpack('<Q', struct.pack('<d', value))[0] for value in donor]
    return f'''fn probe_pharynx_area(initial: bool, cells: &mut {array}) {{
    let phase = if initial {{ 0 }} else {{ 1 }};
    if PROBE_PHARYNX_MASK.get() & (1 << phase) != 0 {{
        let value = [f64::from_bits(0x{values[0]:016x}), f64::from_bits(0x{values[1]:016x})][phase];
        cells[{cell}]{'.area_cm2' if array == '[TractCell]' else ''} = value;
    }}
}}
'''


def patch_pharynx(root, fixed, cell, donor):
    names = (('crates/chimera/src/voice/human_airway.rs',) if fixed else (
        'crates/vocal-core/src/airway/tract_control.rs', 'crates/vocal-core/src/airway/human.rs',
        'crates/vocal-core/src/voice.rs'))
    original = {name: (root / name).read_text() for name in names}
    model = 'HumanAirway' if fixed else 'SagittalModel'
    path = root / names[0]
    with path.open('a') as out:
        out.write(f'''
std::thread_local! {{
    static PROBE_PHARYNX_MASK: std::cell::Cell<u8> = const {{ std::cell::Cell::new(0) }};
}}

impl {model} {{
    pub fn probe_pharynx_mask(mask: u8) {{
        PROBE_PHARYNX_MASK.set(mask);
    }}
}}

{area_injection(cell, donor, '[f64]' if fixed else '[TractCell]')}
''')
    if fixed:
        edit(path, '    pub probe_lip_raw: [f64; 2],',
             '    pub probe_lip_raw: [f64; 2],\n    pub probe_raw_pharynx: Vec<[f64; 2]>,')
        edit(path, '            probe_lip_raw: [0.0; 2],',
             '            probe_lip_raw: [0.0; 2],\n            probe_raw_pharynx: Vec::new(),')
        insert(path, '        self.probe_lip_raw =', '''        self.probe_raw_pharynx.clear();
        self.probe_raw_pharynx.extend(self.ph_areas.iter().zip(&self.ph_min).map(|(&a, &minimum)| [a, minimum]));
''')
        insert(path, '        self.net.set_tube_targets(self.pharynx,', '''        probe_pharynx_area(dt == 0.0, &mut self.ph_areas);
''')
    else:
        insert(path, 'use super::SOUND_SPEED;', 'use crate::anatomy::TractCell;\n')
        edit(path, '        let current = geometry(', '        let mut current = geometry(')
        insert(path, '        Ok(Self {\n            model,',
               '        probe_pharynx_area(true, &mut current.limited.pharynx.cells);\n')
        for baseline, dt in (('self.current.limited', 'dt'), ('self.baseline', 'self.dt')):
            marker = f'        next.limit_against(&{baseline}, {dt});'
            edit(path, marker, marker + '\n        probe_pharynx_area(false, &mut next.limited.pharynx.cells);')
        insert(root / names[1], '    pub fn probe_lip_target(&self)', '''    pub fn probe_pharynx_targets(&self) -> Vec<[f64; 3]> {
        self.tubes[1].nodes.clone().map(|node| {
            let [area, minimum] = self.target_areas_cm2[node];
            [area, minimum, self.target_lengths_cm[node]]
        }).collect()
    }

''')
        edit(root / names[2], 'self.voice.airway.network.probe_lip_node = Some(self.voice.airway.lips);',
             f'self.voice.airway.network.probe_lip_node = Some(self.voice.airway.tubes[1].nodes.start + {cell});')
    snapshot = root / 'tools' / geometry.observer.SNAPSHOT.name
    start = snapshot.read_text()
    if fixed:
        insert(snapshot, '    let end = airway.or_areas.len() - 1;', '''    let pharynx = json!({
        "raw": airway.probe_raw_pharynx,
        "target": (0..airway.n_ph).map(|i| net.probe_lip_target(airway.pharynx.node(i))).collect::<Vec<_>>(),
        "current": (0..airway.n_ph).map(|i| {
            let n = airway.pharynx.node(i);
            [net.area[n], net.amin[n], net.dx[n]]
        }).collect::<Vec<_>>(),
    });
''')
    else:
        insert(snapshot, '    let current = airway.network.section(airway.lips);', '''    let pharynx = json!({
        "raw": targets.raw.pharynx.cells.iter().map(|c| [c.area_cm2, c.minimum_area_cm2]).collect::<Vec<_>>(),
        "target": airway.probe_pharynx_targets(),
        "current": airway.tubes[1].nodes.clone().map(|n| {
            let c = airway.network.section(n);
            [c.area_cm2, c.minimum_area_cm2, c.length_cm]
        }).collect::<Vec<_>>(),
    });
''')
    data = snapshot.read_text()
    if data.count('"grid": grid,') != 2:
        raise ValueError('両版の断面観測の挿入箇所を確認できません')
    snapshot.write_text(data.replace('"grid": grid,', '"grid": grid, "pharynx": pharynx,'))
    lips = 'air.oral.last_node()' if fixed else 'air.lips'
    edit(snapshot, f'''        let lips = {lips};
        tract["load_pair"] = json!((0..2).map(|i| net.probe_lip_pair[i].iter()
            .chain(&net.probe_lip_geometry[i]).copied().chain([lips as f64])
            .chain(net.probe_lip_target).collect::<Vec<_>>()).collect::<Vec<_>>());''', '''        tract["pharynx_node"] = json!(net.probe_lip_node);
        tract["volume_pair"] = json!(net.probe_lip_geometry);''')
    return ''.join(prior.diff(original[name], root / name, name) for name in names) + prior.diff(
        start, snapshot, 'tools/' + snapshot.name)


def patch_entry(path, fixed, factor, reset, cell):
    original = path.read_text()
    centerline.patch_entry(path, fixed, factor, reset)
    if fixed:
        geom = 'chimera::anatomy::human::HumanVocalTract'
        airway = 'chimera::voice::human_airway::HumanAirway'
        activate = '        voice.airway.apply(&voice.artic.x, 0.0);'
        edit(path, '    voice.airway.net.probe_lip_node = Some(voice.airway.oral.last_node());',
             f'    voice.airway.net.probe_lip_node = Some(voice.airway.pharynx.node({cell}));')
        name = 'tools/' + song.PROBE.name
    else:
        geom = airway = 'vocal_core::anatomy::SagittalModel'
        activate = '    let mut voice = ArticulatedVoice::for_speech_with_body('
        name = prior.RESEARCH
    indent = ' ' * (len(activate) - len(activate.lstrip()))
    setting = f'std::env::var("{AREA_MASK}").ok().and_then(|value| value.parse().ok()).unwrap_or(0)'
    insert(path, activate, f'{indent}{airway}::probe_pharynx_mask({setting});\n')
    stop = f'{geom}::probe_axial_swap(0);'
    edit(path, stop, stop + f'\n{indent}    {airway}::probe_pharynx_mask(0);')
    return prior.diff(original, path, name)


def parse_reference(run):
    return tsp.read(tsp.verified_path(run, 'artifacts/observations.json'))


def capture(study, spec, reference, out, execute, *, block_observer=None, render_observer=None):
    m = study['measurement']
    frames, cell, ray = (m[key] for key in ('completed_frames', 'pharynx_cell_index', 'coordinate_exchange_ray'))
    factor = m['internal_sample_rate_hz'] // m['sample_rate_hz']
    baseline = parse_reference(reference)
    snapshots, proof, pcm = {}, {}, {}
    with TemporaryDirectory(prefix='csd-pharynx-cell7-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        for name, source in (MODES, MODES[::-1]):
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
                         'golden_geometry', '--test', 'airway_adversarial'], cwd=root, stdout=test_log)
            else:
                lip.copy_inputs((*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY,
                                 radiation.WORKSPACE / 'data/cmudict.txt.gz', *geometry.CANDIDATE_TEST_CASES), root)
                execute(['cargo', 'test', '--locked', '--release', *flags, '-p', 'vocal-core', '--lib',
                         'resample'], cwd=root, stdout=test_log)
            diff = load.patch_network(root, fixed, execute)
            diff += geometry.prepare_geometry(root, fixed)
            diff += centerline.patch_distances(root, fixed, {ray: baseline[source]['native']['0']['centerline'][ray][0]})
            donor = [target_cell(baseline[name]['ray5'][str(frame)], cell, m['pharynx_cells'])[0] for frame in frames[:2]]
            diff += patch_pharynx(root, fixed, cell, donor)
            if block_observer is not None:
                diff += block_observer(root, fixed)
            if fixed:
                path = root / 'tools/upstream_csd_pharynx_probe.rs'
                path.write_bytes(song.PROBE.read_bytes())
                diff += patch_entry(path, True, factor, frames[-1], cell)
                exe = lip.build_upstream_probe(path, scratch, execute, upstream=root, cargo_args=flags,
                                                extra_libraries=('serde_json',), rustc_args=('--cfg', 'lip_upstream'))
            else:
                diff += patch_entry(root / prior.RESEARCH, False, factor, frames[-1], cell)
                exe = lip.build_pcm_cli(False, root, flags, execute)
            (out / f'{name}-observation.patch').write_text(diff)
            snapshots[name], proof[name] = {}, {}
            for condition, mask in m['conditions'].items():
                distance_mask = 1 << ray if condition == 'ray5' else 0
                key = f'{name}_{condition}'
                paths = tuple(scratch / f'{key}.{ext}' for ext in ('wav', 'json', 'csv'))
                trace = scratch / f'{key}.jsonl'

                def run_command(command, *, stdout=None):
                    if command[0] == 'env':
                        command = [command[0], f'{centerline.MASK}={distance_mask}', f'{AREA_MASK}={mask}', *command[1:]]
                        if render_observer is not None:
                            command, stdout = render_observer(command, name, condition)
                        elif block_observer is not None:
                            stdout = out / f'{key}-block.csv'
                    execute(command, stdout=stdout)

                pcm[key] = load.run(exe, paths, spec, m, run_command, fixed, trace=trace)
                snapshots[name][condition] = area.read_snapshots(trace, frames)
                proof[name][condition] = {'pcm': lip.pcm_digest(pcm[key]), 'plan': tsp.read(paths[1])}
    load.save(out / 'observations.json', snapshots)
    load.save(out / 'pcm-digests.json', proof)
    np.savez_compressed(out / 'pcm.npz', **pcm)


def replay_volume(rows, cell, rate, fixed, control):
    samples = [dict(zip(load.observer.FIELDS, row, strict=True)) for row in rows[1]['volume_pair']]
    initial = rows[0]['pharynx']['current'][cell]
    target = rows[1]['pharynx']['target'][cell]
    steps = [(b - a) * (1.0 / control) for a, b in zip(initial, target, strict=True)]
    before = initial
    valid = (len(samples) == 2 and samples[0]['old_first_pole'] == samples[0]['old_second_pole'] == 0.0)
    records = []
    for sample in samples:
        next_values = [a + step for a, step in zip(before, steps, strict=True)]
        old_volume = max(sample['area_floor'], before[0]) * before[2]
        new_volume = max(sample['area_floor'], next_values[0]) * next_values[2]
        replay_input = sample | {'area_cm2': next_values[0], 'length_cm': next_values[2],
                                 'geometry_inflow_cm3_s': sample['second_pole']}
        reconstructed = lip.geometry(replay_input, rate, fixed)
        valid &= (
            before == [sample[k] for k in ('old_area', 'old_minimum', 'old_length')]
            and steps == [sample[k] for k in ('area_increment', 'minimum_increment', 'length_increment')]
            and [old_volume, new_volume, next_values[1]] == [sample[k] for k in ('old_volume', 'volume', 'minimum')]
            and reconstructed['matches_dimensions_and_volume'] and reconstructed['matches_filter']
            and reconstructed['raw'] == sample['spill'])
        records.append({'area_cm2': next_values[0], 'volume_cm3': new_volume, 'raw_cm3_s': sample['spill'],
                        'smoothed_cm3_s': sample['second_pole']})
        before = next_values
    return records, valid and before == rows[1]['pharynx']['current'][cell]


def validate_geometry(m, data, native, ray5, archived, condition, mask):
    cell, count = m['pharynx_cell_index'], m['pharynx_cells']
    frames = [str(i) for i in m['completed_frames']]
    basis = 'ray5' if condition == 'ray5' else 'native'
    centers_match = all(data[frame][key] == archived[basis][frame][key]
                        for frame in frames for key in ('grid', 'centerline'))
    comparison = []
    for phase, frame in enumerate(frames[:2]):
        pharynx = data[frame]['pharynx']
        compare_raw = ray5[frame]['pharynx']['raw'] if condition == 'ray5' else native[frame]['pharynx']['raw']
        expect_targets = [row.copy() for row in native[frame]['pharynx']['target']]
        if condition == 'ray5':
            expect_targets = ray5[frame]['pharynx']['target']
        elif mask & (1 << phase):
            expect_targets[cell][0] = ray5[frame]['pharynx']['target'][cell][0]
        comparison.append(
            len(pharynx['raw']) == len(pharynx['target']) == count and pharynx['raw'] == compare_raw
            and pharynx['target'] == expect_targets
            and all(target_cell(data[frame], i, count) == pharynx['raw'][i] for i in (cell, cell + 1)))
    phase_shifts = [[i for i, (a, b) in enumerate(zip(native[frame]['pharynx']['raw'], data[frame]['pharynx']['raw'], strict=True))
                     if a != b] for frame in frames[:2]]
    return centers_match and all(comparison) and data[frames[-1]]['pharynx']['target'] == native[frames[-1]]['pharynx']['target'], phase_shifts


def analyze(study, out, reference):
    m = study['measurement']
    cell = m['pharynx_cell_index']
    data = tsp.read(out / 'observations.json')
    archived = parse_reference(reference)
    expected_pcm = tsp.read(tsp.verified_path(reference, 'artifacts/pcm-digests.json'))
    proof = tsp.read(out / 'pcm-digests.json')
    acoustic, geometry_checks, volume_checks, pcm_checks, hypotheses = {}, [], [], [], {}
    with np.load(out / 'pcm.npz', allow_pickle=False) as waves:
        for name in MODES:
            native, ray5 = data[name]['native'], data[name]['ray5']
            original = waves[f'{name}_native']
            swapped = waves[f'{name}_ray5']
            acoustic[name] = {}
            for condition, mask in m['conditions'].items():
                trial = data[name][condition]
                pair = [trial[str(frame)] for frame in m['completed_frames'][:2]]
                valid, area_shifts = validate_geometry(m, trial, native, ray5, archived[name], condition, mask)
                geometry_checks.append(valid)
                volume, checked = replay_volume(pair, cell, m['internal_sample_rate_hz'], name == 'upstream',
                                               m['control_internal_samples'])
                volume_checks.append(checked)
                wave = waves[f'{name}_{condition}']
                p = proof[name][condition]
                pcm_checks.append(
                    len(wave) == m['frames'] and wave.dtype == np.dtype('<f4') and bool(np.isfinite(wave).all())
                    and p['pcm'] == lip.pcm_digest(wave) and p['plan'] == expected_pcm[name]['native']['plan']
                    and (condition not in ('native', 'ray5') or p == expected_pcm[name][condition]))
                focus = m['maxima_frame']
                acoustic[name][condition] = {
                    'raw_cells_changed': area_shifts,
                    'raw_area_cm2': [row['pharynx']['raw'][cell] for row in pair],
                    'effective_area_cm2': [row['pharynx']['target'][cell][0] for row in pair],
                    'first_samples': volume, 'pcm_equals_ray5': lip.bit_equal(wave, swapped),
                    'pcm_to_native': prior.full.metrics(wave.astype(np.float64) - original),
                    'pcm_at_focus': float(wave[focus]),
                }
            rows = acoustic[name]
            hypotheses[name] = {
                'ray5_changes_only_pharynx_mean_area_7': rows['ray5']['raw_cells_changed'] == [[cell], [cell]]
                    and all(a[1] == b[1] for a, b in zip(rows['native']['raw_area_cm2'], rows['ray5']['raw_area_cm2'], strict=True)),
                'target_only_does_not_affect_first_raw_volume_source': rows['target_only']['first_samples'][0]['raw_cm3_s']
                    == rows['native']['first_samples'][0]['raw_cm3_s'],
                'both_area_endpoints_reproduce_ray5_pcm': rows['initial_and_target']['pcm_equals_ray5'],
            }
    return {'checks': {
        'centerline_resampling_single_cell_exchange_and_reset_verified': all(geometry_checks),
        'first_cell_volumes_and_source_replayed': all(volume_checks),
        'full_pcm_and_plans_verified': all(pcm_checks),
    }, 'hypotheses_by_side': hypotheses, 'trials': acoustic}


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
    reference, render = (tsp.open_run(study[key], revision) for key in ('centerline', 'render'))
    spec = tsp.verified_path(render, 'artifacts/candidate-short-128.json')
    inputs = [CASE, Path(__file__).resolve(), spec, song.PROBE, geometry.observer.SNAPSHOT,
              *(Path(m.__file__) for m in (centerline, geometry, load, area, geometry.center, geometry.observer, load.observer)),
              load.observer.UPPER_PATCH, load.observer.LOCAL_PATCH,
              *geometry.CANDIDATE_TEST_CASES, *prior.prefix.capture_dependencies(),
              *(upper / name for name in geometry.UPPER_GEOMETRY),
              *(upper / 'crates/chimera/tests' / name for name in
                ('golden_geometry.rs', 'airway_adversarial.rs', 'common/mod.rs', 'golden/geometry.json')),
              *(run[0] / 'manifest.json' for run in (reference, render)),
              *(tsp.verified_path(reference, f'artifacts/{name}') for name in ('observations.json', 'pcm-digests.json'))]

    def measure(out, execute):
        capture(study, spec, reference, out, execute)
        return analyze(study, out, reference)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
