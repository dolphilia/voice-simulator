"""Firefoxの確認用07で、先頭量子のWASM描画とコピー・観測を計測する。"""

import argparse
import os
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess

import measure_lip_crossing_thickness as stored
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM
from measure_worklet_firefox_native_clock import threads, thread_intervals
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_live_song_render_phases import console_timestamps
from measure_worklet_live_tsp_firefox_native_clock import measure_trial, native_rows
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-render-phases.json'
PREFIX = 'chimera-speech-phase:'
MARKER = re.compile(r'(\d+):(\d+):([a-z-]+)')


def read_markers(thread):
    phases, calibration = {}, []
    for name, time in console_timestamps(thread, PREFIX):
        if name == 'calibration':
            calibration.append(time)
            continue
        match = MARKER.fullmatch(name)
        if not match:
            raise ValueError(f'計測マーカーの書式が不正です ({name})')
        frame, offset, label = match.groups()
        row = phases.setdefault(int(frame), {})
        key = (int(offset), label)
        if key in row:
            raise ValueError(f'同じ計測マーカーが重複しました ({name})')
        row[key] = float(time)
    return phases, calibration


def expected_keys(frame, quantum, stride, tract_frames, glottal):
    keys = [(0, 'quantum-start')]
    for offset in range(0, quantum, stride):
        keys.extend((offset, kind) for kind in ('render-start', 'wasm-start', 'wasm-end',
            'pcm-copy-start', 'pcm-copy-end', 'render-end'))
        if glottal:
            keys.extend((offset, kind) for kind in ('glottal-start', 'glottal-end'))
        end = offset + stride
        keys.extend((end, kind) for kind in ('observation-start', 'observation-end'))
        if frame + end - 1 in tract_frames:
            keys.extend((end, kind) for kind in ('tract-start', 'tract-end'))
    keys.extend((quantum, kind) for kind in ('capture-start', 'capture-end', 'quantum-end'))
    return keys


def describe_quantum(marks, quantum, stride, author, outer):
    a, b = map(float, author)
    c, d = map(float, outer)
    result = {'author_ms': b - a, 'outer_ms': d - c}
    if not marks:
        return result

    def elapsed(offset, label):
        start = (offset, label + '-start')
        end = (offset, label + '-end')
        return marks[end] - marks[start] if start in marks else 0.0

    pieces = []
    for offset in range(0, quantum, stride):
        wasm = elapsed(offset, 'wasm')
        pcm = elapsed(offset, 'pcm-copy')
        pieces.append({'offset_frames': offset, 'wasm_ms': wasm, 'pcm_copy_ms': pcm,
                       'render_other_ms': elapsed(offset, 'render') - wasm - pcm,
                       'glottal_copy_ms': elapsed(offset, 'glottal'),
                       'observation_ms': elapsed(offset + stride, 'observation'),
                       'tract_ms': elapsed(offset + stride, 'tract')})
    totals = {key: sum(row[key] for row in pieces) for key in pieces[0] if key != 'offset_frames'}
    totals['capture_ms'] = elapsed(quantum, 'capture')
    return result | totals | {'author_other_ms': b - a - sum(totals.values()), 'pieces': pieces,
                              'markers': [{'offset_frames': offset, 'phase': label, 'time_from_author_start_ms': time - a}
                                          for (offset, label), time in marks.items()]}


def measure_phases(profile, report, clock_spec, spec, enabled):
    evidence, pair = native_rows(profile, report, clock_spec)
    if pair is None:
        return {'checks': {'phase_native_intervals': False}}
    thread, = [t for t in threads(profile) if (t['pid'], t['tid']) ==
               (evidence['selected_thread']['pid'], evidence['selected_thread']['tid'])]
    outer, author = pair
    marks, calibration = read_markers(thread)
    observed = report['observations']
    quantum, stride = report['shortestQuantum'], observed[0][1]
    frames = [quantum * i for i in spec['quantum_indices']]
    tract_frames = {row[0] for row in report.get('tract', {}).get('rows', [])}
    checks = {}
    result = {'checks': checks, 'quanta': []}
    if enabled:
        checks['phase_markers_complete'] = (set(marks) == set(frames) and
            all(list(marks[frame]) == expected_keys(frame, quantum, stride, tract_frames, 'glottal' in report)
                for frame in frames))
        calls, _ = thread_intervals(thread, clock_spec['author_marker'], processor=clock_spec.get('processor'))
        lead_start, lead_end = calls[evidence['startup_and_lead_quanta'] - 1]
        checks['calibration_inside_final_wait_quantum'] = (
            len(calibration) == spec['calibration_markers'] and sorted(calibration) == calibration
            and all(lead_start <= t <= lead_end for t in calibration))
        if len(calibration) > 1:
            steps = [b - a for a, b in zip(calibration[:-1], calibration[1:], strict=True)]
            result['calibration_steps_ms'] = steps
            result['calibration_within_goal'] = max(steps) <= spec['maximum_marker_calibration_step_ms']
    else:
        checks['control_has_no_markers'] = not (marks or calibration)

    for i, frame in zip(spec['quantum_indices'], frames, strict=True):
        local = {}
        if enabled and checks['phase_markers_complete']:
            values = list(marks[frame].values())
            inside = sorted(values) == values and author[i][0] <= values[0] <= values[-1] <= author[i][1]
            checks[f'phases_inside_author_quantum_{i}'] = bool(inside)
            if inside:
                local = marks[frame]
        result['quanta'].append({'index': i, 'output_frame': frame,
                                 **describe_quantum(local, quantum, stride, author[i], outer[i])})
    if enabled and all('wasm_ms' in row for row in result['quanta']):
        first, second, *steady = result['quanta']
        fields = ('outer_ms', 'author_ms', 'wasm_ms', 'pcm_copy_ms', 'observation_ms', 'glottal_copy_ms',
                  'capture_ms', 'tract_ms', 'render_other_ms', 'author_other_ms')
        differences = [{field: row[field] - median(w[field] for w in steady) for field in fields}
                       for row in (first, second)]
        excess = differences[0]
        share = excess['wasm_ms'] / excess['author_ms'] if excess['author_ms'] > 0 else None
        result.update({'early_minus_steady_ms': differences, 'wasm_share_of_first_excess': share,
                       'prediction_met': share is not None and share >= spec['minimum_wasm_share_of_first_excess']})
    return result


def measure(study, native, baseline, paths, profiler, out, execute, bun):
    spec = study['measurement']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'english'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    checks = {'same_built_wasm': sha256(binary) == sha256(paths['vocal_wasm.wasm'])}
    trials = []
    for pair, order in enumerate(spec['condition_order'], 1):
        for condition in order:
            folder = out / f'{pair}-{condition}'
            enabled = condition == 'phases'
            try:
                result = measure_trial(native, baseline, paths, profiler, folder, execute, trace_render_phases=enabled)
                report = read(folder / 'browser.json')
                profile = read(folder / 'firefox-profile.json')
                phases = measure_phases(profile, report, native['measurement'], spec, enabled)
                result['checks'].update(phases.pop('checks'))
                result['phase_measurement'] = phases
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                result = {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}
            trials.append({'pair': pair, 'condition': condition, **result})
            checks.update({f'{folder.name}/{key}': value for key, value in result['checks'].items()})
            for name in ('firefox-profile.json', 'browser.json'):
                p = folder / name
                if p.is_file():
                    stored.compress(p)
    first = {condition: [item['phase_measurement']['quanta'][0]['author_ms'] for item in trials
                         if item['condition'] == condition and item.get('phase_measurement', {}).get('quanta')]
             for condition in ('control', 'phases')}
    shift = abs(median(first['phases']) - median(first['control'])) if all(first.values()) else None
    return {'checks': checks, 'trials': trials, 'first_author_times_ms': first,
            'median_first_author_shift_ms': shift,
            'median_first_author_shift_within_goal': shift is not None and shift <= spec['maximum_median_first_author_shift_ms']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    native_run = hydrate_run(study['native_run'], study['native_case'], rev)
    native_case = snapshot_case(native_run, study['native_case'])
    native = read(native_case)
    run = hydrate_run(native['baseline_run'], native['baseline_case'], rev)
    baseline = snapshot_case(run, native['baseline_case'])
    profiler_case = WORKSPACE / 'cases' / native['gecko_profile_case']
    paths = {key: verified_file(*run, f'artifacts/firefox/{key}') for key in
             ('browser-case.json', 'browser.json', 'browser.wav')}
    paths['vocal_wasm.wasm'] = verified_file(*run, 'artifacts/vocal_wasm.wasm')
    prior = verified_file(*native_run, 'summary.json')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), baseline, native_case, profiler_case, prior,
              run[0] / 'manifest.json', native_run[0] / 'manifest.json', *paths.values(),
              *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py',
                'measure_worklet_live_tsp_firefox_native_clock.py', 'measure_worklet_live_tsp_source_defaults.py',
                'measure_worklet_live_song_render_phases.py', 'measure_worklet_song_firefox_registration_native.py',
                'measure_worklet_live_ipa_cross_browser.py', 'measure_worklet_firefox_native_clock.py',
                'measure_wasm_fixed.py',
                'measure_worklet_fixed.py', 'measure_worklet_realtime.py', 'measure_tsp_listening.py',
                'measure_lip_crossing_thickness.py', 'measure_speech_timing.py', 'measure_csd_envelope_timing.py',
                'upstream_baseline.py'))]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'firefox_override': os.environ.get('CHIMERA_FIREFOX')}

    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(study, native, baseline, paths, read(profiler_case)['measurement'], out, execute, bun),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
