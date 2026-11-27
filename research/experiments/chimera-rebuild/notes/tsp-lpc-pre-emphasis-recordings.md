# TSP録音2語のプリエンファシスとF2

[既知の極を持つ対照波形](tsp-lpc-pre-emphasis.md)では、プリエンファシスを外すとF2の設計値との差は約131 Hzから約10 Hzに縮んだ一方、自己相関行列の条件数が18.9倍になった。今回は、以前にF2の採用極が変わった2録音で、同じ手続きを実行した。対象は `MK61_01` の `seems` /i/（音素番号13）と `FK61_01` の `again` /ɛ/（番号23）、母音の35・50・65%の計6窓。録音のF2の正解ラベルは無いため、採用極・スペクトルのピーク・欠測・条件数を比較する。[事前登録](../cases/tsp-lpc-pre-emphasis-recordings.json)

## 固定上流の読解

- 上流CLIの `compare tsp` は `tsp::run`、`measure_pair`、`measure` を通し、対応した単母音の測定に `Sig::formants` を使う。MFAの時刻は秒、波形は48 kHzの録音から4対1で間引いた12 kHz。各中心は `t0 + q(t1 − t0)` で、12 kHzの標本番号に切り捨てた位置の150標本前から300標本取る。今回は録音、MFA区間、開始標本、300標本の窓を先行実行と照合した。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[録音と合成の対応](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と次数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- `estimate_formants` の `FormantOpts.pre_emph` は未指定なら0.97。前標本を窓の先頭で0として `y[n] = x[n] − a x[n−1]` を計算し、Hamming窓、自己相関、40 Hzのラグ窓を適用する。Levinson–Durbin法が次数ごとに係数と残差を更新し、多項式の根から周波数と帯域幅をHzで得る。 `MK61_01` は固定の14次、`FK61_01` は固定の12次を使った。0.97と0を比べる際に変更する公開オプションは `pre_emph` だけ。[固定推定器](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L109)・[係数の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[前処理の式](https://praat.org/manual/Sound__Filter__pre-emphasis____.html)
- 150 Hz以上・帯域幅600 Hz以下の極を周波数順に並べる。最初に1300 Hz未満で帯域幅500 Hz未満の極をF1とし、F1＋200 Hzより高く3500 Hz未満の最初の極をF2とする。両方が採れた窓のみ母音ごとの中央値へ入る。固定の基準試験はTypeScriptで保存した自己相関・係数と残差・極・包絡・選択候補を照合する。[F1・F2の規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L541)・[基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 比較方法

[研究CLI](../tools/measure_tsp_lpc_pre_emphasis_recordings.py)は、先行の発話区間長比較で記録した録音のSHA-256とMFA比較の記録を照合して、保存録音を読む。係数を切り替えた固定Rustの計算を、同じ自己相関から係数を求めるToeplitzの直接解法、コンパニオン行列による根の計算、包絡の複素多項式評価で照合する。0.97条件は既存の固定上流の極とF2も照合する。平滑化ピリオドグラムは、前処理後の波形から周波数刻み5 Hz・標準偏差100 Hzで計算し、FFTと直接DFTを比較する。各条件のF2候補から±150 Hzで、その条件のLPC包絡、同じ条件のピリオドグラム、係数0の共通のピリオドグラムの局所最大を探す。

## 実測

| 録音 | F2中央値（0.97 → 0） | 条件数の中央値（0.97 → 0） | 採用窓数 |
| --- | ---: | ---: | ---: |
| `MK61_01` の `seems` | 993.17 → 713.23 Hz | 1790.93 → 222978.80 | 3 → 3 |
| `FK61_01` の `again` | 2073.45 → 823.76 Hz | 158.51 → 6523.73 | 3 → 3 |

6窓すべてで、差は窓内のプリエンファシス済み標本の番号1から現れた。重み付け前の自己相関はラグ0から、予測係数は `a[1]` から変わった。F2が100 Hz以上動いた窓は5件で、新しい欠測は無かった。条件数の中央値は `seems` で124.50倍、`again` で41.16倍。登録した高域と低域のレベル差は6窓すべてで縮まり、その変化量は `seems` で17.23–17.34 dB、`again` で9.62–10.02 dBだった。事前の3予測が成立した。[6窓の要約](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/summary.json)

- `seems` の係数0は695–735 Hzの低い極を採った。3窓ともこの極の±150 Hzには、ケースで指定したLPC包絡と平滑化ピリオドグラムの局所最大が無かった。2.3 kHz付近の別の極は両条件に残った。
- `again` の中央窓では、係数0でF1が620.18 Hzから440.98 Hzへ動き、F2の下限も820.18 Hzから640.98 Hzに下がった。その下限を超える708.24 Hzの極が先に採られ、1999.73 Hzの極も帯域幅231.93 Hzで候補一覧に残った。共通の係数0ピリオドグラムでは、固定F2付近に1970 Hzのピーク、係数0で選んだF2付近に640 Hzのピークがあった。65%窓でも係数0で1958.52 Hzの極が得られ、先に823.76 Hzの極が採られた。[中央窓の固定Rust出力](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/artifacts/upstream-pre-emphasis-04.json)・[両包絡の数値](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/artifacts/spectra.json.gz)

プリエンファシスを外すことは、設計値を持つ対照ではF2の誤差を縮めた。この2録音では、F2の有効数を保ったまま選択極と行列の条件数を大きく変えた。録音の正解F2の注釈が無いため、これらの結果は推定条件に対する感度として扱う。

## 再現

同じ6窓を対象に、人が周波数と根拠を記録する資料を作成した。解析担当の照合表に両条件のLPC値を残し、判定者向けの波形・音声・スペクトログラムからは採択値を伏せた。[注釈資料と既知対照](tsp-f2-annotation.md#実測と保存先)

プリエンファシス0.97で次数だけを変えた追試では、`seems` の3窓すべてで約1 kHzの候補が根の推定段から消え、12次では約2.3 kHzを採った。`again` の移動は79 Hz未満だった。[固定した録音窓での次数対照](tsp-lpc-order-recordings.md#実測)

研究ワークスペースで実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_lpc_pre_emphasis_recordings.py tsp-lpc-pre-emphasis-recordings-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1を使用した。SciPyは録音WAVの補助チャンクを先行計測と同様に読み飛ばした。0.97条件と保存済みの極の最大差は `8.78×10⁻¹¹ Hz` 未満。12計算の固定Rustと独立計算の最大差は、係数で `9.75×10⁻¹¹` 未満、極の周波数・帯域幅で `3.14×10⁻⁹ Hz` 未満、LPC包絡で `3.14×10⁻¹⁰ dB` 未満、FFT対直接DFTで `7.05×10⁻¹² dB` 未満だった。

初回と `/private/tmp` からの再実行で各5判定と固定上流の基準試験1件が通過した。要約、圧縮スペクトル、6窓のRust出力がバイト一致し、保存データの前処理・自己相関・共通スペクトルのピーク・F2の変化を別に再集計した。一度のビルドで複数の窓を観測できるようにした後も、合成対照は4判定を通過し、既存の要約・スペクトル・Rust出力が一致した。3実行で93入力・25出力をサイズとSHA-256で確認し、採取物1,619,866バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-lpc-pre-emphasis-recordings-20261122-a/manifest.json)・[再実行](../runs/tsp-lpc-pre-emphasis-recordings-20261122-repeat/manifest.json)・[合成対照の回帰](../runs/tsp-lpc-pre-emphasis-20261122-batch-regression/manifest.json)
