# TSP実録音2語のLPC次数を12次・14次で比較する

既知の合成対照では、F2の帯域幅が430 Hzのとき、12次では2,075 Hz近傍の根を推定できなかった例があった。録音 `MK61_01` の `seems` と `FK61_01` の `again` では、先行実行でプリエンファシスだけでもF2の採択が変わった。今回はその実録音6窓を使って、次数を独立に変える。前処理の係数は固定上流の0.97、入力標本と窓位置は先行実行のままとした。[事前登録](../cases/tsp-lpc-order-recordings.json)・[既知の対照](tsp-f2-harmonic-bandwidth.md#実測)・[録音のプリエンファシス対照](tsp-lpc-pre-emphasis-recordings.md#実測)

## 固定上流の読解

`compare tsp` の `measure_pair` から `Sig::new` と `Sig::formants` をたどる。録音48 kHzを低域通過後に12 kHzへ間引き、対応付けられた母音の35・50・65%の時刻から300標本ずつ使う。今回の既定次数は `seems` が14次、`again` が12次だった。`estimate_formants` は、窓内の前標本を使うプリエンファシス、Hamming窓、自己相関、40 Hzのラグ窓、Levinson–Durbin再帰、根の探索の順で計算する。次数 `p` によって使う自己相関の遅れは0〜`p`、予測多項式は `1 + a₁z⁻¹ + … + aₚz⁻ᵖ`。再帰では反射係数でそれまでの予測係数と残差を更新するため、次数を増やすと先頭12係数も変わり得る。[録音の比較入口](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L803)・[窓・既定次数・採択](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L530)・[予測係数と残差の更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L28)

根の偏角と半径を周波数と帯域幅に変換する。ともに単位はHzで、公開推定結果は150 Hz以上かつ帯域幅600 Hz以下。TSP側はF1を先に選び、そのF1より200 Hz超かつ3,500 Hz未満の最初の候補をF2にする。根の一覧・公開結果・TSPの採択を別々に照合し、既定次数のF2から100 Hz未満の距離に候補が残るかを見る。変更次数の公開極を使い、F1だけを既定値で固定した再選択も計算する。これは既定次数の採択を参照した差の帰属であり、実録音の共鳴周波数を与える基準には使わない。[公開推定の条件](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/analysis/lpc.rs#L124)・[固定信号の試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/golden_analysis.rs#L186)・[比較で欠測を扱う試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/compare/tsp.rs#L1528)

## 比較と再現

先行のマニフェストで録音WAVとMFA境界を照合し、同じ窓の配列を12次と14次の両方に渡す。既定次数の係数・残差・生の根・公開極・包絡を先行の固定Rust出力と比較する。独立のToeplitz直接解法で正規方程式を解き、求めた多項式の根の周波数と帯域幅を固定上流と照合する。この研究用CLIは試聴資料の回答入力も製品の推定規則も変更せず、比較結果を実行ごとに保存する。[計測CLI](../tools/measure_tsp_lpc_order_recordings.py)・[固定上流の観測器](../tools/upstream_tsp_f2_envelope_probe.rs)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=134217728 \
  ../../.venv/bin/python tools/measure_tsp_lpc_order_recordings.py tsp-lpc-order-recordings-new
```

## 実測

| 録音 | 母音内の窓位置 | 12次の採択F2（Hz） | 14次の採択F2（Hz） |
| --- | ---: | ---: | ---: |
| `seems` | 35% | 2,291.35 | 986.41 |
| `seems` | 50% | 2,330.10 | 993.37 |
| `seems` | 65% | 2,317.88 | 993.17 |
| `again` | 35% | 2,145.60 | 2,066.96 |
| `again` | 50% | 2,073.45 | 2,002.22 |
| `again` | 65% | 2,024.75 | 1,978.85 |

`seems` は既定の14次から12次にすると、全3窓で採択F2が1,304.93〜1,336.73 Hz上がった。約1 kHzの既定の採択極から100 Hz未満の近傍には、公開LPCの選別を適用する前から根が無かった。F1を14次の値に固定して12次の候補から選び直しても、12次と同じ約2.3 kHzになった。変化は根の推定段ですでに生じていた。「大きく変わっても近傍の公開候補が残る窓がある」という予測は、この6窓では反証された。`again` は既定の12次から14次で45.90〜78.63 Hz低くなり、両語の全6窓で欠測は無かった。推定値がどの帯に対応するかを評価するための人手注釈は未取得。[窓別の選別と反実仮想](../runs/tsp-lpc-order-recordings-20261122-a/summary.json)・[判定者用ページ](../runs/tsp-f2-annotation-20261122-repeat/artifacts/review/index.html)

### 初回の不合格と照合方法の改訂

生の根を上半平面に限って並べる初版の比較では、`seems` の12次の50%・65%窓が不合格になった。固定上流では正の実根の虚部がそれぞれ `5.47×10⁻⁴⁸`、`2.74×10⁻⁴⁸` になり、独立計算ではどちらも0だった。50%窓では負の実根にも微小な正の虚部があった。初回から公開LPCの極と採択は独立計算に一致しており、実軸近傍の根は今回のF2変化に関与していなかった。[初回の全判定](../runs/tsp-lpc-order-recordings-20261122-a/summary.json)・[初回の複素根](../runs/tsp-lpc-order-recordings-20261122-a/artifacts/upstream-envelopes.json)

第2版では全根を複素平面で距離に基づいて一対一に対応付け、複素距離に加えて、偏角の絶対値と半径から求めた周波数・帯域幅を比較する。虚部の符号で採否が分かれた根の座標は別に保存する。前処理、公開LPCの極、F1/F2の結果とその許容差は同じ条件で再実行した。[第2版のケース](../cases/tsp-lpc-order-recordings.json)・[再実行の結果](../runs/tsp-lpc-order-recordings-20261122-repeat/summary.json)

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4で、研究ワークスペースと `/private/tmp` から第2版の各4判定と固定上流7試験が通過した。複素距離の最大は `8.90×10⁻¹³`、全根の周波数・帯域幅の差は最大 `2.01×10⁻⁸ Hz`、独立計算と採択値の差は最大 `7.75×10⁻¹¹ Hz`。要約、根、TSPの試験ログがバイト一致した。プリエンファシス比較の回帰は5判定・固定上流1試験が通過し、先行と要約・数値スペクトル・6件のRust出力が一致した。初回の不合格を含む4実行の136入力・25出力を照合し、採取物1,607,391バイトをRTL9210B-CGに保存した。WAVを読み込むとき、既存の補助チャンクをSciPyが読み飛ばす警告が出たが、6窓の既定次数の出力は先行計測と一致した。[第2版の実行](../runs/tsp-lpc-order-recordings-20261122-final/manifest.json)・[再実行](../runs/tsp-lpc-order-recordings-20261122-repeat/manifest.json)・[プリエンファシスの回帰](../runs/tsp-lpc-pre-emphasis-recordings-20261122-order-regression/manifest.json)
