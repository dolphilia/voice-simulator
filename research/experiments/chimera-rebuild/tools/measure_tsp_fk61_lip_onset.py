"""FK61_01の最初の口端流量差を体積変化と放射負荷の入力へさかのぼる。"""

import argparse
from fractions import Fraction
import gzip
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_stressed_vowel_formants as tsp
import tsp_fk61_lip_observation as observer
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_mixed_lip_load_origin import EMBEDDED_DICTIONARY, FIELDS as LOAD_FIELDS, copy_inputs
from measure_fixed_voice_release_lip_load import INPUTS, OUTPUTS, replay
from measure_tsp_active_duration import read_generated
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import DICT, FIELDS as SOURCE_FIELDS, LOCAL, OUTPUT_PATCH, PROBE, SOURCE_PATCH
from measure_tsp_fk61_pcm_first_difference import MODES, archived_pcm
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-lip-onset.json'
TRACE_TOOL = WORKSPACE / 'tools/tsp_fine_trace.rs'
CONFIG = WORKSPACE / 'cases/tsp-held-out-matched-speech.json'
LOAD_COLUMNS = INPUTS + OUTPUTS
RESULT_COLUMNS = ('compliance_cm5_dyn', 'inertance_g_cm4', 'resistance_dyn_s_cm5',
                  'old_pressure_dyn_cm2', 'old_inertance_flow_cm3_s', 'inflow_cm3_s',
                  'new_pressure_dyn_cm2', 'new_inertance_flow_cm3_s', 'lip_flow_cm3_s')
TESTS = {
    'upstream': ('chimera', 'airway', 'airway_adversarial'),
    'candidate': ('vocal-core', 'geometry_ramp'),
}


def build_pcm_cli(fixed, root, flags, execute):
    package = 'chimera-cli' if fixed else 'vocal-cli'
    execute(['cargo', 'build', '--locked', '--release', '-p', package, *flags], cwd=root)
    return Path(flags[-1]) / 'release' / ('chimera' if fixed else package)


def render_pcm_cli(fixed, exe, root, spec, text, wave, measure, execute, *, body):
    if fixed:
        execute([str(exe), 'render', 'text', str(wave), text, body, '--float'], cwd=root)
    else:
        execute([str(exe), 'render-pcm', str(spec), str(wave), '--no-trace', str(measure['block_frames'])])
    return read_generated(wave, measure['sample_rate_hz'])


def normal_pcm(name, root, flags, spec, text, wave, measure, execute, *, body='female'):
    fixed = name == 'upstream'
    exe = build_pcm_cli(fixed, root, flags, execute)
    return render_pcm_cli(fixed, exe, root, spec, text, wave, measure, execute, body=body)


def pcm_digest(samples):
    return {'frames': len(samples), 'sha256_f32le': sha256(samples.astype('<f4', copy=False).tobytes()).hexdigest()}


def read_trace(path, count):
    columns = LOAD_FIELDS + observer.FIELDS
    captured = np.fromfile(path, dtype='<f8').reshape(-1, len(columns))
    if captured.shape[0] != count or not np.isfinite(captured).all() or not (captured[:, 0] == 1).all():
        raise ValueError(f'口端の観測範囲または観測値が登録条件を満たしません ({path.name})')
    return [dict(zip(columns, row.tolist(), strict=True)) for row in captured]


def capture(study, spec, config, archived, out, execute, *, trial_patch=None, prepare=observer.prepare,
            retain_prefix=False):
    measure = study['measurement']
    start, stop = measure['comparison_internal_samples']
    if start % 2 or stop % 2 or measure['internal_sample_rate_hz'] != 2 * measure['sample_rate_hz']:
        raise ValueError('観測区間を出力フレームの境界で指定してください')
    text = tsp.read(spec)['speech_voice']['input']['text']
    f0 = config['body']['female']['base_f0_hz']
    traces, pcm_proof = {}, {}
    states = {}
    frames = measure.get('prefix_frames', stop // 2)
    with TemporaryDirectory(prefix='tsp-fk61-lip-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = scratch / 'upstream'
        checkout.mkdir()
        archive = scratch / 'upstream.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(checkout)])
        local = scratch / 'candidate'
        copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, LOCAL, TRACE_TOOL], local)
        copy_inputs([PROBE, TRACE_TOOL], checkout)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        modes = (*MODES, 'trial') if trial_patch is not None else MODES
        for name in modes:
            fixed = name == 'upstream'
            trial = name == 'trial'
            root = checkout if fixed else scratch / 'trial' if trial else local
            if trial:
                copy_inputs([*candidate_sources(), EMBEDDED_DICTIONARY, LOCAL, TRACE_TOOL,
                             WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs'], root)
                trial_patch(root)
            flags = ('--offline', '--target-dir', str(scratch / f'{name}-target'))
            ordinary_root = UPSTREAM if fixed else root if trial else WORKSPACE
            normal = normal_pcm(name, ordinary_root, flags, spec, text,
                                scratch / f'{name}.wav', measure, execute)
            package, *tests = TESTS['upstream' if fixed else 'candidate']
            test_flags = [value for test in tests for value in ('--test', test)]
            execute(['cargo', 'test', '--locked', '--release', '-p', package, *flags, *test_flags],
                    cwd=ordinary_root, stdout=out / f'{name}-tests.log')
            if fixed:
                for patch in (OUTPUT_PATCH, SOURCE_PATCH):
                    execute(['git', 'apply', str(patch)], cwd=root)
            source = prepare(root, fixed, (start, stop), execute)
            probe = build_upstream_probe(source, scratch, execute, upstream=root,
                package='chimera' if fixed else 'vocal-core', lto='fat' if fixed else 'off',
                extra_libraries=('serde_json',), rustc_args=('--cfg', 'tsp_voice_probe') if fixed else (),
                cargo_args=flags)
            trace, pcm, stages = (scratch / f'{name}.{suffix}' for suffix in ('source', 'pcm', 'stages'))
            path = out / f'{name}-lip.f64le'
            argv = ['env', f'CHIMERA_PROBE_LIP_WINDOW={path}', str(probe), str(spec), str(dictionary)]
            if fixed:
                argv.extend([str(trace), str(pcm), str(scratch / 'score.json'), str(frames), 'default', str(stages)])
            else:
                argv.extend([str(frames), str(measure['initial_f0_hz']), str(f0), *map(str, (trace, pcm, stages))])
            execute(argv, stdout=out / f'{name}-nodes.csv' if retain_prefix else None)
            traces[name] = read_trace(path, stop - start)
            probe_pcm = np.fromfile(pcm, dtype='<f4')
            pcm_proof[name] = {
                'ordinary': pcm_digest(normal), 'probe': pcm_digest(probe_pcm),
                'archived': pcm_digest(archived[name]),
                'bit_equal': bool(bit_equal(normal, archived[name]) and bit_equal(normal, probe_pcm)),
            }
            if retain_prefix:
                states[f'{name}_source'] = np.fromfile(trace, dtype='<f8').reshape(frames * 2, len(SOURCE_FIELDS))
                states[f'{name}_output'] = np.fromfile(stages, dtype='<f8').reshape(frames, 7)
                states[f'{name}_pcm'] = probe_pcm[:frames]
    if retain_prefix:
        np.savez_compressed(out / 'prefix.npz', **states)
    return traces, pcm_proof


def load_inputs(row):
    return dict(zip(LOAD_COLUMNS, (row[key] for key in RESULT_COLUMNS), strict=True))


def solve_matches(row, rate, fixed):
    values = load_inputs(row)
    solved = replay(values, rate, fixed)
    return all(solved[key].hex() == values[key].hex() for key in OUTPUTS)


def geometry(row, rate, fixed):
    dt = 1.0 / rate
    if row['geometry_advances']:
        area = max(0.0, row['old_area'] + row['area_increment'])
        length = row['old_length'] + row['length_increment']
        minimum = min(area, max(0.0, row['old_minimum'] + row['minimum_increment']))
        volume = max(row['area_floor'], area) * length
    else:
        area, length, minimum, volume = (row[key] for key in ('old_area', 'old_length', 'old_minimum', 'old_volume'))
    difference = row['old_volume'] - volume
    raw = (difference * rate if fixed else difference / dt) if row['volume_source_enabled'] else 0.0
    s = minimum / row['squeeze_threshold']
    retained = raw if s >= 1.0 else raw * (s * s * (3.0 - 2.0 * s))
    coefficient = row['pole_coefficient']
    previous_first, previous_second = row['old_first_pole'], row['old_second_pole']
    first = previous_first + coefficient * (row['spill'] - previous_first)
    second = previous_second + coefficient * (first - previous_second)
    return {'raw': raw, 'retained_local': retained, 'spill_minus_retained_local': row['spill'] - retained,
            'matches_dimensions_and_volume': (area, length, minimum, volume) ==
                (row['area_cm2'], row['length_cm'], row['minimum'], row['volume']),
            'matches_filter': (first.hex(), second.hex()) == (row['first_pole'].hex(), row['second_pole'].hex()),
            'matches_geometry_inflow': row['second_pole'] == row['geometry_inflow_cm3_s']}


def volume_rounding(event, rate):
    dt = 1.0 / rate
    exact_raw, rounded_delta = {}, {}
    for name, row in event.items():
        floor = row['area_floor']
        before = Fraction(max(row['old_area'], floor)) * Fraction(row['old_length'])
        after = Fraction(max(row['area_cm2'], floor)) * Fraction(row['length_cm'])
        exact_raw[name] = (before - after) * rate
        rounded_delta[name] = row['old_volume'] - row['volume']
    return {
        'exact_product_raw': {name: float(value) for name, value in exact_raw.items()},
        'exact_candidate_minus_upstream': float(exact_raw['candidate'] - exact_raw['upstream']),
        'stored_volume_delta': rounded_delta,
        'stored_candidate_minus_upstream': rounded_delta['candidate'] - rounded_delta['upstream'],
        'same_multiply_and_divide_on_each_rounded_delta': {
            name: delta * rate == delta / dt for name, delta in rounded_delta.items()},
    }


def evaluate(study, traces, matches, prefix):
    measure = study['measurement']
    rate = measure['internal_sample_rate_hz']
    first, stop = measure['comparison_internal_samples']
    at = measure['expected_first_lip_sample']
    history = {name: [geometry(row, rate, name == 'upstream') for row in traces[name]] for name in MODES}
    event = {name: traces[name][at - first] for name in MODES}
    geometry_event = {name: history[name][at - first] for name in MODES}
    expected = {name: prefix[f'{name}_state'][:, SOURCE_FIELDS.index('lip_cm3_s')] for name in MODES}
    old_first = np.flatnonzero(expected['upstream'] != expected['candidate']).tolist()[0]
    previous_equal = {key: event['upstream'][key] == event['candidate'][key]
                      for key in ('old_pressure_dyn_cm2', 'old_inertance_flow_cm3_s', 'old_first_pole', 'old_second_pole')}
    zero_branch_wall = {name: event[name]['geometry_inflow_cm3_s'] == event[name]['before_wall_inflow_cm3_s']
                        == event[name]['inflow_cm3_s'] for name in MODES}
    swaps = {}
    for src, dst in (MODES, MODES[::-1]):
        source, destination = event[src], event[dst]
        inputs = load_inputs(destination)
        swapped = inputs | {'inflow': source['geometry_inflow_cm3_s']
                            + (inputs['inflow'] - destination['geometry_inflow_cm3_s'])}
        target = source['lip_flow_cm3_s']
        flow = replay(swapped, rate, dst == 'upstream')['lip_flow']
        swaps[dst] = {'source': src, 'inflow': swapped['inflow'], 'lip_flow': flow, 'target_flow': target,
                      'exact': flow == target, 'relative_error': abs(flow - target) / abs(target)}
    return {
        'checks': {
            'all_pcm_matches_archived_normal_and_probe': all(matches.values()),
            'aligned_with_prior_lip_trace_and_onset': old_first == at and at % measure['control_samples'] == 0
                and all(np.array_equal(expected[name][first:stop], [row['lip_flow_cm3_s'] for row in traces[name]])
                        for name in MODES),
            'independent_geometry_and_volume_updates': all(row['matches_dimensions_and_volume']
                for name in MODES for row in history[name]),
            'independent_filter_and_geometry_inflow': all(row['matches_filter'] and row['matches_geometry_inflow']
                for name in MODES for row in history[name]),
            'independent_ordered_load_solve': all(solve_matches(row, rate, name == 'upstream')
                for name in MODES for row in traces[name]),
        },
        'predictions': {
            'equal_prior_load_state_and_zero_branch_wall_contribution': all(previous_equal.values())
                and all(zero_branch_wall.values()),
            'different_local_volume_change_precedes_filter_and_lip': geometry_event['upstream']['raw'] !=
                geometry_event['candidate']['raw'] and all(event['upstream'][key] != event['candidate'][key]
                    for key in ('spill', 'second_pole', 'lip_flow_cm3_s'))
                and all(swap['relative_error'] <= 1e-12 for swap in swaps.values()),
        },
        'first_lip_difference': old_first, 'window': [first, stop], 'ordinary_pcm_matches': matches,
        'equal_previous_states': previous_equal, 'zero_branch_wall_contribution': zero_branch_wall,
        'event': event, 'geometry_event': geometry_event, 'geometry_inflow_swap': swaps,
        'volume_rounding': volume_rounding(event, rate),
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
    previous, matched = (tsp.open_run(study[key], rev) for key in ('previous', 'matched'))
    config, config_path = saved_case(matched, CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    stored = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    preceding = tsp.verified_path(previous, 'artifacts/prefix.npz')
    inputs = [CASE, Path(__file__).resolve(), Path(observer.__file__), LOCAL, PROBE, TRACE_TOOL, DICT,
              EMBEDDED_DICTIONARY, OUTPUT_PATCH, SOURCE_PATCH, observer.LOCAL_PATCH, observer.UPPER_PATCH,
              config_path, spec, stored, preceding, previous[0] / 'manifest.json', matched[0] / 'manifest.json',
              *candidate_sources(), WORKSPACE / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/airway/network.rs',
                  'crates/chimera/tests/airway.rs', 'crates/chimera/tests/airway_adversarial.rs',
                  'crates/chimera/src/voice/human_voice.rs', 'crates/chimera-cli/src/render.rs')),
              *(WORKSPACE / 'tools' / name for name in ('measure_duet_mixed_lip_load_origin.py',
                  'measure_fixed_voice_release_lip_load.py', 'measure_tsp_fk61_pcm_first_difference.py',
                  'measure_tsp_fine_variation.py', 'measure_tsp_stressed_vowel_formants.py', 'measure_uniform_tube.py'))]
    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev}

    def measure(out, execute):
        archived = archived_pcm(stored, uid)
        traces, pcm_proof = capture(study, spec, config, archived, out, execute)
        (out / 'columns.json').write_text(json.dumps(LOAD_FIELDS + observer.FIELDS, indent=2) + '\n')
        (out / 'pcm-digests.json').write_text(json.dumps(pcm_proof, indent=2) + '\n')
        with np.load(preceding, allow_pickle=False) as prefix:
            return evaluate(study, traces, {name: row['bit_equal'] for name, row in pcm_proof.items()}, prefix)

    return record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
