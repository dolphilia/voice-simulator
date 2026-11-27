"""FK61_01の出力2937で分かれる放射入力と出力段を照合する。"""

import argparse
from fractions import Fraction
import gzip
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_fk61_lip_front_radiation as radiation


pcm, lip, tsp = radiation.pcm, radiation.lip, radiation.tsp
CASE = pcm.WORKSPACE / 'cases/tsp-fk61-pcm2937-output.json'
SIGNAL = radiation.RADIATION
MODES = ('upstream', 'bernstein')


def capture(study, config, spec, expected, out, execute):
    measure = study['measurement']
    count = measure['prefix_frames']
    factor = measure['internal_sample_rate_hz'] // measure['sample_rate_hz']
    text = tsp.read(spec)['speech_voice']['input']['text']
    with TemporaryDirectory(prefix='fk61-pcm2937-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        source, tar, dictionary = tmp / 'upstream', tmp / 'upstream.tar', tmp / 'dictionary.tsv'
        source.mkdir()
        execute(['git', 'archive', study['upstream_revision']], cwd=pcm.UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(source)])
        for patch in (pcm.OUTPUT_PATCH, pcm.SOURCE_PATCH):
            execute(['git', 'apply', str(patch)], cwd=source)
        dictionary.write_bytes(gzip.decompress(pcm.DICT.read_bytes()))
        probe, coefficient_probe, cli = pcm.build_pair('upstream', tmp, source, execute)
        execute([str(coefficient_probe)], stdout=out / 'upstream-coefficients.json')
        execute(['cargo', 'test', '--locked', '--release', '-p', 'chimera', '--offline', '--target-dir',
                 str(tmp / 'upstream-target'), '--test', 'engine', 'output_does_not_depend_on_the_host_block_size'],
                cwd=pcm.UPSTREAM, stdout=out / 'upstream-engine-test.log')
        wave, trace, raw, outputs = (tmp / f'upstream.{suffix}' for suffix in ('wav', 'source', 'pcm', 'stage'))
        execute([str(cli), 'render', 'text', str(wave), text, 'female', '--float'], cwd=pcm.UPSTREAM)
        execute([str(probe), str(spec), str(dictionary), str(trace), str(raw), str(tmp / 'plan.json'),
                 str(count), 'default', str(outputs)])
        ordinary = pcm.read_generated(wave, config['sample_rate_hz'])
        samples = np.fromfile(raw, dtype='<f4')
        states = np.column_stack(list(pcm.read_series(trace, count * factor).values()))
        stage = pcm.trace_input(outputs, count)
    proof = {'ordinary': lip.pcm_digest(ordinary), 'probe': lip.pcm_digest(samples),
             'archive': lip.pcm_digest(expected),
             'bit_equal': bool(pcm.bit_equal(ordinary, samples) and pcm.bit_equal(ordinary, expected))}
    (out / 'pcm-digests.json').write_text(json.dumps(proof, indent=2) + '\n')
    np.savez_compressed(out / 'upstream-prefix.npz', source=states, output=stage, pcm=samples[:count])


def subsets(names):
    return [chosen for count in range(len(names) + 1) for chosen in combinations(names, count)]


def one_frame_variants(outputs, pole, frame, reference):
    names = ('current_gain', 'previous_gain', 'previous_dc')
    columns = pcm.COLUMNS
    g, h = columns.index('gain_applied'), columns.index('dc_removed')
    operands = {mode: [float(out[frame, g]), float(out[frame - 1, g]), float(out[frame - 1, h])]
                for mode, out in outputs.items()}
    rows = []
    for selected in subsets(names):
        cur, prev, dc = (operands['upstream' if name in selected else 'bernstein'][i] for i, name in enumerate(names))
        value = (cur - prev) + pole * dc
        rows.append({'terms': list(selected), 'precast': value, 'pcm': float(np.float32(value)),
                     'matches_upstream_at_focus': bool(np.float32(value) == reference)})
    return {'operands': {mode: dict(zip(names, values, strict=True)) for mode, values in operands.items()},
            'variants': rows}


def compare_replay(signal, coefficients, gain, config, reference, frame):
    output, samples = pcm.replay(signal, coefficients, gain, config)
    return {'precast': float(output[frame, 2]), 'pcm': float(samples[frame]),
            'matches_upstream_at_focus': bool(samples[frame] == reference[frame]),
            'first_pcm_difference_through_focus': radiation.signal_difference(
                reference[:frame + 1], samples[:frame + 1])['first_unequal_sample']}


def window_variants(states, coefficients, gain, config, reference, frame):
    factor = config['internal_sample_rate_hz'] // config['sample_rate_hz']
    end = factor * (frame + 1)
    start = end - len(coefficients['taps'])
    windows = {'before_fir': [0, start], 'older_fir': [start, end - factor], 'current_pair': [end - factor, end]}
    rows = []
    upstream, bernstein = (states[mode][SIGNAL][:end] for mode in MODES)
    for names in subsets(tuple(windows)):
        signal = bernstein.copy()
        for name in names:
            a, b = windows[name]
            signal[a:b] = upstream[a:b]
        rows.append({'windows': list(names), **compare_replay(signal, coefficients, gain, config, reference, frame)})
    differences = [float(Fraction(float(tap)) * (Fraction(float(upstream[i])) - Fraction(float(bernstein[i]))))
                   for i, tap in enumerate(reversed(coefficients['taps']), start)]
    first = max(range(len(differences)), key=lambda i: abs(differences[i]))
    return {'internal_windows': windows, 'variants': rows,
            'largest_exact_fir_term': {'sample': start + first, 'delta_cm3_s2': differences[first]}}


def component_variants(states, coefficients, gain, config, reference, frame):
    factor = config['internal_sample_rate_hz'] // config['sample_rate_hz']
    count = factor * (frame + 1)
    results = []
    for fixed in (False, True):
        for names in subsets(radiation.COMPONENTS):
            components = {key: states['upstream' if key in names else 'bernstein'][key][:count]
                          for key in radiation.COMPONENTS}
            _, derivative = radiation.radiation_from_components(components, config['internal_sample_rate_hz'], fixed)
            results.append({'components': list(names), 'derivative_order': 'upstream' if fixed else 'bernstein',
                            **compare_replay(derivative, coefficients, gain, config, reference, frame)})
    return results


def analyze(study, config, gain, out, main_run, older, recorded_coefficients, expected):
    m = study['measurement']
    rate, frame = m['internal_sample_rate_hz'], m['focus_frame']
    count = m['prefix_frames']
    upper_coefficients = tsp.read(out / 'upstream-coefficients.json')
    coefficients = {'upstream': upper_coefficients, 'bernstein': recorded_coefficients['candidate']}
    with np.load(out / 'upstream-prefix.npz', allow_pickle=False) as a, np.load(main_run, allow_pickle=False) as b:
        source_arrays = {name: data['source'] for name, data in zip(MODES, (a, b), strict=True)}
        outputs = {name: data['output'] for name, data in zip(MODES, (a, b), strict=True)}
        samples = {name: data['pcm'][:count] for name, data in zip(MODES, (a, b), strict=True)}
        full_bernstein = b['pcm']
    states = {mode: dict(zip(radiation.FIELDS, source_arrays[mode].T, strict=True)) for mode in MODES}
    first = radiation.signal_difference(samples['upstream'], samples['bernstein'])
    rounding = pcm.midpoint_report(frame, dict(zip(pcm.MODES, outputs.values(), strict=True)),
                                   dict(zip(pcm.MODES, samples.values(), strict=True)))
    for field in ('precast', 'pcm', 'from_midpoint'):
        rounding[field]['bernstein'] = rounding[field].pop('candidate')
    own = {mode: pcm.replay(states[mode][SIGNAL], coefficients[mode], gain, config) for mode in MODES}
    interchange = {
        mode: pcm.replay(states[mode][SIGNAL], coefficients[target], gain, config)
        for mode, target in (MODES, MODES[::-1])
    }
    swaps_match = all(np.array_equal(interchange[mode][0], outputs[mode][:, 2:])
                      and pcm.bit_equal(interchange[mode][1], samples[mode]) for mode in MODES)
    source_differences = {key: radiation.signal_difference(states['upstream'][key], states['bernstein'][key])
                          for key in radiation.FIELDS}
    output_differences = {key: radiation.signal_difference(outputs['upstream'][:, i], outputs['bernstein'][:, i])
                          for i, key in enumerate(pcm.COLUMNS)}
    inputs = one_frame_variants(outputs, coefficients['bernstein']['dc_pole'], frame, samples['upstream'][frame])
    windows = window_variants(states, coefficients['bernstein'], gain, config, samples['upstream'], frame)
    components = component_variants(states, coefficients['bernstein'], gain, config, samples['upstream'], frame)
    proof = tsp.read(out / 'pcm-digests.json')
    same_coefficients = upper_coefficients == recorded_coefficients['upstream'] == recorded_coefficients['candidate']
    names = {'upstream_source': source_arrays['upstream'], 'upstream_output': outputs['upstream'],
             'upstream_pcm': samples['upstream']}
    return {
        'checks': {
            'ordinary_probe_and_retained_pcm_match': (
                proof['bit_equal'] and proof['ordinary'] == proof['probe'] == proof['archive'] == lip.pcm_digest(expected)
                and len(expected) == len(full_bernstein) == m['frames']
                and pcm.bit_equal(samples['upstream'], expected[:count])
                and first['first_unequal_sample'] == frame),
            'earlier_upstream_observations_reproduced': all(
                np.array_equal(data[:len(older[key])], older[key]) for key, data in names.items()),
            'radiation_and_native_output_replayed': all(
                np.array_equal(total, states[mode]['total_cm3_s']) and np.array_equal(signal, states[mode][SIGNAL])
                and np.array_equal(signal, outputs[mode][:, :2].ravel())
                and np.array_equal(own[mode][0], outputs[mode][:, 2:])
                and pcm.bit_equal(own[mode][1], samples[mode])
                for mode in MODES for total, signal in (
                    radiation.radiation_from_components(states[mode], rate, mode == 'upstream'),)),
            'independent_focus_interventions_include_native_endpoints': (
                inputs['variants'][0]['precast'] == rounding['precast']['bernstein']
                and inputs['variants'][-1]['precast'] == rounding['precast']['upstream']
                and windows['variants'][0]['precast'] == rounding['precast']['bernstein']
                and components[0]['precast'] == rounding['precast']['bernstein']
                and components[-1]['first_pcm_difference_through_focus'] is None),
        },
        'predictions': {
            'same_coefficients_and_radiation_explains_output': same_coefficients and swaps_match,
            'first_pcm_is_adjacent_rounding': rounding['adjacent'] and rounding['straddles'],
            'upstream_derivative_order_alone_is_insufficient': not components[len(components) // 2]['matches_upstream_at_focus'],
            'current_gained_value_alone_recovers_2937': inputs['variants'][1]['matches_upstream_at_focus'],
        },
        'rounding': rounding, 'same_coefficients': same_coefficients, 'first_pcm_difference': first,
        'source_differences': source_differences, 'output_differences': output_differences,
        'dc_state_swaps': inputs, 'radiation_window_swaps': windows, 'radiation_component_swaps': components,
        'local_output': [{mode: dict(zip(pcm.COLUMNS, outputs[mode][i].tolist(), strict=True)) for mode in MODES}
                         | {'frame': i} for i in range(*m['comparison_frames'])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = pcm.WORKSPACE, pcm.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    bernstein, output, volume, matched = (tsp.open_run(study[key], revision)
                                          for key in ('bernstein', 'output', 'volume', 'matched'))
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    pcm_input = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial = tsp.verified_path(bernstein, 'artifacts/render.npz')
    prior = tsp.verified_path(volume, 'artifacts/prefix.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    inputs = [CASE, Path(__file__).resolve(), Path(pcm.__file__), config_path, spec, pcm_input, trial, prior, coefficients,
              *(run[0] / 'manifest.json' for run in (bernstein, output, volume, matched)),
              pcm.DICT, pcm.PROBE, pcm.OUTPUT_PATCH, pcm.SOURCE_PATCH, pcm.COEFFICIENTS,
              *(ws / 'tools' / name for name in ('tsp_fine_trace.rs', 'measure_tsp_fine_tip.py',
                 'measure_tsp_fine_variation.py', 'measure_duet_child_output_gain.py', 'measure_tsp_active_duration.py',
                 'measure_tsp_fk61_lip_front_radiation.py', 'measure_tsp_fk61_lip_onset.py', 'measure_uniform_tube.py')),
              *(upper / name for name in ('Cargo.lock', 'crates/chimera/src/voice/human_voice.rs',
                 'crates/chimera/src/airway/decimator.rs', 'crates/chimera/src/airway/network.rs',
                 'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/engine.rs'))]

    def measure(out, execute):
        expected = pcm.archived_pcm(pcm_input, uid)['upstream']
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        with np.load(prior, allow_pickle=False) as older:
            if not {'upstream_source', 'upstream_output', 'upstream_pcm'} <= set(older.files):
                raise ValueError('前回の観測に固定上流の放射・出力段・PCMが揃っていません')
            capture(study, config, spec, expected, out, execute)
            return analyze(study, config, gain, out, trial, older, tsp.read(coefficients), expected)

    info = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return pcm.record_measurement(args.run_id, CASE, inputs, info, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
