"""FK61_02の出力ゲインを旧値へ戻し、出力段とtallの整列境界を照合する。"""

import argparse
import gzip
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_again_initial_tip_mfa as single
import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_duet_child_output_gain import COLUMNS, independent_stages, trace_input
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_variation import DICT, LOCAL
from measure_tsp_held_out_matched_speech import PLAN_KEYS
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-tall-output-gain-mfa.json'
MODES = ('matched', 'old_gain')
ROUTES = {
    'matched': ('matched', 'matched'),
    'old_gain_fixed_window': ('old_gain', 'matched'),
    'old_gain_realigned': ('old_gain', 'old_gain'),
    'prior_render': ('prior', 'prior'),
}


def render_gain_pair(case, paths, out, execute):
    cli = str(WORKSPACE / 'target/release/vocal-cli')
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_voice'],
            cwd=UPSTREAM, stdout=out / 'upstream-golden-voice.log')
    control = formants.read(paths['matched_case'])['speech_voice']
    historical = formants.read(paths['prior_case'])['speech_voice']
    if (control['input'] != historical['input'] or control['input']['id'] != case['utterance']
            or any(control['source_variation'].values())
            or control['voice']['output_gain'] != case['base_gain']
            or historical['voice']['output_gain'] != case['old_gain']):
        raise ValueError('登録した発話、音源またはゲインが保存ケースと一致しません')
    altered = control | {'voice': control['voice'] | {'output_gain': case['old_gain']}}
    rates = case['sample_rate_hz'], case['internal_sample_rate_hz']
    waves, audio, plans, traces = {'prior': paths['prior_wav']}, {}, {}, {}
    verified = {}
    with TemporaryDirectory(prefix='tall-gain-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        probe = build_upstream_probe(LOCAL, scratch, execute, upstream=WORKSPACE, package='vocal-core',
                                     lto='off', extra_libraries=('serde_json',), cargo_args=('--offline',))
        for mode, voice in zip(MODES, (control, altered), strict=True):
            spec = out / f'{mode}-case.json'
            single.save(spec, {'speech_voice': voice})
            plan = out / f'{mode}-plan.json'
            execute([cli, 'inspect', str(spec)], stdout=plan)
            plans[mode] = formants.read(plan)
            waves[mode] = out / f'{mode}-clean.wav'
            execute([cli, 'render-pcm', str(spec), str(waves[mode]), '--no-trace', '128'])
            audio[mode] = aligned.wave_samples(waves[mode], rates[0], np.float32)
            state, probe_pcm, trace = (scratch / f'{mode}-{name}' for name in ('state.f64', 'pcm.f32', 'output.f64'))
            frames = len(audio[mode])
            execute([str(probe), str(spec), str(dictionary), str(frames), str(case['initial_f0_hz']),
                     str(case['base_f0_hz']), str(state), str(probe_pcm), str(trace)])
            verified[mode] = np.array_equal(np.fromfile(probe_pcm, dtype='<u4'), audio[mode].view(np.uint32))
            traces[mode] = trace_input(trace, frames)
    audio['prior'] = aligned.wave_samples(paths['prior_wav'], rates[0], np.float32)
    reference = formants.read(paths['matched_plan'])
    original = aligned.wave_samples(paths['matched_clean'], rates[0], np.float32)
    checks = {
        'usual_pcm_matches_observed_pcm': all(verified.values()),
        'archived_matched_pcm_reproduced': np.array_equal(original.view(np.uint32), audio['matched'].view(np.uint32)),
        'plan_unchanged': all(plan[key] == reference[key] for plan in plans.values() for key in PLAN_KEYS),
    }
    return waves, audio, traces, checks


def output_comparison(case, audio, traces, out):
    gain = {'matched': case['base_gain'], 'old_gain': case['old_gain']}
    stage = {mode: independent_stages(traces[mode], audio[mode], gain[mode], case) for mode in MODES}
    left, right = (traces[mode] for mode in MODES)
    observations = {}
    for index, name in enumerate(COLUMNS):
        delta = right[:, index] - left[:, index]
        changed = np.flatnonzero(delta)
        observations[name] = {'first_different_frame': int(changed[0]) if len(changed) else None,
                              'maximum_absolute_delta': float(np.max(np.abs(delta)))}
    factor = gain['old_gain'] / gain['matched']
    scaled = (audio['matched'].astype(float) * factor).astype(np.float32)
    begin, end = case['measurement']['local_frames']
    wave_comparison = {
        'gain_ratio': factor,
        'gain_change': aligned.describe_delta(audio['matched'], audio['old_gain']),
        'scaled_to_old_gain': aligned.describe_delta(scaled, audio['old_gain']),
        'old_gain_to_old_render': aligned.describe_delta(audio['old_gain'], audio['prior']),
        'old_gain_to_old_render_near_tall': aligned.describe_delta(audio['old_gain'][begin:end], audio['prior'][begin:end]),
    }
    # 一致する間引き出力は一系列だけ保存し、ゲイン以降の独立計算に使う。
    np.savez_compressed(out / 'decimated.npz', decimated=left[:, COLUMNS.index('decimated')])
    limit = case['measurement']['output_tolerance']
    checks = {
        'radiation_and_decimation_unchanged': all(observations[name]['first_different_frame'] is None
                                                  for name in COLUMNS[:3]),
        'gain_only_output_matches_independent': all(stats['pcm_matches_independent_limiter']
            and stats['hold_error_frames'] == 0 and all(stats[key] <= limit for key in
                ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error'))
            for stats in stage.values()),
    }
    predictions = {'gain_is_linear_without_limiting': (
        all(not metrics['peak_limited_frames'] and not metrics['soft_clipped_frames'] for metrics in stage.values())
        and wave_comparison['scaled_to_old_gain']['max_absolute_delta'] <= case['measurement']['linear_pcm_absolute_tolerance'])}
    return stage, observations, wave_comparison, checks, predictions


def measure_formants(case, analysis_case, waves, tiers, indices, out, execute, *, routes=ROUTES):
    cfg = analysis_case['measurement']
    centers = case['measurement']['analysis_centers']
    if centers != sorted(cfg['boundary_centers'] + cfg['reference_centers']):
        raise ValueError('解析窓の中心が固定比較と一致しません')
    uid = case['utterance']
    layout = {uid: {
        'source': {name: {'wave': waves[wave], 'phones': tiers[bounds]['phones']} for name, (wave, bounds) in routes.items()},
        'tokens': [{name: indices[bounds] for name, (_, bounds) in routes.items()}],
    }}
    native, _ = formants.measure_fixed(analysis_case, layout, centers, out, execute)
    signals = {mode: formants.filtered_wave(wave, mode, cfg) for mode, wave in waves.items()}
    rows = {}
    for name, (wave, bounds) in routes.items():
        values = []
        for q, fixed in zip(centers, native[uid]['sources'][name][0]['windows'], strict=True):
            local = formants.window(signals[wave], tiers[bounds]['phones'][indices[bounds]], q, cfg['order']['F'], cfg)
            error = formants.max_error(local['f1_f2_hz'], fixed['f1_f2_hz'])
            values.append({'center': q, 'start_sample': fixed['start_sample'], 'f1_f2_hz': fixed['f1_f2_hz'],
                           'reason': fixed['reason'], 'independent_error_hz': error, 'agrees':
                fixed['start_sample'] == local['start_sample'] and fixed['reason'] == local['reason']
                and error is not None and error <= cfg['frequency_bandwidth_agreement_hz']})
        rows[name] = values
    single.save(out / 'window-comparisons.json', rows)
    return rows


def measure(case, alignment, analysis_case, paths, out, execute):
    waves, audio, traces, checks = render_gain_pair(case, paths, out, execute)
    stage, observations, wave_comparison, independent_checks, predictions = output_comparison(case, audio, traces, out)
    cfg = case['measurement']
    alignment_case = case | {'measurement': cfg | {'sample_rate_hz': case['sample_rate_hz']}}
    tiers, align_checks, noise, mfa_pcm = single.align(alignment_case, alignment, paths, waves, out, execute, MODES)
    indices = {mode: single.phone_at_word(tier, cfg) for mode, tier in tiers.items()}
    boundaries = {mode: tier['phones'][indices[mode]][1] for mode, tier in tiers.items()}
    rows = measure_formants(case, analysis_case, waves, tiers, indices, out, execute)
    deltas = [None if left['f1_f2_hz'] is None or right['f1_f2_hz'] is None else right['f1_f2_hz'][1] - left['f1_f2_hz'][1]
              for left, right in zip(rows['matched'], rows['old_gain_fixed_window'], strict=True)]
    checks |= independent_checks | align_checks | {
        'registered_boundary_endpoints': (boundaries['matched'] == cfg['baseline_end_seconds']
                                          and boundaries['prior'] == cfg['old_end_seconds']),
        'fixed_and_independent_formants_agree': all(item['agrees'] for values in rows.values() for item in values),
    }
    predictions['fixed_window_f2_stays'] = all(value is not None and abs(value) <= cfg['fixed_window_f2_tolerance_hz']
                                               for value in deltas)
    predictions['old_tall_boundary_recreated'] = boundaries['old_gain'] == boundaries['prior']
    return {'checks': checks, 'predictions': predictions, 'tall_vowel_end_seconds': boundaries,
            'alignment_vs_control': aligned.compare_intervals(tiers['matched'], tiers['old_gain']),
            'alignment_vs_old': aligned.compare_intervals(tiers['prior'], tiers['old_gain']),
            'fixed_window_f2_differences_hz': deltas, 'output_stage': stage, 'first_output_differences': observations,
            'pcm': wave_comparison, 'mfa_pcm': mfa_pcm, 'noise': noise}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    baseline, prior, archive, formant_run = (formants.open_run(case[key], revision) for key in
                                             ('baseline', 'previous_render', 'previous_alignment', 'formants'))
    legacy, legacy_snapshot = saved_case(archive, CASE.with_name(f"{case['previous_alignment']['case']}.json"))
    analysis, analysis_snapshot = saved_case(formant_run, formants.CASE)
    uid = case['utterance']
    tag = f'{uid}-variation_zero'
    paths = {name: formants.verified_path(run, 'artifacts/' + path) for name, run, path in (
        ('matched_case', baseline, f'{uid}/variation_zero.json'), ('matched_plan', baseline, f'{uid}/variation_zero.plan.json'),
        ('matched_clean', baseline, f'{uid}/variation_zero.wav'), ('dictionary', baseline, 'synth.dict'),
        ('lab', baseline, f'corpus/{tag}/{tag}.lab'), ('matched_alignment_wav', baseline, f'corpus/{tag}/{tag}.wav'),
        ('matched_alignment', baseline, f'aligned/{tag}/{tag}.json'),
        ('prior_case', prior, f'{uid}/candidate.json'), ('prior_wav', prior, f'{uid}/candidate.wav'),
        ('prior_alignment', archive, f'aligned-1-synth/{uid}-candidate/{uid}-candidate.json'))}
    inputs = [CASE, Path(__file__).resolve(), legacy_snapshot, analysis_snapshot, *paths.values(), *candidate_sources(),
              *(run[0] / 'manifest.json' for run in (baseline, prior, archive, formant_run)),
              LOCAL, LOCAL.with_name('tsp_fine_trace.rs'), DICT, formants.PROBE,
              *(WORKSPACE / 'tools' / name for name in ('measure_duet_child_output_gain.py', 'measure_tsp_again_initial_tip_mfa.py',
                  'measure_tsp_matched_speech_mfa.py', 'measure_tsp_phone_boundaries.py', 'measure_tsp_stressed_vowel_formants.py')),
              *(UPSTREAM / name for name in (formants.TSP_SOURCE, 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera/src/analysis/lpc.rs', 'crates/chimera/tests/golden_voice.rs', 'tools/tsp/mfa.yaml'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': legacy['aligner']}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(
        case, legacy, analysis, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
