"""子ども体型・混合体型の乱流源を、録音・固定上流・ブラウザで照合する。"""

import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_uniform_tube as shared
from measure_duet_head_pressure import UPPER_WASM
from measure_duet_head_turbulence import CAPTURE, browser_checks, controlled, origin, source_at
from measure_duet_telemetry import CASE as TELEMETRY_CASE, Track, candidate_render, upper_render
from measure_duet_words import prior
from measure_fan_crossing_allocations import verified_path
from measure_wasm_fixed import read_json
from measure_worklet_fixed import ROOT, WEB, web_sources
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

CASE = WORKSPACE / 'cases/duet-head-turbulence-body.json'
PROBE = Path(__file__).with_name('upstream_duet_body_probe.rs')
DICTIONARY = UPSTREAM / 'public/data/cmudict.txt.gz'
SHOW_ID = 'duet-turbulence-body'


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def select_rows(rows, layout, spec, diagnostic):
    lo, hi = spec['observation_window_seconds']
    threshold = 10 ** (3.2 * diagnostic['minimum_intensity'])
    rate = spec['sample_rate_hz']
    eligible = [r for r in rows if lo <= r['sample'] / rate <= hi and r['noiseLevel'] > threshold]
    glottal = [r for r in eligible if r['noiseNode'] == layout['glottis_port']]
    oral_span = layout['oral']
    oral = [r for r in eligible if oral_span['base'] <= r['noiseNode'] < oral_span['base'] + oral_span['cells'] - 1]
    if not glottal or not oral:
        raise ValueError('事前登録の観測区間に声門と口腔の乱流源が揃いません')
    selected = {}
    for kind, candidates in [('glottal', glottal), ('oral', oral)]:
        row = max(candidates, key=lambda r: r['noiseLevel'])
        selected[kind] = dict(row, s_cm=origin(layout, row, diagnostic))
    return selected


def make_candidate(spec, stems, out, execute):
    show = out / SHOW_ID
    show.mkdir()
    rate = spec['sample_rate_hz']
    mix = np.zeros(spec['show_frames'])
    metadata, tracks, layouts, sounds = [], [], [], []
    for index, (stem, voice) in enumerate(zip(stems, spec['voices'], strict=True), 1):
        data = read_json(stem)
        song = data['song_voice']
        song['body'] = voice['body']
        source = out / f'candidate-{index}.json'
        write(source, data)
        settings = out / f'candidate-{index}-settings.json'
        execute([str(WORKSPACE / 'target/release/vocal-cli'), 'inspect', str(source)], stdout=settings)
        layout = read_json(settings)['noise_branches']
        wave, tele = candidate_render(source, index, out, execute, block=(128 if index == 1 else 77))
        tele.rename(show / tele.name)
        track = Track(show / tele.name)
        tracks.append(track)
        layouts.append(layout)
        wav_rate, pcm = wavfile.read(wave)
        if wav_rate != rate or pcm.dtype != np.float32 or pcm.ndim != 1 or len(pcm) > len(mix) or not np.isfinite(pcm).all():
            raise ValueError(f'声部{index}のPCMの形式、長さまたは値が条件外です')
        mix[:len(pcm)] += voice['gain'] * pcm.astype(float)
        sounds.append((song, len(pcm)))
        metadata.append({'name': '子ども' if index == 1 else '混合体型', 'tele': tele.name, 'noise_branches': layout})
    peak = float(np.max(np.abs(mix)))
    if not 0 < peak < 32767 / 32768:
        raise ValueError('混合音源の振幅が範囲外です')
    wavfile.write(show / 'mix.wav', rate, np.rint(mix * 32768).astype('<i2'))
    write(show / 'show.json', {'title': '二つの体型の乱流源', 'audio': 'mix.wav',
                              'sample_rate_hz': rate, 'frames': len(mix), 'voices': metadata})
    return show, tracks, layouts, sounds


def make_upper(spec, sounds, out, execute):
    executable = shared.build_upstream_probe(PROBE, out, execute, extra_libraries=('serde_json',))
    results = []
    with TemporaryDirectory(dir=out.parent) as temp:
        dictionary = Path(temp) / 'cmudict.txt'
        with gzip.open(DICTIONARY, 'rb') as compressed, dictionary.open('wb') as unpacked:
            shutil.copyfileobj(compressed, unpacked)
        for i, ((song, _), voice) in enumerate(zip(sounds, spec['voices'], strict=True), 1):
            score = song['score']
            fixture = {'body': voice['body_mix'], 'sample_rate_hz': spec['sample_rate_hz'], 'hop_samples': spec['hop_samples'],
                       'score': {'lyrics': score['lyrics'], 'bpm': score['bpm'], 't0': score['start_seconds'],
                                 'vibrato': song['vibrato_cents'], 'notes': [[n['midi'], n['beats']] for n in score['notes']]}}
            path = out / f'upper-{i}-input.json'
            write(path, fixture)
            result = out / f'upper-{i}-noise.json'
            execute([str(executable), str(path), str(dictionary), str(out / f'upper-{i}.f32le')], stdout=result)
            results.append(read_json(result))
    return results


def compare_upstream_child(song, measured, out, execute):
    wav, tele, pcm_kept = upper_render(
        {'start_seconds': song['score']['start_seconds'], 'body': 'child',
         'midi': [n['midi'] for n in song['score']['notes']]}, song, 1, out, execute)
    rate, cli = wavfile.read(wav)
    probe = np.fromfile(out / 'upper-1.f32le', dtype='<f4')
    track = Track(tele)
    return {
        'child_probe_matches_normal_upper_pcm': rate == track.rate and cli.dtype == np.float32
        and pcm_kept and np.array_equal(cli.view('<u4'), probe.view('<u4')),
        'child_probe_matches_normal_upper_telemetry': len(measured['rows']) == track.rows and all(
            raw['sample'] == i * track.hop and all(raw[k] == v for k, v in source_at(track, i).items())
            for i, raw in enumerate(measured['rows'])),
    }


def compare_upper_positions(readout, candidate_rows, candidate_layouts, upper, diagnostic):
    checks, comparison = {}, []
    for i, (via_wasm, rows, layout, native) in enumerate(zip(
            readout, candidate_rows, candidate_layouts, upper, strict=True), 1):
        above = via_wasm['layout']
        checks[f'voice_{i}_native_and_wasm_layout'] = above == native['layout']
        errors = []
        for observed, source in zip(via_wasm['nativeFrames'], native['rows'], strict=True):
            position = origin(native['layout'], source, diagnostic)
            expected = -1 if position is None else position
            errors.append(abs(observed['s'] - expected))
            if observed['sample'] != source['sample']:
                raise ValueError('固定上流のNativeとWASMでサンプル位置が一致しません')
        checks[f'voice_{i}_native_sources_project_in_wasm'] = max(errors) <= 1e-12
        by_sample = {row['sample']: row for row in rows}
        for observed in via_wasm['frames']:
            source = by_sample[observed['sample']]
            if any(observed[k] != source[k] for k in ('noiseNode', 'noiseLevel', 'phLen', 'orLen')):
                raise ValueError('Pythonと上流のCHTLの読み出しが一致しません')
            own = origin(layout, source, diagnostic)
            swapped = origin(above, source, diagnostic)
            if observed['s'] != (-1 if swapped is None else swapped):
                raise ValueError('枝配置を差し替えた対照で独立式と上流の結果が一致しません')
            comparison.append({'voice': i, **source, 'own_s_cm': own, 'upper_layout_s_cm': swapped})
    checks['wrong_layout_changes_an_active_position'] = any(
        row['noiseLevel'] > 1.5 and row['own_s_cm'] != row['upper_layout_s_cm'] for row in comparison)
    return checks, comparison


def measure(spec, stems, reference, out, execute, bun):
    execute(['cargo', 'build', '--locked', '--release', '-p', 'vocal-cli'])
    execute([*bun, 'test', 'tests/tele.test.ts', 'tests/transport.test.ts'], cwd=UPSTREAM, stdout=out / 'upper-tests.log')
    show, tracks, layouts, sounds = make_candidate(spec, stems, out, execute)
    upper = make_upper(spec, sounds, out, execute)
    diagnostic = reference['diagnostic']
    fmt = read_json(TELEMETRY_CASE)['format']
    checks = compare_upstream_child(sounds[0][0], upper[0], out, execute)
    candidate_rows, selections, upper_selections = [], [], []
    for i, (track, layout, sound, voice, native) in enumerate(zip(
            tracks, layouts, sounds, spec['voices'], upper, strict=True), 1):
        body = np.float32(list(voice['body_mix'].values())).tolist()
        cells = [layout[k]['cells'] for k in ('pharynx', 'oral')]
        checks[f'voice_{i}_recorded_body_grid_and_clock'] = (
            track.body == body and track.header[3:5] == cells == voice['wall_cells'] and track.follows_clock(fmt, sound[1]))
        rows = [{'sample': row * track.hop, **source_at(track, row)} for row in range(track.rows)]
        candidate_rows.append(rows)
        selections.append(select_rows(rows, layout, spec, diagnostic))
        upper_selections.append(select_rows(native['rows'], native['layout'], spec, diagnostic))
    quiet = [{'voice': i, 'sample': 0, 'visible': False} for i in (1, 2)]
    active = [{'voice': i, 'sample': row['sample'], 'visible': True}
              for i, selected in enumerate(selections, 1) for row in selected.values()]
    samples = sorted({item['sample'] for item in active})
    rendered = {**spec, 'show_id': SHOW_ID, 'diagnostic': diagnostic,
                'browser': {'sample_rate_hz': spec['sample_rate_hz'], 'samples': [0, *samples],
                            'live_seeks': samples[::-1], 'viewports': reference['browser']['viewports'],
                            'required_live_sources': quiet + active}}
    config = out / 'browser-case.json'
    write(config, rendered)
    with TemporaryDirectory(dir=out.parent) as dist:
        execute([*bun, 'run', 'build', '--outDir', dist], cwd=WEB, stdout=out / 'browser-build.log')
        shutil.copytree(show, Path(dist) / 'shows' / SHOW_ID)
        execute([*bun, str(CAPTURE), str(config), str(UPSTREAM), str(out), str(show), dist], cwd=WEB)
    observed = read_json(out / 'browser-turbulence.json')
    controls, detail = controlled(read_json(out / 'controlled-turbulence.json'), rendered)
    positions, compare = compare_upper_positions(read_json(out / 'recorded-turbulence.json'),
                                                candidate_rows, layouts, upper, diagnostic)
    checks.update(controls | positions)
    checks.update(legacy_playback=observed['metadata']['legacyPlayback'],
                  swapped_layout_rejected='テレメトリの形式' in observed['metadata']['swappedBodies'],
                  wrong_rate_rejected='テレメトリの形式' in observed['metadata']['badLayout'])
    viewports = []
    for name in observed['viewports']:
        log = read_json(out / name)
        result, summary = browser_checks(rendered, log, tracks, layouts)
        result['uses_recorded_body_per_head'] = all(
            head['body'] == track.header[5] for state in (*log['paused'], *(r['observed'] for r in log['live']))
            for head, track in zip(state['heads'], tracks, strict=True))
        checks.update({f'{log["width"]}_{key}': value for key, value in result.items()})
        viewports.append(summary)
    return {'checks': checks, 'browser': observed['browser'], 'control': detail, 'candidate_selection': selections,
            'upper_selection': upper_selections, 'compared_locations': compare, 'viewports': viewports,
            'candidate_layouts': layouts, 'upper_layouts': [v['layout'] for v in upper]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDが必要です')
    spec = read_json(CASE)
    rev = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if rev != spec['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        parser.error('変更のない固定上流版が必要です')
    ref = spec['reference']
    reference = CASE.parent / ref['turbulence_case']
    reference_manifest = WORKSPACE / 'runs' / ref['turbulence_run'] / 'manifest.json'
    if read_json(reference_manifest)['status'] != 'pass' or sha256(UPPER_WASM) != ref['upper_wasm_sha256']:
        parser.error('保存済みの乱流の実行と固定上流のWASMが必要です')
    source = prior(ref['transport_run'], 'duet-transport', rev, ref['transport_manifest_sha256'])
    stems = [verified_path(source, f'artifacts/voice-{i}.json') for i in (1, 2)]
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    tools = [WORKSPACE / f'tools/{name}.py' for name in (
        'measure_duet_head_turbulence', 'measure_duet_telemetry', 'measure_duet_head_airflow',
        'measure_duet_head_pressure', 'measure_uniform_tube')]
    inputs = [CASE, reference, reference_manifest, source[0] / 'manifest.json', *stems, TELEMETRY_CASE,
              Path(__file__).resolve(), PROBE, CAPTURE, DICTIONARY, UPPER_WASM,
              *tools, *web_sources(), *shared.candidate_sources()]
    details = {'case_id': spec['id'], 'case_revision': spec['revision'], 'upstream_revision': rev,
               'upstream_wasm_sha256': ref['upper_wasm_sha256'], 'analysis_directory': str(Path.cwd()),
               'analysis_command': [sys.executable, *sys.argv],
               'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    return shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda out, run: measure(spec, stems, read_json(reference), out, run, bun), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
