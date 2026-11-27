"""固定 /i/ の輪郭と鼻腔ポートを交差させ、放射とPCMの差を測る。"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.signal import firwin

import measure_fixed_vowel_i_velum_radiation as velum
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-vowel-i-velum-port-only.json'
CONDITIONS = {'closed': ('closed', 'closed'), 'port_only': ('closed', 'open'),
              'shape_only': ('open', 'closed'), 'open': ('open', 'open')}
FIELDS, RAD, PORT = velum.FIELDS, velum.RAD, velum.PORT
COUPLED = velum.coupled
READ, SAME = velum.READ, COUPLED.same_bits
EVIDENCE = ('upper-network.patch', 'upper-voice.patch', 'upper-columns.json', 'invalid.json', 'input-validation.json',
            *(f'{arm}-{name}' for arm in CONDITIONS for name in (
                'input.json', 'inspect.json', 'geometry.csv', 'internal.csv', 'pcm.wav', 'upper.f32', 'upper.f64')))

VALIDATE_INVALID = """
import json
from pathlib import Path
import subprocess
import sys

case, trace = sys.argv[1:]
cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
outcomes = {}
for name, suffix in [('inspect', [case]), ('render', [case, trace])]:
    result = subprocess.run([*cli, name, *suffix], capture_output=True, text=True, check=False)
    outcomes[name] = {'rejected': result.returncode != 0,
                      'area_error': '口蓋帆ポートの上書きには有限の非負面積' in result.stderr}
print(json.dumps({**outcomes, 'trace_created': Path(trace).exists()}))
"""


def archive_inputs(case):
    spec = case['measurement']['reference']
    record, manifest, definition = COUPLED.smoothing.verified_reference(spec, case['upstream_revision'])
    source = velum.archive_inputs(READ(definition))['source.json']
    return {'source.json': source, 'baseline-manifest.json': manifest, 'baseline-case.json': definition,
            'baseline-summary.json': COUPLED.verified_path(record, 'summary.json'),
            **{f'{arm}-{name}': COUPLED.verified_path(record, f'artifacts/{arm}-{name}')
               for arm in ('closed', 'open') for name in ('internal.csv', 'pcm.wav', 'upper.f32', 'upper.f64')}}


def arm_input(base, cfg, arm):
    geometry, port = CONDITIONS[arm]
    return {**base, 'posture': {**base['posture'], 'velum_cm2': cfg['geometry_cm2'][geometry]},
            'fixed_voice_probe': {'internal_trace': True, 'radiation_components': True, 'velum_port': True,
                                  'velum_area_override_cm2': cfg['port_area_cm2'][port]}}


def write_case(path, content):
    path.write_text(json.dumps(content, indent=2, ensure_ascii=False) + '\n')


def capture(case, archive, out, execute):
    cfg = case['measurement']
    base = READ(archive['source.json'])
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    frames = cfg['internal_samples'][1] // (fs // rate)
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'sound_marks_acoustic',
             'a_nasalized_vowel_is_nasal_and_an_oral_one_is_not'], cwd=UPSTREAM, stdout=out / 'upstream-nasality-test.log')
    with TemporaryDirectory(prefix='velum-port-only-', dir=out.parent) as temporary:
        upper = velum.build_upstream(case, out, Path(temporary), execute, port_override=True)
        source = tuple(base['voice'][key] for key in (
            'pressure_cm_h2o', 'gate', 'f0_hz', 'breathiness', 'tension', 'output_gain'))
        for arm in CONDITIONS:
            content = arm_input(base, cfg, arm)
            path = out / f'{arm}-input.json'
            write_case(path, content)
            execute([*cli, 'inspect', str(path)], stdout=out / f'{arm}-inspect.json')
            execute([*cli, 'geometry', str(path), str(out / f'{arm}-geometry.csv')])
            execute([*cli, 'render', str(path), str(out / f'{arm}-internal.csv')])
            execute([*cli, 'render-pcm', str(path), str(out / f'{arm}-pcm.wav'), '--no-trace',
                     str(cfg['host_block_frames'])])
            posture = content['posture']['velum_cm2']
            area = content['fixed_voice_probe']['velum_area_override_cm2']
            execute([str(upper), *map(str, (posture, fs, rate, frames, *source)),
                     str(out / f'{arm}-upper'), 'observer', str(area)])
    bad = arm_input(base, cfg, 'closed')
    bad['fixed_voice_probe']['velum_area_override_cm2'] = -0.01
    write_case(out / 'invalid.json', bad)
    execute([sys.executable, '-c', VALIDATE_INVALID, str(out / 'invalid.json'), str(out / 'invalid.csv')],
            stdout=out / 'input-validation.json')


def compare_arms(cfg, tracks, waves, layout, stages, factor, taps, pole, gain, edition):
    low, high = cfg['steady_output_frames']
    steady = slice(low, high)
    first = COUPLED.first_difference
    time = {arm: {key: first(tracks['closed'][key], tracks[arm][key]) for key in FIELDS}
            for arm in ('port_only', 'shape_only', 'open')}
    pcm_first = {arm: first(waves['closed'], waves[arm]) for arm in time}
    early = time['port_only']
    arrival = early[PORT[1]]
    nose = early[RAD[2]]
    nose_rms = {arm: float(np.sqrt(np.mean(tracks[arm][RAD[2]][factor - 1::factor][steady]**2)))
                for arm in CONDITIONS}
    pcm = {arm: values.astype(float)[steady] for arm, values in waves.items()}
    combined = pcm['open'] - pcm['closed']
    port = pcm['port_only'] - pcm['closed']
    shape = pcm['shape_only'] - pcm['closed']
    interaction = (pcm['open'] - pcm['shape_only']) - port
    ratio = float(np.linalg.norm(interaction) / np.linalg.norm(combined))
    projections = {key: float(np.dot(value, combined) / np.dot(combined, combined))
                   for key, value in (('port', port), ('shape', shape), ('interaction', interaction))}
    make_parts = lambda name: np.column_stack([tracks[name][key] for key in RAD[:3]])
    source = (make_parts('open') - make_parts('shape_only')) - (make_parts('port_only') - make_parts('closed'))
    components = velum.radiation.linear_pcm(
        velum.radiation.derivative(source, cfg['internal_rate_hz'], edition), taps, pole, factor, gain)
    linear_interaction = (stages['open'] - stages['shape_only']) - (stages['port_only'] - stages['closed'])
    linear_error = float(abs(components.sum(axis=1) - linear_interaction).max())
    checks = {
        'port_only_first_differences_follow_port': (
            arrival is not None and all(early[key] is not None and early[key] >= arrival for key in RAD[:3])
            and pcm_first['port_only'] is not None and pcm_first['port_only'] >= arrival // factor),
        'port_only_nose_delay_matches_nasal_branches': (
            arrival is not None and nose is not None and nose - arrival == cfg['expected_port_to_nose_internal_samples']
            == next(tube['cells'] - 1 for tube in layout['closed']['tubes'] if tube['name'] == 'nasal')),
        'shape_only_keeps_early_wall_and_pcm_difference': (
            time['shape_only'][RAD[0]] == time['open'][RAD[0]] and time['open'][RAD[0]] is not None
            and pcm_first['shape_only'] == pcm_first['open'] and pcm_first['open'] is not None),
        'closed_port_silences_nose_and_open_has_steady_flow': (
            all(not np.any(tracks[name][PORT[1]]) and not np.any(tracks[name][RAD[2]])
                for name in ('closed', 'shape_only'))
            and all(nose_rms[name] > cfg['minimum_steady_nose_rms_cm3_s'] for name in ('port_only', 'open'))),
        'interaction_is_measurable_and_reconstructs_by_radiation': (
            ratio > cfg['minimum_relative_pcm_interaction_rms']
            and linear_error < cfg['linear_pcm_interaction_sum_absolute_error_lt']),
    }
    return checks, {
        'first_internal_difference': time, 'first_pcm_difference': pcm_first,
        'steady_nose_rms_cm3_s': nose_rms,
        'steady_pcm_rms': {key: float(np.sqrt(np.mean(values**2))) for key, values in (
            ('combined', combined), ('port', port), ('shape', shape), ('interaction', interaction))},
        'relative_pcm_interaction_rms': ratio, 'projection_on_combined_pcm': projections,
        'max_linear_interaction_component_sum_error': linear_error,
    }


def analyze(case, archive, out):
    cfg = case['measurement']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    count = cfg['internal_samples'][1]
    factor = fs // rate
    frames = count // factor
    base = READ(archive['source.json'])
    comparison = READ(archive['baseline-summary.json'])
    taps = firwin(24 * factor + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    pole = np.exp(-2 * np.pi * 25 / rate)
    gain = base['voice']['output_gain']
    checks = {
        'registered_input_and_trace_fields': (
            cfg['internal_samples'] == [0, base['fixed_airway']['sample_count']]
            and fs == base['fixed_airway']['sample_rate_hz'] and rate == base['voice']['output_sample_rate_hz']
            and READ(out / 'upper-columns.json') == list(FIELDS)),
        'negative_override_rejected_without_creating_trace': (READ(out / 'input-validation.json') == {
            'inspect': {'rejected': True, 'area_error': True}, 'render': {'rejected': True, 'area_error': True},
            'trace_created': False}),
    }
    editions = ('candidate', 'upstream')
    tracks = {edition: {} for edition in editions}
    waves = {edition: {} for edition in editions}
    stages = {edition: {} for edition in editions}
    layouts, parity, residuals = {}, {}, {}
    for arm in CONDITIONS:
        content = arm_input(base, cfg, arm)
        _, internal = COUPLED.pcm.read_columns(out / f'{arm}-internal.csv', count)
        columns = velum.screen.prior.binary_trace(out / f'{arm}-upper.f64', count, len(FIELDS))
        upper = dict(zip(FIELDS, columns.T))
        tracks['candidate'][arm], tracks['upstream'][arm] = internal, upper
        native = COUPLED.read_pcm(out / f'{arm}-pcm.wav', frames, rate)
        reference = np.fromfile(out / f'{arm}-upper.f32', dtype='<f4')
        waves['candidate'][arm], waves['upstream'][arm] = native, reference
        diagnostics = READ(out / f'{arm}-inspect.json')
        layouts[arm] = diagnostics['fixed_airway']
        area = content['fixed_voice_probe']['velum_area_override_cm2']
        checks[f'{arm}/case_and_area_are_constant'] = (
            READ(out / f'{arm}-input.json') == diagnostics['case'] == content
            and diagnostics['voice']['probe']['velum_area_override_cm2'] == layouts[arm]['velum_port_cm2'] == area
            and np.array_equal(internal['internal_sample'], np.arange(count))
            and np.all(internal[PORT[0]] == area) and np.all(upper[PORT[0]] == area))
        for edition in editions:
            series = tracks[edition][arm]
            total = (series[RAD[0]] + series[RAD[1]]) + series[RAD[2]]
            derivative = velum.radiation.derivative(total, fs, edition)
            before = velum.radiation.linear_pcm(derivative, taps, pole, factor, gain)
            stages[edition][arm] = before
            calculated = COUPLED.pcm.independent_limiter(before, rate)[2]
            checks[f'{edition}/{arm}/radiation_sum_derivative_and_independent_pcm'] = (
                SAME(total, series[RAD[3]]) and SAME(derivative, series[RAD[4]]) and SAME(calculated, waves[edition][arm]))
            if area > 0:
                residuals[f'{edition}/{arm}'] = velum.port_residual(layouts[arm], series, fs)
        states = velum.wasm.compare_states(np.column_stack([internal[key] for key in FIELDS]), columns, FIELDS,
                                          np.arange(count), cfg['upstream_series_peak_relative_error_lt'])
        pcm = velum.wasm.compare_pcm(native, reference, cfg['upstream_pcm_absolute_error_lt'])
        checks[f'{arm}/fixed_upstream_tolerances'] = (
            all(item['status'] for item in states.values()) and pcm['maximum_absolute_error'] < cfg['upstream_pcm_absolute_error_lt'])
        parity[arm] = {'state': states, 'pcm': pcm}
    for geometry, a, b in (('closed', 'closed', 'port_only'), ('open', 'shape_only', 'open')):
        checks[f'{geometry}/geometry_unchanged_by_port_override'] = (
            sha256(out / f'{a}-geometry.csv') == sha256(out / f'{b}-geometry.csv')
            and {**layouts[a], 'velum_port_cm2': layouts[b]['velum_port_cm2']} == layouts[b])
    for arm in ('closed', 'open'):
        checks[f'{arm}/archived_combined_reference_reproduced'] = all(
            sha256(out / f'{arm}-{name}') == sha256(archive[f'{arm}-{name}'])
            for name in ('internal.csv', 'pcm.wav', 'upper.f32', 'upper.f64'))
    checks['independent_open_port_pressure_balance'] = all(
        value < cfg['port_pressure_residual_relative_lt'] for value in residuals.values())
    contrasts = {}
    for edition in editions:
        conditions, contrasts[edition] = compare_arms(
            cfg, tracks[edition], waves[edition], layouts, stages[edition], factor, taps, pole, gain, edition)
        checks.update({f'{edition}/{key}': value for key, value in conditions.items()})
        expected = comparison['contrast'][edition]
        results = contrasts[edition]
        checks[f'{edition}/shape_only_early_onsets_match_archived_open'] = (
            results['first_internal_difference']['shape_only'][RAD[0]] == expected['first_difference_internal_samples'][RAD[0]]
            and results['first_pcm_difference']['shape_only'] == expected['first_pcm_difference_frame'])
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'internal_samples': count, 'frames': frames,
            'contrasts': contrasts, 'fixed_upstream_comparisons': parity, 'port_pressure_residuals': residuals}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('英数字で始まる実行IDを指定してください')
    case = READ(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    archive = archive_inputs(case)
    source = WORKSPACE / 'cases' / case['fixed_voice_case']
    if sha256(source) != sha256(archive['source.json']):
        parser.error('現在の固定発声入力が照合元に登録されたケースと一致しません')

    def measure(out, execute):
        capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, source, Path(__file__), velum.UPPER, *archive.values(), *COUPLED.SHARED.candidate_sources(),
              *(Path(module.__file__) for module in (velum, COUPLED, COUPLED.fixed_lf, COUPLED.pcm,
                                                     velum.wasm, velum.radiation, velum.screen)),
              *(UPSTREAM / name for name in (velum.NETWORK, velum.VOICE, 'crates/chimera/src/voice/human_airway.rs',
                'crates/chimera/src/anatomy/human.rs', 'crates/chimera/tests/sound_marks_acoustic.rs', 'Cargo.lock'))]
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return COUPLED.SHARED.record_measurement(
        args.run_id, CASE, inputs, details, measure, command=None, input_root=velum.screen.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
