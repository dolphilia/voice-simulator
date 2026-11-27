"""固定 /i/ の壁・口端・鼻端の放射を採取し、PCM差を分解する。"""

import argparse
from pathlib import Path
import re
import subprocess

import numpy as np
from scipy.signal import firwin, lfilter

import measure_fixed_vowel_i_coupled_smoothing as coupled
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/fixed-vowel-i-radiation-components.json'
READ, SHARED = coupled.READ, coupled.SHARED
EVIDENCE = coupled.REPLAY_EVIDENCE
COMPONENTS = coupled.RADIATION_COMPONENTS[:3]
VARIANTS = (*coupled.VARIANTS, coupled.REPLAY_VARIANT)
COMPARISONS = {
    'full': ('baseline', 'smoothed'),
    'without_area': ('baseline', coupled.REPLAY_VARIANT),
    'area': (coupled.REPLAY_VARIANT, 'smoothed'),
}


def archive_inputs(case):
    archive = coupled.archive_inputs(case)
    record, manifest, definition = coupled.smoothing.verified_reference(case['radiation_reference'], case['upstream_revision'])
    return {
        **archive, 'radiation-reference-manifest.json': manifest, 'radiation-reference-case.json': definition,
        'radiation-reference-states.npz': coupled.verified_path(record, 'artifacts/observations.npz'),
        'radiation-reference-summary.json': coupled.verified_path(record, 'summary.json'),
    }


def derivative(flow, fs, edition):
    change = np.diff(flow, axis=0, prepend=np.zeros((1, *flow.shape[1:])))
    return change * fs if edition == 'upstream' else change / (1.0 / fs)


def linear_pcm(rad, taps, pole, factor, gain):
    decimated = lfilter(taps, [1.0], rad, axis=0)[factor - 1::factor]
    return lfilter([1, -1], [1, -pole], gain * decimated, axis=0)


def decompose(case, edition, flows, state, waves, pre_cast, taps, pole, factor, gain):
    cfg = case['measurement']
    split = case['radiation_split']
    start, stop = cfg['steady_window_samples']
    samples = slice(start // factor, stop // factor)
    fs = cfg['internal_rate_hz']
    results, checks = {}, {}
    first = coupled.first_difference
    for name, (base, trial) in COMPARISONS.items():
        differences = derivative((flows[trial] - flows[base])[:, :3], fs, edition)
        total_difference = state[trial][:, coupled.RADIATION] - state[base][:, coupled.RADIATION]
        components = linear_pcm(differences, taps, pole, factor, gain)
        total = linear_pcm(total_difference, taps, pole, factor, gain)
        sum_error = float(abs(total - components.sum(axis=1)).max())
        checks[f'{name}/linear_component_differences_sum'] = sum_error < split['component_output_sum_max_error_lt']
        norm_squared = float(np.dot(total[samples], total[samples]))
        if norm_squared == 0.:
            raise ValueError(f'切替後の総放射の差がありません ({edition}/{name})')
        captured_first = first(waves[base], waves[trial])
        baseline = pre_cast[base]
        baseline_pcm = baseline.astype(np.float32)
        zero = np.zeros(len(total))
        parts = {}
        for col, label in enumerate(COMPONENTS):
            wave = components[:, col]
            observed = wave[samples]
            parts[label] = {
                'first_radiation_derivative_difference_sample': first(np.zeros(len(differences)), differences[:, col]),
                'first_linear_output_difference_frame': first(zero, wave),
                'first_pcm_difference_frame_with_component_only': first(
                    baseline_pcm, (baseline + wave).astype(np.float32)),
                'rms': float(np.sqrt(np.mean(observed**2))),
                'rms_relative_to_total': float(np.linalg.norm(observed) / np.sqrt(norm_squared)),
                'projection_onto_total': float(np.dot(observed, total[samples]) / norm_squared),
                'linear_change_at_first_stored_pcm_frame': None if captured_first is None else float(wave[captured_first]),
            }
        reconstructed_first = first(baseline_pcm, (baseline + total).astype(np.float32))
        checks[f'{name}/independent_pcm_difference_onset'] = reconstructed_first == captured_first
        wall, lip, nose = (parts[key] for key in COMPONENTS)
        w, l = (part['first_radiation_derivative_difference_sample'] for part in (wall, lip))
        results[name] = {
            'parts': parts, 'total_rms': float(np.sqrt(np.mean(total[samples]**2))),
            'component_output_sum_error': sum_error, 'first_pcm_difference_frame': captured_first,
            'independent_first_pcm_frame': reconstructed_first,
            'hypotheses': {
                'wall_changes_before_lip': w is not None and l is not None and w < l,
                'lip_alone_preserves_stored_pcm_onset': captured_first is not None
                and lip['first_pcm_difference_frame_with_component_only'] == captured_first,
                'nose_unchanged': nose['first_radiation_derivative_difference_sample'] is None,
                'lip_projection_matches_prediction': abs(lip['projection_onto_total'] - split['predicted_lip_projection'][name])
                < split['hypothesis_lip_projection_absolute_error_lt'],
            },
        }
    return results, checks


def analyze(case, archive, output):
    original = coupled.analyze(case, archive, output)
    checks = original['checks']
    base = READ(archive['radiation-reference-case.json'])
    checks['saved_pressure_replay_conditions_reused'] = (
        all(case[key] == base[key] for key in ('measurement', 'pressure_gate', 'pressure_replay_reference'))
        and all(READ(archive['radiation-reference-summary.json'])['checks'].values()))
    cfg = case['measurement']
    split = case['radiation_split']
    fs, rate = cfg['internal_rate_hz'], cfg['output_rate_hz']
    factor = fs // rate
    taps = firwin(factor * 24 + 1, 2 * 0.46 / factor, window=('kaiser', 8.5))
    pole = np.exp(-2 * np.pi * 25 / rate)
    gain = READ(archive['voice-case.json'])['voice']['output_gain']
    outputs, editions = {}, {}
    with (np.load(output / 'observations.npz', allow_pickle=False) as data,
          np.load(archive['radiation-reference-states.npz'], allow_pickle=False) as previous):
        checks['all_previous_observations_and_pcm_are_bit_equal'] = all(
            coupled.same_bits(data[key], previous[key]) for key in previous.files)
        for edition in coupled.EDITIONS:
            flows, state, waves, pre_cast = {}, {}, {}, {}
            outputs[edition] = {}
            for name in VARIANTS:
                stem = f'{edition}_{name}'
                flows[name] = data[f'{stem}_radiation']
                state[name] = data[stem]
                waves[name] = data[f'{stem}_pcm']
                wall, lip, nose, total = flows[name].T
                stored_derivative = state[name][:, coupled.RADIATION]
                rederived = derivative(total, fs, edition)
                checks[f'{stem}/flow_sum_and_derivative_bits'] = (
                    coupled.same_bits((wall + lip) + nose, total) and coupled.same_bits(rederived, stored_derivative))
                component_pcm = linear_pcm(derivative(flows[name][:, :3], fs, edition), taps, pole, factor, gain)
                pre_cast[name] = linear_pcm(stored_derivative, taps, pole, factor, gain)
                peak = float(abs(pre_cast[name]).max())
                sum_error = float(abs(component_pcm.sum(axis=1) - pre_cast[name]).max())
                pcm_error = float(abs(pre_cast[name].astype(np.float32) - waves[name]).max())
                checks[f'{stem}/component_output_sum_and_limiter_inactive'] = (
                    peak < 0.75 and sum_error < split['component_output_sum_max_error_lt']
                    and pcm_error < cfg['pcm_absolute_error_lt'])
                outputs[edition][name] = {'peak_before_f32': peak, 'component_sum_error': sum_error,
                                          'independent_pcm_max_error': pcm_error}
            editions[edition], conditions = decompose(case, edition, flows, state, waves, pre_cast, taps, pole, factor, gain)
            checks.update({f'{edition}/{k}': value for k, value in conditions.items()})
        cross_edition_error = {
            name: coupled.TANGENT.peak_error(data[f'candidate_{name}_radiation'], data[f'upstream_{name}_radiation'])
            for name in VARIANTS}
        checks['all_radiation_components_match_upstream'] = all(
            value < cfg['component_peak_relative_error_lt'] for value in cross_edition_error.values())
    return {**original, 'checks': {key: bool(value) for key, value in checks.items()},
            'radiation_components': {'by_edition': editions, 'output_reconstruction': outputs,
                                     'cross_edition_flows_peak_relative_error': cross_edition_error}}


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
        coupled.capture(case, archive, out, execute)
        return analyze(case, archive, out)

    inputs = [CASE, Path(__file__), *archive.values(), coupled.vowel_voice.PROBE,
              *SHARED.candidate_sources(), *coupled.TANGENT.CANDIDATE_DATA,
              *(Path(module.__file__) for module in (coupled, coupled.smoothing, coupled.fixed_lf, coupled.vowel_i,
                                                    coupled.pcm, SHARED, coupled.TANGENT)),
              UPSTREAM / coupled.TANGENT.UPPER, UPSTREAM / coupled.fixed_lf.UPPER_VOICE, UPSTREAM / coupled.UPPER_GLOTTIS,
              UPSTREAM / 'crates/chimera/src/voice/human_airway.rs', UPSTREAM / 'Cargo.lock',
              *(UPSTREAM / f'crates/chimera/tests/{name}.rs' for name in ('airway', 'airway_adversarial', 'lung_port'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'invoked_from': str(Path.cwd())}
    return SHARED.record_measurement(args.run_id, CASE, inputs, details, measure, command=None,
                                     input_root=coupled.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
