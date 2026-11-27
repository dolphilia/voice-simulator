"""上流と研究版の代表面積補間を揃えたときの体積速度とPCMを照合する。"""

import argparse
from difflib import unified_diff
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_control4992_5120_indexed_area as indexed


area_targets, geometry, oral, volume = indexed.area_targets, indexed.geometry, indexed.oral, indexed.volume
lip, load, radiation, tsp = indexed.lip, indexed.load, indexed.radiation, indexed.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control4992-5120-indexed-area-paired.json'
NETWORK = 'crates/chimera/src/airway/network.rs'
PATCH = 'upstream-indexed-area.patch'
MODES = indexed.MODES
UPPER_FILES = tuple(f'artifacts/{name}' for name in area_targets.SAVED_FILES if name.startswith('upstream-'))
RESEARCH_FILES = tuple(f'artifacts/{name}' for name in indexed.SAVED_FILES)
SAVED_FILES = (PATCH, 'render.npz', 'pcm-digests.json', *(f'{mode}-{suffix}' for mode in MODES for suffix in
    ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv', 'ramp-step.csv', 'ramp-target.csv',
     'centerline.csv', 'area-raw.csv', 'area-grid.csv')))


def patch_upstream(root, measure):
    path = root / NETWORK
    original = path.read_text()
    edit, insert = volume.edit, volume.insert_before
    nodes = measure['area_focus_nodes']
    count = measure['control_internal_samples']
    boundaries = ' | '.join(map(str, measure['area_focus_blocks']))
    saved = ', '.join(f'self.area[{node}]' for node in nodes)
    arms = '\n'.join(f'                    {node} => research_block.map(|(first, areas)| (first, areas[{i}])),'
                     for i, node in enumerate(nodes))
    edit(path, '    dx_target: Vec<f64>,', f'''    dx_target: Vec<f64>,
    research_area_sample: usize,
    research_area_block: Option<(usize, [f64; {len(nodes)}])>,''')
    edit(path, '            dx_target: Vec::new(),', '''            dx_target: Vec::new(),
            research_area_sample: 0,
            research_area_block: None,''')
    insert(path, '        let inv = 1.0 / js_max(1.0, samples as f64);', f'''        self.research_area_block = (samples == {count}
            && self.n_nodes > {max(nodes)}
            && matches!(self.research_area_sample, {boundaries}))
            .then(|| (self.research_area_sample, [{saved}]));
''')
    insert(path, '        let sq = self.squeeze_area;', f'''        let sample = self.research_area_sample;
        self.research_area_sample += 1;
        let research_block = self.research_area_block.filter(|(first, _)| sample - *first < {count});
''')
    edit(path, '                let mut a = area[k] + self.area_step[k];', f'''                let saved = match k {{
{arms}
                    _ => None,
                }};
                let mut a = if let Some((first, start)) = saved {{
                    start + (sample - first + 1) as f64 * self.area_step[k]
                }} else {{
                    area[k] + self.area_step[k]
                }};''')
    return ''.join(unified_diff(original.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                               fromfile='a/' + NETWORK, tofile='b/' + NETWORK))


def retain_mouth(source):
    insert = volume.insert_before
    insert(source, '    let mut output = BufWriter::new(File::create_new(output)?);', '''    let mouth_path =
        std::env::var_os("CHIMERA_PROBE_FULL_MOUTH").ok_or("口端流量全体の保存先がありません")?;
    let mut mouth = BufWriter::new(File::create_new(mouth_path)?);
''')
    anchor = '        #[cfg(tsp_pressure_replay)]\n        for row in &voice.probe_pressure_pair {'
    insert(source, anchor, f'''        for row in &voice.probe_source_pair {{
            tsp_fine_trace::write_row(&mut mouth, &[row[{radiation.FIELDS.index('lip_cm3_s')}]])?;
        }}
''')
    insert(source, '    output.flush()?;\n    trace.flush()?;', '    mouth.flush()?;\n')


def capture(study, spec, out, execute, *, modes=MODES, variant_patch=patch_upstream,
            patch_filename=PATCH, scratch=None):
    measure = study['measurement']
    start, stop = measure['comparison_internal_samples']
    frames = measure['prefix_frames']
    text = tsp.read(spec)['speech_voice']['input']['text']
    with TemporaryDirectory(prefix='fk61-upstream-indexed-area-', dir=scratch or out.parent / 'tmp') as directory:
        temp = Path(directory)
        archive = temp / 'upstream.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=radiation.UPSTREAM, stdout=archive)
        dictionary = temp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(lip.DICT.read_bytes()))
        states, proof = {}, {}
        for mode in modes:
            root = temp / mode
            root.mkdir()
            execute(['tar', '-xf', str(archive), '-C', str(root)])
            lip.copy_inputs([lip.PROBE, lip.TRACE_TOOL], root)
            if mode != 'baseline':
                (out / patch_filename).write_text(variant_patch(root, measure))
            flags = ('--offline', '--target-dir', str(temp / f'{mode}-target'))
            normal = lip.normal_pcm('upstream', root, flags, spec, text, temp / f'{mode}.wav', measure, execute)
            execute(['cargo', 'test', '--locked', '--release', '-p', 'chimera', *flags,
                     '--test', 'airway', '--test', 'airway_adversarial'],
                    cwd=root, stdout=out / f'{mode}-tests.log')
            for patch in (lip.OUTPUT_PATCH, lip.SOURCE_PATCH):
                execute(['git', 'apply', str(patch)], cwd=root)
            source = area_targets.prepare(root, True, (start, stop), execute, measure=measure)
            retain_mouth(source)
            probe = lip.build_upstream_probe(source, temp, execute, upstream=root, lto='fat', package='chimera',
                                            extra_libraries=('serde_json',), rustc_args=('--cfg', 'tsp_voice_probe'),
                                            cargo_args=flags)
            trace, pcm, stages, mouth = (temp / f'{mode}.{suffix}' for suffix in ('source', 'pcm', 'output', 'mouth'))
            execute(['env', f'CHIMERA_PROBE_LIP_WINDOW={out / f"{mode}-lip.f64le"}', f'CHIMERA_PROBE_FULL_MOUTH={mouth}',
                     str(probe), str(spec), str(dictionary), str(trace), str(pcm), str(temp / f'{mode}-score.json'),
                     str(frames), 'default', str(stages)], stdout=out / f'{mode}-nodes.csv')
            area_targets.split_observations(out, mode)
            observed = np.fromfile(pcm, dtype='<f4')
            proof[mode] = {'ordinary': lip.pcm_digest(normal), 'probe': lip.pcm_digest(observed),
                           'bit_equal': bool(lip.bit_equal(normal, observed))}
            states.update({
                f'{mode}_source': np.fromfile(trace, dtype='<f8').reshape(frames * 2, len(radiation.FIELDS)),
                f'{mode}_output': np.fromfile(stages, dtype='<f8').reshape(frames, 7),
                f'{mode}_pcm': observed,
                f'{mode}_mouth': np.fromfile(mouth, dtype='<f8').reshape(measure['frames'] * 2),
            })
    np.savez_compressed(out / 'render.npz', **states)
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')


def rms(values):
    return float(np.sqrt(np.mean(values ** 2)))


def metrics(reference, comparison, *, start=0, pcm=False):
    first = volume.first_diff.first_change(reference, comparison, offset=start)
    delta = comparison.astype(np.float64) - reference
    result = {'first': first, 'peak_absolute_difference': float(np.max(np.abs(delta))), 'rms_difference': rms(delta)}
    if pcm:
        result['unequal_frames'] = int(np.count_nonzero(reference.view('<u4') != comparison.view('<u4')))
    return result


def local_metrics(upper, research, measure):
    samples = measure['control_internal_samples']
    points = [(n, j) for block in measure['area_focus_blocks'] for n in range(block, block + samples)
              for j in measure['area_focus_nodes']]
    metrics_by_field = {}
    for field in ('area_cm2', 'spill_cm3_s', 'pole2_cm3_s'):
        a, b = (np.asarray([capture['cells'][key][field] for key in points]) for capture in (upper, research))
        metrics_by_field[field] = metrics(a, b)
        first = metrics_by_field[field]['first']
        if first is not None:
            first['sample'], first['node'] = points[first['sample']]
    rate = measure['internal_sample_rate_hz']
    geometry_delta = np.asarray([float(oral.exact_raw(upper, n, j, rate) - oral.exact_raw(research, n, j, rate))
                                 for n, j in points])
    raw_delta = np.asarray([upper['cells'][key]['spill_cm3_s'] - research['cells'][key]['spill_cm3_s'] for key in points])
    metrics_by_field['raw_volume_difference_decomposition'] = {
        'geometry_rms_cm3_s': rms(geometry_delta), 'residual_rms_cm3_s': rms(raw_delta - geometry_delta)}
    return metrics_by_field


def analyze(study, out, research_path, prior, archived, config, gain, coefficients):
    measure = study['measurement']
    rate, frames = (measure[k] for k in ('internal_sample_rate_hz', 'frames'))
    intervention = measure['area_focus_blocks'][0]
    upper = {mode: oral.read_capture(out, mode, measure) for mode in MODES}
    research = {mode: oral.read_capture(research_path, mode, measure) for mode in MODES}
    prior_measure = measure | {'comparison_internal_samples': measure['previous_comparison_internal_samples']}
    prior_upper = oral.read_capture(prior, 'upstream', prior_measure)
    shared = area_targets.inlet.shared_capture(prior_upper, upper['baseline'])
    steps, targets = {}, {}
    for mode in MODES:
        steps[mode], targets[mode] = indexed.read_ramps(out, mode, measure)
    ramp_errors = {mode: geometry.verify_ramps(upper[mode], steps[mode], targets[mode], measure,
                                               indexed_area=(mode == 'indexed')) for mode in MODES}
    exact, exact_errors = indexed.exact_area_checks(upper, steps, targets, measure)
    dynamics = {mode: oral.local_replay(data, measure, True) for mode, data in upper.items()}
    with np.load(out / 'render.npz', allow_pickle=False) as data, np.load(research_path / 'render.npz', allow_pickle=False) as saved:
        states, earlier = dict(data), dict(saved)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as saved:
        shared_prefix = (load.same_bits(states['baseline_source'], saved['upstream_source'])
                         and load.same_bits(states['baseline_output'], saved['upstream_output'])
                         and load.same_bits(states['baseline_pcm'][:measure['prefix_frames']], saved['upstream_pcm']))
    proof = tsp.read(out / 'pcm-digests.json')
    prior_proof = tsp.read(research_path / 'pcm-digests.json')
    comparisons = {}
    for a, b in (('baseline', 'baseline'), ('baseline', 'indexed'), ('indexed', 'baseline'), ('indexed', 'indexed')):
        row = local_metrics(upper[a], research[b], measure)
        row['mouth'] = metrics(states[f'{a}_mouth'], earlier[f'{b}_mouth'])
        row['pcm'] = metrics(states[f'{a}_pcm'], earlier[f'{b}_pcm'], pcm=True)
        precast = volume.pcm.COLUMNS.index('dc_removed')
        focus = measure['focus_frame']
        row['precast_at_focus'] = {'upstream': float(states[f'{a}_output'][focus, precast]),
                                   'research': float(earlier[f'{b}_output'][focus, precast])}
        comparisons[f'{a}:{b}'] = row
    base, paired = (comparisons[key] for key in ('baseline:baseline', 'indexed:indexed'))
    within_upper = {kind: metrics(states[f'baseline_{kind}'], states[f'indexed_{kind}'], pcm=(kind == 'pcm'))
                    for kind in ('mouth', 'pcm')}
    hypotheses = {
        'upstream_indexed_reaches_its_targets': all(row['end_residual_cm2'] == 0 for row in exact['indexed'].values()),
        'paired_indexed_reduces_peak_area_difference': paired['area_cm2']['peak_absolute_difference']
                                                       < base['area_cm2']['peak_absolute_difference'],
        'paired_indexed_reduces_raw_volume_rms': paired['spill_cm3_s']['rms_difference'] < base['spill_cm3_s']['rms_difference'],
        'paired_indexed_pcm_first_remains_2937': paired['pcm']['first'] is not None
                                                 and paired['pcm']['first']['sample'] == measure['focus_frame'],
    }
    checks = {
        'ordinary_pcm_matches_each_probe_and_archived_baselines': all(
            proof[mode]['bit_equal'] and proof[mode]['ordinary'] == lip.pcm_digest(states[f'{mode}_pcm'])
            and prior_proof[mode]['bit_equal'] and prior_proof[mode]['ordinary'] == lip.pcm_digest(earlier[f'{mode}_pcm'])
            and len(states[f'{mode}_pcm']) == len(earlier[f'{mode}_pcm']) == frames for mode in MODES)
            and load.same_bits(states['baseline_pcm'], archived['upstream']) and shared_prefix and all(shared.values()),
        'upstream_indexed_area_matches_exact_line_and_other_geometry': not exact_errors and not any(ramp_errors.values())
            and targets['baseline'] == targets['indexed'] and all(
                load.same_bits(upper['baseline']['grid'][field], upper['indexed']['grid'][field])
                for field in ('minimum_cm2', 'length_cm')),
        'upstream_volume_waves_and_output_replayed': not any(any(row.values()) for row in dynamics.values())
            and all(volume.output_checks(states, mode, rate, config, gain, coefficients['upstream'], fixed=True)
                    and volume.output_checks(earlier, mode, rate, config, gain, coefficients['candidate']) for mode in MODES),
        'upstream_mouth_and_pcm_equal_before_intervention': load.same_bits(
            states['baseline_mouth'][:intervention], states['indexed_mouth'][:intervention])
            and load.same_bits(states['baseline_pcm'][:intervention // 2], states['indexed_pcm'][:intervention // 2]),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'comparisons': comparisons, 'within_upstream': within_upper,
            'geometry': exact, 'exact_errors': exact_errors, 'ramp_errors': ramp_errors, 'dynamics_errors': dynamics}


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
    matched, output, research_run, prior = (tsp.open_run(study[key], revision)
        for key in ('matched', 'coefficients', 'previous_focus', 'original_observation'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    retained = [tsp.verified_path(research_run, name) for name in RESEARCH_FILES]
    retained += [tsp.verified_path(prior, name) for name in (*UPPER_FILES, 'artifacts/prefix.npz')]
    dependencies = ('measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_front_radiation.py',
                    'measure_tsp_fk61_lip_front_terminal_branch.py', 'measure_tsp_fk61_oral_onset_inflow.py',
                    'measure_tsp_fk61_branch_first_difference.py', 'measure_tsp_fk61_pcm2937_terminal_load.py',
                    'measure_tsp_fk61_control5504_oral_history.py', 'tsp_fk61_lip_front_radiation_observation.py',
                    'tsp_fk61_terminal_branch_observation.py', 'tsp_fk61_lip_observation.py',
                    'tsp_fk61_oral_geometry_observation.py', 'measure_tsp_fine_variation.py',
                    'measure_fixed_voice_glottal_branch.py', 'measure_uniform_tube.py')
    inputs = [CASE, Path(__file__).resolve(), Path(indexed.__file__), Path(volume.__file__), Path(geometry.__file__),
              Path(area_targets.__file__), config_path, spec, reference_pcm, coefficients, *retained,
              *(run[0] / 'manifest.json' for run in (matched, output, research_run, prior)),
              lip.PROBE, lip.TRACE_TOOL, lip.DICT, lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.UPPER_PATCH,
              *(ws / 'tools' / name for name in dependencies),
              *(upper / name for name in (NETWORK, 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera-cli/src/render.rs', 'Cargo.lock',
                  'crates/chimera/tests/airway.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        capture(study, spec, out, execute)
        archived = volume.pcm.archived_pcm(reference_pcm, uid)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, out, research_run[0] / 'artifacts', prior[0] / 'artifacts', archived,
                       config, gain, tsp.read(coefficients))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
