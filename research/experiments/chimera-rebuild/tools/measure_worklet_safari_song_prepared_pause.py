"""予備描画付き歌唱のSafariでの構築時間と、途中停止後のPCMを測る。"""

import argparse
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_song_schedule_default_source import pcm_difference
from measure_song_schedule_drift import read_json
from measure_uniform_tube import candidate_sources, record_measurement
from measure_worklet_fixed import ROOT, WEB, web_sources
from measure_worklet_safari_song_resume_order import CAPTURE, compare_mid_song_pause
from measure_worklet_song import read_observations
from measure_worklet_song_prepared_source import WASM, same_input
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/worklet-safari-song-prepared-pause.json'


def graph_comparison(folder, pcm, clock, study):
    if (folder / 'output-probe-error.json').exists():
        raise ValueError(read_json(folder / 'output-probe-error.json')['error'])
    probe = read_json(folder / 'output-probe.json')
    quanta = np.asarray(probe['frames'])
    quantum = study['quantum_frames']
    recorded = np.fromfile(folder / 'output-probe.f32le', dtype='<f4')
    start = clock['scheduledContextFrame']
    indices = np.flatnonzero(quanta == start)
    blocks = (len(pcm) + quantum - 1) // quantum
    if (probe['sampleRate'] != study['sample_rate_hz'] or len(recorded) != len(quanta) * quantum
            or len(indices) != 1 or not np.isfinite(recorded).all()):
        raise ValueError('並列観測の開始位置、レートまたはPCMが不正です')
    first = int(indices[0])
    begin, end = first * quantum, (first + blocks) * quantum
    if first < 1 or end >= len(recorded):
        raise ValueError('並列観測に歌唱の先頭・末尾が収まりません')
    difference = pcm_difference(pcm, recorded[begin:begin + len(pcm)], 0)
    passed = (np.array_equal(quanta[first:first + blocks], start + np.arange(blocks) * quantum)
              and difference['bit_differences'] == 0 and not recorded[begin + len(pcm):end].any())
    return passed, {'pcm': difference, 'start_context_frame': start, 'song_blocks': blocks,
                    'deferred_disconnects': probe['deferredDisconnects']}


def analyze_trial(label, trial, study, source, binary_hash, reference_pcm, reference_meta, fields, folder,
                  *, reference_live=False):
    startup = read_json(folder / 'startup.json')
    meta = read_json(folder / 'browser-run.json')
    report = read_json(folder / 'browser.json')
    replay = read_json(folder / 'browser-case.json')
    wav_rate, pcm = wavfile.read(folder / 'browser.wav')
    frames, quantum, rate = (study[k] for k in ('output_frames', 'quantum_frames', 'sample_rate_hz'))
    if (wav_rate != rate or pcm.shape != (frames,) or pcm.dtype != np.float32 or not np.isfinite(pcm).all()
            or reference_pcm.shape != pcm.shape or reference_pcm.dtype != np.float32):
        raise ValueError('Safariまたは比較基準のPCM形式が不正です')
    live = report['realtime']
    start = live['scheduledContextFrame']
    rows = np.asarray(live['blocks'], dtype=float)
    count = (frames + quantum - 1) // quantum
    checks = {
        'trusted_input_and_wasm': (startup['click']['trusted'] and same_input(replay, source)
                                   and meta['engine'] == 'safari' and not meta['errors']
                                   and meta['servedWasmSha256'] == binary_hash),
        'continuous_render_clock': (
            report['sampleRate'] == report['workletSampleRate'] == rate
            and report['outputFrames'] == report['framesRendered'] == frames
            and report['callbacks'] == count and report['discontinuities'] == 0
            and rows.shape == (count, 5) and np.isfinite(rows).all()
            and np.array_equal(rows[:, 0], start + np.arange(count) * quantum) and np.all(rows[:, 1] == quantum)
            and np.array_equal(rows[:, 2], np.minimum(np.arange(1, count + 1) * quantum, frames))),
    }
    pcm_delta = pcm_difference(reference_pcm, pcm, 0)
    checks['pcm_bits'] = pcm_delta['bit_differences'] == 0
    stride = study['observation_stride_frames']
    trace = read_observations(report, {'observed_fields': fields, 'observation_stride_frames': stride}, frames, live=True)
    max_error = None
    if reference_meta is not None:
        reference_trace = read_observations(reference_meta,
            {'observed_fields': fields, 'observation_stride_frames': stride}, frames, live=reference_live)
        max_error = max(float(abs(trace[name] - reference_trace[name]).max()) for name in fields)
        checks['observed_state_and_plan'] = max_error == 0 and report['song']['plan'] == reference_meta['song']['plan']
    timing = report['scoreConstruction']
    markers = {mark['phase']: mark for mark in report['startupTrace']['marks']}
    began, ended = timing['startedAtEpochMs'], timing['finishedAtEpochMs']
    first, click = live['firstOutputEpochMs'], startup['click']['epochMs']
    checks['construction_interval'] = (timing['warmUpFrames'] == trial['warm_up_frames']
                                       and click <= began <= ended <= first
                                       and markers['node_start']['wallMs'] <= markers['node_ready']['wallMs'])
    pause_checks, pause = compare_mid_song_pause(report, startup, trial['mode'], study['pause'])
    checks.update(pause_checks)
    if trial['mode'] == 'paused':
        position = pause['paused_frame']
        following = int(np.searchsorted(rows[:, 0], position))
        if not 0 < following < count:
            raise ValueError('停止位置の前後に描画がありません')
        before, after = rows[following - 1:following + 1]
        gap = float(after[4] - before[4])
        checks['pause_boundary'] = (
            pause['resumed_request_frame'] == position and before[0] == position - quantum and after[0] == position
            and gap >= study['pause']['minimum_callback_gap_ms'])
        pause.update(boundary_frames=[int(before[0]), int(after[0])], boundary_gap_ms=gap)
    if trial['route'] == 'observed':
        checks['graph_pcm_at_scheduled_position'], graph = graph_comparison(folder, pcm, live, study)
    else:
        graph = None
    details = {'trial': label, 'pcm': pcm_delta, 'observation_count': len(trace), 'maximum_state_error': max_error,
               'construction_ms': ended - began, 'node_call_ms': markers['node_ready']['wallMs'] - markers['node_start']['wallMs'],
               'click_to_first_output_ms': first - click, 'pause': pause, 'graph': graph, 'safari': meta['version']}
    return checks, details, pcm


def measure(study, prepared, references, order, artifacts, execute):
    build = ['npm', 'exec', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun', 'run', 'build']
    execute(build, cwd=WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(WASM, binary)
    binary_hash = sha256(binary)
    zero_path, zero_wave = (artifacts / name for name in ('zero-input.json', 'zero-cli.wav'))
    zero = read_json(references[16384]['case'])
    zero['song_voice']['warm_up_frames'] = 0
    zero_path.write_text(json.dumps(zero, ensure_ascii=False, indent=2) + '\n')
    execute(['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--', 'render-pcm',
             str(zero_path), str(zero_wave), '--no-trace', '128'])
    checks, results, waves = {}, {}, {}
    for trial in order:
        label = trial['id']
        folder = artifacts / label
        folder.mkdir()
        settings = {'song_preset': 'prepared', 'startup_timeout_seconds': study['startup_timeout_seconds'],
                    'mid_song_pause': study['pause'] | {'perform_pause': trial['mode'] == 'paused'}}
        if trial['route'] == 'observed':
            settings['output_probe'] = study['graph_probe']
        options = folder / 'capture-case.json'
        options.write_text(json.dumps(settings, ensure_ascii=False, indent=2) + '\n')
        anchor = references.get(trial['warm_up_frames'], {'case': zero_path, 'wave': zero_wave})
        try:
            execute(['node', str(CAPTURE), str(folder), str(anchor['case']), str(options)],
                    cwd=WEB, stdout=folder / 'browser-command.log')
            _, pcm = wavfile.read(anchor['wave'])
            report = read_json(anchor['report']) if 'report' in anchor else None
            local, result, audio = analyze_trial(label, trial, study, read_json(anchor['case']), binary_hash, pcm,
                                                report, list(prepared['measurement']['state_tolerance']), folder)
            checks.update({f'{label}/{name}': value for name, value in local.items()})
            results[label] = trial | result
            waves[label] = audio
        except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
            checks[f'{label}/capture_completed'] = False
            results[label] = trial | {'error': str(error)}
    controls = [v['construction_ms'] for v in results.values() if v['route'] == 'direct' and not v['warm_up_frames']
                and 'construction_ms' in v]
    prepared_times = [v['construction_ms'] for v in results.values() if v['route'] == 'direct' and v['warm_up_frames']
                      and 'construction_ms' in v]
    checks['construction_cost'] = len(controls) == 2 and len(prepared_times) == 4 and median(prepared_times) > median(controls)
    comparison = {}
    for route, warm in (('direct', 16384), ('direct', 16512), ('observed', 16384)):
        label = f'{route}-{warm}'
        previous, paused = (waves.get(label + suffix) for suffix in ('-continuous', '-paused'))
        if previous is not None and paused is not None:
            comparison[label] = pcm_difference(previous, paused, 0)
        checks[f'{label}/paused_to_continuous_pcm'] = label in comparison and comparison[label]['bit_differences'] == 0
    return {'checks': checks, 'trials': results, 'paused_to_continuous_pcm': comparison,
            'controls_construction_ms': controls, 'prepared_construction_ms': prepared_times,
            'construction_median_difference_ms': median(prepared_times) - median(controls)
                if controls and prepared_times else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--reverse', action='store_true', help='登録した採取順を反転する')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    reference_info = study['reference']
    prepared_case = CASE.parent / reference_info['case']
    reference = run_manifest(reference_info['run'], read_json(prepared_case)['id'], revision)
    if reference[1]['status'] != 'pass':
        parser.error('Chromiumの保存基準が必要です')
    inputs = [CASE, prepared_case, reference[0] / 'manifest.json', verified_path(reference, 'summary.json'),
              Path(__file__).resolve(), CAPTURE, CAPTURE.with_name('safari-webdriver.mjs'),
              *web_sources(), *candidate_sources()]
    references = {}
    for warm in sorted({trial['warm_up_frames'] for trial in study['trials']} - {0}):
        label = f'frame-{warm}-noise-{study["noise_scale"]}-offline'
        references[warm] = {kind: verified_path(reference, f'artifacts/{label}{suffix}')
                            for kind, suffix in (('case', '-case.json'), ('wave', '.wav'), ('report', '.json'))}
        inputs.extend(references[warm].values())
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_fan_crossing_allocations.py', 'measure_song_schedule_default_source.py',
        'measure_worklet_fixed.py', 'measure_worklet_safari_song_resume_order.py',
        'measure_worklet_song.py', 'measure_worklet_song_prepared_source.py', 'measure_uniform_tube.py'))
    order = study['trials'][::-1] if args.reverse else study['trials']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'analysis_directory': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv], 'reference_run': reference[0].name,
                'safaridriver': subprocess.check_output(['/usr/bin/safaridriver', '--version'], text=True).strip(),
                'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, read_json(prepared_case), references, order, artifacts, execute),
        command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
