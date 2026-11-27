# tall の母音終端がF2推定に与える感度

## 読解と事前登録

固定上流は `c6147d0198890475dbe8a65a0bb8f56240c539b7`。第46版は同一の整列用PCM16に対し、2つの特徴行を入れ替えると `tall` の /ɔ/–/l/ 境界が1.650秒から1.680秒へ動くことを示した。今回は登録済みの無加工48 kHz float32レンダーをLPCに使う。AO1の開始1.530秒を固定し、終端を1.650、1.660、1.670、1.680秒に動かす。内側の2点は感度を測るために指定した時刻。全4点は保存済みMFA時刻と同じように秒をfloat32に丸めて表現する。[32条件の整列結果](tsp-tall-gmm-frame-subsets.md#実測)・[事前条件](../cases/tsp-tall-f2-boundary-grid.json)

| 読んだ入口と処理 | 入力、状態、出力 |
| --- | --- |
| 固定上流 `crates/chimera-cli/src/compare/tsp.rs` の `run`、`measure_pair`、`measure`、`Sig::new` と `Sig::formants`、親の `compare.rs` の `read_wav` と `median` | `Sig` に発話全体の低域系列 `lo` を保持する。95タップのBlackman窓付きsincで5.4 kHzより上を抑え、4標本おきに12 kHz系列を作る。区間 `[a,b]` に対し中心は `a + q(b - a)`。開始標本は `trunc(12000 × 中心) − 150`、窓長300標本。35%、50%、65%の窓に施したLPCからF1・F2を採り、取得した窓の各周波数の中央値を返す。90%は今回の観測用。 |
| `crates/chimera/src/analysis/lpc.rs` の `estimate_formants`、`autocorr`、`levinson`、`poly_roots` | 毎窓で `x[i] − 0.97 x[i−1]` にHamming窓を掛ける。先頭は前標本0。自己相関に40 Hzのガウス型ラグ窓を掛ける。今回は次数12。Levinson–Durbinで前次数の係数と予測誤差を使い、Durand–Kernerで根を求める。上半平面の根から `f = arg(z) × 12000 / (2π)` Hz、`B = −ln(|z|) × 12000 / π` Hzを得る。150 Hz以上・帯域幅600 Hz以下の極を周波数順に並べる。最初の1300 Hz未満・帯域幅500 Hz未満をF1に、F1+200 Hzより高く3500 Hz未満の最初をF2に採る。 |
| 固定上流 `crates/chimera/tests/golden_analysis.rs` のLPC照合、研究版 `tools/upstream_tsp_formant_probe.rs` と `tools/measure_tsp_stressed_vowel_formants.py` | 既知データで自己相関、係数・誤差、根、極を照合する。既存プローブで上流本体の中央値を測り、窓ごとの極も採取する。独立計算はToeplitz連立方程式とコンパニオン行列の固有値で極を計算し、同じ入力区間で比較する。 |

先行ケースの両端では、中央3窓のF2中央値が1,248.89 Hzから1,241.25 Hzへ、90%窓が1,270.70 Hzから1,528.49 Hzへ変わった。この差を根拠に、4条件でも中央中央値の幅は100 Hz未満、90%窓の幅は100 Hz以上で、終端を遅らせると90%窓のF2は低下しないと事前登録した。12 kHz系列では終端10 msは120標本分で、各中心は42、60、78、108標本ずつ移ると予測する。[両端の保存済み測定](../runs/tsp-tall-mfa-preroll-20261123-repeat/artifacts/upstream-formants.json)

## 実測

| 母音終端（秒） | 時刻の出所 | 中央3窓のF2中央値（Hz） | 90%窓のF2（Hz） | 90%窓の区間外（ms） |
| ---: | --- | ---: | ---: | ---: |
| 1.650 | 圧縮開始条件でMFAが選択 | 1,248.89 | 1,270.70 | 0.417 |
| 1.660 | 感度測定用の指定 | 1,262.25 | 1,338.32 | 0 |
| 1.670 | 感度測定用の指定 | 1,265.23 | 1,412.94 | 0 |
| 1.680 | 2行交換条件でMFAが選択 | 1,241.25 | 1,528.49 | 0 |

4条件のF2変動幅は中央3窓の中央値で23.98 Hz、90%窓で257.79 Hzだった。中央中央値の最大は途中の1.670秒にあり、両端の差は−7.64 Hzだった。90%のF2は4点で増加した。1.660〜1.680秒では窓が指定区間に完全に収まり、この3条件だけでも190.17 Hz動いた。90%窓のF2は全4条件で周波数順の2番目の極だった。保存された各窓の極は周波数と帯域幅の両方を確認できる。[測定値と予測](../runs/tsp-tall-f2-boundary-grid-20261123-repeat/summary.json)・[固定上流の全極](../runs/tsp-tall-f2-boundary-grid-20261123-repeat/artifacts/upstream-formants.json)

開始標本は全16窓で一致した。独立Pythonとの差は採択したF1・F2で最大1.32×10⁻¹⁰ Hz、公開極の周波数と帯域幅で最大7.07×10⁻¹⁰ Hzだった。いずれの条件も中央の3窓すべてを使い、欠測はなかった。両端の整列用WAVはバイト一致し、既存のLPC出力とも一致した。[窓別の独立計算](../runs/tsp-tall-f2-boundary-grid-20261123-repeat/artifacts/window-comparisons.json)

録音側の同じ語ではMFAの母音ラベルが `AA1`、母音終端が1.690秒だった。次は録音側のラベルを維持し、保存済みの録音と境界で同じ窓感度の対照を作る。この比較で得る値は窓位置の診断値になる。人手F2注釈は既存資料と対応させて取り込む。[録音側の境界](../runs/tsp-phone-boundaries-held-out-20261121-a/artifacts/aligned-1-recording/FK61_02/FK61_02.json)・[人手注釈の取込手順](plan-evidence-stage7.md#未確認の観測)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、研究Python 3.14.4。研究ワークスペースで次を実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=2147483648 \
  ../../.venv/bin/python tools/measure_tsp_tall_f2_boundary_grid.py tsp-tall-f2-boundary-grid-new
```

研究ワークスペースと `/tmp` からの2実行は各6判定と上流7試験を通過した。測定要約、上流極、独立計算、ゴールデン試験ログの4出力はバイト一致した。差がある2出力は実行ログだった。再実行のソース一覧を、比較CLIがWAVの読み込みと中央値で使う親モジュールの `compare.rs` に合わせた。[初回](../runs/tsp-tall-f2-boundary-grid-20261123-a/manifest.json)・[再実行](../runs/tsp-tall-f2-boundary-grid-20261123-repeat/manifest.json)
