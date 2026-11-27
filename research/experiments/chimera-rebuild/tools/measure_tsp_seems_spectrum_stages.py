"""同じ発話窓で声門からPCMまでの高域スペクトルを照合する。"""

import argparse
import gzip
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_duet_child_output_gain as output_stage
import measure_tsp_f2_bandwidth_envelope as envelope
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import FIELDS, LOCAL, OUTPUT_PATCH, PROBE, SOURCE_PATCH
import measure_tsp_lpc_order_recordings as recording_order
import measure_tsp_stressed_vowel_formants as tsp
from measure_tsp_coat_to import DICT
from measure_tsp_seems_tract_transfer import CASE as TRANSFER_CASE
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-seems-spectrum-stages.json'
VOICES = ('upstream', 'candidate')
FLOW_STAGES = ('glottal_flow_cm3_s', 'lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s', 'total_cm3_s',
               'radiation_derivative_cm3_s2')
OUTPUT_STAGES = ('decimated', 'dc_removed', 'pcm', 'common_output_replay')


def capture(case, original, wave_paths, out, execute):
    frames = case['trace_frames']
    factor = case['internal_sample_rate_hz'] // case['sample_rate_hz']
    text = tsp.read(original)['speech_voice']['input']['text']
    stages, signals = {}, {}
    with TemporaryDirectory(prefix='seems-spectrum-', dir=out) as directory:
        tmp = Path(directory)
        fixed = tmp / 'upstream'
        fixed.mkdir()
        tar = tmp / 'fixed.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(fixed)])
        for patch in (OUTPUT_PATCH, SOURCE_PATCH):
            execute(['git', 'apply', str(patch)], cwd=fixed)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        candidate = build_upstream_probe(LOCAL, tmp, execute, upstream=WORKSPACE, package='vocal-core', lto='off',
                                         extra_libraries=('serde_json',), cargo_args=('--offline',))
        upstream = build_upstream_probe(PROBE, tmp, execute, upstream=fixed, extra_libraries=('serde_json',),
                                        rustc_args=('--cfg', 'tsp_voice_probe'), cargo_args=('--offline',))
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'golden_analysis'],
                cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'], stdout=out / 'candidate-tests.log')
        execute([str(UPSTREAM / 'target/release/chimera'), 'render', 'text', str(tmp / 'upstream.wav'), text, 'male', '--float'],
                cwd=UPSTREAM)
        execute([str(WORKSPACE / 'target/release/vocal-cli'), 'render-pcm', str(original), str(tmp / 'candidate.wav'),
                 '--no-trace', '128'])
        for voice in VOICES:
            state = tmp / f'{voice}-state.f64'
            pcm = tmp / f'{voice}.f32'
            output = tmp / f'{voice}-output.f64'
            if voice == 'upstream':
                execute([str(upstream), str(original), str(dictionary), str(state), str(pcm), str(tmp / 'plan.json'),
                         str(frames), 'default', str(output)])
            else:
                execute([str(candidate), str(original), str(dictionary), str(frames), str(case['initial_f0_hz']),
                         str(case['base_f0_hz']), str(state), str(pcm), str(output)])
            rate, ordinary = wavfile.read(tmp / f'{voice}.wav')
            observed = np.fromfile(pcm, dtype='<f4')
            raw = np.fromfile(state, dtype='<f8').reshape(-1, len(FIELDS))
            if raw.shape[0] != frames * factor or not np.isfinite(raw).all() or len(observed) < frames:
                raise ValueError(f'観測系列の長さまたは有限性が登録内容と一致しません ({voice})')
            stages[voice] = {
                'ordinary_matches_archive': rate == case['sample_rate_hz'] and sha256(tmp / f'{voice}.wav') == sha256(wave_paths[voice]),
                'probe_pcm_matches_ordinary': ordinary.dtype == np.float32 and np.isfinite(observed).all()
                    and np.array_equal(ordinary.view('u4'), observed.view('u4')),
                'pcm_frames': len(observed),
            }
            signals[voice] = dict(zip(FIELDS, raw.T, strict=True)), output_stage.trace_input(output, frames), observed[:frames]
    return stages, signals


def replay(case, radiation):
    stage = case['stage']
    rate = case['sample_rate_hz']
    factor = case['internal_sample_rate_hz'] // rate
    decimated = output_stage.decimate_radiation(radiation, factor, stage)
    dc = lfilter([1, -1], [1, -math.exp(-math.tau * stage['dc_hz'] / rate)], decimated * case['base_gain'])
    envelope_values, _ = output_stage.envelope_response(dc, rate, stage)
    limit, clip = stage['peak_threshold'], stage['clip_threshold']
    signal = dc * (limit / np.maximum(envelope_values, limit))
    absolute = abs(signal)
    return np.where(absolute > clip, np.sign(signal) * (clip + (1 - clip) * np.tanh((absolute - clip) / (1 - clip))),
                    signal).astype('<f4')


def window_spectra(settings, rate, windows):
    step = settings['grid_step_hz']
    low, high = settings['normalization_band_hz']
    grid = np.arange(low, high + 1, step)
    powers, errors = {}, {}
    for key, x in windows.items():
        windowed = (x - np.mean(x)) * np.hanning(len(x))
        nfft = rate // step
        fft = np.fft.rfft(windowed, nfft)[grid // step]
        direct = np.exp((-2j * np.pi / rate) * grid[:, None] * np.arange(len(x))) @ windowed
        scale = np.max(np.abs(direct))
        powers[key] = np.abs(fft) ** 2
        errors[key] = float(np.max(np.abs(fft - direct)) / scale) if scale else 0.0
    return grid, powers, errors


def compare_spectra(settings, grid, base, candidate):
    band = (grid >= settings['band_hz'][0]) & (grid <= settings['band_hz'][1])
    band_base, band_candidate = base[band], candidate[band]
    if band_base.sum() <= 0 or band_candidate.sum() <= 0:
        return None
    distance = 0.5 * np.sum(abs(band_base / band_base.sum() - band_candidate / band_candidate.sum()))
    power_db = 10 * np.log10((band_candidate.sum() / candidate.sum()) / (band_base.sum() / base.sum()))
    return {'total_variation_high_band': float(distance), 'relative_high_band_power_delta_db': float(power_db)}


def power_spectra(case, windows):
    settings = case['spectra']
    powers, errors = {}, {}
    for names, rate in ((FLOW_STAGES, case['internal_sample_rate_hz']), (OUTPUT_STAGES, case['sample_rate_hz'])):
        group = {f'{voice}_{name}': windows[f'{voice}_{name}'] for voice in VOICES for name in names}
        grid, group_powers, group_errors = window_spectra(settings, rate, group)
        powers.update(group_powers)
        errors.update(group_errors)
    metrics = {}
    for stage in (*FLOW_STAGES, *OUTPUT_STAGES):
        base, candidate = (powers[f'{voice}_{stage}'] for voice in VOICES)
        metrics[stage] = compare_spectra(settings, grid, base, candidate)
    return grid, powers, errors, metrics


def high_lpc_poles(case, cfg, frames, out, execute):
    order = cfg['order']['M']
    probes = envelope.fixed_spectra(list(frames.values()), np.empty(0), out, execute, orders=[order] * len(frames))
    results, errors = {}, []
    low, high = case['spectra']['band_hz']
    for (key, frame), probe in zip(frames.items(), probes, strict=True):
        estimated, negative = tsp.independent_poles(frame, case['sample_rate_hz'] / cfg['decimation'], order, cfg)
        _, error, _ = tsp.compare_poles({'poles': estimated, 'negative_real_roots': negative}, probe, cfg)
        selected = envelope.select(probe['poles'], cfg)
        eligible = recording_order.eligible_f2(probe['poles'], selected['f1'], cfg)
        results[key] = next((pole for pole in eligible if low <= pole[0] <= high), None)
        errors.append(error)
    return results, errors


def lpc_stages(case, cfg, frames, out, execute):
    results, errors = high_lpc_poles(case, cfg, frames, out, execute)
    differences = {}
    for name in OUTPUT_STAGES:
        upstream, candidate = (results[f'{voice}_{name}'] for voice in VOICES)
        differences[name] = candidate[0] - upstream[0] if upstream is not None and candidate is not None else None
    return results, differences, errors


def measure(case, cfg, original, wave_paths, previous, out, execute):
    pcm_checks, signals = capture(case, original, wave_paths, out, execute)
    factor = case['internal_sample_rate_hz'] // case['sample_rate_hz']
    decimation = cfg['decimation']
    start = case['window_start_12khz']
    end = start + case['window_samples_12khz']
    if (end * decimation >= case['trace_frames']
            or (start + end) * decimation // 2 != previous['completed_frames']):
        raise ValueError('観測範囲が先行の窓と整合しません')
    pcm_slice = slice(start * decimation, end * decimation)
    internal_slice = slice(pcm_slice.start * factor, pcm_slice.stop * factor)
    windows, lpc_frames, output_checks = {}, {}, {}
    for voice, (state, output, pcm) in signals.items():
        radiation = state['radiation_derivative_cm3_s2']
        total = state['total_cm3_s']
        recovered = replay(case, radiation)
        sections = (state['lip_cm3_s'] + state['nose_cm3_s']) + state['wall_cm3_s']
        output_checks[voice] = {
            **output_stage.independent_stages(output, pcm, case['base_gain'], case),
            'same_radiation_series': np.array_equal(radiation, output[:, :2].ravel()),
            'radiation_sum_error_cm3_s': float(np.max(abs(sections - total))),
            'radiation_derivative_error_cm3_s2':
                float(np.max(abs(np.diff(total, prepend=0) * case['internal_sample_rate_hz'] - radiation))),
            'full_replay_peak_pcm_error': float(np.max(np.abs(recovered.astype(float) - pcm))),
        }
        waves = {'decimated': output[:, 2], 'dc_removed': output[:, 4], 'pcm': pcm, 'common_output_replay': recovered}
        windows.update({f'{voice}_{name}': state[name][internal_slice] for name in FLOW_STAGES})
        windows.update({f'{voice}_{name}': samples[pcm_slice] for name, samples in waves.items()})
        for name, samples in waves.items():
            lpc_frames[f'{voice}_{name}'] = tsp.analysis_downsample(samples.astype(float), cfg)[start:end]
    grid, powers, dft_errors, metrics = power_spectra(case, windows)
    np.savez_compressed(out / 'stage-spectra.npz', frequency_hz=grid, **powers)
    np.savez_compressed(out / 'stage-windows.npz', **windows, **{f'lpc_{key}': value for key, value in lpc_frames.items()})
    poles, differences, errors = lpc_stages(case, cfg, lpc_frames, out, execute)
    limits = case['limits']
    lpc_limit = cfg['frequency_bandwidth_agreement_hz']
    available = all(value is not None for value in differences.values())
    checks = {
        'ordinary_cli_and_probe_match_archived_pcm': all(row['ordinary_matches_archive'] and row['probe_pcm_matches_ordinary']
                                                       for row in pcm_checks.values()),
        'independent_radiation_and_output_stage': all(
            row['same_radiation_series'] and row['radiation_sum_error_cm3_s'] <= limits['radiation_sum_cm3_s']
            and row['radiation_derivative_error_cm3_s2'] <= limits['radiation_identity_cm3_s2']
            and all(row[name] <= limits['independent_normalized'] for name in
                    ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
            and row['hold_error_frames'] == 0 and row['pcm_matches_independent_limiter']
            and row['full_replay_peak_pcm_error'] <= limits['full_output_replay_absolute'] for row in output_checks.values()),
        'spectra_match_direct_dft': all(error <= limits['relative_dft_agreement'] for error in dft_errors.values()),
        'lpc_matches_independent_and_archived_pcm': available
            and all(error is not None and error <= lpc_limit for error in errors)
            and all(abs(poles[f'{voice}_pcm'][0] - previous['pcm_poles_hz'][voice]) <= lpc_limit for voice in VOICES)
            and all(abs(poles[f'{voice}_common_output_replay'][0] - poles[f'{voice}_pcm'][0]) <= lpc_limit for voice in VOICES),
    }
    earliest = next((name for name in (*FLOW_STAGES, *OUTPUT_STAGES) if metrics[name] is not None
                     and metrics[name]['total_variation_high_band'] >= limits['different_high_band_distribution']), None)
    predictions = {
        'high_band_distribution_differs_at_glottis': earliest == 'glottal_flow_cm3_s',
        'pcm_pole_shift_is_already_in_decimated_radiation': available
            and abs(differences['decimated'] - differences['pcm']) <= limits['same_lpc_shift_hz'],
    }
    return {'checks': checks, 'predictions': predictions, 'pcm_frame_interval': [pcm_slice.start, pcm_slice.stop],
            'pcm_verification': pcm_checks, 'output_stage': output_checks, 'max_relative_dft_error': max(dft_errors.values()),
            'spectra': metrics, 'earliest_observed_stage_over_threshold': earliest,
            'lpc_high_poles_hz': poles, 'lpc_high_candidate_minus_upstream_hz': differences}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    transfer = tsp.open_run(case['transfer_reference'], revision)
    prior, prior_path = saved_case(transfer, TRANSFER_CASE)
    render = tsp.open_run(prior['render'], revision)
    source = tsp.open_run(prior['source_comparison'], revision)
    source_case, source_path = saved_case(source, WORKSPACE / 'cases/tsp-f2-source-comparison.json')
    diagnostic = tsp.open_run(source_case['diagnostic'], revision)
    plan, plan_path = saved_case(diagnostic, tsp.CASE)
    uid = prior['target']['utterance']
    original = tsp.verified_path(render, f'artifacts/{uid}/candidate.json')
    waves = {voice: tsp.verified_path(render, f'artifacts/{uid}/{voice}.wav') for voice in VOICES}
    previous = tsp.verified_path(transfer, 'summary.json')
    modules = ('tsp_fine_trace.rs', 'measure_duet_child_output_gain.py', 'measure_duet_child_glottal_noise_origin.py',
               'measure_tsp_stressed_vowel_formants.py', 'measure_tsp_f2_bandwidth_envelope.py',
               'measure_tsp_f2_bandwidth_held_out.py', 'measure_tsp_lpc_order_recordings.py',
               'measure_tsp_fine_variation.py', 'measure_tsp_coat_to.py', 'measure_uniform_tube.py', 'upstream_baseline.py')
    inputs = [CASE, Path(__file__).resolve(), original, *waves.values(), previous, prior_path, source_path, plan_path,
              PROBE, LOCAL, OUTPUT_PATCH, SOURCE_PATCH, DICT, envelope.PROBE,
              *(run[0] / 'manifest.json' for run in (transfer, render, source, diagnostic)),
              *(WORKSPACE / 'tools' / name for name in modules),
              *(UPSTREAM / name for name in ('crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/airway/network.rs',
                    'crates/chimera-cli/src/render.rs', 'crates/chimera/tests/engine.rs', 'crates/chimera/tests/golden_analysis.rs')),
              *candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, plan['measurement'], original, waves, tsp.read(previous), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
