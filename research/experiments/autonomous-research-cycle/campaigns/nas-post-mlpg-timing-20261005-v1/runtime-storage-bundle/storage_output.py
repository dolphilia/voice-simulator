"""外部出力をマウント確認とディレクトリFDで固定する。合成計算には関与しない。"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
from storage_guard import VolumeGuard
CONFIG=json.loads((Path(__file__).parent/'storage-output-config.json').read_text())

@contextmanager
def open_output(path):
    target=Path(path).resolve()
    root=Path(CONFIG['data_root'])
    if root in target.parents:
        guard=object.__new__(VolumeGuard)
        guard.config=CONFIG
        guard.mount=Path(CONFIG['mount'])
        guard.root=root
        guard.device=CONFIG['device']
        with guard.parent_fd(str(target.relative_to(root))) as (parent,name):
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
            with os.fdopen(fd,'wb') as f:
                yield f
                f.flush();os.fsync(f.fileno())
            os.fsync(parent)
        guard.check()
    else:
        with target.open('xb') as f:
            yield f
            f.flush();os.fsync(f.fileno())
