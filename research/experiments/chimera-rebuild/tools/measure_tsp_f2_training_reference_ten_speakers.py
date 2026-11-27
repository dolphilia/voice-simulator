"""同じ39位置で、学習女性5名と10名のF2診断の感度を比較する。"""

import argparse
import os
from pathlib import Path
import subprocess

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_training_reference_sensitivity as sweep
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-training-reference-ten-speakers.json'
IDENTITY = ('speaker', 'utterance', 'slot', 'original_hz')


def enlarged_request(case, settings, frozen, collection):
    correspondence = collection['correspondence']
    expected = {uid: speaker for speaker, ids in case['cohort'].items() for uid in ids}
    if {uid: row['speaker'] for uid, row in correspondence.items()} != expected:
        raise ValueError('追加録音のIDか話者が事前登録と異なります')
    if frozen['training'].keys() & case['cohort'].keys() or not all(
            name.startswith('F') and name != settings['held_speaker'] for name in case['cohort']):
        raise ValueError('追加話者と固定話者が分離していません')
    addition = {name: [list(row) for row in term.speaker_samples(correspondence, name, settings['ipa'])]
                for name in case['cohort']}
    return frozen | {'training': frozen['training'] | addition, 'intervention_speakers': sorted(frozen['training'])}


def identities(rows):
    return [tuple(row[key] for key in IDENTITY) for row in rows]


def effects(settings, baseline, rows):
    reports = [report for row in rows for report in row['scenarios'].values()]
    metrics = {'centre_log2': ('reference', 0), 'spread_log2': ('reference', 1),
               'held_recording_cost': ('held_recording', 1), 'held_synth_cost': ('held_synth', 1)}
    return sweep.summarize_sweep(settings, rows) | {
        'maximum_absolute_deviation': {
            name: max(abs(report[field][index] - baseline[field][index]) for report in reports)
            for name, (field, index) in metrics.items()
        },
    }


def evaluate(case, settings, frozen, saved, request, native):
    tol = settings['tolerance']
    spec = case['measurement']
    baseline, rows = sweep.independent_sweep(settings, request)
    old_baseline, old_rows = sweep.independent_sweep(settings, frozen)
    old = effects(settings, old_baseline, old_rows)
    new = effects(settings, baseline, rows)
    same_reports = all(
        a['scenarios'].keys() == b['scenarios'].keys() and all(
            sweep.report_agrees(expected, b['scenarios'][key], tol) for key, expected in a['scenarios'].items())
        for a, b in zip(rows, native['interventions'], strict=True))
    before = old['maximum_absolute_deviation']
    after = new['maximum_absolute_deviation']
    return {
        'checks': {
            'original_comparison_and_frozen_positions_replayed': old_baseline == saved['baseline']
                and old_rows == saved['interventions']
                and identities(old_rows) == identities(rows)
                and len(rows) == spec['intervention_tokens']
                and sum(len(row['scenarios']) for row in rows) == spec['scenarios'],
            'all_ten_training_speakers_with_support': len(baseline['training']) == spec['training_speakers']
                and all(v['support'] >= settings['minimum_tokens'] for v in baseline['training'].values())
                and all(report['training'][name] == baseline['training'][name]
                        for row in rows for report in row['scenarios'].values() for name in case['cohort']),
            'upstream_and_independent_enlarged_reference': same_reports
                and identities(rows) == identities(native['interventions'])
                and sweep.report_agrees(baseline, native['baseline'], tol),
            'restoration_and_diagnostic_contract': native['baseline'] == native['after_restore']
                and native['group'] == 'formants' and native['scored'] is False
                and native['held_support'] == {name: len(frozen[f'held_{name}']) for name in ('recording', 'synth')}
                and native['minimum_tokens'] == settings['minimum_tokens']
                and native['minimum_training_speakers'] == settings['minimum_training_speakers']
                and native['spread_floor'] == settings['spread_floor_log2'],
        },
        'predictions': {
            'smaller_maximum_centre_deviation': after['centre_log2'] < before['centre_log2'] - tol,
            'smaller_maximum_held_cost_deviation': all(after[key] < before[key] - tol
                for key in ('held_recording_cost', 'held_synth_cost')),
        },
        'five_speakers': {'baseline': old_baseline, 'effects': old},
        'ten_speakers': {'baseline': baseline, 'effects': new},
        'interventions': rows,
    }


def measure(case, settings, archive_config, aligner, frozen, saved, out, execute):
    collection = term.collect_cohort(case, archive_config, aligner, out, execute, female=True)
    request = enlarged_request(case, settings, frozen, collection)
    native = sweep.native_sweep(request, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return evaluate(case, settings, frozen, saved, request, native)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('比較と整列用に CHIMERA_RUN_STORAGE=rtl9210b を指定してください')
    baseline, alignment = (tsp.open_run(case[key], revision) for key in ('baseline', 'alignment_reference'))
    baseline_case, baseline_snapshot = saved_case(baseline, sweep.CASE)
    alignment_case, alignment_snapshot = saved_case(
        alignment, CASE.with_name(case['alignment_reference']['case'] + '.json'))
    frozen = tsp.verified_path(baseline, 'artifacts/inputs.json')
    saved = tsp.verified_path(baseline, 'summary.json')
    archive_case = CASE.with_name(case['archive_case'])
    sources = (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'tools/tsp/sentences.tsv',
               'Cargo.lock', alignment_case['aligner']['configuration'])
    inputs = [CASE, Path(__file__).resolve(), Path(sweep.__file__), Path(term.__file__), term.PROBE, sweep.PROBE,
              baseline_snapshot, alignment_snapshot, archive_case, term.ALIGNMENT, frozen, saved,
              baseline[0] / 'manifest.json', alignment[0] / 'manifest.json', *(UPSTREAM / name for name in sources)]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
            'aligner': alignment_case['aligner']}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, baseline_case['measurement'], tsp.read(archive_case)['reference'], alignment_case['aligner'],
        tsp.read(frozen), tsp.read(saved), out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
