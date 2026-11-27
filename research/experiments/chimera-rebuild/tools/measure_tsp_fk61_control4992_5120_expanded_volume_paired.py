"""面積補間を揃えた2版で、体積差の展開式と放射を照合する。"""

import argparse
from difflib import unified_diff
from fractions import Fraction
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_tsp_fk61_control4992_5120_indexed_area_paired as paired


indexed, oral, volume = paired.indexed, paired.oral, paired.volume
lip, load, radiation, tsp = paired.lip, paired.load, paired.radiation, paired.tsp
CASE = radiation.WORKSPACE / 'cases/tsp-fk61-control4992-5120-expanded-volume-paired.json'
SIDES = ('upstream', 'research')
MODES = ('indexed', 'expanded')
OBSERVATIONS = ('nodes.csv', 'lip.f64le', 'branch.csv', 'wall.csv', 'compliance.csv',
                'ramp-step.csv', 'ramp-target.csv', 'centerline.csv', 'area-raw.csv', 'area-grid.csv')
ARCHIVED = ('render.npz', 'pcm-digests.json', *(f'indexed-{name}' for name in OBSERVATIONS))
SAVED = ('render.npz', 'pcm-digests.json', *(f'expanded-{name}' for name in OBSERVATIONS),
         'indexed-expanded-volume.patch')


def displaced_patch(root, measure, *, fixed):
    source = paired.NETWORK if fixed else volume.GEOMETRY
    path = root / source
    original = path.read_text()
    # 両版で直接補間が有効なときに限り、同じ節点で体積差を展開する。
    if fixed:
        paired.patch_upstream(root, measure)
        volume.insert_before(path, '                let mut a = if let Some((first, start)) = saved {',
                             '''                let old_area = area[k].max(min_a);
                let old_length = dx[k];
''')
        raw = '                    let raw = -(v - self.vol[k]) * inv_t;'
        volume.edit(path, raw, '''                    let raw = if saved.is_some() {
                        let new_area = a.max(min_a);
                        let displaced = (old_area - new_area) * old_length + new_area * (old_length - d);
                        displaced * inv_t
                    } else {
                        -(v - self.vol[k]) * inv_t
                    };''')
    else:
        indexed.patch_indexed_area(root, measure)
        volume.edit(path, 'use super::{SOUND_SPEED, Section, trim_tiny};',
                    'use super::{MIN_CELL_AREA_CM2, SOUND_SPEED, Section, trim_tiny};')
        volume.insert_before(path, '                let next_area = if let Some(start) = start {',
                             '''                let old_area = section.area_cm2.max(MIN_CELL_AREA_CM2);
                let old_length = section.length_cm;
''')
        raw = '                let raw = (cell.volume_cm3 - next_volume) / dt;'
        volume.edit(path, raw, '''                let raw = if start.is_some() {
                    let new_area = section.area_cm2.max(MIN_CELL_AREA_CM2);
                    let displaced = (old_area - new_area) * old_length
                        + new_area * (old_length - section.length_cm);
                    displaced / dt
                } else {
                    (cell.volume_cm3 - next_volume) / dt
                };''')
    return ''.join(unified_diff(original.splitlines(keepends=True), path.read_text().splitlines(keepends=True),
                               fromfile='a/' + source, tofile='b/' + source))


def expanded_raw(data, n, node, rate, fixed):
    floor = data['loads'][n]['area_floor']
    before, after = (data['cells'][sample, node] for sample in (n - 1, n))
    a0, a1 = (max(floor, row['area_cm2']) for row in (before, after))
    d0, d1 = (row['length_cm'] for row in (before, after))
    change = (a0 - a1) * d0 + a1 * (d0 - d1)
    return change * rate if fixed else change / (1 / rate)


def differences(a, b, measure):
    result = {name: paired.metrics(a[name], b[name], pcm=(name == 'pcm')) for name in ('mouth', 'pcm')}
    for name in ('lip_cm3_s', 'wall_cm3_s', 'nose_cm3_s', 'total_cm3_s', radiation.RADIATION):
        i = radiation.FIELDS.index(name)
        result[name] = paired.metrics(a['source'][:, i], b['source'][:, i])
    i = volume.pcm.COLUMNS.index('dc_removed')
    result['precast'] = paired.metrics(a['output'][:, i], b['output'][:, i])
    result['precast_at_focus'] = [float(row['output'][measure['focus_frame'], i]) for row in (a, b)]
    return result


def analyze(study, out, baselines, config, gain, coefficients):
    measure = study['measurement']
    rate, frames = (measure[key] for key in ('internal_sample_rate_hz', 'frames'))
    blocks, nodes, count = (measure[key] for key in ('area_focus_blocks', 'area_focus_nodes', 'control_internal_samples'))
    points = [(n, j) for block in blocks for n in range(block, block + count) for j in nodes]
    geometry_fields = volume.GEOMETRY_FIELDS
    data, render, errors, exact, spills, matched = {}, {}, {}, {}, {}, {}
    dynamics, first_local = {}, {}
    for side in SIDES:
        fixed = side == 'upstream'
        paths = dict(zip(MODES, (baselines[side], out / side), strict=True))
        data[side], render[side], errors[side], spills[side] = {}, {}, {}, {}
        for mode, path in paths.items():
            data[side][mode] = oral.read_capture(path, mode, measure)
            with np.load(path / 'render.npz', allow_pickle=False) as saved:
                render[side][mode] = {name: saved[f'{mode}_{name}'] for name in ('source', 'output', 'mouth', 'pcm')}
        control, revised = (data[side][mode] for mode in MODES)
        # 有理数参照は観測の幾何から旧体積と新体積を直接計算する。
        exact[side] = [oral.exact_raw(control, n, j, rate) for n, j in points]
        expected = {key: expanded_raw(revised, *key, rate, fixed) for key in points}
        for mode, capture in data[side].items():
            spills[side][mode] = [capture['cells'][key]['spill_cm3_s'] for key in points]
            error = np.array([float(Fraction(q) - ref) for q, ref in zip(spills[side][mode], exact[side], strict=True)])
            errors[side][mode] = {'rms_cm3_s': paired.rms(error), 'peak_cm3_s': float(np.max(np.abs(error)))}
        dynamics[side] = {
            mode: oral.local_replay(capture, measure, fixed, raw_overrides=expected if mode == 'expanded' else None)
            for mode, capture in data[side].items()
        }
        first_local[side] = {
            field: indexed.first_cell_difference(control, revised, field)
            for field in ('spill_cm3_s', 'pole1_cm3_s', 'pole2_cm3_s', 'new_pressure_dyn_cm2')
        }
        first_local[side]['branch'] = indexed.first_branch_difference(control, revised)
        for row in first_local[side].values():
            if row is not None:
                row['expanded'] = row.pop('indexed')
                row['indexed'] = row.pop('baseline')
        matched[side] = {
            'same_geometry': all(load.same_bits(control['grid'][name], revised['grid'][name]) for name in geometry_fields)
                and all((paths['indexed'] / f'indexed-{name}').read_bytes()
                        == (paths['expanded'] / f'expanded-{name}').read_bytes() for name in OBSERVATIONS[5:]),
            'spill_only_changed_at_registered_points': load.same_bits(
                np.array([row['spill_cm3_s'] for row in revised['cells'].values()]),
                np.array([expected.get(key, control['cells'][key]['spill_cm3_s']) for key in revised['cells']])),
        }
        for mode, path in paths.items():
            proof = tsp.read(path / 'pcm-digests.json')[mode]
            results = render[side][mode]
            coeff = coefficients['upstream' if fixed else 'candidate']
            matched[side][f'{mode}_full_pcm_and_output_chain'] = (
                proof['bit_equal'] and proof['ordinary'] == proof['probe'] == lip.pcm_digest(results['pcm'])
                and len(results['pcm']) == frames and len(results['mouth']) == frames * 2
                and all(np.all(np.isfinite(series)) for series in (*results.values(), *data[side][mode]['grid'].values()))
                and volume.output_checks({f'{mode}_{k}': v for k, v in results.items()}, mode, rate, config, gain,
                                         coeff, fixed=fixed))
        start = blocks[0]
        original, changed = (render[side][mode] for mode in MODES)
        matched[side]['same_render_before_first_intervention'] = all(
            load.same_bits(original[name][:stop], changed[name][:stop])
            for name, stop in (('mouth', start), ('source', start), ('output', start // 2), ('pcm', start // 2)))
    geometry_gap = [a - b for a, b in zip(*(exact[side] for side in SIDES), strict=True)]
    comparisons = {}
    for a in MODES:
        for b in MODES:
            row = differences(render['upstream'][a], render['research'][b], measure)
            gap = [Fraction(u) - Fraction(r) for u, r in zip(spills['upstream'][a], spills['research'][b], strict=True)]
            row.update(
                measured_raw_gap_rms_cm3_s=paired.rms(np.array([float(delta) for delta in gap])),
                arithmetic_residual_rms_cm3_s=paired.rms(
                    np.array([float(obs - ref) for obs, ref in zip(gap, geometry_gap, strict=True)])),
            )
            row['filtered_spill'] = paired.metrics(*(
                np.array([data[side][mode]['cells'][key]['pole2_cm3_s'] for key in points])
                for side, mode in zip(SIDES, (a, b), strict=True)))
            comparisons[f'{a}:{b}'] = row
    base, changed = (comparisons[f'{mode}:{mode}'] for mode in MODES)
    residual = 'arithmetic_residual_rms_cm3_s'
    hypotheses = {
        'expanded_reduces_rms_error_of_each_volume_source_by_at_least_100': all(
            row['expanded']['rms_cm3_s'] <= row['indexed']['rms_cm3_s'] / 100 for row in errors.values()),
        'paired_expanded_reduces_arithmetic_residual_rms_by_at_least_100': changed[residual] <= base[residual] / 100,
        'paired_expanded_pcm_first_remains_2937': changed['pcm']['first'] is not None
                                                 and changed['pcm']['first']['sample'] == measure['focus_frame'],
    }
    checks = {
        'geometry_and_ramp_state_unchanged': all(row['same_geometry'] for row in matched.values()),
        'expanded_raw_matches_and_out_of_scope_spill_unchanged': all(
            row['spill_only_changed_at_registered_points'] for row in matched.values()),
        'observed_volume_poles_branches_walls_pressure_and_mouth_replayed': not any(
            bad for side in dynamics.values() for mode in side.values() for bad in mode.values()),
        'ordinary_cli_and_output_chain_match': all(
            row[f'{mode}_full_pcm_and_output_chain'] for row in matched.values() for mode in MODES),
        'mouth_radiation_and_pcm_before_intervention_unchanged': all(
            row['same_render_before_first_intervention'] for row in matched.values()),
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'exact_geometry_gap_rms_cm3_s': paired.rms(
                np.array([float(delta) for delta in geometry_gap])),
            'source_error': errors, 'comparisons': comparisons, 'first_local_change': first_local,
            'within_version': {side: differences(*(render[side][mode] for mode in MODES), measure) for side in SIDES},
            'replay_errors': dynamics, 'invariants': matched}


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
    matched, output, upper_run, research_run = (tsp.open_run(study[key], revision) for key in
                                                ('matched', 'coefficients', 'indexed_upstream', 'indexed_research'))
    uid = study['measurement']['recording_id']
    spec = tsp.verified_path(matched, f'artifacts/{uid}/matched-case.json')
    config, config_path = radiation.saved_case(matched, lip.CONFIG)
    coeff = tsp.verified_path(output, 'artifacts/coefficients.json')
    retained = [tsp.verified_path(run, f'artifacts/{name}') for run in (upper_run, research_run) for name in ARCHIVED]
    baselines = {side: run[0] / 'artifacts' for side, run in zip(SIDES, (upper_run, research_run), strict=True)}
    dependencies = ('measure_tsp_fk61_lip_onset.py', 'measure_tsp_fk61_lip_front_radiation.py',
                    'measure_tsp_fk61_lip_front_terminal_branch.py', 'measure_tsp_fk61_oral_onset_inflow.py',
                    'measure_tsp_fk61_branch_first_difference.py', 'measure_tsp_fk61_pcm2937_terminal_load.py',
                    'measure_tsp_fk61_control5504_oral_history.py', 'tsp_fk61_lip_front_radiation_observation.py',
                    'tsp_fk61_terminal_branch_observation.py', 'tsp_fk61_lip_observation.py',
                    'tsp_fk61_oral_geometry_observation.py', 'measure_tsp_fine_variation.py',
                    'measure_fixed_voice_glottal_branch.py', 'measure_uniform_tube.py')
    inputs = [CASE, Path(__file__).resolve(), *(Path(module.__file__) for module in
              (paired, indexed, volume, paired.geometry, paired.area_targets)),
              spec, config_path, coeff, *retained,
              *(run[0] / 'manifest.json' for run in (matched, output, upper_run, research_run)),
              *radiation.candidate_sources(), lip.PROBE, lip.LOCAL, lip.TRACE_TOOL, lip.DICT, lip.EMBEDDED_DICTIONARY,
              lip.OUTPUT_PATCH, lip.SOURCE_PATCH, lip.observer.UPPER_PATCH, lip.observer.LOCAL_PATCH,
              ws / 'data/cmudict.txt.gz', ws / 'crates/vocal-core/tests/geometry_ramp.rs',
              *(ws / 'tools' / name for name in dependencies),
              *(upper / name for name in (paired.NETWORK, 'crates/chimera/src/voice/human_voice.rs',
                  'crates/chimera-cli/src/render.rs', 'Cargo.lock',
                  'crates/chimera/tests/airway.rs', 'crates/chimera/tests/airway_adversarial.rs'))]

    def measure(out, execute):
        for side in SIDES:
            (out / side).mkdir()
        name = SAVED[-1]
        scratch = out.parent / 'tmp'
        paired.capture(study, spec, out / 'upstream', execute, modes=('expanded',),
                       variant_patch=lambda root, m: displaced_patch(root, m, fixed=True), patch_filename=name,
                       scratch=scratch)
        volume.capture(study, spec, config, out / 'research', execute, modes=('expanded',), patched_modes=('expanded',),
                       variant_patch=lambda root, m: displaced_patch(root, m, fixed=False), patch_filename=name,
                       prepare=paired.area_targets.prepare, split=paired.area_targets.split_observations,
                       scratch=scratch)
        gain = tsp.read(spec)['speech_voice']['voice']['output_gain']
        return analyze(study, out, baselines, config, gain, tsp.read(coeff))

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
