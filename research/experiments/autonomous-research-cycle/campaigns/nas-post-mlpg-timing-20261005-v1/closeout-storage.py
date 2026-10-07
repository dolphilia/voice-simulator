"""時間制御の全波形・認識・隔離・旧封印・費用を終了監査する。"""
from paths import *
from storage_budget import StorageBudget
Budget=StorageBudget
import json,re,numpy as np
from scipy.io import wavfile
import hashlib
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def main():
 b=Budget();p=read(HERE/'protocol.json');s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','全896記録/1792認識・160隔離組と旧封印を終了監査',reserve_bytes=5000000) as j:
  seals=list(read(EVENT/'completion-audit.json')['old_seals'])+[str((EVENT/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
  for n in seals:
   q=read(REPO/n);base=Path(q['path_base'])
   for f,h in q['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   checked[n]=dict(sha256=digest(REPO/n),files=len(q['files']))
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h,n
  for n,h in ec['external_generation_sources'].items():assert digest(REPO/n)==h,n
  for n,h in ec['model_hashes'].items():assert digest(HERE/'models'/n)==h,n
  for n,h in p['dependencies'].items():assert digest(REPO/n)==h,n
  assert digest(HERE/'gain-contract.json')==ec['gain_contract_sha256'] and digest(HERE/'protocol.json')==ec['protocol_sha256']
  assert read(HERE/'self-test.json')['passed'] and read(HERE/'runtime-preflight-storage-02.json')['passed']
  voice_header=(BUNDLE/'mei_normal.htsvoice').read_bytes()[:2048].decode('latin1');assert all('VECTOR_LENGTH['+n+']:'+str(v) in voice_header for n,v in [('MCP',35),('LF0',1),('LPF',31)])
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==896 and manifest['all_models_fixed_before_audio']
  lookup={mode:{q['id']:q for q in rows} for mode,rows in [('training',p['training_rows']),('diagnostic',p['rows'])]};all_e0=True;engineering={}
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==item['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'];fs,audio=wavfile.read(REPO/r['wav']);assert fs==24000 and audio.dtype==np.float32 and np.isfinite(audio).all() and np.max(abs(audio))<1
   q=np.load(REPO/r['parameters']);assert all(np.isfinite(q[k]).all() and ah(q[k])==r['parameter_hashes'][i] for i,k in enumerate(['spectrum','lf0','lpf']))
   assert q['spectrum'].shape[1]==35 and q['lf0'].shape[1]==1 and q['lpf'].shape[1]==31 and len(q['spectrum'])==len(q['lf0'])==len(q['lpf'])==sum(r['duration'])==sum(r['native_duration']) and len(audio)==len(q['lf0'])*120
   assert q['duration'].tolist()==r['duration'] and q['native_duration'].tolist()==r['native_duration'] and np.all(q['duration']>=1) and np.all(q['duration']==np.floor(q['duration']))
   text_id=r['id'].split('/')[0];native=read(HERE/'render'/r['mode']/text_id/r['condition']/'native.json')
   assert r['native_duration']==native['duration'] and r['static_state_hash']==native['static_state_hash'] and r['variance_sha256']==native['variance_sha256'] and r['msd']==native['msd'] and r['vocoder_settings']==native['vocoder_settings']
   current=np.array(r['duration']).reshape(-1,5);original=np.array(native['duration']).reshape(-1,5);row=lookup[r['mode']][text_id]
   mask=np.asarray(r['msd']).reshape(-1,5)>.5;mixed=np.any(mask,axis=1)&~np.all(mask,axis=1)
   assert np.array_equal(current[mixed],original[mixed]) and r['mixed_state_duration_fixed']
   if r['variant'].endswith('_post'):
    pre=read(HERE/'render'/r['mode']/text_id/r['condition']/(r['variant'].split('_')[0]+'_pre.json'));assert r['duration']==pre['duration']
    assert r['engine_duration']==r['native_duration'] and not r['engine_state_clock_changed'] and r['native_parameter_hashes']==native['parameter_hashes'] and r['post_warp']['mixed_parameter_blocks_exact']
    source=np.load(REPO/native['parameters']);oldedge=np.r_[0,np.cumsum(original.sum(1))];newedge=np.r_[0,np.cumsum(current.sum(1))]
    for i in np.flatnonzero(mixed):
     for k in ['spectrum','lf0','lpf']:assert source[k][oldedge[i]:oldedge[i+1]].tobytes()==q[k][newedge[i]:newedge[i+1]].tobytes()
    assert np.array_equal(q['lf0'][:,0]>0,np.repeat(np.asarray(r['msd'])>.5,np.asarray(r['duration'])))
   else:assert r['duration_only_state_change'] and r['engine_duration']==r['duration']
   if r.get('reused_render_from'):
    old=read(REPO/r['reused_render_from']);assert digest(REPO/r['reused_render_from'])==r['reused_record_sha256'] and old['wav_sha256']==r['wav_sha256'] and old['parameters_sha256']==r['parameters_sha256'] and old['duration']==r['duration'] and old['text']==r['text']
   for i,label in enumerate(row['full_context_labels']):
    phone=re.search(r'\-([^+]+)\+',label)[1]
    if phone in ['sil','pau']:assert np.array_equal(current[i],original[i])
    else:assert current[i].sum()>=5 and .8-1e-12<=current[i].sum()/original[i].sum()<=1.25+1e-12
   assert r['means_variance_MSD_layout_voice_settings_unchanged'] and r['total_frame_count_fixed'] and r['sil_pau_unchanged'] and r['output_gain']==.25
   if r['variant']=='native':assert r['duration']==r['native_duration'] and not r['state_clock_changed']
   if r['variant']=='oracle':assert r['mode']=='training' and r['teacher_time_control_used']
   else:assert not r['teacher_time_control_used']
   all_e0 &= r['E0_pass']
   key=r['mode']+'/'+r['variant'];a=engineering.setdefault(key,dict(expected=0,E0_pass=0,support_complete=0,missing=[]));a['expected']+=1;a['E0_pass']+=int(r['E0_pass']);a['support_complete']+=int(r['support_complete'])
   if not r['support_complete']:a['missing'].append(dict(id=r['id'],support_missing=r['missing_support']))
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==896 and a['new_ai']+a['reused']==896 and a['actual_evaluator_sha256']==digest(HERE/'evaluate.py')
   for q in a['rows']:
    r=read(REPO/q['path']);assert digest(REPO/q['path'])==q['sha256'] and r['status']=='completed'
    if r.get('reused_from'):
     old=read(REPO/r['reused_from']);assert digest(REPO/r['reused_from'])==r['reused_sha256'] and old['wav_sha256']==r['wav_sha256'] and old['text']==r['text'] and old['reference_kana']==r['reference_kana'] and old['engine']==engine and old['engine_contract_sha256']==r['engine_contract_sha256']
  rt=read(HERE/'runtime-audit.json');assert rt['passed'] and len(rt['pairs'])==160 and all(q['bit_match'] for q in rt['pairs']) and all(rt['denial_probe']['read_denied']) and rt['denial_probe']['network_denied'] and rt['actual_isolation_controller_sha256']==digest(HERE/'isolate-storage-02.py') and rt['actual_isolation_controller_relative_path']==str((HERE/'isolate-storage-02.py').relative_to(REPO)) and rt['profile_sha256']==digest(HERE/'isolation-storage-02.sb')
  assert len(rt['single_CLI_checks'])==4 and all(q['bit_match'] for q in rt['single_CLI_checks'])
  for mode in ['normal','isolated']:
   batch=read(HERE/('runtime-batch-'+mode+'.json'));assert batch['archive_sha256']==digest(HERE/'runtime-archives'/(mode+'.zip')) and batch['synthesis_calls']==batch['E0_calls']==160 and batch['all_match'] and len(batch['records'])==160
   for ident,value in batch['records'].items():
    path=HERE/'runtime-check'/mode/(ident+'.wav');assert digest(path)==value['sha256']==read(HERE/'render/diagnostic'/(ident+'.json'))['wav_sha256']
  for q in rt['single_CLI_checks']:assert digest(HERE/'runtime-cli'/q['mode']/(q['id']+'.wav'))==q['sha256']
  assert len(read(HERE/'training-render-reuse-audit.json')['records'])==320 and sum(bool(read(REPO/q['record']).get('reused_render_from')) for q in manifest['rows'])==320
  bundle=read(HERE/'runtime-storage-bundle/manifest.json')
  for n,h in bundle['files'].items():assert digest(HERE/'runtime-storage-bundle'/n)==h
  assert not list((HERE/'runtime-storage-bundle').rglob('*.wav')) and not list((HERE/'runtime-storage-bundle').rglob('*.pt'))
  for method in ['direct','student']:
   m=read(HERE/'runtime-storage-bundle'/(method+'.json'));assert np.asarray(m['coefficients']).shape==(58,) and len(m['x_mean'])==len(m['x_scale'])==58 and not m['runtime_neural']
  assert b.audit_data_hashes()>=149
  b.save(HERE/'engineering-all.json',engineering,j)
  b.save(HERE/'completion-audit.json',dict(old_seals=checked,verified_unique_old_files=len(seen),all_old_hashes_unchanged=True,all_frozen_sources_models_gains_verified=True,all896_wave_and1792_ASR_hashes_verified=True,all896_E0_pass=all_e0,duration_bounds_sil_pau_integer_total_clock_independently_rechecked=True,means_variance_MSD_voice_settings_invariants_verified=True,same_pre_post_output_clock_independently_checked=True,post_mixed_parameter_blocks_independently_byte_checked=True,post_engine_clock_and_LF0_mask_independently_checked=True,all160_normal_isolated_pairs_bit_match=True,denial_probe=rt['denial_probe'],fixed58_coefficients_116_normalization_values_each_final_model=True,no_NN_teacher_waveform_or_utterance_lookup_in_final_bundle=True,no_optimization_after_ASR=True,protected_confirmation_opened=False,quality_goal_completed=False),j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[q for q in events if q.get('event')=='finish' and q['campaign']==NAME and q['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 assert c['counts'].get('train',0)==c['counts'].get('teacher',0)==c['counts'].get('inverse',0)==0
 b.save(HERE/'cost-audit.json',dict(global_snapshot=state,local_counts=c['counts'],local_seconds_before_seal=state['seconds']-c['start_seconds'],failed_jobs=failed,active_jobs=0,new_teacher=0,fits=0,inverse=0,new_training_renders=240,reused_training_renders=320,new_diagnostic_renders=336,runtime_renders=324,fixture_renders=14,storage_failed_preflight_reserved_renders=2,new_ASR=new,exact_ASR_reuse=reuse,NN_control_inference_batches=176,download=0,individual_limits_not_raised=True))
 lines=['# 同じ時間制御をMLPG前後へ適用する比較','','2026-10-05。品質目標は未達。固定58特徴の直接/NN/学生を再利用し、整数時計をMLPG前後へ適用する位置だけを比較した。新fit・教師・逆推定は0。','','後段では当該文章からnative MLPG列を1度生成し、各HMM状態の中心格子で数値列を補間する。状態を跨ぐ補間はしない。同じ長さならbyte copy、無声LF0はsentinel保持。有声/無声混在音素の全列はnativeのまま保持する。Cエンジン時計と出力時計を区別し、後段補間の動的MLPG制約保存は主張しない。','','資料は旧96候補中80受理・16不一致の履歴を保持。旧4方式320訓練記録を完全一致再使用し、後段3方式240訓練と旧8/新16×2指定×7方式336診断波形を生成した。新16入力は履歴非衝突を出力前固定した。未使用の保護confirmは開いていない。訓練評価は独立品質証拠ではない。','','内容の同基準比較:']
 for cohort,methods in s['content'].items():
  lines+=['',cohort]
  for method,engines in methods.items():
   values=[]
   for engine,q in engines.items():
    a=q['groups']['both/all'];values.append(engine+' '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
   lines.append('- '+method+': '+'; '.join(values)+'; 工学全条件 '+str(s['engineering'][cohort][method]['all_required_pass']))
 lines+=['','同一モデルのMLPG前→後:']
 for cohort,methods in s['post_vs_pre'].items():
  for method,engines in methods.items():
   for engine,q in engines.items():
    a=q['groups']['both/all'];lines.append('- '+cohort+'/'+method+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
 lines+=['','直接→学生:']
 for cohort,policies in s['student_vs_direct'].items():
  for policy,engines in policies.items():
   for engine,q in engines.items():
    a=q['groups']['both/all'];lines.append('- '+cohort+'/'+policy+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters']))
 lines+=['','限定条件 '+json.dumps(s['qualifications'],ensure_ascii=False)+'。nativeのTrueは同一基準の比較成立だけを示し、最終品質の認定ではない。','','訓練ASR（独立品質ではない）: '+json.dumps(s['training_ASR'],ensure_ascii=False),'','E0/支持欠損: '+json.dumps(engineering,ensure_ascii=False),'','全896波形/parameter・1792認識、160通常/隔離組・単独CLI4件と旧封印を検査した。最終bundleは各58係数+116正規化値の2モデルとHTS/Mei/WORLD/状態内補間。NN重み、教師/参照音声、保存軌跡、発話lookup、通信への依存を拒否した。既知6自己回復/旧4batch/外部4batchは工学fixtureであり品質証拠ではない。','','費用 '+json.dumps(c['counts'],ensure_ascii=False)+'。新ASR'+str(new)+'、完全一致再使用'+str(reuse)+'、失敗attempt'+str(len(failed))+'。外部archive予約100MBと展開予約80MBを別に確保し、まとめてもrender/DSP回数を減らしていない。campaign上限の事後引上げなし。','','未達: 日本語非NNの知覚資格、独立最終品質確認、音響境界/VOTの正解、指定値に対する実F0校正、広い声・文脈への一般化。220/280入力は220基準の半音指定であり実測中央値Hzの保証ではない。','','時間制御はこの比較を含め3件。全候補不通過なら同時計の微調整を打ち切り、励振/APまたは独立したF0指定校正の経路へ移る。包括研究の完了へ読み替えない。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',dict(path_base=str(REPO),files={str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},budget_before_seal=snap,experiment_completed=True,quality_certified=False,quality_goal_completed=False));b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
