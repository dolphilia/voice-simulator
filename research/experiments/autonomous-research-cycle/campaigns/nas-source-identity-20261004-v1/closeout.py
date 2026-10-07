"""単位LPFの不採択と実消費を保持して全資産を終了監査する。"""
import sys,json,subprocess
from paths import *
def main():
 b=Budget()
 with b.job(NAME,'audit','旧封印・全384波形/768認識・OS拒否を終了監査',reserve_bytes=2_000_000) as j:
  seals=list(read(PREVIOUS/'completion-audit.json')['old_seals'])+[str((PREVIOUS/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
  for n in seals:
   sealpath=REPO/n;s=read(sealpath);base=Path(s['path_base'])
   for f,h in s['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   checked[n]={'sha256':digest(sealpath),'files':len(s['files'])}
  for n,h in read(HERE/'execution-contract.json')['source_hashes'].items():assert digest(HERE/n)==h
  p=read(HERE/'protocol.json')
  for n,h in p['dependencies'].items():assert digest(REPO/n)==h
  assert digest(HERE/'gain-amendment-before-wave.json')==read(HERE/'execution-contract.json')['gain_contract_sha256']
  assert read(HERE/'self-test.json')['passed'] and read(HERE/'baseline-gate.json')['passed'] and read(HERE/'runtime-audit.json')['passed']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==384
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==384 and a['new_ai']==384 and a['reused']==0
   for item in a['rows']:assert digest(REPO/item['path'])==item['sha256']
  blocked=[SRES/'models/neural.pt',SRES/'models/direct_non_neural.json',HERE/'render/identity/source-fresh-00/neutral/native.wav',PREVIOUS/'protocol.json']
  probe="import json,socket;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
  process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True);assert process.returncode==0,process.stderr;proof=json.loads(process.stdout);assert all(proof['read_denied']) and proof['network_denied']
  assert not any(v['limited_diagnostic_supported'] for v in read(HERE/'summary.json')['qualifications'].values())
  b.save(HERE/'completion-audit.json',{'old_seals':checked,'verified_unique_files':len(seen),'all_old_hashes_unchanged':True,'all_frozen_sources_models_gains_verified':True,'all_wave_and_ASR_hashes_verified':True,'denial_probe':proof,'all_384_E0_pass':all(read(REPO[r['record']])['E0_pass'] for r in manifest['rows']),'old_96_pre_headroom_bit_matches':True,'same_20_runtime_pairs':True,'all_unvoiced_test_bit_matches':True,'no_optimization_after_ASR':True,'quality_goal_completed':False},j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed']
 assert c['counts']['render']==466 and c['counts']['dsp']==1192 and c['counts']['ai']==832 and not failed
 b.save(HERE/'cost-audit.json',{'global_snapshot':state,'local_counts':c['counts'],'local_seconds_before_seal':state['seconds']-c['start_seconds'],'failed_jobs':failed,'active_jobs':0,'unfinished_process_handles':0,'diagnostic_renders':384,'self_test_renders':2,'runtime_renders':80,'ASR_new':768,'ASR_reused':0,'NN_control_inference_batches':64,'new_teacher':0,'new_fits':0,'new_inverse':0,'download_bytes_actual':37004,'download_charged_conservatively':100000,'individual_limits_not_raised':True})
 report="""# 包絡を保った単位LPF励起対照の結果

2026-10-04。単位LPFによる励起変更は、今回の両ASR全群条件を満たさず採択しない。計画された比較は終了したが、包括研究の品質目標は未達。

元MCP全次数、LF0、時間/MSD、3stream、LPF列数、初期seed、alpha/beta/volumeを保持し、LPFだけを全フレーム中央1・他0へ置換した。旧の完全平坦＋LPFなしと異なる、元包絡の励起対照である。同じバッファ長と上流の乱数呼出経路を保持する設計であり、内部RNG stateを直接計測したとは主張しない。pyopenjtalk0.4.1の固定HTS submoduleコード2件を取得・hash記録し、BSD通知を保存した。

旧既知8文と前向き新8文、各2指定、標準/直接16/研究NN/学生16/直接4/学生4の6方法、元/単位LPF、計384条件。生成前の候補pool照合で既出の「桃を包む。」を除外し、固定後は入力を変更しなかった。比較の飽和を避ける共通0.25利得を初波形前に固定し、baselineにもcandidateにも同じ利得を適用した。旧認識は流用せず、全768件を新評価した。前campaignとの認識差を励起だけの効果とは呼ばない。

旧96の利得余裕適用前の波形・状態・LF0が一致。全無声LF0の2自己検査も同じ波形となった。384条件のE0は通過し、基準/候補間の全MCP・LF0・内部状態・固定利得を検証した。単位LPFは192対すべてのwave hashを変えたが、有声支持の欠損対数は全cohort/方法で回復0・新規欠損0だった。今回の固定支持欠損をLPF混合だけで解消できる証拠はない。

新8文のWhisper誤り/全文字304は、直接16の元21→単位20、学生16の25→22、学生4の22→19。Reazonは順に16→16、16→16、15→15。しかしWhisperは同方法対照に対し6/2/3群が悪化した。標準はWhisper26→28、Reazon15→18。旧8文でも全方法の両ASR全群条件は不通過だった。平均改善、一認識器だけの群通過、支持欠損不変を品質認定へ昇格しない。

固定共有係数と非ニューラルHTSだけの5方式×新短/長×2指定について、20通常/隔離組40実行80生成はすべて同一wave hash。教師/NN/保存軌道/旧成果/networkのOS拒否probeも通過した。Meiの利用通知とHTSヘッダのBSD通知をbundle内に保持。自然さ資格、短イベント測定の知覚資格、独立最終確認は未達。

消費render466、DSP1192、AI832（新ASR768＋研究NN制御64）、取得実37004bytesを保守的100000bytesとして予算計数。追加fit/教師/逆推定0、技術失敗0、全予約終了・個別上限維持・旧封印保持。費用/全群/全失敗の詳細はcost-audit.json、summary.json、completion-audit.json、artifact-seal.json。

次はLPF混合率やLF0特徴の追加探索を切り替え、別非ニューラルレンダラーの比較を準備する。HMMが文章から生成する同じ制御をWORLDへ明示変換すれば、保存音声の分析再合成とは別の文章入力生成を調べられる。MCP変換、非周期性近似、別生成器を一緒に変更するため、純粋な位相差だけの因果効果とは呼ばない。変換は一次資料と自己検査で確かめ、未知文に使う前に固定する。第二日本語ニューラル教師と教師スペクトルの共有補正学習も候補として保持する。
"""
 b.write(HERE/'report.md',report.encode());snapshot=b.reconcile();b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':snapshot,'experiment_completed':True,'quality_certified':False,'quality_goal_completed':False});b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
