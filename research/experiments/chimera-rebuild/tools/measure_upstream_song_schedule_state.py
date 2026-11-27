"""固定上流の歌唱予約を1量子ずらし、声門・乱流・放射・PCMの差を追う。"""

import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import build_upstream_probe, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/upstream-song-schedule-state.json'
PROBE = Path(__file__).with_name('upstream_song_schedule_state_probe.rs').resolve()
DICTIONARY = UPSTREAM / 'public/data/cmudict.txt.gz'


def first_difference(delta, threshold, frames=None):
    positions = np.flatnonzero(delta > threshold)
    if not len(positions):
        return None
    return int(positions[0] if frames is None else frames[positions[0]])


def relative_segments(segments, origin, rate):
    return [(segment['kind'], segment['ipa'], segment.get('stress'),
             round((segment['t0'] - origin) * rate), round((segment['t1'] - origin) * rate))
            for segment in segments]


def compare_pair(left, right, spec):
    earlier, left_pcm = left
    later, right_pcm = right
    frames = earlier['relative_frame']
    columns = {}
    for name, threshold in spec['thresholds'].items():
        delta = later[name] - earlier[name]
        if name == 'glottal_phase_cycles':
            delta = (delta + .5) % 1 - .5
        absolute = abs(delta)
        first = first_difference(absolute, threshold, frames)
        position = None if first is None else int(np.searchsorted(frames, first))
        columns[name] = {'first_frame_over_threshold': first, 'maximum_absolute_difference': float(absolute.max()),
                         'first_values': [float(data[name][position]) for data in (earlier, later)]
                         if position is not None else None}
    pcm = left_pcm.astype(float) - right_pcm
    bit = first_difference(left_pcm.view('<u4') != right_pcm.view('<u4'), 0)
    return {'phase_before_schedule_cycles': [float(t['glottal_phase_cycles'][0]) for t in (earlier, later)],
            'phase_advance_before_schedule_cycles': float((later['glottal_phase_cycles'][0]
                                                          - earlier['glottal_phase_cycles'][0]) % 1.),
            'noise_first_nonzero_pressure_frame': [first_difference(abs(t['signed_noise_pressure_dyn_cm2']), 0, frames)
                                                    for t in (earlier, later)],
            'columns': columns, 'first_pcm_bit_difference': bit,
            'first_pcm_frame_over_tolerance': first_difference(abs(pcm), spec['pcm_difference_floor']),
            'maximum_pcm_difference': float(abs(pcm).max())}


def measure(study, fixture, clips, previous, artifacts, execute):
    dictionary = artifacts / 'cmudict.txt'
    dictionary.write_bytes(gzip.decompress(DICTIONARY.read_bytes()))
    rate = study['output_rate_hz']
    lead = round(rate * study['lead_seconds'])
    input_path = artifacts / 'native-input.json'
    input_path.write_text(json.dumps({**study, **fixture}, ensure_ascii=False, indent=2) + '\n')
    executable = build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    execute([str(executable), str(input_path), str(dictionary), str(artifacts)], cwd=UPSTREAM)
    output = json.loads((artifacts / 'probe.json').read_text())
    sample_count = study['comparison_samples']
    expected_frames = np.arange(-lead - 1, sample_count)
    checks, outputs = {}, {}
    for arm in output['arms']:
        label = arm['label']
        trace = np.genfromtxt(artifacts / f'{label}.csv', names=True, delimiter=',', dtype=np.float64)
        pcm = np.fromfile(artifacts / f'{label}.f32le', dtype='<f4')
        checks[f'{label}/finite_and_aligned'] = bool(
            len(pcm) == sample_count and np.isfinite(pcm).all()
            and all(np.isfinite(trace[column]).all() for column in trace.dtype.names)
            and np.array_equal(trace['relative_frame'], expected_frames)
            and np.array_equal(trace['absolute_frame'], expected_frames + arm['schedule_frame'] + lead))
        checks[f'{label}/schedule_and_rate'] = (round(arm['clock_at_schedule_seconds'] * rate) == arm['schedule_frame']
            and round(arm['origin_seconds'] * rate) == arm['schedule_frame'] + lead
            and arm['internal_sample_rate_hz'] == study['internal_rate_hz'])
        if arm['noise_scale'] == 0:
            checks[f'{label}/no_noise_pressure'] = bool(
                not trace['signed_noise_pressure_dyn_cm2'].any() and not trace['dominant_noise_level'].any())
        injection = arm['first_noise_injection']
        first_pressure = first_difference(abs(trace['signed_noise_pressure_dyn_cm2']), 0, expected_frames)
        checks[f'{label}/first_injection_matches_trace'] = (
            first_pressure is None if injection is None else injection['relative_frame'] == first_pressure)
        outputs[arm['noise_scale'], arm['schedule_frame']] = trace, pcm
    for scale in study['noise_scales']:
        for start in study['schedule_engine_frames']:
            checks[f'noise-{scale}/frame-{start}/available'] = (scale, start) in outputs
    plan = relative_segments(output['segments'], 0., rate)
    browser = []
    for clip, browser_path in clips:
        origin = clip['plan']['t0']
        start = clip['scheduleApplied']['appliedFrame']
        checks[f'browser-{start}/relative_plan'] = (
            plan == relative_segments(clip['plan']['segments'], origin, rate)
            and round((clip['plan']['end'] - origin) * rate) == round(output['end_seconds'] * rate))
        trim = round(origin * rate) - clip['armed']['engineFrame']
        saved = np.fromfile(browser_path, dtype='<f4')[trim:]
        (_, native) = outputs[1, start]
        if len(saved) != len(native) or not np.isfinite(saved).all():
            raise ValueError('ブラウザとネイティブの出力範囲が揃いません')
        delta = abs(native.astype(float) - saved)
        browser.append({'schedule_frame': start,
                        'first_bit_difference': first_difference(native.view('<u4') != saved.view('<u4'), 0),
                        'first_frame_over_tolerance': first_difference(delta, study['pcm_difference_floor']),
                        'maximum_pcm_difference': float(delta.max())})
    comparisons = {str(scale): compare_pair(*(outputs[scale, f] for f in study['schedule_engine_frames']), study)
                   for scale in study['noise_scales']}
    nominal_phase = (study['schedule_engine_frames'][1] - study['schedule_engine_frames'][0]) * fixture['source']['f0'] / rate
    normal, muted = comparisons['1'], comparisons['0']
    native_onset = normal['first_pcm_frame_over_tolerance']
    derived_onset = normal['columns']['radiation_derivative_cm3_s2']['first_frame_over_threshold']
    observed_onset = previous['one_quantum_control']['first_sample_over_tolerance']
    predictions = {
        'initial_glottal_phase_advances': abs(normal['phase_advance_before_schedule_cycles'] - nominal_phase)
                                          <= study['phase_advance_tolerance_cycles'],
        'native_difference_near_browser': native_onset is not None
            and abs(native_onset - observed_onset) <= study['maximum_browser_onset_difference_frames'],
        'radiation_differs_by_first_pcm_difference': derived_onset is not None and native_onset is not None
                                                    and derived_onset <= native_onset,
        'phase_and_pcm_differ_with_noise_muted': muted['first_pcm_frame_over_tolerance'] is not None
            and muted['columns']['glottal_phase_cycles']['first_frame_over_threshold'] == int(expected_frames[0]),
    }
    return {'checks': checks, 'predictions': predictions, 'relative_plan_frames': plan,
            'constant_f0_phase_advance_cycles': nominal_phase,
            'first_noise_injection_by_arm': {a['label']: a['first_noise_injection'] for a in output['arms']},
            'comparisons_by_noise_scale': comparisons, 'browser_reference_pcm': browser,
            'browser_first_frame_over_tolerance_between_starts': observed_onset}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = json.loads(CASE.read_text())
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    ref = study['browser_reference']
    reference_case = CASE.parent / ref['case']
    run = run_manifest(ref['run'], json.loads(reference_case.read_text())['id'], revision)
    summary = verified_path(run, 'summary.json')
    previous = json.loads(summary.read_text())
    capture_path = verified_path(run, 'artifacts/capture-input.json')
    capture = json.loads(capture_path.read_text())
    if (run[1]['status'] != 'pass' or not previous['one_quantum_control']['prediction']
            or capture['schedule_engine_frames'] != study['schedule_engine_frames']
            or capture['expected_pcm_samples'] != study['comparison_samples']
            or capture['measurement']['output_rate_hz'] != study['output_rate_hz']):
        parser.error('登録したブラウザ基準と条件が一致しません')
    clips, files = [], []
    for row in previous['trials']:
        if row['mode'] == 'continuous':
            folder = f'artifacts/{row["trial"]}'
            browser = verified_path(run, f'{folder}/browser.json')
            pcm = verified_path(run, f'{folder}/worklet.f32le')
            clips.append((json.loads(browser.read_text()), pcm))
            files.extend([browser, pcm])
    if len(clips) != 2 or any(clip['input'] != clips[0][0]['input'] for clip, _ in clips):
        parser.error('予約位置以外のブラウザ設定が一致しません')
    fixture = {**{key: clips[0][0]['input'][key] for key in ('body', 'source')}, 'score': capture['score']}
    sources = [UPSTREAM / path for path in ('Cargo.lock', 'crates/chimera/src/engine.rs',
        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/airway/network.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/phonetics/sing.rs')]
    inputs = [CASE, PROBE, DICTIONARY, Path(__file__).resolve(), reference_case, run[0] / 'manifest.json',
              summary, capture_path, *files, *sources]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_command': [sys.executable, *sys.argv],
                'analysis_directory': str(Path.cwd()), 'browser_reference_run': ref['run']}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixture, clips, previous, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
