"""確認女性の文集合ごとのF2をover_setsで集約して照合する。"""

import argparse
import json
import math
import os
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_pooled_reference_sweep as sweep
import measure_tsp_f2_training_reference_sensitivity as original
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-held-synth-over-sets.json'
SPEAKERS = ('FK', 'FL')


def source_rows(native):
    rows = {'baseline': native['baseline']}
    for trial in native['interventions']:
        key = '/'.join(str(trial[k]) for k in ('speaker', 'utterance', 'slot', 'replacement_name'))
        if key in rows:
            raise ValueError('保存した介入のIDが重複しています')
        rows[key] = trial['cohorts']
    return rows


def derive_input(case, prior_inputs, prior_outputs):
    cfg = case['measurement']
    metadata = prior_inputs['FK']['common']
    if any(inputs['common'][key] != metadata[key] for inputs in prior_inputs.values()
           for key in ('term', 'ipa', 'training', 'cohorts')):
        raise ValueError('FKとFLの保存済み学習入力が一致しません')
    if prior_inputs['FK']['trials'] != prior_inputs['FL']['trials']:
        raise ValueError('FKとFLで介入位置か代入値が一致しません')
    held = {speaker: prior_inputs[speaker]['common']['held_synth'] for speaker in SPEAKERS}
    sources = {speaker: source_rows(prior_outputs[speaker]) for speaker in SPEAKERS}
    if {key: len(rows) for key, rows in held.items()} != cfg['held_support']:
        raise ValueError('確認用2集合のF2の件数が登録値と一致しません')
    if not (sources['FK'].keys() == sources['FL'].keys() and len(sources['FK']) == cfg['pairs'] + 1):
        raise ValueError('保存済みの実測で同じ介入条件を特定できません')
    references = {key: {name: rows[name]['reference'][:2] for name in cfg['cohorts']}
                  for key, rows in sources['FK'].items()}
    if any(ref != sources['FL'][key][name]['reference'][:2]
           for key, cohorts in references.items() for name, ref in cohorts.items()):
        raise ValueError('FKとFLで参照中心か評価幅が一致しません')
    return {key: metadata[key] for key in ('term', 'ipa')} | {
        'held': held, 'references': references, 'short_count': cfg['short_count']}


def independent_profiles(request, min_tokens):
    def values(samples):
        return {'support': len(samples),
                'log2_hz': math.log2(median(samples)) if len(samples) >= min_tokens else None}

    def median_over(sets):
        available = [row['log2_hz'] for row in sets if row['log2_hz'] is not None]
        required = (len(sets) + 1) // 2
        return {'support': sum(row['support'] for row in sets),
                'log2_hz': median(available) if len(available) >= required else None}

    fk, fl = (request['held'][speaker] for speaker in SPEAKERS)
    fk_short, fl_short = (values(samples[:request['short_count']]) for samples in (fk, fl))
    profiles = {'FK': values(fk), 'FL': values(fl)}
    variants = {'over_sets': median_over(list(profiles.values())), 'token_pool': values(fk + fl),
                'fl_short': median_over([profiles['FK'], fl_short]),
                'both_short': median_over([fk_short, fl_short])}
    return profiles, variants


def independent_costs(request, variants):
    def cost(log_hz, centre, width):
        return max(0.0, abs(log_hz - centre) / width - 1.0) if log_hz is not None else None

    return {key: {
        cohort: {name: cost(profile['log2_hz'], centre, width) for name, profile in variants.items()}
        for cohort, (centre, width) in refs.items()}
        for key, refs in request['references'].items()}


def measures(costs, names):
    summary = {}
    for cohort, baseline in costs['baseline'].items():
        results = {}
        for name in names:
            all_costs = [rows[cohort][name] for case, rows in costs.items() if case != 'baseline']
            finite = [value for value in all_costs if value is not None]
            results[name] = {'zero_conditions': finite.count(0.0),
                             'positive_conditions': sum(value > 0 for value in finite),
                             'missing_conditions': len(all_costs) - len(finite),
                             'maximum_cost': max(finite, default=None),
                             'maximum_absolute_deviation': max(
                                 (abs(value - baseline[name]) for value in finite), default=None)}
        summary[cohort] = results
    return summary


def equal_value(x, y, limit):
    return x is y if x is None or y is None else abs(x - y) <= limit


def native_agreement(profiles, variants, costs, native, limit):
    profiles_match = all(set(expected) == observed.keys() and all(
        all(equal_value(v, observed[name][key], limit) for key, v in row.items()) for name, row in expected.items())
        for expected, observed in ((profiles, native['held']), (variants, native['variants'])))
    costs_match = native['cases'].keys() == costs.keys() and all(
        native['cases'][key].keys() == cohorts.keys() and all(
            native['cases'][key][cohort].keys() == values.keys() and all(
                equal_value(cost, native['cases'][key][cohort][name]['cost'], limit)
                and equal_value(cost, native['cases'][key][cohort][name]['diagnostic_cost'], limit)
                and (cost == 0) == (native['cases'][key][cohort][name]['cost'] == 0)
                for name, cost in values.items()) for cohort, values in cohorts.items())
        for key, cohorts in costs.items())
    return profiles_match, costs_match


def evaluate(case, settings, request, prior_outputs, native):
    cfg = case['measurement']
    limit = cfg['tolerance']
    profiles, variants = independent_profiles(request, settings['minimum_tokens'])
    costs = independent_costs(request, variants)
    statistics = measures(costs, variants)
    profiles_match, costs_match = native_agreement(profiles, variants, costs, native, limit)
    changes = {name: [key for key, groups in costs.items() if key != 'baseline'
                      and (groups[name]['over_sets'] == 0) != (groups[name]['token_pool'] == 0)]
               for name in cfg['cohorts']}
    source_individual = {speaker: source_rows(prior_outputs[speaker]) for speaker in SPEAKERS}
    solo_match = all(equal_value(ref['held_synth'][0], profiles[speaker]['log2_hz'], limit)
                     for speaker in SPEAKERS for refs in source_individual[speaker].values() for ref in refs.values())
    fk_zero = sum(groups['female']['held_synth'][1] == 0 for key, groups in source_individual['FK'].items()
                  if key != 'baseline')
    female_zeros = statistics['female']['over_sets']['zero_conditions']
    return {
        'checks': {
            'archived_individual_values_and_support_reproduced': profiles_match and solo_match
                and all(profiles[name]['support'] == count for name, count in cfg['held_support'].items()),
            'upstream_values_and_all_costs_reproduced': costs_match and len(costs) == cfg['pairs'] + 1,
            'half_sets_and_missing_controls_reproduced': native['minimum_sets'] == 1
                and native['minimum_tokens'] == settings['minimum_tokens']
                and variants['fl_short']['log2_hz'] == profiles['FK']['log2_hz']
                and variants['both_short']['log2_hz'] is None
                and all(stats['both_short']['missing_conditions'] == cfg['pairs'] for stats in statistics.values()),
            'formants_diagnostic_contract': native['group'] == 'formants' and native['scored'] is False,
        },
        'predictions': {
            'mixed_aggregate_zero_in_all_conditions': statistics['mixed']['over_sets']['zero_conditions'] == cfg['pairs'],
            'female_aggregate_partly_positive_with_more_zero_costs_than_fk': fk_zero < female_zeros < cfg['pairs'],
            'token_pool_changes_zero_classification': any(changes.values()),
        },
        'individual_profiles': profiles, 'aggregate_profiles': variants, 'statistics': statistics,
        'zero_classification_changes': changes, 'costs': costs,
    }


def native_aggregation(request, out, execute):
    input_path, output = out / 'inputs.json', out / 'native.json'
    input_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    command = 'research-f2-held-synth-over-sets'
    with TemporaryDirectory(prefix='tsp-f2-held-over-sets-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = term.prepare_tsp_probe(scratch, out, execute, original.PROBE, command,
                                          'research_tsp_f2_held_synth_over_sets')
        execute(['cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
                 '-p', 'chimera-cli', '--', command, str(input_path)], cwd=checkout, stdout=output)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return tsp.read(output)


def measure(case, settings, inputs, reports, out, execute):
    request = derive_input(case, inputs, reports)
    native = native_aggregation(request, out, execute)
    return evaluate(case, settings, request, reports, native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルド用に CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    sources = {name: tsp.open_run(case[name.lower()], revision) for name in SPEAKERS}
    fk_case, fk_snapshot = saved_case(sources['FK'], sweep.CASE)
    baseline = tsp.open_run(fk_case['original_interventions'], revision)
    baseline_case, baseline_snapshot = saved_case(baseline, original.CASE)
    inputs = {name: tsp.verified_path(run, 'artifacts/inputs.json') for name, run in sources.items()}
    native = {name: tsp.verified_path(run, 'artifacts/native.json') for name, run in sources.items()}
    paths = [CASE, Path(__file__).resolve(), Path(term.__file__), original.PROBE, fk_snapshot, baseline_snapshot,
             *inputs.values(), *native.values(), *((run[0] / 'manifest.json') for run in (*sources.values(), baseline)),
             *(UPSTREAM / name for name in (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock'))]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, paths, info, lambda out, execute: measure(
        case, baseline_case['measurement'], {k: tsp.read(p) for k, p in inputs.items()},
        {k: tsp.read(p) for k, p in native.items()}, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
