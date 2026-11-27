# 肺ポートの持ち越し運動量を揃える

## 読解と事前の予測

上流の [`HumanAirway::new`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_airway.rs#L146) は肺の固定圧節点を気管入口へポートでつなぐ。面積は気管と同じで、長さは1 cm、抵抗には気管の特性インピーダンスの半分を足す。[`HumanVoice::render`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/voice/human_voice.rs#L371) は、前回の肺ポート流量 `U_prev`（cm³/s）の低域成分を更新し、追加抵抗分を補う圧を肺境界へ足してから気道を進める。研究版は [`Breath::step`](../crates/vocal-core/src/breath.rs#L121) で同じ順に境界圧を更新する。肺ポートの流量を今回変更しても、それが境界圧に戻るのは次の内部点以降となる。

上流の [`AirwayNetwork::step`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/src/airway/network.rs#L1029) は、固定径の肺ポートで前回運動量 `M_prev=L×U_prev` を保持し、`M_prev×Fs` を左右圧の差へ足す。慣性 `L` は g/cm⁴、`Fs` は内部サンプルレートなので持ち越し圧の単位は dyn/cm²。肺ポートでは二次損失係数をゼロに設定しており、駆動圧を `L×Fs + R` で割った値が今回の流量となる。この流量を気管入口セルの体積収支に加える。研究版の [`Branch::step`](../crates/vocal-core/src/airway/network.rs#L189) に先行実験で加えた持ち越し圧の上流順の計算を、[`HumanAirway::with_tract`](../crates/vocal-core/src/airway/human.rs#L224) が確定する肺ポート番号にも適用する。粘性抵抗と現時点の慣性の換算は対照の値を使う。

上流の [`a_fricative_keeps_the_lungs_pressure_at_its_folds`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L36) は摩擦音で声門直下の圧力が保たれることを、[`the_port_moves_neither_the_folds_pressure_nor_their_effort`](../../../../docs/reference/chimera-vocal-synth/upstream/crates/chimera/tests/lung_port.rs#L48) は母音の声門下圧と力みを検査する。今回は[先行の直列枝12本の比較](fixed-voice-tracheal-series-momentum-48000.md#末端圧の一致と肺声門ポートに残る差)で判明した8,202点目の肺ポート流量と8,207点目の入口圧を再度測り、声門に残る差と全PCMを照合する。対象、観測点、合否基準は実装前に固定した。[事前登録](../cases/fixed-voice-lung-port-momentum-48000.json)

## 肺境界から気管末端までの一致

出力48 kHz・内部96 kHzの固定 `/i/`、ゲート開放4,096・停止54,656出力フレーム目の条件で、通常CLIから描画した。対照は気管の直列枝12本と声門枝に先行の換算を適用した隔離ソースを復元し、観測とPCMを保存済み出力に照合した。その隔離ソースで、肺ポートの運動量換算だけを上流順にした。

8,201点目までの気管の流量と圧力は対照とビット一致した。8,202点目の肺ポート流量は対照の `1.1502244551555358` から上流の `1.150224455155536` cm³/s に、8,207点目の気管入口圧は `26.600287825200116` から上流の `26.60028782520012` dyn/cm² に一致した。肺境界圧、肺ポートを含む13枝の流量、気管13セルの更新後圧力は、観測した8,188〜8,239点目の全52点で上流とビット一致した。

声門流量は8,217点目で初めて分かれた。左右の圧力と持ち越し圧は両版で一致し、声門枝の慣性と抵抗を足した線形係数を上流値に置き換えると流量を再現した。同じ点の気管末端セルでは、声門への流出が研究版 `8.535131922566457×10⁻⁶`、上流 `8.535131922566455×10⁻⁶` cm³/s だった。流入と壁流出を含む収支の丸め後はどちらも `0.0031441156418226856` cm³/s で、更新後圧力は一致した。[残差の置換と実行要約](../runs/fixed-voice-lung-port-momentum-48000-a/summary.json)・[気管セルの観測CSV](../runs/fixed-voice-lung-port-momentum-48000-a/artifacts/reordered/candidate-path-node.csv)

| 固定上流とのPCM比較 | 直列枝12本の対照 | 肺ポートも変更 |
| --- | ---: | ---: |
| ビット差のある出力フレーム | 16 | 15 |
| 最初に差が出た出力フレーム | 61,467 | 60,225 |
| 最大絶対差 | 2.2737368×10⁻¹³ | 1.1368684×10⁻¹³ |

両版ともビット差はゲート停止後に限られ、最大絶対差は既存判定の `5×10⁻⁷` 以内だった。128・77の分割で全93,056フレームが一致した。次は声門のスリット抵抗だけを上流の計算順に変更し、8,217点目と停止後のPCMを同じ条件で比較する。

## 実行と検証

```bash
# 研究ワークスペースから実行
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  ../../.venv/bin/python tools/measure_fixed_voice_lung_port_momentum.py fixed-voice-lung-port-momentum-48000-a

# /tmp から再実行
experiment=/Users/dolphilia/github/voice-simulator/research/experiments/chimera-rebuild
CHIMERA_RUN_STORAGE=rtl9210b CHIMERA_RUN_BYTES=1073741824 \
  "$experiment/../../.venv/bin/python" "$experiment/tools/measure_fixed_voice_lung_port_momentum.py" \
  fixed-voice-lung-port-momentum-48000-repeat
```

macOS 15.6.1 arm64、Rust 1.94.1、Python 3.14.4で、各10判定と固定上流の各15試験に合格した。各実行の節点1,352点、気管枝1,352点、声門枝104点を有理数と十進数で独立に照合した。再実行間でPCM、観測CSV、差分、要約を含む20出力がバイト一致した。376入力と52出力をハッシュ照合し、採取物13,456,806バイトをRTL9210B-CGに保存した。[初回マニフェスト](../runs/fixed-voice-lung-port-momentum-48000-a/manifest.json)・[再実行マニフェスト](../runs/fixed-voice-lung-port-momentum-48000-repeat/manifest.json)・[独立照合](/Volumes/RTL9210B-CG/voice-simulator/scratch/verify-fixed-voice-lung-port-momentum-48000.json)
