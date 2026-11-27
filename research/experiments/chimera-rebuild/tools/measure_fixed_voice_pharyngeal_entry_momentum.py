"""咽頭入口の1枝の運動量換算だけを変えて連続描画を比較する。"""

import argparse
import json
from pathlib import Path
import subprocess
import sys

from measure_fixed_voice_glottal_branch import NATIVE_NET
from measure_fixed_voice_pharyngeal_entry_branch import (
    CASE as BRANCH_CASE, BALANCE_CASE, DERIVATIVE_CASE, LUNG_CASE, PATCH_ORDER, RADIATION_CASE, REFERENCES, ROOT,
    SERIES_CASE, SINGLE_CASE, WALL_CASE, flow_substitutions, read_capture, read_rows, record_measurement,
    same, source_inputs, verified_artifact, verify_clock,
)
from measure_fixed_voice_radiation_balance import read_measurements
from measure_fixed_voice_tracheal_momentum import capture, pcm_report
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharyngeal-entry-momentum-48000.json'
LOOP = '        for (index, (branch, &noise)) in self'
HISTORY = '            let history_rate = if self.research_lung_port_history == Some(index)'
PHARYNX_HISTORY_EDITS = {NATIVE_NET: (
    (LOOP, '        let pharynx_history_inlet = glottis.map(|branch| self.branches[branch].nodes[1]);\n' + LOOP),
    (HISTORY, HISTORY + '\n                || (pharynx_history_inlet == Some(left) && right == left + 1 && branch.port.is_none())'),
)}
CONTROL_FILES = ('candidate-internal.csv', 'candidate-pharyngeal.csv', 'candidate-pharyngeal-geometry.csv')


def measure(case, branch, radiation, common, refs, saved, copies, snapshot, out, execute):
    patches = (*PATCH_ORDER, 'single.patch', 'series.patch', 'lung.patch', 'slit.patch', 'trace.patch',
               'wall.patch', 'derivative.patch', 'pharynx-trace.patch')
    hashes = capture(common, refs, copies, snapshot, out, execute, patch_order=patches, variant_edits=PHARYNX_HISTORY_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway_adversarial', '--test', 'engine'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    start, end = (branch[key] for key in ('first_internal_sample', 'end_internal_sample_exclusive'))
    samples = list(range(start, end))
    nodes = branch['first_ordered_branch_nodes']
    scope = sorted({sample for a,b in radiation['windows'] for sample in range(a,b)})
    fs = common['internal_rate_hz']
    a, b = (read_capture(out / mode, 'candidate', samples, nodes)[0] for mode in ('control', 'reordered'))
    u = read_rows(saved['upstream-pharyngeal.csv'])
    traces = [{row['internal_sample']: row for row in read_rows(out / name / 'candidate-internal.csv')}
              for name in ('control', 'reordered')]
    rad_a, rad_b = ({row['internal_sample']: row for row in read_measurements(out / mode, 'candidate', scope)[0]}
                    for mode in ('control', 'reordered'))
    upper_rad = {row['internal_sample']: row for row in read_rows(saved['upstream-radiation.csv'])}
    upper_pressure = {row['internal_sample']: row for row in read_rows(saved['upstream-pharynx-balance.csv'])}
    first = next((i for i, left, right in zip(samples, b, u, strict=True) if not same(left['flow'], right['flow'])), None)
    next_radiation = next((i for i in scope if not same(rad_b[i]['derivative'], upper_rad[i]['derivative'])), None)
    pressure_at, radiation_at = (case[key] for key in ('target_pressure_sample', 'target_radiation_sample'))
    pressure_key = 'pressure_supra_dyn_cm2'
    checks = {
        'archived_control_observations': all(sha256(out / 'control' / name) == sha256(saved[name]) for name in CONTROL_FILES),
        'control_equation': verify_clock(a, traces[0], fs, False),
        'reordered_equation': verify_clock(b, traces[1], fs, False, multiply_history=True),
        'registered_flows_match': all(same(b[i-start]['flow'], u[i-start]['flow']) for i in case['target_flow_samples']),
        'registered_pressure_matches': same(traces[1][pressure_at][pressure_key], upper_pressure[pressure_at][pressure_key]),
    }
    pcm_checks, pcm = pcm_report(common, refs, out, archived_control={block: saved[f'block-{block}.wav'] for block in common['blocks']})
    checks.update(pcm_checks)
    events = {str(i): {'control': a[i-start]['flow'], 'reordered': b[i-start]['flow'], 'upstream': u[i-start]['flow']}
              for i in case['target_flow_samples']}
    return {'checks': checks, 'build_sha256': hashes, 'flow_at_target': events,
            'pressure_at_target': {'control': traces[0][pressure_at][pressure_key], 'reordered': traces[1][pressure_at][pressure_key],
                                   'upstream': upper_pressure[pressure_at][pressure_key]},
            'radiation_at_target': {'control': rad_a[radiation_at]['derivative'], 'reordered': rad_b[radiation_at]['derivative'],
                                    'upstream': upper_rad[radiation_at]['derivative']},
            'first_branch_flow_difference': first, 'first_radiation_difference': next_radiation,
            'next_branch_event': None if first is None else flow_substitutions(b[first-start], u[first-start], fs), 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    slit_path = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
    cases = (CASE, BRANCH_CASE, DERIVATIVE_CASE, WALL_CASE, RADIATION_CASE, SINGLE_CASE, BALANCE_CASE,
             SERIES_CASE, LUNG_CASE, slit_path)
    case, branch, derivative, wall, radiation, common, base, series, lung, slit = (json.loads(path.read_text()) for path in cases)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    refs, manifests, saved = {}, {}, {}
    for group, files in REFERENCES.items():
        for name in files:
            if name in PATCH_ORDER or group == 'pcm':
                manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    for group, run in (('single', series['single_branch_run']), ('series', lung['series_run']), ('lung', slit['lung_run']),
                       ('slit', radiation['slit_run']), ('wall', derivative['wall_run']), ('derivative', branch['derivative_run'])):
        manifests[group], refs[f'{group}.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    manifests['radiation'], refs['trace.patch'] = verified_artifact(*wall['radiation_run'], 'artifacts/candidate-radiation.patch')
    _, saved['upstream-radiation.csv'] = verified_artifact(*wall['radiation_run'], 'artifacts/upstream-radiation.csv')
    manifests['prefix'], refs['prefix-case.json'] = verified_artifact(*radiation['prefix_run'], 'artifacts/extended-prefix-case.json')
    manifests['branch'], refs['pharynx-trace.patch'] = verified_artifact(*case['branch_run'], 'artifacts/candidate-pharyngeal-entry.patch')
    for name in (*CONTROL_FILES, 'upstream-pharyngeal.csv'):
        _, saved[name] = verified_artifact(*case['branch_run'], f'artifacts/{name}')
    manifests['pharynx-balance'], saved['upstream-pharynx-balance.csv'] = verified_artifact(
        *branch['upstream_pressure_run'], 'artifacts/upstream-pharynx-balance.csv')
    for block in common['blocks']:
        name = f'block-{block}.wav'
        _, saved[name] = verified_artifact(*branch['derivative_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [*cases, WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *refs.values(), *saved.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, branch, radiation, common, refs, saved, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
