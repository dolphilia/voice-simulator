"""独立実験の入口。未実装の操作を成功と扱わない。"""
import argparse
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))


def main():
    parser = argparse.ArgumentParser(description='独立音声合成の固定仕様実験')
    parser.add_argument('command',choices=['test','qualify','status','prepare-data','fit-e0','evaluate-e0','prepare-p1'])
    args = parser.parse_args()
    if args.command == 'test':
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    if args.command == 'qualify':
        from independent_voice_synthesis.qualification import qualify
        qualify(ROOT)
    elif args.command == 'prepare-p1':
        suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        if not unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful():
            return 1
        from independent_voice_synthesis.reporting import prepare_p1
        print(json.dumps(prepare_p1(ROOT),ensure_ascii=False,indent=2))
    elif args.command in ('prepare-data','fit-e0','evaluate-e0'):
        p = ROOT/'results/e0/qualification/summary.json'
        if not p.exists() or json.loads(p.read_text())['status'] != 'qualified':
            print('前提不成立: 点検を通過していないため、測定取得・適合・判定は実行しません。',file=sys.stderr)
            return 2
        print('未実装: 点検通過時の測定経路。成功として扱いません。',file=sys.stderr)
        return 2
    else:
        from independent_voice_synthesis.reporting import status
        print(json.dumps(status(ROOT),ensure_ascii=False,indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
