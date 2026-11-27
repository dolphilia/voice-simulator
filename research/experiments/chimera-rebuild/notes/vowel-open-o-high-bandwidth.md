# 固定母音 /ɔ/ の高域2ピークの3 dB帯域幅

基準10母音の固定姿勢の線形応答では、成人男性の /ɔ/ の約4,238 Hzと4,570 Hzで帯域幅が欠測だった。元の120〜4,600 Hz・700点の掃引、同じ上限で対数刻みを8分の1にした掃引、元の対数刻みのまま上限を約7,791 Hzに伸ばした掃引、その高密度版を比較した。元の固定姿勢、内部レート96 kHz、閉じた軟口蓋、気道の線形要素、咽頭入口への注入、声門ポートの切断と放射境界を共通にした。 [基準10母音の測定](ten-vowel-benchmark.md#結果)・[事前登録](../cases/vowel-open-o-high-bandwidth.json)

## 呼び出し元・観測点・判定手順

固定上流の `calibrate::formants` は姿勢を適用して、目標の断面積とセル長から `linear_elements` を組み立てる。各枝の抵抗と慣性から複素インピーダンス `Z=R+jωL`、節点の容積と圧縮率からコンプライアンスのアドミタンス `jωC` を求める。壁と口・鼻の放射負荷を各節点に加える。周波数ごとに木の末端から `Y/(1+ZY)` を親へ加算し、根に単位体積速度を注入したときの圧力を求め、親から子へ圧力・流量を復元する。口・鼻・壁の放射体積速度を複素数として合計した比 `H` を観測した。口・鼻・壁の比は単位なし。絶対値のレベルは `20 log₁₀|H|`、放射圧力に比例する別のレベルは `20 log₁₀(ω|H|)`。 [上流の較正入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/calibrate.rs#L138)・[線形要素](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1199)・[木の求解](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L24)

`find_peaks` は3点の対数振幅を放物線補間して、周波数とピークのレベルを推定する。そこから3.0 dB下がる最初の交点を左右に探し、それぞれを線形補間する。片側に交点がない場合、帯域幅を欠測にする。間に浅い谷や他のピークがあっても、レベルが指定値まで下がるまで探索を続ける。ゴールデン試験は、固定姿勢の応答、線形気道の対照、ピーク検出の境界ケースを収録している。研究版の通常の `vocal-cli transfer` と `inspect` を使い、上流の収録プローブも同じ4条件で動かした。 [上流のピーク検出](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/frequency.rs#L185)・[上流のゴールデン試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L92)・[研究CLI](../crates/vocal-cli/src/geometry_case.rs#L393)

独立計算では、木の消去を使わず、枝の両端の流量と節点の収支を複素行列に組み立てた。各グリッドの全周波数で解いて、口・鼻・壁・合計を照合した。さらに高密度グリッドでピークと左右の交点を挟み、区間内で連立方程式を新たな周波数ごとに解いて連続周波数のピーク、谷、交点を求めた。 [独立計算と再現CLI](../tools/measure_vowel_open_o_high_bandwidth.py)

## 測定結果

| 掃引上限 | 点数 | 低いピーク | 高いピーク |
| ---: | ---: | --- | --- |
| 4,600 Hz | 700 | 右側が欠測 | 右側が欠測 |
| 4,600 Hz | 5,593 | 右側が欠測 | 右側が欠測 |
| 7,790.62 Hz | 801 | 522.18 Hz | 109.06 Hz |
| 7,790.62 Hz | 6,401 | 524.96 Hz | 108.97 Hz |

上限だけを広げた801点の先頭700点は、元の周波数と最大3.19×10⁻¹² Hz、元の総放射振幅とピーク比1.06×10⁻¹³以内で一致した。4条件・計13,495点で、研究版と固定上流の総放射振幅の差はピーク比1.05×10⁻¹⁴以下、独立計算との複素応答の差は各成分のピーク比4.68×10⁻¹³以下。元の欠測2件を再現し、事前登録の予測は6件とも成立した。 [測定の要約](../runs/vowel-open-o-high-bandwidth-20261124-registered/summary.json)

| 独立計算 | ピーク周波数 | 左の交点 | 右の交点 | 交点間の幅 |
| --- | ---: | ---: | ---: | ---: |
| 低いピーク | 4,229.28 Hz | 4,209.25 Hz | 4,734.25 Hz | 525.00 Hz |
| 高いピーク | 4,570.47 Hz | 4,513.02 Hz | 4,621.99 Hz | 108.97 Hz |

ピーク間の谷は4,316.76 Hz、3.020 dB。これは低いピークの−3 dB水準1.679 dBより約1.34 dB高いため、525.00 Hzの幅には高いピークの頂点も入る。高いピークの108.97 Hzの幅は同ピークの両脇で閉じる。低いピークの位置は元の粗い掃引より9.06 Hz低く、刻みを8分の1にすると両ピークの交点が連続計算と最大0.035 Hzまで近づいた。交点の残差は最大2.49×10⁻¹³ dB。ピーク幅を比較する際、探索を打ち切った理由と、帯域内に隣接ピークを含むかを一緒に記録できる。 [連続周波数の交点と谷](../runs/vowel-open-o-high-bandwidth-20261124-repeat/summary.json)

## 実行と保存

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1を使用した。事前登録のSHA-256は `7ba2e8809bd9400aacc5b989c8750cd4d925b874db53fe81196420dc1d931817`。RTL9210B-CGのUUIDと書き込み権限を確認し、空き331 GiBの作業用ディスクへ直接保存した。見積もりは依存関係の既存ビルドを使う条件で512 MiB。研究ワークスペースと `/tmp` の両方から実行して、上流のゴールデン試験1件、研究版の一様管3試験と26判定が各実行で通過した。 [初回](../runs/vowel-open-o-high-bandwidth-20261124-registered/manifest.json)・[別ディレクトリからの再実行](../runs/vowel-open-o-high-bandwidth-20261124-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=536870912 \
  ../../.venv/bin/python tools/measure_vowel_open_o_high_bandwidth.py vowel-open-o-high-bandwidth-new
```
