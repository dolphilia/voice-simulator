"""側方通路を制御する音素・口腔断面・流量・波形を固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_alveolar_stop as alveolar
import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('l', 'l-closed', 'dark', 'dark-closed', 'l-palatalized', 'hello')
SUITES = ('geometry_continuity', 'speech_quality', 'golden_phonetics_text', 'sound_marks')
AXES_WITHOUT_LATERAL = ('lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread', 'tongue_tip_x_cm',
                         'tongue_tip_y_cm', 'tongue_body_x_cm', 'tongue_body_y_cm')


def plans(settings, reference, limits):
    score = settings['speech']
    report = score
    if 'phrases' in score:
        report = {'utterances': [{'segments': p['timing']['segments']} for p in score['phrases']]}
    tolerance = limits['gesture_absolute_tolerance']
    segments, evidence = speech.compare_plans({**settings, 'speech': report}, reference, tolerance)
    laterals = [s for s in segments if s['ipa'] in ('l', 'ɫ')]
    rate = max(1, settings['case']['speech_voice']['input']['rate'])
    expected = []
    for segment in laterals:
        ipa = segment['ipa']
        start, end = segment['t0'], segment['t1']
        targets = {'tongue_tip_x_cm':6.25, 'tongue_tip_y_cm':9.68, 'lateral':limits['lateral_opening_scale']}
        if ipa == 'ɫ':
            targets.update(tongue_body_x_cm=1.9, tongue_body_y_cm=6.8)
        expected.append({'label':ipa, 't0':start-.008, 't1':max(start+.010,end),
                         'strength':40, 'speed':1.3, 'rampIn':.030/rate, 'rampOut':.018/rate,
                         'releaseHold':.045/rate, 'targets':targets})
    actual = [g for g in settings['gestures'] if g['label'] in ('l','ɫ')]
    palatal = [g for g in settings['gestures'] if g['label']=='palatalized']
    predicted_palatal = []
    if limits['expected_palatalized']:
        predicted_palatal = [{'label':'palatalized', 't0':laterals[0]['t0'], 't1':laterals[0]['t1'],
                              'strength':3, 'rampIn':.04/rate, 'rampOut':.04/rate,
                              'targets':{'tongue_body_x_cm':3.8,'tongue_body_y_cm':7.95}}]
    diff, _ = timing.compare(actual+palatal, expected+predicted_palatal, tolerance)
    shown = score.get('shown')
    available = score.get('unavailable_speech_symbols', [])
    return laterals, {**evidence, 'expected_gestures_difference':diff, 'shown':shown,
                      'unavailable_speech_symbols':available,'lateral_segments':laterals,
                      'passed':evidence['passed'] and diff is None and shown==limits['expected_shown']
                      and not available and [s['ipa'] for s in laterals]==limits['symbols']}


def independent_lateral(trace, settings, case, limits):
    stride = settings['control_block_internal_samples']//settings['decimation_factor']
    rate = case['voice']['output_sample_rate_hz']
    dt = stride/rate
    clock = np.arange(0,len(trace),stride)/rate
    base = case['posture'].get('lateral',0)*limits['lateral_opening_scale']
    weights, weighted, speeds = np.zeros_like(clock), np.zeros_like(clock), np.ones_like(clock)
    for g in settings['gestures']:
        if 'lateral' not in g['targets']:
            continue
        start,end = g['t0'],g['t1']
        ri,ro = g['rampIn'],g['rampOut']
        rise = np.sin(.5*np.pi*np.clip((clock-start+ri)/ri,0,1))**2
        fall = np.cos(.5*np.pi*np.clip((clock-end)/ro,0,1))**2
        w = np.where(clock<start,rise,np.where(clock<end+ro,fall,0))*g['strength']
        weights += w
        weighted += w*g['targets']['lateral']
        keep = (clock>=start-ri) & (clock<=end+ro+g.get('releaseHold',0))
        speeds[keep] = np.maximum(speeds[keep],g.get('speed',1))
    target = (.05*base+weighted)/(.05+weights)
    omega = 2*math.pi*10*np.where(weights>0,speeds,1)
    position, velocity = base, 0.
    positions = np.empty_like(clock)
    for i,(t,w) in enumerate(zip(target,omega,strict=True)):
        velocity += dt*(w*w*(t-position)-2*w*velocity)
        position += dt*velocity
        positions[i] = position
    fields = ('lateral_position','lateral_effective')
    errors = {name:float(abs(np.repeat(value,stride)[:len(trace)]-trace[name]).max())
              for name,value in zip(fields,(positions,target),strict=True)}
    return {'maximum_errors':errors,'passed':max(errors.values())<=limits['spring_position_tolerance']}


def measure_events(trace, pcm, laterals, rate, limits):
    time = (trace['frame']+1)/rate
    windows = []
    enabled = limits['lateral_opening_scale'] > 0
    for segment in laterals:
        start,end = (segment['t0']+p*(segment['t1']-segment['t0']) for p in limits['center_fraction'])
        mask = (time>=start)&(time<end)
        position, area, flow = (trace[key][mask] for key in ('lateral_position','oral_minimum_cm2','lip_flow_cm3_s'))
        voicing = float(np.median(trace['glottal_voicing'][mask]))
        x = float(np.median(trace['tongue_body_x_cm'][mask]))
        y = float(np.median(trace['tongue_body_y_cm'][mask]))
        opening = float(np.median(position))
        fraction_closed = float(np.mean(area<limits['closed_area_cm2']))
        if enabled:
            passes = (opening>=limits['lateral_median_open_minimum'] and voicing>=limits['minimum_voicing_median_with_opening']
                      and fraction_closed<=limits['max_closed_fraction_with_opening'])
        else:
            passes = not np.any(position) and fraction_closed>=limits['min_closed_fraction_without_opening']
        if segment['ipa']=='ɫ':
            passes = passes and x<=limits['maximum_dark_tongue_x_cm']
        if limits['expected_palatalized']:
            passes = passes and x>=limits['minimum_palatalized_tongue_x_cm']
        windows.append({'ipa':segment['ipa'],'median_lateral':opening,'median_voicing':voicing,
                        'median_tongue_body_cm':[x,y], 'minimum_oral_area_cm2':float(area.min()),
                        'median_oral_area_cm2':float(np.median(area)), 'fraction_closed':fraction_closed,
                        'rms_lip_flow_cm3_s':float(np.sqrt(np.mean(flow**2))),
                        'rms_pcm':float(np.sqrt(np.mean(pcm[mask].astype(float)**2))), 'passed':bool(passes)})
    tail = float(abs(pcm[-round(rate*limits['final_silence_seconds']):]).max())
    return {'windows':windows,'tail_peak':tail,'passed':all(w['passed'] for w in windows) and tail<=limits['final_max_peak_pcm']}


def check_area_floor(open_trace, closed_trace, segment, settings, limits):
    stage = settings['control_block_internal_samples']//settings['decimation_factor']
    rate = settings['case']['speech_voice']['voice']['output_sample_rate_hz']
    frames = np.arange(len(open_trace))
    time = (frames+1)/rate
    start,end = (segment['t0']+f*(segment['t1']-segment['t0']) for f in limits['center_fraction'])
    mask = (time>=start)&(time<end)&(closed_trace['oral_minimum_cm2']<limits['closed_area_cm2'])
    position = open_trace['lateral_position']
    start_frame = frames-frames%stage
    new = position[start_frame]
    previous = position[np.maximum(0,start_frame-stage)]
    expected = .35*(previous + (new-previous)*(frames%stage+1)/stage)
    count = int(mask.sum())
    error = float(abs(open_trace['oral_minimum_cm2'][mask]-expected[mask]).max()) if count else None
    return {'frames_with_closed_control':count, 'maximum_floor_difference_cm2':error,
            'passed':error is not None and error<=limits['geometry_absolute_tolerance']}


def compare_ablated(prior, closed_case, closed_signals, closed_events, settings, limits):
    path = WORKSPACE/'runs'/prior
    manifest = timing.read(path/'manifest.json')
    source_case = manifest['case_id']
    if manifest['status']!='pass' or manifest['upstream_revision']!=closed_case['upstream_revision']:
        raise ValueError('側方開きありの通過実行が必要です')
    inputs = {entry['path']:entry['sha256'] for entry in manifest['inputs']}
    if any(sha256(p)!=inputs.get(p.relative_to(WORKSPACE).as_posix()) for p in shared.candidate_sources()):
        raise ValueError('側方開きありの候補ソースが一致しません')
    case_path = f'cases/{source_case}.json'
    snapshot = path/'artifacts/source'/case_path
    if sha256(snapshot)!=inputs.get(case_path):
        raise ValueError('側方開きありのケースのハッシュが一致しません')
    original = timing.read(snapshot)['speech_voice']
    alternate = dict(closed_case['speech_voice'])
    alternate.pop('lateral_opening_scale')
    alternate['input'] = {**alternate['input'], 'id':original['input']['id']}
    if original!=alternate:
        raise ValueError('側方開き以外の設定が一致しません')
    outputs = {entry['path']:entry['sha256'] for entry in manifest['outputs']}
    for name in ('summary.json','artifacts/settings.json','artifacts/voicing.csv','artifacts/upstream-voicing.csv'):
        if sha256(path/name)!=outputs.get(name):
            raise ValueError(f'対照元のファイルのハッシュが一致しません ({name})')
    open_summary = timing.read(path/'summary.json')
    (segment,) = open_summary['plan']['lateral_segments']
    if timing.read(path/'artifacts/settings.json')['control_block_internal_samples']!=settings['control_block_internal_samples']:
        raise ValueError('側方開きありの制御周期が一致しません')
    result = []
    for i,name in enumerate(('voicing.csv','upstream-voicing.csv')):
        trace = voice.load_trace(path/'artifacts'/name,settings['output_frames'])
        shift = max(float(abs(trace[k]-closed_signals[i][k]).max()) for k in AXES_WITHOUT_LATERAL)
        open_window, = open_summary['candidate_and_upstream_events'][i]['windows']
        closed_window, = closed_events[i]['windows']
        ratio = open_window['rms_lip_flow_cm3_s']/max(1e-12,closed_window['rms_lip_flow_cm3_s'])
        floor = check_area_floor(trace,closed_signals[i],segment,settings,limits)
        result.append({'maximum_other_articulator_difference':shift, 'lip_flow_rms_ratio':ratio,
                       'open':open_window, 'closed':closed_window, 'interpolated_area_floor':floor,
                       'passed':shift<=limits['geometry_absolute_tolerance']
                       and ratio>=limits['minimum_flow_rms_ratio_open_to_closed'] and floor['passed']})
    return result


def measure(path, config, artifacts, execute, prior):
    case,limits = config['speech_voice'],config['measurement']
    settings, trace_path, files, upper_path, raw, plan_file = voice.capture(path,limits['host_block_frames'],artifacts,execute,SUITES)
    reference = timing.read(plan_file)
    laterals,plan = plans(settings,reference,limits)
    frames = settings['output_frames']
    traces = [voice.load_trace(p,frames) for p in (trace_path,upper_path)]
    physical = [name for name in traces[0].dtype.names if name!='oral_minimum_cell']
    first, differences = voice.compare_traces(traces[0][physical],traces[1][physical],limits)
    cells = alveolar.compare_cell_minima(*traces,limits)
    wav,output = files[0]
    rate,pcm = wavfile.read(wav)
    baseline = np.fromfile(raw,dtype='<f4')
    if pcm.shape!=(frames,) or baseline.shape!=(frames,) or not all(np.isfinite(a).all() for a in (pcm,baseline)):
        raise ValueError('PCMのフレーム数または有限性が基準と異なります')
    delta = abs(pcm.astype(float)-baseline)
    outliers = np.flatnonzero(delta>limits['pcm_absolute_tolerance'])
    events = [measure_events(trace,audio,laterals,rate,limits) for trace,audio in zip(traces,(pcm,baseline),strict=True)]
    spring = [independent_lateral(trace,settings,case,limits) for trace in traces]
    checks = {'plan':plan['passed'], 'trace':first is None and cells['passed'],
              'pcm':not outliers.size,'same_frame_count_and_rate':frames==reference['output_frames']
              and rate==case['voice']['output_sample_rate_hz'] and limits['expected_frames'] in (None,frames),
              'same_host_partitions':all(sha256(w)==sha256(wav) and sha256(c)==sha256(output) for w,c in files[1:]),
              'lateral_spring':all(s['passed'] for s in spring),'lateral_and_flow_events':all(e['passed'] for e in events)}
    summary = {'checks':checks, 'frames':frames,'plan':plan,'first_trace_difference':first,'trace_errors':differences,
               'oral_cells':cells,'candidate_and_upstream_spring':spring,'candidate_and_upstream_events':events,
               'pcm_max_abs_error':float(delta.max()), 'first_pcm_frame_over_tolerance':int(outliers[0]) if outliers.size else None}
    if prior is not None:
        pair = compare_ablated(prior, config, traces, events, settings, limits)
        checks['matched_side_opening_ablation'] = all(p['passed'] for p in pair)
        summary['candidate_and_upstream_ablation'] = pair
    if case.get('language')=='english':
        stem = artifacts/'upstream-native'
        log = stem.with_suffix('.log')
        execute(['cargo','run','--locked','--release','-p','chimera-cli','--','render','text',str(stem),case['input']['text'],'male','--float'],
                cwd=UPSTREAM,stdout=log)
        native_rate,native_pcm = wavfile.read(stem.with_suffix('.wav'))
        shown = log.read_text().splitlines()[0]
        checks['upstream_native_ipa_and_frame_count'] = shown==plan['shown'] and native_rate==rate and len(native_pcm)==frames
        summary['native_cli'] = {'shown':shown,'frames':len(native_pcm),'sample_rate_hz':native_rate}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition',choices=CASES)
    parser.add_argument('--enabled-run')
    args = parser.parse_args()
    if not all(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',key) for key in (args.run_id,args.enabled_run or 'valid')):
        parser.error('実行IDは英数字で始めてください')
    if args.condition.endswith('-closed')!=bool(args.enabled_run):
        parser.error('側方開き0では --enabled-run に対照元の実行IDを指定してください')
    path = WORKSPACE/f'cases/lateral-{args.condition}.json'
    case = timing.read(path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    tools = ['measure_alveolar_stop.py','measure_bilabial_stop.py','measure_sibilant.py','measure_speech_timing.py',
             'measure_uniform_tube.py','upstream_baseline.py']
    sources = [path,Path(__file__).resolve(),voice.PROBE,*(WORKSPACE/'tools'/name for name in tools),*shared.candidate_sources()]
    upper = ['phonetics/inventory.rs','phonetics/planner.rs','phonetics/durations.rs','control/articulators.rs',
             'control/score.rs','anatomy/human.rs','voice/human_voice.rs','voice/human_airway.rs']
    if args.condition=='hello':
        sources.extend(WORKSPACE/'data'/name for name in ('cmudict.txt.gz','CMUDICT-LICENSE.txt'))
        upper.append('phonetics/english.rs')
    metadata = {'case_id':case['id'],'upstream_revision':revision,'enabled_run_id':args.enabled_run,
                'upstream_pitch_drift_jitter_shimmer':0,'turbulence_seed':12345,'turbulence_scale':float(args.condition=='hello'),
                'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in upper}}
    return shared.record_measurement(args.run_id,path,sources,metadata,
                                     lambda artifacts,execute:measure(path,case,artifacts,execute,args.enabled_run),command=None)


if __name__=='__main__':
    raise SystemExit(main())
