"""復元したCHIMERAの代表成果を、保存済みマニフェストと照合する。"""

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

from run_storage import ARCHIVE_DISK, ARCHIVE_UUID, WORK_DISK, WORK_UUID, mounted_volume
from upstream_baseline import WORKSPACE, sha256


ROOT = WORKSPACE.parents[2]
RUNS = WORKSPACE / 'runs'
DEFAULT_RUNS = {
    'storage-v3-tube-20261127-repeat': RUNS,
    'storage-v3-plan-audit-20261127': WORK_DISK,
    'lung-voiced-20261119-a': ARCHIVE_DISK,
}
SHARED_SNAPSHOT_RUNS = {'storage-v3-tube-20261127-repeat', 'storage-v3-plan-audit-20261127'}


def relative_path(name):
    path = Path(name)
    if path.is_absolute() or '..' in path.parts or not path.parts:
        raise ValueError(f'マニフェスト内の相対パスが不正です ({name})')
    return path


def check_file(base, entry):
    path = base / relative_path(entry['path'])
    if not path.is_file():
        raise ValueError(f'ファイルまたはリンク先を読めません ({path})')
    if path.stat().st_size != entry['bytes'] or sha256(path) != entry['sha256']:
        raise ValueError(f'サイズまたはSHA-256が一致しません ({path})')
    return path.resolve(strict=True)


def check_run(run_id):
    run = RUNS / run_id
    manifest = json.loads((run / 'manifest.json').read_text())
    if manifest['run_id'] != run_id:
        raise ValueError('マニフェストの実行IDが一致しません')
    outputs = list(manifest.get('outputs', []))
    for case in manifest.get('cases', []):
        outputs.extend(case.get('outputs', []))
        if 'log' in case:
            outputs.append(case['log'])
    if not outputs:
        raise ValueError('照合する出力が記録されていません')
    locations = Counter()
    for entry in outputs:
        path = check_file(run, entry)
        location = next((base for base in (WORK_DISK, ARCHIVE_DISK, RUNS) if path.is_relative_to(base)), path.parent)
        locations[location] += 1
    expected = DEFAULT_RUNS.get(run_id)
    if expected is not None and not locations[expected]:
        raise ValueError(f'代表成果を想定した保存先から読めません ({expected})')

    snapshots = 0
    if snapshot := manifest.get('source_snapshot'):
        base = run / relative_path(snapshot)
        for entry in manifest['inputs']:
            relative = relative_path(entry['path'])
            if (WORKSPACE / relative).is_relative_to(RUNS) or (ROOT / relative).is_relative_to(RUNS):
                continue  # 先行実行の成果はこの実行のソースの写しに含まれない。
            saved = check_file(base, entry)
            if run_id in SHARED_SNAPSHOT_RUNS:
                digest = entry['sha256']
                stored = RUNS / '.source-objects' / digest[:2] / digest
                if not stored.is_file() or stored.is_symlink() or not saved.samefile(stored):
                    raise ValueError(f'ソースの写しと共有実体のハードリンクが一致しません ({saved})')
            snapshots += 1
    print(f'{run_id} 出力 {len(outputs)} 件 / ソースの写し {snapshots} 件', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', action='append', help='照合する実行ID。複数指定可。既定は内蔵・作業用・保管用の代表3実行')
    args = parser.parse_args()
    run_ids = args.run_id or DEFAULT_RUNS
    for run_id in run_ids:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', run_id):
            parser.error(f'実行IDの形式が不正です ({run_id})')
    failed = False
    for mount, uuid in ((WORK_DISK, WORK_UUID), (ARCHIVE_DISK, ARCHIVE_UUID)):
        try:
            mounted_volume(mount, uuid)
            print(f'{mount} {uuid}', flush=True)
        except ValueError as error:
            print(error, file=sys.stderr)
            failed = True
    if failed:
        return 1
    for run_id in run_ids:
        try:
            check_run(run_id)
        except (OSError, ValueError, KeyError, TypeError) as error:
            print(f'{run_id} の照合に失敗しました ({error})', file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
