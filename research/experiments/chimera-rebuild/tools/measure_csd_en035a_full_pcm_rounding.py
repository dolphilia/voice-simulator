"""CSDの登録曲の全曲を区間ごとに照合する。"""

import argparse
import os
from pathlib import Path
import subprocess

import numpy as np

import measure_csd_en005a_full_pcm_rounding as previous


earlier, full, lip, radiation, tsp, pcm = (previous.earlier, previous.full, previous.lip,
                                            previous.radiation, previous.tsp, previous.pcm)
CASE = radiation.WORKSPACE / 'cases/csd-en035a-full-pcm-rounding.json'
SAVED_FILES = earlier.SAVED_FILES


def study_inputs(study):
    rev = study['upstream_revision']
    song, reference = (tsp.open_run(study[key], rev) for key in ('full_song', 'reference'))
    before, definition = radiation.saved_case(reference, previous.CASE)
    adjustment = tsp.open_run(before['adjustment'], rev)
    adjusted, _ = radiation.saved_case(adjustment, earlier.CASE)
    stage, coeff = (tsp.open_run(adjusted[key], rev) for key in ('config', 'coefficients'))
    config, settings = radiation.saved_case(stage, lip.CONFIG)
    name = study['measurement']['song']
    directory = f'artifacts/{name}'
    archived = study.get('archive_outputs', {})
    official = tsp.open_run(study['standard_upstream'], rev) if 'standard_upstream' in study else song
    paths = {
        'spec': tsp.verified_path(song, archived.get('spec', directory + '/candidate-case.json')),
        'archived_research_pcm': tsp.verified_path(song, archived.get('research_pcm', directory + '/candidate.wav')),
        'archived_research_plan': tsp.verified_path(song, archived.get('research_plan', directory + '/candidate-plan.json')),
        'archived_upstream_pcm': tsp.verified_path(official, archived.get('upstream_pcm',
                                                                        f'artifacts/upstream/{name}-synth.wav')),
        'reference_capture': tsp.verified_path(reference, f'artifacts/{SAVED_FILES[0]}'),
        'reference_definition': definition,
        'config': settings,
        'coefficients': tsp.verified_path(coeff, 'artifacts/coefficients.json'),
        **{f'{key}_manifest': run[0] / 'manifest.json' for key, run in
           (('song', song), ('reference', reference), ('adjustment', adjustment), ('stage', stage), ('coeff', coeff))},
    }
    if 'standard_upstream' in study:
        paths['official_manifest'] = official[0] / 'manifest.json'
    comparisons = extra_songs(study)
    if comparisons:
        paths['reference_summary'] = tsp.verified_path(reference, 'summary.json')
    for name, definition in comparisons.items():
        comparison = tsp.open_run(definition, rev)
        paths[f'{name}_capture'] = tsp.verified_path(comparison, f'artifacts/{SAVED_FILES[0]}')
        paths[f'{name}_manifest'] = comparison[0] / 'manifest.json'
        paths[f'{name}_summary'] = tsp.verified_path(comparison, 'summary.json')
    if 'short_reference' in study:
        short = tsp.open_run(study['short_reference'], rev)
        paths['short_manifest'] = short[0] / 'manifest.json'
        paths['short_capture'] = tsp.verified_path(short, f'artifacts/{SAVED_FILES[0]}')
        for mode in ('upstream', 'research'):
            paths[f'short_{mode}_plan'] = tsp.verified_path(short, f'artifacts/{mode}-plan.json')
    return config, paths


def extra_songs(study):
    if 'comparison' in study:
        return {'en035a': study['comparison']}
    return study.get('comparisons', {})


def pcm_prefix(current, archived_path, limit, rate):
    result = {}
    with np.load(archived_path, allow_pickle=False) as previous_song:
        for name in earlier.CONDITIONS:
            a = current[f'{name}_pcm'][:limit]
            b = previous_song[f'{name}_pcm'][:limit]
            if len(a) != limit or len(b) != limit:
                raise ValueError('冒頭のPCMを指定した長さまで比較できません')
            differences = np.flatnonzero(a.view('<u4') != b.view('<u4'))
            length = int(differences[0]) if differences.size else limit
            result[name] = {'matched_prefix_frames': length, 'compared_frames': limit,
                            'matched_prefix_seconds': length / rate}
    return result


def intervals(current, measure, config):
    a, b = earlier.CONDITIONS
    output = [current[f'{key}_output'] for key in (a, b)]
    waves = [current[f'{key}_pcm'] for key in (a, b)]
    bits = [wave.view('<u4') for wave in waves]
    above = [values[:, pcm.COLUMNS.index('envelope')] > config['stage']['peak_threshold'] for values in output]
    pcm_difference = bits[0] != bits[1]
    distance = np.abs(full.sample_rank(waves[0]) - full.sample_rank(waves[1]))
    by_region = {}
    for name, (lo, hi) in measure['segments'].items():
        mask = slice(lo, hi)
        common = above[0][mask] & above[1][mask]
        by_region[name] = {
            'upstream_limiter': int(np.count_nonzero(above[0][mask])),
            'research_limiter': int(np.count_nonzero(above[1][mask])),
            'limiter_flags_differ': int(np.count_nonzero(above[0][mask] != above[1][mask])),
            'pcm_unequal_values': int(np.count_nonzero(distance[mask])),
            'pcm_one_ulp': int(np.count_nonzero(distance[mask] == 1)),
            'pcm_more_than_one_ulp': int(np.count_nonzero(distance[mask] > 1)),
            'pcm_bit_differences_when_both_limit': int(np.count_nonzero(pcm_difference[mask] & common)),
        }
    return by_region


def archived_comparison(current, paths, plan, proof, measure):
    count, rate = measure['frames'], measure['sample_rate_hz']
    normal = current['upstream_standard_pcm']
    research = current['research_normal_pcm']
    upstream_archive = earlier.song.samples(paths['archived_upstream_pcm'], rate, count)
    research_archive = earlier.song.samples(paths['archived_research_pcm'], rate, count)
    return {
        'upstream_standard_pcm': bool(lip.bit_equal(normal, upstream_archive)),
        'upstream_standard_executed': proof['upstream_standard']['pcm'] == lip.pcm_digest(normal)
        and proof['upstream_standard']['plan_matches'],
        'research_pcm': bool(lip.bit_equal(research, research_archive)),
        'research_plan': plan['gestures'] == tsp.read(paths['archived_research_plan'])['gestures'],
        'upstream_standard_difference': full.metrics(normal.astype(np.float64) - upstream_archive),
        'research_difference': full.metrics(research.astype(np.float64) - research_archive),
    }


def compare_with_other_songs(result, current, paths, measure, song_names):
    baselines = {'en005a': tsp.read(paths['reference_summary']),
                 **{name: tsp.read(paths[f'{name}_summary']) for name in song_names}}
    prefixes = {'en005a': result['reference_prefix']}
    for name in song_names:
        limit = min(measure['first_beat_frame'], baselines[name]['plan']['first_beat_frame'])
        prefixes[name] = pcm_prefix(current, paths[f'{name}_capture'], limit, measure['sample_rate_hz'])
    songs = {measure['song']: result, **baselines}
    summary = {
        name: {
            'frames': data['plan']['frames'],
            'peaks': data['peaks'],
            'region_errors': data['comparison']['segments'],
            'limiter': data['limiter'],
            'pcm_squared_error_fraction_at_peak': data['comparison']['pcm_squared_error_fraction_at_outlier'],
        } for name, data in songs.items()
    }
    prefix_witness_shared = all(
        row['matched_prefix_frames'] > measure['common_prefix_witness_frame']
        for rows in prefixes.values() for row in rows.values()
    )
    result['hypotheses']['startup_witness_is_shared'] = prefix_witness_shared
    return {'songs': summary, 'common_pcm_prefixes': prefixes}


def compare_with_short_render(result, current, paths, measure, upper_plan, research_plan):
    prefix = pcm_prefix(current, paths['short_capture'], measure['short_frames'], measure['sample_rate_hz'])
    short_upstream = tsp.read(paths['short_upstream_plan'])['plans']
    short_research = tsp.read(paths['short_research_plan'])['song']['scores']
    research_scores = research_plan['song']['scores']
    plans = {
        'upstream': upper_plan['plans'][:len(short_upstream)] == short_upstream,
        'research': research_scores[:len(short_research)] == short_research,
        'archived_full_research': research_scores == tsp.read(paths['archived_research_plan'])['song']['scores'],
    }
    lengths = [row['matched_prefix_frames'] for row in prefix.values()]
    result['checks']['short_render_plans_and_archived_full_research_scores_match'] = all(plans.values())
    result['hypotheses'].update(
        precast_maximum_is_startup_witness=result['peaks']['precast']['frame'] == measure['common_prefix_witness_frame'],
        short_pcm_shared_through_second_phrase=min(lengths) >= measure['short_minimum_common_frames'],
        short_pcm_changes_with_later_gestures=max(lengths) < measure['short_frames'],
    )
    return {'plans_match': plans, 'common_pcm_prefixes': prefix}


def analyze(study, out, config, paths):
    m = study['measurement']
    spec = tsp.read(paths['spec'])['song_voice']
    coefficients = tsp.read(paths['coefficients'])
    upper_plan, research_plan = (tsp.read(out / f'{name}-plan.json') for name in ('upstream', 'research'))
    plan, spans, expected = previous.plan_details(spec, upper_plan, m)
    proof = tsp.read(out / SAVED_FILES[1])
    with np.load(out / SAVED_FILES[0], allow_pickle=False) as data:
        current = dict(data)
    states = previous.rows_by_source(current)
    replay = earlier.replay_output(current, states, m, config, spec['voice']['output_gain'], coefficients,
                                   output_limiter=True)
    cast, limited = previous.precast_values(current, config)
    compare, peaks, amplitudes, internal, output = previous.compare_song(m, current, states, coefficients, spans, cast)
    archived = archived_comparison(current, paths, research_plan, proof, m)
    first_beat = m['first_beat_frame']
    if 'reference_summary' in paths:
        first_beat = min(first_beat, tsp.read(paths['reference_summary'])['plan']['first_beat_frame'])
    prefix = pcm_prefix(current, paths['reference_capture'], first_beat, m['sample_rate_hz'])
    by_interval = intervals(current, m, config)
    checks = {
        'recorded_score_and_length': expected and plan['upstream_dropped_gestures'] == 0 and archived['research_plan'],
        'standard_fixed_upstream_and_research_match_whole_archives': all(
            archived[key] for key in ('upstream_standard_pcm', 'upstream_standard_executed', 'research_pcm')),
        'matched_normal_and_observed_pcm_and_score_match': (
            all(proof[name]['ordinary'] == proof[name]['observed'] == lip.pcm_digest(current[f'{name}_pcm'])
                and proof[name]['plan_matches'] for name in earlier.CONDITIONS)
            and proof['research_normal']['csv_pcm_matches']),
        'full_song_radiation_and_output_replayed': all(all(row.values()) for row in replay.values()),
        'recorded_output_state_predicts_final_pcm': all(
            lip.bit_equal(samples.astype('<f4'), current[f'{name}_pcm']) for name, samples in cast.items()),
        'same_settings_tolerance_and_rounding_midpoints': compare['pcm_all_one_ulp_straddle']
        and compare['full']['pcm']['peak'] <= m['same_settings_pcm_tolerance'],
        'intervals_cover_all_pcm_differences_and_limiter_activity': (
            all(sum(row[key] for row in by_interval.values()) == compare[key]
                for key in ('pcm_unequal_values', 'pcm_one_ulp', 'pcm_more_than_one_ulp'))
            and all(sum(row[f'{mode}_limiter'] for row in by_interval.values()) == limited[f'{mode}_normal']['limited_frames']
                    for mode in ('upstream', 'research'))),
    }
    share = amplitudes['multiple_ulp_quiet_fraction']
    hypotheses = {
        'startup_witness_is_shared': all(row['matched_prefix_frames'] > m['common_prefix_witness_frame']
                                         for row in prefix.values()),
        'pcm_maximum_after_first_beat': m['first_beat_frame'] <= peaks['pcm']['frame'] < m['last_score_end_frame'],
        'precast_and_pcm_peaks_differ': peaks['precast']['frame'] != peaks['pcm']['frame'],
        'same_limiter_active_frames': all(row['limiter_flags_differ'] == 0 for row in by_interval.values()),
        'multi_ulp_differences_are_mainly_quiet': share is not None and share >= m['multi_ulp_minimum_quiet_share'],
    }
    result = {'checks': checks, 'hypotheses': hypotheses, 'plan': plan, 'archive': archived,
              'output_replay': replay, 'comparison': compare, 'peaks': peaks, 'amplitude_by_ulp': amplitudes,
              'limiter': limited, 'intervals': by_interval, 'reference_prefix': prefix,
              'internal_differences': internal, 'output_differences': output}
    if baselines := extra_songs(study):
        result['song_comparisons'] = compare_with_other_songs(result, current, paths, m, baselines)
    if 'short_reference' in study:
        result['short_extension'] = compare_with_short_render(result, current, paths, m, upper_plan, research_plan)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='登録済みの曲のケース定義')
    args = parser.parse_args()
    ws, upper = radiation.WORKSPACE, radiation.UPSTREAM
    case = args.case.resolve()
    study = tsp.read(case)
    if case.parent != CASE.parent or study['id'] != case.stem:
        parser.error('ケースの保存先またはIDが登録と一致しません')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=upper, text=True).strip()
    if revision != study['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=upper):
        parser.error('変更のない固定上流版が必要です')
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('計測は作業用ディスクを指定してください')
    config, paths = study_inputs(study)
    inputs = [case, Path(__file__).resolve(), *paths.values(), earlier.song.PROBE,
              *(Path(mod.__file__) for mod in (previous, earlier, earlier.song, earlier.matched_pcm, full, pcm)),
              *earlier.prefix.capture_dependencies(),
              *(upper / 'crates/chimera/tests' / name for name in ('sing_fast.rs', 'sung_release.rs', 'denormals.rs'))]

    def measure(out, execute):
        earlier.capture(study, paths['spec'], out, execute, capture_standard=True)
        return analyze(study, out, config, paths)

    details = {'case_id': study['id'], 'case_revision': study['revision'], 'upstream_revision': revision}
    return radiation.record_measurement(args.run_id, case, list(dict.fromkeys(inputs)), details, measure,
                                        command=None, input_root=ws.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
