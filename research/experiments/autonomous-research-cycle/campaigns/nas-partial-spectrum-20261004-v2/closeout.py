"""旧封印・固定条件・実呼出・禁止読取・成果を終了監査する。"""
import sys,json,subprocess,collections
from paths import *

def main():
 b=Budget()
 with b.job(NAME,'audit','旧封印・凍結・依存拒否・終了台帳',reserve_bytes=2_000_000) as j:
  seals=read(PREP/'input-preservation.json')['seals']+[{'seal':str((PREP/'artifact-seal.json').relative_to(REPO))}]
  checked={};seen={}
  for item in seals:
   path=REPO/item['seal'];s=read(path);base=Path(s['path_base'])
   if 'sha256' in item:assert digest(path)==item['sha256']
   for n,h in s['files'].items():
    q=base/n
    if str(q) not in seen:seen[str(q)]=digest(q)
    assert seen[str(q)]==h,str(q)
   checked[item['seal']]={'sha256':digest(path),'files':len(s['files'])}
  for n,h in read(HERE/'execution-contract.json')['source_hashes'].items():assert digest(HERE/n)==h
  for n,h in read(HERE/'technical-amendment-02.json')['files'].items():assert digest(HERE/n)==h
  blocked=[SRES/'models/neural.pt',SRES/'models/direct_non_neural.json',HERE/'render/partial/spectral-fresh-00/neutral/native.wav',PREP/'protocol.json']
  probe="import json,socket;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
  process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True)
  assert process.returncode==0,process.stderr
  proof=json.loads(process.stdout);assert all(proof['read_denied']) and proof['network_denied']
  m=read(HERE/'render-manifest.json');assert len(m['rows'])==256
  for r in m['rows']:
   v=read(REPO/r['record']);assert digest(REPO/v['wav'])==v['wav_sha256']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==256 and a['new_ai']==192 and a['reused']==64
   for r in a['rows']:assert digest(REPO/r['path'])==r['sha256']
  assert read(HERE/'baseline-gate.json')['passed'] and read(HERE/'runtime-audit.json')['passed']
  assert not any(q['limited_diagnostic_supported'] for q in read(HERE/'summary.json')['qualifications'].values())
  b.save(HERE/'completion-audit.json',{'old_seals':checked,'verified_unique_files':len(seen),'all_old_hashes_unchanged':True,'frozen_sources_unchanged':True,'denial_probe':proof,'all_render_asr_hashes_verified':True,'scientific_conditions_not_changed_after_asr':True,'quality_goal_completed':False},j)
 s=b.snapshot();assert not s['jobs'];c=s['campaigns'][NAME]
 events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[v for v in events if v.get('event')=='finish' and v['campaign']==NAME and v['status']=='failed']
 b.save(HERE/'cost-audit.json',{'global_snapshot':s,'local_counts':c['counts'],'local_seconds_so_far':s['seconds']-c['start_seconds'],'technical_failed_jobs':failed,'active_jobs':0,'unfinished_process_handles':0,'new_downloads':0,'teacher_calls':0,'fits':0,'ai_new':384,'ai_reused':128,'renders':370,'DSP_attempts':793,'successful_runtime_renders':48,'runtime_nested_sandbox_failed_render_attempts':2,'limits_not_raised_after_start':True,'note':'包括時間は初期管理30分の保守的加算を含む。seal/報告/台帳の終了書込は以後にも計数する。'})
 report="""# 部分包絡比較の結果

2026-10-04。固定MCP非零次数0.75倍は採択条件を満たさなかった。個別実験終了であり、包括研究の品質完了ではない。

旧8文と新8文、各2指定、標準・直接・研究ニューラル・学生、原包絡と部分包絡の256波形を比較した。旧64はWAV、LF0、全状態、時間、全MLPG列まで元経路と一致した。時間・MSD・LF0・LPF・c0・seed・出力利得は比較間で固定した。新8文は観測済み履歴と生成前照合し、保護された最終確認は開封していない。

新8文の学生は全文字290に対しWhisper誤り11→9、Reazon29→18となったが、両認識器で各2群が悪化した。直接はWhisper10→12、Reazon29→17。総平均だけを採択に使わない。旧8文でも全方法が両ASR全群条件を満たさず、支持欠損・活動長・一部F0の保護違反も残った。包絡の弱化は一部の検出を回復するが、発音の内容保持との両立を証明していない。

256条件の有限性/E0は通過。通常・隔離12組は全てbit一致した。隔離は教師・NN・保存軌道・ネットワークをOSで拒否し、実際の禁止読取/network probeも通過した。固定共有係数とHTSだけを配布する。日本語自然さの資格、短イベントの知覚真値、独立最終品質は未達のまま。

実レンダー370（診断256、元経路64、通常/隔離48、隔離未起動2）、DSP793、実ASR384・保存再使用128、追加教師/fit/取得0。import接続と二重sandboxの技術失敗を保存し、科学条件は変更せず回復した。全予約終了・包括/個別上限内・旧封印保持を確認した。詳細はsummary.json、completion-audit.json、cost-audit.json、artifact-seal.json。

次は包絡倍率探索を繰り返さず、音素ごとのF0補正が未知文内容へ与える影響を切り分ける。既存16特徴からprosody4特徴へ制御を制限し、同じ実波形由来17訓練文の直接学習と研究NNからの蒸留を比較する。教師を変更した効果とは呼ばない。旧比較は診断、新8文は出力前固定の確認とし、閾値は維持する。
"""
 b.write(HERE/'report.md',report.encode())
 before=b.reconcile()
 b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':before,'quality_certified':False,'experiment_completed':True,'quality_goal_completed':False})
 b.close_campaign(NAME)
 print(b.reconcile(),flush=True)
if __name__=='__main__':main()
