"""完了済み終了監査を検証し、集計後に封印する。"""
from paths import *
import json

def main():
 b=Budget();s=read(HERE/'summary.json');audit=read(HERE/'completion-audit.json')
 assert digest(HERE/'completion-audit.json')=='dedf993c65aafa96265389f81c8fea3d94d0d737752887c9003105d62b5cdb89'
 assert audit['all_48_wave_analysis_hashes_verified'] and audit['all_96_ASR_hashes_verified'] and audit['all_old_hashes_unchanged']
 all_e0=audit['all_48_E0_pass']
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
