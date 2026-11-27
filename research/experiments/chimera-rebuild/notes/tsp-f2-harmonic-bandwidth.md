# 励振の7条件でF2の帯域幅を広げたときの推定と採択

前回はF2を2,075 Hz・幅180 Hzに固定し、F0を100〜400 Hzで変えた。今回はF0の7条件それぞれに対して、F2の帯域幅だけを430 Hzにした波形を追加する。F1・F3の極、F2の周波数、インパルスの振幅と開始位相、窓位置はそろえる。F2への対応は設計周波数の±120 Hzで判定する。[事前登録](../cases/tsp-f2-harmonic-bandwidth.json)・[幅180 Hzの先行対照](tsp-f2-harmonic-spacing.md#実測)

## 固定上流の読解と観測点

上流の `compare tsp` は `measure_pair` で録音と合成の対応音素を求め、`Sig::formants` は間引き後の12 kHz波形から母音の35・50・65%を中心に300標本ずつ採る。今回は12 kHzで作った1秒の波形に同じ相対時刻の窓を置く。LPCの前処理では係数0.97のプリエンファシス、Hamming窓、自己相関、40 Hzのラグ窓を順に適用する。Levinson–Durbin法は次数ごとに予測係数と残差を更新し、`poly_roots` が共役根を求める。上半平面の根の偏角は周波数、半径の対数は帯域幅へ変換する。両方の単位はHz。公開LPCは150 Hz以上かつ帯域幅600 Hz以下の極を通す。TSPはこの一覧からF1を選び、そのF1より200 Hz超かつ3,500 Hz未満の最初の極をF2とする。[比較入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓と採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[LPCと選別](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)

測定用の `--roots` は、公開推定器と同じ予測係数・反復数で根を求め、公開結果と一緒に保存する。NumPyで上半平面の根を周波数・帯域幅に戻して600 Hzの選別を再計算し、さらにToeplitzの直接解法で係数を求めた独立の結果と照合する。何も採れない場合と別の極を採った場合は、設計F2の近くの根があるか、公開リストにも残ったか、TSPが選んだかを順に調べる。比較用の300 Hz未満条件はF2を選ぶ時点だけに適用する。上流の固定信号試験とTSP比較試験も実行する。[観測用Rust](../tools/upstream_tsp_f2_envelope_probe.rs)・[研究CLI](../tools/measure_tsp_f2_harmonic_bandwidth.py)・[固定信号のLPC試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[TSP比較の欠測試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)

二次節は設計周波数 `f` と帯域幅 `B` から偏角 `2πf/fs`・半径 `exp(−πB/fs)` をもつ共役極を配置する。各節の状態は直前2標本の出力で、開始時は0。今回変えるのは中央の組の半径だけである。励振の位相が0に戻る時刻で定常1周期を切り出し、出力のDFTをインパルス振幅で割った値を同じ設計の複素伝達関数と全周波数ビンで照合した。[設計式と差分方程式](tsp-f2-bandwidth-known-poles.md#対照波形と測定)

## 実測

表の分母は帯域幅ごとに7種類のF0×3窓×2次数の42件。どちらの規則も全件で数値を返した。

| 設計F2の帯域幅 | 固定上流でF2に対応 | 追加の300 Hz未満条件でF2に対応 | 追加条件でF3に対応 |
| ---: | ---: | ---: | ---: |
| 180 Hz | 42 | 39 | 3 |
| 430 Hz | 27 | 14 | 28 |

幅430 Hzで固定上流の採択が外れた15件はすべて12次だった。F0は100、125、150、200、300 Hzで、各3窓の根は600 Hz上限を適用する前から設計F2の±120 Hzに無かった。14次では21件すべてに設計F2に対応する採択があった。追加の300 Hz未満条件で新たにF3へ移った13件はF0が100、125、150、240 Hzだった。240 Hzの12次・中央窓では、固定規則が2,151.77 Hz・幅523.97 Hzを選び、追加条件を掛けると2,896.64 Hzに移った。[窓ごとの候補と採択](../runs/tsp-f2-harmonic-bandwidth-20261122-a/summary.json)

幅180 Hzでも、F0が200 Hzの12次では3窓とも採択が2,059.94 Hzから2,933.33 Hzへ移った。このとき推定された対応極の帯域幅は371.64 Hz。逆に幅430 Hz・F0が400 Hzの12次では、対応極の推定帯域幅は298.53 Hzで条件を通過した。帯域幅300 Hz未満の規則は設計の共鳴幅だけでは採否を説明できず、どのF0とLPC次数で推定した幅かに依存した。[上流の根と予測係数](../runs/tsp-f2-harmonic-bandwidth-20261122-a/artifacts/upstream-envelopes.json)

両幅の定常1周期のDFTと理論応答の最大誤差は、理論振幅で規格化して `5.22×10⁻¹⁵` 以下。独立計算と比較した設計F2近傍の未選別極の差は最大 `1.14×10⁻⁹ Hz`、公開された極と採択値の差は最大 `2.40×10⁻¹⁰ Hz` 未満だった。幅180 Hzの全波形と42件の公開LPC結果、幅430 Hz・125 Hzの波形と6件の結果も、それぞれ保存実行と一致した。事前の3予測はいずれも成立した。実録音に対する固定規則の正誤は人による注釈がまだ無いため未測定。[実録音の注釈手順](tsp-f2-annotation.md#使い方)

## 再現

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_f2_harmonic_bandwidth.py tsp-f2-harmonic-bandwidth-new
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4、SciPy 1.17.1で実行した。研究ワークスペースからの初回と `/private/tmp` からの再実行で各5判定と固定上流7試験が通過し、波形、根、要約を含む4出力がバイト一致した。既存の細帯域・広帯域対照も `--roots` 無しで再実行し、5判定と固定上流1試験が通過し、先行の6出力とバイト一致した。3実行の78入力・19出力のサイズとSHA-256を照合し、採取物5,117,672バイトをRTL9210B-CGに保存した。[初回](../runs/tsp-f2-harmonic-bandwidth-20261122-a/manifest.json)・[再実行](../runs/tsp-f2-harmonic-bandwidth-20261122-repeat/manifest.json)・[既存対照の回帰](../runs/tsp-f2-known-poles-20261122-harmonic-bandwidth-regression/manifest.json)
