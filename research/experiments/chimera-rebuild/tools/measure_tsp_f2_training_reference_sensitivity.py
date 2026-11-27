"""学習側のF2を一件ずつ差し替え、TSPの参照と費用を照合する。"""

import argparse
import json
import math
import os
from pathlib import Path
from statistics import median
import subprocess
from tempfile import TemporaryDirectory

import measure_tsp_again_f2_term_effect as term
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-training-reference-sensitivity.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_f2_training_reference_probe.rs'


def frozen_f2_inputs(settings, saved, prior):
    corr = saved['correspondence']
    ipa, speaker = settings['ipa'], settings['held_speaker']
    training = {name: [list(row) for row in term.speaker_samples(corr, name, ipa)]
                for name in settings['training_speakers']}
    held = [utt['tokens'] for utt in corr.values() if utt['speaker'] == speaker]
    def frequencies(key):
        return [row[key] for tokens in held for row in tokens
                if row['ipa'] == ipa and row['stressed'] and row[key] is not None]
    return {'term': settings['term'], 'ipa': ipa, 'training': training,
            'held_recording': frequencies('recording_f2_hz'), 'held_synth': frequencies('synth_f2_hz'),
            'replacements': {key: prior['input_f2_hz'][key] for key in settings['replacement_keys']}}


def reference_report(settings, training, held):
    minimum = settings['minimum_tokens']
    values = {name: term.summarize_samples(rows, minimum) for name, rows in training.items()}
    logs = [v['log2_hz'] for v in values.values() if v['log2_hz'] is not None]
    centre = median(logs) if len(logs) >= settings['minimum_training_speakers'] else None
    deviations = [v - centre for v in logs] if centre is not None else []
    mad = 1.4826 * median(abs(v - median(deviations)) for v in deviations) if deviations else None
    spread = max(settings['spread_floor_log2'], mad) if mad is not None else settings['spread_floor_log2']
    report = {'reference': [centre, spread, mad],
              'training': {name: {key: v[key] for key in ('support', 'log2_hz')} for name, v in values.items()}}
    for name, rows in held.items():
        value = term.summarize_samples(rows, minimum, centre, spread)
        report[name] = [value['log2_hz'], value['cost']]
    return report


def independent_sweep(settings, request):
    training = {name: [row[2] for row in rows] for name, rows in request['training'].items()}
    held = {name: request[name] for name in ('held_recording', 'held_synth')}
    out = []
    for speaker in request.get('intervention_speakers', request['training']):
        rows = request['training'][speaker]
        for idx, (uid, slot, original) in enumerate(rows):
            scenarios = {}
            for key, replacement in request['replacements'].items():
                changed = training[speaker].copy()
                changed[idx] = replacement
                scenarios[key] = reference_report(settings, training | {speaker: changed}, held)
            out.append({'speaker': speaker, 'utterance': uid, 'slot': slot,
                        'original_hz': original, 'scenarios': scenarios})
    return reference_report(settings, training, held), out


def summarize_sweep(settings, interventions):
    limit = settings['tolerance']
    by_speaker = {}
    for row in interventions:
        name = row['speaker']
        before, after = (row['scenarios'][key] for key in settings['replacement_keys'])
        centre, spread, mad = (abs(b - a) for a, b in zip(before['reference'], after['reference'], strict=True))
        stats = by_speaker.setdefault(name, dict.fromkeys(
            ('tokens', 'speaker_median_changed', 'centre_changed', 'mad_changed', 'spread_changed',
             'spread_changed_centre_fixed', 'held_recording_cost_changed', 'held_synth_cost_changed'), 0))
        stats['tokens'] += 1
        stats['speaker_median_changed'] += abs(
            before['training'][name]['log2_hz'] - after['training'][name]['log2_hz']) > limit
        stats['centre_changed'] += centre > limit
        stats['mad_changed'] += mad > limit
        stats['spread_changed'] += spread > limit
        stats['spread_changed_centre_fixed'] += spread > limit and centre <= limit
        for group in ('held_recording', 'held_synth'):
            stats[f'{group}_cost_changed'] += abs(before[group][1] - after[group][1]) > limit
    scenarios = [report for row in interventions for report in row['scenarios'].values()]
    return {
        'by_speaker': by_speaker,
        'centre_hz_range': [2 ** f(v['reference'][0] for v in scenarios) for f in (min, max)],
        'mad_log2_range': [f(v['reference'][2] for v in scenarios) for f in (min, max)],
        'spread_log2_range': [f(v['reference'][1] for v in scenarios) for f in (min, max)],
        'spread_floor_conditions': sum(
            row['reference'][2] < settings['spread_floor_log2'] for row in scenarios),
        'held_recording_cost_range': [f(v['held_recording'][1] for v in scenarios) for f in (min, max)],
        'held_synth_cost_range': [f(v['held_synth'][1] for v in scenarios) for f in (min, max)],
    }


def report_agrees(expected, observed, limit):
    return (all(abs(a - b) <= limit for a, b in zip(expected['reference'], observed['reference'], strict=True))
            and all(term.agrees(observed['training'][k], v, limit) for k, v in expected['training'].items())
            and all(tsp.max_error(expected[k], observed[k]) <= limit for k in ('held_recording', 'held_synth')))


def native_sweep(request, out, execute):
    with TemporaryDirectory(prefix='tsp-f2-reference-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = term.prepare_tsp_probe(scratch, out, execute, PROBE, 'research-f2-training-reference',
                                          'research_tsp_f2_training_reference')
        request_path = out / 'inputs.json'
        request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
        output = out / 'native.json'
        execute(['cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
                 '-p', 'chimera-cli', '--', 'research-f2-training-reference', str(request_path)], cwd=checkout, stdout=output)
    return tsp.read(output)


def measure(case, native, prior, out, execute):
    settings = case['measurement']
    request = frozen_f2_inputs(settings, native, prior)
    if sum(map(len, request['training'].values())) != settings['training_tokens']:
        raise ValueError('固定録音の学習側の支持数が登録値と一致しません')
    measured = native_sweep(request, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    baseline, rows = independent_sweep(settings, request)
    limit = settings['tolerance']
    identity = ('speaker', 'utterance', 'slot', 'original_hz')
    comparisons = all(all(a[k] == b[k] for k in identity)
                      and all(report_agrees(expected, b['scenarios'][key], limit)
                              for key, expected in a['scenarios'].items())
                      for a, b in zip(rows, measured['interventions'], strict=True))
    stats = summarize_sweep(settings, rows)
    supports = baseline['training']
    return {
        'checks': {
            'archived_reference_and_held_diagnostics_replayed': report_agrees(baseline, measured['baseline'], limit)
                and tsp.max_error(baseline['reference'], native['reference']) <= limit
                and abs(baseline['held_recording'][1] - prior['conditions']['default']['cost']) <= limit
                and round(baseline['held_synth'][1], 3) == native['conditions']['default']['held_synth_report']['terms'][settings['term']]['cost'],
            'independent_all_token_replacements': len(rows) == settings['training_tokens'] and comparisons,
            'baseline_restored_and_formants_group_verified': measured['baseline'] == measured['after_restore']
                and measured['minimum_tokens'] == settings['minimum_tokens']
                and measured['minimum_training_speakers'] == settings['minimum_training_speakers']
                and measured['spread_floor'] == settings['spread_floor_log2']
                and measured['group'] == 'formants' and measured['scored'] is False,
        },
        'predictions': {
            'finite_replacements_preserve_support': all(
                report['training'][name]['support'] == v['support']
                for row in rows for report in row['scenarios'].values() for name, v in supports.items()),
            'centre_is_monotone_with_replacement': all(row['scenarios']['before']['reference'][0]
                <= row['scenarios']['after']['reference'][0] for row in rows),
            'spread_changes_without_centre_movement': any(
                row['spread_changed_centre_fixed'] for row in stats['by_speaker'].values()),
        },
        'baseline': baseline, 'interventions': rows, 'statistics': stats,
    }


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
    prior = tsp.open_run(case['cohort'], revision)
    native = tsp.verified_path(prior, 'artifacts/native.json')
    summary = tsp.verified_path(prior, 'summary.json')
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(term.__file__), native, summary, prior[0] / 'manifest.json',
              *(UPSTREAM / name for name in (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock'))]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, tsp.read(native), tsp.read(summary), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
