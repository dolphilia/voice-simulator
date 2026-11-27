# again の3つの注釈窓でプリエンファシスとF2の選択を比べる

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。実録音 `FK61_01` の `again` の強勢母音 `EH1` で、12 kHz・300標本の35%窓W07 `[23951, 24251)` と65%窓W02 `[24347, 24647)` を調べる。人手注釈資料のWAVを元録音の切り出しに照合し、測定は元録音全体を既定のフィルタに通した標本で行う。プリエンファシス係数は0〜0.97の0.001刻み、次数は12。50%窓W06は第50版の971点を使い、3窓の採択F2の中央値も求める。[事前条件](../cases/tsp-f2-annotation-again-pre-emphasis.json)・[W06の切り替わり](tsp-f2-annotation-w06-pre-emphasis.md)

| 固定上流の入口 | 入力、状態、更新と出力 |
| --- | --- |
| `crates/chimera-cli/src/compare/tsp.rs` の `measure_pair`、`Sig::new`、`Sig::formants` | 対応する母音区間を受け、5.4 kHzの低域通過と4:1間引きによる12 kHz系列を保持する。35・50・65%を中心とする各300標本の窓でF1とF2を求め、両方得られた窓から周波数の中央値を取る。 |
| `crates/chimera/src/analysis/lpc.rs` の `estimate_formants`、`levinson` と `poly_roots` | プリエンファシス `y[n] = x[n] − a x[n−1]`、Hamming窓、40 Hzのラグ窓付き自己相関の順に処理する。次数12の係数と残差から生根を得る。上半平面の根の角度を周波数、半径の対数を帯域幅へ換算。公開極の帯域幅は600 Hz以下、F1は500 Hz未満。F2はF1から200 Hzを超えて高い候補を周波数順に取る。 |
| `crates/chimera/tests/golden_analysis.rs` の `analysis_matches_typescript`、比較CLIの `a_missing_measurement_has_no_cost` | 根や係数と欠測の扱いを検証する。係数選択を追加した共用プローブの出力を、Toeplitz連立方程式と多項式の根で再計算する。 |

W07は係数0でも既定0.97でもF2は約2.1 kHzで、全点で同じ帯域を採ると予測した。W02の係数0はF1 409.09 Hz・幅283.96 Hz、F2 823.76 Hz・幅477.66 Hz。F1の帯域幅上限より、低いF2自体の公開上限600 Hzが先に選択を変えると予測した。3窓のF2中央値は、W06とW02のうち先に高域に替わる窓の係数で高域へ一度切り替わると予測した。[先行の端点比較](tsp-lpc-pre-emphasis-recordings.md)

## 実測

| 集計対象 | 低域の採択点数 | 高域の採択点数 | 切り替わりの係数 | 採択を決めた条件 |
| --- | ---: | ---: | --- | --- |
| 35%窓 W07 | 0 | 971 | なし | 全点で2,085.11〜2,145.60 Hzを採択 |
| 50%窓 W06 | 112 | 859 | 0.111〜0.112 | F1候補の帯域幅が500 Hzを越えた |
| 65%窓 W02 | 191 | 780 | 0.190〜0.191 | 低いF2候補の帯域幅が600 Hzを越えた |
| 3窓の中央値 | 112 | 859 | 0.111〜0.112 | W06の切り替わりで高域を採る窓が2つになった |

W02では係数0.190で820.55 Hz・幅599.47 Hzの極をF2に採った。0.191では対応する生根が820.53 Hz・幅600.32 Hzとなり、公開極から外れた。F1は429.74 Hzから429.88 Hzへ動き、同じ根を使い続けた。選ばれたF2は1,975.82 Hzへ切り替わった。3窓の中央値の切り替わりは先にW06が替わったときで、822.19 Hzから2,009.79 Hzに移った。W02の境界をまたいだときの中央値の変化は0.094 Hzだった。全係数で3窓すべてが有効だった。[各窓・中央値の全点](../runs/tsp-f2-annotation-again-pre-emphasis-20261123-repeat/summary.json)・[W02の固定上流の生根と公開極](../runs/tsp-f2-annotation-again-pre-emphasis-20261123-repeat/artifacts/upstream-pre-emphasis-01.json)

新規1,942条件で固定上流と独立計算の採択が一致し、複素根の最大差は4.59×10⁻¹²、公開極の周波数・帯域幅は1.18×10⁻⁹ Hz以内だった。3つの資料WAVが元録音の同じ切り出しに一致し、W06の300解析標本と係数列が保存済みの中間値に一致した。次は録音グループのF2中央値を求める上流 `values` と `costs` を読み、同一の対応音素列で今回の1トークンの差が実際のTSPのF2費用にどの程度表れるかを比較する。上流の支持数3件の条件も確認する。[同じ音声の先行評価](../runs/tsp-stressed-vowel-formants-held-out-20261122-repeat/summary.json)・[TSP比較の入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_f2_annotation_again_pre_emphasis.py \
  tsp-f2-annotation-again-pre-emphasis-new
```

研究ワークスペースと `/tmp` で新規の5判定と上流7試験が通過した。入力窓・上流と独立計算の成果・試験ログを含む6出力がバイト一致し、差はビルドと実行のログ1件だった。共用したW06の入口も再実行し、入力窓・上流出力・要約がそれぞれ前版とバイト一致した。成果はRTL9210B-CGに保存した。[初回](../runs/tsp-f2-annotation-again-pre-emphasis-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-annotation-again-pre-emphasis-20261123-repeat/manifest.json)・[W06の回帰](../runs/tsp-f2-annotation-w06-pre-emphasis-20261123-again-regression/manifest.json)
