"""咽頭の枝14→15で現在慣性または持ち越し圧の時間換算を比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET
from measure_fixed_voice_pharyngeal_second_cell import (
    CASE as BALANCE_CASE, ROOT, candidate_patches, event, listed_input, read_observations, read_rows,
    same, source_inputs, validate, verified_artifact,
)
from measure_fixed_voice_radiation_balance import compare_terms, read_measurements, validate as validate_radiation
from measure_fixed_voice_tracheal_momentum import capture, pcm_report, record_measurement
from measure_fixed_voice_tracheal_penultimate import flow_substitutions
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharyngeal-second-cell-inertance-48000.json'
PATCH_NAME = 'candidate-second-cell-inertance.patch'
HISTORY_PATCH_NAME = 'candidate-second-cell-history.patch'
STEP = '            let flow = branch.step(self.dt, difference, observation, rate, history_rate);'
INERTANCE_EDITS = {NATIVE_NET: ((STEP, '''            let inertance_rate = if pharynx_history_inlet.map(|inlet| inlet + 1) == Some(left)
                && right == left + 1 && branch.port.is_none()
            {
                Some(self.research_rate_hz)
            } else {
                rate
            };
            let flow = branch.step(self.dt, difference, observation, inertance_rate, history_rate);'''),)}
SECOND_HISTORY = '                || (pharynx_history_inlet == Some(left) && right == left + 1 && branch.port.is_none())'
HISTORY_EDITS = {NATIVE_NET: ((SECOND_HISTORY, SECOND_HISTORY + '''
                || (pharynx_history_inlet.map(|inlet| inlet + 1) == Some(left)
                    && right == left + 1 && branch.port.is_none())'''),)}
TAGS = ('cell-node', 'cell-wall', 'pharyngeal', 'cell-outgoing')
COMPARISONS = {
    'outgoing': ('cell-outgoing', 'flow'),
    'outgoing_driving_pressure': ('cell-outgoing', 'drive_pressure'),
    'outgoing_current_inertance': ('cell-outgoing', 'inertance_per_step'),
    'outgoing_history': ('cell-outgoing', 'history_pressure'),
    'outgoing_right_pressure': ('cell-outgoing', 'right_pressure'),
    'pressure': ('cell-node', 'new_pressure'),
    'incoming': ('pharyngeal', 'flow'),
    'wall': ('cell-wall', 'flow'),
    'radiation': ('radiation', 'derivative'),
}


def rows_by_sample(path):
    return {int(row['internal_sample']): row for row in read_rows(path)}


def first_differences(left, right):
    return {key: next((sample for sample in left[tag] if not same(left[tag][sample][field], right[tag][sample][field])), None)
            for key, (tag, field) in COMPARISONS.items()}


def inspect(case, base, patches, saved, copies, snapshot, out, execute):
    history_case = 'inertance_run' in case
    refs = {**saved, **{str(index): patch for index, patch in enumerate(patches)}}
    order = tuple(str(index) for index in range(len(patches)))
    build = capture(case, refs, copies, snapshot, out, execute, patch_order=order,
                    variant_edits=HISTORY_EDITS if history_case else INERTANCE_EDITS,
                    variant_patch_name=HISTORY_PATCH_NAME if history_case else PATCH_NAME)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'engine', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    samples = list(range(base['first_internal_sample'], base['end_internal_sample_exclusive']))
    fs = case['internal_rate_hz']
    upper = {tag: rows_by_sample(saved[f'upstream-{tag}.csv']) for tag in (*TAGS, 'radiation')}
    if any(list(upper[tag]) != samples for tag in TAGS) or len(upper['radiation']) != 64:
        raise ValueError('固定上流の観測区間が登録と一致しません')
    if base['nodes'][1:] != case['changed_branch_nodes']:
        raise ValueError('先行の収支の流出枝が比較条件と一致しません')
    checks, candidate, wall_rows = {}, {}, {}
    for mode in ('control', 'reordered'):
        folder = out / mode
        data = read_observations(folder, 'candidate', samples, case['changed_branch_nodes'][0])
        trace = rows_by_sample(folder / 'candidate-internal.csv')
        terms, walls = read_measurements(folder, 'candidate', list(upper['radiation']))
        data['radiation'] = {int(row['internal_sample']): row for row in terms}
        checks[f'{mode}_equations_and_timing'] = validate(data, trace, samples, fs, False,
                                                         scale_outgoing=history_case or mode == 'reordered',
                                                         multiply_outgoing_history=history_case and mode == 'reordered')
        checks[f'{mode}_radiation_equations'] = validate_radiation(terms, walls, trace, fs, False, multiply_rate=True)
        candidate[mode] = data
        wall_rows[mode] = walls

    control, reordered = (candidate[mode] for mode in ('control', 'reordered'))
    comparisons = {'control_upstream': first_differences(control, upper),
                   'reordered_upstream': first_differences(reordered, upper),
                   'reordered_control': first_differences(reordered, control)}
    first_target = case['first_outgoing_target']
    control_files = ['candidate-internal.csv', *(f'candidate-{tag}.csv' for tag in (*TAGS, 'radiation'))]
    if history_case:
        control_files.append('candidate-radiating-wall.csv')
    checks['archived_control_observations'] = all(sha256(out / 'control' / name) == sha256(saved[name]) for name in control_files)
    checks['registered_outgoing_matches'] = (comparisons['control_upstream']['outgoing'] == first_target
        and same(reordered['cell-outgoing'][first_target]['flow'], upper['cell-outgoing'][first_target]['flow']))
    pcm_checks, pcm = pcm_report(case, refs, out, archived_control={
        block: saved[f'block-{block}.wav'] for block in case['blocks']})
    checks.update(pcm_checks)

    targets = {}
    for kind, sample in (('outgoing', first_target), ('pressure', case['pressure_target']), ('incoming', case['incoming_target'])):
        tag, field = COMPARISONS[kind]
        targets[kind] = {'sample': sample, **{mode: data[tag][sample][field] for mode, data in
                        (('control', control), ('reordered', reordered), ('upstream', upper))}}
    next_outgoing = comparisons['reordered_upstream']['outgoing']
    next_pressure = comparisons['reordered_upstream']['pressure']
    next_radiation = comparisons['reordered_upstream']['radiation']
    result = {'checks': checks, 'build_sha256': build, 'first_differences': comparisons, 'targets': targets,
              'first_remaining_outgoing': None if next_outgoing is None else event(reordered, upper, next_outgoing, fs),
              'first_remaining_pressure': None if next_pressure is None else event(reordered, upper, next_pressure, fs),
              'first_remaining_radiation': None if next_radiation is None else compare_terms(
                  reordered['radiation'][next_radiation], upper['radiation'][next_radiation], fs, multiply_rate=True),
              'pcm': pcm}
    if history_case:
        index, node = case['radiation_target'], case['wall_target_node']
        wall_rows['upstream'] = read_rows(saved['upstream-radiating-wall.csv'])
        targets['radiation_and_wall'] = {'sample': index, 'node': node}
        for mode, data in (('control', control), ('reordered', reordered), ('upstream', upper)):
            wall, = [row for row in wall_rows[mode] if row['internal_sample'] == index and row['node'] == node]
            targets['radiation_and_wall'][mode] = {'wall': wall, 'radiation': data['radiation'][index]}
        next_incoming = comparisons['reordered_upstream']['incoming']
        result['first_remaining_incoming'] = None if next_incoming is None else flow_substitutions(
            reordered['pharyngeal'][next_incoming], upper['pharyngeal'][next_incoming], fs)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE)
    args = parser.parse_args()
    case_path = args.case.resolve()
    case, base = (json.loads(path.read_text()) for path in (case_path, BALANCE_CASE))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')

    saved, extra_manifests = {}, []
    if 'inertance_run' in case:
        inertance_manifest, inertance_patch = verified_artifact(*case['inertance_run'], f'artifacts/{PATCH_NAME}')
        inertance_case = listed_input(inertance_manifest, CASE.name)
        case = {**json.loads(inertance_case.read_text()), **case}
        wall_manifest, saved['upstream-radiating-wall.csv'] = verified_artifact(
            *case['upstream_wall_run'], 'artifacts/upstream-radiating-wall.csv')
        extra_manifests.extend((inertance_manifest, inertance_case, wall_manifest))

    for name in ('candidate-second-cell.patch', 'candidate-internal.csv',
                 *(f'{side}-{tag}.csv' for side in ('candidate', 'upstream') for tag in TAGS)):
        balance_manifest, saved[name] = verified_artifact(*case['balance_run'], f'artifacts/{name}')
    for name in ('candidate-tracheal-history.patch', 'reordered/candidate-radiation.csv',
                 *(f'reordered/block-{block}.wav' for block in case['blocks'])):
        baseline_manifest, saved[Path(name).name] = verified_artifact(*base['candidate_run'], f'artifacts/{name}')
    for name in ('upstream-radiation.csv', 'upstream-voice.f32', 'replay-case.json'):
        saved[name] = listed_input(baseline_manifest, name)
    saved['prefix-case.json'] = listed_input(balance_manifest, 'extended-prefix-case.json')
    source_manifest = listed_input(balance_manifest, 'fixed-voice-glottal-branch-48000-v2-repeat/manifest.json')
    patches = [*candidate_patches(baseline_manifest), saved['candidate-tracheal-history.patch'],
               saved['candidate-second-cell.patch']]
    if 'inertance_run' in case:
        patches.append(inertance_patch)
        for name in ('candidate-internal.csv', *(f'candidate-{tag}.csv' for tag in (*TAGS, 'radiation', 'radiating-wall')),
                     *(f'block-{block}.wav' for block in case['blocks'])):
            _, saved[name] = verified_artifact(*case['inertance_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(source_manifest)
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values()) if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [case_path, BALANCE_CASE, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools,
              balance_manifest, baseline_manifest, source_manifest, *extra_manifests, *saved.values(), *patches]
    return record_measurement(args.run_id, case_path, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: inspect(case, base, patches, saved, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
