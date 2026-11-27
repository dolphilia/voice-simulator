import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import stat
import subprocess
from uuid import uuid4

from consolidate import ARCHIVE, GIB, RUNS, SHA256, event, hash_file, metadata, relpath, state


COMPRESSED = getattr(stat, 'UF_COMPRESSED', 0x20)
PACKING_ATTRS = {b'com.apple.decmpfs', b'com.apple.ResourceFork'}


def preserved_metadata(path, info):
    attrs, acl = metadata(path)
    return (info.st_mode, info.st_uid, info.st_gid, info.st_mtime_ns, info.st_flags & ~COMPRESSED,
            tuple(item for item in attrs if item[0] not in PACKING_ATTRS), acl)


def registered():
    digests = defaultdict(set)
    for manifest in sorted(RUNS.glob('*/manifest.json')):
        content = json.loads(manifest.read_bytes())
        entries = list(content.get('outputs', []))
        for case in content.get('cases', []):
            entries.extend(case.get('outputs', []))
        for entry in entries:
            name = relpath(entry.get('path'))
            digest = entry.get('sha256')
            if (name is None or name.suffix != '.csv' or not isinstance(digest, str)
                    or not SHA256.fullmatch(digest)):
                continue
            path = manifest.parent / name
            if not path.is_symlink():
                continue
            try:
                physical = path.resolve(strict=True)
                info = physical.lstat()
            except OSError:
                continue
            if (physical.is_relative_to(ARCHIVE) and stat.S_ISREG(info.st_mode)
                    and info.st_size == entry.get('bytes')):
                digests[info.st_ino].add(digest)
    return digests


def candidates(minimum):
    digests = registered()
    files = defaultdict(list)
    for path in ARCHIVE.rglob('*.csv'):
        info = path.lstat()
        if (stat.S_ISREG(info.st_mode) and info.st_size >= minimum and not info.st_flags & COMPRESSED
                and path.resolve(strict=True) == path and info.st_dev == ARCHIVE.stat().st_dev):
            files[info.st_ino].append((path, info))
    return sorted(
        [(next(iter(digests[inode])), paths) for inode, paths in files.items()
         if len(digests[inode]) == 1 and len(paths) == paths[0][1].st_nlink],
        key=lambda entry: entry[1][0][1].st_blocks, reverse=True,
    )


def compress(digest, files, ledger):
    source, original = files[0]
    if state(source.lstat()) != state(original) or hash_file(source) != digest:
        raise ValueError(f'SHA-256の記録が一致しません {source}')
    source_attrs, _ = metadata(source)
    if any(name in PACKING_ATTRS for name, _ in source_attrs):
        return 0, 0
    staged = source.with_name(f'.chimera-packed-{uuid4().hex}')
    try:
        subprocess.run(['/usr/bin/ditto', '--hfsCompression', str(source), str(staged)], check=True)
        packed = staged.lstat()
        if not packed.st_flags & COMPRESSED or packed.st_blocks >= original.st_blocks:
            return 0, 0
        if packed.st_size != original.st_size or hash_file(staged) != digest:
            raise ValueError(f'透過的に復号したCSVが一致しません {source}')
        if preserved_metadata(source, original) != preserved_metadata(staged, packed):
            raise ValueError(f'圧縮後のファイル属性が一致しません {source}')
        with staged.open('rb') as copy:
            os.fsync(copy.fileno())
        event(ledger, action='prepared', sha256=digest, bytes=original.st_size,
              paths=[str(path.relative_to(ARCHIVE)) for path, _ in files])
        os.fsync(ledger.fileno())
        for path, old in files:
            alias = path.with_name(f'.chimera-packed-link-{uuid4().hex}')
            try:
                os.link(staged, alias, follow_symlinks=False)
                if state(path.lstat()) != state(old) or state(alias.lstat()) != state(packed):
                    raise ValueError(f'切替前にファイルが変化しました {path}')
                os.replace(alias, path)
                if state(path.lstat()) != state(packed):
                    raise ValueError(f'圧縮後のパスが一致しません {path}')
            finally:
                alias.unlink(missing_ok=True)
        gain = (original.st_blocks - packed.st_blocks) * 512
        event(ledger, action='compressed', sha256=digest, paths=len(files), bytes_saved=gain)
        return gain, len(files)
    finally:
        staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('ledger', type=Path)
    parser.add_argument('--groups', type=int)
    parser.add_argument('--minimum-mib', type=int, default=20)
    args = parser.parse_args()
    groups = candidates(args.minimum_mib * 2**20)[:args.groups]
    print('透過圧縮候補', len(groups), '実体', f'{sum(files[0][1].st_blocks * 512 for _, files in groups) / GIB:.2f} GiB', flush=True)
    total = Counter()
    with args.ledger.open('x') as log:
        event(log, action='start', root=str(ARCHIVE), candidates=len(groups))
        for index, (digest, files) in enumerate(groups, 1):
            try:
                saved, paths = compress(digest, files, log)
            except (ValueError, OSError, subprocess.CalledProcessError) as error:
                total['skipped'] += 1
                event(log, action='skip', sha256=digest, reason=str(error))
                continue
            total['bytes_saved'] += saved
            total['paths_compressed'] += paths
            total['objects_compressed'] += paths > 0
            if index % 10 == 0 or index == len(groups):
                print(f'{index}/{len(groups)} 実体', f'{total["bytes_saved"] / GIB:.2f} GiB', flush=True)
        event(log, action='complete', **total)


if __name__ == '__main__':
    main()
