"""同じ混合体型の放射で、ピーク制限前とPCM保存後のゲイン適用を比べる。"""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import firwin, lfilter

import measure_duet_child_glottal_noise_origin as noise
from measure_duet_child_output_gain import difference, trace_input
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_pcm_output import OUTPUT_COLUMNS, PROBE, independent_limiter, read_columns
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/duet-mixed-limiter-gain-order.json'


def save_case(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


def render_comparison(study, references, out, execute):
    source = read_json(references['resting-tip.json'])
    upper_source = read_json(references['upper-2-input.json'])
    rate, frames = study['sample_rate_hz'], study['frames']
    boost = study['radiation_multiplier']
    base = study['base_gain']
    gains = {'base': base, 'body': base * study['body_gain_factor']}
    waves, traces, cli, plan_hashes = {}, {}, {}, {}
    with TemporaryDirectory(prefix='duet-limiter-probe-', dir=out.parent) as directory:
        scratch = Path(directory)
        local, upper = noise.build_observers(study['upstream_revision'], out, execute, scratch)
        for name, gain in gains.items():
            local_input = deepcopy(source)
            local_input['song_voice']['voice']['output_gain'] = boost * gain
            cases = {'candidate': save_case(out / f'{name}-case.json', local_input),
                     'upstream': save_case(out / f'{name}-upper-input.json',
                                            upper_source | {'probe_output_gain': boost * gain})}
            for block in study['block_frames']:
                wav = out / f'{name}-block-{block}.wav'
                execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
                         str(cases['candidate']), str(wav), '--no-trace', str(block)])
                cli[name, block] = wavfile.read(wav)
            for side, exe, dictionary, variant in (('candidate', local, 'local.dict', ()),
                                                    ('upstream', upper, 'upper.dict', ('without_all_three',))):
                stem = f'{side}-{name}'
                raw, stages = out / f'{stem}.f32le', out / f'{stem}-output.f64le'
                plan = out / f'{stem}-gestures.json'
                execute([str(exe), str(cases[side]), str(scratch / dictionary), '0', *variant,
                         str(out / f'{stem}-noise.csv'), str(raw), '--output-trace', str(stages)], stdout=plan)
                traces[side, name] = trace_input(stages, frames)
                waves[side, name] = np.fromfile(raw, dtype='<f4')
                plan_hashes[side, name] = sha256(plan)

    factor = study['internal_sample_rate_hz'] // rate
    raw = trace_input(references['base-output.f64le'], frames)[:, :2].ravel() * boost
    original_signal = out / 'scaled-radiation.txt'
    np.savetxt(original_signal, raw, fmt='%.17g')
    replay_dir = out / 'replay'
    replay_dir.mkdir()
    exe = build_upstream_probe(PROBE, replay_dir, execute)
    replay = {}
    for name, gain in gains.items():
        path = replay_dir / f'{name}-pcm.csv'
        execute([str(exe), str(factor), str(rate), str(gain), str(original_signal)], cwd=UPSTREAM, stdout=path)
        columns, replay[name] = read_columns(path, frames, len(OUTPUT_COLUMNS))
        if columns != OUTPUT_COLUMNS:
            raise ValueError('同一放射の再生結果に必要な観測列がありません')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    return source, upper_source, raw, gains, traces, waves, cli, plan_hashes, replay


def first_and_last(mask):
    transitions = np.flatnonzero(np.diff(mask.astype(np.int8), prepend=0, append=0))
    return [[int(start) + 1, int(end)] for start, end in transitions.reshape(-1, 2)]


def limiter_effect(trace, reference, wave, body_wave, study):
    threshold = study['stage']['peak_threshold']
    factor = study['body_gain_factor']
    tol = study['tolerances']['pcm_absolute']
    dc, envelope, hold = trace[:, 4:].T
    active = envelope > threshold
    previous_envelope = np.r_[0.0, envelope[:-1]]
    previous_hold = np.r_[0.0, hold[:-1]]
    quiet = np.abs(dc) <= threshold
    holding = active & quiet & (envelope == previous_envelope) & (previous_hold > 0)
    releasing = active & quiet & (envelope < previous_envelope)
    attenuation = threshold / np.maximum(envelope, threshold)
    post_scaled = wave.astype(float) * factor
    direct = body_wave.astype(float)
    observed = direct - post_scaled
    analytic = reference * factor * (1 - attenuation)
    result = {
        'before_vs_after_pcm': difference(direct, post_scaled, tol),
        'base_pcm_peak': float(np.max(np.abs(wave))),
        'before_limit_scale_peak': float(np.max(np.abs(direct))),
        'after_limit_scale_peak': float(np.max(np.abs(post_scaled))),
        'difference_formula_max_error': float(np.max(np.abs(observed - analytic))),
        'limiter_output_frames': int(np.count_nonzero(active)),
        'limiter_intervals': first_and_last(active),
        'meaningful_difference_outside_limiter': int(np.count_nonzero((np.abs(observed) > tol) & ~active)),
    }
    for phase, mask in (('hold', holding), ('release', releasing)):
        selected = np.abs(observed[mask])
        result[f'{phase}_below_threshold'] = {
            'frames': int(mask.sum()), 'first_frame': int(np.argmax(mask)) + 1 if np.any(mask) else None,
            'max_difference': float(selected.max(initial=0))}
    return result


def measure(study, references, out, execute):
    source, upper_source, raw, gains, traces, waves, cli, plan_hashes, replay = render_comparison(
        study, references, out, execute)
    rate, frames = study['sample_rate_hz'], study['frames']
    factor = study['internal_sample_rate_hz'] // rate
    stage = study['stage']
    boost = study['radiation_multiplier']
    tol = study['tolerances']
    taps = factor * stage['fir_taps_per_phase'] + 1
    kernel = firwin(taps, 2 * stage['fir_cutoff_at_output_rate'] / factor, window=('kaiser', stage['fir_kaiser_beta']))
    fir = np.convolve(raw, kernel)[:len(raw)][factor - 1::factor]
    raw_pairs = raw.reshape(-1, factor)
    pole = math.exp(-math.tau * stage['dc_hz'] / rate)
    comparisons, all_independent = {}, {}
    for name, gain in gains.items():
        dc = lfilter([1, -1], [1, -pole], fir * gain)
        env, hold, pcm = independent_limiter(dc, rate)
        all_independent[name] = dc
        data = replay[name]
        measurements = {
            'same_input_replay': (raw_pairs, data['decimated'], data['dc_removed'],
                                   data['limiter_envelope'], data['hold_frames'], data['pcm_f32'].astype('<f4')),
        }
        for side in ('candidate', 'upstream'):
            t = traces[side, name]
            measurements[side] = (t[:, :2] * boost, t[:, 2] * boost, t[:, 4], t[:, 5], t[:, 6], waves[side, name])
        comparisons[name] = {}
        for side, (radiation, decimated, measured_dc, envelope, remaining, wave) in measurements.items():
            bounded = measured_dc * (stage['peak_threshold'] / np.maximum(envelope, stage['peak_threshold']))
            comparisons[name][side] = {
                'radiation_cm3_s2': float(np.max(np.abs(radiation - raw_pairs))),
                'fir_times_gain': float(np.max(np.abs(decimated - fir)) * gain),
                'dc_removed': float(np.max(np.abs(measured_dc - dc))),
                'envelope': float(np.max(np.abs(envelope - env))),
                'hold_frames': float(np.max(np.abs(remaining - hold))),
                'pcm': difference(wave, pcm, tol['pcm_absolute']),
                'limiter_frames': int(np.count_nonzero(envelope > stage['peak_threshold'])),
                'soft_clip_frames': int(np.count_nonzero(np.abs(bounded) > stage['clip_threshold'])),
                'envelope_peak': float(envelope.max()),
            }

    target_trace = traces['candidate', 'base']
    reduction = limiter_effect(target_trace, all_independent['base'], waves['candidate', 'base'],
                               waves['candidate', 'body'], study)
    archived = trace_input(references['base-output.f64le'], frames)
    past_envelope_peak = float(archived[:, 5].max())
    predicted_base_peak = boost * past_envelope_peak
    predicted_body_peak = predicted_base_peak * study['body_gain_factor']
    predicted_post_peak = stage['peak_threshold'] * study['body_gain_factor']
    checks = {
        'registered_input': source['song_voice']['body'] == upper_source['body'] == study['reference_body']
        and source['song_voice']['voice']['output_gain'] == study['base_gain']
        and source['song_voice']['internal_sample_rate_hz'] == study['internal_sample_rate_hz']
        and source['song_voice']['voice']['output_sample_rate_hz'] == upper_source['sample_rate_hz'] == rate,
        'plans_unchanged': all(plan_hashes[side, name] == sha256(references[archive])
            for side, archive in (('candidate', 'resting_tip-gestures.json'), ('upstream', 'upstream-gestures.json'))
            for name in gains),
        'render_matches_cli_and_block_splits': all(sample_rate == rate and noise.bit_equal(captured, waves['candidate', name])
            for (name, _), (sample_rate, captured) in cli.items()),
        'finite_render_pcm_and_exact_length': all(wave.shape == (frames,) and np.isfinite(wave).all()
                                                 for wave in waves.values()),
        'unscaled_radiation_and_fir_unchanged': all(np.array_equal(traces[side, name][:, :3].view('<u8'),
            trace_input(references[archive], frames)[:, :3].view('<u8'))
            for side, archive in (('candidate', 'base-output.f64le'), ('upstream', 'upstream-output.f64le')) for name in gains),
        'gain_matches_inputs': all(np.array_equal(t[:, 3], t[:, 2] * (boost * gains[name]))
                                    for (_, name), t in traces.items()),
        'replay_clock_matches_output_clock': all(np.array_equal(columns['frame'], np.arange(frames))
            and np.array_equal(columns['internal_sample'], (np.arange(frames) + 1) * factor - 1)
            for columns in replay.values()),
        'independent_fir_dc_envelope_hold_and_pcm': all(
            row['radiation_cm3_s2'] <= tol['radiation_cm3_s2']
            and max(row[key] for key in ('fir_times_gain', 'dc_removed', 'envelope')) <= tol['normalized']
            and row['hold_frames'] == 0 and row['pcm']['first_over_tolerance_frame'] is None
            for sides in comparisons.values() for row in sides.values()),
        'gain_order_difference_matches_analytic_attenuation': reduction['difference_formula_max_error'] <= tol['pcm_absolute'],
    }
    predictions = {
        'only_base_gain_limits': all(row['limiter_frames'] > 0 for row in comparisons['base'].values())
        and all(row['limiter_frames'] == 0 for row in comparisons['body'].values()),
        'soft_clip_inactive': all(row['soft_clip_frames'] == 0 for sides in comparisons.values() for row in sides.values()),
        'gain_order_peaks_match_prediction': max(
            abs(comparisons['base']['candidate']['envelope_peak'] - predicted_base_peak),
            abs(reduction['before_limit_scale_peak'] - predicted_body_peak),
            abs(reduction['after_limit_scale_peak'] - predicted_post_peak),
            abs(reduction['before_vs_after_pcm']['peak_error'] - (predicted_body_peak - predicted_post_peak))
        ) <= tol['peak_prediction_absolute'],
        'post_scaled_diff_is_inside_limiter_interval': reduction['meaningful_difference_outside_limiter'] == 0
        and reduction['before_vs_after_pcm']['first_over_tolerance_frame'] is not None,
        'hold_and_release_prolong_difference_below_threshold': all(
            reduction[f'{phase}_below_threshold']['max_difference'] > tol['pcm_absolute'] for phase in ('hold', 'release')),
    }
    return {'checks': checks, 'predictions': predictions, 'scipy': scipy.__version__, 'frames': frames,
            'gains': gains, 'radiation_multiplier': boost,
            'reference_prediction': {'base_envelope_peak': predicted_base_peak, 'scaled_before_peak': predicted_body_peak,
                                     'scaled_after_peak': predicted_post_peak},
            'independent_comparisons': comparisons, 'gain_order': reduction}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDに使用できる文字を確認してください')
    study = read_json(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    dependencies = (
        ('reference', 'duet-mixed-output-gain', ('base-output.f64le', 'upstream-output.f64le')),
        ('posture', 'duet-mixed-initial-tip', ('resting-tip.json', 'resting_tip-gestures.json', 'upstream-gestures.json')),
        ('input', 'duet-head-turbulence-body', ('upper-2-input.json',)),
    )
    references, manifests = {}, []
    for key, case_id, files in dependencies:
        run = run_manifest(study[f'{key}_run'], case_id, revision)
        manifest = run[0] / 'manifest.json'
        if run[1]['status'] != 'pass' or sha256(manifest) != study[f'{key}_manifest_sha256']:
            parser.error(f'先行実行 {run[0].name} が登録と一致しません')
        references.update({name: verified_path(run, f'artifacts/{name}') for name in files})
        manifests.append(manifest)
    inputs = [CASE, Path(__file__).resolve(), Path(noise.__file__), noise.PATCH, noise.OUTPUT_PATCH, PROBE,
              *noise.PROBES, *noise.DICTIONARIES, noise.TOOLS / 'duet_child_noise_trace.rs', *manifests,
              *references.values(), *candidate_sources(),
              *(UPSTREAM / name for name in ('crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/src/airway/decimator.rs', 'crates/chimera-cli/src/render.rs',
                  'crates/chimera/tests/engine.rs', 'crates/chimera/tests/body_mix.rs')),
              *(noise.TOOLS / name for name in ('measure_duet_child_output_gain.py', 'measure_pcm_output.py', 'measure_junction.py',
                  'measure_uniform_tube.py', 'measure_fan_crossing_allocations.py', 'measure_wasm_fixed.py',
                  'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, metadata,
                              lambda out, execute: measure(study, references, out, execute),
                              command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
