"""上流発話の音源変動をそろえ、fine のPCM差を内部サンプルから追う。"""

import argparse
import gzip
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_duet_child_output_gain import COLUMNS, independent_stages, trace_input
from measure_duet_child_glottal_noise_origin import OUTPUT_PATCH, bit_equal
from measure_speech_timing import read
from measure_tsp_coat_to import DICT, PROBE
from measure_tsp_listening import ROOT, hydrate_run
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-fine-source-variation.json'
LOCAL = WORKSPACE / 'tools/candidate_tsp_fine_probe.rs'
SOURCE_PATCH = WORKSPACE / 'tools/patches/upstream-tsp-fine-source-states.patch'
FIELDS = ('tongue_tip_y_cm', 'gate', 'pressure_drop_dyn_cm2', 'f0_hz', 'phase', 'glottal_area_cm2',
          'voicing', 'glottal_flow_cm3_s', 'lip_cm3_s', 'nose_cm3_s', 'wall_cm3_s', 'total_cm3_s',
          'radiation_derivative_cm3_s2')
MODES = ('candidate', 'upstream', 'upstream_zero')


def capture(study, source, out, execute):
    count = str(study['trace_frames'])
    snapshots = {name: (out / f'{name}-source.f64le', out / f'{name}.f32le', out / f'{name}-output.f64le')
                 for name in MODES}
    with TemporaryDirectory(prefix='tsp-fine-probe-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = scratch / 'upstream'
        checkout.mkdir()
        archive = scratch / 'upstream.tar'
        execute(['git', 'archive', study['upstream_revision']], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(checkout)])
        for patch in (OUTPUT_PATCH, SOURCE_PATCH):
            execute(['git', 'apply', '--verbose', str(patch)], cwd=checkout)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        candidate = build_upstream_probe(LOCAL, out, execute, upstream=WORKSPACE, lto='off',
                                         package='vocal-core', extra_libraries=('serde_json',),
                                         cargo_args=('--offline',))
        upper = build_upstream_probe(PROBE, out, execute, upstream=checkout,
                                     extra_libraries=('serde_json',), rustc_args=('--cfg', 'tsp_voice_probe'),
                                     cargo_args=('--offline',))
        execute([str(candidate), str(source), str(dictionary), count, str(study['initial_f0_hz']),
                 str(study['speaking_f0_hz']), *map(str, snapshots['candidate'])])
        for name, variant in zip(MODES[1:], ('default', 'zero'), strict=True):
            trace, pcm, output = snapshots[name]
            execute([str(upper), str(source), str(dictionary), str(trace), str(pcm),
                     str(out / f'{name}-plan.json'), count, variant, str(output)])
    return snapshots


def first_difference(values, tolerance=0.0):
    frames = np.flatnonzero(np.abs(values) > tolerance)
    return int(frames[0]) if frames.size else None


def signal_difference(reference, other):
    delta = other.astype('f8') - reference
    first = first_difference(delta)
    peak = int(np.argmax(np.abs(delta)))
    return {'first_unequal_sample': first, 'reference_at_first': float(reference[first]) if first is not None else None,
            'other_at_first': float(other[first]) if first is not None else None,
            'peak_sample': peak, 'peak_error': float(abs(delta[peak]))}


def wave_difference(study, reference, other):
    delta = other.astype('f8') - reference
    a, b = study['attention_frames']
    peak = int(np.argmax(np.abs(delta[a:b]))) + a
    return {
        **signal_difference(reference, other),
        'first_over_tolerance_frame': first_difference(delta, study['tolerance']['significant_pcm']),
        'attention_peak_frame': peak, 'attention_peak_error': float(abs(delta[peak])),
        'attention_rms_error': float(np.sqrt(np.mean(delta[a:b] ** 2))),
    }


def measure(study, source_paths, out, execute):
    source, archived_plan, reference_pcm, candidate_pcm = source_paths
    plan = out / 'candidate-plan.json'
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--',
             'inspect', str(source)], stdout=plan)
    ordinary = out / 'candidate-cli.wav'
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'vocal-cli', '--',
             'render-pcm', str(source), str(ordinary), '--no-trace', '128'])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'],
            stdout=out / 'candidate-tests.log')
    snapshots = capture(study, source, out, execute)
    gain = study['base_gain']
    upper_gain = gain * study['upstream_gain_factor']
    count = study['trace_frames']
    factor = study['internal_sample_rate_hz'] // study['sample_rate_hz']
    waveform, states, diagnostics = {}, {}, {}
    for name, (raw_state, raw_pcm, raw_output) in snapshots.items():
        signal = np.fromfile(raw_pcm, dtype='<f4')
        table = np.fromfile(raw_state, dtype='<f8').reshape(-1, len(FIELDS))
        if (signal.shape != (study['frames'],) or table.shape != (count * factor, len(FIELDS))
                or not np.isfinite(table).all() or not np.isfinite(signal).all()):
            raise ValueError(f'PCMまたは声門系列の長さ・有限性が登録条件を満たしません ({name})')
        waveform[name] = signal
        states[name] = dict(zip(FIELDS, table.T, strict=True))
        trace = trace_input(raw_output, count)
        radiation = states[name]['radiation_derivative_cm3_s2']
        delta = np.diff(states[name]['total_cm3_s'], prepend=0.0) * study['internal_sample_rate_hz']
        diagnostics[name] = {
            **independent_stages(trace, signal[:count], gain if name == 'candidate' else upper_gain, study),
            'radiation_pair_matches': bool(np.array_equal(radiation, trace[:, :2].ravel())),
            'radiation_identity_max_error': float(np.max(np.abs(radiation - delta))),
        }
    archived = [wavfile.read(path) for path in (reference_pcm, candidate_pcm, ordinary)]
    rates = [item[0] for item in archived]
    upper_ref, candidate_ref, native = (item[1] for item in archived)
    tol = study['tolerance']['independent_normalized']
    checks = {
        'ordinary_waves_match_probe': all(rate == study['sample_rate_hz'] for rate in rates)
        and bit_equal(upper_ref, waveform['upstream']) and bit_equal(candidate_ref, native)
        and bit_equal(native, waveform['candidate']),
        'registered_plans_preserved': read(plan) == read(archived_plan)
        and read(out / 'upstream-plan.json') == read(out / 'upstream_zero-plan.json'),
        'independent_radiation_and_output_stage': all(
            d['radiation_pair_matches'] and d['radiation_identity_max_error'] <= study['tolerance']['radiation_identity_cm3_s2']
            and all(d[k] <= tol for k in ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
            and d['hold_error_frames'] == 0 and d['pcm_matches_independent_limiter']
            for d in diagnostics.values()),
    }
    pairs = {'ordinary': ('upstream', 'candidate'), 'zero_vs_candidate': ('upstream_zero', 'candidate'),
             'within_upstream': ('upstream', 'upstream_zero')}
    comparisons = {label: {field: signal_difference(states[left][field], states[right][field]) for field in FIELDS}
                   for label, (left, right) in pairs.items()}
    phase_distance = {}
    for label, (left, right) in pairs.items():
        distance = np.abs(states[right]['phase'] - states[left]['phase'])
        phase_distance[label] = float(np.max(np.minimum(distance, 1.0 - distance)))
    pcm = {label: wave_difference(study, waveform[left], waveform[right]) for label, (left, right) in pairs.items()}
    return {'checks': checks, 'observed_frames': count, 'internal_columns': FIELDS, 'output_columns': COLUMNS,
            'internal_comparisons': comparisons, 'pcm_comparisons': pcm, 'output_stage': diagnostics,
            'phase_circular_peak_error_cycles': phase_distance,
            'hypothesis': {'phase_peak_smaller': phase_distance['zero_vs_candidate'] < phase_distance['ordinary'],
                           'attention_pcm_peak_smaller': pcm['zero_vs_candidate']['attention_peak_error']
                           < pcm['ordinary']['attention_peak_error']}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read(CASE)
    revision = study['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != revision or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版が必要です')
    source = hydrate_run(study['source_run'], study['source_case'], revision)
    prior = hydrate_run(study['transition_run'], 'tsp-soap-saves-transition', revision)
    uid = study['recording_id']
    source_paths = [verified_file(*source, f'artifacts/{uid}/{name}')
                    for name in ('candidate.json', 'inspect.json', 'upstream.wav', 'candidate.wav')]
    inputs = [CASE, Path(__file__).resolve(), PROBE, LOCAL, DICT, OUTPUT_PATCH, SOURCE_PATCH,
              *(WORKSPACE / 'tools' / name for name in ('tsp_fine_trace.rs', 'measure_uniform_tube.py',
                'measure_duet_child_output_gain.py', 'measure_duet_child_glottal_noise_origin.py',
                'measure_csd_envelope_timing.py', 'measure_tsp_listening.py', 'measure_tsp_coat_to.py',
                'measure_speech_timing.py', 'upstream_baseline.py')),
              source[0] / 'manifest.json', prior[0] / 'manifest.json', verified_file(*prior, 'summary.json'),
              *source_paths, *candidate_sources()]
    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd()), 'arguments': sys.argv[1:]}
    return record_measurement(
        args.run_id, CASE, inputs, details, lambda out, execute: measure(study, source_paths, out, execute),
        command=None, input_root=ROOT,
    )


if __name__ == '__main__':
    raise SystemExit(main())
