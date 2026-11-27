"""放射流量微分の時間換算だけを上流と揃え、波形を照合する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET
from measure_fixed_voice_lung_port_momentum import CASE as LUNG_CASE
from measure_fixed_voice_pharyngeal_wall_surface import CASE as WALL_CASE, CONTROL_FILES
from measure_fixed_voice_radiation_balance import (
    CASE as RADIATION_CASE, compare_terms, derivative, read_measurements, validate,
)
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, PATCH_ORDER, REFERENCES, ROOT, capture, pcm_report,
    read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_series_momentum import CASE as SERIES_CASE
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-radiation-derivative-48000.json'
DERIVATIVE_EDITS = {NATIVE_NET: (
    ('        let derivative = (radiation_flow - self.previous_radiation_flow) / self.dt;',
     '        let derivative = (radiation_flow - self.previous_radiation_flow) * self.research_rate_hz;'),
)}


def compare_series(case, observation, control, revised, upstream, fs):
    a, b, u = ({row['internal_sample']: row for row in rows} for rows in (control, revised, upstream))
    if not a.keys() == b.keys() == u.keys():
        raise ValueError('放射微分の内部番号を照合できません')
    previous_diffs = [int(i) for i in a if not same(a[i]['derivative'], u[i]['derivative'])]
    remaining = [int(i) for i in b if not same(b[i]['derivative'], u[i]['derivative'])]
    first = next(iter(remaining), None)
    first_frame = next((i for i in remaining if i % 2), None)
    points = dict.fromkeys(i for i in (*case['target_samples'], first, first_frame,
                                     observation['pcm_probe_internal_sample']) if i is not None)
    observations = {str(i): {'control': a[i], 'multiply_rate': b[i], 'upstream': u[i],
                     'remaining_difference': compare_terms(b[i], u[i], fs, multiply_rate=True) if i in remaining else None}
                    for i in points}
    checks = {
        'radiation_components_unchanged': all(same(a[i][key], b[i][key]) for i in a
            for key in ('wall', 'lip', 'nose', 'total', 'previous_total')),
        'control_flow_times_rate_reproduces_experiment': all(
            same(derivative(a[i]['total'], a[i]['previous_total'], fs, True), b[i]['derivative']) for i in a),
        'registered_derivative_samples_equal_upstream': all(
            same(b[i]['derivative'], u[i]['derivative']) for i in case['target_samples']),
        'registered_first_difference': first == case['expected_first_internal_difference'],
    }
    return checks, {'control_difference_samples': previous_diffs, 'remaining_difference_samples': remaining,
                    'first_internal_difference': first, 'first_frame_end_difference': first_frame, 'events': observations}


def measure(case, common, observation, refs, archives, copies, snapshot, out, execute):
    hashes = capture(common, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single.patch', 'series.patch', 'lung.patch', 'slit.patch', 'trace.patch',
                                  'wall-surface.patch'), variant_edits=DERIVATIVE_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = common['internal_rate_hz']
    samples = sorted({sample for a, b in observation['windows'] for sample in range(a, b)})
    control, control_walls = read_measurements(out / 'control', 'candidate', samples)
    revised, revised_walls = read_measurements(out / 'reordered', 'candidate', samples)
    upper = read_rows(archives['upstream-radiation.csv'])
    traces = [{row['internal_sample']: row for row in read_rows(out / name / 'candidate-internal.csv')}
              for name in ('control', 'reordered')]
    checks = {
        'archived_control_traces': all(sha256(out / 'control' / name) == sha256(archives[name]) for name in CONTROL_FILES),
        'wall_trace_unchanged': sha256(out / 'control/candidate-radiating-wall.csv') == sha256(out / 'reordered/candidate-radiating-wall.csv'),
        'control_equations': validate(control, control_walls, traces[0], fs, False),
        'reordered_equations': validate(revised, revised_walls, traces[1], fs, False, multiply_rate=True),
    }
    timing_checks, results = compare_series(case, observation, control, revised, upper, fs)
    checks.update(timing_checks)
    pcm_checks, pcm = pcm_report(common, refs, out, archived_control={
        block: archives[f'block-{block}.wav'] for block in common['blocks']})
    checks.update(pcm_checks)
    return {'checks': checks, 'build_sha256': hashes, **results, 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    slit_case = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
    paths = (CASE, WALL_CASE, RADIATION_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, slit_case)
    case, wall, radiation, common, base, series, lung, slit = (json.loads(path.read_text()) for path in paths)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    names = {group: [name for name in files if name in PATCH_ORDER or group == 'pcm'] for group, files in REFERENCES.items()}
    refs, manifests, archives = {}, {}, {}
    for group, files in names.items():
        for name in files:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']), ('lung', slit['lung_run']),
                       ('slit', radiation['slit_run']), ('wall-surface', case['wall_run'])):
        manifests[group], refs[f'{group}.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    manifests['prefix'], refs['prefix-case.json'] = verified_artifact(*radiation['prefix_run'], 'artifacts/extended-prefix-case.json')
    manifests['radiation'], refs['trace.patch'] = verified_artifact(*wall['radiation_run'], 'artifacts/candidate-radiation.patch')
    _, archives['upstream-radiation.csv'] = verified_artifact(*wall['radiation_run'], 'artifacts/upstream-radiation.csv')
    for name in (*CONTROL_FILES, *(f'block-{block}.wav' for block in common['blocks'])):
        _, archives[name] = verified_artifact(*case['wall_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [*paths, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *refs.values(), *archives.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, radiation, refs, archives, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
