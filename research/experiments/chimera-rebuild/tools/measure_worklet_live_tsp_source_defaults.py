"""確認用07の実時間再生をオフライン、CLI、固定上流と照合する。"""

import argparse
import gzip
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read
from measure_tsp_fine_gain import render_cli
from measure_tsp_listening import hydrate_run, snapshot_case
from measure_uniform_tube import candidate_sources, record_measurement
from measure_wasm_fixed import WASM, compare_pcm
from measure_worklet_english import DICT, UPPER_DICT
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_realtime import timing_summary
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/worklet-live-tsp-source-defaults.json'


def clock_checks(limits, report, pcm):
    rate = limits['output_rate_hz']
    quantum = limits['render_quantum_frames']
    count = (len(pcm) + quantum - 1) // quantum
    live = report['realtime']
    blocks = np.asarray(live['blocks'], dtype=float)
    if (live['columns'] != ['context_frame', 'quantum_frames', 'frames_rendered', 'process_ms', 'callback_elapsed_ms']
            or blocks.shape != (count, 5) or not np.isfinite(blocks).all()):
        raise ValueError('実時間量子の観測列、件数、有限性を確認できません')
    context, length, rendered, work, elapsed = blocks.T
    lead = limits['lead_frames']
    startup = limits['startup_contiguous_quanta']
    armed, scheduled = live['armedContextFrame'], live['scheduledContextFrame']
    k = np.arange(count)
    expected_absolute = scheduled + k * quantum
    expected_end = np.minimum((k + 1) * quantum, len(pcm))
    stride = limits['observation_stride_frames']
    frames_observed = np.minimum(np.arange(stride, len(pcm) + stride, stride), len(pcm)) - 1
    observations = np.asarray(report['observations'], dtype=float)
    first = np.flatnonzero(pcm)
    first_nonzero = int(first[0]) if first.size else None
    budget = 1000 * quantum / rate
    return {
        'checks': {
            'startup_clock': (live['contextState'] == 'running' and live['startupCallbacks'] >= startup
                and armed == live['startupContiguousFirstContextFrame'] + startup * quantum
                and scheduled == armed + lead == report['firstContextFrame']
                and scheduled % quantum == 0 and live['leadCallbacks'] == lead // quantum),
            'report_and_quantum_clocks': (report['sampleRate'] == report['workletSampleRate'] == rate
                and report['outputChannels'] == 1 and report['outputFrames'] == report['framesRendered'] == len(pcm)
                and report['shortestQuantum'] == report['longestQuantum'] == quantum
                and report['discontinuities'] == 0 and report['callbacks'] == count and report['stableWasmBuffers']
                and np.array_equal(context, expected_absolute) and bool(np.all(length == quantum))
                and np.array_equal(rendered, expected_end)),
            'observation_clock': (report['columns'][:2] == ['output_frame', 'frames_rendered']
                and np.isfinite(observations).all()
                and np.array_equal(observations[:, 0], frames_observed)
                and np.array_equal(observations[:, 1], frames_observed + 1)),
            'first_nonzero_in_speech_clock': (first_nonzero == limits['first_nonzero_pcm_frame']
                and not np.any(pcm[:limits['initial_silence_frames']])),
            'timing_rows_valid': bool(np.all(work >= 0) and elapsed[0] == 0 and np.all(np.diff(elapsed) >= 0)),
        },
        'clock': {'startup_first_context_frame': live['startupFirstContextFrame'],
                  'startup_contiguous_first_context_frame': live['startupContiguousFirstContextFrame'],
                  'startup_discontinuities': live['startupDiscontinuities'], 'startup_callbacks': live['startupCallbacks'],
                  'armed_context_frame': armed, 'scheduled_context_frame': scheduled, 'lead_callbacks': live['leadCallbacks'],
                  'active_callbacks': count, 'last_valid_frames': len(pcm) - (count - 1) * quantum,
                  'last_padding_frames': count * quantum - len(pcm), 'observation_points': len(frames_observed),
                  'first_nonzero_output_frame': first_nonzero,
                  'first_nonzero_context_frame': scheduled + first_nonzero if first_nonzero is not None else None,
                  'wasm_memory_growths': report['wasmMemoryGrowths']},
        'timing': {'clock': live['timingClock'], 'quantum_budget_ms': budget,
                   'all': timing_summary(work, budget), 'warm': timing_summary(work[limits['timing_skip_blocks']:], budget)},
    }


def measure_browser(engine, study, paths, binary, out, execute):
    limits = study['measurement']
    reference = paths['browser-case.json']
    execute(['node', str(CAPTURE), str(out), str(CASE), str(reference), engine])
    web = read(out / 'browser-run.json')
    report = read(out / 'browser.json')
    offline = read(paths['browser.json'])
    replay_case = out / 'browser-case.json'
    (cli_rate, cli), plan = render_cli('browser-replay', replay_case, out, execute)
    rate, pcm = wavfile.read(out / 'browser.wav')
    offline_rate, offline_pcm = wavfile.read(paths['browser.wav'])
    upstream = np.fromfile(paths['upstream.f32le'], dtype='<f4')
    if any(wave.shape != (limits['output_frames'],) or wave.dtype != np.float32
           or not np.isfinite(wave).all() for wave in (pcm, cli, offline_pcm, upstream)):
        raise ValueError('PCMの形式、長さ、有限性を確認できません')
    waves = {'offline': compare_pcm(pcm, offline_pcm, 0), 'cli': compare_pcm(pcm, cli, 0),
             'upstream': compare_pcm(pcm, upstream, limits['upper_pcm_absolute_tolerance'])}
    clock = clock_checks(limits, report, pcm)
    comparable = ('input', 'speech', 'gestures', 'body', 'basePitchHz', 'tract')
    dictionary = sha256(DICT)
    expanded = hashlib.sha256(gzip.decompress(DICT.read_bytes())).hexdigest()
    live_columns, offline_columns = report['columns'], offline['columns']
    live_rows, offline_rows = (np.asarray(r['observations'], dtype='f8') for r in (report, offline))
    state_equal = (live_columns[1:] == offline_columns[1:] and np.array_equal(live_rows.view('u8'), offline_rows.view('u8'))
        and np.array_equal(np.asarray(report['glottal']['values'], dtype='f8').view('u8'),
                           np.asarray(offline['glottal']['values'], dtype='f8').view('u8')))
    return {
        **clock,
        'checks': {
            **clock['checks'],
            'assets_and_stop': (web['engine'] == engine and web['servedWasmSha256'] == web['offlineWasmSha256'] == sha256(binary)
                and web['compiledWasm'] == [web['servedWasmSha256']]
                and web['dictionaryResponseSha256'] == (dictionary if web['dictionaryResponseIsGzip'] else expanded)
                and dictionary == sha256(UPPER_DICT) and web['recovered'] and not web['errors'] and web['stopped']),
            'preserved_case_and_plan': (read(replay_case) == read(reference)
                and all(report[key] == offline[key] for key in comparable)
                and all(report[key] == plan[key] for key in ('speech', 'gestures'))
                and plan['decimation_factor'] * rate == limits['internal_rate_hz']),
            'offline_states_bit_equal': state_equal,
            'native_pcm_bit_equal': (rate == cli_rate == offline_rate == limits['output_rate_hz']
                and all(waves[name]['first_bit_difference_frame'] is None for name in ('offline', 'cli'))),
            'upstream_pcm_tolerance': waves['upstream']['first_frame_over_tolerance'] is None,
        },
        'browser': web,
        'pcm': waves,
    }


def measure(study, paths, out, execute, bun):
    execute([*bun, 'run', 'build'], cwd=WEB, stdout=out / 'browser-build.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'english', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-wasm', '--lib'],
            stdout=out / 'wasm-tests.log')
    binary = out / 'vocal_wasm.wasm'
    shutil.copyfile(WORKSPACE / WASM, binary)
    results = {}
    for engine in study['browser_order']:
        folder = out / engine
        folder.mkdir()
        results[engine] = measure_browser(engine, study, paths, binary, folder, execute)
    cross_browser = len({sha256(out / engine / 'browser.wav') for engine in results}) == 1
    return {'checks': {'same_wave_in_all_browsers': cross_browser,
                       **{f'{engine}/{key}': passed for engine, result in results.items()
                          for key, passed in result['checks'].items()}}, 'browsers': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != rev
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM)):
        parser.error('差分のない固定上流版が必要です')
    base = hydrate_run(study['offline_run'], study['offline_case'], rev)
    upper = hydrate_run(study['upstream_run'], study['upstream_case'], rev)
    offline_case = snapshot_case(base, study['offline_case'])
    upper_case = snapshot_case(upper, study['upstream_case'])
    m = study['measurement']
    offline = read(offline_case)
    keys = ('output_frames', 'output_rate_hz', 'internal_rate_hz', 'observation_stride_frames')
    if (offline['recording_id'] != m['recording_id']
            or any(offline['measurement'][key] != m[key] for key in keys)):
        parser.error('オフラインの保存済み参照が登録条件と一致しません')
    paths = {name: verified_file(*base, f'artifacts/{name}') for name in (
        'browser-case.json', 'browser.json', 'browser.wav')}
    paths['upstream.f32le'] = verified_file(*upper, 'artifacts/upstream.f32le')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, Path(__file__).resolve(), DICT, UPPER_DICT, offline_case, upper_case, *paths.values(),
              base[0] / 'manifest.json', upper[0] / 'manifest.json', *candidate_sources(), *web_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_uniform_tube.py', 'measure_wasm_fixed.py',
                'measure_tsp_listening.py', 'measure_speech_timing.py', 'measure_tsp_fine_gain.py',
                'measure_worklet_fixed.py', 'measure_worklet_english.py', 'measure_worklet_realtime.py',
                'measure_csd_envelope_timing.py', 'upstream_baseline.py'))]
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
                'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '-v'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip(),
                'firefox_override': os.environ.get('CHIMERA_FIREFOX'), 'chromium_override': os.environ.get('CHIMERA_CHROMIUM')}
    return record_measurement(args.run_id, CASE, inputs, metadata, lambda out, run: measure(study, paths, out, run, bun),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
