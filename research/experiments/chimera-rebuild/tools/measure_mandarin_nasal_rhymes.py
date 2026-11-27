"""中国語の鼻音韻尾を調音、流量、PCM、実ブラウザで固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as cells
import measure_bilabial_nasal as velum
import measure_bilabial_stop as voice
import measure_lingual_nasals as nasal
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as browser_song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/mandarin-nasal-rhymes.json'
REVISED_CASE = WORKSPACE / 'cases/mandarin-nasal-rhymes-v2.json'


def compare_plan(config, variant, settings, upper):
    limits = config['measurement']
    tol = limits['gesture_abs_tolerance']
    song = settings['song']['plan']
    notes = song['notes']
    source = {**settings, 'speech': {'utterances': [
        {'segments': p['timing']['segments']} for p in song['phrases']]}}
    parts, reference = frication.compare_plans(source, upper, tol)
    codas = [part for part in parts if part['ipa'] in ('m', 'n', 'ŋ')]
    wanted = variant['rhymes']
    expected_gestures, spans = [], []
    gesture = nasal.gesture
    for rhyme in wanted:
        index = rhyme['note']
        a, b = (notes[index][key] for key in ('beat_seconds', 'nucleus_end_seconds'))
        coda = next(part for part in codas if part['ipa'] == rhyme['ipa'] and abs(part['t0'] - b) <= tol)
        finish = coda['t1']
        length = b - a
        expected_gestures.append(gesture(
            'nasal vowel', b - .06, b + .02, min(.25, .6 * length), .03, 2, {'velum_cm2': .30}))
        if targets := rhyme['approach']:
            expected_gestures.append(gesture(
                'coda approach', b - .01, b + .02, min(.15, .5 * length), .03,
                .6 if rhyme['ipa'] == 'n' else 1.2, targets))
        phrase = next(p for p in song['phrases'] if p['first_note_index'] <= index <= p['last_note_index'])
        if index == phrase['last_note_index']:
            if index + 1 == len(notes):
                hold, release, port = .10, .12, .25
            else:
                next_beat = notes[index + 1]['beat_seconds']
                hold = max(0, min(.10, next_beat - rhyme['expected_next_onset_seconds'] - .05 - finish))
                release, port = .05, hold
            expected_gestures.extend([
                gesture('coda held', finish - .03, finish + hold, .02, release, 40, rhyme['hold_targets']),
                gesture('velum', finish - .03, finish + port, .02, .05, 4, {'velum_cm2': .45}),
            ])
        spans.append({'vowel_start': a, 'vowel_end': b, 'nasal': coda})
    actual = [g for g in settings['gestures'] if g['label'] in ('nasal vowel', 'coda approach', 'coda held')
              or (g['label'] == 'velum' and abs(g['rampIn'] - .02) <= tol)]
    mismatch, error = timing.compare(actual, expected_gestures, tol)
    next_beat = limits['start_seconds']
    expected_notes = []
    for midi, beats in zip(variant['midi'], variant['beats'], strict=True):
        end = next_beat + 60 / limits['bpm'] * beats
        expected_notes.append([next_beat, end, 440.0 * 2 ** ((midi - 69.0) / 12.0)])
        next_beat = end
    actual_notes = [[note[k] for k in ('beat_seconds', 'beat_end_seconds', 'f0_hz')] for note in notes]
    beat_difference, _ = timing.compare(actual_notes, expected_notes, tol)
    checks = {'upstream_plan': reference['passed'], 'nasal_gesture_equations': mismatch is None,
              'independent_beat_frequency': beat_difference is None}
    if variant.get('check_melisma'):
        checks['melisma_coda_on_last_note'] = (len(codas) == len(spans) == 1
            and codas[0]['t0'] >= notes[1]['beat_seconds'] and spans[0]['vowel_start'] == notes[1]['beat_seconds'])
    for rhyme, span in zip(wanted, spans, strict=True):
        last_vowel = [part for part in parts if part['kind'] == 'vowel' and
                      abs(part['t1'] - span['vowel_end']) <= tol]
        checks[f'nucleus_for_note_{rhyme["note"]}'] = (
            len(last_vowel) == 1 and last_vowel[0]['ipa'] == rhyme['vowel'])
    reference.update(rhymes=spans, actual_rhyme_gestures=actual, registered_rhyme_gestures=expected_gestures,
                     first_rhyme_difference=mismatch, maximum_rhyme_difference=error,
                     notes=actual_notes, first_beat_difference=beat_difference)
    return checks, reference, spans or [
        {'vowel_start': notes[0]['beat_seconds'], 'vowel_end': notes[0]['nucleus_end_seconds'], 'nasal': codas[0]}]


def rms_level(pcm, seconds, rate, width):
    first = int((seconds - width / 2) * rate)
    n = round(width * rate)
    power = np.mean(np.square(pcm[first:first + n], dtype='float64'))
    return float(10 * np.log10(max(1e-12, power)))


def observe(trace, pcm, span, rate, variant, limits):
    time = (trace['frame'] + 1) / rate
    a, b = (span[k] for k in ('vowel_start', 'vowel_end'))
    coda = span['nasal']
    end = coda['t1']
    port = trace['velum_port_area_cm2']
    reached = np.flatnonzero((time >= a) & (time < b) & (port >= limits['audible_port_area_cm2']))
    onset = float(time[reached[0]]) if reached.size else None
    lead = b - onset if onset is not None else None
    if coda['ipa'] == 'm':
        # 唇鼻音の観測は唇で閉鎖を判定する。
        area = trace['lip_minimum_cm2']
    else:
        area = trace['oral_minimum_cm2']
        if 'pharynx_minimum_cm2' in trace.dtype.names:
            area = np.minimum(area, trace['pharynx_minimum_cm2'])
    measured = nasal.sample_nasal(trace, coda, {**limits, 'output_rate_hz': rate,
        'minimum_closed_and_open_port_frames': round(rate * limits['minimum_closed_seconds'])})
    width = limits['measurement_frame_seconds']
    lo, hi = limits['terminal_contact_window_seconds']
    terminal = (time >= end + lo) & (time < end + hi)
    terminal_contact = float(np.mean(area[terminal] < limits['sealed_area_cm2']))
    details = {'port_open_time_seconds': onset, 'port_lead_seconds': lead,
               'coda_flow_and_contact': measured, 'terminal_contact_fraction': terminal_contact}
    checks = {'closed_with_nasal_flow': measured['passed'],
              'zero_flow_when_port_closed': bool(np.all(trace['velum_flow_cm3_s'][port == 0] == 0))}
    if variant['rhymes']:
        checks['port_opens_before_coda'] = lead is not None and lead >= limits['minimum_port_lead_seconds']
    if variant.get('terminal_contact_check'):
        checks['contact_held_after_phrase'] = terminal_contact >= limits['minimum_terminal_contact_fraction']
    if variant.get('release_level_check'):
        baseline = rms_level(pcm, end - .05, rate, width)
        rebound = max(rms_level(pcm, end - .02 + i * .02, rate, width) - baseline for i in range(6))
        details['max_terminal_rebound_db'] = rebound
        checks['no_terminal_vowel_level_rebound'] = rebound < limits['maximum_terminal_rebound_db']
    if variant.get('dip_check'):
        start, stop = a + .10, a + variant['beats'][0] * 60 / limits['bpm'] - .06
        levels = [rms_level(pcm, start + .02*i, rate, width) for i in range(int((stop-start)/.02))]
        dip = max((min(max(levels[:i]), max(levels[i+1:])) - levels[i]
                   for i in range(1, len(levels)-1)), default=0)
        details['within_rhyme_dip_db'] = max(0., dip)
        checks['small_dong_dip'] = dip < limits['maximum_dong_dip_db']
    if variant.get('long_murmur_check'):
        reference = rms_level(pcm, a + .4, rate, width)
        late = rms_level(pcm, end - .30, rate, width) - reference
        murmur = rms_level(pcm, end - .04, rate, width) - reference
        details['late_vowel_and_murmur_relative_db'] = [late, murmur]
        checks['long_vowel_then_murmur'] = (late > -limits['long_vowel_level_margin_db']
                                          and murmur < -limits['long_murmur_drop_db'])
    return checks, details


def compare_song(config, variant, base, out, probe, execute):
    out.mkdir()
    limits = config['measurement']
    source = {**timing.read(base)['song_voice'], 'body': variant['body']}
    rate = variant.get('rate_hz', limits['output_rate_hz'])
    source['voice'] = {**source['voice'], 'output_sample_rate_hz': rate}
    score = {'id': variant['id'], 'bpm': limits['bpm'], 'start_seconds': limits['start_seconds'],
             'notes': [{'midi': midi, 'beats': beats} for midi, beats in zip(
                 variant['midi'], variant['beats'], strict=True)]}
    if 'lyrics' in variant:
        score['lyrics'] = variant['lyrics']
    else:
        score.update(syllables=variant['syllables'], dictionary=False)
    source['score'] = score
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], 'song_voice': source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    checks, plan, spans = compare_plan(config, variant, settings, upper)
    frames = settings['output_frames']
    actual, reference = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    fields = [name for name in actual.dtype.names if name != 'oral_minimum_cell']
    first, errors = voice.compare_traces(actual[fields], reference[fields], limits)
    cell_selection = (cells.compare_cell_minima(actual, reference, {**limits, 'closed_area_cm2': limits['sealed_area_cm2']})
                      if 'oral_minimum_cell' in actual.dtype.names else None)
    wav_rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(wave.shape != (frames,) or wave.dtype != np.float32 for wave in (pcm, upper_pcm)):
        raise ValueError('PCMの長さまたは型が異なります')
    diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    independent = velum.independent_velum(actual, settings, {'speech_voice': source, 'measurement': limits},
                                         rate, body_scale=limits['body_linear_scale'])
    events = []
    for label, data, wave in (('candidate', actual, pcm), ('upstream', reference, upper_pcm)):
        recorded = []
        for i, span in enumerate(spans):
            flags, detail = observe(data, wave, span, rate, variant, limits)
            checks.update({f'{label}/rhyme-{i}/{key}': bool(value) for key, value in flags.items()})
            recorded.append(detail)
        events.append(recorded)
    checks.update(
        states=first is None and (cell_selection is None or cell_selection['passed']),
        pcm=diff['first_frame_over_tolerance'] is None and rate == wav_rate and upper['output_frames'] == frames
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        independent_velum=independent['passed'],
        host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(csv) == sha256(files[0][1])
                        for w, csv in files),
    )
    summary = {'plan': plan, 'events': events, 'pcm': diff, 'frames': frames,
               'first_state_difference': first, 'state_errors': errors, 'oral_cells': cell_selection,
               'independent_velum': independent}
    if variant['id'] in limits.get('dorsal_flow_probe', {}).get('variants', []):
        event = events[0][0]['coda_flow_and_contact']
        if event['passed']:
            summary['closed_branches'] = nasal.compare_closed_branches(
                source, event, limits, out, probe, execute, section='song_voice')
            checks['zero_flow_across_seal_with_lip_motion'] = summary['closed_branches']['passed']
        else:
            checks['zero_flow_across_seal_with_lip_motion'] = False
    return checks, summary, (source, settings, actual, reference, pcm)


def measure(config, case_path, base, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'mandarin_rhymes',
             '--test', 'mandarin_ong'], cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    limits = config['measurement']
    checks, variants, rendered = {}, {}, {}
    for variant in config['song']:
        name = variant['id']
        flags, variants[name], replay = compare_song(config, variant, base, artifacts / name, probe, execute)
        checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
        if name in limits['browser_cases']:
            rendered[name] = replay
    gains = []
    for a, b in zip(variants['ban-long']['events'], variants['ban-ordinary']['events'], strict=True):
        observed, control = a[0]['port_lead_seconds'], b[0]['port_lead_seconds']
        gains.append(observed - control if observed is not None and control is not None else None)
    checks['closing_rhyme_opens_port_earlier_than_control'] = all(
        gain is not None and gain >= limits['minimum_port_lead_gain_seconds'] for gain in gains)
    report = {'checks': checks, 'variants': variants, 'port_lead_gain_seconds': gains}
    if browser:
        flags, report['browser'] = browser_song.browser_measure(
            config, rendered, artifacts, execute, bun, case_path=case_path)
        checks.update(flags)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流だけを計測する')
    parser.add_argument('--revision', type=int, choices=(1, 2), default=2, help='ケース定義の版')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = CASE if args.revision == 1 else REVISED_CASE
    config = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    base = WORKSPACE / 'cases' / config['parent_song_case']
    modules = (voice, velum, nasal, cells, frication, timing, shared, browser_song, wasm)
    sources = [case_path, base, voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in modules),
               *(WORKSPACE / 'tools' / name for name in ('upstream_baseline.py', 'measure_song_plan.py',
                                                        'measure_vowel_voice.py')),
               *(WORKSPACE / 'data' / name for name in ('mandarin.txt.gz', 'MANDARIN-PINYIN-LICENSE.txt'))]
    upper_paths = ('crates/chimera/src/phonetics/sing.rs', 'crates/chimera/src/phonetics/inventory.rs',
                   'crates/chimera/src/phonetics/mandarin.rs', 'crates/chimera/src/phonetics/vowelTargets.generated.json',
                   'crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/voice/human_voice.rs',
                   'crates/chimera/tests/mandarin_rhymes.rs', 'crates/chimera/tests/mandarin_ong.rs',
                   'public/data/mandarin.txt.gz')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {p: sha256(UPSTREAM / p) for p in upper_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [browser_song.KOREAN, browser_song.LIVE, *web_sources(),
                    WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(
        args.run_id, case_path, sources, metadata,
        lambda out, run: measure(config, case_path, base, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
