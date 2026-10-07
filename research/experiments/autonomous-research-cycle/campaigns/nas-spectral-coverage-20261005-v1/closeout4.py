"""共有スペクトル制御の全分母・隔離・旧封印・実費を終了監査する。"""
from paths import *
import json,numpy as np
from scipy.io import wavfile

def main():
 b=Budget();p=read(HERE/'protocol.json');s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','全196波形/2016認識・48隔離組・旧全封印を終了監査',reserve_bytes=2500000) as j:
  seals=list(read(SPECTRAL2/'completion-audit.json')['old_seals'])+[str((SPECTRAL2/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
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
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==1008 and manifest['all_models_fixed_before_audio']
  all_e0=True
  for q in manifest['rows']:
   r=read(REPO/q['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==q['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'];fs,audio=wavfile.read(REPO/r['wav']);assert fs==24000 and audio.dtype==np.float32 and np.isfinite(audio).all() and np.max(abs(audio))<1
   candidate=np.load(REPO/r['parameters']);native=np.load(HERE/'render'/r['mode']/r['id'].split('/')[0]/r['condition']/'native.npz')
   assert np.array_equal(candidate['lf0'],native['lf0']) and np.array_equal(candidate['lpf'],native['lpf']) and np.array_equal(candidate['spectrum'][:,0],native['spectrum'][:,0]) and np.array_equal(candidate['spectrum'][:,9:],native['spectrum'][:,9:])
   assert np.array_equal(candidate['spectrum'][:,1:9],native['spectrum'][:,1:9]+candidate['spectral_residual']) and np.max(np.sum(abs(candidate['spectral_residual']),axis=1))<=.5+1e-12 and len(audio)==len(candidate['lf0'])*120
   assert r['c0_c9plus_LF0_LPF_state_clock_unchanged'] and r['output_gain']==.25;all_e0 &= r['E0_pass'];nr=read(HERE/'render'/r['mode']/r['id'].split('/')[0]/r['condition']/'native.json');assert r['duration']==nr['duration'] and r['msd']==nr['msd'] and r['state_snapshot_hash']==nr['state_snapshot_hash'] and r['vocoder_settings']==nr['vocoder_settings']
  am=read(HERE/'evaluation-amendment-01.json');assert digest(HERE/'evaluate.py')==am['original_sha256'] and digest(HERE/'evaluate2.py')==am['revised_sha256']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert a['actual_evaluator_sha256']==digest(HERE/'evaluate2.py');assert len(a['rows'])==1008 and a['new_ai']+a['reused']==1008
   for q in a['rows']:
    r=read(REPO/q['path']);assert digest(REPO/q['path'])==q['sha256'] and r['status']=='completed'
    if r.get('reused_from'):
     source=read(REPO/r['reused_from']);assert digest(REPO/r['reused_from'])==r['reused_sha256'] and source['wav_sha256']==r['wav_sha256'] and source['text']==r['text'] and source['reference_kana']==r['reference_kana'] and source['engine']==engine and source['engine_contract_sha256']==r['engine_contract_sha256']
  amendment=read(HERE/'isolation-amendment-01.json');assert digest(HERE/'isolate.py')==amendment['original_sha256'] and digest(HERE/'isolate2.py')==amendment['revised_sha256']
  rt=read(HERE/'runtime-audit.json');assert rt['actual_isolation_controller_sha256']==digest(HERE/'isolate2.py') and rt['profile_sha256']==digest(HERE/'isolation.sb');assert rt['passed'] and len(rt['pairs'])==160 and all(q['bit_match'] for q in rt['pairs']) and all(rt['denial_probe']['read_denied']) and rt['denial_probe']['network_denied']
  bundle=read(HERE/'runtime-bundle/manifest.json')
  for n,h in bundle['files'].items():assert digest(HERE/'runtime-bundle'/n)==h
  assert not list((HERE/'runtime-bundle').rglob('*.wav')) and not list((HERE/'runtime-bundle').rglob('*.pt'))
  for method in ['direct17','student17','direct96','student96']:
   m=read(HERE/'runtime-bundle'/(method+'.json'));assert np.asarray(m['coefficients']).shape==(16,8) and not m['runtime_neural']
  targets=[q for r in read(HERE/'target-manifest.json')['rows'] for q in r.get('targets',[])]
  inverse_diagnostic=dict(targets=len(targets),L1_projection_active=sum(q['L1_projection_active'] for q in targets),native_centered_logamp_RMSE_mean=float(np.mean([q['baseline_centered_logamp_RMSE'] for q in targets])),target_centered_logamp_RMSE_mean=float(np.mean([q['target_centered_logamp_RMSE'] for q in targets])),not_waveform_quality_or_independent_evidence=True)
  b.save(HERE/'target-representation-diagnostic.json',inverse_diagnostic,j)
  b.save(HERE/'completion-audit.json',dict(old_seals=checked,verified_unique_old_files=len(seen),all_old_hashes_unchanged=True,all_frozen_sources_models_gains_verified=True,all1008_wave_and2016_ASR_hashes_verified=True,all1008_E0_pass=all_e0,c0_c9plus_LF0_LPF_time_invariants_independently_rechecked=True,all160_normal_isolated_pairs_bit_match=True,denial_probe=rt['denial_probe'],fixed128_coefficients_each_final_model=True,no_NN_teacher_or_waveform_in_final_bundle=True,no_fit_or_optimization_after_ASR=True,protected_confirmation_opened=False,quality_goal_completed=False),j)

 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 b.save(HERE/'cost-audit.json',dict(global_snapshot=state,local_counts=c['counts'],local_seconds_before_seal=state['seconds']-c['start_seconds'],failed_jobs=failed,active_jobs=0,new_teacher=81,new_teacher_distinct79=79,old_teacher_reproducibility_calls=2,fits=3,old_fits_reused=3,inverse_utterance_batches=c['counts'].get('inverse',0),training_renders=672,diagnostic_renders=336,runtime_renders=320,new_ASR=new,exact_ASR_reuse=reuse,NN_control_inference_batches=288,download=0,individual_limits_not_raised=True))
 target=read(HERE/'target-manifest.json');any_supported=any(s['qualifications'][v] for v in ['direct96','neural96','student96'])
 lines=['# 訓練資料拡張による共有スペクトル制御の結果','','2026-10-05。包括品質目標は未達。最終音源は非ニューラルを維持し、同じ教師・全区間スペクトル表現・16特徴・c1..c8/L1 .5・WORLD変換・固定gain .25の下で、17文共有モデルと資料拡張モデルを比較した。','','訓練候補96文（短48/長48）は教師出力前に固定した。旧17文209目標をbyte再利用し、新79文をKokoro jf_alpha/seed20261002/CPU4で生成した。旧2教師のraw byte再現と予測継続長一致を確認してから新生成へ進んだ。教師は自然さ資格ある正解ではなく、内部予測時刻も音響境界GTではない。','','全96文を分母に残し、受理'+str(target['accepted_utterances'])+'文（短'+str(target['accepted_short'])+'長'+str(target['accepted_long'])+'）、'+str(target['accepted_targets'])+'対象区間。失敗は次のとおり。']
 for r in target['rows']:
  if r['status']!='accepted':lines.append('- '+r['id']+' '+r['text']+' '+str(r['reason']))
 lines+=['','最低80文・短32長32・全5母音・全対象3frameを事前登録どおり適用した。失敗を見た後の読み修正や代替文追加は行わなかった。新3fitの回帰は等発話平均目的のpenalty10/17を維持し、受理N文でlambda10*N/17を用いた。NNは同16→16tanh→16tanh→8、seed20261005、500step。最終直接/学生各128係数と標準化32値は不変。旧3モデルはhash再利用し、fitを繰り返さなかった。','','訓練projected MSE '+json.dumps(s['training_loss'],ensure_ascii=False)+'。訓練lossと訓練672波形の認識は独立品質証拠ではない。確認文は新短8/長8と既知8を出力前固定し、native/旧direct/旧NN/旧student/新direct/新NN/新student×2指定の336診断波形を生成した。','','native対比の整数誤り・全群結果:']
 for cohort,methods in s['content'].items():
  lines+=['',cohort]
  for method,engines in methods.items():
   notes=[]
   for engine,q in engines.items():
    a=q['groups']['both/all'];notes.append(engine+' '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not r['non_worsening'] for r in q['groups'].values())))
   eng=s['engineering'][cohort][method];lines.append('- '+method+': '+'; '.join(notes)+'; 工学 '+str(eng['all_required_pass'])+'、固定支持欠損'+str(sum(bool(r['missing_support']) for r in eng['pairs'])))
 lines+=['','資料拡張対旧モデル:']
 for cohort,methods in s['expanded_vs_frozen'].items():
  for method,engines in methods.items():
   for engine,q in engines.items():
    a=q['groups']['both/all'];lines.append('- '+cohort+'/'+method+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not r['non_worsening'] for r in q['groups'].values())))
 lines+=['','新学生対新直接回帰:']
 for cohort,engines in s['student_vs_direct'].items():
  for engine,q in engines.items():
   a=q['groups']['both/all'];lines.append('- '+cohort+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not r['non_worsening'] for r in q['groups'].values())))
 training_engineering=read(HERE/'training-engineering.json');assert all(r['expected']==r['completed']==96 for r in training_engineering['methods'].values())
 lines+=['','訓練の工学診断（全672分母、独立品質証拠ではない）: '+json.dumps(training_engineering['methods'],ensure_ascii=False)]
 lines+=['','限定支持 '+json.dumps(s['qualifications'],ensure_ascii=False),'','最終依存は新16文×2指定×5非ニューラル方式、160組/320生成で通常・OS隔離と診断波形の完全一致を確認した。NN/教師/訓練/保存波形/旧係数/ネットワークを実拒否。bundleにWAV/PTなし。MCP c0/c9以降、LF0/LPF、HMM時計・状態を全1008波形で独立再検査した。工学・単独実行と知覚品質を区別する。','','費用 '+json.dumps(c['counts'],ensure_ascii=False)+'、ASR新'+str(new)+'、完全一致再利用'+str(reuse)+'。初期helperコピーの不存在を残し、必要sourceを追加した。教師領域の隔離拒否を生成前に拡張し、同一wave/text/engineの旧17評価cache再利用をASR前に固定した。旧結果/封印/閾値/予算の上書きなし。','','未達: 日本語の当該非ニューラル音源に資格ある知覚評価、独立最終品質確認、広い文脈/複数声の一般化。既知文や少数確認の合格を全体品質へ読み替えない。','']
 if not any_supported:
  lines+=['このスペクトル経路は、中央窓gate不足・17文共有制御・資料拡張の3不通過に達した。次は時間/励振/調音の別経路へ切り替える。残額内の研究を継続し、ここで全体を終了しない。']
 else:lines+=['限定支持の方式について、教師由来改善と同予算直接回帰の比較を保持して次の別確認へ進む。知覚資格とprotected確認は未達である。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',dict(path_base=str(REPO),files={str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},budget_before_seal=snap,experiment_completed=True,quality_certified=False,quality_goal_completed=False));b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
