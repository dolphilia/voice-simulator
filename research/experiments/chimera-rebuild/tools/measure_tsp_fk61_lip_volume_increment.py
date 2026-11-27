"""口端1節点だけを差分式に切り替えてFK61_01の発話を描画する。"""

import argparse
from fractions import Fraction
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_stressed_vowel_formants as tsp
import tsp_fk61_lip_observation as observer
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import COLUMNS, trace_input
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_tip import read_series
from measure_tsp_fine_variation import DICT, FIELDS, LOCAL, signal_difference
from measure_tsp_fk61_lip_onset import (
    CONFIG, EMBEDDED_DICTIONARY, TRACE_TOOL, copy_inputs, geometry, normal_pcm, pcm_digest, read_trace,
    solve_matches,
)
from measure_tsp_fk61_pcm_first_difference import archived_pcm, midpoint_report, replay
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-lip-volume-increment.json'
PATCH = WORKSPACE / 'tools/patches/candidate-tsp-lip-volume-increment.patch'
CLI_DICT = WORKSPACE / 'data/cmudict.txt.gz'
RAMP_TEST = WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs'
TEST_CASES = [WORKSPACE / 'cases' / name for name in ('contour-buffer-reuse.json', 'bilabial-p.json')]
GEOMETRY = (
    'old_area', 'old_length', 'old_minimum', 'area_cm2', 'length_cm', 'minimum',
    'area_increment', 'length_increment', 'minimum_increment', 'old_volume', 'volume',
    'area_floor', 'squeeze_threshold', 'compliance_cm5_dyn', 'inertance_g_cm4', 'resistance_dyn_s_cm5',
)
SIGNALS = ('lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s', 'total_cm3_s', 'radiation_derivative_cm3_s2')


def capture(study, config, spec, out, execute):
    measure = study['measurement']
    text = tsp.read(spec)['speech_voice']['input']['text']
    f0 = config['body']['female']['base_f0_hz']
    frames = measure['prefix_frames']
    with TemporaryDirectory(prefix='fk61-volume-increment-', dir=out.parent / 'tmp') as tmp:
        tmp = Path(tmp)
        root = tmp / 'candidate'
        copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, CLI_DICT, LOCAL, TRACE_TOOL, RAMP_TEST,
                     *TEST_CASES], root)
        execute(['git', 'apply', str(PATCH)], cwd=root)
        flags = ('--offline', '--target-dir', str(tmp / 'target'))
        standard_entry = normal_pcm('candidate', root, flags, spec, text, tmp / 'delta.wav', measure, execute)
        command = ['cargo', 'test', '--locked', '--release', '-p', 'vocal-core', *flags]
        execute([*command, '--lib', 'volume_decrease_combines_area_and_length_with_the_cell_floor'],
                cwd=root, stdout=out / 'formula-test.log')
        execute([*command, '--test', 'geometry_ramp'], cwd=root, stdout=out / 'ramp-test.log')
        source = observer.prepare(root, False, measure['internal_window'], execute)
        probe = build_upstream_probe(source, tmp, execute, upstream=root, lto='off', package='vocal-core',
                                     extra_libraries=('serde_json',), cargo_args=flags)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        state, pcm, output = (tmp / f'delta.{suffix}' for suffix in ('state', 'pcm', 'output'))
        execute(['env', f'CHIMERA_PROBE_LIP_WINDOW={out / "lip.f64le"}', str(probe), str(spec), str(dictionary),
                 str(frames), str(measure['initial_f0_hz']), str(f0), *map(str, (state, pcm, output))])
        samples = np.fromfile(pcm, dtype='<f4')
        states = np.column_stack(list(read_series(state, frames * 2).values()))
        stages = trace_input(output, frames)
    recorded = {'state': states, 'output': stages, 'pcm': samples}
    np.savez_compressed(out / 'render.npz', **recorded)
    proof = {'cli': pcm_digest(standard_entry), 'probe': pcm_digest(samples),
             'same': bool(bit_equal(standard_entry, samples))}
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    return recorded, proof


def raw_flow(row, rate):
    floor = row['area_floor']
    a0, a1 = (max(row[key], floor) for key in ('old_area', 'area_cm2'))
    d0, d1 = row['old_length'], row['length_cm']
    exact = (Fraction(a0) * Fraction(d0) - Fraction(a1) * Fraction(d1)) * rate
    ordered = ((a0 - a1) * d0 + a1 * (d0 - d1)) / (1 / rate)
    return exact, ordered, a0 * d0 == row['old_volume']


def compare_geometry(previous, observed, start, rate):
    rows = []
    for sample, (standard, alternate) in enumerate(zip(previous, observed, strict=True), start):
        exact, ordered, matches_cache = raw_flow(alternate, rate)
        source = geometry(standard, rate, False)
        enhanced = geometry(alternate, rate, False)
        old_value, new_value = source['raw'], alternate['spill']
        rows.append({
            'sample': sample, 'same_geometry_and_load': all(alternate[key] == standard[key] for key in GEOMETRY),
            'preconditions_and_rust_raw_match': (
                standard['geometry_advances'] == alternate['geometry_advances'] == 1.0
                and matches_cache and standard['spill'] == old_value
                and alternate['minimum'] >= alternate['squeeze_threshold']
                and new_value == ordered),
            'independent_filter_and_load_match': (
                enhanced['matches_filter'] and enhanced['matches_geometry_inflow'] and solve_matches(alternate, rate, False)),
            'exact_flow_cm3_s': float(exact), 'standard_flow_cm3_s': old_value, 'trial_flow_cm3_s': new_value,
            'standard_absolute_error': float(abs(Fraction(old_value) - exact)),
            'trial_absolute_error': float(abs(Fraction(new_value) - exact)),
        })
    return rows


def pcm_delta(baseline, trial):
    return signal_difference(baseline, trial) | {
        'unequal_frames': int(np.count_nonzero(baseline.view('<u4') != trial.view('<u4'))),
    }


def first_rounding(frame, prefixes, archived, stages, samples, frames):
    if frame is None or frame >= frames:
        return None
    result = midpoint_report(frame, {'upstream': prefixes['upstream_output'], 'candidate': stages},
                             {'upstream': archived['upstream'], 'candidate': samples})
    for key in ('precast', 'pcm', 'from_midpoint'):
        result[key]['trial'] = result[key].pop('candidate')
    baseline = float(prefixes['candidate_output'][frame, COLUMNS.index('dc_removed')])
    result['precast']['candidate'] = baseline
    result['pcm']['candidate'] = float(archived['candidate'][frame])
    result['from_midpoint']['candidate'] = baseline - result['midpoint']
    return result


def evaluate(study, config, gain, prefixes, archived, recorded, proof, coefficients, previous_lip, trial_lip):
    cfg = study['measurement']
    start, stop = cfg['internal_window']
    onset = cfg['registered_onset']
    frames = cfg['prefix_frames']
    rate = cfg['internal_sample_rate_hz']
    geometry_rows = compare_geometry(previous_lip, trial_lip, start, rate)
    event = geometry_rows[onset - start]
    prefix_matrices = {name: prefixes[f'{name}_state'] for name in ('upstream', 'candidate')}
    prefix_matrices['trial'] = recorded['state']
    states = {name: dict(zip(FIELDS, values.T, strict=True)) for name, values in prefix_matrices.items()}
    observed = states['trial']
    radiation_key = 'radiation_derivative_cm3_s2'
    radiation = observed[radiation_key]
    stages = recorded['output']
    doubles, pcm = replay(radiation, coefficients, gain, config)
    diffs = {}
    for target in ('candidate', 'trial'):
        diffs[target] = {key: signal_difference(states['upstream'][key], states[target][key]) for key in SIGNALS}
    intervention = {key: signal_difference(states['candidate'][key], observed[key]) for key in SIGNALS}
    reference = float(states['upstream'][radiation_key][onset])
    at_onset = {name: float(state[radiation_key][onset]) for name, state in states.items()}
    wave = {
        'upstream_to_candidate': pcm_delta(archived['upstream'], archived['candidate']),
        'upstream_to_trial': pcm_delta(archived['upstream'], recorded['pcm']),
        'candidate_to_trial': pcm_delta(archived['candidate'], recorded['pcm']),
    }
    first = wave['upstream_to_trial']['first_unequal_sample']
    derivative = np.diff(observed['total_cm3_s'], prepend=0.0) / (1 / rate)
    total = (observed['wall_cm3_s'] + observed['lip_cm3_s']) + observed['nose_cm3_s']
    source_fields_changed = [
        key for key in FIELDS if not np.array_equal(states['candidate'][key][:onset], observed[key][:onset])]
    return {
        'checks': {
            'source_and_cache_geometry_match': all(row['same_geometry_and_load'] for row in geometry_rows),
            'independent_local_volume_matches_native': all(row['preconditions_and_rust_raw_match']
                and row['trial_absolute_error'] <= cfg['raw_absolute_error_cm3_s'] for row in geometry_rows),
            'independent_filter_and_termination_match_native': (
                all(row['independent_filter_and_load_match'] for row in geometry_rows)
                and np.array_equal(observed['lip_cm3_s'][start:stop], [row['lip_flow_cm3_s'] for row in trial_lip])),
            'independent_radiation_and_output_match_native': (
                not source_fields_changed and intervention['lip_cm3_s']['first_unequal_sample'] == onset
                and np.array_equal(total, observed['total_cm3_s']) and np.array_equal(derivative, radiation)
                and np.array_equal(stages[:, :2].ravel(), radiation) and np.array_equal(doubles, stages[:, 2:])
                and bit_equal(pcm, recorded['pcm'][:frames])),
            'normal_entry_and_baseline_pcm_verified': (
                proof['same'] and proof['cli'] == proof['probe'] == pcm_digest(recorded['pcm'])
                and all(len(w) == cfg['frames'] and np.isfinite(w).all() for w in (*archived.values(), recorded['pcm']))
                and wave['upstream_to_candidate']['first_unequal_sample'] == cfg['baseline_first_pcm_difference']),
        },
        'predictions': {
            'increment_is_more_accurate': event['trial_absolute_error'] * cfg['minimum_onset_error_improvement']
                <= event['standard_absolute_error'],
            'radiation_onset_agreement_improves': abs(at_onset['trial'] - reference) < abs(at_onset['candidate'] - reference),
            'first_pcm_difference_moves_later': first is None or first > cfg['baseline_first_pcm_difference'],
        },
        'geometry': geometry_rows, 'event': event, 'radiation_at_onset': at_onset,
        'radiation_and_components_from_upstream': diffs, 'intervention': intervention,
        'pcm': wave, 'pre_onset_source_fields_changed': source_fields_changed,
        'first_trial_rounding': first_rounding(first, prefixes, archived, stages, recorded['pcm'], frames),
        'output_stage_differences_from_upstream': {
            key: signal_difference(prefixes['upstream_output'][:, index], stages[:, index])
            for index, key in enumerate(COLUMNS)
        },
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
    lip, output, matched = (tsp.open_run(study[key], rev) for key in ('lip', 'output', 'matched'))
    config, config_path = saved_case(matched, CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    matched_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    preceding = tsp.verified_path(lip, 'artifacts/candidate-lip.f64le')
    prefix_npz = tsp.verified_path(output, 'artifacts/prefix.npz')
    coef_json = tsp.verified_path(output, 'artifacts/coefficients.json')
    inputs = [CASE, Path(__file__).resolve(), PATCH, LOCAL, TRACE_TOOL, DICT, CLI_DICT, RAMP_TEST, *TEST_CASES,
              EMBEDDED_DICTIONARY, observer.LOCAL_PATCH, Path(observer.__file__),
              config_path, spec, matched_pcm, preceding, prefix_npz, coef_json,
              *(r[0] / 'manifest.json' for r in (lip, output, matched)), *candidate_sources(),
              UPSTREAM / 'crates/chimera/src/airway/network.rs', UPSTREAM / 'crates/chimera/tests/airway_adversarial.rs',
              *(WORKSPACE / 'tools' / name for name in ('measure_tsp_fk61_lip_onset.py',
                  'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fk61_pcm_first_difference.py',
                  'measure_tsp_fine_variation.py', 'measure_tsp_stressed_vowel_formants.py', 'measure_uniform_tube.py'))]

    def measure(out, execute):
        recorded, proof = capture(study, config, spec, out, execute)
        first, stop = study['measurement']['internal_window']
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        with np.load(prefix_npz, allow_pickle=False) as prefixes:
            return evaluate(study, config, gain, prefixes, archived_pcm(matched_pcm, uid), recorded, proof,
                            tsp.read(coef_json)['candidate'], read_trace(preceding, stop - first),
                            read_trace(out / 'lip.f64le', stop - first))

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
