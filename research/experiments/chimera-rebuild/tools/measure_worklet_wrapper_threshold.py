"""96 kHzの固定発声でJS→WASMラッパーのコンパイル回数を対照する。"""

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import measure_worklet_release_alignment as release


CASE = release.WORKSPACE / 'cases/worklet-wasm-wrapper-threshold.json'


def inspect_trace(spec, path, report, trial, expected):
    events = release.stored.read(path)['traceEvents']
    release.stored.compress(path)
    return summarize_trace(spec, events, report, trial, expected)


def summarize_trace(spec, events, report, trial, expected):
    callback_name, compile_name = spec['callback_event'], spec['wrapper_event']
    by_thread = defaultdict(list)
    compilations = []
    for event in events:
        if event['ph'] != 'X':
            continue
        if event['name'] == callback_name:
            by_thread[(event['pid'], event['tid'])].append(event)
        elif event['name'] == compile_name:
            compilations.append(event)
    startup = report['startupCallbacks']
    count = len(report['observations'])
    matching = [key for key, callbacks in by_thread.items() if len(callbacks) == startup + count]
    detail = {'expected_quantum': expected, 'startup_callbacks': startup, 'recorded_quanta': count,
              'trace_event_count': len(events), 'trace_data_loss': trial.get('traceDataLoss'),
              'callback_counts_by_thread': [{'pid': pid, 'tid': tid, 'count': len(callbacks)}
                                            for (pid, tid), callbacks in by_thread.items()],
              'compile_events_in_trace': len(compilations)}
    checks = {'complete_trace_alignment': len(matching) == 1 and trial.get('traceDataLoss') is False,
              'wrapper_compilation_at_expected_quantum': False}
    if len(matching) != 1:
        return checks, detail
    pid, tid = matching[0]
    # WorkletStartup.ready が false を返した分だけ、先頭にPCM採取前の処理がある。
    all_callbacks = sorted(by_thread[(pid, tid)], key=lambda item: item['ts'])
    callbacks = all_callbacks[startup:]
    compilations = [event for event in compilations if (event['pid'], event['tid']) == (pid, tid)]
    first_callback = all_callbacks[0]['ts']
    prior = [{'compile_us': event['dur'], 'gap_to_first_callback_us': first_callback - event['ts'] - event['dur']}
             for event in compilations if event['ts'] + event['dur'] <= first_callback]
    hits = []
    overruns = []
    budget_us = 1e6 * report['observations'][0][1] / report['sampleRate']
    for index, callback in enumerate(callbacks):
        began, duration = callback['ts'], callback['dur']
        if duration > budget_us:
            overruns.append({'quantum': index, 'callback_us': duration})
        hits.extend({'quantum': index, 'callback_us': duration, 'compile_us': event['dur'],
                     'compile_offset_us': event['ts'] - began,
                     'worklet_report_ms': report['observations'][index][2]}
                    for event in compilations
                    if began <= event['ts'] and event['ts'] + event['dur'] <= began + duration)
    detail.update({'audio_thread': {'pid': pid, 'tid': tid},
                   'compile_events_on_audio_thread': len(compilations), 'render_compile_events': hits,
                   'pre_callback_compile_events': prior,
                   'first_recorded_callback_us': callbacks[0]['dur'],
                   'thousandth_recorded_callback_us': callbacks[999]['dur'],
                   'budget_us': budget_us, 'over_budget_callbacks': overruns})
    if expected is None:
        checks['wrapper_compilation_before_callbacks'] = len(compilations) == len(prior) == 1
        checks.pop('wrapper_compilation_at_expected_quantum')
    else:
        checks['wrapper_compilation_at_expected_quantum'] = (
            len(hits) == 1 and abs(hits[0]['quantum'] - expected) <= spec['window_radius_quanta'])
    return checks, detail


def compare_warmup(report, detail, requested):
    warmup = report.get('wrapperWarmup', {})
    first_recorded_frame = int(report['observations'][0][0])
    first_callback_frame = report['startupFirstContextFrame']
    diagnostic = {'worklet': warmup, 'clock': report['timingClock'],
                  'startup_first_context_frame': first_callback_frame,
                  'recorded_first_context_frame': first_recorded_frame,
                  'startup_discontinuities': report['startupDiscontinuities'],
                  'voicing_notice_ms': report['voicingNoticeMs']}
    observations = release.np.asarray(report['observations'], dtype='<f8')
    diagnostic['sound_state_sha256'] = hashlib.sha256(observations[:, 4:].tobytes()).hexdigest()
    checks = {'one_audio_thread_compilation': detail.get('compile_events_on_audio_thread') == 1,
              'requested_warmup_executed': warmup.get('calls') == requested,
              'initialization_timing_recorded': (
                  0 <= warmup.get('contextFrame', -1) <= first_callback_frame <= first_recorded_frame
                  and warmup.get('engineInitializationMs', -1) >= 0 and warmup.get('warmupMs', -1) >= 0
                  and report['voicingNoticeMs'] is not None and report['voicingNoticeMs'] >= 0)}
    return checks, diagnostic


def measure(study, preceding, reference, source, artifacts, execute, bun, *,
            prior_pcm=None, prior_state=None, inspect_capture=inspect_trace):
    spec = study['measurement']
    profile = study['profile']
    settings = preceding['measurement']
    execute([*bun, 'run', 'build'], cwd=release.WEB, stdout=artifacts / 'browser-build.log')
    wasm = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(release.WORKSPACE / release.wasm.WASM, wasm)
    binary_hash = release.sha256(wasm)
    probe = release.shared.build_upstream_probe(release.vowel.PROBE, artifacts, execute)
    start, stop, frames = release.profile_sizes(preceding, settings['profiles'][profile])

    checks = {}
    trials = []
    warmup_calls = spec.get('warmup_calls')
    with TemporaryDirectory(prefix='reference-renderer-', dir=artifacts) as temporary:
        intermediate = Path(temporary)
        _, blocks, rate, native, upper, tables = release.realtime.render_replay(
            source, reference, intermediate, execute, start, stop, frames, upstream_probe=probe)
        checks['native_partition_invariance'] = all(
            release.sha256(blocks[settings['quantum_frames']][i]) == release.sha256(blocks[77][i])
            for i in (0, 1))
        shutil.copyfile(intermediate / 'replay-case.json', artifacts / 'reference-replay-case.json')
        for round_index, order in enumerate(spec['capture_order'], start=1):
            for label in order:
                name = f'{round_index}-{label}'
                folder = artifacts / name
                folder.mkdir()
                capture_case = folder / 'capture-case.json'
                capture_settings = {**settings, 'capture_order': [[profile]],
                                    'trace_categories': spec['trace_categories']}
                if warmup_calls is None:
                    capture_settings['wrapper_tiering_budget'] = spec['budgets'][label]
                else:
                    capture_settings['wasm_render_warmup_calls'] = warmup_calls[label]
                if 'marker' in spec:
                    capture_settings['marker'] = spec['marker']
                trace_spec = spec
                if 'dsp_warmup_frames' in spec:
                    frames_to_discard = spec['dsp_warmup_frames'][label]
                    capture_settings['wasm_dsp_warmup_frames'] = frames_to_discard
                    trace_spec = {**spec, 'expected_dsp_warmup_frames': frames_to_discard}
                if 'finalization_modes' in spec:
                    finalization_mode = spec['finalization_modes'][label]
                    capture_settings['finalization_probe'] = finalization_mode
                    trace_spec = {**trace_spec, 'expected_finalization_mode': finalization_mode}
                capture_case.write_text(json.dumps({**preceding, 'measurement': capture_settings},
                                                   ensure_ascii=False, indent=2) + '\n')
                execute(['node', str(release.CAPTURE), str(folder), str(capture_case)])
                browser = release.stored.read(folder / 'browser-run.json')
                trial, = browser['trials']
                capture = folder / trial['artifactId']
                path = capture / 'trace.json'
                local = {'trace_saved': path.is_file()}
                detail = {}
                variant = {}
                if path.is_file():
                    if 'error' in trial:
                        release.stored.compress(path)
                    else:
                        report = release.stored.read(capture / 'browser.json')
                        trace_checks, detail = inspect_capture(trace_spec, path, report, trial,
                                                              spec['expected_zero_based_quantum'][label])
                        local.update(trace_checks)
                        if warmup_calls is not None:
                            warmup_checks, variant = compare_warmup(report, detail, warmup_calls[label])
                            local.update(warmup_checks)
                normal, result = release.compare_trial(preceding, reference, trial, folder,
                                                       (rate, native, upper, *tables), binary_hash)
                checks.update({f'{name}/{key}': value for key, value in {**local, **normal}.items()})
                metadata = {'tiering_budget': spec['budgets'][label]} if warmup_calls is None else {
                    'warmup_calls': warmup_calls[label], 'initialization': variant}
                trials.append({**result, **metadata, 'round': round_index, 'artifactId': name, 'trace': detail})
    if warmup_calls is not None:
        state_hashes = {trial.get('initialization', {}).get('sound_state_sha256') for trial in trials}
        checks['all_sound_states_bit_identical'] = len(state_hashes) == 1 and None not in state_hashes
        checks['all_pcm_matches_previous_cold_run'] = bool(prior_pcm) and all(
            trial.get('browser_pcm_sha256') == prior_pcm for trial in trials)
        if prior_state is not None:
            checks['all_sound_states_match_solo'] = state_hashes == {prior_state}
    if 'finalization_modes' in spec:
        post_times = {'transfer': [], 'copy': []}
        for trial in trials:
            finish = trial['trace'].get('finalization', {})
            if 'phase_wall_us' in finish and not finish['free_prepared']:
                post_times[finish['mode']].append(finish['phase_wall_us']['post_message'])
        checks['copy_post_median_exceeds_transfer'] = bool(
            post_times['transfer'] and post_times['copy']
            and release.np.median(post_times['copy']) > release.np.median(post_times['transfer']))
    return {'checks': checks, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = release.stored.read(CASE)
    preceding_path = release.WORKSPACE / 'cases' / study['release_case']
    preceding = release.stored.read(preceding_path)
    reference_path = release.WORKSPACE / 'cases' / preceding['reference_case']
    reference = release.stored.read(reference_path)
    source = release.WORKSPACE / 'cases' / reference['fixed_voice_case']
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=release.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=release.UPSTREAM, text=True)
            or preceding['upstream_revision'] != revision or reference['upstream_revision'] != revision
            or release.sha256(source) != reference['fixed_voice_sha256']):
        parser.error('固定上流または固定発声の入力を照合できません')
    prior, manifest = release.saved.load_saved_run(
        study['release_run'], preceding['id'], revision, ['summary.json'])
    recorded, = (row['sha256'] for row in release.stored.read(manifest)['inputs']
                 if row['path'].endswith('/' + preceding_path.name))
    if recorded != release.sha256(preceding_path):
        parser.error('呼気停止対照で用いたケースのハッシュが一致しません')
    release.validate_registration(preceding, reference)
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), preceding_path, reference_path, source, manifest, *prior.values(),
              *release.web_sources(), *release.shared.candidate_sources(), release.vowel.PROBE,
              *(Path(module.__file__) for module in (release, release.stored, release.saved, release.shared,
                release.wasm, release.realtime, release.realtime.pcm, release.vowel))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return release.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda a, run: measure(study, preceding, reference, source, a, run, bun),
        command=None, input_root=release.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
