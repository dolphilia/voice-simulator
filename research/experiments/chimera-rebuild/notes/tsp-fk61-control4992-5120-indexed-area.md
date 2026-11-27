# FK61_01の代表面積を標本番号から直接補間する比較

[第88版の採取](tsp-fk61-control4992-5120-area-targets.md#実測)では、4992からの128回の加算で生じた丸めが、5120の節点29・34の開始面積の差を説明した。今回は下唇の評価式を上流に揃えた研究版を基準に、4992〜5119・5120〜5247の代表面積の計算だけを隔離ビルドで切り替える。女性設定のFK61_01、内部96 kHz、出力48 kHz。内部標本、PCMフレーム、節点番号は0始まり。

## 補間と体積源の更新順

通常テキストCLIは発話計画を組み、`HumanVoice::render` の制御境界で `control` が調音と接触補正を進める。上流の `AirwayNetwork::begin_block` は現在の面積 \(A_0\) と制御目標 \(A_t\) を受け、\(\delta A=(A_t-A_0)/N\) を設定する。研究版は `begin_tract_block` から `MovingAreas::set_targets` で同じ更新量を作る。この発話では \(N=128\)。反復加算では毎標本 \(A_k=\max(0,A_{k-1}+\delta A)\) を求める。改変では指定ブロックの開始時に \(A_0\) を保存し、標本位置 \(k=1,\ldots,N\) から \(A_k=\max(0,A_0+k\delta A)\) を求める。最終標本の目標を強制上書きする処理は加えていない。 [通常テキストCLI](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera-cli/src/render.rs#L179)・[上流の制御更新](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L495)・[上流の補間準備](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L708)・[研究版の目標設定](../crates/vocal-core/src/airway/human.rs#L341)・[研究版の補間](../crates/vocal-core/src/airway/network/geometry.rs#L47)

代表面積は cm²、セル長は cm、両者の積は cm³。最小面積を代表面積で上限処理した後、体積速度 \((V_{k-1}-V_k)/\Delta t\) を cm³/s で得る。配分・二段平滑した値が節点の体積源となる。枝流量は旧圧力で更新され、体積源と壁・枝の流量を合わせた後に節点圧を進める。口端流量と壁・鼻端の放射を合計し、差分・間引き・直流除去を経て `f32` PCMに変換する。 [上流の断面・体積速度・平滑](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L832)・[上流の音声出力](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L391)・[研究版の体積源](../crates/vocal-core/src/airway/network/geometry.rs#L110)

```mermaid
flowchart LR
    A["開始面積・目標・128標本"] --> B["代表面積の補間"]
    B --> C["体積差と二段平滑"]
    C --> D["枝流量・節点圧・口端負荷"]
    D --> E["間引きとPCM"]
```

上流の一様管試験・密閉圧縮試験・閉鎖移動試験は、体積と開口の変更時の応答を評価する。今回の2ビルドでは、声門ポートの即時更新中も他の幾何補間が進むことを研究版の試験で確認した。全発話PCMは観測なしの通常CLIでも照合した。 [上流の一様管試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway.rs#L49)・[上流の密閉空洞試験](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/airway_adversarial.rs#L56)・[研究版の補間試験](../crates/vocal-core/tests/geometry_ramp.rs)

## 比較条件

2ブロック計4箇所の開始値と目標値を採取し、各標本の面積を有理数 \(A_0+(A_t-A_0)k/N\) で独立に求める。各ブロックの終端残差と、5120の開始面積が固定上流にどの程度近いかを比較する。4990〜5875でセル体積と二段平滑、壁・枝・節点圧、口端負荷を照合し、0〜6143で放射の内訳と出力段を再計算する。さらに全発話の口端流量とPCMを保存して、最初と最大の差、PCMのRMSと差のあるフレーム数を比較する。 [事前登録](../cases/tsp-fk61-control4992-5120-indexed-area.json)・[計測器](../tools/measure_tsp_fk61_control4992_5120_indexed_area.py)

## 実測

直接補間した4箇所では全512標本の代表面積が、有理数の直線を `f64` へ丸めた値に一致した。終端面積は4箇所とも目標と一致した。標本ごとの直線からの最大偏差は2.220×10⁻¹⁶ cm²で、反復加算の最大2.798×10⁻¹⁴ cm²から減った。5120の上流との開始面積差の絶対値は節点29で5.684×10⁻¹⁴から2.931×10⁻¹⁴ cm²、節点34で4.530×10⁻¹⁴から1.732×10⁻¹⁴ cm²に減った。制御目標・最小面積・セル長は採取区間で両ビルド間で一致した。 [形状、体積源、音響の照合](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/summary.json)

両ビルドの最初の差は4993の節点29の面積で、同じ標本の体積と平滑後の体積源、枝29→30にも現れた。枝は節点の圧力更新に先立って新しい形状の係数を受け取る。口端流量の初差は5006。同じ音声の全発話を通じた口端流量の差は最大8.185×10⁻¹² cm³/sだった。 [局所と全発話の初差](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/summary.json)

| 全発話PCMの比較 | 最初に分かれたフレーム | 差のあるフレーム数 | 最大絶対差 | RMS差 |
| --- | ---: | ---: | ---: | ---: |
| 基準と固定上流 | 2937 | 2,355 | 1.862645×10⁻⁹ | 5.479255×10⁻¹² |
| 直接補間と固定上流 | 2937 | 2,355 | 1.862645×10⁻⁹ | 5.479264×10⁻¹² |
| 基準と直接補間 | 11599 | 14 | 7.275958×10⁻¹² | 2.853667×10⁻¹⁴ |

固定上流とのPCMの初差が遅くなるという予測は棄却した。変わった14フレームのうち6フレームは上流に近づき、8フレームは離れた。2937では直接補間により変換前の振幅が +1.537×10⁻¹⁶ 変化した。丸めの境界までの残差は1.395×10⁻¹⁴だった。局所の面積補間としては誤差が減ったため実験を残し、固定上流とのPCMの再現性を高める変更としては採用を見送る。 [RMSとフレーム2937の丸め](../runs/stage7-evidence-update-20261123-fk61-control4992-5120-indexed-area/summary.json)

同じ範囲の直接補間を上流の隔離ビルドにも適用すると、補間方式を揃えた比較で、目標面積や開始面積の違いに由来する体積速度と放射の差を追える。次は同じ2節点でその対照を採る。 [上流の面積加算](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L845)

## 再実行

固定上流 `c6147d0198890475dbe8a65a0bb8f56240c539b7`、macOS arm64、Rust 1.94.1、Python 3.14.4、NumPy 2.4.4。研究ワークスペースと `/tmp` でそれぞれ5判定と2ビルドの補間試験に通過した。両ビルドとも通常CLIと観測版で116,132フレームのPCMがビット一致した。2実行で採取系列・全発話PCM・隔離パッチ・要約など24出力がバイト一致した。採取系列と軌道の実体はRTL9210B-CGに保存した。 [初回マニフェスト](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-first/manifest.json)・[再実行マニフェスト](../runs/tsp-fk61-control4992-5120-indexed-area-20261123-repeat/manifest.json)

```bash
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=4294967296 \
  ../../.venv/bin/python tools/measure_tsp_fk61_control4992_5120_indexed_area.py tsp-fk61-control4992-5120-indexed-area-new
```
