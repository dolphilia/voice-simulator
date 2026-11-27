"""研究版の歌唱を予約前に描画し、最初の乱流注入とPCM差を固定上流へ照合する。"""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_bilabial_stop import capture_candidate, load_trace
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import candidate_sources, record_measurement
from measure_upstream_song_schedule_state import first_difference
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/song-voice-schedule-state.json'


def input_case(template, fixture, rate, lead, samples, warm_up, noise):
    case = deepcopy(template)
    song = case['song_voice']
    score, source = fixture['score'], fixture['source']
    song.update(warm_up_frames=warm_up, render_end_seconds=(lead + samples) / rate, body=fixture['body'],
                vibrato_cents=score['vibrato_cents'], turbulence={'scale': noise})
    song['score'].update(lyrics=score['lyrics'], bpm=score['bpm'],
                         start_seconds=score['first_beat_seconds'] + lead / rate,
                         notes=[{'midi': midi, 'beats': beats} for midi, beats in score['notes']])
    song['voice'].update(pressure_cm_h2o=source['pressure'], breathiness=source['breathiness'],
                         tension=source['tension'], base_pitch_hz=source['f0'], output_sample_rate_hz=rate)
    # 上流のsendStateが使う中立姿勢と同じく、下顎の回転で決まる舌先から始める。
    posture = song['posture']
    angle = -posture['jaw_cm'] / 9.84
    dx, dy = 6.45 + 2.5, 7.35 - 10.5
    posture['tongue_tip_cm'] = [-2.5 + dx * math.cos(angle) - dy * math.sin(angle),
                               10.5 + dx * math.sin(angle) + dy * math.cos(angle)]
    return case


def first_injection(trace, at):
    pressure = np.column_stack((trace['glottis_noise_forward_pressure'], trace['glottis_noise_reverse_pressure']))
    active = np.flatnonzero((trace['glottis_noise_level'] > 0) & np.any(pressure != 0, axis=1))
    if not len(active):
        return None
    i = active[0]
    return {'frame': int(at[i]), 'source_is_glottis': bool(trace['glottis_noise_source'][i] == -2),
            'forward': int(trace['glottis_noise_forward'][i]), 'reverse': int(trace['glottis_noise_reverse'][i]),
            'pressure_dyn_cm2': [float(x) for x in pressure[i]], 'level': float(trace['glottis_noise_level'][i])}


def compare_pair(earlier, later, upper, native, at, nominal_phase):
    a, x, metadata_a = earlier
    b, y, metadata_b = later
    glottis_pressure = ('glottis_noise_forward_pressure', 'glottis_noise_reverse_pressure')
    names = {
        'gate': ('gate',), 'lip_opening_cm': ('lip_aperture_cm',), 'lip_area_cm2': ('lip_area_cm2',),
        'lung_pressure_dyn_cm2': ('lung_boundary_dyn_cm2',), 'glottal_flow_cm3_s': ('glottal_flow_cm3_s',),
        'glottal_area_cm2': ('glottal_area_cm2',), 'glottal_f0_hz': ('glottal_f0_hz',),
        'glottal_voicing': ('glottal_voicing',), 'subglottal_pressure_dyn_cm2': ('pressure_sub_dyn_cm2',),
        'supraglottal_pressure_dyn_cm2': ('pressure_supra_dyn_cm2',),
        'glottal_phase_cycles': ('glottal_phase',), 'signed_noise_pressure_dyn_cm2': glottis_pressure,
        'radiation_derivative_cm3_s2': ('radiation_derivative_cm3_s2',),
        'lip_radiation_cm3_s': ('lip_flow_cm3_s',), 'nose_radiation_cm3_s': ('nose_flow_cm3_s',),
    }
    stage = {}
    for name, columns in names.items():
        delta = b[columns[0]] - a[columns[0]]
        if name == 'glottal_phase_cycles':
            delta = (delta + .5) % 1 - .5
        elif name == 'signed_noise_pressure_dyn_cm2':
            delta = np.maximum(abs(delta), abs(b[columns[1]] - a[columns[1]]))
        threshold = native['thresholds'][name]
        first = first_difference(abs(delta), threshold, at)
        upper_first = upper['columns'][name]['first_frame_over_threshold']
        stage[name] = {'candidate_first_frame': first, 'upstream_first_frame': upper_first,
                       'first_frame_delta': first - upper_first if first is not None and upper_first is not None else None,
                       'candidate_maximum_absolute_difference': float(abs(delta).max())}
    floor = native['pcm_difference_floor']
    advance = float((b['glottal_phase'][0] - a['glottal_phase'][0]) % 1.)
    pcm = first_difference(abs(y.astype(float) - x), floor, at)
    upstream_pcm = upper['first_pcm_frame_over_tolerance']
    return {'stages': stage, 'first_injection': [metadata_a, metadata_b], 'phase_advance_cycles': advance,
            'phase_advance_from_constant_f0': nominal_phase, 'pcm_first_frame_over_tolerance': pcm,
            'upstream_pcm_first_frame_over_tolerance': upstream_pcm,
            'pcm_onset_difference_frames': pcm - upstream_pcm if pcm is not None and upstream_pcm is not None else None}


def measure(study, template, native, fixture, probe, upper, artifacts, execute):
    rate, samples = native['output_rate_hz'], native['comparison_samples']
    lead = round(native['lead_seconds'] * rate)
    frames = lead + samples
    at = np.arange(frames) - lead
    expected = [(s['ipa'], round(s['t0'] * rate), round(s['t1'] * rate)) for s in probe['segments']]
    checks, results = {}, {}
    for noise in native['noise_scales']:
        for warm in native['schedule_engine_frames']:
            label = f'frame-{warm}-noise-{noise}'
            folder = artifacts / label
            folder.mkdir()
            case_path = folder / 'input.json'
            case = input_case(template, fixture, rate, lead, samples, warm, noise)
            case_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
            info, trace_path, outputs = capture_candidate(case_path, study['host_block_frames'], folder, execute)
            trace = load_trace(trace_path, frames)
            segments = [s for phrase in info['song']['plan']['phrases'] for s in phrase['timing']['segments']]
            plan = [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead,
                     round(s['end_seconds'] * rate) - lead) for s in segments]
            (wave, pcm_trace), *alternate = outputs
            received_rate, pcm = wavfile.read(wave)
            meta = first_injection(trace, at)
            checks[f'{label}/registered_relative_plan'] = plan == expected
            checks[f'{label}/rate_frames_and_finite'] = (received_rate == rate and pcm.shape == (frames,)
                and pcm.dtype == np.float32 and np.isfinite(pcm).all()
                and info['output_frames'] == frames
                and info['control_block_internal_samples'] == 128 and info['decimation_factor'] == 2)
            checks[f'{label}/same_output_at_each_block_size'] = all(
                sha256(w) == sha256(wave) and sha256(c) == sha256(pcm_trace) for w, c in alternate)
            if noise == 0:
                checks[f'{label}/noise_muted'] = meta is None and all(
                    not trace[column].any() for column in trace.dtype.names if column.endswith(('_forward_pressure', '_reverse_pressure')))
            elif meta is not None:
                checks[f'{label}/glottis_branch_matches_geometry'] = (
                    meta['source_is_glottis'] and meta['forward'] == info['noise_branches']['pharynx']['base'] + 1)
            results[noise, warm] = trace, pcm, meta
    starts = native['schedule_engine_frames']
    nominal_phase = (starts[1] - starts[0]) * fixture['source']['f0'] / rate
    comparison = {str(scale): compare_pair(*(results[scale, warm] for warm in starts),
                    upper['comparisons_by_noise_scale'][str(scale)], native, at, nominal_phase)
                  for scale in native['noise_scales']}
    a, b = comparison['1'], comparison['0']
    first, muted = a['pcm_first_frame_over_tolerance'], b['pcm_first_frame_over_tolerance']
    inject = a['stages']['signed_noise_pressure_dyn_cm2']['candidate_first_frame']
    predictions = {
        'phase_advances_at_reservation': abs(a['phase_advance_cycles'] - nominal_phase)
                                         <= native['phase_advance_tolerance_cycles'],
        'lip_opening_and_gate_match': all(a['stages'][field]['candidate_first_frame'] is None
                                         for field in ('lip_opening_cm', 'gate')),
        'glottal_noise_differs_by_first_pcm_difference': first is not None and inject is not None and inject <= first,
        'muting_delays_pcm_difference': first is not None and muted is not None and muted > first,
        'pcm_onsets_near_fixed_upstream': all(
            row['pcm_onset_difference_frames'] is not None
            and abs(row['pcm_onset_difference_frames']) <= study['maximum_onset_difference_frames']
            for row in comparison.values()),
    }
    return {'checks': checks, 'predictions': predictions, 'comparisons_by_noise_scale': comparison,
            'relative_plan_frames': expected, 'lead_frames': lead, 'rendered_frames': frames}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = json.loads(CASE.read_text())
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    info = study['upstream_reference']
    native_path, template_path = (CASE.parent / key for key in (info['case'], study['template']))
    native = json.loads(native_path.read_text())
    template = json.loads(template_path.read_text())
    run = run_manifest(info['run'], native['id'], revision)
    summary = verified_path(run, 'summary.json')
    input_file = verified_path(run, 'artifacts/native-input.json')
    probe_path = verified_path(run, 'artifacts/probe.json')
    upper, fixture, probe = (json.loads(path.read_text()) for path in (summary, input_file, probe_path))
    if (run[1]['status'] != 'pass' or not all(upper['predictions'].values())
            or any(fixture[key] != native[key] for key in ('schedule_engine_frames', 'noise_scales', 'output_rate_hz',
                                                          'internal_rate_hz', 'lead_seconds', 'comparison_samples'))):
        parser.error('固定上流の測定値と登録条件が揃いません')
    inputs = [CASE, native_path, template_path, Path(__file__).resolve(), run[0] / 'manifest.json', summary, input_file,
              probe_path, Path(capture_candidate.__code__.co_filename), Path(first_difference.__code__.co_filename),
              *candidate_sources()]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_command': [sys.executable, *sys.argv],
                'analysis_directory': str(Path.cwd()), 'upstream_reference_run': info['run']}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, template, native, fixture, probe, upper, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
