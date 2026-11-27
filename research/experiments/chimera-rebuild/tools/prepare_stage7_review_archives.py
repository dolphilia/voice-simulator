"""試聴とF2注釈の資料を、別の場所で開けるZIPに保存する。"""

import argparse
import csv
from pathlib import Path
import stat
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from audit_plan_evidence import ROOT, RUNS, read_json
from measure_csd_envelope_timing import verified_file
from measure_uniform_tube import record_measurement
from upstream_baseline import WORKSPACE, sha256


CASE = WORKSPACE / 'cases/stage7-review-archives.json'
BROWSER_TOOLS = ROOT / 'web/prototypes/chimera-research/tools'


def load_packet(spec, revision):
    run = RUNS / spec['run']
    manifest_path = run / 'manifest.json'
    manifest = read_json(manifest_path)
    if (sha256(manifest_path) != spec['manifest_sha256']
            or (manifest['run_id'], manifest['case_id'], manifest['upstream_revision'], manifest['status'])
            != (spec['run'], spec['case_id'], revision, 'pass')):
        raise ValueError(f'登録した元資料の実行と一致しません ({run.name})')
    summary = verified_file(run, manifest, 'summary.json')
    if read_json(summary)['packet_id'] != spec['packet_id']:
        raise ValueError(f'元資料のIDが一致しません ({run.name})')
    prefix = f'artifacts/{spec["folder"]}/'
    public = {}
    for entry in manifest['outputs']:
        if entry['path'].startswith(prefix):
            name = entry['path'][len(prefix):]
            if not name or Path(name).name != name or '\\' in name or name in ('.', '..', 'reference.json'):
                raise ValueError(f'評価者用のファイル名が不正です ({name})')
            public[name] = verified_file(run, manifest, entry['path'])
    audio = [name for name in public if name.endswith('.wav')]
    figures = [name for name in public if name.endswith('.png')]
    if (len(audio), len(figures)) != (spec['audio'], spec['figures']) or set(public) != {
            'index.html', 'observations.csv', *spec['notices'], *audio, *figures}:
        raise ValueError(f'評価者用のファイル一覧が登録値と一致しません ({run.name})')
    original_csv = (verified_file(run, manifest, spec['original_browser_csv'])
                    if 'original_browser_csv' in spec else None)
    return {'public': public, 'original_csv': original_csv, 'inputs': [manifest_path, summary, *public.values()]}


def csv_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        header, *rows = csv.reader(stream, strict=True)
    return header, rows


def create_archive(public, archive):
    with ZipFile(archive, 'x', compression=ZIP_DEFLATED, compresslevel=6) as bundle:
        for name, path in sorted(public.items()):
            info = ZipInfo(name)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            bundle.writestr(info, path.read_bytes())


def validate_export(template, export, spec):
    header, blank = csv_rows(template)
    columns, filled = csv_rows(export)
    if columns != header or header[:2] not in (['packet_id', 'pair'], ['packet_id', 'trial']):
        return False
    if any(len(row) != len(header) for row in (*blank, *filled)):
        return False
    ids = [(row[0], row[1]) for row in filled]
    return (
        len(filled) == len(blank) == spec['trials']
        and ids == [(row[0], row[1]) for row in blank] and len(set(ids)) == spec['trials']
        and all(packet == spec['packet_id'] for packet, _ in ids)
        and all(not any(row[2:]) for row in blank)
        and any(any(row[2:]) for row in filled)
    )


def measure(case, packets, out, execute):
    tests = out / 'synthetic-checks'
    tests.mkdir()
    checks, results = {}, {}
    for label, spec in case['packets'].items():
        entry = packets[label]
        public = entry['public']
        archive = out / f'{label}.zip'
        create_archive(public, archive)
        browser_output = tests / f'{label}-browser.json'
        exported = tests / f'{label}-synthetic-response.csv'
        with TemporaryDirectory(dir=out.parent, prefix=f'{label}-展開-') as directory:
            extracted = Path(directory)
            with ZipFile(archive) as bundle:
                checks[f'{label}/regular_archive_members'] = (
                    bundle.namelist() == sorted(public)
                    and all(stat.S_ISREG(info.external_attr >> 16) for info in bundle.infolist()))
                bundle.extractall(extracted)
            checks[f'{label}/source_bytes_preserved'] = all(
                sha256(extracted / name) == sha256(source) for name, source in public.items())
            execute(['node', str(BROWSER_TOOLS / spec['verifier']), str(extracted / 'index.html'),
                     str(exported)], stdout=browser_output)
            checks[f'{label}/response_rows_and_packet_id'] = validate_export(extracted / 'observations.csv', exported, spec)
        browser = read_json(browser_output)
        checks.update({f'{label}/browser/{name}': value for name, value in browser['checks'].items()})
        if entry['original_csv'] is not None:
            checks[f'{label}/original_browser_csv_reproduced'] = sha256(exported) == sha256(entry['original_csv'])
        results[label] = {'packet_id': spec['packet_id'], 'packet_run': spec['run'], 'files': len(public),
                          'audio': spec['audio'], 'figures': spec['figures'], 'trials': spec['trials'],
                          'archive_bytes': archive.stat().st_size, 'archive_sha256': sha256(archive),
                          'browser_version': browser.get('version', browser.get('browser_version'))}
    return {'checks': checks, 'packets': results, 'response_kind': 'synthetic'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read_json(CASE)
    revision = case['upstream_revision']
    packets = {label: load_packet(spec, revision) for label, spec in case['packets'].items()}
    for label, spec in case['packets'].items():
        if spec.get('tsp_licence'):
            packets[label]['public']['TSP-licence.txt'] = packets['tsp-listening']['public']['TSP-licence.txt']
    inputs = [CASE, Path(__file__).resolve(), *(BROWSER_TOOLS / spec['verifier'] for spec in case['packets'].values())]
    for entry in packets.values():
        inputs.extend(entry['inputs'])
        if entry['original_csv'] is not None:
            inputs.append(entry['original_csv'])
    details = {'case_id': case['id'], 'case_revision': case['revision'], 'upstream_revision': revision,
               'analysis_command': [sys.executable, *sys.argv], 'analysis_directory': str(Path.cwd())}
    return record_measurement(args.run_id, CASE, inputs, details,
                              lambda out, execute: measure(case, packets, out, execute), command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
