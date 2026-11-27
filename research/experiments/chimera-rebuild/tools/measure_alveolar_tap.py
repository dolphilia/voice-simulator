"""歯茎の弾き音の調音、接触、声門の周期、歌唱を固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import find_peaks

import measure_alveolar_stop as cells
import measure_bilabial_stop as voice
import measure_sibilant as frication
import measure_speech_timing as timing
import measure_uniform_tube as shared
import measure_velar_stops as song
import measure_wasm_fixed as wasm
from measure_worklet_fixed import ROOT, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/alveolar-tap.json'
REVISED_CASE = WORKSPACE / 'cases/alveolar-tap-v2.json'


def compare_plan(settings, upper, variant, limits, is_song):
    song_plan = settings['song'] if is_song else None
    source = settings
    if is_song:
        source = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in song_plan['plan']['phrases']]}}
    parts, comparison = frication.compare_plans(source, upper, limits['gesture_abs_tolerance'])
    spans = [part for part in parts if part['ipa'] == variant['ipa']]
    if len(spans) != 1:
        raise ValueError('対象音素を一件取得できません')
    span = spans[0]
    a, b = (span[k] for k in ('t0', 't1'))
    flags = {'upstream_plan': comparison['passed']}
    comparison['span'] = span
    if variant['ipa'] != 'ɾ':
        return flags, comparison, span

    rate = max(1, variant.get('rate', 1))
    expected = [
        {'label': 'ɾ', 't0': a - .008, 't1': max(a + .010, b), 'rampIn': .030 / rate,
         'rampOut': .018 / rate, 'strength': 40, 'releaseHold': .045 / rate, 'speed': 2.8,
         'targets': {'tongue_tip_x_cm': 6.25, 'tongue_tip_y_cm': 9.68}},
        {'label': 'ɾ', 't0': a, 't1': b, 'rampIn': .050 / rate, 'rampOut': .050 / rate, 'strength': 1.2,
         'targets': {'tongue_body_x_cm': 3.2, 'tongue_body_y_cm': 7.4}},
    ]
    if variant.get('palatalized'):
        expected.append({'label': 'palatalized', 't0': a, 't1': b,
                         'rampIn': .04 / rate, 'rampOut': .04 / rate, 'strength': 3,
                         'targets': {'tongue_body_x_cm': 3.8, 'tongue_body_y_cm': 7.95}})
    selected = [g for g in settings['gestures'] if g['label'] in ('ɾ', 'palatalized')]
    first, error = timing.compare(selected, expected, limits['gesture_abs_tolerance'])
    flags['registered_gestures_and_no_glottal_opening'] = first is None and not any(
        g['label'] in ('voiceless', 'aspiration', 'voiced frication', 'voiced affricate', 'breathy')
        and g['t0'] < b and g['t1'] > a for g in settings['gestures'])
    flags['registered_duration'] = abs(b - a - .020 / rate) <= limits['gesture_abs_tolerance']
    comparison.update(first_registered_difference=first, maximum_registered_difference=error,
                      registered_gestures=selected)
    if is_song:
        tokens = {'onsets': [[p['ipa'] for p in s['onset']] for s in song_plan['syllables']],
                  'nuclei': [s['nucleus']['ipa'] for s in song_plan['syllables']],
                  'codas': [[p['ipa'] for p in s['coda']] for s in song_plan['syllables']]}
        note = song_plan['plan']['notes'][variant['tap_note_index']]
        flags['registered_syllables_and_beat'] = tokens == {key: variant[key] for key in tokens} and all(
            abs(b - note[key]) <= limits['gesture_abs_tolerance'] for key in ('beat_seconds', 'nucleus_start_seconds'))
        comparison.update(syllables=tokens, following_beat_seconds=note['beat_seconds'])
    return flags, comparison, span


def contiguous(mask):
    hits = np.flatnonzero(mask)
    return np.split(hits, np.flatnonzero(np.diff(hits) != 1) + 1) if hits.size else []


def crossing_cycle(trace, first, last, limits):
    rate = limits['output_rate_hz']
    half = round(limits['cycle_window_padding_seconds'] * rate)
    lo = max(0, first - half)
    cycle_view = trace['glottal_area_cm2'][lo:last + half + 1]
    peaks = lo + find_peaks(cycle_view, prominence=limits['glottal_area_peak_prominence_cm2'])[0]
    for left, right in zip(peaks[:-1], peaks[1:], strict=True):
        if not left <= first <= last < right:
            continue
        ratio = (right - left) * np.mean(trace['glottal_f0_hz'][[left, right]]) / rate
        lo_ratio, hi_ratio = limits['period_to_f0_ratio']
        if lo_ratio <= ratio <= hi_ratio and trace['glottal_voicing'][[left, right]].min() >= limits['glottal_voicing_minimum']:
            return [int(left), int(right)], float(ratio)
    return None, None


def observe(trace, span, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    margin = limits['window_padding_seconds']
    window = (time >= span['t0'] - margin) & (time < span['t1'] + margin)
    area = trace['oral_minimum_cm2']
    open_lips = trace['lip_minimum_cm2'] >= limits['open_lip_minimum_cm2']
    narrowed = contiguous(window & open_lips & (area < limits['narrow_area_cm2']))
    sealed = contiguous(window & open_lips & (area < limits['closed_area_cm2']))
    result = {'ipa': span['ipa'], 'minimum_cm2': float(area[window].min()),
              'narrowing_count': len(narrowed), 'closed_count': len(sealed),
              'closed_frames': sum(len(run) for run in sealed),
              'maximum_tip_y_cm': float(trace['tongue_tip_y_cm'][window].max())}
    if not narrowed:
        return result
    run = max(narrowed, key=len)
    first, last = int(run[0]), int(run[-1])
    middle = (first + last) // 2
    pair, period_ratio = crossing_cycle(trace, middle, middle, limits)
    result.update(narrowing_frames=[first, last], narrowing_midpoint_frame=middle,
                  closed_spans=[[int(run[0]), int(run[-1])] for run in sealed],
                  cycle_across_midpoint=pair, cycle_period_to_model_ratio=period_ratio,
                  narrowing_glottal_flow_rms_cm3_s=float(np.sqrt(np.mean(trace['glottal_flow_cm3_s'][run]**2))),
                  narrowing_glottal_voicing_median=float(np.median(trace['glottal_voicing'][run])),
                  narrowing_glottal_pressure_drop_dyn_cm2=float(
                      np.median(trace['pressure_sub_dyn_cm2'][run] - trace['pressure_supra_dyn_cm2'][run])))
    if sealed and span['ipa'] == 'ɾ':
        frames = np.concatenate(sealed)
        pair, ratio = crossing_cycle(trace, int(frames[0]), int(frames[-1]), limits)
        result['cycle_enclosing_all_closed_frames'] = pair
        result['closure_cycle_to_model_ratio'] = ratio
        result['closed_glottal_flow_rms_cm3_s'] = float(np.sqrt(np.mean(trace['glottal_flow_cm3_s'][frames]**2)))
        cell = trace['oral_minimum_cell'][frames].astype(int)
        branches = np.column_stack([trace[key] for key in trace.dtype.names if key.startswith('oral_branch_')])
        interior = bool(((cell > 0) & (cell < branches.shape[1])).all())
        result['closed_cells'] = np.unique(cell).tolist()
        result['adjacent_flow_peak_cm3_s'] = (float(np.max(abs(branches[frames[:, None], np.stack((cell - 1, cell), axis=1)])))
                                               if interior else None)
    return result


def compare_variant(config, variant, base, is_song, out, probe, execute):
    out.mkdir()
    key = 'song_voice' if is_song else 'speech_voice'
    source = {**timing.read(base)[key], 'body': variant['body']}
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                           'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']]}
    else:
        before, after = config['speech_vowels']
        consonant = {'ipa': variant['ipa']}
        if variant.get('palatalized'):
            consonant['palatalized'] = True
        source['input'] = {'id': variant['id'], 'rate': variant['rate'], 'segments': [
            {'ipa': variant['vowel'], 'dur': before, 'stress': 1}, consonant,
            {'ipa': variant['vowel'], 'dur': after}]}
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    limits = config['measurement']
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    flags, plan, span = compare_plan(settings, upper, variant, limits, is_song)
    frames = settings['output_frames']
    native, reference = [voice.load_trace(p, frames) for p in (trace, upper_trace)]
    fields = [name for name in native.dtype.names if name != 'oral_minimum_cell']
    mismatches, errors = frication.source_comparison(native[fields], reference[fields], limits)
    cell_diff = cells.compare_cell_minima(
        native, reference, {**limits, 'geometry_absolute_tolerance': limits['geometry_abs_tolerance']})
    rate, pcm = wavfile.read(files[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    if any(x.shape != (frames,) or x.dtype != np.float32 for x in (pcm, upper_pcm)):
        raise ValueError('PCMの長さか型が登録条件と異なります')
    pcm_diff = wasm.compare_pcm(pcm, upper_pcm, limits['pcm_abs_tolerance'])
    events = [observe(t, span, limits) for t in (native, reference)]
    flags.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1])
                             for w, c in files),
    )
    if variant['ipa'] == 'ɾ':
        mode = variant.get('narrowing')
        if mode == 'above-threshold':
            flags['minimum_above_narrowing_threshold'] = all(
                ev['minimum_cm2'] >= limits['narrow_area_cm2'] and ev['narrowing_count'] == 0 for ev in events)
        elif mode == 'front-context':
            flags['single_narrowing_with_closure'] = all(ev['narrowing_count'] == 1 and ev['closed_count'] == 1 for ev in events)
        elif mode != 'intermediate':
            flags['one_short_narrowing'] = all(
                ev['narrowing_count'] == 1 and ev['closed_frames'] / rate <= limits['tap_maximum_closure_seconds']
                for ev in events)
        # 完全閉鎖がない場合、枝の遮断については欠測理由を保存する。
        for event in events:
            if not event['closed_count']:
                event['adjacent_flow_reason'] = '窓内に完全閉鎖がない'
        flags['no_flow_through_detected_closure'] = all(
            not event['closed_count'] or (
                event['adjacent_flow_peak_cm3_s'] is not None
                and event['adjacent_flow_peak_cm3_s'] <= limits['closed_branch_flow_abs_tolerance_cm3_s'])
            for event in events)
    if variant.get('period_across_narrowing'):
        flags['period_across_narrowing'] = all(ev.get('cycle_across_midpoint') is not None for ev in events)
    if variant.get('period_across_closure'):
        flags['period_across_full_closure'] = all(ev.get('cycle_enclosing_all_closed_frames') is not None for ev in events)
    return flags, {'plan': plan, 'first_trace_differences': mismatches, 'trace_errors': errors,
                   'oral_minimum_cells': cell_diff, 'pcm': pcm_diff, 'events': events, 'frames': frames,
                   }, (source, settings, native, reference, pcm)


def measure(config, case_path, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'syllables', '--test', 'russian'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(voice.PROBE, artifacts, execute, extra_libraries=('serde_json',))
    checks, variants, rendered = {}, {}, {}
    for kind in ('speech', 'song'):
        for variant in config[kind]:
            name = variant['id']
            flags, variants[name], replay = compare_variant(
                config, variant, bases[kind], kind == 'song', artifacts / name, probe, execute)
            checks.update({f'{name}/{key}': bool(value) for key, value in flags.items()})
            if kind == 'song':
                rendered[name] = replay
    tap, t, d = (variants[name]['events'] for name in ('tap', 'stop-t', 'stop-d'))
    checks['tap_closes_more_briefly_than_stops'] = all(
        a['closed_frames'] < min(b['closed_frames'], c['closed_frames'])
        for a, b, c in zip(tap, t, d, strict=True))
    if config['revision'] >= 2:
        medium, fast, front = (variants[name]['events'] for name in ('medium-tap', 'fast-tap', 'male-front-tap'))
        checks['intermediate_rate_area_between_endpoints'] = all(
            low['minimum_cm2'] < middle['minimum_cm2'] < high['minimum_cm2']
            for low, middle, high in zip(tap, medium, fast, strict=True))
        checks['same_body_front_vowels_close_longer'] = all(
            a['closed_frames'] < i['closed_frames'] for a, i in zip(tap, front, strict=True))
    report = {'checks': checks, 'variants': variants}
    if browser:
        flags, report['browser'] = song.browser_measure(config, rendered, artifacts, execute, bun, case_path=case_path)
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
    bases = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    sources = [case_path, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in (cells, voice, frication, timing, shared, song, wasm)),
               WORKSPACE / 'tools/upstream_baseline.py', WORKSPACE / 'tools/measure_vowel_voice.py',
               WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/ipa.rs', 'src/phonetics/inventory.rs', 'src/phonetics/planner.rs',
                      'src/phonetics/durations.rs', 'src/phonetics/korean.rs', 'src/phonetics/sing.rs',
                      'src/phonetics/consonantTargets.generated.json', 'src/control/articulators.rs',
                      'src/voice/human_voice.rs', 'src/airway/network.rs', 'tests/russian.rs', 'tests/syllables.rs')
    metadata = {'case_id': config['id'], 'revision': config['revision'], 'upstream_revision': revision,
                'upper_source_sha256': {p: sha256(UPSTREAM / 'crates/chimera' / p) for p in upstream_paths}}
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    if args.native_only:
        sources += [WORKSPACE / 'data/cmudict.txt.gz', WORKSPACE / 'data/CMUDICT-LICENSE.txt']
    else:
        sources += [song.KOREAN, song.LIVE, *web_sources(), WORKSPACE / 'tools/measure_worklet_english_body.py']
        metadata.update(node=subprocess.check_output(['node', '--version'], text=True).strip(),
                        bun=subprocess.check_output([*bun, '--version'], text=True).strip())
    return shared.record_measurement(
        args.run_id, case_path, sources, metadata,
        lambda out, run: measure(config, case_path, bases, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
