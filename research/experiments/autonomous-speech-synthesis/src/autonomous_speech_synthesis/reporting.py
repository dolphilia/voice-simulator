"""証拠不足・工程未達を成功と混同しない報告。"""
from collections import Counter
import json
import numpy as np
from .io import read,write_once,ROOT,file_hash


def report(campaign):
    path=campaign.path
    trials=campaign.results()
    counts=Counter(r["stage"] for r in trials)
    failures=[r for r in trials if not r["evaluation"]["E0_pass"]]
    p2=read(path/"p2-search.json") if (path/"p2-search.json").exists() else {}
    p34=read(path/"p34-speech.json") if (path/"p34-speech.json").exists() else {}
    isolate=read(path/"isolation.json") if (path/"isolation.json").exists() else {}
    decision={"campaign":path.name,"state":"inconclusive","quality_goal_achieved":False,"cycle_ended":True,
              "engineering_state":"signal-qualified" if p34 and all(r["evaluation"]["E0_pass"] for r in trials if r["candidate_id"]=="speech-gestures") else "inconclusive",
              "scope":campaign.config["scope"],"completion_conditions":{"unknown_sentence_generated":isolate.get("passed",False),"reference_and_AI_free_execution":isolate.get("passed",False),"required_quality_gates_passed":False,"reproducible_report":True},
              "reasons":["日本語の物理/規則合成に対する自然さ代理評価器の資格が不足","音素認識・短文CERと自然参照分布の必須ゲートが未達","かな入力を超える任意日本語テキスト品質は対象外"],
              "stage_status":{"P0":"implemented","P1":"numerical-qualified-perception-inconclusive","P2":"pilot-completed","P3":"engineering-only","P4":"engineering-only","P5":"engineering-isolation-only-quality-confirmation-unopened"},
              "trial_counts":dict(counts),"failed_trial_count":len(failures),"selected":p2.get("chosen",[]),"legacy_listener_status_changed":False,
              "next_action":"新しい探索を追加する前に独立した日本語内容・知覚評価の校正資料を確保する。未開封確認群を維持。","automatic_branch":"全必須知覚指標が未資格のため機構診断を完了し研究cycleを閉じる。品質完了とはしない。"}
    write_once(path/"decision.json",decision)
    lines=["# 無人非ニューラル音声研究 実行報告", "",f"campaign: `{path.name}`。判定: **inconclusive（品質目標未達）**。", "",
           "母音・VV・主要子音・短文を共有規則から生成し、別プロセスで未知のかな文を再生成した。信号が成立することを、自然な日本語音声が完成したことへ読み替えない。", "", "## 実行結果", "",
           "| 工程 | 結果 |", "|---|---|",
           *[f"| {k} | {v} |" for k,v in decision["stage_status"].items()], "",
           f"台帳の完了試行: {len(trials)}、E0失敗または実行失敗: {len(failures)}。失敗も予算に含む。", "",
           "## 評価と限界", "",
           "E0は非有限値・clipping・DC・全体無音・継続長・端点を検査する。F0は既知周期信号で資格を点検した。帯域残差は診断に限定し、MOS/CERへ換算していない。", "",
           "JVSは保存済み履歴を走査し、話者と文IDの双方を分割した。リポジトリ外の既知/未知は証明できない。自動alignmentは±10msで摂動し、短すぎる/不安定な母音を除外して率を残した。声道長の厳密整合とラベルの独立確認は未実施。", "",
           "P2は音源→声道→共同の共有制御探索と同数の無作為対照。設定を条件ごとに取り替えた非共有oracleも保存したが、波形自由適合の上限を測ったとは主張しない。seedとフレームを独立話者として数えていない。", "",
           "P3/P4では鼻腔結合近似、閉鎖、摩擦、破裂、促音、撥音、長音、無声化、アクセント核、句内F0を実装した。音素ごとの明瞭性・VOT/調音妥当性・混同行列・ASRのCER・TTSDS2は未資格または未実施であり、工程の品質通過は認定していない。", "",
           "かな前段の助詞表記は発音通りに入力する。漢字解析・辞書アクセントは未接続。外部未知入力も拒否を結果に残し、任意文章対応とはしない。", "", "## 選別候補", ""]
    for item in p2.get("chosen",[]):
        lines.append(f"- `{item['candidate_id']}`: 診断残差 {item['loss']:.6f}、coverage {item['coverage']:.3f}。共有係数 `{json.dumps(item['parameters'],ensure_ascii=False)}`。")
    lines += ["", "## 生成単独実行", "",f"監査フックと生成モジュール静的検査: `{isolate.get('passed',False)}`。同じ入力でfloat64出力ハッシュを比較した。OSのアクセス拒否確認は `os-isolation.json` があれば併読する。", "",
              "移出内容は `bundle/`、共有設定は `voice-config.json`。録音・重み・発話辞書・保存済み制御軌跡を含まない。WAVと制御ログは実行時に生成する。VTLは研究比較のみで、移出bundleに含めていない。", "", "## 実測コスト", "", "| backend | 完了試行数 | 中央値RTF（評価を含む） |", "|---|---:|---:|"]
    for backend in sorted({r["backend"] for r in trials}):
        group=[r for r in trials if r["backend"]==backend]
        rtfs=[r["rtf"] for r in group if "rtf" in r]
        lines.append(f"| {backend} | {len(group)} | {np.median(rtfs) if rtfs else float('nan'):.4f} |")
    lines += ["", "## 再現", "", "リポジトリルートで実行。DSPは既存の `research/.venv`、AI評価は実験専用の `.venv-eval` に分離する。", "", "```bash",
              "research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py status --campaign "+path.name,
              "research/.venv/bin/python -m unittest discover -s research/experiments/autonomous-speech-synthesis/tests -v",
              "research/.venv/bin/python research/experiments/autonomous-speech-synthesis/run.py run --campaign "+path.name,
              "```", "", "同一IDの再実行は保存済み試行を検証して再利用する。コード・設定・環境が違う場合は同じIDで再開しない。新規の再現は別IDを使い、確認データの使用履歴は引き継ぐ。", "",
              "## 残る完了条件", "",*['- '+r for r in decision["reasons"]],"", "計画の完了条件は達成していない。試聴回答を待つ工程は追加していない。"]
    report_path=path/"report.md"
    if not report_path.exists():report_path.write_text("\n".join(lines)+"\n")
    return decision
