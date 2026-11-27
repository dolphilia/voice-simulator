"""歌唱のWorklet登録をHTTP、モジュール評価、完了通知に分けて測る。"""

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
import measure_worklet_song_parallel_registration as registration


CASE = song.WORKSPACE / 'cases/worklet-song-module-evaluation.json'
ORDERS = ('serial', 'parallel')
CONDITIONS = sorted(f'{order}-{kind}' for order in ORDERS for kind in ('control', 'evaluation'))


def evaluation_timing(report, http, registration_ms, tolerance):
    marks = {row['phase']: row for row in report['startupTrace']['marks']}
    worklet = report['workletModuleTiming']
    began = marks['worklet_module_start']['epochMs']
    resolved = marks['worklet_module_ready']['epochMs']
    evaluation = worklet['evaluationStartedAtEpochMs']
    registration_start = worklet['registrationStartedAtEpochMs']
    registered = worklet['registeredAtEpochMs']
    posted = worklet['readyPostedAtEpochMs']
    received = marks['worklet_ready_received']['epochMs']
    node_requested = marks['node_start']['epochMs']
    sequence = [began, http['startedAtEpochMs'], http['finishedAtEpochMs'], evaluation, registration_start,
                registered, resolved, node_requested, posted, received]
    if not np.isfinite(sequence).all():
        raise ValueError('Worklet登録の時計に非有限値があります')
    if not (evaluation <= registration_start <= registered <= posted and
            http['startedAtEpochMs'] <= http['finishedAtEpochMs'] and began <= resolved <= node_requested <= received):
        raise ValueError('同じ時計で採ったWorklet登録の境界が逆転しています')
    error = float(abs((resolved - began) - registration_ms))
    inversion = float(max(0, -np.diff(sequence).min()))
    duration = resolved - began
    return {'call_to_request_ms': http['startedAtEpochMs'] - began,
            'server_response_ms': http['finishedAtEpochMs'] - http['startedAtEpochMs'],
            'response_to_first_statement_ms': evaluation - http['finishedAtEpochMs'],
            'before_evaluation_ms': evaluation - began,
            'first_statement_to_register_call_ms': registration_start - evaluation,
            'register_call_ms': registered - registration_start,
            'evaluation_through_registration_ms': registered - evaluation,
            'registration_to_resolved_ms': resolved - registered,
            'node_request_to_ready_post_ms': posted - node_requested,
            'ready_message_ms': received - posted,
            'before_evaluation_fraction': (evaluation - began) / duration if duration > 0 else None,
            'maximum_clock_inversion_ms': inversion, 'main_clock_duration_error_ms': error,
            'clocks_fit': error <= tolerance and inversion <= tolerance}


def timing_summary(trials, spec):
    result = {}
    for engine in registration.ENGINES:
        result[engine] = {}
        for order in ORDERS:
            groups = {trace: [t for t in trials if t['engine'] == engine and t['order'] == order
                              and t['evaluation_enabled'] == trace and 'timing' in t] for trace in (False, True)}
            control = {t['round']: t for t in groups[False]}
            traced = groups[True]
            pairs = [t['timing']['until_connected_ms'] - control[t['round']]['timing']['until_connected_ms']
                     for t in traced if t['round'] in control]
            values = [t['evaluation_timing'] for t in traced if t.get('evaluation_timing', {}).get('clocks_fit')]
            if len(pairs) != len(spec['condition_order']) or len(values) != len(pairs):
                result[engine][order] = {'completed_pairs': len(pairs), 'valid_evaluation_clocks': len(values)}
                continue
            medians = {name: median(t[name] for t in values) for name, value in values[0].items()
                       if type(value) in (int, float) and all(t[name] is not None for t in values)}
            shift = median(pairs)
            fraction = medians.get('before_evaluation_fraction')
            result[engine][order] = {'evaluation_medians': medians, 'connected_shift_ms_by_round': pairs,
                'connected_shift_median_ms': shift,
                'connected_shift_fits': abs(shift) <= spec['maximum_median_connected_shift_ms'],
                'evaluation_duration_prediction_met': medians['evaluation_through_registration_ms'] <= spec['expected_worklet_evaluation_ms'],
                **({'before_evaluation_prediction_met': fraction is not None and
                    fraction >= spec['expected_firefox_before_evaluation_fraction']} if engine == 'firefox' else {})}
    return result


def measure(study, fixed, live_case, source, reference, artifacts, execute, bun):
    spec = study['measurement']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    binary_hash = song.sha256(binary)
    bundles = {}
    for key, stem in ((False, 'fixed-processor-entry'), (True, 'fixed-processor-measured-entry')):
        matched = list((song.WEB / 'dist/assets').glob(f'{stem}-*.js'))
        if len(matched) != 1:
            raise ValueError(f'計時に使うViteの出力を照合できません ({stem})')
        bundle = matched[0]
        shutil.copyfile(bundle, artifacts / bundle.name)
        bundles[key] = '/assets/' + bundle.name
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *[a for n in song.song.SUITES for a in ('--test', n)]],
            cwd=song.UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    saved_summary = song.wasm.read_json(reference['summary.json'])
    baseline = json.loads(gzip.decompress(reference['artifacts/1-chromium/browser.json.gz'].read_bytes()))
    rate, native = wavfile.read(reference['artifacts/reference/pcm-128.wav'])
    upper = np.frombuffer(gzip.decompress(reference['artifacts/reference/upstream-pcm.f32.gz'].read_bytes()), dtype='<f4')
    expected = cross.signature(baseline, native)
    if rate != fixed['measurement']['output_rate_hz'] or expected != saved_summary['trials'][0]['hashes']:
        raise ValueError('保存済みの歌唱とCLIのPCMを照合できません')
    config = song.wasm.read_json(source)
    notes = config['song_voice']['score']
    beats = np.r_[0.0, np.cumsum([note['beats'] for note in notes['notes'][:-1]])]
    seconds = notes['start_seconds'] + beats * 60 / notes['bpm']
    checks = {'same_wasm_as_reference': binary_hash == song.sha256(reference['artifacts/vocal_wasm.wasm'])}
    toler = spec['cross_clock_tolerance_ms']
    trials = []
    for number, (engines, order) in enumerate(zip(spec['browser_order'], spec['condition_order'], strict=True), 1):
        for engine in engines:
            for condition in order:
                startup_order, variant = condition.split('-')
                measured = variant == 'evaluation'
                label = f'{number}-{engine}-{condition}'
                folder = artifacts / label
                result = {'trial': label, 'engine': engine, 'order': startup_order, 'round': number, 'evaluation_enabled': measured}
                try:
                    run, report, got_rate, audio = cross.capture(folder, engine, live_case, source, spec['unrenderable_lyrics'],
                        execute, options={'trace_startup': True, 'trace_evaluation': measured,
                        'observe_worklet_evaluation': True, 'single_song_capture': True, 'parallel_registration': startup_order == 'parallel'})
                    result['browser'] = run['version']
                    local, result['upstream_pcm'] = registration.checks_for_capture(run, report, got_rate, audio,
                        engine=engine, baseline=baseline, limits=fixed['measurement'], live=live_case['measurement'],
                        expected=expected, dictionary=saved_summary['trials'][0]['dictionary_sha256'], binary_hash=binary_hash,
                        upstream=upper, tolerance=config['measurement']['pcm_absolute_tolerance'],
                        planned_beats=np.rint(seconds * rate).astype(int).tolist(), rejection=spec['rejection_contains'])
                    trace = report['startupTrace']
                    marks = [row for row in trace['marks'] if row['phase'] != 'worklet_ready_received']
                    result['timing'] = registration.timing({**report, 'startupTrace': {**trace, 'marks': marks}},
                                                           startup_order == 'parallel')
                    requests = run['workletRequests']
                    result['worklet_requests'] = requests
                    local['expected_bundle_and_marker'] = (len(requests) == 1 and requests[0]['path'] == bundles[measured]
                        and requests[0]['status'] == 200 and ('workletModuleTiming' in report) == measured
                        and (len(trace['marks']) - len(marks)) == int(measured))
                    if measured and local['expected_bundle_and_marker']:
                        result['evaluation_timing'] = evaluation_timing(report, requests[0], result['timing']['registration_ms'], toler)
                        local['evaluation_clocks_aligned'] = result['evaluation_timing']['clocks_fit']
                except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
                    result['error'] = str(error)
                    local = {'capture_and_comparison_completed': False}
                checks.update({f'{label}/{key}': value for key, value in local.items()})
                trials.append(result)
                cross.clocks.compress_outputs(folder)
    return {'checks': checks, 'groups': timing_summary(trials, spec), 'trials': trials, 'reference_hashes': expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study, fixed = (song.wasm.read_json(path) for path in (CASE, song.CASE))
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
    timings = song.run_manifest(study['registration_reference_run'], registration.CASE.stem, revision)
    reference = {name: song.verified_path(prior, name) for name in ('summary.json', 'artifacts/1-chromium/browser.json.gz',
                'artifacts/reference/pcm-128.wav', 'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')}
    timings_summary = song.verified_path(timings, 'summary.json')
    if any(run[1]['status'] != 'pass' for run in (prior, timings)) or timings[1]['reference_run'] != prior[0].name:
        parser.error('歌唱と登録の基準実行が合格条件を満たしません')
    for path in (song.CASE, live_path, source):
        hashes = [item['sha256'] for item in prior[1]['inputs'] if item['path'].endswith('/' + path.name)]
        if hashes != [song.sha256(path)]:
            parser.error(f'保存済み歌唱の {path.name} と入力が一致しません')
    spec = study['measurement']
    if (len(spec['browser_order']) != len(spec['condition_order']) or not spec['browser_order']
            or any(sorted(order) != list(registration.ENGINES) for order in spec['browser_order'])
            or any(sorted(order) != CONDITIONS for order in spec['condition_order'])):
        parser.error('各ラウンドに両ブラウザと全比較条件が必要です')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, live_path, song.CASE, source, prior[0] / 'manifest.json', timings[0] / 'manifest.json',
              timings_summary, *reference.values(), *song.web_sources(), *song.shared.candidate_sources(), Path(__file__).resolve(),
              *(Path(module.__file__) for module in (song, cross, registration, registration.startup,
                 cross.clocks, song.wasm, song.shared, cross.clocks.release.stored))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
                'registration_reference_run': timings[0].name,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
