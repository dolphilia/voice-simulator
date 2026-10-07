"""元の同じ上限を合算し、残る学習・レンダー・監査だけを使用する。"""
import json
import os
from campaign import ExtensionBudget, ROOT, RESULT, digest, save
REVISION = RESULT/'acoustic-revision'


class RevisionBudget(ExtensionBudget):
    def events(self):
        rows = super().events()
        for path in [RESULT/'post-analysis/ledger.jsonl', REVISION/'ledger.jsonl']:
            if path.exists():
                rows += [json.loads(s) for s in path.read_text().splitlines()]
        return rows

    def append(self,row):
        REVISION.mkdir(parents=True,exist_ok=True)
        with (REVISION/'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            f.flush();os.fsync(f.fileno())

    def reserve(self,kind,*args,**kwargs):
        if kind not in ('setup','train','render','audit'):
            raise ValueError('この改訂では追加の教師生成・AI評価を許可しません')
        repo = ROOT.parents[2]
        for directory in [RESULT,RESULT/'post-analysis']:
            seal = json.loads((directory/'artifact-seal.json').read_text())
            ledger = directory/'ledger.jsonl'
            if digest(ledger) != seal['files'][str(ledger.relative_to(repo))]:
                raise ValueError('先行台帳が変更されています')
        return super().reserve(kind,*args,**kwargs)
