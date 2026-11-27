"""段階の代表実行と保存先を、元のマニフェストから読み直す。"""

import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import subprocess

from measure_uniform_tube import record_measurement
from run_storage import WORK_DISK, WORK_UUID, mounted_volume
from upstream_baseline import UPSTREAM, WORKSPACE, sha256


CASE_PATH = WORKSPACE / 'cases/plan-evidence-audit.json'
RUNS = WORKSPACE / 'runs'
ROOT = WORKSPACE.parents[2]
ARCHIVE_DISK = Path('/Volumes/CT2000X8')
ARCHIVE_UUID = '9B51F3F1-8509-4272-B72B-ABA311912659'


def read_json(path):
    return json.loads(path.read_text())


def read_record(run_id, expected_revision, expected_failure, *, expected_failed_checks=(), expected_error=None):
    run = RUNS / run_id
    manifest = read_json(run / 'manifest.json')
    summary_path = run / 'summary.json'
    checks = read_json(summary_path)['checks'] if summary_path.is_file() else {}
    outputs = list(manifest.get('outputs', []))
    if 'cases' in manifest:
        cases = manifest['cases']
        checks = {entry['id']: entry['status'] == 'pass' and entry['exit_code'] == 0 for entry in cases}
        for entry in cases:
            outputs.extend([entry['log'], *entry['outputs']])
        status_ok = set(checks) == {'airway', 'vowels', 'ipa-vcv', 'melody'}
    else:
        status_ok = manifest['status'] == ('fail' if expected_failure else 'pass')

    errors = []
    locations = Counter()
    hashes = {}
    case_inputs = []
    if manifest.get('upstream_revision', expected_revision) != expected_revision:
        errors.append('上流版が登録値と異なる')
    expected_failed = set(expected_failed_checks)
    if expected_error is not None:
        outcome_ok = expected_failure and manifest.get('error') == expected_error and not summary_path.is_file()
    else:
        outcome_ok = bool(checks) and {name for name, result in checks.items() if result is False} == expected_failed and all(
            value is (name not in expected_failed) for name, value in checks.items())
    if not status_ok or not outcome_ok:
        errors.append('状態または記録済みの判定が不一致')
    if not outputs:
        errors.append('成果の記録が空')

    for entry in outputs:
        name = entry['path']
        path = run / name
        try:
            physical = path.resolve(strict=True)
            if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
                errors.append(f'サイズまたはSHA-256が不一致 ({name})')
                continue
        except OSError as error:
            errors.append(str(error))
            continue
        if physical.is_relative_to(ARCHIVE_DISK):
            locations[ARCHIVE_DISK.name] += 1
        elif physical.is_relative_to(WORK_DISK):
            locations[WORK_DISK.name] += 1
        else:
            locations['internal'] += 1
        hashes[name] = entry['sha256']

    snapshot = manifest.get('source_snapshot')
    if snapshot:
        for entry in manifest.get('inputs', []):
            name = entry['path']
            if '/cases/' not in '/' + name:
                continue
            # 実行成果を入力にした場合は、その先行実行が保持するファイルを参照する。
            referenced = next((base / name for base in (ROOT, WORKSPACE) if (base / name).is_relative_to(RUNS)), None)
            saved = referenced if referenced is not None else run / snapshot / name
            if not saved.is_file() or sha256(saved) != entry['sha256']:
                errors.append(f'保存したケース定義が読めないかSHA-256が不一致 ({name})')
                continue
            case_inputs.append(name)

    return {'passed_checks': [name for name, status in checks.items() if status is True], 'verified_outputs': dict(locations),
            'bytes': sum(entry['bytes'] for entry in outputs), 'case_inputs': case_inputs,
            'revision': manifest.get('upstream_revision'), 'errors': errors}, hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id')
    args = parser.parse_args()
    case = read_json(CASE_PATH)
    retention = case['retention']
    run_ids = list(dict.fromkeys(run for group in case['groups'].values() for run in group))
    inputs = [Path(__file__).resolve(), CASE_PATH, ROOT / 'docs/plans/chimera-research-rebuild-plan.md']
    inputs.extend(RUNS / name / 'manifest.json' for name in run_ids)
    inputs.extend(path for name in run_ids if (path := RUNS / name / 'summary.json').is_file())

    def audit(_artifacts, execute):
        for disk in (WORK_DISK, ARCHIVE_DISK):
            execute(['/usr/sbin/diskutil', 'info', str(disk)])
        mounted_volume(WORK_DISK, WORK_UUID)
        mounted_volume(ARCHIVE_DISK, ARCHIVE_UUID)
        execute(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM)
        execute(['git', 'status', '--porcelain'], cwd=UPSTREAM)
        head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=UPSTREAM, text=True).strip()
        differences = subprocess.check_output(['git', 'status', '--porcelain'], cwd=UPSTREAM, text=True)
        records, hashes = {}, {}
        for name in run_ids:
            records[name], hashes[name] = read_record(name, case['upstream_revision'], name == retention['failure'])
        pairs = {}
        for pair in case['storage_pairs']:
            local, external = hashes[pair['local']], hashes[pair['external']]
            pairs[pair['external']] = all(name in local and name in external and local[name] == external[name]
                                          for name in pair['files'])
        failed = RUNS / retention['failure']
        retained = RUNS / retention['success']
        failed_manifest = read_json(failed / 'manifest.json')
        entry, = read_json(retained / 'manifest.json')['retained_csv']
        with (retained / entry['path']).open(newline='') as stream:
            excerpt = list(csv.reader(stream))
        source = entry['source']
        retained_csv_ok = (excerpt == retention['expected_excerpt'] and entry['rows'] == len(excerpt) - 1
                           and not (retained / source['path']).exists()
                           and hashes[retention['failure']].get(source['path']) == source['sha256']
                           and retention['expected_error'] in failed_manifest.get('error', ''))
        checks = {f'group_{group}': all(not records[name]['errors'] for name in names)
                  for group, names in case['groups'].items()}
        checks.update(fixed_upstream=head == case['upstream_revision'] and not differences,
                      storage_pairs=all(pairs.values()), retained_csv=retained_csv_ok)
        return {'checks': checks, 'storage_pairs': pairs, 'runs': records}

    return record_measurement(args.run_id, CASE_PATH, inputs,
                              {'case_id': case['id'], 'upstream_revision': case['upstream_revision'],
                               'invoked_from': str(Path.cwd()), 'revision': case['revision']},
                              audit, command=None, input_root=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
