"""実行記録と照合した同一CSVを、元のパスで読めるハードリンクにまとめる。"""

import argparse
from collections import defaultdict
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from uuid import uuid4

from upstream_baseline import WORKSPACE, sha256


def file_state(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, permissions(info)


def permissions(info):
    return info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), getattr(info, 'st_flags', 0)


def recorded_csv(runs):
    groups = defaultdict(dict)
    for manifest_path in sorted(runs.glob('*/manifest.json')):
        if manifest_path.resolve() != manifest_path:
            continue
        manifest = json.loads(manifest_path.read_text())
        seen = {}
        for record in (manifest, *manifest.get('cases', [])):
            for entry in record.get('outputs', []):
                name = PurePosixPath(entry['path'])
                if (not name.parts or name.parts[0] != 'artifacts' or '..' in name.parts
                        or name.suffix != '.csv'):
                    continue
                value = entry['bytes'], entry['sha256']
                if name in seen and seen[name] != value:
                    raise ValueError(f'同じ成果に異なる記録があります: {manifest_path} {name}')
                seen[name] = value
        for name, (size, digest) in seen.items():
            path = manifest_path.parent / name
            if not isinstance(size, int) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                continue
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(info.st_mode) and info.st_size == size and path.resolve() == path:
                groups[info.st_dev, permissions(info), size, digest][path] = info
    return groups


def possible_savings(entries):
    allocated = {info.st_ino: info.st_blocks * 512 for info in entries.values()}
    return sum(allocated.values()) - max(allocated.values())


def write_event(ledger, event):
    print(json.dumps(event, ensure_ascii=False), file=ledger, flush=True)


def deduplicate(runs, ledger, limit):
    groups = recorded_csv(runs)
    candidates = sorted(groups.items(), key=lambda group: possible_savings(group[1]), reverse=True)
    candidates = [(key, entries) for key, entries in candidates if possible_savings(entries) > 0][:limit]
    print(f'{len(candidates)} グループ、削減候補 {sum(possible_savings(items) for _, items in candidates) / 2**30:.2f} GiB', flush=True)
    result = {'groups_selected': len(candidates), 'groups_verified': 0, 'paths_linked': 0,
              'bytes_unlinked': 0, 'groups_skipped': 0}
    for index, ((_, _, size, digest), entries) in enumerate(candidates, 1):
        checks = {}
        for path, info in entries.items():
            if file_state(path.lstat()) != file_state(info):
                checks[info.st_ino] = False
            elif info.st_ino not in checks:
                checks[info.st_ino] = sha256(path) == digest and file_state(path.lstat()) == file_state(info)
        if not all(checks.values()):
            result['groups_skipped'] += 1
            write_event(ledger, {'action': 'skip', 'reason': 'ハッシュまたは実体が変化', 'sha256': digest,
                                 'paths': [str(p.relative_to(runs)) for p in entries]})
            continue
        # 共有済みの実体があれば残す。既存のリンク先を維持し、二重置換を避ける。
        canonical = max(entries, key=lambda path: (entries[path].st_nlink, entries[path].st_blocks))
        keep = entries[canonical]
        for path, info in entries.items():
            if info.st_ino == keep.st_ino:
                continue
            temporary = path.with_name(f'.dedup-{uuid4().hex}')
            os.link(canonical, temporary, follow_symlinks=False)
            try:
                current = path.lstat()
                if file_state(current) != file_state(info) or file_state(temporary.lstat()) != file_state(keep):
                    raise OSError(f'置換前に成果の実体が変化しました: {path}')
                event = {'path': str(path.relative_to(runs)), 'canonical': str(canonical.relative_to(runs)),
                         'bytes': size, 'sha256': digest}
                write_event(ledger, {'action': 'prepared', **event})
                os.replace(temporary, path)
                if file_state(path.lstat()) != file_state(keep):
                    raise OSError(f'置換後の実体が一致しません: {path}')
                reclaimed = current.st_blocks * 512 if current.st_nlink == 1 else 0
                write_event(ledger, {'action': 'linked', 'bytes_unlinked': reclaimed, **event})
                result['paths_linked'] += 1
                result['bytes_unlinked'] += reclaimed
            finally:
                temporary.unlink(missing_ok=True)
        result['groups_verified'] += 1
        if index in (1, 10) or index % 100 == 0:
            print(f'{index}/{len(candidates)} グループ、実体 {result["bytes_unlinked"] / 2**30:.2f} GiB を統合', flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ledger', type=Path, help='新規の照合台帳 (JSONL)')
    parser.add_argument('--groups', type=int, help='削減候補が大きい順の対象グループ数')
    args = parser.parse_args()
    if args.groups is not None and args.groups < 1:
        parser.error('--groups には1以上を指定してください')

    runs = WORKSPACE / 'runs'
    with args.ledger.open('x') as ledger:
        write_event(ledger, {'action': 'start', 'time': datetime.now().astimezone().isoformat(),
                             'free_bytes_before': shutil.disk_usage(runs).free})
        result = deduplicate(runs, ledger, args.groups)
        write_event(ledger, {'action': 'complete', 'free_bytes_after': shutil.disk_usage(runs).free, **result})
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
