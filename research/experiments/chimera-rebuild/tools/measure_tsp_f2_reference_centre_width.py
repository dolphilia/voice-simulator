"""固定したFKのF2診断で、参照中心と幅を個別に差し替える。"""

import argparse
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import measure_tsp_again_f2_term_effect as term
from measure_tsp_f2_bandwidth_held_out import saved_case
import measure_tsp_f2_training_reference_sensitivity as sweep
import measure_tsp_stressed_vowel_formants as tsp
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE


CASE = WORKSPACE / 'cases/tsp-f2-reference-centre-width.json'
PROBE = WORKSPACE / 'tools/upstream_tsp_f2_reference_centre_width_probe.rs'
COHORTS = ('five_speakers', 'ten_speakers')


def comparison_input(case, settings, sources):
    cfg = case['measurement']
    pick = cfg['target']
    replacement = cfg['replacement']
    datasets = {}
    checks = {}
    for name, (request, measured) in sources.items():
        rows = request['training'][pick['speaker']]
        matches = [(i, row[2]) for i, row in enumerate(rows) if row[:2] == [pick['utterance'], pick['slot']]]
        i, original = next(iter(matches), (None, None))
        if len(matches) != 1:
            raise ValueError('登録した話者・録音・位置を1件に特定できません')
        selected = [r for r in measured['interventions'] if all(r[k] == v for k, v in pick.items())]
        if len(selected) != 1:
            raise ValueError('保存済みの介入を1件に特定できません')
        training = {speaker: [row[2] for row in samples] for speaker, samples in request['training'].items()}
        held = {voice: request[voice] for voice in cfg['held_costs']}
        baseline = sweep.reference_report(settings, training, held)
        training[pick['speaker']][i] = request['replacements'][replacement]
        intervened = sweep.reference_report(settings, training, held)
        checks[name] = (selected[0]['original_hz'] == original
                        and sweep.report_agrees(baseline, measured['baseline'], cfg['tolerance'])
                        and sweep.report_agrees(intervened, selected[0]['scenarios'][replacement], cfg['tolerance'])
                        and all(baseline[k][0] == intervened[k][0] for k in held))
        c0, w0, _ = baseline['reference']
        c1, w1, raw = intervened['reference']
        datasets[name] = {'centres': {'baseline': c0, 'intervened': c1},
                          'widths': {'baseline': w0, 'intervened': w1, 'raw_intervened_mad': raw},
                          'held': {voice: baseline[voice][0] for voice in held}}
    return {'term': settings['term'], 'cohorts': datasets}, checks


def independent_cells(request):
    cohorts = {}
    for name, cohort in request['cohorts'].items():
        cells = {}
        for centre_name, centre in cohort['centres'].items():
            for width_name, width in cohort['widths'].items():
                voices = {}
                for voice, log_value in cohort['held'].items():
                    gap = abs(log_value - centre)
                    zero = gap <= width
                    cost = 0.0 if zero else gap / width - 1.0
                    voices[voice] = {'log2_hz': log_value, 'gap_log2': gap, 'zero': zero,
                                     'cost': cost, 'diagnostic_cost': cost}
                cells[f'{centre_name}/{width_name}'] = voices
        cohorts[name] = cells
    return cohorts


def effects(cells, voice):
    def cost(centre, width):
        return cells[f'{centre}/{width}'][voice]['cost']

    baseline = cost('baseline', 'baseline')
    centre = cost('intervened', 'baseline')
    width = cost('baseline', 'intervened')
    joint = cost('intervened', 'intervened')
    return {'centre_first': [centre - baseline, joint - centre],
            'width_first': [width - baseline, joint - width],
            'centre_average': ((centre - baseline) + (joint - width)) / 2,
            'width_average': ((width - baseline) + (joint - centre)) / 2,
            'interaction': (joint - centre) - (width - baseline),
            'joint_change': joint - baseline,
            'floor_reduction': cost('intervened', 'raw_intervened_mad') - joint}


def evaluate(case, settings, request, input_checks, observed):
    cfg = case['measurement']
    tol = cfg['tolerance']
    cells = independent_cells(request)
    changes = {name: {voice: effects(rows, voice) for voice in cfg['held_costs']} for name, rows in cells.items()}
    native = observed['cohorts']
    actual_count = sum(len(row) for cohort in cells.values() for row in cohort.values())
    expected_cells = {f'{centre}/{width}' for centre in cfg['centres'] for width in cfg['widths']}
    matches = all(set(rows) == set(native[name]) == expected_cells and all(
        set(v) == set(native[name][key]) and all(
            row.keys() == native[name][key][voice].keys() and row['zero'] is native[name][key][voice]['zero']
            and all(abs(row[k] - native[name][key][voice][k]) <= tol for k in row if k != 'zero')
            for voice, row in v.items()) for key, v in rows.items()) for name, rows in cells.items())
    all_effects = [v for cohort in changes.values() for v in cohort.values()]
    recordings = [v['held_recording'] for v in changes.values()]
    synth = {key: row['held_synth']['cost'] for key, row in cells['ten_speakers'].items()}
    return {
        'checks': {
            'archived_endpoints_and_held_pair_reproduced': all(input_checks.values())
                and request['cohorts']['five_speakers']['held'] == request['cohorts']['ten_speakers']['held'],
            'all_crossed_costs_and_zero_boundary_reproduced': matches and native.keys() == cells.keys()
                and actual_count == cfg['comparison_count'],
            'effects_close_in_both_orders': all(
                all(abs(sum(row[key]) - row['joint_change']) <= tol for key in ('centre_first', 'width_first'))
                and abs(row['centre_average'] + row['width_average'] - row['joint_change']) <= tol
                for row in all_effects),
            'fixed_upstream_diagnostic_and_width_floor': observed['group'] == 'formants' and observed['scored'] is False
                and observed['spread_floor'] == settings['spread_floor_log2']
                and all(v['widths']['intervened'] == max(v['widths']['raw_intervened_mad'], observed['spread_floor'])
                        for v in request['cohorts'].values()),
        },
        'predictions': {
            'recording_width_effect_exceeds_centre': all(row['width_first'][0] > row['centre_first'][0] > 0 for row in recordings),
            'ten_synth_width_crosses_zero_centre_offsets': synth['baseline/baseline'] == synth['intervened/baseline'] == 0
                and synth['baseline/intervened'] > synth['intervened/intervened'],
            'width_floor_caps_recording_cost': all(row['floor_reduction'] > 0 for row in recordings),
        },
        'comparisons': actual_count, 'effects': changes, 'cells': cells,
    }


def measure(case, settings, sources, out, execute):
    request, checks = comparison_input(case, settings, sources)
    request_path, result = out / 'inputs.json', out / 'native.json'
    request_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
    command = 'research-f2-reference-centre-width'
    with TemporaryDirectory(prefix='tsp-f2-reference-centre-width-', dir=out.parent / 'tmp') as directory:
        scratch = Path(directory)
        checkout = term.prepare_tsp_probe(scratch, out, execute, PROBE, command,
                                          'research_tsp_f2_reference_centre_width')
        execute(['cargo', 'run', '--locked', '--offline', '--release', '--target-dir', str(scratch / 'target'),
                 '-p', 'chimera-cli', '--', command, str(request_path)], cwd=checkout, stdout=result)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
            cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
    return evaluate(case, settings, request, checks, tsp.read(result))


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
    sources = {}
    inputs = [CASE, PROBE, Path(__file__).resolve(), Path(sweep.__file__), Path(term.__file__),
              *(UPSTREAM / name for name in (tsp.TSP_SOURCE, term.ENTRY, 'crates/chimera-cli/src/compare.rs', 'Cargo.lock'))]
    for name in COHORTS:
        prior = tsp.open_run(case[name], revision)
        paths = [tsp.verified_path(prior, f'artifacts/{file}.json') for file in ('inputs', 'native')]
        inputs.extend([*paths, prior[0] / 'manifest.json'])
        sources[name] = tuple(map(tsp.read, paths))
        if name == 'five_speakers':
            baseline, snapshot = saved_case(prior, sweep.CASE)
            inputs.append(snapshot)
    info = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, info, lambda out, execute: measure(
        case, baseline['measurement'], sources, out, execute), command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
