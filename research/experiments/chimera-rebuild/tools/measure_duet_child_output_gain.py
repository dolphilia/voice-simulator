"""デュエット声部の出力ゲインだけを変更し、全区間の出力段を照合する。"""

import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import scipy
from scipy.io import wavfile
from scipy.signal import lfilter
from scipy.special import i0

import measure_duet_child_glottal_noise_origin as noise
from measure_duet_telemetry import candidate_render, upper_render
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from measure_wasm_fixed import read_json
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


UPPER_BODY_PROBE = noise.TOOLS / 'upstream_duet_body_probe.rs'
COLUMNS = ('radiation_first', 'radiation_second', 'decimated', 'gain_applied',
           'dc_removed', 'envelope', 'hold_frames')


def trace_input(path, frames):
    values = np.fromfile(path, dtype='<f8').reshape(-1, len(COLUMNS))
    if values.shape[0] != frames or not np.isfinite(values).all():
        raise ValueError(f'出力段の長さまたは有限性が登録と一致しません ({path.name})')
    return values


def difference(left, right, tolerance):
    delta = np.abs(left.astype(float) - right)
    nonzero = np.flatnonzero(delta)
    failures = np.flatnonzero(delta > tolerance)
    peak = int(delta.argmax())
    return {'first_unequal_frame': int(nonzero[0]) + 1 if nonzero.size else None,
            'first_over_tolerance_frame': int(failures[0]) + 1 if failures.size else None,
            'peak_frame': peak + 1, 'peak_error': float(delta[peak]),
            'values_at_peak': [float(left[peak]), float(right[peak])]}


def envelope_response(dc, rate, stage):
    release = math.exp(-1 / (stage['release_seconds'] * rate))
    duration = round(stage['hold_seconds'] * rate)
    peak, remaining = 0.0, 0
    envelope = np.empty_like(dc)
    hold = np.empty_like(dc)
    for index, value in enumerate(np.abs(dc)):
        if value >= peak:
            peak, remaining = value, duration
        elif remaining:
            remaining -= 1
        else:
            peak *= release
        envelope[index], hold[index] = peak, remaining
    return envelope, hold


def decimate_radiation(radiation, factor, stage):
    half_width = factor * stage['fir_taps_per_phase'] // 2
    offsets = np.arange(-half_width, half_width + 1)
    cutoff = stage['fir_cutoff_at_output_rate'] / factor
    beta = stage['fir_kaiser_beta']
    kernel = np.sinc(2 * cutoff * offsets) * i0(beta * np.sqrt(1 - (offsets / half_width)**2))
    kernel /= math.fsum(kernel)
    return np.convolve(radiation, kernel)[:len(radiation)][factor - 1::factor]


def independent_stages(trace, pcm, gain, study):
    stage = study['stage']
    rate = study['sample_rate_hz']
    factor = study['internal_sample_rate_hz'] // rate
    radiation = trace[:, :2].ravel()
    decimated, gain_applied, dc, envelope, hold = trace[:, 2:].T
    fir = decimate_radiation(radiation, factor, stage)
    pole = math.exp(-math.tau * stage['dc_hz'] / rate)
    highpass = lfilter([1, -1], [1, -pole], gain_applied)
    expected_envelope, expected_hold = envelope_response(dc, rate, stage)
    threshold = stage['peak_threshold']
    limited = dc * (threshold / np.maximum(envelope, threshold))
    clip = stage['clip_threshold']
    clipped = np.where(np.abs(limited) > clip, np.sign(limited) *
                       (clip + (1 - clip) * np.tanh((np.abs(limited) - clip) / (1 - clip))), limited)
    return {
        'fir_error_times_base_gain': float(np.max(np.abs(decimated - fir)) * study['base_gain']),
        'gain_input_error': float(np.max(np.abs(gain_applied - decimated * gain))),
        'dc_error': float(np.max(np.abs(dc - highpass))),
        'envelope_error': float(np.max(np.abs(envelope - expected_envelope))),
        'hold_error_frames': float(np.max(np.abs(hold - expected_hold))),
        'pcm_matches_independent_limiter': noise.bit_equal(pcm, clipped.astype('<f4')),
        'peak_envelope': float(envelope.max()),
        'peak_limited_frames': int(np.count_nonzero(envelope > threshold)),
        'soft_clipped_frames': int(np.count_nonzero(np.abs(limited) > clip)),
    }


def capture_upper_reference(song, upper_input, references, out, scratch, execute):
    if isinstance(song['body'], str):
        score = song['score']
        wave, _, tele_same = upper_render(
            {'body': song['body'], 'start_seconds': score['start_seconds'], 'midi': [n['midi'] for n in score['notes']]},
            song, 1, out, execute)
        rate, samples = wavfile.read(wave)
        return rate, samples, tele_same

    fixed = out / 'fixed'
    fixed.mkdir()
    exe = build_upstream_probe(UPPER_BODY_PROBE, fixed, execute, extra_libraries=('serde_json',))
    wave, tele = fixed / 'upper-2.f32le', fixed / 'upper-2-noise.json'
    execute([str(exe), str(upper_input), str(scratch / 'upper.dict'), str(wave)], stdout=tele)
    pcm = np.fromfile(wave, dtype='<f4')
    agrees = sha256(tele) == sha256(references['upper-2-noise.json'])
    agrees = agrees and noise.bit_equal(pcm, np.fromfile(references['upper-2.f32le'], dtype='<f4'))
    return read_json(tele)['layout']['sample_rate_hz'], pcm, agrees


def mixed_gain_rule(body, endpoints):
    female, child = body['female'], body['child']
    weights = ((1 - child) * (1 - female), (1 - child) * female, child)
    scale = math.fsum(w * s for w, s in zip(weights, endpoints, strict=True))
    return scale, 0.875 + 0.125 * min(1.0, max(0.0, (scale - 0.9) / 0.1))


def capture(study, references, out, execute):
    base = read_json(references['resting-tip.json'])
    song = base['song_voice']
    base_settings = song['voice']
    voice_index = study.get('voice_index', 1)
    upper_input = references[f'upper-{voice_index}-input.json']
    gain = study['base_gain'] * study['gain_factor']
    alternative = deepcopy(base)
    alternative['song_voice']['voice']['output_gain'] = gain
    case_path = out / ('child-gain.json' if voice_index == 1 else 'mixed-gain.json')
    case_path.write_text(json.dumps(alternative, ensure_ascii=False, indent=2) + '\n')
    wave_inputs = (references['resting-tip.json'], case_path)
    ordinary = [wavfile.read(candidate_render(source, index, out, execute)[0])
                for index, source in enumerate(wave_inputs, 1)]
    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'engine', '--test', 'body_mix'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    trace, pcm, plans = {}, {}, {}
    with TemporaryDirectory(prefix='duet-gain-probe-', dir=out.parent) as directory:
        scratch = Path(directory)
        local, upper = noise.build_observers(study['upstream_revision'], out, execute, scratch)
        upper_rate, upper_default, upper_reference_agrees = capture_upper_reference(
            song, upper_input, references, out, scratch, execute)
        settings = (('base', local, wave_inputs[0], 'local.dict', ()),
                    ('matched', local, wave_inputs[1], 'local.dict', ()),
                    ('upstream', upper, upper_input, 'upper.dict', ('without_all_three',)),
                    ('upstream_default', upper, upper_input, 'upper.dict', ('default',)))
        for name, executable, source, dictionary, variant in settings:
            wave = out / f'{name}.f32le'
            stages = out / f'{name}-output.f64le'
            plan = out / f'{name}-gestures.json'
            args = [str(executable), str(source), str(scratch / dictionary), '0', *variant,
                    str(out / f'{name}-detail.csv'), str(wave)]
            if name != 'upstream_default':
                args.extend(('--output-trace', str(stages)))
            execute(args, stdout=plan)
            if name != 'upstream_default':
                trace[name] = trace_input(stages, study['frames'])
            pcm[name] = np.fromfile(wave, dtype='<f4')
            plans[name] = sha256(plan)

    tol = study['tolerances']
    diagnostics = {name: independent_stages(trace[name], pcm[name], selected, study)
                   for name, selected in zip(trace, (study['base_gain'], gain, gain), strict=True)}
    upper_check = ('upper_default_matches_unmodified_body_probe' if 'body' in study
                   else 'upper_default_matches_ordinary_cli')
    checks = {
        'registered_inputs': base_settings['output_gain'] == study['base_gain']
        and song['internal_sample_rate_hz'] == study['internal_sample_rate_hz']
        and base_settings['output_sample_rate_hz'] == study['sample_rate_hz'],
        'only_output_gain_changed': gain != base_settings['output_gain']
        and alternative == (base | {'song_voice': song | {'voice': base_settings | {'output_gain': gain}}}),
        'pcm_sizes_and_finiteness': all(len(wave) == study['frames'] and np.isfinite(wave).all() for wave in pcm.values()),
        'local_cli_matches_both_probes': all(rate == study['sample_rate_hz'] and noise.bit_equal(wave, pcm[key])
            for (rate, wave), key in zip(ordinary, ('base', 'matched'), strict=True)),
        upper_check: upper_rate == study['sample_rate_hz'] and upper_reference_agrees
        and noise.bit_equal(upper_default, pcm['upstream_default']),
        'prior_audio_unchanged': all(noise.bit_equal(pcm[key], np.fromfile(references[old], dtype='<f4'))
            for key, old in (('base', 'resting_tip-pcm.f32le'), ('upstream', 'upstream-pcm.f32le'))),
        'prior_scores_unchanged': plans['base'] == plans['matched'] == sha256(references['resting_tip-gestures.json'])
        and plans['upstream'] == plans['upstream_default'] == sha256(references['upstream-gestures.json']),
        'independent_filter_and_envelope': all(max(row[key] for key in (
            'fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error')) <= tol['independent_normalized']
            and row['hold_error_frames'] == 0 for row in diagnostics.values()),
        'independent_limiter_matches_pcm_bits': all(row['pcm_matches_independent_limiter'] for row in diagnostics.values()),
    }
    differences = {}
    for left, right in (('base', 'matched'), ('base', 'upstream'), ('matched', 'upstream')):
        columns = dict(zip(COLUMNS, zip(trace[left].T, trace[right].T, strict=True), strict=True))
        thresholds = (tol['radiation_cm3_s2'],) * 3 + (tol['aligned_cross_normalized'],) * 3 + (0.0,)
        results = {key: difference(*columns[key], limit) for key, limit in zip(COLUMNS, thresholds, strict=True)}
        results['pcm'] = difference(pcm[left], pcm[right], tol['pcm_absolute'])
        differences[f'{left}_vs_{right}'] = results
    cross = differences['matched_vs_upstream']
    predictions = {
        'first_local_difference_is_gain': np.array_equal(trace['base'][:, :3].view('<u8'), trace['matched'][:, :3].view('<u8'))
        and differences['base_vs_matched']['gain_applied']['first_unequal_frame'] is not None,
        'peak_limiter_inactive': all(row['peak_limited_frames'] == row['soft_clipped_frames'] == 0
            for row in diagnostics.values()),
        'gain_closes_pcm_difference': cross['pcm']['first_over_tolerance_frame'] is None
        and differences['base_vs_upstream']['pcm']['peak_error'] >= study['minimum_base_pcm_difference'],
        'aligned_internal_values_within_tolerance': all(
            cross[key]['first_over_tolerance_frame'] is None for key in COLUMNS[:-1]),
    }
    result = {'checks': checks, 'predictions': predictions, 'frames': study['frames'], 'scipy': scipy.__version__,
              'gain_applied': {'base': study['base_gain'], 'matched': gain, 'factor': study['gain_factor']},
              'independent_output': diagnostics, 'differences': differences}
    if 'body' in study:
        scale, factor = mixed_gain_rule(study['body'], study['body_scale_endpoints'])
        checks['registered_mixed_body_and_gain'] = (
            song['body'] == read_json(upper_input)['body'] == study['body']
            and abs(scale - study['expected_body_scale']) <= tol['body_scale_absolute'] and factor == study['gain_factor'])
        post_pcm = difference(pcm['base'].astype(float) * factor, pcm['upstream'], tol['pcm_absolute'])
        predictions['render_gain_reduces_pcm_error_more_than_post_scaling'] = cross['pcm']['peak_error'] < post_pcm['peak_error']
        result['body_scale_and_gain'] = {'scale': scale, 'factor': factor}
        result['post_pcm_scaling_vs_upstream'] = post_pcm
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', choices=('child', 'mixed'), default='child', help='比較する声部')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDに使用できる文字を確認してください')
    case = WORKSPACE / f'cases/duet-{args.case}-output-gain.json'
    study = read_json(case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    voice_index = study.get('voice_index', 1)
    fixed_refs = ('upper-2.f32le', 'upper-2-noise.json') if args.case == 'mixed' else ()
    dependencies = (('input', 'duet-head-turbulence-body', (f'upper-{voice_index}-input.json', *fixed_refs)),
                    ('reference', study.get('reference_case_id', 'duet-child-initial-tip'), ('resting-tip.json', 'resting_tip-pcm.f32le',
                     'upstream-pcm.f32le', 'resting_tip-gestures.json', 'upstream-gestures.json')))
    references, manifests = {}, []
    for key, case_id, files in dependencies:
        run = run_manifest(study[f'{key}_run'], case_id, revision)
        manifest = run[0] / 'manifest.json'
        if run[1]['status'] != 'pass' or sha256(manifest) != study[f'{key}_manifest_sha256']:
            parser.error(f'先行実行 {run[0].name} が登録と一致しません')
        references.update({name: verified_path(run, f'artifacts/{name}') for name in files})
        manifests.append(manifest)
    inputs = [case, Path(__file__).resolve(), Path(noise.__file__), noise.PATCH, noise.OUTPUT_PATCH, *noise.PROBES,
              *noise.DICTIONARIES, noise.TOOLS / 'duet_child_noise_trace.rs', *manifests,
              *references.values(), *candidate_sources(),
              *(UPSTREAM / name for name in ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/airway/decimator.rs',
                  'crates/chimera/src/voice/human_voice.rs', 'crates/chimera-cli/src/render.rs',
                  'crates/chimera/tests/engine.rs', 'crates/chimera/tests/body_mix.rs')),
              *(noise.TOOLS / name for name in ('measure_uniform_tube.py', 'measure_duet_telemetry.py',
                  'measure_fan_crossing_allocations.py', 'measure_wasm_fixed.py', 'upstream_baseline.py'))]
    if args.case == 'mixed':
        inputs.append(UPPER_BODY_PROBE)
    metadata = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, case, inputs, metadata,
                              lambda out, execute: capture(study, references, out, execute),
                              command=None, input_root=noise.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
