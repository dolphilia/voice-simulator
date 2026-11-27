"""同じF2介入39位置で女性参照と男女をまとめた参照を比較する。"""

import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_reference_pooled_sexes as pooled
import measure_tsp_f2_training_reference_sensitivity as sweep
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-pooled-reference-sweep.json'
IDENTITY = ('speaker', 'utterance', 'slot', 'original_hz')
COHORTS = ('female', 'mixed')


def derive_input(case, prior, females, original):
    cfg = case['measurement']
    training = prior['training']
    if (prior['term'], prior['ipa']) != (females['term'], females['ipa']) or any(
            prior[key] != females[key] or females[key] != original[key] for key in pooled.HELD):
        raise ValueError('参照項目か固定したFKの入力が一致しません')
    if any(females['training'][speaker] != rows for speaker, rows in original['training'].items()):
        raise ValueError('元の介入位置と女性10名のデータが一致しません')
    if any(training[speaker] != [row[2] for row in rows] for speaker, rows in females['training'].items()):
        raise ValueError('保存した19名と元の女性側F2が一致しません')
    if females['replacements'] != original['replacements']:
        raise ValueError('固定した2つの差し替え値が一致しません')
    trials = []
    for speaker, rows in original['training'].items():
        for index, (uid, slot, original_hz) in enumerate(rows):
            for name in cfg['replacement_keys']:
                trials.append({'speaker': speaker, 'utterance': uid, 'slot': slot, 'original_hz': original_hz,
                               'index': index, 'replacement_name': name, 'replacement': original['replacements'][name]})
    common = {key: prior[key] for key in ('term', 'ipa', 'training', *pooled.HELD)}
    common['cohorts'] = {name: prior['cohorts'][name] for name in cfg['cohorts']}
    anchor = {key: prior[key] for key in ('speaker', 'index', 'replacement')}
    return {'common': common, 'anchor': anchor, 'trials': trials}


def trial_key(row):
    return tuple(row[k] for k in (*IDENTITY, 'replacement_name'))


def compare_costs(settings, baseline, rows):
    floor, tol = settings['spread_floor_log2'], settings['tolerance']
    effects = {}
    for voice in pooled.HELD:
        samples = [(trial_key(row), {
            name: row['cohorts'][name][voice][1] - baseline[name][voice][1] for name in COHORTS}) for row in rows]
        absolute = [abs(delta['mixed']) - abs(delta['female']) for _, delta in samples]
        largest_increase = max(absolute)
        effects[voice] = {
            'absolute_change_comparison': {
                'decreased': sum(d < -tol for d in absolute),
                'equal': sum(abs(d) <= tol for d in absolute),
                'increased': sum(d > tol for d in absolute),
            },
            'maximum_absolute_deviation': {name: max(abs(d[name]) for _, d in samples) for name in COHORTS},
            'signed_reversals': [list(key) for key, d in samples
                                 if any(d[a] < -tol and d[b] > tol for a, b in (COHORTS, COHORTS[::-1]))],
            'largest_absolute_increase': largest_increase,
            'largest_absolute_increase_trials': [list(key) for (key, _), gap in zip(samples, absolute, strict=True)
                                                 if abs(gap - largest_increase) <= tol and gap > tol],
        }
    return {
        'held_costs': effects,
        'width_floor_conditions': {name: sum(row['cohorts'][name]['pooled_mad'] < floor for row in rows)
                                   for name in COHORTS},
        'zero_cost_conditions': {name: {voice: sum(row['cohorts'][name][voice][1] == 0 for row in rows)
                                         for voice in pooled.HELD} for name in COHORTS},
    }


def evaluate(case, settings, request, native, past_female, past_pooled):
    cfg = case['measurement']
    tol = cfg['tolerance']
    common = request['common']
    recomputed = [{'trial': row, 'reports': pooled.independent_reports(settings, common | row)}
                  for row in request['trials']]
    baseline = {name: rows['baseline'] for name, rows in recomputed[0]['reports'].items()}
    rows = [r['trial'] | {'cohorts': {name: out['intervened'] for name, out in r['reports'].items()}}
            for r in recomputed]
    female = {trial_key(r | {'replacement_name': key}): value for r in past_female['interventions']
              for key, value in r['scenarios'].items()}
    anchor = [r for r in rows if all(r[k] == v for k, v in request['anchor'].items())]
    stats = compare_costs(settings, baseline, rows)
    cost_stats = stats['held_costs']
    male_residuals = {k: v for k, v in baseline['mixed']['residuals'].items() if k.startswith('M')}
    observations_match = all(
        trial_key(independent) == trial_key(upstream)
        and upstream['cohorts'].keys() == independent['cohorts'].keys()
        and all(pooled.agrees(independent['cohorts'][k], upstream['cohorts'][k], tol) for k in COHORTS)
        for independent, upstream in zip(rows, native['interventions'], strict=True))
    all_scenarios = [baseline, *(row['cohorts'] for row in rows)]
    return {
        'checks': {
            'archived_female_sweep_and_mixed_anchor_replayed': (
                {trial_key(row) for row in rows} == female.keys()
                and all(sweep.report_agrees(row['cohorts']['female'], female[trial_key(row)], tol) for row in rows)
                and len(anchor) == 1 and all(
                    pooled.agrees(anchor[0]['cohorts'][name], past_pooled['cohorts'][name]['intervened'], tol)
                    and pooled.agrees(baseline[name], past_pooled['cohorts'][name]['baseline'], tol) for name in COHORTS)),
            'all_paired_references_and_costs_reproduced': (
                observations_match and all(pooled.agrees(baseline[k], native['baseline'][k], tol) for k in COHORTS)
                and len(set(trial_key(row)[:4] for row in rows)) == cfg['tokens']
                and len(rows) == cfg['pairs']
                and sum(len(row['cohorts']) for row in rows) == cfg['intervention_reports']),
            'reference_centres_and_residual_support_reproduced': (
                all({k: r['support'] for k, r in pair[name]['training'].items()} ==
                    {k: r['support'] for k, r in baseline[name]['training'].items()}
                    for pair in all_scenarios for name in COHORTS)
                and all(all(pair['female']['reference'][i] == pair['mixed']['reference'][i] for i in (0, 2))
                        and all(pair['mixed']['residuals'][k] == v for k, v in male_residuals.items())
                        for pair in all_scenarios)),
            'fixed_upstream_diagnostic_and_support_limits': (
                native['diagnostic'] == {'group': 'formants', 'scored': False,
                    'minimum_tokens': settings['minimum_tokens'],
                    'minimum_training_speakers': settings['minimum_training_speakers'],
                    'spread_floor': settings['spread_floor_log2']}),
        },
        'predictions': {
            'both_maximum_cost_deviations_decrease': all(
                r['maximum_absolute_deviation']['mixed'] < r['maximum_absolute_deviation']['female'] - tol
                for r in cost_stats.values()),
            'width_floor_used_less_often': stats['width_floor_conditions']['mixed'] < stats['width_floor_conditions']['female'],
            'some_cost_deviation_grows': any(r['absolute_change_comparison']['increased'] for r in cost_stats.values()),
        },
        'baseline': baseline, 'interventions': rows, 'statistics': stats,
    }


def native_sweep(request, out, execute):
    command = 'research-f2-reference-pooled-sexes'
    baseline, diagnostic = None, None
    runs = []
    with TemporaryDirectory(prefix='tsp-f2-pooled-sweep-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = term.prepare_tsp_probe(scratch, out, execute, sweep.PROBE, command,
                                          'research_tsp_f2_reference_pooled_sexes')
        target = scratch / 'target'
        execute(['cargo', 'build', '--locked', '--offline', '--release', '--target-dir', str(target), '-p', 'chimera-cli'],
                cwd=checkout)
        payload = scratch / 'trial-input.json'
        response = scratch / 'trial-output.json'
        for trial in request['trials']:
            payload.write_text(json.dumps(request['common'] | trial, ensure_ascii=False))
            execute([str(target / 'release/chimera'), command, str(payload)], cwd=checkout, stdout=response)
            result = tsp.read(response)
            current = {name: row['baseline'] for name, row in result['cohorts'].items()}
            flags = {key: value for key, value in result.items() if key != 'cohorts'}
            if baseline is None:
                baseline, diagnostic = current, flags
            if current != baseline or flags != diagnostic:
                raise ValueError('各介入の開始時に参照か診断設定が変わりました')
            runs.append(trial | {'cohorts': {name: r['intervened'] for name, r in result['cohorts'].items()}})
    native = {'baseline': baseline, 'diagnostic': diagnostic, 'interventions': runs}
    (out / 'native.json').write_text(json.dumps(native, ensure_ascii=False, indent=2) + '\n')
    return native


def measure(case, settings, inputs, reports, out, execute):
    request = derive_input(case, *inputs)
    (out / 'inputs.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    native = native_sweep(request, out, execute)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return evaluate(case, settings, request, native, *reports)


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
    source, female, original = [tsp.open_run(case[name], revision)
                                for name in ('pooled_source', 'female_source', 'original_interventions')]
    baseline, baseline_path = saved_case(original, sweep.CASE)
    inputs = [tsp.verified_path(run, 'artifacts/inputs.json') for run in (source, female, original)]
    reports = [tsp.verified_path(run, 'artifacts/native.json') for run in (female, source)]
    tracked = [CASE, Path(__file__).resolve(), Path(pooled.__file__), Path(sweep.__file__), Path(term.__file__),
               sweep.PROBE, baseline_path, *inputs, *reports, *(r[0] / 'manifest.json' for r in (source, female, original)),
               *(UPSTREAM / name for name in (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock'))]
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, tracked, info, lambda out, execute: measure(
        case, baseline['measurement'], list(map(tsp.read, inputs)), list(map(tsp.read, reports)), out, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
