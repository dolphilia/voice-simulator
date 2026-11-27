"""TSP参照の幅に男女の学習残差をまとめたときのF2診断を照合する。"""

import argparse
import json
import os
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_reference_centre_width as centre_width
import measure_tsp_f2_training_reference_sensitivity as sweep
import measure_tsp_f2_training_reference_ten_speakers as ten
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-reference-pooled-sexes.json'
HELD = ('held_recording', 'held_synth')
COHORTS = ('female', 'male_four', 'mixed')


def derive_input(case, prior, females, collection):
    cfg = case['measurement']
    correspondence = collection['correspondence']
    expected = {uid: name for name, ids in case['cohort'].items() for uid in ids}
    if {uid: row['speaker'] for uid, row in correspondence.items()} != expected:
        raise ValueError('追加録音の話者かIDが登録値と一致しません')
    pick = prior['measurement']['target']
    female = females['training']
    male = {name: [row[2] for row in term.speaker_samples(correspondence, name, females['ipa'])]
            for name in case['cohort']}
    if not (all(k.startswith('F') for k in female) and all(k.startswith('M') for k in male)):
        raise ValueError('話者IDの性別が登録と一致しません')
    positions = [idx for idx, row in enumerate(female[pick['speaker']])
                 if row[:2] == [pick['utterance'], pick['slot']]]
    if len(positions) != 1:
        raise ValueError('介入位置が保存済みの学習データに1件ありません')
    return {
        'term': females['term'], 'ipa': females['ipa'],
        'training': {name: [row[2] for row in rows] for name, rows in female.items()} | male,
        'cohorts': {'female': sorted(female), 'male_four': sorted(female) + cfg['male_threshold_control'],
                    'mixed': sorted(female) + sorted(male)},
        'speaker': pick['speaker'], 'index': positions[0],
        'replacement': females['replacements'][prior['measurement']['replacement']],
        **{name: females[name] for name in HELD},
    }


def scaled_mad(values):
    if not values:
        return None
    centre = median(values)
    return 1.4826 * median(abs(value - centre) for value in values)


def report(settings, training, held):
    minimum = settings['minimum_tokens']
    support = {name: term.summarize_samples(rows, minimum) for name, rows in training.items()}
    profiles = {name: {k: v[k] for k in ('support', 'log2_hz')} for name, v in support.items()}
    centres, by_sex = {}, {}
    for sex in 'FM':
        values = {name: v['log2_hz'] for name, v in profiles.items()
                  if name.startswith(sex) and v['log2_hz'] is not None}
        centre = median(values.values()) if len(values) >= settings['minimum_training_speakers'] else None
        centres[sex] = centre
        by_sex[sex] = {name: value - centre for name, value in values.items()} if centre is not None else {}
    residuals = by_sex['F'] | by_sex['M']
    pooled_mad = scaled_mad(list(residuals.values()))
    minimum_width = settings['spread_floor_log2']
    width = max(minimum_width, pooled_mad) if pooled_mad is not None else minimum_width
    result = {'training': profiles, 'residuals': residuals, 'pooled_mad': pooled_mad,
              'reference': [centres['F'], width, scaled_mad(list(by_sex['F'].values()))],
              'male_reference': [centres['M'], width, scaled_mad(list(by_sex['M'].values()))]}
    for name, rows in held.items():
        value = term.summarize_samples(rows, minimum, centres['F'], width)
        result[name] = [value['log2_hz'], value['cost']]
    return result


def independent_reports(settings, request):
    held = {name: request[name] for name in HELD}
    speaker = request['speaker']
    intervention = request['training'][speaker].copy()
    intervention[request['index']] = request['replacement']
    output = {}
    for key, names in request['cohorts'].items():
        training = {name: request['training'][name] for name in names}
        output[key] = {'baseline': report(settings, training, held),
                       'intervened': report(settings, training | {speaker: intervention}, held)}
    return output


def agrees(expected, native, limit):
    return (sweep.report_agrees(expected, native, limit)
            and native['training'].keys() == expected['training'].keys()
            and native['residuals'].keys() == expected['residuals'].keys()
            and all(abs(v - native['residuals'][k]) <= limit for k, v in expected['residuals'].items())
            and abs(expected['pooled_mad'] - native['pooled_mad']) <= limit
            and all(a is b if a is None or b is None else abs(a - b) <= limit
                    for a, b in zip(expected['male_reference'], native['male_reference'], strict=True)))


def evaluate(case, settings, prior_input, request, native):
    cfg = case['measurement']
    limit = settings['tolerance']
    cohorts = independent_reports(settings, request)
    ff, small, mixed = (cohorts[name] for name in COHORTS)
    states = ('baseline', 'intervened')
    delta = {name: {key: rows['intervened'][key][1] - rows['baseline'][key][1] for key in HELD}
             for name, rows in cohorts.items()}
    preserved = lambda key: [ff[state][key] for state in states] == [small[state][key] for state in states]
    return {
        'checks': {
            'registered_cohorts_and_support_reproduced': (
                len(ff['baseline']['training']) == cfg['expected_female_speakers']
                and len(mixed['baseline']['training']) - len(ff['baseline']['training']) == cfg['expected_male_speakers']
                and len(cfg['male_threshold_control']) == settings['minimum_training_speakers'] - 1
                and all(row['support'] >= settings['minimum_tokens'] for row in mixed['baseline']['training'].values())
                and mixed['baseline']['residuals'].keys() == mixed['baseline']['training'].keys()
                and all(mixed['baseline']['residuals'][speaker] == mixed['intervened']['residuals'][speaker]
                        for speaker in mixed['baseline']['residuals'] if speaker.startswith('M'))),
            'all_native_centres_residuals_widths_and_costs_reproduced': (
                native['cohorts'].keys() == cohorts.keys() and sum(map(len, cohorts.values())) == cfg['comparison_count']
                and all(agrees(rows[state], native['cohorts'][name][state], limit)
                        for name, rows in cohorts.items() for state in states)),
            'saved_female_reference_and_fixed_held_values_replayed': (
                all(abs(ff[state]['reference'][0] - prior_input['centres'][state]) <= limit
                    and abs(ff[state]['reference'][1] - prior_input['widths'][state]) <= limit
                    for state in states)
                and abs(ff['intervened']['reference'][2] - prior_input['widths']['raw_intervened_mad']) <= limit
                and all(abs(rows[state][key][0] - prior_input['held'][key]) <= limit
                        for rows in cohorts.values() for state in states for key in HELD)),
            'fixed_upstream_diagnostic_and_limits': native['group'] == 'formants' and native['scored'] is False
                and native['minimum_tokens'] == settings['minimum_tokens']
                and native['minimum_training_speakers'] == settings['minimum_training_speakers']
                and native['spread_floor'] == settings['spread_floor_log2'],
        },
        'predictions': {
            'male_four_do_not_contribute_residuals': all(small[state]['male_reference'][0] is None
                and small[state]['male_reference'][2] is None for state in states)
                and all(preserved(key) for key in ('reference', 'residuals', 'pooled_mad', *HELD)),
            'mixed_width_changes_without_female_centre_change': (
                all(ff[state]['reference'][i] == mixed[state]['reference'][i] for state in states for i in (0, 2))
                and any(abs(ff[state]['reference'][1] - mixed[state]['reference'][1]) > limit for state in states)),
            'mixed_recording_sensitivity_is_smaller': (
                abs(delta['mixed']['held_recording']) < abs(delta['female']['held_recording']) - limit),
        },
        'cohorts': cohorts, 'held_cost_change': delta,
    }


def measure(case, settings, prior, old_input, females, archive, aligner, out, execute):
    collection = term.collect_cohort(case, archive, aligner, out, execute, female=False)
    request = derive_input(case, prior, females, collection)
    request_path, output = out / 'inputs.json', out / 'native.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    command = 'research-f2-reference-pooled-sexes'
    with TemporaryDirectory(prefix='tsp-f2-pooled-reference-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = term.prepare_tsp_probe(scratch, out, execute, sweep.PROBE, command,
                                          'research_tsp_f2_reference_pooled_sexes')
        execute(['cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
                 '-p', 'chimera-cli', '--', command, str(request_path)], cwd=checkout, stdout=output)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return evaluate(case, settings, old_input, request, tsp.read(output))


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
    female_run, contrast_run, alignment_run = (tsp.open_run(case[key], revision)
        for key in ('female_reference', 'centre_width', 'alignment_reference'))
    female_case, female_snapshot = saved_case(female_run, ten.CASE)
    baseline = tsp.open_run(female_case['baseline'], revision)
    baseline_case, baseline_snapshot = saved_case(baseline, sweep.CASE)
    prior, prior_snapshot = saved_case(contrast_run, centre_width.CASE)
    align_case, align_snapshot = saved_case(alignment_run, CASE.with_name(case['alignment_reference']['case'] + '.json'))
    females, old_input = (tsp.verified_path(run, 'artifacts/inputs.json') for run in (female_run, contrast_run))
    archive = CASE.with_name(case['archive_case'])
    upstream = (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock',
                'tools/tsp/sentences.tsv', align_case['aligner']['configuration'])
    inputs = [CASE, Path(__file__).resolve(), Path(term.__file__), Path(sweep.__file__), term.PROBE, sweep.PROBE,
              archive, term.ALIGNMENT, females, old_input, female_snapshot, prior_snapshot, align_snapshot,
              baseline_snapshot, *(run[0] / 'manifest.json' for run in (female_run, contrast_run, alignment_run, baseline)),
              *(UPSTREAM / path for path in upstream)]
    aligner = align_case['aligner']
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'aligner': aligner}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, baseline_case['measurement'], prior, tsp.read(old_input)['cohorts']['ten_speakers'], tsp.read(females),
        tsp.read(archive)['reference'], aligner, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
