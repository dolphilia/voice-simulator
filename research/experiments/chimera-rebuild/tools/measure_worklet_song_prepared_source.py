"""予備描画を保存した歌唱を、画面の2経路から既存のCLI・固定上流へ照合する。"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_bilabial_stop import load_trace
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_song_schedule_default_source import pcm_difference
from measure_song_schedule_drift import read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import CAPTURE, ROOT, WEB, web_sources
from measure_worklet_song import read_observations
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-song-prepared-source.json'
SONG_CASE = WORKSPACE / 'cases/worklet-song-voice.json'
WASM = WORKSPACE / 'target/wasm32-unknown-unknown/release/vocal_wasm.wasm'


def same_input(sample, reference):
    actual, expected = (voice.copy() for voice in (sample['song_voice'], reference['song_voice']))
    for song in (actual, expected):
        if song['body'] == 'male':
            song['body'] = {'female': 0, 'child': 0}
        song['posture'] = {'epilarynx': 0, 'ventricular': 0, 'lateral': 0} | song['posture']
    return actual == expected


def measure(case, references, cli_summary, browser, artifacts, execute):
    spec = case['measurement']
    rate = case['song_voice']['voice']['output_sample_rate_hz']
    lead, samples, quantum = (spec[k] for k in ('lead_frames', 'comparison_samples', 'quantum_frames'))
    frames, floor = lead + samples, spec['pcm_threshold']
    fields = list(spec['state_tolerance'])
    stride = read_json(SONG_CASE)['measurement']['observation_stride_frames']
    observe = {'observation_stride_frames': stride, 'observed_fields': fields}
    build = ['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build']
    execute(build, cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    execute(['env', f'CHIMERA_CHROMIUM={browser}', 'node', str(CAPTURE), str(artifacts), str(CASE)], cwd=WEB)
    browser_runs = read_json(artifacts / 'browser-run.json')
    checks, details, browser_pcm = {}, {}, {}
    for label, (start, noise, reference_case, csv, wav, upper_path) in references.items():
        expected_input = read_json(reference_case)
        reference = load_trace(csv, frames)
        cli_rate, cli = wavfile.read(wav)
        upper = np.fromfile(upper_path, dtype='<f4')
        if cli_rate != rate or cli.shape != (frames,) or upper.shape != (samples,):
            raise ValueError('基準PCMのレートまたは長さが登録と一致しません')
        details[label] = {}
        for path in spec['paths']:
            name = f'{label}-{path}'
            live = path == 'realtime'
            recorded = read_json(artifacts / f'{name}.json')
            meta = browser_runs[name]
            replay_path = artifacts / f'{name}-case.json'
            replay = read_json(replay_path)
            wav_rate, pcm = wavfile.read(artifacts / f'{name}.wav')
            trace = read_observations(recorded, observe, frames, live=live)
            if pcm.dtype != np.float32 or pcm.shape != (frames,) or not np.isfinite(pcm).all():
                raise ValueError(f'ブラウザのPCM形式・長さまたは値が不正です ({name})')
            checks[f'{name}/input_and_wasm'] = (
                same_input(replay, expected_input) and meta['recovered'] and not meta['errors']
                and meta['servedWasmSha256'] == sha256(binary))
            checks[f'{name}/output_clock'] = (
                wav_rate == recorded['sampleRate'] == recorded['workletSampleRate'] == rate
                and recorded['outputFrames'] == recorded['framesRendered'] == frames
                and recorded['outputChannels'] == 1 and recorded['discontinuities'] == 0
                and recorded['callbacks'] == (frames + quantum - 1) // quantum
                and recorded['shortestQuantum'] == recorded['longestQuantum'] == quantum
                and recorded['firstContextFrame'] == (recorded['realtime']['scheduledContextFrame'] if live else 0))
            segments = [s for phrase in recorded['song']['plan']['phrases'] for s in phrase['timing']['segments']]
            checks[f'{name}/relative_plan'] = (
                [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead,
                  round(s['end_seconds'] * rate) - lead) for s in segments]
                == [(ipa, t0, t1) for _, ipa, _, t0, t1 in cli_summary['relative_plan_frames']])
            errors = {}
            for field in fields:
                before, after = reference[field][trace['frame']], trace[field]
                delta = abs(before - after)
                first = np.flatnonzero(delta > 0)
                errors[field] = {'maximum_absolute_difference': float(delta.max()),
                                 'first_difference': int(trace['frame'][first[0]]) if first.size else None}
            checks[f'{name}/observed_state'] = all(
                errors[field]['maximum_absolute_difference'] <= spec['state_tolerance'][field] for field in fields)
            native = pcm_difference(cli, pcm, floor, -lead)
            upstream = pcm_difference(upper, pcm[lead:], floor)
            checks[f'{name}/pcm'] = native['first_over_tolerance'] is None and upstream['first_over_tolerance'] is None
            details[label][path] = {'cli_to_browser_pcm': native, 'upstream_to_browser_pcm': upstream,
                                    'observations': len(trace), 'states': errors}
            browser_pcm[noise, start, path] = pcm[lead:]
            if path == spec['paths'][0]:
                cli_replay = artifacts / f'{label}-cli-replay.wav'
                execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
                         str(replay_path), str(cli_replay), str(artifacts / f'{label}-cli-replay.csv'), '128'])
                checks[f'{label}/downloaded_replay'] = sha256(cli_replay) == sha256(wav)
    schedule = {}
    first, second = spec['warm_up_frames']
    for noise in spec['noise_scales']:
        schedule[str(noise)] = {}
        for path in spec['paths']:
            pair = pcm_difference(browser_pcm[noise, first, path], browser_pcm[noise, second, path], floor)
            schedule[str(noise)][path] = pair
            checks[f'noise-{noise}/{path}/scheduled_difference'] = (
                pair['first_over_tolerance'] == spec['expected_between_schedules_first'][str(noise)])
    return {'checks': checks, 'arms': details, 'between_schedules': schedule, 'frames': frames}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--chromium', type=Path,
                        default=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'))
    args = parser.parse_args()
    case = read_json(CASE)
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    ref = case['reference']
    cli_case = CASE.parent / ref['case']
    cli_run = run_manifest(ref['run'], read_json(cli_case)['id'], revision)
    upper_ref = read_json(cli_case)['references']['native']
    upper_run = run_manifest(upper_ref['run'], read_json(CASE.parent / upper_ref['case'])['id'], revision)
    if any(run[1]['status'] != 'pass' for run in (cli_run, upper_run)):
        parser.error('基準実行が合格していません')
    summary = verified_path(cli_run, 'summary.json')
    inputs = [CASE, cli_case, CASE.parent / upper_ref['case'], cli_run[0] / 'manifest.json',
              upper_run[0] / 'manifest.json', summary, Path(__file__).resolve(),
              *candidate_sources(), *web_sources()]
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_bilabial_stop.py', 'measure_song_schedule_default_source.py', 'measure_worklet_song.py',
        'measure_fan_crossing_allocations.py', 'measure_uniform_tube.py', 'measure_worklet_fixed.py'))
    references = {}
    for start in case['measurement']['warm_up_frames']:
        for noise in case['measurement']['noise_scales']:
            label = f'frame-{start}-noise-{noise}'
            files = [verified_path(cli_run, f'artifacts/{label}/{name}')
                     for name in ('input.json', 'voicing.csv', 'pcm-128.wav')]
            files.append(verified_path(upper_run, f'artifacts/{label}.f32le'))
            references[label] = (start, noise, *files)
            inputs.extend(files)
    metadata = {'case_id': case['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv], 'cli_reference_run': cli_run[0].name,
                'upper_reference_run': upper_run[0].name,
                'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(case, references, read_json(summary), args.chromium.resolve(strict=True),
                                           artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
