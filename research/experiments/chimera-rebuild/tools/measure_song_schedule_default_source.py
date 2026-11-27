"""通常の上流音源の短い歌唱を、ネイティブ、Safari保存PCM、研究版CLIで照合する。"""

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import numpy as np

from measure_bilabial_stop import capture_candidate
from measure_fan_crossing_allocations import run_manifest, verified_path
from measure_glottal_pitch import independent_pitch
from measure_song_schedule_drift import compare_pair, load_candidate, load_upstream, phase_delta, read_json
from measure_song_schedule_jitter import calculate_phase
from measure_song_schedule_shimmer import CANDIDATE_COLUMNS, cycle_amplitudes
from measure_uniform_tube import candidate_sources, record_measurement
from measure_upstream_song_schedule_state import first_difference, relative_segments
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/song-voice-schedule-default-source.json'


def pcm_difference(reference, candidate, floor, first_frame=0):
    bits = reference.view('<u4') != candidate.view('<u4')
    delta = abs(candidate.astype(float) - reference)
    at = first_frame + np.arange(len(reference))
    return {'first_bit_difference': first_difference(bits, 0, at),
            'bit_differences': int(np.count_nonzero(bits)),
            'first_over_tolerance': first_difference(delta, floor, at),
            'maximum_absolute_difference': float(delta.max())}


def load_safari(browser, raw, native, lead, expected, end):
    rate = native['output_rate_hz']
    start = browser['scheduleApplied']['appliedFrame']
    rows = np.array(browser['rows'], dtype=np.int64)
    engine_frames, lengths = rows[:, 1], rows[:, 2]
    origin = browser['plan']['t0']
    total = lead + native['comparison_samples']
    pcm = np.fromfile(raw, dtype='<f4')
    if (not browser['hasPCM'] or browser['sampleRate'] != rate or browser['engineError']
            or browser['armed']['engineFrame'] != start or browser['scheduleReceived']['target'] != start
            or browser['scheduleReceived']['receivedFrame'] > start or round(origin * rate) != start + lead
            or engine_frames[0] != start or np.any(lengths <= 0)
            or not np.array_equal(engine_frames[1:], engine_frames[:-1] + lengths[:-1])
            or np.any(lengths[:-1] != 128) or lengths[-1] > 128 or int(lengths.sum()) != total
            or len(pcm) != total or not np.isfinite(pcm).all()
            or browser['input']['source'] != native['source'] or browser['input']['body'] != native['body']
            or browser['input']['lyrics'] != native['score']['lyrics']
            or relative_segments(browser['plan']['segments'], origin, rate) != expected
            or round((browser['plan']['end'] - origin) * rate) != round(end * rate)):
        raise ValueError(f'Safariの予約位置・音源・計画または波形が登録と一致しません ({raw.parent.name})')
    return start, pcm


def measure(study, native, probe, safari_summary, references, clips, artifacts, execute):
    rate, fs = native['output_rate_hz'], native['internal_rate_hz']
    factor = fs // rate
    lead = round(native['lead_seconds'] * rate)
    at = np.arange(-lead, native['comparison_samples'])
    floor = native['pcm_difference_floor']
    window = lo, hi = study['voiced_window_frames']
    expected = relative_segments(probe['segments'], 0, rate)
    model = independent_pitch({
        'sample_count': factor * (max(native['schedule_engine_frames']) + lead),
        'update_interval_samples': study['pitch_update_internal_samples'],
        'drift_seed': study['pitch_drift_seed'],
    }, {
        'f0_hz': native['source']['f0'], 'drift_cents': study['pitch_drift_cents'],
        'vibrato_depth_cents': 0, 'vibrato_rate_hz': native['source']['vibratoRate'],
    }, fs)[factor - 1::factor]

    checks, predictions, results, saved = {}, {}, {}, {}
    for label, (start, noise, up_csv, up_pcm, base) in references.items():
        folder = artifacts / label
        folder.mkdir()
        case = read_json(base)
        case['song_voice']['voice']['pitch_drift_cents'] = study['pitch_drift_cents']
        source = folder / 'input.json'
        source.write_text(json.dumps(case, ensure_ascii=False, indent=2) + '\n')
        info, csv, paths = capture_candidate(source, study['host_block_frames'], folder, execute)
        wave, stage = paths[0]
        checks[f'{label}/block_invariance'] = all(
            sha256(w) == sha256(wave) and sha256(s) == sha256(stage) for w, s in paths[1:])
        segments = [s for phrase in info['song']['plan']['phrases'] for s in phrase['timing']['segments']]
        checks[f'{label}/score_and_rates'] = (
            [(s['segment']['ipa'], round(s['start_seconds'] * rate) - lead, round(s['end_seconds'] * rate) - lead)
             for s in segments] == [(ipa, t0, t1) for _, ipa, _, t0, t1 in expected]
            and info['output_frames'] == len(at) and info['decimation_factor'] == factor
            and info['control_block_internal_samples'] == 64 * factor)
        upper, native_pcm = load_upstream(up_csv, up_pcm, at, start, lead)
        trace, pcm = load_candidate(csv, wave, rate, at, 0,
                                    columns=CANDIDATE_COLUMNS | {'cycle_amplitude': 'glottal_cycle_amplitude_scale'})
        compare = compare_pair((upper, native_pcm), (trace, pcm[lead:]), at, native, window)
        compare['stages']['lip_minimum_cm2'] = compare['stages'].pop('lip_area_cm2')
        f0_measurement = trace['glottal_f0_hz']
        pitch_error = float(abs(f0_measurement[:lead] - model[start:start + lead]).max())
        independent_phase, cycles = calculate_phase(trace, start, model[:start], fs, factor,
                                                     study['period_jitter'], study['cycle_seed'])
        phase_error = float(abs(phase_delta(trace['glottal_phase_cycles'], independent_phase)).max())
        expected_amplitude, _ = cycle_amplitudes(study, independent_phase, cycles)
        amplitude_error = float(abs(trace['cycle_amplitude'] - expected_amplitude).max())
        predictions[f'{label}/independent_source'] = (
            pitch_error <= study['pitch_tolerance_hz'] and phase_error <= study['phase_tolerance_cycles']
            and amplitude_error <= study['amplitude_scale_tolerance'])
        predictions[f'{label}/all_measured_stages_match_native'] = (
            compare['first_pcm_over_threshold'] is None
            and all(observation['first_frame'] is None for observation in compare['stages'].values()))
        checks[f'{label}/active_voicing_window'] = all(
            float(t['glottal_voicing'][lo + lead:hi + lead].min()) >= study['active_voicing_floor']
            for t in (trace, upper))
        results[label] = compare | {
            'initial_f0_independent_hz': float(model[start]),
            'independent_preface_pitch_error_hz': pitch_error,
            'independent_phase_error_cycles': phase_error,
            'independent_amplitude_scale_error': amplitude_error,
            'bitwise_different_f0_frames': int(np.count_nonzero(upper['glottal_f0_hz'].view(np.uint64)
                                                               != f0_measurement.view(np.uint64))),
            'bitwise_different_phase_frames': int(np.count_nonzero(
                upper['glottal_phase_cycles'].view(np.uint64) != trace['glottal_phase_cycles'].view(np.uint64))),
            'native_to_cli_pcm': pcm_difference(native_pcm, pcm[lead:], floor),
            'native_to_cli_pcm_voiced_window': pcm_difference(native_pcm[lo:hi], pcm[lead + lo:lead + hi], floor, lo),
        }
        saved[noise, start] = native_pcm, pcm

    safari_results, safari_pcm = {}, {}
    for name, (browser, raw) in clips.items():
        start, pcm = load_safari(browser, raw, native, lead, expected, probe['end_seconds'])
        native_pcm, cli_pcm = saved[1, start]
        row = {'schedule_frame': start, 'mode': browser['mode'],
               'engine_to_context_offset_frames': browser['armed']['contextFrame'] - start,
               'native_to_safari_pcm': pcm_difference(native_pcm, pcm[lead:], floor),
               'safari_to_cli_pcm': pcm_difference(pcm[lead:], cli_pcm[lead:], floor),
               'safari_to_cli_with_lead': pcm_difference(pcm, cli_pcm, floor, -lead)}
        predictions[f'{name}/native_to_safari_bits'] = row['native_to_safari_pcm']['bit_differences'] == 0
        predictions[f'{name}/safari_to_cli_threshold'] = row['safari_to_cli_with_lead']['first_over_tolerance'] is None
        safari_results[name] = row
        key = (start, browser['mode'])
        if key in safari_pcm:
            raise ValueError('Safariの予約時刻と停止条件が重複しています')
        safari_pcm[key] = pcm

    expected_safari = safari_summary['one_quantum_control']
    first, second = native['schedule_engine_frames']
    for start in (first, second):
        checks[f'{start}/safari_pause_pcm'] = (
            np.array_equal(safari_pcm[start, 'continuous'].view('<u4'), safari_pcm[start, 'paused'].view('<u4')))
    schedule_differences = {}
    for noise in native['noise_scales']:
        old_native, old_cli = saved[noise, first]
        new_native, new_cli = saved[noise, second]
        a = pcm_difference(old_native, new_native, floor)
        b = pcm_difference(old_cli[lead:], new_cli[lead:], floor)
        target = expected_safari['first_sample_over_tolerance'] if noise == 1 else 20903
        predictions[f'noise-{noise}/first_difference_between_reservations'] = (
            a['first_over_tolerance'] == b['first_over_tolerance'] == target)
        schedule_differences[str(noise)] = {'native': a, 'cli': b}
    browser_pair = pcm_difference(safari_pcm[first, 'continuous'][lead:],
                                  safari_pcm[second, 'continuous'][lead:], floor)
    heard = browser_pair['first_over_tolerance']
    predictions['safari_schedule_difference_before_pause'] = (
        heard == expected_safari['first_sample_over_tolerance'] and heard is not None
        and heard < expected_safari['earliest_hold_sample'])
    return {'checks': checks | predictions, 'hypothesis_checks': predictions, 'arms': results,
            'safari': safari_results, 'safari_between_schedules': browser_pair,
            'between_schedules': schedule_differences, 'relative_plan_frames': expected,
            'voiced_window_frames': window, 'lead_frames': lead}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    study = read_json(CASE)
    revision = study['upstream_revision']
    if (subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)):
        parser.error('変更のない固定上流が必要です')
    inputs, runs, summaries = [CASE, Path(__file__).resolve()], {}, {}
    for name, ref in study['references'].items():
        path = CASE.parent / ref['case']
        run = run_manifest(ref['run'], read_json(path)['id'], revision)
        if run[1]['status'] != 'pass':
            parser.error(f'基準実行が合格していません ({ref["run"]})')
        runs[name] = run
        summary = verified_path(run, 'summary.json')
        inputs.extend([path, run[0] / 'manifest.json', summary])
        summaries[name] = read_json(summary)
    native_file = verified_path(runs['native'], 'artifacts/native-input.json')
    probe_file = verified_path(runs['native'], 'artifacts/probe.json')
    capture_file = verified_path(runs['safari'], 'artifacts/capture-input.json')
    native, probe, capture = map(read_json, (native_file, probe_file, capture_file))
    registered = native['source']
    if (not summaries['safari']['one_quantum_control']['prediction'] or capture['score'] != native['score']
            or capture['schedule_engine_frames'] != native['schedule_engine_frames']
            or capture['expected_pcm_samples'] != native['comparison_samples']
            or registered['drift'] != study['pitch_drift_cents'] or registered['vibratoDepth'] != 0
            or registered['fry'] != 0
            or not math.isclose(0.0021 + 0.0245 * registered['roughness'], study['period_jitter'], abs_tol=1e-15)
            or not math.isclose(0.02 + 0.22 * registered['roughness'], study['amplitude_shimmer'], abs_tol=1e-15)):
        parser.error('固定上流の音源または採取条件が登録と一致しません')
    inputs.extend([native_file, probe_file, capture_file])
    clips = {}
    for trial in summaries['safari']['trials']:
        folder = f'artifacts/{trial["trial"]}'
        meta = verified_path(runs['safari'], folder + '/browser.json')
        pcm = verified_path(runs['safari'], folder + '/worklet.f32le')
        clips[trial['trial']] = read_json(meta), pcm
        inputs.extend([meta, pcm])
    references = {}
    for noise in native['noise_scales']:
        for start in native['schedule_engine_frames']:
            label = f'frame-{start}-noise-{noise}'
            csv = verified_path(runs['native'], f'artifacts/{label}.csv')
            pcm = verified_path(runs['native'], f'artifacts/{label}.f32le')
            base = verified_path(runs['candidate'], f'artifacts/{label}/input.json')
            song = read_json(base)['song_voice']
            voice = song['voice']
            if (song['warm_up_frames'] != start or song['turbulence']['scale'] != noise
                    or voice['base_pitch_hz'] != registered['f0'] or voice.get('pitch_drift_cents', 0) != 0
                    or voice['period_jitter'] != study['period_jitter']
                    or voice['amplitude_shimmer'] != study['amplitude_shimmer']):
                parser.error(f'研究版の基準が登録条件と一致しません ({label})')
            references[label] = (start, noise, csv, pcm, base)
            inputs.extend([csv, pcm, base])
    inputs.extend(candidate_sources())
    inputs.extend(WORKSPACE / 'tools' / name for name in (
        'measure_bilabial_stop.py', 'measure_fan_crossing_allocations.py', 'measure_glottal_cycle.py',
        'measure_glottal_pitch.py', 'measure_song_schedule_drift.py', 'measure_song_schedule_jitter.py',
        'measure_song_schedule_shimmer.py', 'measure_turbulence.py', 'measure_uniform_tube.py',
        'measure_upstream_song_schedule_state.py', 'upstream_song_schedule_state_probe.rs'))
    inputs.extend(UPSTREAM / path for path in (
        'Cargo.lock', 'crates/chimera/src/engine.rs', 'crates/chimera/src/math.rs',
        'crates/chimera/src/sources/glottis.rs', 'crates/chimera/src/voice/human_voice.rs',
        'crates/chimera-wasm/src/lib.rs', 'src/worklet/processor.ts'))
    details = {'case_id': study['id'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd()),
               'reference_runs': {name: run[0].name for name, run in runs.items()}}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda artifacts, execute: measure(study, native, probe, summaries['safari'], references,
                                           clips, artifacts, execute),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
