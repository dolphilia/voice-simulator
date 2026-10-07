"""追加前段・調音制御・厳格予算の意味的な回帰検査。"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from campaign_v2 import BoundedCampaign,BudgetExhausted
from japanese_frontend import from_labels
from vtl_japanese import timed_segments,patch_taps


class JapaneseTests(unittest.TestCase):
    def test_mora_duration_not_proportional_to_consonant_count(self):
        a={'phonemes':['a','k','a','ky','a'],'phrases':[{'moras':[{'phones':['a'],'high':False},{'phones':['k','a'],'high':True},{'phones':['ky','a'],'high':True}]}]}
        seg,pitch,times=timed_segments(a,.2)
        self.assertAlmostEqual(sum(d for _,d in seg),.75)
        self.assertAlmostEqual(times[0]['end']-times[0]['start'],.2)
        self.assertAlmostEqual(times[2]['end']-times[1]['start'],.2)
        self.assertAlmostEqual(times[-1]['end']-times[3]['start'],.2)
        self.assertAlmostEqual(sum(d for d,_ in pitch),.75)

    def test_geminate_after_pause_and_palatalized_mora(self):
        a={'phonemes':['ky','o','pau','Q','t','e'],'phrases':[{'moras':[{'phones':['ky','o'],'high':True}]},{'pause':True},{'moras':[{'phones':['Q'],'high':False},{'phones':['t','e'],'high':False}]}]}
        seg,_,times=timed_segments(a)
        q=next(t for t in times if t['phone']=='Q')
        self.assertAlmostEqual(q['end']-q['start'],.2)
        self.assertIn(('t',.2),seg)

    def test_dictionary_accent_phrase_structure(self):
        d=json.loads((ROOT/'results/frontend-v2/analysis.json').read_text())['records'][0]
        p=from_labels(d['full_context_labels'])
        self.assertEqual([(r['mora_count'],r['accent_nucleus']) for r in p],[(5,2),(3,1),(4,3),(3,3)])
        self.assertEqual([m['high'] for m in p[0]['moras']],[False,True,False,False,False])
        self.assertEqual([m['high'] for m in p[1]['moras']],[True,False,False])
        with self.assertRaises(ValueError):from_labels(['xx^xx-a+xx=xx/A:xx/F:xx'])

    def test_tap_preserves_timeline_and_other_gestures(self):
        root=ET.fromstring('<gestural_score><gesture_sequence type="tongue-tip-gestures"><gesture value="s" duration_s=".1"/><gesture value="tt-alveolar-lateral" duration_s=".09"/><gesture value="s" duration_s=".2"/></gesture_sequence></gestural_score>')
        self.assertEqual(patch_taps(root),1)
        seq=list(root[0]);self.assertAlmostEqual(sum(float(g.get('duration_s')) for g in seq),.39)
        closure=[g for g in seq if g.get('value')=='tt-alveolar-closure'][0]
        self.assertAlmostEqual(float(closure.get('duration_s')),.028)
        self.assertEqual([g.get('value') for g in seq if g.get('value')=='s'],['s','s'])


class BudgetTests(unittest.TestCase):
    def config(self):
        config=json.loads((ROOT/'config/campaign-v1.json').read_text());config['max_p34_tasks']=1;return config

    def test_task_limit_persists_after_failure_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp,patch('autonomous_speech_synthesis.runner.ROOT',Path(tmp)):
            c=BoundedCampaign('bounded',self.config())
            task={'id':'first','stage':'P4'}
            def fail():raise RuntimeError('失敗を消費に含める')
            c.trial('x','vtl','P4',task,1,{},fail);c.close()
            c=BoundedCampaign('bounded',self.config())
            try:
                with self.assertRaises(BudgetExhausted):c.trial('x','vtl','P4',{'id':'second'},1,{},fail)
                self.assertEqual(len(c.results()),1)
                with self.assertRaises(BudgetExhausted):c.preflight_tasks([task,{'id':'second','stage':'P4'}])
            finally:c.close()

    def test_failed_initialization_closes_lock(self):
        with tempfile.TemporaryDirectory() as tmp,patch('autonomous_speech_synthesis.runner.ROOT',Path(tmp)):
            config=self.config();c=BoundedCampaign('locked',config);c.close();config=copy.deepcopy(config);config['seed']+=1
            obj=BoundedCampaign.__new__(BoundedCampaign)
            with self.assertRaises(FileExistsError):obj.__init__('locked',config)
            self.assertTrue(obj.lock.closed)
            c=BoundedCampaign('locked',self.config());c.close()


if __name__=='__main__':unittest.main()
