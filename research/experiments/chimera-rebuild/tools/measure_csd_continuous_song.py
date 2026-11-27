"""CSDの2句を一つの発声器で描画し、句間に残る状態とPCMを測る。"""

import argparse
import math
import os
from pathlib import Path
import subprocess
import wave

import numpy as np
from scipy.io import wavfile

import measure_speech_timing as timing
import measure_uniform_tube as shared
from measure_song_plan import segments
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-continuous-song.json'
SOURCE = WORKSPACE / 'cases/csd-song-planning.json'
PROBE = WORKSPACE / 'tools/upstream_csd_continuous_probe.rs'
CLI = WORKSPACE / 'target/release/vocal-cli'


def samples(path, rate, count):
    fs, pcm = wavfile.read(path)
    if fs != rate or pcm.shape != (count,) or pcm.dtype != np.float32 or not np.isfinite(pcm).all():
        raise ValueError(f'描画したPCMの形式、長さまたは値が不正です ({path.name})')
    return pcm


def state(path, fields, count):
    with path.open() as stream:
        names = stream.readline().strip().split(',')
        rows = np.loadtxt(stream, delimiter=',', usecols=[names.index(x) for x in fields],
                          dtype=[(x, 'f8') for x in fields])
    if not np.array_equal(rows['frame'], np.arange(count)) or any(not np.isfinite(rows[x]).all() for x in fields):
        raise ValueError(f'状態のフレーム番号または値が不正です ({path.name})')
    return rows


def breaths(gestures):
    return [g for g in gestures if 'breath' in g['targets']]


def independent_gate(gestures, fields, fs, stride):
    dt = stride / fs
    clock = np.arange(0, len(fields), stride) / fs
    weight, target = np.zeros_like(clock), np.zeros_like(clock)
    for g in gestures:
        rise = np.clip((clock - (g['t0'] - g['rampIn'])) / g['rampIn'], 0, 1)
        fall = np.clip(((g['t1'] + g['rampOut']) - clock) / g['rampOut'], 0, 1)
        w = np.sin(.5 * np.pi * np.minimum(rise, fall)) ** 2 * g['strength']
        weight += w
        target += w * g['targets']['breath']
    goal = target / np.maximum(1, weight)
    values = []
    gate = hold = 0.0
    for level, w in zip(goal, weight, strict=True):
        hold = .15 if w > 0 else max(0, hold - dt)
        tau = .025 if level > gate else .02 if hold > 0 else .07
        retain = math.exp(-dt / tau)
        gate = retain * gate + (1 - retain) * level
        values.append(gate)
    prediction = np.repeat(values, stride)[:len(fields)]
    return float(np.max(np.abs(fields['gate'] - prediction)))


def delta(left, right, *, tolerance):
    difference = np.abs(left.astype(float) - right)
    nonzero = np.flatnonzero(left != right)
    above = np.flatnonzero(difference > tolerance)
    return {'first_different_frame': int(nonzero[0]) if nonzero.size else None,
            'first_above_tolerance_frame': int(above[0]) if above.size else None,
            'maximum_absolute_difference': float(difference.max())}


def pcm_bits_equal(a, b):
    return np.array_equal(a.view('u4'), b.view('u4'))


def record_variant(candidate_case, name, output, blocks, execute):
    case = output / f'{name}.json'
    timing.write(case, candidate_case)
    wave_path = output / f'{name}.wav'
    trace_path = output / f'{name}.csv'
    execute([str(CLI), 'render-pcm', str(case), str(wave_path), str(trace_path), str(blocks)])
    return wave_path, trace_path, case


def measurement(case, source, recording, voice_base, out, execute):
    limits = case['measurement']
    fs, short, full = (limits[k] for k in ('output_rate_hz', 'short_frames', 'output_frames'))
    block, other_block = limits['host_blocks']
    plans = {row['id']: row for row in timing.read(source / 'song-inputs.json')['song_plan']['scores']}
    observed_inputs = [plans[key] for key in case['phrases']]
    base = timing.read(voice_base)['song_voice']
    settings = {key: value for key, value in base.items() if key != 'score'}
    settings.update(body=case['body'], vibrato_cents=case['vibrato_cents'],
                    voice={**base['voice'], 'output_gain': case['output_gain']})
    short_case = {'song_voice': {**settings, 'scores': observed_inputs, 'render_end_seconds': short / fs}}
    full_case = {'song_voice': {**settings, 'scores': observed_inputs, 'render_end_seconds': full / fs}}
    second_case = {'song_voice': {**settings, 'score': observed_inputs[1], 'render_end_seconds': short / fs}}

    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    short_path, short_csv, native_input = record_variant(short_case, 'candidate-short-128', out, block, execute)
    alt_path, alt_csv, _ = record_variant(short_case, 'candidate-short-77', out, other_block, execute)
    full_path, _, _ = record_variant(full_case, 'candidate-full', out, block, execute)
    second_path, _, _ = record_variant(second_case, 'candidate-second', out, block, execute)
    native_settings = out / 'candidate-inspect.json'
    native_state = out / 'candidate-state.csv'
    execute([str(CLI), 'inspect', str(native_input)], stdout=native_settings)
    execute([str(CLI), 'render', str(native_input), str(native_state)])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine',
             '--test', 'sing_fast', '--test', 'sung_release'], cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    reference, reference_pcm = {}, {}
    names = case['retain_csv']['candidate-state.csv']['columns']
    trace = {'candidate': state(native_state, names, short)}
    for mode in ('standard', 'matched'):
        pcm_path, trace_path, plan_path = (out / f'{mode}.{ext}' for ext in ('f32', 'csv', 'json'))
        execute([str(probe), str(native_input), mode, str(pcm_path), str(trace_path), str(plan_path)])
        reference[mode] = timing.read(plan_path)
        reference_pcm[mode] = np.fromfile(pcm_path, dtype='<f4')
        if reference_pcm[mode].shape != (short,) or not np.isfinite(reference_pcm[mode]).all():
            raise ValueError('上流のPCMが同じ長さの有限値になっていません')
        trace[mode] = state(trace_path, names, short)

    normal = samples(short_path, fs, short)
    full_pcm = samples(full_path, fs, full)
    second = samples(second_path, fs, short)
    ordinary_upper = samples(source / 'csd' / f"{case['song']}-synth.wav", fs, full)
    with wave.open(str(recording), 'rb') as audio:
        rate, frames = audio.getframerate(), audio.getnframes()
    output_frames, remainder = divmod(frames * fs, rate)
    output_frames += int(2 * remainder >= rate)

    inspect = timing.read(native_settings)
    stride = inspect['control_block_internal_samples'] // inspect['decimation_factor']
    song = inspect['song']['scores']
    beats = [n for row in song for n in row['plan']['notes']]
    observed_beats = [[n['beat_seconds'], n['f0_hz']] for n in beats]
    expected_beats = [[a, 440 * math.exp2((midi - 69) / 12)] for a, midi in
                      zip(limits['beat_seconds'], limits['beat_midi'], strict=True)]
    beat_difference, _ = timing.compare(observed_beats, expected_beats, limits['control_tolerance'])
    gate = {key: breaths(inspect['gestures'] if key == 'candidate' else
                         [g for p in reference[key]['plans'] for g in p['gestures']]) for key in trace}
    gate_error = {key: independent_gate(gate[key], dataset, fs, stride) for key, dataset in trace.items()}
    native_segments = [segments(row['plan']) for row in song]
    upper_segments = [p['segments'] for p in reference['standard']['plans']]
    segment_difference, _ = timing.compare(native_segments, upper_segments, limits['control_tolerance'])
    breath_difference, _ = timing.compare(gate['candidate'], gate['standard'], limits['control_tolerance'])

    tol = limits['same_settings_pcm_tolerance']
    pcms = {mode: delta(normal, ref, tolerance=tol) for mode, ref in reference_pcm.items()}
    state_differences = {mode: {key: delta(trace['candidate'][key], ref[key], tolerance=limits['control_tolerance'])
                                for key in names if key != 'frame'}
                         for mode, ref in trace.items() if mode != 'candidate'}
    gap = slice(*(round(t * fs) for t in limits['interphrase_window_seconds']))
    history = slice(*(round(t * fs) for t in limits['history_observation_seconds']))
    gap_rms, isolated_rms = (float(np.sqrt(np.mean(x[gap].astype(float) ** 2))) for x in (normal, second))
    affected = np.flatnonzero(normal[history].view('u4') != second[history].view('u4'))
    prefix = limits['reference_prefix_frames']
    return {
        'checks': {
            'recording_clock_and_length': (frames, rate) == (limits['recording_frames'], limits['recording_rate_hz'])
                                          and output_frames == full and len(full_pcm) == output_frames,
            'same_short_prefix_of_full_render': pcm_bits_equal(normal, full_pcm[:short]),
            'host_blocks': sha256(short_path) == sha256(alt_path) and sha256(short_csv) == sha256(alt_csv),
            'upstream_standard_probe_matches_full_song_prefix': pcm_bits_equal(reference_pcm['standard'][:prefix],
                                                                             ordinary_upper[:prefix]),
            'same_plan_and_breath_reservations': beat_difference is None and segment_difference is None
                                                  and breath_difference is None and len(gate['candidate']) == 2
                                                  and all(row['dropped'] == 0 for row in reference.values()),
            'independent_gate': max(gate_error.values()) <= limits['control_tolerance'],
            'residual_of_first_phrase_in_gap': gap_rms - isolated_rms >= limits['minimum_gap_rms_delta_pcm'],
            'first_phrase_affects_second': bool(np.any(affected + history.start >= round(limits['beat_seconds'][1] * fs))),
            'same_voice_settings_pcm': pcms['matched']['maximum_absolute_difference'] <= tol,
        },
        'output_frames': full,
        'short_frames': short,
        'source_prefix_frames': prefix,
        'beats_with_f0_hz': observed_beats,
        'breath_gestures': gate,
        'first_beat_difference': beat_difference,
        'first_segment_difference': segment_difference,
        'first_breath_difference': breath_difference,
        'maximum_gate_error': gate_error,
        'pcm_comparison': pcms,
        'state_comparison': state_differences,
        'history_control': {'gap_frames': [gap.start, gap.stop], 'gap_rms_with_first_phrase': gap_rms,
                            'gap_rms_with_only_second': isolated_rms, 'bit_difference_frames': int(affected.size),
                            'maximum_difference_during_observation': float(abs(normal[history] - second[history]).max())},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    case = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    run = WORKSPACE / 'runs' / case['source_run']
    source = run / 'artifacts'
    manifest = timing.read(run / 'manifest.json')
    hashes = {row['path']: row['sha256'] for row in manifest['outputs']}
    dataset_name = f"CSD/english/wav/{case['song']}.wav"
    recording = Path(timing.read(SOURCE)['dataset']['work_root']) / dataset_name
    recorded = manifest['dataset']['files'][dataset_name]
    if sha256(recording) != recorded['sha256']:
        parser.error('録音が固定済みの版と一致しません')
    originals = [source / 'song-inputs.json', source / 'csd' / f"{case['song']}-synth.wav"]
    if any(sha256(path) != hashes.get(path.relative_to(run).as_posix()) for path in originals):
        parser.error('保存した音符または全曲のPCMが先行実行と一致しません')
    base = WORKSPACE / 'cases' / case['voice_base_case']
    inputs = [CASE, SOURCE, PROBE, base, Path(__file__).resolve(), Path(shared.__file__),
              WORKSPACE / 'tools/measure_song_plan.py', WORKSPACE / 'tools/measure_speech_timing.py',
              run / 'manifest.json', *originals, *shared.candidate_sources()]
    return shared.record_measurement(args.run_id, CASE, inputs,
        {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
         'recording': {'path': str(recording), **recorded}},
        lambda out, execute: measurement(case, source, recording, base, out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
