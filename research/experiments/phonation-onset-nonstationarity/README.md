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

試聴回答後は、範囲、欠損、凍結音声、重複回答の一貫性を検証してから仮説別に集計します。

```bash
research/.venv/bin/python research/experiments/phonation-onset-nonstationarity/run.py analyze-listening
```

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
