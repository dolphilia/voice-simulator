"""時間制御の全波形・認識・隔離・旧封印・費用を終了監査する。"""
from paths import *
import json,re,numpy as np
from scipy.io import wavfile
import hashlib
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def main():
 b=Budget();p=read(HERE/'protocol.json');s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','全896記録/1792認識・160隔離組と旧封印を終了監査',reserve_bytes=5000000) as j:
  seals=list(read(TIME/'completion-audit.json')['old_seals'])+[str((TIME/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
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
  assert read(HERE/'self-test.json')['passed'] and read(HERE/'runtime-preflight.json')['passed']
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
   if r['variant'].endswith('mixed_fixed'):assert np.array_equal(current[mixed],original[mixed]) and r['mixed_state_duration_fixed']
   if r.get('reused_render_from'):
    old=read(REPO/r['reused_render_from']);assert digest(REPO/r['reused_render_from'])==r['reused_record_sha256'] and old['wav_sha256']==r['wav_sha256'] and old['parameters_sha256']==r['parameters_sha256'] and old['duration']==r['duration'] and old['text']==r['text']
   for i,label in enumerate(row['full_context_labels']):
    phone=re.search(r'\-([^+]+)\+',label)[1]
    if phone in ['sil','pau']:assert np.array_equal(current[i],original[i])
    else:assert current[i].sum()>=5 and .8-1e-12<=current[i].sum()/original[i].sum()<=1.25+1e-12
   assert r['means_variance_MSD_layout_voice_settings_unchanged'] and r['duration_only_state_change'] and r['total_frame_count_fixed'] and r['sil_pau_unchanged'] and r['output_gain']==.25
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
  rt=read(HERE/'runtime-audit.json');assert rt['passed'] and len(rt['pairs'])==160 and all(q['bit_match'] for q in rt['pairs']) and all(rt['denial_probe']['read_denied']) and rt['denial_probe']['network_denied'] and rt['actual_isolation_controller_sha256']==digest(HERE/'isolate.py') and rt['profile_sha256']==digest(HERE/'isolation.sb')
  assert len(rt['single_CLI_checks'])==4 and all(q['bit_match'] for q in rt['single_CLI_checks'])
  for mode in ['normal','isolated']:
   batch=read(HERE/('runtime-batch-'+mode+'.json'));assert batch['archive_sha256']==digest(HERE/'runtime-archives'/(mode+'.zip')) and batch['synthesis_calls']==batch['E0_calls']==160 and batch['all_match'] and len(batch['records'])==160
   for ident,value in batch['records'].items():
    path=HERE/'runtime-check'/mode/(ident+'.wav');assert digest(path)==value['sha256']==read(HERE/'render/diagnostic'/(ident+'.json'))['wav_sha256']
  for q in rt['single_CLI_checks']:assert digest(HERE/'runtime-cli'/q['mode']/(q['id']+'.wav'))==q['sha256']
  assert len(read(HERE/'training-render-reuse-audit.json')['records'])==320 and sum(bool(read(REPO[q['record']]).get('reused_render_from')) for q in manifest['rows'])==320
  bundle=read(HERE/'runtime-bundle/manifest.json')
  for n,h in bundle['files'].items():assert digest(HERE/'runtime-bundle'/n)==h
  assert not list((HERE/'runtime-bundle').rglob('*.wav')) and not list((HERE/'runtime-bundle').rglob('*.pt'))
  for method in ['direct','student']:
   m=read(HERE/'runtime-bundle'/(method+'.json'));assert np.asarray(m['coefficients']).shape==(58,) and len(m['x_mean'])==len(m['x_scale'])==58 and not m['runtime_neural']
  b.save(HERE/'engineering-all.json',engineering,j)
  b.save(HERE/'completion-audit.json',dict(old_seals=checked,verified_unique_old_files=len(seen),all_old_hashes_unchanged=True,all_frozen_sources_models_gains_verified=True,all896_wave_and1792_ASR_hashes_verified=True,all896_E0_pass=all_e0,duration_bounds_sil_pau_integer_total_clock_independently_rechecked=True,means_variance_MSD_voice_settings_invariants_verified=True,all160_normal_isolated_pairs_bit_match=True,denial_probe=rt['denial_probe'],fixed58_coefficients_116_normalization_values_each_final_model=True,no_NN_teacher_waveform_or_utterance_lookup_in_final_bundle=True,no_optimization_after_ASR=True,protected_confirmation_opened=False,quality_goal_completed=False),j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[q for q in events if q.get('event')=='finish' and q['campaign']==NAME and q['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 assert c['counts'].get('train',0)==c['counts'].get('teacher',0)==c['counts'].get('inverse',0)==0
 b.save(HERE/'cost-audit.json',dict(global_snapshot=state,local_counts=c['counts'],local_seconds_before_seal=state['seconds']-c['start_seconds'],failed_jobs=failed,active_jobs=0,new_teacher=0,fits=0,inverse=0,new_training_renders=240,reused_training_renders=320,new_diagnostic_renders=336,runtime_renders=324,fixture_renders=10,new_ASR=new,exact_ASR_reuse=reuse,NN_control_inference_batches=176,download=0,individual_limits_not_raised=True))
 lines=['# 混在有声状態の長さを保つ時間投影の対照','','2026-10-05。包括品質目標は未達。前比較は学生の未知文総誤りが両ASRで減ったが、群悪化と支持欠損が残った。教師の内部時計oracleも訓練ASRを悪化させたため、モデル容量やlossを増やす前に状態長の投影だけを対照とした。','','同じ直接/NN/学生をhash再利用し、新fit/教師/波形逆推定0。新しい投影は、MSD>0.5の真偽が5state内で混在するspoken phoneの状態長をnativeへ固定する。残りの全有声/全無声音素だけで、.8..1.25/min5frame・総時間同一へ整数再配分する。sil/pau固定。DIO/ASR結果・音素名による例外は使わない。','','相対状態長を保っても、音素の絶対開始時刻や隣接MLPG出力・波形が同一とは限らない。状態平均/分散/MSD/layout・voice/settings・総frameだけを不変として検証した。実音素境界/VOTの正解、教師時計の音響資格は未確認。220/280の入力は220を基準にした半音換算の設定であり、実測F0中央値の保証ではない。','','資料は旧96候補中80受理文と16不一致の履歴を保持。旧訓練4方法320記録/波形/parameter/支持を完全一致再使用。新投影3方法240訓練波形、旧8/新16×2指定×7方法336診断波形を新生成した。訓練は独立品質証拠ではない。旧MSE '+json.dumps(s['training_loss'],ensure_ascii=False)+' は新投影の音質認定へ使わない。','','新短8/長8は前ASR結果を見る前に保存したpoolから、全履歴との文章/label非衝突で初出力前に固定。未使用の保護confirmは開かない。','','工学fixture: 新6ゼロ生成が前基準の全parameter/state/waveと一致。非ゼロでも混在状態長固定・総時間・平均/分散/MSDの保存を検査。均一MSDでは元投影と同値、非有限MSDを拒否。まとめ生成は既知2指定×両環境4波形で前基準と一致した。fixtureを品質証拠にしない。','','両ASR・全整数誤り・悪化/欠損群:']
 for cohort,methods in s['content'].items():
  lines+=['',cohort]
  for method,engines in methods.items():
   a=[]
   for engine,q in engines.items():
    g=q['groups']['both/all'];a.append(engine+' '+str(g['native_errors'])+'→'+str(g['errors'])+'/'+str(g['characters'])+'、不通過群'+str(sum(not x['non_worsening'] for x in q['groups'].values())))
   lines.append('- '+method+': '+'; '.join(a)+'; 工学全条件'+str(s['engineering'][cohort][method]['all_required_pass']))
 lines+=['','元投影→混在固定の同モデル因果対照:']
 for cohort,methods in s['policy_vs_original'].items():
  for method,engines in methods.items():
   for engine,q in engines.items():
    a=q['groups']['both/all'];lines.append('- '+cohort+'/'+method+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
 lines+=['','直接→学生の同policy比較:']
 for cohort,policies in s['student_vs_direct'].items():
  for policy,engines in policies.items():
   for engine,q in engines.items():
    a=q['groups']['both/all'];lines.append('- '+cohort+'/'+policy+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
 lines+=['','訓練ASR（独立ではない）: '+json.dumps(s['training_ASR'],ensure_ascii=False),'','全工程のE0/支持欠損: '+json.dumps(engineering,ensure_ascii=False),'','限定条件 '+json.dumps(s['qualifications'],ensure_ascii=False)+'。nativeのTrueは同一基準の比較成立を表し、最終品質の合格ではない。','','最終依存: 新16×2指定×5非NN方法160組。通常/隔離の320waveと単独CLI4waveが診断waveと一致。NN/教師/保存軌跡/旧資料/波形/通信を実拒否し、出力archiveのread-dataも拒否。二つの最終共有モデルは各58係数+116正規化値で、WAV/PT/発話lookupをbundleへ含めない。HTS/Mei/WORLD/教師由来通知を保持。','','管理: 各160waveを1 archiveへ書き、通常/隔離で計320render/320E0を予約した。バッチ化で呼出回数を減らさない。単一ファイルの外部変更検査を維持し、archiveと取り出し書込の両方を計数・保存。batch実時間 '+json.dumps(rt['management_seconds'],ensure_ascii=False)+'。前比較と文章長や方法数が異なるため、これだけを同条件の速度改善認定には使わない。','','費用 '+json.dumps(c['counts'],ensure_ascii=False)+'、新ASR'+str(new)+'/一致再使用'+str(reuse)+'。失敗attempt '+str(len(failed))+'。初期setupの参照場所誤りとpool転記欠落は別版・履歴に保存し、出力前に修正。実記録約21MBの転記は開始前に50MB予約を確保。campaign/包括上限の事後引上げはない。','','未達: 日本語非NN知覚資格、独立最終品質確認、音響境界とVOT、指定値に対する実F0校正、広い声・文脈への一般化。旧不通過・不一致・欠損を消さず、全体研究は残額内で継続する。次は同モデルでのpolicy差を参照して、内部時計の不確かさとイベント内の時間表現、または励振/APの原因へ進む。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',dict(path_base=str(REPO),files={str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},budget_before_seal=snap,experiment_completed=True,quality_certified=False,quality_goal_completed=False));b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
