"""研究版の確認女性120発話を固定上流と同じ整列・参照に通す。"""

import argparse
import csv
from itertools import zip_longest
import json
import math
import os
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_full_held_women as full
import measure_tsp_f2_held_synth_over_sets as over_sets
import measure_tsp_f2_pooled_reference_sweep as sweep
import measure_tsp_f2_training_reference_sensitivity as original
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-f2-full-held-candidate.json'
SENTENCES = UPSTREAM / 'tools/tsp/sentences.tsv'


def candidate_inputs(corpus, template):
    ids = {uid: speaker for speaker, rows in full.cohort_ids(corpus).items() for uid in rows}
    observed = {}
    with SENTENCES.open(newline='') as table:
        for uid, speaker, text in csv.reader(table, delimiter='\t'):
            if uid in ids:
                if ids[uid] != speaker or uid in observed:
                    raise ValueError('記録IDと話者が対応しません')
                observed[uid] = template | {'input': template['input'] | {'id': uid, 'text': text}}
    if observed.keys() != ids.keys():
        raise ValueError('120発話の本文が揃いません')
    return observed


def candidate_plan(inspect, rate):
    return [[s['segment']['ipa'], s['segment'].get('stress') or 0,
             math.floor(s['start_seconds'] * rate + 0.5), math.floor(s['end_seconds'] * rate + 0.5)]
            for phrase in inspect['speech']['phrases'] for s in phrase['timing']['segments']]


def render(case, inputs, scratch, out, execute):
    cfg = case['measurement']
    target = scratch / 'candidate-target'
    execute(['cargo', 'build', '--locked', '--offline', '--release', '--target-dir', str(target), '-p', 'vocal-cli'])
    cli = target / 'release/vocal-cli'
    wave_dir = scratch / 'rendered'
    wave_dir.mkdir()
    observed, failures = {}, {}
    for uid, spec in inputs.items():
        case_path, inspect_path = scratch / f'{uid}.json', scratch / 'inspect.json'
        case_path.write_text(json.dumps({'speech_voice': spec}, ensure_ascii=False) + '\n')
        wave_path = wave_dir / f'{uid}.wav'
        try:
            execute([str(cli), 'inspect', str(case_path)], stdout=inspect_path)
            inspected = tsp.read(inspect_path)
            execute([str(cli), 'render-pcm', str(case_path), str(wave_path), '--no-trace', str(cfg['block_frames'])])
        except subprocess.CalledProcessError as error:
            failures[uid] = {'operation': error.cmd[1], 'exit_code': error.returncode}
            continue
        observed[uid] = {
            'plan': candidate_plan(inspected, cfg['sample_rate_hz']), 'frames': inspected['output_frames'],
            'input_sha256': sha256(case_path), 'wav_sha256': sha256(wave_path),
        }
    renders = {'rendered': observed, 'failures': failures, 'candidate_cli_sha256': sha256(cli)}
    (out / 'renders.json').write_text(json.dumps(renders, ensure_ascii=False, indent=2) + '\n')
    return wave_dir, renders


def collect(case, corpus, archive, aligner, scratch, out, wave_dir, execute):
    collection = out / 'collection'
    collection.mkdir()
    dataset, hashes = term.checked_corpus({'cohort': full.cohort_ids(corpus)}, archive, scratch, all_annotated=True)
    (collection / 'recordings.json').write_text(json.dumps(
        {'archive_sha256': archive['sha256'], 'wav_sha256': hashes}, indent=2) + '\n')
    request = {'recordings': sorted(hashes), 'dataset_dir': str(dataset), 'synth_dir': str(scratch / 'synth-mfa'),
               'female': True, 'held': True, 'candidate_dir': str(wave_dir),
               'pcm_tolerance': case['measurement']['pcm_absolute']}
    return term.native_probe(aligner, scratch, collection, execute, request, collect_only=True)


def eligible(collection, ipa):
    return {uid: [row for row in utt['tokens'] if row['ipa'] == ipa and row['stressed']]
            for uid, utt in collection['correspondence'].items() if any(
                row['ipa'] == ipa and row['stressed'] for row in utt['tokens'])}


def retain_f2_frames(collection, ipa, wave_dir, cfg, out):
    windows = []
    indices = []
    rate = cfg['sample_rate_hz'] / cfg['decimation']
    length = int(rate * cfg['frame_seconds'])
    for uid, rows in eligible(collection, ipa).items():
        signal = tsp.filtered_wave(wave_dir / f'{uid}.wav', 'candidate', cfg)
        for row in rows:
            left, right = row['synth_interval']
            ids = []
            for q in cfg['reference_centers']:
                start = int((left + q * (right - left)) * rate) - length // 2
                if start < 0 or start + length > len(signal):
                    ids.append(None)
                else:
                    ids.append(len(windows))
                    windows.append(signal[start:start + length])
            indices.append({'uid': uid, 'slot': row['slot'], 'frames': ids})
    (out / 'f2-frame-index.json').write_text(json.dumps(indices, indent=2) + '\n')
    np.savez_compressed(out / 'f2-frames.npz', frames=np.asarray(windows))
    return indices, windows


def audit_f2_frames(collection, ipa, cfg, indices, frames):
    source = {(uid, row['slot']): row['synth_f2_hz'] for uid, rows in eligible(collection, ipa).items() for row in rows}
    identity = {(row['uid'], row['slot']) for row in indices}
    if identity != source.keys() or len(indices) != len(identity):
        raise ValueError('保存したLPC窓と対応したF2のIDが一致しません')
    errors = []
    missing_mismatches = []
    for row in indices:
        poles = [tsp.window(frames[i], [0, cfg['frame_seconds'], 'EH1'], 0.5, cfg['order']['F'], cfg)['f1_f2_hz']
                 for i in row['frames'] if i is not None]
        picked = [v[1] for v in poles if v is not None]
        uid, slot = row['uid'], row['slot']
        observed = source[uid, slot]
        if picked and observed is not None:
            errors.append(abs(median(picked) - observed))
        elif bool(picked) != (observed is not None):
            missing_mismatches.append([uid, slot])
    return {'tokens': len(indices), 'finite_tokens': len(errors), 'missing_mismatches': missing_mismatches,
            'maximum_error_hz': max(errors, default=None)}


def compare_stages(case, upper, candidate, renders, ipa):
    rate = case['measurement']['sample_rate_hz']
    tolerance = case['measurement']['pcm_absolute']
    stages = {}
    for uid, render in candidate['render_comparison'].items():
        ref_plan = [[name, stress, math.floor(rate * a + 0.5), math.floor(rate * b + 0.5)]
                    for name, stress, a, b in render['upstream_plan']]
        observed = renders['rendered'][uid]
        plan = next((i for i, (a, b) in enumerate(zip_longest(ref_plan, observed['plan'])) if a != b), None)
        recorded = upper['correspondence'][uid]['tokens']
        matched = candidate['correspondence'][uid]['tokens']
        by_recording = [{t['recording_index']: t for t in rows} for rows in (recorded, matched)]
        differences, f2_differences = [], []
        for index in sorted(by_recording[0].keys() | by_recording[1].keys()):
            a, b = (rows.get(index) for rows in by_recording)
            fields = ('ipa', 'stressed', 'synth_interval')
            if a is None or b is None or any(a[key] != b[key] for key in fields):
                differences.append({'recording_index': index, 'upstream': a, 'candidate': b})
            if any(row is not None and row['ipa'] == ipa and row['stressed'] for row in (a, b)):
                f2 = [row['synth_f2_hz'] if row is not None and row['stressed'] else None for row in (a, b)]
                if f2[0] != f2[1]:
                    f2_differences.append({'recording_index': index, 'upstream_hz': f2[0], 'candidate_hz': f2[1]})
        stages[uid] = {
            'plan_first_difference': plan, 'plan_frames_match': render['upstream_frames'] == observed['frames'],
            'candidate_pcm_frames_match_plan': render['candidate_frames'] == observed['frames'],
            'pcm_first_difference': render['first_difference'],
            'pcm_first_above_tolerance': render['first_above_tolerance'],
            'pcm_maximum_absolute_difference': render['maximum_absolute_difference'],
            'pcm_exceeds_tolerance': render['maximum_absolute_difference'] > tolerance,
            'alignment_differences': len(differences), 'alignment_first_difference': next(iter(differences), None),
            'f2_differences': len(f2_differences), 'f2_first_difference': next(iter(f2_differences), None),
        }
    return stages


def evaluate(case, settings, upper_input, upper_summary, upper_collection, candidate, renders, request, native, lpc):
    cfg = case['measurement']
    profiles, variants = over_sets.independent_profiles(request, settings['minimum_tokens'])
    costs = over_sets.independent_costs(request, variants)
    stats = over_sets.measures(costs, variants)
    stages = compare_stages(case, upper_collection, candidate, renders, request['ipa'])
    old = upper_summary['costs']
    changed = {name: [k for k in costs if k != 'baseline' and
                      (costs[k][name]['over_sets'] == 0) != (old[k][name]['over_sets'] == 0)]
               for name in stats}
    return {
        'checks': {
            'all_ordinary_renders_and_measurements_present': not renders['failures'] and len(stages) == cfg['recordings']
                and stages.keys() == candidate['correspondence'].keys() == upper_collection['correspondence'].keys()
                and stages.keys() == renders['rendered'].keys()
                and all(s['candidate_pcm_frames_match_plan'] for s in stages.values()),
            'candidate_f2_matches_independent_lpc': not lpc['missing_mismatches']
                and lpc['maximum_error_hz'] is not None
                and lpc['finite_tokens'] == sum(v['support'] for v in profiles.values()),
            'fixed_reference_aggregate_and_diagnostic_agree': request['references'] == upper_input['references']
                and all(over_sets.native_agreement(profiles, variants, costs, native, cfg['tolerance']))
                and native['group'] == 'formants' and native['scored'] is False,
        },
        'predictions': {
            'planned_timing_matches_every_utterance': all(r['plan_first_difference'] is None and r['plan_frames_match']
                                                          for r in stages.values()),
            'some_pcm_exceeds_tolerance': any(r['pcm_exceeds_tolerance'] for r in stages.values()),
            'some_alignment_or_f2_changes': any(r['alignment_differences'] or r['f2_differences'] for r in stages.values()),
            'female_zero_classification_changes': bool(changed['female']),
        },
        'stages': stages, 'lpc': lpc, 'synth_profiles': profiles, 'aggregate_profiles': variants,
        'statistics': stats, 'zero_classification_changes': changed, 'costs': costs,
        'focus_case': {'id': cfg['focus_case'], 'upstream': old[cfg['focus_case']], 'candidate': costs[cfg['focus_case']]},
    }


def measure(case, settings, corpus, template, archive, aligner, cfg, baseline, out, execute):
    upper_input, upper_summary, upper_collection = baseline
    inputs = candidate_inputs(corpus, template['speech_voice'])
    (out / 'render-inputs.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n')
    with TemporaryDirectory(prefix='tsp-f2-full-candidate-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        wave_dir, renders = render(case, inputs, scratch, out, execute)
        if renders['failures']:
            return {'checks': {'all_ordinary_renders_and_measurements_present': False}, 'failures': renders['failures']}
        candidate = collect(case, corpus, archive, aligner, scratch, out, wave_dir, execute)
        request = full.full_request(corpus, upper_input, candidate)
        indices, frames = retain_f2_frames(candidate, request['ipa'], wave_dir, cfg, out)
        lpc = audit_f2_frames(candidate, request['ipa'], cfg, indices, frames)
    if lpc['maximum_error_hz'] is None or lpc['maximum_error_hz'] > cfg['frequency_bandwidth_agreement_hz']:
        raise ValueError('候補のF2が独立計算の許容範囲に入りません')
    native = over_sets.native_aggregation(request, out, execute)
    return evaluate(case, settings, upper_input, upper_summary, upper_collection, candidate, renders, request, native, lpc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('全発話の描画と整列に CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    source, matched, aligned = (tsp.open_run(case[key], revision) for key in ('baseline', 'matched_settings', 'alignment'))
    corpus, corpus_path = saved_case(source, full.CASE)
    partial = tsp.open_run(corpus['partial'], revision)
    partial_case, partial_path = saved_case(partial, over_sets.CASE)
    fk_run = tsp.open_run(partial_case['fk'], revision)
    fk_case, fk_path = saved_case(fk_run, sweep.CASE)
    original_run = tsp.open_run(fk_case['original_interventions'], revision)
    settings, settings_path = saved_case(original_run, original.CASE)
    alignment, alignment_path = saved_case(aligned, CASE.with_name(case['alignment']['case'] + '.json'))
    aligner = alignment['aligner']
    template = tsp.verified_path(matched, case['render_template'])
    base_paths = [tsp.verified_path(source, name) for name in
                  ('artifacts/inputs.json', 'summary.json', 'artifacts/collection/native.json')]
    archive = CASE.with_name(corpus['archive_case'])
    lpc = CASE.with_name(case['lpc_case'])
    relevant = (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock', aligner['configuration'])
    tracked = [CASE, Path(__file__).resolve(), Path(term.__file__), Path(full.__file__), Path(over_sets.__file__),
               Path(tsp.__file__), term.PROBE, original.PROBE, SENTENCES, term.ALIGNMENT, archive, lpc, template,
               corpus_path, partial_path, fk_path, settings_path, alignment_path, *base_paths, *candidate_sources(),
               *(r[0] / 'manifest.json' for r in (source, matched, aligned, partial, fk_run, original_run)),
               *(UPSTREAM / name for name in relevant)]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
            'aligner': aligner}
    return record_measurement(args.run_id, CASE, tracked, info, lambda out, execute: measure(
        case, settings['measurement'], corpus, tsp.read(template), tsp.read(archive)['reference'], aligner,
        tsp.read(lpc)['measurement'], list(map(tsp.read, base_paths)), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
