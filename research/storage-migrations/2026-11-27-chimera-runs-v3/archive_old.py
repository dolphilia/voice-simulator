import argparse
from collections import Counter, defaultdict
from datetime import datetime
import json
import os
from pathlib import Path
import stat
import subprocess
from uuid import uuid4

from consolidate import ARCHIVE, GIB, ROOT, RUNS, SHA256, event, hash_file, metadata, relpath, state


CUTOFF = datetime.fromisoformat('2026-11-21T00:00:00+09:00').timestamp()
DESTINATION = ARCHIVE / '2026-11-27-chimera-runs-v3'


def mappings():
    protected = set()
    pinned = set()
    runs = {path.name for path in RUNS.iterdir() if path.is_dir() and not path.name.startswith('.')}
    local = defaultdict(dict)
    archive = defaultdict(set)
    for case in (RUNS.parent / 'cases').glob('*.json'):
        data = json.loads(case.read_bytes())
        pending = [data]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str) and value in runs:
                pinned.add(value)
    for manifest in sorted(RUNS.glob('*/manifest.json')):
        data = json.loads(manifest.read_bytes())
        for record in data.get('inputs', []):
            name = record.get('path')
            if isinstance(name, str):
                name = '/' + name
                if '/runs/' in name:
                    protected.add(name.partition('/runs/')[2])
        records = list(data.get('outputs', []))
        for entry in data.get('cases', []):
            records.extend(entry.get('outputs', []))
        for entry in records:
            relative = relpath(entry.get('path'))
            size, digest = entry.get('bytes'), entry.get('sha256')
            if (relative is None or relative.parts[0] != 'artifacts' or relative.suffix != '.csv'
                    or type(size) is not int or size < 20 * 2**20
                    or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
                continue
            path = manifest.parent / relative
            try:
                status = path.lstat()
                if stat.S_ISLNK(status.st_mode):
                    physical = path.resolve(strict=True)
                    if physical.is_relative_to(ARCHIVE) and physical.stat().st_size == size:
                        archive[(size, digest)].add(physical)
                    continue
                if (data.get('status') == 'pass' and manifest.stat().st_mtime < CUTOFF
                        and stat.S_ISREG(status.st_mode) and status.st_size == size
                        and status.st_mtime < CUTOFF and path.resolve(strict=True) == path):
                    local[(size, digest)][path] = status
            except OSError:
                continue
    return local, archive, protected, pinned


def mode(info):
    return info.st_mode, info.st_uid, info.st_gid, info.st_flags


def move(paths, choices, size, digest, ledger):
    partition = defaultdict(list)
    verified = set()
    for path, info in paths:
        if state(path.lstat()) != state(info):
            raise ValueError(f'元の状態が変わりました {path}')
        if info.st_ino not in verified:
            if hash_file(path) != digest or state(path.lstat()) != state(info):
                raise ValueError(f'元のSHA-256が一致しません {path}')
            verified.add(info.st_ino)
        partition[mode(info), metadata(path)].append((path, info))
    result = Counter()
    for (attributes, extended), members in partition.items():
        source = members[0][0]
        target = next((
            path for path in sorted(choices)
            if path.is_file() and mode(path.lstat()) == attributes and metadata(path) == extended
            and hash_file(path) == digest
        ), None)
        if target is None:
            target = DESTINATION / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f'.archive-copy-{uuid4().hex}')
            try:
                subprocess.run(['/bin/cp', '-p', str(source), str(temporary)], check=True)
                pack = temporary.lstat()
                if pack.st_size != size or mode(pack) != attributes or metadata(temporary) != extended:
                    raise ValueError(f'コピーのサイズまたは属性が一致しません {source}')
                if hash_file(temporary) != digest:
                    raise ValueError(f'コピーのSHA-256が一致しません {source}')
                with temporary.open('rb') as archived:
                    os.fsync(archived.fileno())
                os.link(temporary, target, follow_symlinks=False)
            finally:
                temporary.unlink(missing_ok=True)
            result['archive_bytes_added'] += target.stat().st_blocks * 512
        else:
            result['existing_archive_reused'] += 1
        archived_state = state(target.lstat())
        event(ledger, action='prepared', target=str(target), sha256=digest, bytes=size,
              paths=[str(path.relative_to(ROOT)) for path, _ in members])
        os.fsync(ledger.fileno())
        for path, info in members:
            temporary = path.with_name(f'.archive-link-{uuid4().hex}')
            try:
                temporary.symlink_to(target)
                before = path.lstat()
                if state(before) != state(info) or state(temporary.stat()) != archived_state:
                    raise ValueError(f'切替前の照合に失敗しました {path}')
                os.replace(temporary, path)
                if path.resolve(strict=True) != target or state(path.stat()) != archived_state:
                    raise ValueError(f'切替後の照合に失敗しました {path}')
                result['paths_archived'] += 1
                if before.st_nlink == 1:
                    result['local_bytes_unlinked'] += before.st_blocks * 512
            finally:
                temporary.unlink(missing_ok=True)
        event(ledger, action='archived', target=str(target), sha256=digest, **result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--ledger', type=Path)
    parser.add_argument('--groups', type=int)
    args = parser.parse_args()
    if args.apply and args.ledger is None:
        parser.error('--apply には --ledger が必要です')
    local, archive, protected, pinned = mappings()
    groups = []
    for key, files in local.items():
        inode_paths = defaultdict(list)
        for path, info in files.items():
            inode_paths[info.st_ino].append((path, info))
        complete = [
            aliases for aliases in inode_paths.values()
            if len(aliases) == aliases[0][1].st_nlink
            and all(path.relative_to(RUNS).as_posix() not in protected
                    and path.relative_to(RUNS).parts[0] not in pinned for path, _ in aliases)
        ]
        if complete:
            blocks = sum(aliases[0][1].st_blocks * 512 for aliases in complete)
            groups.append((key, [item for aliases in complete for item in aliases], blocks))
    groups.sort(key=lambda entry: (bool(archive[entry[0]]), entry[2]), reverse=True)
    groups = groups[:args.groups]
    print('候補', len(groups), '群', sum(len(files) for _, files, _ in groups), 'パス',
          f'{sum(blocks for _, _, blocks in groups) / GIB:.3f} GiB', '既存保存先あり',
          f'{sum(blocks for key, _, blocks in groups if archive[key]) / GIB:.3f} GiB', flush=True)
    print('後続の入力で参照されたパス', len(protected), 'ケースで指定された実行', len(pinned), flush=True)
    for key, files, blocks in groups[:8]:
        print(f'{blocks / GIB:.3f} GiB', len(files), files[0][0].relative_to(RUNS), bool(archive[key]), flush=True)
    if not args.apply:
        return
    if not os.path.ismount(ARCHIVE.parents[1]):
        raise SystemExit('保存用ディスクを確認してください')
    total = Counter()
    with args.ledger.open('x') as ledger:
        event(ledger, action='start', destination=str(DESTINATION), groups=len(groups))
        for index, ((size, digest), files, _) in enumerate(groups, 1):
            total.update(move(files, archive[(size, digest)], size, digest, ledger))
            if index % 10 == 0 or index == len(groups):
                print('保管移行', index, '/', len(groups), dict(total), flush=True)
        event(ledger, action='complete', **total)


if __name__ == '__main__':
    main()
