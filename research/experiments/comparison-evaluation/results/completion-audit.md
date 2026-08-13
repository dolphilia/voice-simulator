# 比較評価基盤 完了条件監査

監査日: 2026-08-13

`docs/plans/comparison-evaluation-framework-plan.md` の各フェーズを、現在のファイルと実行結果に対して確認した。意図や実装済みという記述だけでなく、再実行可能な証拠を基準にした。

## 判定

| フェーズ | 判定 | 主な証拠 |
| --- | --- | --- |
| 0 仕様固定 | 完了 | `config/metric-catalog.md`、schema/profile version、旧CLI自己比較回帰テスト |
| 1 fixture・テスト | 完了 | `fixtures/expected/analytic.json`、既知F0/formant/noise/tilt/delay/gain/polarity/stretch/異常入力を含む28テスト |
| 2 特徴抽出 | 完了 | feature bundle、frame series、multi-resolution STFT、log-mel/MFCC、F0 contour、formant/Bark/bandwidth、H1-H2/HNR/CPP、時間変化、signal integrity |
| 3 manifest・split | 完了 | UTAU 128件、development 58 / calibration 49 / holdout 21、話者・元録音漏洩validator、`license-ledger.csv` |
| 4 人間基準分布 | 完了 | 同話者同音素28ペアを含む4層のペア、median/MAD/percentile、LOSO 5母音精度0.600（偶然0.200）、失敗率、Spearman冗長性 |
| 5 profile・scorecard | 完了 | 5 profile、Target/Human-likeness分離、coverage/confidence、符号付き方向診断、調整提案、Pareto・Markdown/JSON |
| 6 holdout・反復接続 | 完了 | `/a/` original 10 + spectral-match 10の全試行、方式中央値、明示許可が必要なholdout比較、5母音task雛形 |
| 7 継続的回帰 | 完了 | 28テスト、旧出力fixture、gate終了コード、benchmark差分、入力hash/profile version cache |
| 8 試聴準備 | 完了 | gate/Pareto絞り込み、匿名化、音量正規化、seed、重複提示、回答validator、方式選択文書、短い知覚評価スイート |
| 9 少人数試聴 | 完了 | 初回17提示と校正アンカー10提示を回答・解析済み。重複3組は完全一致 |
| 10 総合判断校正 | 完了（棄却） | 14対象で校正し、未提示6候補で独立holdout検証。順位・絶対誤差基準を全軸で満たさず、暫定重みを不採用と確定 |

## 再検証コマンド

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py test
research/.venv/bin/python research/experiments/comparison-evaluation/run.py validate-manifest \
  --manifest research/experiments/comparison-evaluation/config/manifests/utau-evaluation.csv
research/.venv/bin/python research/experiments/comparison-evaluation/run.py baseline \
  --features research/experiments/comparison-evaluation/results/utau-features.jsonl \
  --output /private/tmp/utau-baseline.json
```

直近のテスト結果は28件すべて成功。manifestは128件でvalid。基準分布はcalibration splitだけを利用する。

## 自動評価から得られた判断

- `spectral-match` はdevelopmentの方式中央値で spectral/timbre target 66.7→77.6、resonance target 16.1→22.5へ改善した。
- 同時に spectral/timbre のHuman-likeness中央値は66.6→62.6へ低下した。Targetへの近さと人間分布への適合が一致しないトレードオフを検出している。
- holdoutでもoriginalとimprovedの双方がPareto候補に残り、一方を全面的に優位とは断定できない。
- calibrationの5母音LOSO精度は0.600で偶然水準0.200を上回るが、十分高くはない。自動的な音素同一性判定を最終判断には使わない。
- calibration内のF0、formant、音声validation失敗率は今回0。ただし別条件へ一般化した成功率ではない。
- UTAU偏重、未確認の個別利用条件、holdout 2話者という制約が残る。台帳は全行 `export_allowed=no` としている。

## 残作業に必要な外部証拠

フェーズ9と10は完了した。初回候補だけでは不足した尺度分散を匿名校正アンカーで補い、14対象のdevelopment暫定対応を固定した。その後、未提示6候補を独立holdout評価し、暫定モデルが自然さ・声質を大幅に過大評価することを確認した。重みは再調整せず棄却し、正式総合点を導入しない判断を成果として固定した。

正式な総合点は独立検証不合格のため `aggregate=null` に確定した。次版を研究する場合も、今回確認したholdoutを調整用に再利用しない。
