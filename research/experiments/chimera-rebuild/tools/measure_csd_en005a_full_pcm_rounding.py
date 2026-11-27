"""CSDの確認曲en005aの全区間で放射からPCMへの丸めを照合する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_csd_en001a_two_phrase_pcm_rounding as earlier


full, lip, radiation, tsp, pcm = earlier.full, earlier.lip, earlier.radiation, earlier.tsp, earlier.pcm
CASE = radiation.WORKSPACE / 'cases/csd-en005a-full-pcm-rounding.json'
SAVED_FILES = earlier.SAVED_FILES
ORIGINAL_ERROR = '観測区間でリミッターが作動し、DC出力を変換前の値に使えません'


def study_inputs(study):
    rev = study['upstream_revision']
    song, startup, adjustment = (tsp.open_run(study[key], rev) for key in ('full_song', 'startup', 'adjustment'))
    adjusted_study, saved = radiation.saved_case(adjustment, earlier.CASE)
    stage, coeff = (tsp.open_run(adjusted_study[key], rev) for key in ('config', 'coefficients'))
    config, settings = radiation.saved_case(stage, lip.CONFIG)
    paths = {
        'spec': tsp.verified_path(song, 'artifacts/candidate-case.json'),
        'old_pcm': tsp.verified_path(song, 'artifacts/candidate.wav'),
        'old_plan': tsp.verified_path(song, 'artifacts/candidate-inspect.json'),
        'startup_upper': tsp.verified_path(startup, 'artifacts/matched.f32'),
        'startup_plan': tsp.verified_path(startup, 'artifacts/matched.json'),
        'startup_research': tsp.verified_path(startup, 'artifacts/candidate.wav'),
        'adjustment_spec': tsp.verified_path(tsp.open_run(adjusted_study['reference'], rev),
                                           'artifacts/candidate-short-128.json'),
        'adjustment_capture': tsp.verified_path(adjustment, f'artifacts/{SAVED_FILES[0]}'),
        'adjustment_definition': saved, 'config': settings,
        'coefficients': tsp.verified_path(coeff, 'artifacts/coefficients.json'),
        **{f'{key}_manifest': row[0] / 'manifest.json' for key, row in
           (('song', song), ('startup', startup), ('adjustment', adjustment), ('stage', stage), ('coeff', coeff))},
    }
    return config, paths


def rows_by_source(current):
    return {name: dict(zip(earlier.SOURCE_FIELDS, current[f'{name}_source'].T, strict=True))
            for name in earlier.CONDITIONS}


def validate_adjustment(paths, config, coefficients):
    measure = tsp.read(paths['adjustment_definition'])['measurement']
    gain = tsp.read(paths['adjustment_spec'])['song_voice']['voice']['output_gain']
    with np.load(paths['adjustment_capture'], allow_pickle=False) as saved:
        current = dict(saved)
    return earlier.replay_output(current, rows_by_source(current), measure, config, gain, coefficients)


def plan_details(spec, upper_plan, measure):
    score = spec['scores']
    frames = measure['frames']
    rate = measure['sample_rate_hz']
    start = round(score[0]['start_seconds'] * rate)
    last = score[-1]
    end = round((last['start_seconds'] + sum(note['beats'] for note in last['notes']) * 60 / last['bpm']) * rate)
    spans = [(phrase['id'], round(phrase['start_seconds'] * rate),
              round((phrase['start_seconds'] + sum(note['beats'] for note in phrase['notes']) * 60 / phrase['bpm']) * rate))
             for phrase in score]
    detail = {'phrases': len(score), 'notes': sum(len(phrase['notes']) for phrase in score),
              'frames': round(spec['render_end_seconds'] * rate), 'first_beat_frame': start,
              'last_score_end_frame': end, 'upstream_dropped_gestures': upper_plan['dropped']}
    expected = all(detail[key] == measure[key] for key in ('phrases', 'notes', 'frames', 'first_beat_frame',
                                                           'last_score_end_frame'))
    expected &= [plan['id'] for plan in upper_plan['plans']] == [phrase['id'] for phrase in score]
    expected &= measure['segments'] == {'before_first_beat': [0, start], 'score': [start, end],
                                       'after_last_score_end': [end, frames]}
    return detail, spans, expected


def precast_values(current, config):
    cast, compression = {}, {}
    for name in earlier.CONDITIONS:
        output = current[f'{name}_output']
        dc, envelope = output[:, pcm.COLUMNS.index('dc_removed')], output[:, pcm.COLUMNS.index('envelope')]
        samples, limited, softened = pcm.limited_output(dc, envelope, config['stage'])
        active = np.flatnonzero(limited)
        cast[name] = samples
        compression[name] = {
            'envelope_peak': float(envelope.max()),
            'first_frame': int(active[0]) if active.size else None,
            'last_frame': int(active[-1]) if active.size else None,
            'limited_frames': int(active.size),
            'soft_clip_frames': int(np.count_nonzero(softened)),
        }
    return cast, compression


def compare_song(measure, current, states, coefficients, spans, cast):
    a, b = earlier.CONDITIONS
    upper, research = (current[f'{name}_pcm'] for name in (a, b))
    peak = int(np.argmax(np.abs(research.astype(np.float64) - upper)))
    parameters = measure | {'pcm_outlier_to_exclude': peak}
    poles = (coefficients['upstream']['dc_pole'], coefficients['candidate']['dc_pole'])
    summary = full.compare(a, b, current, parameters, poles, precast=(cast[a], cast[b]))
    region = {}
    for label, field in (('precast', 'precast'), ('pcm', 'pcm')):
        at = summary['full'][field]['peak_frame']
        phrase = next((name for name, start, end in spans if start <= at < end), None)
        segment = next(key for key, (start, end) in measure['segments'].items() if start <= at < end)
        region[label] = {'frame': at, 'seconds': at / measure['sample_rate_hz'], 'segment': segment, 'phrase': phrase}
    amplitudes = earlier.matched_pcm.amplitude_groups(upper, research, measure['quiet_pcm_threshold'])
    internal = {field: full.metrics(states[b][field] - states[a][field]) for field in earlier.SOURCE_FIELDS}
    left, right = (current[f'{name}_output'] for name in (a, b))
    output = {field: full.metrics(right[:, i] - left[:, i]) for i, field in enumerate(pcm.COLUMNS[2:], start=2)}
    return summary, region, amplitudes, internal, output


def analyze(study, out, config, paths):
    m = study['measurement']
    spec = tsp.read(paths['spec'])['song_voice']
    coeff = tsp.read(paths['coefficients'])
    adjustment = validate_adjustment(paths, config, coeff)
    upper_plan, research_plan = (tsp.read(out / f'{name}-plan.json') for name in ('upstream', 'research'))
    plan, spans, expected = plan_details(spec, upper_plan, m)
    with np.load(out / SAVED_FILES[0], allow_pickle=False) as saved:
        current = dict(saved)
    states = rows_by_source(current)
    replay = earlier.replay_output(current, states, m, config, spec['voice']['output_gain'], coeff, output_limiter=True)
    cast, limited = precast_values(current, config)
    comparison, peaks, amplitudes, internal, output = compare_song(m, current, states, coeff, spans, cast)
    count, rate, n = (m[key] for key in ('frames', 'sample_rate_hz', 'archived_prefix_frames'))
    gain_proof = tsp.read(out / SAVED_FILES[1])
    upper, research = (current[f'{name}_pcm'] for name in earlier.CONDITIONS)
    old_upper = np.fromfile(paths['startup_upper'], dtype='<f4')
    old_research = earlier.song.samples(paths['old_pcm'], rate, count)
    old_research_prefix = earlier.song.samples(paths['startup_research'], rate, n)
    archived = {
        'upstream_first_20_ms': bool(lip.bit_equal(upper[:n], old_upper)),
        'upstream_plan': upper_plan == tsp.read(paths['startup_plan']),
        'research_first_20_ms': bool(lip.bit_equal(research[:n], old_research_prefix)),
        'research_whole_song': bool(lip.bit_equal(research, old_research)),
        'research_plan_gestures': research_plan['gestures'] == tsp.read(paths['old_plan'])['gestures'],
        'research_whole_song_change': full.metrics(research.astype(np.float64) - old_research),
        'research_first_20_ms_change': full.metrics(research[:n].astype(np.float64) - old_research_prefix),
    }
    checks = {
        'recorded_score_and_duration': expected and archived['research_plan_gestures'],
        'upstream_prefix_and_score_match_previous_capture': archived['upstream_first_20_ms'] and archived['upstream_plan'],
        'normal_and_observed_pcm_and_score_match': (
            all(gain_proof[name]['ordinary'] == gain_proof[name]['observed'] == lip.pcm_digest(current[f'{name}_pcm'])
                and gain_proof[name]['plan_matches'] for name in earlier.CONDITIONS)
            and gain_proof['research_normal']['csv_pcm_matches']),
        'full_song_output_stages_replayed': all(all(row.values()) for row in replay.values()),
        'observed_envelope_and_dc_predict_final_pcm': all(
            lip.bit_equal(samples.astype('<f4'), current[f'{name}_pcm']) for name, samples in cast.items()),
        'adjustment_song_output_still_replays': all(all(row.values()) for row in adjustment.values()),
        'same_settings_tolerance_and_pcm_midpoints': comparison['pcm_all_one_ulp_straddle']
        and comparison['full']['pcm']['peak'] <= m['same_settings_pcm_tolerance'],
    }
    first = internal[radiation.RADIATION]['first_nonzero_frame']
    share = amplitudes['multiple_ulp_quiet_fraction']
    hypotheses = {
        'radiation_differs_in_first_output_pair': first is not None and first < 2,
        'pcm_maximum_after_first_beat': peaks['pcm']['frame'] >= m['first_beat_frame'],
        'same_precast_and_pcm_peak_position': peaks['precast']['frame'] == peaks['pcm']['frame'],
        'multi_ulp_differences_are_mainly_quiet': share is not None and share >= m['multi_ulp_minimum_quiet_share'],
    }
    return {'checks': checks, 'hypotheses': hypotheses, 'plan': plan, 'archive': archived, 'output_replay': replay,
            'adjustment_replay': adjustment, 'comparison': comparison, 'peaks': peaks, 'amplitude_by_ulp': amplitudes,
            'limiter': limited,
            'internal_differences': internal, 'output_differences': output,
            'initial_source_rows': {name: current[f'{name}_source'][:m['initial_internal_samples']].tolist()
                                    for name in earlier.CONDITIONS},
            'source_field_order': list(earlier.SOURCE_FIELDS)}


def capture_inputs(study, run_id):
    capture = tsp.run_manifest(run_id, study['id'], study['upstream_revision'])
    path, manifest = capture
    saved, definition = radiation.saved_case(capture, CASE)
    approved = manifest['status'] == 'pass' or (manifest['status'] == 'fail' and manifest.get('error') == ORIGINAL_ERROR)
    if saved != study or not approved:
        raise ValueError(f'採取実行のケースまたは停止理由が一致しません ({run_id})')
    return path / 'manifest.json', definition, [tsp.verified_path(capture, f'artifacts/{name}') for name in SAVED_FILES]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--capture-run', help='保存済みの全曲採取を検算し直す')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    study = tsp.read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    config, paths = study_inputs(study)
    inputs = [CASE, Path(__file__).resolve(), *paths.values(), earlier.song.PROBE,
              *(Path(module.__file__) for module in (earlier, earlier.song, earlier.matched_pcm, full, pcm)),
              *earlier.prefix.capture_dependencies(),
              *(upper / 'crates/chimera/tests' / name for name in ('sing_fast.rs', 'sung_release.rs', 'denormals.rs'))]

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    if args.capture_run:
        manifest, definition, captured = capture_inputs(study, args.capture_run)
        inputs.extend((manifest, definition, *captured))
        details.update(capture_run=args.capture_run, capture_manifest_sha256=tsp.sha256(manifest))

    def measure(out, execute):
        if args.capture_run:
            for path in captured:
                os.link(path.resolve(), out / path.name)
        else:
            earlier.capture(study, paths['spec'], out, execute)
        return analyze(study, out, config, paths)

    return radiation.record_measurement(args.run_id, CASE, list(dict.fromkeys(inputs)), details, measure,
                                        command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
