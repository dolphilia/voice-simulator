"""隔離ビルドで2ブロックの代表面積を標本番号から直接補間する。"""

import argparse
from difflib import unified_diff
from fractions import Fraction
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_control4992_5120_area_targets as area_targets
import measure_tsp_fk61_node40_expanded_volume as volume


geometry, oral, load, terminal = area_targets.geometry, volume.oral, volume.load, volume.terminal
radiation, tsp, lip = volume.radiation, volume.tsp, volume.lip
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control4992-5120-indexed-area.json'
MODES = ('baseline', 'indexed')
PATCH = 'indexed-area.patch'
PRIOR_FILES = area_targets.SAVED_FILES[:-1]
SAVED_FILES = ('render.npz', 'pcm-digests.json', PATCH, *(f'{mode}-{tag}' for mode in MODES for tag in (
    'nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv', 'ramp-step.csv', 'ramp-target.csv',
    'centerline.csv', 'area-raw.csv', 'area-grid.csv')))


def patch_indexed_area(root, measure):
    path = root / volume.GEOMETRY
    original = path.read_text()
    edit, insert = volume.edit, volume.insert_before
    nodes = measure['area_focus_nodes']
    frames = measure['control_internal_samples']
    boundaries = ' | '.join(map(str, measure['area_focus_blocks']))
    starts = ', '.join(f'sections[{node}].area_cm2' for node in nodes)
    arms = '\n'.join(f'                    {node} => self.research_area_start.map(|area| area[{i}]),'
                     for i, node in enumerate(nodes))
    edit(path, '    remaining: usize,', f'''    remaining: usize,
    research_sample: usize,
    research_area_start: Option<[f64; {len(nodes)}]>,''')
    edit(path, '            remaining: 0,', '''            remaining: 0,
            research_sample: 0,
            research_area_start: None,''')
    insert(path, '        let scale = 1.0 / steps as f64;', f'''        self.research_area_start = (steps == {frames}
            && sections.len() > {max(nodes)}
            && matches!(self.research_sample, {boundaries}))
            .then(|| [{starts}]);
''')
    insert(path, '        if !self.enabled {', '        self.research_sample += 1;\n')
    edit(path, '                section.area_cm2 = (section.area_cm2 + cell.area_increment_cm2).max(0.0);',
         f'''                let start = match i {{
{arms}
                    _ => None,
                }};
                let next_area = if let Some(start) = start {{
                    start + ({frames} - self.remaining) as f64 * cell.area_increment_cm2
                }} else {{
                    section.area_cm2 + cell.area_increment_cm2
                }};
                section.area_cm2 = next_area.max(0.0);''')
    return ''.join(unified_diff(original.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                               fromfile='a/' + volume.GEOMETRY, tofile='b/' + volume.GEOMETRY))


def read_ramps(out, mode, measure):
    first, stop = measure['comparison_internal_samples']
    nodes = measure['nodes'][1:]
    steps = terminal.read_records(out / f'{mode}-ramp-step.csv', ('sample', 'node', *geometry.observer.STEP_FIELDS), 2,
                                  {(n, j) for n in range(first, stop) for j in nodes})
    targets, _ = geometry.read_targets(out / f'{mode}-ramp-target.csv',
        {(n, j) for n in measure['control_boundaries'] for j in nodes})
    return steps, targets


def exact_area_checks(recorded, steps, targets, measure):
    focus, errors = {}, []
    count = measure['control_internal_samples']
    for mode, data in recorded.items():
        focus[mode] = {}
        for n in measure['area_focus_blocks']:
            for j in measure['area_focus_nodes']:
                beginning = Fraction(steps[mode][n, j]['area'])
                target = Fraction(targets[mode][n, j]['area'])
                residuals = []
                for i in range(1, count + 1):
                    exact = beginning + (target - beginning) * Fraction(i, count)
                    value = data['cells'][n + i - 1, j]['area_cm2']
                    residuals.append(float(Fraction(value) - exact))
                    if mode == 'indexed' and value != float(exact):
                        errors.append((n + i - 1, j))
                focus[mode][f'{n}:{j}'] = {
                    'start_cm2': float(beginning), 'target_cm2': float(target), 'end_cm2': data['cells'][n + count - 1, j]['area_cm2'],
                    'end_residual_cm2': residuals[-1], 'max_residual_cm2': max(map(abs, residuals))}
    return focus, errors


def first_cell_difference(baseline, indexed, field):
    for (n, j), row in baseline['cells'].items():
        other = indexed['cells'][n, j]
        if row[field] != other[field]:
            return {'sample': n, 'node': j, 'baseline': row[field], 'indexed': other[field]}
    return None


def first_branch_difference(baseline, indexed):
    for (n, left, right), row in baseline['branch'].items():
        other = indexed['branch'][n, left, right]
        if row['flow'] != other['flow']:
            return {'sample': n, 'edge': [left, right], 'baseline': row['flow'], 'indexed': other['flow']}
    return None


def compare_mouth(a, b, start=0):
    diff = volume.first_diff.first_change(a, b, offset=start)
    if diff is None:
        return None
    return {'sample': diff['sample'], 'reference': diff['upstream'], 'comparison': diff['comparison'],
            'peak_error_cm3_s': float(np.max(np.abs(a - b)))}


def pcm_diagnostics(out, prior, archived, frame):
    column = volume.pcm.COLUMNS.index('dc_removed')
    with np.load(out / 'render.npz', allow_pickle=False) as data, np.load(prior / 'prefix.npz', allow_pickle=False) as reference:
        baseline, indexed = (data[f'{mode}_pcm'].astype(np.float64) for mode in MODES)
        precast = {mode: float(data[f'{mode}_output'][frame, column]) for mode in MODES}
        precast['upstream'] = float(reference['upstream_output'][frame, column])
    errors = {'baseline_vs_upstream': baseline - archived['upstream'],
              'indexed_vs_upstream': indexed - archived['upstream'],
              'indexed_vs_baseline': indexed - baseline}
    baseline_error, indexed_error = (np.abs(errors[f'{mode}_vs_upstream']) for mode in MODES)
    midpoint = (baseline[frame] + float(archived['upstream'][frame])) / 2
    return {
        'rms': {key: float(np.sqrt(np.mean(value ** 2))) for key, value in errors.items()},
        'frames_closer_to_upstream': int(np.count_nonzero(indexed_error < baseline_error)),
        'frames_farther_from_upstream': int(np.count_nonzero(indexed_error > baseline_error)),
        'focus_frame': frame, 'precast': precast, 'midpoint': float(midpoint),
        'from_midpoint': {key: value - float(midpoint) for key, value in precast.items()},
    }


def analyze(study, out, prior, archived, config, gain, coefficients, proof):
    measure = study['measurement']
    rate, frames, prefix_frames = (measure[k] for k in ('internal_sample_rate_hz', 'frames', 'prefix_frames'))
    start = measure['area_focus_blocks'][0]
    recording = {mode: oral.read_capture(out, mode, measure) for mode in MODES}
    steps, targets = {}, {}
    for mode in MODES:
        steps[mode], targets[mode] = read_ramps(out, mode, measure)
    baseline, indexed = (recording[mode] for mode in MODES)
    old_measure = measure | {'comparison_internal_samples': measure['previous_comparison_internal_samples']}
    previous = {mode: oral.read_capture(prior, mode, old_measure) for mode in ('upstream', 'trial')}
    earlier = area_targets.inlet.shared_capture(previous['trial'], baseline)
    ramp_errors = {mode: geometry.verify_ramps(recording[mode], steps[mode], targets[mode], measure,
                                               indexed_area=(mode == 'indexed')) for mode in MODES}
    exact, exact_errors = exact_area_checks(recording, steps, targets, measure)
    dynamics = {mode: oral.local_replay(recording[mode], measure, False) for mode in MODES}
    with np.load(out / 'render.npz', allow_pickle=False) as data:
        states = dict(data)
    with np.load(prior / 'prefix.npz', allow_pickle=False) as before:
        shared_prefix = (load.same_bits(states['baseline_source'], before['trial_source'])
                         and load.same_bits(states['baseline_output'], before['trial_output'])
                         and load.same_bits(states['baseline_pcm'][:prefix_frames], before['trial_pcm'])
                         and load.same_bits(archived['upstream'][:prefix_frames], before['upstream_pcm']))
        upstream_mouth = before['upstream_source'][:, radiation.FIELDS.index('lip_cm3_s')]
    mouth = {
        'indexed_vs_baseline_full': compare_mouth(states['baseline_mouth'], states['indexed_mouth']),
        **{f'{mode}_vs_upstream_prefix': compare_mouth(upstream_mouth, states[f'{mode}_mouth'][:len(upstream_mouth)])
           for mode in MODES},
    }
    pcm = {f'{mode}_vs_upstream': volume.pcm_delta(archived['upstream'], states[f'{mode}_pcm']) for mode in MODES}
    pcm['indexed_vs_baseline'] = volume.pcm_delta(states['baseline_pcm'], states['indexed_pcm'])
    chronology = {field: first_cell_difference(baseline, indexed, field)
                  for field in ('area_cm2', 'volume_cm3', 'spill_cm3_s', 'pole2_cm3_s', 'new_pressure_dyn_cm2')}
    chronology['branch_flow'] = first_branch_difference(baseline, indexed)
    checkpoint = measure['area_focus_blocks'][1]
    differences = {str(j): {
        mode: steps[mode][checkpoint, j]['area'] - previous['upstream']['cells'][checkpoint - 1, j]['area_cm2']
        for mode in MODES} for j in measure['area_focus_nodes']}
    baseline_first = pcm['baseline_vs_upstream']['first_unequal_sample']
    indexed_first = pcm['indexed_vs_upstream']['first_unequal_sample']
    mouth_first = mouth['indexed_vs_baseline_full']
    unchanged_targets = targets['baseline'] == targets['indexed']
    unchanged_minimum_length = all(load.same_bits(baseline['grid'][field], indexed['grid'][field])
                                   for field in ('minimum_cm2', 'length_cm'))
    hypotheses = {
        'indexed_reaches_targets_without_accumulated_error': all(row['end_residual_cm2'] == 0 for row in exact['indexed'].values()),
        'indexed_reduces_upstream_5120_start_discrepancy': all(abs(row['indexed']) < abs(row['baseline']) for row in differences.values()),
        'mouth_change_follows_area_intervention': mouth_first is not None and mouth_first['sample'] >= start,
        'indexed_delays_first_pcm_difference_from_upstream': indexed_first is None or indexed_first > baseline_first,
        'indexed_does_not_increase_peak_pcm_error': pcm['indexed_vs_upstream']['peak_error']
                                                    <= pcm['baseline_vs_upstream']['peak_error'],
    }
    checks = {
        'ordinary_and_observed_pcm_match_for_each_build': all(
            len(states[f'{mode}_pcm']) == frames and proof[mode]['bit_equal']
            and proof[mode]['ordinary'] == proof[mode]['probe'] == lip.pcm_digest(states[f'{mode}_pcm']) for mode in MODES),
        'previous_baseline_and_upstream_pcm_reproduced': (
            all(earlier.values()) and shared_prefix and load.same_bits(states['baseline_pcm'], archived['trial'])
            and baseline_first == measure['focus_frame']),
        'indexed_area_matches_exact_line_and_keeps_other_geometry': (
            not exact_errors and not any(ramp_errors.values()) and unchanged_targets and unchanged_minimum_length),
        'local_volume_wave_and_output_replayed': not any(any(row.values()) for row in dynamics.values())
            and all(volume.output_checks(states, mode, rate, config, gain, coefficients) for mode in MODES),
        'before_intervention_mouth_and_pcm_match': (
            load.same_bits(states['baseline_mouth'][:start], states['indexed_mouth'][:start])
            and load.same_bits(states['baseline_pcm'][:start // 2], states['indexed_pcm'][:start // 2])
            and (chronology['area_cm2'] is None or chronology['area_cm2']['sample'] >= start)),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'geometry': exact, 'geometry_errors': exact_errors,
            'ramp_errors': ramp_errors, 'dynamics_errors': dynamics, 'start_area_minus_upstream_cm2': differences,
            'local_first_difference': chronology, 'mouth': mouth, 'pcm': pcm}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('試験ビルドにCHIMERA_RUN_STORAGE=rtl9210bを指定してください')
    matched, bernstein, prior, output = (tsp.open_run(study[key], revision)
                                        for key in ('matched', 'bernstein', 'previous_focus', 'coefficients'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    reference_pcm = tsp.verified_path(matched, 'artifacts/matched-pcm.npz')
    trial_pcm = tsp.verified_path(bernstein, 'artifacts/render.npz')
    coefficients = tsp.verified_path(output, 'artifacts/coefficients.json')
    retained = [tsp.verified_path(prior, f'artifacts/{name}') for name in PRIOR_FILES]
    dependencies = ['measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_front_radiation.py',
                    'measure_tsp_fk61_lip_front_terminal_branch.py', 'measure_tsp_fk61_oral_onset_inflow.py',
                    'measure_tsp_fk61_branch_first_difference.py', 'measure_tsp_fk61_pcm2937_terminal_load.py',
                    'measure_tsp_fk61_lip_volume_increment.py', 'measure_tsp_fk61_control5504_oral_history.py',
                    'measure_tsp_fine_variation.py', 'tsp_fk61_lip_observation.py',
                    'tsp_fk61_lip_front_radiation_observation.py', 'tsp_fk61_terminal_branch_observation.py',
                    'tsp_fk61_lower_lip_bernstein_observation.py', 'tsp_fk61_oral_geometry_observation.py',
                    'measure_fixed_voice_glottal_branch.py', 'measure_uniform_tube.py']
    inputs = [CASE, Path(__file__).resolve(), Path(volume.__file__), Path(geometry.__file__), Path(area_targets.__file__),
              spec, config_path, reference_pcm, trial_pcm, coefficients, *retained,
              *(run[0] / 'manifest.json' for run in (matched, bernstein, prior, output)),
              *radiation.candidate_sources(), lip.EMBEDDED_DICTIONARY, lip.DICT, lip.LOCAL, lip.TRACE_TOOL,
              lip.observer.LOCAL_PATCH, ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in dependencies)]

    def measure(out, execute):
        archived = volume.pcm.archived_pcm(reference_pcm, uid)
        with np.load(trial_pcm, allow_pickle=False) as saved:
            archived['trial'] = saved['pcm']
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        proof = volume.capture(study, spec, config, out, execute, modes=MODES, variant_patch=patch_indexed_area,
                               patch_filename=PATCH, prepare=area_targets.prepare, split=area_targets.split_observations)
        return analyze(study, out, prior[0] / 'artifacts', archived, config, gain, tsp.read(coefficients)['candidate'], proof)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
