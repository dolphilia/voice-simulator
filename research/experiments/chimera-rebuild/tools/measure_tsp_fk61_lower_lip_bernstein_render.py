"""下唇内面の評価順を切り替えた通常レンダーを保存して照合する。"""

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_node42_volume_source as volume
import measure_tsp_fk61_ray43_intersection as ray
import tsp_fk61_lower_lip_bernstein_observation as observer
from measure_tsp_fk61_lip_volume_increment import TEST_CASES, pcm_delta


radiation, lip, tsp, pcm = volume.radiation, volume.lip, volume.tsp, volume.pcm
front = ray.front
CASE = front.WORKSPACE / 'cases/tsp-fk61-lower-lip-bernstein-render.json'
LABEL = 'bernstein'
VOLUME_FIELDS = ('volume_change_cm3', 'raw_cm3_s', 'spill_cm3_s', 'first_pole_cm3_s', 'second_pole_cm3_s')


def capture(study, config, spec, out, execute):
    measure = study['measurement']
    text = tsp.read(spec)['speech_voice']['input']['text']
    f0 = config['body']['female']['base_f0_hz']
    frames = measure['prefix_frames']
    with TemporaryDirectory(prefix='fk61-lower-bernstein-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        root = tmp / 'candidate'
        lip.copy_inputs([*front.candidate_sources(), front.EMBEDDED_DICTIONARY, front.CLI_DICT, front.LOCAL,
                         front.TRACE_TOOL, front.RAMP_TEST, front.area.observer.SNAPSHOT, *TEST_CASES], root)
        observer.ray.apply_trial(root)
        (out / 'lower-lip-evaluation.patch').write_text(observer.apply_curve(root))
        flags = ('--offline', '--target-dir', str(tmp / 'target'))
        standard = lip.normal_pcm('candidate', root, flags, spec, text, tmp / 'bernstein.wav', measure, execute)
        command = ['cargo', 'test', '--locked', '--release', '-p', 'vocal-core', *flags]
        execute([*command, '--test', 'geometry_ramp'], cwd=root, stdout=out / 'ramp-test.log')
        execute([*command, '--lib', 'anatomy::grid::tests'], cwd=root, stdout=out / 'grid-tests.log')
        source = observer.prepare(root, measure, execute)
        probe = front.build_upstream_probe(source, tmp, execute, upstream=root, lto='off', package='vocal-core',
                                           extra_libraries=('serde_json',), cargo_args=flags)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(front.DICT.read_bytes()))
        state, samples, output = (tmp / f'bernstein.{suffix}' for suffix in ('source', 'pcm', 'output'))
        mixed = out / f'{LABEL}-nodes.csv'
        execute(['env', f'CHIMERA_PROBE_LIP_WINDOW={out / f"{LABEL}-lip.f64le"}', str(probe), str(spec),
                 str(dictionary), str(frames), str(measure['initial_f0_hz']), str(f0), *map(str, (state, samples, output))],
                stdout=mixed)
        lines = mixed.read_text().splitlines(keepends=True)
        (out / f'{LABEL}.jsonl').write_text(''.join(line for line in lines if line.startswith('{')))
        mixed.write_text(''.join(line for line in lines if not line.startswith('{')))
        volume.split_capture(out, LABEL)
        observed = np.fromfile(samples, dtype='<f4')
        states = np.fromfile(state, dtype='<f8').reshape(frames * 2, len(radiation.FIELDS))
        stages = np.fromfile(output, dtype='<f8').reshape(frames, 7)
    proof = {'cli': lip.pcm_digest(standard), 'probe': lip.pcm_digest(observed),
             'bit_equal': bool(lip.bit_equal(standard, observed))}
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    np.savez_compressed(out / 'render.npz', source=states, output=stages, pcm=observed)


def analyze(study, config, gain, coefficients, out, previous, archived, baseline_prefix, baseline_volume):
    measure = study['measurement']
    rate, index, target = (measure[key] for key in ('internal_sample_rate_hz', 'grid_index', 'focus_sample'))
    focus_index = target - measure['onset_sample']
    frames = measure['completed_frames']
    recorded = volume.read_capture(out, LABEL, measure)
    rows, rebuilt, mismatches, flow_checks = volume.rebuild(measure, False, recorded)
    focus = volume.focused_events(measure, rows, rebuilt)
    revised = front.area.read_snapshots(out / f'{LABEL}.jsonl', frames)
    comparisons = {}
    for frame in frames:
        actual = revised[frame]
        old = previous['trial'][frame]
        picked = ray.replay(actual, index)
        controls = ray.lower_lip_controls(old)
        n = len(old['ray43']['lower_lip']) - 1
        expected = [ray.curve_point(controls, i / n, True) for i in range(n + 1)]
        comparisons[str(frame)] = {
            'bernstein_matches_all_lower_points': actual['ray43']['lower_lip'] == expected,
            'upper_contour_matches_base': actual['ray43']['outer'] == old['ray43']['outer'],
            'teeth_match_base': actual['ray43']['lower_teeth'] == old['ray43']['lower_teeth'],
            'intersection_matches': picked['distance_exact_match'] and picked['before_contact_exact_match'],
            'ray43': actual['grid'][index], 'before_lip': actual['before_lip'],
            'lower_lip': actual['ray43']['lower_lip'],
            'cell_replayed': front.area.resample(actual, actual['grid'],
                                                 index_from_end=measure['oral_cells_from_end'])['cell']
            == actual['before_lip']['raw'],
        }
    with np.load(out / 'render.npz', allow_pickle=False) as render:
        samples = render['pcm']
        stages = render['output']
        states = dict(zip(radiation.FIELDS, render['source'].T, strict=True))
    total, derivative = radiation.radiation_from_components(states, rate, False)
    evaluated, expected_pcm = pcm.replay(derivative, coefficients['candidate'], gain, config)
    out_ok = (np.array_equal(total, states['total_cm3_s']) and
              np.array_equal(derivative, states[radiation.RADIATION]) and
              np.array_equal(derivative, stages[:, :2].ravel()) and np.array_equal(evaluated, stages[:, 2:])
              and lip.bit_equal(expected_pcm, samples[:measure['prefix_frames']]))
    proof = tsp.read(out / 'pcm-digests.json')
    old_delta = pcm_delta(archived['upstream'], archived['trial'])
    new_delta = pcm_delta(archived['upstream'], samples)
    first = new_delta['first_unequal_sample']
    first_output = None
    if first is not None and first < len(evaluated):
        upper_pcm, study_pcm = float(archived['upstream'][first]), float(samples[first])
        value = float(evaluated[first, 2])
        midpoint = (upper_pcm + study_pcm) / 2
        first_output = {'frame': first, 'upstream_pcm': upper_pcm, 'bernstein_pcm': study_pcm,
                        'bernstein_before_cast': value, 'pcm_midpoint': midpoint,
                        'distance_from_midpoint': value - midpoint,
                        'adjacent_pcm': bool(np.nextafter(samples[first], archived['upstream'][first])
                                             == archived['upstream'][first])}
    prefix_diff = {}
    for mode in ('upstream', 'trial'):
        base = dict(zip(radiation.FIELDS, baseline_prefix[f'{mode}_source'].T, strict=True))
        fields = (*radiation.COMPONENTS, 'total_cm3_s', radiation.RADIATION)
        prefix_diff[mode] = {key: radiation.signal_difference(base[key], states[key][:len(base[key])])
                             for key in fields}
    upstream = baseline_volume['focus']['upstream'][focus_index]
    before = baseline_volume['focus']['trial'][focus_index]
    after = focus[focus_index]
    volume_diff = {key: {'upstream': upstream[key], 'trial': before[key], 'bernstein': after[key]}
                   for key in VOLUME_FIELDS}
    initial = comparisons['0']
    return {
        'checks': {
            'ordinary_and_probe_pcm_match': proof['bit_equal'] and proof['cli'] == proof['probe'] == lip.pcm_digest(samples)
                and all(len(wave) == len(samples) == measure['frames'] for wave in archived.values()),
            'isolated_curve_and_intersections_replayed': all(
                row[key] for row in comparisons.values() for key in ('bernstein_matches_all_lower_points',
                    'upper_contour_matches_base', 'teeth_match_base', 'intersection_matches', 'cell_replayed')),
            'native_volume_source_replayed': not mismatches and all(flow_checks.values()),
            'radiation_and_prefix_output_replayed': bool(out_ok),
        },
        'predictions': {
            'initial_ray_and_cell_match_upstream': initial['lower_lip'] == previous['upstream'][0]['ray43']['lower_lip']
                and initial['ray43'] == previous['upstream'][0]['grid'][index]
                and initial['before_lip']['raw'] == previous['upstream'][0]['before_lip']['raw'],
            'source_at_3969_matches_upstream': all(upstream[key] == after[key] for key in VOLUME_FIELDS),
            'first_pcm_difference_moves_later': first is None or first > old_delta['first_unequal_sample'],
            'peak_pcm_error_does_not_increase': new_delta['peak_error'] <= old_delta['peak_error'],
        },
        'frames': comparisons, 'volume_focus': volume_diff, 'focus_samples': focus,
        'volume_mismatches': mismatches, 'radiation_prefix': prefix_diff, 'first_pcm_output_stage': first_output,
        'pcm': {'baseline': old_delta, 'bernstein': new_delta, 'only_change': pcm_delta(archived['trial'], samples)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = front.WORKSPACE, front.UPSTREAM
    study = tsp.read(CASE)
    measure = study['measurement']
    if measure['oral_cells_from_end'] < 1 or measure['prefix_frames'] < max(measure['completed_frames']):
        parser.error('計測するセルを選び、出力の観測範囲に指定スナップショットを含めてください')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    intersection, volume_run, output, matched = (
        tsp.open_run(study[key], revision) for key in ('intersection', 'volume', 'output', 'matched'))
    config, config_path = front.saved_case(matched, front.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(intersection, 'artifacts/trial-pcm.npz')
    last_volume = tsp.verified_path(volume_run, 'summary.json')
    last_prefix = tsp.verified_path(volume_run, 'artifacts/prefix.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    snapshots = {mode: tsp.verified_path(intersection, f'artifacts/{mode}.jsonl') for mode in ('trial', 'upstream')}
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), Path(front.__file__), Path(ray.__file__),
              config_path, spec, pcm_input, trial_pcm, last_volume, last_prefix, coefficients, *snapshots.values(),
              *(run[0] / 'manifest.json' for run in (intersection, volume_run, output, matched)),
              *front.candidate_sources(), front.EMBEDDED_DICTIONARY, front.CLI_DICT, front.DICT, front.LOCAL,
              front.TRACE_TOOL, front.RAMP_TEST, front.area.observer.SNAPSHOT, lip.observer.LOCAL_PATCH, *TEST_CASES,
              *(ws / 'tools' / name for name in ('tsp_fk61_ray43_observation.py', 'tsp_fk61_node42_area_observation.py',
                 'tsp_fk61_lip_front_observation.py', 'tsp_fk61_lip_area_observation.py',
                 'tsp_fk61_lip_observation.py', 'tsp_fk61_lip_front_radiation_observation.py',
                 'tsp_fk61_node_volume_observation.py', 'measure_tsp_fk61_node42_volume_source.py',
                 'measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_area_origin.py',
                 'measure_tsp_fk61_lip_front_radiation.py', 'measure_tsp_fk61_lip_volume_increment.py',
                 'measure_tsp_fk61_pcm_first_difference.py', 'measure_tsp_fine_variation.py', 'measure_uniform_tube.py')),
              upper / 'crates/chimera/src/anatomy/geom.rs']

    def measure(out, execute):
        capture(study, config, spec, out, execute)
        archived = front.archived_pcm(pcm_input, uid) | {'trial': ray.read_trial(trial_pcm)}
        prior = {mode: front.area.read_snapshots(path, study['measurement']['completed_frames'])
                 for mode, path in snapshots.items()}
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        with np.load(last_prefix, allow_pickle=False) as prefix:
            return analyze(study, config, gain, tsp.read(coefficients), out, prior, archived, prefix, tsp.read(last_volume))

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return front.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
