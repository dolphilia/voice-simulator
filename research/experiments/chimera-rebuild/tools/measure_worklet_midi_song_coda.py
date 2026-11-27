"""鍵盤歌唱の最後の離鍵と語末の両唇閉鎖を固定上流と照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_wasm_fixed import compare_pcm, first_index, read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_midi_song import CAPTURE
from measure_worklet_midi_songbird import rms
from measure_worklet_songbird import read_wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-midi-song-coda.json'
PROBE = WORKSPACE / 'tools/upstream_live_song_probe.rs'
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
FIELDS = ('lip_aperture_cm', 'lip_minimum_cm2', 'gate', 'voicing', 'lip_flow_cm3_s',
          'glottal_area_cm2', 'glottal_flow_cm3_s', 'radiation_derivative_cm3_s2')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    return path


def read_states(path, frames):
    state = np.genfromtxt(path, delimiter=',', names=True, usecols=('frame', *FIELDS))
    if not np.array_equal(state['frame'], np.arange(frames)) or not all(
            np.isfinite(state[name]).all() for name in FIELDS):
        raise ValueError(f'{path.name} の観測フレームまたは有限性が条件外です')
    return state


def candidate_render(case, name, artifacts, execute, frames, rate):
    trace, wave, pcm_trace = (artifacts / suffix for suffix in (f'{name}-voice.csv', f'{name}.wav', f'{name}-pcm.csv'))
    execute([*CLI, 'render', str(case), str(trace)])
    execute([*CLI, 'render-pcm', str(case), str(wave), str(pcm_trace), '113'])
    return read_states(trace, frames), read_wave(wave, rate, frames)


def upstream_render(probe, voice, commands, name, artifacts, execute, frames, rate):
    path = write_json(artifacts / f'{name}-case.json', voice | {'events': commands})
    trace, raw = (artifacts / f'{name}-voice.{ext}' for ext in ('csv', 'f32'))
    execute([str(probe), str(path), str(trace), str(raw)], cwd=UPSTREAM)
    audio = np.fromfile(raw, dtype='<f4')
    if audio.shape != (frames,) or not np.isfinite(audio).all():
        raise ValueError('固定上流のPCMが条件外です')
    wavfile.write(artifacts / f'{name}.wav', rate, audio)
    return read_states(trace, frames), audio


def compare_plan(inspect, commands, off, ipa, spec):
    before, after = (row['gestures'] for row in inspect['scheduled'])
    existing = {tag for tag, _ in before}
    created = [(tag, g) for tag, g in after if tag not in existing]
    off_clock = inspect['transitions'][-1]['transition']['clock_seconds']
    selected = [(tag, g) for tag, g in created if g['label'] == ipa and 'lip_aperture_cm' in g['targets']]
    tag, candidate = selected[0]
    released = [c['tag'] for c in commands[-1]['commands'] if c['type'] == 'release']
    upper_schedule, = [c for c in commands[-1]['commands'] if c['type'] == 'schedule']
    upper, = [g for g in upper_schedule['gestures'] if g.get('label') == ipa and 'lipAp' in g['targets']]
    start = spec['relative_segment_start_seconds']
    duration = spec['upstream_intrinsic_seconds'] * spec['singing_scale']
    expected = {'start_seconds': start - spec['oral_onset_lead_seconds'],
                'end_seconds': max(start + .01, start + duration - spec['oral_release_lead_seconds']),
                'ramp_in_seconds': spec['activation_ramp_in_seconds'],
                'ramp_out_seconds': spec['activation_ramp_out_seconds']}
    def positions(gesture, offset):
        return dict(zip(expected, (gesture['t0'] + offset, gesture['t1'] + offset,
                                   gesture['rampIn'], gesture['rampOut']), strict=True))
    result = {'candidate': positions(candidate, -off_clock), 'fixed_upstream': positions(upper, upper_schedule['lead'])}
    checks = {
        'last_release_retires_vowel_and_has_new_coda_tag': inspect['scheduled'][-1]['frame'] == off
            and len(selected) == 1 and tag not in existing
            and not any(g['label'] == ipa for _, g in before)
            and len(set(released)) == 2 and upper['tag'] not in released,
        'dominant_lip_plan_matches_independent_times': all(
            abs(row[key] - val) <= spec['maximum_timing_error_seconds']
            for row in result.values() for key, val in expected.items())
            and abs(candidate['targets']['lip_aperture_cm'] - upper['targets']['lipAp']) <= 1e-12
            and candidate['strength'] == upper['strength'],
    }
    return checks, {**result, 'analytic': expected, 'analytic_segment_seconds': [start, start + duration],
                    'lip_target_cm': candidate['targets']['lip_aperture_cm'],
                    'strength': candidate['strength'], 'candidate_coda_tag': tag,
                    'fixed_released_tags': released, 'fixed_coda_tag': upper['tag']}


def window(off, rate, bounds):
    return slice(off + round(bounds[0] * rate), off + round(bounds[1] * rate))


def acoustics(state, audio, alternate, alternate_audio, off, rate, settings):
    held = window(off, rate, settings['held_window_before_release_seconds'])
    coda = window(off, rate, settings['coda_window_after_release_seconds'])
    decay = window(off, rate, settings['decay_window_after_release_seconds'])
    lip = state['lip_minimum_cm2']
    limit = settings['closed_lip_area_cm2']
    local = first_index(lip[coda] < limit)
    closed = coda.start + local if local is not None else None
    local = first_index(lip[closed:coda.stop] >= limit) if closed is not None else None
    opened = closed + local if local is not None else None
    center = None
    if opened is not None:
        trim = round((opened - closed) * settings['closed_flow_trim_fraction'])
        center = slice(closed + trim, opened - trim)
    held_flow = rms(state['lip_flow_cm3_s'][held])
    closed_flow = rms(state['lip_flow_cm3_s'][center]) if center is not None and center.start < center.stop else None
    flow_ratio = closed_flow / held_flow if closed_flow is not None and held_flow > 0 else None
    held_rms = rms(audio[held])
    decay_ratio = rms(audio[decay]) / held_rms if held_rms > 0 else None
    diff = compare_pcm(audio, alternate_audio, settings['pcm_difference_threshold'])
    first = {field: first_index(state[field] != alternate[field]) for field in FIELDS}
    pcm_first = diff['first_frame_over_tolerance']
    checks = {
        'held_vowel_is_open_and_voiced': float(lip[held].min()) > settings['open_lip_area_cm2']
            and float(state['voicing'][held].min()) > settings['minimum_held_voicing'],
        'coda_closes_and_reopens_with_small_lip_flow': closed is not None and opened is not None
            and flow_ratio is not None and flow_ratio <= settings['maximum_closed_flow_ratio'],
        'coda_decays_to_quiet': decay_ratio is not None and decay_ratio <= settings['maximum_release_rms_ratio'],
        'without_coda_no_closure_and_same_pcm_before_key_up': float(alternate['lip_minimum_cm2'][coda].min()) >= limit
            and all(frame is not None and frame >= off for field, frame in first.items() if field != 'voicing')
            and np.array_equal(audio[:off].view('u4'), alternate_audio[:off].view('u4'))
            and pcm_first is not None and off <= pcm_first <= off + round(rate * settings['maximum_pcm_difference_delay_seconds']),
    }
    return checks, {'closure_frame': closed, 'reopen_frame': opened,
                    'closure_offset_seconds': (closed - off) / rate if closed is not None else None,
                    'reopening_offset_seconds': (opened - off) / rate if opened is not None else None,
                    'closed_lip_flow_rms_cm3_s': closed_flow, 'held_lip_flow_rms_cm3_s': held_flow,
                    'closed_to_held_flow_ratio': flow_ratio, 'held_pcm_rms': held_rms, 'decay_pcm_ratio': decay_ratio,
                    'coda_minimum_lip_cm2': float(lip[coda].min()),
                    'coda_minimum_voicing': float(state['voicing'][coda].min()),
                    'no_coda_minimum_lip_cm2': float(alternate['lip_minimum_cm2'][coda].min()),
                    'first_change_from_no_coda': first, 'pcm_difference_from_no_coda': diff}


def measure(case, artifacts, execute, bun):
    m = case['measurement']
    fixture = case['input']
    rate = fixture['output_rate_hz']
    execute([*bun, 'test', 'tests/singing-live.test.ts', '-t', 'each key sings the next syllable'], cwd=UPSTREAM)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'golden_planning', 'live_notes_match_typescript'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-plans-test.log')
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=artifacts / 'browser-build.log')
    execute(['node', str(CAPTURE), str(artifacts), str(CASE), str(UPSTREAM)], cwd=WEB)
    browser = read_json(artifacts / 'midi-song-browser.json')
    replay = artifacts / 'midi-song-case.json'
    report = read_json(artifacts / 'midi-song.json')
    voice = read_json(replay)['live_song_voice']
    frames = voice['frames']
    inspected = write_json(artifacts / 'inspect-case.json', {'live_song_voice': voice | {'observe_gestures': True}})
    execute([*CLI, 'inspect', str(inspected)], stdout=artifacts / 'cli-inspect.json')
    inspect = read_json(artifacts / 'cli-inspect.json')
    on, off = (event['frame'] for event in voice['events'])
    trace, candidate = candidate_render(replay, 'cli', artifacts, execute, frames, rate)
    pcm = read_wave(artifacts / 'midi-song.wav', rate, frames)
    coda_removed = [syl | {'coda': []} for syl in voice['syllables']]
    no_coda = write_json(artifacts / 'no-coda-case.json', {'live_song_voice': voice | {'syllables': coda_removed}})
    control, control_pcm = candidate_render(no_coda, 'no-coda', artifacts, execute, frames, rate)
    source = browser['upstream']
    commands = [{'frame': frame, 'commands': row['commands']}
                for frame, row in zip((on, off), source['events'], strict=True)]
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    upper, upper_pcm = upstream_render(probe, voice, commands, 'upstream', artifacts, execute, frames, rate)
    off_only = commands[-1] | {'commands': [op for op in commands[-1]['commands'] if op['type'] == 'release']}
    upper_control, upper_control_pcm = upstream_render(
        probe, voice, [commands[0], off_only], 'upstream-no-coda', artifacts, execute, frames, rate)

    plan_checks, plan = compare_plan(inspect, commands, off, m['coda_ipa'], m['expected_p_plan'])
    measured = {}
    checks = dict(plan_checks)
    for name, states, audio, alt, alt_audio in (('candidate', trace, candidate, control, control_pcm),
                                                ('fixed_upstream', upper, upper_pcm, upper_control, upper_control_pcm)):
        outcomes, value = acoustics(states, audio, alt, alt_audio, off, rate, m)
        checks.update({f'{name}_{label}': ok for label, ok in outcomes.items()})
        measured[name] = value

    observed = dict(zip(report['columns'], np.asarray(report['observations']).T, strict=True))
    points = observed['frames_rendered'].astype(int) - 1
    quantum = m['render_quantum_frames']
    fields = {'lip_minimum_cm2': 'lip_minimum_cm2', 'gate': 'gate', 'glottal_voicing': 'voicing',
              'glottal_area_cm2': 'glottal_area_cm2', 'glottal_flow_cm3_s': 'glottal_flow_cm3_s',
              'radiation_derivative_cm3_s2': 'radiation_derivative_cm3_s2'}
    deltas = {name: float(abs(observed[name] - trace[field][points]).max()) for name, field in fields.items()}
    expected_keys = [{k: v for k, v in event.items() if k != 'seconds'} for event in fixture['events']]
    notes = [row['transition'] for row in inspect['transitions']]
    glyphs = {k: [[p['ipa'] for p in s['coda']] for s in v]
              for k, v in (('candidate', voice['syllables']), ('fixed_upstream', source['syllables']))}
    checks.update({
        'both_normal_singing_screens_use_midi_and_pronounce_coda': all(
            browser[side]['requests'] == [{'sysex': False}] and not browser[side]['errors']
            for side in ('candidate', 'upstream'))
            and all(pattern == [[m['coda_ipa']]] for pattern in glyphs.values())
            and [(e['pitch'], e['text'], e['held']) for e in source['events']]
                == [(m['expected_note'], fixture['lyrics'], [m['expected_note']]), (None, None, [])]
            and [n['action'] for n in notes] == ['syllable', 'release']
            and [n['sounding_note'] for n in notes] == [m['expected_note'], None],
        'applied_keys_and_contiguous_worklet': [row['key'] for row in inspect['transitions']] == expected_keys
            and report['songKeys'] == voice['events']
            and all(frame % quantum == 0 for frame in (on, off))
            and abs((off - on) / rate - (fixture['events'][1]['seconds'] - fixture['events'][0]['seconds']))
                <= m['maximum_relative_event_error_seconds']
            and np.array_equal(points, np.arange(quantum - 1, frames, quantum))
            and np.all(np.diff(observed['context_frame']) == quantum)
            and report['sampleRate'] == rate == source['rate'],
        'candidate_browser_and_cli_pcm_and_state': np.array_equal(pcm.view('u4'), candidate.view('u4'))
            and max(deltas.values()) <= m['maximum_cli_observation_error'],
    })
    initial = {key: first_index(trace[key] != upper[key]) for key in FIELDS}
    after = {key: first_index(trace[key][off:] != upper[key][off:]) for key in FIELDS}
    return {'checks': {name: bool(value) for name, value in checks.items()}, 'browser': browser['chromium'],
            'frames': frames, 'key_frames': [on, off], 'observations': len(points), 'candidate_trace_deltas': deltas,
            'plan': plan, 'acoustics': measured, 'syllables': glyphs, 'fixed_engine_first_difference': initial,
            'fixed_engine_first_difference_relative_to_release': after,
            'fixed_engine_pcm': compare_pcm(candidate, upper_pcm, m['pcm_difference_threshold'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case = read_json(CASE)
    baseline = WORKSPACE / 'runs' / case['measurement']['baseline_run'] / 'manifest.json'
    previous = read_json(baseline)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if (revision != case['upstream_revision'] or previous['status'] != 'pass'
            or previous['case_id'] != Path(case['source_case']).stem or previous['upstream_revision'] != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流と合格済みの鍵盤歌唱の基準を確認してください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    upstream = [UPSTREAM / path for path in ('src/ui/midi.ts', 'src/ui/store.ts', 'src/ui/singing.ts',
             'src/audio/AudioEngine.ts', 'src/worklet/processor.ts', 'crates/chimera/src/engine.rs',
             'crates/chimera/src/control/score.rs', 'crates/chimera/src/phonetics/sing.rs',
             'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/phonetics/durations.rs',
             'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/tests/golden_planning.rs', 'tests/singing-live.test.ts')]
    sources = [CASE, WORKSPACE / 'cases' / case['source_case'], baseline, PROBE, CAPTURE, Path(__file__),
               *(WORKSPACE / 'tools' / f'{name}.py' for name in ('measure_worklet_midi_song',
                 'measure_wasm_fixed', 'measure_worklet_songbird', 'measure_worklet_midi_songbird')),
               *web_sources(), *shared.candidate_sources(), *upstream]
    details = {'case_id': case['id'], 'revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'baseline_manifest_sha256': sha256(baseline),
               'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(args.run_id, CASE, sources, details,
        lambda out, execute: measure(case, out, execute, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
