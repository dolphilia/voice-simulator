# Comparison Evaluation

`docs/plans/comparison-evaluation-framework-plan.md` を実装する比較評価基盤です。

現行の `research/scripts/compare_waveforms.py` を互換性のある基礎として残しながら、次を追加します。

- 指標仕様と評価プロファイルのバージョン管理
- 解析 fixture と既知変形による自動校正
- multi-resolution STFT、log-mel、MFCC、F0 contour、声質特徴
- 評価 manifest と話者単位 split
- 人間音声同士の robust 基準分布
- target similarity / human-likeness のカテゴリ別スコアカード

## 実行

リポジトリルートから実行します。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py test
```

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py validate-manifest \
  --manifest research/experiments/comparison-evaluation/fixtures/manifests/analytic.csv
```

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py extract \
  --manifest path/to/samples.csv \
  --output /private/tmp/features.jsonl
```

基準分布は calibration split だけから生成する。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py baseline \
  --features research/experiments/comparison-evaluation/results/utau-features.jsonl \
  --output research/experiments/comparison-evaluation/results/utau-baseline.json
```

開発ベンチマークを実行する。holdout task は通常実行では拒否され、候補固定後に明示的な `--allow-holdout` が必要になる。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py benchmark \
  --tasks research/experiments/comparison-evaluation/config/tasks/vowel-a-development.csv \
  --baseline research/experiments/comparison-evaluation/results/utau-baseline.json \
  --output /private/tmp/benchmark.json \
  --markdown /private/tmp/benchmark.md
```

試聴候補は gate と Pareto 条件で絞り、音量正規化、匿名化、順序の乱数固定、重複提示まで自動化する。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py prepare-listening \
  --benchmark research/experiments/comparison-evaluation/results/vowel-a-development.json \
  --output /private/tmp/listening-session
```

`responses.csv` 記入後は、回答の範囲と重複提示の一貫性を検査する。続く `calibrate` は自動カテゴリとの Spearman 順位相関を出すが、独立holdout試聴が揃うまで重みを有効化しない。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py analyze-listening \
  --session path/to/listening-session --output /private/tmp/listening.json
research/.venv/bin/python research/experiments/comparison-evaluation/run.py calibrate \
  --listening /private/tmp/listening.json --benchmark path/to/benchmark.json \
  --output /private/tmp/calibration.json
```

5母音・`し/す`識別、brightness / breathiness順序、参照A/Bは別の短いスイートにまとめる。

```bash
research/.venv/bin/python research/experiments/comparison-evaluation/run.py render-perceptual-fixtures \
  --output /private/tmp/perceptual-fixtures --manifest /private/tmp/rendered.json
research/.venv/bin/python research/experiments/comparison-evaluation/run.py prepare-perceptual-suite \
  --rendered /private/tmp/rendered.json \
  --benchmark research/experiments/comparison-evaluation/results/vowel-a-development.json \
  --output /private/tmp/perceptual-suite
```

## 評価スキーマ

- schema version: `1.0.0`
- metric profile version: `1.0.0`
- baseline version: `1.0.0`

出力には入力ファイルの SHA-256、設定、実装バージョンを含めます。推定不能な値は 0 にせず、`null`、coverage、confidence、reason として保持します。

## 旧CLIとの関係

初期段階では既存の `audio_utils.py` を利用します。新基盤が安定するまでは旧CSV列を変更しません。回帰fixtureにより、旧結果との違いを追跡します。

## 実装状況（2026-08-13）

- フェーズ0〜5: 指標契約、解析fixture、特徴量、manifest、基準分布、カテゴリ別スコアカードを実装済み
- フェーズ6: `/a/` の旧方式と `spectral-match` を development / holdout で再評価済み。5母音taskテンプレートを追加済み
- フェーズ7: 28件の自動テスト、旧CLI自己比較回帰、gate終了コード、前回差分検査を実装済み
- フェーズ8: 少数候補の匿名試聴セット生成と回答検査を実装済み
- フェーズ9: 評定、5母音・`し/す`識別、brightness/breathiness順序、参照A/B、校正アンカーを実施・解析済み
- フェーズ10: development暫定対応を独立holdoutで検証し、全軸不合格のため棄却。正式総合点は`null`を確定し、カテゴリ診断を継続利用

主要な仕様は [metric catalog](config/metric-catalog.md)、参照データの偏りは [UTAU audit](results/utau-audit.md)、既存モデルの多面的な比較は [development benchmark](results/vowel-a-development.md) と [holdout benchmark](results/vowel-a-holdout.md) を参照する。

知覚評価方式の選択と回答品質基準は [listening protocol](config/listening-protocol.md)、音源利用条件の確認状況は [license ledger](config/license-ledger.csv) を参照する。台帳上で `export_allowed=no` の音声や派生物を外部公開しない。

知覚評価の最終結論は [holdout validation summary](results/holdout-validation-summary.md)、総合点の機械可読な採否は [aggregate adoption decision](results/aggregate-adoption-decision.json) を参照する。暫定モデルは独立holdoutで自然さ・声質を大幅に過大評価したため、正式な重み付き総合点を導入しない判断となった。

## 現時点の解釈上の制約

- UTAU参照は128件、話者単位で development 58 / calibration 49 / holdout 21。holdoutは2話者で、未知話者評価の主張はまだ限定的である。
- 権利条件はローカル研究用途として保守的に扱い、音源ごとの元readmeを未確認のまま再配布しない。
- Human-likeness はUTAU calibration分布への適合度であって、人間一般の自然さではない。
- 一部の指標は相関し、同じ現象を二重に測る。試聴校正前はカテゴリ横断の重み付き総合点を出さない。
- F0・LPC formant・CPPなどの推定器は初期実装で、coverage/confidenceと既知fixtureを伴って診断用途に使う。
