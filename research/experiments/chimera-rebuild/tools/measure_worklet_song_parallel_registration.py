"""通常の実時間歌唱で、Worklet登録を再開要求の直後に始める条件を照合する。"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
from statistics import median
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_song_cross_browser as cross
import measure_worklet_song as song
import measure_worklet_song_startup as startup


CASE = song.WORKSPACE / 'cases/worklet-song-parallel-registration.json'
ENGINES = ('chromium', 'firefox')
REGISTRATION = ('worklet_module_start', 'worklet_module_ready')
WASM = ('wasm_fetch', 'wasm_bytes', 'wasm_ready')
RESUME = ('resume_start', 'resume_ready')
SERIAL = tuple(name for name in startup.SEQUENCE if name not in REGISTRATION)


def timing(report, parallel):
    trace = report['startupTrace']
    rows = trace['marks']
    stamps = {row['phase']: row['wallMs'] for row in rows}
    positions = {name: i for i, name in enumerate(stamps)}
    if (trace['dictionaryState'] != 'warm' or trace['parallelRegistration'] is not parallel
            or len(rows) != len(stamps) or set(stamps) != set(SERIAL + WASM + RESUME + REGISTRATION)):
        raise ValueError('辞書の準備または開始時点の採取が登録条件と一致しません')
    clock = list(stamps.values())
    frames = [row['contextFrame'] for row in rows]
    if (not np.isfinite(clock).all() or np.any(np.diff(clock) < 0) or frames[0] is not None
            or any(type(frame) is not int or frame < 0 for frame in frames[1:])):
        raise ValueError('開始時点の時計が不正です')
    orders = [SERIAL, ('context_created', *WASM, 'parallel_ready'), ('wasm_fetch', *RESUME, 'parallel_ready'),
              (*REGISTRATION, 'node_start')]
    orders.append(('resume_start', REGISTRATION[0], 'resume_ready') if parallel else
                  ('planner_ready', REGISTRATION[0]))
    if any(list(order) != sorted(order, key=positions.get) for order in orders):
        raise ValueError('登録の開始または依存する時点の順序が一致しません')

    def duration(a, b):
        return stamps[b] - stamps[a]

    start, ready = (stamps[name] for name in REGISTRATION)

    def overlap(a, b):
        return max(0, min(ready, stamps[b]) - max(start, stamps[a]))

    return {'until_connected_ms': duration('context_start', 'connected'),
            'resume_ms': duration(*RESUME), 'wasm_ms': duration(WASM[0], WASM[-1]),
            'parallel_preparation_ms': duration('context_created', 'parallel_ready'),
            'planner_ms': duration('planner_start', 'planner_ready'),
            'registration_ms': ready - start,
            'registration_overlaps_ms': {'resume': overlap(*RESUME), 'wasm': overlap(WASM[0], WASM[-1]),
                                         'planner': overlap('planner_start', 'planner_ready')},
            'registration_after_planner_ms': max(0, ready - max(start, stamps['planner_ready'])),
            'first_worklet_frame': report['realtime']['startupFirstContextFrame'],
            'scheduled_frame': report['realtime']['scheduledContextFrame']}


def checks_for_capture(run, report, rate, audio, *, engine, baseline, limits, live, expected, dictionary,
                       binary_hash, upstream, tolerance, planned_beats, rejection):
    pcm = song.wasm.compare_pcm(audio, upstream, tolerance)
    encoding = 'compressed' if run['dictionaryResponseIsGzip'] else 'expanded'
    beats = [round(note['beat_seconds'] * rate) for note in report['song']['plan']['notes']]
    checks = {'input_and_assets': run['engine'] == engine and report['input'] == baseline['input']
              and run['servedWasmSha256'] == binary_hash and run['dictionaryRequests'] == 1
              and run['dictionaryResponseSha256'] == dictionary[encoding] and run['recovered']
              and rejection in (run['rejected'] or '') and not run['errors'],
              'audio_and_observations': rate == limits['output_rate_hz'] and audio.dtype == np.float32
              and cross.signature(report, audio) == expected,
              'upstream_pcm': pcm['first_frame_over_tolerance'] is None,
              'schedule_and_beats': beats == planned_beats and startup.clocks_schedule(report, limits, live)}
    return checks, pcm


def timing_summary(trials, spec):
    engines = {}
    for engine in ENGINES:
        pairs = []
        groups = {condition: [] for condition in ('serial', 'parallel')}
        for round_number in range(1, len(spec['condition_order']) + 1):
            values = {t['condition']: t['timing'] for t in trials if t['engine'] == engine
                      and t['round'] == round_number and 'timing' in t}
            if len(values) != 2:
                continue
            pairs.append(values['serial']['until_connected_ms'] - values['parallel']['until_connected_ms'])
            for condition, value in values.items():
                groups[condition].append(value)
        if len(pairs) != len(spec['condition_order']):
            engines[engine] = {'paired_savings_ms': pairs, 'prediction_met': None}
            continue
        savings = median(pairs)
        minimum_savings = (spec['minimum_firefox_paired_median_saving_ms'] if engine == 'firefox'
                           else -spec['maximum_chromium_paired_median_regression_ms'])
        medians = {q: {key: median(t[key] for t in values) for key in values[0]
                       if key != 'registration_overlaps_ms'} for q, values in groups.items()}
        for condition, values in groups.items():
            medians[condition]['registration_overlaps_ms'] = {
                key: median(item['registration_overlaps_ms'][key] for item in values)
                for key in values[0]['registration_overlaps_ms']}
        engines[engine] = {'paired_savings_ms': pairs, 'median_saving_ms': savings, 'medians': medians,
                           'prediction_met': savings >= minimum_savings}
    return engines


def measure(study, fixed, live_case, source, reference, artifacts, execute, bun):
    spec = study['measurement']
    limits, live = fixed['measurement'], live_case['measurement']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    binary_hash = song.sha256(binary)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *[a for n in song.song.SUITES for a in ('--test', n)]],
            cwd=song.UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    saved_summary = song.wasm.read_json(reference['summary.json'])
    pcm_path = reference['artifacts/reference/pcm-128.wav']
    native_rate, native = wavfile.read(pcm_path)
    base_path = reference['artifacts/1-chromium/browser.json.gz']
    baseline = json.loads(gzip.decompress(base_path.read_bytes()))
    upper_path = reference['artifacts/reference/upstream-pcm.f32.gz']
    upstream = np.frombuffer(gzip.decompress(upper_path.read_bytes()), dtype='<f4')
    archived_trial = saved_summary['trials'][0]
    expected = cross.signature(baseline, native)
    if archived_trial['hashes'] != expected or native_rate != limits['output_rate_hz']:
        raise ValueError('保存済み歌唱とCLIの音声が一致しません')
    config = song.wasm.read_json(source)
    notes = config['song_voice']['score']
    beats = np.r_[0.0, np.cumsum([note['beats'] for note in notes['notes'][:-1]])]
    seconds = notes['start_seconds'] + beats * 60 / notes['bpm']
    planned_beats = np.rint(seconds * native_rate).astype(int).tolist()
    audio_check = dict(baseline=baseline, limits=limits, live=live, expected=expected,
                       dictionary=archived_trial['dictionary_sha256'], binary_hash=binary_hash, upstream=upstream,
                       tolerance=config['measurement']['pcm_absolute_tolerance'], planned_beats=planned_beats,
                       rejection=spec['rejection_contains'])
    checks = {'same_wasm_as_reference': binary_hash == song.sha256(reference['artifacts/vocal_wasm.wasm'])}
    trials, cancellations = [], []
    for round_number, (engines, order) in enumerate(zip(spec['browser_order'], spec['condition_order'], strict=True), 1):
        for engine in engines:
            for condition in order:
                label = f'{round_number}-{engine}-{condition}'
                folder = artifacts / label
                result = {'trial': label, 'engine': engine, 'round': round_number, 'condition': condition}
                try:
                    run, report, rate, audio = cross.capture(folder, engine, live_case, source, spec['unrenderable_lyrics'],
                        execute, options={'trace_startup': True, 'single_song_capture': True,
                                          'parallel_registration': condition == 'parallel'})
                    local, result['upstream_pcm'] = checks_for_capture(run, report, rate, audio, engine=engine, **audio_check)
                    result.update({'browser': run['version'], 'timing': timing(report, condition == 'parallel'),
                                   'hashes': cross.signature(report, audio)})
                    local['registration_order'] = True
                except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
                    result['error'] = str(error)
                    local = {'capture_and_comparison_completed': False}
                checks.update({f'{label}/{key}': value for key, value in local.items()})
                trials.append(result)
                cross.clocks.compress_outputs(folder)
    for engine in ENGINES:
        label = f'{engine}-cancel-and-replay'
        folder = artifacts / label
        result = {'trial': label}
        try:
            run, report, rate, audio = cross.capture(folder, engine, live_case, source, spec['unrenderable_lyrics'], execute,
                options={'trace_startup': True, 'parallel_registration': True, 'stop_during_registration': True})
            local, result['upstream_pcm'] = checks_for_capture(run, report, rate, audio, engine=engine, **audio_check)
            before, after = run['beforeRegistrationStop'], run['stop']
            offline_rate, offline = wavfile.read(folder / 'offline.wav')
            offline_report = song.wasm.read_json(folder / 'offline.json')
            local.update({'stop_while_registering': before['contextState'] == 'closed' and before['ready']
                          and not before['connected'] and not before['unhandled'],
                          'stop_after_connection': after['connectedSeconds'] >= live['stop_after_connected_seconds']
                          and after['contextState'] == 'closed' and after['ready'] and after['replayed'],
                          'offline_and_recovered_pcm': offline_rate == rate and cross.signature(offline_report, offline) == expected})
            result.update({'before_registration_stop': before, 'after_connection_stop': after, 'timing': timing(report, True)})
        except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
            result['error'] = str(error)
            local = {'capture_and_comparison_completed': False}
        checks.update({f'{label}/{key}': value for key, value in local.items()})
        cancellations.append(result)
        cross.clocks.compress_outputs(folder)
    return {'checks': checks, 'timing': timing_summary(trials, spec), 'trials': trials,
            'cancellations': cancellations, 'reference_hashes': expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = song.wasm.read_json(CASE)
    fixed = song.wasm.read_json(song.CASE)
    live_path = song.WORKSPACE / 'cases' / study['live_case']
    live = song.wasm.read_json(live_path)
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    revision = study['upstream_revision']
    if (live_path != song.LIVE_CASE or live['song_case'] != song.CASE.name
            or any(item['upstream_revision'] != revision for item in (fixed, live))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流と歌唱の登録が一致しません')
    prior = song.run_manifest(study['reference_run'], cross.CASE.stem, revision)
    phase_prior = song.run_manifest(study['startup_reference_run'], startup.CASE.stem, revision)
    reference = {name: song.verified_path(prior, name) for name in ('summary.json', 'artifacts/1-chromium/browser.json.gz',
                 'artifacts/reference/pcm-128.wav', 'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')}
    prior_phase_summary = song.verified_path(phase_prior, 'summary.json')
    if (any(manifest[1]['status'] != 'pass' for manifest in (prior, phase_prior))
            or phase_prior[1]['reference_run'] != prior[0].name
            or not all(song.wasm.read_json(prior_phase_summary)['checks'].values())
            or not all(song.wasm.read_json(reference['summary.json'])['checks'].values())):
        parser.error('歌唱の基準実行が合格条件を満たしません')
    for path in (song.CASE, live_path, source):
        hashes = [item['sha256'] for item in prior[1]['inputs'] if item['path'].endswith('/' + path.name)]
        if hashes != [song.sha256(path)]:
            parser.error(f'保存済み歌唱の {path.name} と入力が一致しません')
    spec = study['measurement']
    if (len(spec['browser_order']) != len(spec['condition_order']) or not spec['browser_order']
            or any(sorted(order) != list(ENGINES) for order in spec['browser_order'])
            or any(sorted(order) != ['parallel', 'serial'] for order in spec['condition_order'])):
        parser.error('各ラウンドには両ブラウザと両方の条件を一度ずつ含めてください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, live_path, song.CASE, source, prior[0] / 'manifest.json', phase_prior[0] / 'manifest.json',
              prior_phase_summary, *reference.values(), *song.web_sources(), *song.shared.candidate_sources(),
              Path(__file__).resolve(), *(Path(module.__file__) for module in
                (song, startup, cross, cross.clocks, song.wasm, song.shared, cross.clocks.release.stored))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
                'startup_reference_run': phase_prior[0].name,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
