"""確認用発話の音源・初期舌先・ゲインをそろえ、全PCMと計画音素を比較する。"""

import argparse
import gzip
import math
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import numpy as np

import measure_tsp_seems_initial_tip as initial_tip
import measure_tsp_stressed_vowel_formants as tsp
from measure_duet_child_glottal_noise_origin import bit_equal
from measure_duet_child_output_gain import independent_stages, trace_input
from measure_tsp_active_duration import active_interval, compare_pcm, read_generated, save, windows
from measure_tsp_f2_bandwidth_held_out import saved_case
from measure_tsp_fine_tip import peak, radiated, read_series
from measure_tsp_fine_variation import DICT, FIELDS, LOCAL, OUTPUT_PATCH, PROBE, SOURCE_PATCH, first_difference
from measure_tsp_seems_period_jitter import cycle_model
from measure_tsp_startup import resting_tip
from measure_uniform_tube import build_upstream_probe, candidate_sources, record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-held-out-matched-speech.json'
RENDER_CASE = WORKSPACE / 'cases/tsp-active-duration-original.json'
PLAN_KEYS = ('speech', 'gestures', 'output_frames', 'control_block_internal_samples', 'decimation_factor')


def phone_intervals(plan, rate, *, upstream):
    if upstream:
        rows = ((entry['ipa'], entry['kind'], entry.get('stress', 0), entry['t0'], entry['t1'])
                for entry in plan['segments'])
    else:
        rows = ((entry['segment']['ipa'], entry['manner'], entry['segment'].get('stress', 0),
                 entry['start_seconds'], entry['end_seconds'])
                for phrase in plan['speech']['phrases'] for entry in phrase['timing']['segments'])
    return [{'ipa': ipa, 'manner': manner, 'stress': stress or 0,
             'frames': [math.floor(rate * start + 0.5), math.floor(rate * stop + 0.5)]}
            for ipa, manner, stress, start, stop in rows]


def pcm_report(reference, samples, config):
    report = compare_pcm(reference, samples)
    count = report['common_frames']
    delta = samples[:count].astype('f8') - reference[:count]
    significant = np.flatnonzero(abs(delta) > config['limits']['pcm_absolute'])
    report.update(
        reference_frames=len(reference), candidate_frames=len(samples),
        initial_peak_difference=peak(delta[:config['windows']['initial_frames']]),
        first_over_limit=int(significant[0]) if significant.size else None,
        last_over_limit=int(significant[-1]) if significant.size else None,
        peak_frame=int(np.argmax(abs(delta))) if report['different_bits'] else None)
    return report, delta


def phone_at(intervals, frame):
    if frame is None:
        return None
    return next((phone for phone in intervals if phone['frames'][0] <= frame < phone['frames'][1]), None)


def duration(samples, config):
    size, hop, threshold = (config['windows'][name] for name in ('size_frames', 'hop_frames', 'threshold_db'))
    series = windows(samples, size, hop)
    accumulated = np.r_[0.0, np.cumsum(samples.astype('f8') ** 2)]
    starts = np.arange(len(series)) * hop
    difference = series ** 2 - (accumulated[starts + size] - accumulated[starts]) / size
    return {'interval': list(active_interval(series, size, hop, threshold)),
            'maximum_mean_square_error': peak(difference)}


def state_metrics(a, b, config):
    internal_count = min(len(a['phase']), len(b['phase']))
    result = {}
    for field in FIELDS:
        difference = b[field][:internal_count] - a[field][:internal_count]
        if field == 'phase':
            circular = abs(difference)
            difference = np.minimum(circular, 1 - circular)
        result[field] = {'first_difference': first_difference(difference), 'maximum_absolute_difference': peak(difference),
                         'first_over_limit': first_difference(difference, config['limits']['state'][field])}
    return result


def output_checks(config, gain, state, trace, wave):
    radiation = radiated(config, state, trace)
    replay = independent_stages(trace, wave, gain, config | {'base_gain': gain})
    limits = config['limits']
    okay = (radiation['timeline_matches']
            and radiation['sum_peak_error_cm3_s'] <= limits['radiation_derivative_cm3_s2'] / config['internal_sample_rate_hz']
            and radiation['difference_peak_error_cm3_s2'] <= limits['radiation_derivative_cm3_s2']
            and replay['pcm_matches_independent_limiter'] and replay['hold_error_frames'] == 0
            and all(replay[key] <= limits['independent_normalized'] for key in
                    ('fir_error_times_base_gain', 'gain_input_error', 'dc_error', 'envelope_error')))
    return okay, radiation, replay


def cycle_checks(config, states, amplitudes):
    variation = config['source_variation']
    result = {}
    for name, state in states.items():
        phase, scales, boundaries = cycle_model(config['cycle'], config['internal_sample_rate_hz'], state['f0_hz'],
                                               variation['period_jitter'], variation['amplitude_shimmer'])
        result[name] = {'phase_maximum_error': peak(phase - state['phase']), 'boundary_count': len(boundaries)}
        if name == 'candidate':
            result[name]['amplitude_maximum_error'] = peak(scales[:, 1] - amplitudes)
    return result


def build_probes(config, tmp, out, execute):
    checkout = tmp / 'upstream'
    checkout.mkdir()
    archive = tmp / 'fixed.tar'
    execute(['git', 'archive', config['upstream_revision']], cwd=UPSTREAM, stdout=archive)
    execute(['tar', '-xf', str(archive), '-C', str(checkout)])
    for patch in (OUTPUT_PATCH, SOURCE_PATCH):
        execute(['git', 'apply', str(patch)], cwd=checkout)
    upper = build_upstream_probe(PROBE, tmp, execute, upstream=checkout, extra_libraries=('serde_json',),
                                 rustc_args=('--cfg', 'tsp_voice_probe'), cargo_args=('--offline',))
    candidate = build_upstream_probe(LOCAL, tmp, execute, upstream=WORKSPACE, package='vocal-core', lto='off',
                                     extra_libraries=('serde_json',), cargo_args=('--offline',))
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'chimera-cli'], cwd=UPSTREAM)
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_planning', '--test', 'golden_voice'],
            cwd=UPSTREAM, stdout=out / 'upstream-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'vocal-core', '--lib'], stdout=out / 'candidate-tests.log')
    return upper, candidate


def measure_one(config, saved, probes, dictionary, scratch, output, execute):
    original = tsp.read(saved['candidate.json'])['speech_voice']
    uid = original['input']['id']
    body = original['body']
    settings = config['body'][body]
    pause_tip = resting_tip(original['posture'])
    matched = {'speech_voice': original | {
        'posture': original['posture'] | {'tongue_tip_cm': pause_tip},
        'voice': original['voice'] | {'output_gain': settings['output_gain']},
        'source_variation': config['source_variation'],
    }}
    folder = output / uid
    folder.mkdir()
    matched_case = folder / 'matched-case.json'
    save(matched_case, matched)
    candidate_plan_path = folder / 'matched-plan.json'
    upstream_plan_path = folder / 'upstream-plan.json'
    upper, candidate = probes
    render_rate = config['sample_rate_hz']
    ordinary_upper = scratch / 'upstream.wav'
    ordinary_candidate = scratch / 'candidate.wav'
    upper_command = str(UPSTREAM / 'target/release/chimera')
    vocal = str(WORKSPACE / 'target/release/vocal-cli')
    execute([upper_command, 'render', 'text', str(ordinary_upper), original['input']['text'], body, '--float'], cwd=UPSTREAM)
    execute([vocal, 'inspect', str(matched_case)], stdout=candidate_plan_path)
    execute([vocal, 'render-pcm', str(matched_case), str(ordinary_candidate), '--no-trace', '128'])
    waves = {name: read_generated(path, render_rate) for name, path in
             (('upstream', ordinary_upper), ('candidate', ordinary_candidate), ('baseline', saved['candidate.wav']))}
    states, lengths, radiations, replays, identical_probe, output_ok = {}, {}, {}, {}, {}, {}
    factor = config['internal_sample_rate_hz'] // render_rate
    amplitudes = scratch / 'amplitudes.f64'
    for name, observer in (('upstream', upper), ('candidate', candidate)):
        state, pcm, trace = (scratch / f'{name}-{suffix}' for suffix in ('state.f64', 'pcm.f32', 'output.f64'))
        lengths[name] = len(waves[name])
        count = str(lengths[name])
        if name == 'upstream':
            execute([str(observer), str(saved['candidate.json']), str(dictionary), str(state), str(pcm),
                     str(upstream_plan_path), count, 'default', str(trace)])
        else:
            execute([str(observer), str(matched_case), str(dictionary), count, '110', str(settings['base_f0_hz']),
                     *map(str, (state, pcm, trace, amplitudes))])
        measured = np.fromfile(pcm, dtype='<f4')
        identical_probe[name] = bit_equal(measured, waves[name])
        states[name] = read_series(state, lengths[name] * factor)
        okay, radiation, replay = output_checks(config, settings['output_gain'], states[name],
                                                trace_input(trace, lengths[name]), waves[name])
        output_ok[name], radiations[name], replays[name] = okay, radiation, replay
    upstream_plan, candidate_plan, saved_plan = (tsp.read(path) for path in
                                                (upstream_plan_path, candidate_plan_path, saved['inspect.json']))
    upper_phones = phone_intervals(upstream_plan, render_rate, upstream=True)
    candidate_phones = phone_intervals(candidate_plan, render_rate, upstream=False)
    matched_report, delta = pcm_report(waves['upstream'], waves['candidate'], config)
    baseline_report, _ = pcm_report(waves['upstream'], waves['baseline'], config)
    active = {name: duration(wave, config) for name, wave in waves.items()}
    cycles = cycle_checks(config, states, np.fromfile(amplitudes, dtype='<f8'))
    state = state_metrics(states['upstream'], states['candidate'], config)
    events = {key: {'frame': matched_report[key], 'upstream': phone_at(upper_phones, matched_report[key]),
                    'candidate': phone_at(candidate_phones, matched_report[key])}
              for key in ('first_bit_difference', 'first_over_limit', 'peak_frame')}
    regional = {}
    for index, phone in enumerate(candidate_phones):
        start, stop = phone['frames']
        values = delta[start:stop]
        if len(values):
            regional[str(index)] = {'phone': phone, 'maximum_absolute_difference': peak(values),
                                    'samples_compared': len(values)}
    checks = {
        'archived_upstream_pcm': sha256(ordinary_upper) == sha256(saved['upstream.wav']),
        'ordinary_pcm_matches_observation': all(identical_probe.values()),
        'candidate_plan_unchanged': all(candidate_plan[key] == saved_plan[key] for key in PLAN_KEYS),
        'body_rest_tip_matches': all(abs(row['tongue_tip_y_cm'][0] - pause_tip[1]) <= config['limits']['tip_cm']
                                     for row in states.values()),
        'independent_cycle_and_output': all(output_ok.values()) and all(
            row['phase_maximum_error'] <= config['limits']['phase_cycles'] for row in cycles.values())
            and cycles['candidate']['amplitude_maximum_error'] <= config['limits']['amplitude_coefficient'],
        'independent_window_mean_square': all(row['maximum_mean_square_error'] <= config['limits']['window_mean_square']
                                              for row in active.values()),
    }
    return {'checks': checks, 'uid': uid, 'body': body, 'text': original['input']['text'],
            'resting_tip_cm': pause_tip, 'baseline_pcm': baseline_report, 'matched_pcm': matched_report,
            'phones': {'upstream': upper_phones, 'candidate': candidate_phones, 'match': upper_phones == candidate_phones},
            'active_intervals': active, 'difference_events': events, 'phone_peaks': regional,
            'internal_differences': state, 'cycle_model': cycles, 'radiation': radiations, 'output_stage': replays}, waves


def measure(config, paths, out, execute):
    details, evidence = {}, {}
    with TemporaryDirectory(prefix='tsp-held-out-', dir=out.parent / 'tmp') as directory:
        tmp = Path(directory)
        dictionary = tmp / 'dictionary.tsv'
        dictionary.write_bytes(gzip.decompress(DICT.read_bytes()))
        probes = build_probes(config, tmp, out, execute)
        for uid, inputs in paths.items():
            with TemporaryDirectory(prefix=f'{uid}-', dir=tmp) as scratch:
                row, waves = measure_one(config, inputs, probes, dictionary, Path(scratch), out, execute)
                if row['uid'] != uid:
                    raise ValueError(f'発話IDが登録内容と一致しません ({uid})')
                details[uid] = row
                evidence.update({f'{uid}_{name}': values for name, values in waves.items() if name != 'baseline'})
    np.savez_compressed(out / 'matched-pcm.npz', **evidence)
    rows = list(details.values())
    checks = {key: all(row['checks'][key] for row in rows) for key in rows[0]['checks']}
    same_length = [row['matched_pcm']['candidate_frames'] == row['matched_pcm']['reference_frames'] for row in rows]
    predictions = {
        'initial_pcm_agrees_in_all_utterances': all(row['matched_pcm']['initial_peak_difference']
                                                  <= config['limits']['initial_pcm_absolute'] for row in rows),
        'phone_boundaries_agree_in_all_utterances': all(same_length) and all(row['phones']['match'] for row in rows),
        'full_pcm_agrees_in_all_utterances': all(same_length) and all(
            row['matched_pcm']['maximum_absolute_difference'] <= config['limits']['pcm_absolute']
            and row['active_intervals']['upstream']['interval'] == row['active_intervals']['candidate']['interval'] for row in rows),
    }
    largest = max(rows, key=lambda row: row['matched_pcm']['maximum_absolute_difference'])
    return {'checks': checks, 'predictions': predictions, 'utterance_count': len(rows),
            'largest_difference_utterance': largest['uid'], 'utterances': details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    reference = tsp.open_run(case['reference'], revision)
    definition, case_path = saved_case(reference, RENDER_CASE)
    startup = tsp.open_run(case['startup_reference'], revision)
    _, startup_path = saved_case(startup, initial_tip.CASE)
    if case['recording_ids'] != definition['held_out_ids']:
        parser.error('確認用発話の対象または順序が元の登録と一致しません')
    paths = {uid: {name: tsp.verified_path(reference, f'artifacts/{uid}/{name}')
                   for name in ('candidate.json', 'candidate.wav', 'upstream.wav', 'inspect.json')}
             for uid in case['recording_ids']}
    modules = ('measure_tsp_active_duration.py', 'measure_tsp_fine_tip.py', 'measure_tsp_startup.py',
               'measure_tsp_seems_period_jitter.py', 'measure_tsp_seems_drift_only.py', 'measure_tsp_fine_variation.py',
               'measure_duet_child_output_gain.py', 'measure_duet_child_glottal_noise_origin.py', 'tsp_fine_trace.rs')
    sources = ('crates/chimera-cli/src/render.rs', 'crates/chimera/src/phonetics/planner.rs',
               'crates/chimera/src/voice/human_voice.rs', 'crates/chimera/src/sources/glottis.rs',
               'crates/chimera/tests/golden_planning.rs', 'crates/chimera/tests/golden_voice.rs')
    inputs = [CASE, Path(__file__).resolve(), case_path, startup_path, reference[0] / 'manifest.json',
              startup[0] / 'manifest.json', DICT, LOCAL, PROBE, OUTPUT_PATCH, SOURCE_PATCH,
              *(item for group in paths.values() for item in group.values()),
              *(WORKSPACE / 'tools' / name for name in modules),
              *(UPSTREAM / name for name in sources), *candidate_sources()]
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision}
    return record_measurement(args.run_id, CASE, inputs, details, lambda out, execute: measure(case, paths, out, execute),
                              command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
