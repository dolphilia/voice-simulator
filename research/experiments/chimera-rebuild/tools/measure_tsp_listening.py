"""既存のTSP試聴対を再生できる資料にし、回答を照合して集計する。"""

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy.io import wavfile

from measure_csd_envelope_timing import verified_file
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
CASE = WORKSPACE / 'cases/tsp-listening-responses.json'
PAGE = WORKSPACE / 'tools/tsp_listening.html'
BROWSER = ROOT / 'web/prototypes/chimera-research/tools/verify-tsp-listening.mjs'
IDENTIFIER = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]*')
COLUMNS = ('packet_id', 'pair', 'tempo', 'pauses', 'observations')
LETTERS = ('A', 'B')
SOURCES = ('candidate', 'recording')
CHOICES = ('', *LETTERS, 'same', 'unsure')
BINS = (*SOURCES, 'same', 'unsure', 'unanswered')


def hydrate_run(run_id, case_id, revision):
    root = WORKSPACE / 'runs' / run_id
    path = root / 'manifest.json'
    manifest = read(path)
    if (manifest['run_id'] != run_id or manifest['case_id'] != case_id
            or manifest['upstream_revision'] != revision or manifest['status'] != 'pass'):
        raise ValueError(f'{run_id} は固定上流版で合格した指定ケースの実行ではありません')
    return root, manifest


def snapshot_case(run, case_id):
    root, manifest = run
    relative = (CASE.parent / f'{case_id}.json').relative_to(ROOT)
    entry, = (item for item in manifest['inputs'] if item['path'] == str(relative))
    path = root / manifest['source_snapshot'] / relative
    if sha256(path) != entry['sha256']:
        raise ValueError(f'{case_id} の保存済みケースとハッシュが一致しません')
    return path


def load_trials(case):
    run = hydrate_run(case['source_run'], case['source_case'], case['upstream_revision'])
    key_path = verified_file(*run, 'artifacts/listening-key.json')
    summary_path = verified_file(*run, 'summary.json')
    licence = verified_file(*run, 'artifacts/listening/TSP-licence.txt')
    scope = snapshot_case(run, case['source_case'])
    original = read(scope)
    base = snapshot_case(run, Path(original['base_case']).stem)
    primary = str(read(base)['measurement']['threshold_db_relative_to_maximum_window_rms'])
    inputs = [run[0] / 'manifest.json', key_path, summary_path, licence, scope, base]
    key, summary = read(key_path), read(summary_path)
    expected = [(split, uid) for split in case['splits'] for uid in original[f'{split}_ids']]
    if (len(key) != len(expected) or Counter(split for split, _ in expected) != case['splits']
            or not all(summary['checks'].values()) or summary['sample_rate_hz'] != case['sample_rate_hz']):
        raise ValueError('試聴対の区分・件数・レートが登録条件と一致しません')
    pairs = {}
    clips = {}
    for ordinal, (split, uid) in enumerate(expected, start=1):
        pair = f'{ordinal:02}'
        info = key[pair]
        measured = summary['splits'][split][uid]
        if (info['split'] != split or info['recording_id'] != uid or measured['listening_pair'] != pair
                or {info[label] for label in LETTERS} != set(SOURCES)):
            raise ValueError(f'試聴対と元の区分または音源が一致しません ({pair})')
        waves = {}
        for label in LETTERS:
            source = info[label]
            interval = measured['windows'][source]['thresholds'][primary]
            filename = f'{pair}-{label}.wav'
            path = verified_file(*run, f'artifacts/listening/{filename}')
            rate, pcm = wavfile.read(path)
            if (rate != case['sample_rate_hz'] or pcm.dtype != np.float32
                    or pcm.shape != (interval['end_frame_exclusive'] - interval['start_frame'],)
                    or not pcm.size or not np.isfinite(pcm).all()):
                raise ValueError(f'試聴音源の形式または発話区間が一致しません ({filename})')
            waves[label] = {'sha256': sha256(path), 'frames': len(pcm)}
            inputs.append(path)
            clips[filename] = path
        pairs[pair] = {**info, 'clips': waves}
    return pairs, clips, licence, inputs


def encode(rows):
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def parse(blob, packet):
    result = {}
    with io.StringIO(blob.decode('utf-8-sig'), newline='') as stream:
        reader = csv.reader(stream, strict=True)
        if next(reader, None) != list(COLUMNS):
            raise ValueError('CSVの列名が試聴資料と一致しません')
        for row in reader:
            if not row:
                continue
            if len(row) != len(COLUMNS):
                raise ValueError(f'CSVの列数が一致しません ({reader.line_num}行目)')
            packet_id, pair, tempo, pauses, note = row
            if packet_id != packet['packet_id'] or pair not in packet['pairs']:
                raise ValueError(f'資料IDまたは試聴対が一致しません ({reader.line_num}行目)')
            if pair in result:
                raise ValueError(f'同じ試聴対の回答が重複しています ({pair})')
            if tempo not in CHOICES or pauses not in CHOICES:
                raise ValueError(f'試聴の選択肢が登録値と一致しません ({pair})')
            aliases = packet['pairs'][pair]
            result[pair] = {'tempo': aliases[tempo] if tempo in LETTERS else tempo or 'unanswered',
                            'pauses': aliases[pauses] if pauses in LETTERS else pauses or 'unanswered',
                            'observations': note}
    return result


def summarize(packet, responses):
    totals = {entry['split']: {'rows': [0, 0, 0], 'tempo': dict.fromkeys(BINS, 0), 'pauses': dict.fromkeys(BINS, 0)}
              for entry in packet['pairs'].values()}
    for rows in responses.values():
        for pair, entry in packet['pairs'].items():
            group = totals[entry['split']]
            row = rows.get(pair)
            tempo = row['tempo'] if row else 'unanswered'
            pauses = row['pauses'] if row else 'unanswered'
            group['rows'][0] += 1
            group['rows'][1] += row is not None
            group['rows'][2] += tempo != 'unanswered' or pauses != 'unanswered' or bool(row and row['observations'].strip())
            group['tempo'][tempo] += 1
            group['pauses'][pauses] += 1
    return totals


def panel(pair):
    choices = ('未回答', 'A', 'B', '同程度', '判定不能')
    options = ''.join(f'<option value="{value}">{label}</option>' for value, label in zip(CHOICES, choices, strict=True))
    return f'''<section data-pair="{pair}" aria-labelledby="pair-{pair}">
  <h2 id="pair-{pair}">試聴 {pair}</h2>
  <div class="row">
    <div class="field"><span>A</span><audio aria-label="試聴 {pair} A" controls preload="none" src="{pair}-A.wav"></audio></div>
    <div class="field"><span>B</span><audio aria-label="試聴 {pair} B" controls preload="none" src="{pair}-B.wav"></audio></div>
    <label class="field">発話が速く聞こえた方<select class="tempo">{options}</select></label>
    <label class="field">文中の間が長く聞こえた方<select class="pauses">{options}</select></label>
  </div>
  <label>気付いたこと<textarea></textarea></label>
</section>'''


def validate_packet(case, packet, page, template, out, execute):
    browser = out / 'browser-fixture.csv'
    execute(['node', str(BROWSER), str(page), str(browser)], stdout=out / 'browser-verification.json')
    observed = read(out / 'browser-verification.json')
    key = packet['packet_id']
    manual = out / 'manual-fixture.csv'
    manual.write_bytes(encode((key, *row) for row in case['manual_fixture']))
    responses = {name: parse(path.read_bytes(), packet) for name, path in [('browser', browser), ('manual', manual)]}
    summary = summarize(packet, responses)
    blank = summarize(packet, {'blank': parse(template.read_bytes(), packet)})
    lengths = {f'{pair}-{label}.wav': clip['frames'] / case['sample_rate_hz']
               for pair, item in packet['pairs'].items() for label, clip in item['clips'].items()}
    row = (key, '01', 'A', '', '')
    invalid = ([row, row], [('other', *row[1:])], [(key, '01', 'C', '', '')])
    rejected = 0
    for rows in invalid:
        try:
            parse(encode(rows), packet)
        except ValueError:
            rejected += 1
    checks = {
        'browser_and_wav_durations': all(observed['checks'].values())
        and set(dict(observed['files'])) == set(lengths)
        and all(abs(duration - lengths[name]) < 1 / case['sample_rate_hz'] for name, duration in observed['files']),
        'browser_export_preserves_observation': responses['browser']['01']['observations'] == '速さの差, "比較"\n文中の間',
        'independent_counts_by_split': summary == case['expected_fixture'],
        'blank_rows_have_no_judgments': all(totals['rows'] == [case['splits'][split]] * 2 + [0]
                                            for split, totals in blank.items()),
        'malformed_responses_rejected': rejected == len(invalid),
    }
    write(out / 'synthetic-responses.json', {'data_kind': 'synthetic', 'responses': responses, 'by_split': summary})
    return checks


def prepare(case, pairs, clips, licence, out, execute):
    folder = out / 'listening'
    folder.mkdir()
    for name, path in clips.items():
        shutil.copyfile(path, folder / name)
    shutil.copyfile(licence, folder / licence.name)
    bundle = {'case_revision': case['revision'], 'licence_sha256': sha256(licence), 'pairs': pairs}
    packet_id = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode('utf-8')).hexdigest()
    packet = {'packet_id': packet_id, **bundle}
    write(out / 'reference.json', packet)
    page, template = folder / 'index.html', folder / 'observations.csv'
    page.write_text(PAGE.read_text().replace('__PACKET_ID__', packet_id)
                    .replace('<!--PAIRS-->', '\n'.join(panel(pair) for pair in pairs)))
    template.write_bytes(encode((packet_id, pair, '', '', '') for pair in pairs))
    checks = {
        'original_audio_and_licence': all(sha256(folder / name) == sha256(path) for name, path in clips.items())
        and sha256(folder / licence.name) == bundle['licence_sha256'],
        'no_key_or_recording_ids_in_listening_folder': {p.name for p in folder.iterdir()}
        == {'index.html', 'observations.csv', licence.name, *clips}
        and all(item['recording_id'] not in page.read_text() for item in pairs.values()),
    }
    checks.update(validate_packet(case, packet, page, template, out, execute))
    return {'checks': checks, 'packet_id': packet_id, 'pairs_by_split': case['splits'],
            'audio_files': len(clips), 'human_responses': 0}


def answered_observations(rows):
    # 試験回答との照合では、空欄の行やCSV由来の改行を判定内容に含めない。
    answered = {}
    for pair, row in rows.items():
        tempo, pauses = row['tempo'], row['pauses']
        note = row['observations'].replace('\r\n', '\n').replace('\r', '\n').strip()
        if tempo != 'unanswered' or pauses != 'unanswered' or note:
            answered[pair] = (tempo, pauses, note)
    return answered


def collect(packet, blobs, data_kind, fixtures, out):
    try:
        parsed = {name: parse(blob, packet) for name, blob in blobs.items()}
    except (ValueError, csv.Error, UnicodeError) as error:
        raise ValueError(f'回答を読み込めません ({error})') from error
    if data_kind == 'human':
        fixture_responses = [answered_observations(parse(blob, packet)) for blob in fixtures]
        for name, rows in parsed.items():
            observations = answered_observations(rows)
            if not observations:
                raise ValueError(f'{name}: 人の回答には記入済みの観測が必要です')
            if observations in fixture_responses:
                raise ValueError(f'{name}: 試験用回答を人の回答として登録できません')
    original = out / 'responses'
    original.mkdir()
    for name, blob in blobs.items():
        (original / f'{name}.csv').write_bytes(blob)
    write(out / 'responses-by-source.json', {'data_kind': data_kind, 'packet_id': packet['packet_id'], 'responses': parsed})
    return {'checks': {'responses_match_packet': bool(parsed)}, 'data_kind': data_kind,
            'packet_id': packet['packet_id'], 'response_ids': list(parsed), 'by_split': summarize(packet, parsed)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    commands.add_parser('prepare').add_argument('run_id')
    intake = commands.add_parser('collect')
    intake.add_argument('run_id')
    intake.add_argument('--packet', required=True)
    intake.add_argument('--kind', choices=('human', 'synthetic'), required=True)
    intake.add_argument('--response', metavar='ID=CSV', action='append', required=True)
    args = parser.parse_args()
    case = read(CASE)
    revision = case['upstream_revision']
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
    if head != revision or subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM):
        parser.error('変更のない固定上流版が必要です')
    inputs = [CASE, Path(__file__).resolve(), WORKSPACE / 'tools/measure_csd_envelope_timing.py',
              WORKSPACE / 'tools/measure_speech_timing.py', WORKSPACE / 'tools/measure_uniform_tube.py',
              WORKSPACE / 'tools/upstream_baseline.py']
    metadata = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
                'action': args.action, 'invoked_from': str(Path.cwd()),
                'analysis_command': [sys.executable, *sys.argv]}
    if args.action == 'prepare':
        pairs, clips, licence, source_inputs = load_trials(case)
        inputs.extend((PAGE, BROWSER, *source_inputs, UPSTREAM / 'docs/speech-comparison.md',
                       UPSTREAM / 'crates/chimera-cli/src/compare/tsp.rs'))

        def run(out, execute):
            execute(['cargo', 'test', '--locked', '--offline', '-p', 'chimera-cli', 'compare::tsp::tests'],
                    cwd=UPSTREAM, stdout=out / 'upstream-tsp-tests.log')
            return prepare(case, pairs, clips, licence, out, execute)
    else:
        if not IDENTIFIER.fullmatch(args.packet):
            parser.error('試聴資料の実行IDが不正です')
        packet_run = hydrate_run(args.packet, case['id'], revision)
        if packet_run[1]['action'] != 'prepare' or packet_run[1]['case_revision'] != case['revision']:
            parser.error('同じ版で作った試聴資料の実行IDを指定してください')
        reference = verified_file(*packet_run, 'artifacts/reference.json')
        packet = read(reference)
        fixture_paths = [verified_file(*packet_run, f'artifacts/{kind}-fixture.csv') for kind in ('browser', 'manual')]
        inputs.extend((packet_run[0] / 'manifest.json', reference, *fixture_paths))
        inputs.extend(verified_file(*packet_run, f'artifacts/listening/{name}')
                      for name in ('index.html', 'observations.csv', 'TSP-licence.txt'))
        inputs.extend(verified_file(*packet_run, f'artifacts/listening/{pair}-{label}.wav')
                      for pair in packet['pairs'] for label in LETTERS)
        data = {}
        for response in args.response:
            name, marker, path = response.partition('=')
            if not marker or not IDENTIFIER.fullmatch(name) or not path or name in data:
                parser.error('重複しない回答IDとCSVをID=CSVで指定してください')
            csv_path = Path(path).resolve(strict=True)
            if not csv_path.is_file() or csv_path in data.values():
                parser.error('各回答に異なるCSVファイルを指定してください')
            data[name] = csv_path
        blobs = {name: path.read_bytes() for name, path in data.items()}
        metadata.update(packet_run=args.packet, data_kind=args.kind, response_files={
            name: {'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()} for name, blob in blobs.items()})

        def run(out, _execute):
            return collect(packet, blobs, args.kind, [path.read_bytes() for path in fixture_paths], out)

    return record_measurement(args.run_id, CASE, inputs, metadata, run, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
