# 調査メモ: 母音 /a/ 反復生成・比較実験

## 概要

このメモは、波形比較ツールを使って UTAU リファレンス音声に近づける反復生成実験を行った結果の要約である。

対象リファレンスは `research/data/raw/reference/utau-samples/maoto/単独音/あ.wav` とした。目的は、UTAU 音声を合成素材として使うことではなく、Voice Simulator のフォルマントフィルタ型プロトタイプで使う調整値と評価手順を得ることだった。

## 実験の位置づけ

今回の反復生成は、以下の流れで行った。

1. UTAU 分析から得た `/a/` のフォルマント値を初期値にする
2. 生成 WAV とリファレンス WAV を比較ツールで評価する
3. 指標の悪化要因を見て、F0、F1/F3、ゲイン、source tilt を調整する
4. 10 回の試行後、最良パラメータで `trial-10.wav` を生成する
5. 改善版では参照安定区間のスペクトル包絡をゆるく反映する `spectral_match` を追加する

`spectral_match` は、参照音にどこまで近づけられるかを見る上限確認用の補正である。Web プロトタイプへ直接移植するものではなく、フォルマント周波数、帯域幅、ゲイン、source tilt、帯域別ゲインへ分解して扱う。

## 初期実験の結果

初期実験では、複合スコアが `88.669039` から `54.075995` へ改善した。改善率は `39.01%` である。

主な指標:

| 指標 | 初期 | 最終 |
| --- | ---: | ---: |
| 複合スコア | 88.669039 | 54.075995 |
| `log_spectral_distance_db` | 73.054717 | 43.242226 |
| `formant_mae_hz` | 396.535406 | 204.349761 |
| `f0_delta_cents` | -13.578376 | 0.000000 |

初期実験の最終パラメータは、F0 と一部フォルマントの改善には有効だった。一方で、スペクトル包絡全体の差分とフォルマント MAE はまだ大きく、3 バンドフォルマントだけでは参照音の安定区間に十分近づききれないことが分かった。

## 改善版の結果

改善版では `spectral_match` を追加し、参照安定区間のスペクトル包絡を段階的に反映した。複合スコアは `88.669039` から `48.588397` へ改善した。改善率は `45.20%` である。

主な指標:

| 指標 | 初期 | 改善版最終 |
| --- | ---: | ---: |
| 複合スコア | 88.669039 | 48.588397 |
| `log_spectral_distance_db` | 73.054717 | 42.877531 |
| `spectral_convergence` | 1.102948 | 0.436571 |
| `formant_mae_hz` | 396.535406 | 44.510082 |
| `normalized_cross_correlation` | 0.249916 | 0.519529 |
| `f0_delta_cents` | -13.578376 | 0.000000 |

初期実験の最終結果と比較すると、改善版最終では以下の追加改善があった。

| 指標 | 初期実験最終 | 改善版最終 | 追加改善 |
| --- | ---: | ---: | ---: |
| 複合スコア | 54.075995 | 48.588397 | 10.15% |
| `spectral_convergence` | 0.790617 | 0.436571 | 44.78% |
| `formant_mae_hz` | 204.349761 | 44.510082 | 78.22% |

## Web プロトタイプへの反映値

`web/prototypes/vowel-formant-prototype/src/audio/vowels.ts` には、`reference` / `utau` / `tuned` の 3 セット構成を用意した。今回の反復実験から、`tuned` の `/a/` だけを先に反映している。

反映値:

| フォルマント | 周波数 Hz | 帯域幅 Hz | ゲイン |
| --- | ---: | ---: | ---: |
| F1 | 1073 | 123 | 0.45 |
| F2 | 1405 | 74 | 1.00 |
| F3 | 2053 | 102 | 0.25 |

F2 は比較ツール側の LPC 推定で参照値が欠損しやすかったため、UTAU 分析値 `1405` を維持した。F1 と F3 は反復実験の最終候補を採用した。

`/i/ /u/ /e/ /o/` の `tuned` は、現時点では `utau` と同じ値を使う。後続の反復実験で個別に更新する。

## 成果物

- `research/data/raw/generated/vowel-match-a-improved/trial-10.wav`
- `research/data/processed/analysis/plots/vowel-match-a-improved/trial-10.png`
- `research/data/processed/analysis/vowel-match-a-iterations.csv`
- `research/data/processed/analysis/vowel-match-a-comparisons.csv`
- `research/data/processed/analysis/vowel-match-a-improved-iterations.csv`
- `research/data/processed/analysis/vowel-match-a-improved-comparisons.csv`

## 次の作業

次は `/i/ /u/ /e/ /o/` も同じ評価フローで反復できるよう、`research/scripts/iterate_vowel_match.py` を母音汎用にする。その後、`spectral_match` で得られた差分を source tilt と帯域別ゲインへ分解し、Web 実装で扱える制御に落とし込む。
