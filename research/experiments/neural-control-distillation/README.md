# ニューラル教師から非ニューラル制御へ移す小規模実験

[研究計画](../../../docs/plans/neural-assisted-non-neural-speech-plan-2026-10-02.md)の実施領域。旧実験の封印済みコード・結果を変更しない。

目的は、教師の韻律・時間構造を実際のVTLで再現し、その制御を未知文にも適用できる共有モデルへ移せるかを比較すること。日本語全体の自然さを、この小規模実験だけで認定しない。

## 契約

- `nas-pilot-20261002-v1` の1 campaign。開始から4時間、追加3 GB、教師生成48回、実レンダー2,000回、AI評価300回まで。失敗・再試行も開始予約時に消費する。
- 24短文を生成前に開発12・選別6・監査6へ固定する。旧最終確認参照は使用しない。
- 比較は手書き規則、参照に適合した制御、直接学習する非ニューラル制御、研究用ニューラル制御、蒸留した非ニューラル制御。
- 最終入力は文章由来の音素・文脈・韻律指定のみ。発話IDや音声特徴を入力せず、発話ごとの制御列を最終モデルへ保存しない。
- 学習・モデル選択は開発/選別だけ。監査結果を見た後の変更は同じ監査で再認定しない。
- 旧評価器の知覚資格を継承しない。品質認定の正・負の経路を実装するが、人工テストを実音の品質証明にしない。

依存は既存 `.venv-eval` を読み取り再利用し、新規パッケージ・教師重みは本実験の `.cache` へ分離する。コードとモデルの版・ハッシュ・利用条件を記録する。

## 実行状況

規定のpilot比較を実施済み。最終品質目標は未達。[結果報告](../../../docs/note/neural-assisted-non-neural-speech-pilot-result-2026-10-02.md)と `results/nas-pilot-20261002-v1/completion-audit.json` を参照。

教師の時間・F0を非ニューラル共有回帰へ移せたが、VTL版は内容保護に不通過。日本語HMM版では小標本の改善があり、直接学習と蒸留はほぼ同等だった。自然さの品質認定は行わない。

## 保存した単独実行版

- `results/nas-pilot-20261002-v1/bundle/`：VTL、直接回帰/蒸留回帰。内容品質は未達。
- `results/nas-pilot-20261002-v1/hts-bundle-v2/`：日本語HMM、直接回帰/蒸留回帰、出力利得修正。研究版。

HMM版の例（リポジトリのルートから、出力は存在しないパスへ）：

```bash
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python \
  research/experiments/neural-control-distillation/results/nas-pilot-20261002-v1/hts-bundle-v2/hts_runtime.py \
  --text '遠くの鐘が鳴る。' --model direct_non_neural --output /tmp/nas-hts-example.wav
```

教師・参照音声・ニューラル推論・ネットワークを遮断した実行検査に通過。Python/NumPy/SciPy/辞書導入済みpyopenjtalkは別途必要。再生成する場合は2回のHMM合成を計数する。

## 再現と監査

`ledger.jsonl` が失敗を含む試行数、`cost-audit.json` が費用、`dependency-manifest.json` が依存/重みのハッシュ、`model-selection.json` が選択凍結、`main-comparison-summary.json` と `extended-comparison-summary-v2.json` が比較結果。

実験入口の順序は `prepare.py` → `teacher.py` → `extract_controls.py` → `qualify_renderer.py` / `fit_controls.py` → `train_controls.py` → `compare_controls.py` → `evaluate_content.py`。補助対照と修正は個別のprotocolと台帳に記録した。これらは一括再実行スクリプトではなく、保存済み成果を排他的作成する段階別CLIである。同じIDへ全処理を再実行しない。

```bash
research/experiments/autonomous-speech-synthesis/.venv-eval/bin/python -m unittest discover \
  -s research/experiments/neural-control-distillation/tests -v
```

9テスト通過。AI評価は299/300予約を使用済み。今の監査群を使った再調整や、次campaignへの自動延長は行わない。
