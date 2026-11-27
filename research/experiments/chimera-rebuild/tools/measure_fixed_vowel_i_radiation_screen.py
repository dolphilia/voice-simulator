"""固定母音画面の放射観測、表示時刻、保存データをCLIと上流に照合する。"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import firwin

import measure_fixed_vowel_i_wasm_radiation as prior
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-radiation-screen.json'
ROOT, WEB = prior.web.ROOT, prior.web.WEB
HOST = WEB / 'tools/capture-fixed-radiation-screen.mjs'
READ = prior.cli.READ
FIELDS = ('wall_radiation_flow_cm3_s', 'lip_flow_cm3_s', 'nose_flow_cm3_s',
          'radiation_flow_cm3_s', 'radiation_derivative_cm3_s2')
READOUT = ('PCM', '壁', '口端', '鼻端', '合算', '放射微分')
UNITS = ('振幅', 'cm³/s', 'cm³/s', 'cm³/s', 'cm³/s', 'cm³/s²')
RENDERS = ('implicit', 'observed', 'disabled')
EVIDENCE = ('native-input.json', 'native-internal-input.json', 'native-frame.csv', 'native-internal.csv', 'native-pcm.wav',
            'replay-frame.csv', 'replay-pcm.wav', 'vocal_wasm.wasm',
            *(f'{browser}/{name}' for browser in ('chromium', 'firefox') for name in (
                'screen.json', 'observed-case.json', *(f'{render}.{ext}' for render in RENDERS for ext in ('wav', 'json')))))


def archive_inputs(study):
    coupled = prior.cli.coupled
    cfg = study['measurement']
    record, manifest, definition = coupled.smoothing.verified_reference(
        cfg['upstream_reference'], study['upstream_revision'])
    run, header = record
    entry, = (item for item in header['inputs'] if item['path'].endswith(f"/cases/{study['fixed_voice_case']}"))
    voice = run / header['source_snapshot'] / entry['path']
    if sha256(voice) != entry['sha256'] or sha256(voice) != cfg['input_sha256']:
        raise ValueError('固定発声の登録ケースと上流の保存ケースが一致しません')
    return {'upstream-manifest.json': manifest, 'upstream-case.json': definition, 'source.json': voice,
            **{name: coupled.verified_path(record, f'artifacts/{name}')
               for name in ('upstream-trace.csv', 'upstream-voice.f32')}}


def rendered_native(source, out, block, execute):
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    base = READ(source)
    options = {'radiation_components': True}
    content = {**base, 'fixed_voice_probe': options}
    direct = out / 'native-input.json'
    direct.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
    execute([*cli, 'render', str(direct), str(out / 'native-frame.csv')])
    internal = out / 'native-internal-input.json'
    internal.write_text(json.dumps({**content, 'fixed_voice_probe': {**options, 'internal_trace': True}},
                                   ensure_ascii=False, indent=2) + '\n')
    execute([*cli, 'render', str(internal), str(out / 'native-internal.csv')])
    execute([*cli, 'render-pcm', str(direct), str(out / 'native-pcm.wav'), '--no-trace', str(block)])
    replay = out / 'chromium/observed-case.json'
    execute([*cli, 'render', str(replay), str(out / 'replay-frame.csv')])
    execute([*cli, 'render-pcm', str(replay), str(out / 'replay-pcm.wav'), '--no-trace', str(block)])


def window(frame, zoomed, step, frames):
    if not zoomed:
        return 0, frames
    first = frame // step * step
    return first, min(first + step, frames)


def verify_cursor(row, frame, bounds, rate, values):
    first, end = bounds
    percent = (frame - first) * 100 / max(1, end - first - 1)
    time = lambda index: f'{1000 * index / rate:.5f} ms'
    displayed = [float(entry['displayed']) for entry in row['values']]
    return (
        row['frame'] == frame and row['time'] == time(frame)
        and row['accessibleTime'] == f'{frame}フレーム、{time(frame)}'
        and row['bounds'] == [time(first), time(end - 1)]
        and row['plots'] == ['PCMの時系列', '放射成分の時系列', '放射微分の時系列']
        and len(row['cursorPercent']) == 3 and all(abs(x - percent) < 0.0002 for x in row['cursorPercent'])
        and [entry['label'] for entry in row['values']] == list(READOUT)
        and [entry['unit'] for entry in row['values']] == list(UNITS)
        and np.array_equal([entry['value'] for entry in row['values']], values)
        and bool(np.allclose(displayed, values, atol=0, rtol=5e-8)))


def overview_error(overview, pcm):
    width, height = overview['width'], overview['height']
    peak = float(np.abs(pcm).max())
    errors = []
    for entry in overview['pixels']:
        pixel = entry['x']
        span = pcm[pixel * len(pcm) // width:(pixel + 1) * len(pcm) // width]
        expected = [height / 2 - float(value) * (height / 2 - 3) / peak
                    for value in (span.max(), span.min())]
        if entry['top'] is None or entry['bottom'] is None:
            raise ValueError(f'PCM描画の画素を取得できません（列{pixel}）')
        errors.extend(abs(actual - y) for actual, y in zip((entry['top'], entry['bottom']), expected, strict=True))
    return max(errors)


def analyze(study, archive, out):
    cfg = study['measurement']
    base = READ(archive['source.json'])
    first, frames = cfg['comparison_output_frames']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    factor = fs // rate
    count = frames * factor
    samples = np.arange(factor - 1, count, factor)
    read_cols = prior.cli.coupled.pcm.read_columns
    frame = read_cols(out / 'native-frame.csv', frames)[1]
    whole = read_cols(out / 'native-internal.csv', count)[1]
    upper = read_cols(archive['upstream-trace.csv'], frames)[1]
    obs = np.column_stack([frame[key] for key in FIELDS])
    read_pcm = prior.cli.coupled.read_pcm
    native = read_pcm(out / 'native-pcm.wav', frames, rate)
    same = prior.cli.coupled.same_bits
    total = (whole[FIELDS[0]] + whole[FIELDS[1]]) + whole[FIELDS[2]]
    derivative = np.diff(total, prepend=0.) / (1.0 / fs)
    taps = firwin(factor * 24 + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    before = prior.cli.radiation.linear_pcm(derivative, taps, np.exp(-2 * np.pi * 25 / rate), factor,
                                           base['voice']['output_gain'])
    independent = prior.cli.coupled.pcm.independent_limiter(before, rate)[2]
    wasm_hash = sha256(out / 'vocal_wasm.wasm')
    expected_case = {**base, 'fixed_voice_probe': {'radiation_components': True}}
    checks = {
        'case_inputs_and_output_clock': (
            first == 0 and READ(out / 'native-input.json') == expected_case
            and READ(out / 'native-internal-input.json') == {
                **expected_case, 'fixed_voice_probe': {'radiation_components': True, 'internal_trace': True}}
            and base['voice']['pressure_cm_h2o'] == 7.2 and base['voice']['output_sample_rate_hz'] == rate
            and base['fixed_airway']['sample_rate_hz'] == fs and base['fixed_airway']['sample_count'] == count
            and np.array_equal(whole['internal_sample'], np.arange(count))
            and np.array_equal(frame['frame'], np.arange(frames))
            and np.array_equal(frame['internal_sample'], samples)
            and all(same(frame[key], whole[key][samples]) for key in FIELDS)),
        'independent_flow_sum_derivative_and_pcm': (
            same(total, whole[FIELDS[3]]) and same(derivative, whole[FIELDS[4]]) and same(independent, native)),
        'downloaded_case_replays_through_cli': (
            (out / 'native-frame.csv').read_bytes() == (out / 'replay-frame.csv').read_bytes()
            and same(read_pcm(out / 'replay-pcm.wav', frames, rate), native)),
    }
    upper_audio = np.fromfile(archive['upstream-voice.f32'], dtype='<f4')
    upper_pcm = prior.wasm.compare_pcm(native, upper_audio, cfg['upstream_pcm_absolute_error_lt'])
    shared = ('lip_flow_cm3_s', 'nose_flow_cm3_s', 'radiation_derivative_cm3_s2')
    upper_states = prior.wasm.compare_states(
        np.column_stack([frame[k] for k in shared]), np.column_stack([upper[k] for k in shared]), shared,
        np.arange(frames), cfg['upstream_shared_trace_peak_relative_error_lt'])
    checks['fixed_upstream_clock_shared_series_and_pcm'] = (
        np.array_equal(upper['internal_sample'], samples) and all(item['status'] for item in upper_states.values())
        and upper_pcm['maximum_absolute_error'] < cfg['upstream_pcm_absolute_error_lt'])
    verified = {}
    zoom_frames = round(cfg['zoom_ms'] * rate / 1000)
    selected = np.column_stack([native, obs])
    for browser in cfg['browsers']:
        folder = out / browser
        reading = READ(folder / 'screen.json')
        reports = {key: READ(folder / f'{key}.json') for key in RENDERS}
        observed = reports['observed'].copy()
        radiation = observed.pop('radiation')
        audio = {key: read_pcm(folder / f'{key}.wav', frames, rate) for key in RENDERS}
        checkpoints = np.arange(cfg['worklet_observation_stride'] - 1, frames, cfg['worklet_observation_stride'])
        states = np.asarray(observed['observations'])
        cols = observed['columns'][2:]
        checks[f'{browser}/served_wasm_and_optional_analysis'] = (
            reading['kind'] == browser and reading['servedWasm'] == [wasm_hash] and not reading['errors']
            and reading['checkedInitially'] is False and reading['states'] == [
                {'checked': False, 'scope': 0, 'replay': 0}, {'checked': True, 'scope': 1, 'replay': 1},
                {'checked': False, 'scope': 0, 'replay': 0}]
            and reports['implicit'] == reports['disabled'] == observed
            and READ(folder / 'observed-case.json') == expected_case)
        checks[f'{browser}/report_clock_and_pcm_match_cli'] = (
            observed['caseId'] == base['id'] and observed['sampleRate'] == observed['workletSampleRate'] == rate
            and observed['outputFrames'] == observed['framesRendered'] == frames
            and observed['stableWasmBuffers'] is True
            and observed['firstContextFrame'] == observed['discontinuities'] == 0
            and observed['columns'][:2] == ['context_frame', 'frames_rendered']
            and np.array_equal(states, np.column_stack(
                [checkpoints, checkpoints + 1, *(frame[key][checkpoints] for key in cols)]))
            and all(same(data, native) for data in audio.values()))
        checks[f'{browser}/radiation_download_matches_all_frames'] = (
            radiation['columns'] == list(FIELDS)
            and np.array_equal(np.asarray(radiation['values']).reshape(-1, len(FIELDS)), obs))
        checks[f'{browser}/cursor_samples_and_zoom'] = all(
            verify_cursor(row, index, window(index, zoomed, zoom_frames, frames), rate, selected[index])
            for zoomed, key in ((False, 'all'), (True, 'zoom'))
            for index, row in zip(cfg['cursor_frames'], reading['cursors'][key], strict=True))
        origin, end = window(cfg['cursor_frames'][-2], True, zoom_frames, frames)
        pointer = reading['pointer']
        expected_pointer = origin + int(np.floor(pointer['fraction'] * (end - origin - 1) + 0.5))
        checks[f'{browser}/keyboard_and_pointer_share_clock'] = (
            reading['keyboard'] == [0, 1, frames - 1]
            and verify_cursor(pointer, expected_pointer, (origin, end), rate, selected[expected_pointer]))
        narrow = reading['mobile']
        checks[f'{browser}/mobile_scope_fits_viewport'] = (
            narrow['viewport'] == cfg['viewports']['mobile'][0]
            and 0 < narrow['sectionWidth'] <= narrow['viewport']
            and narrow['sectionWidth'] == narrow['scrollWidth'] and narrow['controlCount'] == 2)
        peak_error = overview_error(reading['overview'], native)
        checks[f'{browser}/overview_preserves_pcm_extrema'] = peak_error <= cfg['overview_canvas_max_pixel_error']
        verified[browser] = {'version': reading['version'], 'pointer_frame': pointer['frame'],
                             'overview_pcm_pixel_error': peak_error, 'mobile_panel_width_px': narrow['sectionWidth']}
    checks['browsers_download_identical_data'] = all(
        (out / cfg['browsers'][0] / filename).read_bytes() == (out / browser / filename).read_bytes()
        for browser in cfg['browsers'][1:]
        for filename in ('observed-case.json', *(f'{name}.{ext}' for name in RENDERS for ext in ('json', 'wav'))))
    return {'checks': checks, 'frames': frames, 'sample_rate_hz': rate, 'wasm_sha256': wasm_hash,
            'browsers': verified, 'upstream_derivative_and_port_flows': upper_states, 'upstream_pcm': upper_pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)
    source = WORKSPACE / 'cases' / study['fixed_voice_case']
    if sha256(source) != study['measurement']['input_sha256']:
        parser.error('画面の固定母音ケースが登録時の内容と一致しません')
    firefox = args.firefox.resolve(strict=True)
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']

    def measure(out, execute):
        with TemporaryDirectory(dir=out.parent) as build:
            execute([*bun, 'run', 'build', '--outDir', build], cwd=WEB, stdout=out / 'web-build.log')
            binary, = sorted(Path(build).glob('assets/vocal_wasm-*.wasm'))
            shutil.copyfile(binary, out / 'vocal_wasm.wasm')
            execute(['node', str(HOST), build, str(CASE), str(out), str(firefox)], cwd=WEB)
        rendered_native(source, out, study['measurement']['host_block_frames'], execute)
        return analyze(study, archive, out)

    inputs = [CASE, source, Path(__file__), HOST, *archive.values(), *prior.web.web_sources(),
              *prior.cli.SHARED.candidate_sources(),
              *(Path(module.__file__) for module in (prior, prior.wasm, prior.web, prior.cli, prior.cli.coupled,
                                                     prior.cli.coupled.pcm, prior.cli.radiation)),
              *(UPSTREAM / name for name in ('src/worklet/processor.ts', 'src/ui/components/Stroboscope.tsx',
                                            'crates/chimera/tests/engine.rs'))]
    details = {'case_id': study['id'], 'case_revision': study['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '--version'], text=True).strip(),
               'firefox_binary': str(firefox), 'firefox_binary_sha256': sha256(firefox)}
    return prior.cli.SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
