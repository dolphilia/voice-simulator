"""舌先・舌背の鼻音と韓国語歌唱を、調音計画・鼻端流量・PCMで照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as alveolar
import measure_bilabial_nasal as nasal
import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_song_plan as song_plan
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as velar
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/lingual-nasals.json'


def gesture(label, t0, t1, rise, fall, strength, targets, **extra):
    return {'label': label, 't0': t0, 't1': t1, 'rampIn': rise, 'rampOut': fall,
            'strength': strength, 'targets': targets, **extra}


def expected_gestures(part, delay, seal_lead):
    name, start, end = (part[key] for key in ('ipa', 't0', 't1'))
    aim = start + min(delay, max(0.0, end - start - .03))
    hold = {'releaseHold': .045, 'speed': 1.55}
    if name == 'ŋ':
        closure = [
            gesture(name, aim - .024, max(aim + .01, end - .034), .03, .03, 40,
                    {'tongue_body_y_cm': 8.35}, releaseHold=.045, speed=1.1925),
            gesture(name, aim, end, .05, .05, 2.2, {'jaw_cm': .7}),
            gesture(name, aim, end, .05, .05, .25, {'tongue_body_x_cm': 2.3}),
        ]
    elif name == 'n':
        closure = [
            gesture(name, aim - .031, max(aim + .01, end - .02), .03, .018, 40,
                    {'tongue_tip_x_cm': 6.25, 'tongue_tip_y_cm': 9.68}, **hold),
            gesture(name, aim, end, .05, .05, 1.2,
                    {'tongue_body_x_cm': 3.2, 'tongue_body_y_cm': 7.4}),
        ]
    else:
        closure = [gesture(name, aim - .022, max(aim + .01, end - .019), .03, .018, 40,
                           {'lip_aperture_cm': -.25}, **hold)]
    return [*closure, gesture('velum', start - .02, end - seal_lead, .05, .03, 4, {'velum_cm2': .45})]


def compare_plan(settings, reference, variant, tol):
    song = settings.get('song')
    if song is not None:
        spans = [{'segments': phrase['timing']['segments']} for phrase in song['plan']['phrases']]
        comparison = {**settings, 'speech': {'utterances': spans}}
    else:
        comparison = settings
    parts, upstream = speech.compare_plans(comparison, reference, tol)
    symbols = [row[0] for row in variant['nasals']]
    nasals = [s for s in parts if s['ipa'] in ('m', 'n', 'ŋ')]
    actual = [g for g in settings['gestures'] if g['label'] in {*symbols, 'velum'}]
    expected = []
    same_parts = [p['ipa'] for p in nasals] == symbols
    if same_parts:
        for part, (_, delay, seal) in zip(nasals, variant['nasals'], strict=True):
            expected.extend(expected_gestures(part, delay, seal))
    first, error = timing.compare(actual, expected, tol)
    velum = [g for g in actual if g['label'] == 'velum']
    leads = [p['t1'] - g['t1'] for p, g in zip(nasals, velum)]
    checks = {'upstream_plan': upstream['passed'], 'registered_closure_and_velum': same_parts and first is None}
    summary = {'upstream': upstream, 'first_registered_difference': first, 'independent_gesture_max_error': error,
               'nasal_spans': nasals, 'velum_seal_lead_seconds': leads, 'velum_gestures': velum}
    if song is not None:
        syllables = song['syllables']
        boundaries = [s['wordEnd'] for s in syllables]
        onset, coda = ([[p['ipa'] for p in s[k]] for s in syllables] for k in ('onset', 'coda'))
        checks['lyrics_nasalization'] = ((onset, coda, boundaries)
                                          == (variant['onsets'], variant['codas'], variant['word_ends']))
        summary['syllables'] = syllables
    return checks, summary


def sample_nasal(trace, part, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    port = trace['velum_port_area_cm2']
    lip = trace['lip_minimum_cm2']
    if part['ipa'] == 'm':
        area = lip
    else:
        area = trace['oral_minimum_cm2']
        if 'pharynx_minimum_cm2' in trace.dtype.names:
            area = np.minimum(area, trace['pharynx_minimum_cm2'])
    in_span = (time >= part['t0']) & (time < part['t1'])
    active = in_span & (port >= limits['audible_port_area_cm2']) & (area < limits['sealed_area_cm2'])
    if part['ipa'] != 'm':
        active &= lip >= limits['open_lip_minimum_cm2']
    indices = np.flatnonzero(active)
    out = {'ipa': part['ipa'], 'passed': False, 'closed_and_open_port_frames': 0,
           'area_minimum_in_span_cm2': float(area[in_span].min()),
           'max_port_in_span_cm2': float(port[in_span].max())}
    if not indices.size:
        return out
    closed = max(np.split(indices, np.flatnonzero(np.diff(indices) != 1) + 1), key=len)
    left, right = int(closed[0]), int(closed[-1])
    first, last = (left + round(len(closed) * ratio) for ratio in limits['center_fraction'])
    samples = slice(first, max(last, first + 1))
    nose, mouth, through = [float(np.sqrt(np.mean(trace[name][samples]**2)))
                            for name in ('nose_flow_cm3_s', 'lip_flow_cm3_s', 'velum_flow_cm3_s')]
    fraction = nose / (nose + mouth) if nose + mouth > 0 else 0
    ratio_required = part['ipa'] != 'ŋ' or 'dorsal_flow_probe' not in limits
    minimum_ratio = limits.get('minimum_nasal_ratio') if ratio_required else None
    early = np.flatnonzero((time >= part['t0'] - .06) & (time < part['t1'])
                           & (area < limits['acoustic_closure_area_cm2']))
    return {**out, 'first_sustained_frame': left, 'last_sustained_frame': right,
            'first_acoustic_closure_frame': int(early[0]) if early.size else None,
            'center_lip_area_cm2': float(lip[(left + right) // 2]),
            'center_flow_rms_cm3_s': {'nose': nose, 'mouth': mouth, 'port': through},
            'nose_fraction': fraction, 'closed_and_open_port_frames': len(closed),
            'passed': len(closed) >= limits['minimum_closed_and_open_port_frames']
            and (minimum_ratio is None or fraction >= minimum_ratio)
            and nose >= limits['minimum_nose_rms_cm3_s']}


def compare_closed_branches(source, event, limits, out, probe, execute, *, section='speech_voice'):
    options = limits['dorsal_flow_probe']
    first, last = (event[k] for k in ('first_sustained_frame', 'last_sustained_frame'))
    frames = list(range(first, last + 1, options['stride_output_frames']))
    path = out / 'closure-profile-input.json'
    timing.write(path, {section: {**source, 'tract_profile_frames': frames, 'tract_profile_acoustics': True}})
    candidate, reference = (out / name for name in ('closure-profile-cli.csv', 'closure-profile-upstream.csv'))
    execute([*song_plan.CLI, 'render', str(path), str(candidate)])
    execute([str(probe), str(path), str(reference), str(out / 'closure-profile-upstream.f32'),
             str(out / 'closure-profile-upstream-plan.json')], cwd=UPSTREAM)
    a, b = [np.genfromtxt(p, delimiter=',', names=True, dtype=None, encoding='utf-8') for p in (candidate, reference)]
    if list(np.unique(a['frame'])) != frames or any(not np.array_equal(a[k], b[k]) for k in ('frame', 'tube', 'cell')):
        raise ValueError('閉鎖断面の比較時刻かセルが一致しません')
    cols = ('length_cm', 'area_cm2', 'minimum_area_cm2')
    errors = {k: float(abs(a[k] - b[k]).max()) for k in cols}
    state_rel = max(float(abs(a[k] - b[k]).max()) / max(float(abs(b[k]).max()), 1e-6)
                    for k in ('pressure_dyn_cm2', 'outward_flow_cm3_s'))

    def sealed_flows(data):
        touches = []
        lip = []
        for frame in frames:
            row = data[data['frame'] == frame]
            flow = row['outward_flow_cm3_s']
            closed = np.flatnonzero(row['minimum_area_cm2'] < limits['sealed_area_cm2'])
            if not closed.size or closed[0] == 0 or closed[-1] == len(row) - 1:
                raise ValueError('指定フレームに唇の内側の閉鎖セルがありません')
            touches.extend(abs(flow[np.union1d(closed - 1, closed)]))
            lip.append(abs(flow[-1]))
        return {'maximum_closed_branch_flow_cm3_s': float(max(touches)),
                'maximum_lip_flow_during_closure_cm3_s': float(max(lip))}

    native, upstream = (sealed_flows(x) for x in (a, b))
    passed = (max(errors.values()) <= limits['geometry_absolute_tolerance']
        and state_rel <= limits['audio_state_peak_relative_tolerance']
        and all(x['maximum_closed_branch_flow_cm3_s'] == 0
                and x['maximum_lip_flow_during_closure_cm3_s'] >= options['minimum_lip_peak_cm3_s']
                for x in (native, upstream)))
    return {'passed': passed, 'sampled_frames': len(frames), 'cli': native, 'upstream': upstream,
            'geometry_absolute_errors': errors, 'acoustic_state_peak_relative_error': state_rel}


def compare_variant(config, variant, is_song, base, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    section = 'song_voice' if is_song else 'speech_voice'
    source = {**timing.read(base)[section], 'body': variant['body']}
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'], 'notes': config['notes']}
    else:
        source['input'] = {'id': variant['id'], 'text': variant['text'], 'rate': 1.0}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], section: source})
    settings, trace, files, upper_trace, upper_wave, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    baseline = timing.read(upper_plan)
    checks, plan = compare_plan(settings, baseline, variant, limits['gesture_absolute_tolerance'])
    frames = settings['output_frames']
    actual, upper = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    fields = [field for field in actual.dtype.names if field != 'oral_minimum_cell']
    first_difference, series = voice.compare_traces(actual[fields], upper[fields], limits)
    cells = alveolar.compare_cell_minima(actual, upper, {**limits, 'closed_area_cm2': limits['sealed_area_cm2']})
    rate, pcm = wavfile.read(files[0][0])
    ref = np.fromfile(upper_wave, dtype='<f4')
    if any(x.shape != (frames,) or x.dtype != np.float32 or not np.isfinite(x).all() for x in (pcm, ref)):
        raise ValueError('PCMの長さ、型、有限性が一致しません')
    diff = wasm.compare_pcm(pcm, ref, limits['pcm_absolute_tolerance'])
    scale = limits['body_linear_scale'][variant['body']]
    independent = nasal.independent_velum(
        actual, settings, {'speech_voice': source, 'measurement': limits}, rate, body_scale=scale)
    events, upstream_events = [[sample_nasal(t, part, limits) for part in plan['nasal_spans']]
                              for t in (actual, upper)]
    indices = ('first_sustained_frame', 'last_sustained_frame', 'first_acoustic_closure_frame')
    checks.update({
        'trace': first_difference is None and cells['passed'],
        'pcm_and_format': diff['first_frame_over_tolerance'] is None
            and rate == limits['output_rate_hz'] and frames == baseline['output_frames'],
        'velum_dynamics_and_exact_zero_flow': independent['passed']
            and all(np.all(t['velum_flow_cm3_s'][t['velum_port_area_cm2'] == 0] == 0) for t in (actual, upper)),
        'oral_closure_with_nasal_flow': bool(events) and all(e['passed'] for e in (*events, *upstream_events)),
        'closure_event_frames': all(all(a.get(k) == b.get(k) for k in indices)
                                    for a, b in zip(events, upstream_events, strict=True)),
        'same_host_partitions': all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1])
                                    for w, c in files),
    })
    summary = {'plan': plan, 'candidate_events': events, 'upstream_events': upstream_events,
               'independent_velum': independent, 'first_trace_over_tolerance': first_difference,
               'trace_errors': series, 'cell_selection': cells, 'pcm': diff}
    if 'dorsal_flow_probe' in limits:
        matches = [abs(a['nose_fraction'] - b['nose_fraction']) for a, b in zip(events, upstream_events, strict=True)
                   if 'nose_fraction' in a and 'nose_fraction' in b]
        checks['nose_fraction_matches_reference'] = (bool(matches) and len(matches) == len(events)
            and max(matches) <= limits['dorsal_flow_probe']['nose_fraction_absolute_tolerance'])
        if variant['id'] in limits['dorsal_flow_probe']['variants']:
            if len(events) == 1 and events[0]['passed']:
                summary['closure_probe'] = compare_closed_branches(source, events[0], limits, out, probe, execute)
                checks['closed_branches_with_lip_flow'] = summary['closure_probe']['passed']
            else:
                checks['closed_branches_with_lip_flow'] = False
    browser_reference = (source, settings, actual, upper, pcm) if is_song else None
    return checks, summary, browser_reference


def measure(config, sources, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'nasal_spans', '--test', 'syllables'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, rendered = {}, {}, {}
    for kind, source in sources.items():
        for variant in config[kind]:
            label = variant['id']
            verdicts, variants[label], replay = compare_variant(
                config, variant, kind == 'song', source, artifacts / label, probe, execute)
            checks.update({f'{label}/{key}': bool(passed) for key, passed in verdicts.items()})
            if replay is not None:
                rendered[label] = replay
    onset_leads = [variants[name]['plan']['velum_seal_lead_seconds'] for name in ('before-t', 'before-d')]
    seal_delta = onset_leads[0][0] - onset_leads[1][0] if all(len(s) == 1 for s in onset_leads) else None
    checks['voiced_stop_delays_seal'] = (seal_delta is not None
        and abs(seal_delta - .015) <= config['measurement']['gesture_absolute_tolerance'])
    result = {'checks': checks, 'variants': variants, 'voiced_stop_seal_delay_seconds': seal_delta}
    if browser:
        flags, details = velar.browser_measure(config, rendered, artifacts, execute, bun, case_path=CASE)
        checks.update(flags)
        result['browser'] = details
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='固定上流とCLIを比較する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    paths = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    modules = (alveolar, nasal, voice, speech, song_plan, timing, shared, velar, wasm)
    inputs = [CASE, *paths.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
              *(Path(module.__file__) for module in modules), WORKSPACE / 'tools/upstream_baseline.py']
    reference = ('src/phonetics/inventory.rs', 'src/phonetics/planner.rs', 'src/phonetics/korean.rs',
                 'src/phonetics/sing.rs', 'src/control/articulators.rs', 'src/voice/human_airway.rs',
                 'src/anatomy/human.rs', 'tests/nasal_spans.rs', 'tests/syllables.rs')
    meta = {'case_id': config['id'], 'case_revision': config['revision'], 'upstream_revision': revision,
            'upper_source_sha256': {name: sha256(UPSTREAM / 'crates/chimera' / name) for name in reference}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if not args.native_only:
        inputs += [velar.KOREAN, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        meta.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                    bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    else:
        inputs += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    return shared.record_measurement(args.run_id, CASE, inputs, meta,
        lambda out, run: measure(config, paths, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
