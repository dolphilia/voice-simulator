"""固定境界対照の全分母、旧封印、実費を監査して封印する。"""
from paths import *
import json

def main():
 b=Budget();s=read(HERE/'summary.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','旧全封印・240境界音声・480認識・payload検査の終了監査',reserve_bytes=2500000) as j:
  seals=list(read(JP/'completion-audit.json')['old_seals'])+[str((JP/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
  for n in seals:
   seal=read(REPO/n);base=Path(seal['path_base'])
   for f,h in seal['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   checked[n]={'sha256':digest(REPO/n),'files':len(seal['files'])}
  assert digest(JP/'artifact-seal.json')==ec['prior_artifact_seal_sha256'] and digest(JP/'execution-contract.json')==ec['prior_dependency_contract_sha256']
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h,n
  for n,h in ec['old_teacher_dependency_hashes'].items():assert digest(REPO/n)==h,n
  assert digest(HERE/'registration.json')==ec['registration_sha256'] and digest(HERE/'protocol.json')==ec['protocol_sha256']
  a=read(HERE/'prepare-amendment-01.json');assert digest(HERE/'prepare.py')==a['original'] and digest(HERE/'prepare2.py')==a['repaired']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==240
  for item in manifest['rows']:
   r=read(REPO/item['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==item['wav_sha256'] and digest(REPO/r['DIO_file'])==r['DIO_sha256']
   assert r['boundary']['interior_payload_exact'] and r['source_payload_checks_except_endpoint_pass']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==240 and a['new_ai']+a['reused']==240
   for q in a['rows']:
    r=read(REPO/q['path']);assert digest(REPO/q['path'])==q['sha256'] and r['status']=='completed'
    if r.get('reused_from'):
     source=read(REPO/r['reused_from']);assert digest(REPO/r['reused_from'])==r['reused_sha256'] and source['wav_sha256']==r['wav_sha256'] and source['text']==r['text'] and source['reference_kana']==r['reference_kana']
  proof={'old_seals':checked,'verified_unique_old_files':len(seen),'all_old_hashes_unchanged':True,'all_frozen_sources_and_reused_dependency_hashes_unchanged':True,'all_240_wave_analysis_and_480_ASR_hashes_verified':True,'exact_ASR_reuse_checked':True,'all_middle_payload_and_clock_checks_passed':True,'no_selection_or_optimization_after_ASR':True,'protected_confirmation_opened':False,'final_text_runtime_qualification_not_claimed':True,'quality_goal_completed':False}
  b.save(HERE/'completion-audit.json',proof,j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed'];new=sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']);reuse=sum(read(HERE/('asr-manifest-'+e+'.json'))['reused'] for e in ['whisper','reazon'])
 b.save(HERE/'cost-audit.json',{'global_snapshot':state,'local_counts':c['counts'],'local_seconds_before_seal':state['seconds']-c['start_seconds'],'failed_jobs':failed,'active_jobs':0,'teacher_calls_new':16,'analysis_resynthesis_renders':16,'boundary_renders':240,'ASR_new':new,'ASR_reused':reuse,'download_charged':c['counts'].get('download',0),'optional_raw_source_download_actual':0,'new_fits':0,'new_inverse':0,'individual_limits_not_raised':True})
 lines=['# 音声境界処理と内容認識の比較結果','','2026-10-05。旧診断12文と出力前固定の新8文、二教師と各WORLD再合成に対し、raw、前後.9秒無音、12ms線形端点taper＋同無音を比較した。教師は新16生成、WORLD新16生成、旧48音声再利用。240境界音声を二認識器で評価し、完全同波形・同text・同reading・同engine契約の旧/同run結果だけ厳密再利用した。','','Reazon公式K2 transcribe.pyはPAD_SECONDS=.9を用い、audio.pyのpad_audioは16k mono正規化の後に両側constant paddingする。今回は24k波形境界処理を二認識器に共通適用した対照で、公式resample入口全体と同一ではない。[公式transcribe.py](https://github.com/reazon-research/ReazonSpeech/blob/master/pkg/k2-asr/src/transcribe.py)、[公式audio.py](https://github.com/reazon-research/ReazonSpeech/blob/master/pkg/k2-asr/src/audio.py)。webで一次ソースを確認。任意のローカル原本保存はsandbox DNS拒否で失敗し、原本hashは未取得。失敗の保守予約100KBは計数し、枠を事後増加しなかった。','','paddingはspeechの全sampleを保持する。taperは両端各288sampleだけ変更し中間payloadを保持する。全長を正確に+43200sampleし、speech offset .9秒を記録した。追加peak正規化はしなかった。無音外端のE0だけで内部stepを隠さず、埋め込みspeech両端amplitude<=1e-6を工程支持の追加条件にした。これは自然さの測定資格ではない。','','全分母の結果（baseline→candidateの整数誤り、文字数、固定7群の不通過数）:']
 for cohort,comparisons in s['content'].items():
  lines+=['',cohort]
  for name,engines in comparisons.items():
   notes=[]
   for engine,q in engines.items():
    a=q['groups']['all'];notes.append(engine+' '+str(a['baseline_errors'])+'→'+str(a['errors'])+'/'+str(a['characters'])+'、不通過群'+str(sum(not g['non_worsening'] for g in q['groups'].values())))
   lines.append('- '+name+': '+'; '.join(notes))
 lines+=['','新8文の内容全群＋工程支持: '+json.dumps(s['qualifications'],ensure_ascii=False),'','工程結果:']
 for policy in ['raw','pad_900ms','taper12ms_pad900ms']:
  q=[r for r in s['engineering'] if r['condition']==policy];lines.append('- '+policy+': E0 '+str(sum(r['E0_pass'] for r in q))+'/'+str(len(q))+'、埋め込みstep込み '+str(sum(r['joint_engineering_pass'] for r in q))+'/'+str(len(q)))
 lines+=['','旧結果は保持した。旧12文の改善を独立確認へ数えず、新8文の境界対照も広い日本語自然さ・最終共有制御の成功とは扱わない。教師モデル/声/内部正規化差は単一原因に分離していない。WORLD再合成は教師波形を必要とし、非ニューラル未知文生成への移出は未検証。包括品質目標は未達。','','費用: '+json.dumps(c['counts'],ensure_ascii=False)+'。ASR新'+str(new)+'、厳密再利用'+str(reuse)+'。登録上限は増加せず、失敗はcost-auditへ保存した。旧全封印・教師/評価依存を維持した。','','次の経路は新8文の全群と両認識器の結果を基に選ぶ。支持された教師・境界条件があれば、その音素対応/測定検査と低次元共有制御への移出を別campaignで登録し、直接非ニューラル対照とニューラル経由蒸留を同資料で比較する。条件が支持されなければ別教師または合成制御の表現へ切り替え、確認結果を使ったpadding長の探索は行わない。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile();b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':snap,'experiment_completed':True,'quality_certified':False,'quality_goal_completed':False});b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
