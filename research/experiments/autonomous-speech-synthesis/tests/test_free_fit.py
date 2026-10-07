"""条件別適合の範囲制約とP1予算の独立性を検査する。"""
import itertools
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from free_fit import FreeFitCampaign
from free_fit_bounds_v2 import voice_from_point
from autonomous_speech_synthesis.runner import BudgetExhausted
from autonomous_speech_synthesis.gestures import voice_config,validate_voice


class FreeFitTests(unittest.TestCase):
    def test_parameter_bounds_preserve_ordered_formants_and_valid_gains(self):
        base=voice_config()
        for vowel in 'aiueo':
            for point in itertools.product((0.,1.),repeat=6):
                voice=voice_from_point(base,vowel,point)
                validate_voice(voice)
                self.assertEqual(base['source'],voice['source'])
                self.assertEqual(base['formants_hz']['a'],voice_config()['formants_hz']['a'])

    def test_p1_budget_includes_failures_and_does_not_consume_p2(self):
        config=json.loads((ROOT/'config/campaign-v1.json').read_text());config['budget']['max_p1_renders']=2
        with tempfile.TemporaryDirectory() as tmp,patch('autonomous_speech_synthesis.runner.ROOT',Path(tmp)):
            c=FreeFitCampaign('p1-count',config)
            def fail():raise RuntimeError('計数用の失敗')
            try:
                c.trial('a','dsp','P1',{'id':'probe'},1,{},fail)
                c.trial('a','dsp','P1',{'id':'probe'},1,{},fail)
                c.trial('b','dsp','P1',{'id':'probe'},1,{},fail)
                with self.assertRaises(BudgetExhausted):c.trial('c','dsp','P1',{'id':'probe'},1,{},fail)
                started=[e for e in c.events if e['event']=='started']
                self.assertEqual(len(started),2)
                self.assertTrue(all(e['budget_key']=='max_p1_renders' for e in started))
                self.assertEqual(c.budget_check('P2','dsp'),'max_p2_per_backend')
            finally:c.close()


if __name__=='__main__':unittest.main()
