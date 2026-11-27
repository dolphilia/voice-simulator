"""確認用4発話で、音源変動の設定による整列窓の変化を照合する。"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_matched_speech_mfa as aligned
import measure_tsp_phone_boundaries as mfa
import measure_tsp_stressed_vowel_formants as formants
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_held_out_matched_speech import PLAN_KEYS
from measure_tsp_seems_drift_only import drift_cents
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-matched-pitch-drift-mfa.json'
VARIATION_CASE = CASE.with_name('tsp-matched-source-variation-zero-mfa.json')
ROUTES = {
    'matched': ('matched', 'matched'),
    'matched_old_window': ('matched', 'old'),
    'drift_zero_fixed_window': ('drift_zero', 'matched'),
    'drift_zero_realigned': ('drift_zero', 'drift_zero'),
}


def variant_name(case):
    return 'variation_zero' if 'variation' in case else 'drift_zero'


def comparison_routes(variant):
    if variant == 'drift_zero':
        return ROUTES
    return {'matched': ('matched', 'matched'), 'matched_old_window': ('matched', 'old'),
            f'{variant}_fixed_window': (variant, 'matched'), f'{variant}_realigned': (variant, variant),
            'old_render': ('old_render', 'old')}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def read_f0(path, frames):
    with path.open() as stream:
        header = stream.readline().strip().split(',')
        values = np.loadtxt(stream, delimiter=',', usecols=(header.index('frame'), header.index('glottal_f0_hz')))
    if not np.array_equal(values[:, 0], np.arange(frames)) or not np.isfinite(values).all() or np.any(values[:, 1] <= 0):
        raise ValueError('出力フレームのF0観測が所定の形式と一致しません')
    return values[:, 1]


def render_pair(case, uid, paths, single, out, scratch, pcm, execute):
    directory = out / uid
    directory.mkdir()
    cli = str(WORKSPACE / 'target/release/vocal-cli')
    baseline = formants.read(paths['case'])['speech_voice']
    variation = baseline['source_variation']
    settings = single['drift']
    cycle = single['cycle']
    rate = single['measurement']['sample_rate_hz']
    if (baseline['input']['id'] != uid or baseline['internal_sample_rate_hz'] != cycle['internal_sample_rate_hz']
            or variation != {'pitch_drift_cents': settings['default_cents'], 'period_jitter': cycle['jitter_active'],
                             'amplitude_shimmer': cycle['amplitude_shimmer']}):
        raise ValueError(f'基準の発話IDまたは音源設定が登録と一致しません ({uid})')
    variant = variant_name(case)
    changes = case.get('variation', {'pitch_drift_cents': settings['disabled_cents']})
    variants = {
        'matched': baseline,
        variant: baseline | {'source_variation': variation | changes},
    }
    waves, f0, plans, audio = {}, {}, {}, {}
    reference = formants.read(paths['plan'])
    for mode, voice in variants.items():
        spec, plan, wave = (directory / f'{mode}.{ext}' for ext in ('json', 'plan.json', 'wav'))
        save(spec, {'speech_voice': voice})
        execute([cli, 'inspect', str(spec)], stdout=plan)
        plans[mode] = formants.read(plan)
        execute([cli, 'render-pcm', str(spec), str(wave), '--no-trace', str(single['measurement']['output_block_frames'])])
        waves[mode] = wave
        audio[mode] = aligned.wave_samples(wave, rate, np.float32)
        trace = scratch / f'{uid}-{mode}.csv'
        execute([cli, 'render', str(spec), str(trace)])
        f0[mode] = read_f0(trace, len(audio[mode]))
        trace.unlink()
    baseline_bits = pcm[f'{uid}_candidate'].view(np.uint32)
    factor = cycle['internal_sample_rate_hz'] // rate
    frames = len(f0['matched'])
    measured = 1200 * np.log2(f0['matched'] / f0[variant])
    expected = drift_cents(settings, cycle['internal_sample_rate_hz'], frames * factor)[factor - 1::factor]
    metrics = {'frames': frames, 'first_difference_frame': int(np.flatnonzero(measured)[0]) if measured.any() else None,
               'range_cents': [float(measured.min()), float(measured.max())],
               'maximum_error_cents': float(np.max(abs(measured - expected))),
               'pcm_difference': aligned.describe_delta(audio['matched'], audio[variant])}
    trace = np.column_stack((np.arange(frames), measured, expected))[::settings['control_interval_samples'] // factor]
    checks = {'matched_pcm': np.array_equal(audio['matched'].view(np.uint32), baseline_bits),
              'plans_match': all(plan[key] == reference[key] for plan in plans.values() for key in PLAN_KEYS),
              'independent_f0_ratio': metrics['maximum_error_cents'] <= single['limits']['pitch_ratio_agreement_cents']}
    return waves, metrics, trace, checks


def align_pairs(case, legacy_case, paths, waves, out, scratch, execute):
    config = legacy_case['aligner']
    root = Path(config['environment_root'])
    model, _ = mfa.versions(root, config, out, execute)
    corpus = out / 'corpus'
    dictionary = out / 'synth.dict'
    shutil.copyfile(paths['dictionary'], dictionary)
    tags, noise, same_inputs = {}, {}, {}
    rate = legacy_case['measurement']['sample_rate_hz']
    for uid in case['utterances']:
        tags[uid], noise[uid] = {}, {}
        for mode in ('matched', variant_name(case)):
            tag = f"{uid}-{'candidate' if mode == 'matched' else mode}"
            folder = corpus / tag
            folder.mkdir(parents=True)
            tags[uid][mode] = tag
            shutil.copyfile(paths['utterances'][uid]['lab'], folder / f'{tag}.lab')
            wave = folder / f'{tag}.wav'
            noise[uid][mode] = mfa.alignment_wav(waves[uid][mode], wave, config, rate)
            if mode == 'matched':
                same_inputs[uid] = sha256(wave) == sha256(paths['utterances'][uid]['matched_tape'])
    result = out / 'aligned'
    temp = scratch / 'mfa'
    temp.mkdir()
    mfa.mfa_run(root, config, corpus, dictionary, model, result, temp, execute)
    observed, controls = {}, {}
    for uid, modes in tags.items():
        old = paths['utterances'][uid]
        observed[uid] = {mode: mfa.tiers(result / tag / f'{tag}.json') for mode, tag in modes.items()}
        observed[uid]['old'] = mfa.tiers(old['old_alignment'])
        controls[uid] = same_inputs[uid] and observed[uid]['matched'] == mfa.tiers(old['matched_alignment'])
    return observed, noise, controls


def window_starts(case, registered, observed):
    cfg = case['measurement']
    rows = []
    for row in registered:
        uid, index, q = row['utterance'], row['phone_index'], row['center']
        if uid not in case['utterances'] or q not in cfg['centers']:
            raise ValueError(f'母音窓が事前登録の範囲外です ({uid})')
        starts = {}
        labels = [item[2] for item in observed[uid]['matched']['phones']]
        for mode, tiers in observed[uid].items():
            phones = tiers['phones']
            if [item[2] for item in phones] != labels:
                raise ValueError(f'音素のラベル列を対応付けられません ({uid}/{mode})')
            a, b, _ = phones[index]
            starts[mode] = int((a + q * (b - a)) * cfg['analysis_sample_rate_hz']) - cfg['frame_samples'] // 2
        if (starts['matched'] != row['candidate']['start_samples'][1]
                or starts['old'] != row['candidate']['start_samples'][0]):
            raise ValueError(f'保存済みの窓開始位置を再現できません ({uid}/{index}/{q})')
        rows.append({'utterance': uid, 'phone_index': index, 'word': row['word'], 'ipa': row['ipa'], 'center': q,
                     'start_samples': starts})
    return rows


def summarize_windows(rows, variant='drift_zero'):
    old_changed = [r for r in rows if r['start_samples']['old'] != r['start_samples']['matched']]
    changed = [r for r in rows if r['start_samples'][variant] != r['start_samples']['matched']]
    key = 'drift_changed_starts' if variant == 'drift_zero' else 'variation_zero_changed_starts'
    return {'windows': len(rows), 'old_changed_starts': len(old_changed), key: len(changed),
            'recreated_old_changes': sum(r['start_samples'][variant] == r['start_samples']['old'] for r in old_changed),
            'new_changes': sum(r['start_samples']['old'] == r['start_samples']['matched'] for r in changed)}


def window_formants(case, analysis_case, waves, observed, rows, out, execute):
    cfg = case['measurement']
    analysis = analysis_case['measurement']
    centers = cfg['centers']
    rate = analysis['sample_rate_hz'] // analysis['decimation']
    if (centers != sorted(analysis['reference_centers'] + analysis['boundary_centers'])
            or rate != cfg['analysis_sample_rate_hz'] or int(rate * analysis['frame_seconds']) != cfg['frame_samples']):
        raise ValueError('LPCの窓の登録値が元の計測と一致しません')
    layout, source = {}, {}
    routes = comparison_routes(variant_name(case))
    for uid, conditions in waves.items():
        indices = sorted({row['phone_index'] for row in rows if row['utterance'] == uid})
        layout[uid] = {
            'source': {name: {'wave': conditions[wave], 'phones': observed[uid][bounds]['phones']}
                       for name, (wave, bounds) in routes.items()},
            'tokens': [dict.fromkeys(routes, index) for index in indices],
        }
        source[uid] = {mode: formants.filtered_wave(path, mode, analysis) for mode, path in conditions.items()}
    native, _ = formants.measure_fixed(analysis_case, layout, centers, out, execute)
    indexed = {uid: {name: {entry['index']: dict(zip(centers, entry['windows'], strict=True)) for entry in entries}
                     for name, entries in native[uid]['sources'].items()} for uid in waves}
    for row in rows:
        uid, index, q = row['utterance'], row['phone_index'], row['center']
        row['f2_hz'], row['independent'] = {}, {}
        for name, (mode, bounds) in routes.items():
            fixed = indexed[uid][name][index][q]
            interval = observed[uid][bounds]['phones'][index]
            independent = formants.window(source[uid][mode], interval, q, analysis['order'][uid[0]], analysis)
            error = formants.max_error(independent['f1_f2_hz'], fixed['f1_f2_hz'])
            value = fixed['f1_f2_hz']
            row['f2_hz'][name] = None if value is None else value[1]
            row['independent'][name] = {'error_hz': error, 'reason': fixed['reason'], 'agrees':
                fixed['start_sample'] == row['start_samples'][bounds] == independent['start_sample']
                and fixed['reason'] == independent['reason'] and error is not None
                and error <= analysis['frequency_bandwidth_agreement_hz']}


def outside_boundary(case, observed, drift_alignment):
    cfg = case['outside_window_boundary']
    tiers_by_mode = observed[cfg['utterance']] | {'drift_only': mfa.tiers(drift_alignment)}
    values = {}
    for mode, tiers in tiers_by_mode.items():
        times = {}
        for kind in ('words', 'phones'):
            intervals = tiers[kind]
            boundaries = [[left[1], right[0]] for left, right in zip(intervals, intervals[1:])
                          if [left[2], right[2]] == cfg[kind]]
            if len(boundaries) != 1:
                raise ValueError(f'評価窓外の境界が一つに定まりません ({kind}/{mode})')
            times[kind] = boundaries[0]
        values[mode] = times
    return values


def measure(case, single, legacy, analysis, paths, out, execute):
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    waves, ratio, traces, checks_by_uid = {}, {}, {}, {}
    with (TemporaryDirectory(prefix='cohort-drift-', dir=out.parent / 'tmp') as directory,
          np.load(paths['pcm'], allow_pickle=False) as pcm):
        scratch = Path(directory)
        for uid, entry in paths['utterances'].items():
            waves[uid], ratio[uid], traces[uid], checks_by_uid[uid] = render_pair(
                case, uid, entry, single, out, scratch, pcm, execute)
        observed, noise, controls = align_pairs(case, legacy, paths, waves, out, scratch, execute)
    variant = variant_name(case)
    if 'old_render' in case:
        for uid, entry in paths['utterances'].items():
            waves[uid]['old_render'] = entry['old_wav']
    np.savez_compressed(out / 'pitch-ratios.npz', **traces)
    rows = window_starts(case, formants.read(paths['windows']), observed)
    window_formants(case, analysis, waves, observed, rows, out, execute)
    save(out / 'window-comparisons.json', rows)
    summaries = {uid: summarize_windows([r for r in rows if r['utterance'] == uid], variant) for uid in case['utterances']}
    overall = summarize_windows(rows, variant)
    cfg = case['measurement']
    control = 'MK61_01' if 'all_zero_reference' in case else 'FK61_01'
    checks = {key: all(c[key] for c in checks_by_uid.values()) for key in next(iter(checks_by_uid.values()))}
    checks |= {
        'matched_mfa_archive': all(controls.values()),
        'first_intervention_reproduced': (sha256(waves[control][variant]) == sha256(paths['single_pcm'])
            and observed[control][variant] == mfa.tiers(paths['single_alignment'])),
        'noise_floor': all(abs(data['noise_ratio_db'] - legacy['aligner']['noise_db']) <= legacy['measurement']['noise_tolerance_db']
                           and not data['pcm16_clipped_frames'] for items in noise.values() for data in items.values()),
        'registered_windows': overall['windows'] == cfg['windows']
            and {uid: metrics['old_changed_starts'] for uid, metrics in summaries.items()} == cfg['old_changed_starts'],
        'fixed_and_independent_formants_agree': all(test['agrees'] for row in rows for test in row['independent'].values()),
    }
    predictions = {'old_start_positions_recreated': overall['recreated_old_changes'] == overall['old_changed_starts'],
                   'no_new_start_changes': overall['new_changes'] == 0}
    boundaries = {uid: {mode: aligned.compare_intervals(tiers[mode], tiers[variant]) for mode in ('old', 'matched')}
                  for uid, tiers in observed.items()}
    extra = {}
    if 'outside_window_boundary' in case:
        outside = outside_boundary(case, observed, paths['drift_only_boundary'])
        extra['outside_window_boundary'] = outside
        predictions['outside_boundary_recreated'] = outside['old'] == outside[variant]
    return {'checks': checks, 'predictions': predictions, 'overall': overall, 'windows_by_utterance': summaries,
            'boundaries': boundaries, 'pitch_ratio': ratio, 'noise': noise, **extra}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=lambda value: Path(value).resolve(), choices=(CASE, VARIATION_CASE), default=CASE)
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('MFAの作業領域は CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    case = formants.read(args.case)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    matched, alignment, old, prior, f2 = (formants.open_run(case[key], revision) for key in (
        'matched_render', 'matched_alignment', 'old_alignment', 'single_intervention', 'formants'))
    legacy, legacy_snapshot = saved_case(old, CASE.with_name(f"{case['old_alignment']['case']}.json"))
    single, single_snapshot = saved_case(prior, CASE.with_name(f"{case['single_intervention']['case']}.json"))
    analysis, analysis_snapshot = saved_case(f2, formants.CASE)
    references = [matched, alignment, old, prior, f2]
    control = (prior, 'drift_zero', 'FK61_01')
    if 'all_zero_reference' in case:
        combined, drift_only, old_render = (formants.open_run(case[key], revision) for key in (
            'all_zero_reference', 'drift_only_reference', 'old_render'))
        references.extend((combined, drift_only, old_render))
        control = (combined, 'jitter_zero', 'MK61_01')
    control_run, control_mode, control_uid = control
    control_tag = f'{control_uid}-{control_mode}'
    paths = {name: formants.verified_path(run, f'artifacts/{path}') for name, run, path in (
        ('pcm', matched, 'matched-pcm.npz'), ('dictionary', alignment, 'synth.dict'),
        ('windows', alignment, 'window-comparisons.json'), ('single_pcm', control_run, f'{control_mode}-clean.wav'),
        ('single_alignment', control_run, f'aligned/{control_tag}/{control_tag}.json'))}
    if 'outside_window_boundary' in case:
        tag = f"{case['outside_window_boundary']['utterance']}-drift_zero"
        paths['drift_only_boundary'] = formants.verified_path(drift_only, f'artifacts/aligned/{tag}/{tag}.json')
    paths['utterances'] = {}
    for uid in case['utterances']:
        tag = f'{uid}-candidate'
        paths['utterances'][uid] = {name: formants.verified_path(run, f'artifacts/{path}') for name, run, path in (
            ('case', matched, f'{uid}/matched-case.json'), ('plan', matched, f'{uid}/matched-plan.json'),
            ('lab', alignment, f'corpus/{tag}/{tag}.lab'), ('matched_tape', alignment, f'corpus/{tag}/{tag}.wav'),
            ('matched_alignment', alignment, f'aligned/{tag}/{tag}.json'),
            ('old_alignment', old, f'aligned-1-synth/{tag}/{tag}.json'))}
        if 'old_render' in case:
            paths['utterances'][uid]['old_wav'] = formants.verified_path(old_render, f'artifacts/{uid}/candidate.wav')
    inputs = [args.case, Path(__file__).resolve(), legacy_snapshot, single_snapshot, analysis_snapshot, formants.PROBE,
              *(value for key, value in paths.items() if key != 'utterances'),
              *(value for row in paths['utterances'].values() for value in row.values()), *candidate_sources(),
              *(run[0] / 'manifest.json' for run in references),
              *(WORKSPACE / 'tools' / file for file in ('measure_tsp_matched_speech_mfa.py', 'measure_tsp_phone_boundaries.py',
                'measure_tsp_held_out_matched_speech.py', 'measure_tsp_seems_drift_only.py', 'measure_tsp_stressed_vowel_formants.py')),
              *(UPSTREAM / file for file in (formants.TSP_SOURCE, 'crates/chimera-cli/src/render.rs',
                'crates/chimera-cli/src/main.rs', 'crates/chimera/src/analysis/lpc.rs', 'crates/chimera/src/math.rs',
                'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/voice/human_voice.rs', 'tools/tsp/mfa.yaml'))]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'aligner': legacy['aligner']}
    return record_measurement(args.run_id, args.case, inputs, details, lambda out, execute: measure(
        case, single, legacy, analysis, paths, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
