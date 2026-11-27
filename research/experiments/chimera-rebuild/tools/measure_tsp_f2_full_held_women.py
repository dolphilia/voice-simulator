"""FKとFLの全発話で、確認女性のF2集約を部分集合と比較する。"""

import argparse
from itertools import zip_longest
import os
from pathlib import Path
import subprocess

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_held_synth_over_sets as over_sets
import measure_tsp_f2_pooled_reference_sweep as sweep
import measure_tsp_f2_training_reference_sensitivity as original
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-full-held-women.json'
SPEAKERS = ('FK', 'FL')


def cohort_ids(case):
    corpus = case['corpus']
    return {
        speaker: [f'{speaker}{group:02}_{sentence:02}' for group in range(first, last + 1)
                  for sentence in range(1, corpus['sentences_per_list'] + 1)]
        for speaker, (first, last) in corpus['lists'].items()
    }


def selected_f2(correspondence, speaker, ipa, field):
    return [row[field] for utt in correspondence.values() if utt['speaker'] == speaker
            for row in utt['tokens'] if row['ipa'] == ipa and row['stressed'] and row[field] is not None]


def full_request(case, partial, collection):
    correspondence = collection['correspondence']
    expected = {uid: name for name, ids in cohort_ids(case).items() for uid in ids}
    if {uid: row['speaker'] for uid, row in correspondence.items()} != expected:
        raise ValueError('全発話の対応結果が登録した確認話者・録音IDの集合に一致しません')
    held = {name: selected_f2(correspondence, name, partial['ipa'], 'synth_f2_hz') for name in SPEAKERS}
    return partial | {'held': held}


def overlap_report(partial_collection, full_collection):
    found = []
    differences = {}
    field_order = ('recording_index', 'synth_index', 'ipa', 'stressed',
                   'recording_interval', 'synth_interval', 'recording_f2_hz', 'synth_f2_hz')
    for uid, source in sorted(partial_collection.items()):
        if uid not in full_collection:
            continue
        found.append(uid)
        previous, current = source['tokens'], full_collection[uid]['tokens']
        changed_slots = []
        for index, (old, new) in enumerate(zip_longest(previous, current)):
            if old != new:
                fields = [k for k in field_order if old[k] != new[k]] if old is not None and new is not None else ['slot']
                changed_slots.append({'slot': index, 'fields': fields, 'partial': old, 'full': new})
        if changed_slots:
            differences[uid] = {'changed_slots': len(changed_slots), 'first_difference': changed_slots[0],
                                'fields': sorted(set(key for row in changed_slots for key in row['fields']))}
    return {'readings': found, 'differences': differences}


def evaluate(case, settings, partial, partial_result, partial_collection, collection, request, native):
    cfg = case['measurement']
    source = collection['correspondence']
    overlap = overlap_report(partial_collection, source)
    samples = {name: term.summarize_samples(selected_f2(source, name, request['ipa'], 'recording_f2_hz'),
                                            settings['minimum_tokens']) for name in SPEAKERS}
    profiles, variants = over_sets.independent_profiles(request, settings['minimum_tokens'])
    costs = over_sets.independent_costs(request, variants)
    stats = over_sets.measures(costs, variants)
    matched = all(over_sets.native_agreement(profiles, variants, costs, native, cfg['tolerance']))
    old_individual, old_profiles = over_sets.independent_profiles(partial, settings['minimum_tokens'])
    old_costs = over_sets.independent_costs(partial, old_profiles)
    old_stats = partial_result['statistics']
    shifted = {name: [ref for ref in costs if ref != 'baseline'
                      and (costs[ref][name]['over_sets'] == 0) != (old_costs[ref][name]['over_sets'] == 0)]
               for name in stats}
    return {
        'checks': {
            'all_recordings_matched_and_partial_overlap_retained': (
                len(source) == case['corpus']['recordings']
                and len(overlap['readings']) == len(partial_collection) == cfg['prior_recordings']
                and all(v['support'] >= settings['minimum_tokens']
                        for v in (*samples.values(), *profiles.values()))),
            'same_references_and_archived_partial_replayed': (
                request['references'] == partial['references'] and len(costs) == cfg['ref_cases']
                and old_individual == partial_result['individual_profiles']
                and old_profiles == partial_result['aggregate_profiles'] and old_costs == partial_result['costs']),
            'all_native_aggregates_and_costs_reproduced': matched,
            'fixed_upstream_diagnostic_and_limits': (
                native['minimum_sets'] == 1 and native['minimum_tokens'] == settings['minimum_tokens']
                and native['group'] == 'formants' and native['scored'] is False),
        },
        'predictions': {
            'shared_recordings_keep_matched_f2': not overlap['differences'],
            'mixed_aggregate_stays_zero': stats['mixed']['over_sets']['zero_conditions'] == cfg['ref_cases'] - 1,
            'female_zero_count_changes': stats['female']['over_sets']['zero_conditions']
                != old_stats['female']['over_sets']['zero_conditions'],
        },
        'overlap': overlap, 'recording_profiles': samples, 'synth_profiles': profiles,
        'aggregate_profiles': variants, 'statistics': stats, 'partial_statistics': old_stats,
        'zero_classification_changes': shifted, 'costs': costs,
    }


def partial_rows(case, fk, fl, fk_definition):
    sources = {'FK': fk, 'FL': fl}
    ids = {'FK': fk_definition['measurement']['cohort']['FK'], 'FL': case['cohort']['FL']}
    return {uid: sources[name]['correspondence'][uid] for name in SPEAKERS for uid in ids[name]}


def measure(case, settings, partial, summary, partial_collection, archive, aligner, out, execute):
    collection = term.collect_cohort({'cohort': cohort_ids(case)}, archive, aligner, out, execute,
                                     female=True, held=True, all_annotated=True)
    request = full_request(case, partial, collection)
    native = over_sets.native_aggregation(request, out, execute)
    return evaluate(case, settings, partial, summary, partial_collection, collection, request, native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('全発話の整列と試験ビルドに CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    partial, fk, fl, alignment = (tsp.open_run(case[key], revision)
        for key in ('partial', 'fk_recordings', 'fl_recordings', 'alignment_reference'))
    partial_case, partial_snapshot = saved_case(partial, over_sets.CASE)
    sweep_run = tsp.open_run(partial_case['fk'], revision)
    sweep_case, sweep_snapshot = saved_case(sweep_run, sweep.CASE)
    baseline_run = tsp.open_run(sweep_case['original_interventions'], revision)
    baseline, baseline_snapshot = saved_case(baseline_run, original.CASE)
    fk_case, fk_snapshot = saved_case(fk, term.CASE)
    fl_case, fl_snapshot = saved_case(fl, CASE.with_name(case['fl_recordings']['case'] + '.json'))
    align_case, align_snapshot = saved_case(alignment, CASE.with_name(case['alignment_reference']['case'] + '.json'))
    partial_input = tsp.verified_path(partial, 'artifacts/inputs.json')
    summary = tsp.verified_path(partial, 'summary.json')
    fk_native = tsp.verified_path(fk, 'artifacts/native.json')
    fl_native = tsp.verified_path(fl, 'artifacts/collection/native.json')
    archive = CASE.with_name(case['archive_case'])
    aligner = align_case['aligner']
    sources = (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock', 'tools/tsp/sentences.tsv',
               aligner['configuration'])
    inputs = [CASE, Path(__file__).resolve(), Path(term.__file__), Path(over_sets.__file__), term.PROBE, original.PROBE,
              term.ALIGNMENT, archive, partial_input, summary, fk_native, fl_native, partial_snapshot, sweep_snapshot,
              baseline_snapshot, fk_snapshot, fl_snapshot, align_snapshot,
              *(run[0] / 'manifest.json' for run in (partial, fk, fl, alignment, sweep_run, baseline_run)),
              *(UPSTREAM / name for name in sources)]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': aligner}
    old = partial_rows(fl_case, tsp.read(fk_native), tsp.read(fl_native), fk_case)
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, baseline['measurement'], tsp.read(partial_input), tsp.read(summary), old, tsp.read(archive)['reference'],
        aligner, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
