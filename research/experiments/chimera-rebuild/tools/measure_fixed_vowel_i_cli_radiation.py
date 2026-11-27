"""固定発声CLIの放射列を隔離計測、上流および出力PCMに照合する。"""

import argparse
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.signal import firwin

import measure_fixed_vowel_i_coupled_smoothing as coupled
import measure_fixed_vowel_i_radiation_components as radiation
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-cli-radiation.json'
READ, SHARED = coupled.READ, coupled.SHARED
ADDED_FIELDS = ('wall_radiation_flow_cm3_s', 'radiation_flow_cm3_s')
PHARYNX_FIELDS = ('pharynx_next_pressure_dyn_cm2', 'pharynx_outflow_cm3_s', 'pharynx_wall_flow_cm3_s',
                  'pharynx_volume_source_cm3_s', 'pharynx_area_cm2', 'pharynx_length_cm', 'pharynx_compliance_cgs')
VARIANTS = {
    'implicit': None,
    'disabled': {'radiation_components': False},
    'frame': {'radiation_components': True},
    'internal': {'internal_trace': True, 'radiation_components': True},
    'balance': {'internal_trace': True, 'pharynx_entry_balance': True},
    'combined': {'internal_trace': True, 'pharynx_entry_balance': True, 'radiation_components': True},
}
RENDER_PCM_MODES = ('implicit', 'disabled', 'internal', 'alternate')
EVIDENCE = (*(f'{name}.csv' for name in VARIANTS), *(f'{name}-inspect.json' for name in VARIANTS),
            *(f'{name}-input.json' for name in VARIANTS),
            *(f'{name}-pcm.{suffix}' for name in RENDER_PCM_MODES for suffix in ('wav', 'csv')))


def archive_inputs(case):
    reference = case['measurement']['radiation_reference']
    record, manifest, definition = coupled.smoothing.verified_reference(reference, case['upstream_revision'])
    return {'radiation-reference-manifest.json': manifest, 'radiation-reference-case.json': definition,
            'radiation-reference-states.npz': coupled.verified_path(record, 'artifacts/observations.npz'),
            'radiation-reference-voice.json': coupled.verified_path(record, 'artifacts/voice-input.json')}


def variant_input(case, options):
    content = {key: value for key, value in case.items() if key != 'fixed_voice_probe'}
    if options is not None:
        content['fixed_voice_probe'] = options
    return content


def capture(case, out, execute):
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    for name, options in VARIANTS.items():
        source = out / f'{name}-input.json'
        content = variant_input(case, options)
        source.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n')
        execute([*cli, 'inspect', str(source)], stdout=out / f'{name}-inspect.json')
        execute([*cli, 'render', str(source), str(out / f'{name}.csv')])
    first, alternate = case['measurement']['host_block_frames']
    for name in RENDER_PCM_MODES:
        source = out / f'{("internal" if name == "alternate" else name)}-input.json'
        block = alternate if name == 'alternate' else first
        execute([*cli, 'render-pcm', str(source), str(out / f'{name}-pcm.wav'),
                 str(out / f'{name}-pcm.csv'), str(block)])


def analyze(case, archive, out):
    cfg = case['measurement']
    fs = case['fixed_airway']['sample_rate_hz']
    rate = case['voice']['output_sample_rate_hz']
    count = case['fixed_airway']['sample_count']
    factor = fs // rate
    frames = count // factor
    load = coupled.pcm.read_columns
    same = coupled.same_bits
    transcripts = {name: load(out / f'{name}.csv', count if (probe or {}).get('internal_trace') else frames)
                   for name, probe in VARIANTS.items()}
    base_header, base = transcripts['implicit']
    headers = {name: header for name, (header, _) in transcripts.items()}
    frame_data = transcripts['frame'][1]
    internal = transcripts['internal'][1]
    balance = transcripts['balance'][1]
    combined = transcripts['combined'][1]
    frame_times = slice(factor - 1, None, factor)
    summary = {name: READ(out / f'{name}-inspect.json')['voice'] for name in VARIANTS}
    expected_probe = {
        'internal_trace': False, 'prescribed_glottal_flow': False, 'glottal_area_drives_port': True}
    clock_info = summary['implicit']
    voice_keys = ('voice', 'body', 'posture', 'fixed_airway')
    reference_voice = READ(archive['radiation-reference-voice.json'])
    checks = {
        'registered_reference_and_probe': (
            all(case[key] == reference_voice[key] for key in voice_keys)
            and case['fixed_voice_probe'] == VARIANTS['internal']
            and all(READ(out / f'{name}-input.json') == variant_input(case, options) for name, options in VARIANTS.items())
            and cfg['comparison_samples'] == [0, count]
            and [fs, rate, count] == [96000, 48000, 65536]),
        'implicit_and_disabled_csv_schema_unchanged': (
            headers['disabled'] == base_header and (out / 'implicit.csv').read_bytes() == (out / 'disabled.csv').read_bytes()
            and not any(name in base_header for name in ADDED_FIELDS)),
        'only_two_explicit_columns_appended': (
            tuple(headers['frame']) == tuple(headers['internal']) == (*base_header, *ADDED_FIELDS)
            and tuple(headers['combined']) == (*headers['balance'], *ADDED_FIELDS)
            and tuple(headers['balance']) == (*base_header, *PHARYNX_FIELDS)),
        'inspect_reports_only_active_probe_options': (
            'probe' not in clock_info and summary['disabled']['probe'] == expected_probe
            and all(summary[name]['probe'] == expected_probe | options for name, options in VARIANTS.items()
                    if options is not None and name != 'disabled')
            and all({key: value for key, value in row.items() if key != 'probe'} == clock_info
                    for row in summary.values())),
        'internal_and_output_frame_clocks_match': (
            np.array_equal(internal['internal_sample'], np.arange(count))
            and np.array_equal(internal['frame'], np.arange(count))
            and np.array_equal(base['frame'], np.arange(frames))
            and np.array_equal(base['internal_sample'], np.arange(factor - 1, count, factor))
            and all(same(frame_data[key], internal[key][frame_times]) for key in frame_data if key != 'frame')
            and all(same(frame_data[key], base[key]) for key in base_header)),
        'pharynx_balance_and_radiation_compose': (
            all(same(combined[key], balance[key]) for key in headers['balance'])
            and all(same(combined[key], internal[key]) for key in headers['internal'])),
    }
    total = internal['radiation_flow_cm3_s']
    derivative = np.diff(total, prepend=0.) / (1.0 / fs)
    checks['radiation_sum_and_derivative_match'] = (
        same((internal['wall_radiation_flow_cm3_s'] + internal['lip_flow_cm3_s']) + internal['nose_flow_cm3_s'], total)
        and same(derivative, internal['radiation_derivative_cm3_s2']))
    wave = {name: coupled.read_pcm(out / f'{name}-pcm.wav', frames, rate) for name in RENDER_PCM_MODES}
    checks['pcm_and_output_csv_invariant_to_observation_and_host_block'] = (
        all(same(data, wave['implicit']) for data in wave.values())
        and all((out / f'{name}-pcm.csv').read_bytes() == (out / 'implicit-pcm.csv').read_bytes()
                for name in RENDER_PCM_MODES[1:]))
    radiators = np.column_stack([internal[key] for key in (ADDED_FIELDS[0], 'lip_flow_cm3_s', 'nose_flow_cm3_s', ADDED_FIELDS[1])])
    taps = firwin(factor * 24 + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    pole = np.exp(-2 * np.pi * 25 / rate)
    before_limiter = radiation.linear_pcm(derivative, taps, pole, factor, case['voice']['output_gain'])
    expected_pcm = coupled.pcm.independent_limiter(before_limiter, rate)[2]
    checks['independent_pcm_from_radiation_sum_matches'] = same(expected_pcm, wave['internal'])
    with np.load(archive['radiation-reference-states.npz'], allow_pickle=False) as reference:
        checks['isolated_native_radiation_and_pcm_match_bitwise'] = (
            same(reference['candidate_baseline_radiation'], radiators)
            and same(reference['candidate_baseline'][:, coupled.RADIATION], derivative)
            and same(reference['candidate_baseline_pcm'], wave['internal']))
        relative = coupled.TANGENT.peak_error(radiators, reference['upstream_baseline_radiation'])
        pcm_difference = float(abs(reference['upstream_baseline_pcm'].astype(float) - wave['internal']).max())
        checks['pinned_upstream_radiation_and_pcm_match'] = (
            relative < cfg['upstream_flow_peak_relative_error_lt'] and pcm_difference < cfg['upstream_pcm_absolute_error_lt'])
    return {'checks': checks, 'internal_samples': count, 'output_frames': frames,
            'upstream_flow_peak_relative_error': relative, 'upstream_pcm_max_error': pcm_difference,
            'radiation_columns': list(ADDED_FIELDS)}


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

    def measure(out, execute):
        capture(case, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), *SHARED.candidate_sources(), *coupled.TANGENT.CANDIDATE_DATA,
              *(Path(module.__file__) for module in (coupled, coupled.smoothing, coupled.pcm, radiation, SHARED)),
              UPSTREAM / coupled.TANGENT.UPPER, UPSTREAM / coupled.fixed_lf.UPPER_VOICE,
              UPSTREAM / 'crates/chimera/tests/airway.rs', UPSTREAM / 'Cargo.lock']
    details = {'case_id': case['id'], 'case_revision': case['measurement']['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=coupled.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
