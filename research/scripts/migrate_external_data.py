"""研究データを検証して外部へ移し、元のパスをファイル単位のリンクで保つ。

コード・文書・環境は移動しない。移動一覧と処理状態を内蔵のSQLiteへ保存し、
コピーのSHA-256確認前に元ファイルを置換しない。科学的な成果は書き換えない。
"""
import argparse
from collections import defaultdict
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parents[2]
CYCLE = REPO / 'research/experiments/autonomous-research-cycle'
RUN = REPO / 'research/storage-migrations/2026-10-08-v1'
MIGRATION_ID = 'repository-data-20261008-v1'
DATA = {'.wav', '.flac', '.mp3', '.ogg', '.npz', '.npy', '.parquet',
        '.tar', '.zip', '.gz', '.whl', '.frq'}
WEIGHTS = {'.pt', '.pth', '.onnx', '.safetensors', '.bin'}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save_json(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


def skipped_dir(name):
    return (name in {'.git', 'node_modules', '__pycache__', 'site-packages'}
            or name.startswith('.venv') or name.startswith('packages'))


def reason(path, size):
    if path.suffix.lower() in DATA:
        return '音声・解析配列・データセット・取得アーカイブ'
    if path.suffix.lower() in WEIGHTS and size >= 1_000_000:
        return '大容量の研究用モデル重み'
    if ('.cache' in path.parts and 'blobs' in path.parts
            and size >= 1_000_000):
        return '取得済みモデルのキャッシュ実体'
    return None


def connect():
    con = sqlite3.connect(RUN / 'manifest.sqlite')
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA synchronous=FULL')
    return con


def plan():
    if RUN.exists():
        raise FileExistsError('既存の移動記録があります。applyで保存済み計画を使ってください。')
    RUN.mkdir(parents=True)
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=REPO)
                  .decode().split('\0'))
    con = connect()
    con.execute('''CREATE TABLE files (
        name TEXT PRIMARY KEY, physical TEXT UNIQUE, size INTEGER,
        mtime INTEGER, device INTEGER, inode INTEGER, mode INTEGER,
        category TEXT, managed INTEGER, status TEXT DEFAULT 'planned',
        sha256 TEXT, target_mtime INTEGER)''')
    totals = defaultdict(lambda: {'bytes': 0, 'files': 0})
    rows = []
    seals = {}
    for directory, dirs, names in os.walk(REPO / 'research', followlinks=False):
        dirs[:] = [d for d in dirs if not skipped_dir(d)
                   and not (Path(directory) / d).is_symlink()
                   and (Path(directory) / d) != RUN.parent]
        for name in names:
            p = Path(directory) / name
            if p.is_symlink() or not p.is_file():
                continue
            relative = str(p.relative_to(REPO))
            if name == 'artifact-seal.json':
                seals[relative] = digest(p)
            st = p.stat()
            category = reason(p, st.st_size)
            if not category or relative in tracked:
                continue
            managed = CYCLE in p.parents
            if managed:
                physical = str(Path('arc-20261004-v1') / p.relative_to(CYCLE))
            else:
                physical = str(Path(MIGRATION_ID) / relative)
            rows.append((relative, physical, st.st_size, st.st_mtime_ns,
                         st.st_dev, st.st_ino, stat.S_IMODE(st.st_mode),
                         category, int(managed)))
            key = ('/'.join(p.relative_to(REPO).parts[:3])
                   if relative.startswith('research/experiments/')
                   else 'research/data')
            totals[key]['bytes'] += st.st_size
            totals[key]['files'] += 1
    # 台帳の対象を先に移し、その後参照資料等を移す。
    rows.sort(key=lambda r: (-r[8], -r[2], r[0]))
    con.executemany('INSERT INTO files '
                    '(name,physical,size,mtime,device,inode,mode,category,managed) '
                    'VALUES (?,?,?,?,?,?,?,?,?)', rows)
    con.commit()
    con.close()
    summary = dict(
        migration_id=MIGRATION_ID, created_epoch=time.time(),
        user_authorization='計画を継続する前に、コアなコードや文書は残し、容量の大きいものや外部に移動して問題ないものを選定して移動する。',
        files=len(rows), bytes=sum(r[2] for r in rows),
        managed_files=sum(r[8] for r in rows),
        managed_bytes=sum(r[2] for r in rows if r[8]),
        categories=dict(totals), sealed_documents=seals,
        script_sha256=digest(Path(__file__)),
        kept=['コード、文書、JSON・CSV・台帳・封印記録',
              '仮想環境、依存ライブラリ、node_modules',
              '小容量の最終共有モデルとhtsvoice',
              'Git追跡ファイル、既存の外部参照リンク'],
        research_generation_started=False)
    save_json(RUN / 'plan.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def unchanged(source, row):
    st = source.lstat()
    if (not stat.S_ISREG(st.st_mode) or
            (st.st_size, st.st_mtime_ns, st.st_dev, st.st_ino) !=
            (row['size'], row['mtime'], row['device'], row['inode'])):
        raise RuntimeError('移動元の変更を検出: ' + str(source))


def copy_verified(source, row, guard):
    """新しい実体を排他的に作成し、書込後の読み直しで内容を検証する。"""
    unchanged(source, row)
    with guard.parent_fd(row['physical']) as (parent, name):
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                      row['mode'], dir_fd=parent)
        source_fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        h = hashlib.sha256()
        with os.fdopen(out, 'wb') as target, os.fdopen(source_fd, 'rb') as original:
            for block in iter(lambda: original.read(4 * 1024 * 1024), b''):
                h.update(block)
                target.write(block)
            target.flush()
            os.fchmod(target.fileno(), row['mode'])
            os.fsync(target.fileno())
        physical = guard.root / row['physical']
        os.utime(name, ns=(row['mtime'], row['mtime']), dir_fd=parent,
                 follow_symlinks=False)
        os.fsync(parent)
    guard.check()
    unchanged(source, row)
    if physical.stat().st_size != row['size'] or digest(physical) != h.hexdigest():
        raise RuntimeError('外部コピーの検証不一致。元ファイルは保持: ' + str(source))
    return h.hexdigest(), physical.stat().st_mtime_ns


@contextmanager
def writable_parent(parent, audit=None):
    """自分が所有する読取専用フォルダだけ、一時的に書込可能にして戻す。"""
    st = parent.lstat()
    if not stat.S_ISDIR(st.st_mode):
        raise RuntimeError('移動元の親が通常のディレクトリではありません')
    mode = stat.S_IMODE(st.st_mode)
    changed = not (mode & stat.S_IWUSR)
    if changed and st.st_uid != os.getuid():
        raise PermissionError('自分が所有していない読取専用フォルダです')
    def record(status):
        if audit is not None:
            with audit.open('a', encoding='utf8') as f:
                f.write(json.dumps(dict(path=str(parent), original_mode=mode,
                                        status=status), ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
    if changed:
        record('before-temporary-write')
        os.chmod(parent, mode | stat.S_IWUSR, follow_symlinks=False)
    try:
        yield
    finally:
        if changed:
            os.chmod(parent, mode, follow_symlinks=False)
            record('restored')


def replace_with_link(source, target, row, sha, audit=None):
    """検証済みコピーだけを、同じディレクトリのリンクと原子的に置換する。"""
    unchanged(source, row)
    if target.is_symlink() or target.stat().st_size != row['size'] or digest(target) != sha:
        raise RuntimeError('検証後のコピー変更。元ファイルは保持: ' + str(source))
    temporary = source.with_name('.' + source.name + '.external-migration-link')
    with writable_parent(source.parent, audit):
        os.symlink(str(target), temporary)
        try:
            unchanged(source, row)
            os.replace(temporary, source)
            fd = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            if os.path.lexists(temporary):
                temporary.unlink()


def ledger_checkpoint(b, con, started):
    """位置とmtimeだけを追記更新し、過去の容量・回数・封印を維持する。"""
    state = json.loads(b.state_path.read_text())
    record = state['storage_maintenance'][MIGRATION_ID]
    known = record.get('managed_files_applied', 0)
    rows = list(con.execute("SELECT * FROM files WHERE managed=1 AND status='linked' ORDER BY name"))
    with b.index() as index:
        locations = {r[0]: r[1:] for r in index.execute('SELECT * FROM locations')}
        for row in rows:
            name = str((REPO / row['name']).relative_to(CYCLE))
            target = b.guard.root / row['physical']
            expected = (row['physical'], row['size'],
                        len(os.fsencode(str(target))), row['sha256'])
            if locations.get(name) == expected:
                continue
            index.execute('INSERT OR REPLACE INTO locations VALUES (?,?,?,?,?)',
                          (name, row['physical'], row['size'],
                           len(os.fsencode(str(target))), row['sha256']))
            index.execute('UPDATE files SET size=?,mtime=? WHERE name=?',
                          (row['size'], row['target_mtime'], name))
    # 既存論理容量は同じ。複製の書込と位置/index更新は累積費用に加算。
    total = sum(r['size'] for r in rows)
    state['write_bytes'] += total - record.get('managed_bytes_applied', 0)
    state['write_bytes'] += max(0, len(rows) - known) * 131072
    now = time.time()
    state['seconds'] += max(0, now - record['last_checkpoint_epoch'])
    record.update(managed_files_applied=len(rows), managed_bytes_applied=total,
                  last_checkpoint_epoch=now)
    b._write_state(state)


def apply():
    sys.path.insert(0, str(CYCLE))
    from storage_budget import StorageBudget
    b = StorageBudget()
    summary = json.loads((RUN / 'plan.json').read_text())
    current_script_hash = digest(Path(__file__))
    if summary['script_sha256'] != current_script_hash:
        amendment = json.loads((RUN / 'script-amendment-0001.json').read_text())
        if (amendment['original_script_sha256'] != summary['script_sha256'] or
                amendment['updated_script_sha256'] != current_script_hash):
            raise RuntimeError('記録した移動スクリプトから変更されています')
    con = connect()
    started = time.time()
    with b.locked():
        state = json.loads(b.state_path.read_text())
        if state['session'] is not None or state['jobs']:
            raise RuntimeError('研究セッション・ジョブが残っています')
        active = state.get('storage_maintenance', {}).get(MIGRATION_ID)
        if active and active['status'] == 'completed':
            raise RuntimeError('完了済み。verifyで検証してください')
        if not active:
            if b.inventory() != b.registered():
                raise RuntimeError('移動前の論理台帳が不一致')
            if shutil.disk_usage(b.guard.mount).free < summary['bytes'] + 2_000_000_000:
                raise RuntimeError('外部メディアの実空き容量不足')
            if state['write_bytes'] + summary['managed_bytes'] + summary['managed_files'] * 131072 >= state['limits']['write_bytes']:
                raise RuntimeError('包括累積書込予算不足')
            b._check(state, summary['managed_bytes'], tier='external')
            save_json(RUN / 'before.json', dict(
                internal_free=shutil.disk_usage(REPO).free,
                external_free=shutil.disk_usage(b.guard.mount).free,
                budget_state=state, existing_external_hashes=b.audit_data_hashes()))
            state.setdefault('storage_maintenance', {})[MIGRATION_ID] = dict(
                status='running', manifest=str((RUN / 'manifest.sqlite').relative_to(REPO)),
                plan_sha256=digest(RUN / 'plan.json'),
                reserved_external_bytes=summary['bytes'],
                managed_files_applied=0, managed_bytes_applied=0,
                user_authorization=summary['user_authorization'],
                last_checkpoint_epoch=started,
                scientific_counters_unchanged=True)
            b.event(state, dict(kind='authorized-storage-migration-start',
                                migration=MIGRATION_ID, planned_bytes=summary['bytes']))
            b._write_state(state)
        last = time.monotonic()
        rows = list(con.execute('SELECT * FROM files ORDER BY managed DESC,size DESC,name'))
        complete = 0
        size = 0
        for row in rows:
            source = REPO / row['name']
            target = b.guard.root / row['physical']
            if row['status'] == 'linked':
                if not source.is_symlink() or os.readlink(source) != str(target):
                    raise RuntimeError('既存移動リンクの変更')
            else:
                if row['status'] == 'planned':
                    unchanged(source, row)
                    con.execute("UPDATE files SET status='copying' WHERE name=?", (row['name'],))
                    con.commit()
                    sha, mtime = copy_verified(source, row, b.guard)
                    con.execute("UPDATE files SET status='copied',sha256=?,target_mtime=? WHERE name=?",
                                (sha, mtime, row['name']))
                    con.commit()
                    row = con.execute('SELECT * FROM files WHERE name=?', (row['name'],)).fetchone()
                elif row['status'] == 'copying':
                    # 中断したコピーが完全一致の場合だけ保存済み実体を再利用。
                    unchanged(source, row)
                    sha = digest(source)
                    if not target.exists() or target.is_symlink() or target.stat().st_size != row['size'] or digest(target) != sha:
                        raise RuntimeError('途中コピーは自動削除しません。元データを保持して停止: ' + row['name'])
                    con.execute("UPDATE files SET status='copied',sha256=?,target_mtime=? WHERE name=?",
                                (sha, target.stat().st_mtime_ns, row['name']))
                    con.commit()
                    row = con.execute('SELECT * FROM files WHERE name=?', (row['name'],)).fetchone()
                if source.is_symlink():
                    if os.readlink(source) != str(target) or digest(target) != row['sha256']:
                        raise RuntimeError('中断後のリンク検証に失敗')
                else:
                    replace_with_link(source, target, row, row['sha256'],
                                      RUN / 'directory-mode-adjustments.jsonl')
                con.execute("UPDATE files SET status='linked' WHERE name=?", (row['name'],))
                con.commit()
            complete += 1
            size += row['size']
            if time.monotonic() - last >= 15 or complete == len(rows):
                b.guard.check()
                ledger_checkpoint(b, con, started)
                print(json.dumps(dict(moved=complete, total=len(rows), bytes=size,
                                      elapsed_seconds=round(time.time()-started),
                                      last=row['name']), ensure_ascii=False), flush=True)
                last = time.monotonic()
        ledger_checkpoint(b, con, started)
        state = json.loads(b.state_path.read_text())
        state['storage_maintenance'][MIGRATION_ID]['status'] = 'copied-awaiting-final-audit'
        b._write_state(state)
    con.close()
    verify()


def verify():
    sys.path.insert(0, str(CYCLE))
    from storage_budget import StorageBudget
    b = StorageBudget()
    con = connect()
    summary = json.loads((RUN / 'plan.json').read_text())
    last = time.monotonic()
    rows = list(con.execute('SELECT * FROM files ORDER BY name'))
    for i, row in enumerate(rows, 1):
        p = REPO / row['name']
        target = b.guard.root / row['physical']
        if row['status'] != 'linked' or not p.is_symlink() or os.readlink(p) != str(target):
            raise RuntimeError('未移動・リンク不一致: ' + row['name'])
        if p.stat().st_size != row['size'] or digest(p) != row['sha256']:
            raise RuntimeError('移動後の内容不一致: ' + row['name'])
        if time.monotonic() - last >= 15:
            print(json.dumps(dict(audited=i, total=len(rows)), ensure_ascii=False), flush=True)
            last = time.monotonic()
    for name, sha in summary['sealed_documents'].items():
        if digest(REPO / name) != sha:
            raise RuntimeError('封印記録が変化: ' + name)
    with b.locked():
        actual = b.inventory()
        if actual != b.registered():
            raise RuntimeError('移動後の台帳不一致')
        state = json.loads(b.state_path.read_text())
        if sum(v[0] for v in actual.values()) != state['payload_bytes']:
            raise RuntimeError('移動後の論理容量不一致')
        b._check(state)
        verified = b.audit_data_hashes()
        before = json.loads((RUN / 'before.json').read_text())
        for key in ['counts', 'limits', 'campaigns', 'payload_bytes', 'authorization']:
            if state[key] != before['budget_state'][key]:
                raise RuntimeError('研究の既存条件・件数が変化: ' + key)
        state['storage_maintenance'][MIGRATION_ID].update(status='completed',
                                                        completed_epoch=time.time())
        record = state['storage_maintenance'][MIGRATION_ID]
        state['seconds'] += max(0, time.time() - record['last_checkpoint_epoch'])
        record['last_checkpoint_epoch'] = time.time()
        b.event(state, dict(kind='authorized-storage-migration-complete',
                            migration=MIGRATION_ID, files=len(rows), bytes=summary['bytes']))
        b._write_state(state)
    result = dict(migration_id=MIGRATION_ID, files=len(rows), bytes=summary['bytes'],
                  sha256_verified_files=len(rows), sealed_documents_unchanged=len(summary['sealed_documents']),
                  managed_external_hashes_verified=verified, logical_ledger_passed=True,
                  scientific_counters_unchanged=True, research_generation_started=False,
                  internal_free_before=before['internal_free'],
                  internal_free_after=shutil.disk_usage(REPO).free,
                  external_free_before=before['external_free'],
                  external_free_after=shutil.disk_usage(b.guard.mount).free,
                  categories=summary['categories'])
    save_json(RUN / 'result.json', result)
    con.close()
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'apply', 'verify'])
    arguments = parser.parse_args()
    globals()[arguments.action]()
