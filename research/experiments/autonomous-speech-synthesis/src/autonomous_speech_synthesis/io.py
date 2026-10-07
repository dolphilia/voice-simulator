"""内容ハッシュ、追記台帳、上書き防止。"""
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[2]


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_once(path, value):
    """中断した一時ファイルは成果とせず、完成した内容だけ公開する。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if read(path) != value:
            raise FileExistsError(f"既存IDの結果は上書きしません: {path}")
        return
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    with temporary.open("x") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(temporary, path)
    finally:
        temporary.unlink()


def append(path, value):
    with Path(path).open("a") as f:
        f.write(canonical(value) + "\n")
        f.flush()
        os.fsync(f.fileno())


def rows(path):
    if not Path(path).exists():
        return []
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def now():
    return datetime.now(timezone.utc).isoformat()


def code_manifest():
    paths = sorted((ROOT / "src").rglob("*.py")) + sorted((ROOT / "config").glob("*.json")) + [ROOT / "run.py"]
    result={str(p.relative_to(ROOT)): file_hash(p) for p in paths}
    legacy=ROOT.parent/"synthetic-vowel-baseline"
    for p in sorted((legacy/"src").rglob("*.py"))+sorted((legacy/"config").glob("*.json")):
        result["../synthetic-vowel-baseline/"+str(p.relative_to(legacy))]=file_hash(p)
    return result


def environment():
    import numpy
    import scipy
    return {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
            "numpy": numpy.__version__, "scipy": scipy.__version__}
