"""韻律4特徴比較の未達を保持し、旧封印・固定資産・全成果を監査する。"""
import sys,json,subprocess
from paths import *
def main():
 b=Budget();summary=read(HERE/'summary.json')
 with b.job(NAME,'audit','旧封印・4係数・全波形認識・禁止依存を終了監査',reserve_bytes=2_000_000) as j:
  seals=list(read(CURRENT/'completion-audit.json')['old_seals'])+[str((CURRENT/'artifact-seal.json').relative_to(REPO)),str((ROOT/'campaigns/nas-prosody-only-20261004-v1/artifact-seal.json').relative_to(REPO))];seen={};verified={}
  for n in seals:
   q=REPO/n;s=read(q);base=Path(s['path_base'])
   for f,h in s['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   verified[n]={'sha256':digest(q),'files':len(s['files'])}
  ec=read(HERE/'execution-contract.json')
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h
  for n,h in read(HERE/'model-comparison.json')['new_model_hashes'].items():assert digest(HERE/'models'/(n+'.json'))==h
  assert digest(HERE/'run-resume.py')==read(HERE/'storage-amendment-01.json')['resume_source_sha256']
  assert digest(HERE/'training-wave-resume.py')==read(HERE/'technical-amendment-02.json')['fixed_source_sha256']
  blocked=[SRES/'models/neural.pt',SRES/'models/direct_non_neural.json',HERE/'render/prosody-fresh-00/neutral/native.wav',CURRENT/'protocol.json']
  probe="import json,socket;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
  process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True);assert process.returncode==0,process.stderr
  proof=json.loads(process.stdout);assert all(proof['read_denied']) and proof['network_denied']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==192
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256']
   if 'reused_record' in r:assert digest(REPO/r['reused_record'])==r['reused_record_sha256']
  for e in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+e+'.json'));assert len(a['rows'])==192 and a['new_ai']==128 and a['reused']==64
   for item in a['rows']:assert digest(REPO/item['path'])==item['sha256']
  assert read(HERE/'runtime-audit.json')['passed'];assert not any(x['limited_diagnostic_supported'] for x in summary['qualifications'].values())
  initial=read(ROOT/'campaigns/nas-prosody-only-20261004-v1/registration.json')['new_texts'];final=read(HERE/'registration.json')['new_texts']
  assert initial[1]=='糸を結ぶ。' and final[1]=='絹を染める。';assert all(a==z for i,(a,z) in enumerate(zip(initial,final)) if i!=1)
  b.save(HERE/'completion-audit.json',{'old_seals':verified,'verified_unique_files':len(seen),'all_old_hashes_unchanged':True,'source_and_model_hashes_unchanged':True,'all_render_asr_hashes_verified':True,'denial_probe':proof,'initial_and_new_registered_texts':{'initial':initial,'new':final},'prepared_before_any_generation':True,'scientific_conditions_not_changed_after_ASR':True,'quality_goal_completed':False},j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed']
 b.save(HERE/'cost-audit.json',{'global_snapshot':state,'local_counts':c['counts'],'local_seconds_before_seal':state['seconds']-c['start_seconds'],'failed_jobs':failed,'counts_include_failures':True,'new_diagnostic_renders':128,'saved_diagnostic_renders':64,'successful_training_renders':8,'successful_runtime_renders':16,'training_pre_wave_failed_attempts':1,'new_DSP_with_failed_attempt':427,'ASR_new':256,'ASR_reused':128,'NN_control_inference_batches':33,'fits':2,'teacher_generation':0,'downloads':0,'active_jobs':0,'unfinished_process_handles':0,'started_limits_not_raised':True})
 report="""# 韻律4特徴へ制限した共有制御の結果

2026-10-04。直接/蒸留4係数は、固定二ASRの全群条件と支持/全体F0条件を満たさず、採択しない。元の16特徴より良い合計があるが、標準より悪化した群を残す。包括研究の品質目標は未達。

同一の17訓練文/209音素区間を再使用し、韻律4特徴の直接回帰と保存研究NNからの蒸留を各1回fitした。λ10、中心化・一様縮尺±3半音、HTSの包絡/LPF/時間/MSDは維持。教師の世代や声を変えた比較ではない。旧8×2条件×既存4方法64波形は再使用し、新方法と新8文を生成して計192条件を揃えた。事前候補の既出「糸を結ぶ。」はfit/音声生成前に停止し、未使用文を別登録した。保護最終確認は開封していない。

4特徴の訓練制御MSEは直接0.461685、学生0.464215。保存16特徴の0.445620/0.447843より大きい。固定順の訓練短2長2文を実合成した全8条件で教師F0形状距離は標準以下になったが、この4文は訓練内診断であり未知文転移の証明ではない。

新8文の全文字分母306に対し、Whisperは標準24、直接16特徴34、直接4特徴27、学生16特徴35、学生4特徴29。Reazonは順に15/15/14/14/15。直接4特徴でもWhisper12群が標準より悪化し、16特徴対照に対しても1群悪化した。学生4特徴はWhisper16群が標準より悪化した。音響支持の欠損は新8で標準0、直接/学生16特徴各1、直接4特徴3、学生4特徴4、研究NN5条件。特徴制限だけで改善を一般化できない。

192診断条件のE0/有限性は通過。新4係数の通常/隔離8組は全て同一波形。固定サイズモデルを入力文から計算し、教師/NN/保存軌道/ネットワークの拒否を実検査した。自然さ資格・短イベント測定資格・独立最終確認は未達。

消費はrender153（診断128＋訓練8＋隔離16＋生成前失敗1）、DSP427（失敗3込み）、新ASR256、保存認識再使用128、研究NN制御推論33batch、fit2、追加教師/取得0。過大JSON予約拒否と保存layoutのtuple/list比較不一致を、元波形・科学条件を保って技術再試行で解決した。旧封印と全成果hash、失敗台帳、全予約終了を確認した。

LF0共有関数の強度や特徴数だけの追加探索はここで切り替える。次は包絡を維持したままLPFを単位インパルスへ置換する励起対照を検討する。これは旧の完全平坦＋LPFなしとは異なり、元の3stream、乱数取得経路、リング遅延を保持して、混合励起の影響を切り分ける。実装の根拠は公式HTS_vocoder.cの励起関数を参照する（https://github.com/r9y9/hts_engine_API/blob/master/src/lib/HTS_vocoder.c）。原コードは今回のバイナリ版を別途確認し、一次資料のmasterが凍結版と一致するとは仮定しない。
"""
 b.write(HERE/'report.md',report.encode());before=b.reconcile();b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':before,'experiment_completed':True,'quality_certified':False,'quality_goal_completed':False});b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
