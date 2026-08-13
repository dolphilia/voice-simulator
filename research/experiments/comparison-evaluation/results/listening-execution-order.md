# 試聴評価の実施順序

データ漏洩を避けるため、次の順序を変えない。

1. `listening-sessions/vowel-a-initial/` の7提示を評価する。
2. `listening-sessions/perceptual-suite/` の10提示を評価する。
3. 2つの `responses.csv` を保存し、development回答を変更しない状態にする。（完了）
4. `analyze-listening` と `analyze-perceptual-suite` を実行する。（完了）
5. 初回候補だけでは評定分散が不足したため、`listening-sessions/calibration-anchors/` の10提示を評価する。（完了）
6. 初回回答とアンカー回答を結合し、development benchmarkで `calibrate` を実行してprovisional weightsを固定する。（完了）
7. ここで初めて `listening-sessions/vowel-a-holdout/` の7提示を評価する。（完了）
8. holdout回答を解析し、`validate-calibration` で独立検証する。（完了・不合格）
9. holdout順位との対応、重複回答の一貫性、軸ごとの説明可能性を確認し、重みの採否を判断する。（完了・棄却）

`session-key.json` は各セッションの回答完了まで開かない。holdout音声はステップ6まで聴かない。

## 入力箇所

- development評定: `listening-sessions/vowel-a-initial/responses.csv`
- 識別・属性・A/B: `listening-sessions/perceptual-suite/responses.csv`
- calibrationアンカー: `listening-sessions/calibration-anchors/responses.csv`
- holdout評定: `listening-sessions/vowel-a-holdout/responses.csv`

## 所要量

- development評定: 7提示（重複1件を含む）
- 知覚評価スイート: 10提示
- calibrationアンカー: 10提示（重複2件を含む）
- holdout評定: 7提示（6ユニーク候補、重複1件を含む）

一度に完了させる必要はない。セッション間で休憩できるが、同じ再生機器と音量を維持する。
