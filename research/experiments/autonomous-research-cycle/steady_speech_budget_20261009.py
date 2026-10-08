"""初回A〜Dを凍結し、同じ長期予算で後続の音声改善を計数する別版。"""
import copy,hashlib
from budget import ROOT,read,digest,encode
from long_horizon_budget import LongHorizonBudget,TOTALS,CLOSING_SECONDS
REPO=ROOT.parents[2]
def first_hash(p):return hashlib.sha256(encode(p['first_stage'])).hexdigest()
def account_steady(s):
 p=s['research_execution_plan'];v=p.get('steady_phase')
 if p['status']!='active' or not v or p['segment']['stage']!='steady':raise RuntimeError('初回工程の終了後入口ではない')
 if first_hash(p)!=v['first_stage_sha256']:raise RuntimeError('初回工程の凍結時計/上限/状態の変更禁止')
 if any(x['status'] not in ['completed','partial_switched'] for x in p['first_stage']['stages']):raise RuntimeError('初回工程が未終了')
 if s['long_horizon']['scientific_completed']<v['started_scientific_completed'] or s['long_horizon']['last_review']['scientific_completed']<v['started_review_checkpoint']['scientific_completed'] or s['long_horizon']['last_review']['seconds']<v['started_review_checkpoint']['seconds']:raise RuntimeError('科学/既定レビュー時計の巻戻し禁止')
 if s['seconds']<v['started_cumulative_seconds'] or any(s['counts'].get(k,0)<n for k,n in v['started_counts'].items()) or s['write_bytes']<v['started_write_bytes']:raise RuntimeError('後続開始以前の消費の返金/初期化禁止')
 delta=s['seconds']-p['last_accounted_seconds']
 if delta < -1e-9:raise RuntimeError('累積時計の減算禁止')
 if delta:
  v['used_seconds']+=delta
  if p['segment']['foundation_only']:p['foundation_only']['used_seconds']+=delta
  p['last_accounted_seconds']=s['seconds']
 return p
def check_steady(s,expected_seconds=0):
 p=account_steady(s);v=p['steady_phase']
 if expected_seconds<0:raise ValueError('負の予約')
 pending=sum(x.get('expected_seconds',0) for x in s['jobs'].values() if x['status']=='running')
 need=pending+expected_seconds
 if v['used_seconds']+need>v['maximum_seconds']:raise RuntimeError('後続の通常時間予約上限')
 if s['seconds']+need>=TOTALS['seconds']-CLOSING_SECONDS:raise RuntimeError('最後12時間は終了専用')
 if p['segment']['foundation_only'] and p['foundation_only']['used_seconds']+need>p['foundation_only']['maximum_seconds']:raise RuntimeError('基盤12時間の切替境界')
 if s['continuation_checkpoint'].get('user_pause_requested'):raise RuntimeError('ユーザーの停止が有効')
 return p
def prepare_transition(s,reason,validation_path,validation_sha256):
 s=copy.deepcopy(s);p=s['research_execution_plan']
 if s['continuation_checkpoint'].get('user_pause_requested'):raise RuntimeError('ユーザー停止中の工程切替禁止')
 if s['jobs'] or any(not c['closed'] for c in s['campaigns'].values()):raise RuntimeError('全ジョブ/契約を先に閉じる')
 if p['status']!='active' or p['segment']['stage']!='D' or p.get('steady_phase'):raise RuntimeError('初回工程の二重終了/巻戻し禁止')
 if any(x['status'] not in ['completed','partial_switched'] for x in p['first_stage']['stages'][:-1]):raise RuntimeError('前工程が未終了')
 d=p['first_stage']['stages'][-1]
 if d['id']!='D' or d['used_seconds']>d['maximum_seconds'] or p['first_stage']['used_seconds']>p['first_stage']['maximum_seconds']:raise RuntimeError('初回工程時計が不整合')
 d.update(status='completed',exit_reason=reason,quality_goal_completed=False)
 p['first_stage']['status']='completed_with_scientific_nonpasses'
 p['steady_phase']=dict(id='speech-improvement-steady-20261009-v1',started_cumulative_seconds=s['seconds'],started_counts=copy.deepcopy(s['counts']),started_write_bytes=s['write_bytes'],started_scientific_completed=s['long_horizon']['scientific_completed'],started_review_checkpoint=copy.deepcopy(s['long_horizon']['last_review']),used_seconds=0.,maximum_seconds=TOTALS['seconds']-CLOSING_SECONDS-s['seconds'],first_stage_sha256=first_hash(p),guard_validation=dict(path=validation_path,sha256=validation_sha256),boundary_path='steady-speech-boundary-20261009-v1.json',boundary_sha256=None,retired_mechanism='Aで登録したaiu六TCX/TCY係数。k/t開発とD語句で不通過。旧集合での救済やC未実施sの移し替えは禁止。新しい要因/資料/機構は旧役割を保持して別登録。')
 p['last_accounted_seconds']=s['seconds'];p['segment']=dict(stage='steady',foundation_only=True,reason=reason);p['foundation_only']['status']='running'
 return s
class SteadySpeechBudget(LongHorizonBudget):
 def _load(self,active=True):
  s=super()._load(active);account_steady(s);return s
 def _check(self,s,extra=0,campaign=None,tier='internal'):
  check_steady(s);return super()._check(s,extra,campaign,tier)
 def _science_ready(self,s):
  super()._science_ready(s);p=check_steady(s);v=p['steady_phase'];old=p['guard_validation']
  if digest(ROOT/old['path'])!=old['sha256']:raise RuntimeError('旧工程ガードの封印不一致')
  for n,h in read(ROOT/old['path'])['validated_sources'].items():
   if digest(ROOT/n)!=h:raise RuntimeError('旧工程ガード源不一致')
  g=v['guard_validation'];path=ROOT/g['path']
  if digest(path)!=g['sha256'] or not read(path)['passed']:raise RuntimeError('後続工程ガード未検証')
  for n,h in read(path)['validated_sources'].items():
   if digest(REPO/n)!=h:raise RuntimeError('後続管理源不一致')
  boundary=ROOT/v['boundary_path']
  if not v['boundary_sha256'] or digest(boundary)!=v['boundary_sha256']:raise RuntimeError('初回工程終了の封印不一致')
  record=read(boundary)
  if record['first_stage_sha256']!=first_hash(p) or record['started_counts']!=v['started_counts'] or record['started_cumulative_seconds']!=v['started_cumulative_seconds']:raise RuntimeError('初回終了の消費記録不一致')
 def reserve(self,campaign,kind,label,count=1,reserve_bytes=0,*,expected_seconds=0):
  with self.locked():
   s=self._load();check_steady(s,expected_seconds);self._write_state(s)
  return super().reserve(campaign,kind,label,count,reserve_bytes,expected_seconds=expected_seconds)
 def set_focus(self,foundation_only,reason):
  with self.locked():
   s=self._load();check_steady(s);p=s['research_execution_plan'];p['segment'].update(foundation_only=bool(foundation_only),reason=reason);p['foundation_only']['status']='running' if foundation_only else 'secondary_or_audio_work'
   self.event(s,dict(event='steady_focus_changed',foundation_only=bool(foundation_only),reason=reason));self._write_state(s)
