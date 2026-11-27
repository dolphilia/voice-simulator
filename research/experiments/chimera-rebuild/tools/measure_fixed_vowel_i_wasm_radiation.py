"""通常のWasmとWorkletで固定 /i/ の放射を採取し、CLIと上流に照合する。"""

import argparse
from pathlib import Path
import re
import shutil
import subprocess

import numpy as np
from scipy.signal import firwin

import measure_fixed_vowel_i_cli_radiation as cli
import measure_wasm_fixed as wasm
import measure_worklet_fixed as web
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-wasm-radiation.json'
HOST = web.WEB / 'tools/capture-fixed-radiation.mjs'
KINDS = ('enabled', 'implicit', 'disabled')
BLOCKS = (128, 77, 4096)
EVIDENCE = ('vocal_wasm.wasm', 'host.json', 'browser.json', 'browser-enabled.f64',
            *(f'browser-{kind}.f32' for kind in KINDS),
            *(f'host-{kind}-{block}.f32' for kind in KINDS for block in BLOCKS),
            *(f'host-enabled-{block}.f64' for block in BLOCKS))


def archive_inputs(study):
    coupled = cli.coupled
    result = {}
    for label, name, files in (
        ('cli', Path(study['fixed_voice_case']).stem, ('frame.csv', 'internal.csv', 'internal-pcm.wav')),
        ('upstream', 'fixed-vowel-i-radiation-components', ('observations.npz',)),
    ):
        reference = {'case': name, **study['measurement'][f'{label}_reference']}
        record, manifest, definition = coupled.smoothing.verified_reference(reference, study['upstream_revision'])
        result[f'{label}-manifest.json'] = manifest
        result[f'{label}-case.json'] = definition
        result.update({filename: coupled.verified_path(record, f'artifacts/{filename}') for filename in files})
    return result


def binary_trace(path, rows, columns):
    values = np.fromfile(path, dtype='<f8')
    if values.size != rows * columns or not np.isfinite(values).all():
        raise ValueError(f'放射流量の長さまたは有限性が条件外です（{path.name}）')
    return values.reshape(rows, columns)


def analyze(study, archive, out):
    cfg = study['measurement']
    source = cli.READ(archive['cli-case.json'])
    fields = cfg['observed_fields']
    first, frames = cfg['comparison_output_frames']
    internal, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    factor = internal // rate
    count = frames * factor
    blocks = cfg['host_block_frames']
    native_pcm = cli.coupled.read_pcm(archive['internal-pcm.wav'], frames, rate)
    load = cli.coupled.pcm.read_columns
    whole = load(archive['internal.csv'], count)[1]
    frame = load(archive['frame.csv'], frames)[1]
    native = np.column_stack([frame[field] for field in fields])
    internal_samples = np.arange(factor - 1, count, factor)
    same = cli.coupled.same_bits
    total = (whole[fields[0]] + whole[fields[1]]) + whole[fields[2]]
    derivative = np.diff(total, prepend=0.) / (1.0 / internal)
    taps = firwin(24 * factor + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    before_limiter = cli.radiation.linear_pcm(
        derivative, taps, np.exp(-2 * np.pi * 25 / rate), factor, source['voice']['output_gain'])
    independent = cli.coupled.pcm.independent_limiter(before_limiter, rate)[2]
    with np.load(archive['observations.npz'], allow_pickle=False) as reference:
        upstream = np.column_stack((reference['upstream_baseline_radiation'],
                                    reference['upstream_baseline'][:, cli.coupled.RADIATION]))[internal_samples]
        upper_pcm = reference['upstream_baseline_pcm']

    host = cli.READ(out / 'host.json')
    browser = cli.READ(out / 'browser.json')
    captures = browser['captures']
    legacy_fields = host['legacyFields']
    vbytes = sha256(out / 'vocal_wasm.wasm')
    allocation_log = (out / 'native-abi-test.log').read_text()
    allocations = re.findall(r'放射観測付きレンダー中の割り当て: (\d+)', allocation_log)
    checks = {
        'registered_case_and_clocks': (
            first == 0 and blocks == list(BLOCKS) and source['fixed_voice_probe']['radiation_components'] is True
            and source['fixed_airway']['sample_rate_hz'] == internal and source['fixed_airway']['sample_count'] == count
            and source['voice']['output_sample_rate_hz'] == rate
            and np.array_equal(frame['frame'], np.arange(frames))
            and np.array_equal(frame['internal_sample'], internal_samples)
            and np.array_equal(whole['internal_sample'], np.arange(count))
            and all(same(frame[key], whole[key][internal_samples]) for key in fields)),
        'internal_sum_derivative_and_pcm_reconstructed': (
            same(total, whole[fields[3]]) and same(derivative, whole[fields[4]]) and same(independent, native_pcm)),
        'legacy_layout_and_radiation_fields': (
            not host['imports'] and host['layout'] == cfg['legacy_layout_version']
            and f'vocal_legacy_observation_words: {cfg["legacy_raw_observation_words"]}' in allocation_log
            and legacy_fields == ['frames_rendered', 'gate', 'glottal_area_cm2', 'glottal_flow_cm3_s',
                                  'glottal_phase', 'glottal_voicing', 'glottal_f0_hz', 'radiation_derivative_cm3_s2']
            and host['radiationFields'] == captures['enabled']['fields'] == fields
            and all(captures[kind]['fields'] is None for kind in KINDS[1:])),
        'native_trace_allocations': allocations == ['0'],
        'browser_served_current_wasm': not browser['errors'] and browser['servedWasm'] == [vbytes],
    }
    legacy = np.column_stack([np.arange(1, frames + 1), *(frame[key] for key in legacy_fields[1:])])
    comparisons = {}
    host_trace = {}
    for block in blocks:
        at = np.minimum(np.arange(block, frames + block, block), frames) - 1
        records = [host['host'][f'{kind}-{block}'] for kind in KINDS]
        enabled = records[0]
        checks[f'host_{block}_legacy_observations'] = (
            all(row['rows'] == enabled['rows'] and row['stable'] for row in records)
            and np.array_equal(np.asarray(enabled['rows']), legacy[at]))
        checks[f'host_{block}_option_and_bounds'] = (
            all(row['missingBefore'] and row['missingAfter'] and row['missingWhileDisabled'] for row in records)
            and enabled['rejectedInvalidOffset']
            and all(not (out / f'host-{kind}-{block}.f64').exists() for kind in KINDS[1:]))
        host_trace[block] = binary_trace(out / f'host-enabled-{block}.f64', frames, len(fields))
        checks[f'host_{block}_radiation_bitwise'] = same(host_trace[block], native)
        comparisons[f'host-{block}'] = wasm.compare_pcm(
            np.fromfile(out / f'host-enabled-{block}.f32', dtype='<f4'), native_pcm, 0)
        checks[f'host_{block}_pcm_bitwise'] = (
            comparisons[f'host-{block}']['first_bit_difference_frame'] is None
            and all(same(np.fromfile(out / f'host-{kind}-{block}.f32', dtype='<f4'), native_pcm)
                    for kind in KINDS[1:]))

    reports = [captures[kind]['report'] for kind in KINDS]
    report = reports[0]
    stride = cfg['worklet_observation_stride']
    at = np.minimum(np.arange(stride, frames + stride, stride), frames) - 1
    quantum = cfg['worklet_quantum_frames']
    checks['worklet_legacy_columns_and_clock'] = (
        all(row == report for row in reports)
        and report['columns'] == ['context_frame', *legacy_fields]
        and np.array_equal(np.asarray(report['observations']), np.column_stack((at, legacy[at])))
        and report['sampleRate'] == report['workletSampleRate'] == rate
        and report['framesRendered'] == report['outputFrames'] == frames
        and report['outputChannels'] == 1
        and report['firstContextFrame'] == report['discontinuities'] == 0
        and report['shortestQuantum'] == report['longestQuantum'] == quantum
        and report['callbacks'] == (frames + quantum - 1) // quantum
        and report['stableWasmBuffers'] is True)
    browser_trace = binary_trace(out / 'browser-enabled.f64', frames, len(fields))
    checks['worklet_radiation_bitwise'] = (
        same(browser_trace, native) and all(same(browser_trace, trace) for trace in host_trace.values())
        and all(not (out / f'browser-{kind}.f64').exists() for kind in KINDS[1:]))
    browser_pcm = np.fromfile(out / 'browser-enabled.f32', dtype='<f4')
    comparisons['worklet'] = wasm.compare_pcm(browser_pcm, native_pcm, 0)
    checks['worklet_pcm_bitwise'] = (
        comparisons['worklet']['first_bit_difference_frame'] is None
        and all(same(np.fromfile(out / f'browser-{kind}.f32', dtype='<f4'), native_pcm) for kind in KINDS[1:]))
    traces = {'worklet': browser_trace, **{f'host-{block}': trace for block, trace in host_trace.items()}}
    differences = {
        name: wasm.compare_states(trace, native, fields, np.arange(frames), 0) for name, trace in traces.items()}
    upper_flow_error = cli.coupled.TANGENT.peak_error(browser_trace, upstream)
    upper_pcm_error = wasm.compare_pcm(browser_pcm, upper_pcm, cfg['upstream_pcm_absolute_error_lt'])
    checks['fixed_upstream_series_and_pcm'] = (
        upper_flow_error < cfg['upstream_peak_relative_error_lt']
        and upper_pcm_error['maximum_absolute_error'] < cfg['upstream_pcm_absolute_error_lt'])
    return {'checks': checks, 'frames': frames, 'callbacks': report['callbacks'], 'browser': browser['version'],
            'wasm_sha256': vbytes, 'native_trace_render_allocations': int(allocations[0]) if allocations else None,
            'cli_pcm': comparisons, 'cli_radiation': differences,
            'upstream_radiation_and_derivative_max_peak_relative_error': upper_flow_error, 'upstream_pcm': upper_pcm_error}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    study = cli.READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(study)
    source = WORKSPACE / 'cases' / study['fixed_voice_case']
    if sha256(source) != sha256(archive['cli-case.json']):
        parser.error('現在の固定発声入力と保存済みの固定発声入力が一致しません')

    def measure(out, execute):
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-wasm',
                 '--target', 'wasm32-unknown-unknown'])
        binary = out / 'vocal_wasm.wasm'
        shutil.copyfile(WORKSPACE / wasm.WASM, binary)
        execute(['cargo', 'test', '--locked', '--offline', '--release', '-p', 'vocal-wasm',
                 'fixed_voice_radiation_trace_does_not_allocate', '--', '--nocapture'],
                stdout=out / 'native-abi-test.log')
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'airway'],
                cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
        execute(['node', '--experimental-transform-types', str(HOST), str(binary), str(source), str(CASE), str(out)],
                cwd=web.WEB)
        return analyze(study, archive, out)

    inputs = [CASE, source, Path(__file__), HOST, *archive.values(), *web.web_sources(), *cli.SHARED.candidate_sources(),
              *(Path(module.__file__) for module in (cli, wasm, web, cli.coupled, cli.coupled.pcm, cli.radiation)),
              *(UPSTREAM / name for name in ('crates/chimera-wasm/src/lib.rs', 'crates/chimera/src/engine.rs',
                'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/airway/network.rs',
                'crates/chimera/tests/engine.rs', 'crates/chimera/tests/airway.rs', 'Cargo.lock'))]
    details = {'case_id': study['id'], 'case_revision': study['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'node': subprocess.check_output(['node', '--version'], text=True).strip()}
    return cli.SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=web.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
