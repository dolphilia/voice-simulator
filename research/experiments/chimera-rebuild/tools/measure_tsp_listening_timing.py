"""TSPの試聴回答を同じ音源の区間長と低エネルギー時間に対応付ける。"""

import argparse
from collections import Counter
import csv
from itertools import groupby
import math
from pathlib import Path
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read, write
from measure_tsp_listening import IDENTIFIER, LETTERS, ROOT, SOURCES, hydrate_run, parse, snapshot_case
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE = WORKSPACE / 'cases/tsp-listening-timing.json'
SIGNALS = ('recording', 'upstream', 'candidate')


def timing(values, width, hop, threshold_db, minimum_quiet):
    floor = max(values) * 10**(threshold_db / 20)
    loud, quiet = [], []
    for below, group in groupby(enumerate(values), key=lambda pair: pair[1] < floor):
        indices = [index for index, _ in group]
        if len(indices) >= (minimum_quiet if below else 3):
            (quiet if below else loud).append((indices[0] * hop, indices[-1] * hop))
    if not loud:
        raise ValueError('区間を決める連続した有効窓がありません')
    start, stop = loud[0][0], loud[-1][1] + width
    # 窓中心から次のホップまでを数え、重なりを二重に数えない。
    inside = [[a + width // 2, b + width // 2 + hop] for a, b in quiet if start <= a and b + width <= stop]
    quiet_frames = sum(b - a for a, b in inside)
    return {'span': [start, stop], 'quiet_intervals': inside, 'span_frames': stop - start,
            'quiet_frames': quiet_frames, 'span_minus_quiet_frames': stop - start - quiet_frames}


def read_windows(path, recorded, width, hop):
    windows = {source: [] for source in SIGNALS}
    with path.open(newline='') as stream:
        rows = csv.DictReader(stream)
        if rows.fieldnames != ['source', 'start_frame', 'rms']:
            raise ValueError(f'窓RMSの列が一致しません ({path})')
        for row in rows:
            values = windows[row['source']]
            value = float(row['rms'])
            if int(row['start_frame']) != len(values) * hop or not math.isfinite(value) or value < 0:
                raise ValueError(f'開始フレームまたはRMSが不正です ({path})')
            values.append(value)
    for name, values in windows.items():
        original = recorded['windows'][name]
        if len(values) != (original['pcm_frames'] - width) // hop + 1 or max(values) != original['maximum_window_rms']:
            raise ValueError(f'窓数またはRMSの最大値が保存値と一致しません ({path}, {name})')
    return windows


def direction(candidate_minus_recording, tolerance):
    if abs(candidate_minus_recording) <= tolerance:
        return 'indeterminate'
    return 'candidate' if candidate_minus_recording > 0 else 'recording'


def directions(measures, tolerance):
    candidate, recording = (measures[name] for name in SOURCES)
    return {'faster_by_span': direction(recording['span_frames'] - candidate['span_frames'], tolerance),
            'faster_by_span_minus_quiet': direction(
                recording['span_minus_quiet_frames'] - candidate['span_minus_quiet_frames'], tolerance),
            'longer_low_energy': direction(candidate['quiet_frames'] - recording['quiet_frames'], tolerance)}


def compare_judgment(choice, estimate):
    labels = {'missing_row': 'missing_row', 'unanswered': 'unanswered',
              'same': 'listener_same', 'unsure': 'listener_unsure'}
    if choice in labels:
        return labels[choice]
    if estimate == 'indeterminate':
        return 'measurement_indeterminate'
    return 'agree' if choice == estimate else 'disagree'


def compare_responses(pairs, responses, primary, sensitivity):
    results = {}
    for rater, rows in responses.items():
        comparisons = {}
        for pair, entry in pairs.items():
            answer = rows.get(pair, {'tempo': 'missing_row', 'pauses': 'missing_row', 'observations': ''})
            predictions = entry['thresholds'][primary]['directions']
            comparisons[pair] = {
                'split': entry['split'], 'answer': answer,
                'tempo_vs_span': compare_judgment(answer['tempo'], predictions['faster_by_span']),
                'tempo_vs_span_minus_quiet': compare_judgment(answer['tempo'], predictions['faster_by_span_minus_quiet']),
                'pauses_vs_low_energy': compare_judgment(answer['pauses'], predictions['longer_low_energy']),
                'sensitivity_directions': entry['thresholds'][sensitivity]['directions'],
            }
        results[rater] = comparisons
    return results


def measure(case, source_data, packet, paths, response, out):
    rate, width, hop = (source_data[key] for key in ('sample_rate_hz', 'window_frames', 'hop_frames'))
    tolerance = hop * case['direction_tolerance_hops']
    primary, sensitivity = map(str, case['thresholds_db'])
    positive = case['control']
    for threshold in case['thresholds_db']:
        observed = timing(positive['rms'], positive['window_frames'], positive['hop_frames'],
                          threshold, case['minimum_quiet_windows'])
        if observed['span'] != positive['span'] or observed['quiet_intervals'] != positive['quiet_intervals'][str(threshold)]:
            raise ValueError('既知の窓系列で発話区間または低エネルギー区間が一致しません')
    result = {}
    for pair, key in packet['pairs'].items():
        recorded = source_data['splits'][key['split']][key['recording_id']]
        if recorded['listening_pair'] != pair:
            raise ValueError(f'元の計測と試聴対が一致しません ({pair})')
        windows = read_windows(paths[pair]['windows'], recorded, width, hop)
        result[pair] = {'split': key['split'], 'recording_id': key['recording_id'], 'thresholds': {}}
        for threshold in case['thresholds_db']:
            measures = {source: timing(values, width, hop, threshold, case['minimum_quiet_windows'])
                        for source, values in windows.items()}
            for source, entry in measures.items():
                expected = recorded['windows'][source]['thresholds'][str(threshold)]
                if entry['span'] != [expected['start_frame'], expected['end_frame_exclusive']]:
                    raise ValueError(f'発話区間が元の保存値と一致しません ({pair}, {source}, {threshold} dB)')
            result[pair]['thresholds'][str(threshold)] = {'signals': measures, 'directions': directions(measures, tolerance)}
        for letter in LETTERS:
            clip = paths[pair][letter]
            fs, samples = wavfile.read(clip)
            saved = key['clips'][letter]
            expected = result[pair]['thresholds'][primary]['signals'][key[letter]]['span_frames']
            if (fs != rate or samples.shape != (expected,) or samples.dtype != np.float32
                    or saved['frames'] != expected or saved['sha256'] != sha256(clip)):
                raise ValueError(f'試聴用WAVと主しきい値の区間が一致しません ({pair}-{letter})')
    write(out / 'pair-measurements.json', result)
    primary_change, sensitivity_change = [], []
    for pair, row in result.items():
        first = row['thresholds'][primary]['directions']
        second = row['thresholds'][sensitivity]['directions']
        if first['faster_by_span'] != first['faster_by_span_minus_quiet']:
            primary_change.append(pair)
        if first != second:
            sensitivity_change.append(pair)
    report = {'checks': {'known_window_control': True, 'archived_intervals': True, 'listening_wav_frames': True},
              'pairs_by_split': dict(Counter(row['split'] for row in result.values())),
              'interval_count': len(result) * len(case['thresholds_db']) * len(SIGNALS),
              'sample_rate_hz': rate, 'window_frames': width, 'hop_frames': hop, 'direction_tolerance_frames': tolerance,
              'tempo_direction_changed_by_quiet_exclusion': primary_change,
              'direction_differs_between_thresholds': sensitivity_change, 'response_data_kind': None}
    if response is not None:
        run_id, data = response
        compared = compare_responses(result, data['responses'], primary, sensitivity)
        write(out / 'response-comparisons.json', {'data_kind': data['data_kind'], 'responses': compared})
        report.update(response_data_kind=data['data_kind'], response_count=len(compared))
        if run_id == case['fixture_run']:
            report['checks']['registered_trial_judgments'] = data['data_kind'] == 'synthetic' and all(
                compared[name][pair]['tempo_vs_span'] == expected
                for name, pair, expected in case['expected_fixture_tempo'])
    return report


def load_responses(run, packet, inputs):
    root, manifest = run
    summary = verified_file(*run, 'summary.json')
    result = verified_file(*run, 'artifacts/responses-by-source.json')
    report, data = read(summary), read(result)
    kind = manifest.get('data_kind')
    if (manifest.get('action') != 'collect' or kind not in ('synthetic', 'human')
            or not kind == data['data_kind'] == report['data_kind']
            or not packet['packet_id'] == data['packet_id'] == report['packet_id']
            or set(report['response_ids']) != data['responses'].keys()):
        raise ValueError('回答の出所または資料IDを照合できません')
    inputs.extend((root / 'manifest.json', summary, result))
    for rater, expected in data['responses'].items():
        if not IDENTIFIER.fullmatch(rater):
            raise ValueError('回答IDが不正です')
        path = verified_file(*run, f'artifacts/responses/{rater}.csv')
        inputs.append(path)
        if parse(path.read_bytes(), packet) != expected:
            raise ValueError(f'元のCSVと音源を対応付けた回答が一致しません ({rater})')
    return root.name, data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--responses', metavar='RUN', help='照合する試聴回答の取込実行ID')
    args = parser.parse_args()
    if args.responses and not IDENTIFIER.fullmatch(args.responses):
        parser.error('回答実行IDが不正です')
    case = read(CASE)
    revision = case['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != revision or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    prepared = hydrate_run(case['packet_run'], case['listening_case'], revision)
    if prepared[1].get('action') != 'prepare':
        parser.error('試聴資料の生成実行が必要です')
    listening_path = snapshot_case(prepared, case['listening_case'])
    listening = read(listening_path)
    source = hydrate_run(listening['source_run'], listening['source_case'], revision)
    scope = snapshot_case(source, listening['source_case'])
    base = snapshot_case(source, Path(read(scope)['base_case']).stem)
    measurement = read(base)['measurement']
    if case['thresholds_db'] != [measurement['threshold_db_relative_to_maximum_window_rms'], measurement['sensitivity_threshold_db']]:
        parser.error('元の発話区間のしきい値を指定してください')
    source_summary = verified_file(*source, 'summary.json')
    reference = verified_file(*prepared, 'artifacts/reference.json')
    packet = read(reference)
    inputs = [CASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_tsp_listening.py',
              WORKSPACE / 'tools/measure_uniform_tube.py', WORKSPACE / 'tools/upstream_baseline.py',
              WORKSPACE / 'tools/measure_csd_envelope_timing.py', WORKSPACE / 'tools/measure_speech_timing.py',
              prepared[0] / 'manifest.json', listening_path, reference, source[0] / 'manifest.json',
              scope, base, source_summary]
    paths = {}
    for pair, key in packet['pairs'].items():
        paths[pair] = {letter: verified_file(*prepared, f'artifacts/listening/{pair}-{letter}.wav') for letter in LETTERS}
        paths[pair]['windows'] = verified_file(*source, f"artifacts/{key['recording_id']}/windows.csv")
        inputs.extend(paths[pair].values())
    data = load_responses(hydrate_run(args.responses, case['listening_case'], revision), packet, inputs) if args.responses else None
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'invoked_from': str(Path.cwd()), 'packet_run': case['packet_run'], 'response_run': args.responses,
                'cli_arguments': sys.argv[1:]}

    def run(out, execute):
        execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
                cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
        return measure(case, read(source_summary), packet, paths, data, out)

    return record_measurement(args.run_id, CASE, inputs, metadata, run, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
