"""共有WASMの応答を保留した英語発話の停止・再開を照合する。"""

import argparse
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_live_tsp_rate import same_states, wave
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-shared-wasm-abort-44100.json'
CAPTURE = WEB / 'tools/capture-shared-english-wasm-abort.mjs'


def compare_output(folder, name, reference, reference_pcm, upper_pcm, limits):
    wav_path, json_path = (folder / f'{name}.{extension}' for extension in ('wav', 'json'))
    if not wav_path.is_file() or not json_path.is_file():
        return {f'{name}_produced_outputs': False}, {}
    pcm = wave(wav_path, limits['output_rate_hz'], limits['output_frames'])
    report = read(json_path)
    nonzero = np.flatnonzero(pcm)
    first = int(nonzero[0]) if nonzero.size else None
    comparison = compare_pcm(pcm, upper_pcm, limits['upstream_pcm_absolute_tolerance'])
    return {
        f'{name}_pcm_matches_saved_reference': np.array_equal(pcm.view('u4'), reference_pcm.view('u4')),
        f'{name}_plan_and_observations_match': same_states(report, reference)
        and all(report[key] == reference[key] for key in ('speech', 'gestures', 'tract')),
        f'{name}_render_clock_matches_case': report['sampleRate'] == report['workletSampleRate'] == limits['output_rate_hz']
        and report['shortestQuantum'] == report['longestQuantum'] == limits['render_quantum_frames']
        and report['framesRendered'] == limits['output_frames'] and first == limits['first_nonzero_frame'],
        f'{name}_pcm_is_within_fixed_upstream_tolerance': comparison['first_frame_over_tolerance'] is None,
    }, {'first_nonzero_frame': first, 'upstream_pcm': comparison}


def compare_browser(folder, engine, limits, references, wasm_hash):
    evidence = read(folder / 'abort-evidence.json')
    before, held, offline, restarted = (
        evidence[key] for key in ('beforeStop', 'whileHeld', 'afterOffline', 'afterRestart'))
    events = evidence['events']
    times = {item['name']: item['ms'] for item in events}
    ordered_names = ('stopped_start', 'wasm_fetch', 'offline_start', 'stop_requested',
                     'stopped_rejected', 'response_allowed', 'wasm_compile',
                     'planner_created', 'offline_fulfilled', 'restarted_start', 'restarted_fulfilled')
    ordered_times = [times.get(name) for name in ordered_names]
    expected_rate = limits['output_rate_hz']
    closed_first = {'state': 'closed', 'rate': expected_rate, 'nodes': 0}
    checks = {
        'browser_and_page_are_healthy': engine == evidence['engine'] and not evidence['pageErrors'],
        'calls_overlap_while_wasm_is_held': before['calls'] == {
            'stopped': {'outcome': 'pending'}, 'offline': {'outcome': 'pending'}}
        and before['fetches'] == 1 and before['compilations'] == before['planners'] == 0,
        'stop_closes_only_realtime_context_before_response': evidence['stoppedWhileHeld']
        and held['calls']['stopped']['outcome'] == 'rejected' and held['calls']['stopped']['error'] == 'AbortError'
        and held['contexts'] == [closed_first] and held['calls']['offline'] == {'outcome': 'pending'}
        and held['offlineNodes'] == [] and held['compilations'] == held['planners'] == 0,
        'surviving_offline_call_completes_after_response': evidence['offlineSettled']
        and offline['calls']['offline'] == {'outcome': 'fulfilled'}
        and offline['offlineNodes'] == [expected_rate] and offline['contexts'] == [closed_first],
        'restarted_call_uses_its_own_context': evidence['restartedSettled']
        and restarted['calls']['restarted'] == {'outcome': 'fulfilled'}
        and restarted['contexts'] == [closed_first, {'state': 'closed', 'rate': expected_rate, 'nodes': 1}]
        and restarted['offlineNodes'] == [expected_rate],
        'both_outputs_reuse_one_original_module_and_planner': evidence['routeRequests'] == 1
        and evidence['compiledSha256'] == [wasm_hash]
        and all(stage['fetches'] == stage['compilations'] == stage['planners'] == 1 for stage in (offline, restarted)),
        'observed_events_are_ordered': None not in ordered_times and ordered_times == sorted(ordered_times)
        and all(sum(item['name'] == name for item in events) == 1 for name in ordered_names),
    }
    upper = np.fromfile(references['upstream.f32le'], dtype='<f4')
    if upper.shape != (limits['output_frames'],) or not np.isfinite(upper).all():
        raise ValueError('固定上流のPCMの長さまたは有限性を確認できません')
    timings = {}
    for name, stem in (('offline', 'offline'), ('restarted', 'browser')):
        old_pcm = wave(references[f'{stem}.wav'], expected_rate, limits['output_frames'])
        comparison, timing = compare_output(folder, name, read(references[f'{stem}.json']), old_pcm, upper, limits)
        checks.update(comparison)
        timings[name] = timing
    return {
        'checks': checks, 'engine': engine, 'browser': evidence['browser'],
        'wasm_requests': evidence['routeRequests'], 'after_restart': restarted, 'signals': timings,
        'stop_to_rejection_ms': times['stopped_rejected'] - times['stop_requested']
        if 'stopped_rejected' in times else None,
    }


def measure(out, execute, limits, references, firefox, refresh=None):
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-wasm',
             '--target', 'wasm32-unknown-unknown'], stdout=out / 'wasm-build.log')
    wasm_hash = sha256(WORKSPACE / WASM)
    reference_hash = read(references['browser-run.json'])['servedWasmSha256']
    expected = refresh['expected_current_sha256'] if refresh else reference_hash
    if refresh and reference_hash != refresh['reference_sha256']:
        raise ValueError('比較対象のWASMが登録されたSHA-256と一致しません')
    if wasm_hash != expected:
        raise ValueError('ビルドしたWASMが登録されたSHA-256と一致しません')
    execute(['env', f'CHIMERA_FIREFOX={firefox}', 'node', str(CAPTURE), str(out), str(CASE),
             str(references['speech-case.json'])], cwd=WEB, stdout=out / 'browser-command.log')
    results = {engine: compare_browser(out / engine, engine, limits, references, wasm_hash)
               for engine in limits['browsers']}
    return {
        'checks': {f'{engine}/{name}': passed for engine, result in results.items()
                   for name, passed in result['checks'].items()},
        'wasm_sha256': wasm_hash, 'reference_wasm_sha256': reference_hash, 'browsers': results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    firefox = args.firefox.resolve(strict=True)
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('差分のない固定上流版が必要です')
    run, manifest = hydrate_run(case['reference_run'], case['reference_case'], revision)
    references = {name: verified_file(run, manifest, f'artifacts/{name}') for name in (
        'speech-case.json', 'browser-run.json', 'offline.json', 'offline.wav',
        'browser.json', 'browser.wav', 'upstream.f32le')}
    voice = read(references['speech-case.json'])['speech_voice']
    limits = case['measurement']
    if (voice['input']['id'] != case['recording_id'] or voice['body'] != 'female'
            or voice['input']['rate'] != 1 or voice['internal_sample_rate_hz'] != limits['internal_rate_hz']
            or voice['voice']['output_sample_rate_hz'] != limits['output_rate_hz']):
        parser.error('保存済みの発話条件が一致しません')
    inputs = [CASE, CAPTURE, Path(__file__).resolve(), run / 'manifest.json', *references.values(),
              *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_live_tsp_rate.py', 'measure_worklet_fixed.py',
                 'measure_wasm_fixed.py', 'measure_uniform_tube.py', 'measure_csd_envelope_timing.py',
                 'measure_tsp_listening.py', 'upstream_baseline.py'))]
    refresh = case.get('wasm_refresh')
    if refresh:
        previous = WORKSPACE / 'runs' / refresh['prior_audit'] / 'manifest.json'
        if sha256(previous) != refresh['prior_manifest_sha256']:
            parser.error('差を検出した先行監査のマニフェストが一致しません')
        inputs.append(previous)
    metadata = {
        'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
        'firefox_binary': str(firefox), 'firefox_binary_sha256': sha256(firefox),
        'firefox_xul_sha256': sha256(firefox.with_name('XUL')),
        'node': subprocess.check_output(['node', '--version'], text=True).strip(),
        'analysis_command': [sys.executable, *sys.argv],
    }
    return record_measurement(args.run_id, CASE, inputs, metadata, lambda out, execute: measure(
        out, execute, limits, references, firefox, refresh), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
