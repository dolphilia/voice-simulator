"""咽頭入口の壁面積の演算順だけを変え、放射とPCMを比較する。"""

import argparse
import json
from math import pi, sqrt
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_fixed_voice_glottal_branch import NATIVE_NET, f64
from measure_fixed_voice_lung_port_momentum import CASE as LUNG_CASE
from measure_fixed_voice_radiation_balance import (
    CASE as RADIATION_CASE, PREFIX_CASE, compare_terms, read_measurements, validate, wall_events,
)
from measure_fixed_voice_tracheal_momentum import (
    BALANCE_CASE, CASE as SINGLE_CASE, PATCH_ORDER, REFERENCES, ROOT, capture, pcm_report,
    read_rows, record_measurement, same, source_inputs, verified_artifact,
)
from measure_fixed_voice_tracheal_series_momentum import CASE as SERIES_CASE
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/fixed-voice-pharyngeal-wall-surface-48000.json'
CONTROL_FILES = ('candidate-internal.csv', 'candidate-raw.txt', 'candidate-radiation.csv', 'candidate-radiating-wall.csv')
SURFACE = '                let surface = section.wall_surface();'
SURFACE_EDITS = {NATIVE_NET: (
    ('        let mut wall_radiation = 0.0;',
     '        let pharynx_entry = glottis.map(|branch| self.branches[branch].nodes[1]);\n'
     '        let mut wall_radiation = 0.0;'),
    (SURFACE, '''                let surface = if pharynx_entry == Some(node) {
                    let perimeter = section.perimeter_factor * 2.0 * PI.sqrt();
                    perimeter * section.area_cm2.max(MIN_CELL_AREA_CM2).sqrt() * section.length_cm
                } else {
                    section.wall_surface()
                };'''),
)}


def surface_check(control, revised, node):
    lookup = {(row['node'], row['internal_sample']): row for row in control}
    q = f64(f64(f64(1.25) * 2) * f64(sqrt(pi)))
    sampled = []
    for row in revised:
        previous = lookup[row['node'], row['internal_sample']]
        if row['node'] == node:
            area = f64(sqrt(row['area']))
            modeled = float(f64(f64(q * area) * f64(row['length'])))
            sampled.append(same(row['surface'], modeled))
        elif not same(row['surface'], previous['surface']):
            return False
    return bool(sampled) and all(sampled)


def compare_points(case, control, revised, upstream, samples, fs, pcm_internal_sample):
    a, b, u = ({row['internal_sample']: row for row in rows} for rows in (control, revised, upstream))
    first = next((i for i in samples if not same(b[i]['derivative'], u[i]['derivative'])), None)
    first_frame = next((i for i in samples if i % 2 and not same(b[i]['derivative'], u[i]['derivative'])), None)
    onset, following = case['first_wall_flow_sample'], case['following_sample']
    expected = compare_terms(a[onset], u[onset], fs)
    wall_only = next(entry['estimate'] for entry in expected['substitutions'] if entry['terms'] == ('wall',))
    checks = {
        'wall_sums_equal_upstream_at_registered_samples': all(same(b[i]['wall'], u[i]['wall']) for i in (onset, following)),
        'first_derivative_residual_matches_wall_only_replacement': same(b[onset]['derivative'], wall_only),
        'following_derivative_equal_upstream': same(b[following]['derivative'], u[following]['derivative']),
    }
    event_indices = dict.fromkeys(i for i in (onset, following, first, first_frame, pcm_internal_sample) if i is not None)
    events = {str(i): {'control': a[i], 'wall_surface': b[i], 'upstream': u[i],
                      'remaining_difference': None if same(b[i]['derivative'], u[i]['derivative'])
                      else compare_terms(b[i], u[i], fs)} for i in event_indices}
    return checks, {'first_internal_difference': first, 'first_frame_end_difference': first_frame, 'events': events}


def measure(case, common, radiation, refs, saved, copies, snapshot, out, execute):
    hashes = capture(common, refs, copies, snapshot, out, execute,
                     patch_order=(*PATCH_ORDER, 'single.patch', 'series.patch', 'lung.patch', 'slit.patch', 'trace.patch'),
                     variant_edits=SURFACE_EDITS)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'airway', '--test', 'airway_adversarial'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    fs = common['internal_rate_hz']
    samples = sorted({i for a, b in radiation['windows'] for i in range(a, b)})
    control, control_walls = read_measurements(out / 'control', 'candidate', samples)
    revised, revised_walls = read_measurements(out / 'reordered', 'candidate', samples)
    upstream = read_rows(saved['upstream-radiation.csv'])
    upstream_walls = read_rows(saved['upstream-radiating-wall.csv'])
    native_clocks = [{row['internal_sample']: row for row in read_rows(out / side / 'candidate-internal.csv')}
                     for side in ('control', 'reordered')]
    checks = {
        'archived_control_traces': all(sha256(out / 'control' / name) == sha256(saved[name]) for name in CONTROL_FILES),
        'surface_formula_and_scope': surface_check(control_walls, revised_walls, case['pharynx_entry_node']),
        'control_wall_and_radiation_equations': validate(control, control_walls, native_clocks[0], fs, False),
        'reordered_wall_and_radiation_equations': validate(revised, revised_walls, native_clocks[1], fs, False),
    }
    pcm_internal_sample = radiation['pcm_probe_internal_sample']
    more_checks, radiation_results = compare_points(case, control, revised, upstream, samples, fs, pcm_internal_sample)
    checks.update(more_checks)
    pcm_checks, pcm = pcm_report(common, refs, out, archived_control={
        block: saved[f'block-{block}.wav'] for block in common['blocks']})
    checks.update(pcm_checks)
    frame = pcm_internal_sample // (fs // common['sample_rate_hz'])
    original, changed = (wavfile.read(out / mode / 'block-128.wav')[1] for mode in ('control', 'reordered'))
    upstream_pcm = np.fromfile(refs['upstream-voice.f32'], dtype='<f4')
    pcm_point = {'frame': frame, 'control': float(original[frame]), 'wall_surface': float(changed[frame]),
                 'upstream': float(upstream_pcm[frame])}
    return {'checks': checks, 'build_sha256': hashes, **radiation_results,
            'first_wall_differences': wall_events(revised_walls, upstream_walls, samples),
            'pcm_probe_frame': pcm_point, 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    slit_path = WORKSPACE / 'cases/fixed-voice-glottal-slit-48000.json'
    case, radiation, common, base, series, lung, slit = (json.loads(path.read_text()) for path in (
        CASE, RADIATION_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, slit_path))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    groups = {**base['references'], 'onset': common['onset_run'], 'pcm': common['pcm_input_run']}
    patch_names = {group: [name for name in names if name in PATCH_ORDER or group == 'pcm'] for group, names in REFERENCES.items()}
    refs, manifests, saved = {}, {}, {}
    for group, names in patch_names.items():
        for name in names:
            manifests[group], refs[name] = verified_artifact(*groups[group], f'artifacts/{name}')
    extra = (('single', series['single_branch_run']), ('series', lung['series_run']),
             ('lung', slit['lung_run']), ('slit', radiation['slit_run']))
    for group, run in extra:
        manifests[group], refs[f'{group}.patch'] = verified_artifact(*run, 'artifacts/candidate-tracheal-history.patch')
    manifests['prefix'], refs['prefix-case.json'] = verified_artifact(*radiation['prefix_run'], 'artifacts/extended-prefix-case.json')
    manifests['radiation'], refs['trace.patch'] = verified_artifact(*case['radiation_run'], 'artifacts/candidate-radiation.patch')
    for name in (*CONTROL_FILES, 'upstream-radiation.csv', 'upstream-radiating-wall.csv'):
        _, saved[name] = verified_artifact(*case['radiation_run'], f'artifacts/{name}')
    for block in common['blocks']:
        name = f'block-{block}.wav'
        _, saved[name] = verified_artifact(*radiation['slit_run'], f'artifacts/reordered/{name}')
    copies, archived, snapshot = source_inputs(manifests['scaled'])
    loaded = (Path(file).resolve() for module in tuple(sys.modules.values())
              if (file := getattr(module, '__file__', None)))
    tools = sorted({path for path in loaded if path.parent == WORKSPACE / 'tools' and path.suffix == '.py'})
    inputs = [CASE, RADIATION_CASE, SINGLE_CASE, BALANCE_CASE, SERIES_CASE, LUNG_CASE, slit_path,
              WORKSPACE / 'LICENSE-CHIMERA', *archived, *tools, *manifests.values(), *refs.values(), *saved.values()]
    return record_measurement(args.run_id, CASE, inputs, {'case_id': case['id'], 'upstream_revision': revision},
                              lambda out, run: measure(case, common, radiation, refs, saved, copies, snapshot, out, run),
                              command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
