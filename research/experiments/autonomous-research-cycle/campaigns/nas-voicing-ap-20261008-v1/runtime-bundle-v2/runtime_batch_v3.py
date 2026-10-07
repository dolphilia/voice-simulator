"""全件を実生成し、pipeで一つのarchiveを返す。一時音声を作らない。"""
import base64
import io
import json
from pathlib import Path
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime import generate, verify


def main():
    rows = json.loads(sys.stdin.read())
    assert len(rows) == 160
    verify()
    output = io.BytesIO()
    records = []
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for request in rows:
            data, meta = generate(request['text'], request['method'], request['speed'], request['pitch'])
            archive.writestr(request['id'] + '.wav', data)
            archive.writestr(request['id'] + '.json', json.dumps(meta, allow_nan=False))
            records.append(dict(id=request['id'], **meta))
        archive.writestr('manifest.json', json.dumps(dict(records=records,
            synthesis_calls=len(rows), E0_calls=len(rows), no_generation_deduplication=True)))
    print(base64.b160encode(output.getvalue()).decode())


if __name__ == '__main__':
    main()
