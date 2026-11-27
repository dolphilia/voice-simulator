"""確認用07で、WASM内の調音制御と気道伝搬の一部を計時する。"""

import argparse
import os
from pathlib import Path
from statistics import median
import shutil
import subprocess

import measure_lip_crossing_thickness as stored
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM
from measure_worklet_firefox_native_clock import threads
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_live_song_render_phases import console_timestamps
from measure_worklet_live_tsp_firefox_native_clock import measure_trial, native_rows
from measure_worklet_live_tsp_firefox_render_phases import measure_phases
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-wasm-core-phases.json'
PROBE_TARGET = Path('/Volumes/RTL9210B-CG/voice-simulator/build/chimera-render-phase-probe')
PREFIX = 'chimera-speech-core:'


def read_core_marks(thread, author_start):
    marks = {}
    for label, time in console_timestamps(thread, PREFIX):
        frame, offset, phase, internal = map(int, label.split(':'))
        if frame not in author_start:
            raise ValueError(f'登録区間外にWASMの計時点があります ({label})')
        group = marks.setdefault((frame, offset), {})
        key = (phase, internal)
        if key in group:
            raise ValueError(f'WASM内の計時点が重複しています ({label})')
        group[key] = float(time - author_start[frame])
    return marks


def describe_slice(points, control, stride, factor, sample_offsets, wasm_start, wasm_end):
    expected = [(0, 0)]
    if control:
        expected += [(2, 0), (3, 0)]
    expected += [(phase, i) for i in sample_offsets for phase in (4, 5)]
    expected += [(1, stride * factor)]
    times = list(points.values())
    inside = (list(points) == expected and sorted(times) == times
              and wasm_start <= times[0] <= times[-1] <= wasm_end)
    if not inside:
        return {'valid': False, 'expected_markers': expected, 'observed_markers': list(points),
                'outer_wasm_ms': [wasm_start, wasm_end], 'observed_times_ms': times}
    loop_ms = points[1, stride * factor] - points[0, 0]
    control_ms = points[3, 0] - points[2, 0] if control else 0.0
    airway = [{'internal_offset': i, 'ms': points[5, i] - points[4, i]} for i in sample_offsets]
    return {'valid': True, 'loop_ms': loop_ms, 'control_ms': control_ms, 'loop_without_control_ms': loop_ms - control_ms,
            'sampled_airway_steps': airway,
            'markers': [{'phase': phase, 'internal_offset': i, 'time_from_author_start_ms': time}
                        for (phase, i), time in points.items()]}


def analyze_core(profile, report, host, native_spec, spec, enabled, factor):
    evidence, pair = native_rows(profile, report, native_spec)
    if pair is None:
        return {'checks': {'core_native_intervals': False}}
    thread, = [t for t in threads(profile) if (t['pid'], t['tid']) ==
               (evidence['selected_thread']['pid'], evidence['selected_thread']['tid'])]
    author = pair[1]
    quantum = report['shortestQuantum']
    stride = spec['output_frames_per_call']
    starts = {i * quantum: float(author[i][0]) for i in spec['quantum_indices']}
    marks = read_core_marks(thread, starts)
    if not enabled:
        return {'checks': {'no_core_markers': not marks}}

    expected_slices = {(frame, offset) for frame in starts for offset in range(0, quantum, stride)}
    checks = {'all_core_slices_marked': set(marks) == expected_slices,
              'registered_host_stride': report['observations'][0][1] == stride}
    quanta = []
    for row in host['quanta']:
        frame = row['output_frame']
        host_marks = {(r['offset_frames'], r['phase']): r['time_from_author_start_ms'] for r in row.get('markers', ())}
        slices = []
        for offset in range(0, quantum, stride):
            begin, end = (host_marks.get((offset, 'wasm-' + name)) for name in ('start', 'end'))
            if begin is not None and end is not None:
                desc = describe_slice(marks.get((frame, offset), {}),
                    (frame + offset) % spec['control_output_interval'] == 0, stride, factor,
                    spec['internal_offsets_for_airway_step'], begin, end)
            else:
                desc = {'valid': False}
            slices.append({'output_offset': offset, **desc})
        checks[f'core_markers_ordered_and_contained_{frame}'] = all(r['valid'] for r in slices)
        q = {'output_frame': frame, 'slices': slices}
        if checks[f'core_markers_ordered_and_contained_{frame}']:
            q |= {key: sum(r[key] for r in slices) for key in ('loop_ms', 'control_ms', 'loop_without_control_ms')}
        quanta.append(q)
    result = {'checks': checks, 'quanta': quanta}
    if all(checks.values()):
        first, _, *steady = quanta
        keys = ('loop_ms', 'control_ms', 'loop_without_control_ms')
        delta = {key: first[key] - median(row[key] for row in steady) for key in keys}
        share = delta['control_ms'] / delta['loop_ms'] if delta['loop_ms'] > 0 else None
        result |= {'first_minus_steady_ms': delta, 'control_share_of_loop_excess': share,
                   'control_explains_at_least_half': share is not None and share >= 0.5}
    return result


def measure(study, phase, native, baseline, paths, profiler, out, execute, bun):
    spec = study['measurement']
    limits = read(baseline)['measurement']
    factor = limits['internal_rate_hz'] // limits['output_rate_hz']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'english'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-wasm',
             '--features', 'render-phase-probe', '--target', 'wasm32-unknown-unknown',
             '--target-dir', str(PROBE_TARGET)], stdout=out / 'probe-build.log')
    stock = out / 'vocal_wasm.wasm'
    probe = out / 'vocal_wasm_probe.wasm'
    shutil.copyfile(WORKSPACE / WASM, stock)
    shutil.copyfile(PROBE_TARGET / Path(WASM).relative_to('target'), probe)
    checks = {'distinct_stock_and_probe_wasm': sha256(stock) != sha256(probe)}
    trials = []
    for pair, order in enumerate(spec['condition_order'], 1):
        for condition in order:
            folder = out / f'{pair}-{condition}'
            override = None if condition == 'stock' else probe
            try:
                result = measure_trial(native, baseline, paths | {'vocal_wasm.wasm': override or stock}, profiler,
                                       folder, execute, trace_render_phases=True, wasm_override=override,
                                       trace_wasm_core=condition == 'core')
                report = read(folder / 'browser.json')
                profile = read(folder / 'firefox-profile.json')
                host = measure_phases(profile, report, native['measurement'], phase['measurement'], True)
                core = analyze_core(profile, report, host, native['measurement'], spec, condition == 'core', factor)
                result['checks'].update(host.pop('checks'))
                result['checks'].update(core.pop('checks'))
                result |= {'host_phases': host, 'core_phases': core}
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                result = {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}
            trials.append({'pair': pair, 'condition': condition, **result})
            checks.update({f'{folder.name}/{key}': value for key, value in result['checks'].items()})
            for name in ('firefox-profile.json', 'browser.json'):
                p = folder / name
                if p.is_file():
                    stored.compress(p)
    first = {condition: [t['host_phases']['quanta'][0]['author_ms'] for t in trials
                         if t['condition'] == condition and t.get('host_phases', {}).get('quanta')]
             for condition in ('stock', 'control', 'core')}
    shifts = {}
    for base, measured in (('stock', 'control'), ('control', 'core')):
        if first[base] and first[measured]:
            delta = median(first[measured]) - median(first[base])
            shifts[f'{base}_to_{measured}'] = {'median_shift_ms': delta,
                'within_goal': abs(delta) <= spec['maximum_first_quantum_median_shift_ms']}
    return {'checks': checks, 'trials': trials, 'first_author_times_ms': first, 'timing_shifts': shifts,
            'stock_wasm_matches_previous': sha256(stock) == sha256(paths['vocal_wasm.wasm'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    phase_run = hydrate_run(study['phase_run'], study['phase_case'], rev)
    phase_case = snapshot_case(phase_run, study['phase_case'])
    phase = read(phase_case)
    native_run = hydrate_run(phase['native_run'], phase['native_case'], rev)
    native_case = snapshot_case(native_run, phase['native_case'])
    native = read(native_case)
    normal = hydrate_run(native['baseline_run'], native['baseline_case'], rev)
    baseline = snapshot_case(normal, native['baseline_case'])
    profiler_case = WORKSPACE / 'cases' / native['gecko_profile_case']
    paths = {key: verified_file(*normal, f'artifacts/firefox/{key}') for key in
             ('browser-case.json', 'browser.json', 'browser.wav')}
    paths['vocal_wasm.wasm'] = verified_file(*normal, 'artifacts/vocal_wasm.wasm')
    spec = study['measurement']
    if (spec['quantum_indices'] != phase['measurement']['quantum_indices']
            or spec['output_frames_per_call'] != read(baseline)['measurement']['observation_stride_frames']):
        parser.error('従来の量子番号と観測間隔を照合できません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), phase_case, native_case, baseline, profiler_case,
              *(run[0] / 'manifest.json' for run in (phase_run, native_run, normal)), *paths.values(),
              *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py',
                'measure_worklet_live_tsp_firefox_render_phases.py', 'measure_worklet_live_tsp_firefox_native_clock.py',
                'measure_worklet_live_tsp_source_defaults.py', 'measure_worklet_live_song_render_phases.py',
                'measure_worklet_song_firefox_registration_native.py', 'measure_worklet_live_ipa_cross_browser.py',
                'measure_worklet_firefox_native_clock.py', 'measure_wasm_fixed.py', 'measure_worklet_fixed.py',
                'measure_worklet_realtime.py', 'measure_tsp_listening.py', 'measure_lip_crossing_thickness.py',
                'measure_speech_timing.py', 'measure_csd_envelope_timing.py', 'upstream_baseline.py'))]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'firefox_override': os.environ.get('CHIMERA_FIREFOX')}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        study, phase, native, baseline, paths, read(profiler_case)['measurement'], out, execute, bun),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
