"""確認話者FLのF2を保存済みの女性・男女参照の78条件で照合する。"""

import argparse
import json
import os
from pathlib import Path
import subprocess

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_pooled_reference_sweep as sweep
from measure_tsp_f2_reference_pooled_sexes import HELD
import measure_tsp_f2_training_reference_sensitivity as original
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-pooled-reference-held-fl.json'


def held_request(case, previous, measured):
    cfg = case['measurement']
    expected = {uid: speaker for speaker, ids in case['cohort'].items() for uid in ids}
    if {uid: utt['speaker'] for uid, utt in measured['correspondence'].items()} != expected:
        raise ValueError('確認用録音の話者とIDが登録と一致しません')
    ipa = previous['common']['ipa']
    samples = {name: [] for name in HELD}
    for uid, utt in measured['correspondence'].items():
        for row in utt['tokens']:
            if row['ipa'] != ipa or not row['stressed']:
                continue
            for name in HELD:
                side = name.removeprefix('held_')
                f2 = row[f'{side}_f2_hz']
                if f2 is not None:
                    samples[name].append([uid, row['slot'], f2])
    common = previous['common'] | {name: [row[2] for row in samples[name]] for name in HELD}
    return previous | {'common': common, 'confirmation_speaker': cfg['held'], 'confirmation_samples': samples}


def voice_profiles(settings, request):
    profiles = {name: term.summarize_samples(request['common'][name], settings['minimum_tokens']) for name in HELD}
    if any(row['log2_hz'] is None for row in profiles.values()):
        raise ValueError('FLの録音か合成のF2が上流の最低件数を満たしません')
    return profiles


def same_reference(a, b):
    return {key: v for key, v in a.items() if key not in HELD} == {key: v for key, v in b.items() if key not in HELD}


def score_refs(profiles, reports):
    observations = {}
    for cohort, report in reports.items():
        centre, width, _ = report['reference']
        values = {}
        for voice, profile in profiles.items():
            value = profile['log2_hz']
            gap = abs(value - centre)
            values[voice] = {'log2_hz': value, 'gap_minus_width_log2': gap - width,
                             'cost': 0.0 if gap <= width else gap / width - 1.0}
        observations[cohort] = values
    return observations


def cost_stats(baseline, rows):
    result = {}
    for cohort, profiles in baseline.items():
        sides = {}
        for name, base in profiles.items():
            costs = [r['held'][cohort][name]['cost'] for r in rows]
            margins = [r['held'][cohort][name]['gap_minus_width_log2'] for r in rows]
            sides[name] = {'zero_conditions': sum(cost == 0 for cost in costs),
                           'cost_range': [min(costs), max(costs)],
                           'maximum_absolute_deviation': max(abs(cost - base['cost']) for cost in costs),
                           'margin_range_log2': [min(margins), max(margins)]}
        result[cohort] = sides
    return result


def evaluate(case, settings, request, past, native):
    cfg = case['measurement']
    tol = cfg['tolerance']
    profiles = voice_profiles(settings, request)
    baseline = score_refs(profiles, past['baseline'])
    rows = [{'trial': list(sweep.trial_key(row)), 'held': score_refs(profiles, row['cohorts'])}
            for row in past['interventions']]
    identical_pairs = all(
        sweep.trial_key(old) == sweep.trial_key(new) == sweep.trial_key(design)
        for old, new, design in zip(past['interventions'], native['interventions'], request['trials'], strict=True))
    reference_pairs = [(past['baseline'], native['baseline'])]
    reference_pairs.extend((old['cohorts'], new['cohorts'])
                           for old, new in zip(past['interventions'], native['interventions'], strict=True))
    same_centres = all(old.keys() == new.keys() and all(same_reference(old[k], new[k]) for k in old)
                       for old, new in reference_pairs)
    checks = []
    for expected, (_, observed) in zip([baseline, *(row['held'] for row in rows)], reference_pairs, strict=True):
        checks.extend(
            abs(vals['log2_hz'] - observed[cohort][name][0]) <= tol
            and abs(vals['cost'] - observed[cohort][name][1]) <= tol
            and (vals['cost'] == 0) == (observed[cohort][name][1] == 0)
            for cohort, voices in expected.items() for name, vals in voices.items())
    fk = {name: {voice: sum(row['cohorts'][name][voice][1] == 0 for row in past['interventions']) for voice in HELD}
          for name in past['baseline']}
    fl = cost_stats(baseline, rows)
    return {
        'checks': {
            'same_archived_pairs_and_learning_reference': identical_pairs and same_centres
                and len(rows) == cfg['pairs'],
            'held_values_and_zero_costs_independently_reproduced': all(checks)
                and len(checks) == (cfg['pairs'] + 1) * len(sweep.COHORTS) * len(HELD),
            'fixed_upstream_diagnostic_rules_reproduced': native['diagnostic'] == past['diagnostic']
                and native['diagnostic']['spread_floor'] == settings['spread_floor_log2']
                and native['diagnostic']['group'] == 'formants' and native['diagnostic']['scored'] is False,
            'paired_source_support': request['confirmation_speaker'] == cfg['held']
                and all(v['support'] >= native['diagnostic']['minimum_tokens'] for v in profiles.values())
                and fk['mixed']['held_synth'] == cfg['pairs'],
        },
        'predictions': {
            'fl_has_positive_pooled_synth_cost': fl['mixed']['held_synth']['zero_conditions'] < cfg['pairs'],
            'pooled_has_at_least_as_many_zero_costs': all(
                fl['mixed'][name]['zero_conditions'] >= fl['female'][name]['zero_conditions'] for name in HELD),
            'pooled_reduces_maximum_recording_deviation': (
                fl['mixed']['held_recording']['maximum_absolute_deviation']
                < fl['female']['held_recording']['maximum_absolute_deviation'] - tol),
        },
        'profiles': profiles, 'fl_baseline': baseline, 'fl_interventions': rows, 'fl_statistics': fl,
        'fk_zero_conditions': fk,
    }


def measure(case, settings, previous, past, archive, aligner, out, execute):
    collection = term.collect_cohort(case, archive, aligner, out, execute, female=True, held=True)
    request = held_request(case, previous, collection)
    (out / 'inputs.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    voice_profiles(settings, request)
    native = sweep.native_sweep(request, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return evaluate(case, settings, request, past, native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('整列と比較用に CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    prior, align = (tsp.open_run(case[key], revision) for key in ('sweep', 'alignment_reference'))
    prior_case, prior_snapshot = saved_case(prior, sweep.CASE)
    baseline = tsp.open_run(prior_case['original_interventions'], revision)
    baseline_case, baseline_snapshot = saved_case(baseline, original.CASE)
    align_case, align_snapshot = saved_case(align, CASE.with_name(case['alignment_reference']['case'] + '.json'))
    previous, past = (tsp.verified_path(prior, f'artifacts/{name}.json') for name in ('inputs', 'native'))
    archive = CASE.with_name(case['archive_case'])
    aligner = align_case['aligner']
    paths = (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock',
             'tools/tsp/sentences.tsv', aligner['configuration'])
    inputs = [CASE, Path(__file__).resolve(), Path(sweep.__file__), Path(term.__file__), term.PROBE, original.PROBE,
              term.ALIGNMENT, previous, past, archive, prior_snapshot, baseline_snapshot, align_snapshot,
              *(run[0] / 'manifest.json' for run in (prior, align, baseline)), *(UPSTREAM / name for name in paths)]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': aligner}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, baseline_case['measurement'], tsp.read(previous), tsp.read(past), tsp.read(archive)['reference'],
        aligner, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
