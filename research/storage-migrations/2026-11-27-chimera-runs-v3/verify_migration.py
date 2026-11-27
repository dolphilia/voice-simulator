"""移行台帳から既存パスの共有状態と読込結果を再確認する。"""

from collections import Counter
from datetime import datetime
from pathlib import Path
import json
import subprocess

from consolidate import ARCHIVE, ROOT, RUNS, WORK, hash_file


MIGRATION = Path(__file__).resolve().parent
GROUPS = {'local': RUNS, 'source': RUNS, 'work': WORK, 'archive': ARCHIVE, 'mfa-cache': WORK}
BEFORE_KIB = {
    'internal_chimera': 52520220,
    'internal_runs': 52191324,
    'work_project': 123363544,
    'work_runs': 89228220,
    'archive': 29261536,
}


def load_ledger(name):
    file = MIGRATION / f'{name}.jsonl'
    packed = file.with_suffix('.jsonl.zst')
    if packed.is_file():
        raw = subprocess.check_output(['zstd', '-qdc', str(packed)])
        if file.is_file() and raw != file.read_bytes():
            raise ValueError(f'圧縮台帳が元の内容と一致しません {file}')
        file = packed
    else:
        raw = file.read_bytes()
    entries = [json.loads(line) for line in raw.splitlines()]
    if entries[-1]['action'] != 'complete':
        raise ValueError(f'台帳に終了記録がありません {file}')
    return entries, {'file': file.name, 'sha256': hash_file(file), 'result': entries[-1]}


def verify_hash(path, digest, size):
    if path.stat().st_size != size or hash_file(path) != digest:
        raise ValueError(f'現在のファイルが台帳と一致しません {path}')


def verify_links(log, directory):
    prepared = [item for item in log if item['action'] == 'prepared']
    count = 0
    for row in prepared:
        canonical = directory / row['canonical']
        info = canonical.stat()
        for relative in row['paths']:
            alias = (directory / relative).stat()
            if (info.st_dev, info.st_ino, info.st_size) != (alias.st_dev, alias.st_ino, alias.st_size):
                raise ValueError(f'共有実体が一致しません {directory / relative}')
            count += 1
    samples = sorted(prepared, key=lambda row: row['bytes'], reverse=True)[:3]
    for row in samples:
        verify_hash(directory / row['canonical'], row['sha256'], row['bytes'])
    return {'verified_paths': count, 'rehashed_objects': len(samples)}


def verify_archive_moves(log):
    prepared = [item for item in log if item['action'] == 'prepared']
    count = 0
    for row in prepared:
        target = Path(row['target'])
        if target.stat().st_size != row['bytes']:
            raise ValueError(f'保存先のサイズが一致しません {target}')
        for name in row['paths']:
            path = ROOT / name
            if not path.is_symlink() or path.resolve(strict=True) != target:
                raise ValueError(f'移行後のリンクを参照できません {path}')
            count += 1
    samples = sorted(prepared, key=lambda row: row['bytes'], reverse=True)[:5]
    for row in samples:
        verify_hash(ROOT / row['paths'][0], row['sha256'], row['bytes'])
    return {'verified_paths': count, 'rehashed_objects': len(samples)}


def verify_compression(log):
    stored = {item['sha256'] for item in log if item['action'] == 'compressed'}
    groups = [item for item in log if item['action'] == 'prepared' and item['sha256'] in stored]
    count = 0
    for row in groups:
        paths = [ARCHIVE / name for name in row['paths']]
        states = [path.stat() for path in paths]
        if not all(info.st_flags & 0x20 and info.st_size == row['bytes'] and info.st_ino == states[0].st_ino
                   for info in states):
            raise ValueError(f'透過圧縮の実体が一致しません {paths[0]}')
        count += len(paths)
    samples = sorted(groups, key=lambda row: row['bytes'], reverse=True)[:5]
    for row in samples:
        verify_hash(ARCHIVE / row['paths'][0], row['sha256'], row['bytes'])
    return {'verified_paths': count, 'rehashed_objects': len(samples)}


def du_kib(path):
    return int(subprocess.check_output(['/usr/bin/du', '-x', '-k', '-s', str(path)]).split()[0])


def run_check(run_id):
    run = RUNS / run_id
    manifest = json.loads((run / 'manifest.json').read_bytes())
    summary = json.loads((run / 'summary.json').read_bytes())
    checks = Counter(status is True for status in summary['checks'].values())
    if manifest['status'] != 'pass' or checks[False]:
        raise ValueError(f'再実行の判定が不一致です {run}')
    return {'run_id': run_id, 'checks_passed': checks[True], 'manifest_sha256': hash_file(run / 'manifest.json')}


def main():
    records = {}
    for name, base in GROUPS.items():
        log, record = load_ledger(name)
        records[name] = {**record, **verify_links(log, base)}
    moves, record = load_ledger('old-csv')
    records['old-csv'] = {**record, **verify_archive_moves(moves)}
    packed, record = load_ledger('transparent-compression')
    records['transparent-compression'] = {**record, **verify_compression(packed)}
    checks = [run_check(run) for run in (
        'storage-v3-tube-20261127-a', 'storage-v3-tube-20261127-repeat',
        'storage-v3-tsp-listening-07-20261127', 'storage-v3-plan-audit-20261127',
    )]
    measurements = {
        'internal_chimera': RUNS.parent,
        'internal_runs': RUNS,
        'work_project': WORK.parents[1],
        'work_runs': WORK,
        'archive': ARCHIVE,
    }
    result = {
        'recorded_at': datetime.now().astimezone().isoformat(),
        'du_allocated_kib_before': BEFORE_KIB,
        'du_allocated_kib_after': {label: du_kib(path) for label, path in measurements.items()},
        'ledgers': records,
        'regression_checks': checks,
    }
    with (MIGRATION / 'verification.json').open('x') as output:
        json.dump(result, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
