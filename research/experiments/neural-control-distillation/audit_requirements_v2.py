"""ファイルの存在だけではなく、計画要件ごとの実際の証拠と限界を再点検する。"""
import json
import time
from collections import Counter
from pathlib import Path
from budget import ROOT,RESULT,save,digest
from post_pilot import PostBudget,POST


def read(name):return json.loads((RESULT/name).read_text())


def main():
    with PostBudget().job('audit','計画の要件別完了監査v2',3000000):
        repo=ROOT.parents[2];seal=read('artifact-seal.json')
        changed=[name for name,sha in seal['files'].items() if not (repo/name).is_file() or digest(repo/name)!=sha]
        if changed:raise ValueError('封印したpilot成果に変更があります: '+str(changed))
        models=read('model-selection.json')
        model_ok=all(digest(ROOT/r['path'])==r['sha256'] for r in models['chosen'].values())
        teacher=read('teacher-provenance.json')
        teacher_ok=all(digest(ROOT/r['path'])==r['sha256'] for r in teacher['files'])
        rows=read('splits.json')['rows'];split_counts=Counter(r['split'] for r in rows)
        unique=len({r['text'] for r in rows})==24
        main=read('main-comparison-summary.json');comp=main['rows']
        # 数値そのものと個別記録を検査する。存在だけを合格に変換しない。
        asr_count=len(list((RESULT/'content').glob('*/*.json')))
        content_checks={k:r['content_protection_pass'] for k,r in main['contrasts'].items()}
        renders=list((RESULT/'hts-transfer-gain-v2').glob('new-*/*.json'))
        gain_pass=len(renders)==16 and all(json.loads(p.read_text())['evaluation']['E0_pass'] for p in renders)
        runtime={name:read(name) for name in ['runtime-audit.json','hts-runtime-audit-v2.json']}
        runtime_checks={name:len(r['rows'])==4 and all(x['same_float64'] and all(not y['forbidden_imports'] for y in x['runs']) for x in r['rows']) for name,r in runtime.items()}
        events=PostBudget().events();start=[e for e in events if e['event']=='start'];end={e['id']:e for e in events if e['event']=='finish'}
        train_end=max(e['epoch']+end[e['id']]['seconds'] for e in start if e['kind']=='train')
        audit_render_start=min(e['epoch'] for e in start if e['kind']=='render' and '/handwritten' in e['label'] and e['label'].startswith('audit-'))
        manifest_files={name:read(name+'/manifest.json') for name in ['bundle','hts-bundle-v2']}
        final_ok=all(not any(Path(f).suffix in ('.wav','.pt','.pth','.onnx','.npz') for f in m['files']) and all(digest(RESULT/name/f)==sha for f,sha in m['files'].items()) for name,m in manifest_files.items())
        requirements=[]
        def add(section,requirement,status,evidence,scope):requirements.append({'plan_section':section,'requirement':requirement,'status':status,'evidence':evidence,'scope':scope})
        add('1,5','最終生成は非ニューラル、発話別音声/高密度軌跡を最終資産へ持ち込まない','verified' if final_ok else 'failed',['bundle/manifest.json','hts-bundle-v2/manifest.json'],'許可リストと内容ハッシュを再検査。固定共有回帰とVTL/古典HMM。依存ライブラリの全実装を形式検証したわけではない')
        add('3,8','教師コード・重み・声・由来・固定版とローカル実行費','verified' if teacher_ok else 'failed',['teacher-provenance.json','teacher-load-verification.json','cost-audit.json'],'来歴に列挙された5ファイルの実ハッシュ一致。別教師の成功は未検証')
        add('5,6B,8','事前の開発/選別/監査分割と監査によらない学習','verified' if unique and split_counts=={'development':12,'selection':6,'audit':6} and model_ok and train_end<audit_render_start else 'failed',['splits.json','model-selection.json','ledger.jsonl','train_controls.py'],'24文は非重複。学習完了は監査レンダーより前。教師音声/内部時間の一括作成はそれ以前で、モデル学習コードは開発と選別のみ使用')
        add('5','音素・前後文脈・モーラ/句位置・アクセントから低次元制御','verified',['control-schema.json','shared_control.py','models/direct_non_neural.json'],'継続長/F0のみ。101特徴、各202回帰係数。実行時F0/速度指定の品質一般化は未認定')
        add('5','閉鎖・開放・摩擦・鼻腔・声質・母音遷移の拡張','incomplete',['renderer.py','control-schema.json'],'日本語r側音近似、uと無声化未校正。継続長/F0の結果を他の制御の完了へ拡張しない')
        add('6A','自然音声・教師・共有規則・参照適合・蒸留の比較','verified',['natural-comparison/protocol.json','main-comparison-summary.json','extended-comparison-summary-v2.json'],'自然参照は既知開発の3話者。自由適合は全体2倍率に限定され、調音モデルの到達上限を証明しない')
        add('6A','同じ制御をニューラル生成器へ与える対照','not-implemented',['control-schema.json','teacher-provenance.json'],'計画上は実装可能な場合。KokoroへVTLの調音制御を同一意味で与える経路はなく、ニューラル制御器の比較とは別')
        add('6A','WORLD再合成による生成機構の切り分け','verified',['world-provenance.json','extended-comparison-summary-v2.json'],'6監査文の高密度参照依存再合成。未知文用共有制御とは数えない')
        add('6B','直接非ニューラル・ニューラル制御・蒸留を同じ資料/実生成予算で比較','verified' if model_ok and len(comp)==120 and asr_count==144 else 'failed',['model-selection.json','main-comparison-summary.json','content'],'同一VTL上の全24文×5条件。教師を含む144 ASR。HMM追加対照は後続診断として区別')
        add('6B','文章・語彙・音素文脈の一般化','limited',['splits.json','extended-comparison-summary-v2.json'],'監査内容語12種は未出、三つ組55/64未出。未学習音素もあり、日本語全体の品質通過ではない')
        add('6B','F0/速度組合せ、複数教師/自然参照の一般化','incomplete',['runtime-audit.json','natural-comparison/protocol.json'],'未知指定で工学生成のみ。単一教師での短文品質を速度別・複数教師へ外挿しない')
        add('6C','失敗に応じた分岐、再調整せずに保存','verified',['main-comparison-summary.json','hts-transfer/protocol.json','hts-transfer-gain-v2/protocol.json'],'VTL内容不通過→WORLD/HTS対照→新4文HMM移行。出力利得の修正は同じ文の修正検査として明示')
        add('7','E0・制御範囲・再実行・費用・メモリ','limited' if gain_pass else 'failed',['renderer-qualification.json','fit-qualification.json','hts-transfer-gain-v2','hts-runtime-audit-v2.json'],'最終候補の実施済み条件は通過。任意入力の一律保証ではない')
        add('7','内容保護と別方式ASR監査','failed-for-vtl',['main-comparison-summary.json','extended-comparison-summary-v2.json'],str(content_checks)+'。HMM4文は両ASRで改善/維持だが小標本、修正再利用あり')
        add('7','F0・長さ・帯域・有声比・多解像度スペクトル','verified',['main-comparison-summary.json','extended-comparison-summary-v2.json'],'整列距離はWORLD同一時間軸のみ。発声の自然さを証明しない')
        add('7','VOT・局所遷移の信頼できる計測','failed-qualification',['post-pilot/local-events/protocol.json','post-pilot/local-events/summary.json'],'外部公称VOT30件で工学診断不通過。指令時刻・エネルギー開始を破裂の正解としない')
        add('7','知覚指標の日本語/方式別資格・事前の非劣性幅','unavailable',['post-pilot/public-evidence-review.json','protocol.json'],'言語・発話/歌声・生成方式が違う公開MOSを自動転用しない。適格な個票/波形組と推定器の独立性が未確認')
        add('7','品質判定器の正負経路','limited',['quality_gate.py','tests.json','quality-decision.json'],'人工fixtureの分岐は通過。実証拠の対象資格と独立確認が未充足なので、実音声の合格はない')
        add('8','1 campaign、失敗/再試行を含む予算上限と管理費','verified',['contract.json','cost-audit.json','post-pilot/ledger.jsonl','management-benchmark.json'],'過去台帳を保全し合算。差分計数の外部書込見落としを検出、全対象領域照合を維持')
        add('9','依存遮断と未知入力での最終実行','verified' if all(runtime_checks.values()) else 'failed',list(runtime_checks),'各4組のOS隔離/通常波形一致。HMM2文のうち1文は工学修正で再利用、独立品質確認とは別')
        add('9','成果・失敗例・来歴・再現コマンド・結論','verified',['artifact-seal.json','cost-audit.json','dependency-manifest.json','../../../docs/note/neural-assisted-non-neural-speech-pilot-result-2026-10-02.md'],'pilotの実施記録は保全。品質の達成を証明する最終確認は未実施')
        add('旧計画1,6.3,7P5 / 新計画7','独立未使用条件で適用資格内の最終品質ゲート通過','incomplete',['quality-decision.json','completion-audit.json'],'工学確認・音響改善・内容改善の各観測を自然さの目標到達へ置換しない')
        save(POST/'requirements-audit-v2.json',{'requirements':requirements,'original_sealed_files_verified':len(seal['files']),
             'original_changed':changed,'teacher_files_verified':teacher_ok,'model_hashes_verified':model_ok,
             'all_requirements_met':False,'previous_turn_classification':'progress',
             'no_new_generation_or_ai':True,'remaining_constraints':['AI評価残り1では新しい比較/校正一式を実行できない',
                    '日本語の候補生成方式に適用資格を与える独立評点/境界資料が取得・検証できていない'],
             'goal_status':'active','reason':'品質と局所測定の要件が未達。完了へ変更しない'})
    events=PostBudget().events();counts=Counter()
    for e in events:
        if e['event']=='start':counts[e['kind']]+=e.get('count',1)
    save(POST/'cost-snapshot.json',{'counts':dict(counts),'elapsed_seconds':time.time()-read('contract.json')['started_epoch'],
                                  'inventory':PostBudget().inventory(),'limits':read('contract.json')['limits']})
    print(json.dumps({'requirements':len(requirements),'sealed_files_preserved':len(seal['files']),'all_requirements_met':False,'counts':dict(counts)},ensure_ascii=False))


if __name__=='__main__':main()
