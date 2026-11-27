# W06でプリエンファシスによるF2の選択境界を測る

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。人手注釈資料W06の `FK61_01` の `again` について、12 kHzの半開区間 `[24149, 24449)` と次数12を固定する。前回の窓位置比較で元録音と照合した間引き系列の同じ300標本を使う。プリエンファシス係数 `a` だけを0から0.97まで0.001刻みで変える。[事前条件](../cases/tsp-f2-annotation-w06-pre-emphasis.json)・[W06の窓位置とPCM](tsp-f2-annotation-w06-window-shift.md)

| 読んだ上流と研究用の入口 | 入力、更新、観測点 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `measure_pair` と `Sig::formants` | 録音と対応音素を受け、調べたい時刻の300標本を12 kHz系列から切り出す。母音中央の測定に既定の `FormantOpts` を渡す。候補F1は1300 Hz未満・幅500 Hz未満。F2はF1より200 Hzを超えて高く3500 Hz未満の最初の公開極。 |
| `crates/chimera/src/analysis/lpc.rs` の `estimate_formants`、`autocorr`、`levinson`、`poly_roots` | 窓先頭は前標本0とし、`y[n] = x[n] − a x[n−1]` にHamming窓を掛ける。自己相関に40 Hzのラグ窓を掛け、予測係数と残差をLevinson–Durbinで更新する。複素根の角度から周波数を、絶対値の対数から帯域幅を計算する。150 Hz以上・幅600 Hz以下の上半平面の根だけを周波数順の公開極として返す。 |
| 上流の `crates/chimera/tests/golden_analysis.rs`、比較CLIの `a_missing_measurement_has_no_cost`、研究用 `upstream_tsp_lpc_pre_emphasis_probe.rs` | ゴールデン試験で自己相関、係数、残差、生根、公開極を照合する。既存プローブから `FormantOpts.pre_emph` だけを指定し、上流の出力と、Toeplitz連立方程式・多項式の根による独立計算を比べる。 |

先行の係数0ではF1が440.98 Hz・幅441.00 Hz、F2が708.24 Hz。既定0.97ではF1が620.18 Hz、F2が2,073.45 Hzだった。係数を上げる途中で、係数0のF1が公開極またはF1としての条件から外れると予測した。そのとき従来の低いF2極がF1へ繰り上がり、次の約2.1 kHzの極がF2に選ばれると予測する。各切り替わりではF1からの周波数差と、隣接係数間の生根の対応を確認する。[端点の測定](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/summary.json)

## 実測

| プリエンファシス係数 | 最低周波数の公開極（周波数・帯域幅、Hz） | 採択F1（Hz） | 採択F2（Hz） |
| ---: | ---: | ---: | ---: |
| 0.111 | 467.61・499.47 | 467.61 | 680.23 |
| 0.112 | 467.94・500.13 | 679.88 | 2,009.79 |

低域をF2に採ったのは係数0〜0.111の112点、高域を採ったのは0.112〜0.970の859点。切り替わりは0.111と0.112の間の1回で、欠測は0件だった。両点とも約468 Hz、680 Hz、2,010 Hzの極は公開されていた。約468 Hzの帯域幅がF1の上限500 Hzを越え、約680 Hzの極がF1になった。約2,010 Hzの候補極は同じ2点で0.09 Hz動き、採択F2は1,329.56 Hz上がった。周波数と帯域幅を使って隣接条件間の複素根を対応させると、元のF1とF2の根の変位はそれぞれ0.000216と0.000183だった。[全971点と切り替わり](../runs/tsp-f2-annotation-w06-pre-emphasis-20261123-repeat/summary.json)・[固定上流の前処理と極](../runs/tsp-f2-annotation-w06-pre-emphasis-20261123-repeat/artifacts/upstream-pre-emphasis.json)

固定上流と独立計算は全点で照合に通過した。LPC係数の最大差は3.27×10⁻¹²、複素根は4.90×10⁻¹³、公開極の周波数・帯域幅は2.15×10⁻⁹ Hz以内。既定0.97と明示的な0の両端で保存済みの前処理・係数・極・採択を再現した。この結果は1つの録音窓の自動採択を示す。次は同じ人手注釈資料の `again` の35%点W07と65%点W02に同じ係数範囲を適用し、F1の帯域幅条件による切り替わりが他の2窓にも現れるか比較する。[人手注釈資料](../runs/tsp-f2-annotation-20261122-repeat/artifacts/reference.json)・[取込手順](tsp-f2-human-intake.md)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_tsp_f2_annotation_w06_pre_emphasis.py \
  tsp-f2-annotation-w06-pre-emphasis-new
```

研究ワークスペースと `/tmp` からの各実行は3判定と上流7試験に通過した。入力窓、固定上流の全出力、要約、TSP試験ログの4出力がバイト一致し、残る2件は実行ログだった。既存の録音6窓の二条件比較を共用プローブで再実行し、9出力が一致した。成果はRTL9210B-CGに保存した。[初回](../runs/tsp-f2-annotation-w06-pre-emphasis-20261123-a/manifest.json)・[再実行](../runs/tsp-f2-annotation-w06-pre-emphasis-20261123-repeat/manifest.json)・[既存比較の回帰](../runs/tsp-lpc-pre-emphasis-recordings-20261123-w06-regression/manifest.json)
