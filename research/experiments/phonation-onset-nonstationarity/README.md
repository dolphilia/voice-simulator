# Phonation Onset and Nonstationarity

[`docs/plans/phonation-onset-and-nonstationarity-research-plan.md`](../../../docs/plans/phonation-onset-and-nonstationarity-research-plan.md) の実行用ワークスペースです。

人間音声は、開始部・持続部の寄与を切り分ける研究刺激と、特徴量を測るリファレンスにだけ使います。完全生成候補には録音断片を含めません。`export_allowed=no` の入力および派生音声はローカル研究用途に限定します。

## 現在の対象

- 母音 `/a/`
- onset-development: 3話者、各2音源表情
- 人間音声内の A0〜A4 切除・ループ刺激
- 発声活動、周期性、安定音高、安定音源、安定母音の境界候補
- F0、RMS、周期性、HNR、CPP、H1-H2、スペクトル、formant の時間軌道
- C1〜C7 の完全生成 onset ablation

UTAUの同一話者別サブセットは、同一条件の別テイクではなく音源表情の違いを含みます。初期パイプラインの検証には使いますが、人間一般への結論には使いません。

## 実行

リポジトリルートから実行します。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py test
```

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py validate-manifest
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py render-stimuli
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py render-synthesis
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py freeze-candidates
```

## CLI試聴ウィザード

未回答の旧チェックポイントと同じ13比較から、CLIウィザード用の17提示（隠し重複4件）を生成済みです。旧チェックポイントは変更していません。

まず音量確認と操作練習だけを行えます。本番回答は保存されません。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen --check-only
```

本番試聴は次で開始します。中断した場合も同じコマンドで続きから再開します。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen
```

ウィザードでは、音量確認、練習、A/B再生、質問、休憩、自動保存を順に案内します。音声は質問中に何度でも再生できます。はい・いいえの質問には、`y` / `n`、`yes` / `no`、または日本語の「はい」/「いいえ」で回答できます。音声ファイルやCSVを手動で開く必要はありません。

試聴回答後は、範囲、欠損、凍結音声、`SAME` / `UNSURE`、重複回答の一貫性を検証してから仮説別に集計します。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze-listening
```

第1試聴の結果は `results/listening/checkpoint-wizard-v1/interpretation.md` に判定メモとして固定しています。H1比較に長さ・端点・音量の交絡が見つかったため、統制した短い再監査セッションは次で準備します。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py prepare-onset-reaudit
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen --session onset-reaudit-wizard-v1
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze-listening --session onset-reaudit-wizard-v1
```

再監査は0.8秒、同一の先頭・終端フェード、定常区間RMSを揃え、stable境界前40/80/160/240 msの文脈を比較します。8ユニーク比較＋隠し重複2件です。

統制再監査では人間らしさが8/8で同等、開始自然さが4/8でonset文脈ありとなりました。最終分類前の非UTAU追試はJVS 2話者の文頭長母音を使う6提示です。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py prepare-external-reaudit
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py listen --session onset-reaudit-jvs-wizard-v1
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze-listening --session onset-reaudit-jvs-wizard-v1
```

JVS追試は孤立持続母音ではないため、後続子音を避けた120 ms提示と40/80 ms文脈に限定しています。この制約は `config/reaudit-external-references.json` と刺激manifestに固定されています。

## 最終判断

UTAUとJVSの統制比較12件では、onset文脈が人間らしさで選ばれた例は0件でした。H1は反証とし、S系列は実装しません。統合結果は `results/listening/h1-final-decision.md` に保存しています。

次工程は `docs/plans/synthetic-vowel-baseline-recovery-plan.md` に従い、完全生成の定常 `/a/` が目的母音かつ人声として成立することを先に検証します。holdoutは未開封です。

`pipeline` は上記の試聴前工程を順に実行します。`onset-holdout` は通常コマンドでは読み込みません。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py pipeline
```

## 証拠の区別

- `results/analysis/`: 自動測定。知覚自然さの証拠ではない
- `results/stimuli/`: 人間音声を加工した研究限定刺激
- `results/generated/`: 人間音声断片を含まない完全生成音
- `results/listening/`: 回答前に凍結した候補と、後の試聴回答

既存の比較評価で棄却されたHuman-likeness総合点は使用しません。候補の自動選別は、信号健全性、加工境界、操作の成立、特徴上の重複だけで行います。
