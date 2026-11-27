"""声門摩擦音の開大、枝への圧力注入とPCMを固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import periodogram

import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('h', 'h-muted', 'voiced', 'h-48k', 'h-english')
SUITES = ('lung_port', 'sound_marks', 'speech_quality')


def check_plan(settings, reference, limits):
    plan = settings['speech']
    report = {'utterances': [{'segments': row['timing']['segments']} for row in plan['phrases']]} if 'phrases' in plan else plan
    tol = limits['gesture_abs_tolerance']
    segments, evidence = speech.compare_plans({**settings, 'speech': report}, reference, tol)
    index = next(i for i, s in enumerate(segments) if s['ipa'] == limits['ipa'])
    segment = segments[index]
    following = next(s for s in segments[index+1:] if s['kind'] == 'vowel')
    gesture = next(g for g in settings['gestures'] if g['label'] == limits['ipa'])
    actual = {
        'start_offset_seconds': gesture['t0']-segment['t0'],
        'end_offset_seconds': gesture['t1']-segment['t1'],
        'opening_cm2': gesture['targets'].get('abduction_cm2'),
        'ramp_in_seconds': gesture['rampIn'],
        'ramp_out_seconds': gesture['rampOut'],
        'strength': gesture['strength'],
    }
    diff, _ = timing.compare(actual, limits['expected_abduction_gesture'], tol)
    shown = plan.get('shown')
    return segment, following, {**evidence, 'expected_gesture_difference':diff, 'observed_gesture':actual,
                                'shown':shown, 'abduction_only':list(gesture['targets'])==['abduction_cm2'],
                                'passed':evidence['passed'] and diff is None and shown==limits['expected_shown']
                                and list(gesture['targets'])==['abduction_cm2']}


def window(trace, rate, span, fraction):
    time = (trace['frame']+1)/rate
    dur = span['t1']-span['t0']
    lo, hi = [span['t0']+x*dur for x in fraction]
    return (time >= lo) & (time < hi)


def observe(trace, pcm, rate, segment, following, limits):
    center = window(trace, rate, segment, limits['center_fraction'])
    recovery = window(trace, rate, following, limits['vowel_recovery_fraction'])
    v = float(np.median(trace['glottal_voicing'][center]))
    follow = float(np.median(trace['glottal_voicing'][recovery]))
    lip = float(trace['lip_minimum_cm2'][center].min())
    flow = trace['glottal_flow_cm3_s'][center]
    level = trace['glottis_noise_level'][center]
    p = trace['glottis_noise_forward_pressure'][center]
    back = trace['glottis_noise_reverse_pressure'][center]
    rms = float(np.sqrt(np.mean(p*p)))
    active = float(np.mean(level > 0))
    enabled = limits['expected_noise_scale'] > 0
    noise_ok = (rms >= limits['min_forward_pressure_rms_dyn_cm2'] and active >= limits['minimum_active_fraction']
                if enabled else not np.any(level) and not np.any(p) and not np.any(back))
    hz, density = periodogram(pcm[center].astype('f8'), fs=rate, window='hann')
    band_lo, band_hi = limits['comparison_band_hz']
    power = float(density[(hz >= band_lo) & (hz <= band_hi)].sum()*(hz[1]-hz[0]))
    tail = float(np.max(abs(pcm[-round(rate*limits['tail_seconds']):])))
    low, high = limits['expected_center_voicing']
    branches = [np.unique(trace['glottis_noise_'+key]).astype(int).tolist() for key in ('source','forward','reverse')]
    connected = branches[0] == [-2] and all(len(b)==1 and b[0]>=0 for b in branches[1:]) and branches[1]!=branches[2]
    return {'central_voicing_median':v, 'following_vowel_voicing_median':follow,
            'central_lip_minimum_cm2':lip,'central_flow_median_cm3_s':float(np.median(flow)),
            'central_abduction_median_cm2':float(np.median(trace['abduction_cm2'][center])),
            'source_forward_reverse':branches, 'active_fraction':active, 'forward_pressure_rms_dyn_cm2':rms,
            'central_other_sources_max_level':float(max(trace[key][center].max() for key in
                ('constriction_noise_level','teeth_noise_level'))),
            'reverse_pressure_rms_dyn_cm2':float(np.sqrt(np.mean(back*back))),
            'central_band_power':power, 'tail_pcm_peak':tail,
            'passed':bool(connected and noise_ok and low<=v<=high and follow>=limits['min_recovered_voicing']
                          and lip>=limits['minimum_lip_area_cm2'] and tail<=limits['max_tail_peak_pcm'])}


def independent_control(trace, settings, case, limits):
    block = settings['control_block_internal_samples']//settings['decimation_factor']
    rate = case['voice']['output_sample_rate_hz']
    start = np.arange(0, len(trace), block)/rate
    weighted = np.zeros_like(start)
    weights = np.zeros_like(start)
    for g in settings['gestures']:
        if 'abduction_cm2' not in g['targets']:
            continue
        a, b = g['t0'], g['t1']
        attack = np.clip((start-a+g['rampIn'])/g['rampIn'], 0, 1)
        release = np.clip((start-b)/g['rampOut'], 0, 1)
        w = g['strength'] * np.where(start<a,np.sin(np.pi*attack/2)**2,np.cos(np.pi*release/2)**2)
        weights += w
        weighted += w*g['targets']['abduction_cm2']
    mixed = np.divide(weighted, weights, where=weights>0, out=np.zeros_like(weighted))
    control = .1*case['voice']['breathiness']**2 + mixed*np.minimum(1,weights/2)
    values = np.repeat(control, block)[:len(trace)]
    max_diff = float(abs(values-trace['abduction_cm2']).max())
    return {'maximum_difference_cm2':max_diff,'passed':max_diff<=limits['independent_abduction_tolerance_cm2']}


def independent_noise_level(trace, settings, case, limits):
    if settings['decimation_factor'] != 1:
        return {'measured':False,'reason':'直前の内部サンプルの枝面積と流量には出力と同じ内部レートが必要'}
    area = trace['glottis_jet_area_cm2']
    flow = trace['glottal_flow_cm3_s']
    open_ = area > .0002
    re_sq = np.zeros_like(area)
    nu = .000186/.00114
    np.divide(4*flow**2,np.pi*nu**2*area,out=re_sq,where=open_)
    excess = np.maximum(0,re_sq-1800**2)
    rate = case['internal_sample_rate_hz']
    saturated = 1+excess/(12000**2-1800**2)
    expected = 3.2e-6*limits['expected_noise_scale']*math.sqrt(96000/rate)*excess/saturated
    measured = trace['glottis_noise_level'][1:]
    delta = abs(expected[:-1] - measured)
    same_frame_delta = abs(expected[1:] - measured)
    hits = np.flatnonzero(delta>limits['independent_level_tolerance_dyn_cm2'])
    count = int(np.count_nonzero(expected[:-1]))
    return {'measured':True,'active_samples':count,'maximum_difference_dyn_cm2':float(delta.max()),
            'same_frame_maximum_difference_dyn_cm2':float(same_frame_delta.max()),
            'first_difference_frame':int(hits[0]+1) if hits.size else None,
            'passed':not hits.size and count>=limits['min_independent_active_samples']}


def pair_ablation(run, case, actual, upper, events, limits):
    prior = WORKSPACE/'runs'/run
    manifest = timing.read(prior/'manifest.json')
    original = timing.read(prior/'artifacts/source/cases/glottal-h.json')
    baseline, variant = ({**x['speech_voice']} for x in (original,case))
    variant.pop('turbulence')
    variant['input'] = {**variant['input'], 'id':baseline['input']['id']}
    if manifest['status']!='pass' or original['upstream_revision']!=case['upstream_revision'] or baseline!=variant:
        raise ValueError('倍率1の通過記録と倍率0でケースが一致しません')
    registered_inputs = {e['path']:e['sha256'] for e in manifest['inputs']}
    if any(sha256(p)!=registered_inputs.get(p.relative_to(WORKSPACE).as_posix()) for p in shared.candidate_sources()):
        raise ValueError('倍率1の実行と候補ソースが一致しません')
    outputs = {e['path']:e['sha256'] for e in manifest['outputs']}
    if sha256(prior/'summary.json')!=outputs.get('summary.json'):
        raise ValueError('倍率1の要約のハッシュが一致しません')
    prior_events = timing.read(prior/'summary.json')
    result = {}
    for prefix, trace, measurement, artifact in (
        ('candidate',actual,events[0],'voicing.csv'), ('upstream',upper,events[1],'upstream-voicing.csv')):
        path = prior/'artifacts'/artifact
        if sha256(path)!=outputs.get(f'artifacts/{artifact}'):
            raise ValueError('倍率1の観測CSVのハッシュが一致しません')
        other = voice.load_trace(path,len(trace))
        geometry = ('lip_aperture_cm','lip_minimum_cm2','noise_minimum_cm2','noise_teeth_distance_cm','abduction_cm2')
        same = all(np.array_equal(trace[key],other[key]) for key in geometry)
        p0 = measurement['central_band_power']
        p1 = prior_events[f'{prefix}_event']['central_band_power']
        db = 10*math.log10(max(p1,1e-30)/max(p0,1e-30))
        result[prefix] = {'same_geometry_and_abduction':same,'enabled_band_power':p1,'disabled_band_power':p0,
                          'enabled_band_advantage_db':db,'passed':same and db>=limits['minimum_enabled_band_advantage_db']}
    return result


def measure(path, config, artifacts, execute, prior):
    case = config['speech_voice']
    limits = config['measurement']
    settings, trace_path, files, up_path, up_pcm, up_plan = voice.capture(path,limits['host_block_frames'],artifacts,execute,SUITES)
    count = settings['output_frames']
    actual, upper = (voice.load_trace(p,count) for p in (trace_path,up_path))
    mismatches, differences = speech.source_comparison(actual,upper,limits)
    reference = timing.read(up_plan)
    segment, following, plan = check_plan(settings,reference,limits)
    wav, csv = files[0]
    rate, pcm = wavfile.read(wav)
    baseline = np.fromfile(up_pcm,dtype='<f4')
    if pcm.shape!=(count,) or baseline.shape!=(count,) or not all(np.isfinite(x).all() for x in (pcm,baseline)):
        raise ValueError('PCMのフレーム数または有限性が基準と異なります')
    errors = abs(pcm.astype('f8')-baseline)
    bad = np.flatnonzero(errors>limits['pcm_abs_tolerance'])
    events = [observe(t,p,rate,segment,following,limits) for t,p in ((actual,pcm),(upper,baseline))]
    control = [independent_control(t,settings,case,limits) for t in (actual,upper)]
    level = [independent_noise_level(t,settings,case,limits) for t in (actual,upper)]
    ablation = pair_ablation(prior,config,actual,upper,events,limits) if prior else None
    checks = {'plan':plan['passed'],'trace_and_sources':not mismatches,'pcm':not bad.size,
              'same_frame_count_and_rate':count==reference['output_frames'] and rate==case['voice']['output_sample_rate_hz'],
              'same_host_partition_output':all(sha256(w)==sha256(wav) and sha256(c)==sha256(csv) for w,c in files[1:]),
              'acoustic_event_and_voicing':all(e['passed'] for e in events),
              'independent_abduction':all(m['passed'] for m in control)}
    if settings['decimation_factor']==1:
        checks['independent_noise_level']=all(m['passed'] for m in level)
    if ablation is not None:
        checks['turbulence_ablation']=all(m['passed'] for m in ablation.values())
    return {'checks':checks,'frames':count,'plan':plan,'candidate_event':events[0],'upstream_event':events[1],
            'independent_abduction_candidate_and_upstream':control,'independent_level_candidate_and_upstream':level,
            'first_trace_differences':mismatches,'trace_error':differences,'ablation':ablation,
            'pcm_max_abs_error':float(errors.max()),'first_pcm_frame_over_tolerance':int(bad[0]) if bad.size else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition', choices=CASES)
    parser.add_argument('--enabled-run')
    args = parser.parse_args()
    if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', key) for key in (args.run_id,args.enabled_run or 'valid')):
        parser.error('実行IDは英数字で始めてください')
    if (args.condition=='h-muted') != bool(args.enabled_run):
        parser.error('倍率0の条件では --enabled-run に倍率1の実行IDを指定してください')
    path = WORKSPACE/f'cases/glottal-{args.condition}.json'
    case = timing.read(path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    tools = [Path(__file__).resolve(),voice.PROBE,Path(voice.__file__),Path(speech.__file__),Path(timing.__file__),Path(shared.__file__),WORKSPACE/'tools/upstream_baseline.py']
    sources = [path,*tools,*shared.candidate_sources()]
    upper = ['phonetics/planner.rs','phonetics/inventory.rs','voice/human_voice.rs','voice/human_airway.rs',
             'sources/glottis.rs','airway/network.rs','physics.rs']
    if args.condition=='h-english':
        sources.extend(WORKSPACE/'data'/name for name in ('cmudict.txt.gz','CMUDICT-LICENSE.txt'))
        upper.append('phonetics/english.rs')
    meta = {'upstream_revision':revision,'case_id':case['id'],'upstream_pitch_drift_jitter_shimmer':0,
            'turbulence_seed':case['measurement']['seed'],'turbulence_scale':case['measurement']['expected_noise_scale'],
            'enabled_run_id':args.enabled_run,
            'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper}}
    return shared.record_measurement(args.run_id,path,sources,meta,
                                     lambda artifacts,execute:measure(path,case,artifacts,execute,args.enabled_run),command=None)


if __name__ == '__main__':
    raise SystemExit(main())
