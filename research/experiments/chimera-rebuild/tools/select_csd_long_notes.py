"""CSDの注釈だけで長音の曲を選び、別実行で選定済みのWAVだけを取得する。"""

import argparse
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import sys
import wave
from zipfile import BadZipFile, ZipFile

from fetch_csd_inputs import RemoteZip
from measure_csd_envelope_timing import verified_file
from measure_csd_song_f0 import measurement_windows
from measure_csd_song_planning import parse_notes
from measure_speech_timing import read, write
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/csd-long-note-vibrato.json'


class CountedZip(RemoteZip):
    def __init__(self, url, size, prefix):
        self.ranges = []
        super().__init__(url, size, prefix)

    def fetch(self, start, stop):
        payload = super().fetch(start, stop)
        self.ranges.append({'first_byte': start, 'last_byte': stop-1, 'bytes': len(payload)})
        return payload


def zip_input(data):
    root = Path(data['work_root'])
    prefix = root / 'CSD.zip'
    if not prefix.is_file():
        prefix = root / 'CSD.zip.part'
    return CountedZip(data['archive_url'], data['archive_bytes'], prefix)


def packed_path(song, kind):
    return f'CSD/english/{kind}/{song}.{kind}'


def extract(archive, entry, out):
    info = archive.getinfo(entry)
    contents = archive.read(info)  # ZipFile で CRC32 を検証する。
    target = out / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(contents)
    return target, {'path': entry, 'bytes': len(contents), 'crc32': f'{info.CRC:08x}',
                    'sha256': hashlib.sha256(contents).hexdigest()}


def summarize_song(path, song, selection, score, pitch):
    counts, notable, grid_differences = [], [], []
    notes = parse_notes(path, score)
    for i, n in enumerate(notes):
        melisma = n['syllable'].get('melisma', False)
        _, centers = measurement_windows({'start': float(n['start']), 'end': float(n['end']),
                                          'melisma': melisma}, pitch)
        trims = pitch['melisma_window'] if melisma else pitch['regular_window']
        fraction = 1 - sum(Decimal(str(x)) for x in trims)
        ideal = int((n['end']-n['start']) * fraction / Decimal(str(pitch['hop_seconds']))) + 1
        count = len(centers)
        counts.append(count)
        if count != ideal:
            grid_differences.append({'note_index': i, 'float_frames': count, 'decimal_frames': ideal})
        if count >= selection['eligible_frames']:
            notable.append({'note_index': i, 'annotation_seconds': [float(n['start']), float(n['end'])],
                            'stable_frames': count, 'midi': float(n['midi']), 'melisma': melisma})
    split = 'held_out' if int(song[2:-1]) % 5 == 0 else 'calibration'
    return {'id': song, 'split': split, 'notes': len(notes), 'total_frames': sum(counts),
            'longest_grid_frames': max(counts), 'eligible_notes': len(notable),
            'preferred_notes': sum(x >= selection['preferred_frames'] for x in counts),
            'annotation_long_notes': notable, 'grid_rounding_differences': grid_differences}


def select(case, planning, pitch, out, _execute):
    config = case['selection']
    first, last = config['song_number_range']
    ids = [f"en{n:03d}{config['key']}" for n in range(first, last+1)]
    wanted = {packed_path(song, 'csv'): song for song in ids}
    ranking, inputs = [], {}
    remote = zip_input(planning['dataset'])
    try:
        with ZipFile(remote) as archive:
            entries = sorted((archive.getinfo(p) for p in wanted), key=lambda x: x.header_offset)
            for info in entries:
                path, item = extract(archive, info.filename, out)
                song = wanted[info.filename]
                ranking.append(summarize_song(path, song, config, planning['score'], pitch))
                inputs[song] = item
    except (BadZipFile, KeyError) as exc:
        raise ValueError(f'配布ZIPの注釈が登録と一致しません ({exc})') from exc
    ranking.sort(key=lambda r: (r['split'], -r['preferred_notes'], -r['eligible_notes'], -r['longest_grid_frames'], r['id']))
    chosen = {}
    for split in ('calibration', 'held_out'):
        chosen[split] = next((r['id'] for r in ranking if r['split'] == split and r['eligible_notes']), None)
    differences = [abs(x['float_frames']-x['decimal_frames'])
                   for s in ranking for x in s['grid_rounding_differences']]
    checks = {'all_annotations': sorted(r['id'] for r in ranking) == ids,
              'stable_windows_match_decimal_grid': max(differences, default=0) <= config['max_grid_difference_frames'],
              'separate_registered_splits': set(chosen) == {'calibration', 'held_out'}}
    return {'checks': checks, 'selected': chosen, 'ranking': ranking, 'annotations': inputs,
            'zip_ranges': remote.ranges, 'wav_payloads_opened': 0}


def fetch_waves(planning, selection, out, _execute):
    remote = zip_input(planning['dataset'])
    data = {}
    try:
        with ZipFile(remote) as archive:
            for split, song in selection['selected'].items():
                if song is None:
                    continue
                f, desc = extract(archive, packed_path(song, 'wav'), out)
                with wave.open(str(f), 'rb') as wav:
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (
                            2, 2, planning['dataset']['recording_rate_hz']):
                        raise ValueError(f'録音のサンプル形式が先行CSDケースと一致しません ({song})')
                    desc.update(rate_hz=wav.getframerate(), frames=wav.getnframes())
                data[split] = {'song': song, 'wav': desc}
    except (BadZipFile, KeyError, wave.Error) as exc:
        raise ValueError(f'配布ZIPの録音を確認できません ({exc})') from exc
    return {'checks': {'only_selected_waves': {k: r['song'] for k, r in data.items()} ==
                      {k: s for k, s in selection['selected'].items() if s is not None}},
            'waves': data, 'zip_ranges': remote.ranges}


def verified_selection(root, case):
    manifest_path = root / 'manifest.json'
    manifest = read(manifest_path)
    registered = CASE.relative_to(WORKSPACE.parents[2]).as_posix()
    current = next((v['sha256'] for v in manifest['inputs'] if v['path'] == registered), None)
    if (manifest['status'] != 'pass' or manifest['case_id'] != case['id']
            or manifest['stage'] != 'annotations' or current != sha256(CASE)):
        raise ValueError('現行ケースと同じ条件で選定した注釈実行を指定してください')
    output = verified_file(root, manifest, 'summary.json')
    return manifest_path, manifest, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    parser.add_argument('--selection-run', help='注釈の選定後に取得するWAVの元実行ID')
    args = parser.parse_args()
    if os.environ.get('CHIMERA_RUN_STORAGE') != 'rtl9210b':
        parser.error('作業用ディスクを指定してください')
    case = read(CASE)
    planning_case, pitch_case = (CASE.parent / case[k] for k in ('dataset_case', 'pitch_case'))
    planning = read(planning_case)
    data = planning['dataset']
    metadata_path = Path(data['work_root']) / 'zenodo-4916302.json'
    prior = read(metadata_path.with_name('selected-inputs.json'))
    official = read(metadata_path)
    archive, = (x for x in official['files'] if x['key'] == 'CSD.zip')
    if (sha256(metadata_path) != prior['metadata_sha256'] or official['doi'] != data['doi']
            or (archive['size'], archive['checksum'], archive['links']['self']) !=
              (data['archive_bytes'], 'md5:'+data['archive_md5'], data['archive_url'])
            or official['metadata']['license']['id'] != data['license'].lower().replace(' ', '-')):
        parser.error('配布元の保存済みメタデータが登録版と一致しません')
    inputs = [CASE, planning_case, pitch_case, Path(__file__).resolve(), WORKSPACE / 'tools/fetch_csd_inputs.py',
              WORKSPACE / 'tools/measure_csd_song_f0.py', WORKSPACE / 'tools/measure_csd_song_planning.py',
              WORKSPACE / 'tools/measure_csd_envelope_timing.py']
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': case['upstream_revision'],
               'driver': [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
               'dataset_doi': data['doi'], 'archive_whole_md5_verified': False, 'license': data['license'],
               'distribution_metadata_sha256': prior['metadata_sha256']}
    if args.selection_run:
        root = WORKSPACE / 'runs' / args.selection_run
        manifest_path, _, selected_path = verified_selection(root, case)
        inputs.extend((manifest_path, selected_path))
        selected = read(selected_path)
        details.update(stage='recordings', selection_run=args.selection_run)

        def work(out, execute):
            (out / 'zenodo-4916302.json').write_bytes(metadata_path.read_bytes())
            return fetch_waves(planning, selected, out, execute)
    else:
        details['stage'] = 'annotations'
        pitch = read(pitch_case)['measurement']

        def work(out, execute):
            (out / 'zenodo-4916302.json').write_bytes(metadata_path.read_bytes())
            return select(case, planning, pitch, out, execute)

    return record_measurement(args.run_id, CASE, inputs, details, work, command=None, input_root=WORKSPACE.parents[2])


if __name__ == '__main__':
    raise SystemExit(main())
