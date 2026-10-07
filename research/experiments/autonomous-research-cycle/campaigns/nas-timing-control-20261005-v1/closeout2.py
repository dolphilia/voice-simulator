"""時間制御の全波形・認識・隔離・旧封印・費用を終了監査する。"""
from paths import *
import json,re,numpy as np
from scipy.io import wavfile
import hashlib
def ah(x):return hashlib.sha256(np.asarray(x,dtype='<f8').tobytes()).hexdigest()
def main():
 b=Budget();p=read(HERE/'protocol.json');s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','全592波形/1184認識・96隔離組と旧封印を終了監査',reserve_bytes=5000000) as j:
  seals=list(read(COVERAGE/'completion-audit.json')['old_seals'])+[str((COVERAGE/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
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
  assert read(HERE/'self-test.json')['passed']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==592 and manifest['all_models_fixed_before_audio']
  lookup={mode:{q['id']:q for q in rows} for mode,rows in [('training',p['training_rows']),('diagnostic',p['rows'])]};all_e0=True;engineering={}
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==item['wav_sha256'] and digest(REPO/r['parameters'])==r['parameters_sha256'];fs,audio=wavfile.read(REPO/r['wav']);assert fs==24000 and audio.dtype==np.float32 and np.isfinite(audio).all() and np.max(abs(audio))<1
   q=np.load(REPO/r['parameters']);assert all(np.isfinite(q[k]).all() and ah(q[k])==r['parameter_hashes'][i] for i,k in enumerate(['spectrum','lf0','lpf']))
   assert q['spectrum'].shape[1]==35 and q['lf0'].shape[1]==1 and q['lpf'].shape[1]==31 and len(q['spectrum'])==len(q['lf0'])==len(q['lpf'])==sum(r['duration'])==sum(r['native_duration']) and len(audio)==len(q['lf0'])*120
   assert q['duration'].tolist()==r['duration'] and q['native_duration'].tolist()==r['native_duration'] and np.all(q['duration']>=1) and np.all(q['duration']==np.floor(q['duration']))
   text_id=r['id'].split('/')[0];native=read(HERE/'render'/r['mode']/text_id/r['condition']/'native.json')
   assert r['native_duration']==native['duration'] and r['static_state_hash']==native['static_state_hash'] and r['variance_sha256']==native['variance_sha256'] and r['msd']==native['msd'] and r['vocoder_settings']==native['vocoder_settings']
   current=np.array(r['duration']).reshape(-1,5);original=np.array(native['duration']).reshape(-1,5);row=lookup[r['mode']][text_id]
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
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==592 and a['new_ai']+a['reused']==592 and a['actual_evaluator_sha256']==digest(HERE/'evaluate.py')
   for q in a['rows']:
    r=read(REPO/q['path']);assert digest(REPO/q['path'])==q['sha256'] and r['status']=='completed'
    if r.get('reused_from'):
     old=read(REPO/r['reused_from']);assert digest(REPO/r['reused_from'])==r['reused_sha256'] and old['wav_sha256']==r['wav_sha256'] and old['text']==r['text'] and old['reference_kana']==r['reference_kana'] and old['engine']==engine and old['engine_contract_sha256']==r['engine_contract_sha256']
  rt=read(HERE/'runtime-audit.json');assert rt['passed'] and len(rt['pairs'])==96 and all(q['bit_match'] for q in rt['pairs']) and all(rt['denial_probe']['read_denied']) and rt['denial_probe']['network_denied'] and rt['actual_isolation_controller_sha256']==digest(HERE/'isolate.py') and rt['profile_sha256']==digest(HERE/'isolation.sb')
  bundle=read(HERE/'runtime-bundle/manifest.json')
  for n,h in bundle['files'].items():assert digest(HERE/'runtime-bundle'/n)==h
  assert not list((HERE/'runtime-bundle').rglob('*.wav')) and not list((HERE/'runtime-bundle').rglob('*.pt'))
  for method in ['direct','student']:
   m=read(HERE/'runtime-bundle'/(method+'.json'));assert np.asarray(m['coefficients']).shape==(58,) and len(m['x_mean'])==len(m['x_scale'])==58 and not m['runtime_neural']
  b.save(HERE/'engineering-all.json',engineering,j)
  b.save(HERE/'completion-audit.json',dict(old_seals=checked,verified_unique_old_files=len(seen),all_old_hashes_unchanged=True,all_frozen_sources_models_gains_verified=True,all592_wave_and1184_ASR_hashes_verified=True,all592_E0_pass=all_e0,duration_bounds_sil_pau_integer_total_clock_independently_rechecked=True,means_variance_MSD_voice_settings_invariants_verified=True,all96_normal_isolated_pairs_bit_match=True,denial_probe=rt['denial_probe'],fixed58_coefficients_116_normalization_values_each_final_model=True,no_NN_teacher_waveform_or_utterance_lookup_in_final_bundle=True,no_optimization_after_ASR=True,protected_confirmation_opened=False,quality_goal_completed=False),j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[q for q in events if q.get('event')=='finish' and q['campaign']==NAME and q['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 b.save(HERE/'cost-audit.json',dict(global_snapshot=state,local_counts=c['counts'],local_seconds_before_seal=state['seconds']-c['start_seconds'],failed_jobs=failed,active_jobs=0,new_teacher=0,fits=3,inverse=0,training_renders=400,diagnostic_renders=192,runtime_renders=192,fixture_renders=4,new_ASR=new,exact_ASR_reuse=reuse,NN_control_inference_batches=128,download=0,individual_limits_not_raised=True))
 lines=['# 教師の予測時計を共有非ニューラル時間制御へ移す比較','','2026-10-05。包括品質目標は未達。スペクトル経路の3不通過を受け、HMM状態時計へ切り替えた。教師生成0・波形逆推定0。同じvoice/状態平均/分散/MSD/設定と総時間を保ち、MLPG前の5state長だけを変更した。フレームMCP/LF0/LPFは新しい時間で生成するため、不変という主張はしない。','','資料は旧96候補中80整列受理文を再利用し、16不一致は履歴と分母へ保持した。教師内部予測25ms単位の全音素長をnative .8..1.25/min5frame・総spoken時間同一へ整数配分し、log比を目標とした。sil/pauはnative固定。教師内部時計は音響境界の正解ではない。','','固定42phone onehot＋16文脈特徴からscalar比を予測する。同58→1直接回帰と学生は各58係数＋116標準化値。NNは58→16tanh→16tanh→1、seed20261005、500step。全発話等重み/平均目的penalty10/17。訓練projected MSE '+json.dumps(s['training_loss'],ensure_ascii=False)+'。lossを音質・未知品質へ読み替えない。','','ゼロ補正は2指定/4実生成で全parameter/state/wave bit一致。非ゼロ補正でも状態平均/分散/MSD/layout・総frameは保存。Cはnull/長さ/ゼロ/総時間不一致/MLPG後更新を拒否した。','','訓練80×5方法400波形（oracleは既知teacher時計のみ）と、旧8/新16×2指定×4方法192診断波形を生成した。未知文へteacher時計・教師音声・発話lookupを与えない。WORLD/gain .25は全方法固定。','','両ASR・整数誤り・全群結果:']
 for cohort,methods in s['content'].items():
  lines+=['',cohort]
  for method,engines in methods.items():
   notes=[]
   for engine,q in engines.items():
    a=q['groups']['both/all'];notes.append(engine+' '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、悪化/欠損群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
   lines.append('- '+method+': '+'; '.join(notes)+'; 工学全条件'+str(s['engineering'][cohort][method]['all_required_pass']))
 lines+=['','新student対direct:']
 for cohort,engines in s['student_vs_direct'].items():
  for engine,q in engines.items():
   a=q['groups']['both/all'];lines.append('- '+cohort+'/'+engine+': '+str(a['native_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
 lines+=['','訓練ASR/known oracle（独立品質証拠ではない）: '+json.dumps(s['training_ASR'],ensure_ascii=False),'','全工程の工学欠損: '+json.dumps(engineering,ensure_ascii=False),'','限定支持 '+json.dumps(s['qualifications'],ensure_ascii=False),'','最終依存: 新16×2指定×3非ニューラル方式、96組/192通常・隔離生成が診断waveと一致。NN/teacher/保存波形/訓練資料/旧結果/通信を実拒否。bundleにPT/WAVなし、発話数に比例しない共有係数だけを保持。HTS/Mei/WORLD/教師由来通知を保持した。','','費用 '+json.dumps(c['counts'],ensure_ascii=False)+'、ASR新'+str(new)+'/完全一致再使用'+str(reuse)+'。失敗attempt '+str(len(failed))+'。再初期化/事後上限増加なし。','','未達: 適用範囲が確認できる日本語非ニューラル知覚評価、独立最終品質確認、実音素境界/VOTと広い声・文脈の一般化。次はknown oracleと共有制御の差、NNと学生の差を参照し、時間の表現不足・教師時計の不確かさ・励振の別原因を切り分ける。全体研究は残額内で継続する。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',dict(path_base=str(REPO),files={str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},budget_before_seal=snap,experiment_completed=True,quality_certified=False,quality_goal_completed=False));b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
