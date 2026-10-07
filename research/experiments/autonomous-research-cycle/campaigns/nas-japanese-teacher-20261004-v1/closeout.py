"""日本語教師診断を、品質達成とは分離して封印する。"""
from paths import *
import json,importlib.metadata as metadata

def main():
 b=Budget();p=read(HERE/'protocol.json');ec=read(HERE/'execution-contract.json')
 with b.job(NAME,'audit','教師・48波形・96認識・旧封印・分離環境の終了監査',reserve_bytes=2000000) as j:
  seals=list(read(PREVIOUS/'completion-audit.json')['old_seals'])+[str((PREVIOUS/'artifact-seal.json').relative_to(REPO))];seen={};checked={}
  for n in seals:
   s=read(REPO/n);base=Path(s['path_base'])
   for f,h in s['files'].items():
    path=base/f
    if str(path) not in seen:seen[str(path)]=digest(path)
    assert seen[str(path)]==h,str(path)
   checked[n]={'sha256':digest(REPO/n),'files':len(s['files'])}
  for n,h in ec['source_hashes'].items():assert digest(HERE/n)==h,n
  for n,h in ec['new_dependency_files'].items():assert digest(HERE/n)==h,n
  for field in ['old_teacher_dependency_hashes','fixed_metric_dependencies']:
   for n,h in ec[field].items():assert digest(REPO/n)==h,n
  for n,h in p['dependencies'].items():assert digest(REPO/n)==h,n
  for n,v in ec['old_env_versions'].items():assert metadata.version(n)==v
  assert digest(HERE/'registration.json')==ec['registration_sha256'] and digest(HERE/'protocol.json')==ec['protocol_sha256']
  assert digest(HERE/'teacher-generator-contract.json')==ec['teacher_generator_contract_sha256']
  amendment=read(HERE/'generation-amendment-01.json');assert digest(HERE/'generate-jvnv.py')==amendment['original'] and digest(HERE/'generate-jvnv2.py')==amendment['repaired']
  manifest=read(HERE/'render-manifest.json');assert len(manifest['rows'])==48 and manifest['audio_and_analysis_completed_before_ASR']
  all_e0=True
  for q in manifest['rows']:
   r=read(REPO/q['record']);assert digest(REPO/r['wav'])==r['wav_sha256']==q['wav_sha256']
   assert digest(REPO/r['DIO_file'])==r['DIO_sha256'];all_e0 &= r['E0_pass']
   if r['mode']=='world':assert digest(REPO/r['parameters'])==r['parameters_sha256'] and r['requires_teacher_audio_at_runtime'] and not r['final_text_synthesis']
  for engine in ['whisper','reazon']:
   a=read(HERE/('asr-manifest-'+engine+'.json'));assert len(a['rows'])==48 and a['new_ai']+a['reused']==48
   for q in a['rows']:assert digest(REPO/q['path'])==q['sha256'] and read(REPO/q['path'])['status']=='completed'
  b.save(HERE/'completion-audit.json',{'old_seals':checked,'verified_unique_old_files':len(seen),'all_old_hashes_unchanged':True,'all_frozen_sources_and_dependency_hashes_unchanged':True,'old_environment_versions_unchanged':True,'technical_generation_amendment_verified':True,'all_48_wave_analysis_hashes_verified':True,'all_96_ASR_hashes_verified':True,'all_48_E0_pass':all_e0,'no_fit_or_optimization_after_ASR':True,'teacher_is_research_only':True,'WORLD_requires_teacher_waveform':True,'isolated_final_text_runtime_not_claimed':True,'quality_goal_completed':False},j)
 state=b.snapshot();assert not state['jobs'];c=state['campaigns'][NAME];events=[json.loads(t) for t in (ROOT/'control/jobs.jsonl').read_text().splitlines()];failed=[r for r in events if r.get('event')=='finish' and r['campaign']==NAME and r['status']=='failed'];s=read(HERE/'summary.json')
 b.save(HERE/'cost-audit.json',{'global_snapshot':state,'local_counts':c['counts'],'local_seconds_before_seal':state['seconds']-c['start_seconds'],'failed_jobs':failed,'active_jobs':0,'teacher_calls_new':20,'old_Kokoro_wave_reused':4,'analysis_resynthesis_renders':24,'ASR_new':sum(read(HERE/('asr-manifest-'+e+'.json'))['new_ai'] for e in ['whisper','reazon']),'new_fits':0,'new_inverse':0,'payload_download_bytes_actual':sum(q['bytes'] for q in read(HERE/'payload-audit.json')['files']),'download_charged':c['counts'].get('download',0),'individual_limits_not_raised':True})
 lines=['# 日本語教師とWORLD解析再合成の診断結果','','2026-10-05。固定比較は終了。共有文章制御への移出と知覚品質は未検証で、包括研究の品質目標は未達。','','Style-Bert-VITS2 JP-Extra/JVNV F1 NeutralをKokoro jf_alphaと比較した。モデル全体・声・G2P・内部正規化・依存版の差を含み、日本語学習だけの因果効果ではない。教師の内部attention時間は予測で、音響上の正解ではない。','','既知4文は診断再利用、新短4/長4文は生成前に固定。新教師生成20回と旧Kokoro4波形で教師24音声を用意し、24のWORLD再合成と合わせ48音声を両認識器で評価した。全48波形は同じ24kHz入口・共通.25headroom。WORLDはDIO+StoneMask/5ms、CheapTrick FFT2048、D4C .85を用い、追加gain1・教師sample数へのcropを固定。保存教師音声を必要とする再合成であり、最終文章合成ではない。','','結果（全文字数と整数誤り、固定群の不通過数）:']
 for cohort,comparisons in s['content'].items():
  lines += ['',cohort]
  for name,engines in comparisons.items():
   notes=[]
   for engine,q in engines.items():
    g=q['groups']['all'];notes.append(engine+' '+str(g['baseline_errors'])+'→'+str(g['errors'])+'/'+str(g['characters'])+'、不通過群'+str(sum(not a['non_worsening'] for a in q['groups'].values())))
   lines.append('- '+name+': '+'; '.join(notes))
 lines += ['','限定内容/再合成支持: '+str(s['JVNV_limited_content_and_resynthesis_supported'])+'。E0全48: '+str(all_e0)+'。ASRの平均改善を自然さ認定へ読み替えない。独立最終確認は未開封。','','新依存を専用prefixへ保存し、旧環境・全旧封印を維持した。最初のBERT検査は非persistent position_idsの照合先を修正して再照合した。生成前再読込の監査同値比較は、学習専用未保存キーの集合列挙順だけで失敗したため両側の同リストをソートした。元ソース・失敗・全重み厳密照合は保持し、科学設定や入力を変更していない。','','費用: '+json.dumps(c['counts'],ensure_ascii=False)+'。失敗attemptを含めcost-auditへ保存。キャンペーン上限は開始後変更していない。','','利用条件・モデル由来を保存。コードAGPL-3.0、JVNV/BERT CC-BY-SA-4.0の条件を後続の研究資産にも引き継ぐ。公開・外部配布は本実験では行っていない。','','次は本結果に基づいて共有制御の学習経路を登録する。教師内部時間を音響上の正解として使わず、音素対応とスペクトル表現の測定検査を先に行う。非ニューラル直接対照とニューラル経由蒸留を同じ入力資料で比較し、既知診断とは別の新文章を出力前に固定する。']
 b.write(HERE/'report.md',('\n'.join(lines)+'\n').encode());snap=b.reconcile()
 b.save(HERE/'artifact-seal.json',{'path_base':str(REPO),'files':{str(q.relative_to(REPO)):digest(q) for q in HERE.rglob('*') if q.is_file()},'budget_before_seal':snap,'experiment_completed':True,'quality_certified':False,'quality_goal_completed':False})
 b.close_campaign(NAME);print(b.reconcile(),flush=True)
if __name__=='__main__':main()
