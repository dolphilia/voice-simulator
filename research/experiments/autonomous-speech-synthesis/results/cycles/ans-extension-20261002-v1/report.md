# 追加サイクル終了報告

`ans-extension-20261002-v1`: **inconclusive（品質目標未達）**。承認済み追加3 campaignを終了した。

|campaign|完了レンダー|AI評価|E0失敗|
|---|---:|---:|---:|
|ans-spectral-fit-v1|94|0|0|
|ans-spectral-multistart-v1|1780|108|0|
|ans-vtl-tap-timing-v1|48|27|0|

計1922レンダー、135 AI評価。追加保存量は終了集計時点787,391,110 bytes、経過70.3分。旧封印3,652ファイルのhashは一致。

制約付き自由適合は14条件中13条件で選別話者平均残差を減らしたが、/o/160Hzでは1.0442から1.2311へ増加した。10条件が利得上端の1%以内。自由適合係数は共有生成規則へ移出していない。

舌尖接触時刻の前後8ms変更は、いずれも保護条件に不合格で採用しない。URGENT日本語16話者の評点順位とUTMOS予測の平均相関は0.175（95%区間 −0.122〜0.441）で、物理合成の知覚資格には使わない。

## 完了条件との対応

|条件|現在の証拠|
|---|---|
|unknown_input|既存の限定入力で生成を確認。任意の日本語全体の品質は未検証。|
|reference_AI_free|旧DSP/VTLの隔離生成・波形一致を保持。追加資料の拒否profileはアクセス検査のみ。|
|required_E1_E2_gates|未達。内容誤りと物理合成に対応する独立した知覚資格が残る。|
|P5_quality_adjudication|未実装。現行confirm/reportは工学確認とinconclusiveの保存まで。品質認定の正の経路を完成済みとみなさない。|
|reproducible_report|設定・台帳・結果・コード版・予算・報告を保存。|

## 再現と詳細

- 数値・費用・封印hash: `decision.json`。
- コード版: `tools-manifest.json` と各campaignの `identity.json`。
- 最終14条件: `../../ans-spectral-multistart-v1/speaker-comparison.json`。
- 詳細報告: `docs/note/autonomous-non-neural-speech-extension-progress-2026-10-02.md`（リポジトリ直下から）。
- 31テストの記録: `../../extension-tests-31.log`。

追加3枠は使用済み。必須E1/E2、P5の品質認定経路、独立最終確認が残る。新しい試聴回答は必須条件ではない。
