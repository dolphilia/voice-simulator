# 12次LPCのプリエンファシスとF2

[前回のラグ窓の比較](tsp-lpc-lag-window.md)では、設計F2が2075 Hz・帯域幅430 Hzの波形で、ラグ窓を外すと固定F2が2205.57 Hzから2211.56 Hzへ動いた。今回は同じ300標本、12次LPC、ラグ窓40 Hzで、プリエンファシスの既定係数0.97と係数0を比較する。[ケース定義](../cases/tsp-lpc-pre-emphasis.json)

## 固定上流の読解

- `compare tsp` の `tsp::run` は `measure_pair` で録音と合成の音素を対応させ、`measure` が単母音に `Sig::formants` を呼ぶ。通常は48 kHz波形を12 kHzへ間引き、母音の35・50・65%を中心とする各300標本を使う。今回は先行実行で確認した12 kHz波形の50%窓、開始標本5850を参照する。[CLI入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[対応付け](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- `estimate_formants` は `FormantOpts.pre_emph` が未指定なら0.97を取る。プリエンファシスは `y[n] = x[n] − a x[n−1]` の2タップFIRで、窓の先頭は `x[−1] = 0` として扱う。係数を0にすると `y[n] = x[n]` になる。その後Hamming窓を掛けて自己相関を計算する。0.97側と0側の信号差は符号を揃えると `y₀[n] − y₀.₉₇[n] = 0.97 x[n−1]`。周波数応答は `H(e^{jω}) = 1 − a e^{−jω}` で、正の係数は高域に対する低域の振幅を下げる。[固定上流の前処理とオプション](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L109)・[プリエンファシスの式](https://praat.org/manual/Sound__Filter__pre-emphasis____.html)
- 両条件とも40 Hzのラグ窓で自己相関 `r[k]` を重み付けする。Levinson–Durbin法は次数を進めながら反射係数、予測係数、残差を更新する。続いて予測多項式の根を求め、周波数と帯域幅（Hz）に変換する。F1は1300 Hz未満・帯域幅500 Hz未満の最初の極。F2はF1＋200 Hzより高く3500 Hz未満の最初の極。上流の基準試験は自己相関、予測係数、残差、根、包絡、オプションを適用した推定極をTypeScriptの保存結果と照合する。[係数・残差](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[極の推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[採用順](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L541)・[基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 比較方法

[研究CLI](../tools/measure_tsp_lpc_pre_emphasis.py)は先行実行と同じ波形、窓、LPC次数、ラグ窓をマニフェストで照合する。[Rustの観測プログラム](../tools/upstream_tsp_lpc_pre_emphasis_probe.rs)は固定コミットのライブラリを使い、公開オプションだけで既定の0.97と明示的な0を指定する。前処理は先行ラグ窓の0.97条件、係数と全根は別計算、包絡は複素多項式で照合する。620 Hzと2075 Hzについて、FIR単体の解析ゲインとHamming窓後の平滑化ピリオドグラムをそれぞれ5 Hz刻みの測定点に揃えて比較する。ピリオドグラムは同じ窓のFFTと直接DFTで照合し、平滑化には先行計測と同じ標準偏差100 Hzを使う。

## 実測

| 量 | 固定係数0.97 | 係数0 |
| --- | ---: | ---: |
| 自己相関のラグ0 | 0.00477618 | 0.01637190 |
| 最初の予測係数 `a[1]` | −1.86760 | −2.67643 |
| Toeplitz行列の2ノルム条件数 | 3326.95 | 62868.21 |
| 採用F2 | 2205.57 Hz | 2065.35 Hz |
| 採用F2の帯域幅 | 546.12 Hz | 426.95 Hz |
| 設計F2との差 | +130.57 Hz | −9.65 Hz |
| 平滑ピリオドグラムの2075 Hz−620 Hz | −2.80 dB | −12.83 dB |

入力と窓内の先頭標本は一致し、差は2番目の標本（番号1）のプリエンファシス出力から現れた。差は約 `−0.003025` で、前標本に0.97を掛けた値に一致した。Hamming窓の後は自己相関のラグ0から差があり、係数は `a[1]` から変化した。両条件でF1・F2が得られた。FIR単体の2075 Hzと620 Hzの相対ゲインは、0.97で約+10.06 dB、0で0 dB。実際に平滑化したピリオドグラムでは、係数0で高域側の相対レベルが約10.02 dB低下した。[段階別の採取値](../runs/tsp-lpc-pre-emphasis-20261122-repeat/artifacts/upstream-pre-emphasis.json)・[LPC包絡とピリオドグラム](../runs/tsp-lpc-pre-emphasis-20261122-repeat/artifacts/spectra.json)

この窓では、係数0で設計F2への絶対誤差が約120.91 Hz縮まり、帯域幅も設計値430 Hzに近づいた。同時に行列の条件数は18.90倍になった。14次や実録音での周波数推定・欠測・数値条件は引き続き確認が必要である。2つの予測はこの1窓で成立した。[要約](../runs/tsp-lpc-pre-emphasis-20261122-repeat/summary.json)

## 再現

研究ワークスペースで実行する。入力の波形は既知の極の実行から参照する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_lpc_pre_emphasis.py tsp-lpc-pre-emphasis-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1で実行した。0.97の前処理・自己相関・係数・残差・極・選択結果・LPC包絡は先行の40 Hz条件と一致した。両条件のRustと独立計算では係数の最大差が `2.06×10⁻¹¹` 未満、根の複素平面上の差が `3.25×10⁻¹²` 未満、採用候補の周波数・帯域幅の差が `6.54×10⁻¹⁰ Hz` 未満だった。LPC包絡の差は `5.46×10⁻¹¹ dB` 未満、平滑化ピリオドグラムのFFT対直接DFTの差は `3.09×10⁻¹² dB` 未満だった。

初回と `/private/tmp` からの再実行で各4判定と固定上流の基準試験1件が通過し、要約・段階別Rust出力・両条件の数値スペクトルがバイト一致した。保存データから全300標本の前処理差、両条件の全13ラグ、ピリオドグラムの2周波数間の差を別に計算した。2実行の62入力・10出力をサイズとSHA-256で照合し、採取物355,872バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-lpc-pre-emphasis-20261122-a/manifest.json)・[再実行](../runs/tsp-lpc-pre-emphasis-20261122-repeat/manifest.json)
