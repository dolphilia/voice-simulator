# TSP方式のLPC自己相関ラグ窓

[既知の極を使った前回の比較](tsp-f2-bandwidth-known-poles.md)では、帯域幅430 Hz・設計F2 2075 Hzの波形に12次LPCを適用したとき、50%窓の固定F2は2205.57 Hzだった。帯域幅による採用条件を加える前にずれが起きていた。今回はその窓、推定次数、前処理、F2の選択規則を固定し、自己相関ラグ窓の40 Hzだけを0 Hzに変えた。[事前登録](../cases/tsp-lpc-lag-window.json)

## 固定上流の読解

- 上流CLIの `compare tsp` は `tsp::run`、`measure_pair`、`measure` を経て、単母音に `Sig::formants` を呼ぶ。通常はMFA境界を秒で読み、48 kHz音声から得た12 kHz列の35・50・65%に各25 ms窓を置く。今回は先行実行の12 kHz波形から、開始5850標本の300標本だけを使う。窓先頭の前標本を0として、係数0.97のプリエンファシスとHamming窓を適用する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[測定の呼び出し](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[標本窓の定義](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- `autocorr` は窓内の標本同士の積を0〜12ラグで足し、`r[k] = Σ x[i] x[i−k]` を得る。ラグ `k` の単位は標本。固定コードは `exp(−0.5(2π × 40 × k / fs)²)` を掛け、後続のラグほど小さくする。0 Hzではすべての重みが1。ラグ0は両条件で同じ値を使う。この処理は、波形に掛けたHamming窓の後で自己相関列に作用する。[自己相関とラグ窓](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L7)・[固定推定器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[自己相関の定義](https://dsprelated.com/freebooks/mdft/Autocorrelation.html)
- `levinson` は残差を `r[0] × (1 + 10⁻⁹) + 10⁻³⁰` で初期化し、反射係数と予測係数を次数ごとに更新する。別計算では同じ対角補正を持つToeplitz行列を直接解く。固定RustはDurand–Kerner法で根を求め、偏角と半径を周波数・帯域幅（Hz）に変換して選別する。F2はF1＋200 Hzより上かつ3500 Hz未満の最初の候補で、今回の両条件でこの規則を使う。既存基準試験はTypeScript由来の自己相関、残差、係数、根、包絡、採用極を照合する。[係数と残差](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[根とFormantOpts](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L54)・[F2の規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L538)・[上流の基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 比較方法

[研究CLI](../tools/measure_tsp_lpc_lag_window.py)は先行マニフェストにある波形・ケース・結果のSHA-256を照合する。[Rust観測プログラム](../tools/upstream_tsp_lpc_lag_probe.rs)は固定上流の `estimate_formants` と、固定コミットから取得した `lpc.rs` の40.0だけを0.0にした一時モジュールを、同じ入力で呼び出す。重み付け前後の自己相関、係数、残差、全根と採用極を出力する。Pythonでは直接解法、コンパニオン行列の固有値、複素多項式評価で再計算し、共通の平滑ピリオドグラムはFFTと直接DFTで照合する。ラグ窓が数値条件に与える影響は、対角補正後のToeplitz行列の最小・最大固有値から求めた2ノルム条件数で見る。計測の合否とF2に関する予測の成否を記録する。

## 実測

| 量 | 固定40 Hz | 0 Hz（重みなし） |
| --- | ---: | ---: |
| ラグ1の重み | 0.999780700 | 1 |
| ラグ12の重み | 0.968910791 | 1 |
| 最初の予測係数 `a[1]` | −1.867603 | −1.851059 |
| 予測残差 | 0.000332234 | 0.000322107 |
| Toeplitz行列の2ノルム条件数 | 3326.95 | 3342.81 |
| 採用F2 | 2205.57 Hz | 2211.56 Hz |
| 採用F2の帯域幅 | 546.12 Hz | 496.85 Hz |
| 設計F2との差 | +130.57 Hz | +136.56 Hz |

重み付け前の自己相関とラグ0は一致した。最初の差はラグ1の重み付けで、重みを外すと自己相関が約 `4.80×10⁻⁷` 大きくなった。係数列では `a[0] = 1` が共通で、差は `a[1]` から現れた。どちらもF1・F2を採用できた。帯域幅は49.26 Hz狭まり、設計帯域幅430 Hzに近づいた。周波数は5.99 Hz上がり、設計F2との差が広がった。条件数は約0.48%増えた。したがって、F2が設計値に近づく予測は反証され、条件数が増える予測は成立した。この窓で残った約137 Hzのずれの原因はまだ分離できていない。[要約](../runs/tsp-lpc-lag-window-20261122-repeat/summary.json)・[二つの包絡と共通ピリオドグラム](../runs/tsp-lpc-lag-window-20261122-repeat/artifacts/spectra.json)・[固定コミットとの差分](../runs/tsp-lpc-lag-window-20261122-repeat/artifacts/zero-lag-window.patch)

## 再現

研究ワークスペースで実行する。元の試験波形は先行実行の保存ファイルを参照する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_lpc_lag_window.py tsp-lpc-lag-window-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1で実行した。40 Hzの係数・残差・極・F2・LPC包絡は先行出力と一致した。両条件でRustと直接解法の係数の最大差は `2.45×10⁻¹²` 未満、採用候補の周波数・帯域幅の最大差は `1.97×10⁻¹⁰ Hz` 未満。LPC包絡と複素多項式の差は `1.34×10⁻¹¹ dB` 未満、FFTと直接DFTの差は `6.51×10⁻¹³ dB` 未満だった。

初回と `/private/tmp` からの再実行で各5判定と固定上流の基準試験1件が通過した。要約、段階別のRust出力、数値スペクトル、定数の差分がバイト一致した。別集計で差分の1行と全13ラグの重みを確認した。2実行の54入力・12出力をサイズとSHA-256で照合し、270,266バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-lpc-lag-window-20261122-a/manifest.json)・[再実行](../runs/tsp-lpc-lag-window-20261122-repeat/manifest.json)
