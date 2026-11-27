# TSPの未使用10母音でのF2帯域幅条件

[前回の2語の調査](tsp-f2-bandwidth-envelope.md)で使った `MK61_01` の `plea` と `seems` を除き、録音・固定上流・研究版に共通する主強勢の単母音10か所を対象にした。母音内35・50・65%の窓を使うため、10か所×3生成元×3窓で計90窓となる。録音側10母音の内訳は /ʌ/ が4、/ɛ/ が4、/i/ が2。300 Hzは2語の調査から引き継いだ。追加欠測が生じるかと、どの生成元で採用極が変わるかを事前に登録した。[ケース定義](../cases/tsp-f2-bandwidth-held-out.json)

## 固定上流の読解

- `compare tsp` の `tsp::run` は `measure_pair` を通して録音と合成の音素をIPAで対応させ、両者に同じ主強勢判定を適用する。母音ごとの入力は48 kHz波形とMFAの開始・終了（秒）。`Sig::new` が発話全体を12 kHzに変換し、`measure` が単母音に対して `Sig::formants` を呼ぶ。中心時刻 `t0 + q × (t1 − t0)` を12 kHzの標本番号へ切り捨てて変換し、その番号の150標本前から300標本を使う。今回のMFA区間・波形・開始標本は、前回の記録と照合した。[CLIの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/main.rs#L95)・[音素対応と測定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L761)・[窓の選択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L528)
- `estimate_formants` は先行標本を0として係数0.97でプリエンファシスをかけ、Hamming窓、自己相関、40 Hzのラグ窓、Levinson–Durbin法、根の探索の順に処理する。LPCの反射係数・予測多項式・残差は次数を進めながら更新する。録音IDの話者に合わせ、F系列は12次、M系列は14次を使う。根の偏角と大きさからHz単位の周波数と帯域幅を求め、150 Hz以上かつ帯域幅600 Hz以下の極を周波数順に並べる。[LPC係数](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)・[固定の極の推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)
- 固定規則はF1を1300 Hz未満・帯域幅500 Hz未満で最初の極とし、F2をF1＋200 Hzより高く3500 Hz未満で最初の極とする。両方を採った窓だけが、その母音のF1・F2の中央値に入る。波形処理や極の計算を揃え、F2選択のときだけ帯域幅300 Hz未満を要求した。上流の試験は音素の対応、欠測の扱い、TypeScript由来のLPC基準と包絡を照合する。[採用規則](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L541)・[対応と欠測の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1529)・[包絡の基準試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)

## 照合

[確認用の研究CLI](../tools/measure_tsp_f2_bandwidth_held_out.py)は、録音PCM16と整列ノイズ添加前の両合成のfloat32を先行マニフェストで照合する。90窓で保存済みの固定Rustの極と独立LPCの極を比較し、両方に固定規則と帯域幅付き規則を適用する。ナイキスト上の負の実根との対応は[先行ケースの第2版](tsp-stressed-vowel-formants-held-out.md#初回の不一致と判定の改訂)の許容差を用いた。今回、該当したのは4窓で、いずれもF2の上限外だった。

極が最初に入れ替わった窓と移動が最大だった窓で、固定RustのLPC包絡と独立に計算した平滑化ピリオドグラムを採取した。固有の欠測が生じた場合も同じ手順で最初の窓を出す。LPC包絡は `lpc_envelope_db` と複素多項式の直接評価で照合し、ピリオドグラムはFFTとDFTの直接和で照合した。どちらも5 Hz刻みで、ピリオドグラムは先行ケースと同じく電力を標準偏差100 Hzのガウス核で平滑化した。採用極の周囲150 Hzから局所最大を照合した。[包絡の計算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L167)・[6窓の先行測定条件](tsp-f2-bandwidth-envelope.md#比較条件)

## 実測

| 生成元 | F2を保持 | 極を置換 | 追加欠測 | 条件追加後にF1・F2が揃った語 |
| --- | ---: | ---: | ---: | ---: |
| 録音 | 27 / 30 | 3 / 30 | 0 / 30 | 10 / 10 |
| 固定上流の合成 | 30 / 30 | 0 / 30 | 0 / 30 | 10 / 10 |
| 研究版の合成 | 30 / 30 | 0 / 30 | 0 / 30 | 10 / 10 |

置換はすべて録音 `FK61_01` の `again`（/ɛ/）だった。固定は2025–2146 Hz・帯域幅384–432 Hzの低い極を採った。条件を加えると、この極が外れ、2905–2938 Hz・帯域幅150–193 Hzの次の極を採った。3窓とも元の周波数条件に入る極はこの2つだけだった。最初の35%窓（開始標本23951）では、LPC包絡に2155 Hzと2930 Hz、平滑化ピリオドグラムに2205 Hzと2885 Hzの局所最大があった。移動が最大だった65%窓ではF2が880.24 Hz上がった。この窓でも両方の極の近くに各包絡の局所最大があった。差が現れた段はF2の帯域幅判定だった。[窓別の値](../runs/tsp-f2-bandwidth-held-out-20261122-repeat/summary.json)・[2窓の包絡データ](../runs/tsp-f2-bandwidth-held-out-20261122-repeat/artifacts/diagnostic-spectra.json)

この語では録音のF2中央値が2073.45 Hzから2913.42 Hzに変わり、固定上流と研究版の合成はそれぞれ2041.66 Hz・2036.16 Hzだった。研究版と録音の差は約37 Hzから877 Hzになった。元の極が近傍のピークを持つため、周波数差の増大には選択規則の影響が含まれる。録音の真の共鳴周波数は未確定。追加欠測があるという予測はこの90窓では成立せず、残る二つの予測は成立した。300 Hzはこの段階では感度を調べる条件として扱う。

## 再現

研究ワークスペースから実行する。

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_bandwidth_held_out.py tsp-f2-bandwidth-held-out-new
```

macOS 15.6.1 arm64、Python 3.14.4、rustc 1.94.1、NumPy 2.4.4、SciPy 1.17.1で実行した。録音WAVの補助チャンクは前回と同様にSciPyが読み飛ばした。90窓の極の最大差はナイキスト軸の照合後で `7.72×10⁻¹⁰ Hz` 未満、帯域幅条件の選択結果の最大差は `2.53×10⁻¹⁰ Hz` 未満。診断窓の包絡の差はLPCで `6.93×10⁻¹⁴ dB` 未満、平滑化ピリオドグラムで `2.03×10⁻¹² dB` 未満だった。

初回と `/private/tmp` からの再実行で各6判定、固定上流の基準試験1件が通過し、要約と両包絡の数値ファイルがバイト一致した。2診断窓の局所最大を保存データから再集計した。既存の2語はRustプローブに窓ごとの次数を加えた後も、7判定と4予測が成立し、要約・固定RustのJSON・圧縮CSV・図が既存実行と一致した。3実行の93入力・16出力をサイズとSHA-256で照合し、701,033バイトの採取物をRTL9210B-CGに保存した。[初回](../runs/tsp-f2-bandwidth-held-out-20261122-a/manifest.json)・[再実行](../runs/tsp-f2-bandwidth-held-out-20261122-repeat/manifest.json)・[既存2語の回帰](../runs/tsp-f2-bandwidth-envelope-20261122-order-regression/manifest.json)
