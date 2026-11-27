"""体型別のブラウザ歌唱を、保存したケース・CLI・固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_body_song as body_song
import measure_song_voice as song
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_wasm_fixed as wasm
from measure_worklet_english_body import compare_observations, reference_artifacts
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-song-body.json'
LIVE = WORKSPACE / 'cases/worklet-live-song.json'


def sample_events(observed, native, note_checks, spans, rate, limit, closed_area):
    def frames(trace):
        closed = trace['lip_minimum_cm2'] < closed_area
        first_closed = wasm.first_index(closed)
        first_open = wasm.first_index(~closed & np.r_[False, closed[:-1]])
        if first_closed is None or first_open is None:
            return None
        freqs = note_checks['note_f0_hz']
        midpoints = [math.sqrt(a * b) for a, b in zip(freqs, freqs[1:])]
        crossings = [wasm.first_index(trace['smoothed_f0_hz'] >= midpoint) for midpoint in midpoints]
        if any(cross is None for cross in crossings):
            return None
        return [int(trace['frame'][index]) for index in (first_closed, first_open, *crossings)]

    actual, dense = frames(observed), frames(native)
    if actual is None or dense is None:
        return {'passed': False, 'worklet_frames': actual, 'cli_frames': dense}
    delay = [a - b for a, b in zip(actual, dense, strict=True)]
    heads = [span for span in spans if span['ipa'] in ('s', 'z')]
    seconds = [(frame + 1) / rate for frame in actual[2:]]
    passed = all(0 <= d <= limit for d in delay) and all(
        span['t0'] <= t < span['t1'] for t, span in zip(seconds, heads, strict=True))
    return {'passed': passed, 'worklet_frames': actual, 'cli_frames': dense,
            'worklet_pitch_transition_seconds': seconds, 'delay_frames': delay}


def compare_render(prefix, report, native, upper, waves, rate, limits, *, live):
    fs, pcm = wavfile.read(prefix.with_suffix('.wav'))
    frames = limits['output_frames']
    quantum = limits['expected_render_quantum_frames']
    if any(samples.shape != (frames,) or samples.dtype != np.float32 for samples in (pcm, *waves)):
        raise ValueError('歌唱PCMの長さまたは型が登録条件と一致しません')
    cli_pcm = wasm.compare_pcm(pcm, waves[0], 0)
    upper_pcm = wasm.compare_pcm(pcm, waves[1], limits['upper_pcm_absolute_tolerance'])
    observed, state_checks, state = compare_observations(report, native, upper, limits, frames, live=live)
    flags = {
        'format': fs == rate == report['sampleRate'] == report['workletSampleRate']
            and report['outputChannels'] == 1 and frames == report['outputFrames'] == report['framesRendered'],
        'cli_pcm_bit_equal': cli_pcm['first_bit_difference_frame'] is None,
        'upstream_pcm': upper_pcm['first_frame_over_tolerance'] is None,
        'worklet_clock': report['shortestQuantum'] == report['longestQuantum'] == quantum
            and report['callbacks'] == (frames + quantum - 1) // quantum and report['discontinuities'] == 0,
        **state_checks,
    }
    return flags, {'cli_pcm': cli_pcm, 'upstream_pcm': upper_pcm, **state}, observed


def compare_variant(variant, source, limits, reference, site, tables, wasm_hash, artifacts, execute):
    label = variant['id']
    rate = limits['output_rate_hz']
    frames = limits['output_frames']
    saved = artifacts / f'{label}-offline-case.json'
    live_saved = artifacts / f'{label}-live-case.json'
    report_path = artifacts / f'{label}-cli-plan.json'
    trace_path = artifacts / f'{label}-cli-trace.csv'
    wave_path = artifacts / f'{label}-cli.wav'
    cli_args = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    execute([*cli_args, 'inspect', str(saved)], stdout=report_path)
    execute([*cli_args, 'render', str(saved), str(trace_path)])
    execute([*cli_args, 'render-pcm', str(saved), str(wave_path),
             str(artifacts / f'{label}-cli-pcm.csv'), str(limits['expected_render_quantum_frames'])])
    cli = timing.read(report_path)
    exported = timing.read(saved)
    original = timing.read(reference / 'case.json')['song_voice']
    saved_voice = exported['song_voice']
    reference_plan = timing.read(reference / 'upstream-plan.json')
    native, upper = [speech.load_trace(path, frames) for path in (trace_path, reference / 'upstream-voicing.csv')]
    native_rate, native_pcm = wavfile.read(wave_path)
    waves = native_pcm, np.fromfile(reference / 'upstream-pcm.f32', dtype='<f4')
    spans, plan = song.compare_plans(cli, reference_plan, source['measurement'])
    vowels, tips, bodies = tables
    notes = body_song.independent_notes(cli, source)
    shape = body_song.independent_shape(cli, variant, source['measurement'], vowels, tips)
    scale = math.fsum(w * bodies[name]['scale'] for name, w in zip(body_song.ANCHORS, variant['weights'], strict=True))
    native_events = song.observe(native, native_pcm, spans, rate, source['measurement'])
    controls = song.independent_controls(
        native, cli, {**exported, 'measurement': source['measurement']}, rate, body_scale=scale)
    checks = {
        'saved_case_both_modes': sha256(saved) == sha256(live_saved)
            and site['offline']['replayFilename'] == 'worklet-song-case.json'
            and site['live']['replayFilename'] == 'worklet-live-song-case.json',
        'saved_voice_and_score': exported['upstream_revision'] == source['upstream_revision']
            and all(saved_voice.get(key) == value for key, value in original.items() if key != 'score')
            and all(saved_voice['score'].get(key) == value for key, value in original['score'].items() if key != 'id'),
        'cli_rate_and_count': native_rate == rate and frames == cli['output_frames'] == reference_plan['output_frames']
            and cli['decimation_factor'] * rate == limits['internal_rate_hz'],
        'upstream_and_registered_plan': plan['passed'],
        'independent_beats_midi_targets_and_controls': notes['difference'] is None and shape['difference'] is None
            and controls['passed'],
        'native_vowel_pitch_vibrato_and_release': native_events['passed'],
    }
    result = {'native_events': native_events, 'notes': notes, 'oral_targets': shape,
              'independent_controls': controls, 'upstream_plan': plan}
    for mode in ('offline', 'live'):
        prefix = artifacts / f'{label}-{mode}'
        report = timing.read(prefix.with_suffix('.json'))
        live = mode == 'live'
        flags, output, observed = compare_render(prefix, report, native, upper, waves, rate, limits, live=live)
        plan_diff, plan_error = timing.compare(report['song'], cli['song'], limits['plan_numeric_tolerance'])
        gesture_diff, gesture_error = timing.compare(report['gestures'], cli['gestures'], limits['plan_numeric_tolerance'])
        events = sample_events(observed, native, notes, spans, rate, limits['maximum_sampled_event_delay_frames'],
                               source['measurement']['closed_area_cm2'])
        browser = site[mode]
        flags.update({
            'input_body_assets': (report['body'] == variant['body']
                and all(report['input'].get(k) == source['score'][k] for k in ('syllables', 'notes', 'bpm', 'start_seconds'))
                and report['input']['vibrato_cents'] == source['vibrato_cents']
                and browser['servedWasmSha256'] == wasm_hash and browser['dictionaryRequests'] == 0
                and not browser['errors'] and browser['recovered']),
            'cli_plan_and_gestures': plan_diff is None and gesture_diff is None,
            'sampled_stop_and_head_pitch_transitions': events['passed'],
        })
        if live:
            clock = report['realtime']
            flags['start_stop_and_replay'] = (report['firstContextFrame'] == clock['scheduledContextFrame']
                and clock['scheduledContextFrame'] - clock['armedContextFrame'] == limits['expected_live_schedule_lead_frames']
                and browser['stop']['contextState'] == 'closed' and browser['stop']['ready'] and browser['stop']['replayed'])
        else:
            flags['starts_at_zero'] = report['firstContextFrame'] == 0
        result[mode] = {**output, 'events': events, 'plan_first_difference': plan_diff, 'plan_maximum_error': plan_error,
                        'gesture_first_difference': gesture_diff, 'gesture_maximum_error': gesture_error}
        checks.update({f'{mode}/{key}': value for key, value in flags.items()})
    return checks, result


def measure(config, source_path, references, artifacts, execute, bun):
    source = timing.read(source_path)
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'sing_fast',
             '--test', 'sung_release', '--test', 'body_mix'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / wasm.WASM, binary)
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(source_path), str(LIVE)])
    browser = timing.read(artifacts / 'browser-run.json')
    tables = (timing.read(body_song.vowel.TABLE), timing.read(body_song.ipa.CASE)['expected_sibilant_tip_y_cm'],
              timing.read(body_song.ipa.BODY_TABLE)['measurement']['reference_endpoints'])
    checks, cases = {}, {}
    wasm_hash = sha256(binary)
    for variant in source['variants']:
        label = variant['id']
        flags, cases[label] = compare_variant(variant, source, config['measurement'], references[label],
                                               browser[label], tables, wasm_hash, artifacts, execute)
        checks.update({f'{label}/{name}': bool(value) for name, value in flags.items()})
    return {'checks': checks, 'cases': cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    run_id = parser.parse_args().run_id
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source = WORKSPACE / 'cases' / config['native_case']
    references, inputs = reference_artifacts(config, source)
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    modules = (speech, body_song, body_song.ipa, body_song.vowel, body_song.calibrated, song, shared, timing, wasm)
    inputs += [CASE, LIVE, source, body_song.ipa.BODY_TABLE, body_song.ipa.CASE, Path(__file__).resolve(),
               *shared.candidate_sources(), *web_sources(), *(Path(m.__file__) for m in modules),
               *(WORKSPACE / 'tools' / name for name in ('measure_worklet_english_body.py', 'measure_worklet_fixed.py',
                   'upstream_baseline.py', 'measure_body_english.py', 'measure_alveolar_stop.py', 'measure_sibilant.py',
                   'measure_pcm_output.py'))]
    meta = {'case_id': config['id'], 'upstream_revision': revision, 'reference_run': config['reference_run'],
            'node': subprocess.check_output(['node', '--version'], text=True).strip(),
            'bun': subprocess.check_output([*bun, '--version'], text=True).strip(), 'input_root': '$REPOSITORY'}
    return shared.record_measurement(run_id, CASE, inputs, meta,
                                     lambda out, run: measure(config, source, references, out, run, bun),
                                     command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
