"""CLIのPCMを固定上流、独立したFIR・出力計算、ブロック分割に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import firwin, freqz, lfilter

import measure_junction as reference
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


PROBE = WORKSPACE / 'tools/upstream_pcm_probe.rs'
NATIVE_TEST = ('engine', 'output_does_not_depend_on_the_host_block_size')
SIGNAL = 'radiation_flow_derivative_cm3_s2'
OUTPUT_COLUMNS = ['frame', 'internal_sample', 'decimated', 'dc_removed',
                  'limiter_envelope', 'hold_frames', 'pcm_f32']


def read_columns(path, count, columns=None):
    if columns is None:
        with path.open() as stream:
            columns = len(stream.readline().split(','))
    header, data = shared.read_trace(path, count, columns)
    return header, dict(zip(header, data.T, strict=True))


def independent_limiter(dc_removed, rate):
    release = np.exp(-1 / (rate * 0.2))
    hold_length = int(np.floor(rate * 0.025 + 0.5))
    envelope = np.empty_like(dc_removed)
    held = np.empty(dc_removed.size, dtype=int)
    value = 0.0
    deadline = 0
    for frame, peak in enumerate(np.abs(dc_removed)):
        if peak >= value:
            value = peak
            deadline = frame + hold_length
        elif frame > deadline:
            value *= release
        envelope[frame] = value
        held[frame] = max(0, deadline - frame)
    bounded = dc_removed.copy()
    limiting = envelope > 0.75
    bounded[limiting] *= 0.75 / envelope[limiting]
    magnitude = np.abs(bounded)
    clipping = magnitude > 0.85
    bounded[clipping] = np.sign(bounded[clipping]) * (0.85 + 0.15 * np.tanh((magnitude[clipping] - 0.85) / 0.15))
    return envelope, held, bounded.astype(np.float32)


def render_blocks(case_path, cfg, artifacts, execute):
    """各回で同一のケースを最初から、異なるサイズのホストブロックでレンダーする。"""
    outputs = {}
    for block in cfg['block_frames']:
        wav = artifacts / f'block-{block}.wav'
        trace = artifacts / f'block-{block}.csv'
        execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
                 str(case_path), str(wav), str(trace), str(block)])
        outputs[block] = wav, trace
    return outputs


def upper_output(executable, label, raw, factor, rate, gain, artifacts, execute):
    source = artifacts / f'{label}-radiation.txt'
    target = artifacts / f'{label}-pcm.csv'
    np.savetxt(source, raw, fmt='%.17g')
    execute([str(executable), str(factor), str(rate), str(gain), str(source)], cwd=UPSTREAM, stdout=target)
    return target


def measure(case, case_path, artifacts, execute):
    cfg, settings = (case[key] for key in ('measurement', 'pcm'))
    fs = case['network']['sample_rate_hz']
    rate, gain = settings['sample_rate_hz'], settings['gain']
    count = cfg['sample_count']
    factor, frames = fs // rate, count // (fs // rate)
    metadata = json.loads((artifacts / 'settings.json').read_text())['pcm']
    taps = np.asarray(metadata['filter_coefficients'])
    h = np.ones(1) if factor == 1 else firwin(factor * 24 + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    if len(taps) != len(h) or metadata['frames'] != frames or metadata['decimation_factor'] != factor:
        raise ValueError('PCMのフレーム数またはフィルタの長さが一致しません')
    coefficients_error = float(np.max(np.abs(taps - h)))
    lo, hi = cfg['passband_hz']
    band = np.linspace(lo, hi, 1025)
    _, response = freqz(taps, worN=band, fs=fs)
    passband_error = float(np.max(np.abs(np.abs(response) - 1)))
    _, alias = freqz(taps, worN=[cfg['alias_probe_hz']], fs=fs)
    alias_gain = float(np.abs(alias[0]))

    block_files = render_blocks(case_path, cfg, artifacts, execute)
    base_wave, base_csv = block_files[cfg['block_frames'][0]]
    waveform_hash, trace_hash = sha256(base_wave), sha256(base_csv)
    block_checks = {str(block): {'pcm_identical': sha256(wav) == waveform_hash,
                                 'trace_identical': sha256(trace) == trace_hash}
                    for block, (wav, trace) in block_files.items()}
    header, cand = read_columns(base_csv, frames, len(OUTPUT_COLUMNS))
    if header != OUTPUT_COLUMNS:
        raise ValueError('候補のPCM観測列が一致しません')
    sample_rate, wave = wavfile.read(base_wave)
    if sample_rate != rate or wave.shape != (frames,) or wave.dtype != np.dtype('<f4'):
        raise ValueError('WAVが指定したレート・長さのモノラルf32ではありません')
    recorded = cand['pcm_f32'].astype(np.float32)

    raw_header, source = read_columns(artifacts / 'trace.csv', count)
    upper_graph_path = reference.capture_upstream(case, artifacts, execute, NATIVE_TEST)
    upstream_raw_header, upper_source = read_columns(upper_graph_path, count, len(raw_header))
    if raw_header != upstream_raw_header:
        raise ValueError('上流と候補の内部系列の観測列が一致しません')
    internal_error = shared.compare_series(source[SIGNAL], upper_source[SIGNAL],
                                           cfg['upstream_internal_peak_relative_error_lt'])
    program = shared.build_upstream_probe(PROBE, artifacts, execute)
    control_path = upper_output(program, 'common-input-upstream', source[SIGNAL], factor, rate, gain, artifacts, execute)
    full_path = upper_output(program, 'end-to-end-upstream', upper_source[SIGNAL], factor, rate, gain, artifacts, execute)
    for path in (control_path, full_path):
        if read_columns(path, frames, len(OUTPUT_COLUMNS))[0] != OUTPUT_COLUMNS:
            raise ValueError('上流と候補のPCM観測列が一致しません')
    _, control = read_columns(control_path, frames, len(OUTPUT_COLUMNS))
    _, upper = read_columns(full_path, frames, len(OUTPUT_COLUMNS))
    stage_tolerance = cfg['upstream_output_peak_relative_error_lt']
    upper_stage = {name: shared.compare_series(cand[name], control[name], stage_tolerance)
                   for name in OUTPUT_COLUMNS[2:]}
    upper_final = shared.compare_series(recorded, upper['pcm_f32'].astype(np.float32), stage_tolerance)

    decimated = lfilter(h, [1.0], source[SIGNAL])[factor - 1::factor]
    dc_pole = np.exp(-2 * np.pi * 25 / rate)
    highpassed = lfilter([1, -1], [1, -dc_pole], gain * decimated)
    envelope, held, limited = independent_limiter(cand['dc_removed'], rate)
    tolerance = cfg['output_state_peak_relative_error_lt']
    comparisons = {
        'fir_convolution': shared.compare_series(cand['decimated'], decimated, cfg['convolution_peak_relative_error_lt']),
        'highpass': shared.compare_series(cand['dc_removed'], highpassed, tolerance),
        'envelope': shared.compare_series(cand['limiter_envelope'], envelope, tolerance),
        'hold': shared.compare_series(cand['hold_frames'], held, tolerance),
        'pcm': shared.compare_series(recorded, limited, tolerance),
    }
    pcm_peak = float(np.max(np.abs(wave)))
    limited_count = int(np.count_nonzero(cand['limiter_envelope'] > 0.75))
    release_count = int(np.count_nonzero(np.diff(cand['limiter_envelope']) < 0))
    return {
        'checks': {
            'independent_coefficients': coefficients_error < cfg['coefficients_absolute_error_lt'],
            'filter_passband': passband_error < cfg['passband_gain_diff_lt'],
            'alias_attenuation': alias_gain < cfg['alias_gain_lt'],
            'decimator_phase': bool(np.array_equal(cand['internal_sample'], np.arange(factor - 1, count, factor))),
            'independent_output_states': all(item['status'] for item in comparisons.values()),
            'upstream_internal': internal_error['status'],
            'upstream_on_common_input': all(item['status'] for item in upper_stage.values()),
            'upstream_end_to_end_pcm': upper_final['status'],
            'host_block_continuity': all(all(item.values()) for item in block_checks.values()),
            'wave_matches_f32_trace': bool(np.isfinite(wave).all() and np.array_equal(wave.view(np.uint32), recorded.view(np.uint32))),
            'triggered_limiter_and_release': (limited_count > 0 and release_count > 0)
            if cfg['expect_limiter'] else limited_count == 0,
            'bounded_nonzero_pcm': 0 < pcm_peak < cfg['pcm_peak_limit'],
        },
        'frames': frames, 'sample_rate_hz': rate, 'fir_taps': len(taps),
        'group_delay_internal_samples': (len(taps) - 1) / 2,
        'coefficients_max_absolute_error': coefficients_error,
        'passband_max_gain_deviation': passband_error, 'alias_gain': alias_gain,
        'alias_probe_hz': cfg['alias_probe_hz'], 'pcm_peak': pcm_peak,
        'limited_frames': limited_count, 'limiter_release_frames': release_count,
        'blocks': block_checks, 'independent': comparisons,
        'upstream_internal_error': internal_error, 'upstream_output_states': upper_stage,
        'upstream_end_to_end_pcm_error': upper_final,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=['pcm-impulse', 'pcm-voiced'])
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始め、英数字、ハイフン、アンダースコアで指定してください')
    case_path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(case_path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        raise ValueError('変更のない固定上流版が必要です')

    def measure_run(artifacts, execute):
        return measure(case, case_path, artifacts, execute)

    inputs = [case_path, PROBE, reference.PROBE, Path(__file__).resolve(), Path(reference.__file__),
              Path(shared.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, case_path, inputs, details, measure_run)


if __name__ == '__main__':
    raise SystemExit(main())
