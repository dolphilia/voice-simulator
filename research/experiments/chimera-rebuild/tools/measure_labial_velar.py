"""/w/ の調音・断面・LPC・波形を固定上流と照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

import measure_alveolar_stop as alveolar
import measure_bilabial_stop as voice
import measure_sibilant as speech
import measure_speech_timing as timing
import measure_uniform_tube as shared
from measure_vowel_voice import independent_lpc
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('w', 'w-fast', 'w-english', 'w-final')
SUITES = ('speech_quality', 'geometry_continuity', 'golden_phonetics_text')
LIPS = ('lip_aperture_cm', 'lip_protrusion_cm', 'lip_spread')


def plans(settings, reference, registered):
    report = settings['speech']
    if 'phrases' in report:
        report = {'utterances': [{'segments': row['timing']['segments']} for row in report['phrases']]}
    tolerance = registered['gesture_absolute_tolerance']
    segments, comparison = speech.compare_plans({**settings, 'speech': report}, reference, tolerance)
    index = next(i for i, part in enumerate(segments) if part['ipa'] == 'w')
    approximant = segments[index]
    before = registered['adjacent_vowel'] == 'preceding'
    vowel = segments[index - 1 if before else index + 1]
    rate = max(1, settings['case']['speech_voice']['input']['rate'])
    gestures = settings['gestures']
    labeled = [g for g in gestures if g['label'] == 'w']
    if len(labeled) != 1 or vowel['kind'] != 'vowel':
        return approximant, vowel, {**comparison, 'passed':False, 'reason':'接近音の目標または隣接する母音がありません'}
    start, end = approximant['t0'], approximant['t1']
    expected = {
        'label':'w', 't0':start-.008, 't1':max(start+.010,end), 'rampIn':.030/rate,
        'rampOut':.018/rate, 'releaseHold':.045/rate, 'strength':40, 'speed':1.3,
        'targets':registered['strong_targets'],
    }
    diff, error = timing.compare(labeled[0], expected, tolerance)
    exhale = next(g for g in gestures if g['label']=='exhale')
    exhale_delay = exhale['t0'] - segments[-1]['t1']
    shown = settings['speech'].get('shown')
    return approximant, vowel, {
        **comparison, 'expected_gesture_difference':diff, 'registered_maximum_numeric_error':error,
        'shown':shown, 'approximant_gesture':labeled[0],'final_exhale_delay_seconds':exhale_delay,
        'passed':comparison['passed'] and diff is None and shown==registered['expected_shown']
        and abs(exhale_delay-.045)<=tolerance,
    }


def articulator_spring(trace, settings, initial, rate, frequency_hz, tolerance):
    stride = settings['control_block_internal_samples']//settings['decimation_factor']
    step = stride/rate
    clock = np.arange(0,len(trace),stride)/rate
    axes = tuple(initial)
    rest = np.array([initial[axis] for axis in axes])
    weights = np.zeros((len(clock),len(axes)))
    weighted = np.zeros_like(weights)
    speed = np.ones_like(weights)
    for gesture in settings['gestures']:
        start, end = gesture['t0'], gesture['t1']
        a, b = gesture['rampIn'], gesture['rampOut']
        attack = np.sin(.5*np.pi*np.clip((clock-start+a)/a,0,1))**2
        release = np.cos(.5*np.pi*np.clip((clock-end)/b,0,1))**2
        active = gesture['strength']*np.where(clock<start,attack,np.where(clock<end+b,release,0))
        for i, axis in enumerate(axes):
            target = gesture['targets'].get(axis)
            if target is None:
                continue
            weights[:,i] += active
            weighted[:,i] += active*target
            if 'speed' in gesture:
                hold = gesture.get('releaseHold',0)
                keep = (clock>=start-a) & (clock<=end+b+hold)
                speed[keep,i] = np.maximum(speed[keep,i],gesture['speed'])
    target = (.05*rest+weighted)/(.05+weights)
    angular_frequency = 2*math.pi*frequency_hz*np.where(weights>0,speed,1)
    positions = np.zeros_like(weights)
    position = rest.copy()
    velocity = np.zeros_like(rest)
    for i, (value, omega) in enumerate(zip(target,angular_frequency,strict=True)):
        velocity += (omega**2*(value-position)-2*omega*velocity)*step
        position += velocity*step
        positions[i] = position
    estimates = np.repeat(positions,stride,axis=0)[:len(trace)]
    channels = {axis: float(np.max(abs(estimates[:,i]-trace[axis]))) for i,axis in enumerate(axes)}
    return {'maximum_position_error':channels, 'passed':max(channels.values())<=tolerance}


def gestures_and_area(trace, pcm, segment, rate, limits):
    time = (trace['frame']+1)/rate
    duration = segment['t1']-segment['t0']
    low, high = (segment['t0']+fraction*duration for fraction in limits['center_fraction'])
    selected = (low<=time) & (time<high)
    central = {k:float(np.median(trace[k][selected])) for k in (*LIPS,'tongue_body_x_cm','tongue_body_y_cm','glottal_voicing')}
    min_area = float(trace['oral_minimum_cm2'][selected].min())
    lip_area = float(trace['lip_minimum_cm2'][selected].min())
    tail = float(abs(pcm[-round(rate*limits['final_silence_seconds']):]).max())
    return {'central_medians':central,'minimum_oral_area_cm2':min_area,'minimum_lip_area_cm2':lip_area,
            'peak_pcm_at_tail':tail,'passed':bool(min(min_area,lip_area)>limits['closed_area_cm2']
            and central['glottal_voicing']>=limits['minimum_voicing_median']
            and central['lip_protrusion_cm']>=limits['minimum_protrusion_center_cm']
            and central['lip_spread']<=limits['maximum_spread_center'] and tail<=limits['final_max_peak_pcm'])}


def spectrum(wave, span, rate, limits):
    center = span['t0']+limits['measure_lpc_at_fraction']*(span['t1']-span['t0'])
    count = round(rate*limits['window_duration_seconds'])
    start = round(center*rate)-count//2
    if start<0 or start+count>len(wave):
        raise ValueError('LPCの窓が波形の範囲外です')
    cfg = limits['lpc']
    lpc_rate = cfg['lpc_sample_rate_hz']
    values = independent_lpc(resample_poly(wave[start:start+count].astype(float),lpc_rate,rate),cfg)
    values = values[values[:,0]<lpc_rate/2-cfg['lpc_nyquist_guard_hz']]
    return {'ipa':span['ipa'],'start_frame':start,'frame_count':count,'poles_hz':values.tolist()}


def compare_acoustics(pcm, baseline, target, neighbor, rate, limits):
    results = [{key:spectrum(wave,segment,rate,limits) for key,segment in (('w',target),('vowel',neighbor))}
               for wave in (pcm,baseline)]
    n = limits['formant_index']
    errors, rises, missing = [], [], []
    for name in ('w','vowel'):
        a,b = (row[name]['poles_hz'] for row in results)
        if min(len(a),len(b))>=n:
            errors.append(float(abs(np.array(a[:n])-np.array(b[:n])).max()))
        else:
            missing.append(name)
    if not missing:
        rises = [row['vowel']['poles_hz'][n-1][0]-row['w']['poles_hz'][n-1][0] for row in results]
    return {'formant_index':n,'candidate_and_upstream':results,'missing_windows':missing,
            'maximum_compared_formant_error_hz':max(errors,default=None),'vowel_minus_w_hz':rises,
            'passed':not missing and max(errors)<=limits['formant_match_hz'] and min(rises)>=limits['minimum_formant_rise_hz']}


def measure(path, config, artifacts, execute):
    case, limits = config['speech_voice'], config['measurement']
    settings, trace_path, files, up_path, up_pcm, up_plan = voice.capture(path,limits['host_block_frames'],artifacts,execute,SUITES)
    count = settings['output_frames']
    candidate, upstream = (voice.load_trace(p,count) for p in (trace_path,up_path))
    reference = timing.read(up_plan)
    target, neighbor, plan = plans(settings,reference,limits)
    physical = [name for name in candidate.dtype.names if name!='oral_minimum_cell']
    first, trace_errors = voice.compare_traces(candidate[physical],upstream[physical],limits)
    cells = alveolar.compare_cell_minima(candidate,upstream,limits)
    wav,csv = files[0]
    rate,pcm = wavfile.read(wav)
    baseline = np.fromfile(up_pcm,dtype='<f4')
    if pcm.shape!=(count,) or baseline.shape!=(count,) or not all(np.isfinite(w).all() for w in (pcm,baseline)):
        raise ValueError('PCMのフレーム数または有限性が基準と異なります')
    delta = abs(pcm.astype(float)-baseline)
    over = np.flatnonzero(delta>limits['pcm_absolute_tolerance'])
    initial_lips = {axis:case['posture'][axis] for axis in LIPS}
    control = [articulator_spring(trace,settings,initial_lips,rate,11,limits['spring_position_tolerance'])
               for trace in (candidate,upstream)]
    area = [gestures_and_area(trace,wave,target,rate,limits) for trace,wave in ((candidate,pcm),(upstream,baseline))]
    acoustics = compare_acoustics(pcm,baseline,target,neighbor,rate,limits)
    return {
        'checks':{'plans':plan['passed'],'geometry_and_trace':first is None and cells['passed'],
                  'frame_count_and_rate':count==reference['output_frames'] and rate==case['voice']['output_sample_rate_hz'],
                  'same_host_partitions':all(sha256(w)==sha256(wav) and sha256(c)==sha256(csv) for w,c in files[1:]),
                  'pcm':not over.size,'independent_lip_dynamics':all(x['passed'] for x in control),
                  'narrowing_and_voicing':all(x['passed'] for x in area),'adjacent_formant_movement':acoustics['passed']},
        'frames':count,'plan':plan,'oral_cells':cells,'first_trace_difference':first,'trace_errors':trace_errors,
        'candidate_and_upstream_area':area,'independent_candidate_and_upstream':control,'acoustics':acoustics,
        'pcm_max_abs_error':float(delta.max()),'first_pcm_frame_over_tolerance':int(over[0]) if over.size else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition',choices=CASES)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_path = WORKSPACE/f'cases/approximant-{args.condition}.json'
    case = timing.read(case_path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=case['upstream_revision'] or subprocess.check_output(['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    tools = ['measure_alveolar_stop.py','measure_bilabial_stop.py','measure_sibilant.py','measure_speech_timing.py',
             'measure_uniform_tube.py','measure_vowel_voice.py','measure_pcm_output.py','upstream_baseline.py']
    sources = [case_path,Path(__file__).resolve(),voice.PROBE,*(WORKSPACE/'tools'/name for name in tools),*shared.candidate_sources()]
    upper = ['phonetics/inventory.rs','phonetics/planner.rs','phonetics/durations.rs','phonetics/consonantTargets.generated.json',
             'control/score.rs','control/articulators.rs','voice/human_voice.rs','anatomy/human.rs']
    if args.condition=='w-english':
        upper.append('phonetics/english.rs')
        sources.extend(WORKSPACE/'data'/name for name in ('cmudict.txt.gz','CMUDICT-LICENSE.txt'))
    evidence = {'upstream_revision':revision,'case_id':case['id'],'upstream_pitch_drift_jitter_shimmer':0,
                'turbulence_scale':0,'upper_source_sha256':{f:sha256(UPSTREAM/'crates/chimera/src'/f) for f in upper}}
    return shared.record_measurement(args.run_id,case_path,sources,evidence,
                                     lambda artifacts,execute:measure(case_path,case,artifacts,execute),command=None)


if __name__=='__main__':
    raise SystemExit(main())
