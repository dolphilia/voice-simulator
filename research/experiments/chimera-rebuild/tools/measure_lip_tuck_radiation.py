"""前突した下唇の断面段差を、有声時の気道とPCMまで追う。"""

import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess

import numpy as np
from scipy.io import wavfile

import measure_articulation as artic
import measure_pcm_output as pcm
import measure_tract_control as tract
import measure_uniform_tube as shared
import measure_voiced_vowel_motion as voiced
from upstream_baseline import WORKSPACE, UPSTREAM, sha256


CASE = WORKSPACE / 'cases/lip-tuck-voiced-radiation.json'
CLI = ['cargo', 'run', '--locked', '--release', '-q', '-p', 'vocal-cli', '--']
DETAIL = ('labiodental', 'lip_pressure_dyn_cm2', 'wall_radiation_cm3_s')
SOURCES = ('output_sample_rate_hz', 'pressure_cm_h2o', 'gate', 'f0_hz', 'breathiness', 'tension', 'output_gain')
APPLIED = ('applied_area_cm2', 'applied_minimum_cm2', 'pressure_dyn_cm2')


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


def load_samples(path, indices, period, cells, extra_columns=()):
    with path.open() as file:
        columns = tuple(file.readline().strip().split(','))
        values = np.loadtxt(file, delimiter=',', ndmin=2)
    expected = (*voiced.COLUMNS, *voiced.ARTICULATION, *DETAIL,
                *(f'oral_{cell}_{metric}' for cell in cells for metric in APPLIED), *extra_columns)
    if (columns != expected or values.shape != (len(indices), len(expected))
            or not np.isfinite(values).all() or not np.array_equal(values[:, 0], indices)
            or not np.array_equal(values[:, 1], indices // period)):
        raise ValueError(f'{path.name} の列・制御時刻が一致しません')
    return dict(zip(columns, values.T, strict=True))


def output_names(folder, block):
    return folder / f'block-{block}.wav', folder / f'block-{block}.csv'


def capture_candidate(path, folder, blocks, indices, period, cells, execute, *, extra_columns=()):
    trace = folder / 'candidate-samples.csv'
    metadata = folder / 'settings.json'
    execute([*CLI, 'inspect', str(path)], stdout=metadata)
    execute([*CLI, 'render', str(path), str(trace)])
    for block in blocks:
        wave_path, output_path = output_names(folder, block)
        execute([*CLI, 'render-pcm', str(path), str(wave_path), str(output_path), str(block)])
    wave_path, output_path = output_names(folder, blocks[0])
    rate, wave = wavfile.read(wave_path)
    columns, output = pcm.read_columns(output_path, len(wave), len(pcm.OUTPUT_COLUMNS))
    if columns != pcm.OUTPUT_COLUMNS or not np.array_equal(output['pcm_f32'].astype(np.float32), wave):
        raise ValueError('出力段のCSVとWAVが一致しません')
    same_blocks = all(tuple(map(sha256, output_names(folder, blocks[0])))
                      == tuple(map(sha256, output_names(folder, block))) for block in blocks[1:])
    return (load_samples(trace, indices, period, cells, extra_columns), wave, rate, output,
            json.loads(metadata.read_text())['voice'], same_blocks)


def capture_upstream(executable, case, plan, label, folder, block, indices, period, cells, execute, *, rate_limit=None,
                     alternate_host=False):
    trace = folder / f'{label}-samples.csv'
    raw = folder / f'{label}.f32'
    prefix = [str(executable), str(plan), 'voice', *map(str, (case['voice'][key] for key in SOURCES))]
    suffix = [','.join(map(str, cells)), *([] if rate_limit is None else [str(rate_limit)])]
    execute([*prefix, '1', str(raw), str(trace), *suffix], cwd=UPSTREAM)
    same_host = True
    if alternate_host:
        other = folder / f'{label}-host.f32'
        execute([*prefix, str(block), str(other), '-', *suffix], cwd=UPSTREAM)
        same_host = sha256(raw) == sha256(other)
    rate = case['voice']['output_sample_rate_hz']
    wave = np.fromfile(raw, dtype='<f4')
    wavfile.write(folder / f'{label}.wav', rate, wave)
    return load_samples(trace, indices, period, cells), wave, same_host


def geometry(case, executable, plan, folder, execute):
    path = folder / 'geometry-case.json'
    write_json(path, {**{k: v for k, v in case.items() if k != 'voice'},
                      'measurement': {'frames': case['measurement']['frames']}})
    target, base = (folder / f'{name}-targets.csv' for name in ('candidate', 'upstream'))
    execute([*CLI, 'render', str(path), str(target)])
    execute([str(executable), str(plan), 'tract-with-contact'], cwd=UPSTREAM, stdout=base)
    cfg = case['measurement']['dynamic_lip_tuck']
    counts, frames = cfg['tube_cells'], case['measurement']['frames']
    current, cells = tract.read_trace(target, counts, frames)
    reference, _ = tract.read_trace(base, counts, frames)
    instance = case['articulators']
    rate = instance['sample_rate_hz']
    exact = tract.independent_trace(current, cells, instance['control_block_samples'] / rate,
                                    rate, folder / 'independent-targets.csv')
    tolerance = cfg['geometry_absolute_lt']
    compared = tract.compare(current, reference, cells,
                             {'length_absolute_lt_cm': tolerance, 'area_absolute_lt_cm2': tolerance})
    return current, reference, exact, compared


def applied_error(targets, signal, cells, period, pharynx, factor, *, unlimited=False):
    source = [0, 1] if unlimited else [2, 3]
    fractions = np.arange(factor, period + 1, factor)[None, :, None] / period
    step_starts = np.array(list(targets.values())[:-1])
    step_ends = np.array(list(targets.values())[1:])
    errors = {}
    for cell in cells:
        index = pharynx + cell
        before, after = (table[:, index, source] for table in (step_starts, step_ends))
        values = before[:, None, :] + (after - before)[:, None, :] * fractions
        measured = np.column_stack([signal[f'oral_{cell}_{metric}'] for metric in APPLIED[:2]])
        errors[f'oral_{cell}'] = float(abs(values.reshape(-1, 2) - measured).max())
    before, after = [table[:, pharynx, 5] for table in (step_starts, step_ends)]
    length = before[:, None] + (after - before)[:, None] * fractions[:, :, 0]
    oral_count = step_ends.shape[1] - pharynx
    errors['oral_dx_cm'] = float(abs(length.ravel() / oral_count - signal['oral_dx_cm']).max())
    return errors


def geometry_change(targets, signal, control, period, pharynx, cell, cfg):
    a = targets[(control - 1, 'apply')][pharynx + cell, :4]
    b = targets[(control, 'apply')][pharynx + cell, :4]
    d = b - a
    measured = np.array([signal[f'oral_{cell}_{metric}'][control * period] for metric in APPLIED[:2]])
    return {'raw_and_limited_before_cm2': a.tolist(), 'raw_and_limited_after_cm2': b.tolist(),
            'raw_and_limited_step_cm2': d.tolist(), 'first_internal_sample_cm2': measured.tolist(),
            'limited_to_raw_step_ratio': (d[2:] / d[:2]).tolist(),
            'first_sample_to_raw_step_ratio': ((measured - a[2:]) / d[:2]).tolist(),
            'raw_jump_registered': bool(cfg['raw_area_jump_cm2'][0] <= d[0] <= cfg['raw_area_jump_cm2'][1]
                                        and cfg['raw_minimum_jump_cm2'][0] <= d[1] <= cfg['raw_minimum_jump_cm2'][1])}


def onset_difference(delta, threshold):
    hits = np.flatnonzero(np.abs(delta) > threshold)
    return int(hits[0]) if hits.size else None


def band_rms(signal, rate, splits):
    window = np.hanning(len(signal))
    energy = abs(np.fft.rfft(signal * window))**2 / (len(signal) * np.sum(window**2))
    energy[1:] *= 2
    if len(signal) % 2 == 0:
        energy[-1] /= 2
    frequency = np.fft.rfftfreq(len(signal), 1 / rate)
    bounds = np.searchsorted(frequency, splits)
    return [float(np.sqrt(part.sum())) for part in np.split(energy, bounds)]


def contrasts(a, b, wave_a, wave_b, cfg, at, rate):
    fields = {
        'oral_pressure': (f'oral_{cfg["affected_cell"]}_pressure_dyn_cm2', 'pressure_dyn_cm2'),
        'lip_pressure': ('lip_pressure_dyn_cm2', 'pressure_dyn_cm2'),
        'glottis_supra_pressure': ('pressure_supra_dyn_cm2', 'pressure_dyn_cm2'),
        'lip_flow': ('lip_flow_cm3_s', 'lip_flow_cm3_s'),
        'radiation_derivative': ('radiation_derivative_cm3_s2', 'radiation_derivative_cm3_s2'),
    }
    differences = {key: (a[column] - b[column], cfg['detection_floors'][limit])
                   for key, (column, limit) in fields.items()}
    differences['pcm'] = (wave_a.astype(float) - wave_b, cfg['detection_floors']['pcm'])
    first = {key: onset_difference(row, floor) for key, (row, floor) in differences.items()}
    windows = []
    for start, stop in cfg['windows_from_crossing_ms']:
        lo, hi = (at + round(rate * t / 1000) for t in (start, stop))
        if not 0 <= lo < hi <= len(wave_a):
            raise ValueError('比較の観測窓が出力フレームの範囲外です')
        selected = {key: row[lo:hi] for key, (row, _) in differences.items()}
        windows.append({'start_output_frame': lo, 'stop_output_frame': hi,
                        'rms': {key: float(np.sqrt(np.mean(row**2))) for key, row in selected.items()},
                        'peak': {key: float(abs(row).max()) for key, row in selected.items()},
                        'pcm_band_rms': band_rms(selected['pcm'], rate, cfg['spectral_split_hz'])})
    return {'first_output_frame_over_floor': first, 'windows': windows}


def compare_samples(candidate, upstream, cfg):
    geometry_fields = (*voiced.GEOMETRY, *voiced.ARTICULATION, 'labiodental',
                       *(key for key in candidate if '_applied_' in key))
    geometry = {key: voiced.compare(candidate[key], upstream[key], cfg['geometry_absolute_lt'])
                for key in geometry_fields}
    acoustic = {key: shared.compare_series(candidate[key], upstream[key], cfg['component_peak_relative_error_lt'])
                for key in candidate if key not in (*geometry_fields, 'internal_sample', 'control_frame')}
    first = min(((value['first_sample_over_tolerance'], name) for name, value in (geometry | acoustic).items()
                 if value['first_sample_over_tolerance'] is not None), default=None)
    return {'geometry': geometry, 'acoustic': acoustic, 'first_over_tolerance': first,
            'first_exact_stage_differences': {
                'geometry': voiced.first_exact_difference(candidate, upstream, geometry_fields, slice(None)),
                'acoustic': voiced.first_exact_difference(candidate, upstream, acoustic, slice(None)),
            }}


def compress_traces(artifacts):
    for path in sorted(artifacts.glob('*/*-samples.csv')):
        with path.open('rb') as source, path.with_suffix('.csv.gz').open('wb') as stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as compressed:
                shutil.copyfileobj(source, compressed)
        path.unlink()


def measure(case, fixed_event, artifacts, execute):
    cfg = case['measurement']['dynamic_lip_tuck']
    voice, controls = case['voice'], case['articulators']
    rate, internal_rate, period = voice['output_sample_rate_hz'], controls['sample_rate_hz'], controls['control_block_samples']
    factor = internal_rate // rate
    count = period * case['measurement']['frames']
    indices, output_indices = np.arange(count), np.arange(factor - 1, count, factor)
    cells, blocks = case['measurement']['voiced_tract_oral_cells'], cfg['host_block_sizes']
    event = cfg['first_crossing_control_frame']
    at, pharynx = event * period // factor, cfg['tube_cells']['pharynx']

    for suite, name in [('airway_adversarial', 'fast_but_articulator_limited_closure_gives_bounded_piston_pressure'),
                        ('engine', 'output_does_not_depend_on_the_host_block_size')]:
        execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', suite, name],
                cwd=UPSTREAM, stdout=artifacts / f'upstream-{suite}.log')
    executable = shared.build_upstream_probe(artic.PROBE, artifacts, execute)
    result, samples, tracks, waves = {}, {}, {}, {}
    checks = {}
    for moving in (False, True):
        tag = 'cross' if moving else 'hold'
        folder = artifacts / tag
        folder.mkdir()
        variant = case if moving else {**case, 'id': case['id'] + '-hold', 'articulators': {**controls, 'events': []}}
        path, plan = folder / 'case.json', folder / 'upstream-events.txt'
        write_json(path, variant)
        artic.write_upstream_events(variant, plan)
        candidate, wave, actual_rate, output, metadata, host_equal = capture_candidate(
            path, folder, blocks if moving else blocks[:1], indices, period, cells, execute)
        reference, ref_wave, ref_host = capture_upstream(
            executable, variant, plan, 'upstream', folder, blocks[-1], output_indices, period, cells, execute,
            alternate_host=moving)
        if (any(data.shape != (len(output_indices),) or data.dtype != np.float32 or not np.isfinite(data).all()
                for data in (wave, ref_wave)) or actual_rate != rate or metadata['frames'] != len(output_indices)):
            raise ValueError('PCMのフレーム、レート、型を照合できません')
        aligned = {key: value[output_indices] for key, value in candidate.items()}
        measured = compare_samples(aligned, reference, cfg)
        output_check = voiced.independently_render(candidate, output, wave, rate, factor,
                                                  voice['output_gain'], metadata, cfg)
        pcm_diff = voiced.compare(wave, ref_wave, cfg['pcm_absolute_lt'])
        total = sum(candidate[key] for key in ('wall_radiation_cm3_s', 'lip_flow_cm3_s', 'nose_flow_cm3_s'))
        radiation_error = float(abs(np.diff(total, prepend=0.0) * internal_rate
                                   - candidate['radiation_derivative_cm3_s2']).max())
        result[tag] = {'upstream': measured, 'pcm': pcm_diff, 'radiation_error_cm3_s2': radiation_error,
                       'independent_output': output_check}
        checks.update({
            f'{tag}_upstream_voice_and_geometry': measured['first_over_tolerance'] is None and pcm_diff['status'],
            f'{tag}_radiation_identity': radiation_error < cfg['independent_radiation_max_absolute_error_lt_cm3_s2'],
            f'{tag}_independent_pcm_and_host_blocks': host_equal and ref_host
                                                     and all(item['status'] for item in output_check.values()),
            f'{tag}_voiced_and_nasal_port_closed': bool(np.min(candidate['glottal_voicing'][event * period:]) >= cfg['minimum_voicing']
                                                       and not np.any(candidate['nose_flow_cm3_s'])),
        })
        samples[tag], tracks[tag], waves[tag] = candidate, (aligned, reference), (wave, ref_wave)

    folder = artifacts / 'cross'
    candidate, upstream, limits, geometry_comparison = geometry(case, executable, folder / 'upstream-events.txt', folder, execute)
    unlimited, unlimited_wave, _ = capture_upstream(
        executable, case, folder / 'upstream-events.txt', 'upstream-unlimited', folder, blocks[0],
        output_indices, period, cells, execute, rate_limit=cfg['controls']['upstream_unlimited_rate_cm2_s'])
    start = event * period
    art_data = artic.independent_trace(case, period / internal_rate, folder / 'independent-articulators.csv')[1]
    lab = art_data[:, artic.KEYS.index('labiodental'), 0]
    observed = samples['cross']['labiodental'][::period]
    angle_error = float(abs(observed - lab).max())
    lo, hi = fixed_event['u']
    passage = bool(observed[event - 1] < lo < hi <= observed[event])
    jump = geometry_change(candidate, samples['cross'], event, period, pharynx, cfg['affected_cell'], cfg)
    applied = {
        'candidate': applied_error(candidate, samples['cross'], cells, period, pharynx, 1),
        'upstream': applied_error(upstream, tracks['cross'][1], cells, period, pharynx, factor),
        'upstream_unlimited': applied_error(upstream, unlimited, cells, period, pharynx, factor, unlimited=True),
    }
    tolerance = cfg['geometry_absolute_lt']
    effects = {name: contrasts(a, b, wave, base, cfg, at, rate)
               for name, a, b, wave, base in [
                   ('candidate_cross_minus_hold', tracks['cross'][0], tracks['hold'][0], waves['cross'][0], waves['hold'][0]),
                   ('upstream_cross_minus_hold', tracks['cross'][1], tracks['hold'][1], waves['cross'][1], waves['hold'][1]),
                   ('upstream_unlimited_minus_hold', unlimited, tracks['hold'][1], unlimited_wave, waves['hold'][1]),
                   ('upstream_unlimited_minus_limited', unlimited, tracks['cross'][1], unlimited_wave, waves['cross'][1]),
               ]}
    prefix = all(not any(row['windows'][0]['peak'].values()) for row in effects.values())
    observed_effect = all(at <= frame < at + round(.02 * rate)
                          for result_item in effects.values()
                          for frame in [result_item['first_output_frame_over_floor']['pcm']] if frame is not None)
    detected = all(all(frame is not None for frame in item['first_output_frame_over_floor'].values()) for item in effects.values())
    if unlimited_wave.shape != waves['cross'][1].shape or not np.isfinite(unlimited_wave).all():
        raise ValueError('速度制限の対照のPCMが一致するフレーム数・有限性を持ちません')
    raw_cells = cfg['affected_cell']
    last = at + period // factor - 1
    target_frame = {key: [float(track[f'oral_{raw_cells}_{metric}'][last]) for metric in APPLIED[:2]]
                    for key, track in [('upstream', tracks['cross'][1]), ('upstream_unlimited', unlimited)]}
    checks.update({
        'registered_crossing_and_independent_articulation': passage and angle_error < tolerance
            and np.array_equal(observed[:event], np.full(event, observed[0])),
        'geometry_upstream_and_no_contact_projection': geometry_comparison['first_over_tolerance'] is None
            and not any(stage == 'reapply' for _, stage in candidate.keys() | upstream.keys()),
        'independent_speed_limit': limits['limited_area_error_cm2'] < tolerance and limits['lip_cells_match_from_teeth_distance'],
        'registered_raw_jump_and_attenuation': jump['raw_jump_registered']
            and all(0 < ratio < cfg['maximum_limited_to_raw_step_ratio'] for ratio in jump['limited_to_raw_step_ratio'])
            and all(0 < ratio < cfg['maximum_initial_sample_to_raw_step_ratio'] for ratio in jump['first_sample_to_raw_step_ratio']),
        'applied_area_and_length_ramps': max(value for rows in applied.values() for value in rows.values()) < tolerance,
        'identical_through_preevent_window': prefix
            and all(np.array_equal(waves['cross'][i][:at], waves['hold'][i][:at]) for i in range(2))
            and np.array_equal(unlimited_wave[:at], waves['cross'][1][:at]),
        'post_crossing_pressure_flow_and_pcm': observed_effect and detected,
    })
    if all(checks.values()):
        compress_traces(artifacts)
    return {'checks': {key: bool(value) for key, value in checks.items()}, 'samples': result,
            'crossing': {'control_frame': event, 'internal_sample': start, 'output_frame': at,
                         'labiodental_before_and_after': observed[event-1:event+1].tolist(), 'position_error': angle_error},
            'geometry': geometry_comparison, 'speed_limit': limits, 'juxtaposed_cell': jump,
            'applied_at_first_block_end_cm2': target_frame, 'applied_max_errors': applied, 'contrasts': effects}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = json.loads(CASE.read_text())
    revision = case['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('固定上流版と作業状態を確認してください')
    cfg = case['measurement']['dynamic_lip_tuck']
    fixed = WORKSPACE / 'runs' / cfg['static_reference_run']
    manifest_path, summary_path = fixed / 'manifest.json', fixed / 'summary.json'
    baseline = json.loads(manifest_path.read_text())
    if (baseline['status'] != 'pass' or baseline['upstream_revision'] != revision
            or not any(row['path'] == 'summary.json' and row['sha256'] == sha256(summary_path)
                       for row in baseline['outputs'])):
        parser.error('固定姿勢の比較基準を照合できません')
    event = json.loads(summary_path.read_text())['events'][cfg['static_reference_event']]
    sources = [CASE, manifest_path, summary_path, Path(__file__).resolve(), artic.PROBE,
               *(Path(module.__file__) for module in (artic, pcm, tract, shared, voiced)), *shared.candidate_sources()]
    sources.extend(UPSTREAM / 'crates/chimera' / relative for relative in (
        'src/voice/human_voice.rs', 'src/voice/human_airway.rs', 'src/airway/network.rs', 'src/control/articulators.rs',
        'tests/airway_adversarial.rs', 'tests/engine.rs'))
    return shared.record_measurement(args.run_id, CASE, sources,
                                    {'case_id': case['id'], 'upstream_revision': revision},
                                    lambda artifacts, execute: measure(case, event, artifacts, execute),
                                    command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
