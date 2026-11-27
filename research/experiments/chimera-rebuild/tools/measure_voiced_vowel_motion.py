"""可動声道の有声レンダーを上流のPCM、内部系列、独立した出力処理に照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import firwin, lfilter, resample_poly

from measure_articulation import PROBE, write_upstream_events
import measure_pcm_output as pcm
import measure_uniform_tube as shared
from measure_vowel_voice import cycle_f0, independent_lpc, independent_yin
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASES = tuple(f'vowel-motion-voice-{name}' for name in ('vowels', 'nasal', 'unvoiced'))
GEOMETRY = ('jaw_cm', 'tongue_tip_y_cm', 'pharynx_dx_cm', 'oral_dx_cm',
            'oral_area_cm2', 'oral_minimum_cm2', 'velum_area_cm2')
VOICE = ('gate', 'lung_boundary_dyn_cm2', 'pressure_sub_dyn_cm2', 'pressure_supra_dyn_cm2',
         'glottal_area_cm2', 'glottal_flow_cm3_s', 'glottal_phase', 'glottal_voicing', 'glottal_f0_hz',
         'velum_flow_cm3_s', 'lip_flow_cm3_s', 'nose_flow_cm3_s', 'radiation_derivative_cm3_s2')
COLUMNS = ('internal_sample', 'control_frame', *GEOMETRY, *VOICE)
ARTICULATION = ('tongue_body_x_cm', 'tongue_body_y_cm', 'lip_aperture_cm', 'lip_minimum_cm2')


def load_track(path, indices, control_period):
    with path.open() as stream:
        header = tuple(stream.readline().strip().split(','))
        data = np.loadtxt(stream, delimiter=',', ndmin=2)
    if (header not in (COLUMNS, (*COLUMNS, *ARTICULATION)) or data.shape != (len(indices), len(header))
            or not np.isfinite(data).all() or not np.array_equal(data[:, 0], indices)
            or not np.array_equal(data[:, 1], indices // control_period)):
        raise ValueError(f'{path.name} のサンプル時刻または観測値が不正です')
    return dict(zip(header, data.T, strict=True))


def capture_upstream(case, cfg, artifacts, execute):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine',
             'output_does_not_depend_on_the_host_block_size', '--', '--nocapture'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-engine.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute)
    event_path = artifacts / 'upstream-events.txt'
    write_upstream_events(case, event_path)
    settings = case['voice']
    rate, pressure, gate, f0, breathiness, tension, gain = (
        settings[key] for key in ('output_sample_rate_hz', 'pressure_cm_h2o', 'gate', 'f0_hz',
                                  'breathiness', 'tension', 'output_gain'))
    prefix = [str(probe), str(event_path), 'voice', *map(str, (rate, pressure, gate, f0, breathiness, tension, gain))]
    primary = artifacts / 'upstream-voice.f32'
    alternate = artifacts / 'upstream-host-voice.f32'
    execute([*prefix, '1', str(primary), str(artifacts / 'upstream-trace.csv')], cwd=UPSTREAM)
    execute([*prefix, str(cfg['host_block_sizes'][-1]), str(alternate), '-'], cwd=UPSTREAM)
    reference = np.fromfile(primary, dtype='<f4')
    wavfile.write(artifacts / 'upstream-voice.wav', rate, reference)
    return reference, sha256(primary) == sha256(alternate)


def compare(a, b, limit):
    error = abs(a.astype(float) - b)
    bad = np.flatnonzero(error >= limit)
    return {
        'max_absolute_difference': float(error.max()),
        'first_sample_over_tolerance': int(bad[0]) if bad.size else None,
        'status': not bool(bad.size),
    }


def first_exact_difference(candidate, upstream, columns, selected):
    candidates = []
    for column in columns:
        difference = candidate[column][selected] - upstream[column]
        hit = np.flatnonzero(difference)
        if hit.size:
            candidates.append((int(hit[0]), column, float(difference[hit[0]])))
    if not candidates:
        return None
    index, column, difference = min(candidates)
    return {'internal_sample': int(upstream['internal_sample'][index]), 'column': column,
            'candidate_minus_upstream': difference}


def independently_render(track, out_trace, output, rate, factor, gain, metadata, cfg):
    signal = track['radiation_derivative_cm3_s2']
    h = np.ones(1) if factor == 1 else firwin(factor * 24 + 1, 2 * .46 / factor, window=('kaiser', 8.5))
    filters = compare(np.asarray(metadata['filter_coefficients']), h, 1e-12)
    decimated = lfilter(h, [1], signal)[factor - 1::factor]
    pole = np.exp(-2 * np.pi * 25 / rate)
    dc = lfilter([gain, -gain], [1, -pole], decimated)
    envelope, held, limited = pcm.independent_limiter(dc, rate)
    cfg_tol = cfg['output_state_peak_relative_error_lt']
    return {
        'fir_coefficients': filters,
        'decimated': shared.compare_series(out_trace['decimated'], decimated, cfg_tol),
        'dc_removed': shared.compare_series(out_trace['dc_removed'], dc, cfg_tol),
        'limiter_envelope': shared.compare_series(out_trace['limiter_envelope'], envelope, cfg_tol),
        'hold_frames': compare(out_trace['hold_frames'], held, 1.0),
        'pcm': compare(output, limited, cfg['pcm_absolute_lt']),
    }


def within(value, interval):
    return value is not None and interval[0] <= value <= interval[1]


def spectral_window(output, reference, phase, rate, cfg, window):
    start, count = window['start_frame'], window['frame_count']
    if start < 0 or count < 2 or start + count > len(output):
        raise ValueError('有効な周波数計測窓を指定してください')
    selected = slice(start, start + count)
    results = []
    for signal in (output[selected], reference[selected]):
        wave = signal.astype(float)
        f0, aperiodicity = independent_yin(wave, rate, cfg)
        lpc_rate = cfg['lpc_sample_rate_hz']
        formants = independent_lpc(resample_poly(wave, lpc_rate, rate), cfg)
        formants = formants[formants[:, 0] < lpc_rate / 2 - cfg['lpc_nyquist_guard_hz']]
        results.append({'f0_hz': f0, 'aperiodicity': aperiodicity,
                        'lpc_frequency_bandwidth_hz': formants.tolist(), 'rms': float(np.sqrt(np.mean(wave**2)))})
    candidate, upstream = results
    natural = cycle_f0(phase[selected], rate)
    observed = candidate['lpc_frequency_bandwidth_hz'][:3]
    checks = {
        'pcm_f0': within(candidate['f0_hz'], window['pcm_f0_interval_hz']),
        'phase_f0': within(natural, window['phase_f0_interval_hz']),
        'first_3_lpc': len(observed) == 3 and all(within(row[0], interval) for row, interval in zip(
            observed, window['first_3_lpc_hz'], strict=True)),
        'rms': within(candidate['rms'], window['rms_interval']),
    }
    return {'ipa': window['ipa'], 'start_frame': start, 'frame_count': count,
            'candidate': candidate, 'upstream_wave_analysis': upstream, 'phase_f0_hz': natural, 'checks': checks}


def measure(case, path, artifacts, execute):
    voice, cfg = case['voice'], case['measurement']['voice_motion']
    rate = voice['output_sample_rate_hz']
    internal_rate = case['articulators']['sample_rate_hz']
    period = case['articulators']['control_block_samples']
    factor = internal_rate // rate
    frames = cfg['output_frames']
    count = factor * frames
    if (internal_rate != factor * rate or period != 64 * factor or case['measurement']['frames'] * period != count
            or not case['area_control']['project_contacts']):
        raise ValueError('固定上流の発声比較は出力64サンプルごとの制御と接触補正にそろえてください')
    metadata = json.loads((artifacts / 'settings.json').read_text())['voice']
    tracks = load_track(artifacts / 'trace.csv', np.arange(count), period)
    selected = slice(factor - 1, None, factor)
    reference, upper_host_ok = capture_upstream(case, cfg, artifacts, execute)
    upper_tracks = load_track(artifacts / 'upstream-trace.csv', np.arange(count)[selected], period)
    blocks = pcm.render_blocks(path, {'block_frames': cfg['host_block_sizes']}, artifacts, execute)
    wave_path, trace_path = next(iter(blocks.values()))
    observed_rate, wave = wavfile.read(wave_path)
    if (observed_rate != rate or wave.dtype != np.float32 or wave.shape != (frames,) or reference.shape != wave.shape
            or not np.isfinite(wave).all() or not np.isfinite(reference).all()):
        raise ValueError('同じレート・フレーム数の有限なモノラルf32 PCMを指定してください')
    headers, out_trace = pcm.read_columns(trace_path, frames, len(pcm.OUTPUT_COLUMNS))
    if headers != pcm.OUTPUT_COLUMNS:
        raise ValueError('PCM出力段の観測列が不正です')
    geometry = {col: compare(tracks[col][selected], upper_tracks[col], cfg['geometry_absolute_lt']) for col in GEOMETRY}
    audio = {col: shared.compare_series(tracks[col][selected], upper_tracks[col], cfg['component_peak_relative_error_lt'])
             for col in VOICE}
    first_difference = min(((v['first_sample_over_tolerance'], col) for col, v in (geometry | audio).items()
                            if v['first_sample_over_tolerance'] is not None), default=None)
    pcm_error = compare(wave, reference, cfg['pcm_absolute_lt'])
    differing_bits = np.flatnonzero(wave.view(np.uint32) != reference.view(np.uint32))
    stages = {
        'geometry': GEOMETRY, 'breath': VOICE[:2], 'glottal_and_pressures': VOICE[2:9],
        'branch_and_radiation': VOICE[9:],
    }
    exact = {stage: first_exact_difference(tracks, upper_tracks, columns, selected)
             for stage, columns in stages.items()}
    independent = independently_render(tracks, out_trace, wave, rate, factor, voice['output_gain'], metadata, cfg)
    onset = np.flatnonzero(abs(wave) > cfg['onset_amplitude_threshold'])
    onset_frame = int(onset[0]) if len(onset) else None
    peak = float(abs(wave).max())
    nose_flow = float(abs(tracks['nose_flow_cm3_s'][selected]).max())
    voicing = float(tracks['glottal_voicing'].max())
    velum_area = tracks['velum_area_cm2'][selected]
    opened = np.flatnonzero(velum_area >= .0002)
    velum_bounds = cfg['velum_open_frame_bounds']
    if velum_bounds is None:
        velum_ok = not len(opened)
    else:
        a, b, c, d = velum_bounds
        velum_ok = bool(len(opened) and a <= opened[0] <= b and c <= opened[-1] <= d
                        and len(opened) == opened[-1] - opened[0] + 1)
    windows = [spectral_window(wave, reference, tracks['glottal_phase'][selected], rate, cfg['spectral_analysis'], w)
               for w in cfg['windows']]
    checks = {
        'registered_clock': (metadata['frames'] == frames and metadata['decimation_factor'] == factor
                             and metadata['control_block_internal_samples'] == period
                             and np.array_equal(out_trace['internal_sample'], np.arange(count)[selected])),
        'upstream_geometry': all(result['status'] for result in geometry.values()),
        'upstream_audio_state': all(result['status'] for result in audio.values()),
        'upstream_pcm': pcm_error['status'],
        'wave_matches_pcm_trace': np.array_equal(wave.view(np.uint32), out_trace['pcm_f32'].astype(np.float32).view(np.uint32)),
        'candidate_host_partition_invariance': all(sha256(wav) == sha256(wave_path) and sha256(csv) == sha256(trace_path)
                                                   for wav, csv in blocks.values()),
        'upstream_host_partition_invariance': upper_host_ok,
        'independent_fir_dc_limiter': all(item['status'] for item in independent.values()),
        'registered_onset': within(onset_frame, cfg['onset_frame_interval']),
        'registered_pcm_peak': within(peak, cfg['pcm_peak_interval']),
        'registered_nose_flow': within(nose_flow, cfg['nose_flow_peak_cm3_s']),
        'registered_velum_open_frames': velum_ok,
        'closed_velum_flow_zero': np.all(tracks['velum_flow_cm3_s'][tracks['velum_area_cm2'] < .0002] == 0),
        'registered_voicing_peak': within(voicing, cfg['voicing_peak']),
    }
    if 'silent_until_frame' in cfg:
        checks['zero_gate_preroll_and_no_voicing'] = (not np.any(wave[:cfg['silent_until_frame']])
                                                      and not np.any(tracks['gate']) and not np.any(tracks['glottal_voicing']))
    for window in windows:
        checks.update({f"{window['ipa']}_{key}": value for key, value in window['checks'].items()})
    return {
        'checks': {key: bool(value) for key, value in checks.items()},
        'frames': frames, 'internal_samples': count, 'onset_output_frame': onset_frame,
        'pcm_peak': peak, 'pcm_to_upstream': pcm_error,
        'differing_pcm_samples': int(len(differing_bits)),
        'first_pcm_bit_difference': (None if not len(differing_bits) else {
            'output_frame': int(differing_bits[0]), 'candidate': float(wave[differing_bits[0]]),
            'upstream': float(reference[differing_bits[0]]),
        }),
        'first_exact_internal_difference_by_stage': exact,
        'first_internal_sample_over_tolerance': (
            None if first_difference is None else {'sample': (first_difference[0] + 1) * factor - 1, 'column': first_difference[1]}),
        'geometry': geometry, 'audio_states': audio, 'independent_output': independent,
        'peak_nose_flow_cm3_s': nose_flow, 'peak_glottal_voicing': voicing,
        'peak_glottal_flow_cm3_s': float(abs(tracks['glottal_flow_cm3_s']).max()),
        'peak_lung_boundary_pressure_dyn_cm2': float(abs(tracks['lung_boundary_dyn_cm2']).max()),
        'velum_open_output_frames': [int(opened[0]), int(opened[-1])] if len(opened) else None,
        'windows': windows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('case', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    path = WORKSPACE / 'cases' / f'{args.case}.json'
    case = json.loads(path.read_text())
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise ValueError('変更のない固定上流版が必要です')
    sources = [path, PROBE, Path(__file__).resolve(), Path(shared.__file__), Path(pcm.__file__),
               *(WORKSPACE / f'tools/{name}.py' for name in ('measure_articulation', 'measure_vowel_voice',
                                                            'measure_junction', 'upstream_baseline')),
               *shared.candidate_sources()]
    details = {'upstream_revision': revision, 'case_id': case['id'], 'scipy_version': scipy.__version__}
    return shared.record_measurement(args.run_id, path, sources, details,
                                     lambda artifacts, execute: measure(case, path, artifacts, execute))


if __name__ == '__main__':
    raise SystemExit(main())
