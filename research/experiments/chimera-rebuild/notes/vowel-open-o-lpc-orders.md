# 連続母音列 /ɔ/ の固定窓でLPC次数を変える

前回は連続母音列の /ɔ/ で、0.375秒開始の100 msを16 kHzにした同じ入力に、12次と18次を適用した。12次は732.38 Hzを含む2ピーク、18次は619.47 Hzを含む8ピークを返した。今回は保存PCMからその窓を切り出し直し、先行実行の `lpc_28`・`lpc_29` とビット照合した。窓は元の48 kHz波形のフレーム162,000〜166,799。3点平均で16 kHzの1,600標本とし、プリエンファシス、窓関数、ラグ窓、帯域幅上限600 Hzを共通にしてLPC 12〜18次を実行した。 [事前登録](../cases/vowel-open-o-lpc-orders.json)・[先行実行の比較](vowel-open-o-lpc-matched.md#観測結果)

## 入口と係数の更新順序

上流の通常の `render::vowels` は較正済みの母音列を48 kHzで描画し、母音ごとの窓を `estimate_formants` に渡す。その通常入口で生成した保存波形を使い、解析は固定上流版の公開 `estimate_formants` を呼ぶ。計測プローブには周波数下限と帯域幅上限を指定できるようにし、今回の90 Hz・600 Hzを渡した。既存のTSPの呼び出しは150 Hz・600 Hzで別に再実行して照合した。 [通常レンダー](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L829)・[計測プローブ](../tools/upstream_tsp_lpc_pre_emphasis_probe.rs#L8)

入力 `x[n]` から `x[n] − 0.97 x[n−1]` を作り、Hamming窓を掛ける。自己相関はラグ `k` の標本積の和。40 Hzのガウス形のラグ窓で重みを掛け、Levinson–Durbinの係数と予測誤差を更新する。次数を `p−1` から `p` に上げると、反射係数 `k_p` は新しいラグと前の予測係数・誤差で決まる。新しい係数 `a_p[j]` は `a_(p−1)[j] + k_p a_(p−1)[p−j]`、最後の係数は `k_p`。予測誤差には `1 − k_p²` を掛ける。多項式の正の虚部を持つ根 `z` の偏角が周波数、半径の対数が帯域幅を定める。単位は `fs arg(z)/(2π)` と `−fs ln(|z|)/π` のどちらもHz。公開推定器は周波数と帯域幅で根を選別してから周波数順に返す。 [上流の自己相関と係数更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L7)・[上流の推定と選別](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)

独立計算では、各次数で重み済みの自己相関からToeplitz行列を組み、対角に上流と同じ微小補正を入れて連立方程式を解く。得られた多項式の根を、上流のDurand–Kernerによる根と複素平面上で一対一に対応させる。実軸付近は虚部の符号の丸めを記録し、正の虚部を持つ公開候補と区別する。400〜2,700 Hzの包絡も独立に評価する。上流のゴールデン試験では自己相関、係数、根、包絡、公開ピークを保存済みの値に照合する。 [ゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[今回の独立計算](../tools/measure_vowel_open_o_lpc_orders.py#L86)

## 観測結果

| LPC次数 | 第1公開ピーク | 850〜1,250 Hzの公開ピーク | 2,050〜2,675 Hzの根（周波数 / 帯域幅） | 公開ピーク総数 |
| ---: | ---: | ---: | ---: | ---: |
| 12 | 732.38 Hz | なし | 2,255.37 / 1,108.80 Hz（選別で除外） | 2 |
| 13 | 695.28 Hz | なし | 2,541.76 / 618.68 Hz（選別で除外） | 2 |
| 14 | 582.82 Hz | 934.71 Hz | 2,469.66 / 224.75 Hz | 6 |
| 15 | 569.64 Hz | 932.39 Hz | 2,429.55 / 158.74 Hz | 5 |
| 16 | 565.95 Hz | 928.83 Hz | 2,412.79 / 155.87 Hz | 4 |
| 17 | 603.34 Hz | 980.12 Hz | 2,439.80 / 69.41 Hz | 8 |
| 18 | 619.47 Hz | 999.11 Hz | 2,433.16 / 46.75 Hz | 8 |

12〜18次の端点で第1ピークは112.91 Hz下がった。帯域幅上限を外して同じ根を並べても第1ピークの差は112.91 Hz。最低周波数の採択点に現れる変化は根の推定段から生じた。850〜1,250 Hzは12・13次の選別前から該当根がなく、14次で934.71 Hzの根が現れた。2 kHz台の根は12・13次でも算出されており、600 Hzの上限で落ちた。1200 Hzを同じ根に適用する対照ではその2根が戻った。事前登録した3帯域すべてに公開ピークが揃ったのは14次が最初だった。 [全次数・選別前後の数値](../runs/vowel-open-o-lpc-orders-20261124-repeat/summary.json)

次数間で共通する自己相関と重み済みラグはビット一致した。13次から14次に上げると反射係数は0.43157で、共有する予測係数が最大0.37426変わった。隣接する次数の係数更新の独立計算との差は最大4.81×10⁻¹⁵。7条件105根の複素座標の差は最大3.30×10⁻¹³、公開ピークの最大差は1.45×10⁻¹⁰ Hz、LPC包絡の差は最大4.63×10⁻¹² dBだった。12次と18次の根・公開ピークは先行実行に一致した。4件の予測はすべて成立した。 [係数更新と独立計算の誤差](../runs/vowel-open-o-lpc-orders-20261124-repeat/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。事前登録のSHA-256は `c72b4147c0e849dfcbce5ceb4ea411c247cf2de294ee18387ee8352a9d22d8f6`。既存ビルドを使用し、一時領域込み256 MiBを見積もり、空き331 GiBとUUIDを照合したRTL9210B-CGに保存した。研究ワークスペースと `/tmp` からの2実行で各4判定、上流の解析ゴールデン試験に通過した。分析窓・7次数の上流の観測・要約はバイト一致した。TSPの既存プローブを既定のまま再実行した4判定も通過し、従来の上流観測、スペクトルと要約に一致した。 [初回](../runs/vowel-open-o-lpc-orders-20261124-registered/manifest.json)・[再実行](../runs/vowel-open-o-lpc-orders-20261124-repeat/manifest.json)・[既定値の回帰確認](../runs/tsp-lpc-pre-emphasis-20261124-order-probe-regression/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=268435456 \
  ../../.venv/bin/python tools/measure_vowel_open_o_lpc_orders.py vowel-open-o-lpc-orders-new
```
