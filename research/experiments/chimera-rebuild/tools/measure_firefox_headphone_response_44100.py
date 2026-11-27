"""44.1 kHzの連続した既知音でcubebとタップの複素振幅比を測る。"""

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

from inspect_firefox_cubeb_output import host_tick_ms
from measure_csd_envelope_timing import verified_file
from measure_cubeb_output_callback import load_blocks
from measure_firefox_output_marker import BROWSER
from measure_safari_process_tap_calibration import OUTPUT_DEVICE, capture_on_output
from measure_speech_timing import read
from measure_tsp_listening import hydrate_run
from measure_uniform_tube import record_measurement
from measure_worklet_fixed import ROOT, WEB
from measure_worklet_tsp_device_tap import capture_tap
from smooth_tap_marker import chip_values, find_anchor, marker_pcm
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/firefox-process-tap-headphone-response-44100.json'


def fixture(case, count):
    spec = case['tone_probe']
    out = marker_pcm(count, case['marker'])
    start, stop = spec['first'], spec['last_exclusive']
    times = np.arange(stop - start)
    blend = np.minimum(1, np.minimum(times, times[-1] - times) / spec['blend_frames'])
    phase = 2 * np.pi * times[:, None] * np.asarray(spec['frequencies_hz']) / case['sample_rate_hz']
    tones = np.sin(phase + spec['phases_radians']).sum(axis=1) * spec['amplitude']
    out[start:stop] = (1 - blend) * out[start:stop] + blend * tones
    return out


def read_stereo(path):
    return np.fromfile(path, dtype='<f4').reshape(-1, 2).astype(float)


def anchors(pcm, spec, bounds, *, trailing_search_frames=None):
    if not np.isfinite(pcm).all():
        return None
    width = spec['window_frames']
    first, last = (bounds[key] for key in ('first', 'last_exclusive'))
    side = (pcm[:, 0] - pcm[:, 1]) / 2
    chips = chip_values(spec['marker'])
    left = find_anchor(side, chips, spec, first)
    if left is None:
        return None
    origin = left['offset'] - first
    trailing_frame = last - width
    start, stop = 0, len(side)
    if trailing_search_frames is not None:
        nominal = origin + trailing_frame
        start = max(0, nominal - trailing_search_frames)
        stop = min(len(side), nominal + trailing_search_frames + width)
    right = find_anchor(side[start:stop], chips, spec, trailing_frame)
    if right is None:
        return None
    right['offset'] += start
    shift = right['offset'] - (last - width) - origin
    advance = shift - right['fraction'] + left['fraction']
    return {'origin_in_pcm': origin, 'integer_advance': shift, 'endpoint_advance_frames': advance,
            'first': left, 'last': right}


def continuous_blocks(blocks, offset, clock, first, last, width, pcm_length):
    sequence = [(row[offset], row) for row in blocks]
    if (not sequence or sequence[0][0] != 0 or sequence[-1][0] + sequence[-1][1]['frames'] != pcm_length
            or any(b != a + row['frames'] for (a, row), (b, _) in zip(sequence, sequence[1:]))):
        return None
    selected = [(a, row) for a, row in sequence if a < last and a + row['frames'] > first]
    if not selected or first < selected[0][0] or last > selected[-1][0] + selected[-1][1]['frames']:
        return None
    if any(row['frames'] != width or row.get(clock) is None or not np.isfinite(row[clock]) for _, row in selected):
        return None
    if any(b[clock] - a[clock] != a['frames'] for (_, a), (_, b) in zip(selected, selected[1:])):
        return None
    return [row for _, row in selected]


def fit_tones(samples, basis):
    coefficients = 2 * basis.conj().T @ samples / len(samples)
    reconstructed = (basis @ coefficients).real
    amplitude = np.linalg.norm(samples)
    residual = np.linalg.norm(samples - reconstructed) / amplitude if amplitude else 0
    return coefficients, float(residual)


def measure_tones(cubeb, tap, cb, tb, case, model, review=None):
    analysis = case['analysis']
    f = np.asarray(case['tone_probe']['frequencies_hz'])
    rate = case['sample_rate_hz']
    w = 2 * np.pi * f / rate
    span = review['subwindow_frames'] if review else analysis['window_frames']
    basis = np.exp(1j * np.arange(span)[:, None] * w)
    h = np.asarray(model['positive_offset_coefficients'])
    predicted = model['center_coefficient'] + 2 * np.cos(w[:, None] * np.arange(1, len(h) + 1)) @ h
    fractions = np.asarray([tb[key]['fraction'] - cb[key]['fraction'] for key in ('first', 'last')])
    starts = [start + step for start in analysis['first_frames']
              for step in range(0, analysis['window_frames'], span)]
    pilot_index = case['tone_probe']['frequencies_hz'].index(review['phase_reference_hz']) if review else None
    rows = []
    for start in starts:
        stop = start + span
        coefficients, errors = [], []
        for pcm, anchor in ((cubeb, cb), (tap, tb)):
            offset = anchor['origin_in_pcm']
            stereo = pcm[offset + start:offset + stop]
            side = (stereo[:, 0] - stereo[:, 1]) / 2
            fit, error = fit_tones(side, basis)
            coefficients.append(fit)
            errors.append(error)
        raw_ratio = coefficients[1] / coefficients[0]
        fraction = float(fractions.mean() if pilot_index is None else np.angle(raw_ratio[pilot_index]) / w[pilot_index])
        correction = np.exp(-1j * w * fraction)
        ratios = raw_ratio * correction
        model_error = ratios / predicted
        observed_amplitude = np.abs(ratios)
        rows.append({'source_frames': [start, stop], 'cubeb_residual': errors[0], 'tap_residual': errors[1],
                     'phase_correction_frames': fraction,
                     'frequencies': [
                         {'hz': float(hz), 'cubeb_amplitude': float(abs(coefficients[0][i])),
                          'tap_amplitude': float(abs(coefficients[1][i])),
                          'predicted_amplitude_ratio': float(abs(predicted[i])),
                          'amplitude_ratio': float(observed_amplitude[i]),
                          'amplitude_error': float(abs(observed_amplitude[i] - abs(predicted[i]))),
                          'raw_phase_degrees': float(np.angle(raw_ratio[i], deg=True)),
                          'phase_degrees': float(np.angle(ratios[i], deg=True)),
                          'phase_error_degrees': float(np.angle(model_error[i], deg=True))}
                         for i, hz in enumerate(f)]})
    qualified = rows
    if review:
        for row in rows:
            row['stationary'] = (max(row['cubeb_residual'], row['tap_residual']) <= analysis['maximum_tone_residual']
                and abs(row['phase_correction_frames']) <= review['maximum_pilot_phase_offset_frames'])
        qualified = [row for row in rows if row['stationary']]
    checks = {
        'cubeb_matches_source_tone_levels': all(
            abs(row['cubeb_amplitude'] - case['tone_probe']['amplitude']) <= analysis['maximum_cubeb_source_amplitude_error']
            for window in rows for row in window['frequencies']),
        'tone_fit_residuals': bool(qualified) and all(
            max(row['cubeb_residual'], row['tap_residual']) <= analysis['maximum_tone_residual'] for row in qualified),
        'tap_matches_fir_amplitude': bool(qualified) and all(
            row['amplitude_error'] <= limit for window in qualified for row, limit in
            zip(window['frequencies'], analysis['maximum_model_amplitude_errors'], strict=True)),
        'tap_matches_fir_phase': bool(qualified) and all(
            abs(row['phase_error_degrees']) <= analysis['maximum_model_phase_error_degrees']
            for window in qualified for row in window['frequencies']),
        'gain_repeats_across_windows': bool(qualified) and all(
            max(values) - min(values) <= analysis['maximum_repeated_amplitude_difference']
            for values in zip(*[[row['amplitude_ratio'] for row in window['frequencies']]
                                for window in qualified], strict=True)),
    }
    if review:
        checks['registered_stationary_window_count'] = len(qualified) >= review['minimum_stationary_windows']
    return {'checks': checks, 'fractional_alignment_difference_frames': fractions.tolist(), 'windows': rows}


def analyze(folder, case, calibration, route, model, review=None):
    graph = read(folder / 'graph.json')
    ready = read(folder / 'trace-ready.json')
    played = np.fromfile(folder / 'graph.f32le', dtype='<f4')
    quantum = case['quantum_frames']
    anchor = case['anchor']
    first, last = anchor['first'], anchor['last_exclusive']
    reference = fixture(case, last)
    selected = route['selected']
    active = read(folder / 'browser.json')['output']
    device, = (d for d in active['devices'] if d['id'] == active['defaultOutput'])
    expected_device = case['output_device']
    checks = {'graph_matches_source': (len(played) == last and graph['startFrame'] == graph['scheduledFrame']
        and graph['inputFrames'] == [quantum] * (last // quantum)
        and graph['frames'] == list(range(graph['startFrame'], graph['startFrame'] + last, quantum))
        and ready == {'trustedClick': True, 'sampleRate': case['sample_rate_hz']}
        and np.max(np.abs(played - reference)) <= case['analysis']['maximum_graph_absolute_difference']),
        'headphone_and_rate': (selected['defaultOutput'] == active['defaultOutput']
            and (device['uid'], device['sampleRate'], device['bufferFrames']) ==
            (expected_device['uid'], case['sample_rate_hz'], expected_device['expected_frames'])),
        'original_output_restored': route['after']['defaultOutput'] == route['before']['defaultOutput']}
    checks = {name: bool(value) for name, value in checks.items()}
    result = {'checks': checks, 'output_device': device, 'rejected_streams': []}
    tape = read(folder / 'tap.json')
    tap = read_stereo(folder / 'tap.f32le')
    tb = anchors(tap, calibration, anchor)
    checks['tap_window_identified'] = bool(tb and tb['integer_advance'] == 0
        and (review or abs(tb['endpoint_advance_frames']) <= anchor['maximum_endpoint_change_frames']))
    if not checks['tap_window_identified']:
        return result
    tap_origin = tb['origin_in_pcm']
    tap_blocks = continuous_blocks(tape['blocks'], 'offset', 'sampleTime', tap_origin + first, tap_origin + last,
                                   case['analysis']['tap_expected_frames'], len(tap))
    checks['registered_tap_clock_and_format'] = bool(tap_blocks and tape['sampleRate'] == case['sample_rate_hz']
        and not tape['overflow'] and not tape['formatErrors'] and tape['frames'] == len(tap)
        and all(row.get('hostTime') is not None for row in tap_blocks)
        and all(b['hostTime'] > a['hostTime'] for a, b in zip(tap_blocks, tap_blocks[1:]))
        and np.isclose(tape['timebaseNumer'] / tape['timebaseDenom'] / 1e6, host_tick_ms(), rtol=1e-12, atol=0))
    streams = []
    for path in sorted((folder / 'cubeb').glob(f"cubeb-output-{tape['pid']}-*")):
        pcm = read_stereo(path / 'pcm.f32le')
        cb = anchors(pcm, calibration, anchor)
        if not cb or cb['integer_advance'] or abs(cb['endpoint_advance_frames']) > anchor['maximum_endpoint_change_frames']:
            result['rejected_streams'].append({'stream': path.name, 'reason': '前後のマーカー窓が連続しません'})
            continue
        with (path / 'format.csv').open(newline='') as file:
            formats, = csv.DictReader(file)
        for row in (blocks := load_blocks(path)):
            row['pcm_frame'] = row['pcm_byte_offset'] // 8
        origin = cb['origin_in_pcm']
        block_window = continuous_blocks(blocks, 'pcm_frame', 'sample_time', origin + first, origin + last,
                                         case['analysis']['cubeb_expected_frames'], len(pcm))
        if (block_window and set(map(float, formats.values())) == {case['sample_rate_hz']}
                and (path / 'state.txt').read_text().strip() == 'ready'
                and all(row['stage'] == 'data' and row['timestamp_flags'] & 3 == 3 for row in block_window)
                and all(b['host_time'] > a['host_time'] for a, b in zip(block_window, block_window[1:]))):
            streams.append((pcm, cb, path.name, block_window))
        else:
            result['rejected_streams'].append({'stream': path.name, 'reason': 'PCMの時計または形式を確認できません'})
    checks['one_continuous_cubeb_window'] = len(streams) == 1
    if not checks['one_continuous_cubeb_window']:
        return result
    pcm, cb, stream, blocks = streams[0]
    ends = ('first',) if review else ('first', 'last')
    checks['relative_fractional_alignment'] = all(
        abs(tb[key]['fraction'] - cb[key]['fraction']) <= anchor['maximum_anchor_fraction_difference_frames']
        for key in ends)
    measured = measure_tones(pcm, tap, cb, tb, case, model, review)
    checks.update(measured.pop('checks'))
    result.update(cubeb_anchor=cb, tap_anchor=tb, cubeb_stream=stream, tap_pid=tape['pid'],
                  cubeb_blocks_in_window=len(blocks), tap_blocks_in_window=len(tap_blocks or []), **measured)
    if review:
        chips = chip_values(calibration['marker'])
        side = (tap[:, 0] - tap[:, 1]) / 2
        result['trailing_markers'] = [
            {'source_start_frame': t, 'anchor': find_anchor(side, chips, calibration, t)}
            for t in review['trailing_marker_starts']]
    return result


def collect(folder, execute, case, binary, app):
    probe = folder / 'coreaudio-output-device'
    execute(['xcrun', 'swiftc', '-O', '-framework', 'CoreAudio', str(OUTPUT_DEVICE), '-o', str(probe)])
    effective = folder / 'effective-case.json'
    effective.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    cubeb = folder / 'cubeb'
    cubeb.mkdir()
    acquire = capture_tap(execute, folder, case['capture'], app)
    command = ['env', f'CHIMERA_FIREFOX={binary}', f'CHIMERA_CUBEB_OUTPUT_DIR={cubeb}',
               f"CHIMERA_CUBEB_OUTPUT_BLOCKS={case['snapshot_blocks']}", 'node', str(BROWSER),
               str(effective), str(folder), str(probe)]
    return capture_on_output(case, folder, probe, lambda: acquire(
        command, cwd=WEB, stdout=folder / 'browser-command.log'))


def capture(folder, execute, case, calibration, binary, app, model):
    route = collect(folder, execute, case, binary, app)
    return analyze(folder, case, calibration, route, model)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('firefox', type=Path)
    parser.add_argument('app', type=Path)
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    registered = args.case.resolve()
    review = None if registered == CASE else read(registered)
    if review is None:
        if args.run_id not in case['trial_ids']:
            parser.error('事前登録した試行IDを指定してください')
    elif (review['base_case'] != CASE.name or review['id'] != case['id']
          or args.run_id not in [item['review_run'] for item in review['capture_reviews']]
          or case['analysis']['window_frames'] % review['subwindow_frames']):
        parser.error('事前登録した補足ケースと試行IDを指定してください')
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    options = case['prior_fir']
    fit = hydrate_run(options['run'], options['case_id'], revision)
    fit_summary = verified_file(*fit, 'summary.json')
    if fit[1]['case_revision'] != options['case_revision']:
        parser.error('登録したFIRの実行版と一致しません')
    model = read(fit_summary)['models'][options['model']]
    if not model['passes_registered_transfer_criteria']:
        parser.error('検証済みのFIRを指定してください')
    cal = hydrate_run(case['safari_calibration_run'], 'safari-process-tap-smooth-marker-44100', revision)
    calibration_path = verified_file(*cal, 'artifacts/effective-case.json')
    calibration = read(calibration_path)
    if calibration['sample_rate_hz'] != case['sample_rate_hz']:
        parser.error('前後のマーカーの校正レートが一致しません')
    case['marker'] = calibration['marker']
    binary, app = args.firefox.resolve(strict=True), args.app.resolve(strict=True)
    hashes = {'firefox_binary_sha256': sha256(binary), 'firefox_xul_sha256': sha256(binary.with_name('XUL')),
              'tap_binary_sha256': sha256(app / 'Contents/MacOS/chimera-process-tap'),
              'tap_info_sha256': sha256(app / 'Contents/Info.plist')}
    reference = WORKSPACE / 'runs' / case['reference_capture'] / 'manifest.json'
    prior = read(reference)
    if prior['upstream_revision'] != revision or any(prior[key] != value for key, value in hashes.items()):
        parser.error('先行試験と同じFirefoxおよびプロセスタップを指定してください')
    subprocess.run(['/usr/bin/codesign', '--verify', str(app)], check=True)
    sources = [CASE, Path(__file__).resolve(), BROWSER, BROWSER.with_name('shared-context-marker.mjs'),
               BROWSER.with_name('shared-context-marker-worklet.js'), OUTPUT_DEVICE, reference,
               fit[0] / 'manifest.json', fit_summary, cal[0] / 'manifest.json', calibration_path,
               *(WORKSPACE / 'tools' / name for name in ('measure_worklet_live_song_process_tap.py',
                 'measure_worklet_tsp_device_tap.py', 'measure_firefox_output_marker.py',
                 'measure_safari_process_tap_calibration.py', 'measure_cubeb_output_callback.py',
                 'chimera-cubeb-output-snapshot.patch', 'chimera_process_tap.swift', 'smooth_tap_marker.py'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], **hashes}
    if review:
        capture_run, = [item['capture_run'] for item in review['capture_reviews'] if item['review_run'] == args.run_id]
        folder = WORKSPACE / 'runs' / capture_run
        manifest_path = folder / 'manifest.json'
        manifest = read(manifest_path)
        for key, value in (({'run_id': capture_run} | {k: v for k, v in details.items() if k != 'analysis_command'}).items()):
            if manifest.get(key) != value:
                parser.error('元の収録とケースまたはバイナリが異なります')
        names = ['effective-case.json', 'graph.f32le', 'graph.json', 'trace-ready.json', 'browser.json',
                 'output-device.json', 'tap.json', 'tap.f32le']
        originals = [f'artifacts/{name}' for name in names]
        originals.extend(row['path'] for row in manifest['outputs'] if row['path'].startswith('artifacts/cubeb/'))
        inputs = [verified_file(folder, manifest, name) for name in originals]
        before = verified_file(folder, manifest, 'summary.json')
        artifacts = folder / 'artifacts'
        if read(artifacts / 'effective-case.json') != case:
            parser.error('元の試験音または採取設定が異なります')
        route = read(artifacts / 'output-device.json')

        def remeasure(out, execute):
            result = analyze(artifacts, case, calibration, route, model, review)
            return {**result, 'registered_checks': read(before)['checks'], 'capture_run': capture_run}

        details.update(case_revision=review['revision'], capture_run=capture_run)
        return record_measurement(args.run_id, registered, [*sources, registered, manifest_path, before, *inputs], details,
                                  remeasure, command=None, input_root=ROOT)
    return record_measurement(args.run_id, CASE, sources, details, lambda out, execute:
                              capture(out, execute, case, calibration, binary, app, model), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
