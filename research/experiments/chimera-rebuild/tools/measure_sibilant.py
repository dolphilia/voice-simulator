"""歯茎摩擦音を、乱流源の選択、圧力注入、波形と帯域で照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import lfilter, periodogram

import measure_bilabial_stop as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('s', 'z', 's-muted')


def compare_plans(actual, reference, tolerance):
    segments = [part for row in actual['speech']['utterances'] for part in row['segments']]
    candidate = []
    for part in segments:
        symbol = {'ipa': part['segment']['ipa'], 't0': part['start_seconds'],
                  't1': part['end_seconds'], 'kind': part['manner'] or '?'}
        if symbol['kind'] == 'vowel':
            symbol['stress'] = part['segment'].get('stress', 0)
        candidate.append(symbol)
    upper_segments = [s for plan in reference['plans'] for s in plan['segments']]
    upper_gestures = [{**g, 'targets': {speech.KEYS[k]: v for k, v in g['targets'].items()}}
                      for plan in reference['plans'] for g in plan['gestures']]
    g_diff, g_err = timing.compare(actual['gestures'], upper_gestures, tolerance)
    s_diff, _ = timing.compare(candidate, upper_segments, tolerance)
    return candidate, {
        'first_gesture_difference': g_diff, 'maximum_checked_gesture_difference': g_err,
        'first_segment_difference': s_diff, 'passed': not (g_diff or s_diff),
    }


def plan_report(config, actual, reference):
    expected = config['measurement']['expected']
    tol = config['measurement']['gesture_abs_tolerance']
    candidate, report = compare_plans(actual, reference, tol)
    symbol = expected['ipa']
    frication = next(s for s in candidate if s['ipa'] == symbol)
    g_tip = next(g for g in actual['gestures'] if g.get('label') == symbol and 'tongue_tip_y_cm' in g['targets'])
    g_source = next(g for g in actual['gestures'] if g.get('label') in ('voiceless', 'voiced frication'))
    prediction, _ = timing.compare({
        'ipa': symbol, 'tip_y_cm': g_tip['targets']['tongue_tip_y_cm'],
        'abduction_add_cm2': g_source['targets']['abduction_cm2'],
    }, expected, tol)
    return candidate[0], frication, {
        **report, 'registered_difference': prediction,
        'passed': report['passed'] and prediction is None,
    }


def source_comparison(actual, reference, limits):
    if actual.dtype.names != reference.dtype.names:
        raise ValueError('候補と上流で観測列が一致しません')
    abs_tol = limits['selection_abs_tolerance']
    geometry = {'lip_aperture_cm', 'lip_minimum_cm2', 'lip_area_cm2', 'noise_minimum_cm2',
                'noise_teeth_distance_cm', 'noise_jet_area_cm2', 'glottis_jet_area_cm2', 'velum_position_cm2',
                'velum_effective_cm2', 'velum_port_area_cm2', 'oral_min_cell_area_cm2'}
    mismatches = []
    peaks = {}
    for field in actual.dtype.names[1:]:
        delta = np.abs(actual[field] - reference[field])
        peak = max(float(np.max(np.abs(reference[field]))), 1e-6)
        if field == 'noise_cell' or field.endswith(('_source', '_forward', '_reverse')):
            cutoff = 0.0
        elif field in geometry:
            cutoff = limits['geometry_abs_tolerance']
        elif field.endswith(('_lowpass_hz', '_gain')):
            cutoff = abs_tol
        else:
            cutoff = peak * limits['state_peak_relative_tolerance']
        hits = np.flatnonzero(delta > cutoff)
        if hits.size:
            first = int(hits[0])
            mismatches.append({'frame': first, 'field': field,
                               'candidate': float(actual[field][first]),
                               'upstream': float(reference[field][first]), 'allowance': cutoff})
        peaks[field] = {'absolute': float(delta.max()), 'relative_to_upstream_peak': float(delta.max())/peak}
    return sorted(mismatches, key=lambda x: x['frame']), peaks


def independent_band(trace, tolerance, *, body_scale=1.0, lowpass_floor_hz=0.0):
    teeth = trace['teeth_noise_source'] >= 0
    if not teeth.any():
        return {'registered_frames': 0, 'passed': False}
    a = np.maximum(trace['noise_jet_area_cm2'][teeth], 1e-6)
    distance = trace['noise_teeth_distance_cm'][teeth]
    area = trace['noise_minimum_cm2'][teeth]
    diameter = np.sqrt(4 * a / np.pi)
    eddy = np.maximum(diameter, .17 * distance)
    upper_cutoff = np.abs(trace['noise_jet_flow_cm3_s'][teeth]) * diameter / (a * eddy**2)

    def transition(x, left, right):
        u = np.clip((x-left)/(right-left), 0, 1)
        return 3*u**2 - 2*u**3

    reference_distance = distance / body_scale
    reference_area = area / body_scale**2
    geometric_weight = (transition(reference_distance, 1, 1.5)
                        * (1-transition(reference_distance, 2.6, 4.0))
                        * (1-transition(reference_area, .2, .5)))
    gain = 3e-6 * geometric_weight * np.sqrt(5000/np.maximum(upper_cutoff, 1200))
    effective_cutoff = np.maximum(upper_cutoff, lowpass_floor_hz)
    band_delta = float(np.max(np.abs(effective_cutoff - trace['teeth_noise_lowpass_hz'][teeth])))
    gain_delta = float(np.max(np.abs(gain - trace['teeth_noise_gain'][teeth])))
    return {
        'registered_frames': int(teeth.sum()), 'cutoff_max_error_hz': band_delta,
        'gain_max_error': gain_delta, 'passed': band_delta <= tolerance and gain_delta <= tolerance,
    }


def event_metrics(trace, pcm, rate, vowel, segment, limits, scale):
    total = segment['t1']-segment['t0']
    fa, fb = limits['center_fraction']
    ta, tb = segment['t0'] + fa*total, segment['t0'] + fb*total
    times = np.arange(len(pcm))/rate
    center = (times >= ta) & (times < tb)
    consonant = (times >= segment['t0']) & (times < segment['t1'])
    voice = (times >= vowel['t0']+.03) & (times < vowel['t1']-.03)
    center_count = int(center.sum())
    if not center_count or not voice.any():
        raise ValueError('摩擦音と先行する強勢母音の測定窓にサンプルがありません')
    level = trace['teeth_noise_level']
    active = center & (level > 0)
    active_count = int(active.sum())
    reference = center & (trace['teeth_noise_source'] >= 0)
    fractions = active_count / center_count, int(reference.sum()) / center_count
    if not reference.any():
        return {'passed': False, 'reason': '歯を選ぶ条件が中央窓にありません'}

    narrow = float(np.median(trace['noise_minimum_cm2'][reference]))
    distance = trace['noise_teeth_distance_cm'][reference]
    frequency = trace['teeth_noise_lowpass_hz'][reference]
    fwd_pressure = trace['teeth_noise_forward_pressure'][center]
    sm = 1-math.exp(-2*math.pi*limits['low_band_cutoff_hz']/rate)
    low = lfilter([sm], [1,-(1-sm)], lfilter([sm], [1,-(1-sm)], pcm.astype('f8')))
    relative_lo = 10*math.log10((1e-20 + np.mean(low[center]**2))/(1e-20 + np.mean(low[voice]**2)))
    hz, density = periodogram(pcm[center].astype('f8'), fs=rate, window='hann')
    lo, hi = limits['high_band_interval_hz']
    high = float(density[(hz>=lo)&(hz<=hi)].sum()*(hz[1]-hz[0]))
    active_frames = np.flatnonzero(consonant & (level > 0))
    quiet = all(not trace[name].any() for name in trace.dtype.names
                if name.endswith(('_level', '_forward_pressure', '_reverse_pressure')))
    z_limit = limits['z_low_band_relative_max_db']
    return {
        'center_seconds': [ta,tb],
        'center_teeth_active_and_registered_fraction': list(fractions),
        'first_last_active_frame_within_segment': ([int(active_frames[0]),int(active_frames[-1])]
                                                    if active_frames.size else []),
        'median_minimum_cm2': narrow,
        'teeth_distance_min_max_cm': [float(distance.min()),float(distance.max())],
        'teeth_cutoff_min_max_hz': [float(frequency.min()),float(frequency.max())],
        'median_glottal_voicing': float(np.median(trace['glottal_voicing'][center])),
        'teeth_forward_pressure_rms_dyn_cm2': float(np.sqrt(np.mean(fwd_pressure**2))),
        'low_band_relative_to_vowel_db': relative_lo, 'high_band_power': high,
        'passed': bool(limits['central_narrowing_interval_cm2'][0] <= narrow <= limits['central_narrowing_interval_cm2'][1]
                       and distance.min() >= limits['teeth_distance_interval_cm'][0]
                       and distance.max() <= limits['teeth_distance_interval_cm'][1]
                       and (fractions[0] >= limits['minimum_teeth_active_fraction'] if scale else quiet)
                       and (z_limit is None or relative_lo <= z_limit)),
    }


def measure(case_path, config, artifacts, execute, enabled):
    limits = config['measurement']
    settings, trace_path, files, upper_trace_path, upper_pcm_path, upper_plan = speech.capture(
        case_path, limits['host_block_frames'], artifacts, execute, ('voiced_fricatives', 'lung_port'),
    )
    count = settings['output_frames']
    actual = speech.load_trace(trace_path,count)
    reference = speech.load_trace(upper_trace_path,count)
    mismatches, differences = source_comparison(actual,reference,limits)
    up = timing.read(upper_plan)
    vowel, segment, plan = plan_report(config,settings,up)
    wave,csv = files[0]
    rate, pcm = wavfile.read(wave)
    upper_pcm = np.fromfile(upper_pcm_path,dtype='<f4')
    if len(pcm) != count or pcm.shape != upper_pcm.shape or not all(np.isfinite(w).all() for w in (pcm,upper_pcm)):
        raise ValueError('PCMの長さまたは有限性が基準と異なります')
    delta = np.abs(pcm.astype('f8')-upper_pcm)
    outliers = np.flatnonzero(delta > limits['pcm_abs_tolerance'])
    band = independent_band(actual,limits['selection_abs_tolerance'])
    scale = config['speech_voice']['turbulence']['scale']
    candidate_event, reference_event = (event_metrics(t,p,rate,vowel,segment,limits,scale)
                                         for t,p in ((actual,pcm),(reference,upper_pcm)))
    result = {
        'checks': {
            'planned_ipa_and_gestures': plan['passed'],
            'output_frames': count == up['output_frames'] and rate == config['speech_voice']['voice']['output_sample_rate_hz'],
            'geometry_sources_and_acoustic_trace': not mismatches,
            'pcm': not outliers.size,
            'same_host_partition_output': all(sha256(w)==sha256(wave) and sha256(c)==sha256(csv) for w,c in files[1:]),
            'teeth_band_independent_expression': band['passed'],
            'expected_event': candidate_event['passed'] and reference_event['passed'],
        },
        'frames':count,'plan':plan,'pcm_max_error':float(delta.max()),
        'first_pcm_frame_over_tolerance':int(outliers[0]) if outliers.size else None,
        'first_trace_differences':mismatches,'trace_error':differences,
        'independent_teeth_band':band,'candidate_event':candidate_event,'upstream_event':reference_event,
    }

    if enabled:
        summary, trace = enabled
        prior = timing.read(summary)
        prior_trace = speech.load_trace(trace,count)
        geometric_fields = ('lip_aperture_cm','lip_minimum_cm2','noise_cell',
                            'noise_minimum_cm2','noise_teeth_distance_cm')
        same_geometry = all(np.array_equal(prior_trace[name],actual[name]) for name in geometric_fields)
        power_enabled = prior['candidate_event']['high_band_power']
        power_muted = candidate_event['high_band_power']
        result['ablation'] = {
            'geometry_byte_values_equal': same_geometry,
            'high_band_power_enabled': power_enabled, 'high_band_power_muted': power_muted,
            'high_band_delta_db': 10*math.log10(max(power_enabled,1e-30)/max(power_muted,1e-30)),
        }
        result['checks']['turbulence_increases_high_band_at_same_geometry'] = same_geometry and power_enabled > power_muted
    return result


def enabled_comparison(run_id, current, sources):
    directory = WORKSPACE/'runs'/run_id
    manifest = directory/'manifest.json'
    data = timing.read(manifest)
    if data['status'] != 'pass' or data['case_id'] != 'sibilant-s' or data['upstream_revision'] != current['upstream_revision']:
        raise ValueError('同じ上流版で通過した乱流あり /s/ の実行が必要です')
    revision = {entry['path']:entry['sha256'] for entry in data['inputs']}
    if any(revision.get(str(p.relative_to(WORKSPACE))) != sha256(p) for p in sources):
        raise ValueError('乱流あり・なしの比較には同じ候補ソースが必要です')
    outputs = {entry['path']:entry['sha256'] for entry in data['outputs']}
    names = ('summary.json','artifacts/voicing.csv','artifacts/settings.json')
    files = tuple(directory/name for name in names)
    if any(sha256(p) != outputs[name] for p,name in zip(files,names,strict=True)):
        raise ValueError('保存済みの乱流ありの観測結果とハッシュが一致しません')
    control = timing.read(files[2])['case']['speech_voice']
    treatment = current['speech_voice']
    def comparable(value):
        source = {**value['input']}
        del source['id']
        return {**value,'input':source,'turbulence':{}}
    if control['turbulence']['scale'] <= 0 or treatment['turbulence']['scale'] != 0 or comparable(control) != comparable(treatment):
        raise ValueError('発話・調音・音声設定をそろえ、乱流倍率だけを変えてください')
    return (manifest,*files)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition',choices=CASES)
    parser.add_argument('--enabled-run', help='乱流倍率0の条件と比較する s の通過済み実行')
    args=parser.parse_args()
    if args.enabled_run and (args.condition != 's-muted' or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.enabled_run)):
        parser.error('--enabled-run は s-muted の条件で有効な実行IDを指定してください')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始めてください')
    path=WORKSPACE/f'cases/sibilant-{args.condition}.json'
    config=timing.read(path)
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    candidate_sources = shared.candidate_sources()
    sources=[path,speech.PROBE,Path(__file__).resolve(),Path(shared.__file__),Path(timing.__file__),
             Path(speech.__file__), WORKSPACE/'tools/upstream_baseline.py',*candidate_sources]
    enabled = None
    if args.enabled_run:
        manifest, summary, trace, settings = enabled_comparison(args.enabled_run,config,candidate_sources)
        sources.extend((manifest,summary,trace,settings))
        enabled = (summary,trace)
    upper=['phonetics/planner.rs','phonetics/inventory.rs','phonetics/consonantTargets.generated.json',
           'voice/human_voice.rs','voice/human_airway.rs','airway/network.rs']
    metadata={'upstream_revision':revision,'case_id':config['id'],'noise_seed':config['measurement']['seed'],
              'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper}}
    if args.enabled_run:
        metadata['enabled_run_id']=args.enabled_run
    return shared.record_measurement(args.run_id,path,sources,metadata,
                                     lambda artifacts,execute:measure(path,config,artifacts,execute,enabled),command=None)


if __name__ == '__main__':
    raise SystemExit(main())
