"""封印済みの成果物を、生成・AI評価なしで点検する。"""
import json
from pathlib import Path
from campaign import ROOT, PRIOR, RESULT, digest


def main():
    seals = [RESULT/'artifact-seal.json', PRIOR/'artifact-seal.json', PRIOR/'post-pilot/artifact-seal.json']
    for path in seals:
        seal = json.loads(path.read_text())
        changed = [p for p, sha in seal['files'].items() if digest(Path(seal['path_base'])/p) != sha]
        if changed:
            raise ValueError('封印後の変更: '+repr(changed))
        print(path.parent.name, len(seal['files']), 'ハッシュ一致')
    events = [json.loads(line) for line in (RESULT/'ledger.jsonl').read_text().splitlines()]
    starts = [e for e in events if e['event'] == 'start']
    finishes = [e for e in events if e['event'] == 'finish']
    if len(starts) != len(finishes) or {e['id'] for e in starts} != {e['id'] for e in finishes}:
        raise ValueError('台帳に未終了または重複があります')
    counts = {k: sum(e.get('count', 1) for e in starts if e['kind'] == k) for k in ['teacher', 'render', 'ai']}
    if counts != {'teacher': 24, 'render': 228, 'ai': 300}:
        raise ValueError('確定使用量の変更')
    if json.loads((RESULT/'requirements-audit.json').read_text())['all_requirements_met']:
        raise ValueError('未達の品質条件を完了へ変更しません')
    print('使用量一致、未終了処理なし、品質未達の記録を確認')


if __name__ == '__main__':
    main()
