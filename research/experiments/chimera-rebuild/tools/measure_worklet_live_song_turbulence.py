"""同じ短音の歌唱で乱流係数0と1の波形・状態・返却時刻を比較する。"""

import argparse
from pathlib import Path
import shutil
from statistics import median
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

import inspect_firefox_cubeb_output as cubeb
import measure_firefox_cubeb_return_time as return_time
import measure_worklet_live_song_shared_context as context


song = context.song
phases = context.phases
read = song.wasm.read_json
CASES = song.WORKSPACE / 'cases'
CASE = CASES / 'worklet-live-song-fast-turbulence.json'
TRACE = 'artifacts/voicing.csv'
UPSTREAM_TRACE = 'artifacts/upstream-voicing.csv'
NOISE_PRESSURES = tuple(f'{source}_noise_{direction}_pressure'
                        for source in ('glottis', 'constriction', 'teeth') for direction in ('forward', 'reverse'))
TRACE_FIELDS = (*NOISE_PRESSURES, 'gate', 'abduction_cm2', 'glottal_area_cm2', 'glottal_flow_cm3_s',
                'glottal_f0_hz', 'radiation_derivative_cm3_s2')


def trace_values(path, frames):
    with path.open() as file:
        headers = file.readline().strip().split(',')
        values = np.loadtxt(file, delimiter=',', usecols=[headers.index('frame'),
                            *(headers.index(field) for field in TRACE_FIELDS)])
    if values.shape != (frames, len(TRACE_FIELDS) + 1) or not np.isfinite(values).all() or not np.array_equal(
            values[:, 0], np.arange(frames)):
        raise ValueError(f'音響の時系列を同じフレームで照合できません ({path})')
    return values[:, 1:]


def pcm_evidence(study, references, fixed):
    limits = fixed['measurement']
    rate, frames = limits['output_rate_hz'], limits['output_frames']
    left, right = (round(seconds * rate) for seconds in study['noise_window_seconds'])
    summaries = {}
    for engine, trace_name in (('cli', TRACE), ('upstream', UPSTREAM_TRACE)):
        quiet, turbulent = (trace_values(ref[trace_name], frames) for ref in references)
        quiet_noise = quiet[:, :len(NOISE_PRESSURES)]
        turbulent_noise = turbulent[:, :len(NOISE_PRESSURES)]
        if engine == 'cli':
            audio = [wavfile.read(ref['artifacts/pcm-128.wav'])[1] for ref in references]
        else:
            audio = [np.fromfile(ref['artifacts/upstream-pcm.f32'], dtype='<f4') for ref in references]
        pcm_delta = np.abs(audio[0].astype(float) - audio[1])
        summaries[engine] = {'first_difference_by_field': {
            field: song.wasm.first_index(quiet[:, i] != turbulent[:, i]) for i, field in enumerate(TRACE_FIELDS)},
            'zero_noise_pressure_peak_dyn_cm2': float(abs(quiet_noise).max()),
            'active_noise_pressure_window_peak_dyn_cm2': float(abs(turbulent_noise[left:right]).max()),
            'pcm_first_bit_difference_frame': song.wasm.first_index(audio[0].view('<u4') != audio[1].view('<u4')),
            'pcm_first_difference_above_floor_frame': song.wasm.first_index(pcm_delta > study['pcm_difference_floor']),
            'pcm_maximum_absolute_difference': float(pcm_delta.max())}
    return summaries


def measure(study, source, fixed, live, marker, preparation, references, return_reference, browser, frame_spec,
            phase, profiler, firefox, bun, artifacts, execute):
    reg = phases.registration.evaluation.registration
    checks, zero = phases.build_comparison(fixed, live, source, references[0], artifacts, execute, bun)
    enabled_source = references[1]['artifacts/turbulence-input.json']
    one_checks, one = phases.read_comparison(fixed, live, enabled_source, references[1], artifacts / 'vocal_wasm.wasm')
    checks.update({f'scale1/{key}': value for key, value in one_checks.items()})
    checks['same_plan_across_scales'] = zero['expected']['score'] == one['expected']['score']
    audio = pcm_evidence(study, references, fixed)
    trials = []
    for round_number, order in enumerate(study['condition_order'], 1):
        for scale in order:
            label = f'{round_number}-scale{scale}'
            folder = artifacts / label
            trial = {'trial': label, 'condition': 'split192', 'turbulence_scale': scale, 'round': round_number}
            options = {'shared_context_marker': marker['marker'], 'record_asset_evidence_timing': True,
                       'render_preparation': study['preparation']}

            def capture_execute(command, **kwargs):
                directory = folder / 'cubeb'
                directory.mkdir()
                execute(['env', f'CHIMERA_FIREFOX={firefox}', f'CHIMERA_CUBEB_OUTPUT_DIR={directory}',
                         f"CHIMERA_CUBEB_OUTPUT_BLOCKS={browser['capture']['snapshot_blocks']}", *command], **kwargs)

            try:
                path, comparison = (source, zero) if scale == 0 else (enabled_source, one)
                run, report, rate, pcm = context.cross.capture(folder, 'firefox', live, path, '...', capture_execute,
                                                               profiler, options=options)
                local, trial['upstream_pcm'] = reg.checks_for_capture(run, report, rate, pcm, **comparison)
                replay = read(folder / 'browser-case.json')['song_voice']
                lead = report['firstContextFrame'] - report['realtime']['startupFirstContextFrame']
                local['replayed_turbulence_scale'] = replay['turbulence']['scale'] == scale
                local['same_frames_before_song'] = lead == study['expected_frames_before_song']
                signal_checks, trial['reference_signal'], frames = context.shared.marker_signal(
                    marker['marker'], folder, marker['marker']['quantum'], rate)
                local.update(signal_checks)
                timing, trial['timing'] = context.shared_timing(read(folder / 'firefox-profile.json'), report,
                                                                marker, phase, frames, 'split192', preparation)
                local.update(timing)
                trial['coreaudio'] = cubeb.inspect(folder, trial, marker['marker'], browser, frame_spec,
                                                   phase['engine_marker'])
                local['cubeb_output_window'] = trial['coreaudio']['valid']
                local['split_blocks_in_separate_requests'] = trial['coreaudio'].get('split_requests_valid', False)
            except (OSError, EOFError, KeyError, TypeError, ValueError, subprocess.CalledProcessError) as error:
                local = {'capture_and_comparison_completed': False}
                trial['error'] = str(error)
            checks.update({f'{label}/{k}': v for k, v in local.items()})
            trials.append(trial)
            context.cross.clocks.compress_outputs(folder)
    timing = context.fast_return_times(trials, browser, return_reference)
    checks['all_center_requests_aligned'] = len(timing['trials']) == len(trials)
    by_name = {row['trial']: row for row in timing['trials']}
    differences = []
    for number in range(1, len(study['condition_order']) + 1):
        a, b = (by_name.get(f'{number}-scale{scale}') for scale in (0, 1))
        if a is not None and b is not None:
            differences.append({'round': number, 'change_ms': b['scheduled_host_minus_return_ms'] -
                                                               a['scheduled_host_minus_return_ms']})
    change = median(row['change_ms'] for row in differences) if differences else None
    predicted = study['maximum_predicted_median_return_change_ms']
    return {'checks': checks, 'trials': trials, 'acoustic': audio, 'return_time': timing,
            'paired_return_time_differences': differences, 'median_paired_return_time_difference_ms': change,
            'predictions': {'small_paired_return_time_change': change is not None and
                            len(differences) == len(study['condition_order']) and abs(change) < predicted,
                            'noise_and_pcm_changed': all(a['zero_noise_pressure_peak_dyn_cm2'] == 0 and
                                                         a['active_noise_pressure_window_peak_dyn_cm2'] > 0 and
                                                         a['pcm_first_difference_above_floor_frame'] is not None
                                                         for a in audio.values())}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('one_reference')
    parser.add_argument('--cubeb-output', type=Path, required=True)
    args = parser.parse_args()
    study, browser, phase = (read(path) for path in (CASE, context.CUBEB_OUTPUT_CASE, phases.CASE))
    fixed_path = CASES / study['offline_case']
    fixed = read(fixed_path)
    source = CASES / fixed['song_voice_case']
    shared_path = CASES / browser['shared_context_case']
    marker = read(shared_path)['measurement']
    marker['marker']['stereo_difference'] = True
    live = read(song.LIVE_CASE)
    context.set_song_schedule(live, fixed)
    frame_path = CASES / browser['frame_validation_case']
    profiler_path = CASES / phase['measurement']['profiler_case']
    preparation_path = context.SPLIT_PREPARATION_CASE
    preparation = read(preparation_path)
    revision = study['upstream_revision']
    if (any(case['upstream_revision'] != revision for case in (fixed, browser, phase, preparation, live)) or
            study['preparation'] != context.SPLIT_OPTIONS['split192'] or
            any(sorted(pair) != [0, 1] for pair in study['condition_order']) or
            subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision or
            subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流、歌唱設定または比較条件が一致しません')
    firefox = args.cubeb_output.resolve(strict=True)
    xul_sha = song.sha256(firefox.with_name('XUL'))
    references, manifests = [], []
    for scale, name in enumerate((study['zero_reference_run'], args.one_reference)):
        run = song.run_manifest(name, fixed['id'], revision)
        if run[1]['status'] != 'pass' or run[1]['turbulence_scale'] != scale:
            parser.error(f'{name} の歌唱基準または乱流係数が一致しません')
        paths = [*phases.OFFLINE_REFERENCE, TRACE, UPSTREAM_TRACE]
        if scale == 1:
            paths.append('artifacts/turbulence-input.json')
        ref = {path: song.verified_path(run, path) for path in paths}
        expected = read(source)
        if scale == 1:
            expected['song_voice']['turbulence'] = {'scale': 1}
            same_source = expected == read(ref['artifacts/turbulence-input.json'])
        else:
            same_source = any(row['path'].endswith('/' + source.name) and row['sha256'] == song.sha256(source)
                              for row in run[1]['inputs'])
        if not same_source:
            parser.error(f'{name} の歌唱入力を照合できません')
        references.append(ref)
        manifests.append(run[0] / 'manifest.json')
    return_run = song.run_manifest(study['return_reference_run'], return_time.CASE.stem, revision)
    return_path = song.verified_path(return_run, 'summary.json')
    if return_run[1]['status'] != 'pass' or return_run[1]['firefox_xul_sha256'] != xul_sha:
        parser.error('返却時刻の基準または試験用Firefoxが一致しません')
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    inputs = [CASE, fixed_path, source, shared_path, frame_path, profiler_path, phases.CASE, context.CUBEB_OUTPUT_CASE,
              preparation_path, song.LIVE_CASE, song.CASE, return_path, return_run[0] / 'manifest.json', *manifests,
              Path(__file__).resolve(), *(Path(m.__file__) for m in (context, context.cross, context.shared, phases, song,
                phases.registration, phases.registration.evaluation.registration, cubeb, cubeb.tap.callback, return_time)),
              *(path for ref in references for path in ref.values()), *song.web_sources(), *song.shared.candidate_sources()]
    details = {'case_id': study['id'], 'upstream_revision': revision, 'firefox_xul_sha256': xul_sha,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return song.shared.record_measurement(args.run_id, CASE, inputs, details,
        lambda out, run: measure(study, source, fixed, live, marker, preparation, references, read(return_path),
                                 browser, read(frame_path)['measurement'], phase['measurement'],
                                 read(profiler_path)['measurement'], firefox, bun, out, run),
        command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
