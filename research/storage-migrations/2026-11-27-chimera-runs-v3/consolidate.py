import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
import ctypes as c
from dataclasses import dataclass
from datetime import datetime
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from uuid import uuid4


ROOT = Path.cwd().resolve()
RUNS = ROOT / 'research/experiments/chimera-rebuild/runs'
WORK = Path('/Volumes/RTL9210B-CG/voice-simulator/scratch/chimera-runs')
ARCHIVE = Path('/Volumes/CT2000X8/voice-simulator/archive')
DESTINATIONS = {'work': WORK, 'archive': ARCHIVE, 'local': RUNS, 'source': RUNS}
GIB = 2**30
SHA256 = re.compile(r'[0-9a-f]{64}\Z')

lib = c.CDLL(None, use_errno=True)
lib.listxattr.argtypes = [c.c_char_p, c.c_void_p, c.c_size_t, c.c_int]
lib.listxattr.restype = c.c_ssize_t
lib.getxattr.argtypes = [c.c_char_p, c.c_char_p, c.c_void_p, c.c_size_t, c.c_uint32, c.c_int]
lib.getxattr.restype = c.c_ssize_t
lib.acl_get_link_np.argtypes = [c.c_char_p, c.c_int]
lib.acl_get_link_np.restype = c.c_void_p
lib.acl_to_text.argtypes = [c.c_void_p, c.c_void_p]
lib.acl_to_text.restype = c.c_void_p
lib.acl_free.argtypes = [c.c_void_p]


def metadata(path):
    encoded = os.fsencode(path)
    length = lib.listxattr(encoded, None, 0, 1)
    if length < 0:
        raise OSError(c.get_errno(), str(path))
    names = c.create_string_buffer(length)
    if lib.listxattr(encoded, names, length, 1) != length:
        raise OSError(c.get_errno(), str(path))
    values = []
    for name in sorted(names.raw.rstrip(b'\0').split(b'\0')) if length else ():
        size = lib.getxattr(encoded, name, None, 0, 0, 1)
        if size < 0:
            raise OSError(c.get_errno(), str(path))
        value = c.create_string_buffer(size)
        if lib.getxattr(encoded, name, value, size, 0, 1) != size:
            raise OSError(c.get_errno(), str(path))
        values.append((name, value.raw))
    acl = lib.acl_get_link_np(encoded, 0x100)
    acl_value = None
    if acl:
        try:
            text = lib.acl_to_text(acl, None)
            if not text:
                raise OSError(c.get_errno(), str(path))
            try:
                acl_value = c.string_at(text)
            finally:
                lib.acl_free(text)
        finally:
            lib.acl_free(acl)
    elif c.get_errno() not in (errno.ENOENT, getattr(errno, 'ENOATTR', 93)):
        raise OSError(c.get_errno(), str(path))
    return tuple(values), acl_value


def state(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_flags, info.st_size, info.st_mtime_ns)


def permissions(info):
    return (info.st_dev, info.st_mode, info.st_uid, info.st_gid, info.st_flags)


def hash_file(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def relpath(value):
    if not isinstance(value, str):
        return None
    path = PurePosixPath(value)
    return path if not path.is_absolute() and path.parts and '..' not in path.parts else None


@dataclass(frozen=True)
class File:
    path: Path
    info: os.stat_result


def inventory(mode, minimum):
    destination = DESTINATIONS[mode]
    device = destination.stat().st_dev
    groups = defaultdict(dict)
    for manifest in sorted(RUNS.glob('*/manifest.json')):
        content = json.loads(manifest.read_bytes())
        if mode == 'source':
            snap = relpath(content.get('source_snapshot'))
            if snap is None or snap != PurePosixPath('artifacts/source'):
                continue
            parent = manifest.parent / snap
            records = content.get('inputs', [])
        else:
            parent = manifest.parent
            records = list(content.get('outputs', []))
            for entry in content.get('cases', []):
                records.extend(entry.get('outputs', []))
        for entry in records:
            relative = relpath(entry.get('path'))
            size = entry.get('bytes')
            digest = entry.get('sha256')
            if (relative is None or type(size) is not int or size < minimum
                    or not isinstance(digest, str) or not SHA256.fullmatch(digest)):
                continue
            if mode != 'source' and (
                relative.parts[0] != 'artifacts' or relative.name.endswith('.log')
                or relative.is_relative_to(PurePosixPath('artifacts/source'))
            ):
                continue
            logical = parent / relative
            try:
                first = logical.lstat()
                if first.st_dev != device and not stat.S_ISLNK(first.st_mode):
                    continue
                if mode in ('local', 'source') and not stat.S_ISREG(first.st_mode):
                    continue
                if mode in ('work', 'archive') and not stat.S_ISLNK(first.st_mode):
                    continue
                physical = logical.resolve(strict=True)
                if not physical.is_relative_to(destination):
                    continue
                if mode in ('local', 'source') and physical != logical:
                    continue
                info = physical.lstat()
            except (OSError, RuntimeError):
                continue
            if stat.S_ISREG(info.st_mode) and info.st_dev == device and info.st_size == size:
                groups[(size, digest, permissions(info))][physical] = File(physical, info)
    return groups


def by_inode(files):
    return {file.info.st_ino: file for file in files}


def potential(files):
    blocks = [file.info.st_blocks * 512 for file in by_inode(files).values()]
    return sum(blocks) - max(blocks)


def event(ledger, **fields):
    ledger.write(json.dumps(fields, ensure_ascii=False, separators=(',', ':')) + '\n')
    ledger.flush()


def replace_with_link(alias, canonical):
    temporary = alias.path.with_name(f'.chimera-link-{uuid4().hex}')
    try:
        os.link(canonical.path, temporary, follow_symlinks=False)
        current = alias.path.lstat()
        if state(current) != state(alias.info) or state(temporary.lstat()) != state(canonical.info):
            raise RuntimeError(f'置換直前にファイルが変化しました {alias.path}')
        os.replace(temporary, alias.path)
        if state(alias.path.lstat()) != state(canonical.info):
            raise RuntimeError(f'置換結果が一致しません {alias.path}')
        return current.st_blocks * 512 if current.st_nlink == 1 else 0
    finally:
        temporary.unlink(missing_ok=True)


def consolidate(args):
    base = DESTINATIONS[args.mode]
    result = Counter()
    all_groups = inventory(args.mode, args.minimum)
    groups = sorted(((key, list(files.values())) for key, files in all_groups.items()
                     if len(by_inode(files.values())) > 1), key=lambda item: potential(item[1]), reverse=True)
    if args.groups is not None:
        groups = groups[:args.groups]
    if args.offset:
        groups = groups[args.offset:]
    print(args.mode, '照合候補', len(groups), '群', f'{sum(potential(files) for _, files in groups) / GIB:.2f} GiB',
          'パス', sum(len(files) for _, files in groups), flush=True)
    if not args.apply:
        return
    with args.ledger.open('x') as ledger:
        event(ledger, action='start', mode=args.mode, root=str(base), group_count=len(groups),
              started=datetime.now().astimezone().isoformat())
        for index, ((size, digest, _), files) in enumerate(groups, 1):
            partitions = defaultdict(list)
            for file in files:
                try:
                    partitions[metadata(file.path)].append(file)
                except OSError:
                    result['metadata_unreadable'] += 1
            for subgroup in partitions.values():
                inodes = by_inode(subgroup)
                if len(inodes) < 2:
                    continue
                valid = {}
                for inode, file in inodes.items():
                    try:
                        valid[inode] = (
                            state(file.path.lstat()) == state(file.info) and hash_file(file.path) == digest
                            and state(file.path.lstat()) == state(file.info)
                        )
                    except OSError:
                        valid[inode] = False
                if not all(valid.values()):
                    result['invalid_groups'] += 1
                    event(ledger, action='skip', reason='内容または属性に差', sha256=digest,
                          paths=[str(inodes[inode].path.relative_to(base)) for inode, ok in valid.items() if not ok])
                    continue
                canonical = max(subgroup, key=lambda file: (file.info.st_nlink, file.info.st_blocks))
                aliases = [file for file in subgroup if file.info.st_ino != canonical.info.st_ino]
                event(ledger, action='prepared', sha256=digest, bytes=size,
                      canonical=str(canonical.path.relative_to(base)), paths=[str(file.path.relative_to(base)) for file in aliases])
                reclaimed = 0
                for alias in aliases:
                    reclaimed += replace_with_link(alias, canonical)
                result['groups_verified'] += 1
                result['paths_linked'] += len(aliases)
                result['bytes_unlinked'] += reclaimed
                event(ledger, action='linked', sha256=digest, paths_linked=len(aliases), bytes_unlinked=reclaimed)
            if index % 50 == 0 or index == len(groups):
                print(args.mode, f'{index}/{len(groups)} 群', f'{result["bytes_unlinked"] / GIB:.2f} GiB', flush=True)
        event(ledger, action='complete', mode=args.mode, **result)
    print(args.mode, dict(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=DESTINATIONS)
    parser.add_argument('--minimum', type=int, default=1)
    parser.add_argument('--groups', type=int)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--ledger', type=Path)
    arguments = parser.parse_args()
    if arguments.apply and arguments.ledger is None:
        parser.error('--apply には --ledger が必要です')
    for volume in (Path('/Volumes/RTL9210B-CG'), Path('/Volumes/CT2000X8')):
        if not os.path.ismount(volume):
            raise SystemExit(f'外部媒体がマウントされていません {volume}')
    consolidate(arguments)
