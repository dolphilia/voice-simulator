"""唇前端のx座標の体型変換を1箇所だけ切り替えて比較する。"""

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_lip_area_origin as area
import measure_tsp_stressed_vowel_formants as tsp
import tsp_fk61_lip_front_observation as observer
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import DICT, LOCAL, PROBE
from measure_tsp_fk61_lip_onset import CONFIG, EMBEDDED_DICTIONARY, TRACE_TOOL, copy_inputs, normal_pcm, pcm_digest
from measure_tsp_fk61_lip_volume_increment import CLI_DICT, RAMP_TEST, pcm_delta
from measure_tsp_fk61_pcm_first_difference import archived_pcm
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-lip-front-origin.json'
MODES = ('upstream', 'candidate', 'trial')
FRONT = ('template_x_cm', 'scaled_x_cm', 'front_x_cm', 'upper_edge_x_cm', 'lower_edge_x_cm')


def capture(study, spec, config, archived, out, execute, *, observation=observer, scratch_prefix='fk61-front-'):
    settings = study['measurement']
    text = tsp.read(spec)['speech_voice']['input']['text']
    f0 = config['body']['female']['base_f0_hz']
    snapshots, proof = {}, {}
    with TemporaryDirectory(prefix=scratch_prefix, dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        upper = scratch / 'upstream'
        upper.mkdir()
        archive = scratch / 'fixed.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(upper)])
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        copy_inputs([PROBE, area.observer.SNAPSHOT], upper)
        for name in MODES:
            fixed, trial = name == 'upstream', name == 'trial'
            root = upper if fixed else scratch / name
            if not fixed:
                copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, CLI_DICT, RAMP_TEST,
                             LOCAL, TRACE_TOOL, area.observer.SNAPSHOT], root)
            if trial:
                observation.apply_trial(root)
            original = UPSTREAM if fixed else root if trial else WORKSPACE
            flags = ('--offline', '--target-dir', str(scratch / f'{name}-target'))
            ordinary = normal_pcm('upstream' if fixed else 'candidate', original, flags, spec, text,
                                  scratch / f'{name}.wav', settings, execute)
            if fixed:
                execute(['cargo', 'test', '--locked', '--release', '-p', 'chimera', *flags,
                         '--test', 'geometry_continuity', 'no_area_jumps_as_the_lower_lip_tucks_for_f'],
                        cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
            if trial:
                execute(['cargo', 'test', '--locked', '--release', '-p', 'vocal-core', *flags,
                         '--test', 'geometry_ramp'], cwd=root, stdout=out / 'trial-tests.log')
            source = observation.prepare(root, fixed, settings['completed_frames'], trial=trial)
            probe = build_upstream_probe(source, scratch, execute, upstream=root, lto='fat' if fixed else 'off',
                                        package='chimera' if fixed else 'vocal-core', extra_libraries=('serde_json',),
                                        cargo_args=flags, rustc_args=('--cfg', 'lip_upstream') if fixed else ())
            trace, pcm, stages = (scratch / f'{name}.{suffix}' for suffix in ('trace', 'pcm', 'stage'))
            args = [str(probe), str(spec), str(dictionary)]
            if fixed:
                args.extend(map(str, (trace, pcm, scratch / 'plan.json')))
            else:
                args.extend(['0', str(settings['initial_f0_hz']), str(f0), *map(str, (trace, pcm, stages))])
            jsonl = out / f'{name}.jsonl'
            execute(args, stdout=jsonl)
            observed = np.fromfile(pcm, dtype='<f4')
            snapshots[name] = area.read_snapshots(jsonl, settings['completed_frames'])
            proof[name] = {'ordinary': pcm_digest(ordinary), 'probe': pcm_digest(observed),
                           'ordinary_equal': bool(bit_equal(ordinary, observed))}
            if trial:
                np.savez_compressed(out / 'trial-pcm.npz', pcm=observed)
            else:
                proof[name].update(archive=pcm_digest(archived[name]),
                                   archive_equal=bool(bit_equal(ordinary, archived[name])))
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    return snapshots, proof


def replay_front(row, fixed_order):
    scale, _, _, _ = row['area_inputs']
    _, protrusion, spread, labiodental = row['lip_controls']
    if labiodental != 0.0:
        raise ValueError('今回の独立計算は唇と歯の引き込みがない時刻を対象とします')
    template = 8.15 + 0.12 * (1.0 - min(1.0, max(0.0, spread)))
    stride = template - 0.5
    reduced = 0.5 + stride * 0.86 if fixed_order else template - stride * 0.14
    scaled = reduced * scale
    front = scaled + 0.95 * (min(1.6, max(-0.2, protrusion)) * scale)
    return reduced, [template, scaled, front, front - 0.15 * scale, front - 0.25 * scale]


def replay_rays(row, coordinates, indices):
    scale, _, teeth, _ = row['area_inputs']
    aperture = row['lip_controls'][0] * scale
    edge = min(coordinates[-2:])
    start = teeth + 0.03 * scale
    end = max(start + 0.3 * scale, edge - 0.04 * scale)
    front_rays = [i for i, g in enumerate(row['grid']) if g[2] == 3]
    if len(front_rays) != 6:
        raise ValueError('口唇前方の6本の測定線を照合できません')
    replayed = []
    for index in indices:
        g = row['grid'][index].copy()
        x = start + (end - start) * (front_rays.index(index) / (len(front_rays) - 1))
        depth = max(0.0, edge - x)
        cap = max(0.0, aperture + depth * depth / (1.2 * scale))
        g[9] = x
        g[4] = min(g[3], cap)
        a, weight = area.front_area(g, row['area_inputs'])
        replayed.append({'index': index, 'x_cm': x, 'depth_cm': depth, 'ray_gap_cm': g[3],
                         'cap_cm': cap, 'gap_cm': g[4], 'area_cm2': a, 'lip_weight': weight})
    return {'start_cm': start, 'end_cm': end, 'active_edge_x_cm': edge, 'rays': replayed}


def measure_frame(snapshots, baseline, frame, indices):
    variants = {}
    previous_keys = ('raw', 'limited', 'target', 'current', 'grid', 'area_inputs')
    for name in MODES:
        row = snapshots[name][frame]
        reduced, coords = replay_front(row, name != 'candidate')
        predicted = replay_rays(row, coords, indices)
        ray_area_matches, ray_geometry_matches = True, True
        for ray in predicted['rays']:
            g = row['grid'][ray['index']]
            ray_geometry_matches = ray_geometry_matches and (
                ray['x_cm'] == g[9] and ray['gap_cm'] == g[4] and ray['cap_cm'] < g[3])
            ray_area_matches = ray_area_matches and abs(ray['area_cm2'] - g[1]) <= 5e-16
        variants[name] = {
            'controls': row['lip_controls'], 'unscaled_body_x_cm': reduced,
            'coordinates': dict(zip(FRONT, row['front_coordinates'], strict=True)),
            'formula_reproduces_coordinates': coords == row['front_coordinates'],
            'replay': predicted, 'ray_geometry_matches': ray_geometry_matches, 'ray_area_matches': ray_area_matches,
            'rays': [{'index': i, 'midpoint_x_cm': row['grid'][i][9],
                      'contact_gap_cm': row['grid'][i][4], 'area_cm2': row['grid'][i][1]} for i in indices],
            'local_cell': row['raw'], 'replayed_cell': area.resample(row, row['grid'])['cell'],
            'prior_geometry_matches': name == 'trial' or all(row[key] == baseline[name][frame][key]
                                                           for key in previous_keys),
        }
    return variants


def evaluate(study, snapshots, baseline, archive, proof, trial_pcm):
    settings = study['measurement']
    frames = {str(frame): measure_frame(snapshots, baseline, frame, settings['rays'])
              for frame in settings['completed_frames']}
    initial = frames['0']
    upper, candidate, trial = (initial[name] for name in MODES)
    controls_equal = upper['controls'] == candidate['controls'] == trial['controls']
    differences = {
        'upstream_to_candidate': pcm_delta(archive['upstream'], archive['candidate']),
        'upstream_to_trial': pcm_delta(archive['upstream'], trial_pcm),
        'candidate_to_trial': pcm_delta(archive['candidate'], trial_pcm),
    }
    onset = differences['upstream_to_trial']['first_unequal_sample']
    roots = initial['candidate']['coordinates']
    keys = [key for key in FRONT if roots[key] != upper['coordinates'][key]]
    variants = [variant for f in frames.values() for variant in f.values()]
    return {
        'checks': {
            'standard_and_trial_pcm_verified': (
                all(proof[name]['ordinary_equal'] and proof[name]['ordinary'] == proof[name]['probe']
                    and proof[name]['ordinary']['frames'] == settings['frames'] for name in MODES)
                and all(proof[name]['archive_equal'] and proof[name]['ordinary'] == proof[name]['archive']
                        == pcm_digest(archive[name]) for name in archive)
                and proof['trial']['ordinary'] == pcm_digest(trial_pcm)),
            'observed_prior_geometry_matches': all(row['prior_geometry_matches'] for row in variants),
            'independent_lip_coordinates_contact_area_and_cells': all(
                row['formula_reproduces_coordinates'] and row['ray_geometry_matches'] and row['ray_area_matches']
                and row['local_cell'] == row['replayed_cell'] for row in variants),
        },
        'predictions': {
            'first_coordinate_delta_comes_from_equivalent_body_transform': (
                controls_equal and all(snapshots[name][0]['area_inputs'][0] == snapshots['upstream'][0]['area_inputs'][0]
                                       for name in MODES)
                and upper['unscaled_body_x_cm'] != candidate['unscaled_body_x_cm']
                and keys[:1] == ['scaled_x_cm'] and trial['coordinates'] == upper['coordinates']),
            'front_transform_trial_matches_initial_contact_and_cell': (
                trial['rays'] == upper['rays'] and trial['local_cell'] == upper['local_cell']),
            'first_pcm_difference_moves_later': (
                onset is None or onset > differences['upstream_to_candidate']['first_unequal_sample']),
        },
        'first_coordinate_difference': keys[0] if keys else None,
        'observations': frames, 'pcm': differences,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    geometry, matched = (tsp.open_run(study[key], rev) for key in ('geometry', 'matched'))
    settings, settings_path = saved_case(geometry, area.CASE)
    config, config_path = saved_case(matched, CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_path = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    baseline_paths = {name: tsp.verified_path(geometry, f'artifacts/{name}.jsonl') for name in ('upstream', 'candidate')}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(area.__file__),
              Path(observer.area.__file__), observer.area.SNAPSHOT, EMBEDDED_DICTIONARY, DICT, CLI_DICT, RAMP_TEST,
              LOCAL, PROBE, TRACE_TOOL, settings_path, config_path, spec, pcm_path, *baseline_paths.values(),
              *(run[0] / 'manifest.json' for run in (geometry, matched)), *candidate_sources(),
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/anatomy/human.rs',
                  'crates/chimera/src/anatomy/geom.rs', 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/tests/geometry_continuity.rs')),
              *(WORKSPACE / 'tools' / name for name in ('measure_tsp_fk61_lip_onset.py',
                   'tsp_fk61_lip_observation.py', 'measure_tsp_fk61_lip_volume_increment.py',
                   'measure_tsp_fk61_pcm_first_difference.py', 'measure_uniform_tube.py'))]

    def measure(out, execute):
        archive = archived_pcm(pcm_path, uid)
        observed, proof = capture(study, spec, config, archive, out, execute)
        baseline = {name: area.read_snapshots(path, settings['measurement']['completed_frames'])
                    for name, path in baseline_paths.items()}
        with np.load(out / 'trial-pcm.npz', allow_pickle=False) as recorded:
            return evaluate(study, observed, baseline, archive, proof, recorded['pcm'])

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
