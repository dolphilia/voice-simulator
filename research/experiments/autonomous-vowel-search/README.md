# Autonomous Vowel Search

[試聴待ちで停止しない母音自動探索 v1](../../../docs/plans/autonomous-vowel-search-plan.md)のA0〜A5を実装する。

既存のB9生成器と比較評価基盤をversion付きadapterから再利用し、候補台帳、回帰、感度pilot、特徴空間探索、F0/seed頑健性検査、試聴package凍結まで行う。音響値の改善を人声らしさの改善とは扱わない。

## 実行

リポジトリルートから実行する。

```bash
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py test
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py inventory
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py validate-config
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py regression
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py sensitivity
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py evaluate-references
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py time-structure
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py onset-sensitivity
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py run-campaign
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py robustness
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py freeze-listening
research/.venv/bin/python research/experiments/autonomous-vowel-search/run.py status
```

各生成コマンドは既存成果物を上書きしない。結果を変更する場合は新しいversionまたはcampaign IDを作る。

## 現在の境界

- 対象は `/a/`、220 Hz、B9定常部の近傍である。
- 録音は測定上の参照にのみ使用し、生成音へ連結・コピーしない。
- tilt cutoffと制御帯域は探索範囲の保存根拠が不足しているため、A2 pilotでは固定する。
- A5 packageは凍結するが、既存試聴キューが有効な間は開始しない。候補採用・release変更は行わない。

## 実行結果（2026-09-13）

- A0: 46候補を台帳化し、46音すべての保存hashを確認した。24候補に既存試聴証拠への参照がある。
- A1: B9 canonical WAVのSHA-256完全一致、工学制約、seed非同一性、欠損状態を確認した。
- A2: 11設定×3 seedの33音を生成し、全音が工学制約を通過した。
- A2b: holdoutを除く4話者・4参照に対して132件のカテゴリ別比較を実行した。
- measurement adapter 1.0.0のF0転記漏れを検出し、旧結果を保持したまま1.0.1の `avs-a220-v1.1` で再実行した。修正版は33/33音で音響F0を取得した。
- 大きなF0変動は一部proxyを改善するが、既存のB9対B10試聴方向とは一致しない。このためA3を自然さ最適化から特徴空間被覆へ改訂した。
- A3: 64設定×3 seedの192音を完了。全設定が工学通過し、構造化探索と層別無作為探索はいずれも13特徴セルを占有した。
- A4: 8候補×10未使用seed×3 F0の240音を完了し、全条件が工学通過した。
- A5: 4候補、B9アンカー、隠し重複を含む6提示をhash付きで凍結した。状態は `not_queued` である。
- onset: v1.0の定常部RMS制約判定漏れを修正したv1.1で、0/40/60/80 ms×3 seedを再実行した。全12音が通過し、G40を副次的な開始自然さアンカーとして維持した。

pilot判断は `results/avs-a220-v1.1/a2-decision.md`、正式探索判断は `results/avs-a220-search-v1/campaign-decision.md`、onset判断は `results/avs-onset-a220-v1.1/decision.md` に保存している。
