# 共鳴が一定のときの倍音間隔とF2の観測

前回の注釈資料では、真のF2が2,075 Hzの合成対照で、波形の帯域ピークは2,126.95 Hzに出た。その対照の励振は12 kHzで96標本おきの周期インパルス、すなわち125 Hzだった。今回は同じ三つの共役極と入力パルスの振幅を使い、F0を100〜400 Hzの7条件に変える。帯域ピークとLPCの採択値がどの段で設計F2から離れるかを調べる。[事前登録](../cases/tsp-f2-harmonic-spacing.json)・[注釈の合成対照](tsp-f2-annotation.md#実測と保存先)

## 読解と比較方法

上流の `measure_pair` は対応した音素を人声・合成それぞれの `Sig` に渡す。`Sig::new` は48 kHzのPCMを低域通過させて12 kHzに間引く。`Sig::formants` は母音の35・50・65%に相当する各時刻を標本番号に変換し、300標本を切り出す。`estimate_formants` はプリエンファシス0.97、Hamming窓、自己相関、40 Hzのラグ窓、Levinson–Durbin法、根の計算の順に処理する。極の偏角を周波数、半径を帯域幅へ変換してHzで保持する。`Sig::formants` では帯域幅と周波数でF1を選び、それより200 Hz超かつ3,500 Hz未満にある最初の候補をF2として採る。上流の音素対応試験と `golden_analysis` の固定信号試験も実行する。[上流TSPの入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[LPCの推定](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[固定信号試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L94)

発声の代わりに、12 kHzの周期インパルス `x[n]` を同じ三つの二次節へ通す。二次節は周波数 `f` と帯域幅 `B` から `r = exp(−πB/fs)`、`θ = 2πf/fs` とし、分母を `1 − 2r cos(θ) z⁻¹ + r² z⁻²` とする。各節の状態は直前2標本の出力。始めは状態を0にし、定常部の末尾1周期を測る。1周期のDFTを取ると入力は各調波で同じ複素振幅を持つため、出力をパルスの振幅で割った値は伝達関数 `H(kF0)` に一致する。F0で変わるのは、固定された伝達関数を観測する周波数列 `kF0`。1,500〜2,500 Hzで最も強くなる倍音は、帯域内の連続曲線を最大にする周波数とは別に求める。[既知の極の設計](tsp-f2-bandwidth-known-poles.md)・[対照の実装](../tools/measure_tsp_f2_harmonic_spacing.py)

表示ピークには前回と同じ0.4〜0.6秒を使い、PCM16への変換と切り出しのあと、2 msごとに25 ms Hann窓の電力を求めて平均する。LPCの比較は従来と同じ300標本の浮動小数点波形を3窓使用し、固定上流の公開関数と独立のToeplitz解法に渡す。F2から120 Hz以内に候補が無い場合は推定段、近くの候補がある状態で別の極や欠測になった場合は採択段を最初の差として記録する。両方とも、上流内部の極の周波数と帯域幅を保存する。[固定上流の観測器](../tools/upstream_tsp_f2_envelope_probe.rs)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_harmonic_spacing.py tsp-f2-harmonic-spacing-new
```

## 実測

| F0（Hz） | 理論上の帯域内最強倍音（Hz） | 平均スペクトルのピーク（Hz） | LPCの採択範囲（Hz、2次数） |
| ---: | ---: | ---: | ---: |
| 100 | 2,100 | 2,097.66 | 2,081.29〜2,094.74 |
| 125 | 2,125 | 2,126.95 | 2,082.82〜2,099.73 |
| 150 | 2,100 | 2,097.66 | 2,085.28〜2,099.25 |
| 200 | 2,000 | 1,998.05 | 2,059.94〜2,061.73 |
| 240 | 2,160 | 2,162.11 | 2,127.21〜2,134.28 |
| 300 | 2,100 | 2,097.66 | 2,095.46〜2,114.06 |
| 400 | 2,000 | 1,998.05 | 1,998.13〜2,005.91 |

定常1周期のDFTから求めた応答は全7条件で理論値に一致し、最大絶対誤差を各条件の理論応答の最大振幅で規格化すると `5.11×10⁻¹⁵` 以下だった。平均スペクトルのピークは7条件すべてで理論上の最強倍音から2.35 Hz以内。ピークの全範囲は164.06 Hzで、変化はF0から決まる倍音の位置にすでに現れていた。125 Hzの波形、注釈資料のピーク、既存の6件の採択結果も再現した。[7条件・42計測の要約](../runs/tsp-f2-harmonic-spacing-20261122-a/summary.json)

固定上流のLPCは21窓×2次数の42件すべてでF2を返した。設計F2との差の最大は76.87 Hzで、400 Hz・12次で2,075 Hzに対して1,998.13 Hzを採った。120 Hzを超えるか欠測になるという事前予測は反証された。12次と14次を合わせた極と採択値は独立計算と最大 `1.86×10⁻¹⁰ Hz` 以内で一致した。この対照では単一の波形ピークをF2として読むと設計値から最大87.11 Hzずれる。実録音では個々の倍音の強さと時間方向に持続する帯を併せて比較する。ここで使った全極フィルタのF2の帯域幅は180 Hzで、実録音のF2の採否は未判定。[固定上流が返した極](../runs/tsp-f2-harmonic-spacing-20261122-a/artifacts/upstream-envelopes.json)・[帯域幅430 Hzの別対照](tsp-f2-bandwidth-known-poles.md#実測)

図の水平線は設計F2。三角の `kF₀` は帯域内で理論上最も強い倍音、×印は平均スペクトルの最大位置、色付きの点は各窓のLPC採択値。各次数の点は、同じF0内で見分けられるよう横方向に±3 Hzずらして描いた。[条件別の比較図](../runs/tsp-f2-harmonic-spacing-20261122-final-repeat/artifacts/f2-harmonics.png)

同じ7条件で幅430 Hzにすると、12次・15件で選別前からF2近傍の根が無かった。14次は21件すべてで設計F2の近くを採った。300 Hz未満の比較規則は、固定上流でF2近傍を採れたうち13件をF3へ移した。[幅を変えた追試](tsp-f2-harmonic-bandwidth.md#実測)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で測定した。研究ワークスペースと `/private/tmp` の再実行で各4判定、上流7試験を通過した。最終2実行は数値・波形・図など13出力がバイト一致した。初回の図と同じ数値を使用し、最終版では凡例を式と記号で表示した。前回の注釈資料の生成コードでは、実際は周期インパルスだった平均化対象をコメントで雑音励振としていたため訂正した。平均スペクトルの実装を共用した後も注釈資料と要約はバイト一致した。5実行の119入力・81出力を照合し、採取物6,670,421バイトをRTL9210B-CGに保存した。[最終実行](../runs/tsp-f2-harmonic-spacing-20261122-final/manifest.json)・[別ディレクトリでの再実行](../runs/tsp-f2-harmonic-spacing-20261122-final-repeat/manifest.json)・[注釈資料の回帰](../runs/tsp-f2-annotation-20261122-harmonic-regression/manifest.json)
