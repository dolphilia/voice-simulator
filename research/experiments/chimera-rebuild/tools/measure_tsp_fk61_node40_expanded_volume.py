"""節点40の1内部標本で体積差の展開式を通常発話に適用する。"""

import argparse
from difflib import unified_diff
from fractions import Fraction
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_oral_onset_inflow as oral
from measure_duet_mixed_volume_difference import EXPANSION, volume_flows
from measure_tsp_fk61_lip_volume_increment import pcm_delta
from tsp_fk61_lip_observation import edit, insert_before


first_diff, drive, load, terminal = oral.first_diff, oral.drive, oral.load, oral.terminal
radiation, tsp, lip, pcm = oral.radiation, oral.tsp, oral.lip, oral.pcm
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-node40-expanded-volume.json'
GEOMETRY = 'crates/vocal-core/src/airway/network/geometry.rs'
MODES = ('baseline', 'expanded')
GEOMETRY_FIELDS = ('area_cm2', 'minimum_cm2', 'length_cm', 'old_volume_cm3', 'volume_cm3')
SAVED_FILES = ('render.npz', 'pcm-digests.json', 'node40-volume.patch',
               *(f'{mode}-{tag}' for mode in MODES for tag in
                 ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv')))


def patch_volume(root, measure):
    path = root / GEOMETRY
    original = path.read_text()
    edit(path, 'use super::{SOUND_SPEED, Section, trim_tiny};',
         'use super::{MIN_CELL_AREA_CM2, SOUND_SPEED, Section, trim_tiny};')
    edit(path, '    remaining: usize,', '    remaining: usize,\n    research_steps: usize,')
    edit(path, '            remaining: 0,', '            remaining: 0,\n            research_steps: 0,')
    insert_before(path, '        if !self.enabled {', '''        let research_sample = self.research_steps;
        self.research_steps += 1;
''')
    insert_before(path, '                section.area_cm2 = (section.area_cm2 + cell.area_increment_cm2).max(0.0);',
                  '''                let old_area = section.area_cm2.max(MIN_CELL_AREA_CM2);
                let old_length = section.length_cm;
''')
    raw = '                let raw = (cell.volume_cm3 - next_volume) / dt;'
    edit(path, raw, f'''                // 指定した1セル・1標本でだけ体積差の式を切り替える。
                let raw = if i == {measure['changed_node']} && research_sample == {measure['changed_internal_sample']} {{
                    let new_area = section.area_cm2.max(MIN_CELL_AREA_CM2);
                    let displaced_volume = (old_area - new_area) * old_length
                        + new_area * (old_length - section.length_cm);
                    displaced_volume / dt
                }} else {{
                    (cell.volume_cm3 - next_volume) / dt
                }};''')
    return ''.join(unified_diff(original.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                               fromfile='a/' + GEOMETRY, tofile='b/' + GEOMETRY))


def retain_mouth_for_full_utterance(source):
    insert_before(source, '    for frame in 0..frames {', '''    let mouth_path = std::env::var_os("CHIMERA_PROBE_FULL_MOUTH")
        .ok_or("口端流量全体の保存先がありません")?;
    let mut mouth = BufWriter::new(File::create_new(mouth_path)?);
''')
    insert_before(source, '        let mut radiation_pair = [0.0; 2];', '        let mut mouth_pair = [0.0; 2];\n')
    insert_before(source, '            let radiation = sample.radiation.radiation_flow_derivative_cm3_s2;',
                  '            mouth_pair = [mouth_pair[1], sample.lip_flow_cm3_s];\n')
    insert_before(source, '        pcm.write_all(&out.pcm.to_le_bytes())?;',
                  '        tsp_fine_trace::write_row(&mut mouth, &mouth_pair)?;\n')
    insert_before(source, '    output.flush()?;', '    mouth.flush()?;\n')


def capture(study, spec, config, out, execute, *, modes=MODES, variant_patch=patch_volume,
            patch_filename='node40-volume.patch', prepare=None, split=terminal.split_capture,
            patched_modes=None, scratch=None):
    measure = study['measurement']
    nodes = measure['nodes']
    start, stop = measure['comparison_internal_samples']
    frames = measure['prefix_frames']
    text = tsp.read(spec)['speech_voice']['input']['text']
    base_f0 = config['body']['female']['base_f0_hz']
    if patched_modes is None:
        patched_modes = modes[1:]
    states, proof = {}, {}
    with TemporaryDirectory(prefix='fk61-node40-volume-', dir=scratch or out.parent / 'tmp') as directory:
        temp = Path(directory)
        dictionary = temp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(lip.DICT.read_bytes()))
        for mode in modes:
            root = temp / mode
            lip.copy_inputs([*radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.LOCAL, lip.TRACE_TOOL,
                             radiation.WORKSPACE / 'data/cmudict.txt.gz',
                             radiation.WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs'], root)
            load.patch_trial(root)
            if mode in patched_modes:
                (out / patch_filename).write_text(variant_patch(root, measure))
            flags = ('--offline', '--target-dir', str(temp / f'{mode}-target'))
            ordinary = lip.normal_pcm(mode, root, flags, spec, text, temp / f'{mode}.wav', measure, execute)
            execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-core', *flags, '--test', 'geometry_ramp'],
                    cwd=root, stdout=out / f'{mode}-tests.log')
            if prepare is None:
                source = terminal.observer.prepare(root, False, (start, stop), execute, cell_indices=nodes,
                                                   branch_left_indices=nodes[:-1], wall_indices=nodes[1:],
                                                   compliance_indices=measure['pressure_nodes'])
            else:
                source = prepare(root, False, (start, stop), execute, measure=measure)
            retain_mouth_for_full_utterance(source)
            probe = lip.build_upstream_probe(source, temp, execute, upstream=root, lto='off', package='vocal-core',
                                            extra_libraries=('serde_json',), cargo_args=flags)
            trace, probe_pcm, output, mouth = (temp / f'{mode}.{suffix}' for suffix in ('source', 'pcm', 'output', 'mouth'))
            execute(['env', f'CHIMERA_PROBE_LIP_WINDOW={out / f"{mode}-lip.f64le"}', f'CHIMERA_PROBE_FULL_MOUTH={mouth}',
                     str(probe), str(spec), str(dictionary), str(frames), str(measure['initial_f0_hz']), str(base_f0),
                     *map(str, (trace, probe_pcm, output))], stdout=out / f'{mode}-nodes.csv')
            split(out, mode)
            observed = np.fromfile(probe_pcm, dtype='<f4')
            proof[mode] = {'ordinary': lip.pcm_digest(ordinary), 'probe': lip.pcm_digest(observed),
                           'bit_equal': bool(lip.bit_equal(ordinary, observed))}
            states.update({
                f'{mode}_source': np.fromfile(trace, dtype='<f8').reshape(frames * 2, len(radiation.FIELDS)),
                f'{mode}_output': np.fromfile(output, dtype='<f8').reshape(frames, 7),
                f'{mode}_pcm': observed,
                f'{mode}_mouth': np.fromfile(mouth, dtype='<f8').reshape(measure['frames'] * 2),
            })
    np.savez_compressed(out / 'render.npz', **states)
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def output_checks(states, mode, rate, config, gain, coefficients, *, fixed=False):
    components = dict(zip(radiation.FIELDS, states[f'{mode}_source'].T, strict=True))
    total, derivative = radiation.radiation_from_components(components, rate, fixed)
    stages = states[f'{mode}_output']
    independent, samples = pcm.replay(derivative, coefficients, gain, config)
    return all((
        load.same_bits(total, components['total_cm3_s']),
        load.same_bits(derivative, components[radiation.RADIATION]),
        load.same_bits(derivative, stages[:, :2].ravel()),
        load.same_bits(independent, stages[:, 2:]),
        lip.bit_equal(samples, states[f'{mode}_pcm'][:len(samples)]),
        load.same_bits(components['lip_cm3_s'], states[f'{mode}_mouth'][:len(derivative)]),
    ))


def analyze(study, out, prior, archived, config, gain, coefficients, proof):
    measure = study['measurement']
    rate, frames = measure['internal_sample_rate_hz'], measure['frames']
    target = (measure['changed_internal_sample'], measure['changed_node'])
    n, node = target
    recorded = {mode: oral.read_capture(out, mode, measure) for mode in MODES}
    saved = oral.read_capture(prior, 'trial', measure)
    baseline, variant = (recorded[mode] for mode in MODES)
    old, new, exact = volume_flows(baseline['cells'][n - 1, node], baseline['cells'][target], 1 / rate)
    volume_errors = {mode: float(abs(Fraction(flow) - exact)) for mode, flow in zip(MODES, (old, new), strict=True)}
    replay_errors = {mode: oral.local_replay(recorded[mode], measure, False,
                                            raw_overrides={target: new} if mode == 'expanded' else None)
                     for mode in MODES}
    spills = [[row['cells'][key]['spill_cm3_s'] for key in baseline['cells']] for row in (baseline, variant)]
    changed_spills = [list(key) for key, a, b in zip(baseline['cells'], *spills, strict=True) if a != b]
    geometry_equal = all(
        load.same_bits(baseline['grid'][key], variant['grid'][key]) for key in GEOMETRY_FIELDS)
    shared_capture = all(json.dumps(list(baseline[key].items())) == json.dumps(list(saved[key].items()))
                         for key in ('cells', 'branch', 'wall', 'compliance', 'loads'))
    with np.load(out / 'render.npz', allow_pickle=False) as data:
        states = dict(data)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as previous:
        unchanged_baseline = (
            load.same_bits(states['baseline_source'], previous['trial_source'])
            and load.same_bits(states['baseline_output'], previous['trial_output'])
            and load.same_bits(states['baseline_pcm'][:measure['prefix_frames']], previous['trial_pcm']))
        upper_mouth = previous['upstream_source'][:, radiation.FIELDS.index('lip_cm3_s')]
    reports = {
        'baseline_vs_upstream': pcm_delta(archived['upstream'], states['baseline_pcm']),
        'expanded_vs_upstream': pcm_delta(archived['upstream'], states['expanded_pcm']),
        'expanded_vs_baseline': pcm_delta(states['baseline_pcm'], states['expanded_pcm']),
    }
    original_first = reports['baseline_vs_upstream']['first_unequal_sample']
    new_first = reports['expanded_vs_upstream']['first_unequal_sample']
    mouth = {
        'expanded_vs_baseline_full': first_diff.first_change(states['baseline_mouth'], states['expanded_mouth']),
        **{f'{mode}_vs_upstream_prefix': first_diff.first_change(upper_mouth, states[f'{mode}_mouth'][:len(upper_mouth)])
           for mode in MODES},
    }
    onset = mouth['expanded_vs_baseline_full']
    output_replays = {mode: output_checks(states, mode, rate, config, gain, coefficients) for mode in MODES}
    upper_spill = oral.read_capture(prior, 'upstream', measure)['cells'][target]['spill_cm3_s']
    hypotheses = {
        'expanded_reduces_local_exact_error': volume_errors['expanded'] < volume_errors['baseline'],
        'expanded_reduces_raw_difference_from_pinned_upstream': abs(new - upper_spill) < abs(old - upper_spill),
        'mouth_difference_follows_the_intervention': onset is not None and onset['sample'] > n,
        'expanded_delays_first_pcm_difference_from_pinned_upstream': new_first is None or new_first > original_first,
        'expanded_does_not_increase_maximum_pcm_error': reports['expanded_vs_upstream']['peak_error']
                                                       <= reports['baseline_vs_upstream']['peak_error'],
    }
    checks = {
        'ordinary_and_observed_pcm_bit_exact_for_full_utterance': all(
            proof[mode]['bit_equal'] and proof[mode]['ordinary'] == proof[mode]['probe'] == lip.pcm_digest(states[f'{mode}_pcm'])
            and len(states[f'{mode}_pcm']) == frames for mode in MODES),
        'baseline_matches_all_retained_observations': (
            unchanged_baseline and shared_capture and lip.bit_equal(states['baseline_pcm'], archived['trial'])
            and original_first == measure['previous_pcm_focus_frame']),
        'single_raw_source_intervention_and_local_dynamics_replayed': (
            changed_spills == [list(target)] and geometry_equal and baseline['cells'][target]['spill_cm3_s'] == old
            and variant['cells'][target]['spill_cm3_s'] == new
            and not any(any(errors.values()) for errors in replay_errors.values())),
        'mouth_and_prefix_output_replayed': all(output_replays.values()),
        'pre_intervention_mouth_and_pcm_match': (
            load.same_bits(states['baseline_mouth'][:n], states['expanded_mouth'][:n])
            and lip.bit_equal(states['baseline_pcm'][:n//2], states['expanded_pcm'][:n//2])),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'changed_spills': changed_spills, 'replay_errors': replay_errors,
            'local_volume': {'baseline_cm3_s': old, 'expanded_cm3_s': new, 'pinned_upstream_cm3_s': upper_spill,
                             'exact_cm3_s': float(exact), 'absolute_errors_cm3_s': volume_errors},
            'focus': {mode: recorded[mode]['cells'][target] for mode in MODES},
            'mouth': mouth, 'pcm': reports}


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
    matched, bernstein, prior, output = (tsp.open_run(study[key], revision)
                                        for key in ('matched', 'bernstein', 'oral_inflow', 'coefficients'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    retained = [tsp.verified_path(prior, f'artifacts/{name}') for name in oral.SAVED_FILES]
    inputs = [CASE, Path(__file__).resolve(), Path(oral.__file__), Path(first_diff.__file__), Path(drive.__file__),
              Path(load.__file__), Path(terminal.__file__), Path(terminal.observer.__file__), Path(radiation.__file__),
              config_path, spec, reference_pcm, trial_pcm, coefficients, *retained, EXPANSION,
              *(run[0] / 'manifest.json' for run in (matched, bernstein, prior, output)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.TRACE_TOOL,
              lip.observer.LOCAL_PATCH, ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in ('tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_observation.py',
                 'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_ray43_observation.py',
                 'tsp_fk61_node_volume_observation.py', 'tsp_fk61_lower_lip_bernstein_observation.py',
                 'measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_node42_volume_source.py',
                 'measure_duet_mixed_volume_difference.py', 'measure_tsp_fk61_lip_volume_increment.py',
                 'measure_tsp_fk61_pcm_first_difference.py', 'measure_fixed_voice_glottal_branch.py',
                 'measure_fixed_voice_radiation_balance.py', 'measure_fixed_voice_release_lip_load.py',
                 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        archived = pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as base:
            archived['trial'] = base['pcm']
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        proof = capture(study, spec, config, out, execute)
        return analyze(study, out, prior[0] / 'artifacts', archived, config, gain,
                       tsp.read(coefficients)['candidate'], proof)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
