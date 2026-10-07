"""共有スペクトル制御の全分母・隔離・旧封印・実費を終了監査する。"""
from paths import *
import json,numpy as np
from scipy.io import wavfile

def main():
 b=Budget();p=read(HERE/'protocol.json');s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','全196波形/392認識・48隔離組・旧全封印を終了監査',reserve_bytes=2500000) as j:
  seals=list(read(BOUNDARY/'completion-audit.json')['old_seals'])+[str((BOUNDARY/'artifact-seal.json').relative_to(REPO)),str((SPECTRAL1/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
  for n in seals:
   q=read(REPO/n);base=Path(q['path_base'])
   for f,h in q['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   checked[n]={'sha256':digest(REPO/n),'files':len(q['files'])}
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h,n
  for n,h in ec['external_generation_sources'].items():assert digest(REPO/n)==h,n
  for n,h in ec['model_hashes'].items():assert digest(HERE/'models'/n)==h,n
  for n,h in p['dependencies'].items():assert digest(REPO/n)==h,n
  assert digest(HERE/'gain-contract.json')==ec['gain_contract_sha256'] and digest(HERE/'protocol.json')==ec['protocol_sha256']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==196 and manifest['all_models_fixed_before_audio']
  all_e0=True
  for q in manifest['rows']:
   r=read(REPO/q['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==q['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'];fs,audio=wavfile.read(REPO/r['wav']);assert fs==24000 and audio.dtype==np.float32 and np.isfinite(audio).all() and np.max(abs(audio))<1
   candidate=np.load(REPO/r['parameters']);native=np.load(HERE/'render'/r['mode']/r['id'].split('/')[0]/r['condition']/'native.npz')
   assert np.array_equal(candidate['lf0'],native['lf0']) and np.array_equal(candidate['lpf'],native['lpf']) and np.array_equal(candidate['spectrum'][:,0],native['spectrum'][:,0]) and np.array_equal(candidate['spectrum'][:,9:],native['spectrum'][:,9:])
   assert np.array_equal(candidate['spectrum'][:,1:9],native['spectrum'][:,1:9]+candidate['spectral_residual']) and np.max(np.sum(abs(candidate['spectral_residual']),axis=1))<=.5+1e-12 and len(audio)==len(candidate['lf0'])*120
   assert r['c0_c9plus_LF0_LPF_state_clock_unchanged'] and r['output_gain']==.25;all_e0 &= r['E0_pass'];nr=read(HERE/'render'/r['mode']/r['id'].split('/')[0]/r['condition']/'native.json');assert r['duration']==nr['duration'] and r['msd']==nr['msd'] and r['state_snapshot_hash']==nr['state_snapshot_hash'] and r['vocoder_settings']==nr['vocoder_settings']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==196 and a['new_ai']+a['reused']==196
   for q in a['rows']:
    r=read(REPO/q['path']);assert digest(REPO/q['path'])==q['sha256'] and r['status']=='completed'
    if r.get('reused_from'):
     source=read(REPO/r['reused_from']);assert digest(REPO/r['reused_from'])==r['reused_sha256'] and source['wav_sha256']==r['wav_sha256'] and source['text']==r['text'] and source['reference_kana']==r['reference_kana']
  rt=read(HERE/'runtime-audit.json');assert rt['passed'] and len(rt['pairs'])==48 and all(q['bit_match'] for q in rt['pairs']) and all(rt['denial_probe']['read_denied']) and rt['denial_probe']['network_denied']
  bundle=read(HERE/'runtime-bundle/manifest.json')
  for n,h in bundle['files'].items():assert digest(HERE/'runtime-bundle'/n)==h
  assert not list((HERE/'runtime-bundle').rglob('*.wav')) and not list((HERE/'runtime-bundle').rglob('*.pt'))
  for method in ['direct_non_neural','distilled_non_neural']:
   m=read(HERE/'runtime-bundle'/(method+'.json'));assert np.asarray(m['coefficients']).shape==(16,8) and not m['runtime_neural']
  targets=[q for r in read(HERE/'target-manifest.json')['rows'] for q in r['targets']]
  inverse_diagnostic=dict(targets=len(targets),L1_projection_active=sum(q['L1_projection_active'] for q in targets),native_centered_logamp_RMSE_mean=float(np.mean([q['baseline_centered_logamp_RMSE'] for q in targets])),target_centered_logamp_RMSE_mean=float(np.mean([q['target_centered_logamp_RMSE'] for q in targets])),not_waveform_quality_or_independent_evidence=True)
  b.save(HERE/'target-representation-diagnostic.json',inverse_diagnostic,j)
  b.save(HERE/'completion-audit.json',dict(old_seals=checked,verified_unique_old_files=len(seen),all_old_hashes_unchanged=True,all_frozen_sources_models_gains_verified=True,all196_wave_and392_ASR_hashes_verified=True,all196_E0_pass=all_e0,c0_c9plus_LF0_LPF_time_invariants_independently_rechecked=True,all48_normal_isolated_pairs_bit_match=True,denial_probe=rt['denial_probe'],fixed128_coefficients_each_final_model=True,no_NN_teacher_or_waveform_in_final_bundle=True,no_fit_or_optimization_after_ASR=True,protected_confirmation_opened=False,quality_goal_completed=False),j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 b.save(HERE/'cost-audit.json',dict(global_snapshot=state,local_counts=c['counts'],local_seconds_before_seal=state['seconds']-c['start_seconds'],failed_jobs=failed,active_jobs=0,new_teacher=0,fits=3,inverse_utterance_batches=17,training_renders=68,diagnostic_renders=128,runtime_renders=96,new_ASR=new,exact_ASR_reuse=reuse,NN_control_inference_batches=49,download=0,individual_limits_not_raised=True))
 lines=['# 教師スペクトルの共有制御への移出結果','','2026-10-05。Kokoro既存17訓練文の内部予測時刻を研究用整列に使い、スペクトル包絡の残差をMCP c1..c8へ近似した。未知生成の入力は文章/辞書音素・韻律と指定だけ。教師音声、発話ID検索、保存軌跡、NN重みを最終候補へ持ち込まなかった。包括品質目標は未達。','','中央50%区間版は短い音素の3frame不足で11/17受理（短10長1）、fit0で終了し封印した。本版は同じ既存power/native MCPを再利用し、予測全音素区間に変えて同じ3frame・最低12文/短5長3・全対象保持を満たした。17文209区間。内部予測時間の合計とIPA全列対応は確認したが、実際の音素境界の正解資格ではない。全区間には共調音/他音素の寄与もあり得る。','','CheapTrick24k/FFT2048の1025周波数を、48k/FFT4096/alpha .55のMCP c1..c8基底へ投影した。周波数平均を除去し、inverse ridge .001、係数L1<=.5を固定した。全209目標が上限投影され、平均中心化logamp RMSEは '+str(inverse_diagnostic['native_centered_logamp_RMSE_mean'])+'→'+str(inverse_diagnostic['target_centered_logamp_RMSE_mean'])+'。この小さな近似改善は実波形改善を保証せず、表現/制約/逆推定法の制限を保持した。','','同一16特徴から直接回帰と同サイズ学生（各128係数+標準化32値）を学習した。研究NNは16→16tanh→16tanh→8、500step、seed20261005。回帰lambda10と文ごとの重みを固定した。訓練projected MSE: '+json.dumps(s['training_loss'],ensure_ascii=False)+'。NNの小さいlossを未知生成の優位性へ読み替えない。','','各音素の前後10%をsin²fadeとしてフレームc1..c8へ加算した。c0/c9以降、LF0、LPF、HMM状態/時計は完全に保持し、gain .25を全方法へ固定した。世界変換は既存検証済み式を維持した。17訓練×4方法68と、既知8/新8×2指定×4方法128、計196波形。訓練波形と既知文再評価は独立品質証拠ではない。','','全文字・固定21群の結果:']
 for cohort,methods in s['content'].items():
  lines+=['',cohort]
  for method,engines in methods.items():
   notes=[]
   for engine,q in engines.items():
    a=q['groups']['both/all'];notes.append(engine+' '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not r['non_worsening'] for r in q['groups'].values())))
   eng=s['engineering'][cohort][method];lines.append('- '+method+': '+'; '.join(notes)+'; E0 '+str(sum(r['E0_pass'] for r in eng['pairs']))+'/16、固定支持欠損 '+str(sum(bool(r['missing_support']) for r in eng['pairs']))+'/16')
 lines+=['','未知文の限定内容/工程支持: '+json.dumps(s['qualifications'],ensure_ascii=False),'','学生と直接回帰の比較:']
 for cohort,q in s['student_vs_direct'].items():
  for engine,v in q.items():
   a=v['groups']['both/all'];lines.append('- '+cohort+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not r['non_worsening'] for r in v['groups'].values())))
 lines+=['','最終依存: 8新文×2指定×3非ニューラル方法の48組、通常/隔離96生成で診断波形と完全一致。NN/教師/元係数/保存波形/訓練パラメータ/通信の実拒否を確認した。bundleにWAV/PTなし、固定サイズ共有係数のみ。HTS/Mei、WORLD/PyWORLD、教師由来通知を保持した。工学的な非ニューラル独立実行と、知覚品質/日本語一般化を区別する。','','費用: '+json.dumps(c['counts'],ensure_ascii=False)+'。ASR新'+str(new)+'、完全一致再利用'+str(reuse)+'。初期登録のmanifest複写は50KB符号化予約を超え、保存前に拒否された。参照hash保存へ切替え、失敗・旧manifest・全上限を維持した。再初期化/事後上限増加なし。','','未達: 日本語の当該方式に資格ある知覚評価、独立最終品質確認、信頼できる実音素境界/VOT、複数声と広い文章への一般化。未知8の前向き診断だけで全体を完了しない。','','次の判断: NNだけが支持され学生で失われる場合は学生表現の拡張を検討する。全方式で支持されない場合は、全目標でL1投影が働きスペクトル近似改善が小さい点を踏まえ、同じ上限の下で制約を直接扱う逆推定の自己回復/到達性を別登録で検査する。旧診断や確認文で閾値・利得・支持を再調整しない。スペクトル経路で3不合格に達したら別の時間/励起/共調音経路へ切り替える。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',dict(path_base=str(REPO),files={str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},budget_before_seal=snap,experiment_completed=True,quality_certified=False,quality_goal_completed=False));b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
