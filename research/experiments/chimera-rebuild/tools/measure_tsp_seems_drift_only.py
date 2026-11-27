"""上流のドリフト振幅だけを変え、seems の母音中央を比較する。"""

import argparse
import gzip
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_duet_child_output_gain as output_stage
import measure_tsp_seems_spectrum_stages as stages
import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_tsp_f2_bandwidth_envelope import PROBE as LPC_PROBE
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import FIELDS, first_difference
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-seems-drift-only.json'
UPSTREAM_CONDITIONS = {'upstream': 'default', 'drift_zero': 'drift_zero'}
CONDITIONS = (*UPSTREAM_CONDITIONS, 'candidate')


def gaussians(seed):
    """周期変動とドリフトに使う乱数をRustとは別に計算する。"""
    state = seed or 1
    mask = (1 << 32) - 1

    def uniform():
        nonlocal state
        state = (state + 0x6d2b79f5) & mask
        value = ((state ^ (state >> 15)) * (state | 1)) & mask
        inner = ((value ^ (value >> 7)) * (value | 61)) & mask
        value ^= (value + inner) & mask
        return (value ^ (value >> 14)) / (1 << 32)

    while True:
        yield (sum(uniform() for _ in range(4)) - 2) * 1.7320508


def drift_cents(settings, rate, samples):
    interval = settings['control_interval_samples']
    amplitude = settings['default_cents'] - settings['disabled_cents']
    base = settings['filter_base_hz']
    poles = [math.exp(-math.tau * base * ratio * interval / rate) for ratio in (1, 3, 9)]
    gains = [math.sqrt(1 - pole ** 2) for pole in poles]
    filtered = [0.0] * len(poles)
    gaussian = gaussians(settings['seed'])
    control = []
    for _ in range(0, samples, interval):
        for index, (pole, gain) in enumerate(zip(poles, gains, strict=True)):
            filtered[index] = pole * filtered[index] + gain * next(gaussian)
        control.append(amplitude * sum(value / index for index, value in enumerate(filtered, 1)) / 1.4)
    return np.repeat(control, interval)[:samples]


def capture(base, original, reference_wav, out, execute, *, pressure_patch=None, cycle_patch=None,
            include_shimmer_zero=False, variants=None):
    frames = base['trace_frames']
    factor = base['internal_sample_rate_hz'] // base['sample_rate_hz']
    text = tsp.read(original)['speech_voice']['input']['text']
    with TemporaryDirectory(prefix='seems-drift-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        fixed = tmp / 'upstream'
        fixed.mkdir()
        tar = tmp / 'fixed.tar'
        execute(['git', 'archive', base['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(fixed)])
        patches = [stages.OUTPUT_PATCH, stages.SOURCE_PATCH]
        rustc_args = ['--cfg', 'tsp_voice_probe']
        conditions = dict(UPSTREAM_CONDITIONS if variants is None else variants)
        donors = {'pressure_self': 'drift_zero', 'pressure_replay': 'upstream'}
        if pressure_patch is not None:
            patches.append(pressure_patch)
            rustc_args.extend(('--cfg', 'tsp_pressure_replay'))
            conditions.update(dict.fromkeys(donors, 'drift_zero'))
        if cycle_patch is not None:
            patches.append(cycle_patch)
            rustc_args.extend(('--cfg', 'tsp_cycle_scales'))
            conditions['jitter_zero'] = 'jitter_zero'
            if include_shimmer_zero:
                conditions['shimmer_zero'] = 'zero'
        for patch in patches:
            execute(['git', 'apply', str(patch)], cwd=fixed)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(stages.DICT.read_bytes()))
        probe = build_upstream_probe(stages.PROBE, tmp, execute, upstream=fixed, extra_libraries=('serde_json',),
                                     rustc_args=rustc_args, cargo_args=('--offline',))
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'voice_source',
                 '--test', 'golden_voice', '--test', 'golden_analysis'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
        ordinary = tmp / 'ordinary.wav'
        execute([str(UPSTREAM / 'target/release/chimera'), 'render', 'text', str(ordinary), text, 'male', '--float'],
                cwd=UPSTREAM)
        rate, np_wave = wavfile.read(ordinary)
        signals, plans, verification, pressure, cycles = {}, {}, {}, {}, {}
        for name, variant in conditions.items():
            state, pcm, output = (tmp / f'{name}-{file}' for file in ('state.f64', 'pcm.f32', 'output.f64'))
            plan = out / f'{name}-plan.json'
            argv = [str(probe), str(original), str(dictionary), str(state), str(pcm), str(plan),
                    str(frames), variant, str(output)]
            if pressure_patch is not None:
                pressure_trace = tmp / f'{name}-pressure.f64'
                env = ['env', '-u', 'CHIMERA_PROBE_PRESSURE_INPUT', f'CHIMERA_PROBE_PRESSURE_TRACE={pressure_trace}']
                if name in donors:
                    path = tmp / f'{name}-drive.f64'
                    pressure[donors[name]][:, 0].tofile(path)
                    env.append(f'CHIMERA_PROBE_PRESSURE_INPUT={path}')
                argv = env + argv
            if cycle_patch is not None:
                cycle_trace = tmp / f'{name}-cycle.f64'
                argv = ['env', f'CHIMERA_PROBE_CYCLE_TRACE={cycle_trace}', *argv]
            execute(argv)
            trace = np.fromfile(state, dtype='<f8').reshape(-1, len(FIELDS))
            wave = np.fromfile(pcm, dtype='<f4')
            if (trace.shape[0] != frames * factor or wave.shape != np_wave.shape
                    or not np.isfinite(trace).all() or not np.isfinite(wave).all()):
                raise ValueError(f'観測系列の長さまたは有限性が登録値と一致しません ({name})')
            signals[name] = dict(zip(FIELDS, trace.T, strict=True)), output_stage.trace_input(output, frames), wave[:frames]
            plans[name] = sha256(plan)
            verification[name] = {'frames': len(wave), 'pcm_sha256': sha256(pcm)}
            if pressure_patch is not None:
                measured = np.fromfile(pressure_trace, dtype='<f8').reshape(-1, 2)
                if measured.shape[0] != len(wave) * factor or not np.isfinite(measured).all():
                    raise ValueError(f'圧差系列の長さまたは有限性が登録値と一致しません ({name})')
                pressure[name] = measured
            if cycle_patch is not None:
                scales = np.fromfile(cycle_trace, dtype='<f8').reshape(-1, 2)
                if scales.shape[0] != len(trace) or not np.isfinite(scales).all():
                    raise ValueError(f'周期倍率の長さまたは有限性が登録値と一致しません ({name})')
                cycles[name] = scales
            if variant == 'default':
                verification['default_matches_ordinary_pcm'] = np_wave.dtype == np.float32 and bit_equal(np_wave, wave)
        verification['ordinary_matches_archived_wav'] = rate == base['sample_rate_hz'] and sha256(ordinary) == sha256(reference_wav)
        verification['same_plan'] = len(set(plans.values())) == 1
    return signals, verification, pressure, cycles


def analyze(base, cfg, signals, previous, out, execute):
    start = base['window_start_12khz']
    stop = start + base['window_samples_12khz']
    factor = base['internal_sample_rate_hz'] // base['sample_rate_hz']
    rate = base['internal_sample_rate_hz']
    offset = start * cfg['decimation']
    end = stop * cfg['decimation']
    internal = slice(offset * factor, end * factor)
    flows, lpc_frames, output_checks = {}, {}, {}
    windows = {}
    for name, (state, output, pcm) in signals.items():
        radiation = state['radiation_derivative_cm3_s2']
        recovered = stages.replay(base, radiation)
        total = state['total_cm3_s']
        sections = state['lip_cm3_s'] + state['nose_cm3_s'] + state['wall_cm3_s']
        output_checks[name] = {
            **output_stage.independent_stages(output, pcm, base['base_gain'], base),
            'same_radiation_series': np.array_equal(radiation, output[:, :2].ravel()),
            'radiation_sum_error_cm3_s': float(np.max(abs(sections - total))),
            'radiation_derivative_error_cm3_s2': float(np.max(abs(np.diff(total, prepend=0) * rate - radiation))),
            'full_replay_peak_pcm_error': float(np.max(abs(recovered.astype(float) - pcm))),
        }
        flows[name] = state['glottal_flow_cm3_s'][internal]
        lpc_frames[name] = tsp.analysis_downsample(pcm.astype(float), cfg)[start:stop]
        windows.update({f'{name}_{field}': samples[internal] for field, samples in state.items()})
    with np.load(previous, allow_pickle=False) as saved:
        agrees = np.array_equal(flows['upstream'], saved['upstream_glottal_flow_cm3_s'])
        agrees = agrees and np.array_equal(lpc_frames['upstream'], saved['lpc_upstream_pcm'])
        if 'candidate' in signals:
            agrees = agrees and np.array_equal(flows['candidate'], saved['candidate_glottal_flow_cm3_s'])
            agrees = agrees and np.array_equal(lpc_frames['candidate'], saved['lpc_candidate_pcm'])
        else:
            flows['candidate'] = saved['candidate_glottal_flow_cm3_s']
            lpc_frames['candidate'] = saved['lpc_candidate_pcm']
    windows.update({f'{name}_lpc_pcm': frame for name, frame in lpc_frames.items()})
    windows['candidate_glottal_flow_cm3_s'] = flows['candidate']
    np.savez_compressed(out / 'drift-windows.npz', **windows)
    grid, powers, dft_errors = stages.window_spectra(base['spectra'], rate, flows)
    np.savez_compressed(out / 'drift-spectra.npz', frequency_hz=grid, **powers)
    distributions = {name: stages.compare_spectra(base['spectra'], grid, powers[name], powers['candidate'])
                     for name in signals if name != 'candidate'}
    poles, errors = stages.high_lpc_poles(base, cfg, lpc_frames, out, execute)
    limits = base['limits']
    qualifies = all(pole is not None for pole in poles.values())
    checks = {
        'default_window_matches_archive': agrees,
        'both_radiation_and_output_stages_agree': all(
            row['same_radiation_series'] and row['radiation_sum_error_cm3_s'] <= limits['radiation_sum_cm3_s']
            and row['radiation_derivative_error_cm3_s2'] <= limits['radiation_identity_cm3_s2']
            and all(row[field] <= limits['independent_normalized'] for field in
                    ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
            and row['hold_error_frames'] == 0 and row['pcm_matches_independent_limiter']
            and row['full_replay_peak_pcm_error'] <= limits['full_output_replay_absolute'] for row in output_checks.values()),
        'spectra_match_direct_dft': max(dft_errors.values()) <= limits['relative_dft_agreement']
            and all(metric is not None for metric in distributions.values()),
        'lpc_matches_independent': qualifies and all(
            error is not None and error <= cfg['frequency_bandwidth_agreement_hz'] for error in errors),
    }
    return checks, {
        'pcm_frame_interval': [offset, end], 'internal_sample_interval': [internal.start, internal.stop],
        'output_stage': output_checks, 'max_relative_dft_error': max(dft_errors.values()),
        'independent_lpc_errors_hz': dict(zip(lpc_frames, errors, strict=True)),
        'glottal_distance_to_candidate': distributions, 'lpc_high_poles_hz': poles,
    }


def measure(case, base, cfg, original, reference_wav, previous, out, execute):
    signals, verification, _, _ = capture(base, original, reference_wav, out, execute)
    checks, result = analyze(base, cfg, signals, previous, out, execute)
    one, two = (signals[name] for name in UPSTREAM_CONDITIONS)
    upstream, disabled = one[0], two[0]
    rate = base['internal_sample_rate_hz']
    expected = drift_cents(case['source_drift'], rate, len(upstream['f0_hz']))
    actual = 1200 * np.log2(upstream['f0_hz'] / disabled['f0_hz'])
    error = float(np.max(abs(actual - expected)))
    np.savez_compressed(out / 'pitch-trace.npz', upstream_f0_hz=upstream['f0_hz'], drift_zero_f0_hz=disabled['f0_hz'],
                        expected_cents=expected)
    first = {field: first_difference(upstream[field] - disabled[field]) for field in FIELDS}
    first_pcm = first_difference(one[2] - two[2])
    by_mode = result['glottal_distance_to_candidate']
    poles = result['lpc_high_poles_hz']
    glottal_shift = (by_mode['upstream']['total_variation_high_band'] - by_mode['drift_zero']['total_variation_high_band']
                     if all(by_mode.values()) else None)
    lpc_gap = ({name: poles['candidate'][0] - poles[name][0] for name in UPSTREAM_CONDITIONS}
               if all(poles.values()) else {})
    lpc_convergence = abs(lpc_gap['upstream']) - abs(lpc_gap['drift_zero']) if lpc_gap else None
    checks.update(
        default_cli_pcm_and_plans_match=all(verification[key] for key in
                                           ('default_matches_ordinary_pcm', 'ordinary_matches_archived_wav', 'same_plan')),
        independent_drift_f0_ratio=bool(np.isfinite(actual).all() and error <= case['limits']['pitch_ratio_agreement_cents']),
    )
    predictions = {
        'first_change_is_f0_and_phase': first['f0_hz'] == first['phase'] == 0 and checks['independent_drift_f0_ratio'],
        'glottal_distribution_moves_toward_candidate': glottal_shift is not None and glottal_shift > 0,
        'pcm_pole_moves_toward_candidate': lpc_convergence is not None
            and lpc_convergence >= case['limits']['meaningful_lpc_convergence_hz'],
    }
    start, stop = result['internal_sample_interval']
    return {'checks': checks, 'predictions': predictions, **result, 'pcm_verification': verification,
            'first_different_internal_sample': first, 'first_different_pcm_frame': first_pcm,
            'pitch_ratio_max_error_cents': error, 'pitch_ratio_internal_samples': len(expected),
            'drift_cents_in_window': [float(actual[start:stop].min()), float(actual[start:stop].max())],
            'glottal_distance_reduction': glottal_shift, 'lpc_high_candidate_minus_upstream_hz': lpc_gap,
            'lpc_gap_reduction_hz': lpc_convergence}


def reference_inputs(spec, revision):
    prior = tsp.open_run(spec, revision)
    base, base_path = saved_case(prior, stages.CASE)
    transfer = tsp.open_run(base['transfer_reference'], revision)
    transfer_case, transfer_path = saved_case(transfer, stages.TRANSFER_CASE)
    render = tsp.open_run(transfer_case['render'], revision)
    source = tsp.open_run(transfer_case['source_comparison'], revision)
    source_case, source_path = saved_case(source, WORKSPACE / 'cases/tsp-f2-source-comparison.json')
    diagnostic = tsp.open_run(source_case['diagnostic'], revision)
    diagnostic_case, cfg_path = saved_case(diagnostic, tsp.CASE)
    uid = transfer_case['target']['utterance']
    original = tsp.verified_path(render, f'artifacts/{uid}/candidate.json')
    reference_wav = tsp.verified_path(render, f'artifacts/{uid}/upstream.wav')
    previous = tsp.verified_path(prior, 'artifacts/stage-windows.npz')
    modules = ('measure_tsp_seems_spectrum_stages.py', 'measure_duet_child_output_gain.py',
               'measure_duet_child_glottal_noise_origin.py', 'measure_tsp_fine_variation.py', 'tsp_fine_trace.rs',
               'measure_tsp_stressed_vowel_formants.py', 'measure_tsp_f2_bandwidth_envelope.py',
               'measure_tsp_lpc_order_recordings.py', 'measure_tsp_f2_bandwidth_held_out.py',
               'measure_uniform_tube.py', 'upstream_baseline.py')
    upstream_sources = ('src/math.rs', 'src/sources/glottis.rs', 'src/voice/human_voice.rs',
                        'tests/golden_voice.rs', 'tests/voice_source.rs', 'tests/golden_analysis.rs')
    paths = [Path(__file__).resolve(), base_path, transfer_path, source_path, cfg_path, original, reference_wav,
             previous, stages.PROBE, stages.OUTPUT_PATCH, stages.SOURCE_PATCH, stages.DICT, LPC_PROBE,
             *(run[0] / 'manifest.json' for run in (prior, transfer, render, source, diagnostic)),
             *(WORKSPACE / 'tools' / name for name in modules),
             *(UPSTREAM / 'crates/chimera' / name for name in upstream_sources),
             UPSTREAM / 'crates/chimera-cli/src/render.rs']
    return base, diagnostic_case['measurement'], original, reference_wav, previous, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    base, cfg, original, reference_wav, previous, paths = reference_inputs(case['reference'], revision)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, [CASE, *paths], details,
        lambda out, execute: measure(case, base, cfg, original, reference_wav, previous, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
