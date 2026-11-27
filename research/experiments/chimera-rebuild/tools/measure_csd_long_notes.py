"""注釈で選んだCSDの長音を、録音と固定上流・再実装の通常描画で比較する。"""

import argparse
from pathlib import Path
import os
import subprocess
import sys

from measure_csd_envelope_timing import verified_file, waveforms
from measure_csd_song_f0 import NotePitch, measure_notes, reference_error
from measure_csd_song_planning import parse_notes, phrase_inputs
from measure_csd_vibrato_aperiodicity import measure_song
from measure_speech_timing import read, write
from measure_uniform_tube import candidate_sources, record_measurement
from select_csd_long_notes import CASE, packed_path, verified_selection
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


def plan_differences(inspected, official, tolerance):
    notes = [n for p in inspected['song']['scores'] for n in p['plan']['notes']]
    annotation = official['notes']
    pairs = list(zip(notes, annotation, strict=True))
    times = []
    for index, (one, other) in enumerate(pairs):
        actual = one['nucleus_start_seconds']
        rounded = other['plannedVowelStart']
        accept = abs(actual-other['start']) <= tolerance
        times.append({'note_index': index, 'annotation_seconds': other['start'],
                      'upstream_seconds_rounded': rounded, 'candidate_seconds': actual,
                      'absolute_rounding_difference_seconds': abs(rounded-actual),
                      'candidate_aligned': accept, 'upstream_aligned': other['aligned'],
                      'same_beat_and_midi': abs(one['beat_seconds']-other['start']) <= 1e-10
                                            and one['note']['midi'] == other['midi']})
    return times


def candidate_render(out, filename, original, phrases, sample_rate, frames, blocks, execute):
    cli = str(WORKSPACE / 'target/release/vocal-cli')
    working = out / filename
    working.mkdir()
    spec = working / 'candidate-case.json'
    song = {**original['song_voice'], 'scores': [phrase[0] for phrase in phrases],
            'render_end_seconds': frames/sample_rate}
    write(spec, {'song_voice': song})
    state = working / 'candidate-plan.json'
    execute([cli, 'inspect', str(spec)], stdout=state)
    primary = working / 'candidate.wav'
    alternate = out.parent / 'tmp' / f'{filename}-alternate.wav'
    for target, size in zip((primary, alternate), blocks, strict=True):
        execute([cli, 'render-pcm', str(spec), str(target), '--no-trace', str(size)], cwd=working)
    h1, h2 = sha256(primary), sha256(alternate)
    if h1 == h2:
        alternate.unlink()
    else:
        alternate.rename(working / alternate.name)
    return primary, read(state), h1, h2


def check_longest_eligible(song_result, ranked):
    potential = {row['note_index'] for row in ranked['annotation_long_notes']}
    for note in song_result['notes']:
        if note['note_index'] not in potential and any(s['eligible'] for s in note['signals'].values()):
            return False
    return True


def evaluate(case, planning, pitch, periodicity, sources, original, out, execute):
    input_dir = out.parent / 'tmp' / 'input'
    for _, ranked, annotation, wav, _ in sources:
        for kind, path in (('csv', annotation), ('wav', wav)):
            link = input_dir / packed_path(ranked['id'], kind)
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(path)
    reference = out / 'upstream'
    body = planning['score']['body']
    names = ','.join(source[1]['id'] for source in sources)
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::'],
            cwd=UPSTREAM, stdout=out / 'fixed-compare-tests.log')
    execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera', '--test', 'golden_analysis'],
            cwd=UPSTREAM, stdout=out / 'fixed-analysis-tests.log')
    execute(['cargo', 'run', '--locked', '--offline', '--release', '-p', 'chimera-cli', '--', 'compare', 'csd',
             str(input_dir / 'CSD'), str(reference), '--songs', names, '--body', body, '--jobs', '1', '--float'],
            cwd=UPSTREAM, stdout=out / 'fixed-csd.log')
    execute(['cargo', 'build', '--locked', '--offline', '--release', '-p', 'vocal-cli'])
    report = read(reference / 'report.json')
    if report['errors'] or {s['summary']['id'] for s in report['songs']} != set(names.split(',')):
        raise ValueError(f"CSDの通常比較に曲の欠測があります ({report['errors']})")
    scores = read(reference / 'score.json')
    published = {s['summary']['id']: s for s in report['songs']}
    checks, results = {}, {}
    settings = case['analysis']
    rate = planning['measurement']['output_rate_hz']
    if original['song_voice']['body'] != body or original['song_voice']['vibrato_cents'] != planning['score']['vibrato_cents']:
        raise ValueError('保存した合成設定の体型またはビブラート深さが登録と一致しません')
    for split, rank, annotation, recording, wav in sources:
        song = rank['id']
        notes = parse_notes(annotation, planning['score'])
        phrases = phrase_inputs(song, notes, planning['score'])
        original_report = published[song]
        frames = (2*wav['frames']*rate + wav['rate_hz']) // (2*wav['rate_hz'])
        fresh, inspected, primary_hash, alternate_hash = candidate_render(
            out, song, original, phrases, rate, frames, settings['candidate_host_block_frames'], execute)
        plans = plan_differences(inspected, original_report, settings['alignment_tolerance_seconds'])
        comparisons = {'note_count': len(plans) == rank['notes'],
                       'same_beat_midi_and_alignment': all(row['same_beat_and_midi'] and
                            row['candidate_aligned'] == row['upstream_aligned'] for row in plans),
                       'same_vowel_start_at_report_precision': all(row['absolute_rounding_difference_seconds']
                            <= planning['measurement']['rounded_reference_tolerance_seconds'] for row in plans),
                       'candidate_matches_block_partitions': primary_hash == alternate_hash,
                       'registered_output_length': inspected['output_frames'] == frames}
        if len(phrases) != len(inspected['song']['scores']):
            raise ValueError('確定したスコアと候補の句の数が一致しません')
        write(out / song / 'vowel-alignment.json', {'notes': plans,
                  'first_nonzero_difference': next((r for r in plans if r['absolute_rounding_difference_seconds']), None)})
        paths = (recording, reference / f'{song}-synth.wav', fresh)
        config = {'measurement': pitch,
                  'render': {'recording_rate_hz': wav['rate_hz'], 'recording_frames': wav['frames'],
                             'sample_rate_hz': rate, 'output_frames': frames}}
        f0_csv = out / song / 'note-f0-frames.csv'
        minimum = min(n['midi'] for n in original_report['notes'])
        tracks = {key: NotePitch(pcm, fs, minimum, pitch) for key, (pcm, fs) in waveforms(paths, config['render']).items()}
        baseline = measure_notes(original_report['notes'], tracks, pitch, f0_csv)
        comparisons['published_f0_and_coverage'], f0_diffs = reference_error(baseline, original_report['notes'], pitch)
        del tracks
        choice = {'id': song, 'split': split, 'notes': rank['notes'], 'centers_per_signal': rank['total_frames']}
        result = measure_song({'measurement': periodicity}, choice, original_report,
                              scores['train' if split == 'calibration' else 'heldout'],
                              f0_csv, config, paths, out / song)
        comparisons.update(result['checks'])
        comparisons['eligible_runs_inside_registered_grid'] = check_longest_eligible(result, rank)
        checks.update({f'{song}_{k}': ok for k, ok in comparisons.items()})
        columns = {label: {n['note_index'] for n in result['notes'] if n['aligned'] and n['signals'][label]['eligible']}
                   for label in result['signals']}
        results[song] = {**result, 'wave_frames': config['render'], 'phrases': len(phrases),
                         'recording_vibrato_observable': bool(columns['recording']),
                         'common_eligible_notes': sorted(set.intersection(*columns.values())),
                         'all_annotated_long_notes': rank['annotation_long_notes'],
                         'verified_f0_report_differences': f0_diffs, 'block_hashes': [primary_hash, alternate_hash]}
    missing_splits = sorted({'calibration', 'held_out'} - {s[0] for s in sources})
    return {'checks': checks, 'songs': results, 'unavailable_annotation_splits': missing_splits}


def load_sources(case, annotation_run, recording_run, inputs):
    root = WORKSPACE / 'runs' / annotation_run
    selection_path, selection_manifest, selected_path = verified_selection(root, case)
    selected = read(selected_path)
    audio = WORKSPACE / 'runs' / recording_run
    manifest = audio / 'manifest.json'
    meta = read(manifest)
    if (meta['status'] != 'pass' or meta['case_id'] != case['id'] or meta['stage'] != 'recordings'
            or meta['selection_run'] != annotation_run or meta['case_revision'] != case['revision']):
        raise ValueError('この選定で取得した録音の実行を指定してください')
    index = verified_file(audio, meta, 'summary.json')
    inputs.extend((selection_path, selected_path, manifest, index))
    waves = read(index)['waves']
    by_song = {row['id']: row for row in selected['ranking']}
    result = []
    for split, expected in selected['selected'].items():
        if expected is None:
            continue
        wav = waves[split]['wav']
        if waves[split]['song'] != expected or by_song[expected]['split'] != split:
            raise ValueError('区分と取得した録音が選定と一致しません')
        annotation = verified_file(root, selection_manifest, f"artifacts/{selected['annotations'][expected]['path']}")
        recording = verified_file(audio, meta, f"artifacts/{wav['path']}")
        if sha256(annotation) != selected['annotations'][expected]['sha256'] or sha256(recording) != wav['sha256']:
            raise ValueError('注釈・録音のハッシュが選定資料と一致しません')
        inputs.extend((annotation, recording))
        result.append((split, by_song[expected], annotation, recording, wav))
    if not result:
        raise ValueError('分析対象の録音がありません')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--selection-run', required=True)
    parser.add_argument('--recording-run', required=True)
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('作業用ディスクを指定してください')
    case = read(CASE)
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if revision != case['upstream_revision'] or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('差分のない固定上流版を用意してください')
    scores, f0, aper = (CASE.parent / case[k] for k in ('dataset_case', 'pitch_case', 'periodicity_case'))
    pitch = read(f0)['measurement']
    periodicity = read(aper)['measurement']
    if (periodicity['hop_seconds'] != pitch['hop_seconds']
            or case['analysis']['minimum_voiced_run_frames']*pitch['hop_seconds'] != periodicity['minimum_run_seconds']):
        parser.error('登録した格子と既存のビブラート測定条件が一致しません')
    base = WORKSPACE / 'runs' / case['candidate_settings_run']
    manifest = base / 'manifest.json'
    metadata = read(manifest)
    if metadata['status'] != 'pass' or metadata['upstream_revision'] != revision:
        parser.error('固定上流で照合した発声設定を用意してください')
    original = verified_file(base, metadata, 'artifacts/candidate-short-128.json')
    inputs = [CASE, scores, f0, aper, manifest, original, Path(__file__).resolve(),
              *(WORKSPACE / 'tools' / name for name in ('select_csd_long_notes.py', 'measure_csd_song_planning.py',
                   'measure_csd_song_f0.py', 'measure_csd_vibrato_aperiodicity.py', 'measure_csd_envelope_timing.py',
                   'measure_csd_continuous_song.py', 'measure_vowel_voice.py', 'measure_speech_timing.py',
                   'measure_uniform_tube.py', 'upstream_baseline.py')),
              UPSTREAM / 'crates/chimera-cli/src/compare.rs', UPSTREAM / 'crates/chimera-cli/src/compare/score.rs',
              *candidate_sources()]
    sources = load_sources(case, args.selection_run, args.recording_run, inputs)
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision, 'stage': 'comparison',
               'selection_run': args.selection_run, 'recording_run': args.recording_run,
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]]}
    return record_measurement(args.run_id, CASE, inputs, details,
        lambda out, exe: evaluate(case, read(scores), pitch, periodicity, sources, read(original), out, exe),
        command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
