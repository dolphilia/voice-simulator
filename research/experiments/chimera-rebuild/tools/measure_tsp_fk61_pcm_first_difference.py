"""FK61_01の最初のPCM差を放射入力からfloat32変換まで照合する。"""

import argparse
import gzip
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import COLUMNS, independent_stages, trace_input
from measure_tsp_active_duration import read_generated
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_tip import radiated, read_series
from measure_tsp_fine_variation import DICT, FIELDS, LOCAL, OUTPUT_PATCH, PROBE, SOURCE_PATCH, signal_difference
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fk61-pcm-first-difference.json'
COEFFICIENTS = WORKSPACE / 'tools/tsp_pcm_output_coefficients.rs'
MODES = ('upstream', 'candidate')


def limited_output(dc, envelope, stage):
    """ピーク抑制とソフトクリップを適用し、float32変換直前の値を返す。"""
    adjusted = dc.copy()
    peak = stage['peak_threshold']
    active = envelope > peak
    adjusted[active] *= peak / envelope[active]
    clip = stage['clip_threshold']
    magnitude = np.abs(adjusted)
    softened = magnitude > clip
    if np.any(softened):
        width = 0.15
        curve = clip + width * np.tanh((magnitude[softened] - clip) / width)
        adjusted[softened] = np.copysign(curve, adjusted[softened])
    return adjusted, active, softened


def replay(radiation, coefficients, gain, config, *, state_trim=None, output_limiter=False):
    stage = config['stage']
    rate = config['sample_rate_hz']
    factor = config['internal_sample_rate_hz'] // rate
    taps = coefficients['taps'][::-1]
    samples = np.pad(np.asarray(radiation, dtype=np.float64), (len(taps) - 1, 0))
    frames = len(radiation) // factor
    result = np.empty((frames, 5))
    decimated, gained = result[:, 0], result[:, 1]
    decimated.fill(0.0)
    product = np.empty(frames)
    # 各出力の加算順を保ち、同じタップを全フレームに一度に適用する。
    for offset, coefficient in enumerate(taps, start=factor - 1):
        np.multiply(samples[offset:offset + frames * factor:factor], coefficient, out=product)
        np.add(decimated, product, out=decimated)
    np.multiply(decimated, gain, out=gained)
    previous_input = highpassed = envelope = 0.0
    hold = 0
    duration = round(rate * stage['hold_seconds'])
    for n, value in enumerate(map(float, gained)):
        if state_trim is not None:
            interval, threshold = state_trim
            if (n * factor) % interval == 0:
                previous_input = 0.0 if abs(previous_input) < threshold else previous_input
                highpassed = 0.0 if abs(highpassed) < threshold else highpassed
                envelope = 0.0 if abs(envelope) < threshold else envelope
        highpassed = value - previous_input + coefficients['dc_pole'] * highpassed
        previous_input = value
        if abs(highpassed) >= envelope:
            envelope, hold = abs(highpassed), duration
        elif hold:
            hold -= 1
        else:
            envelope *= coefficients['release']
        result[n, 2:] = highpassed, envelope, hold
    if output_limiter:
        precast, _, _ = limited_output(result[:, 2], result[:, 3], stage)
    elif np.any(result[:, 3] > stage['peak_threshold']) or np.any(np.abs(result[:, 2]) > stage['clip_threshold']):
        raise ValueError('観測区間でリミッターが作動し、DC出力を変換前の値に使えません')
    else:
        precast = result[:, 2]
    return result, precast.astype('<f4')


def midpoint_report(frame, outputs, pcm):
    dc = COLUMNS.index('dc_removed')
    before_cast = {name: float(outputs[name][frame, dc]) for name in MODES}
    stored = {name: float(pcm[name][frame]) for name in MODES}
    low, high = sorted(stored.values())
    midpoint = (low + high) / 2
    offsets = {name: value - midpoint for name, value in before_cast.items()}
    adjacent = np.nextafter(np.float32(low), np.float32(high)) == np.float32(high) and low != high
    return {'frame': frame, 'precast': before_cast, 'pcm': stored, 'midpoint': midpoint,
            'from_midpoint': offsets, 'adjacent': bool(adjacent), 'straddles': min(offsets.values()) < 0 < max(offsets.values())}


def evaluate(case, config, gain, captured, coefficients, expected_pcm, ordinary_matches):
    cfg = case['measurement']
    count = cfg['frame_count']
    states = {name: dict(zip(FIELDS, captured[f'{name}_state'].T, strict=True)) for name in MODES}
    outputs = {name: captured[f'{name}_output'] for name in MODES}
    pcm = {name: captured[f'{name}_pcm'] for name in MODES}
    radiation = {name: states[name]['radiation_derivative_cm3_s2'] for name in MODES}
    source_differences = {key: signal_difference(states['upstream'][key], states['candidate'][key]) for key in FIELDS}
    output_differences = {key: signal_difference(outputs['upstream'][:, i], outputs['candidate'][:, i])
                          for i, key in enumerate(COLUMNS)}
    pcm_delta = signal_difference(pcm['upstream'], pcm['candidate'])
    first = pcm_delta['first_unequal_sample']
    if first is None:
        raise ValueError('最初の2048フレームにPCM差がありません')
    own_replay = {name: replay(radiation[name], coefficients[name], gain, config) for name in MODES}
    interchanged = {dest: bit_equal(replay(radiation[src], coefficients[dest], gain, config)[1], pcm[src])
                    for src, dest in (MODES, MODES[::-1])}
    same_parameters = coefficients['upstream'] == coefficients['candidate']
    independent = {name: independent_stages(outputs[name], pcm[name], gain, config | {'base_gain': gain})
                   for name in MODES}
    physical = {name: radiated(config, states[name], outputs[name]) for name in MODES}
    radiation_first = source_differences['radiation_derivative_cm3_s2']['first_unequal_sample']
    rounding = midpoint_report(first, outputs, pcm)
    frame_begin, frame_end = cfg['comparison_frames']
    local_trace = [
        {'frame': n, 'outputs': {name: dict(zip(COLUMNS, outputs[name][n].tolist(), strict=True)) for name in MODES},
         'pcm': {name: float(pcm[name][n]) for name in MODES}}
        for n in range(frame_begin, frame_end)]
    limit = config['limits']['independent_normalized']
    return {
        'checks': {
            'ordinary_pcm_matches_probes_archives_and_first_frame': (
                all(ordinary_matches.values())
                and all(bit_equal(pcm[name], expected_pcm[name][:count]) for name in MODES)
                and first == cfg['expected_first_pcm_frame']),
            'radiation_columns_and_independent_filter_replay': (
                all(r['timeline_matches'] for r in physical.values())
                and all(all(row[key] <= limit for key in ('fir_error_times_base_gain', 'gain_input_error', 'dc_error',
                                                          'envelope_error')) and row['hold_error_frames'] == 0
                        and row['pcm_matches_independent_limiter'] for row in independent.values())),
            'ordered_exact_replay_matches_each_native_output': all(
                np.array_equal(own_replay[name][0], outputs[name][:, 2:]) and bit_equal(own_replay[name][1], pcm[name])
                for name in MODES),
            'recorded_precast_values_round_to_the_observed_pcm': all(
                bit_equal(outputs[name][:, COLUMNS.index('dc_removed')].astype('<f4'), pcm[name]) for name in MODES),
        },
        'predictions': {
            'radiation_difference_precedes_pcm': radiation_first is not None
                and radiation_first // (config['internal_sample_rate_hz'] // config['sample_rate_hz']) < first,
            'same_output_parameters_transfer_radiation_difference': same_parameters and all(interchanged.values()),
            'first_pcm_difference_straddles_rounding_midpoint': rounding['adjacent'] and rounding['straddles'],
        },
        'input_swap_matches_source_pcm': interchanged, 'same_filter_parameters': same_parameters,
        'rounding': rounding, 'source_differences': source_differences, 'output_differences': output_differences,
        'pcm_difference': pcm_delta, 'local_trace': local_trace, 'physical_checks': physical,
        'independent_checks': independent, 'ordinary_matches': ordinary_matches,
    }


def build_pair(name, scratch, checkout, execute):
    fixed = name == 'upstream'
    target = scratch / f'{name}-target'
    root = checkout if fixed else WORKSPACE
    package = 'chimera' if fixed else 'vocal-core'
    cli = 'chimera-cli' if fixed else 'vocal-cli'
    flags = ('--offline', '--target-dir', str(target))
    probe = build_upstream_probe(PROBE if fixed else LOCAL, scratch, execute, upstream=root, package=package,
                                 lto='fat' if fixed else 'off', extra_libraries=('serde_json',),
                                 rustc_args=('--cfg', 'tsp_voice_probe') if fixed else (), cargo_args=flags)
    coefficients = build_upstream_probe(COEFFICIENTS, scratch, execute, upstream=root, package=package,
        lto='fat' if fixed else 'off', extra_libraries=('serde_json',) if fixed else ('serde_json', 'libm'),
        rustc_args=() if fixed else ('--cfg', 'tsp_candidate_output'), cargo_args=flags)
    execute(['cargo', 'build', '--locked', '--release', '-p', cli, *flags], cwd=UPSTREAM if fixed else root)
    return probe, coefficients, target / 'release' / ('chimera' if fixed else 'vocal-cli')


def capture(case, config, spec, expected_pcm, out, execute):
    cfg = case['measurement']
    count = cfg['frame_count']
    rate = config['sample_rate_hz']
    factor = config['internal_sample_rate_hz'] // rate
    setting = tsp.read(spec)['speech_voice']
    f0 = config['body']['female']['base_f0_hz']
    text = setting['input']['text']
    coefficients, retained, matches = {}, {}, {}
    with TemporaryDirectory(prefix='tsp-fk61-pcm-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = scratch / 'upstream'
        checkout.mkdir()
        tarball = scratch / 'upstream.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tarball)
        execute(['tar', '-xf', str(tarball), '-C', str(checkout)])
        for patch in (OUTPUT_PATCH, SOURCE_PATCH):
            execute(['git', 'apply', str(patch)], cwd=checkout)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        for name in MODES:
            probe, coefficient_probe, cli = build_pair(name, scratch, checkout, execute)
            coefficient_path = scratch / f'{name}-coefficients.json'
            execute([str(coefficient_probe)], stdout=coefficient_path)
            coefficients[name] = tsp.read(coefficient_path)
            wave = scratch / f'{name}-normal.wav'
            trace, raw, output = (scratch / f'{name}.{suffix}' for suffix in ('source', 'f32le', 'stage'))
            if name == 'upstream':
                execute([str(cli), 'render', 'text', str(wave), text, 'female', '--float'], cwd=UPSTREAM)
                execute([str(probe), str(spec), str(dictionary), str(trace), str(raw),
                         str(scratch / 'upstream-plan.json'), str(count), 'default', str(output)])
            else:
                execute([str(cli), 'render-pcm', str(spec), str(wave), '--no-trace', str(cfg['block_frames'])])
                execute([str(probe), str(spec), str(dictionary), str(count), str(cfg['initial_f0_hz']), str(f0),
                         *map(str, (trace, raw, output))])
            samples = read_generated(wave, rate)
            observed = np.fromfile(raw, dtype='<f4')
            matches[name] = bit_equal(samples, expected_pcm[name]) and bit_equal(samples, observed)
            series = read_series(trace, count * factor)
            retained[f'{name}_state'] = np.column_stack([series[key] for key in FIELDS])
            retained[f'{name}_output'] = trace_input(output, count)
            retained[f'{name}_pcm'] = observed[:count]
    (out / 'coefficients.json').write_text(json.dumps(coefficients, indent=2) + '\n')
    (out / 'ordinary-pcm.json').write_text(json.dumps(matches, indent=2) + '\n')
    np.savez_compressed(out / 'prefix.npz', **retained)
    return retained, coefficients, matches


def archived_pcm(path, uid):
    with np.load(path, allow_pickle=False) as data:
        return {name: data[f'{uid}_{name}'] for name in MODES}


def measure(case, config, spec, archived, out, execute):
    retained, coefficients, matches = capture(case, config, spec, archived, out, execute)
    gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
    return evaluate(case, config, gain, retained, coefficients, archived, matches)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    baseline, matched = (tsp.open_run(case[key], rev) for key in ('baseline', 'matched'))
    config, config_path = saved_case(matched, WORKSPACE / 'cases/tsp-held-out-matched-speech.json')
    summary = tsp.verified_path(baseline, 'summary.json')
    uid = case['measurement']['recording_id']
    if tsp.read(summary)['stages'][uid]['pcm_first_difference'] != case['measurement']['expected_first_pcm_frame']:
        parser.error('先行計測の最初の差が登録値と一致しません')
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    stored = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    saved = archived_pcm(stored, uid)
    inputs = [CASE, Path(__file__).resolve(), COEFFICIENTS, LOCAL, PROBE, DICT, OUTPUT_PATCH, SOURCE_PATCH,
              WORKSPACE / 'tools/tsp_fine_trace.rs', config_path, summary, spec, stored,
              baseline[0] / 'manifest.json', matched[0] / 'manifest.json', *candidate_sources(),
              *(UPSTREAM / name for name in ('Cargo.lock', 'crates/chimera/src/voice/human_voice.rs',
                'crates/chimera/src/airway/decimator.rs', 'crates/chimera-cli/src/render.rs'))]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': rev}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, config, spec, saved, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
