"""歯茎硬口蓋破擦音の閉鎖、乱流、声門の振動を固定上流と照合する。"""

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

CASE = WORKSPACE / 'cases/alveolopalatal-affricates.json'
SYMBOLS = ('tɕ', 'dʑ')


def expected_gestures(span, target, rate, tip_height):
    ipa = span['ipa']
    a, b = span['t0'], span['t1']
    split = a + .45 * (b - a)
    release_start = max(a, split - .015)
    oral_targets = {'tongue_tip_x_cm': 5.85, 'tongue_body_x_cm': 3.6,
                    'lip_protrusion_cm': 0, 'lip_spread': .7}
    oral = {'label': ipa, 'strength': 40, 'rampIn': .030 / rate,
            'rampOut': .018 / rate, 'releaseHold': .045 / rate}
    articulation = [
        {**oral, 't0': a - .031, 't1': max(a + .010, split - .020), 'speed': 2.0,
         'targets': {**oral_targets, 'tongue_tip_y_cm': 10, 'tongue_body_y_cm': 8.1}},
        {**oral, 't0': release_start - .008, 't1': max(release_start + .010, b), 'speed': 1.4,
         'targets': {**oral_targets, 'tongue_tip_y_cm': tip_height, 'tongue_body_y_cm': 7.75, 'jaw_cm': .3}},
    ]
    if 'aspirated' in target:
        open_start = a + .25 * (b - a)
        if target['aspirated']:
            hold, fall, opening = b + max(0, target['vot'] - .03) / rate, .045, .36
        else:
            hold, fall, opening = b + .0048, .020, .22
    else:
        open_start = split if ipa == 'dʑ' else a + .15 * (b - a)
        hold, fall, opening = max(open_start, b - .03), min(.03, b - open_start), .36
    articulation.append({
        'label': 'voiced affricate' if ipa == 'dʑ' else 'aspiration',
        't0': open_start, 't1': hold, 'strength': 6, 'rampIn': .035 / rate, 'rampOut': fall / rate,
        'targets': {'abduction_cm2': opening},
    })
    return articulation


def compare_plan(settings, upper, variant, config, is_song):
    source = settings
    if is_song:
        source = {**settings, 'speech': {'utterances': [
            {'segments': p['timing']['segments']} for p in settings['song']['plan']['phrases']]}}
    limits = config['measurement']
    parts, report = frication.compare_plans(source, upper, limits['gesture_abs_tolerance'])
    spans = [part for part in parts if part['ipa'] in SYMBOLS]
    targets = variant['targets'] if is_song else [{'ipa': variant['ipa']}]
    if [span['ipa'] for span in spans] != [target['ipa'] for target in targets]:
        raise ValueError('計画から登録済みの破擦音列を取得できません')
    rate = max(1, variant.get('rate', 1))
    expected = [g for span, target in zip(spans, targets, strict=True)
                for g in expected_gestures(span, target, rate, config['release_tip_cm'][span['ipa']][variant['body']])]
    actual = [g for g in settings['gestures'] if g['label'] in (*SYMBOLS, 'aspiration', 'voiced affricate')]
    first, error = timing.compare(actual, expected, limits['gesture_abs_tolerance'])
    flags = {'upstream_plan': report['passed'], 'registered_gestures': first is None}
    report.update(spans=spans, first_registered_difference=first, maximum_registered_difference=error,
                  registered_gestures=actual)
    if is_song:
        syllables = settings['song']['syllables']
        tokens = {'onsets': [[part['ipa'] for part in s['onset']] for s in syllables],
                  'nuclei': [s['nucleus']['ipa'] for s in syllables],
                  'codas': [[part['ipa'] for part in s['coda']] for s in syllables]}
        fields = ('ipa', 'aspirated', 'vot')
        marks = [{key: part[key] for key in fields if key in part}
                 for s in syllables for part in s['onset'] if part['ipa'] in SYMBOLS]
        flags['registered_syllables'] = tokens == {key: variant[key] for key in tokens} and marks == targets
        report.update(syllables=tokens, aspiration_marks=marks)
    return flags, report, spans


def periodic_onset(trace, time, begin, end, limits):
    search_end = int(np.searchsorted(time, end))
    peaks = begin + find_peaks(
        trace['glottal_area_cm2'][begin:search_end],
        prominence=limits['glottal_area_peak_prominence_cm2'])[0]
    low, high = limits['period_to_f0_ratio']
    rate = limits['output_rate_hz']
    for left, right in zip(peaks[:-1], peaks[1:], strict=True):
        ratio = (right - left) * np.mean(trace['glottal_f0_hz'][[left, right]]) / rate
        if low <= ratio <= high and np.min(trace['glottal_voicing'][[left, right]]) >= limits['glottal_voicing_minimum']:
            return int(left), int(right - left)
    return None, None


def observe(trace, pcm, span, limits):
    rate = limits['output_rate_hz']
    time = (trace['frame'] + 1) / rate
    a, b = span['t0'], span['t1']
    window = (time >= a - limits['closure_window_padding_seconds']) & (time < b)
    area = trace['oral_minimum_cm2']
    detected = np.flatnonzero(window & (area < limits['closed_area_cm2'])
                              & (trace['lip_minimum_cm2'] >= limits['open_lip_minimum_cm2']))
    if not len(detected):
        return {'ipa': span['ipa'], 'passed': False, 'closed_frames': 0,
                'smallest_oral_area_cm2': float(area[window].min())}
    closed = max(np.split(detected, np.flatnonzero(np.diff(detected) != 1) + 1), key=len)
    start, release = int(closed[0]), int(closed[-1]) + 1
    branches = np.column_stack([trace[key] for key in trace.dtype.names if key.startswith('oral_branch_')])
    cell = trace['oral_minimum_cell'][closed].astype(int)
    interior = bool(((cell > 0) & (cell < branches.shape[1])).all())
    flow = float(np.max(abs(branches[closed[:, None], np.stack((cell - 1, cell), axis=1)]))) if interior else None
    noise_source = limits.get('release_noise_source', 'teeth_noise')
    minimum_noise_frames = limits.get('minimum_release_noise_frames',
                                     limits.get('minimum_teeth_active_frames_after_release'))
    jet = np.flatnonzero((trace['frame'] >= release) & (time < b + limits['release_window_padding_seconds'])
                         & (trace[f'{noise_source}_level'] > 0))
    first_voiced, period = periodic_onset(
        trace, time, release, b + limits['voicing_search_padding_seconds'], limits)
    early = slice(start, min(release, start + round(rate * limits['early_closure_window_seconds'])))
    passage = pcm[release:release + round(rate * .01)]
    first_jet = int(jet[0]) if jet.size else None
    return {
        'ipa': span['ipa'], 'closure_frame': start, 'release_frame': release, 'closed_frames': len(closed),
        'closure_cells': np.unique(cell).tolist(), 'adjacent_flow_peak_cm3_s': flow,
        'release_from_split_ms': (time[release] - a - .45 * (b - a)) * 1000,
        'first_jet_frame': first_jet, 'last_jet_frame': int(jet[-1]) if jet.size else None,
        'jet_frames': len(jet), 'pulse_onset_frame': first_voiced, 'pulse_period_frames': period,
        'pulse_from_opening_ms': (first_voiced - release) * 1000 / rate if first_voiced is not None else None,
        'pulse_from_planned_end_ms': (time[first_voiced] - b) * 1000 if first_voiced is not None else None,
        'early_closure_voicing_median': float(np.median(trace['glottal_voicing'][early])),
        'release_pcm_peak': float(abs(passage).max(initial=0)),
        'passed': bool(len(closed) >= limits['minimum_closed_frames'] and area[release] >= limits['closed_area_cm2']
                       and interior and flow <= limits['closed_branch_flow_abs_tolerance_cm3_s']
                       and len(jet) >= minimum_noise_frames
                       and first_voiced is not None and first_jet < first_voiced),
    }


def compare_variant(config, variant, base, is_song, out, probe, execute):
    out.mkdir()
    key = 'song_voice' if is_song else 'speech_voice'
    limits = config['measurement']
    source = {**timing.read(base)[key], 'body': variant['body']}
    if is_song:
        source['score'] = {**source['score'], 'id': variant['id'], 'lyrics': variant['lyrics'],
                           'notes': [{'midi': midi, 'beats': 1} for midi in variant['midi']]}
    else:
        source['input'] = {key: variant[key] for key in ('id', 'text', 'segments', 'rate') if key in variant}
        source.pop('turbulence', None)
    path = out / 'case.json'
    timing.write(path, {'id': variant['id'], 'upstream_revision': config['upstream_revision'], key: source})
    settings, trace, files, upper_trace, upper_raw, upper_plan = voice.capture(
        path, limits['host_block_frames'], out, execute, (), probe=probe)
    upper = timing.read(upper_plan)
    flags, plan, spans = compare_plan(settings, upper, variant, config, is_song)
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
    events = [[observe(t, p, span, limits) for span in spans] for t, p in ((native, pcm), (reference, upper_pcm))]
    flags.update(
        trace=not mismatches and cell_diff['passed'],
        pcm=pcm_diff['first_frame_over_tolerance'] is None,
        sample_rates_and_frames=rate == limits['output_rate_hz'] and frames == upper['output_frames']
        and source['internal_sample_rate_hz'] == limits['internal_rate_hz'],
        same_host_blocks=all(sha256(w) == sha256(files[0][0]) and sha256(c) == sha256(files[0][1])
                             for w, c in files),
    )
    if not variant.get('short_control'):
        flags['closed_then_frication_then_periodic'] = all(event['passed'] for row in events for event in row)
    return flags, {
        'plan': plan, 'first_trace_differences': mismatches, 'trace_errors': errors, 'oral_minimum_cells': cell_diff,
        'pcm': pcm_diff, 'events': events, 'frames': frames,
    }, (source, settings, native, reference, pcm)


def measure(config, bases, artifacts, execute, bun, browser):
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'affricates', '--test', 'syllables'],
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
    vcv = [variants[name]['events'] for name in ('ipa-tsh', 'ipa-dzh')]
    delta = [b[0]['early_closure_voicing_median'] - a[0]['early_closure_voicing_median']
             if a[0]['closed_frames'] and b[0]['closed_frames'] else None for a, b in zip(*vcv, strict=True)]
    checks['voiced_closure_retains_voicing'] = all(d is not None and d > 0 for d in delta)
    report = {'checks': checks, 'variants': variants, 'vcv_voiced_minus_voiceless_early_voicing': delta}
    if browser:
        flags, report['browser'] = song.browser_measure(config, rendered, artifacts, execute, bun, case_path=CASE)
        checks.update(flags)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--native-only', action='store_true', help='CLIと固定上流だけを計測する')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    config = timing.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    bases = {kind: WORKSPACE / 'cases' / config[kind + '_case'] for kind in ('speech', 'song')}
    sources = [CASE, *bases.values(), voice.PROBE, Path(__file__).resolve(), *shared.candidate_sources(),
               *(Path(module.__file__) for module in (cells, voice, frication, timing, shared, song, wasm)),
               WORKSPACE / 'tools/upstream_baseline.py', WORKSPACE / 'tools/measure_vowel_voice.py',
               WORKSPACE / 'tools/measure_song_plan.py']
    upstream_paths = ('src/phonetics/ipa.rs', 'src/phonetics/inventory.rs', 'src/phonetics/planner.rs',
                      'src/phonetics/korean.rs', 'src/phonetics/sing.rs', 'src/phonetics/consonantTargets.generated.json',
                      'src/voice/human_airway.rs', 'src/airway/network.rs', 'tests/affricates.rs', 'tests/syllables.rs')
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
        args.run_id, CASE, sources, metadata,
        lambda out, run: measure(config, bases, out, run, bun, not args.native_only), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
