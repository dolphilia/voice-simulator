"""追加承認枠の抜け道、再開、失敗時の計数を点検する。"""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'src'))
from cycle_campaign_v1 import CycleCampaign, LIMITS
from autonomous_speech_synthesis.io import read,write_once
from autonomous_speech_synthesis.runner import BudgetExhausted

class CycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.config=read(ROOT/'config/campaign-v1.json')
    def tearDown(self):self.temp.cleanup()
    def test_old_campaigns_cannot_be_reenrolled_and_three_new_slots(self):
        for i in range(6):write_once(self.root/f'results/old{i}/started.json',{'unix':0})
        for i in range(3):
            c=CycleCampaign(f'new{i}',self.config,self.root);c.close()
        with self.assertRaises(BudgetExhausted):CycleCampaign('new3',self.config,self.root)
        with self.assertRaises(ValueError):CycleCampaign('old0',self.config,self.root)
        c=CycleCampaign('new0',self.config,self.root);c.close()
    def test_failure_resume_and_identity_mismatch(self):
        self.config['budget']['max_p1_renders']=1
        c=CycleCampaign('failure',self.config,self.root)
        task={'id':'failure','phonemes':['a'],'prosody':{}}
        def fail():raise ValueError('故意の失敗')
        r=c.trial('first','dsp','P1',task,1,{},fail)
        self.assertEqual(r['status'],'unavailable');c.close()
        c=CycleCampaign('failure',self.config,self.root)
        self.assertEqual(c.trial('first','dsp','P1',task,1,{},fail),r)
        with self.assertRaises(BudgetExhausted):c.trial('second','dsp','P1',task,1,{},fail)
        c.close()
        changed=copy.deepcopy(self.config);changed['seed']+=1
        with self.assertRaises(FileExistsError):CycleCampaign('failure',changed,self.root)
        c=CycleCampaign('failure',self.config,self.root);c.close()
    def test_cycle_time_and_added_storage_do_not_credit_deletion(self):
        old=self.root/'old.bin';old.write_bytes(b'a'*100)
        c=CycleCampaign('limits',self.config,self.root)
        baseline=c.approval['unix']
        with patch('cycle_campaign_v1.time.time',return_value=baseline+86401):
            with self.assertRaises(BudgetExhausted):c.budget_check('P1','dsp')
        old.unlink();(self.root/'new.bin').write_bytes(b'b'*200)
        c.approval['baseline_inventory'].update({str(p.relative_to(self.root)):p.stat().st_size for p in self.root.rglob('*') if p.is_file() and p.name!='new.bin'})
        with patch.dict(LIMITS,{'max_additional_bytes':10_000_150}):
            with self.assertRaises(BudgetExhausted):c.check_cycle()
        c.close()

if __name__=='__main__':unittest.main()
