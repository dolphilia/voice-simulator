"""同じ先行枝で、先行PCMの値または先行する量子数を比較する。"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

import measure_worklet_live_song_context_lead as lead


song = lead.song
READ = lead.READ
CASE = song.WORKSPACE / 'cases/worklet-live-song-fast-zero-lead-pcm.json'


def compare_pairs(trials, order):
    pairs = []
    for number, pair_order in enumerate(order, 1):
        modes = sorted(pair_order)
        group = {row['mode']: row for row in trials if row['pair'] == number and 'error' not in row}
        if set(group) != set(modes):
            continue
        pairs.append({'pair': number,
                      'missing_frames_before_song': {mode: group[mode]['missing_frames_before_song'] for mode in modes},
                      'lead_from_first_voice_frame': {mode: group[mode]['clock']['lead_from_startup_frames'] for mode in modes},
                      'marker_callbacks_before_voice': {mode: group[mode]['marker']['marker_callbacks_before_voice'] for mode in modes},
                      'lead_from_first_marker_frame': {
                          mode: group[mode]['clock']['start_frame'] - group[mode]['marker']['first_frame'] for mode in modes}})
    return pairs


def measure(study, prior, spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun):
    markers = {mode: {**prior['marker'], **overrides, 'observe_input': True}
               for mode, overrides in study['marker_pcm_overrides'].items()}
    order = study['condition_order']
    checks, trials = lead.capture_trials(order, markers, prior['marker_observation_quanta'],
                                         spec, fixed, fixed_path, live, offline, upper, wasm, artifacts, execute, bun)
    pairs = compare_pairs(trials, order)
    expected_frames = spec['startup_contiguous_callbacks'] * spec['quantum'] + spec['lead_frames']
    predictions = {'both_leads_have_no_startup_gaps': len(pairs) == len(order) and all(
        not any(row['missing_frames_before_song'].values()) for row in pairs),
        'both_leads_start_at_expected_distance': len(pairs) == len(order) and all(
            all(distance == expected_frames for distance in row['lead_from_first_voice_frame'].values()) for row in pairs)}
    if 'ready_quanta_contrast' in study:
        quantum = spec['quantum']
        expected = quantum * (markers['long']['ready_quanta'] - markers['short']['ready_quanta'])
        tolerance = quantum * study['ready_quanta_contrast']['maximum_reduction_error_quanta']
        for row in pairs:
            starts = row['lead_from_first_marker_frame']
            row['shorter_wait_reduction_frames'] = starts['long'] - starts['short']
            row['expected_reduction_frames'] = expected
        predictions['marker_to_song_interval_shortens_as_registered'] = len(pairs) == len(order) and all(
            abs(row['shorter_wait_reduction_frames'] - expected) <= tolerance for row in pairs)
    return {'checks': checks, 'predictions': predictions, 'paired_startup': pairs, 'trials': trials}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--case', type=Path, default=CASE, help='先行PCMまたは先行量子数の比較ケース')
    args = parser.parse_args()
    case_path = args.case.resolve(strict=True)
    study = READ(case_path)
    cases = CASE.parent
    prior_path = cases / study['lead_study']
    prior = READ(prior_path)
    realtime_path = cases / prior['realtime_study']
    realtime = READ(realtime_path)
    offline_path = cases / realtime['offline_study']
    offline_case = READ(offline_path)
    fixed_path = cases / offline_case['capture_case']
    live_path = cases / realtime['live_case']
    fixed, live = READ(fixed_path), READ(live_path)
    revision = study['upstream_revision']
    spec = realtime['measurement']
    zero_pcm = {'multiplier': 0, 'offset': prior['marker']['center']}
    compare_wait = 'ready_quanta_contrast' in study
    expected_overrides = ({'short': {**zero_pcm, 'ready_quanta': 8}, 'long': {**zero_pcm, 'ready_quanta': 32}}
                          if compare_wait else {'pattern': {}, 'zero': zero_pcm})
    if (any(c['upstream_revision'] != revision for c in (prior, realtime, offline_case, fixed, live))
            or any(sorted(pair) != sorted(expected_overrides) for pair in study['condition_order'])
            or study['marker_pcm_overrides'] != expected_overrides
            or subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=song.UPSTREAM, text=True).strip() != revision
            or subprocess.check_output(['git', 'status', '--porcelain'], cwd=song.UPSTREAM, text=True)):
        parser.error('固定上流、先行信号のPCM、または比較条件が一致しません')
    prior_run = song.run_manifest(study['lead_reference_run'], prior['id'], revision)
    offline = song.run_manifest(realtime['offline_run'], offline_case['id'], revision)
    upstream = song.run_manifest(offline_case['reference_run'], 'song-voice-fast-constriction-source', revision)
    if any(run[1]['status'] != 'pass' for run in (prior_run, offline, upstream)):
        parser.error('先行信号、オフライン、または固定上流の保存基準が揃いません')
    label = prior['condition']
    reference = {name: song.verified_path(offline, f'artifacts/{label}/{name}') for name in (
        'input.json', 'browser.wav', 'browser.json', 'browser-case.json')}
    upper = song.verified_path(upstream, 'artifacts/upstream-pcm.f32')
    wasm = song.verified_path(offline, 'artifacts/vocal_wasm.wasm')
    prior_summary = song.verified_path(prior_run, 'summary.json')
    inputs = [case_path, prior_path, realtime_path, offline_path, fixed_path, live_path, Path(__file__).resolve(),
              upper, wasm, prior_summary, *reference.values(), *(r[0] / 'manifest.json' for r in (prior_run, offline, upstream))]
    if compare_wait:
        zero_path = cases / study['zero_lead_study']
        zero_study = READ(zero_path)
        zero_run = song.run_manifest(study['zero_lead_reference_run'], zero_study['id'], revision)
        if zero_run[1]['status'] != 'pass' or zero_study['marker_pcm_overrides']['zero'] != zero_pcm:
            parser.error('先行PCMが0の保存済み対照が一致しません')
        inputs.extend([zero_path, zero_run[0] / 'manifest.json', song.verified_path(zero_run, 'summary.json')])
    bun = ['bun'] if shutil.which('bun') else ['npx', '--offline', '--yes', '--package=bun@1.4.4', '--', 'bun']
    metadata = {'case_id': study['id'], 'upstream_revision': revision, 'turbulence_seed': offline_case['noise_seed'],
                'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv],
                'node': subprocess.check_output(['node', '--version'], text=True).strip(),
                'bun': subprocess.check_output([*bun, '--version'], text=True).strip()}
    inputs.extend([*song.web_sources(), *song.shared.candidate_sources(), *(Path(module.__file__) for module in (
        lead, lead.realtime, lead.realtime.cross, song, song.wasm, song.shared, song.realtime))])
    return song.shared.record_measurement(args.run_id, case_path, inputs, metadata,
        lambda artifacts, execute: measure(study, prior, spec, fixed, fixed_path, live, reference, upper, wasm,
                                           artifacts, execute, bun), command=None, input_root=song.ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
