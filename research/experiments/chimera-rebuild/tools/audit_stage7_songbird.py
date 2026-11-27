"""鳴禽の短区間・全区間と停止時の出力を保存した一次ファイルで照合する。"""

from pathlib import Path

import numpy as np
from scipy.io import wavfile

from audit_plan_evidence import ROOT, RUNS, read_json
from measure_csd_envelope_timing import verified_file
from measure_songbird_sustain_pcm import fir_tolerance, independent_output, internal
from measure_uniform_tube import read_trace
from upstream_baseline import WORKSPACE, sha256


CONDITIONS = ('matched_time', 'native_block', 'no_tracking')
SHORT_VARIANT = 'beak-inlet-half-inertance'
UPSTREAM_CALL = 'artifacts/chirps-44100'
INLET = 'beak_0_inflow_cm3_s'
FLOW = 'radiation_flow_cm3_s'
DERIVATIVE = 'radiation_derivative_cm3_s2'


def songbird_inputs(scope):
    short, short_upper, full, full_upper, stopped = (
        RUNS / scope[key] for key in ('short_run', 'short_upstream_run', 'full_run', 'full_upstream_run', 'stopped_run'))
    return [
        Path(__file__).resolve(), WORKSPACE / 'tools/measure_songbird_sustain_pcm.py',
        full / read_json(full / 'manifest.json')['source_snapshot'] / (WORKSPACE / 'cases/songbird-sustain-pcm.json').relative_to(ROOT),
        *(run / 'manifest.json' for run in (short, short_upper, full, full_upper, stopped)),
        *(short / 'artifacts' / filename for name in CONDITIONS
          for filename in (f'{name}.json', f'{name}-control.csv', f'{name}-{SHORT_VARIANT}.csv')),
        *(short_upper / 'artifacts' / f'{name}-upstream.csv' for name in CONDITIONS),
        *(full / 'artifacts' / f'{label}-{suffix}' for label in ('standard', 'experiment')
          for suffix in ('trace.csv', '128.wav', '77.wav')),
        *(full_upper / UPSTREAM_CALL / file for file in ('case.json', 'upstream.csv', 'pcm-128.wav', 'pcm-128.csv')),
        *(stopped / entry['path'] for entry in read_json(stopped / 'manifest.json')['outputs']),
    ]


def observation(path, length):
    with path.open() as stream:
        count = len(next(stream).split(','))
    fields, values = read_trace(path, length, count)
    if len(set(fields)) != count:
        raise ValueError(f'重複する観測列があります ({path.name})')
    return dict(zip(fields, values.T, strict=True))


def bit_difference(left, right):
    kind = np.dtype(f'u{left.dtype.itemsize}')
    changed = np.flatnonzero(left.view(kind) != right.view(kind))
    return [int(changed[0]) if changed.size else None, int(changed.size)]


def check_reference(run, registered, revision):
    path = run / 'manifest.json'
    manifest = read_json(path)
    if (run.name != registered['run'] or sha256(path) != registered['manifest_sha256']
            or manifest['status'] != 'pass' or manifest['upstream_revision'] != revision):
        raise ValueError(f'登録済みの観測元と一致しません ({run.name})')
    return manifest


def upstream_input(owner, source_run, source, relative):
    path = verified_file(source_run, source, relative)
    return verified_file(ROOT, {'outputs': owner['inputs']}, path.relative_to(ROOT).as_posix())


def check_short(scope, case, revision):
    run = RUNS / scope['short_run']
    manifest = read_json(run / 'manifest.json')
    upper = RUNS / scope['short_upstream_run']
    reference = check_reference(upper, case['upstream_observation'], revision)
    checks, report = {}, {}
    cells, window, rate = (case[key] for key in ('beak_cells', 'observation_internal_samples', 'sample_rate_hz'))
    fields = [f'beak_{i}_{column}' for i in range(cells)
              for column in ('area_cm2', 'pressure_dyn_cm2', 'inflow_cm3_s')] + [FLOW, DERIVATIVE]
    for name in CONDITIONS:
        start = case['condition_control_samples'][name]
        settings = read_json(run / 'artifacts' / f'{name}.json')['songbird_airway']
        checks[f'songbird_short/{name}/capture_layout'] = (
            settings['sample_rate_hz'] == rate and settings['sample_count'] == start + window
            and settings['control_block_samples'] == settings['events'][0]['sample'] == start)
        paths = (run / 'artifacts' / f'{name}-control.csv',
                 run / 'artifacts' / f'{name}-{SHORT_VARIANT}.csv',
                 upstream_input(manifest, upper, reference, f'artifacts/{name}-upstream.csv'))
        control, experiment, upstream = (observation(path, start + window) for path in paths)
        offset, _ = bit_difference(experiment[INLET][start:], control[INLET][start:])
        effect = None if offset is None else {'offset': offset, 'flow_hex': float(experiment[INLET][start + offset]).hex()}
        checks[f'songbird_short/{name}/registered_inlet_change'] = effect == case['predicted_first_inlet_effect'][name]
        matched = sum(window - bit_difference(experiment[field][start:], upstream[field][start:])[1] for field in fields)
        checks[f'songbird_short/{name}/beak_and_radiation_bit_exact'] = matched == window * len(fields)
        checks[f'songbird_short/{name}/derivative_from_flow'] = all(
            bit_difference(np.diff(trace[FLOW][start - 1:]) * rate, trace[DERIVATIVE][start:])[1] == 0
            for trace in (control, experiment, upstream))
        if name == 'no_tracking':
            checks['songbird_short/no_tracking_unexcited'] = all(
                not np.any(trace[field]) for trace in (control, experiment, upstream)
                for field in fields if not field.endswith('_area_cm2'))
        report[name] = {'start_sample': start, 'samples': window, 'columns': len(fields), 'matched_values': matched,
                        'first_inlet_change': effect}
    return checks, report


def check_full(scope, case, revision):
    run = RUNS / scope['full_run']
    manifest = read_json(run / 'manifest.json')
    upper = RUNS / scope['full_upstream_run']
    reference = check_reference(upper, case['call_reference'], revision)
    settings_path = upstream_input(manifest, upper, reference, f'{UPSTREAM_CALL}/case.json')
    settings = read_json(settings_path)['songbird_voice']
    frames, rate, internal_rate = (case[key] for key in ('frames', 'output_rate_hz', 'sample_rate_hz'))
    factor = internal_rate // rate
    sustain = WORKSPACE / 'cases/songbird-sustain-pcm.json'
    config = read_json(run / manifest['source_snapshot'] / sustain.relative_to(ROOT))['measurement']
    traces = {label: observation(run / 'artifacts' / f'{label}-trace.csv', frames) for label in ('standard', 'experiment')}
    traces['upstream'] = observation(upstream_input(manifest, upper, reference, f'{UPSTREAM_CALL}/upstream.csv'), frames)
    signals = {label: {'radiation': internal(trace, factor), 'decimated': trace['decimated'],
                       'dc_removed': trace['dc_removed'], 'pcm_f32': trace['pcm_f32'].astype(np.float32)}
               for label, trace in traces.items()}
    checks = {'songbird_full/capture_layout': settings['frames'] == frames and settings['sample_rate_hz'] == rate
              and all(np.array_equal(trace['internal_sample'], np.arange(1, frames + 1) * factor - 1)
                      for trace in traces.values())}
    differences = {}
    for label in ('standard', 'experiment'):
        differences[label] = {field: bit_difference(values, signals['upstream'][field])
                              for field, values in signals[label].items()}
        checks[f'songbird_full/{label}/differences_from_raw'] = differences[label] == scope['full_differences'][label]
        for host_block in case['host_block_frames']:
            wav_rate, pcm = wavfile.read(run / 'artifacts' / f'{label}-{host_block}.wav')
            checks[f'songbird_full/{label}/wav_{host_block}'] = (
                wav_rate == rate and pcm.shape == (frames,) and pcm.dtype == np.float32
                and bit_difference(pcm, signals[label]['pcm_f32'])[1] == 0)
    standard_wave = upstream_input(manifest, upper, reference, f'{UPSTREAM_CALL}/pcm-128.wav')
    standard_trace = upstream_input(manifest, upper, reference, f'{UPSTREAM_CALL}/pcm-128.csv')
    checks['songbird_full/archived_standard_reproduced'] = all(
        sha256(run / 'artifacts' / filename) == sha256(source)
        for filename, source in (('standard-128.wav', standard_wave), ('standard-trace.csv', standard_trace)))
    independent = {}
    for label, observed in signals.items():
        expected = independent_output(observed['radiation'], settings, factor, config)
        errors = {field: float(np.max(np.abs(expected[field] - observed[field])))
                  for field in ('decimated', 'dc_removed', 'pcm_f32')}
        checks[f'songbird_full/{label}/pcm_and_filters_recalculated'] = (
            bit_difference(expected['pcm_f32'], observed['pcm_f32'])[1] == 0
            and errors['decimated'] <= fir_tolerance(expected['decimated'], config)
            and errors['dc_removed'] <= case['limits']['dc_absolute_tolerance'])
        independent[label] = errors
    return checks, {'rates_hz': {'pcm': rate, 'internal': internal_rate}, 'frames': frames,
                    'internal_samples': frames * factor, 'differences': differences, 'independent_recalculation': independent}


def check_stopped(scope, revision):
    run = RUNS / scope['stopped_run']
    complete = RUNS / scope['full_run']
    manifest = read_json(run / 'manifest.json')
    complete_manifest = read_json(complete / 'manifest.json')
    cmd = manifest['commands'][-1]
    fixed_command = next(row['argv'] for row in complete_manifest['commands'] if row['argv'][1] == 'render-pcm')
    output = {row['path']: verified_file(run, manifest, row['path']) for row in manifest['outputs']}
    reason = 'このケースのPCM出力には計測CSVのパスが必要です'
    matched = [name for name in ('artifacts/standard-128.wav', 'artifacts/standard-trace.csv',
                                 'artifacts/standard-settings.json')
               if sha256(output[name]) == sha256(verified_file(complete, complete_manifest, name))]
    ok = (sha256(run / 'manifest.json') == scope['stopped_manifest_sha256']
          and manifest['status'] == 'fail' and manifest['case_id'] == complete_manifest['case_id']
          and manifest['case_revision'] == complete_manifest['case_revision']
          and manifest['upstream_revision'] == revision and not (run / 'summary.json').exists()
          and cmd['argv'][1] == 'render-pcm' and cmd['argv'][-2:] == ['--no-trace', '77'] and cmd['exit_code'] == 1
          and cmd['argv'][2] == fixed_command[2]
          and reason in output['artifacts/cargo.log'].read_text())
    return {'songbird_full/stopped_cli_reason_preserved': ok,
            'songbird_full/stopped_outputs_match_complete': len(matched) == 3}, {
                'run': run.name, 'reason': reason, 'verified_outputs': len(output), 'matching_outputs': matched}


def audit_songbird(scope, revision, definitions):
    checks, short = check_short(scope, definitions[scope['short_run']], revision)
    full_checks, full = check_full(scope, definitions[scope['full_run']], revision)
    stopped_checks, stopped = check_stopped(scope, revision)
    return checks | full_checks | stopped_checks, {'short': short, 'full': full, 'stopped': stopped}
