"""短音の歌唱で歯の低域通過周波数の下限だけを変えて比較する。"""

import argparse
from itertools import islice
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter

import measure_fan_crossing_allocations as archive
import measure_song_constriction_source as constriction
import measure_song_glottis_source as glottis
import measure_song_voice as song
import measure_turbulence as noise
from upstream_baseline import sha256


WORKSPACE = song.WORKSPACE
CASE = WORKSPACE / 'cases/song-voice-fast-teeth-lowpass-floor.json'
SOURCES = (*constriction.SOURCES, 'teeth')
REPLAY = ('settings.json', 'voicing.csv', 'pcm-128.wav', 'pcm-128.csv')
TRACES = ('voicing.csv', 'upstream-voicing.csv', 'pcm-128.wav', 'upstream-pcm.f32')


def spectral_filter_pressure(trace, window, rate, factor, seed):
    start, end = window
    sources = np.column_stack([trace[f'{name}_noise_source'] for name in SOURCES])
    forwards = np.column_stack([trace[f'{name}_noise_forward'] for name in SOURCES])
    current = slice(start, end)
    forward = trace['teeth_noise_forward'][current]
    cutoff = trace['teeth_noise_lowpass_hz'][current]
    reverse = trace['teeth_noise_reverse'][current]
    unchanged = np.all(sources[current] == sources[start]) and np.all(forwards[current] == forwards[start])
    reused = np.any((sources[start - 1] == sources[start, -1]) & (forwards[start - 1] == forward[0]))
    if (not unchanged or reused or np.any(sources[current] == -1) or np.any(cutoff != cutoff[0])
            or np.any(forward == reverse)):
        raise ValueError('フィルタ照合区間には枝が切り替わった後の一定帯域・3乱流源が必要です')
    skip = int(np.count_nonzero(sources[:start] != -1)) * factor
    count = (end - start) * factor * len(SOURCES)
    draws = np.fromiter(islice(noise.mulberry32(seed, skip + count), skip, None), dtype=float, count=count)
    white = (2 * draws.reshape(-1, len(SOURCES))[:, -1] - 1) * 1.732
    high_pole = np.exp(-2 * np.pi * 1200 / rate)
    low_pole = np.exp(-2 * np.pi * cutoff[0] / rate)
    band = lfilter([high_pole, -high_pole], [1, -high_pole], white)
    for _ in range(2):
        band = lfilter([1 - low_pole], [1, -low_pole], band)
    expected = trace['teeth_noise_level'][current] * band[factor-1::factor]
    observed = trace['teeth_noise_forward_pressure'][current] - trace['teeth_noise_reverse_pressure'][current]
    return {'cutoff_hz': float(cutoff[0]), 'internal_samples': len(white), 'prior_random_draws': skip,
            'first_expected_injection_frame': (start + int(i)) if (i := glottis.first(expected != 0)) is not None else None,
            'maximum_pressure_error_dyn_cm2': float(np.max(np.abs(observed - expected)))}


def observe(study, trace, reference, pcm, zero_pcm):
    effect = glottis.differences(reference, trace, zero_pcm, pcm, study['pcm_difference_floor'])
    first = glottis.first(trace['teeth_noise_level'] > 0)
    pressure = [effect['trace'][f'teeth_noise_{direction}_pressure'] for direction in ('forward', 'reverse')]
    injection = min((frame for frame in pressure if frame is not None), default=None)
    return {'first_activity_frame': first, 'first_pressure_frame': injection,
            'activity_to_pressure_frames': None if first is None or injection is None else injection - first,
            'against_zero': effect}


def windows(study, changed, baseline, zero, closed):
    rows = {}
    for name, (start, end) in study['windows'].items():
        delta = changed[start:end].astype(float) - baseline[start:end]
        against_zero = changed[start:end] - zero[start:end]
        mask = closed[start:end]
        rows[name] = {'frames': [start, end], 'pcm_difference_peak': float(np.max(np.abs(delta))),
                      'pcm_difference_rms': float(np.sqrt(np.mean(delta**2))), 'oral_closed_frames': int(mask.sum()),
                      'nonzero_pcm_differences_against_zero_when_closed': int(np.count_nonzero(against_zero[mask]))}
    return rows


def measure(study, base, saved, baseline_files, zero_files, artifacts, execute):
    blocks = base['measurement']['host_block_frames']
    replay = artifacts / 'reference-replay'
    replay.mkdir()
    song.voice.capture_candidate(saved, blocks[:1], replay, execute)
    replay_hashes = {name: sha256(replay / name) for name in REPLAY}
    replay_match = all(value == sha256(baseline_files[name]) for name, value in replay_hashes.items())
    if replay_match:
        shutil.rmtree(replay)

    config = {**base, 'song_voice': {**base['song_voice'], 'turbulence': study['turbulence']}}
    path = artifacts / 'case.json'
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    settings, trace_path, files = song.voice.capture_candidate(path, blocks, artifacts, execute)
    count = base['measurement']['expected_frames']
    trace, native, upstream, zero, zero_upstream = [song.voice.load_trace(p, count) for p in (
        trace_path, baseline_files['voicing.csv'], baseline_files['upstream-voicing.csv'],
        zero_files['voicing.csv'], zero_files['upstream-voicing.csv'])]
    sample_rate = base['song_voice']['voice']['output_sample_rate_hz']
    rate, pcm = wavfile.read(files[0][0])
    native_pcm, zero_pcm = (wavfile.read(d['pcm-128.wav'])[1] for d in (baseline_files, zero_files))
    upstream_pcm, zero_upstream_pcm = (np.fromfile(d['upstream-pcm.f32'], dtype='<f4') for d in (baseline_files, zero_files))
    if any(p.shape != (count,) or p.dtype != np.float32 or not np.isfinite(p).all()
           for p in (pcm, native_pcm, zero_pcm, upstream_pcm, zero_upstream_pcm)):
        raise ValueError('PCMのフレーム数・形式・有限性が一致しません')

    band = song.speech.independent_band(trace, study['teeth_band_absolute_tolerance_hz'],
                                       lowpass_floor_hz=study['turbulence']['teeth_lowpass_floor_hz'])
    internal = base['song_voice']['internal_sample_rate_hz']
    opening = study['windows']['first_opening']
    filter_checks = {key: spectral_filter_pressure(row, opening, internal, internal // rate, study['noise_seed'])
                     for key, row in (('with_floor', trace), ('reference', native), ('upstream', upstream))}
    closed = trace['oral_minimum_cm2'] <= base['measurement']['closed_area_cm2']
    window_results = windows(study, pcm, native_pcm, zero_pcm, closed)
    effect = observe(study, trace, zero, pcm, zero_pcm)
    reference = observe(study, native, zero, native_pcm, zero_pcm)
    prior_settings = song.timing.read(baseline_files['settings.json'])
    delta_upper_pcm = np.abs(pcm.astype(float) - upstream_pcm)
    predictions = {
        'activity_onset_unchanged': effect['first_activity_frame'] is not None
        and effect['first_activity_frame'] == reference['first_activity_frame'],
        'shorter_injection_delay': effect['activity_to_pressure_frames'] is not None
        and reference['activity_to_pressure_frames'] is not None
        and 0 <= effect['activity_to_pressure_frames'] < reference['activity_to_pressure_frames'],
        'first_radiation_and_pcm_earlier': all(new is not None and prior is not None and new < prior for new, prior in (
            (effect['against_zero']['trace']['radiation_derivative_cm3_s2'],
             reference['against_zero']['trace']['radiation_derivative_cm3_s2']),
            (effect['against_zero']['pcm_first_bit_difference_frame'], reference['against_zero']['pcm_first_bit_difference_frame']))),
        'no_pcm_difference_in_closure': window_results['before_reopening']['oral_closed_frames'] > 0
        and window_results['before_reopening']['nonzero_pcm_differences_against_zero_when_closed'] == 0,
    }
    return {
        'checks': {
            'reference_replay_byte_identical': replay_match,
            'frame_count_and_rate': settings['output_frames'] == count and rate == sample_rate,
            'host_partitions_byte_identical': all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1])
                                                  for w, c in files[1:]),
            'same_plan_and_control_targets': all(settings[field] == prior_settings[field] for field in ('song', 'gestures'))
            and all(np.array_equal(native[field], trace[field]) for field in constriction.CONTROLS),
            'source_slots_preserved': all(np.array_equal(native[f'{name}_noise_{field}'], trace[f'{name}_noise_{field}'])
                                          for name in SOURCES for field in ('source', 'forward', 'reverse')),
            'other_two_sources_remain_muted': all(constriction.without_sources(trace, native, name)
                                                 for name in constriction.SOURCES),
            'independent_teeth_band_and_gain': band['passed'] and band['gain_max_error'] <= study['teeth_gain_absolute_tolerance'],
            'independent_filter_pressure': all(row['maximum_pressure_error_dyn_cm2'] <= study['filter_pressure_tolerance_dyn_cm2']
                                               for row in filter_checks.values()),
        },
        'predictions': predictions, 'reference_replay_sha256': replay_hashes,
        'reference': reference, 'upstream': observe(study, upstream, zero_upstream, upstream_pcm, zero_upstream_pcm),
        'with_floor': effect, 'with_floor_against_reference': glottis.differences(
            native, trace, native_pcm, pcm, study['pcm_difference_floor']),
        'first_modified_teeth_cutoff_frame': glottis.first(trace['teeth_noise_lowpass_hz'] != native['teeth_noise_lowpass_hz']),
        'first_modified_teeth_level_frame': glottis.first(trace['teeth_noise_level'] != native['teeth_noise_level']),
        'with_floor_against_fixed_upstream_pcm': {'maximum_absolute_difference': float(delta_upper_pcm.max()),
            'first_frame_above_floor': glottis.first(delta_upper_pcm > study['pcm_difference_floor'])},
        'independent_teeth_band': band, 'filter_pressure': filter_checks, 'windows': window_results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = song.timing.read(CASE)
    source = CASE.parent / study['source_case']
    base = song.timing.read(source)
    revision = study['upstream_revision']
    if (base['upstream_revision'] != revision or
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('変更のない固定上流と短音の比較ケースが必要です')
    reference = archive.run_manifest(study['reference_run'], constriction.CASE.stem, revision)
    zero = archive.run_manifest(study['zero_reference_run'], 'worklet-song-voice-fast', revision)
    saved = archive.verified_path(reference, 'artifacts/case.json')
    reference_case = song.timing.read(saved)
    turbulence = dict(study['turbulence'])
    del turbulence['teeth_lowpass_floor_hz']
    if (reference[1]['status'] != 'pass' or zero[1]['status'] != 'pass' or zero[1]['turbulence_scale'] != 0 or
            reference_case != {**base, 'song_voice': {**base['song_voice'], 'turbulence': turbulence}} or
            not any(p['path'].endswith('/' + source.name) and p['sha256'] == sha256(source) for p in zero[1]['inputs'])):
        parser.error('保存済みの声門・狭窄を抑えた条件が、下限だけを変える対照と一致しません')
    baseline_files = {name: archive.verified_path(reference, 'artifacts/' + name) for name in dict.fromkeys((*REPLAY, *TRACES))}
    zero_files = {name: archive.verified_path(zero, 'artifacts/' + name) for name in TRACES}
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'turbulence_seed': study['noise_seed'],
                'reference_run': reference[0].name, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv]}
    modules = (archive, constriction, glottis, noise, song, song.voice, song.speech, song.shared, song.timing)
    inputs = [CASE, source, saved, Path(__file__).resolve(), reference[0] / 'manifest.json', zero[0] / 'manifest.json',
              *baseline_files.values(), *zero_files.values(), *(Path(module.__file__) for module in modules),
              *song.shared.candidate_sources()]
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, base, saved, baseline_files, zero_files, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
