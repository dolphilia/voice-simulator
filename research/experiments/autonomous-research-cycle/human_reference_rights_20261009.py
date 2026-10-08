"""既存の人間参照の権利メタデータだけを確認し、音声本文はまだ読まない。"""
import argparse,hashlib,json,os
from pathlib import Path
from budget import ROOT,read,digest,encode
from steady_speech_budget_20261009 import SteadySpeechBudget as Budget
REPO=ROOT.parents[2];HERE=ROOT/'campaigns/nas-human-reference-rights-20261009-v1';NAME='human-reference-rights-v1'
REFERENCE=REPO/'research/data/raw/reference/utau-samples'
FILES=[REFERENCE/'maoto/単独音/readme.txt',REFERENCE/'つくよみちゃんUTAU音源/ReadMe.txt',REFERENCE/'つくよみちゃんUTAU音源/利用規約.txt']
def register():
 b=Budget();b.recover();s=b.snapshot();assert not s['jobs'] and not any(not c['closed'] for c in s['campaigns'].values()) and not b.review_due(s)['due']
 assert s['long_horizon']['scientific_completed']==73;b.set_focus(False,'不採択の合成参照適合から、人間参照の権利/測定適格性と低費用の直接音声改善へ。音声本文は権利確認後だけ。')
 lim=dict(seconds=7200,bytes=64000000,write_bytes=500000000,setup=10,audit=10,render=0,dsp=0,ai=0,teacher=0,train=0,inverse=0,download=1000000)
 reg=dict(question='native合成包絡への六係数訓練は内容へ移転しなかった。権利が確認できる人間の単独母音から、発話lookup/録音断片/高密度軌跡を最終経路へ持ち込まず低次元の声源/フィルタ標的を測定する次要因を準備できるか。',role='この契約は権利/由来の確認のみ。音声本文、DSP/学習/生成/評価は未開始。',metadata=[dict(path=str(p.relative_to(REPO)),sha256=digest(p),bytes=p.stat().st_size) for p in FILES],primary_lookup='メタデータに記載された権利者の通常公開公式ページだけ確認。第三者記事から許諾を推定せず、不明な資料は音声を読まない。',no_audio_or_publication_or_contact_or_payment=True,old_maoto_reference_role='旧資料は再使用/由来確認。過去に見た資料を独立確認へ戻さない。',future_model='直接非ニューラルの共有低次元の声源/フォルマント/帯域幅等。原音声/密なスペクトル/話者埋め込みを最終音源にしない。',limits=lim,controller_sha256=digest(Path(__file__)),quality_goal_completed=False,P5_opened=False)
 b.start_campaign(NAME,str(HERE.relative_to(ROOT)),lim,hashlib.sha256(encode(reg)).hexdigest())
 with b.job(NAME,'setup','人間参照のメタデータ/役割/公式確認/費用を初読取前登録',reserve_bytes=4000000) as j:b.save(HERE/'registration.json',reg,j)
 with b.locked():
  s=b._load();s['continuation_checkpoint'].update(active_campaign=NAME,next='登録push→権利メタデータだけ読取→公式一次許諾確認→将来音声役割と留保を封印。音声本文は本契約で開かない。',git_save_pending=True);b._write_state(s)
 print('人間参照の権利メタデータだけを登録')
def metadata():
 b=Budget();b.recover();reg=read(HERE/'registration.json');assert digest(Path(__file__))==reg['controller_sha256'];rows=[]
 with b.job(NAME,'setup','権利メタデータの文字コードと記載を確認',reserve_bytes=4000000) as j:
  for item in reg['metadata']:
   p=REPO/item['path'];assert digest(p)==item['sha256'];data=p.read_bytes();assert len(data)<256000
   encoding='utf-8-sig'
   try:text=data.decode(encoding)
   except UnicodeDecodeError:encoding='cp932';text=data.decode(encoding)
   # 確認した本文は既存参照のまま保持し、Gitへ全文再配布しない。
   rows.append(dict(path=item['path'],sha256=item['sha256'],encoding=encoding,characters=len(text),audio_read=False))
   print('--- '+str(p.relative_to(REPO))+' ['+encoding+'] ---')
   print(text[:14000])
  b.save(HERE/'metadata-read-audit.json',dict(rows=rows,only_rights_metadata_read=True,audio_read=False,quality_goal_completed=False),j)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('stage',choices=['register','metadata']);a=p.parse_args();globals()[a.stage]()
