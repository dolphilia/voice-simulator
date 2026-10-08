"""初回時計と既消費を維持する後続入口の否定検査。品質の証拠ではない。"""
import copy,unittest
from steady_speech_budget_20261009 import account_steady,check_steady,prepare_transition
def old():
 return dict(seconds=147000.,write_bytes=67000000000,counts=dict(render=83849,dsp=73790,train=16,inverse=102),jobs={},campaigns={},long_horizon=dict(scientific_completed=73,last_review=dict(scientific_completed=72,seconds=146000.)),continuation_checkpoint=dict(user_pause_requested=False),research_execution_plan=dict(status='active',last_accounted_seconds=147000.,segment=dict(stage='D',foundation_only=True),first_stage=dict(maximum_seconds=86400,used_seconds=22345.,stages=[dict(id='A',maximum_seconds=7200,used_seconds=797.,status='completed'),dict(id='B',maximum_seconds=21600,used_seconds=591.,status='partial_switched'),dict(id='C',maximum_seconds=36000,used_seconds=13611.,status='partial_switched'),dict(id='D',maximum_seconds=21600,used_seconds=7346.,status='running')]),foundation_only=dict(maximum_seconds=43200,used_seconds=1388.)))
def fixture():return prepare_transition(old(),'D全体不採択を保持','guard.json','a'*64)
class SteadyTests(unittest.TestCase):
 def test_first_clocks_not_reset_or_recharged(self):
  s=fixture();before=copy.deepcopy(s['research_execution_plan']['first_stage']);s['seconds']+=90;account_steady(s);account_steady(s)
  self.assertEqual(s['research_execution_plan']['first_stage'],before);self.assertEqual(s['research_execution_plan']['steady_phase']['used_seconds'],90)
 def test_old_cap_change_denied(self):
  s=fixture();s['research_execution_plan']['first_stage']['stages'][2]['maximum_seconds']+=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_old_clock_decrement_denied(self):
  s=fixture();s['research_execution_plan']['first_stage']['used_seconds']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_recent_render_refund_denied(self):
  s=fixture();s['counts']['render']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_science_and_review_not_reset(self):
  s=fixture();s['long_horizon']['scientific_completed']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
  s=fixture();s['long_horizon']['last_review']['scientific_completed']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_recent_write_refund_denied(self):
  s=fixture();s['write_bytes']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_negative_clock_denied(self):
  s=fixture();s['seconds']-=1
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_stop_denied(self):
  s=fixture();s['continuation_checkpoint']['user_pause_requested']=True
  with self.assertRaises(RuntimeError):check_steady(s)
 def test_pending_reservations_and_closing_preserved(self):
  s=fixture();s['jobs']['x']=dict(status='running',expected_seconds=4000);s['seconds']=649200.
  with self.assertRaises(RuntimeError):check_steady(s,1)
 def test_foundation_carries_old_clock(self):
  s=fixture();s['research_execution_plan']['foundation_only']['used_seconds']=43190.;s['seconds']+=5
  self.assertEqual(account_steady(s)['foundation_only']['used_seconds'],43195.)
  with self.assertRaises(RuntimeError):check_steady(s,6)
 def test_audio_does_not_charge_foundation(self):
  s=fixture();s['research_execution_plan']['segment']['foundation_only']=False;s['seconds']+=20
  self.assertEqual(account_steady(s)['foundation_only']['used_seconds'],1388.)
 def test_open_work_blocks_transition(self):
  s=old();s['jobs']['x']={}
  with self.assertRaises(RuntimeError):prepare_transition(s,'x','g','h')
  s=old();s['campaigns']['x']=dict(closed=False)
  with self.assertRaises(RuntimeError):prepare_transition(s,'x','g','h')
 def test_repeated_transition_denied(self):
  s=fixture()
  with self.assertRaises(RuntimeError):prepare_transition(s,'x','g','h')
 def test_running_first_stage_denied(self):
  s=old();s['research_execution_plan']['first_stage']['stages'][1]['status']='running'
  with self.assertRaises(RuntimeError):prepare_transition(s,'x','g','h')
if __name__=='__main__':unittest.main()
