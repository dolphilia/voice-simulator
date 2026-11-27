"""TSP確認用07を、出力ゲインだけ変えて通常CLIと観測器で比較する。"""

import argparse
from copy import deepcopy
import gzip
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import COLUMNS, independent_stages, trace_input
from measure_speech_timing import read, write
from measure_tsp_coat_to import DICT
from measure_tsp_fine_variation import FIELDS, LOCAL, signal_difference, wave_difference
from measure_tsp_listening import ROOT, hydrate_run, snapshot_case
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-fine-output-gain.json'
MODES = ('base', 'matched')


def render_cli(mode, source, out, execute):
    cli = ['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--']
    wave = out / f'{mode}.wav'
    plan = out / f'{mode}-plan.json'
    execute([*cli, 'inspect', str(source)], stdout=plan)
    execute([*cli, 'render-pcm', str(source), str(wave), '--no-trace', '128'])
    return wavfile.read(wave), read(plan)


def capture(study, cases, out, execute):
    base_source = out / 'base-source.f64le'
    stage, pcm, hashes = {}, {}, {}
    with TemporaryDirectory(prefix='tsp-fine-gain-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        probe = build_upstream_probe(LOCAL, out, execute, upstream=WORKSPACE, lto='off',
                                     package='vocal-core', extra_libraries=('serde_json',),
                                     cargo_args=('--offline',))
        internal_count = study['frames'] * study['internal_sample_rate_hz'] // study['sample_rate_hz']
        for mode, source in cases.items():
            internal = base_source if mode == 'base' else scratch / 'matched-source.f64le'
            raw_pcm = scratch / f'{mode}.f32le'
            output = out / f'{mode}-output.f64le'
            execute([str(probe), str(source), str(dictionary), str(study['frames']),
                     str(study['initial_f0_hz']), str(study['speaking_f0_hz']),
                     str(internal), str(raw_pcm), str(output)])
            series = np.fromfile(internal, dtype='<f8').reshape(-1, len(FIELDS))
            step = trace_input(output, study['frames'])
            if (series.shape != (internal_count, len(FIELDS)) or not np.isfinite(series).all()
                    or not np.array_equal(series[:, FIELDS.index('radiation_derivative_cm3_s2')], step[:, :2].ravel())):
                raise ValueError(f'内部系列の時計、長さまたは放射が一致しません ({mode})')
            hashes[mode] = {'sha256': sha256(internal), 'bytes': internal.stat().st_size}
            stage[mode] = step
            pcm[mode] = np.fromfile(raw_pcm, dtype='<f4')
        states_equal = hashes['base'] == hashes['matched']
        if not states_equal:
            shutil.move(str(internal), str(out / internal.name))
    return stage, pcm, hashes, states_equal


def measure(study, source, prior, out, execute):
    case = read(source)
    gain = study['base_gain']
    matched_gain = study['matched_gain']
    alternative = deepcopy(case)
    alternative['speech_voice']['voice']['output_gain'] = matched_gain
    variant = out / 'matched-case.json'
    write(variant, alternative)
    cases = {'base': source, 'matched': variant}
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'body_mix', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'],
            stdout=out / 'candidate-tests.log')
    cli = {mode: render_cli(mode, path, out, execute) for mode, path in cases.items()}
    outputs, wave, hash_entries, identical_sources = capture(study, cases, out, execute)
    reference = np.fromfile(prior['upstream_zero.f32le'], dtype='<f4')
    stored = np.fromfile(prior['candidate.f32le'], dtype='<f4')
    prefix = trace_input(prior['candidate-output.f64le'], study['reference_trace_frames'])
    if reference.shape != (study['frames'],) or not np.isfinite(reference).all():
        raise ValueError('固定上流の保存済みPCMが登録条件に一致しません')
    plan_fields = ('speech', 'gestures', 'output_frames', 'control_block_internal_samples', 'decimation_factor')
    archived_plan = read(prior['candidate-plan.json'])
    checks = {
        'only_gain_changed': case['speech_voice']['voice']['output_gain'] == gain and gain != matched_gain
        and alternative == case | {'speech_voice': case['speech_voice']
                                   | {'voice': case['speech_voice']['voice'] | {'output_gain': matched_gain}}}
        and matched_gain == gain * study['upstream_gain_factor'],
        'identical_plans': all(plan[key] == archived_plan[key] for _, plan in cli.values() for key in plan_fields),
        'normal_waves_equal_probes': bit_equal(stored, wave['base']) and all(
            rate == study['sample_rate_hz'] and bit_equal(samples, wave[mode])
            for mode, ((rate, samples), _) in cli.items()),
        'pre_gain_bit_identity': identical_sources and np.array_equal(
            outputs['base'][:, :3].view('u8'), outputs['matched'][:, :3].view('u8'))
        and np.array_equal(outputs['base'][:len(prefix)].view('u8'), prefix.view('u8')),
    }
    tolerance = study['tolerance']['independent_normalized']
    diagnostics = {mode: independent_stages(outputs[mode], wave[mode], g, study)
                   for mode, g in zip(MODES, (gain, matched_gain), strict=True)}
    checks['independent_output_equations'] = all(
        all(row[key] <= tolerance for key in ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
        and row['hold_error_frames'] == 0 and row['pcm_matches_independent_limiter'] for row in diagnostics.values())
    stages = {key: signal_difference(outputs['base'][:, i], outputs['matched'][:, i])
              for i, key in enumerate(COLUMNS)}
    pcm = {mode: wave_difference(study, reference, wave[mode]) for mode in MODES}
    a, b = study['attention_frames']
    recorded = trace_input(prior['upstream_zero-output.f64le'], study['reference_trace_frames'])
    matched_dc = outputs['matched'][a:b, COLUMNS.index('dc_removed')]
    reference_dc = recorded[a:b, COLUMNS.index('dc_removed')]
    return {
        'checks': checks, 'gain': {'base': gain, 'matched': matched_gain},
        'hypothesis': {'attention_pcm_near_upstream': pcm['matched']['attention_peak_error'] <= study['tolerance']['attention_pcm'],
                       'initial_pcm_difference_remains': pcm['matched']['first_unequal_sample'] == 0},
        'frames': study['frames'], 'observed_internal_samples': study['frames'] * 2,
        'internal_columns': FIELDS, 'internal_series': hash_entries, 'output_columns': COLUMNS,
        'output_stage': diagnostics, 'stage_changes': stages, 'pcm_comparisons': pcm,
        'attention_dc_peak_error_against_upstream': float(np.max(np.abs(matched_dc - reference_dc))),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    rev = study['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != rev or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版が必要です')
    source = hydrate_run(study['source_run'], study['source_case'], rev)
    prior = hydrate_run(study['reference_run'], study['reference_case'], rev)
    spec = snapshot_case(prior, study['reference_case'])
    original = read(spec)
    keys = ('source_run', 'recording_id', 'frames', 'sample_rate_hz', 'internal_sample_rate_hz', 'stage')
    if any(original[key] != study[key] for key in keys) or original['trace_frames'] < study['attention_frames'][1]:
        parser.error('先行の音源対照と入力や観測範囲が一致しません')
    observation = study | {'reference_trace_frames': original['trace_frames']}
    reference = {name: verified_file(*prior, f'artifacts/{name}') for name in (
        'upstream_zero.f32le', 'upstream_zero-output.f64le', 'candidate.f32le', 'candidate-output.f64le', 'candidate-plan.json')}
    source_path = verified_file(*source, f"artifacts/{study['recording_id']}/candidate.json")
    inputs = [CASE, Path(__file__).resolve(), LOCAL, DICT, spec, source_path,
              *(WORKSPACE / 'tools' / name for name in ('tsp_fine_trace.rs', 'measure_tsp_fine_variation.py',
                'measure_duet_child_output_gain.py', 'measure_duet_child_glottal_noise_origin.py', 'measure_tsp_coat_to.py',
                'measure_csd_envelope_timing.py', 'measure_tsp_listening.py', 'measure_speech_timing.py',
                'measure_uniform_tube.py', 'upstream_baseline.py')),
              prior[0] / 'manifest.json', source[0] / 'manifest.json', *reference.values(), *candidate_sources()]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': rev,
               'invoked_from': str(Path.cwd()), 'arguments': sys.argv[1:]}
    return record_measurement(
        args.run_id, CASE, inputs, details,
        lambda out, execute: measure(observation, source_path, reference, out, execute),
        command=None, input_root=ROOT,
    )


if __name__ == '__main__':
    raise SystemExit(main())
