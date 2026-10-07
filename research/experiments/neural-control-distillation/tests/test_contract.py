"""予算漏れと根拠不足の品質昇格を防ぐ異常系を検査する。"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from budget import Budget
from quality_gate import decide


class BudgetTests(unittest.TestCase):
    def test_two_pass_render_is_reserved_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = Budget(root, root / 'results')
            contract = budget.initialize()
            contract['limits']['render'] = 3
            (budget.result / 'contract.json').write_text(json.dumps(contract))
            ticket = budget.reserve('render', '二段生成', count=2)
            budget.finish(ticket, 'failed')
            with self.assertRaises(RuntimeError):
                budget.reserve('render', '残り一回では二段生成不可', count=2)
            ticket = budget.reserve('render', '残り一回', count=1)
            budget.finish(ticket, 'completed')
            with self.assertRaises(ValueError):
                budget.reserve('render', '不正な計数', count=0)

    def test_failed_attempt_consumes_limit_and_pending_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = Budget(root, root / 'results')
            contract = budget.initialize()
            contract['limits']['teacher'] = 1
            (budget.result / 'contract.json').write_text(json.dumps(contract))
            ticket = budget.reserve('teacher', '失敗を試す')
            with self.assertRaises(RuntimeError):
                budget.reserve('render', '未終了との競合')
            budget.finish(ticket, 'failed')
            with self.assertRaises(RuntimeError):
                budget.reserve('teacher', '再試行も上限内')
            with self.assertRaises(RuntimeError):
                budget.finish(ticket, 'completed')

    def test_external_file_and_time_are_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = Budget(root, root / 'results')
            contract = budget.initialize()
            contract['limits']['bytes'] = 100_000
            (budget.result / 'contract.json').write_text(json.dumps(contract))
            (root / 'unexpected.bin').write_bytes(b'x' * 50_000)
            with self.assertRaises(RuntimeError):
                budget.reserve('render', '外部書込を検出')
            contract['limits']['bytes'] = 1_000_000
            contract['started_epoch'] = 0
            (budget.result / 'contract.json').write_text(json.dumps(contract))
            with self.assertRaises(RuntimeError):
                budget.reserve('render', '時間切れ')


class GateTests(unittest.TestCase):
    def fixture(self):
        # これは分岐を検査する人工fixtureであり、実音声の認定ではない。
        return {'engineering_pass': True, 'runtime_non_neural_verified': True,
                'confirmation': {'frozen_before_selection': True, 'independent': True,
                                 'reused_for_tuning': False, 'source_manifest_sha256': 'fixture'},
                'metrics': {k: {'qualification': {'status': 'qualified',
                              'target_domain': 'japanese-non-neural-speech', 'evidence_sha256': 'fixture'},
                           'loss_delta_ci': [-.2, -.1], 'noninferiority_margin': 0,
                           'multiplicity_controlled': True, 'missing_count': 0,
                           'protection_pass': True} for k in ('content', 'prosody', 'perception')}}

    def test_positive_path_and_each_missing_metric(self):
        self.assertEqual(decide(self.fixture())['state'], 'autonomously-validated')
        for key in ('content', 'prosody', 'perception'):
            x = self.fixture()
            del x['metrics'][key]
            self.assertEqual(decide(x)['state'], 'inconclusive')

    def test_bad_scope_leakage_and_worse_audio(self):
        x = self.fixture()
        x['metrics']['perception']['qualification']['target_domain'] = 'enhanced-speech'
        self.assertEqual(decide(x)['state'], 'inconclusive')
        x = self.fixture()
        x['confirmation']['reused_for_tuning'] = True
        self.assertEqual(decide(x)['state'], 'inconclusive')
        x = self.fixture()
        x['metrics']['content']['loss_delta_ci'] = [-.1, .1]
        self.assertEqual(decide(x)['state'], 'rejected')
        x['metrics']['content']['loss_delta_ci'] = [float('nan'), 0]
        self.assertEqual(decide(x)['state'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
