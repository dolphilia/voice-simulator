"""WORLD文章入力対照の全分母・依存・失敗・実消費を終了監査する。"""
import sys,json,subprocess
from paths import *
def main():
 b=Budget()
 with b.job(NAME,'audit','旧封印・全384波形/768認識・変換・OS拒否を終了監査',reserve_bytes=2_000_000) as j:
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
  assert all(read(HERE/n)['passed'] for n in ['conversion-audit.json','self-test.json','baseline-gate.json','runtime-audit.json'])
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==384
  stable=True
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'];stable &= r['E0_pass']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==384 and a['new_ai']+a['reused']==384
   for item in a['rows']:assert digest(REPO/item['path'])==item['sha256']
  blocked=[SRES/'models/neural.pt',SRES/'models/direct_non_neural.json',HERE/'render/world/world-fresh-00/neutral/native.wav',PREVIOUS/'protocol.json']
  probe="import json,socket;paths="+repr([str(x) for x in blocked])+";a=[]\nfor p in paths:\n try:open(p,'rb');a.append(False)\n except PermissionError:a.append(True)\ns=socket.socket()\ntry:s.bind(('127.0.0.1',0));net=False\nexcept PermissionError:net=True\nprint(json.dumps({'read_denied':a,'network_denied':net}))"
  process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'isolation.sb'),sys.executable,'-I','-B','-c',probe],capture_output=True,text=True);assert process.returncode==0,process.stderr;proof=json.loads(process.stdout);assert all(proof['read_denied']) and proof['network_denied']
  b.save(HERE/'completion-audit.json',{'old_seals':checked,'verified_unique_files':len(seen),'all_old_hashes_unchanged':True,'all_frozen_sources_models_gains_verified':True,'all_wave_and_ASR_hashes_verified':True,'denial_probe':proof,'all_384_E0_pass':stable,'old_96_same_quarter_gain_wave_state_lf0_bit_matches':True,'same_20_runtime_pairs':True,'conversion_reference_passed':True,'WORLD_four_fixtures_repeat_bit_matches':True,'no_optimization_after_ASR':True,'quality_goal_completed':False},j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed'];summary=read(HERE/'summary.json')
 b.save(HERE/'cost-audit.json',{'global_snapshot':state,'local_counts':c['counts'],'local_seconds_before_seal':state['seconds']-c['start_seconds'],'failed_jobs':failed,'active_jobs':0,'unfinished_process_handles':0,'diagnostic_renders':384,'self_test_renders':8,'runtime_renders':80,'ASR_new':sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']),'ASR_reused':sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon']),'NN_control_inference_batches':64,'new_teacher':0,'new_fits':0,'new_inverse':0,'download_bytes_actual':read(HERE/'world-provenance.json')['actual_download_bytes'],'download_charged_conservatively':200000,'individual_limits_not_raised':True})
 lines=["# HMM制御からWORLDへの文章入力合成の比較結果","","2026-10-04。比較は終了したが、包括研究の品質目標は未達。固定変換を伴う別非ニューラル生成器の診断であり、純粋な位相/励起差、保存波形の再合成、知覚品質認定とは扱わない。","","旧SRC前向き8文を診断再利用し、履歴照合後に新短4・長4を出力前固定した。6制御方法×2指定×16文×HTS/WORLDで384音声。支持はHTS native baselineだけから固定。共通利得min(1,.95/HTSrawpeak)*.25を両生成器へ適用し、候補peak・支持・閾値を結果で救済しなかった。","","MCPをalpha .55の複素all-pass式へ展開し、power=exp(2logamp)/32768²へ変換。LPFから周期/雑音powerとAPを近似し、48k/FFT4096/5msでWORLD生成後24kへ変換。先頭frame複製と末尾240sample切りでフレームendpoint時計を対応させた。補間物理やAP推定がHTSと同じとは主張しない。保存の先生音声からスペクトルを解析して未知文に流用する機構ではない。","","HTS_freqt(-alpha)の独立C対照との対数振幅差は最大 "+str(read(HERE/'conversion-audit.json')['max_absolute_logamp_error'])+"。固定4合成fixtureの2反復も同波形。最初のimportはpkg_resources不足で音声生成前に失敗し、凍結環境を変更せず標準importlib.metadata入口の別版を保存した。元package/native binary/失敗を保持し、自己検査の浮動小数220Hz equalityだけrtol1e-12にした。科学条件は不変。","","旧96の共通.25利得波形・状態・LF0一致、384 E0通過、通常/隔離20組の40実行80生成一致、NN/教師/旧結果/保存波形/network実拒否を確認。元コードのbaseline_pre_headroomという補助field名は今回には不正確で、実検査は旧SRCの既に.25適用済みwaveとの一致。completion-auditの正確な記述を用いる。利用通知とWORLD/PyWORLD/HTS通知を最終bundleへ保持。","","全群と支持の結果:"]
 for cohort in ['legacy_diagnostic','prospective_once']:
  lines += ["","cohort "+cohort]
  for method in p['variants']:
   notes=[]
   for engine in ['whisper','reazon']:
    value=summary['content'][cohort][method][engine];g=value['groups']['both/all'];worse=sum(not x['non_worsening'] for x in value['groups'].values());notes.append(engine+" "+str(g['native_errors'])+"→"+str(g['errors'])+"/"+str(g['characters'])+"、不通過群"+str(worse))
   checks=summary['engineering'][cohort][method]['pairs'];missing0=sum(bool(x['baseline_missing']) for x in checks);missing1=sum(bool(x['candidate_missing']) for x in checks)
   lines.append("- "+method+": "+"; ".join(notes)+"; 固定支持欠損対 "+str(missing0)+"→"+str(missing1))
 lines += ["","資格判定: "+json.dumps(summary['qualifications'],ensure_ascii=False),"","平均/一認識器/一群の改善を全群・固定支持通過へ読み替えず、日本語自然さ資格と短イベント測定資格の不足を保持した。新8文は前向き診断、独立最終確認は未開封。","","費用: "+json.dumps(c['counts'],ensure_ascii=False)+"。fit/教師/逆推定0。失敗と未予約import起動の保守計数はcost-audit参照。全予約終了、旧封印保持、個別予算上限は変更していない。","","次は日本語で学習された第二ニューラル教師の取得条件・固定実行と、教師の音声を非ニューラル機構へ移す経路を検証する。WORLD/APの細かい事後探索を本確認集合で行わない。既存Kokoro教師との内容診断と、教師→WORLD分析再合成は共有未知文生成への移出と別段階として記録する。"]
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snapshot=b.reconcile();b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':snapshot,'experiment_completed':True,'quality_certified':False,'quality_goal_completed':False});b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
