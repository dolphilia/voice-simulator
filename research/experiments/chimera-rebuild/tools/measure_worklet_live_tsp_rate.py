"""確認用07を44.1 kHzで実時間・オフライン・CLI・固定上流から再生する。"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_coat_to import DICT, PROBE
from measure_tsp_fine_gain import render_cli
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_live_tsp_source_defaults import CASE as BROWSER_CASE, clock_checks
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-live-tsp-44100.json'
REUSE_CASE = WORKSPACE / 'cases/worklet-live-tsp-english-planner-reuse-44100.json'
REUSE_CAPTURE = WEB / 'tools/capture-english-planner-reuse.mjs'


def wave(path, rate, length):
    actual_rate, pcm = wavfile.read(path)
    if actual_rate != rate or pcm.shape != (length,) or pcm.dtype != np.float32 or not np.isfinite(pcm).all():
        raise ValueError(f'PCMの形式、レート、長さまたは有限性が登録設定と一致しません ({path})')
    return pcm


def same_states(a, b):
    return a['columns'][1:] == b['columns'][1:] and all(np.array_equal(
        np.asarray(x, dtype='f8').view('u8'), np.asarray(y, dtype='f8').view('u8')) for x, y in (
            (a['observations'], b['observations']), (a['glottal']['values'], b['glottal']['values'])))


def compare_planner_reuse(out, execute, study, references, firefox, source, result, rate, frames):
    execute(['env', f'CHIMERA_FIREFOX={firefox}', 'node', str(REUSE_CAPTURE), str(out), str(REUSE_CASE), str(source)],
            cwd=WEB, stdout=out / 'english-planner-reuse.log')
    probe = read(out / 'english-planner-reuse.json')
    shared = probe['transitions']['shared']
    fresh = probe['transitions']['fresh']
    long, short, changed, rejected, restored = shared['rows']
    settings = study['measurement']
    browser = result['browser']
    reference_browser = read(references['browser-run.json'])
    reference_report = read(references['browser.json'])
    report = read(out / 'browser.json')
    reference_pcm = wave(references['browser.wav'], rate, frames)
    pcm = wave(out / 'browser.wav', rate, frames)

    def phones(row):
        return [part['segment']['ipa'] for phrase in row['plan']['speech']['phrases']
                for part in phrase['timing']['segments']]

    result['checks'].update({
        'normal_page_module_and_planner_are_reused':
            len(reference_browser['compiledWasm']) == 2
            and browser['compiledWasm'] == [browser['servedWasmSha256']] * settings['normal_page_compilations']
            and browser['pagePlannerInstances'] == settings['normal_page_planner_instances'],
        'ordinary_recorded_pcm_and_state_match_reference':
            np.array_equal(pcm.view('u4'), reference_pcm.view('u4'))
            and same_states(report, reference_report)
            and all(report[key] == reference_report[key] for key in ('speech', 'gestures', 'tract')),
        'probe_compares_one_shared_instance_against_five_fresh_instances':
            shared['instances'] == [1] and fresh['instances'] == [1] * 5,
        'input_changes_and_recovery_match_fresh_plan_and_score':
            shared['rows'] == fresh['rows']
            and [row['name'] for row in shared['rows']] == ['long', 'short', 'new_dictionary', 'invalid_dictionary', 'restored']
            and len(long['scoreHex']) > len(short['scoreHex']) > 0
            and restored | {'name': 'long'} == long,
        'dictionary_changes_vowel_and_score':
            settings['probe']['expected_vowels'] == [phones(short)[1], phones(changed)[1]]
            and phones(short)[::2] == phones(changed)[::2]
            and short['scoreHex'] != changed['scoreHex'],
        'dictionary_error_leaves_previously_returned_score_and_plan_untouched':
            rejected['error'] == '発音辞書をUTF-8として読めません'
            and shared['retainedFirst'] == {key: long[key] for key in ('plan', 'scoreHex')},
        'failed_module_fetch_is_retried_in_the_same_page':
            probe['retry']['firstError'] == 'WASMの取得に失敗しました（503）'
            and probe['retry']['wasmRequests'] == 2
            and probe['retry']['frames'] == frames and probe['retry']['speech'] == report['speech'],
    })
    result['planner_reuse'] = {
        'normal_reference_compilations': len(reference_browser['compiledWasm']),
        'normal_compilations': len(browser['compiledWasm']),
        'normal_planner_instances': browser['pagePlannerInstances'],
        'probe_shared_instances': sum(shared['instances']),
        'probe_fresh_instances': sum(fresh['instances']),
        'probe_score_words': {row['name']: len(row['scoreHex']) // 16 for row in shared['rows'] if 'scoreHex' in row},
        'retry_wasm_requests': probe['retry']['wasmRequests'],
    }
    return result


def measure(out, execute, case, source, previous, firefox):
    limits = case['measurement']
    rate = limits['output_rate_hz']
    frames = limits['output_frames']
    input_case = read(source)
    voice = input_case['speech_voice']
    voice['internal_sample_rate_hz'] = limits['internal_rate_hz']
    voice['voice']['output_sample_rate_hz'] = rate
    converted = out / 'speech-case.json'
    converted.write_text(json.dumps(input_case, ensure_ascii=False, indent=2) + '\n')

    (native_rate, native), plan = render_cli('cli', converted, out, execute)
    if native_rate != rate or native.shape != (frames,) or native.dtype != np.float32:
        raise ValueError('CLIの出力レート、長さまたはPCM形式が登録条件と異なります')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'english'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    probe = build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',), cargo_args=('--offline',))
    dictionary = out.parent / 'tmp' / 'dictionary.tsv'
    dictionary.parent.mkdir(parents=True, exist_ok=True)
    dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
    raw = out / 'upstream.f32le'
    execute([str(probe), str(converted), str(dictionary), str(out / 'upstream-states.csv'),
             str(raw), str(out / 'upstream-plan.json')])
    upper = np.fromfile(raw, dtype='<f4')
    if upper.shape != (frames,) or not np.isfinite(upper).all():
        raise ValueError('固定上流のPCMの長さまたは有限性が登録設定と一致しません')

    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['env', f'CHIMERA_FIREFOX={firefox}', 'node', str(CAPTURE), str(out), str(BROWSER_CASE),
             str(converted), 'firefox', '--native-clock', '--save-offline-before-live'], cwd=WEB,
            stdout=out / 'browser-command.log')
    report = read(out / 'browser.json')
    offline = read(out / 'offline.json')
    browser = read(out / 'browser-run.json')
    saved = out / 'browser-case.json'
    live_wave = wave(out / 'browser.wav', rate, frames)
    off_wave = wave(out / 'offline.wav', rate, frames)
    nonzero = np.flatnonzero(live_wave)
    first = int(nonzero[0]) if nonzero.size else None
    clock = clock_checks(limits | {'first_nonzero_pcm_frame': first}, report, live_wave)
    comparisons = {name: compare_pcm(live_wave, other, 0 if name != 'upstream' else limits['upper_pcm_absolute_tolerance'])
                   for name, other in (('cli', native), ('offline', off_wave), ('upstream', upper))}
    speech = report['speech']
    upper_plan = read(out / 'upstream-plan.json')
    checks = clock['checks'] | {
        'rate_and_assets': (report['sampleRate'] == report['workletSampleRate'] == offline['sampleRate']
            == offline['workletSampleRate'] == rate and browser['engine'] == 'firefox'
            and browser['servedWasmSha256'] == sha256(WORKSPACE / WASM) and not browser['errors']),
        'preserved_case_and_plan': (read(saved) == input_case and voice['input']['id'] == case['recording_id']
            and all(report[key] == plan[key] == offline[key] == previous[key] for key in ('speech', 'gestures'))
            and plan['decimation_factor'] * rate == limits['internal_rate_hz']
            and plan['output_frames'] == upper_plan['output_frames'] == frames
            and frames == round(speech['render_end_seconds'] * rate)),
        'first_nonzero_prediction': (first is not None and abs(first - limits['predicted_first_nonzero_frame'])
            <= limits['first_nonzero_tolerance_frames']),
        'offline_states_bit_equal': same_states(report, offline),
        'cli_and_offline_pcm_bit_equal': all(comparisons[key]['first_bit_difference_frame'] is None
                                             for key in ('cli', 'offline')),
        'upstream_pcm_within_tolerance': comparisons['upstream']['first_frame_over_tolerance'] is None,
    }
    return clock | {'checks': checks, 'browser': browser, 'pcm': comparisons,
                   'render_end_seconds': speech['render_end_seconds'],
                   'first_nonzero': {name: int(f[0]) if (f := np.flatnonzero(pcm)).size else None
                                     for name, pcm in (('cli', native), ('offline', off_wave),
                                                       ('worklet', live_wave), ('upstream', upper))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('--reuse-english-planner', action='store_true', help='発話計画器のページ内共有も照合する')
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    firefox = args.firefox.resolve(strict=True)
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流版が必要です')
    run, manifest = hydrate_run(case['source_run'], case['source_case'], revision)
    source, previous = (verified_file(run, manifest, 'artifacts/firefox/' + name) for name in
                        ('browser-case.json', 'browser.json'))
    inputs = [CASE, BROWSER_CASE, Path(__file__).resolve(), source, previous, run / 'manifest.json', DICT, PROBE,
              *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_worklet_live_tsp_source_defaults.py',
                 'measure_tsp_fine_gain.py', 'measure_uniform_tube.py', 'measure_wasm_fixed.py',
                 'measure_worklet_realtime.py', 'measure_tsp_listening.py', 'measure_csd_envelope_timing.py'))]
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'firefox_binary': str(firefox), 'firefox_xul_sha256': sha256(firefox.with_name('XUL')),
                'firefox_binary_sha256': sha256(firefox), 'analysis_command': [sys.executable, *sys.argv]}
    case_path = REUSE_CASE if args.reuse_english_planner else CASE
    if args.reuse_english_planner:
        study = read(REUSE_CASE)
        assert study['upstream_revision'] == revision
        baseline, baseline_manifest = hydrate_run(study['reference_run'], study['reference_case'], revision)
        references = {name: verified_file(baseline, baseline_manifest, f'artifacts/{name}')
                      for name in ('browser-run.json', 'browser.json', 'browser.wav')}
        inputs.extend([REUSE_CASE, REUSE_CAPTURE, baseline / 'manifest.json', *references.values()])
        metadata.update(case_id=study['id'], case_revision=study['revision'])

    def run_measurement(out, execute):
        result = measure(out, execute, case, source, read(previous), firefox)
        if args.reuse_english_planner:
            return compare_planner_reuse(out, execute, study, references, firefox, out / 'speech-case.json',
                                         result, case['measurement']['output_rate_hz'], case['measurement']['output_frames'])
        return result

    return record_measurement(args.run_id, case_path, inputs, metadata, run_measurement, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
