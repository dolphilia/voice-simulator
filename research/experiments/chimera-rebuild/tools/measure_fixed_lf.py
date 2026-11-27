"""固定声道を通常の声門、流量の再入力、固定LFで駆動して比較する。"""

import argparse
import difflib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
from scipy.integrate import quad
from scipy.io import wavfile
from scipy.optimize import brentq

import measure_lip_crossing_thickness as saved_run
import measure_pcm_output as pcm
import measure_uniform_tube as shared
import measure_vowel_voice as vowel
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-lf-glottal-flow.json'
UPPER_VOICE = 'crates/chimera/src/voice/human_voice.rs'
UPPER_NETWORK = 'crates/chimera/src/airway/network.rs'
OBSERVED = ('pressure_sub_dyn_cm2', 'pressure_supra_dyn_cm2', 'glottal_flow_cm3_s',
            'lip_flow_cm3_s', 'nose_flow_cm3_s', 'radiation_derivative_cm3_s2')
Q = OBSERVED[2]
LIP = OBSERVED[3]
RAD = OBSERVED[-1]
FIXTURE = (WORKSPACE.parent
           / 'autonomous-research-cycle/campaigns/nas-lf-source-mechanism-20261008-v1/fixture-audit.json')
CLI = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']


def patch_source(code, name, replacements):
    file = code / name
    before = after = file.read_text()
    for old, new in replacements:
        if after.count(old) != 1:
            raise ValueError(f'固定上流の計測箇所を特定できません ({name})')
        after = after.replace(old, new)
    file.write_text(after)
    return ''.join(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                        fromfile=f'a/{name}', tofile=f'b/{name}'))


def build_reference(revision, artifacts, execute):
    with TemporaryDirectory(prefix='upstream-fixed-flow-', dir=artifacts) as temporary:
        scratch = Path(temporary)
        code = scratch / 'code'
        code.mkdir()
        archive = scratch / 'source.tar'
        execute(['git', 'archive', revision], cwd=UPSTREAM, stdout=archive)
        execute(['tar', '-xf', str(archive), '-C', str(code)])
        voice_patch = patch_source(code, UPPER_VOICE, (
            ('    pub glottis: crate::sources::glottis::ParametricGlottis,\n',
             '    pub glottis: crate::sources::glottis::ParametricGlottis,\n'
             '    pub research_flow: Option<Vec<f64>>,\n'
             '    pub research_flow_trace: Option<Vec<[f64; 6]>>,\n'),
            ('            glottis: crate::sources::glottis::ParametricGlottis::new(fs),\n',
             '            glottis: crate::sources::glottis::ParametricGlottis::new(fs),\n'
             '            research_flow: None,\n'
             '            research_flow_trace: None,\n'),
            ('                net.set_port_area(gp, a);\n                let y = net.step();',
             """                let input = self.research_flow.as_ref().zip(self.research_flow_trace.as_ref())
                    .map(|(flow, trace)| (gp, flow[trace.len()]));
                net.set_port_area(gp, if input.is_some() { 0.0 } else { a });
                let y = net.research_step(input);
                if let Some(trace) = &mut self.research_flow_trace {
                    trace.push([net.p[sub_node], net.p[supra], net.u[gp],
                        net.radiated_flow(self.airway.rad_lips),
                        net.radiated_flow(self.airway.rad_nose), y]);
                }"""),
        ))
        airway_patch = patch_source(code, UPPER_NETWORK, (
            ('    pub fn step(&mut self) -> f64 {\n',
             '    pub fn step(&mut self) -> f64 {\n        self.research_step(None)\n    }\n\n'
             '    pub(crate) fn research_step(&mut self, prescribed: Option<(usize, f64)>) -> f64 {\n'),
            ('                let b = b_b[j];\n                let l: f64;',
             """                let b = b_b[j];
                if let Some((_, flow)) = prescribed.filter(|&(branch, _)| branch == j) {
                    u_arr[j] = flow;
                    flow_sum[a] -= flow;
                    flow_sum[b] += flow;
                    continue;
                }
                let l: f64;"""),
        ))
        (artifacts / 'upstream-fixed-flow.patch').write_text(voice_patch + airway_patch)
        return shared.build_upstream_probe(vowel.PROBE, artifacts, execute, upstream=code,
                                           rustc_args=('--cfg', 'research_fixed_glottal_flow'))


def lf_volume_flow(config, target_mean):
    tp, te, ta, ee = (config['lf_shape'][name] for name in ('tp', 'te', 'ta', 'ee'))
    duration = 1 - te
    omega = np.pi / tp
    epsilon = brentq(lambda e: -np.expm1(-e * duration) - e * ta, 1e-6, 1 / ta)
    tail = np.exp(-epsilon * duration)

    def return_integral(t):
        return (np.expm1(-epsilon * t) / epsilon + t * tail) * ee / (epsilon * ta)

    def e0(growth):
        return -ee / (np.exp(growth * te) * np.sin(omega * te))

    def open_integral(t, growth):
        angle = omega * t
        return e0(growth) * (
            np.exp(growth * t) * (growth * np.sin(angle) - omega * np.cos(angle)) + omega
        ) / (growth**2 + omega**2)

    alpha = brentq(lambda a: open_integral(te, a) + return_integral(duration), 0, 10)
    at_te = open_integral(te, alpha)
    count, fs, f0 = (config[key] for key in ('duration_samples', 'internal_rate_hz', 'f0_hz'))
    phase = np.remainder((np.arange(count) + 1) * f0, fs) / fs
    unique, inverse = np.unique(phase, return_inverse=True)
    shape = np.where(unique <= te, open_integral(np.minimum(unique, te), alpha),
                     at_te + return_integral(np.maximum(unique - te, 0)))
    fade = np.sin(np.pi / 2 * np.minimum(np.arange(count) / config['fade_samples'], 1))**2
    window = slice(*config['steady_window_samples'])
    scale = target_mean / np.mean(shape[inverse][window])
    prescribed = shape[inverse] * scale * fade

    # 解析積分とは別に、LF微分の二つの区間を数値積分する。
    def open_derivative(t):
        return e0(alpha) * np.exp(alpha * t) * np.sin(omega * t)

    def return_derivative(t):
        return -ee * (np.exp(-epsilon * (t - te)) - tail) / (epsilon * ta)

    reference_at_te = quad(open_derivative, 0, te, epsabs=1e-13)[0]
    reference = np.array([
        quad(open_derivative, 0, t, epsabs=1e-13)[0] if t <= te
        else reference_at_te + quad(return_derivative, te, t, epsabs=1e-13)[0]
        for t in unique
    ])
    return prescribed, {
        'epsilon': epsilon, 'alpha': alpha, 'e0': float(e0(alpha)), 'scale_cm3_s': float(scale),
        'minimum_flow_cm3_s': float(prescribed.min()),
        'absolute_quad_max_error_cm3_s': float(np.max(np.abs(prescribed - reference[inverse] * scale * fade))),
        'cycle_end_cm3_s': float(scale * (at_te + return_integral(duration))),
        'fixture_max_coefficient_error': float(np.max(np.abs(
            np.array([epsilon, alpha, e0(alpha)]) - np.array(saved_run.read(FIXTURE)['coefficients'][3:6])))),
    }


def render_arm(config, case, folder, probe, execute, native_input=None, upper_input=None):
    folder.mkdir()
    casepath = folder / 'case.json'
    if native_input is not None:
        case['fixed_voice_probe']['prescribed_flow_cm3_s'] = [
            repr(value) for value in native_input.tolist()
        ]
    casepath.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
    execute([*CLI, 'inspect', str(casepath)], stdout=folder / 'settings.json')
    trace = folder / 'trace.csv'
    execute([*CLI, 'render', str(casepath), str(trace)])
    n, fs, rate = (config[key] for key in ('duration_samples', 'internal_rate_hz', 'output_rate_hz'))
    frames = n // (fs // rate)
    columns, raw = pcm.read_columns(trace, n, len(vowel.TRACE))
    if tuple(columns) != vowel.TRACE or not np.array_equal(raw['internal_sample'], np.arange(n)):
        raise ValueError('固定発声の内部系列を照合できません')
    blocks = pcm.render_blocks(casepath, {'block_frames': config['host_block_frames']}, folder, execute)
    first, *rest = blocks.values()
    observed_rate, wave = wavfile.read(first[0])
    same_blocks = all(wav.read_bytes() == first[0].read_bytes() and csv.read_bytes() == first[1].read_bytes()
                      for wav, csv in rest)
    args = [case['measurement']['voice']['ipa'], fs, rate, frames, *(case['voice'][key] for key in
            ('pressure_cm_h2o', 'gate', 'breathiness', 'tension', 'output_gain')), folder]
    if upper_input is not None:
        path = folder / 'upstream-input.f64'
        upper_input.astype('<f8').tofile(path)
        args.append(path)
    execute([str(probe), 'render-research-flow', *map(str, args)], cwd=UPSTREAM)
    ref = np.fromfile(folder / 'upstream-internal.f64', dtype='<f8').reshape(n, len(OBSERVED))
    upper_wave = np.fromfile(folder / 'upstream-voice.f32', dtype='<f4')
    if (observed_rate != rate or wave.dtype != np.float32 or upper_wave.shape != wave.shape
            or wave.shape != (frames,) or not all(np.isfinite(a).all() for a in (ref, wave, upper_wave))):
        raise ValueError('PCMまたは上流の内部系列を照合できません')
    return raw, dict(zip(OBSERVED, ref.T, strict=True)), wave, upper_wave, same_blocks


def max_error(a, b):
    return float(np.max(np.abs(a - b)))


def relative_error(a, b):
    peak = float(np.max(np.abs(b)))
    return max_error(a, b) / peak if peak else (0.0 if np.array_equal(a, b) else None)


def first_difference(a, b, threshold=0):
    samples = np.flatnonzero(np.abs(a - b) > threshold)
    return int(samples[0]) if len(samples) else None


def stats(arm, config):
    trace, _, wave, _, _ = arm
    fs, rate, f0 = (config[key] for key in ('internal_rate_hz', 'output_rate_hz', 'f0_hz'))
    start, end = config['steady_window_samples']
    hop = fs // rate
    signals = {key: trace[key][start:end] for key in OBSERVED}
    lip_derivative = np.diff(trace[LIP], prepend=0.0) * fs
    nose_derivative = np.diff(trace['nose_flow_cm3_s'], prepend=0.0) * fs
    signals['lip_derivative_cm3_s2'] = lip_derivative[start:end]
    signals['wall_derivative_cm3_s2'] = signals[RAD] - (
        lip_derivative[start:end] + nose_derivative[start:end]
    )
    signals['pcm'] = wave[start // hop:end // hop].astype(float)
    bins = np.arange(1, config['harmonics'] + 1) * round(f0 * (end - start) / fs)
    spectrum = {key: np.fft.rfft(y)[bins] * (2 / len(y)) for key, y in signals.items()}
    rows = {key: {'mean': float(y.mean()), 'ac_rms': float(y.std()),
                  'harmonics': np.abs(spectrum[key]).tolist()} for key, y in signals.items()}
    rows[Q]['h1_minus_h2_db'] = float(20 * np.log10(abs(spectrum[Q][0] / spectrum[Q][1])))
    rows[Q]['estimated_f0_hz'] = vowel.independent_yin(signals[Q], fs, {
        'pitch_min_hz': 70, 'pitch_max_hz': 200, 'yin_threshold': 0.15,
    })[0]
    for key in (LIP, RAD):
        transfer = spectrum[key] / spectrum[Q]
        rows[key]['over_glottal_flow'] = [[float(z.real), float(z.imag)] for z in transfer]
    return rows


def compare(arms, config, lf_flow, lf_details, prior):
    coupled, replay, lf = (arms[name] for name in ('coupled', 'replay', 'lf'))
    criteria = config['criteria']
    values = {name: stats(arm, config) for name, arm in arms.items()}
    relative = {name: {key: relative_error(arm[0][key], arm[1][key]) for key in OBSERVED}
                for name, arm in arms.items()}
    pcm_error = {name: max_error(arm[2], arm[3]) for name, arm in arms.items()}
    old_rate, old_wav = wavfile.read(prior / 'artifacts/block-128.wav')
    old_pcm = np.fromfile(prior / 'artifacts/upstream-voice.f32', dtype='<f4')
    exact_replay = {
        revision: {key: np.array_equal(coupled[index][key], replay[index][key]) for key in OBSERVED}
        | {'pcm': np.array_equal(coupled[index + 2], replay[index + 2])}
        for index, revision in enumerate(('candidate', 'upstream'))
    }
    naive_diff = {key: first_difference(coupled[0][key], lf[0][key]) for key in OBSERVED}
    naive_diff['pcm'] = first_difference(coupled[2], lf[2])
    floor = criteria['first_difference_relative_peak_threshold']
    visible = {key: first_difference(coupled[0][key], lf[0][key],
                                     floor * np.max(np.abs(coupled[0][key]))) for key in OBSERVED}
    visible['pcm'] = first_difference(coupled[2], lf[2], floor * np.max(np.abs(coupled[2])))
    source_mean_error = abs(values['lf'][Q]['mean'] / values['coupled'][Q]['mean'] - 1)
    source_tilt_change = values['lf'][Q]['h1_minus_h2_db'] - values['coupled'][Q]['h1_minus_h2_db']
    acoustic_change = {key: values['lf'][key]['ac_rms'] / values['coupled'][key]['ac_rms'] - 1
                       for key in (LIP, RAD, 'lip_derivative_cm3_s2', 'wall_derivative_cm3_s2', 'pcm')}
    checks = {
        'lf_quadrature': max(lf_details['absolute_quad_max_error_cm3_s'], abs(lf_details['cycle_end_cm3_s']))
        <= criteria['lf_reference_absolute_error_max_cm3_s'],
        'lf_fixture_coefficients': lf_details['fixture_max_coefficient_error'] < 1e-12,
        'lf_flow_nonnegative': lf_details['minimum_flow_cm3_s'] >= criteria['lf_min_flow_cm3_s'],
        'lf_input_applied_exactly': all(np.array_equal(lf_flow, trace[Q]) for trace in lf[:2]),
        'registered_steady_mean': source_mean_error <= criteria['mean_match_relative_error_max'],
        'registered_pitch': all(row[Q]['estimated_f0_hz'] is not None
                                and abs(row[Q]['estimated_f0_hz'] - config['f0_hz'])
                                <= criteria['f0_absolute_error_max_hz'] for row in values.values()),
        'upstream_internal_signals': all(b is not None and b <= criteria['upstream_signal_relative_peak_error_max']
                                         for a in relative.values() for b in a.values()),
        'upstream_pcm': max(pcm_error.values()) <= criteria['upstream_pcm_absolute_error_max'],
        'replay_exact': all(all(row.values()) for row in exact_replay.values())
        == criteria['replay_same_backend_exact'],
        'host_block_invariance': all(arm[-1] for arm in arms.values()),
        'previous_candidate_pcm_exact': old_rate == config['output_rate_hz']
        and np.array_equal(coupled[2], old_wav[:len(coupled[2])]),
        'previous_upstream_pcm_exact': np.array_equal(coupled[3], old_pcm[:len(coupled[3])]),
        'lf_tilt_difference': abs(source_tilt_change) >= criteria['min_glottal_h1_minus_h2_difference_db'],
        'lf_acoustic_level_difference': min(abs(acoustic_change[key]) for key in (LIP, RAD))
        >= criteria['min_lip_and_radiation_relative_ac_rms_difference'],
        'causal_order': naive_diff[Q] is not None and naive_diff[LIP] is not None
        and all(naive_diff[key] == naive_diff[Q] for key in OBSERVED[:2])
        and naive_diff[LIP] > naive_diff[Q],
    }
    return {'checks': checks, 'stats': values, 'lf': lf_details, 'mean_relative_error': source_mean_error,
            'lf_minus_coupled_source_h1_minus_h2_db': source_tilt_change,
            'lf_minus_coupled_relative_ac_rms': acoustic_change, 'first_difference_sample': naive_diff,
            'difference_sample_rates_hz': {'pcm': config['output_rate_hz'], 'other': config['internal_rate_hz']},
            'first_difference_over_relative_floor': visible, 'upstream_pcm_max_error': pcm_error,
            'upstream_internal_relative_peak_error': relative, 'exact_replay': exact_replay}


def measure(config, base, prior, artifacts, execute):
    for test in ('voice_source', 'lung_port'):
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', test],
                cwd=UPSTREAM, stdout=artifacts / f'upstream-{test}.log')
    probe = build_reference(config['upstream_revision'], artifacts, execute)
    base['fixed_airway']['sample_count'] = config['duration_samples']

    def arm(name, native=None, upper=None):
        case = {**base, 'id': f"{config['id']}-{name}", 'fixed_voice_probe': {'internal_trace': True}}
        return render_arm(config, case, artifacts / name, probe, execute, native, upper)

    coupled = arm('coupled')
    replay = arm('replay', coupled[0][Q], coupled[1][Q])
    window = slice(*config['steady_window_samples'])
    flow, lf_details = lf_volume_flow(config, coupled[0][Q][window].mean())
    lf = arm('lf', flow, flow)
    summary = compare({'coupled': coupled, 'replay': replay, 'lf': lf}, config, flow, lf_details, prior)
    for folder in ('coupled', 'replay', 'lf'):
        for trace in sorted((artifacts / folder).glob('*.csv')):
            saved_run.compress(trace)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    config = saved_run.read(CASE)
    revision = config['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流のコミットと作業状態を確認してください')
    base_case = WORKSPACE / 'cases' / f"{config['base_case']}.json"
    base = saved_run.read(base_case)
    if (base['upstream_revision'], base['fixed_airway']['sample_rate_hz'],
            base['voice']['output_sample_rate_hz'], base['voice']['f0_hz']) != (
                revision, config['internal_rate_hz'], config['output_rate_hz'], config['f0_hz']):
        parser.error('基準ケースの版、標本化周波数、F0を確認してください')
    prior, paths = saved_run.saved({'baseline': config['prior_run']}, [
        'summary.json', 'artifacts/block-128.wav', 'artifacts/upstream-voice.f32',
    ], revision)
    source = next((row for row in saved_run.read(paths[0])['inputs']
                   if row['path'].endswith(f"cases/{base_case.name}")), None)
    if source is None or source['sha256'] != sha256(base_case):
        parser.error('以前の固定母音実行とケースが一致しません')
    inputs = [CASE, Path(__file__).resolve(), base_case, FIXTURE, vowel.PROBE, *paths,
              *shared.candidate_sources(),
              *(Path(module.__file__) for module in (saved_run, pcm, shared, vowel)),
              *(UPSTREAM / key for key in (UPPER_VOICE, UPPER_NETWORK, 'crates/chimera/src/sources/glottis.rs',
                                           'crates/chimera/tests/voice_source.rs', 'crates/chimera/tests/lung_port.rs'))]
    return shared.record_measurement(args.run_id, CASE, inputs, {'case_id': config['id'], 'upstream_revision': revision},
                                     lambda artifacts, execute: measure(config, base, prior, artifacts, execute),
                                     command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
