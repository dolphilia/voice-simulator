"""音声品質の証明ではなく、包括予算の誤使用を実際に拒否する検査。"""
import tempfile
from pathlib import Path
from budget import Budget,LIMITS,read
import json


def tests():
    with tempfile.TemporaryDirectory(prefix='arc-budget-',dir='/private/tmp') as directory:
        root=Path(directory);limits={**LIMITS,'experiment_bytes':2_000_000,'bytes':3_000_000,'render':2}
        b=Budget(root,limits);b.initialize({'fixture':True});b.resume()
        local={'seconds':3600,'bytes':1_000_000,'render':1,'audit':10}
        b.start_campaign('a','campaigns/a',local,'fixture')
        with b.job('a','render','一回を先に予約',reserve_bytes=20) as j:
            b.write(root/'campaigns/a/out',b'abc',j)
        assert b.snapshot()['counts']['render']==1
        try:b.reserve('a','render','ローカル超過')
        except RuntimeError:pass
        else:raise AssertionError('ローカル回数超過')
        b.start_campaign('b','campaigns/b',local,'fixture')
        try:
            with b.job('b','render','失敗も計数',reserve_bytes=2) as j:
                b.write(root/'campaigns/b/out',b'abc',j)
        except RuntimeError:pass
        else:raise AssertionError('符号化後容量超過')
        assert not (root/'campaigns/b/out').exists()
        s=b.snapshot();assert s['counts']['render']==2
        events=[json.loads(x) for x in (b.control/'jobs.jsonl').read_text().splitlines()]
        assert [e['status'] for e in events if e['event']=='finish']==['completed','failed']
        assert not s['jobs']
        b.start_campaign('c','campaigns/c',local,'fixture')
        try:b.reserve('c','render','包括超過')
        except RuntimeError:pass
        else:raise AssertionError('包括回数超過')
        try:b.initialize({})
        except FileExistsError:pass
        else:raise AssertionError('再初期化')
        with b.job('a','audit','外部予約',reserve_bytes=10) as j:
            with b.external_output(root/'campaigns/a/external',3,j):
                (root/'campaigns/a/external').write_bytes(b'abc')
        b.reconcile()
        try:b.write(root/'campaigns/a/out',b'replace')
        except FileExistsError:pass
        else:raise AssertionError('成果上書き')
        (root/'unexpected').write_bytes(b'x')
        try:b.reconcile()
        except RuntimeError:pass
        else:raise AssertionError('外部変更')
        (root/'unexpected').unlink()
        b.close_campaign('a')
        try:b.reserve('a','audit','終了後処理')
        except RuntimeError:pass
        else:raise AssertionError('終了campaign処理')
        b.suspend();assert b.snapshot()['session'] is None
        b.resume();b.reconcile();b.suspend()
    return {'local_and_global_attempt_caps':True,'failed_attempts_charged':True,
            'encoded_write_reservation':True,'external_write_reservation':True,
            'unregistered_changes_rejected':True,'restart_does_not_reset':True,
            'output_overwrite_and_closed_campaign_rejected':True,
            'session_suspend_resume':True,'quality_evidence':False}


if __name__=='__main__':print(tests())
