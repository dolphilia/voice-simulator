"""歯茎破裂音のスコア、舌先閉鎖、声門とPCMを固定上流と照合する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('d', 't', 't-fast', 't-placed', 'd-english')
SUITES = ('fast_speech', 'aspiration', 'speech_quality', 'consonant_artifacts')


def compare_plans(settings, reference, limits):
    plan = settings['speech']
    if 'phrases' in plan:
        plan = {'utterances': [{'segments': row['timing']['segments']} for row in plan['phrases']]}
    tolerance = limits['gesture_absolute_tolerance']
    segments, evidence = speech.compare_plans({**settings, 'speech': plan}, reference, tolerance)
    symbol = limits['stop']
    stops = [s for s in segments if s['ipa'] == symbol]
    gestures = settings['gestures']
    primary = [g for g in gestures if g['label'] == symbol and 'tongue_tip_y_cm' in g['targets']]
    secondary = [g for g in gestures if g['label'] == symbol and 'tongue_body_y_cm' in g['targets']]
    aspiration = [g for g in gestures if g['label'] == 'aspiration']
    if not len(stops) == len(primary) == len(secondary) == len(limits['closure_delays_seconds']):
        return segments, stops, {**evidence, 'passed': False, 'reason': '対象音素と計画の個数が異なります'}
    rate = max(1.0, settings['case']['speech_voice']['input']['rate'])
    actual, expected = [], []
    for stop, a, b, delay in zip(stops, primary, secondary, limits['closure_delays_seconds'], strict=True):
        t0, t1 = stop['t0'], stop['t1']
        duration = t1-t0
        aim = t0+min(delay, max(0., duration-.03))
        asp = next((g for g in aspiration if abs(g['t0']-t0-.25*duration) <= tolerance), None)
        actual.append({'tip':{k:a[k] for k in ('t0','t1','rampIn','rampOut','releaseHold','speed','strength','targets')},
                       'body':{k:b[k] for k in ('t0','t1','rampIn','rampOut','strength','targets')},
                       'aspiration_cm2':asp['targets']['abduction_cm2'] if asp else None})
        expected.append({
            'tip':{'t0':aim-.031, 't1':max(aim+.010, t1-.020), 'rampIn':.030/rate,
                   'rampOut':.018/rate, 'releaseHold':.045/rate, 'speed':1.55, 'strength':40.,
                   'targets':{'tongue_tip_x_cm':6.25, 'tongue_tip_y_cm':9.68}},
            'body':{'t0':aim, 't1':t1, 'rampIn':.050/rate, 'rampOut':.050/rate, 'strength':1.2,
                    'targets':{'tongue_body_x_cm':3.2, 'tongue_body_y_cm':7.4}},
            'aspiration_cm2':limits['aspiration_cm2'],
        })
    difference, error = timing.compare(actual, expected, tolerance)
    shown = settings['speech'].get('shown')
    return segments, stops, {**evidence, 'registered_difference':difference, 'registered_max_error':error,
                             'observed':actual, 'shown':shown,
                             'passed':evidence['passed'] and difference is None and shown==limits.get('expected_shown')}


def observe(trace, pcm, segments, stops, rate, limits):
    time = (trace['frame']+1)/rate
    area = trace['oral_minimum_cm2']
    lip = trace['lip_minimum_cm2']
    midpoints = [(s['t0']+s['t1'])/2 for s in stops]
    peaks = limits.get('minimum_release_pcm_per_stop', [limits['minimum_recovery_pcm_peak']]*len(stops))
    events = []
    for i, (stop, midpoint, peak) in enumerate(zip(stops, midpoints, peaks, strict=True)):
        margin = limits['closure_search_before_and_after_seconds']
        start, end = stop['t0']-margin, stop['t1']+margin
        if i > 0:
            start = max(start, (midpoints[i-1]+midpoint)/2)
        if i+1 < len(stops):
            end = min(end, (midpoint+midpoints[i+1])/2)
        window = (time >= start) & (time < end) & (lip >= limits['minimum_lip_area_at_closure_cm2'])
        minimum = float(area[window].min(initial=np.inf))
        eligible = np.flatnonzero(window & (area < limits['closed_area_cm2']))
        unsealed = limits.get('unsealed_stops', {}).get(str(i))
        if not eligible.size:
            events.append({'closed_frames':0, 'measured_minimum_cm2':minimum if np.isfinite(minimum) else None,
                           'passed':unsealed is not None and minimum <= unsealed})
            continue
        parts = np.split(eligible, np.flatnonzero(np.diff(eligible) != 1)+1)
        closed = max(parts, key=len)
        left, right = int(closed[0]), int(closed[-1]+1)
        middle = (left+right)//2
        size = round(rate*limits['recovery_window_seconds'])
        pcm_peak = float(abs(pcm[right:right+size]).max(initial=0))
        cell = int(trace['oral_minimum_cell'][middle])
        burst = pcm[right:right+min(size, round(rate*.005))]
        peak_frame = right + int(np.argmax(abs(burst))) if burst.size else None
        events.append({
            'first_closed_frame':left, 'first_open_frame':right, 'closed_frames':right-left,
            'closure_offset_from_start_ms':1000*float(time[left]-stop['t0']),
            'opening_offset_from_end_ms':1000*float(right/rate+1/rate-stop['t1']) if right < len(time) else None,
            'central_minimum_cell':cell, 'central_lip_area_cm2':float(lip[middle]),
            'central_abduction_cm2':float(trace['abduction_cm2'][middle]),
            'recovery_peak_pcm':pcm_peak, 'peak_frame_first_5ms':peak_frame,
            'passed':unsealed is None and right < len(area) and bool(
                area[right] >= limits['closed_area_cm2'] and len(closed) >= limits['minimum_closed_frames']
                and lip[middle] >= limits['minimum_lip_area_at_closure_cm2']
                and (peak is None or pcm_peak >= peak)),
        })
    tail = float(abs(pcm[-round(rate*limits['silence_window_seconds']):]).max())
    inner_vowels = [s for s in segments if s['kind']=='vowel' and any(p['t1']<=s['t0'] for p in stops)
                    and any(n['t0']>=s['t1'] for n in stops)]
    vowel_peaks = [float(area[(time>=v['t0']) & (time<v['t1'])].max()) for v in inner_vowels]
    expected_peak = limits.get('intervening_vowel_minimum_peak_cm2')
    return {'closures':events,'tail_pcm_peak':tail,'intervening_vowel_peaks_cm2':vowel_peaks,
            'passed':all(e['passed'] for e in events) and tail<=limits['maximum_tail_pcm_peak']
            and (expected_peak is None or bool(vowel_peaks and min(vowel_peaks)>=expected_peak))}


def compare_cell_minima(candidate, upper, limits):
    fields = [name for name in candidate.dtype.names if name.startswith('oral_cell_')]
    values = [np.column_stack([trace[name] for name in fields]) for trace in (candidate,upper)]
    idx = [trace['oral_minimum_cell'].astype(int) for trace in (candidate,upper)]
    toler = limits['geometry_absolute_tolerance']
    paired = np.arange(len(candidate))
    if any((i<0).any() or (i>=len(fields)).any() for i in idx):
        raise ValueError('最小断面のセル番号が範囲外です')
    a,b = values
    a_idx,b_idx = idx
    each_min = [matrix.min(axis=1) for matrix in values]
    checks = [np.array_equal(matrix[paired, i], minimum) and np.array_equal(trace['oral_minimum_cm2'], minimum)
              for matrix,i,minimum,trace in zip(values,idx,each_min,(candidate,upper),strict=True)]
    # 同率に近いセルについても、相手が選んだセルの実面積で確認する。
    gap = np.maximum(a[paired,b_idx]-each_min[0], b[paired,a_idx]-each_min[1])
    changed = np.flatnonzero(a_idx != b_idx)
    closed = limits['closed_area_cm2']
    first = int(changed[0]) if changed.size else None
    return {
        'first_distinct_cell_frame': first,
        'different_selected_cells': int(changed.size),
        'other_selected_cell_max_excess_cm2': float(gap.max()),
        'first_distinct_cell_areas': [{str(i):float(m[first,i]) for i in sorted({a_idx[first],b_idx[first]})}
                                     for m in values] if first is not None else [],
        'per_cell_closed_equal': bool(np.array_equal(a<closed,b<closed)),
        'passed':all(checks) and bool((gap<=toler).all() and np.array_equal(a<closed,b<closed)),
    }


def measure(path, config, artifacts, execute):
    limits = config['measurement']
    settings, trace_path, files, upper_path, upper_pcm, ref = voice.capture(
        path, limits['host_block_frames'], artifacts, execute, SUITES)
    reference = timing.read(ref)
    segments, stops, plan = compare_plans(settings, reference, limits)
    frames = settings['output_frames']
    actual, upper = voice.load_trace(trace_path, frames), voice.load_trace(upper_path, frames)
    physical_fields = [name for name in actual.dtype.names if name != 'oral_minimum_cell']
    first, errors = voice.compare_traces(actual[physical_fields], upper[physical_fields], limits)
    cells = compare_cell_minima(actual, upper, limits)
    wav, output_csv = files[0]
    rate, pcm = wavfile.read(wav)
    baseline = np.fromfile(upper_pcm, dtype='<f4')
    if pcm.shape != (frames,) or baseline.shape != (frames,) or not all(np.isfinite(a).all() for a in (pcm, baseline)):
        raise ValueError('PCMのフレーム数または有限性が基準と異なります')
    delta = abs(pcm.astype('f8')-baseline)
    over = np.flatnonzero(delta > limits['pcm_absolute_tolerance'])
    candidate, upstream = (observe(t, p, segments, stops, rate, limits) for t, p in ((actual,pcm),(upper,baseline)))
    matched = all(all(a.get(k)==b.get(k) for k in ('first_closed_frame','first_open_frame','peak_frame_first_5ms'))
                  for a,b in zip(candidate['closures'],upstream['closures'],strict=True))
    return {
        'checks':{'plans':plan['passed'],'frame_count_and_rate':frames==reference['output_frames']
                  and rate==config['speech_voice']['voice']['output_sample_rate_hz'],
                  'trace':first is None,'closed_cells_and_minima':cells['passed'],'pcm':not over.size,'measured_closures':candidate['passed'] and upstream['passed'],
                  'same_event_frames':matched,'host_partition_byte_agreement':
                  all(sha256(w)==sha256(wav) and sha256(c)==sha256(output_csv) for w,c in files[1:])},
        'frames':frames,'plan':plan,'first_trace_difference':first,'trace_errors':errors,'oral_cells':cells,
        'pcm_first_frame_over_tolerance':int(over[0]) if over.size else None,'pcm_max_abs_error':float(delta.max()),
        'candidate_events':candidate,'upstream_events':upstream,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition', choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始めてください')
    path = WORKSPACE/f'cases/alveolar-{args.condition}.json'
    case = timing.read(path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    sources = [path,Path(__file__).resolve(),voice.PROBE,Path(voice.__file__),Path(speech.__file__),Path(timing.__file__),
               Path(shared.__file__),WORKSPACE/'tools/upstream_baseline.py',*shared.candidate_sources()]
    upper_names = ['phonetics/planner.rs','phonetics/inventory.rs','phonetics/consonantTargets.generated.json',
                   'voice/human_voice.rs','anatomy/human.rs','airway/network.rs']
    if case['speech_voice'].get('language') == 'english':
        sources.extend(WORKSPACE/'data'/name for name in ('cmudict.txt.gz','CMUDICT-LICENSE.txt'))
        upper_names.append('phonetics/english.rs')
    metadata = {'upstream_revision':revision,'case_id':case['id'],'upstream_noise_scale':0.,
                'upstream_pitch_drift_jitter_shimmer':0.,
                'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper_names}}
    return shared.record_measurement(args.run_id,path,sources,metadata,
                                     lambda artifacts,execute:measure(path,case,artifacts,execute),command=None)


if __name__ == '__main__':
    raise SystemExit(main())
