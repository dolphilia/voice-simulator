"""時計の減算、停止、二重加算、予約超過を否定する検査。"""
import unittest
from research_plan_budget_20261009 import account_plan,check_plan

def fixture():
    return dict(seconds=1000.,jobs={},continuation_checkpoint=dict(user_pause_requested=False),research_execution_plan=dict(status='active',last_accounted_seconds=1000.,segment=dict(stage='A',foundation_only=True),first_stage=dict(maximum_seconds=86400,used_seconds=0.,stages=[dict(id='A',maximum_seconds=7200,used_seconds=0.),dict(id='B',maximum_seconds=21600,used_seconds=0.)]),foundation_only=dict(maximum_seconds=43200,used_seconds=0.)))
class ClockTests(unittest.TestCase):
    def test_time_not_double_charged(self):
        s=fixture();s['seconds']+=75;p=account_plan(s);account_plan(s);self.assertEqual(p['first_stage']['used_seconds'],75);self.assertEqual(p['foundation_only']['used_seconds'],75)
    def test_manual_fee_charged(self):
        s=fixture();s['seconds']+=180;self.assertEqual(check_plan(s)['first_stage']['stages'][0]['used_seconds'],180)
    def test_suspended_no_added_clock(self):
        s=fixture();s['session']=None;account_plan(s);self.assertEqual(s['research_execution_plan']['first_stage']['used_seconds'],0)
    def test_decrement_denied(self):
        s=fixture();s['seconds']=999
        with self.assertRaises(RuntimeError):account_plan(s)
    def test_pending_job_reserved(self):
        s=fixture();s['jobs']['x']=dict(status='running',expected_seconds=4000)
        with self.assertRaises(RuntimeError):check_plan(s,3201)
    def test_total_limit(self):
        s=fixture();s['research_execution_plan']['first_stage']['used_seconds']=86399
        with self.assertRaises(RuntimeError):check_plan(s,2)
    def test_foundation_continues_after_stage(self):
        s=fixture();p=s['research_execution_plan'];p['foundation_only']['used_seconds']=43190;p['segment']['stage']='B';s['seconds']+=5;self.assertEqual(account_plan(s)['foundation_only']['used_seconds'],43195)
        with self.assertRaises(RuntimeError):check_plan(s,6)
    def test_audio_does_not_charge_foundation(self):
        s=fixture();p=s['research_execution_plan'];p['segment']['foundation_only']=False;s['seconds']+=10;self.assertEqual(account_plan(s)['foundation_only']['used_seconds'],0);self.assertEqual(p['first_stage']['used_seconds'],10)
    def test_stop_and_unresumed_denied(self):
        s=fixture();s['continuation_checkpoint']['user_pause_requested']=True
        with self.assertRaises(RuntimeError):check_plan(s)
        s=fixture();s['research_execution_plan']['status']='adopted_pending_user_resume'
        with self.assertRaises(RuntimeError):account_plan(s)
if __name__=='__main__':unittest.main()
