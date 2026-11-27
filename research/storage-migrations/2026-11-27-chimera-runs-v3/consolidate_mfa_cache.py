from collections import Counter, defaultdict
import json
from pathlib import Path
import stat
import sys

from consolidate import File, GIB, RUNS, WORK, event, hash_file, metadata, permissions, replace_with_link, state


def main():
    groups = defaultdict(list)
    for path in WORK.glob('tsp-phone-boundaries-*/tmp/mfa-*/extracted_models'):
        run = path.relative_to(WORK).parts[0]
        manifest = RUNS / run / 'manifest.json'
        if not manifest.is_file() or json.loads(manifest.read_bytes()).get('status') != 'pass':
            continue
        for model in path.rglob('*'):
            info = model.lstat()
            if not stat.S_ISREG(info.st_mode) or model.resolve(strict=True) != model:
                continue
            digest = hash_file(model)
            if state(model.lstat()) != state(info):
                raise ValueError(f'MFAモデルが変化しました {model}')
            key = info.st_size, digest, permissions(info), metadata(model)
            groups[key].append(File(model, info))
    result = Counter()
    with Path(sys.argv[1]).open('x') as ledger:
        event(ledger, action='start', root=str(WORK))
        for (size, digest, _, _), files in groups.items():
            if len({file.info.st_ino for file in files}) < 2:
                continue
            keep = max(files, key=lambda file: file.info.st_nlink)
            aliases = [file for file in files if file.info.st_ino != keep.info.st_ino]
            event(ledger, action='prepared', sha256=digest, bytes=size,
                  canonical=str(keep.path.relative_to(WORK)),
                  paths=[str(file.path.relative_to(WORK)) for file in aliases])
            assert hash_file(keep.path) == digest
            freed = 0
            for file in aliases:
                freed += replace_with_link(file, keep)
            result['bytes_unlinked'] += freed
            result['paths_linked'] += len(aliases)
            result['groups_verified'] += 1
            event(ledger, action='linked', sha256=digest, paths_linked=len(aliases), bytes_unlinked=freed)
        event(ledger, action='complete', **result)
    print(dict(result), f'{result["bytes_unlinked"] / GIB:.2f} GiB', flush=True)


if __name__ == '__main__':
    main()
