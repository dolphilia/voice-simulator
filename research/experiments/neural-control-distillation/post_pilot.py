"""同じcampaignの残枠で、封印後の診断を追記台帳へ記録する。"""
import json
import os
from budget import Budget,ROOT,RESULT,digest,save

POST=RESULT/'post-pilot'


class PostBudget(Budget):
    def events(self):
        prior=super().events()
        p=POST/'ledger.jsonl'
        return prior+([json.loads(s) for s in p.read_text().splitlines()] if p.exists() else [])

    def append(self,row):
        POST.mkdir(exist_ok=True)
        with (POST/'ledger.jsonl').open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n');f.flush();os.fsync(f.fileno())

    def reserve(self,*args,**kwargs):
        # 過去台帳を変更せず、既存予約と追加予約を合算して同じ上限を検査する。
        seal=json.loads((RESULT/'artifact-seal.json').read_text())
        repo=ROOT.parents[2]
        name=str((RESULT/'ledger.jsonl').relative_to(repo))
        if digest(RESULT/'ledger.jsonl')!=seal['files'][name]:raise ValueError('封印済み台帳が変更されています')
        return super().reserve(*args,**kwargs)
