"""発話中の実効断面を固定し、線形共鳴とPCMのLPC極を比較する。"""

import argparse
import csv
import gzip
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.io import wavfile

import measure_tsp_stressed_vowel_formants as tsp
from measure_tsp_coat_to import DICT
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_vowel_transfer import independent_response, peak_rows
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-seems-tract-transfer.json'
TOOLS = WORKSPACE / 'tools'
UPPER = TOOLS / 'upstream_tsp_tract_transfer_probe.rs'
CANDIDATE = TOOLS / 'candidate_tsp_fine_probe.rs'
PATCH = TOOLS / 'patches/upstream-tsp-linear-current.patch'
VOICES = ('upstream', 'candidate')


def observe(case, original, archive, out, execute):
    completed = case['observation']['completed_pcm_frames']
    text = tsp.read(original)['speech_voice']['input']['text']
    probe_case = tsp.read(original)
    probe_case['speech_voice']['tract_profile_frames'] = [completed - 1]
    profile_case = out / 'candidate-profile-case.json'
    profile_case.write_text(json.dumps(probe_case, ensure_ascii=False, indent=2) + '\n')
    with TemporaryDirectory(prefix='seems-transfer-', dir=out) as directory:
        scratch = Path(directory)
        checkout = scratch / 'upstream'
        checkout.mkdir()
        tar = scratch / 'upstream.tar'
        execute(['git', 'archive', case['upstream_revision']], cwd=UPSTREAM, stdout=tar)
        execute(['tar', '-xf', str(tar), '-C', str(checkout)])
        execute(['git', 'apply', str(PATCH)], cwd=checkout)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
        execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis', '--test', 'airway'],
                cwd=UPSTREAM, stdout=out / 'upstream-analysis-tests.log')
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'],
                stdout=out / 'candidate-tests.log')
        vocal = WORKSPACE / 'target/release/vocal-cli'
        chimera = UPSTREAM / 'target/release/chimera'
        candidate_wave = scratch / 'candidate-cli.wav'
        upstream_wave = scratch / 'upstream-cli.wav'
        execute([str(vocal), 'render-pcm', str(original), str(candidate_wave), '--no-trace', '128'])
        execute([str(vocal), 'render', str(profile_case), str(out / 'candidate-sections.csv')])
        execute([str(chimera), 'render', 'text', str(upstream_wave), text, 'male', '--float'], cwd=UPSTREAM)
        native = build_upstream_probe(UPPER, scratch, execute, upstream=checkout,
                                      extra_libraries=('serde_json',), cargo_args=('--offline',))
        local = build_upstream_probe(CANDIDATE, scratch, execute, upstream=WORKSPACE,
                                     package='vocal-core', lto='off', extra_libraries=('serde_json',),
                                     rustc_args=('--cfg', 'tsp_tract_snapshot'), cargo_args=('--offline',))
        execute([str(native), str(original), str(dictionary), str(CASE), str(scratch / 'upstream.f32'),
                 str(out / 'upstream-linear.json')])
        execute([str(local), str(original), str(dictionary), '0', '110', '112', str(scratch / 'no-source-trace'),
                 str(scratch / 'candidate.f32'), str(scratch / 'no-output-trace'), str(CASE),
                 str(out / 'candidate-linear.json')])
        rates = {}
        for voice, cli_wave in zip(VOICES, (upstream_wave, candidate_wave), strict=True):
            rate, native_pcm = wavfile.read(cli_wave)
            probe = np.fromfile(scratch / f'{voice}.f32', dtype='<f4')
            rates[voice] = {'pcm_rate_hz': rate, 'pcm_frames': int(native_pcm.size),
                            'cli_matches_archived_file': sha256(cli_wave) == sha256(archive[voice]),
                            'observed_pcm_matches_cli': native_pcm.dtype == np.float32
                                and np.isfinite(native_pcm).all()
                                and np.array_equal(native_pcm.view('u4'), probe.view('u4'))}
    return rates


def local_peaks(grid, magnitude):
    return [[float(f), float(bw) if np.isfinite(bw) else None, float(db)]
            for f, bw, db in peak_rows(grid, magnitude, grid[0])]


def compare_response(case, snapshot):
    sweep = case['transfer']
    grid = np.arange(sweep['start_hz'], sweep['end_hz'] + 1, sweep['step_hz'], dtype=float)
    nodes = np.array(snapshot['nodes'], dtype=float)
    branches = np.array(snapshot['branches'], dtype=float)
    source = {name: snapshot[name] for name in ('inject', 'lips', 'nose')}
    source['cut'] = tuple(snapshot['cut'])
    independent = np.concatenate([independent_response(chunk, nodes, branches, source)[:, -1]
                                  for chunk in np.array_split(grid, 16)])
    native = np.asarray(snapshot['magnitude'])
    relative_error = float(np.max(abs(native - abs(independent))) / np.max(abs(independent)))
    complex_error = None
    if 'complex' in snapshot:
        real, imaginary = np.asarray(snapshot['complex']).T
        complex_error = float(np.max(abs(real + 1j * imaginary - independent)) / np.max(abs(independent)))
    peaks = snapshot['peaks'] if 'peaks' in snapshot else local_peaks(grid, native)
    checked = local_peaks(grid, abs(independent))
    maximum_peak_error = (max(abs(a[0] - b[0]) for a, b in zip(peaks, checked, strict=True))
                          if len(peaks) == len(checked) and peaks else None)
    band = [p for p in peaks if sweep['high_band_hz'][0] <= p[0] <= sweep['high_band_hz'][1]]
    principal = max(band, key=lambda p: p[2], default=None)
    finite = (np.isfinite(nodes).all() and np.isfinite(branches).all() and np.isfinite(native).all()
              and np.isfinite(independent).all() and np.array_equal(snapshot['frequencies_hz'], grid))
    return {'grid_and_finite': bool(finite), 'relative_magnitude_error': relative_error, 'relative_complex_error': complex_error,
            'max_peak_distance_from_independent_hz': maximum_peak_error, 'high_band_peak': principal,
            'high_band_peak_count': len(band), 'peaks': peaks}


def compare_sections(upper, candidate):
    by_tube = {}
    for tube in ('pharynx', 'oral'):
        values = [np.asarray([numbers[2:] for numbers in state['sections'] if numbers[0] == tube], dtype=float)
                  for state in (upper, candidate)]
        by_tube[tube] = {'counts': [len(v) for v in values],
                        'lengths_cm': [float(v[:, 0].sum()) for v in values],
                        'minimum_areas_cm2': [float(v[:, 2].min()) for v in values],
                        'max_area_difference_cm2':
                            float(np.max(abs(values[1][:, 1] - values[0][:, 1]))) if values[0].shape == values[1].shape else None}
    return by_tube


def measure(case, original, archive, pcm_reference, previous, out, execute):
    settings = case['observation']
    target = case['target']
    specified = (target['start_sample_12khz'] + target['window_samples'] // 2) * settings['pcm_rate_hz'] // 12000
    if specified != settings['completed_pcm_frames'] or (settings['pcm_rate_hz'], settings['internal_rate_hz']) != (48000, 96000):
        raise ValueError('登録したLPC窓中央と出力フレームの関係が一致しません')
    pcm = observe(case, original, archive, out, execute)
    states = {voice: tsp.read(out / f'{voice}-linear.json') for voice in VOICES}
    with (out / 'candidate-sections.csv').open(newline='') as stream:
        entries = list(csv.DictReader(stream))
    candidate_sections = [[row['tube'], int(row['cell']), *(float(row[name])
                          for name in ('length_cm', 'area_cm2', 'minimum_area_cm2'))] for row in entries]
    section_agreement = all(int(row['frame']) == specified - 1 for row in entries) and candidate_sections == states['candidate']['sections']
    response = {voice: compare_response(case, snapshot) for voice, snapshot in states.items()}
    peaks, pcm_poles = {}, {}
    for voice in VOICES:
        prior, = (row for row in pcm_reference['windows'] if row['source'] == voice and row['center'] == target['center'])
        if prior['start_sample'] != target['start_sample_12khz']:
            raise ValueError('先行のPCM窓が観測位置と一致しません')
        pcm_poles[voice] = prior['bands']['high']['eligible'][0][0] if prior['bands']['high']['eligible'] else None
        band = response[voice]['high_band_peak']
        peaks[voice] = band[0] if band is not None else None
        response[voice]['peak_minus_pcm_hz'] = (peaks[voice] - pcm_poles[voice]
                                               if peaks[voice] is not None and pcm_poles[voice] is not None else None)
    linear_delta, pcm_delta = (values['candidate'] - values['upstream'] if None not in values.values() else None
                               for values in (peaks, pcm_poles))
    limits = case['limits']
    linear_sign_resolved = linear_delta is not None and abs(linear_delta) > limits['minimum_linear_difference_to_resolve_sign_hz']
    checks = {
        'ordinary_cli_and_probe_pcm_match_archive': all(row['cli_matches_archived_file'] and row['observed_pcm_matches_cli']
                                                       and row['pcm_rate_hz'] == settings['pcm_rate_hz'] for row in pcm.values()),
        'candidate_sections_match_ordinary_cli': section_agreement,
        'capture_completed_pcm_frame': all(state['completed_frames'] == specified for state in states.values()),
        'native_and_independent_linear_response': all(row['grid_and_finite']
            and row['relative_magnitude_error'] <= limits['solver_relative_error']
            and (row['relative_complex_error'] is None or row['relative_complex_error'] <= limits['solver_relative_error'])
            and row['max_peak_distance_from_independent_hz'] is not None
            and row['max_peak_distance_from_independent_hz'] <= limits['native_peak_difference_hz'] for row in response.values()),
        'revision_keeps_initial_measurements': previous['linear'] == response and previous['pcm_poles_hz'] == pcm_poles
            and previous['linear_delta_hz'] == linear_delta and previous['pcm_delta_hz'] == pcm_delta,
    }
    predictions = {
        'high_band_peak_near_pcm': all(row['peak_minus_pcm_hz'] is not None
            and abs(row['peak_minus_pcm_hz']) <= limits['peak_to_pcm_difference_hz'] for row in response.values()),
        'sign_of_high_band_difference_matches_pcm': (linear_delta * pcm_delta > 0
                                                    if linear_sign_resolved and pcm_delta is not None else None),
    }
    return {'checks': checks, 'predictions': predictions, 'completed_frames': specified, 'pcm': pcm,
            'linear': response, 'pcm_poles_hz': pcm_poles, 'linear_delta_hz': linear_delta, 'pcm_delta_hz': pcm_delta,
            'sign_resolution': {'linear_sign_resolved': linear_sign_resolved,
                                'threshold_hz': limits['minimum_linear_difference_to_resolve_sign_hz'],
                                'previous_prediction': previous['predictions']['sign_of_high_band_difference_matches_pcm']},
            'sections': compare_sections(states['upstream'], states['candidate'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    source = tsp.open_run(case['source_comparison'], revision)
    render = tsp.open_run(case['render'], revision)
    comparison_before_revision = tsp.open_run(case['previous'], revision)
    pcm_reference = tsp.verified_path(source, 'summary.json')
    previous = tsp.verified_path(comparison_before_revision, 'summary.json')
    uid = case['target']['utterance']
    original = tsp.verified_path(render, f'artifacts/{uid}/candidate.json')
    archive = {voice: tsp.verified_path(render, f'artifacts/{uid}/{voice}.wav') for voice in VOICES}
    inputs = [CASE, Path(__file__).resolve(), original, pcm_reference, previous, *archive.values(), UPPER, CANDIDATE, PATCH, DICT,
              *(TOOLS / name for name in ('tsp_transfer_request.rs', 'candidate_tsp_tract_snapshot.rs', 'tsp_fine_trace.rs',
                    'measure_tsp_stressed_vowel_formants.py', 'measure_vowel_transfer.py', 'measure_uniform_tube.py', 'upstream_baseline.py')),
              *(run[0] / 'manifest.json' for run in (source, render, comparison_before_revision)),
              *(UPSTREAM / name for name in ('crates/chimera/src/airway/network.rs', 'crates/chimera/src/airway/frequency.rs',
                    'crates/chimera/src/voice/human_voice.rs', 'crates/chimera-cli/src/render.rs',
                    'crates/chimera/tests/airway.rs', 'crates/chimera/tests/golden_analysis.rs')), *candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, execute: measure(case, original, archive, tsp.read(pcm_reference), tsp.read(previous), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
