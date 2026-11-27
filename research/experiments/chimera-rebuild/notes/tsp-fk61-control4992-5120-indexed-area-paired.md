# FK61_01の両版で代表面積の直接補間を揃える比較

[第89版](tsp-fk61-control4992-5120-indexed-area.md#実測)では、研究版の節点29・34に直接補間を適用し、終端面積の誤差が解消した。今回は固定上流の隔離ビルドにも同じ変更を加え、補間方式を揃えたときに残る差を見る。比較入力は女性設定のFK61_01で、研究版は下唇の評価式を上流に揃えた版を使う。内部96 kHz、出力48 kHz。節点・標本・フレームの番号は0始まり。

## 上流での開始値の保存と補間

通常の `render text` は英語の発話計画を `HumanVoice` に渡す。各制御境界で `control` が姿勢を更新し、接触補正後の断面と長さを `AirwayNetwork::begin_block` に渡す。通常はその時点の面積 \(A_0\) と次の目標 \(A_t\) から増分 \(\delta A=(A_t-A_0)/128\) を求め、標本ごとに前の面積へ足す。隔離ビルドでは4992・5120の境界で節点29・34の \(A_0\) を保存し、同じ増分から \(\max(0,A_0+k\delta A)\) を求める。位置 \(k\) は各ブロックの1〜128、面積と増分の単位は cm²。研究版の隔離ビルドは残り標本数から \(k\) を求め、上流版は内部標本の通算値から境界を引く。両方の演算は同じ順序の乗算と加算で行う。 [通常CLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[制御境界](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L495)・[上流の幾何補間](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[研究版の隔離パッチ](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/artifacts/indexed-area.patch)

体積は断面積とセル長の積で cm³。標本差から収縮を正とする体積速度を求める。上流では差に時間刻みの逆数を掛け、研究版では刻みで割る。配分後に一極フィルターを二段通し、節点の圧力更新へ使う。口端・鼻端・壁の放射を足した体積速度を差分してから、間引きと出力段を通してPCMにする。補間が揃っても、入力の面積目標、開始時の断面積、圧力・枝の状態、二段平滑の開始値、後段の演算差が残り得る。 [上流の体積速度と放射](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L832)・[研究版の体積速度](../crates/vocal-core/src/airway/network/geometry.rs#L110)・[上流の出力段](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L393)

```mermaid
flowchart LR
    A["上流と研究版の開始面積・目標"] --> B["反復加算・直接補間の4条件"]
    B --> C["面積・体積速度・平滑状態"]
    C --> D["口端流量と放射"]
    D --> E["全発話PCM"]
```

上流の一様管試験と気道の境界条件試験を両ビルドで実行し、通常CLIと観測版の全発話PCMを照合する。研究版の通常CLIと観測版を照合した第89版の出力をハッシュ検証して使う。直接補間の式は、有理数の直線を最後に `f64` へ丸めて別に計算する。 [上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[上流の気道試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の計測](tsp-fk61-control4992-5120-indexed-area.md#再実行)

## 比較条件

上流と研究版をそれぞれ反復加算・直接補間の2通りにし、組合せ4条件を比較する。節点29・34の2ブロック計512標本で面積、配分後の体積速度、第二極の差を計算する。採取した面積とセル長の積を有理数として計算した体積速度差で幾何の寄与を求め、観測した体積速度差から引いた残差も記録する。4990〜5875の局所力学、0〜6143の放射内訳・出力段、全発話の口端流量とPCMを比較する。 [事前登録](../cases/tsp-fk61-control4992-5120-indexed-area-paired.json)・[計測器](../tools/measure_tsp_fk61_control4992_5120_indexed_area_paired.py)

## 実測

上流の隔離ビルドでも512標本の代表面積が、有理数の直線を `f64` に丸めた値と一致した。4箇所の終端面積は目標と一致し、最大偏差は反復加算の2.798×10⁻¹⁴から2.220×10⁻¹⁶ cm²に減った。両版を直接補間にすると、対象区間の面積の最大差は4分の1、平滑後の体積速度のRMS差は約50分の1になった。5120の開始面積の差は節点29で1.776×10⁻¹⁵ cm²、節点34で1.066×10⁻¹⁴ cm²で、前ブロックの目標面積差と一致した。 [採取と4条件の結果](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/summary.json)

| 上流／研究版 | 対象区間の面積の最大差（cm²） | 体積速度のRMS差（cm³/s） | 平滑後のRMS差（cm³/s） | 全発話PCMのRMS差 | 差のあるPCMフレーム数 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 反復／反復 | 5.684×10⁻¹⁴ | 2.383×10⁻¹¹ | 1.674×10⁻¹² | 5.479255×10⁻¹² | 2,355 |
| 反復／直接 | 2.931×10⁻¹⁴ | 1.882×10⁻¹¹ | 8.351×10⁻¹³ | 5.479264×10⁻¹² | 2,355 |
| 直接／反復 | 2.931×10⁻¹⁴ | 1.931×10⁻¹¹ | 8.657×10⁻¹³ | 5.468595×10⁻¹² | 2,357 |
| 直接／直接 | 1.421×10⁻¹⁴ | 2.146×10⁻¹¹ | 3.315×10⁻¹⁴ | 5.468604×10⁻¹² | 2,355 |

直接／直接の最初の局所差は4992の節点29で、面積差は +4.441×10⁻¹⁶ cm²、体積速度差は −2.132×10⁻¹¹ cm³/sだった。全512標本で、面積と長さから丸めずに求めた体積速度差のRMSは1.670×10⁻¹¹ cm³/s、観測値との差のRMSは1.151×10⁻¹¹ cm³/sだった。両版それぞれの採取済みの体積差について、96,000を掛けた値と時間刻みで割った値は512標本で一致した。次の比較では、体積を作る積を丸めてから差を取る計算に着目する。 [体積源の再計算](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/summary.json)

上流内の2ビルドの比較では口端流量が5006で初めて分かれ、全発話PCMの初差は11629で、差のあるフレームは5だった。上流と研究版の比較では全4条件で口端の初差が3971、PCMの初差が2937に残った。両版を直接補間に揃えた条件では、2937の変換前の値の差が1.602×10⁻¹⁴から1.509×10⁻¹⁴に減った。両条件で上流と研究版の値は同じ丸め境界の両側にあった。全発話の口端流量のRMS差は8.969×10⁻¹²から8.972×10⁻¹² cm³/sだった。 [全発話の口端とPCM](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/artifacts/render.npz)・[研究版の対応出力](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/artifacts/render.npz)・[比較結果](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/summary.json)

次は両版を直接補間に揃えた状態で、同じ2節点・2ブロックに体積差の展開式を適用する。512標本の体積速度の丸め残差が減るか、第二極と出力まで変化が伝わるかを対照する。 [節点40での体積差の展開式](tsp-fk61-node40-expanded-volume.md)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。初回は上流の直接補間の差分が口端観測パッチの適用箇所に重なり、観測版の準備で停止した。標本カウンターの挿入位置を体積源の計算直前へ移し、観測パッチの適用とコンパイルを確認して再実行した。 [初回の失敗](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-first/manifest.json)・[上流の隔離パッチ](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/artifacts/upstream-indexed-area.patch)

修正後に研究ワークスペースと `/tmp` で再実行し、各4判定と上流の各ビルドのRust試験9件に通過した。各上流ビルドで通常CLI・観測版の全116,132フレームのPCMがビット一致し、2実行の採取・全発話出力・隔離パッチ・要約を含む24出力がバイト一致した。採取と全発話出力はRTL9210B-CGに保存した。 [修正後のマニフェスト](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-corrected/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-control4992-5120-indexed-area-paired-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control4992_5120_indexed_area_paired.py tsp-fk61-control4992-5120-indexed-area-paired-new
```
