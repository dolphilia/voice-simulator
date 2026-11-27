"""単一設定を旧値へ戻し、againの再整列境界とF2を照合する。"""

import argparse
import csv
from copy import deepcopy
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_matched_speech_mfa as matched_mfa
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_tsp_fine_variation import DICT, FIELDS, LOCAL
from measure_tsp_seems_drift_only import drift_cents
from measure_tsp_seems_period_jitter import compare_cycles
from measure_tsp_active_duration import read_generated
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_held_out_matched_speech import PLAN_KEYS
from measure_tsp_startup import resting_tip
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-again-initial-tip-mfa.json'
JITTER_CASE = CASE.with_name('tsp-again-period-jitter-mfa.json')
DRIFT_CASE = CASE.with_name('tsp-again-pitch-drift-mfa.json')
SHIMMER_CASE = CASE.with_name('tsp-again-amplitude-shimmer-mfa.json')
MALE_JITTER_CASE = CASE.with_name('tsp-again-male-period-jitter-mfa.json')
MODES = ('matched', 'old_tip')
JITTER_MODES = ('matched', 'jitter_zero')
DRIFT_MODES = ('matched', 'drift_zero')
SHIMMER_MODES = ('matched', 'shimmer_zero')
CLIS = (WORKSPACE / 'target/release/vocal-cli', UPSTREAM / 'target/release/chimera')


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def phone_at_word(tiers, settings):
    matches = [row[:2] for row in tiers['words'] if row[2] == settings['word']]
    if len(matches) != 1:
        raise ValueError('対象語の区間が一つに定まりません')
    start, end = matches[0]
    phones = tiers['phones']
    vowel, following = settings['phones']
    indices = [i for i, (a, b, label) in enumerate(phones[:-1])
               if start <= a < b <= end and label == vowel and phones[i + 1][2] == following
               and phones[i + 1][0] == b and phones[i + 1][1] <= end]
    if len(indices) != 1:
        raise ValueError('対象語の隣接音素と境界が一つに定まりません')
    return indices[0]


def render(case, paths, out, execute, modes):
    cfg = case['measurement']
    vocal, chimera = map(str, CLIS)
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'apical', '--test', 'golden_voice'],
            cwd=UPSTREAM, stdout=out / 'upstream-voice-tests.log')
    if modes != MODES:
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'voice_source'],
                cwd=UPSTREAM, stdout=out / 'upstream-source-tests.log')
    baseline = formants.read(paths['matched_case'])
    voice = baseline['speech_voice']
    matched_tip = voice['posture']['tongue_tip_cm']
    older = formants.read(paths['prior_case'])['speech_voice']
    if baseline['speech_voice']['input'] != older['input'] or voice['input']['id'] != case['utterance']:
        raise ValueError('比較発話が保存済みケースと一致しません')
    adjusted = deepcopy(baseline)
    if modes != MODES:
        cycle = case['cycle']
        variation = voice['source_variation']
        if modes == SHIMMER_MODES:
            field, disabled = 'amplitude_shimmer', case['shimmer']['disabled']
        elif modes == DRIFT_MODES:
            field, disabled = 'pitch_drift_cents', case['drift']['disabled_cents']
        else:
            field, disabled = 'period_jitter', cycle['jitter_inactive']
        if (variation['period_jitter'] != cycle['jitter_active']
            or variation['amplitude_shimmer'] != cycle['amplitude_shimmer']
            or variation['pitch_drift_cents'] != cycle['pitch_drift_cents']
            or older.get('source_variation', {}).get(field, 0) != disabled
            or voice['internal_sample_rate_hz'] != cycle['internal_sample_rate_hz']):
            raise ValueError('音源の対照が旧ケースまたは登録値と一致しません')
        adjusted['speech_voice']['source_variation'][field] = disabled
    else:
        old_tip = older['posture']['tongue_tip_cm']
        if old_tip == matched_tip:
            raise ValueError('介入する舌先の座標に差がありません')
        adjusted['speech_voice']['posture']['tongue_tip_cm'] = old_tip
    first_plan = formants.read(paths['matched_plan'])
    wave_paths = {'upstream': out / 'upstream-clean.wav', 'prior': paths['prior_wav']}
    execute([chimera, 'render', 'text', str(wave_paths['upstream']), voice['input']['text'], voice['body'], '--float'],
            cwd=UPSTREAM)
    postures, plans = {}, {}
    for mode, settings in zip(modes, (baseline, adjusted), strict=True):
        spec = out / f'{mode}-case.json'
        save(spec, settings)
        plan = out / f'{mode}-plan.json'
        execute([vocal, 'inspect', str(spec)], stdout=plan)
        plans[mode] = formants.read(plan)
        wave_paths[mode] = out / f'{mode}-clean.wav'
        execute([vocal, 'render-pcm', str(spec), str(wave_paths[mode]), '--no-trace',
                 str(cfg['output_block_frames'])])
        profile = out / f'{mode}-profile-case.json'
        save(profile, {'speech_voice': settings['speech_voice'] | {
            'tract_profile_frames': cfg['profile_frames'], 'tract_profile_posture': True}})
        trace = out / f'{mode}-posture.csv'
        execute([vocal, 'render', str(profile), str(trace)])
        with trace.open(newline='') as stream:
            postures[mode] = list(csv.DictReader(stream))
        if [int(row['frame']) for row in postures[mode]] != cfg['profile_frames']:
            raise ValueError(f'調音姿勢の観測フレームが登録と一致しません ({mode})')
    coordinates = ['tongue_tip_x_cm', 'tongue_tip_y_cm']
    positions = []
    for left, right in zip(*(postures[mode] for mode in modes), strict=True):
        a, b = ([float(row[key]) for key in coordinates] for row in (left, right))
        positions.append({'frame': int(left['frame']), 'matched_cm': a, 'old_tip_cm': b,
                          'maximum_axis_delta_cm': max(abs(x - y) for x, y in zip(a, b, strict=True))})
    rate = cfg['sample_rate_hz']
    waves = {mode: read_generated(path, rate) for mode, path in wave_paths.items()}
    with np.load(paths['matched_pcm'], allow_pickle=False) as pcm:
        upstream_match = np.array_equal(waves['upstream'].view(np.uint32), pcm[f"{case['utterance']}_upstream"].view(np.uint32))
        reference_pcm = (read_generated(paths['baseline_wav'], rate) if 'baseline_wav' in paths
                         else pcm[f"{case['utterance']}_candidate"])
        known_waves = upstream_match and np.array_equal(waves['matched'].view(np.uint32), reference_pcm.view(np.uint32))
    plan_unchanged = all(plan[key] == first_plan[key] for plan in plans.values() for key in PLAN_KEYS)
    predicted_tip = resting_tip(voice['posture'])
    rest_agrees = max(abs(a - b) for a, b in zip(predicted_tip, matched_tip, strict=True)) <= cfg['tip_coordinate_tolerance_cm']
    return wave_paths, waves, positions, {'matched_pcm_archive': known_waves,
                                         'independent_resting_tip': rest_agrees,
                                         'plan_and_duration_unchanged': plan_unchanged and len({len(w) for w in waves.values()}) == 1}


def align(case, alignment, paths, wave_paths, out, execute, modes):
    cfg, config = case['measurement'], alignment['aligner']
    root = Path(config['environment_root'])
    rate = cfg['sample_rate_hz']
    model, _ = mfa.versions(root, config, out, execute)
    dictionary = out / 'synth.dict'
    shutil.copyfile(paths['dictionary'], dictionary)
    corpus = out / 'corpus'
    derived, noise = {}, {}
    for mode in modes:
        tag = f"{case['utterance']}-{'candidate' if mode == 'matched' else mode}"
        folder = corpus / tag
        folder.mkdir(parents=True)
        shutil.copyfile(paths['lab'], folder / f'{tag}.lab')
        wave = folder / f'{tag}.wav'
        derived[mode] = (tag, wave)
        noise[mode] = mfa.alignment_wav(wave_paths[mode], wave, config, rate)
    target = out / 'aligned'
    with TemporaryDirectory(prefix='again-mfa-', dir=out.parent / 'tmp') as directory:
        mfa.mfa_run(root, config, corpus, dictionary, model, target, Path(directory), execute)
    tiers = {mode: mfa.tiers(target / tag / f'{tag}.json') for mode, (tag, _) in derived.items()}
    tiers['prior'] = mfa.tiers(paths['prior_alignment'])
    control = mfa.tiers(paths['matched_alignment'])
    samples = {mode: matched_mfa.wave_samples(wave, rate, np.int16) for mode, (_, wave) in derived.items()}
    expected = matched_mfa.wave_samples(paths['matched_alignment_wav'], rate, np.int16)
    return tiers, {
        'matched_alignment_archive': np.array_equal(expected, samples['matched']) and tiers['matched'] == control,
        'noise_floor': all(abs(row['noise_ratio_db'] - config['noise_db']) <= alignment['measurement']['noise_tolerance_db']
                           and row['pcm16_clipped_frames'] == 0 for row in noise.values()),
    }, noise, matched_mfa.describe_delta(*(samples[mode] for mode in modes))


def window_comparison(case, formant_case, tiers, wave_paths, paths, out, execute, mode):
    cfg = case['measurement']
    centers = cfg['analysis_centers']
    analysis = formant_case['measurement']
    report = formants.read(paths['formants'])
    indices = {mode: phone_at_word(tier, cfg) for mode, tier in tiers.items()}
    routes = {
        'upstream': ('upstream', 'matched'),
        'matched': ('matched', 'matched'),
        'matched_prior_window': ('matched', 'prior'),
        f'{mode}_fixed_window': (mode, 'matched'),
        f'{mode}_realigned': (mode, mode),
    }
    data = {case['utterance']: {
        'source': {name: {'wave': wave_paths[wave], 'phones': tiers[bound]['phones']}
                   for name, (wave, bound) in routes.items()},
        'tokens': [{name: indices[bound] for name, (_, bound) in routes.items()}],
    }}
    formants.measure_fixed(formant_case, data, centers, out, execute)
    fixed = formants.read(out / 'upstream-formants.json')[case['utterance']]['sources']
    independent = {}
    for name, (wave, bound) in routes.items():
        f32 = read_generated(wave_paths[wave], cfg['sample_rate_hz'])
        signal = formants.analysis_downsample(f32.astype(float), analysis)
        interval = tiers[bound]['phones'][indices[bound]]
        points = []
        for q, native in zip(centers, fixed[name][0]['windows'], strict=True):
            local = formants.window(signal, interval, q, analysis['order'][case['utterance'][0]], analysis)
            delta = formants.max_error(local['f1_f2_hz'], native['f1_f2_hz'])
            points.append({'center': q, 'start_sample': native['start_sample'],
                           'missing_reason': native['reason'], 'f1_f2_hz': native['f1_f2_hz'],
                           'independent_error_hz': delta,
                           'agrees': local['start_sample'] == native['start_sample'] and local['reason'] == native['reason']
                           and delta is not None and delta <= analysis['frequency_bandwidth_agreement_hz']})
        independent[name] = points
    prepared = [row for row in report['windows'] if row['utterance'] == case['utterance']
                and row['word'] == cfg['word'] and row['source'] == 'upstream']
    matched_rows = [(row['center'], row['start_sample'], row['f2_hz']) for row in prepared]
    repeated = [(row['center'], row['start_sample'], row['f1_f2_hz'][1] if row['f1_f2_hz'] is not None else None)
                for row in independent['upstream']]
    conditions = {'existing_centers_and_reference_windows': (
        cfg['analysis_rate_hz'] == report['sample_rate_hz'] and cfg['frame_samples'] == report['frame_samples']
        and centers == sorted(analysis['reference_centers'] + analysis['boundary_centers']) and matched_rows == repeated),
        'fixed_and_independent_formants_agree': all(row['agrees'] for rows in independent.values() for row in rows)}
    return indices, independent, conditions


def source_observations(case, paths, waves, out, execute, modes):
    cycle = case['cycle']
    factor = cycle['internal_sample_rate_hz'] // case['measurement']['sample_rate_hz']
    signals, amplitudes, matches = {}, {}, {}
    with TemporaryDirectory(prefix='again-source-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        dictionary = scratch / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        probe = build_upstream_probe(LOCAL, scratch, execute, upstream=WORKSPACE, package='vocal-core',
                                     lto='off', extra_libraries=('serde_json',), cargo_args=('--offline',))
        for mode in modes:
            state, pcm, output, amplitude = (scratch / f'{mode}-{name}' for name in
                                             ('state.f64', 'pcm.f32', 'output.f64', 'amplitude.f64'))
            frames = len(waves[mode])
            execute([str(probe), str(paths[mode]), str(dictionary), str(frames), str(cycle['initial_f0_hz']),
                     str(cycle['base_f0_hz']), *map(str, (state, pcm, output, amplitude))])
            raw = np.fromfile(state, dtype='<f8').reshape(-1, len(FIELDS))
            observed = np.fromfile(pcm, dtype='<f4')
            scales = np.fromfile(amplitude, dtype='<f8')
            if (len(raw) != frames * factor or len(scales) != len(raw)
                or any(not np.isfinite(a).all() for a in (raw, observed, scales))):
                raise ValueError(f'声門の観測範囲が登録値と一致しません ({mode})')
            matches[mode] = np.array_equal(observed.view(np.uint32), waves[mode].view(np.uint32))
            signals[mode] = (dict(zip(FIELDS, raw.T, strict=True)), None, observed)
            amplitudes[mode] = scales
    parameters = {mode: formants.read(paths[mode])['speech_voice']['source_variation'] for mode in modes}
    checks, independent, stages = compare_cycles(
        case, cycle, signals, {}, amplitudes, out,
        pairs={'research': modes},
        parameters=lambda _, mode: (parameters[mode]['period_jitter'], parameters[mode]['amplitude_shimmer']))
    return checks | {'internal_observer_pcm_matches_cli': all(matches.values())}, independent, stages['research']


def check_pitch_ratio(case, out):
    with np.load(out / 'cycle-traces.npz', allow_pickle=False) as trace:
        active, disabled = (trace[f'{mode}_f0_hz'] for mode in DRIFT_MODES)
    if np.any(active <= 0) or np.any(disabled <= 0):
        raise ValueError('ドリフトの比較に正の瞬時F0が必要です')
    settings = case['drift']
    measured = 1200 * np.log2(active / disabled)
    expected = drift_cents(settings, case['cycle']['internal_sample_rate_hz'], len(measured))
    delta = abs(measured - expected)
    step = settings['control_interval_samples']
    np.savez_compressed(out / 'pitch-ratio.npz', sample=np.arange(0, len(measured), step),
                        observed_cents=measured[::step], independent_cents=expected[::step])
    return {'internal_samples': len(measured), 'first_cents': float(measured[0]),
            'range_cents': [float(measured.min()), float(measured.max())],
            'maximum_error_cents': float(delta.max())}


def shimmer_amplitudes(out):
    with np.load(out / 'cycle-traces.npz', allow_pickle=False) as trace:
        active, disabled = (trace[f'{mode}_amplitude'] for mode in SHIMMER_MODES)
    changed = np.flatnonzero(active != disabled)
    first = int(changed[0]) if len(changed) else None
    return {'first_changed_internal_sample': first,
            'values_at_first_change': None if first is None else [float(active[first]), float(disabled[first])],
            'active_range': [float(active.min()), float(active.max())],
            'disabled_range': [float(disabled.min()), float(disabled.max())]}


def compare_source(case, waves, out, execute, pcm, boundary, comparison, modes):
    paths = {mode: out / f'{mode}-case.json' for mode in modes}
    checks, independent, stages = source_observations(case, paths, waves, out, execute, modes)
    fixed = comparison[f'{modes[1]}_fixed_window']
    baseline = comparison['matched']
    f2_differences = [
        None if left['f1_f2_hz'] is None or right['f1_f2_hz'] is None else right['f1_f2_hz'][1] - left['f1_f2_hz'][1]
        for left, right in zip(baseline, fixed, strict=True)]
    first = stages['first_different_internal_sample']
    limits = case['limits']
    diagnostics = {'independent_cycles': independent, 'first_changes': stages,
                   'fixed_window_f2_differences_hz': f2_differences}
    if modes == SHIMMER_MODES:
        amplitudes = shimmer_amplitudes(out)
        diagnostics['cycle_amplitude'] = amplitudes
        onset = {'shimmer_starts_at_first_boundary': (
            stages['first_boundary'] is not None and amplitudes['first_changed_internal_sample'] == stages['first_boundary']
            and first['f0_hz'] is None and first['phase'] is None and stages['max_boundary_shift_samples'] == 0)}
    elif modes == DRIFT_MODES:
        ratio = check_pitch_ratio(case, out)
        diagnostics['pitch_ratio'] = ratio
        checks['independent_pitch_ratio_agrees'] = ratio['maximum_error_cents'] <= limits['pitch_ratio_agreement_cents']
        onset = {'drift_changes_f0_and_phase_at_first_sample': first['f0_hz'] == first['phase'] == 0
                 and stages['matched_cycle_amplitude']}
    else:
        onset = {'jitter_changes_phase_after_first_wrap': first['f0_hz'] is None and stages['matched_cycle_amplitude']
                 and stages['first_boundary'] is not None and first['phase'] == stages['first_boundary'] + 1}
    predictions = {
        **onset,
        'fixed_window_f2_changes': pcm['near_boundary']['changed_frames'] > 0
            and any(delta is not None and abs(delta) >= limits['meaningful_fixed_window_f2_hz'] for delta in f2_differences),
    }
    prediction = 'boundary_stays_at_drift_zero_control' if modes == SHIMMER_MODES else 'boundary_shift_at_most_one_mfa_step'
    predictions[prediction] = abs(boundary[modes[1]] - boundary['matched']) <= limits['maximum_predicted_boundary_shift_s']
    return checks, predictions, diagnostics


def measure(case, align_case, analysis_case, paths, out, execute):
    cfg = case['measurement']
    if 'shimmer' in case:
        modes = SHIMMER_MODES
    elif 'drift' in case:
        modes = DRIFT_MODES
    else:
        modes = JITTER_MODES if 'cycle' in case else MODES
    wave_paths, waves, posture, checks = render(case, paths, out, execute, modes)
    tiers, align_checks, noise, mfa_pcm = align(case, align_case, paths, wave_paths, out, execute, modes)
    indices, comparison, window_checks = window_comparison(case, analysis_case, tiers, wave_paths, paths, out, execute, modes[1])
    left, right = (waves[mode] for mode in modes)
    begin, end = cfg['late_pcm_region']
    pcm = {'all': matched_mfa.describe_delta(left, right),
           'preroll': matched_mfa.describe_delta(left[:cfg['initial_frames']], right[:cfg['initial_frames']]),
           'near_boundary': matched_mfa.describe_delta(left[begin:end], right[begin:end])}
    boundary = {mode: tier['phones'][indices[mode]][1] for mode, tier in tiers.items()}
    starts = {name: rows[-1]['start_sample'] for name, rows in comparison.items()}
    checks |= align_checks | window_checks | {'old_boundary_is_reproduced_from_archive':
        boundary['matched'] == cfg['expected_matched_end_seconds']
        and boundary['prior'] == cfg['expected_previous_end_seconds']
        and starts['matched_prior_window'] - starts['matched'] == cfg['expected_previous_90_percent_offset_samples']}
    if modes != MODES:
        observed, predictions, diagnostics = compare_source(case, waves, out, execute, pcm, boundary, comparison, modes)
        checks.update(observed)
        if 'baseline_intervention' in case:
            diagnostics['alignment_vs_control'] = matched_mfa.compare_intervals(tiers['matched'], tiers[modes[1]])
            diagnostics['alignment_vs_old'] = matched_mfa.compare_intervals(tiers['prior'], tiers[modes[1]])
            diagnostics['old_window_starts_recreated'] = sum(
                old['start_sample'] == new['start_sample']
                for old, new in zip(comparison['matched_prior_window'], comparison[f'{modes[1]}_realigned'], strict=True))
    else:
        diagnostics = {}
        predictions = {
            'preroll_waveform_changes': pcm['preroll']['max_absolute_delta'] > cfg['early_pcm_difference_minimum'],
            'late_tip_returns_to_matched_position': all(row['maximum_axis_delta_cm'] <= cfg['maximum_late_tip_difference_cm']
                                                        for row in posture[-2:]),
            'old_tip_keeps_matched_boundary_and_last_window': (boundary['old_tip'] == boundary['matched']
                                                              and starts['old_tip_realigned'] == starts['matched']),
        }
    save(out / 'window-comparisons.json', comparison)
    return {'checks': checks, 'predictions': predictions, 'eh1_end_seconds': boundary,
            'last_window_start_12khz': starts, 'pcm': pcm, 'posture': posture, 'mfa_pcm': mfa_pcm, 'noise': noise,
            'phone_indices': indices, **diagnostics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=lambda value: Path(value).resolve(),
                        choices=(CASE, JITTER_CASE, DRIFT_CASE, SHIMMER_CASE, MALE_JITTER_CASE), default=CASE)
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(args.case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    prior, matched, prior_align, matched_align, report = (formants.open_run(case[key], revision) for key in
        ('previous_render', 'matched_render', 'previous_alignment', 'matched_alignment', 'formants'))
    align_case, align_snapshot = saved_case(prior_align, CASE.with_name(f"{case['previous_alignment']['case']}.json"))
    report_case, report_snapshot = saved_case(report, CASE.with_name(f"{case['formants']['case']}.json"))
    f2_run = formants.open_run(report_case['reference'], revision)
    analysis_case, analysis_snapshot = saved_case(f2_run, formants.CASE)
    uid = case['utterance']
    tag = f'{uid}-candidate'
    paths = {key: formants.verified_path(run, 'artifacts/' + path) for key, run, path in (
        ('prior_case', prior, f'{uid}/candidate.json'), ('prior_wav', prior, f'{uid}/candidate.wav'),
        ('matched_case', matched, f'{uid}/matched-case.json'), ('matched_plan', matched, f'{uid}/matched-plan.json'),
        ('matched_pcm', matched, 'matched-pcm.npz'), ('dictionary', matched_align, 'synth.dict'),
        ('lab', matched_align, f'corpus/{tag}/{tag}.lab'), ('matched_alignment_wav', matched_align, f'corpus/{tag}/{tag}.wav'),
        ('matched_alignment', matched_align, f'aligned/{tag}/{tag}.json'),
        ('prior_alignment', prior_align, f'aligned-1-synth/{tag}/{tag}.json'),
        ('formants', report, 'f2-candidates.json'))}
    baseline_inputs = []
    if spec := case.get('baseline_intervention'):
        baseline = formants.open_run(spec, revision)
        drift_tag = f'{uid}-drift_zero'
        files = spec.get('outputs', {
            'matched_case': f'{uid}/drift_zero.json', 'baseline_wav': f'{uid}/drift_zero.wav',
            'matched_alignment_wav': f'corpus/{drift_tag}/{drift_tag}.wav',
            'matched_alignment': f'aligned/{drift_tag}/{drift_tag}.json',
        })
        paths.update({key: formants.verified_path(baseline, 'artifacts/' + path) for key, path in files.items()})
        baseline_inputs.append(baseline[0] / 'manifest.json')
    source_files = ('crates/chimera/src/anatomy/human.rs', 'crates/chimera/src/control/articulators.rs',
                    'crates/chimera/src/voice/human_voice.rs', 'crates/chimera-cli/src/render.rs', formants.TSP_SOURCE,
                    'crates/chimera/tests/golden_voice.rs', 'crates/chimera/tests/apical.rs',
                    'crates/chimera-cli/src/main.rs', 'crates/chimera/src/analysis/lpc.rs', 'tools/tsp/mfa.yaml')
    inputs = [args.case, Path(__file__).resolve(), align_snapshot, report_snapshot, analysis_snapshot, *paths.values(), *baseline_inputs,
              *(run[0] / 'manifest.json' for run in (prior, matched, prior_align, matched_align, report, f2_run)),
              *(UPSTREAM / name for name in source_files), formants.PROBE, *candidate_sources(),
              *(WORKSPACE / 'tools' / name for name in ('measure_tsp_matched_speech_mfa.py', 'measure_tsp_phone_boundaries.py',
                  'measure_tsp_startup.py', 'measure_tsp_stressed_vowel_formants.py', 'measure_tsp_held_out_matched_speech.py'))]
    if 'cycle' in case:
        inputs.extend((LOCAL, DICT, LOCAL.with_name('tsp_fine_trace.rs'),
                       *(WORKSPACE / 'tools' / name for name in ('measure_tsp_fine_variation.py',
                           'measure_tsp_seems_period_jitter.py', 'measure_tsp_seems_drift_only.py')),
                       *(UPSTREAM / name for name in ('crates/chimera/src/sources/glottis.rs',
                           'crates/chimera/src/math.rs', 'crates/chimera/tests/voice_source.rs'))))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'aligner': align_case['aligner']}
    return record_measurement(args.run_id, args.case, inputs, details, lambda out, execute: measure(
        case, align_case, analysis_case, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
