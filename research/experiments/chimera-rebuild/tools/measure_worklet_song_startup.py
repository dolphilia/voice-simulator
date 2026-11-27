"""通常の実時間歌唱でContext作成からWorklet接続までを分けて測る。"""

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


CASE = song.WORKSPACE / 'cases/worklet-song-startup-phases.json'
CONDITIONS = {'warm-control', 'warm-traced', 'cold-traced', 'syllables-traced'}
SEQUENCE = ('context_start', 'context_created', 'parallel_ready', 'dictionary_start', 'dictionary_ready',
            'planner_start', 'planner_instance', 'planner_input', 'planner_wasm', 'planner_result', 'planner_ready',
            'worklet_module_start', 'worklet_module_ready', 'node_start', 'node_ready', 'connect_start', 'connected')
SERIAL = {'context': ('context_start', 'context_created'),
          'parallel_preparation': ('context_created', 'parallel_ready'),
          'dictionary': ('dictionary_start', 'dictionary_ready'), 'planner_instance': ('planner_start', 'planner_instance'),
          'planner_input': ('planner_instance', 'planner_input'), 'planner_wasm': ('planner_input', 'planner_wasm'),
          'planner_result': ('planner_wasm', 'planner_ready'), 'worklet_module': ('worklet_module_start', 'worklet_module_ready'),
          'node': ('node_start', 'node_ready'), 'connect': ('connect_start', 'connected')}


def phases(report, cache):
    points = report['startupTrace']['marks']
    marks = {row['phase']: row for row in points}
    names = tuple(marks)
    branches = {'wasm_fetch', 'wasm_bytes', 'wasm_ready', 'resume_start', 'resume_ready'}
    if (report['startupTrace']['dictionaryState'] != cache or len(points) != len(marks)
            or tuple(name for name in names if name not in branches) != SEQUENCE or set(names) != set(SEQUENCE) | branches):
        raise ValueError('歌唱開始の観測点または辞書の状態が登録条件と一致しません')
    for chain in (('context_created', 'wasm_fetch', 'resume_start'),
                  ('wasm_fetch', 'wasm_bytes', 'wasm_ready', 'parallel_ready'),
                  ('resume_start', 'resume_ready', 'parallel_ready')):
        if sorted(chain, key=names.index) != list(chain):
            raise ValueError('WASMとContextの並行区間の順序が不正です')
    wall = np.asarray([item['wallMs'] for item in points], dtype=float)
    frames = [item['contextFrame'] for item in points]
    if (not np.isfinite(wall).all() or np.any(np.diff(wall) < 0) or frames[0] is not None
            or any(type(frame) is not int or frame < 0 for frame in frames[1:])):
        raise ValueError('歌唱開始の時計に不正な値があります')

    def elapsed(a, b):
        return marks[b]['wallMs'] - marks[a]['wallMs']

    duration = {key: elapsed(*pair) for key, pair in SERIAL.items()}
    total = elapsed('context_start', 'connected')
    # 連続した境界間を直接足し、各機構の前後に挟まる待ち時間も明示する。
    serial = {pair for pair in SERIAL.values()}
    gaps = sum(elapsed(a, b) for a, b in zip(SEQUENCE[:-1], SEQUENCE[1:], strict=True)
               if (a, b) not in serial and (a, b) != ('planner_wasm', 'planner_result')
               and (a, b) != ('planner_result', 'planner_ready'))
    if abs(total - (sum(duration.values()) + gaps)) > 1e-6:
        raise ValueError('接続までの時間を重複なしで復元できません')
    return {**duration, 'between_phases': gaps, 'until_connected': total,
            'wasm_fetch_bytes': elapsed('wasm_fetch', 'wasm_bytes'), 'wasm_compile': elapsed('wasm_bytes', 'wasm_ready'),
            'resume': elapsed('resume_start', 'resume_ready'),
            'parallel_last': 'wasm' if names.index('wasm_ready') > names.index('resume_ready') else 'resume',
            'planner_wasm_context_frames': marks['planner_wasm']['contextFrame'] - marks['planner_input']['contextFrame'],
            'connected_context_frame': marks['connected']['contextFrame'],
            'first_worklet_minus_connected_frame': report['realtime']['startupFirstContextFrame'] - marks['connected']['contextFrame']}


def compare_groups(results, limits, checks):
    metrics = {}
    for engine in ('chromium', 'firefox'):
        for condition in sorted(CONDITIONS):
            samples = [r for r in results if r['engine'] == engine and r['condition'] == condition and 'error' not in r]
            if len(samples) != len(limits['condition_order']):
                return metrics, {}
            stages = samples[0].get('phases_ms', {})
            recorded = {key: median(r['phases_ms'][key] for r in samples)
                        for key, value in stages.items() if isinstance(value, (int, float))}
            metrics.setdefault(engine, {})[condition] = {**recorded, **{
                key: median(r[key] for r in samples) for key in ('first_worklet_frame', 'scheduled_frame')}}
        for key in ('first_worklet_frame', 'scheduled_frame'):
            diff = metrics[engine]['warm-traced'][key] - metrics[engine]['warm-control'][key]
            checks[f'{engine}/probe_shift_{key}'] = abs(diff) <= limits['maximum_median_probe_shift_frames']
    chrome, firefox = (metrics[engine]['warm-traced'] for engine in ('chromium', 'firefox'))
    gap = firefox['until_connected'] - chrome['until_connected']
    planner_gap = firefox['planner_wasm'] - chrome['planner_wasm']
    share = planner_gap / gap if gap > 0 else None
    explain = {'warm_firefox_minus_chromium_ms': {key: firefox[key] - chrome[key] for key in SERIAL},
               'warm_connection_gap_ms': gap, 'warm_planner_wasm_share': share,
               'warm_planner_prediction_met': share is not None and share >= limits['expected_warm_planner_gap_fraction'],
               'cold_to_syllables': {}}
    for engine in metrics:
        cold, syllables = (metrics[engine][condition] for condition in ('cold-traced', 'syllables-traced'))
        fraction = 1 - syllables['planner_wasm'] / cold['planner_wasm'] if cold['planner_wasm'] > 0 else None
        explain['cold_to_syllables'][engine] = {
            'planner_wasm_reduction': fraction, 'until_connected_ms_saved': cold['until_connected'] - syllables['until_connected'],
            'planner_reduction_prediction_met': fraction is not None and fraction >= limits['expected_cold_planner_reduction_fraction']}
    return metrics, explain


def measure(study, fixed, live, source, reference, artifacts, execute, bun):
    spec, limits = study['measurement'], fixed['measurement']
    execute([*bun, 'run', 'build'], cwd=song.WEB, stdout=artifacts / 'browser-build.log')
    binary = artifacts / 'vocal_wasm.wasm'
    shutil.copyfile(song.WORKSPACE / song.wasm.WASM, binary)
    binary_hash = song.sha256(binary)
    execute(['cargo', 'test', '--locked', '-p', 'chimera', *[arg for name in song.song.SUITES for arg in ('--test', name)]],
            cwd=song.UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    baseline = json.loads(gzip.decompress(reference['artifacts/1-chromium/browser.json.gz'].read_bytes()))
    old_summary = song.wasm.read_json(reference['summary.json'])
    expected_dict = old_summary['trials'][0]['dictionary_sha256']
    native_rate, native = wavfile.read(reference['artifacts/reference/pcm-128.wav'])
    upstream = np.frombuffer(gzip.decompress(reference['artifacts/reference/upstream-pcm.f32.gz'].read_bytes()), dtype='<f4')
    expected = cross.signature(baseline, native)
    if old_summary['trials'][0]['hashes'] != expected:
        raise ValueError('保存済みの歌唱・観測・CLIのハッシュが一致しません')
    config = song.wasm.read_json(source)
    upper_tolerance = config['measurement']['pcm_absolute_tolerance']
    syllables_case = artifacts / 'syllables-case.json'
    structured_score = config['song_voice']['score']
    structured_score.pop('lyrics')
    structured_score['syllables'] = baseline['song']['syllables']
    syllables_case.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    structured_input = {**structured_score, 'vibrato_cents': baseline['input']['vibrato_cents']}
    worklet = live['measurement']
    checks = {'same_wasm_as_reference': binary_hash == song.sha256(reference['artifacts/vocal_wasm.wasm'])}
    trials = []
    for number, (engines, order) in enumerate(zip(spec['browser_order'], spec['condition_order'], strict=True), 1):
        for engine in engines:
            for condition in order:
                label = f'{number}-{engine}-{condition}'
                folder = artifacts / label
                traced = condition != 'warm-control'
                warmed = condition.startswith('warm-')
                structured = condition == 'syllables-traced'
                result = {'trial': label, 'engine': engine, 'condition': condition}
                try:
                    run, report, rate, audio = cross.capture(folder, engine, live, syllables_case if structured else source,
                        spec['unrenderable_lyrics'], execute, options={'single_song_capture': True,
                        'trace_startup': traced, 'skip_invalid_lyrics': not warmed})
                    result['version'] = run['version']
                    result['first_worklet_frame'] = report['realtime']['startupFirstContextFrame']
                    result['scheduled_frame'] = report['realtime']['scheduledContextFrame']
                    result['hashes'] = cross.signature({**report, 'input': baseline['input']}, audio)
                    result['upstream_pcm'] = song.wasm.compare_pcm(audio, upstream, upper_tolerance)
                    if traced:
                        result['phases_ms'] = phases(report, 'warm' if warmed else 'none' if structured else 'cold')
                    input_ok = report['input'] == (structured_input if structured else baseline['input'])
                    dictionary_kind = 'compressed' if run.get('dictionaryResponseIsGzip') else 'expanded'
                    dictionary_ok = (run['dictionaryRequests'] == 0 if structured else
                                     run['dictionaryRequests'] == 1 and run['dictionaryResponseSha256'] == expected_dict[dictionary_kind])
                    result['beat_frames'] = [round(row['beat_seconds'] * rate) for row in report['song']['plan']['notes']]
                    nominal_input = baseline['input']
                    seconds = nominal_input['start_seconds'] + np.r_[0., np.cumsum([n['beats'] for n in nominal_input['notes'][:-1]])] * 60 / nominal_input['bpm']
                    local = {'ui_and_assets': input_ok and dictionary_ok and run['engine'] == engine
                             and run['servedWasmSha256'] == binary_hash and not run['errors'] and run['recovered']
                             and (spec['rejection_contains'] in (run['rejected'] or '') if warmed else run['rejected'] is None),
                             'pcm_and_upstream': rate == native_rate == limits['output_rate_hz'] and audio.dtype == np.float32
                             and result['hashes']['pcm'] == expected['pcm'] and result['upstream_pcm']['first_frame_over_tolerance'] is None,
                             'score_and_observations': result['hashes'] == expected,
                             'beats_and_schedule': result['beat_frames'] == np.rint(seconds * rate).astype(int).tolist()
                             and clocks_schedule(report, limits, worklet),
                             'trace_requested': ('startupTrace' in report) == traced}
                except (OSError, KeyError, ValueError, subprocess.CalledProcessError) as error:
                    result['error'] = str(error)
                    local = {'capture_and_comparison_completed': False}
                trials.append(result)
                checks.update({f'{label}/{key}': passed for key, passed in local.items()})
                cross.clocks.compress_outputs(folder)
    medians, attribution = compare_groups(trials, spec, checks)
    return {'checks': checks, 'trials': trials, 'medians': medians, 'attribution': attribution,
            'reference_hashes': expected}


def clocks_schedule(report, limits, worklet):
    return (report['callbacks'] == worklet['expected_active_callbacks'] and report['discontinuities'] == 0
            and report['realtime']['startupCallbacks'] >= worklet['startup_contiguous_callbacks']
            and cross.clocks.check_schedule(report, limits, worklet))


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
    reference = {name: song.verified_path(prior, name) for name in ('summary.json', 'artifacts/1-chromium/browser.json.gz',
                 'artifacts/reference/pcm-128.wav', 'artifacts/reference/upstream-pcm.f32.gz', 'artifacts/vocal_wasm.wasm')}
    if prior[1]['status'] != 'pass' or not all(song.wasm.read_json(reference['summary.json'])['checks'].values()):
        parser.error('歌唱の基準実行が合格条件を満たしません')
    for path in (song.CASE, live_path, source):
        hashes = [item['sha256'] for item in prior[1]['inputs'] if item['path'].endswith('/' + path.name)]
        if hashes != [song.sha256(path)]:
            parser.error(f'保存済み歌唱の {path.name} と入力が一致しません')
    spec = study['measurement']
    if (len(spec['browser_order']) != len(spec['condition_order']) or not spec['browser_order']
            or any(sorted(order) != ['chromium', 'firefox'] for order in spec['browser_order'])
            or any(sorted(order) != sorted(CONDITIONS) for order in spec['condition_order'])):
        parser.error('各ラウンドには両ブラウザと全比較条件を一度ずつ含めてください')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, live_path, song.CASE, source, prior[0] / 'manifest.json', *reference.values(),
              *song.web_sources(), *song.shared.candidate_sources(), Path(__file__).resolve(),
              *(Path(module.__file__) for module in (song, cross, cross.clocks, song.wasm, song.shared,
                                                     cross.clocks.release.stored))]
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'reference_run': prior[0].name,
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return song.shared.record_measurement(args.run_id, CASE, inputs, metadata,
        lambda artifacts, execute: measure(study, fixed, live, source, reference, artifacts, execute, bun),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
