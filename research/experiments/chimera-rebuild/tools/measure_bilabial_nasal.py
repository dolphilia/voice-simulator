"""両唇鼻音のスコア・軟口蓋・口鼻の放射を固定上流に照合する。"""

import argparse
import math
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as speech
import measure_sibilant as sibilant
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASES = ('m', 'mb', 'mp', 'final', 'vcv')
SUITES = ('nasal_spans', 'speech_quality')


def nasal_plan(settings, reference, config):
    limits = config['measurement']
    tolerance = limits['gesture_abs_tolerance']
    segments, evidence = sibilant.compare_plans(settings, reference, tolerance)
    nasal = next(row for row in segments if row['ipa'] == 'm')
    gestures = settings['gestures']
    velum = next(g for g in gestures if 'velum_cm2' in g['targets'])
    exhale = next(g for g in reversed(gestures) if g['label'] == 'exhale')
    end = settings['speech']['utterances'][-1]['end_seconds']
    prediction = {
        'nasal_t0': nasal['t0'], 'nasal_t1': nasal['t1'],
        'velum_onset_lead_s': nasal['t0'] - velum['t0'],
        'velum_seal_lead_s': nasal['t1'] - velum['t1'],
        'velum_peak_target_cm2': velum['targets']['velum_cm2'],
        'exhale_delay_s': exhale['t0'] - end,
        'ordered_utterances': [row['text'] for row in settings['speech']['utterances']],
    }
    expected = limits['expected']
    difference, _ = timing.compare({key: prediction[key] for key in expected}, expected, tolerance)
    evidence['registered_difference'] = difference
    evidence['passed'] = evidence['passed'] and difference is None
    return nasal, end, evidence, prediction


def independent_velum(trace, settings, config, output_rate, *, body_scale=1.0):
    block = settings['control_block_internal_samples']//settings['decimation_factor']
    dt = block/output_rate
    base = config['speech_voice']['posture']['velum_cm2']
    area_scale = body_scale**2
    pos, velocity, port = base, 0.0, max(0.0, base) * area_scale
    omega = 24*math.pi
    gestures = [g for g in settings['gestures'] if 'velum_cm2' in g['targets']]
    analytic = np.empty((3, len(trace)))

    def activation(g, t):
        if t < g['t0']:
            u = max(0,(t-g['t0']+g['rampIn'])/max(1e-6,g['rampIn']))
            return math.sin(math.pi/2*u)**2
        u = max(0,(t-g['t1'])/max(1e-6,g['rampOut']))
        return math.cos(math.pi/2*u)**2 if u < 1 else 0.0

    for i in range(0,len(trace),block):
        t = i/output_rate
        weights = [activation(g,t)*g['strength'] for g in gestures]
        total = math.fsum(weights)
        value = math.fsum(w*g['targets']['velum_cm2'] for w,g in zip(weights,gestures,strict=True))
        effective = base if total == 0 else base + min(1.0,total/2)*(value/total-base)
        velocity = velocity*(1-2*omega*dt) + omega**2*(effective-pos)*dt
        pos += dt*velocity
        target = max(pos,0.0) * area_scale
        n = min(block,len(trace)-i)
        analytic[0,i:i+n] = effective
        analytic[1,i:i+n] = pos
        analytic[2,i:i+n] = port + (target-port)*np.arange(1,n+1)/block
        port = target

    keys = ('velum_effective_cm2','velum_position_cm2','velum_port_area_cm2')
    limit = config['measurement']['independent_velum_abs_tolerance']
    delta = abs(np.vstack([trace[key] for key in keys])-analytic)
    max_abs = dict(zip(keys,delta.max(axis=1).tolist(),strict=True))
    return {'maximum_absolute_error':max_abs,'passed':max(max_abs.values())<=limit}


def nasal_events(trace, pcm, nasal, end, rate, limits):
    count = len(trace)
    seconds = (np.arange(count)+1)/rate
    t0,t1 = nasal['t0'],nasal['t1']
    width = t1-t0
    a,b = limits['center_fraction']
    center = (seconds>=t0+a*width) & (seconds<t0+b*width)
    around = (seconds>=t0-.08) & (seconds<t1+.12)
    port = trace['velum_port_area_cm2']
    prev_open = (np.roll(port,1)>=limits['velum_audible_cm2'])
    now_open = port>=limits['velum_audible_cm2']

    def first(mask):
        values = np.flatnonzero(mask)
        return int(values[0]) if values.size else None

    onset = first(around & ~prev_open & now_open)
    offset = first(around & (seconds>=t0+.5*width) & prev_open & ~now_open)
    acoustic = first(around & (trace['oral_min_cell_area_cm2']<limits['oral_acoustic_area_cm2']))
    seal = first(around & (trace['lip_minimum_cm2']<limits['lip_seal_area_cm2']))
    # 直前5 msのRMSを使い、有声周期中の瞬間的な交差と区別する。
    samples = max(1,round(.005*rate))
    power_difference = np.square(trace['nose_flow_cm3_s']) - np.square(trace['lip_flow_cm3_s'])
    favor_nose = first(around & now_open & (np.convolve(power_difference,np.ones(samples),'full')[:count]>0))
    if not center.any() or any(frame is None for frame in (onset,offset,acoustic,seal,favor_nose)):
        return {'passed':False,'reason':'鼻音の閉鎖または流量切替が測定窓内にありません',
                'open_close_frames':[onset,offset],'oral_acoustic_and_lip_seal_frames':[acoustic,seal],
                'nasal_dominance_onset_frame':favor_nose}

    def rms(signal):
        return float(np.sqrt(np.mean(np.square(signal,dtype='f8'))))

    nose, lip, flow = [rms(trace[name][center]) for name in ('nose_flow_cm3_s','lip_flow_cm3_s','velum_flow_cm3_s')]
    ratio = nose/(lip+nose) if nose+lip else 0.0
    voice = float(np.median(trace['glottal_voicing'][center]))
    value = float(port[center].max())
    tail_samples = pcm[seconds>=end+limits['tail_start_after_end_s']]
    if not tail_samples.size:
        raise ValueError('句末の減衰を測るフレームがありません')
    tail = 20*math.log10(max(rms(tail_samples),1e-20)/max(float(abs(pcm).max()),1e-20))
    zero_port = bool(np.all(trace['velum_flow_cm3_s'][port<limits['lip_seal_area_cm2']]==0))
    return {
        'open_close_frames':[onset,offset], 'open_close_seconds':[float(seconds[onset]),float(seconds[offset])],
        'oral_acoustic_and_lip_seal_frames':[acoustic,seal],
        'oral_acoustic_and_lip_seal_offsets_ms':[float((seconds[acoustic]-t0)*1000),float((seconds[seal]-t0)*1000)],
        'nasal_dominance_onset_frame':favor_nose, 'nasal_dominance_onset_seconds':float(seconds[favor_nose]),
        'nasal_dominance_rms_window_seconds':samples/rate,
        'center_velum_max_cm2':value,'center_nose_lip_and_port_flow_rms_cm3_s':[nose,lip,flow],
        'center_nasal_flow_ratio':ratio,'center_median_voicing':voice,'tail_rms_relative_to_peak_db':tail,
        'closed_velum_branch_flow_zero':zero_port,
        'passed': (value>=limits['minimum_center_velum_cm2'] and ratio>=limits['minimum_nasal_ratio']
                   and voice>=limits['minimum_voiced_coeff_center']
                   and tail<=limits['tail_max_db_relative_to_peak'] and zero_port),
    }


def measure(path, config, artifacts, execute, voiceless):
    limits = config['measurement']
    settings, trace_path, files, upper_trace, upstream_pcm, upstream_plan = speech.capture(
        path,limits['host_block_frames'],artifacts,execute,SUITES,
    )
    frames = settings['output_frames']
    reference = timing.read(upstream_plan)
    actual = speech.load_trace(trace_path,frames)
    upper = speech.load_trace(upper_trace,frames)
    wave,csv = files[0]
    rate,pcm = wavfile.read(wave)
    upper_pcm = np.fromfile(upstream_pcm,dtype='<f4')
    if len(pcm) != frames or pcm.shape != upper_pcm.shape or not all(np.isfinite(x).all() for x in (pcm,upper_pcm)):
        raise ValueError('PCMの長さまたは有限性が基準と異なります')
    delta = abs(pcm.astype('f8')-upper_pcm)
    pcm_hits = np.flatnonzero(delta>limits['pcm_abs_tolerance'])
    mismatches,errors = sibilant.source_comparison(actual,upper,{**limits,'selection_abs_tolerance':1e-9})
    nasal,end,plan,prediction = nasal_plan(settings,reference,config)
    candidate,upper_events = (nasal_events(trace,audio,nasal,end,rate,limits)
                              for trace,audio in ((actual,pcm),(upper,upper_pcm)))
    independent = independent_velum(actual,settings,config,rate)
    events_fields = ('open_close_frames','oral_acoustic_and_lip_seal_frames','nasal_dominance_onset_frame')
    report = {
        'checks': {
            'plan':plan['passed'], 'trace':not mismatches, 'pcm':not pcm_hits.size,
            'frame_count': frames==reference['output_frames'] and rate==config['speech_voice']['voice']['output_sample_rate_hz'],
            'independent_velum':independent['passed'], 'nasal_flow_and_tail':candidate['passed'] and upper_events['passed'],
            'measured_event_frames':all(candidate.get(key)==upper_events.get(key) for key in events_fields),
            'host_partition':all(sha256(w)==sha256(wave) and sha256(c)==sha256(csv) for w,c in files[1:]),
        },
        'frames':frames,'plan':plan,'plan_observations':prediction,'first_trace_differences':mismatches,
        'trace_errors':errors,'pcm_max_abs_error':float(delta.max()),
        'first_pcm_frame_over_tolerance':int(pcm_hits[0]) if pcm_hits.size else None,
        'independent_velum':independent,'candidate_events':candidate,'upstream_events':upper_events,
    }
    if voiceless:
        control = timing.read(voiceless)
        t_b = candidate['open_close_seconds'][1]
        t_p = control['candidate_events']['open_close_seconds'][1]
        same_span = all(control['plan_observations'][key]==prediction[key] for key in ('nasal_t0','nasal_t1'))
        lo,hi = limits['voiceless_stop_comparison_delay_s']
        seal_delay = control['plan_observations']['velum_seal_lead_s'] - prediction['velum_seal_lead_s']
        report['following_stop_comparison'] = {'same_m_span':same_span,'measured_port_seal_delay_s':t_b-t_p,
                                               'planned_velum_release_delay_s':seal_delay}
        report['checks']['voiced_stop_delays_port_seal'] = same_span and lo<=t_b-t_p<=hi
    return report


def validated_control(run_id,revision,sources):
    folder = WORKSPACE/'runs'/run_id
    manifest, summary = folder/'manifest.json',folder/'summary.json'
    control = timing.read(manifest)
    inputs = {row['path']:row['sha256'] for row in control['inputs']}
    outputs = {row['path']:row['sha256'] for row in control['outputs']}
    if (control['case_id']!='bilabial-nasal-mp' or control['status']!='pass' or control['upstream_revision']!=revision
            or outputs.get('summary.json')!=sha256(summary)
            or any(inputs.get(str(p.relative_to(WORKSPACE)))!=sha256(p) for p in sources)):
        raise ValueError('同一の実装と上流版で通過した /mp/ の対照を指定してください')
    return manifest,summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('condition',choices=CASES)
    parser.add_argument('--voiceless-run',help='/mb/ と比較する /mp/ の通過済み実行')
    args = parser.parse_args()
    id_pattern = r'[A-Za-z0-9][A-Za-z0-9_-]*'
    if not re.fullmatch(id_pattern,args.run_id):
        parser.error('実行IDは英数字で始めてください')
    if args.voiceless_run and (args.condition!='mb' or not re.fullmatch(id_pattern,args.voiceless_run)):
        parser.error('--voiceless-run は mb の条件で有効な実行IDを指定してください')
    path = WORKSPACE/f'cases/bilabial-nasal-{args.condition}.json'
    config = timing.read(path)
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=UPSTREAM,text=True).strip()
    if revision!=config['upstream_revision'] or subprocess.check_output(
            ['git','status','--porcelain'],cwd=UPSTREAM,text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    candidate = shared.candidate_sources()
    sources = [path,speech.PROBE,Path(__file__).resolve(),Path(shared.__file__),Path(timing.__file__),
               Path(speech.__file__),Path(sibilant.__file__),WORKSPACE/'tools/upstream_baseline.py',*candidate]
    voiceless = None
    if args.voiceless_run:
        manifest,voiceless = validated_control(args.voiceless_run,revision,candidate)
        sources.extend((manifest,voiceless))
    names = ['phonetics/planner.rs','phonetics/inventory.rs','voice/human_voice.rs','voice/human_airway.rs',
             'control/articulators.rs','anatomy/human.rs','airway/network.rs']
    info = {'case_id':config['id'],'upstream_revision':revision,
            'upper_source_sha256':{name:sha256(UPSTREAM/'crates/chimera/src'/name) for name in names}}
    if args.voiceless_run:
        info['voiceless_run_id'] = args.voiceless_run
    return shared.record_measurement(args.run_id,path,sources,info,
        lambda artifacts,execute:measure(path,config,artifacts,execute,voiceless),command=None)


if __name__=='__main__':
    raise SystemExit(main())
