"""通常画面の実時間歌唱をブラウザ間で照合し、Firefoxの描画区間も測る。"""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_worklet_live_ipa_cross_browser as clocks
import measure_worklet_song as song


CASE = song.WORKSPACE / 'cases/worklet-live-song-cross-browser.json'


def signature(report, audio):
    values = np.asarray(report['observations'], dtype='<f8')
    plan = {k: report[k] for k in ('input', 'song', 'gestures', 'body')}
    columns = json.dumps(report['columns'][1:], separators=(',', ':')).encode()
    return {'pcm': sha256(audio.astype('<f4', copy=False)).hexdigest(),
            'observations': sha256(columns + values.tobytes()).hexdigest(),
            'score': sha256(json.dumps(plan, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def capture(folder, engine, live, source, fixture, execute, profiler=None, *, options=None, case_path=song.CASE):
    folder.mkdir()
    runtime = folder / 'capture-case.json'
    config = {**live, 'measurement': {**live['measurement'], 'unrenderable_lyrics': fixture,
                                     'browser_engine': engine, 'profiler_capture_only': profiler is not None,
                                     **(options or {})}}
    runtime.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    command = ['node', str(song.CAPTURE), str(folder), str(case_path), str(source), f'--live={runtime}']
    if profiler is not None:
        command = clocks.profiler_command(command, folder, profiler)
    execute(command, stdout=folder / 'browser-command.log')
    rate, audio = wavfile.read(folder / 'browser.wav')
    return (song.wasm.read_json(folder / 'browser-run.json'), song.wasm.read_json(folder / 'browser.json'), rate, audio)


def measure(study, fixed, live, source, prior, archived, profile, artifacts, execute, bun):
    spec = study['measurement']
    limits = fixed['measurement']
    warm = live['measurement']['timing_exclude_first_blocks']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    settings = song.wasm.read_json(source)
    reference = artifacts / 'reference'
    reference.mkdir()
    references = song.voice.capture(source, settings['measurement']['host_block_frames'],
                                    reference, execute, song.song.SUITES)
    allocations = reference / 'native-allocations.log'
    song.capture_allocations(execute, allocations)
    _, cli_trace, files, upstream_trace, upstream_wave, _ = references
    _, cli_audio = wavfile.read(files[0][0])
    _, archived_audio = wavfile.read(archived['artifacts/browser.wav'])
    archived_report = song.wasm.read_json(archived['artifacts/browser.json'])
    archived_report.setdefault('body', 'male')
    checks, trials, diagnostics = {}, [], []
    native_allocations = None
    for number, order in enumerate(spec['browser_order'], 1):
        for engine in order:
            label = f'{number}-{engine}'
            folder = artifacts / label
            result = {'trial': label, 'engine': engine}
            try:
                run, report, _, audio = capture(folder, engine, live, source, spec['unrenderable_lyrics'], execute)
                result.update(song.compare_capture(source, fixed, folder, execute, False, live, prior, binary=binary,
                                                   references=references, allocation_log=allocations,
                                                   rejection_contains=spec['rejection_contains']))
                native_allocations = result['realtime'].pop('native_allocations')
                result['hashes'] = signature(report, audio)
                result['callback_cadence'] = clocks.callback_cadence(report, warm)
                offline_kind = 'compressed' if run['offline']['dictionaryResponseIsGzip'] else 'expanded'
                local = {**result['checks'], 'requested_engine': run['engine'] == run['offline']['engine'] == engine,
                         'offline_validates_lyrics': spec['rejection_contains'] in (run['offline']['rejected'] or ''),
                         'offline_dictionary_matches_live': run['offline']['dictionaryResponseSha256'] ==
                         result['dictionary_sha256'][offline_kind]}
            except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
                result['error'] = str(error)
                local = {'capture_and_comparison_completed': False}
            trials.append(result)
            checks.update({f'{label}/{key}': passed for key, passed in local.items()})
            clocks.compress_outputs(folder)

    for key in ('pcm', 'observations', 'score'):
        values = {item.get('hashes', {}).get(key) for item in trials}
        checks[f'all_current_{key}_equal'] = len(values) == 1 and None not in values
    matched = next((r for r in trials if r.get('hashes') and r['checks']['cli_pcm_bit_equality']), None)
    for number in range(1, spec['native_firefox_trials'] + 1):
        label = f'native-firefox-{number}'
        folder = artifacts / label
        result = {'trial': label}
        try:
            run, report, rate, audio = capture(folder, 'firefox', live, source, spec['unrenderable_lyrics'],
                                               execute, profiler=profile['measurement'])
            result.update({'version': run['version'], 'hashes': signature(report, audio)})
            profile_path = folder / 'firefox-profile.json'
            if profile_path.is_file():
                result.update(clocks.native_timing(song.wasm.read_json(profile_path), spec['native_marker'],
                                                   report, warm))
            received_kind = 'compressed' if run['dictionaryResponseIsGzip'] else 'expanded'
            local = {
                'audio_and_schedule': run['engine'] == 'firefox' and run['servedWasmSha256'] == song.sha256(binary)
                and not run['errors'] and run['recovered'] and spec['rejection_contains'] in (run['rejected'] or '')
                and rate == limits['output_rate_hz'] and clocks.check_schedule(report, limits, live['measurement'])
                and song.wasm.compare_pcm(audio, cli_audio, 0)['first_bit_difference_frame'] is None,
                'state_matches_ordinary_trials': matched is not None and result['hashes'] == matched['hashes'],
                'dictionary_matches_ordinary_trials': matched is not None and run['dictionaryResponseSha256'] ==
                matched['dictionary_sha256'][received_kind],
                'native_intervals_aligned': 'native_after_warmup' in result,
            }
        except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
            result['error'] = str(error)
            local = {'capture_and_comparison_completed': False}
        diagnostics.append(result)
        checks.update({f'{label}/{key}': passed for key, passed in local.items()})
        clocks.compress_outputs(folder)
    for path in (cli_trace, upstream_trace, upstream_wave, *(pair[1] for pair in files)):
        clocks.release.stored.compress(path)
    return {'checks': checks, 'trials': trials, 'native_firefox': diagnostics, 'native_allocations': native_allocations,
            'archive': {'run': study['archived_chromium_run'], 'hashes': signature(archived_report, archived_audio),
                        'same_wasm_as_current': song.sha256(archived['artifacts/vocal_wasm.wasm']) == song.sha256(binary),
                        'cli_pcm_difference': song.wasm.compare_pcm(cli_audio, archived_audio, 0)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = song.wasm.read_json(CASE)
    live_path = song.WORKSPACE / 'cases' / study['live_case']
    profile_path = song.WORKSPACE / 'cases' / study['firefox_profile_case']
    fixed, live, profile = (song.wasm.read_json(path) for path in (song.CASE, live_path, profile_path))
    revision = study['upstream_revision']
    if (live_path != song.LIVE_CASE or live['song_case'] != song.CASE.name
            or any(case['upstream_revision'] != revision for case in (fixed, live, profile))
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流と歌唱の事前登録が一致しません')
    source = song.WORKSPACE / 'cases' / fixed['song_voice_case']
    prior = song.run_manifest(live['reference']['offline_run'], fixed['id'], revision)
    earlier = song.run_manifest(study['archived_chromium_run'], live['id'], revision)
    offline_manifest = prior[0] / 'manifest.json'
    if (song.sha256(offline_manifest) != live['reference']['offline_manifest_sha256']
            or any(run[1]['status'] != 'pass' for run in (prior, earlier))):
        parser.error('オフライン参照と以前のChromium実行を照合できません')
    archived = {name: song.verified_path(earlier, name) for name in
                ('summary.json', 'artifacts/browser.wav', 'artifacts/browser.json', 'artifacts/vocal_wasm.wasm')}
    if not all(song.wasm.read_json(archived['summary.json'])['checks'].values()):
        parser.error('以前のChromiumの判定を照合できません')
    for path in (song.CASE, live_path, source):
        matches = [row['sha256'] for row in earlier[1]['inputs'] if row['path'].endswith('/' + path.name)]
        if matches != [song.sha256(path)]:
            parser.error(f'以前のChromiumの入力と {path.name} が一致しません')
    if any(sorted(order) != ['chromium', 'firefox'] for order in study['measurement']['browser_order']):
        parser.error('各ラウンドにはChromiumとFirefoxを一度ずつ含めてください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, live_path, profile_path, song.CASE, source, offline_manifest, earlier[0] / 'manifest.json',
              *archived.values(), *(song.verified_path(prior, f'artifacts/browser.{ext}') for ext in ('wav', 'json')),
              song.voice.PROBE, *song.shared.candidate_sources(), *song.web_sources(), *(Path(module.__file__) for module in
                (song, song.song, song.voice, song.vowel, song.timing, song.wasm, song.realtime, song.shared, clocks,
                 clocks.mozilla, clocks.release.stored)), Path(__file__).resolve()]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_offline': prior[0].name,
                'turbulence_seed': 12345, 'turbulence_scale': 1.0,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, prior, archived, profile, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
