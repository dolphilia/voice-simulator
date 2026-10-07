"""全旧領域の走査、新実験だけの走査、差分台帳案の費用と盲点を比較する。"""
import json
from pathlib import Path
import tempfile
import time
from budget import Budget,ROOT,RESULT,save


def inventory(root):
    start=time.monotonic()
    paths=[p for p in root.rglob('*') if p.is_file() and not p.is_symlink()]
    return {'files':len(paths),'bytes':sum(p.stat().st_size for p in paths),
            'seconds':time.monotonic()-start}


def main():
    budget=Budget()
    with budget.job('audit','実験管理費と外部書込の検査',1_000_000):
        old=inventory(ROOT.parent/'autonomous-speech-synthesis')
        fresh=inventory(ROOT)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'managed').write_bytes(b'x'*40)
            accounted=40;limit=100;reservation=30
            # 外部書込は差分台帳には現れない。定期照合だけでは次の予約前に検出できない。
            (root/'external').write_bytes(b'x'*40)
            incremental_allows=accounted+reservation<=limit
            actual=sum(p.stat().st_size for p in root.iterdir())
            full_scan_allows=actual+reservation<=limit
        save(RESULT/'management-benchmark.json',{'legacy_whole_tree':old,'new_experiment_tree':fresh,
            'incremental_prototype':{'accounted_bytes':accounted,'actual_bytes':actual,'reservation':reservation,
                                     'limit':limit,'incorrectly_allows':incremental_allows and not full_scan_allows},
            'decision':'新実験の管理対象全体を予約前に照合する現方式を維持。旧領域は毎回走査しない',
            'reason':'差分計数だけでは協調しない外部書込を予約前に検出できない。現方式の費用が小さく、安全条件を満たす',
            'scope':'1回の実測であり普遍的な速度比ではない。新実験の依存/重みも容量に含める'})
        print(json.dumps({'legacy_seconds':old['seconds'],'new_seconds':fresh['seconds'],
                          'incremental_external_write_gap':incremental_allows and not full_scan_allows}))


if __name__=='__main__':main()
