"""固定上流の単発キック B と調音、口腔圧、開口後の放射を照合する。"""

import argparse
import re
import subprocess
from pathlib import Path

import numpy as np
from scipy.io import wavfile

import measure_bilabial_stop as bilabial
import measure_speech_timing as timing
import measure_uniform_tube as shared
from upstream_baseline import UPSTREAM, WORKSPACE, sha256

PROBE = WORKSPACE / 'tools/upstream_beatbox_single_probe.rs'
ORAL_PROBE = WORKSPACE / 'tools/upstream_beatbox_oral_trace.rs'
PROBE_SOURCES = (PROBE, ORAL_PROBE)


def capture(case_path, config, artifacts, execute):
    prefix = ['cargo', 'run', '--locked', '--release', '-p', 'vocal-cli', '--']
    settings, trace = (artifacts / name for name in ('settings.json', 'trace.csv'))
    execute([*prefix, 'inspect', str(case_path)], stdout=settings)
    execute([*prefix, 'render', str(case_path), str(trace)])
    output = []
    for block in config['measurement']['host_block_frames']:
        wave, index = artifacts / f'pcm-{block}.wav', artifacts / f'pcm-{block}.csv'
        execute([*prefix, 'render-pcm', str(case_path), str(wave), str(index), str(block)])
        output.append((wave, index))

    execute(['cargo', 'test', '--locked', '-p', 'chimera', '--test', 'beatbox'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-tests.log')
    probe = shared.build_upstream_probe(PROBE, artifacts, execute, extra_libraries=('serde_json',))
    upper = tuple(artifacts / name for name in ('upstream.csv', 'upstream.f32', 'upstream.json'))
    execute([str(probe), str(case_path), *(str(path) for path in upper)], cwd=UPSTREAM)
    kit = artifacts / 'upstream-kit'
    sound = config['beatbox_voice']['sound']
    execute(['cargo', 'run', '--locked', '--release', '-p', 'chimera-cli', '--', 'render',
             'beatbox', str(kit), sound, 'male', '120', '1', '--float'],
            cwd=UPSTREAM, stdout=artifacts / 'upstream-kit.log')
    kit_stem = re.sub(r'[^A-Za-z]', '_', sound)
    return timing.read(settings), trace, output, upper, kit / f'{kit_stem}.wav'


def compare_plans(settings, reference, config, offsets):
    tolerance = config['measurement']['gesture_absolute_tolerance']
    def rename(targets):
        return {bilabial.KEYS[key]: value for key, value in targets.items()}

    expected = [{**gesture, 'targets': rename(gesture['targets'])}
                for gesture in reference['gestures']]
    diff, maximum = timing.compare(settings['gestures'], expected, tolerance)
    ready_diff, ready_maximum = timing.compare(
        settings['beatbox']['ready_targets'], rename(reference['ready_targets']), tolerance,
    )
    initial = rename(reference['initial_posture'])
    posture = config['beatbox_voice']['posture']
    pose = {key: value for key, value in posture.items() if key not in (
        'tongue_body_cm', 'tongue_tip_cm',
    )}
    for part in ('body', 'tip'):
        pose.update(zip((f'tongue_{part}_{axis}_cm' for axis in ('x', 'y')),
                        posture[f'tongue_{part}_cm'], strict=True))
    for key in ('lateral', 'epilarynx', 'ventricular'):
        pose.setdefault(key, 0.0)
    initial_diff, initial_maximum = timing.compare(pose, initial, tolerance)
    # 計画の絶対時刻と励振条件を、双方の言語実装を呼ばずに照合する。
    hit = config['beatbox_voice']['hit_seconds']
    calculated = [[hit + t0, hit + t1] for t0, t1 in offsets]
    observed = [[gesture['t0'], gesture['t1']] for gesture in settings['gestures']]
    time_diff, time_maximum = timing.compare(observed, calculated, tolerance)
    return {
        'gesture_difference': diff, 'gesture_max_abs_error': maximum,
        'ready_target_difference': ready_diff, 'ready_target_max_abs_error': ready_maximum,
        'initial_posture_difference': initial_diff, 'initial_posture_max_abs_error': initial_maximum,
        'independent_time_difference': time_diff, 'independent_time_max_abs_error_s': time_maximum,
    }


def compare_traces(candidate, upper, limits):
    first = None
    errors = {}
    geometry = {'lip_aperture_cm', 'lip_minimum_cm2', 'lip_area_cm2', 'jaw_cm', 'larynx_cm',
                'tongue_tip_x_cm', 'tongue_tip_y_cm', 'oral_minimum_cm2', 'labiodental',
                'noise_teeth_distance_cm', 'pharynx_minimum_cm2', 'tongue_body_x_cm', 'tongue_body_y_cm',
                'dorsum', 'lip_protrusion_cm', 'lip_spread'}
    diagnostics = limits.get('diagnostic_trace_columns', ['glottal_f0_hz'])
    for name in upper.dtype.names[1:]:
        delta = abs(candidate[name] - upper[name])
        peak = max(float(abs(upper[name]).max()), 1e-6)
        cell_geometry = name.startswith('oral_cell_') and name.endswith(('_minimum_cm2', '_volume_cm3'))
        tolerance = (limits['geometry_absolute_tolerance'] if name in geometry or cell_geometry
                     else peak * limits['audio_state_peak_relative_tolerance'])
        errors[name] = {'absolute': float(delta.max()), 'allowance': tolerance}
        # 声帯の振動とは別に、発声しない間の周期変動も診断値として保存する。
        if name in diagnostics:
            continue
        outliers = np.flatnonzero(delta > tolerance)
        tie_area = limits.get('zero_area_cell_index_tie_tolerance_cm2')
        if name == 'oral_minimum_cell' and tie_area is not None and outliers.size:
            ties = zero_area_cell_ties(candidate, upper, outliers, tie_area)
            errors[name]['zero_area_tied_frames'] = int(ties.sum())
            errors[name]['zero_area_tolerance_cm2'] = tie_area
            outliers = outliers[~ties]
        if outliers.size and (first is None or outliers[0] < first['frame']):
            index = int(outliers[0])
            first = {'field': name, 'frame': index, 'candidate': float(candidate[name][index]),
                     'upstream': float(upper[name][index]), 'allowance': tolerance}
    return first, errors


def zero_area_cell_ties(candidate, upper, rows, tolerance):
    """選択された2セルが、両実装でゼロとみなせる場合に限り同率とする。"""
    return np.array([
        all(abs(trace[f'oral_cell_{cell}_minimum_cm2'][row]) <= tolerance
            for trace in (candidate, upper)
            for cell in (int(candidate['oral_minimum_cell'][row]), int(upper['oral_minimum_cell'][row])))
        for row in rows
    ], dtype=bool)


def events(trace, pcm, config):
    kick = config['beatbox_voice']
    limits = config['measurement']
    rate = kick['voice']['output_sample_rate_hz']
    hit = kick['hit_seconds']
    clock = (trace['frame'] + 1) / rate
    window = (clock >= hit + limits['closure_offset_seconds'][0]) & (
        clock <= hit + limits['release_offset_seconds'][1])
    closed = np.flatnonzero(window & (trace['lip_minimum_cm2'] < limits['closed_area_cm2']))
    if not closed.size or closed[-1] + 1 >= len(trace):
        return {'closed_then_opened': False}
    start, release = int(closed[0]), int(closed[-1] + 1)
    if trace['lip_minimum_cm2'][release] < limits['closed_area_cm2']:
        return {'closed_then_opened': False}
    pressure = trace[limits.get('pressure_column', 'oral_end_pressure_dyn_cm2')]
    near_close = pressure[start:min(release, start + round(rate * 0.005))]
    pressure_index = start + int(np.argmax(pressure[start:release]))
    peak_pressure = float(pressure[pressure_index])
    pressure_rise = float(peak_pressure - near_close.mean())
    duration = (release - start) / rate
    closure_offset, release_offset = float(clock[start] - hit), float(clock[release] - hit)
    larynx = float(trace['larynx_cm'][start:release].max())
    glottal_area = float(trace['glottal_area_cm2'][pressure_index])
    voicing = float(abs(trace['glottal_voicing']).max())
    burst = slice(release, release + round(rate * limits['burst_window_seconds']))
    burst_frame = release + int(np.argmax(abs(pcm[burst])))
    peak_pcm = float(abs(pcm[burst_frame]))
    lip_flow = float(abs(trace['lip_flow_cm3_s'][burst]).max())
    tail = float(abs(pcm[-round(rate * limits['quiet_window_seconds']):]).max())
    f = kick['voice']['breathiness']
    static_area = (0.1 * f**2 + 0.008 + 0.03 * f) * 0.08
    return {
        'closed_then_opened': (len(closed) == release - start
                               and duration >= limits['minimum_closed_seconds']
                               and limits['closure_offset_seconds'][0] <= closure_offset <= limits['closure_offset_seconds'][1]
                               and limits['release_offset_seconds'][0] <= release_offset <= limits['release_offset_seconds'][1]),
        'compression_while_closed': (pressure_rise >= limits['minimum_closed_pressure_rise_dyn_cm2']
                                     and larynx >= limits['minimum_peak_larynx_cm']
                                     and glottal_area <= limits['maximum_glottal_area_at_pressure_peak_cm2']),
        'burst_and_quiet_tail': (lip_flow >= limits['minimum_burst_lip_flow_cm3_s']
                                 and peak_pcm >= limits['minimum_burst_peak_pcm']
                                 and tail <= limits['quiet_max_peak_pcm']),
        'no_pulmonic_gate_or_sustained_voicing': (not bool(np.any(trace['gate']))
                                                  and voicing <= limits['maximum_glottal_voicing']),
        'first_closed_frame': start, 'first_open_frame': release, 'burst_frame': burst_frame,
        'closure_offset_seconds': closure_offset, 'open_offset_seconds': release_offset,
        'closed_duration_seconds': duration, 'closed_larynx_peak_cm': larynx,
        'closed_pressure_peak_frame': pressure_index, 'closed_pressure_peak_dyn_cm2': peak_pressure,
        'closed_pressure_rise_dyn_cm2': pressure_rise, 'glottal_area_at_pressure_peak_cm2': glottal_area,
        'independent_static_closed_area_cm2': static_area,
        'static_closed_area_abs_error_cm2': abs(glottal_area - static_area),
        'maximum_glottal_voicing': voicing, 'burst_lip_flow_cm3_s': lip_flow, 'burst_pcm_peak': peak_pcm,
        'tail_pcm_peak': tail,
    }


def compare_render(case_path, config, artifacts, execute, *, offsets, observe):
    settings, trace, outputs, (upper_trace, upper_raw, upper_plan), upper_wave = capture(
        case_path, config, artifacts, execute,
    )
    frames = settings['output_frames']
    reference = timing.read(upper_plan)
    candidate = bilabial.load_trace(trace, frames)
    upper = bilabial.load_trace(upper_trace, frames)
    rate, pcm = wavfile.read(outputs[0][0])
    upper_pcm = np.fromfile(upper_raw, dtype='<f4')
    official_rate, official_pcm = wavfile.read(upper_wave)
    if pcm.shape != (frames,) or upper_pcm.shape != pcm.shape:
        raise ValueError('上流と再実装のモノラルPCMフレーム数が一致しません')
    if not np.isfinite(pcm).all() or not np.isfinite(upper_pcm).all():
        raise ValueError('PCMに非有限値があります')

    limits = config['measurement']
    plan = compare_plans(settings, reference, config, offsets)
    first, trace_errors = compare_traces(candidate, upper, limits)
    pcm_error = abs(pcm.astype('f8') - upper_pcm)
    pcm_first = np.flatnonzero(pcm_error > limits['pcm_absolute_tolerance'])
    current = observe(candidate, pcm, config)
    target = observe(upper, upper_pcm, config)
    waveform, index = outputs[0]
    checks = {
        'initial_posture_and_ready_targets': (plan['initial_posture_difference'] is None
                                             and plan['ready_target_difference'] is None),
        'gestures_equal_and_match_independent_times': (plan['gesture_difference'] is None
                                                       and plan['independent_time_difference'] is None),
        'sample_counts_and_rates': (frames == reference['output_frames']
                                    and rate == config['beatbox_voice']['voice']['output_sample_rate_hz']
                                    and settings['decimation_factor'] == reference['decimation_factor']),
        'trace_agreement': first is None,
        'pcm_agreement': not bool(pcm_first.size),
        'upper_probe_matches_normal_cli': (official_rate == rate and official_pcm.dtype == np.float32
                                            and np.array_equal(official_pcm, upper_pcm)),
        'same_event_frames': all(key in current and current[key] == target.get(key) for key in
                                 ('first_closed_frame', 'first_open_frame', 'burst_frame')),
        'host_partition_byte_agreement': all(sha256(wave) == sha256(waveform) and sha256(csv) == sha256(index)
                                             for wave, csv in outputs[1:]),
    }
    return {
        'checks': checks, 'frames': frames, 'output_rate_hz': rate, 'plan': plan,
        'first_trace_difference': first, 'trace_errors': trace_errors,
        'pcm_max_absolute_error': float(pcm_error.max()),
        'pcm_first_difference_frame': int(pcm_first[0]) if pcm_first.size else None,
        'candidate_events': current, 'upstream_events': target,
    }


def measure(case_path, config, artifacts, execute):
    offsets = [[-0.107, -0.029], [-0.085, -0.010], [-0.097, 0.020], [-0.060, -0.006]]
    result = compare_render(case_path, config, artifacts, execute, offsets=offsets, observe=events)
    limits = config['measurement']
    current, target = result['candidate_events'], result['upstream_events']
    for name in ('closed_then_opened', 'compression_while_closed', 'burst_and_quiet_tail',
                 'no_pulmonic_gate_or_sustained_voicing'):
        result['checks'][name] = current.get(name, False) and target.get(name, False)
    if 'static_closed_area_abs_tolerance_cm2' in limits:
        result['checks']['independent_static_glottal_area_at_pressure_peak'] = all(
            outcome.get('static_closed_area_abs_error_cm2', np.inf)
            <= limits['static_closed_area_abs_tolerance_cm2'] for outcome in (current, target)
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--version', type=int, choices=(1, 2), default=2)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.run_id):
        parser.error('実行IDは英数字で始めてください')
    case_name = 'beatbox-kick-b' if args.version == 1 else 'beatbox-kick-b-v2'
    case_path = WORKSPACE / f'cases/{case_name}.json'
    config = timing.read(case_path)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != config['upstream_revision'] or subprocess.check_output(
            ['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True):
        raise SystemExit('変更のない固定上流版が必要です')
    source_files = [
        case_path, *PROBE_SOURCES, Path(__file__).resolve(), Path(shared.__file__), Path(bilabial.__file__),
        Path(timing.__file__), WORKSPACE / 'tools/upstream_baseline.py', *shared.candidate_sources(),
    ]
    upper_sources = [
        'crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/beatbox.rs',
        'crates/chimera/src/phonetics/planner.rs', 'crates/chimera/src/control/beat_player.rs',
        'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/sources/glottis.rs',
    ]
    details = {
        'upstream_revision': revision, 'case_id': config['id'],
        'upper_source_sha256': {path: sha256(UPSTREAM / path) for path in upper_sources},
    }
    return shared.record_measurement(args.run_id, case_path, source_files, details,
                                     lambda artifacts, execute: measure(case_path, config, artifacts, execute),
                                     command=None)


if __name__ == '__main__':
    raise SystemExit(main())
