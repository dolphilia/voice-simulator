"""周期長のジッターだけを両版で切り替え、声門の状態とPCMを照合する。"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_tsp_seems_drift_only as drift
import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import trace_input
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import DICT, FIELDS, LOCAL, first_difference
from measure_tsp_seems_spectrum_stages import compare_spectra
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-seems-period-jitter.json'
PRESSURE_CASE = WORKSPACE / 'cases/tsp-seems-pressure-replay.json'
PATCH = WORKSPACE / 'tools/patches/upstream-tsp-cycle-scales.patch'
PAIRS = {'upstream': ('jitter_zero', 'drift_zero'), 'candidate': ('candidate', 'candidate_jitter')}
PARTS = ('upstream', 'drift_zero', 'jitter_zero', 'candidate', 'candidate_jitter')


def candidate_capture(base, original, saved_wav, saved_plan, out, execute, *, adjustment,
                      adjustment_section='source_variation', snapshot_request=None):
    variant, field, amount = adjustment
    frames = base['trace_frames']
    factor = base['internal_sample_rate_hz'] // base['sample_rate_hz']
    rate = base['sample_rate_hz']
    altered = tsp.read(original)
    variation = altered['speech_voice'].setdefault(adjustment_section, {})
    variation[field] = amount
    altered_path = out / f"{variant.replace('_', '-')}-case.json"
    altered_path.write_text(json.dumps(altered, ensure_ascii=False, indent=2) + '\n')
    signals, amplitudes, pcm_checks, plans = {}, {}, {}, {}
    with TemporaryDirectory(prefix='seems-candidate-jitter-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        rustc_args = ('--cfg', 'tsp_tract_snapshot') if snapshot_request is not None else ()
        probe = build_upstream_probe(LOCAL, tmp, execute, upstream=WORKSPACE, package='vocal-core', lto='off',
                                     extra_libraries=('serde_json',), rustc_args=rustc_args, cargo_args=('--offline',))
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'], stdout=out / 'candidate-tests.log')
        cli = str(WORKSPACE / 'target/release/vocal-cli')
        for name, source in (('candidate', original), (variant, altered_path)):
            path = out / f'{name}-plan.json'
            execute([cli, 'inspect', str(source)], stdout=path)
            plans[name] = tsp.read(path)
            ordinary = tmp / f'{name}.wav'
            state, pcm, output, amplitude = (tmp / f'{name}-{file}' for file in
                                               ('state.f64', 'pcm.f32', 'output.f64', 'amplitude.f64'))
            execute([cli, 'render-pcm', str(source), str(ordinary), '--no-trace', '128'])
            argv = [str(probe), str(source), str(dictionary), str(frames), str(base['initial_f0_hz']),
                    str(base['base_f0_hz']), *map(str, (state, pcm, output, amplitude))]
            if snapshot_request is not None:
                argv.extend((str(snapshot_request), str(out / f'{name}-initial-geometry.json')))
            execute(argv)
            raw = np.fromfile(state, dtype='<f8').reshape(-1, len(FIELDS))
            waveform = np.fromfile(pcm, dtype='<f4')
            scales = np.fromfile(amplitude, dtype='<f8')
            if (raw.shape[0] != frames * factor or len(scales) != len(raw) or len(waveform) < frames
                    or not all(np.isfinite(values).all() for values in (raw, waveform, scales))):
                raise ValueError(f'研究版の観測範囲が登録内容と一致しません ({name})')
            observed_rate, rendered = wavfile.read(ordinary)
            pcm_checks[name] = {'pcm_matches_candidate_cli': observed_rate == rate and bit_equal(rendered, waveform),
                                'frames': len(waveform), 'pcm_sha256': sha256(pcm)}
            if name == 'candidate':
                pcm_checks[name]['default_wav_matches_archive'] = sha256(ordinary) == sha256(saved_wav)
            amplitudes[name] = scales
            signals[name] = (dict(zip(FIELDS, raw.T, strict=True)), trace_input(output, frames), waveform[:frames])
    archived_plan = tsp.read(saved_plan)
    keys = ('gestures', 'speech', 'output_frames')
    plan_match = all(plans['candidate'][key] == plans[variant][key] == archived_plan[key] for key in keys)
    return signals, amplitudes, pcm_checks, plan_match


def cycle_model(settings, rate, f0, jitter, shimmer):
    phase, period, amplitude = 0.0, 1.0, 1.0
    phases = np.empty(len(f0))
    scales = np.empty((len(f0), 2))
    boundaries = []
    gaussian = drift.gaussians(settings['seed'])
    low, high = settings['period_scale_bounds']
    for index, step in enumerate(f0 / rate):
        phase += float(step) / period
        if phase >= 1:
            phase -= 1
            period = min(high, max(low, 1 + jitter * next(gaussian)))
            amplitude = max(settings['amplitude_scale_min'], 1 + shimmer * next(gaussian))
            boundaries.append(index)
        phases[index] = phase
        scales[index] = (period, amplitude)
    return phases, scales, np.array(boundaries, dtype=int)


def cycle_parameters(settings, name):
    jitter = settings['jitter_inactive'] if name in ('jitter_zero', 'candidate') else settings['jitter_active']
    shimmer = settings['candidate_shimmer'] if name in PAIRS['candidate'] else settings['upstream_shimmer']
    return jitter, shimmer


def phase_wraps(phase):
    return np.flatnonzero(np.diff(phase) < 0) + 1


def compare_cycles(case, base, signals, cycles, amplitudes, out, *, pairs=PAIRS, parameters=cycle_parameters):
    settings = case['cycle']
    rate = base['internal_sample_rate_hz']
    checks, comparisons, traces, boundaries = {}, {}, {}, {}
    for name, (state, _, _) in signals.items():
        f0, phase = state['f0_hz'], state['phase']
        jitter, shimmer = parameters(settings, name)
        expected_phase, expected_scales, expected_wraps = cycle_model(settings, rate, f0, jitter, shimmer)
        amplitude = amplitudes[name]
        wraps = phase_wraps(phase)
        boundaries[name] = wraps
        row = {
            'phase_max_error': float(np.max(abs(phase - expected_phase))),
            'amplitude_scale_max_error': float(np.max(abs(amplitude - expected_scales[:, 1]))),
            'same_boundaries': bool(np.array_equal(expected_wraps, wraps)),
            'cycle_count': len(wraps), 'first_boundaries': wraps[:8].tolist(),
        }
        traces.update({f'{name}_f0_hz': f0, f'{name}_phase': phase, f'{name}_amplitude': amplitude})
        if name in cycles:
            traces[f'{name}_period'] = cycles[name][:, 0]
            row['period_scale_max_error'] = float(np.max(abs(cycles[name][:, 0] - expected_scales[:, 0])))
        comparisons[name] = row
    tolerance = case['limits']['cycle_absolute']
    checks['independent_cycle_state_matches'] = all(row['same_boundaries'] and all(
        value <= tolerance for key, value in row.items() if key.endswith('_max_error')) for row in comparisons.values())
    np.savez_compressed(out / 'cycle-traces.npz', **traces)
    differences = {}
    for engine, (inactive, active) in pairs.items():
        a, b = (signals[name] for name in (inactive, active))
        fields = {key: first_difference(b[0][key] - a[0][key]) for key in FIELDS}
        peak = np.abs(b[0]['phase'] - a[0]['phase'])
        one, two = boundaries[inactive], boundaries[active]
        count = min(len(one), len(two))
        a_amp, b_amp = amplitudes[inactive][one[:count]], amplitudes[active][two[:count]]
        boundary_shifts = two[:count] - one[:count]
        differences[engine] = {'first_different_internal_sample': fields,
                               'first_different_pcm_frame': first_difference(b[2] - a[2]),
                               'first_boundary': int(one[0]) if count else None,
                               'max_boundary_shift_samples': int(np.max(abs(boundary_shifts))) if count else None,
                               'max_circular_phase_error': float(np.max(np.minimum(peak, 1 - peak))),
                               'matched_cycle_amplitude': count > 0 and bool(np.array_equal(a_amp, b_amp))}
    return checks, comparisons, differences


def measure(case, base, cfg, original, references, out, execute):
    signals, upstream_checks, _, cycles = drift.capture(
        base, original, references['upstream.wav'], out, execute, cycle_patch=PATCH)
    candidate_signals, candidate_amplitudes, candidate_checks, candidate_plan = candidate_capture(
        base, original, references['candidate.wav'], references['inspect.json'], out, execute,
        adjustment=('candidate_jitter', 'period_jitter', case['cycle']['jitter_active']))
    signals.update(candidate_signals)
    amplitudes = {name: values[:, 1] for name, values in cycles.items()}
    amplitudes.update(candidate_amplitudes)
    checks, result = drift.analyze(base, cfg, signals, references['stage-windows.npz'], out, execute)
    checks['radiation_and_output_stages_agree'] = checks.pop('both_radiation_and_output_stages_agree')
    cycle_checks, independent, pairs = compare_cycles(case, base, signals, cycles, amplitudes, out)
    checks.update(cycle_checks)
    prior = tsp.read(references['drift-summary.json'])
    with np.load(references['drift-windows.npz'], allow_pickle=False) as before, np.load(out / 'drift-windows.npz', allow_pickle=False) as after:
        same_drift = all(upstream_checks[name] == prior['pcm_verification'][name]
            and all(np.array_equal(before[f'{name}_{field}'], after[f'{name}_{field}']) for field in (*FIELDS, 'lpc_pcm'))
            for name in drift.UPSTREAM_CONDITIONS)
    checks.update(
        upstream_cli_plans_and_baseline_match=same_drift and all(upstream_checks[key] for key in
            ('default_matches_ordinary_pcm', 'ordinary_matches_archived_wav', 'same_plan')),
        candidate_cli_plans_and_archive_match=candidate_plan and candidate_checks['candidate']['default_wav_matches_archive']
            and all(row['pcm_matches_candidate_cli'] for row in candidate_checks.values()))
    with np.load(out / 'drift-spectra.npz', allow_pickle=False) as data:
        spectral = {engine: compare_spectra(base['spectra'], data['frequency_hz'], *(data[name] for name in pair))
                    for engine, pair in PAIRS.items()}
    poles = result['lpc_high_poles_hz']
    shifts = {engine: poles[active][0] - poles[inactive][0] for engine, (inactive, active) in PAIRS.items()
              if poles[active] is not None and poles[inactive] is not None}
    baseline_gap = adjusted_gap = None
    if all(poles.values()):
        baseline_gap = poles['candidate'][0] - poles['drift_zero'][0]
        adjusted_gap = poles['candidate'][0] - poles['jitter_zero'][0]
    predictions = {
        'jitter_changes_phase_after_first_wrap': all(row['matched_cycle_amplitude'] and row['first_boundary'] is not None
            and row['first_different_internal_sample']['phase'] == row['first_boundary'] + 1
            and row['first_different_internal_sample']['f0_hz'] is None for row in pairs.values()),
        'upstream_lpc_moves_at_least_two_hz': abs(shifts.get('upstream', 0)) >= case['limits']['meaningful_lpc_shift_hz'],
        'within_engine_lpc_shifts_agree_in_sign': shifts.get('upstream', 0) * shifts.get('candidate', 0) > 0,
    }
    return {'checks': checks, 'predictions': predictions, **result, 'cycle_models': independent, 'within_engine': pairs,
            'pcm_verification': {**upstream_checks, **candidate_checks}, 'glottal_jitter_effect': spectral,
            'lpc_shift_zero_to_active_hz': shifts, 'candidate_minus_upstream_drift_zero_hz': baseline_gap,
            'candidate_minus_upstream_also_jitter_zero_hz': adjusted_gap}


def reference_inputs(case, revision):
    pressure_run = tsp.open_run(case['reference'], revision)
    pressure_case, pressure_path = saved_case(pressure_run, PRESSURE_CASE)
    drift_run = tsp.open_run(pressure_case['reference'], revision)
    drift_case, drift_path = saved_case(drift_run, drift.CASE)
    base, cfg, original, upper_wav, default_window, paths = drift.reference_inputs(drift_case['reference'], revision)
    render = original.parents[2]
    render_run = render, tsp.read(render / 'manifest.json')
    references = {name: tsp.verified_path(render_run, str(original.with_name(name).relative_to(render)))
                  for name in ('candidate.wav', 'inspect.json')}
    references.update({'upstream.wav': upper_wav, 'stage-windows.npz': default_window,
                       'drift-windows.npz': tsp.verified_path(drift_run, 'artifacts/drift-windows.npz'),
                       'drift-summary.json': tsp.verified_path(drift_run, 'summary.json')})
    paths = [Path(__file__).resolve(), PATCH, LOCAL, pressure_path, drift_path,
              pressure_run[0] / 'manifest.json', drift_run[0] / 'manifest.json',
              *references.values(), *paths, *candidate_sources()]
    return base, cfg, original, references, paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    base, cfg, original, references, paths = reference_inputs(case, revision)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, [CASE, *paths], details,
        lambda out, execute: measure(case, base, cfg, original, references, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
