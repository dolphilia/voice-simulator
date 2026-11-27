"""短音の実時間歌唱と並列観測のPCMを、オフライン基準に照合する。"""

import argparse
import gzip
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_song_cross_browser as cross
import measure_worklet_song as song
from upstream_baseline import sha256


CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-teeth-lowpass-floor.json'
READ = song.wasm.read_json
COLUMNS = ['context_frame', 'quantum_frames', 'frames_rendered', 'process_ms', 'callback_elapsed_ms']


def schedule(report, spec):
    live = report['realtime']
    quantum, frames = spec['quantum'], spec['frames']
    count = (frames + quantum - 1) // quantum
    blocks = np.asarray(live['blocks'], dtype=float)
    if live['columns'] != COLUMNS or blocks.shape != (count, len(COLUMNS)) or not np.isfinite(blocks).all():
        raise ValueError('実時間量子の観測の列または点数が一致しません')
    start = live['scheduledContextFrame']
    first = live['startupFirstContextFrame']
    consecutive_start = live['startupContiguousFirstContextFrame']
    minimum_lead = spec['startup_contiguous_callbacks'] * quantum + spec['lead_frames']
    expected_start = consecutive_start + minimum_lead
    origin = np.arange(count) * quantum
    duration, elapsed = blocks[:, 3], blocks[:, 4]
    budget = 1000 * quantum / spec['sample_rate_hz']
    checks = {
        'independent_start': (start == report['firstContextFrame'] == expected_start
                              == live['armedContextFrame'] + spec['lead_frames'] and start % quantum == 0
                              and live['startupCallbacks'] >= spec['startup_contiguous_callbacks']
                              and consecutive_start >= first
                              and (consecutive_start == first) == (live['startupDiscontinuities'] == 0)
                              and live['leadCallbacks'] == spec['lead_frames'] // quantum),
        'all_quantum_frames_and_padding': (report['callbacks'] == count and report['framesRendered'] == frames
                                           and report['shortestQuantum'] == report['longestQuantum'] == quantum
                                           and report['discontinuities'] == 0
                                           and bool(np.all(blocks[:, 1] == quantum))
                                           and np.array_equal(blocks[:, 0], start + origin)
                                           and np.array_equal(blocks[:, 2], np.minimum(origin + quantum, frames))),
        'timing_samples_valid': bool(elapsed[0] == 0 and np.all(np.diff(elapsed) >= 0) and np.all(duration >= 0)),
        'running_context_and_stable_wasm': (live['contextState'] == 'running' and report['stableWasmBuffers']
                                             and report['wasmMemoryGrowths'] == 0
                                             and live['firstWasmMemoryGrowthFrame'] is None),
    }
    return checks, {'startup_frame': first, 'contiguous_startup_frame': consecutive_start,
                    'startup_discontinuities': live['startupDiscontinuities'], 'start_frame': start,
                    'lead_from_startup_frames': start - first, 'lead_from_contiguous_start_frames': start - consecutive_start,
                    'first_quantum_to_start_as_predicted': start == first + minimum_lead,
                    'independent_start_frame': expected_start, 'last_quantum_frame': int(blocks[-1, 0]),
                    'valid_frames_in_last_quantum': frames - int(origin[-1]),
                    'padded_frames': count * quantum - frames, 'timing_clock': live['timingClock'],
                    'base_latency_seconds': live['baseLatencySeconds'], 'budget_ms': budget,
                    'timing': song.realtime.timing_summary(duration, budget),
                    'timing_after_32_quanta': song.realtime.timing_summary(duration[32:], budget),
                    'maximum_callback_spacing_ms': float(np.diff(elapsed).max())}


def compare_output_probe(folder, clock, expected, spec):
    trace = READ(folder / 'output-probe.json')
    frames = np.asarray(trace['frames'])
    observed = np.fromfile(folder / 'output-probe.f32le', dtype='<f4')
    quantum = spec['quantum']
    count = spec['output_probe_quanta']
    if frames.shape != (count,) or observed.shape != (count * quantum,) or not np.isfinite(observed).all():
        raise ValueError('並列観測の量子数またはPCMの形式が一致しません')
    steps = np.diff(frames)
    if not np.all(np.isfinite(frames)) or np.any(frames % quantum) or np.any(steps <= 0):
        raise ValueError('並列観測の絶対フレームが昇順の量子境界に揃いません')
    first_song = int(np.searchsorted(frames, clock['start_frame']))
    if first_song == count or frames[first_song] != clock['start_frame']:
        raise ValueError('並列観測に予定した歌唱の先頭量子がありません')
    start = first_song * quantum
    end = start + len(expected)
    padded_end = end + clock['padded_frames']
    if padded_end > len(observed):
        raise ValueError('並列観測に予定した歌唱の区間が含まれていません')
    pre = spec['minimum_before_song_quanta']
    post = spec['minimum_after_padding_quanta']
    expected_count = (padded_end - start) // quantum
    required_frames = clock['start_frame'] + np.arange(-pre, expected_count + post) * quantum
    actual_frames = frames[max(first_song - pre, 0):first_song + expected_count + post]
    startup = frames[(frames >= clock['startup_frame']) & (frames < clock['start_frame'])]
    endings = np.flatnonzero(np.diff(startup) != quantum) + 1
    ready = next((part[spec['startup_contiguous_callbacks']] for part in np.split(startup, endings)
                  if len(part) > spec['startup_contiguous_callbacks']), None)
    before, padding, after = observed[:start], observed[end:padded_end], observed[padded_end:]
    difference = song.wasm.compare_pcm(observed[start:end], expected, 0)
    checks = {'probe_rate_and_clock': (trace['sampleRate'] == spec['sample_rate_hz']
                                      and np.array_equal(actual_frames, required_frames)),
              'probe_independent_startup': bool(len(startup) and startup[0] == clock['startup_frame']
                                                and ready == clock['start_frame'] - spec['lead_frames']),
              'probe_pcm_at_scheduled_position': difference['first_bit_difference_frame'] is None,
              'probe_silence_before_and_after': (len(before) >= quantum * spec['minimum_before_song_quanta']
                                                and len(after) >= quantum * spec['minimum_after_padding_quanta']
                                                and not any(np.any(x) for x in (before, padding, after)))}
    return checks, {'capture_start_frame': int(frames[0]), 'capture_end_frame': int(frames[-1] + quantum),
                    'gaps': [{'after_frame': int(frames[i]), 'missing_frames': int(steps[i] - quantum)}
                             for i in np.flatnonzero(steps != quantum)],
                    'before_song_frames': len(before), 'final_padding_frames': len(padding),
                    'after_padding_frames': len(after), 'song_pcm_against_offline': difference}


def compare(trial, report, rate, pcm, folder, offline, fixed, upper_pcm, dictionary_hashes, binary_hash, spec,
            *, engine='chromium'):
    baseline = READ(offline['browser.json'])
    offline_rate, expected = wavfile.read(offline['browser.wav'])
    if (any(x.shape != (spec['frames'],) or x.dtype != np.float32 or not np.isfinite(x).all()
            for x in (pcm, expected, upper_pcm))):
        raise ValueError('PCMの型・フレーム数・有限性が一致しません')
    pcm_result = song.wasm.compare_pcm(pcm, expected, 0)
    states = [song.read_observations(r, fixed['measurement'], spec['frames'], live=live)
              for r, live in ((report, True), (baseline, False))]
    exported = READ(folder / 'browser-case.json')
    compressed = trial['dictionaryResponseIsGzip']
    checks, clock = schedule(report, spec)
    checks.update({
        f'{engine}_input_and_assets': (trial['engine'] == engine and not trial['errors'] and trial['recovered']
                                      and trial['servedWasmSha256'] == binary_hash
                                      and trial['dictionaryResponseSha256'] == dictionary_hashes[compressed]),
        'pcm_format_and_rate': (rate == offline_rate == report['sampleRate'] == report['workletSampleRate']
                                == spec['sample_rate_hz'] and report['outputChannels'] == 1
                                and report['outputFrames'] == spec['frames']),
        'all_pcm_matches_offline': pcm_result['first_bit_difference_frame'] is None,
        'all_sampled_states_and_plan_match_offline': np.array_equal(*states)
        and all(report[key] == baseline[key] for key in ('input', 'song', 'gestures', 'body')),
        'exported_case_matches_offline': exported == READ(offline['browser-case.json']),
    })
    absolute_beats = [clock['start_frame'] + round(n['beat_seconds'] * rate) for n in report['song']['plan']['notes']]
    input_score = exported['song_voice']['score']
    computed_beats = input_score['start_seconds'] + np.cumsum(
        [0.0, *(note['beats'] for note in input_score['notes'][:-1])]) * (60 / input_score['bpm'])
    checks['absolute_beats'] = absolute_beats == (np.rint(computed_beats * rate).astype(int) + clock['start_frame']).tolist()
    result = {'browser': trial, 'clock': clock, 'absolute_beat_frames': absolute_beats,
              'offline_pcm': pcm_result, 'fixed_upstream_pcm': song.wasm.compare_pcm(pcm, upper_pcm, spec['change_floor']),
              'observations': len(states[0]), 'exported_turbulence': exported['song_voice']['turbulence']}
    return checks, result, expected


def measure(study, fixed, case_path, live, references, upper, wasm, artifacts, execute, bun):
    spec = study['measurement']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    copied = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, copied)
    binary_hash = sha256(copied)
    dictionary_hashes = {True: sha256(song.DICTIONARY),
                         False: song.bytes_digest(gzip.decompress(song.DICTIONARY.read_bytes())).hexdigest()}
    upper_pcm = np.fromfile(upper, dtype='<f4')
    checks = {'wasm_matches_offline': binary_hash == sha256(wasm),
              'dictionary_matches_upstream': dictionary_hashes[True] == sha256(song.UPSTREAM_DICTIONARY)}
    trials, audio = {}, {}
    for mode, order in study['order'].items():
        audio[mode] = {}
        for condition in order:
            label = f'{mode}-{condition}'
            options = {'single_song_capture': True, 'skip_invalid_lyrics': True}
            if mode == 'observed':
                options['output_probe'] = {'quantum': spec['quantum'], 'captureQuanta': spec['output_probe_quanta']}
            folder = artifacts / label
            try:
                offline = references[condition]
                browser, report, rate, pcm = cross.capture(folder, 'chromium', live, offline['input.json'], '...',
                                                            execute, options=options, case_path=case_path)
                local, result, expected = compare(browser, report, rate, pcm, folder, offline, fixed,
                                                  upper_pcm, dictionary_hashes, binary_hash, spec)
                if mode == 'observed':
                    probe_checks, result['output_probe'] = compare_output_probe(folder, result['clock'], expected, spec)
                    local.update(probe_checks)
                trials[label] = result
                audio[mode][condition] = pcm
            except (OSError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                trials[label] = {'error': str(error)}
                local = {'capture_and_comparison_completed': False}
            checks.update({f'{label}/{key}': passed for key, passed in local.items()})

    predictions = {f'{label}/first_quantum_to_start_exactly': result['clock']['first_quantum_to_start_as_predicted']
                   for label, result in trials.items() if 'clock' in result}
    effects = {}
    for mode, pair in audio.items():
        if set(pair) != set(study['cutoffs_hz']):
            predictions[f'{mode}/first_pcm_differences'] = False
            continue
        result = song.wasm.compare_pcm(pair['floor1200'], pair['floor0'], spec['change_floor'])
        effects[mode] = result
        predictions[f'{mode}/first_pcm_differences'] = (
            result['first_bit_difference_frame'] == spec['expected_first_bit_difference']
            and result['first_frame_over_tolerance'] == spec['expected_first_difference_over_floor'])
    return {'checks': checks, 'predictions': predictions, 'trials': trials, 'floor1200_against_floor0': effects}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = READ(CASE)
    offline_study_path = CASE.parent / study['offline_study']
    offline_study = READ(offline_study_path)
    fixed_path = CASE.parent / offline_study['capture_case']
    live_path = CASE.parent / study['live_case']
    source = CASE.parent / offline_study['source_case']
    fixed, live, base = (READ(path) for path in (fixed_path, live_path, source))
    revision = study['upstream_revision']
    spec = study['measurement']
    limits = fixed['measurement']
    if (any(obj['upstream_revision'] != revision for obj in (offline_study, fixed, live, base))
            or not (spec['sample_rate_hz'] == limits['output_rate_hz'] and spec['frames'] == limits['output_frames']
                    and spec['quantum'] == limits['expected_render_quantum_frames'])
            or any(live['measurement'][key] != spec[key] for key in ('lead_frames', 'startup_contiguous_callbacks'))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流、歌唱入力、量子または開始の条件が一致しません')
    offline = song.run_manifest(study['offline_run'], offline_study['id'], revision)
    pinned = song.run_manifest(offline_study['reference_run'], 'song-voice-fast-constriction-source', revision)
    previous = song.run_manifest(study['previous_run'], study['id'], revision)
    previous_summary = song.verified_path(previous, 'summary.json')
    if offline[1]['status'] != 'pass' or pinned[1]['status'] != 'pass':
        parser.error('オフラインと固定上流の基準が揃いません')
    reference_paths = {}
    for label, hz in study['cutoffs_hz'].items():
        files = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
            'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
        turbulence = {**study['turbulence'], 'teeth_lowpass_floor_hz': hz}
        if READ(files['input.json']) != {**base, 'song_voice': {**base['song_voice'], 'turbulence': turbulence}}:
            parser.error('保存済み入力の乱流条件または短音スコアが一致しません')
        reference_paths[label] = files
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    upper = song.verified_path(pinned, 'artifacts/upstream-pcm.f32')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_offline': offline[0].name,
                'measurement_revision': study['measurement_revision'], 'previous_run': previous[0].name,
                'turbulence_seed': offline_study['noise_seed'], 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv],
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs = [CASE, offline_study_path, fixed_path, live_path, source, Path(__file__).resolve(), wasm, upper,
              offline[0] / 'manifest.json', pinned[0] / 'manifest.json', previous[0] / 'manifest.json', previous_summary,
              *(path for group in reference_paths.values() for path in group.values()),
              *song.web_sources(), *song.shared.candidate_sources(),
              *(Path(module.__file__) for module in (cross, song, song.shared, song.realtime, song.wasm))]
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, fixed_path, live, reference_paths, upper, wasm,
                                           artifacts, execute, bun), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
