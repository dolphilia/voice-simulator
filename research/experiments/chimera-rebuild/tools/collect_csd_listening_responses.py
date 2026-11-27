"""CSD試聴の回答CSVを、試聴した素材の音源対応表で集計する。"""

import argparse
import csv
from hashlib import sha256 as hash_bytes
import io
from pathlib import Path
import re
import sys

from measure_csd_envelope_timing import verified_file
from measure_csd_f0_search_sensitivity import add_file, run_inputs
from measure_csd_song_f0 import LABELS
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from prepare_csd_listening import packet_identity
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-listening-responses.json'
ROOT = WORKSPACE.parents[2]
BROWSER_TEST = ROOT / 'web/prototypes/chimera-research/tools/verify-csd-listening.mjs'
LETTERS = ('A', 'B', 'C')
SPECIAL_ANSWERS = {'': 'unanswered', '判定不能': 'unable_to_judge', '差なし': 'no_difference'}
ID_PATTERN = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_-]*')


def listening_inputs(case, run_id):
    inputs = []
    run = run_inputs(run_id, case['upstream_revision'], inputs)
    root, manifest = run
    case_relative = (CASE.parent / case['listening_case']).relative_to(ROOT)
    snapshot = root / manifest['source_snapshot'] / case_relative
    hashes = [row['sha256'] for row in manifest['inputs'] if row['path'] == str(case_relative)]
    if manifest['run_id'] != run_id or hashes != [sha256(snapshot)]:
        raise ValueError('試聴素材の実行IDまたは生成時のケースを照合できません')
    listening = read(snapshot)
    if manifest['case_id'] != listening['id'] or manifest['case_revision'] != listening['revision']:
        raise ValueError('試聴素材のケースと版が一致しません')
    inputs.append(snapshot)
    key_path = add_file(run, 'artifacts/listening-key.json', inputs)
    key = read(key_path)
    trials = {f'{i:02d}': item for i, item in enumerate(listening['trials'], 1)}
    if key.keys() != trials.keys():
        raise ValueError('音源対応表の区間番号がケースと一致しません')
    for trial, source in key.items():
        labels = source['labels']
        if (any(source.get(k) != v for k, v in trials[trial].items()) or
                set(labels) != set(LETTERS) or set(labels.values()) != set(LABELS)):
            raise ValueError(f'音源対応表の区間または音源が一致しません ({trial})')
    packet_id = None
    if listening['listening']['observations_schema'][0] == 'packet_id':
        clips = [add_file(run, f'artifacts/listening/{trial}-{letter}.wav', inputs)
                 for trial in key for letter in LETTERS]
        packet = read(add_file(run, 'artifacts/listening-packet.json', inputs))
        if packet != packet_identity(listening, key_path, clips):
            raise ValueError('資料IDを音源対応と試聴WAVから再現できません')
        packet_id = packet['packet_id']
    return listening, key, run, inputs, packet_id


def read_response(blob, response_id, key, columns, scores, packet_id=None):
    rows = {}
    try:
        stream = io.StringIO(blob.decode('utf-8-sig'), newline='')
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != columns:
            raise ValueError(f'{response_id} の列名または列順が試聴ケースと一致しません')
        for row in reader:
            if not row:
                continue
            if len(row) != len(columns):
                raise ValueError(f'{response_id} のCSV {reader.line_num}行目の列数が一致しません')
            if packet_id is not None:
                received_id, *row = row
                if received_id != packet_id:
                    raise ValueError(f'{response_id} のCSV {reader.line_num}行目の資料IDが一致しません')
            raw_trial, *fields = row
            raw_trial = raw_trial.strip()
            trial = raw_trial.lstrip('0').zfill(2) if raw_trial.isascii() and raw_trial.isdecimal() else raw_trial
            if trial not in key:
                raise ValueError(f'{response_id} のCSV {reader.line_num}行目に未登録の区間番号があります')
            if trial in rows:
                raise ValueError(f'{response_id} で区間 {trial} の回答が重複しています')
            pitch = [v.strip() for v in fields[:3]]
            preference, comment = fields[3].strip(), fields[4]
            if any(v not in ('', *scores) for v in pitch):
                raise ValueError(f'{response_id} の区間 {trial} に未定義の揺れの評点があります')
            if preference not in (*LETTERS, *SPECIAL_ANSWERS):
                raise ValueError(f'{response_id} の区間 {trial} に未定義の自然さの選択があります')
            rows[trial] = (pitch, preference, comment)
    except (UnicodeError, csv.Error) as err:
        raise ValueError(f'{response_id} のUTF-8 CSVを読み取れません ({err})') from err
    return rows


def normalize_response(rows, response_id, key):
    normalized = []
    for trial, item in key.items():
        pitch, preference, comment = rows.get(trial, ([''] * 3, '', ''))
        labels = item['labels']
        normalized.append({
            'response_id': response_id, 'trial': trial, 'split': item['split'],
            'song': item['song'], 'note_index': item['note_index'], 'category': item['category'],
            'row_present': trial in rows,
            'periodic_pitch': {labels[letter]: SPECIAL_ANSWERS.get(value, value)
                               for letter, value in zip(LETTERS, pitch, strict=True)},
            'naturalness_preference': labels[preference] if preference in LETTERS else SPECIAL_ANSWERS[preference],
            'observations': comment,
        })
    return normalized


def observation_signature(rows):
    return tuple(sorted((trial, tuple(pitch), preference, note.replace('\r\n', '\n').replace('\r', '\n').strip())
                        for trial, (pitch, preference, note) in rows.items()
                        if any(pitch) or preference or note.strip()))


def human_intake_error(signature, fixtures):
    if not signature:
        return '人の回答には記入済みの観測が必要です'
    if signature in fixtures:
        return '既知の試験用回答を人の回答として登録できません'
    return None


def known_observations(case, inputs):
    run_id = case['human_intake']['fixture_verification_run']
    run = run_inputs(run_id, case['upstream_revision'], inputs)
    manifest = run[1]
    reference = read(add_file(run, 'summary.json', inputs))
    if manifest['run_id'] != run_id or manifest['case_id'] != case['id'] or manifest['mode'] != 'verify':
        raise ValueError('既知の試験用回答の実行を照合できません')
    source, key, _, dependencies, packet_id = listening_inputs(case, manifest['listening_run'])
    inputs.extend(dependencies)
    if reference['data_kind'] != 'synthetic' or reference['packet_id'] != packet_id:
        raise ValueError('試験用回答の区分または試聴資料が一致しません')
    signatures = set()
    for kind in ('browser', 'manual'):
        path = add_file(run, f'artifacts/{kind}-fixture.csv', inputs)
        rows = read_response(path.read_bytes(), kind, key, source['listening']['observations_schema'],
                             source['listening']['scores'], packet_id)
        signatures.add(observation_signature(rows))
    if any(not signature for signature in signatures) or len(signatures) != reference['fixture_responses']:
        raise ValueError('既知の試験用回答の件数または記入が一致しません')
    return signatures


def summarize(rows, key, scores):
    pitch_bins = [SPECIAL_ANSWERS.get(value, value) for value in scores] + ['unanswered']
    preference_bins = (*LABELS, 'no_difference', 'unable_to_judge', 'unanswered')
    splits = {item['split']: {
        'expected_rows': 0, 'received_rows': 0, 'answered_rows': 0,
        'periodic_pitch': {source: dict.fromkeys(pitch_bins, 0) for source in LABELS},
        'naturalness_preference': dict.fromkeys(preference_bins, 0),
    } for item in key.values()}
    for row in rows:
        group = splits[row['split']]
        group['expected_rows'] += 1
        group['received_rows'] += row['row_present']
        preference = row['naturalness_preference']
        group['answered_rows'] += (preference != 'unanswered' or bool(row['observations'].strip())
                                   or any(v != 'unanswered' for v in row['periodic_pitch'].values()))
        group['naturalness_preference'][preference] += 1
        for source, score in row['periodic_pitch'].items():
            group['periodic_pitch'][source][score] += 1
    return splits


def validation(case, key, listening, page, template, out, execute, packet_id):
    columns = listening['observations_schema']
    scores = listening['scores']
    browser_csv = out / 'browser-fixture.csv'
    execute(['node', str(BROWSER_TEST), str(page), str(browser_csv)], stdout=out / 'browser-verification.json')
    manual_csv = out / 'manual-fixture.csv'
    with manual_csv.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        prefix = [packet_id] if packet_id is not None else []
        writer.writerows(prefix + row for row in case['manual_fixture_rows'])
    browser_raw = read_response(browser_csv.read_bytes(), 'browser', key, columns, scores, packet_id)
    manual_raw = read_response(manual_csv.read_bytes(), 'manual', key, columns, scores, packet_id)
    browser = normalize_response(browser_raw, 'browser', key)
    manual = normalize_response(manual_raw, 'manual', key)
    rows = browser + manual
    by_split = summarize(rows, key, scores)
    observed = {
        split: {'rows': [group[k] for k in ('expected_rows', 'received_rows', 'answered_rows')],
                'pitch': {source: list(group['periodic_pitch'][source].values()) for source in LABELS},
                'naturalness': list(group['naturalness_preference'].values())}
        for split, group in by_split.items()
    }
    blank_raw = read_response(template.read_bytes(), 'blank', key, columns, scores, packet_id)
    blank = normalize_response(blank_raw, 'blank', key)
    blank_totals = summarize(blank, key, scores)
    signatures = {observation_signature(raw) for raw in (browser_raw, manual_raw)}
    checks = {'independent_expected_totals': observed == case['expected_fixture'],
              'blank_template_adds_no_score_or_vote': all(
                  group['received_rows'] == group['expected_rows'] and group['answered_rows'] == 0 and
                  group['naturalness_preference']['unanswered'] == group['expected_rows'] and
                  all(score['unanswered'] == group['expected_rows'] for score in group['periodic_pitch'].values())
                  for group in blank_totals.values()),
              'browser_roundtrip': browser[0]['observations'] == '音の入り, "比較"\n余韻' and
              browser[0]['periodic_pitch'] == {'upstream': '2', 'recording': 'unable_to_judge', 'candidate': 'unanswered'},
              'missing_rows_and_numeric_ids': [row['trial'] for row in manual if row['row_present']] == ['02', '04', '05'],
              'browser_checks': all(read(out / 'browser-verification.json')['checks'].values()),
              'human_intake_excludes_empty_and_known_fixtures':
                  human_intake_error(observation_signature(blank_raw), signatures) is not None
                  and all(human_intake_error(signature, signatures) is not None for signature in signatures),
              'human_intake_retains_zero_and_observation_only':
                  all(human_intake_error(observation_signature({'06': row}), signatures) is None for row in (
                      (['0', '', ''], '', ''), (['', '', ''], '', '余韻に差がある')))}
    legacy_malformed = {
        'duplicate_trial': ('01,,,,,\n1,,,,,\n', '重複'),
        'unknown_trial': ('07,,,,,\n', '未登録'),
        'invalid_pitch': ('01,4,,,,\n', '未定義の揺れ'),
        'invalid_preference': ('01,,,,D,\n', '未定義の自然さ'),
        'uneven_columns': ('01,,,A,\n', '列数'),
        'invalid_quotes': ('01,,,,,"unfinished', 'UTF-8 CSV'),
    }
    header = ','.join(columns) + '\n'
    prefix = f'{packet_id},' if packet_id is not None else ''
    malformed = {name: (header + ''.join(prefix + line for line in data.splitlines(keepends=True)), expected)
                 for name, (data, expected) in legacy_malformed.items()}
    if packet_id is not None:
        other = '0' * len(packet_id)
        malformed.update({
            'different_packet_id': (header + f'{other},01,,,,,\n', '資料ID'),
            'mixed_packet_ids': (header + f'{packet_id},01,,,,,\n{other},02,,,,,\n', '資料ID'),
            'missing_packet_column': (','.join(columns[1:]) + '\n01,,,,,\n', '列名'),
        })
    rejected = {}
    for name, (data, expected) in malformed.items():
        try:
            read_response(data.encode(), name, key, columns, scores, packet_id)
        except ValueError as err:
            rejected[name] = str(err)
        checks[f'reject_{name}'] = expected in rejected.get(name, '')
    write(out / 'fixture-responses-by-source.json', rows)
    return {'checks': checks, 'data_kind': 'synthetic', 'fixture_responses': 2, 'packet_id': packet_id,
            'by_split': by_split, 'rejected_fixtures': rejected}


def collect(responses, listening, key, out, packet_id, data_kind, fixtures):
    rows = []
    for response_id, blob in responses.items():
        raw = read_response(blob, response_id, key, listening['observations_schema'], listening['scores'], packet_id)
        if data_kind == 'human':
            reason = human_intake_error(observation_signature(raw), fixtures)
            if reason:
                raise ValueError(f'{response_id}: {reason}')
        rows.extend(normalize_response(raw, response_id, key))
    # 入力全体の検証後に、解析に使ったものと同じバイト列を保存する。
    folder = out / 'responses'
    folder.mkdir()
    for response_id, blob in responses.items():
        (folder / f'{response_id}.csv').write_bytes(blob)
    write(out / 'responses-by-source.json', rows)
    return {'checks': {'response_files_validated': bool(responses)},
            'data_kind': data_kind, 'response_ids': list(responses), 'packet_id': packet_id,
            'by_split': summarize(rows, key, listening['scores'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id', help='新規に保存する集計の実行ID')
    parser.add_argument('--package-run', help='回答者が試聴した素材の実行ID')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--response', nargs=2, action='append', metavar=('回答ID', 'CSV'),
                      help='匿名の回答IDとCSVを指定。複数指定可')
    mode.add_argument('--verify', action='store_true', help='既知の試験入力とブラウザで動作を照合')
    parser.add_argument('--kind', choices=('human', 'synthetic'), help='回答を人手または試験入力として区分')
    args = parser.parse_args()
    case = read(CASE)
    if args.verify and args.kind:
        parser.error('--kind は回答CSVを指定するときに使用してください')
    if args.response and not args.package_run:
        parser.error('回答のCSVには、試聴した素材を --package-run で指定してください')
    package_id = args.package_run or case['listening_run']
    ids = [key for key, _ in args.response or []]
    if not all(ID_PATTERN.fullmatch(value) for value in (package_id, *ids)) or len(ids) != len(set(ids)):
        parser.error('実行IDと回答IDは英数字で始まる短い識別子を使い、回答IDは重複させないでください')
    try:
        paths = {ident: Path(path).resolve(strict=True) for ident, path in args.response or []}
        if len(set(paths.values())) != len(paths) or any(not path.is_file() for path in paths.values()):
            raise ValueError('回答CSVは異なる読み取り可能なファイルを指定してください')
        responses = {ident: path.read_bytes() for ident, path in paths.items()}
        listening, key, run, inputs, packet_id = listening_inputs(case, package_id)
        fixtures = known_observations(case, inputs) if args.kind == 'human' else ()
        if args.verify:
            html = verified_file(*run, 'artifacts/listening/index.html')
            template = verified_file(*run, 'artifacts/listening/observations.csv')
            inputs.extend((html, template, BROWSER_TEST))
            if packet_id is None:
                inputs.extend(verified_file(*run, f'artifacts/listening/{trial}-{letter}.wav')
                              for trial in key for letter in LETTERS)
    except (OSError, KeyError, ValueError) as err:
        parser.error(str(err))
    inputs.extend((CASE, Path(__file__).resolve(), WORKSPACE / 'tools/prepare_csd_listening.py',
                   WORKSPACE / 'tools/measure_csd_envelope_timing.py',
                   WORKSPACE / 'tools/measure_csd_f0_search_sensitivity.py', WORKSPACE / 'tools/measure_csd_song_f0.py'))
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'listening_run': package_id, 'packet_id': packet_id, 'mode': 'verify' if args.verify else 'collect',
               'analysis_directory': str(Path.cwd()), 'analysis_command': [sys.executable, *sys.argv]}
    data_kind = 'synthetic' if args.verify else args.kind or 'response_csv'
    details['data_kind'] = data_kind
    if responses:
        details['response_files'] = {ident: {'bytes': len(blob), 'sha256': hash_bytes(blob).hexdigest()}
                                     for ident, blob in responses.items()}

    def measure(out, execute):
        if args.verify:
            return validation(case, key, listening['listening'], html, template, out, execute, packet_id)
        return collect(responses, listening['listening'], key, out, packet_id, data_kind, fixtures)

    return record_measurement(args.run_id, CASE, inputs, details, measure, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
