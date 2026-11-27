"""確認用07のWorklet時計を、同じFirefox再生のネイティブ区間に照合する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_lip_crossing_thickness as stored
from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_firefox_native_clock import thread_intervals, threads
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_live_ipa_cross_browser import fingerprints, profiler_command
from measure_worklet_live_tsp_source_defaults import clock_checks
from measure_worklet_realtime import timing_summary
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-tsp-firefox-native-clock.json'


def ordered_intervals(intervals):
    return (np.isfinite(intervals).all() and bool(np.all(intervals[:, 1] >= intervals[:, 0]))
            and bool(np.all(intervals[1:, 0] >= intervals[:-1, 1])))


def native_rows(profile, report, spec):
    live = report['realtime']
    warmup_wait = live['startupCallbacks'] + live['leadCallbacks']
    expected = warmup_wait + len(live['blocks'])
    counts, matches = [], []
    for thread in threads(profile):
        spans, _ = thread_intervals(thread, spec['engine_marker'])
        calls, _ = thread_intervals(thread, spec['author_marker'], processor=spec.get('processor'))
        if not (spans or calls):
            continue
        counted = {'name': thread['name'], 'pid': thread['pid'], 'tid': thread['tid'],
                   'process_blocks': len(spans), 'author_calls': len(calls)}
        counts.append(counted)
        if len(calls) != expected or len(spans) < expected:
            continue
        outer, inner = np.asarray(spans, dtype='f8'), np.asarray(calls, dtype='f8')
        if not ordered_intervals(outer) or not ordered_intervals(inner):
            continue
        indices = np.searchsorted(outer[:, 1], inner[:, 1])
        if (np.any(indices == len(outer)) or np.any(np.diff(indices) <= 0)
                or np.any(inner[:, 0] < outer[indices, 0])):
            continue
        match = counted | {'engine_blocks_without_author': len(outer) - len(inner),
                           'unpaired_engine_blocks_between_author_calls': int(indices[-1] - indices[0] + 1 - expected)}
        first, last = warmup_wait, expected
        matches.append((match, outer[indices[first:last]], inner[first:last]))
    evidence = {'expected_author_calls': expected, 'startup_and_lead_quanta': warmup_wait,
                'matched_threads': len(matches), 'threads': counts}
    if len(matches) != 1:
        return evidence, None
    match, outer, inner = matches[0]
    return evidence | {'selected_thread': match}, (outer, inner)


def compare_times(profile, report, spec, folder):
    evidence, pair = native_rows(profile, report, spec)
    if pair is None:
        return {'checks': {'unique_native_intervals': False}, 'mapping': evidence}
    outer, inner = pair
    blocks = np.asarray(report['realtime']['blocks'], dtype='f8')
    date = blocks[:, 3]
    native = outer[:, 1] - outer[:, 0]
    author = inner[:, 1] - inner[:, 0]
    gaps_date, gaps_native = np.diff(blocks[:, 4]), np.diff(outer[:, 0])
    mean_error = float(np.mean(np.abs(gaps_date - gaps_native)))
    shifted = [float(np.mean(np.abs(gaps_date[1:] - gaps_native[:-1]))),
               float(np.mean(np.abs(gaps_date[:-1] - gaps_native[1:])))]
    budget = 1000 * float(blocks[0, 1]) / report['sampleRate']
    warm = spec['warmup_quanta']
    frames = np.r_[0, blocks[:-1, 2]].astype(int)
    data = np.column_stack((np.arange(len(blocks)), frames, blocks[:, 0], date, outer, inner, native, author))
    np.savetxt(folder / 'aligned-quanta.csv', data, delimiter=',', fmt=('%d',) * 3 + ('%.9f',) * 7,
               header='quantum,output_frame,context_frame,date_ms,engine_start_ms,engine_end_ms,'
                      'call_start_ms,call_end_ms,engine_ms,call_ms', comments='')

    def classify(window):
        date_over, engine_over, call_over = (x[window] > budget for x in (date, native, author))
        frames_in_window = frames[window]
        return {
            'date_only_frames': frames_in_window[date_over & ~engine_over].tolist(),
            'both_engine_and_date_frames': frames_in_window[date_over & engine_over].tolist(),
            'engine_only_frames': frames_in_window[engine_over & ~date_over].tolist(),
            'author_frames': frames_in_window[call_over].tolist(),
        }

    warmed = slice(warm, None)
    timing = {name: {'all': timing_summary(x, budget), 'warmed': timing_summary(x[warmed], budget)}
              for name, x in (('date', date), ('engine', native), ('author', author))}
    classification = {'all': classify(slice(None)), 'warmed': classify(warmed)}
    p99 = timing['engine']['warmed']['p99_ms']
    return {
        'checks': {
            'unique_native_intervals': True,
            'match_supported_by_callback_gaps': mean_error <= spec['callback_gap_max_mean_error_ms']
            and mean_error < min(shifted),
        },
        'mapping': evidence, 'quantum_budget_ms': budget,
        'mean_callback_gap_error_ms': mean_error, 'one_quantum_shift_error_ms': shifted,
        'timing': timing, 'classification': classification,
        'hypothesis': {'warmed_native_p99_within_budget': p99 <= budget,
                       'date_over_budget_while_engine_within_budget': bool(classification['warmed']['date_only_frames'])},
    }


def measure_trial(study, baseline, paths, prof, folder, execute, *,
                  trace_render_phases=False, wasm_override=None, trace_wasm_core=False, preparation=None,
                  marker=None, delay_one_quantum=False):
    spec = study['measurement']
    folder.mkdir()
    profile = folder / 'firefox-profile.json'
    run_browser = ['node', str(CAPTURE), str(folder), str(baseline), str(paths['browser-case.json']),
                   'firefox', '--native-clock']
    if trace_render_phases:
        run_browser.append('--trace-phases')
    if wasm_override is not None:
        run_browser.append(f'--wasm-probe={wasm_override}')
    if trace_wasm_core:
        run_browser.append('--trace-wasm-core')
    if preparation is not None:
        run_browser.append(f'--speech-preparation={preparation}')
    if delay_one_quantum:
        run_browser.append('--speech-delay-one-quantum')
    if marker is not None:
        settings = folder / 'marker-settings.json'
        settings.write_text(json.dumps(marker, ensure_ascii=False) + '\n')
        run_browser.append(f'--speech-marker={settings}')
    execute(profiler_command(run_browser, folder, prof), stdout=folder / 'browser-command.log')
    report = read(folder / 'browser.json')
    web = read(folder / 'browser-run.json')
    source = read(paths['browser.json'])
    rate, pcm = wavfile.read(folder / 'browser.wav')
    ref_rate, expected = wavfile.read(paths['browser.wav'])
    if pcm.dtype != np.float32 or pcm.shape != expected.shape or not np.isfinite(pcm).all():
        raise ValueError('PCMの形式、長さ、有限性を確認できません')
    reference_hash = sha256(paths['vocal_wasm.wasm'])
    result = compare_times(read(profile), report, spec, folder)
    limits = read(baseline)['measurement']
    if delay_one_quantum:
        limits['lead_frames'] += limits['render_quantum_frames']
    clock = clock_checks(limits, report, pcm)
    result['checks'].update({
        'registered_browser_and_assets': web['engine'] == 'firefox' and web['recovered'] and not web['errors']
        and web['servedWasmSha256'] == reference_hash and web['compiledWasm'] == [reference_hash],
        'registered_case_and_states': read(folder / 'browser-case.json') == read(paths['browser-case.json'])
        and fingerprints(report, pcm) == fingerprints(source, expected),
        'registered_pcm': rate == ref_rate and compare_pcm(pcm, expected, 0)['first_bit_difference_frame'] is None,
        'ordinary_clock': all(clock['checks'].values()),
    })
    result['browser'] = web['version']
    result['clock'] = clock['clock']
    return result


def measure(study, baseline, paths, prof, out, execute, bun):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'english'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    checks = {'same_built_wasm': sha256(binary) == sha256(paths['vocal_wasm.wasm'])}
    trials = []
    for i in range(1, study['measurement']['trials'] + 1):
        folder = out / f'firefox-{i}'
        try:
            result = measure_trial(study, baseline, paths, prof, folder, execute)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            result = {'checks': {'capture_and_comparison_completed': False}, 'error': str(error)}
        trials.append({'trial': i, **result})
        checks.update({f'{folder.name}/{k}': v for k, v in result['checks'].items()})
        for p in (folder / 'firefox-profile.json', folder / 'browser.json'):
            if p.is_file():
                stored.compress(p)
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    run = hydrate_run(study['baseline_run'], study['baseline_case'], rev)
    baseline = snapshot_case(run, study['baseline_case'])
    profile_case = WORKSPACE / 'cases' / study['gecko_profile_case']
    paths = {key: verified_file(*run, f'artifacts/firefox/{key}') for key in
             ('browser-case.json', 'browser.json', 'browser.wav')}
    paths['vocal_wasm.wasm'] = verified_file(*run, 'artifacts/vocal_wasm.wasm')
    old_summary = verified_file(*run, 'summary.json')
    stored_clock = read(old_summary)['browsers']['firefox']['timing']
    limits = read(baseline)['measurement']
    if limits['timing_skip_blocks'] != study['measurement']['warmup_quanta']:
        parser.error('定常区間が通常再生の登録と一致しません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), baseline, profile_case, old_summary, run[0] / 'manifest.json',
              *paths.values(), *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'measure_wasm_fixed.py',
                'measure_worklet_fixed.py', 'measure_worklet_realtime.py', 'measure_worklet_live_tsp_source_defaults.py',
                'measure_worklet_live_ipa_cross_browser.py', 'measure_worklet_firefox_native_clock.py',
                'measure_lip_crossing_thickness.py', 'measure_tsp_listening.py', 'measure_speech_timing.py',
                'measure_csd_envelope_timing.py', 'upstream_baseline.py'))]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
               'firefox_override': os.environ.get('CHIMERA_FIREFOX')}

    def collect(out, execute):
        result = measure(study, baseline, paths, read(profile_case)['measurement'], out, execute, bun)
        return result | {'ordinary_capture_timing': stored_clock}

    return record_measurement(args.run_id, CASE, inputs, details, collect, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
